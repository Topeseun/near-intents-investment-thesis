# NEAR as a Cross-Chain Settlement Business — Investment Thesis

**NEAR Hackathon 2026 · Investment Thesis track** · Development ends **Fri 14 Nov 2026, 23:59 UTC** · Solo builder, free resources only, no paid APIs.

## Thesis

NEAR's base layer barely earns anything — its Intents layer already grossed $5,578,208 of fees in 30 days, keeps a growing share (measured 30-day capture rate 35.97%) for NEAR buybacks, and is the only part of NEAR with a compounding, measurable revenue curve. The long-term investment case is not "cheap fast L1" but "toll road on cross-chain volume": this repo values NEAR on retained Intents revenue (fee-capture DCF), with base-layer usage and staking economics as the supporting chapters that test whether the toll road has a moat.

## Headline results (data fetched 2026-11-10 ~03:05 UTC)

| Figure | Value |
|---|---|
| NEAR price / market cap | $3.60 / ~$4.72B |
| F30 — trailing-30d Intents gross fees | **$5,578,208** (DefiLlama) |
| Intents 30d volume (new, M15) | **$3,714,703,671** (DefiLlama dexs daily series; endpoint total $3,561,518,211) — −22.0% vs prior 30d; implied gross fee rate **15.02 bps** |
| Measured 30d capture rate (retained ÷ gross) | **35.97%** (revenue.near.org; rising: 19.1% all-time → 23.0% YTD → 36.0% 30d) |
| R0 — annualised retained revenue | **$24,077,777/yr** |
| DCF base value/token (r=15%, g=10%, c=35.97%) | **$0.42 vs $3.60 price — 11.8% of the price** |
| Market cap / retained revenue | **196.2×** (gross-fee basis: 70.6×) |
| NEAR issued/yr vs bought/yr | 32,782,327 vs 6,688,271 — net **+26,094,055 NEAR/yr, still inflationary** |
| Break-even retained revenue | **$118.0M/yr, ~4.9× current R0** |
| Daily txns / active accounts (new, M12–M13) | 895,302 txns/day (**93.6% below** the 13,935,402 peak of 2023-12-01) · 77,752 active accounts/day (**96.6% below** the 2,256,512 peak of 2024-04-22) |
| New accounts, 30d (new, M14) | 287,194 (−18.9% vs prior 30d); net +265,067 after deletions |
| Price vs Intents fees, weekly (new, M16) | Pearson r = **0.06** (n=366 weeks) — essentially no weekly co-movement; price vs base gas fees r = 0.57. Correlation only, no lead-lag claim. |
| Staking APY / max inflation / real yield | 4.91% / 2.5% / 2.41pp |
| NEAR Intents 30d fees vs competitors | NEAR $5.58M > Chainflip $2.79M > deBridge $0.44M > THORChain $0.019M |

**The honest framing:** retained revenue alone supports ~12% of the price. No cell in the 27-cell sensitivity grid (capture ≤35% × growth ≤20% at r=12%) reaches $3.60 — the best valid cell is $1.03. The case for NEAR is the *option value* on fee growth (g) and capture (c) rising, which the sensitivity grid makes explicit. This repo does not hide that; the dashboard leads with it. The new daily-activity series adds the bear leg the thesis was missing: base-layer usage has collapsed more than 90% from its peaks even while Intents fees grew — the moat, if there is one, is the Intents product, not base-layer activity.

## Dated predictions

Seven falsifiable predictions, committed 2026-11-10 — see [PREDICTIONS.md](PREDICTIONS.md).
Each names a numeric threshold, a resolution date (31 Dec 2026 – 28 Feb 2027) and
the exact public source that decides it (DefiLlama, revenue.near.org, NEARBlocks,
CoinGecko). They cover the thesis's load-bearing claims: Intents 30d fees
(≥ $5,578,208 by 31 Dec 2026) and capture rate (≥ 35.97% by 31 Jan 2027), the DCF
conclusion (value/token still < 25% of price on 28 Feb 2027), Intents volume
(≥ $3B by 31 Dec 2026), the lead over Chainflip (≥ 1.5× by 31 Jan 2027), base-layer
usage staying collapsed (< 100,000 active accounts/day, 30d avg, by 28 Feb 2027),
and price still not tracking fees (|weekly r| < 0.30). **A missed prediction
counts against this thesis.** The dashboard renders them from
`data/predictions.json`.

## Independent on-chain revenue check

