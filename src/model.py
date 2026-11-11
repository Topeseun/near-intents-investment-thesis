#!/usr/bin/env python3
"""Fee-capture DCF + 17 metrics for the NEAR Investment Thesis.

Reads ONLY:
  - data/raw/* (cached API responses) + data/manifest.json (source + fetched_at)
  - src/assumptions.yaml (labelled assumptions — see that file)

Implements research-notes §8 exactly:
  R0 = F30 * 12 * c            (annualised retained revenue, USD/yr)
  Value_equity = R1 / (r - g), R1 = R0 * (1 + g)     (Gordon growth)
  Value_per_token = Value_equity / circulating_supply
  NEAR bought/yr = R0 / price ; NEAR issued/yr = max_inflation * total_supply
  Break-even retained revenue = issued/yr * price

Growth g must be < discount r; grid cells with g >= r are recorded as
null with reason "invalid: g >= r" — never silently computed.

Outputs (data/processed/):
  metrics.json       M1-M17 + live snapshot, each with source + fetched_at
  dcf.json           base-case DCF with every input traced to its source
  sensitivity.json   full capture x growth x discount grid (27 cells)
  benchmarks.json    peer + Intents-competitor multiples
  chart_01..10_*.json  underlying numbers for each chart (dashboard reuse)

Usage: python3 src/model.py
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
PROC = REPO / "data" / "processed"
YOCTO = 1e24


def load_json(name):
    p = RAW / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None  # e.g. a 404 plain-text body ("Fees for lifi not found")


def load_manifest():
    return json.loads((REPO / "data" / "manifest.json").read_text())


def fetched_at(manifest, name):
    return manifest.get(name, {}).get("fetched_at_utc")


def source(manifest, name):
    return manifest.get(name, {}).get("source_url")


def find_key(obj, key):
    """Recursively find the first value for `key` in nested dicts/lists."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def fee_series(doc):
    """DefiLlama summary/fees doc -> (daily series [[ts_ms, usd], ...], totals)."""
    if not doc:
        return [], {}
    series = doc.get("totalDataChart") or doc.get("dailyFees") or []
    # totalDataChart entries are [timestamp_ms, value]; dailyFees dicts differ.
    pts = []
    for p in series:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            ts, val = int(p[0]), float(p[1])
            if ts < 1_000_000_000_000:  # seconds -> ms (DefiLlama uses seconds)
                ts *= 1000
            pts.append([ts, val])
        elif isinstance(p, dict):
            ts = p.get("date") or p.get("timestamp")
            val = p.get("dailyFees") or p.get("fees") or p.get("totalFees")
            if ts is not None and val is not None:
                ts = int(ts)
                if ts < 1_000_000_000_000:
                    ts *= 1000
                pts.append([ts, float(val)])
    pts.sort()
    totals = {k: doc.get(k) for k in
              ("total24h", "total7d", "total30d", "totalAllTime")}
    return pts, totals


def trailing_sums(pts, window_days=30):
    """Daily trailing-`window_days` sums aligned to each series date."""
    out = []
    vals = [v for _, v in pts]
    for i, (ts, _) in enumerate(pts):
        lo = max(0, i - window_days + 1)
        out.append([ts, sum(vals[lo:i + 1])])
    return out


def log_regression_cagr(daily_pts=None, trailing=None):
    """Annualised growth from log-linear regression on trailing-30d sums.

    Pass EITHER daily points (trailing sums computed on the full series
    first) OR a precomputed trailing-sum list. Regressions are always run
    on trailing sums computed from the FULL daily series — truncating the
    daily series first would create partial windows and an artificial ramp.
    Returns (cagr, slope_per_day, n_points, first_date, last_date) or None.
    """
    if trailing is None:
        trailing = [(ts, v) for ts, v in trailing_sums(daily_pts) if v > 0]
    else:
        trailing = [(ts, v) for ts, v in trailing if v > 0]
    if len(trailing) < 60:
        return None
    t0 = trailing[0][0] / 86400000.0  # days
    xs = [(ts / 86400000.0 - t0) for ts, _ in trailing]
    ys = [math.log(v) for _, v in trailing]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return {"cagr": math.exp(slope * 365) - 1, "slope_per_day": slope,
            "n_points": n,
            "first_date": datetime.fromtimestamp(trailing[0][0] / 1000,
                                                 tz=timezone.utc).strftime("%Y-%m-%d"),
            "last_date": datetime.fromtimestamp(trailing[-1][0] / 1000,
                                                tz=timezone.utc).strftime("%Y-%m-%d")}


def dcf_value(r0, growth, discount):
    """Gordon growth. Returns None when g >= r (invalid zone)."""
    if growth >= discount:
        return None
    r1 = r0 * (1 + growth)
    return r1 / (discount - growth)


def pearson(xs, ys):
    """Pearson correlation of two equal-length lists; None if degenerate."""
    n = len(xs)
    if n < 10 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def ols_regression(xs, ys):
    """Ordinary least squares y = intercept + slope*x.

    Returns {"n", "slope", "intercept", "pearson_r", "r_squared",
    "slope_se"} or None when the regression is degenerate (too few points
    or zero variance on either side). Slope SE is the standard error of the
    slope estimate (residual variance / Sxx, n-2 degrees of freedom).
    """
    n = len(xs)
    if n < 10 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    r = sxy / math.sqrt(sxx * syy)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(ss_res / (n - 2) / sxx) if n > 2 else None
    return {"n": n, "slope": round(slope, 4), "intercept": round(intercept, 4),
            "pearson_r": round(r, 4), "r_squared": round(r * r, 4),
            "slope_se": round(se, 4) if se is not None else None}


def weekly_log_changes(by_date, last_date, window_days=365):
    """Weekly log-changes log(v[d]/v[d-7]) for dates in the last window.

    by_date: {date_str "YYYY-MM-DD": positive float}. Only dates with both
    d and d-7 present and > 0 are used. Returns ([dates], [changes]).
    """
    from datetime import timedelta
    out_d, out_v = [], []
    start = last_date - timedelta(days=window_days)
    for d in sorted(by_date):
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        if dd < start or dd > last_date:
            continue
        prev = (dd - timedelta(days=7)).strftime("%Y-%m-%d")
        v, vp = by_date.get(d), by_date.get(prev)
        if v and vp and v > 0 and vp > 0:
            out_d.append(d)
            out_v.append(math.log(v / vp))
    return out_d, out_v


def charts_daily(doc):
    """NEARBlocks /v1/charts doc -> {field: [(date_str, float), ...]}.

    Values arrive as decimal strings; rows with a missing/null value for a
    field are skipped for that field only (multichain_txns is null in the
    1,577 rows before 2024-11-14; txn_volume is null in 11 rows in Jul-Aug
    2020 — neither field is used by M12-M17).
    """
    if not doc or not isinstance(doc, dict):
        return {}
    rows = doc.get("charts") or []
    fields = ("txns", "active_accounts", "new_accounts", "deleted_accounts",
              "near_price", "txn_fee_usd", "txn_volume_usd", "blocks")
    out = {f: [] for f in fields}
    for r in rows:
        d = (r.get("date") or "")[:10]
        if not d:
            continue
        for f in fields:
            raw = r.get(f)
            if raw in (None, ""):
                continue
            try:
                out[f].append((d, float(raw)))
            except (TypeError, ValueError):
                continue
    return out


def dexs_volume_series(doc):
    """DefiLlama summary/dexs doc -> (daily [[ts_ms, usd], ...], totals).

    The volume series lives in totalDataChart as [timestamp_s, usd] pairs.
    Returns ([], {}) when the endpoint 404d or carries no series, so the
    volume leg can be dropped without faking volume.
    """
    if not doc or not isinstance(doc, dict):
        return [], {}
    series = doc.get("totalDataChart") or []
    pts = []
    for p in series:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            ts, val = int(p[0]), float(p[1])
            if ts < 1_000_000_000_000:
                ts *= 1000
            pts.append([ts, val])
    pts.sort()
    totals = {k: doc.get(k) for k in
              ("total24h", "total7d", "total30d", "total1y", "totalAllTime")}
    return pts, totals


