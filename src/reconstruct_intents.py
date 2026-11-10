#!/usr/bin/env python3
"""Reconstruct NEAR Intents captured revenue independently from on-chain data.

Method (independent of revenue.near.org and DefiLlama):
  1. Enumerate every receipt received by the three Intents revenue wallets
     (fefundsadmin.sputnik-dao.near, buybacks.multisignature.near,
     1csfundsadmin.sputnik-dao.near) via the NEARBlocks indexer API
     (https://api.nearblocks.io/v1/account/{wallet}/txns, paged, order=desc).
  2. Keep only receipts whose predecessor is intents.near and whose action
     is TRANSFER. Each such receipt is one fee sweep: intents.near unwraps
     wNEAR via wrap.near `near_withdraw` and forwards the NEAR to the wallet
     (verified for sampled txs against archival RPC, see verify_sample()).
  3. Convert each sweep's NEAR to USD at that UTC day's NEAR close price
     (CoinGecko market_chart, daily close; fallback: NEARBlocks /v1/charts
     daily near_price).
  4. Reconcile the summed USD against, for the same window:
       - revenue.near.org 30D / 7D net revenue and gross fees (SSR parse,
         same method as src/fetch.py, plus the unambiguous RSC
         `nearAmount` wallet table for the all-time census check), and
       - DefiLlama summary/fees/near-intents dailyFees and dailyRevenue
         (headline totals AND sums of the daily series over the same dates).

What this is NOT: it does not rebuild *gross* fees from swap events
(DIP-4 token_diff events on intents.near would be needed for that, plus a
full-history indexer — see docs/RECONCILIATION.md). It rebuilds the
*retained / captured* leg — the exact leg the thesis's capture rate and R0
rest on — from the wallets that receive it.

Precision note: NEARBlocks returns `deposit` as a JSON float in yoctoNEAR
(~1e27), so the last ~10 yocto digits are float noise. Receipts are parsed
with Decimal(str(float)) and all money totals are reported in NEAR (error
per receipt < 1e-9 NEAR, negligible in USD).

Usage:
  python3 src/reconstruct_intents.py [--days 30] [--all-time]
      [--out data/processed/reconstruction_intents.json]
  --all-time enumerates every receipt back to each wallet's first
  intents.near sweep (census cross-check vs revenue.near.org all-time
  wallet totals). Without it, only the trailing --days window is fetched.
  Exit 0 even if a comparison source fails; failures are recorded in the
  output JSON.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
OUT_DEFAULT = REPO / "data" / "processed" / "reconstruction_intents.json"
RECEIPTS_CACHE = REPO / "data" / "raw" / "reconstruction_intents_receipts.json"

WALLETS = [
    "fefundsadmin.sputnik-dao.near",
    "buybacks.multisignature.near",
    "1csfundsadmin.sputnik-dao.near",
]
INTENTS = "intents.near"
YOCTO = Decimal(10) ** 24
NEARBLOCKS_TXNS = "https://api.nearblocks.io/v1/account/{wallet}/txns"
ARCHIVAL_RPC = "https://archival-rpc.mainnet.near.org"
REVENUE_URL = "https://revenue.near.org/"
DEFILLAMA_FEES = "https://api.llama.fi/summary/fees/near-intents?dataType={kind}"
COINGECKO_CHART = ("https://api.coingecko.com/api/v3/coins/near/market_chart"
                   "?vs_currency=usd&days=35")
NEARBLOCKS_CHARTS = "https://api.nearblocks.io/v1/charts"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "near-thesis-recon/1.0 (+hackathon research)"})
TIMEOUT = 60


def get_with_retry(url, params=None, retries=5):
    """GET with backoff on 429/5xx (NEARBlocks rate-limits fast paging)."""
    delay = 5.0
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            print(f"[retry] transport error {e} — sleeping {delay}s",
                  file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == retries - 1:
                r.raise_for_status()
            print(f"[retry] {r.status_code} {url} — sleeping {delay}s",
                  file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("unreachable")


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dstr(ts_ns):
    return datetime.fromtimestamp(int(ts_ns) // 10**9, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- receipts
def fetch_wallet_receipts(wallet, stop_before_ts_ns=None, max_pages=200):
    """Page NEARBlocks txns (desc) until receipts are older than the window.

    Returns (receipts, pages_fetched, oldest_ts_ns_seen, stalled). Receipts
    are the raw dicts; filtering happens in filter_sweeps(). `stalled` is
    True when paging stopped making progress (a page whose oldest receipt
    is no older than the previous page's — NEARBlocks caps deep paging, so
    without this guard an --all-time run would grind to max_pages).
    """
    receipts, pages = [], 0
    oldest = None
    prev_oldest = None
    stalled = False
    for page in range(1, max_pages + 1):
        url = NEARBLOCKS_TXNS.format(wallet=wallet)
        r = get_with_retry(url, params={"page": page, "per_page": 100, "order": "desc"})
        doc = json.loads(r.text, parse_float=Decimal)
        txns = doc.get("txns") or []
        pages += 1
        if not txns:
            break
        page_oldest = min(int(t["block_timestamp"]) for t in txns)
        if prev_oldest is not None and page_oldest >= prev_oldest:
            stalled = True
            print(f"[{wallet}] page {page}: STALLED (oldest {dstr(page_oldest)} "
                  f"not older than {dstr(prev_oldest)}) — stopping",
                  file=sys.stderr, flush=True)
            break
        prev_oldest = page_oldest
        receipts.extend(txns)
        oldest = page_oldest
        print(f"[{wallet}] page {page}: {len(receipts)} receipts, "
              f"oldest {dstr(oldest)}", flush=True)
        if stop_before_ts_ns is not None and oldest < stop_before_ts_ns:
            break
        time.sleep(1.0)
    return receipts, pages, oldest, stalled


def filter_sweeps(receipts, wallet):
    """intents.near -> wallet TRANSFER receipts only, normalised."""
    out = []
    for t in receipts:
        if t.get("predecessor_account_id") != INTENTS:
            continue
        actions = t.get("actions") or []
        if not actions or actions[0].get("action") != "TRANSFER":
            continue
        dep = actions[0].get("deposit")
        if dep is None:
            continue
        out.append({
            "tx_hash": t.get("transaction_hash"),
            "receipt_id": t.get("receipt_id"),
            "wallet": wallet,
            "block_height": (t.get("block") or {}).get("block_height"),
            "timestamp_ns": int(t["block_timestamp"]),
            "date": dstr(t["block_timestamp"]),
            "deposit_yocto": str(Decimal(dep)),
            "deposit_near": str(Decimal(dep) / YOCTO),
        })
    return out


# ------------------------------------------------------------------ prices
def daily_prices():
    """{date: {"close": float, "mean": float}} NEAR USD prices.

    CoinGecko hourly points -> last point per UTC day (close) and intraday
    mean. The mean is a sensitivity check: in a fast-moving market the
    close-vs-mean choice moves the 30d USD total (measured 2026-11-10:
    +0.53% for mean vs close). Falls back to NEARBlocks /v1/charts daily
    near_price (close only; mean == close there) on any failure.
    Returns (prices, source).
    """
    try:
        r = get_with_retry(COINGECKO_CHART)
        pts = r.json().get("prices") or []
        by_day = {}
        for ts_ms, price in pts:
            d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            by_day.setdefault(d, []).append(float(price))
        if len(by_day) >= 7:
            return ({d: {"close": v[-1], "mean": sum(v) / len(v)}
                     for d, v in by_day.items()},
                    "CoinGecko /coins/near/market_chart days=35 "
                    "(daily close; mean shown as sensitivity)")
    except Exception as e:  # noqa: BLE001 - fallback is the point
        print(f"[prices] CoinGecko failed ({e}); falling back to NEARBlocks charts",
              file=sys.stderr)
    r = get_with_retry(NEARBLOCKS_CHARTS)
    rows = r.json().get("charts") or []
    by_day = {row["date"][:10]: {"close": float(row["near_price"]),
                                 "mean": float(row["near_price"])}
              for row in rows if row.get("near_price")}
    return by_day, "NEARBlocks /v1/charts daily near_price"


# ------------------------------------------------------- comparison sources
def fetch_defillama(kind):
    r = get_with_retry(DEFILLAMA_FEES.format(kind=kind))

    return r.json()


def parse_money(s):
    s = s.strip().lstrip("$").replace(",", "")
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1:], 1)
    if s[-1:] in "KMB":
        s = s[:-1]
    return float(s) * mult


def fetch_revenue_dashboard():
    """revenue.near.org SSR parse (same approach as src/fetch.py).

    Wallet totals use the unambiguous RSC `nearAmount` JSON objects, NOT
    the visible-table regex: the table regex misattributes values across
    rows (verified 2026-11-10: it reported buybacks=555,348.3 NEAR, which
    is 1csfundsadmin's value; true buybacks all-time is 1,730,368.0 NEAR).
    """
    r = get_with_retry(REVENUE_URL)

    u = r.text.replace('\\"', '"').replace("\\\\", "\\")
    out = {"extraction_method": "SSR HTML (RSC payload) parse, no browser"}
    m = re.search(r'"children":"Net revenue".{0,600}?"value":"\$\$([0-9.,]+[KMB])"', u, re.S)
    if m:
        out["net_revenue_30d_usd"] = parse_money(m.group(1))
    m = re.search(r'"children":"Fees generated".{0,600}?"value":"\$\$([0-9.,]+[KMB])"', u, re.S)
    if m:
        out["gross_fees_30d_usd_dashboard"] = parse_money(m.group(1))
    split = {}
    for mech in ("pp_fe", "pp_b2b", "pp_qi"):
        for win in ("all_time", "ytd", "d30", "d7"):
            m = re.search(r'"' + mech + "_" + win + r'":([0-9.]+)', u)
            if m:
                split.setdefault(win, {})[mech] = float(m.group(1))
    out["capture_split_by_window"] = split
    out["capture_rate_by_window"] = {w: round(sum(v.values()), 4)
                                     for w, v in split.items() if len(v) == 3}
    wallets = {}
    for m in re.finditer(
            r'"name":"([a-z0-9._-]+)","nearAmount":([0-9.]+),"share":([0-9.]+)', u):
        wallets[m.group(1)] = {"near_all_time": float(m.group(2)),
                                "share_pct": float(m.group(3))}
    out["revenue_wallets_all_time_near"] = wallets
    out["revenue_wallets_total_near"] = round(
        sum(w["near_all_time"] for w in wallets.values()), 2)
    return out


# ------------------------------------------------- archival RPC verification
def archival_verify(sample):
    """Verify sampled sweeps against the public archival RPC directly.

    For each sampled sweep: EXPERIMENTAL_tx_status(tx_hash, wallet) must
    return FINAL and contain a receipt with receiver_id == wallet whose
    Transfer deposit equals the NEARBlocks deposit. Returns a list of
    per-sample verdicts (pass/fail + evidence/error).
    """
    verdicts = []
    for s in sample:
        entry = {"tx_hash": s["tx_hash"], "wallet": s["wallet"], "date": s["date"]}
        try:
            r = None
            delay = 5.0
            for attempt in range(5):
                try:
                    r = SESSION.post(ARCHIVAL_RPC, json={
                        "jsonrpc": "2.0", "id": "recon-verify",
                        "method": "EXPERIMENTAL_tx_status",
                        "params": [s["tx_hash"], s["wallet"]]}, timeout=TIMEOUT)
                except requests.RequestException as e:
                    if attempt == 4:
                        raise
                    time.sleep(delay)
                    delay *= 2
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt == 4:
                        r.raise_for_status()
                    time.sleep(delay)
                    delay *= 2
                    continue
                break
            r.raise_for_status()
            doc = r.json()
            if "error" in doc:
                entry.update({"verified": False, "error": doc["error"]})
                verdicts.append(entry)
                continue
            res = doc.get("result") or {}
            entry["final_execution_status"] = res.get("final_execution_status")
            match = None
            for rc in res.get("receipts") or []:
                rec = (rc.get("receipt") or {}).get("Action") or {}
                if rc.get("receiver_id") != s["wallet"]:
                    continue
                for a in rec.get("actions") or []:
                    if "Transfer" in a:
                        match = a["Transfer"].get("deposit")
            entry["archival_deposit_yocto"] = match
            entry["nearblocks_deposit_yocto"] = s["deposit_yocto"]
            # Exact-int vs float comparison: allow 1e-9 relative tolerance
            # (float noise in NEARBlocks' deposit is ~1e-14 relative).
            rel_diff = None
            if match is not None:
                a, b = Decimal(match), Decimal(s["deposit_yocto"])
                rel_diff = str(abs(a - b) / a) if a else None
            entry["relative_difference"] = rel_diff
            entry["verified"] = (
                res.get("final_execution_status") == "FINAL"
                and match is not None
                and rel_diff is not None
                and Decimal(rel_diff) < Decimal("1e-9"))
            verdicts.append(entry)
        except Exception as e:  # noqa: BLE001 - record, don't crash the run
            entry.update({"verified": False, "error": str(e)})
            verdicts.append(entry)
        time.sleep(1.0)
    return verdicts


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--all-time", action="store_true",
                    help="enumerate every receipt (census cross-check)")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    end_date = datetime.now(timezone.utc).date()
    if args.all_time:
        start_date = None
        stop_ns = None
    else:
        start_date = end_date - timedelta(days=args.days - 1)
        stop_ns = int(datetime(start_date.year, start_date.month, start_date.day,
                               tzinfo=timezone.utc).timestamp() * 10**9)
    window = {"start": start_date.isoformat() if start_date else None,
              "end": end_date.isoformat(), "days": args.days,
              "all_time": args.all_time}

    # 1. receipts + sweeps
    all_sweeps, per_wallet = [], {}
    for w in WALLETS:
        receipts, pages, oldest, stalled = fetch_wallet_receipts(
            w, stop_before_ts_ns=stop_ns)
        sweeps = filter_sweeps(receipts, w)
        if start_date is not None:
            sweeps = [s for s in sweeps if s["date"] >= start_date.isoformat()]
        # Checkpoint per wallet so a killed run keeps its work.
        ck = REPO / "data" / "raw" / f"reconstruction_intents_receipts_{w}.json"
        ck.parent.mkdir(parents=True, exist_ok=True)
        ck.write_text(json.dumps({"generated_at_utc": utcnow(), "window": window,
                                  "wallet": w, "receipts": receipts}, indent=2,
                                 default=str))
        # Total inflows (ALL predecessors/actions) — the comparable figure
        # for revenue.near.org's wallet table, which counts total inflows,
        # not just intents.near sweeps. Before ~Apr 2026 fefundsadmin was
        # funded by auroraliqsupport.near transfers, not intents.near sweeps.
        total_inflow = sum(
            (Decimal((t.get("actions") or [{}])[0].get("deposit") or 0)
             / YOCTO) for t in receipts)
        per_wallet[w] = {
            "receipts_scanned": len(receipts), "pages": pages,
            "paging_stalled": stalled,
            "total_inflow_near_all_receipts": str(total_inflow),
            "oldest_receipt_date": dstr(oldest) if oldest else None,
            "sweeps_in_window": len(sweeps),
            "sweeps_total_near": str(sum(Decimal(s["deposit_near"]) for s in sweeps)),
            "non_intents_receipts_in_window": len(
                [t for t in receipts if t.get("predecessor_account_id") != INTENTS
                 and dstr(t["block_timestamp"]) >= start_date.isoformat()])
            if start_date is not None else None,
        }
        all_sweeps.extend(sweeps)
        print(f"[{w}] {len(receipts)} receipts, {pages} pages, "
              f"{len(sweeps)} intents.near sweeps in window, "
              f"{per_wallet[w]['sweeps_total_near']} NEAR")
    # Dedupe: NEARBlocks paging can return the same receipt on two adjacent
    # pages (observed 2026-11-10: receipt 2fZe1oad5NFftw6VFGWKtupf6gfHTDyy5x1jh8uRBqqE
    # twice, buybacks, 2026-04-23, 1,314.37 NEAR). Dedupe by receipt_id;
    # a single tx yielding two DISTINCT receipts to the same wallet is still
    # counted twice, as it should be (two transfers).
    seen = set()
    deduped = []
    for sw in all_sweeps:
        if sw["receipt_id"] in seen:
            continue
        seen.add(sw["receipt_id"])
        deduped.append(sw)
    duplicate_receipts_removed = len(all_sweeps) - len(deduped)
    all_sweeps = deduped
    # duplicate tx_hash guard: one sweep tx must yield exactly one wallet receipt
    hashes = [s["tx_hash"] for s in all_sweeps]
    dupes = len(hashes) - len(set(hashes))

    # 2. prices + USD
    prices, price_source = daily_prices()
    missing_price_days = sorted({s["date"] for s in all_sweeps} - set(prices))
    for s in all_sweeps:
        p = prices.get(s["date"])
        if p:
            s["near_usd_close"] = p["close"]
            s["near_usd_mean"] = p["mean"]
            s["usd"] = str(Decimal(s["deposit_near"]) * Decimal(str(p["close"])))
            s["usd_at_daily_mean"] = str(Decimal(s["deposit_near"])
                                         * Decimal(str(p["mean"])))
        else:
            s["near_usd_close"] = s["near_usd_mean"] = None
            s["usd"] = s["usd_at_daily_mean"] = None
    by_date = {}
    for s in all_sweeps:
        d = by_date.setdefault(s["date"], {"near": Decimal(0), "usd": Decimal(0),
                                           "usd_mean": Decimal(0), "sweeps": 0,
                                           "price_close": s.get("near_usd_close"),
                                           "price_mean": s.get("near_usd_mean")})
        d["near"] += Decimal(s["deposit_near"])
        if s["usd"] is not None:
            d["usd"] += Decimal(s["usd"])
            d["usd_mean"] += Decimal(s["usd_at_daily_mean"])
        d["sweeps"] += 1
    total_near = sum(Decimal(s["deposit_near"]) for s in all_sweeps)
    total_usd = sum(Decimal(s["usd"]) for s in all_sweeps if s["usd"] is not None)
    total_usd_mean = sum(Decimal(s["usd_at_daily_mean"]) for s in all_sweeps
                         if s["usd_at_daily_mean"] is not None)

    # 3. comparison sources (live, same run)
    comparisons, errors = {}, {}
    try:
        fees = fetch_defillama("dailyFees")
        rev = fetch_defillama("dailyRevenue")
        def series_sum(doc):
            # DefiLlama totalDataChart timestamps are SECONDS (see
            # src/model.py fee_series); normalise before converting.
            pts = doc.get("totalDataChart") or []
            s = 0.0
            for ts, v in pts:
                ts = int(ts)
                if ts < 1_000_000_000_000:
                    ts *= 1000
                d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                if start_date is None or d >= start_date.isoformat():
                    s += float(v)
            return s
        comparisons["defillama"] = {
            "fees_total30d_headline_usd": fees.get("total30d"),
            "fees_total7d_headline_usd": fees.get("total7d"),
            "fees_total24h_headline_usd": fees.get("total24h"),
            "fees_series_sum_window_usd": series_sum(fees),
            "revenue_total30d_headline_usd": rev.get("total30d"),
            "revenue_total7d_headline_usd": rev.get("total7d"),
            "revenue_total24h_headline_usd": rev.get("total24h"),
            "revenue_series_sum_window_usd": series_sum(rev),
            "note": ("headline totals are DefiLlama trailing totals at fetch time; "
                     "series sums cover exactly the reconstruction window dates"),
        }
    except Exception as e:  # noqa: BLE001
        errors["defillama"] = str(e)
    try:
        comparisons["revenue_near_org"] = fetch_revenue_dashboard()
    except Exception as e:  # noqa: BLE001
        errors["revenue_near_org"] = str(e)

    # 4. archival RPC spot verification (spread across the window)
    verify = []
    if not args.no_verify and all_sweeps:
        ordered = sorted(all_sweeps, key=lambda s: s["date"])
        idx = {0, len(ordered) // 2, len(ordered) - 1}
        if len(ordered) > 3:
            idx |= {len(ordered) // 4, (3 * len(ordered)) // 4}
        sample = [ordered[i] for i in sorted(idx)]
        print(f"[verify] archival RPC check on {len(sample)} sampled sweeps...")
        verify = archival_verify(sample)

    out = {
        "generated_at_utc": utcnow(),
        "method": ("intents.near -> revenue-wallet TRANSFER receipts via "
                   "NEARBlocks indexer API; USD at daily NEAR close"),
        "window": window,
        "wallets": WALLETS,
        "per_wallet": per_wallet,
        "duplicate_tx_hashes": dupes,
        "duplicate_receipts_removed": duplicate_receipts_removed,
        "totals": {
            "sweeps": len(all_sweeps),
            "near": str(total_near),
            "usd": str(total_usd),
            "usd_at_daily_mean_price": str(total_usd_mean),
            "price_source": price_source,
            "missing_price_days": missing_price_days,
        },
        "daily": {d: {"near": str(v["near"]), "usd": str(v["usd"]),
                      "usd_at_daily_mean_price": str(v["usd_mean"]),
                      "price_close": v["price_close"],
                      "price_mean": v["price_mean"],
                      "sweeps": v["sweeps"]} for d, v in sorted(by_date.items())},
        "comparisons": comparisons,
        "archival_rpc_verification": verify,
        "errors": errors,
    }
    op = Path(args.out)
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(out, indent=2))
    # cache the raw sweeps for audit
    RECEIPTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RECEIPTS_CACHE.write_text(json.dumps(
        {"generated_at_utc": utcnow(), "window": window, "sweeps": all_sweeps},
        indent=2))
    print(f"[done] {len(all_sweeps)} sweeps, {total_near} NEAR, ${total_usd:,.2f} "
          f"-> {op}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