The capture rate above (35.97%) comes from revenue.near.org, a third-party
aggregator. `src/reconstruct_intents.py` rebuilds the **retained leg**
independently from on-chain receipts: every `intents.near` → revenue-wallet
`TRANSFER` receipt (wallets `fefundsadmin.sputnik-dao.near`,
`buybacks.multisignature.near`, `1csfundsadmin.sputnik-dao.near`), valued at
each day's NEAR close, with sampled sweeps re-verified against the public
archival RPC. Full method, results and reconciliation:
[`docs/RECONCILIATION.md`](docs/RECONCILIATION.md).

Headline, 30d window 2026-10-12 → 2026-11-10 (fresh run 2026-11-10 ~19:30 UTC):
**1,125 sweeps, 406,488 NEAR, $1,807,930** — 98.4% of DefiLlama's 30d
revenue ($1,838,057) and 102.9% of its daily-series sum over the same dates
($1,756,771), but 90.0% of revenue.near.org's displayed 30D net revenue
($2.01M). The gap is decomposed in `docs/RECONCILIATION.md` §8: it is the
pp_qi (quote-improvement) leg, counted in the dashboard's net revenue but
not received in the revenue wallets. The cash capture rate is **~32.8%**
(vs 35.97% from revenue.near.org alone). No thesis number has been changed
on this evidence — see `docs/RECONCILIATION.md` §8.6 for the sensitivity
(R0 ~$21.9M/yr and DCF ~$0.38/token at 32.8% capture, same conclusion). Reproduce:

```bash
python3 src/reconstruct_intents.py [--days 30] [--all-time]
```

Output: `data/processed/reconstruction_intents.json` (raw sweeps cached in
`data/raw/reconstruction_intents_receipts.json`).

## What this repo contains

```
├── README.md                     # this file
├── src/
│   ├── fetch.py                  # Tier-1 API fetches only (no keys); caches to data/raw/ + data/manifest.json
│   ├── model.py                  # Fee-capture DCF, metrics M1–M16, benchmarks → data/processed/*.json
│   ├── charts.py                 # 9 charts → dashboard/assets/*.png (+ .svg twins)
│   ├── build.py                  # Runs model.py then charts.py (no network)
│   ├── build_dashboard.py        # Renders dashboard/index.html from data/processed/*.json (no network)
│   ├── reconstruct_intents.py    # Independent on-chain rebuild of retained Intents revenue (see docs/RECONCILIATION.md)
│   └── assumptions.yaml          # THE one assumptions file (DCF knobs + scenario grid)
├── tests/
│   └── test_outputs.py           # stdlib-unittest checks (see "Tests" below)
├── data/
│   ├── raw/                      # 29 cached API responses (with data/manifest.json: source URL, fetched_at UTC, bytes)
│   ├── manifest.json             # Source URL + fetch timestamp for every cached response
│   └── processed/
│       ├── metrics.json          # M1–M16, each with source + fetched_at
│       ├── dcf.json              # Base-case DCF inputs + outputs
│       ├── sensitivity.json      # 27-cell grid (capture × growth × discount)
│       ├── benchmarks.json       # NEAR vs SOL/AVAX/ETH + Intents competitors
│       ├── chart_01_data.json … chart_09_data.json   # Per-chart numbers
│       └── BUILD_NOTES.md        # Pipeline/model build notes, gaps, corrections, reproducibility
├── docs/                         # GitHub Pages copy of dashboard/index.html + dashboard/assets/*.svg (same content)
│   └── RECONCILIATION.md         # On-chain revenue reconstruction: method, results, reconciliation
└── dashboard/
    ├── index.html                # Static dashboard (single page, no server, no external JS/CSS)
    ├── BUILD_NOTES.md            # Dashboard build notes (what was built, how to regenerate, verification)
    └── assets/
        └── chart01_*.png … chart09_*.png   # The 9 charts (PNG + SVG twins; PNGs are git-ignored)
```

What the code does, exactly:

- `src/fetch.py` fetches NEARBlocks stats/validators/blocks/accounts **and the full daily `/v1/charts` series (2,303 points, 2020-07-21 → today)**, NEAR RPC status/gas price/protocol config, CoinGecko prices + 365d market charts (4 coins), DefiLlama Intents/chain/competitor fees + TVL **and the Intents daily volume series (`summary/dexs/near-intents`, 699 points from 2024-12-10)**, and parses the revenue.near.org server-rendered payload for the measured capture rate. Every response is cached to `data/raw/` with a timestamped manifest. No API keys. CoinGecko: 5 calls, 2.5 s sleep between them (30/min limit); a 429 gets one retry after a 60 s backoff.
- `src/model.py` computes the fee-capture DCF (Gordon growth: Value = R1/(r−g), R0 = F30 × 12 × capture), the 16 metrics M1–M16, the 27-cell sensitivity grid, and the peer/competitor benchmarks — all from the cache, no network.
- `src/charts.py` renders the 9 charts as PNGs (+ SVG twins) from the model outputs.
- `src/build_dashboard.py` renders `dashboard/index.html` from `data/processed/*.json`. Every number on the page is formatted from those JSONs — nothing is hardcoded — so re-running the pipeline and this script regenerates a dashboard that always matches the model.

## Reproduce in one command

```bash
python3 src/fetch.py && python3 src/build.py && python3 src/build_dashboard.py
```

Requirements: Python 3.12, `requests`, `pandas`, `matplotlib`, `PyYAML`, `numpy`. No API keys, no paid services, no server. Then open `dashboard/index.html` in any browser (or `python3 -m http.server` from `dashboard/`).

Verified: a clean re-run (`rm -rf data && python3 src/fetch.py && python3 src/build.py`) reproduces the fee-derived numbers exactly (F30 $5,578,208, capture 35.97%, R0 $24,077,777, DCF $0.4238/token); price-dependent numbers move only with the live price tick. See `data/processed/BUILD_NOTES.md` and `dashboard/BUILD_NOTES.md`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Stdlib `unittest` only — no new dependencies. 14 tests: every `data/processed/*.json` exists and parses; F30/capture/R0/DCF arithmetic is internally consistent (R0 = F30 × 12 × capture; Gordon growth; value/token = Value ÷ supply); the sensitivity grid is 3 × 3 × 3 = 27 cells with invalid g ≥ r cells null and valid cells matching the formula; buyback-vs-issuance arithmetic; M12–M16 sanity (peaks above current, percentages in range, volume positive, implied fee rate 1–100 bps, correlation in [−1, 1]); all 9 charts exist as PNG + SVG; the dashboard references all 9 SVGs; `docs/` mirrors `dashboard/index.html` byte-for-byte; the README contains the headline numbers (fee-stable figures + the all-time activity peaks).

## GitHub Pages

The dashboard is published from `docs/`: copy `dashboard/index.html` + `dashboard/assets/*.svg` into `docs/` (same content — the SVGs are text, so they push through text-only tooling; PNGs stay local). Enable it in the repo: **Settings → Pages → Build and deployment → Deploy from a branch → branch `main`, folder `/docs`** → Save. The site then serves at `https://<user>.github.io/<repo>/`. Re-copy `docs/` after any dashboard rebuild so Pages stays in sync with `dashboard/`.

## The 9 charts

1. Intents daily fees, May 2025 → Nov 2026 (549 pts, log scale + 30d moving average)
2. Intents fees vs base-chain gas fees (same log axis)
3. NEAR price vs trailing-30d Intents fees, indexed to 100 (365d)
4. Valuation multiples — mcap/annualised fees: NEAR (gross + retained) vs SOL/AVAX/ETH
5. Buyback vs issuance — NEAR bought/yr vs issued/yr under 3 capture scenarios
6. Staking economics — APY 4.91% vs inflation 2.5% vs real yield, stake + validators
7. Sensitivity heatmap — implied value/token across capture (15/25/35%) × growth (0/10/20%) at r=12%, invalid g≥r zone marked
8. Daily transactions & daily active accounts, 2020 → today (log scale, all-time peaks marked) — the usage collapse: txns 93.6% and active accounts 96.6% below peak
9. Intents daily volume & daily fees (log scale, two panels) — volume 30d $3.71B, implied gross fee rate 15.02 bps

## Data sources

| Source | What it gives | URL |
|---|---|---|
| DefiLlama API | NEAR Intents daily fees + aggregates; base-chain fees; peer/competitor fees; NEAR TVL | https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees |
| DefiLlama API | NEAR Intents daily volume (699 pts, 2024-12-10 → today) | https://api.llama.fi/summary/dexs/near-intents |
| NEARBlocks API | Daily activity series — txns, active/new accounts, gas fees, price (2,303 pts, 2020-07-21 → today) | https://api.nearblocks.io/v1/charts |
| revenue.near.org | Measured capture rate (30d net revenue ÷ gross fees, cross-checked vs per-mechanism split) | https://revenue.near.org/ |
| CoinGecko free API | Prices/market caps (NEAR, SOL, AVAX, ETH); 365d price/mcap history | https://api.coingecko.com/api/v3/simple/price |
| NEARBlocks API | Chain stats, validators (APY, stake, concentration) | https://api.nearblocks.io/v1/stats |
| NEAR mainnet RPC | Protocol config — max inflation cap 2.5% ([1,40]) | https://rpc.mainnet.near.org |