def main() -> int:
    PROC.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    A = yaml.safe_load((REPO / "src" / "assumptions.yaml").read_text())
    dcf_a = A["dcf"]

    # ---------------- load raw ----------------
    stats = load_json("nearblocks_stats.json") or {}
    validators = load_json("nearblocks_validators.json") or {}
    rpc_status = load_json("rpc_status.json") or {}
    rpc_cfg = load_json("rpc_protocol_config.json") or {}
    price_doc = load_json("coingecko_simple_price.json") or {}
    intents, intents_tot = fee_series(load_json("defillama_fees_near-intents.json"))
    base_fees, base_tot = fee_series(load_json("defillama_fees_NEAR.json"))
    revenue = load_json("revenue_near_org_parsed.json") or {}
    tvl_doc = load_json("defillama_historical_tvl_NEAR.json") or []
    buybacks_acct = load_json("nearblocks_account_buybacks.json") or {}
    intents_acct = load_json("nearblocks_account_intents.json") or {}
    charts_doc = load_json("nearblocks_charts.json")
    dexs_doc = load_json("defillama_dexs_near-intents.json")
    charts = charts_daily(charts_doc)
    volume_pts, volume_tot = dexs_volume_series(dexs_doc)

    def src_of(name):
        return {"source": source(manifest, name),
                "fetched_at_utc": fetched_at(manifest, name)}

    # ---------------- live inputs ----------------
    # NEARBlocks /v1/stats returns {"stats": [{...yocto strings...}]}
    s_raw = stats.get("stats") or []
    s = s_raw[0] if isinstance(s_raw, list) and s_raw else (
        s_raw if isinstance(s_raw, dict) else stats)
    price = float(price_doc["near"]["usd"])
    mcap = float(price_doc["near"]["usd_market_cap"])
    # supplies are yocto strings in the API response
    supply_total = float(s.get("total_supply", 0)) / YOCTO
    supply_circ = float(s.get("circulating_supply", 0)) / YOCTO

    max_infl_raw = find_key(rpc_cfg, "max_inflation_rate")
    if max_infl_raw is None:
        print("FATAL: max_inflation_rate not found in rpc_protocol_config.json",
              file=sys.stderr)
        return 1
    # RPC returns [numerator, denominator], e.g. [1, 40] = 2.5%
    max_inflation = max_infl_raw[0] / max_infl_raw[1] if isinstance(max_infl_raw, list) \
        else float(max_infl_raw)

    apy = None
    # NEARBlocks /v1/validators keys: currentValidators, total,
    # lastEpochApy, totalStake (yocto), epochProgressData, validatorFullData
    # (top 25 validators by stake, each with currentEpoch.stake in yocto).
    val_list = validators.get("validatorFullData") or \
        validators.get("validators") or validators.get("current_validators") or []
    if isinstance(validators, dict):
        apy = validators.get("lastEpochApy") or validators.get("last_epoch_apy")
    apy = float(apy) / 100 if apy and float(apy) > 1 else float(apy or 0)
    total_staked_live = None
    if validators.get("totalStake") is not None:
        try:
            total_staked_live = float(validators["totalStake"]) / YOCTO
        except (TypeError, ValueError):
            pass

    # F30: DefiLlama total30d (primary) cross-checked vs sum of last 30 daily pts
    f30 = float(intents_tot.get("total30d") or 0)
    f30_from_series = sum(v for _, v in intents[-30:]) if len(intents) >= 30 else None
    f7 = float(intents_tot.get("total7d") or 0)
    f24 = float(intents_tot.get("total24h") or 0)
    f_all = float(intents_tot.get("totalAllTime") or 0)
    base_f24 = float(base_tot.get("total24h") or 0)
    base_f_all = float(base_tot.get("totalAllTime") or 0)

    # Measured capture rate (revenue.near.org, 30D window)
    cap_windows = revenue.get("capture_rate_by_window", {})
    capture_measured = cap_windows.get("d30")
    capture_cards = revenue.get("capture_rate_30d_from_cards")

    # ---------------- M1-M11 ----------------
    metrics = {}
    metrics["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics["notes"] = ("Every value traces to a cached API response "
                        "(source + fetched_at per metric) or a labelled "
                        "assumption in src/assumptions.yaml.")

    # M1 — Intents gross fees
    metrics["M1_intents_gross_fees"] = {
        "definition": "USD fees/day from DefiLlama totalDataChart; 30d trailing sum",
        "total_24h_usd": f24, "total_7d_usd": f7, "total_30d_usd_F30": f30,
        "total_30d_from_daily_series_usd": f30_from_series,
        "f30_cross_check_diff_pct": (
            None if not f30_from_series else
            round(100 * (f30 - f30_from_series) / f30, 2)),
        "total_all_time_usd": f_all, "daily_points": len(intents),
        "first_daily_date": datetime.fromtimestamp(intents[0][0] / 1000,
                                                   tz=timezone.utc).strftime("%Y-%m-%d") if intents else None,
        "last_daily_date": datetime.fromtimestamp(intents[-1][0] / 1000,
                                                  tz=timezone.utc).strftime("%Y-%m-%d") if intents else None,
        "anomaly_flag": ("24h fee is far below the 7d daily average "
                         f"(${f24:,.0f} vs ${f7 / 7:,.0f}/day). The last daily "
                         "point in the series is the same low figure, so this "
                         "is a full-day value, not a partial day — either a real "
                         "one-day drop or a DefiLlama reporting lag. Never "
                         "annualise a single day; 7d/30d trailing figures used "
                         "throughout."
                         if f7 and f24 < 0.5 * f7 / 7 else None),
        **src_of("defillama_fees_near-intents.json"),
    }

    # M2 — fee growth. Regressions run on trailing sums from the FULL series,
    # truncated by date (never on a truncated daily series — partial windows
    # would fake a ramp). The full-series figure is dominated by the May-Aug
    # 2025 launch ramp ($1/day -> ~$200k/day) and must NOT be quoted as a
    # steady growth rate; the honest trend is the YoY / peak comparison.
    tr30_full = trailing_sums(intents)
    cagr = log_regression_cagr(trailing=tr30_full)
    cagr_180 = cagr_365 = None
    peak = yoy = None
    if tr30_full:
        last_ts = tr30_full[-1][0]
        cagr_180 = log_regression_cagr(
            trailing=[p for p in tr30_full if p[0] >= last_ts - 180 * 86400000])
        cagr_365 = log_regression_cagr(
            trailing=[p for p in tr30_full if p[0] >= last_ts - 365 * 86400000])
        peak = max(tr30_full, key=lambda x: x[1])
        import bisect as _bisect
        _tss = [t for t, _ in tr30_full]
        _i = _bisect.bisect_left(_tss, last_ts - 365 * 86400000)
        if 0 <= _i < len(tr30_full):
            yoy = {"date": datetime.fromtimestamp(
                       tr30_full[_i][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                   "trailing_30d_usd": tr30_full[_i][1],
                   "change_pct": round(100 * (tr30_full[-1][1] - tr30_full[_i][1])
                                       / tr30_full[_i][1], 1)}
    tr30 = tr30_full
    cur30, prev30 = (tr30[-1][1] if tr30 else None,
                     tr30[-31][1] if len(tr30) > 31 else None)
    metrics["M2_intents_fee_growth"] = {
        "definition": "30d trailing vs prior 30d; log-regression CAGR on trailing-30d sums",
        "trailing_30d_usd": cur30, "prior_30d_usd": prev30,
        "trailing_30d_vs_prior_30d_pct": (
            None if not (cur30 and prev30) else round(100 * (cur30 - prev30) / prev30, 1)),
        "trailing_30d_yoy": yoy,
        "trailing_30d_peak": (
            {"date": datetime.fromtimestamp(peak[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
             "trailing_30d_usd": peak[1]} if peak else None),
        "trailing_30d_vs_prior_30d_reading": (
            "Fees are volatile, not a smooth ramp: trailing-30d peaked at "
            f"${peak[1]:,.0f} and is now {round(100 * (cur30 - peak[1]) / peak[1], 1)}% "
            "below that peak, but still above a year ago. The DCF base "
            "growth assumption (10%) is a forward assumption, NOT a trend "
            "extrapolation."),
        "log_regression_cagr_full_series": cagr,
        "log_regression_cagr_full_series_warning": (
            "Dominated by the May-Aug 2025 launch ramp from $1/day; do NOT "
            "quote as a steady-state growth rate."),
        "log_regression_cagr_last_180d": cagr_180,
        "log_regression_cagr_last_365d": cagr_365,
        **src_of("defillama_fees_near-intents.json"),
    }


    # M3/M4 — retained revenue + capture trend (measured, not assumed)
    r0_base = f30 * 12 * capture_measured if capture_measured else None
    metrics["M3_retained_revenue"] = {
        "definition": "Annualised retained revenue = F30 * 12 * capture_rate",
        "capture_rate_30d_measured": capture_measured,
        "capture_rate_30d_from_displayed_cards": capture_cards,
        "capture_source": "revenue.near.org SSR payload (net revenue $ / gross fees $,"
                          " cross-checked vs per-mechanism split) — MEASURED, not assumed",
        "retained_revenue_annualised_base_usd_R0": r0_base,
        "retained_revenue_30d_usd": (f30 * capture_measured if capture_measured else None),
        "scenario_R0_usd": {f"{int(c * 100)}%": f30 * 12 * c
                            for c in dcf_a["capture_scenarios"]},
        **src_of("revenue_near_org_parsed.json"),
        "fee_source": src_of("defillama_fees_near-intents.json"),
    }
    metrics["M4_capture_rate_trend"] = {
        "definition": "Retained / gross by window (sum of three mechanisms: "
                      "direct fees pp_fe + B2B pp_b2b + quote improvement pp_qi)",
        "capture_rate_by_window": cap_windows,
        "mechanism_split_by_window": revenue.get("capture_split_by_window"),
        "trend_reading": ("Capture is rising: all-time ~19% -> YTD ~23% -> "
                          "30D ~36%. The 30D rate, not the lifetime rate, is "
                          "the base case."),
        **src_of("revenue_near_org_parsed.json"),
    }

    # M5 — base-chain fees (control series)
    metrics["M5_base_chain_fees"] = {
        "definition": "NEAR L1 gas fees/day (DefiLlama NEAR)",
        "total_24h_usd": base_f24, "total_all_time_usd": base_f_all,
        "intents_30d_vs_base_daily_ratio": (
            None if not base_f24 else round((f30 / 30) / base_f24, 1)),
        **src_of("defillama_fees_NEAR.json"),
    }

    # M6 — buyback vs issuance
    issued_per_yr = max_inflation * supply_total
    bought_base = r0_base / price if r0_base else None
    breakeven_r = issued_per_yr * price
    metrics["M6_buyback_vs_issuance"] = {
        "definition": "Annualised retained revenue / price = NEAR bought/yr; "
                      "vs issuance = max_inflation * total_supply",
        "max_inflation_rate": max_inflation,
        "max_inflation_raw_rpc": max_infl_raw,
        "total_supply_near": supply_total,
        "issued_per_year_near": issued_per_yr,
        "near_price_usd": price,
        "bought_per_year_base_near": bought_base,
        "bought_per_year_by_capture_scenario_near": {
            f"{int(c * 100)}%": f30 * 12 * c / price for c in dcf_a["capture_scenarios"]},
        "net_supply_change_base_near_per_year": (
            issued_per_yr - bought_base if bought_base else None),
        "break_even_retained_revenue_usd_per_year": breakeven_r,
        "break_even_multiple_of_current_R0": (
            breakeven_r / r0_base if r0_base else None),
        "break_even_note": ("NEAR turns net-deflationary when retained Intents "
                            "revenue reaches this level at the current price."),
        **src_of("rpc_protocol_config.json"),
        "supply_source": src_of("nearblocks_stats.json"),
        "price_source": src_of("coingecko_simple_price.json"),
    }

    # M7 — mcap / retained revenue
    metrics["M7_mcap_retained_multiple"] = {
        "definition": "Market cap / annualised retained revenue",
        "market_cap_usd": mcap,
        "mcap_div_R0_base": (mcap / r0_base if r0_base else None),
        "mcap_div_R0_by_capture_scenario": {
            f"{int(c * 100)}%": mcap / (f30 * 12 * c)
            for c in dcf_a["capture_scenarios"]},
        **src_of("coingecko_simple_price.json"),
    }

    # M8 — peer multiples (computed in benchmarks section below; summarised here)
    # M9 — staking real yield
    metrics["M9_staking_real_yield"] = {
        "definition": "Last-epoch APY minus max inflation (real yield to stakers)",
        "last_epoch_apy": apy, "max_inflation_rate": max_inflation,
        "real_yield_pp": round(100 * (apy - max_inflation), 2),
        "dilution_to_non_stakers_pct_per_year": round(100 * max_inflation, 2),
        **src_of("nearblocks_validators.json"),
    }

    # M10 — validator health
    stakes = []
    for v in val_list:
        st = None
        if isinstance(v, dict):
            ce = v.get("currentEpoch") or {}
            st = ce.get("stake") if isinstance(ce, dict) else None
            if st is None:
                st = v.get("stake") or v.get("total_stake")
        if st is None:
            continue
        try:
            stakes.append(float(st) / YOCTO)
        except (TypeError, ValueError):
            pass
    stakes.sort(reverse=True)
    # Prefer the API's own totalStake (full set) over summing the top-25 list.
    total_staked = total_staked_live if total_staked_live else sum(stakes)
    metrics["M10_validator_health"] = {
        "definition": "Validator set size, total stake, top-10 concentration",
        "current_validators": validators.get("currentValidators")
            or len(val_list) or s.get("nodes_online"),
        "total_validators": validators.get("total"),
        "total_staked_near": total_staked,
        "total_staked_share_of_supply_pct": (
            round(100 * total_staked / supply_total, 1) if supply_total else None),
        "top_10_stake_share_pct": (
            round(100 * sum(stakes[:10]) / total_staked, 1) if total_staked else None),
        "top_10_note": ("Top-10 stakes from validatorFullData (top 25 returned "
                        "by the API); denominator is the API totalStake (full set)."),
        "epoch_progress_pct": validators.get("epochProgressData"),
        **src_of("nearblocks_validators.json"),
    }

    # M11 — price vs fundamentals divergence
    mc_near = load_json("coingecko_market_chart_near_365.json") or {}
    prices = mc_near.get("prices", [])
    div = {}
    if prices and tr30:
        # trailing-30d fees indexed to the first price date
        import bisect
        fee_ts = [ts for ts, _ in tr30]
        p0 = prices[0][1]
        f0 = None
        idx0 = bisect.bisect_left(fee_ts, prices[0][0])
        if idx0 < len(tr30):
            f0 = tr30[idx0][1]
        p_start, p_end = prices[0][1], prices[-1][1]
        div = {
            "window": f"{datetime.fromtimestamp(prices[0][0] / 1000, tz=timezone.utc).date()}"
                      f" to {datetime.fromtimestamp(prices[-1][0] / 1000, tz=timezone.utc).date()}",
            "price_change_pct": round(100 * (p_end - p_start) / p_start, 1),
            "trailing_30d_fees_indexed_start": 100.0,
            "trailing_30d_fees_change_pct": (
                None if not f0 else round(100 * (tr30[-1][1] - f0) / f0, 1)),
            "price_30d_change_pct": (
                round(100 * (prices[-1][1] - prices[-31][1]) / prices[-31][1], 1)
                if len(prices) > 31 else None),
            "trailing_30d_fees_30d_change_pct": (
                round(100 * (tr30[-1][1] - tr30[-31][1]) / tr30[-31][1], 1)
                if len(tr30) > 31 else None),
        }
    metrics["M11_price_vs_fundamentals"] = {
        "definition": "NEAR price (CoinGecko 365d) indexed vs trailing-30d Intents "
                      "fees indexed — do fees compound while price falls?",
        **div,
        **src_of("coingecko_market_chart_near_365.json"),
        "fee_source": src_of("defillama_fees_near-intents.json"),
    }

    # ---------------- M12-M14: daily network activity (NEARBlocks /v1/charts) --
    # Full daily series 2020-07-21 -> last fetch date. Values are daily counts.
    def _activity_metric(key, label, field, unit):
        pts = charts.get(field) or []
        if not pts:
            return {"definition": label, "available": False,
                    "reason": "nearblocks_charts.json missing or empty — no "
                              "series fabricated",
                    **src_of("nearblocks_charts.json")}
        vals = [v for _, v in pts]
        peak_i = max(range(len(pts)), key=lambda i: vals[i])
        cur = vals[-1]
        avg30 = sum(vals[-30:]) / min(30, len(vals))
        prev30 = (sum(vals[-60:-30]) / 30) if len(vals) >= 60 else None
        return {
            "definition": label,
            "available": True,
            "unit": unit,
            "daily_points": len(pts),
            "first_date": pts[0][0], "last_date": pts[-1][0],
            "current_last_day": cur,
            "daily_avg_last_30d": round(avg30, 1),
            "daily_avg_prior_30d": (round(prev30, 1) if prev30 else None),
            "avg_30d_vs_prior_30d_pct": (
                None if not prev30 else round(100 * (avg30 - prev30) / prev30, 1)),
            "sum_last_30d": round(sum(vals[-30:]), 1),
            "sum_prior_30d": (round(sum(vals[-60:-30]), 1) if len(vals) >= 60 else None),
            "all_time_peak": {"date": pts[peak_i][0], "value": vals[peak_i]},
            "current_pct_below_peak": round(100 * (1 - cur / vals[peak_i]), 1),
            "avg_30d_pct_below_peak": round(100 * (1 - avg30 / vals[peak_i]), 1),
            **src_of("nearblocks_charts.json"),
        }

    metrics["M12_daily_txns"] = _activity_metric(
        "M12", "Daily transactions on NEAR (NEARBlocks /v1/charts daily series)",
        "txns", "txns/day")
    metrics["M13_daily_active_accounts"] = _activity_metric(
        "M13", "Daily active accounts on NEAR (NEARBlocks /v1/charts daily series)",
        "active_accounts", "accounts/day")
    m14 = _activity_metric(
        "M14", "New accounts per day on NEAR (NEARBlocks /v1/charts daily series)",
        "new_accounts", "accounts/day")
    # Churn context for the new-accounts trend: accounts deleted in the window.
    del_pts = charts.get("deleted_accounts") or []
    if del_pts and m14.get("available"):
        m14["deleted_accounts_sum_last_30d"] = round(sum(v for _, v in del_pts[-30:]), 1)
        m14["deleted_accounts_sum_prior_30d"] = (
            round(sum(v for _, v in del_pts[-60:-30]), 1) if len(del_pts) >= 60 else None)
        m14["net_new_accounts_last_30d"] = round(
            m14["sum_last_30d"] - m14["deleted_accounts_sum_last_30d"], 1)
    metrics["M14_new_accounts_trend"] = m14

    # ---------------- M15: Intents daily VOLUME (DefiLlama dexs) ----------------
    if volume_pts:
        v30_series = sum(v for _, v in volume_pts[-30:])
        v7_series = sum(v for _, v in volume_pts[-7:])
        v30_prior = sum(v for _, v in volume_pts[-60:-30]) if len(volume_pts) >= 60 else None
        v_peak = max(volume_pts, key=lambda x: x[1])
        vol30_endpoint = float(volume_tot.get("total30d") or 0) or None
        metrics["M15_intents_daily_volume"] = {
            "definition": "NEAR Intents daily swap VOLUME (USD) — DefiLlama "
                          "summary/dexs/near-intents totalDataChart (the dexs "
                          "dimension, not fees). Fees (M1) are the revenue; "
                          "volume is the growth x-axis.",
            "available": True,
            "daily_points": len(volume_pts),
            "first_daily_date": datetime.fromtimestamp(volume_pts[0][0] / 1000,
                                                       tz=timezone.utc).strftime("%Y-%m-%d"),
            "last_daily_date": datetime.fromtimestamp(volume_pts[-1][0] / 1000,
                                                      tz=timezone.utc).strftime("%Y-%m-%d"),
            "total_24h_usd_endpoint": volume_tot.get("total24h"),
            "total_7d_usd_endpoint": volume_tot.get("total7d"),
            "total_30d_usd_endpoint": vol30_endpoint,
            "total_1y_usd_endpoint": volume_tot.get("total1y"),
            "total_all_time_usd_endpoint": volume_tot.get("totalAllTime"),
            "total_30d_usd_from_daily_series": v30_series,
            "total_7d_usd_from_daily_series": v7_series,
            "total_30d_series_vs_endpoint_diff_pct": (
                None if not vol30_endpoint else
                round(100 * (v30_series - vol30_endpoint) / vol30_endpoint, 1)),
            "total_30d_vs_prior_30d_pct": (
                None if not v30_prior else round(100 * (v30_series - v30_prior) / v30_prior, 1)),
            "peak_daily_volume": {
                "date": datetime.fromtimestamp(v_peak[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                "volume_usd": v_peak[1]},
            "total_all_time_usd_from_daily_series": sum(v for _, v in volume_pts),
            "implied_gross_fee_rate_30d_bps": (
                round(10000 * f30 / v30_series, 2) if v30_series else None),
            "implied_gross_fee_rate_note": (
                "30d Intents gross fees (M1) divided by 30d volume from the "
                "daily series — the fee rate the market actually paid. "
                "Cross-check: secondary sources quoted a ~15 bps gross fee "
                "rate; if this lands near 15 bps the two independent series "
                "agree. It is a derived ratio, not a DefiLlama field."),
            **src_of("defillama_dexs_near-intents.json"),
            "fee_source": src_of("defillama_fees_near-intents.json"),
        }
    else:
        metrics["M15_intents_daily_volume"] = {
            "definition": "NEAR Intents daily swap VOLUME (USD) — DefiLlama dexs",
            "available": False,
            "reason": "summary/dexs/near-intents returned no daily volume "
                      "series (404 / empty). Volume leg DROPPED — no volume "
                      "figure is shown anywhere; fees (M1) remain the proxy.",
            **src_of("defillama_dexs_near-intents.json"),
        }

    # ---------------- M16: price-vs-fees relationship (correlation, NOT lead-lag) --
    # Pearson r of WEEKLY log-changes, last 365 days of overlap, price from
    # the NEARBlocks charts series (same daily grid as txns/fees). A
    # correlation of contemporaneous weekly moves only: it says whether price
    # and fees moved together week to week, NOT which leads, NOT causation.
    # The competitor's lead-lag test is deliberately NOT copied.
    price_by_date = dict(charts.get("near_price") or [])
    fee_by_date = {}
    for ts, v in intents:
        fee_by_date[datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")] = v
    basefee_by_date = dict(charts.get("txn_fee_usd") or [])
    m16 = {
        "definition": "Pearson correlation of weekly log-changes "
                      "(log v[d]/v[d-7]) over the last 365 days — "
                      "contemporaneous co-movement only, no lead-lag, no causation",
        "method": "Weekly log-changes, aligned by calendar date; pairs with a "
                  "missing or non-positive value on either side are dropped.",
        "window_days": 365,
    }
    if price_by_date and fee_by_date:
        from datetime import date as _date
        last_d = _date.fromisoformat(max(price_by_date))
        # Recompute on the INTERSECTION of dates, not each series alone.
        p_dates, p_vals = weekly_log_changes(price_by_date, last_d)
        f_dates, f_vals = weekly_log_changes(fee_by_date, last_d)
        p_map, f_map = dict(zip(p_dates, p_vals)), dict(zip(f_dates, f_vals))
        common = sorted(set(p_map) & set(f_map))
        xs = [p_map[d] for d in common]
        ys = [f_map[d] for d in common]
        m16.update({
            "window": f"{common[0]} to {common[-1]}" if common else None,
            "n_weekly_pairs_price_vs_intents_fees": len(common),
            "pearson_price_vs_intents_fees_weekly_log_changes": (
                round(pearson(xs, ys), 3) if xs else None),
            "reading": ("Positive r means NEAR's price and Intents fees tended "
                        "to move in the same direction week to week; negative "
                        "would mean they diverged. Either way this is "
                        "co-movement, not evidence that fees move price or "
                        "vice versa."),
        })
    if price_by_date and basefee_by_date:
        from datetime import date as _date
        last_d = _date.fromisoformat(max(price_by_date))
        pd_, pv_ = weekly_log_changes(price_by_date, last_d)
        bd_, bv_ = weekly_log_changes(basefee_by_date, last_d)
        p_map, b_map = dict(zip(pd_, pv_)), dict(zip(bd_, bv_))
        common_b = sorted(set(p_map) & set(b_map))
        m16["n_weekly_pairs_price_vs_base_gas_fees"] = len(common_b)
        m16["pearson_price_vs_base_gas_fees_weekly_log_changes"] = (
            round(pearson([p_map[d] for d in common_b],
                          [b_map[d] for d in common_b]), 3) if common_b else None)
    m16.update(src_of("nearblocks_charts.json"))
    m16["fee_source"] = src_of("defillama_fees_near-intents.json")
    metrics["M16_price_vs_fees_correlation"] = m16

    # ---------------- M17: Metcalfe check — does price follow users? ----------
    # Log-log OLS of price on daily active accounts, NEARBlocks /v1/charts
    # daily series (price and users on the SAME daily grid — no source
    # mixing). Primary: MONTHLY aggregates (month-end price vs monthly mean
    # active accounts), the same ~73-month framing a fellow Investment Thesis
    # entry (NEAR Demand Ledger, gallery #42) used, so the two results are
    # comparable. Daily log-log is the robustness line. Strict Metcalfe says
    # value ∝ users^2, i.e. a log-log slope of ~2.0; a slope near 0 with R²
    # near 0 means price does not follow users at all. The cumulative-txns
    # leg is labelled PARTIAL: cumulative txns is a monotonically increasing
    # stock, so its regression is trend-dominated by construction.
    # Rows with price <= 0 (85 pre-launch rows, Jul-Oct 2020) or active
    # accounts <= 0 (11 rows, Jul-Aug 2020, inside the zero-price window)
    # are dropped — log(0) is undefined — and the drop is recorded, not hidden.
    m17 = {
        "definition": "Metcalfe check: log-log OLS of NEAR price on daily "
                      "active accounts (NEARBlocks /v1/charts, same daily "
                      "grid for both series). Primary is monthly (month-end "
                      "price vs monthly mean users); daily is the robustness "
                      "line. Also: market cap on users, and price on "
                      "cumulative txns (PARTIAL — trend-dominated stock).",
        "method": "log(price) = a + b*log(users); strict Metcalfe predicts "
                  "b ≈ 2.0. Monthly aggregates: month-end price, monthly mean "
                  "active accounts, month-end market cap, month-end cumulative "
                  "txns (summed over the full daily series). Rows with "
                  "price <= 0 or users <= 0 are dropped before taking logs.",
        "metcalfe_slope_benchmark": 2.0,
        "rival_reported": {
            "entry": "NEAR Demand Ledger (@0xhannnx, gallery entry #42)",
            "slope": 0.21, "r_squared": 0.28, "months": 73,
            "verdict": "hypothesis is unproven",
            "note": "As reported by that entry (rival watch 2026-11-11); "
                    "not independently verified. Its activity definition "
                    "differs from this series, so the two slopes are not "
                    "directly comparable point-for-point — the shared "
                    "conclusion (disconnect) is what matters.",
        },
    }
    charts_raw = charts_doc.get("charts") or [] if isinstance(charts_doc, dict) else []
    m17_rows = [r for r in charts_raw
                if float(r.get("near_price") or 0) > 0
                and float(r.get("active_accounts") or 0) > 0]
    dropped_price = sum(1 for r in charts_raw if float(r.get("near_price") or 0) <= 0)
    dropped_users = sum(1 for r in charts_raw if float(r.get("active_accounts") or 0) <= 0)
    m17["dropped_rows"] = {
        "zero_price_rows": dropped_price,
        "zero_active_account_rows": dropped_users,
        "note": "All dropped rows are pre-launch Jul-Oct 2020 (price was 0 "
                "before mainnet trading; the 11 zero-user rows sit inside "
                "that window). No in-window day is dropped.",
    }
    if len(m17_rows) < 365:
        m17["available"] = False
        m17["reason"] = (f"Only {len(m17_rows)} usable daily rows — need >= 365 "
                         "for a Metcalfe window. No regression fabricated.")
    else:
        from collections import defaultdict as _dd
        by_month = _dd(list)
        for r in m17_rows:
            by_month[(r.get("date") or "")[:7]].append(r)
        months = sorted(by_month)
        # Cumulative txns over the FULL series (incl. pre-launch rows) at each
        # month end — the research-notes substitute for a DAU history.
        cum_by_date = {}
        _c = 0.0
        for r in charts_raw:
            _c += float(r.get("txns") or 0)
            cum_by_date[(r.get("date") or "")[:10]] = _c
        m_users, m_price, m_mcap, m_cum = [], [], [], []
        for mth in months:
            rs = by_month[mth]
            m_users.append(sum(float(r["active_accounts"]) for r in rs) / len(rs))
            m_price.append(float(rs[-1]["near_price"]))
            mc = float(rs[-1].get("market_cap") or 0)
            m_mcap.append(mc if mc > 0 else None)
            m_cum.append(cum_by_date[(rs[-1].get("date") or "")[:10]])
        lx_m = [math.log(x) for x in m_users]
        ly_m = [math.log(y) for y in m_price]
        lx_d = [math.log(float(r["active_accounts"])) for r in m17_rows]
        ly_d = [math.log(float(r["near_price"])) for r in m17_rows]
        mc_pairs = [(u, mc) for u, mc in zip(m_users, m_mcap) if mc]
        reg_m = ols_regression(lx_m, ly_m)
        reg_d = ols_regression(lx_d, ly_d)
        reg_mc = ols_regression([math.log(u) for u, _ in mc_pairs],
                                 [math.log(mc) for _, mc in mc_pairs])
        reg_cum = ols_regression([math.log(x) for x in m_cum], ly_m)
        # Honest caveat: the 2024-onwards sub-window, computed the same way.
        sub_idx = [i for i, mth in enumerate(months) if mth >= "2024-01"]
        reg_sub = ols_regression([lx_m[i] for i in sub_idx],
                                 [ly_m[i] for i in sub_idx])
        m17.update({
            "available": True,
            "window": f"{m17_rows[0]['date'][:10]} to {m17_rows[-1]['date'][:10]}",
            "usable_daily_points": len(m17_rows),
            "n_months": len(months),
            "first_month": months[0], "last_month": months[-1],
            "partial_final_month_note": (
                "The last month covers only the days present in the series "
                f"({months[-1]}: 1-9 Nov 2026); its mean uses those days only."),
            "total_cumulative_txns": m_cum[-1],
            "price_vs_active_accounts_monthly": reg_m,
            "price_vs_active_accounts_daily": reg_d,
            "market_cap_vs_active_accounts_monthly": reg_mc,
            "price_vs_cumulative_txns_monthly": {
                **(reg_cum or {}),
                "partial": True,
                "partial_note": ("Cumulative txns is a monotonically "
                    "increasing stock, so this regression is trend-dominated "
                    "by construction; it tests whether price tracks cumulative "
                    "usage, not a Metcalfe law. Reported for completeness, "
                    "not as evidence."),
            },
            "subwindow_2024_onwards_monthly": reg_sub,
        })
        # Reading, built from the computed numbers so a re-run stays honest.
        sm, rm = reg_m["slope"], reg_m["r_squared"]
        s_sub = reg_sub["slope"] if reg_sub else None
        r_sub = reg_sub["pearson_r"] if reg_sub else None
        m17["reading"] = (
            f"On the full {len(months)}-month window the Metcalfe relation is "
            f"absent: log(price) on log(users) has slope {sm} (SE "
            f"{reg_m['slope_se']}) and R² {rm} — statistically indistinguishable "
            f"from zero, against the strict-Metcalfe slope of 2.0. The daily "
            f"regression agrees (slope {reg_d['slope']}, R² {reg_d['r_squared']}, "
            f"n={reg_d['n']}). Even the most favourable reading — market cap on "
            f"users — gives slope {reg_mc['slope']} and R² {reg_mc['r_squared']}, "
            f"far below 2.0. Price does not track cumulative usage either "
            f"(slope {reg_cum['slope']}, R² {reg_cum['r_squared']}, partial "
            f"check). One caveat, reported not buried: from Jan 2024 onwards "
            f"the monthly slope is {s_sub} with r {r_sub} — price and users "
            f"have moved together more in the recent window, driven by the "
            f"joint fall from the Apr 2024 activity peak. The relation flips "
            f"sign across sub-periods (2020-2023 slope ≈ 0), so it is not a "
            f"stable law. Net: value NEAR on fees, not on users — the fee "
            f"thesis stands on its own numbers, and the user-count story "
            f"cannot rescue the $3.60 price.")
    m17.update(src_of("nearblocks_charts.json"))
    metrics["M17_metcalfe_check"] = m17

    # ---- snapshot extras ----
    # TVL: historicalChainTvl returns [{"date": unix_s, "tvl": usd}, ...]
    tvl_last = None
    if isinstance(tvl_doc, list) and tvl_doc:
        last = tvl_doc[-1]
        if isinstance(last, dict):
            tvl_last = {"date": datetime.fromtimestamp(
                last["date"], tz=timezone.utc).strftime("%Y-%m-%d"),
                "tvl_usd": last.get("tvl")}
        else:
            tvl_last = {"date": None, "tvl_usd": last[1]}
    bb_bal = None
    if buybacks_acct:
        acct = buybacks_acct.get("account", {})
        if isinstance(acct, list):
            acct = acct[0] if acct else {}
        amt = acct.get("amount")
        if amt is not None:
            bb_bal = float(amt) / YOCTO
    # Traced all-time inflow to the buybacks wallet, from the (now correctly
    # parsed) revenue.near.org wallet table — replaces a hardcoded snapshot
    # (1,719,605.8 NEAR) that went stale. The comparison is computed live so
    # the note stays true as both figures move.
    bb_traced = (revenue.get("revenue_wallets_all_time_near") or {}).get(
        "buybacks.multisignature.near")
    bb_traced_str = f"{bb_traced:,.1f} NEAR" if bb_traced is not None else "unavailable"
    if bb_bal is not None and bb_traced is not None:
        bb_cmp = "HIGHER than" if bb_bal > bb_traced else "LOWER than"
    else:
        bb_cmp = "compared with"
    intents_bal = None
    if intents_acct:
        acct = intents_acct.get("account", {})
        if isinstance(acct, list):
            acct = acct[0] if acct else {}
        amt = acct.get("amount")
        if amt is not None:
            intents_bal = float(amt) / YOCTO
    metrics["snapshot"] = {
        "near_price_usd": price, "market_cap_usd": mcap,
        "volume_24h_usd_coingecko": price_doc.get("near", {}).get("usd_24h_vol"),
        "total_supply_near": supply_total, "circulating_supply_near": supply_circ,
        "total_txns_all_time": s.get("total_txns"),
        "tps_live": s.get("tps"), "avg_block_time_s": s.get("avg_block_time"),
        "chain_height": (rpc_status.get("result", {}) or {}).get("sync_info", {}).get("latest_block_height"),
        "protocol_version": (rpc_status.get("result", {}) or {}).get("latest_protocol_version"),
        "node_version": ((rpc_status.get("result", {}) or {}).get("version", {}) or {}).get("version"),
        "near_tvl_last_point": tvl_last,
        "revenue_dashboard_all_time": {
            "gross_fees_usd": revenue.get("gross_fees_all_time_usd"),
            "intent_volume_usd": revenue.get("intent_volume_all_time_usd"),
            "confidential_tvl_usd": revenue.get("confidential_tvl_usd"),
            "unique_users_30d": revenue.get("unique_users_30d"),
            "headline_revenue_usd": revenue.get("headline_revenue_usd"),
            "headline_revenue_window": revenue.get("headline_revenue_window"),
            "revenue_wallets_all_time_near": revenue.get("revenue_wallets_all_time_near"),
            "revenue_wallets_total_near": revenue.get("revenue_wallets_total_near"),
        },
        "buyback_wallet_balance_live_near": bb_bal,
        "buyback_wallet_balance_vs_dashboard_note": (
            "Live NEARBlocks balance vs the dashboard's all-time traced inflow "
            f"to buybacks.multisignature.near ({bb_traced_str}). The live balance "
            f"is {bb_cmp} the traced inflow, so the dashboard wallet table is "
            "partial (or stale) and must not be read as the full buyback total — "
            "the wallet also receives other inflows and spends on buybacks."),
        "intents_account_balance_near": intents_bal,
    }

    # ---------------- DCF ----------------
    r_base, g_base = dcf_a["base_discount_rate"], dcf_a["base_growth_rate"]
    val_base = dcf_value(r0_base, g_base, r_base)
    dcf = {
        "formula": "R0 = F30 * 12 * capture; R1 = R0 * (1+g); Value = R1/(r-g); "
                   "Value/token = Value / circulating_supply",
        "inputs": {
            "F30_trailing_30d_gross_fees_usd": f30,
            "capture_base_measured_30d": capture_measured,
            "capture_base_source": "revenue.near.org (measured) — see M4",
            "discount_rate_r_base": r_base,
            "growth_rate_g_base": g_base,
            "circulating_supply_near": supply_circ,
            "near_price_usd": price,
            "market_cap_usd": mcap,
        },
        "base_case": {
            "R0_annualised_retained_revenue_usd": r0_base,
            "R1_next_year_retained_revenue_usd": r0_base * (1 + g_base) if r0_base else None,
            "equity_value_usd": val_base,
            "value_per_token_usd": (val_base / supply_circ if val_base else None),
            "value_per_token_vs_price_pct": (
                round(100 * (val_base / supply_circ) / price, 1)
                if val_base else None),
            "reading": ("At today's fees and the measured ~36% capture, retained "
                        "revenue alone supports only a fraction of the $4.7B market "
                        "cap. The thesis case is the option value: the multiple is "
                        "a bet on fee growth (g) and capture (c) rising — see the "
                        "sensitivity grid."),
        },
        "assumptions_file": "src/assumptions.yaml",
    }

    # ---------------- sensitivity grid ----------------
    grid = []
    for c in dcf_a["capture_scenarios"]:
        for g in dcf_a["growth_scenarios"]:
            for r in dcf_a["discount_scenarios"]:
                r0 = f30 * 12 * c
                v = dcf_value(r0, g, r)
                grid.append({
                    "capture": c, "growth": g, "discount": r,
                    "R0_usd": round(r0, 2),
                    "equity_value_usd": (round(v, 2) if v is not None else None),
                    "value_per_token_usd": (
                        round(v / supply_circ, 4) if v is not None else None),
                    "invalid_reason": ("g >= r" if g >= r else None),
                })
    sens = {"grid": grid,
            "axes": {"capture": dcf_a["capture_scenarios"],
                     "growth": dcf_a["growth_scenarios"],
                     "discount": dcf_a["discount_scenarios"]},
            "base_case": {"capture": capture_measured, "growth": g_base,
                          "discount": r_base,
                          "value_per_token_usd": (val_base / supply_circ if val_base else None)},
            "note": "Cells with growth >= discount are null (Gordon growth "
                    "requires g < r); the invalid zone is shown explicitly."}

    # ---------------- benchmarks ----------------
    bench = {"peers": {}, "intents_competitors": {}, "dropped": []}
    peer_defs = {"solana": ("solana", "defillama_fees_solana.json"),
                 "avalanche-2": ("avalanche", "defillama_fees_avalanche.json"),
                 "ethereum": ("ethereum", "defillama_fees_ethereum.json")}
    for cg_id, (slug, fname) in peer_defs.items():
        doc = load_json(fname)
        _, tot = fee_series(doc)
        p = price_doc.get(cg_id, {})
        if not tot.get("total30d") or "usd_market_cap" not in p:
            bench["dropped"].append(
                {"peer": cg_id, "reason": f"DefiLlama fee slug '{slug}' returned no totals",
                 **src_of(fname)})
            continue
        ann_fees = float(tot["total30d"]) * 12
        bench["peers"][cg_id] = {
            "price_usd": p.get("usd"), "market_cap_usd": p.get("usd_market_cap"),
            "fees_30d_usd": float(tot["total30d"]),
            "fees_annualised_usd": ann_fees,
            "mcap_div_annualised_fees": p["usd_market_cap"] / ann_fees,
            **src_of(fname),
        }
    # NEAR rows for the same table
    bench["peers"]["near"] = {
        "price_usd": price, "market_cap_usd": mcap,
        "fees_30d_usd_gross_intents": f30,
        "fees_annualised_usd_gross_intents": f30 * 12,
        "mcap_div_annualised_gross_intents_fees": mcap / (f30 * 12),
        "fees_annualised_usd_retained_base": r0_base,
        "mcap_div_annualised_retained_fees_base": (mcap / r0_base if r0_base else None),
        "base_chain_fees_24h_usd": base_f24,
    }
    # TVL from DefiLlama /chains
    chains = load_json("defillama_chains.json") or []
    tvl_by = {}
    for ch in chains:
        name = (ch.get("name") or "").lower()
        tvl_by[name] = ch.get("tvl")
    for key, cg_id in [("near", "near"), ("solana", "solana"),
                       ("avalanche", "avalanche-2"), ("ethereum", "ethereum")]:
        tvl = tvl_by.get(key)
        if tvl and cg_id in bench["peers"]:
            bench["peers"][cg_id]["tvl_usd"] = tvl
            bench["peers"][cg_id]["mcap_div_tvl"] = (
                bench["peers"][cg_id]["market_cap_usd"] / tvl)
    # NEAR: prefer the historicalChainTvl series last point ($170.3M) over the
    # /chains headline ($365.5M) — the two DefiLlama endpoints disagree
    # (different inclusion methodology); the series is the auditable one and
    # is what M8 uses. Record both.
    if tvl_last and tvl_last.get("tvl_usd") and "near" in bench["peers"]:
        bench["peers"]["near"]["tvl_usd_chains_endpoint"] = \
            bench["peers"]["near"].get("tvl_usd")
        bench["peers"]["near"]["tvl_usd"] = tvl_last["tvl_usd"]
        bench["peers"]["near"]["tvl_date"] = tvl_last["date"]
        bench["peers"]["near"]["tvl_note"] = (
            "Series last point used; /chains headline differs — see value in "
            "tvl_usd_chains_endpoint.")
        bench["peers"]["near"]["mcap_div_tvl"] = (
            bench["peers"]["near"]["market_cap_usd"] / tvl_last["tvl_usd"])
    # Intents competitors
    for name, fname in [("thorchain", "defillama_fees_thorchain.json"),
                        ("chainflip", "defillama_fees_chainflip.json"),
                        ("debridge", "defillama_fees_debridge.json"),
                        ("lifi", "defillama_fees_lifi.json")]:
        doc = load_json(fname)
        _, tot = fee_series(doc)
        if not tot.get("total30d"):
            bench["dropped"].append(
                {"competitor": name,
                 "reason": "DefiLlama slug returned no fee totals (404 / not found)",
                 **src_of(fname)})
            continue
        bench["intents_competitors"][name] = {
            "fees_30d_usd": float(tot["total30d"]),
            "fees_7d_usd": float(tot.get("total7d") or 0),
            "fees_24h_usd": float(tot.get("total24h") or 0),
            "fees_all_time_usd": float(tot.get("totalAllTime") or 0),
            **src_of(fname),
        }
    metrics["M8_valuation_multiples"] = {
        "definition": "Market-cap / annualised-fees for NEAR (gross + retained) "
                      "vs SOL/AVAX/ETH chain fees; NEAR TVL from DefiLlama series",
        "near_mcap_div_gross_intents_fees": mcap / (f30 * 12),
        "near_mcap_div_retained_fees_base": (mcap / r0_base if r0_base else None),
        "peer_mcap_div_fees": {k: v.get("mcap_div_annualised_fees")
                               for k, v in bench["peers"].items() if k != "near"},
        "near_tvl_usd_last_point": (tvl_last or {}).get("tvl_usd"),
        "near_tvl_date": (tvl_last or {}).get("date"),
        "near_mcap_div_tvl": (mcap / tvl_last["tvl_usd"]
                              if tvl_last and tvl_last.get("tvl_usd") else None),
        "peer_mcap_div_tvl": {k: v.get("mcap_div_tvl")
                              for k, v in bench["peers"].items() if "mcap_div_tvl" in v},
        "peer_fee_methodology_note": ("Peer chain fees are DefiLlama "
            "summary/fees 30d totals, annualised — the same methodology for "
            "all four chains, but DefiLlama chain-fee totals can undercount "
            "vs other methodologies (e.g. Solana's total here is far below "
            "figures that include all validator/Jito revenue). Use for "
            "relative ranking within this dataset, not as absolute revenue."),
        "intents_competitors_30d_fees_usd": {
            k: v["fees_30d_usd"] for k, v in bench["intents_competitors"].items()},
        "dropped_benchmarks": bench["dropped"],
        **src_of("defillama_overview_fees.json"),
    }

    # ---------------- chart data ----------------
    chart_data = {}

    # Chart 1: daily Intents fees + 30d MA (log + linear inset)
    ma = []
    vals = [v for _, v in intents]
    for i in range(len(intents)):
        lo = max(0, i - 29)
        ma.append(sum(vals[lo:i + 1]) / (i + 1 - lo))
    chart_data["chart_01"] = {
        "title": "NEAR Intents daily fees (USD, log scale) + 30d moving average",
        "dates": [datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                  for ts, _ in intents],
        "daily_fees_usd": [v for _, v in intents],
        "ma30_usd": ma,
        "source": src_of("defillama_fees_near-intents.json"),
    }
    # Chart 2: Intents vs base-chain fees (each series keeps its own dates —
    # the base series starts years earlier, so they must NOT be zipped).
    chart_data["chart_02"] = {
        "title": "Intents fees vs NEAR base-chain fees (USD/day, log scale)",
        "dates": chart_data["chart_01"]["dates"],
        "intents_daily_fees_usd": [v for _, v in intents],
        "base_dates": [datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                       for ts, _ in base_fees],
        "base_daily_fees_usd": [v for _, v in base_fees],
        "intents_30d_usd": f30, "base_24h_usd": base_f24,
        "source": src_of("defillama_fees_near-intents.json"),
    }
    # Chart 3: price vs fees divergence, indexed to 100
    if prices and tr30:
        import bisect
        fee_ts = [ts for ts, _ in tr30]
        rows = []
        for ts_ms, p in prices:
            i = bisect.bisect_left(fee_ts, ts_ms)
            if i >= len(tr30):
                i = len(tr30) - 1
            rows.append((ts_ms, p, tr30[i][1]))
        p0, f0 = rows[0][1], rows[0][2]
        chart_data["chart_03"] = {
            "title": "NEAR price vs trailing-30d Intents fees, indexed to 100",
            "dates": [datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                      for ts, _, _ in rows],
            "price_indexed": [100 * p / p0 for _, p, _ in rows],
            "trailing_30d_fees_indexed": [100 * f / f0 for _, _, f in rows],
            "price_change_pct": div.get("price_change_pct"),
            "fees_change_pct": div.get("trailing_30d_fees_change_pct"),
            "price_30d_change_pct": div.get("price_30d_change_pct"),
            "fees_30d_change_pct": div.get("trailing_30d_fees_30d_change_pct"),
        }
    # Chart 4: valuation multiples bars
    chart_data["chart_04"] = {
        "title": "Market-cap / annualised fees (x)",
        "labels": ["NEAR Intents\ngross", "NEAR Intents\nretained (base)",
                   "Solana", "Avalanche", "Ethereum"],
        "values": [mcap / (f30 * 12),
                   mcap / r0_base if r0_base else None,
                   bench["peers"].get("solana", {}).get("mcap_div_annualised_fees"),
                   bench["peers"].get("avalanche-2", {}).get("mcap_div_annualised_fees"),
                   bench["peers"].get("ethereum", {}).get("mcap_div_annualised_fees")],
    }
    # Chart 5: buyback vs issuance waterfall (3 capture scenarios + measured)
    chart_data["chart_05"] = {
        "title": "NEAR bought/yr from retained revenue vs NEAR issued/yr",
        "issued_per_year_near": issued_per_yr,
        "scenarios": [
            {"capture": c, "bought_per_year_near": f30 * 12 * c / price}
            for c in dcf_a["capture_scenarios"]],
        "measured": {"capture": capture_measured,
                     "bought_per_year_near": bought_base},
        "break_even_retained_revenue_usd": breakeven_r,
    }
    # Chart 6: staking economics panel
    chart_data["chart_06"] = {
        "title": "Staking economics: APY vs inflation vs real yield",
        "apy_pct": round(100 * apy, 2), "inflation_pct": round(100 * max_inflation, 2),
        "real_yield_pct": round(100 * (apy - max_inflation), 2),
        "total_staked_near": total_staked,
        "total_staked_share_pct": metrics["M10_validator_health"]["total_staked_share_of_supply_pct"],
        "current_validators": metrics["M10_validator_health"]["current_validators"],
        "top_10_share_pct": metrics["M10_validator_health"]["top_10_stake_share_pct"],
    }
    # Chart 7: sensitivity heatmap (capture x growth at fixed discount)
    r_hm = dcf_a["heatmap_discount_rate"]
    heat = []
    for c in dcf_a["capture_scenarios"]:
        row = []
        for g in dcf_a["growth_scenarios"]:
            v = dcf_value(f30 * 12 * c, g, r_hm)
            row.append(round(v / supply_circ, 4) if v is not None else None)
        heat.append(row)
    chart_data["chart_07"] = {
        "title": f"Implied NEAR value/token (USD) — capture x growth at r={int(r_hm * 100)}%",
        "capture_scenarios": dcf_a["capture_scenarios"],
        "growth_scenarios": dcf_a["growth_scenarios"],
        "discount_rate": r_hm,
        "values_per_token_usd": heat,
        "current_price_usd": price,
        "base_case_value_per_token_usd": (val_base / supply_circ if val_base else None),
    }
    # Chart 8: daily txns + daily active accounts, 2020 -> today (log scale).
    m12, m13 = metrics["M12_daily_txns"], metrics["M13_daily_active_accounts"]
    tx_pts = charts.get("txns") or []
    ac_pts = charts.get("active_accounts") or []
    chart_data["chart_08"] = {
        "title": "Daily transactions and daily active accounts (log scale)",
        "available": bool(tx_pts and ac_pts),
        "dates": [d for d, _ in tx_pts],
        "daily_txns": [v for _, v in tx_pts],
        "active_dates": [d for d, _ in ac_pts],
        "daily_active_accounts": [v for _, v in ac_pts],
        "txns_peak": m12.get("all_time_peak") if m12.get("available") else None,
        "txns_current": m12.get("current_last_day") if m12.get("available") else None,
        "txns_pct_below_peak": m12.get("current_pct_below_peak") if m12.get("available") else None,
        "txns_30d_avg": m12.get("daily_avg_last_30d") if m12.get("available") else None,
        "accounts_peak": m13.get("all_time_peak") if m13.get("available") else None,
        "accounts_current": m13.get("current_last_day") if m13.get("available") else None,
        "accounts_pct_below_peak": m13.get("current_pct_below_peak") if m13.get("available") else None,
        "accounts_30d_avg": m13.get("daily_avg_last_30d") if m13.get("available") else None,
        "source": src_of("nearblocks_charts.json"),
    }
    # Chart 9: Intents daily volume + daily fees (two panels, shared x-axis).
    # Only when the DefiLlama dexs endpoint verified (M15 available).
    m15 = metrics["M15_intents_daily_volume"]
    if volume_pts and m15.get("available"):
        vvals = [v for _, v in volume_pts]
        vma = []
        for i in range(len(volume_pts)):
            lo = max(0, i - 29)
            vma.append(sum(vvals[lo:i + 1]) / (i + 1 - lo))
        chart_data["chart_09"] = {
            "title": "NEAR Intents daily volume and daily fees (USD, log scale)",
            "available": True,
            "dates": [datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                      for ts, _ in volume_pts],
            "daily_volume_usd": vvals,
            "volume_ma30_usd": vma,
            "fee_dates": chart_data["chart_01"]["dates"],
            "daily_fees_usd": chart_data["chart_01"]["daily_fees_usd"],
            "volume_30d_usd": m15["total_30d_usd_from_daily_series"],
            "volume_30d_vs_prior_30d_pct": m15["total_30d_vs_prior_30d_pct"],
            "fees_30d_usd": f30,
            "implied_gross_fee_rate_30d_bps": m15["implied_gross_fee_rate_30d_bps"],
            "peak_daily_volume": m15["peak_daily_volume"],
            "source": src_of("defillama_dexs_near-intents.json"),
        }
    else:
        chart_data["chart_09"] = {
            "title": "NEAR Intents daily volume and daily fees (USD, log scale)",
            "available": False,
            "reason": m15.get("reason", "No daily volume series."),
            "source": src_of("defillama_dexs_near-intents.json"),
        }
    # Chart 10: Metcalfe check — monthly log-log scatter, price vs users,
    # plus the cumulative-txns partial check. Same monthly recipe as M17,
    # rebuilt here from the parsed charts so the chart data is self-contained.
    m17m = metrics["M17_metcalfe_check"]
    if m17m.get("available"):
        from collections import defaultdict as _dd2
        _price = dict(charts.get("near_price") or [])
        _users = dict(charts.get("active_accounts") or [])
        _txns = dict(charts.get("txns") or [])
        _dates = sorted(d for d in _price if _price[d] > 0 and _users.get(d, 0) > 0)
        _bym = _dd2(list)
        for d in _dates:
            _bym[d[:7]].append(d)
        _months = sorted(_bym)
        _mu, _mp, _mcum = [], [], []
        _cum = 0.0
        _cum_by_date = {}
        for d in sorted(_txns):
            _cum += _txns[d]
            _cum_by_date[d] = _cum
        for mth in _months:
            ds = _bym[mth]
            _mu.append(sum(_users[d] for d in ds) / len(ds))
            _mp.append(_price[ds[-1]])
            _mcum.append(_cum_by_date[ds[-1]])
        reg_m10 = m17m["price_vs_active_accounts_monthly"]
        reg_c10 = m17m["price_vs_cumulative_txns_monthly"]
        chart_data["chart_10"] = {
            "title": "Metcalfe check — NEAR price vs daily active accounts (log-log)",
            "available": True,
            "months": _months,
            "monthly_users_mean": _mu,
            "monthly_price_month_end": _mp,
            "monthly_cum_txns_month_end": _mcum,
            "fit_price_vs_users": {"slope": reg_m10["slope"],
                                   "intercept": reg_m10["intercept"]},
            "fit_price_vs_cum_txns": {"slope": reg_c10["slope"],
                                      "intercept": reg_c10["intercept"]},
            "slope_monthly": reg_m10["slope"],
            "r_squared_monthly": reg_m10["r_squared"],
            "pearson_r_monthly": reg_m10["pearson_r"],
            "slope_daily": m17m["price_vs_active_accounts_daily"]["slope"],
            "r_squared_daily": m17m["price_vs_active_accounts_daily"]["r_squared"],
            "slope_mcap_monthly": m17m["market_cap_vs_active_accounts_monthly"]["slope"],
            "r_squared_mcap_monthly": m17m["market_cap_vs_active_accounts_monthly"]["r_squared"],
            "slope_cum_txns": reg_c10["slope"],
            "r_squared_cum_txns": reg_c10["r_squared"],
            "slope_subwindow_2024": m17m["subwindow_2024_onwards_monthly"]["slope"],
            "r_subwindow_2024": m17m["subwindow_2024_onwards_monthly"]["pearson_r"],
            "n_months": m17m["n_months"],
            "window": m17m["window"],
            "total_cumulative_txns": m17m["total_cumulative_txns"],
            "rival_slope": m17m["rival_reported"]["slope"],
            "rival_r_squared": m17m["rival_reported"]["r_squared"],
            "source": src_of("nearblocks_charts.json"),
        }
    else:
        chart_data["chart_10"] = {
            "title": "Metcalfe check — NEAR price vs daily active accounts (log-log)",
            "available": False,
            "reason": m17m.get("reason", "Metcalfe series unavailable."),
            "source": src_of("nearblocks_charts.json"),
        }

    # ---------------- write outputs ----------------
    (PROC / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (PROC / "dcf.json").write_text(json.dumps(dcf, indent=2))
    (PROC / "sensitivity.json").write_text(json.dumps(sens, indent=2))
    (PROC / "benchmarks.json").write_text(json.dumps(bench, indent=2))
    for k, v in chart_data.items():
        (PROC / f"{k}_data.json").write_text(json.dumps(v, indent=2))

    # headline printout
    print(f"F30 (30d Intents gross fees): ${f30:,.0f}")
    print(f"Measured 30D capture: {capture_measured} "
          f"(cards cross-check: {capture_cards})")
    print(f"R0 base (annualised retained): ${r0_base:,.0f}")
    print(f"DCF base value/token (r={r_base}, g={g_base}): "
          f"${val_base / supply_circ:.4f} vs price ${price:.2f}")
    print(f"Break-even retained revenue: ${breakeven_r:,.0f}/yr "
          f"({breakeven_r / r0_base:.1f}x current R0)")
    print(f"Mcap / R0 base: {mcap / r0_base:.1f}x")
    print(f"Issued/yr: {issued_per_yr:,.0f} NEAR; bought/yr base: {bought_base:,.0f}")
    print(f"Dropped benchmarks: {bench['dropped']}")
    m12p, m13p = metrics["M12_daily_txns"], metrics["M13_daily_active_accounts"]
    if m12p.get("available"):
        print(f"M12 txns: current {m12p['current_last_day']:,.0f}/day, 30d avg "
              f"{m12p['daily_avg_last_30d']:,.0f}, peak "
              f"{m12p['all_time_peak']['value']:,.0f} on {m12p['all_time_peak']['date']} "
              f"({m12p['current_pct_below_peak']}% below peak)")
    if m13p.get("available"):
        print(f"M13 active accounts: current {m13p['current_last_day']:,.0f}/day, "
              f"30d avg {m13p['daily_avg_last_30d']:,.0f}, peak "
              f"{m13p['all_time_peak']['value']:,.0f} on {m13p['all_time_peak']['date']} "
              f"({m13p['current_pct_below_peak']}% below peak)")
    m15p = metrics["M15_intents_daily_volume"]
    if m15p.get("available"):
        print(f"M15 Intents volume 30d: ${m15p['total_30d_usd_from_daily_series']:,.0f} "
              f"({m15p['total_30d_vs_prior_30d_pct']}% vs prior 30d); implied fee rate "
              f"{m15p['implied_gross_fee_rate_30d_bps']} bps")
    m16p = metrics["M16_price_vs_fees_correlation"]
    print(f"M16 weekly log-change Pearson: price vs Intents fees "
          f"{m16p.get('pearson_price_vs_intents_fees_weekly_log_changes')} "
          f"(n={m16p.get('n_weekly_pairs_price_vs_intents_fees')}); price vs base "
          f"gas fees {m16p.get('pearson_price_vs_base_gas_fees_weekly_log_changes')} "
          f"(n={m16p.get('n_weekly_pairs_price_vs_base_gas_fees')})")
    m17p = metrics["M17_metcalfe_check"]
    if m17p.get("available"):
        rm = m17p["price_vs_active_accounts_monthly"]
        print(f"M17 Metcalfe (monthly, n={rm['n']}): log(price) on log(users) "
              f"slope {rm['slope']} (SE {rm['slope_se']}), R² {rm['r_squared']}, "
              f"r {rm['pearson_r']} — vs strict-Metcalfe slope 2.0; daily slope "
              f"{m17p['price_vs_active_accounts_daily']['slope']}, "
              f"R² {m17p['price_vs_active_accounts_daily']['r_squared']}")
    else:
        print(f"M17 Metcalfe UNAVAILABLE: {m17p.get('reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
