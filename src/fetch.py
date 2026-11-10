#!/usr/bin/env python3
"""Fetch all Tier-1 data for the NEAR Investment Thesis (Hackathon 2026).

Sources (all free, no API key):
  - NEARBlocks API: /v1/stats, /v1/validators, /v1/blocks/latest,
    /v1/account/intents.near, /v1/account/buybacks.multisignature.near,
    /v1/charts (FULL daily series 2020-07-21 -> today: txns, active/new
    accounts, gas fees, price, supply — verified live 2026-11-10)
  - DefiLlama: summary/dexs/near-intents (daily Intents VOLUME series,
    2024-12-10 -> today — verified live 2026-11-10)
  - NEAR mainnet RPC: status, gas_price, EXPERIMENTAL_protocol_config
  - CoinGecko free API: /simple/price (4 coins), /coins/{id}/market_chart days=365
  - DefiLlama: summary/fees/{near-intents,NEAR,thorchain,chainflip,debridge,
    solana,avalanche,ethereum}, v2/historicalChainTvl/NEAR, /chains,
    /overview/fees
  - revenue.near.org: SSR HTML parse (the dashboard is JS-rendered, but its
    live figures are server-rendered into the HTML payload — no browser needed).
    Extracts the 30D net-revenue / gross-fee pair and the per-mechanism
    capture split (pp_fe / pp_b2b / pp_qi) for the all-time / YTD / 30D / 7D
    windows. See BUILD_NOTES.md for the extraction method and validation.

Every response is cached to data/raw/ with a fetch-timestamp manifest
(data/manifest.json: source URL, fetched_at UTC, bytes, status).
CoinGecko free tier: 30 calls/min — we sleep 2.5 s between CoinGecko calls
(5 calls total, well inside the limit).

Daily-txn series via NEARBlocks /v1/txns paging is NOT attempted here:
measured max page size is 100 txns and one page takes ~1.6 s, while the
chain does ~1M txns/day, so one day of history needs ~10,400 pages (~4.6 h
sequential). It is also unnecessary now: the bare /v1/charts endpoint
(never tested in the research phase — only /v1/charts/daily-txns etc.,
all 404) returns the full daily series. See BUILD_NOTES.md. No DAU series
is fabricated: every daily figure comes from /v1/charts.

Payload note: /v1/charts is ~1.5 MB (2,303 daily rows). The response is
written to disk once as raw bytes (save() below) and parsed only later by
model.py — it is never held in memory twice in this script.

Usage:  python3 src/fetch.py [--raw-dir DIR] [--manifest PATH]
Exit code 0 even if a non-critical source fails; failures are recorded in
the manifest with status != 200 and listed on stdout.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "data" / "raw"
MANIFEST = REPO / "data" / "manifest.json"

CG_SLEEP = 2.5  # seconds between CoinGecko calls (30/min limit)
TIMEOUT = 60

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "near-thesis-fetch/1.0 (+hackathon research)"})

# (cache filename, url, method, json body or None, is_coingecko)
GETS = [
    # --- NEARBlocks ---
    ("nearblocks_stats.json", "https://api.nearblocks.io/v1/stats", None),
    ("nearblocks_validators.json", "https://api.nearblocks.io/v1/validators", None),
    ("nearblocks_blocks_latest.json", "https://api.nearblocks.io/v1/blocks/latest", None),
    ("nearblocks_account_intents.json", "https://api.nearblocks.io/v1/account/intents.near", None),
    ("nearblocks_account_buybacks.json", "https://api.nearblocks.io/v1/account/buybacks.multisignature.near", None),
    # Full daily series (2,303 pts, 2020-07-21 -> today). ~1.5 MB: written
    # to disk once as raw bytes, parsed only in model.py.
    ("nearblocks_charts.json", "https://api.nearblocks.io/v1/charts", None),
    # --- CoinGecko (sleep between these) ---
    ("coingecko_simple_price.json",
     "https://api.coingecko.com/api/v3/simple/price?ids=near,solana,avalanche-2,ethereum"
     "&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
     "&include_24hr_change=true", "coingecko"),
    ("coingecko_market_chart_near_365.json",
     "https://api.coingecko.com/api/v3/coins/near/market_chart?vs_currency=usd&days=365", "coingecko"),
    ("coingecko_market_chart_solana_365.json",
     "https://api.coingecko.com/api/v3/coins/solana/market_chart?vs_currency=usd&days=365", "coingecko"),
    ("coingecko_market_chart_avalanche-2_365.json",
     "https://api.coingecko.com/api/v3/coins/avalanche-2/market_chart?vs_currency=usd&days=365", "coingecko"),
    ("coingecko_market_chart_ethereum_365.json",
     "https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days=365", "coingecko"),
    # --- DefiLlama fees ---
    ("defillama_fees_near-intents.json",
     "https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees", None),
    ("defillama_fees_NEAR.json",
     "https://api.llama.fi/summary/fees/NEAR?dataType=dailyFees", None),
    ("defillama_fees_thorchain.json",
     "https://api.llama.fi/summary/fees/thorchain?dataType=dailyFees", None),
    ("defillama_fees_chainflip.json",
     "https://api.llama.fi/summary/fees/chainflip?dataType=dailyFees", None),
    ("defillama_fees_debridge.json",
     "https://api.llama.fi/summary/fees/debridge?dataType=dailyFees", None),
    ("defillama_fees_lifi.json",
     "https://api.llama.fi/summary/fees/lifi?dataType=dailyFees", None),
    ("defillama_fees_solana.json",
     "https://api.llama.fi/summary/fees/solana?dataType=dailyFees", None),
    ("defillama_fees_avalanche.json",
     "https://api.llama.fi/summary/fees/avalanche?dataType=dailyFees", None),
    ("defillama_fees_ethereum.json",
     "https://api.llama.fi/summary/fees/ethereum?dataType=dailyFees", None),
    # Intents daily VOLUME (DefiLlama dexs dimension, not fees).
    # totalDataChart: 699 daily pts, 2024-12-10 -> today. Verified live
    # 2026-11-10: 200, 50,347 B. If this 404s, model.py drops the volume
    # leg (M15/chart_09) instead of faking volume.
    ("defillama_dexs_near-intents.json",
     "https://api.llama.fi/summary/dexs/near-intents", None),
    # --- DefiLlama TVL / overview ---
    ("defillama_historical_tvl_NEAR.json",
     "https://api.llama.fi/v2/historicalChainTvl/NEAR", None),
    ("defillama_chains.json", "https://api.llama.fi/chains", None),
    ("defillama_overview_fees.json", "https://api.llama.fi/overview/fees", None),
]

# RPC calls are POSTs: (cache filename, method, params)
RPC_URL = "https://rpc.mainnet.near.org"
RPC_CALLS = [
    ("rpc_status.json", "status", []),
    ("rpc_gas_price.json", "gas_price", [None]),
    # NB: params must be a MAP for this method — a list gives
    # REQUEST_VALIDATION_ERROR ("invalid type: sequence").
    ("rpc_protocol_config.json", "EXPERIMENTAL_protocol_config", {"finality": "final"}),
]

REVENUE_URL = "https://revenue.near.org/"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save(name: str, content: bytes, manifest: dict, url: str, status: int) -> None:
    path = RAW_DIR / name
    path.write_bytes(content)
    manifest[name] = {
        "source_url": url,
        "fetched_at_utc": utcnow(),
        "bytes": len(content),
        "status": status,
    }


def parse_money(s: str):
    """'$5.41M' / '$37.94B' / '$60.40M' / '644.7K' -> float USD (or units)."""
    s = s.strip().lstrip("$").replace(",", "")
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1:], 1)
    if s[-1:] in "KMB":
        s = s[:-1]
    return float(s) * mult


def parse_revenue_dashboard(html: str) -> dict:
    """Extract live figures from revenue.near.org's server-rendered HTML.

    The page is a Next.js app; the live numbers are embedded in the RSC
    payload (escaped JSON). Validation of the interpretation:
      * pp_fe / pp_b2b / pp_qi are the three capture mechanisms (direct
        fees / B2B / quote-improvement). Their sums per window:
        all-time 0.1195+0.0525+0.0191 = 0.1911 (19.1%)
        YTD     0.1329+0.0711+0.0258 = 0.2298 (23.0%)
        30D     0.2140+0.1090+0.0368 = 0.3598 (36.0%)
        7D      0.1820+0.0981+0.0422 = 0.3223 (32.2%)
      * The 30D card pair (net revenue $1.95M / fees generated $5.41M)
        gives 1.95/5.41 = 36.0% — identical to the 30D pp_* sum.
      * Headline revenue $11.54M / all-time gross fees $60.40M = 19.1% —
        identical to the all-time pp_* sum. The headline figure's window
        is not labelled in the payload, so it is stored as displayed
        ("headline_revenue_usd", window unlabelled) and only used as a
        cross-check, never as a model input.
    """
    u = html.replace('\\"', '"').replace("\\\\", "\\")
    out = {"extraction_method": "SSR HTML (RSC payload) parse, no browser",
           "extraction_notes": "pp_* = capture-mechanism shares of gross fees; "
           "totals cross-checked against the displayed $ card pairs (see docstring)."}

    # 30D card pair: "Net revenue" $X / "Fees generated" $Y
    m = re.search(r'"children":"Net revenue".{0,600}?"value":"\$\$([0-9.,]+[KMB])"', u, re.S)
    if m:
        out["net_revenue_30d_usd"] = parse_money(m.group(1))
    m = re.search(r'"children":"Fees generated".{0,600}?"value":"\$\$([0-9.,]+[KMB])"', u, re.S)
    if m:
        out["gross_fees_30d_usd_dashboard"] = parse_money(m.group(1))
    if "net_revenue_30d_usd" in out and "gross_fees_30d_usd_dashboard" in out:
        out["capture_rate_30d_from_cards"] = (
            out["net_revenue_30d_usd"] / out["gross_fees_30d_usd_dashboard"])

    # Hero headline revenue (window not labelled in payload)
    m = re.search(r'"value":"\$\$([0-9.,]+[KMB])","duration":2', u)
    if m:
        out["headline_revenue_usd"] = parse_money(m.group(1))
        out["headline_revenue_window"] = "UNLABELLED in page payload (consistent with all-time net revenue)"

    # All-time stat cards
    for label, key in [
        ("Total Fees \u00b7 all-time", "gross_fees_all_time_usd"),
        ("Intent Volume \u00b7 all-time", "intent_volume_all_time_usd"),
        ("Confidential TVL \u00b7 Now", "confidential_tvl_usd"),
        ("Unique Users \u00b7 30D", "unique_users_30d"),
    ]:
        m = re.search(r'"label":"' + re.escape(label) + r'","value":"\$*([0-9.,]+[KMB])"', u)
        if m:
            out[key] = parse_money(m.group(1))

    # Capture-mechanism split per window
    split = {}
    for mech in ("pp_fe", "pp_b2b", "pp_qi"):
        for win in ("all_time", "ytd", "d30", "d7"):
            m = re.search(r'"' + mech + "_" + win + r'":([0-9.]+)', u)
            if m:
                split.setdefault(win, {})[mech] = float(m.group(1))
    out["capture_split_by_window"] = split
    out["capture_rate_by_window"] = {
        win: round(sum(v.values()), 4) for win, v in split.items() if len(v) == 3}
    # Wallet breakdown (all-time, static table)
    wallets = {}
    for m in re.finditer(
            r'>(fefundsadmin\.sputnik-dao\.near|buybacks\.multisignature\.near'
            r'|1csfundsadmin\.sputnik-dao\.near)<.*?([0-9,]+\.[0-9]+)<!-- --> NEAR',
            u, re.S):
        wallets[m.group(1)] = float(m.group(2).replace(",", ""))
    out["revenue_wallets_all_time_near"] = wallets
    out["revenue_wallets_total_near"] = round(sum(wallets.values()), 1)
    return out


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    failures = []

    for name, url, kind in GETS:
        if kind == "coingecko":
            time.sleep(CG_SLEEP)
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            # CoinGecko free tier 429s under burst load (seen 2026-11-10 on
            # the ethereum market_chart call, which also clobbered the good
            # cached file — hence the retry BEFORE save()). One retry after
            # a 60 s backoff; if it still 429s, the failure is recorded and
            # model.py drops that peer instead of using a 429 body.
            if r.status_code == 429:
                print(f"429 {name} — backing off 60 s and retrying once")
                time.sleep(60)
                r = SESSION.get(url, timeout=TIMEOUT)
            save(name, r.content, manifest, url, r.status_code)
            print(f"{r.status_code} {name} ({len(r.content)} B)")
            if r.status_code != 200:
                failures.append((name, r.status_code))
        except Exception as e:  # noqa: BLE001 - record and continue
            print(f"ERROR {name}: {e}")
            failures.append((name, str(e)))

    for name, method, params in RPC_CALLS:
        try:
            r = SESSION.post(RPC_URL, json={
                "jsonrpc": "2.0", "id": method, "method": method, "params": params,
            }, timeout=TIMEOUT)
            save(name, r.content, manifest, f"{RPC_URL}#{method}", r.status_code)
            print(f"{r.status_code} {name} ({len(r.content)} B)")
            if r.status_code != 200:
                failures.append((name, r.status_code))
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {name}: {e}")
            failures.append((name, str(e)))

    # revenue.near.org — HTML + parsed extraction
    try:
        r = SESSION.get(REVENUE_URL, timeout=TIMEOUT)
        save("revenue_near_org.html", r.content, manifest, REVENUE_URL, r.status_code)
        print(f"{r.status_code} revenue_near_org.html ({len(r.content)} B)")
        if r.status_code == 200:
            parsed = parse_revenue_dashboard(r.text)
            blob = json.dumps(parsed, indent=2).encode()
            save("revenue_near_org_parsed.json", blob, manifest,
                 REVENUE_URL + " (parsed SSR payload)", 200)
            print("  parsed capture 30D:",
                  parsed.get("capture_rate_by_window", {}).get("d30"),
                  "| net/gross 30D:",
                  parsed.get("capture_rate_30d_from_cards"))
        else:
            failures.append(("revenue_near_org.html", r.status_code))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR revenue_near_org: {e}")
        failures.append(("revenue_near_org", str(e)))

    manifest["_fetch_completed_utc"] = utcnow()
    manifest["_failures"] = failures
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"\nmanifest -> {MANIFEST}")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        print("Non-critical failures are recorded; model.py must handle them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