Every cached response is listed with its source URL and fetch timestamp in `data/manifest.json`; every metric carries its source + `fetched_at_utc` in `data/processed/metrics.json`.

## Assumptions

All model assumptions live in one file: [`src/assumptions.yaml`](src/assumptions.yaml). The DCF base case is r=15% (discount rate, WACC proxy), g=10% (perpetual growth of retained revenue — a forward assumption, *not* a trend extrapolation: trailing-30d fees are −30.5% vs the prior 30 days and the 365-day log-regression growth is ≈ −0.7%), capture scenarios 15/25/35% (the measured 30d rate, 35.97%, is the base case). Gordon growth requires g < r; cells with g ≥ r are null and shown as invalid.

## Limitations

- **Daily activity is measured — and it is weak.** The research-phase claim that "NEARBlocks has no public daily-stats endpoint" was wrong: the bare `/v1/charts` path (never tested — only suffixed paths like `/v1/charts/daily-txns`, all 404) returns the full daily series from 21 Jul 2020 (2,303 points). Daily txns are 93.6% below their 1 Dec 2023 peak (13,935,402/day) and daily active accounts 96.6% below their 22 Apr 2024 peak (2,256,512/day) — this **confirms** the ">90% decline from peak" claim, it does not contradict it. Early rows have gaps: `multichain_txns` is null before 14 Nov 2024 and `txn_volume` is null on 11 days in Jul–Aug 2020; neither field is used in any metric. Paging `/v1/txns` backwards stays cut (measured: ~10,400 pages / ~4.6 h for one day) — now unnecessary.
- **Volume is measured, with a shorter window.** DefiLlama `summary/dexs/near-intents` gives a daily Intents *volume* series (699 points from 10 Dec 2024): 30d volume $3,714,703,671 from the daily series vs the endpoint's own 30d total $3,561,518,211 (+4.3% — the endpoint's rolling window ends at fetch time, after the last daily point of 8 Nov). The implied gross fee rate (30d fees ÷ 30d volume) is 15.02 bps, matching the ~15 bps quoted in secondary sources — two independent series agreeing. The volume series starts Dec 2024, so it covers a shorter window than the fee series (May 2025) and the activity series (Jul 2020).
- **365-day price cap.** CoinGecko's free tier limits history to 365 days.
- **24-hour fee anomaly.** Intents fees for 9 Nov 2026 were $16,790 vs a 7-day daily average of ~$185,884 — a full-day value, so either a real one-day drop or a DefiLlama reporting lag. No single day is ever annualised; all annualisation uses 7d/30d trailing figures.
- **Fees are volatile, not a ramp.** Trailing-30d fees peaked at $8,236,902 on 14 Oct 2026 and are −32.3% below that peak. The full-series launch-ramp CAGR is a May–Aug 2025 artefact and is not quoted anywhere.
- **Revenue-dashboard caveats.** Its headline revenue figure ($11.54M) has an unlabelled window in the page payload and is never used as a model input. Its wallet table is partial: the live NEARBlocks balance of buybacks.multisignature.near (2,229,769 NEAR) exceeds the dashboard's traced all-time inflow (1,719,605.8 NEAR).
- **TVL endpoints disagree.** DefiLlama's NEAR historical-series last point ($171.1M) vs its /chains headline ($365.5M). The auditable series value is used.
- **Peer fees undercount.** DefiLlama chain-fee totals can miss revenue other methodologies include (notably Solana). Benchmarks rank within this dataset only.
- **LI.FI dropped from the benchmark.** DefiLlama returns 404 ("Fees for lifi not found").

Full detail: `data/processed/BUILD_NOTES.md`.

## Judging

Built for the NEAR Hackathon 2026 Investment Thesis track — "build a long-term investment thesis for NEAR and back it with data: onchain analytics, live dashboards and models anyone can re-run. Judged on the evidence, not the conviction." $250K prize pool paid in NEAR; per-track 1st $10K, 2nd $3K, 3rd $2K. Payout account (if awarded): `topeseun20.near`.

*Not investment advice. All figures are as fetched on 2026-11-10 ~03:05 UTC; re-run the pipeline for current data.*
