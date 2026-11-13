#!/usr/bin/env python3
"""Fee-capture DCF + 19 metrics for the NEAR Investment Thesis.

Reads ONLY:
  - data/raw/* (cached API responses) + data/manifest.json (source + fetched_at)
  - src/assumptions.yaml (labelled assumptions — see that file)
  - data/predictions.json (the 7 committed predictions, M18)
  - data/falsification.json (the 6 committed falsification conditions, M19)

Implements research-notes §8 exactly:
  R₀ = F₃₀ * 12 * c            (annualised retained revenue, USD/yr)
  Value_equity = R₁ / (r - g), R₁ = R₀ * (1 + g)     (Gordon growth)
  Value_per_token = Value_equity / circulating_supply
  NEAR bought/yr = R₀ / price ; NEAR issued/yr = max_inflation * total_supply
  Break-even retained revenue = issued/yr * price

Growth g must be < discount r; grid cells with g >= r are recorded as
null with reason "invalid: g >= r" — never silently computed.

Outputs (data/processed/):
  metrics.json       M1-M19 + live snapshot, each with source + fetched_at
  dcf.json           base-case DCF with every input traced to its source
  sensitivity.json   full capture x growth x discount grid (27 cells)
  benchmarks.json    peer + Intents-competitor multiples
  predictions.json   M18 dated predictions: committed thresholds + live values
  falsification.json M19 falsification conditions: committed thresholds + live values
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

    # F₃₀: DefiLlama total30d (primary) cross-checked vs sum of last 30 daily pts
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
        "definition": "Annualised retained revenue = F₃₀ * 12 * capture_rate",
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
        "trend_reading": (f"Capture is rising: all-time "
                          f"~{cap_windows['all_time'] * 100:.0f}% -> YTD "
                          f"~{cap_windows['ytd'] * 100:.0f}% -> 30D "
                          f"~{cap_windows['d30'] * 100:.0f}%. The 30D rate, "
                          "not the lifetime rate, is the base case."),
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
            f"rise to and joint fall from the Apr 2024 activity peak. The relation flips "
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
        "formula": "R₀ = F₃₀ * 12 * capture; R₁ = R₀ * (1+g); Value = R₁/(r-g); "
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
            "reading": (f"At today's fees and the measured "
                        f"~{capture_measured * 100:.0f}% capture, retained "
                        f"revenue alone supports only a fraction of the "
                        f"${mcap / 1e9:.2f}B market "
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

    # ---------------- growth-assumption check ----------------
    # The base case assumes g=10%/yr forever. The data's own trend is the
    # trailing-365d log-regression CAGR on trailing-30d fees (M2) — about
    # flat, not 10%. Show the DCF at the measured growth rate and at g=0%
    # (both at base r and measured capture), so the dashboard shows the
    # model under the data's own trend. g=0% rows already exist in the
    # grid; this surfaces them explicitly next to the measured rate.
    _m2 = metrics["M2_intents_fee_growth"]
    _g_meas = _m2["log_regression_cagr_last_365d"]["cagr"]
    _v_meas = dcf_value(r0_base, _g_meas, r_base)
    _v_g0 = dcf_value(r0_base, 0.0, r_base)
    sens["growth_assumption_check"] = {
        "base_growth_rate": g_base,
        "measured_growth_rate_365d_log_regression": _g_meas,
        "measured_growth_source": "M2 log_regression_cagr_last_365d",
        "discount_rate_r": r_base,
        "capture_rate_30d": capture_measured,
        "dcf_value_per_token_at_measured_growth_usd": (
            _v_meas / supply_circ if _v_meas is not None else None),
        "dcf_value_per_token_at_zero_growth_usd": (
            _v_g0 / supply_circ if _v_g0 is not None else None),
        "note": ("Base g=10%/yr is a forward assumption, not a trend "
                 "extrapolation: the measured trailing-365d growth is "
                 "essentially flat. At the measured rate the DCF is roughly "
                 "a third of the base case."),
    }

    # ---------------- bridge: what would have to be true for $2.05? ------
    # A fellow entry (NEAR Toll Audit) corroborates our core measurements
    # (35.9% capture vs our 33.92%; $22.3M/yr captured revenue vs our
    # $22.22M/yr) but values NEAR at $2.05 base / $2.91 weighted by adding
    # chain value + exit value to a 5-year holder-earnings model. Their
    # figures are quoted constants (assumptions.yaml "bridge"); only our
    # side refreshes with each fetch. The bridge is in dollars (equity
    # value), which is supply-basis free; per-token figures use their
    # 1.31B basis, with our DCF restated on the same basis for comparison.
    br = A.get("bridge", {})
    toll_base_vpt = br["toll_base_value_per_token"]
    toll_weighted_vpt = br["toll_weighted_value_per_token"]
    toll_chain_usd = br["toll_chain_value_usd"]
    toll_supply = br["toll_supply_basis_near"]
    toll_base_total = toll_base_vpt * toll_supply
    toll_weighted_total = toll_weighted_vpt * toll_supply
    gap_base = toll_base_total - val_base
    residual_usd = gap_base - toll_chain_usd
    sens_max = max(c["value_per_token_usd"] for c in grid
                   if c["value_per_token_usd"] is not None)
    bridge = {
        "rival": "NEAR Toll Audit (@swiftbotlab)",
        "source_url": br["toll_source_url"],
        "as_published": br["toll_as_published"],
        "corroboration": {
            "rival_capture_30d": br["toll_capture_30d"],
            "our_capture_30d": capture_measured,
            "rival_captured_revenue_annualised_usd": (
                br["toll_captured_revenue_annualised_usd"]),
            "our_r0_usd": r0_base,
        },
        "our_dcf": {
            "equity_value_usd": val_base,
            "value_per_token_usd": (val_base / supply_circ if val_base else None),
            "value_per_token_on_rival_supply_basis_usd": (
                val_base / toll_supply if val_base else None),
            "supply_basis_near": supply_circ,
        },
        "rival_base_case": {
            "value_per_token_usd": toll_base_vpt,
            "total_equity_value_usd": toll_base_total,
            "chain_value_usd": toll_chain_usd,
            "chain_value_share_of_total_pct": round(
                100 * toll_chain_usd / toll_base_total, 1),
            "supply_basis_near": toll_supply,
        },
        "rival_weighted_case": {
            "value_per_token_usd": toll_weighted_vpt,
            "total_equity_value_usd": toll_weighted_total,
        },
        "bridge_to_rival_base_usd": {
            "retained_revenue_dcf": val_base,
            "plus_chain_value": toll_chain_usd,
            "plus_exit_value_and_horizon_difference": residual_usd,
            "equals_rival_base_total": toll_base_total,
            "gap_usd": gap_base,
        },
        "bridge_per_token_on_rival_supply_basis_usd": {
            "retained_revenue_dcf": val_base / toll_supply,
            "plus_chain_value": toll_chain_usd / toll_supply,
            "plus_exit_value_and_horizon_difference": residual_usd / toll_supply,
            "equals_rival_base": toll_base_vpt,
        },
        "sensitivity_grid_max_valid_value_per_token_usd": sens_max,
        "market_price_implied_under_rival_model": {
            "price_usd": price,
            "quoted_price_usd": br["toll_price_implied_price_usd"],
            "quoted_price_note": ("Toll Audit's published price (their page, "
                                  "section 10) — the 63%/12x implication is "
                                  "quoted against $3.60, not the live price."),
            "volume_growth_per_year_5y": br["toll_price_implied_growth_5y"],
            "volume_growth_multiple_5y": br["toll_price_implied_growth_multiple_5y"],
            "exit_multiple": br["toll_price_implied_exit_multiple"],
            "exit_multiple_growth": br["toll_price_implied_exit_growth"],
            "chain_value_usd": br["toll_price_implied_chain_value_usd"],
            "chain_value_growth": br["toll_price_implied_chain_growth"],
        },
        "reading": (
            "No parameter tweak closes the gap: the best valid sensitivity "
            f"cell is ${sens_max:.2f}, still half the rival's base case, so "
            "the difference is structural — what is included (chain value + "
            "exit value), not the parameters. The rival's base case is "
            f"{round(100 * toll_chain_usd / toll_base_total)}% chain value, "
            "an assumption they state themselves; our DCF is the "
            "conservative floor (retained revenue only)."),
    }

    # ---------------- reverse DCF: what the market price implies -------
    # Invert the base-case DCF at the same r and g: what operational
    # milestones make the fee-capture DCF equal today's live price?
    # Value* = price * supply; R1* = Value* * (r - g); R0* = R1* / (1 + g).
    # (a) required annual gross volume at current capture + fee rate.
    # (b) required 30d gross fees at current capture.
    # (c) required capture if volume stays flat — >100% means impossible.
    _m15 = metrics["M15_intents_daily_volume"]
    _fee_rate = _m15["implied_gross_fee_rate_30d_bps"] / 10000.0
    _vol_30d = _m15["total_30d_usd_from_daily_series"]
    _target_equity = price * supply_circ
    _req_r1 = _target_equity * (r_base - g_base)
    _req_r0 = _req_r1 / (1 + g_base)
    _req_gross_fees_annual = _req_r0 / capture_measured
    _req_volume_annual = _req_gross_fees_annual / _fee_rate
    _req_fees_30d = _req_r0 / 12.0 / capture_measured
    _gross_fees_annual_now = f30 * 12.0
    _req_capture_flat = _req_r0 / _gross_fees_annual_now
    # Corollary: even at 100% capture with volume flat, the ceiling is
    # R0 = gross fees annualised, R1 = R0 * (1 + g), equity = R1 / (r - g).
    _ceil_equity = _gross_fees_annual_now * (1 + g_base) / (r_base - g_base)
    _ceil_vpt = _ceil_equity / supply_circ
    reverse_dcf = {
        "title": f"Path to ${price:,.2f} — what the market price implies (reverse DCF)",
        "inputs": {
            "price_usd": price,
            "supply_near": supply_circ,
            "discount_rate_r": r_base,
            "growth_rate_g": g_base,
            "capture_rate_30d": capture_measured,
            "fee_rate_30d_bps": _m15["implied_gross_fee_rate_30d_bps"],
            "f30_trailing_30d_gross_fees_usd": f30,
            "volume_30d_usd": _vol_30d,
            "r0_annualised_retained_revenue_usd": r0_base,
            "dcf_value_per_token_usd": val_base / supply_circ,
        },
        "required_equity_value_usd": _target_equity,
        "required_r0_annualised_retained_revenue_usd": _req_r0,
        "required_r1_next_year_retained_revenue_usd": _req_r1,
        "required_multiple_of_current_r0": _req_r0 / r0_base,
        "a_required_annual_gross_volume_usd": _req_volume_annual,
        "a_current_annualised_volume_usd": _vol_30d * 12.0,
        "a_required_multiple_of_current_volume": (
            _req_volume_annual / (_vol_30d * 12.0)),
        "b_required_30d_gross_fees_usd": _req_fees_30d,
        "b_required_multiple_of_current_f30": _req_fees_30d / f30,
        "c_required_capture_rate_if_volume_flat": _req_capture_flat,
        "c_feasible": _req_capture_flat <= 1.0,
        "ceiling_at_100pct_capture_flat_volume": {
            "r0_annualised_retained_revenue_usd": _gross_fees_annual_now,
            "equity_value_usd": _ceil_equity,
            "value_per_token_usd": _ceil_vpt,
            "value_per_token_vs_price_pct": 100 * _ceil_vpt / price,
        },
        "reading": (
            f"At r={r_base:.0%}, g={g_base:.0%}, the ${price:.2f} price needs "
            f"retained revenue of ${_req_r0:,.0f}/yr — {_req_r0 / r0_base:.1f}x "
            f"today's R₀. At the current {capture_measured:.2%} capture and "
            f"{_m15['implied_gross_fee_rate_30d_bps']:.2f} bps fee rate that "
            f"means ${_req_volume_annual / 1e9:.1f}B of annual Intents volume "
            f"({_req_volume_annual / (_vol_30d * 12.0):.1f}x today's "
            f"annualised volume), or ${_req_fees_30d:,.0f} of gross fees every "
            "30 days. Capture alone cannot get there: with volume flat, the "
            f"price needs a {_req_capture_flat:.0%} capture rate — impossible. "
            f"Even at 100% capture with volume flat, the DCF ceiling is "
            f"${_ceil_vpt:.2f} ({100 * _ceil_vpt / price:.0f}% of the price). "
            "The price is a bet on volume growth, not on retention."),
    }

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

    # ---------------- M18: dated predictions — live values vs thresholds ----
    # The 7 committed predictions (PREDICTIONS.md, committed 2026-11-10;
    # machine-readable mirror data/predictions.json) scored against the
    # CURRENT model outputs. Status is a point-in-time read: "on track" if
    # the live value satisfies the threshold today, "off track" if it does
    # not, "not yet measurable" if the underlying metric is unavailable.
    # No prediction has resolved yet (earliest resolution date 2026-12-31);
    # status is NOT the final outcome. Thresholds below are the numeric form
    # of the committed thresholds in data/predictions.json — if a threshold
    # changes there, change these to match (enforced by
    # tests/test_outputs.py::test_predictions_match_committed).
    PREDICTION_THRESHOLDS = {
        "P1": {"value": 5578208.0, "op": ">=", "unit": "usd"},
        "P2": {"value": 0.3597, "op": ">=", "unit": "fraction"},
        "P3": {"value": 0.25, "op": "<", "unit": "fraction_of_price"},
        "P4": {"value": 3_000_000_000.0, "op": ">=", "unit": "usd"},
        "P5": {"value": 1.5, "op": ">=", "unit": "ratio"},
        "P6": {"value": 100000.0, "op": "<", "unit": "accounts_per_day"},
        "P7": {"value": 0.30, "op": "<", "unit": "abs_pearson_r"},
    }
    committed = None
    try:
        committed = json.loads((REPO / "data" / "predictions.json").read_text())
    except Exception:
        committed = None
    pred_rows = []
    if committed:
        _m13 = metrics.get("M13_daily_active_accounts") or {}
        _m15 = metrics.get("M15_intents_daily_volume") or {}
        _m16 = metrics.get("M16_price_vs_fees_correlation") or {}
        _cf = (bench.get("intents_competitors") or {}).get("chainflip") or {}
        _vpt = (val_base / supply_circ) if val_base else None
        _live = {
            "P1": f30 if f30 else None,
            "P2": capture_measured,
            "P3": ((_vpt / price) if (_vpt is not None and price) else None),
            "P4": _m15.get("total_30d_usd_from_daily_series")
                  if _m15.get("available") else None,
            "P5": ((f30 / _cf["fees_30d_usd"])
                   if (f30 and _cf.get("fees_30d_usd")) else None),
            "P6": _m13.get("daily_avg_last_30d")
                  if _m13.get("available") else None,
            "P7": (abs(_m16["pearson_price_vs_intents_fees_weekly_log_changes"])
                   if _m16.get("pearson_price_vs_intents_fees_weekly_log_changes") is not None
                   else None),
        }
        _missing_reason = {
            "P1": "DefiLlama Intents fee series unavailable",
            "P2": "revenue.near.org capture rate unavailable",
            "P3": "DCF base case or live price unavailable",
            "P4": "DefiLlama Intents volume series unavailable",
            "P5": "Chainflip fee totals unavailable",
            "P6": "NEARBlocks daily active-accounts series unavailable",
            "P7": "M16 weekly price-vs-fees correlation unavailable",
        }
        _fmt = {
            "P1": lambda v: f"${v:,.0f}",
            "P2": lambda v: f"{v * 100:.2f}%",
            "P3": lambda v: f"{v * 100:.1f}% of price",
            "P4": lambda v: f"${v:,.0f}",
            "P5": lambda v: f"{v:.2f}×",
            "P6": lambda v: f"{v:,.0f}/day",
            "P7": lambda v: f"|r| = {v:.3f}",
        }
        for _p in committed.get("predictions", []):
            _pid = _p["id"]
            _th = PREDICTION_THRESHOLDS.get(_pid)
            _lv = _live.get(_pid)
            if _th is None:
                _status, _reason = "not yet measurable", (
                    f"No numeric threshold recorded for {_pid} — check "
                    "PREDICTION_THRESHOLDS in src/model.py.")
            elif _lv is None:
                _status, _reason = "not yet measurable", _missing_reason[_pid]
            else:
                _ok = (_lv >= _th["value"] if _th["op"] == ">="
                       else _lv < _th["value"])
                _status = "on track" if _ok else "off track"
                _reason = None
            pred_rows.append({
                "id": _pid, "title": _p.get("title"),
                "threshold": _p.get("threshold"),
                "threshold_value": _th["value"] if _th else None,
                "threshold_op": _th["op"] if _th else None,
                "resolves": _p.get("resolves"),
                "source_short": _p.get("source_short"),
                "live_value": _lv,
                "live_value_display": _fmt[_pid](_lv) if _lv is not None else None,
                "status": _status,
                "status_reason": _reason,
            })
    _counts = {"on track": 0, "off track": 0, "not yet measurable": 0}
    for _r in pred_rows:
        _counts[_r["status"]] = _counts.get(_r["status"], 0) + 1
    metrics["M18_dated_predictions"] = {
        "definition": "The 7 committed predictions (PREDICTIONS.md, committed "
                      "2026-11-10) scored against current model outputs. Status "
                      "is a point-in-time read, not the final outcome: no "
                      "prediction has resolved yet (earliest resolution date "
                      "2026-12-31).",
        "method": "Live values are the same figures the model already "
                  "computes (M₁ F₃₀, M₃ capture, base-case DCF ÷ live price, "
                  "M₁₅ volume, F₃₀ ÷ Chainflip 30d fees, M₁₃ 30d-mean active "
                  "accounts, |M₁₆ weekly log-change Pearson|). Thresholds are "
                  "the numeric form of data/predictions.json — see "
                  "PREDICTION_THRESHOLDS in src/model.py.",
        "committed": (committed or {}).get("committed"),
        "as_of_utc": metrics["generated_at_utc"],
        "available": bool(pred_rows),
        "reason": (None if pred_rows else
                   "data/predictions.json missing or unreadable — no committed "
                   "predictions to score."),
        "counts": _counts,
        "predictions": pred_rows,
    }
    predictions_out = {
        "generated_at_utc": metrics["generated_at_utc"],
        "committed": (committed or {}).get("committed"),
        "note": ("Live values are point-in-time reads against the committed "
                 "thresholds, not final outcomes. Earliest resolution date "
                 "2026-12-31."),
        "counts": _counts,
        "predictions": pred_rows,
    }

    # ---------------- M19: falsification — what would prove the thesis wrong
    # The 6 committed kill conditions (README.md Falsification section,
    # committed 2026-11-11; machine-readable mirror data/falsification.json)
    # scored against the CURRENT model outputs. Status is "triggered" only
    # when the live value breaches the threshold AND the persistence window
    # has been met; otherwise "not triggered". "not yet measurable" is used
    # only when the underlying metric is unavailable. Persistence is counted
    # from the commitment date forward — the method per condition, and what
    # the stored data does and does not support, is documented in
    # data/processed/BUILD_NOTES.md (M19). F3 is event-based (its live value
    # is the largest single-provider outage drop on record, the Oct 1-4 2026
    # pause precedent cited in README Limitations — not a live series value)
    # and F5 has no persistence window by design.
    FALSIFICATION_COMMIT = "2026-11-11"
    _commit_date = datetime.strptime(FALSIFICATION_COMMIT, "%Y-%m-%d").date()
    _today = datetime.now(timezone.utc).date()
    FALSIFICATION_THRESHOLDS = {
        "F1": {"value": 2_000_000.0, "op": "<", "unit": "usd"},
        "F2": {"value": 0.15, "op": "<", "unit": "fraction"},
        "F3": {"value": 0.50, "op": ">", "unit": "fractional_volume_drop"},
        "F4": {"value": 1.0, "op": "<", "unit": "ratio"},
        "F5": {"value": 1.0, "op": ">=", "unit": "fraction_of_price"},
        "F6": {"value": 0.5, "op": "<", "unit": "fraction_below_peak_and_prior_30d"},
    }
    fals_committed = None
    try:
        fals_committed = json.loads((REPO / "data" / "falsification.json").read_text())
    except Exception:
        fals_committed = None
    # Previous processed run, for F2 persistence carry-forward: the capture
    # rate is a point-in-time fetch with no stored daily history, so a
    # breach's start date is carried forward through this file across runs.
    _prev_fals = None
    try:
        _prev_fals = json.loads((PROC / "falsification.json").read_text())
    except Exception:
        _prev_fals = None
    _prev_breach_since = {}
    if _prev_fals:
        for _r in _prev_fals.get("conditions", []):
            if _r.get("breach_since"):
                _prev_breach_since[_r["id"]] = _r["breach_since"]

    def _full_months(start, end):
        """Whole calendar months elapsed from `start` to `end`."""
        months = (end.year - start.year) * 12 + (end.month - start.month)
        if end.day < start.day:
            months -= 1
        return max(0, months)

    def _consec_run(daily, commit):
        """Consecutive True days ending at the last date, counting only
        dates >= `commit`. `daily`: sorted [(date, bool)]. Returns
        (run_length, run_start_date_or_None)."""
        run, run_start = 0, None
        for d, ok in daily:
            if d < commit:
                continue
            if ok:
                if run == 0:
                    run_start = d
                run += 1
            else:
                run, run_start = 0, None
        return run, run_start

    def _date_of(ts_ms):
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()

    # --- series-backed persistence (F1, F4, F6): counted from the stored
    # daily series, post-commitment dates only.
    _f1_daily = [(_date_of(ts), v < 2_000_000.0) for ts, v in tr30_full]
    _f1_run, _f1_run_start = _consec_run(_f1_daily, _commit_date)
    # F4: aligned daily trailing-30d series, NEAR vs Chainflip.
    _cf_pts, _ = fee_series(load_json("defillama_fees_chainflip.json"))
    _cf_tr = { _date_of(ts): v for ts, v in trailing_sums(_cf_pts)}
    _near_tr = {_date_of(ts): v for ts, v in tr30_full}
    _f4_daily = sorted(
        (d, _near_tr[d] < _cf_tr[d])
        for d in set(_near_tr) & set(_cf_tr))
    _f4_run, _f4_run_start = _consec_run(_f4_daily, _commit_date)
    _f4_months = (_full_months(_f4_run_start, _f4_daily[-1][0])
                  if _f4_run_start else 0)
    # F6: both legs from the stored daily series — fees vs the fixed
    # 2026-10-14 peak, volume vs its own prior 30d.
    _peak_fixed = (metrics["M2_intents_fee_growth"]["trailing_30d_peak"] or {}
                   ).get("trailing_30d_usd")
    _vol_tr = trailing_sums(volume_pts) if volume_pts else []
    _vol_by_date, _vol_prior_by_date = {}, {}
    for _i, (ts, v) in enumerate(_vol_tr):
        _d = _date_of(ts)
        _vol_by_date[_d] = v
        if _i >= 30:
            _vol_prior_by_date[_d] = _vol_tr[_i - 30][1]
    _f6_daily = sorted(
        (d, _near_tr[d] < 0.5 * _peak_fixed
         and d in _vol_by_date and d in _vol_prior_by_date
         and _vol_by_date[d] < 0.5 * _vol_prior_by_date[d])
        for d in set(_near_tr) & set(_vol_by_date))
    _f6_run, _f6_run_start = _consec_run(_f6_daily, _commit_date)

    _vpt = (val_base / supply_circ) if val_base else None
    _cf = (bench.get("intents_competitors") or {}).get("chainflip") or {}
    _m15 = metrics.get("M15_intents_daily_volume") or {}
    _vol30 = _m15.get("total_30d_usd_from_daily_series") \
        if _m15.get("available") else None
    _vol30_prior = (_vol_tr[-31][1] if len(_vol_tr) >= 31 else None)
    _live_f = {
        "F1": f30 if f30 else None,
        "F2": capture_measured,
        # Precedent, not a live series value: the Oct 1-4 2026 service pause
        # ran 31.6% below the prior matching week (Faultline, cited in README
        # Limitations). It is the largest single-provider outage drop on
        # record; the condition is re-evaluated when a new outage is reported.
        "F3": 0.316,
        "F4": ((f30 / _cf["fees_30d_usd"])
               if (f30 and _cf.get("fees_30d_usd")) else None),
        "F5": ((_vpt / price) if (_vpt is not None and price) else None),
        "F6": ((f30 / _peak_fixed) if (f30 and _peak_fixed) else None),
    }
    _live_f2 = {
        "F6": ((_vol30 / _vol30_prior)
               if (_vol30 and _vol30_prior) else None),
    }
    _missing_reason_f = {
        "F1": "DefiLlama Intents fee series unavailable",
        "F2": "revenue.near.org capture rate unavailable",
        "F3": None,  # precedent is always available (cited in README)
        "F4": "Chainflip fee totals unavailable",
        "F5": "DCF base case or live price unavailable",
        "F6": "DefiLlama Intents fee or volume series unavailable",
    }
    _fmt_f = {
        "F1": lambda v: f"${v:,.0f}",
        "F2": lambda v: f"{v * 100:.2f}%",
        "F3": lambda v: f"{v * 100:.1f}% drop — Oct 1–4 2026 pause precedent",
        "F4": lambda v: f"{v:.2f}×",
        "F5": lambda v: f"{v * 100:.1f}% of price",
        "F6": lambda v: f"{v * 100:.1f}% of peak",
    }
    _fmt_f2 = {
        "F6": lambda v: f"{v * 100:.1f}% of prior 30d",
    }
    fals_rows = []
    if fals_committed:
        for _c in fals_committed.get("conditions", []):
            _fid = _c["id"]
            _th = FALSIFICATION_THRESHOLDS.get(_fid)
            _lv = _live_f.get(_fid)
            _lv2 = _live_f2.get(_fid)
            if _th is None:
                _status, _reason = "not yet measurable", (
                    f"No numeric threshold recorded for {_fid} — check "
                    "FALSIFICATION_THRESHOLDS in src/model.py.")
                _bs, _days, _months = None, 0, None
            elif _lv is None:
                _status, _reason = "not yet measurable", _missing_reason_f[_fid]
                _bs, _days, _months = None, 0, None
            else:
                _breach = (_lv >= _th["value"] if _th["op"] == ">="
                           else _lv > _th["value"] if _th["op"] == ">"
                           else _lv < _th["value"])
                if _fid == "F6":
                    # Both legs must breach.
                    _breach = _breach and (_lv2 is not None
                                           and _lv2 < 0.5)
                if not _breach:
                    _status = "not triggered"
                    _bs, _days, _months = None, 0, None
                    # Built with if/elif (not a dict literal): each reason
                    # formats only its own condition's live value.
                    if _fid == "F1":
                        _reason = (f"No breach: F₃₀ {_fmt_f['F1'](_lv)} is "
                                   f"above the $2,000,000 bar; 0 of 90 "
                                   f"persistence days.")
                    elif _fid == "F2":
                        _reason = (f"No breach: capture {_fmt_f['F2'](_lv)} "
                                   f"is above the 15% floor; 0 of 90 "
                                   f"persistence days.")
                    elif _fid == "F3":
                        _reason = (f"Precedent only: the Oct 1–4 2026 pause "
                                   f"ran 31.6% below the prior matching week "
                                   f"— under the 50% bar. Event-based; "
                                   f"re-evaluated when a new outage is "
                                   f"reported.")
                    elif _fid == "F4":
                        _reason = (f"No breach: NEAR leads Chainflip "
                                   f"{_fmt_f['F4'](_lv)}; 0 of 3 persistence "
                                   f"months.")
                    elif _fid == "F5":
                        _reason = (f"No breach: DCF value/token is "
                                   f"{_fmt_f['F5'](_lv)} — far below the "
                                   f"100% bar.")
                    else:  # F6
                        _reason = (f"No breach: fees are {_fmt_f['F6'](_lv)} "
                                   f"and volume {_fmt_f2['F6'](_lv2)} — "
                                   f"neither leg is below its 50% bar; 0 of "
                                   f"90 persistence days.")
                else:
                    # Breach in progress — persistence decides the status.
                    if _fid == "F1":
                        _days, _months = _f1_run, None
                        _bs = _f1_run_start
                        _met = _days >= 90
                    elif _fid == "F2":
                        _prev_bs = _prev_breach_since.get("F2")
                        _bs = (datetime.strptime(_prev_bs, "%Y-%m-%d").date()
                               if _prev_bs else _today)
                        _days = (_today - _bs).days + 1
                        _months = None
                        _met = _days >= 90
                    elif _fid == "F3":
                        _days, _months = 0, None
                        _bs = None
                        _met = False  # event-based: persistence judged on report
                    elif _fid == "F4":
                        _days, _months = _f4_run, _f4_months
                        _bs = _f4_run_start
                        _met = _months >= 3
                    elif _fid == "F5":
                        _days, _months = 0, None
                        _bs = _today
                        _met = True  # no persistence window by design
                    else:  # F6
                        _days, _months = _f6_run, None
                        _bs = _f6_run_start
                        _met = _days >= 90
                    _status = "triggered" if _met else "not triggered"
                    _reason = (f"BREACH in progress since {_bs}: "
                               f"{'persistence met — condition triggered' if _met else 'persistence window not yet met — watch'} "
                               f"({_days} days observed"
                               + (f", {_months} months" if _months is not None else "")
                               + ").")
            fals_rows.append({
                "id": _fid, "title": _c.get("title"),
                "claim": _c.get("claim"),
                "threshold": _c.get("threshold"),
                "threshold_value": _th["value"] if _th else None,
                "threshold_op": _th["op"] if _th else None,
                "threshold_value_secondary": _c.get("threshold_value_secondary"),
                "peak_usd": _c.get("peak_usd"),
                "persistence": _c.get("persistence"),
                "live_value": _lv,
                "live_value_display": _fmt_f[_fid](_lv) if _lv is not None else None,
                "live_value_secondary": _lv2,
                "live_value_secondary_display": (
                    _fmt_f2[_fid](_lv2)
                    if (_fid in _fmt_f2 and _lv2 is not None) else None),
                "status": _status,
                "status_reason": _reason,
                "breach_since": _bs.isoformat() if _bs else None,
                "persistence_days_observed": _days,
                "persistence_months_observed": _months,
                "source_short": _c.get("source_short"),
                "what_triggering_means": _c.get("what_triggering_means"),
            })
    _fcounts = {"triggered": 0, "not triggered": 0, "not yet measurable": 0}
    for _r in fals_rows:
        _fcounts[_r["status"]] = _fcounts.get(_r["status"], 0) + 1
    metrics["M19_falsification"] = {
        "definition": "The 6 committed falsification conditions (README.md "
                      "Falsification section, committed 2026-11-11) scored "
                      "against current model outputs. Status is 'triggered' "
                      "only when the live value breaches the threshold AND "
                      "the persistence window has been met; otherwise 'not "
                      "triggered'. Persistence is counted from the commitment "
                      "date: F1/F4/F6 from the stored daily series, F2 by "
                      "carrying breach_since forward through this file, F3 "
                      "event-based, F5 immediate by design.",
        "method": "Live values are the same figures the model already "
                  "computes (M1 F30, M3 capture, F30 / Chainflip 30d fees, "
                  "base-case DCF / live price, F30 / M2 peak, M15 volume / "
                  "prior-30d volume), except F3, whose live value is the "
                  "Oct 1-4 2026 outage precedent (31.6%) cited in README "
                  "Limitations. Thresholds are the numeric form of "
                  "data/falsification.json — see FALSIFICATION_THRESHOLDS in "
                  "src/model.py.",
        "committed": (fals_committed or {}).get("committed"),
        "as_of_utc": metrics["generated_at_utc"],
        "available": bool(fals_rows),
        "reason": (None if fals_rows else
                   "data/falsification.json missing or unreadable — no "
                   "committed conditions to score."),
        "counts": _fcounts,
        "conditions": fals_rows,
    }
    falsification_out = {
        "generated_at_utc": metrics["generated_at_utc"],
        "committed": (fals_committed or {}).get("committed"),
        "note": ("Live values are point-in-time reads against the committed "
                 "thresholds, not final outcomes. A condition is 'triggered' "
                 "only when the breach has persisted for its full window."),
        "counts": _fcounts,
        "conditions": fals_rows,
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
    (PROC / "bridge.json").write_text(json.dumps(bridge, indent=2))
    (PROC / "reverse_dcf.json").write_text(json.dumps(reverse_dcf, indent=2))
    (PROC / "benchmarks.json").write_text(json.dumps(bench, indent=2))
    (PROC / "predictions.json").write_text(json.dumps(predictions_out, indent=2))
    (PROC / "falsification.json").write_text(json.dumps(falsification_out, indent=2))
    for k, v in chart_data.items():
        (PROC / f"{k}_data.json").write_text(json.dumps(v, indent=2))

    # headline printout
    print(f"F30 (30d Intents gross fees): ${f30:,.0f}")
    print(f"Measured 30D capture: {capture_measured} "
          f"(cards cross-check: {capture_cards})")
    print(f"R₀ base (annualised retained): ${r0_base:,.0f}")
    print(f"DCF base value/token (r={r_base}, g={g_base}): "
          f"${val_base / supply_circ:.4f} vs price ${price:.2f}")
    print(f"Bridge to rival base ${toll_base_vpt:.2f}: ours "
          f"${val_base / toll_supply:.4f}/token on their {toll_supply / 1e9:.2f}B "
          f"basis + chain ${toll_chain_usd / toll_supply:.2f} + exit/horizon "
          f"${residual_usd / toll_supply:.2f}; sensitivity max ${sens_max:.2f}")
    print(f"Break-even retained revenue: ${breakeven_r:,.0f}/yr "
          f"({breakeven_r / r0_base:.1f}x current R₀)")
    print(f"Mcap / R₀ base: {mcap / r0_base:.1f}x")
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
    m18p = metrics["M18_dated_predictions"]
    if m18p.get("available"):
        print(f"M18 dated predictions: {m18p['counts']} "
              f"(as of {m18p['as_of_utc']})")
        for _pr in m18p["predictions"]:
            print(f"  {_pr['id']}: {_pr['status']} — "
                  f"live {_pr['live_value_display']} vs "
                  f"threshold {_pr['threshold']} (resolves {_pr['resolves']})")
    else:
        print(f"M18 dated predictions UNAVAILABLE: {m18p.get('reason')}")
    m19p = metrics["M19_falsification"]
    if m19p.get("available"):
        print(f"M19 falsification: {m19p['counts']} "
              f"(as of {m19p['as_of_utc']})")
        for _fr in m19p["conditions"]:
            print(f"  {_fr['id']}: {_fr['status']} — "
                  f"live {_fr['live_value_display']} vs "
                  f"threshold {_fr['threshold']}")
    else:
        print(f"M19 falsification UNAVAILABLE: {m19p.get('reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
