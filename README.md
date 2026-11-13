# NEAR as a Cross-Chain Settlement Business — Investment Thesis

**Verdict: overvalued on retained revenue.** Retained revenue alone supports $0.41 per token — 11.7% of the $3.50 price. The price itself implies retained revenue of $198.8M/yr (8.6× today's R₀). Separately, buybacks only stop the token from inflating when retained revenue reaches $114.8M/yr (4.9× today's R₀) — the break-even where buybacks match issuance (net +26,145,681 NEAR/yr today). The case for NEAR is the option on fee growth and rising capture, not today's cash flow.

**NEAR Hackathon 2026 · Investment Thesis track** · Development ends **Fri 14 Nov 2026, 23:59 UTC** · Solo builder, free resources only, no paid APIs.

**Live dashboard: https://topeseun.github.io/near-intents-investment-thesis/**

**Demo post (X): https://x.com/Niamsco/status/2119996831333589480**

## Executive summary for judges

- **Key finding.** Retained revenue alone supports **$0.41 per token — 11.7% of the $3.50 price** (r=15%, g=10%, measured 33.37% capture). The price itself implies retained revenue of **$198.8M/yr (8.6× today's R₀)**; buybacks only stop the token from inflating at **$114.8M/yr (4.9× R₀)**. The case is the option on fee growth and rising capture, not today's cash flow.
- **Falsification.** Six committed conditions (F₁–F₆) that would kill the thesis — **0 triggered**: revenue base too small, retention fails, SwapKit concentration (34.1% of observed 1Click volume), competitive lead lost, thesis too bearish, growth story dies.
- **Predictions.** Seven dated, committed predictions (P₁–P₇) scored against reality — **6 on track, 1 off track** (P₂: capture 33.37% vs the 35.97% bar). A missed prediction counts against the thesis.
- **The thesis.** NEAR's base layer barely earns anything; its Intents layer grossed $5,807,392 of fees in 30 days and keeps a growing share for buybacks. Value NEAR as a toll road on cross-chain volume — retained Intents revenue, fee-capture DCF — not as a cheap fast L1. Base-layer usage is 93.6% (transactions) and 96.2% (accounts) below peak — the moat, if there is one, is the Intents product, not base-layer activity.

Upside catalysts — AI-agent cross-chain execution, Chain Signatures expansion, SwapKit concentration mitigation, and new retained-fee mechanisms raising capture toward the 35.97% P₂ bar:

| Catalyst | What it would do | What to watch (live metric) |
|---|---|---|
| AI-agent cross-chain execution | Agents settle through Intents; gross volume grows without NEAR needing new human users | Intents volume (M₁₅) + capture (M₃) rising while base-layer accounts stay flat |
| Chain Signatures expansion | More chains/assets route through Intents via NEAR MPC signatures — same toll, wider road | New chains/assets in Intents volume; 30d volume vs the $3B P₄ bar |
| SwapKit concentration mitigation | More routing providers diversify flow; F₃ (single-provider outage) gets less likely | SwapKit share of observed 1Click volume falling from 34.1% |
| New retained-fee mechanisms | B2B + quote improvement already add ~14pp; new mechanisms lift capture toward the 35.97% P₂ bar | M₄ mechanism split; 7d capture recovering toward the 30d rate |

## Thesis

NEAR's base layer barely earns anything — its Intents layer already grossed $5,807,392 of fees in 30 days, keeps about a third of it (measured 30-day capture rate 33.37%) for NEAR buybacks, and is the only part of NEAR with a compounding, measurable revenue curve. The long-term investment case is not "cheap fast L1" but "toll road on cross-chain volume": this repo values NEAR on retained Intents revenue (fee-capture DCF), with base-layer usage and staking economics as the supporting chapters that test whether the toll road has a moat.

## Headline results (data fetched 2026-11-13 ~11:05 UTC)

| Figure | Value |
|---|---|
| NEAR price / market cap | $3.50 / ~$4.60B |
| F₃₀ — trailing-30d Intents gross fees | **$5,807,392** (DefiLlama) |
| Intents 30d volume (new, M₁₅) | **$3,774,153,452** (DefiLlama dexs daily series; endpoint total agrees exactly) — −21.6% vs prior 30d; implied gross fee rate **15.39 bps** |
| Measured 30d capture rate (retained ÷ gross) | **33.37%** (revenue.near.org; rising: 19.2% all-time → 23.0% YTD → 33.4% 30d) |
| R₀ — annualised retained revenue | **$23,255,121/yr** |
| DCF base value/token (r=15%, g=10%, c=33.37%) | **$0.41 vs $3.50 price — 11.7% of the price** |
| Market cap / retained revenue | **197.7×** (gross-fee basis: 66.0×) |
| NEAR issued/yr vs bought/yr | 32,790,001 vs 6,644,320 — net **+26,145,681 NEAR/yr, still inflationary** |
| Break-even retained revenue | **$114.8M/yr, ~4.9× current R₀** |
| Daily txns / active accounts (new, M₁₂–M₁₃) | 891,523 txns/day (**93.6% below** the 13,935,402 peak of 2023-12-01) · 85,370 active accounts/day (**96.2% below** the 2,256,512 peak of 2024-04-22) |
| New accounts, 30d (new, M₁₄) | 287,996 (−16.4% vs prior 30d); net +269,289 after deletions |
| Price vs Intents fees, weekly (new, M₁₆) | Pearson r = **0.06** (n=366 weeks) — essentially no weekly co-movement; price vs base gas fees r = 0.56. Correlation only, no lead-lag claim. |
| Metcalfe check, log(price) on log(users) (new, M₁₇) | Monthly slope **0.02** (R² 0.005, r 0.07, n=74 months, Oct 2020 – Nov 2026) vs strict-Metcalfe 2.0; daily slope 0.01 (R² 0.001); market-cap slope 0.19 (R² 0.27) — price does not follow users. A fellow entry (NEAR Demand Ledger) reports 0.21 / 0.28 on 73 months — same disconnect, weaker on this series. Caveat: from Jan 2024 the slope is 0.33 (r 0.64), the rise to and joint fall from the Apr 2024 peak, not a stable law. |
| Staking APY / max inflation / real yield | 4.91% / 2.5% / 2.41pp |
| NEAR Intents 30d fees vs competitors | NEAR $5.81M > Chainflip $2.97M > deBridge $0.46M > THORChain $0.018M |

**The honest framing:** retained revenue alone supports ~12% of the price. No cell in the 27-cell sensitivity grid (capture ≤35% × growth ≤20% at r=12%) reaches $3.50 — the best valid cell is $1.07. The case for NEAR is the *option value* on fee growth (g) and capture (c) rising, which the sensitivity grid makes explicit. This repo does not hide that; the dashboard leads with it. The new daily-activity series adds the bear leg the thesis was missing: base-layer usage has collapsed more than 90% from its peaks even while Intents fees grew — the moat, if there is one, is the Intents product, not base-layer activity.

**What the market price implies (reverse DCF — full arithmetic in `data/processed/reverse_dcf.json`):** at r=15%, g=10%, the $3.50 price needs retained revenue of **$198.8M/yr — 8.6× today's R₀**. At the current 33.37% capture and 15.39 bps fee rate that means (a) **$387.2B of annual Intents volume** (8.5× today's $45.3B annualised), or (b) **$49.7M of gross fees every 30 days** (8.6× F₃₀). And (c) **capture alone cannot get there**: with volume flat, the price needs a **285% capture rate — impossible**. Even at 100% capture with volume flat, the DCF ceiling is **$1.23 (35% of the price)**. The $3.50 price is a bet on volume growth, not on retention.

## Dated predictions — score this thesis against reality

Committed 2026-11-10 ([PREDICTIONS.md](PREDICTIONS.md) — timestamped by git history; machine-readable mirror `data/predictions.json`). These predictions are derived from the thesis's own numbers — no threshold here is invented. **A missed prediction counts against the thesis.** That is the point: a thesis that cannot be wrong is not evidence. Live values below are as of the latest fetch (2026-11-13 ~11:05 UTC) — a point-in-time read against the threshold, *not* the final outcome: no prediction has resolved yet (earliest resolution date 2026-12-31). Current tally: **6 on track, 1 off track**.

P₁ ($5,578,208) and P₂ (35.97%) are set at the thesis's own November levels — the trailing-30d fees and 30d capture rate exactly as measured on the commit date (2026-11-10) — so the bar is the thesis's own starting point, not an external target. Both started exactly at their bar; P₂ has since fallen off track (33.37%), and that is disclosed here and on the dashboard, not hidden. P₁ also went off track — on the Nov 11 fetch trailing-30d fees had fallen to $5,458,382, below the $5,578,208 bar — then recovered above it on the Nov 13 fetch ($5,807,392), so P₁ is back on track; P₂ is the one miss.

| ID | Prediction | Threshold | Resolves | Live value | Status |
|---|---|---|---|---|---|
| P₁ | Intents fees recover to their November level | Trailing-30d gross fees ≥ $5,578,208 | 2026-12-31 | $5,807,392 | on track |
| P₂ | The capture rate holds its level | 30d capture rate ≥ 35.97% | 2027-01-31 | 33.37% | **off track** |
| P₃ | The DCF gap persists | DCF value/token < 25% of NEAR price | 2027-02-28 | 11.7% of price | on track |
| P₄ | Intents volume holds above $3B | Trailing-30d volume ≥ $3,000,000,000 | 2026-12-31 | $3,774,153,452 | on track |
| P₅ | NEAR keeps its lead over Chainflip | NEAR 30d fees ≥ 1.5× Chainflip 30d fees | 2027-01-31 | 1.95× | on track |
| P₆ | Base-layer usage stays collapsed | 30d avg daily active accounts < 100,000/day | 2027-02-28 | 63,923/day | on track |
| P₇ | The price still does not track Intents fees | Weekly Pearson \|r\| < 0.30 (52w, M₁₆ method) | 2026-12-31 | \|r\| = 0.055 | on track |

The one miss is honest news, not a rounding error: the capture rate sits 2.60pp below its level (33.37% vs 35.97%). Fees, meanwhile, recovered above the November level ($5,807,392 vs $5,578,208), so P₁ flipped back on track on this fetch. When a resolution date arrives, re-run the pipeline and record the outcome in PREDICTIONS.md. The live dashboard renders this table from `data/processed/predictions.json` (M₁₈) on every refresh.

## Falsification — what would prove this thesis wrong

A thesis that cannot be wrong is not evidence — so here are the six kill conditions, committed 2026-11-11. If one triggers, the thesis (or the part of it the condition tests) is wrong and must be revised, not defended. Live values below are as of the latest fetch (2026-11-13 ~11:05 UTC). Current tally: **0 triggered, 6 not triggered**.

| ID | Condition | Threshold | Live value | Status |
|---|---|---|---|---|
| F₁ | Revenue base too small | Trailing-30d Intents gross fees (F₃₀) below $2,000,000 sustained for 90 consecutive days | $5,807,392 | **not triggered** |
| F₂ | Retention fails | 30d capture rate below 15% sustained for 90 consecutive days | 33.37% | **not triggered** |
| F₃ | Concentration kills the moat | A single routing-provider outage cuts observed 1Click volume by more than 50% for 7+ days | 31.6% drop — Oct 1–4 2026 pause precedent | **not triggered** |
| F₄ | Competitive lead lost | A competitor's trailing-30d Intents fees exceed NEAR's (ratio < 1.0) for 3 consecutive months | 1.95× vs Chainflip | **not triggered** |
| F₅ | Thesis too bearish (reverse falsification) | DCF value/token at or above 100% of NEAR price | 11.7% of price | **not triggered** |
| F₆ | Growth story dies | Trailing-30d fees fall more than 50% from the $8,236,902 peak of 14 Oct 2026 AND 30d volume falls more than 50% vs its prior 30d, both sustained for 90 consecutive days | Fees 70.5% of peak; volume 78.4% of prior 30d | **not triggered** |

Three conditions overlap the dated predictions — deliberately, not by accident: F₁ tests the same revenue base as P₁ (but at the kill level, $2M, not the November level), F₂ the same capture rate as P₂ (at the 15% floor, not the 35.97% level), and F₄ the same competitive lead as P₅ (at parity, not 1.5×). A prediction going off track is a warning; a falsification condition triggering is the thesis failing. Persistence is counted from the commitment date (2026-11-11) and re-evaluated on every daily refresh: F₁, F₄ and F₆ are scored against the stored daily series, so their persistence is measured, not asserted; F₂'s capture rate is a point-in-time fetch with no stored history, so its 90-day clock is carried forward through `data/processed/falsification.json` across runs; F₃ is event-based — the 31.6% figure is the Oct 1–4 2026 pause precedent, the largest single-provider outage drop on record, and the condition is re-checked when a new outage is reported. F₅ has no persistence window by design: a single recomputation at or above 100% is enough. Committed thresholds: `data/falsification.json`. Method and honesty notes: `data/processed/BUILD_NOTES.md` (M₁₉). The live dashboard renders this table from `data/processed/falsification.json` (M₁₉) on every refresh.

## The bridge — what would have to be true for $2.05?

A fellow entry, [NEAR Toll Audit](https://apps.swiftbotlab.workers.dev/near-toll-audit/) (@swiftbotlab), corroborates this thesis's core measurements — 35.9% capture vs our 33.37%, $22.3M/yr captured revenue vs our $23,255,121/yr — but values NEAR at **$2.05 base / $2.91 weighted**, far above our $0.41 DCF. The gap is not a measurement dispute. It is what each model includes. Bridging our number to theirs, in dollars (figures as of the 2026-11-13 build, data fetched 2026-11-13 ~11:05 UTC):

| Component | Equity value | Per token* |
|---|---|---|
| Retained-revenue DCF (this thesis) | $511.61M | $0.39 |
| + Chain value (their assumption) | $1.66B | $1.27 |
| + Exit value & horizon difference (their 5-yr model + exit) | $513.89M | $0.39 |
| = Their base case | $2.69B | $2.05 |

\* Per-token figures on their 1.31B supply basis; our headline $0.41 uses CoinGecko circulating supply (~1.25B NEAR). On their basis our DCF is $0.39 — a ~5% difference, disclosed, not hidden.

Three things follow. First, **no parameter tweak closes the gap**: the best valid cell in our 27-cell sensitivity grid is $1.07 (35% capture, 10% growth, r=12%) — still about half their base case. The difference is structural, not parametric. Second, **their base case is 62% chain value** ($1.66B of $2.69B), and they say so themselves: chain value "is an assumption". Our DCF is the conservative floor — retained revenue only, no chain value, no exit value. Third, **the market price implies even more**: under their model, $3.60 needs 63%/yr volume growth for five years (12×), or a 40× exit (7×), or a $3.9B chain value (3×). ($3.60 is their published price — their page, section 10 — not our live price; the 63%/12× implication is quoted against it.)

This section is computed by the pipeline (`src/model.py` → `data/processed/bridge.json`; rival figures are quoted constants from their published page, 2026-11-13 — only our side refreshes with each fetch) and rendered live on the dashboard. It does not change our thesis: it prices the disagreement.

## What this repo contains

```
├── README.md                     # this file
├── src/
│   ├── fetch.py                  # Tier-1 API fetches only (no keys); caches to data/raw/ + data/manifest.json
│   ├── model.py                  # Fee-capture DCF, metrics M₁–M₁₈, benchmarks → data/processed/*.json
│   ├── charts.py                 # 10 charts → dashboard/assets/*.png (+ .svg twins)
│   ├── build.py                  # Runs model.py then charts.py (no network)
│   ├── build_dashboard.py        # Renders dashboard/index.html from data/processed/*.json (no network)
│   └── assumptions.yaml          # THE one assumptions file (DCF knobs + scenario grid)
├── tests/
│   └── test_outputs.py           # stdlib-unittest checks (see "Tests" below)
├── data/
│   ├── raw/                      # 29 cached API responses (with data/manifest.json: source URL, fetched_at UTC, bytes)
│   ├── manifest.json             # Source URL + fetch timestamp for every cached response
│   └── processed/
│       ├── metrics.json          # M₁–M₁₈, each with source + fetched_at
│       ├── dcf.json              # Base-case DCF inputs + outputs
│       ├── sensitivity.json      # 27-cell grid (capture × growth × discount)
│       ├── bridge.json           # Bridge to the rival $2.05 valuation (chain + exit value)
│       ├── reverse_dcf.json      # Reverse DCF: required volume / 30d fees / capture to reach the live price
│       ├── benchmarks.json       # NEAR vs SOL/AVAX/ETH + Intents competitors
│       ├── predictions.json      # M₁₈ dated predictions: committed thresholds + live values + statuses
│       ├── falsification.json    # M₁₉ falsification conditions: committed thresholds + live values + statuses
│       ├── chart_01_data.json … chart_10_data.json   # Per-chart numbers
│       └── BUILD_NOTES.md        # Pipeline/model build notes, gaps, corrections, reproducibility
├── docs/                         # GitHub Pages copy of dashboard/index.html + dashboard/assets/*.svg (same content)
└── dashboard/
    ├── index.html                # Static dashboard (single page, no server, no external JS/CSS)
    ├── BUILD_NOTES.md            # Dashboard build notes (what was built, how to regenerate, verification)
    └── assets/
        └── chart01_*.png … chart10_*.png   # The 10 charts (PNG + SVG twins; PNGs are git-ignored)
```

What the code does, exactly:

- `src/fetch.py` fetches NEARBlocks stats/validators/blocks/accounts **and the full daily `/v1/charts` series (2,306 points, 2020-07-21 → today)**, NEAR RPC status/gas price/protocol config, CoinGecko prices + 365d market charts (4 coins), DefiLlama Intents/chain/competitor fees + TVL **and the Intents daily volume series (`summary/dexs/near-intents`, 703 points from 2024-12-10)**, and parses the revenue.near.org server-rendered payload for the measured capture rate. Every response is cached to `data/raw/` with a timestamped manifest. No API keys. CoinGecko: 5 calls, 2.5 s sleep between them (30/min limit); a 429 gets one retry after a 60 s backoff.
- `src/model.py` computes the fee-capture DCF (Gordon growth: Value = R₁/(r−g), R₀ = F₃₀ × 12 × capture), the 19 metrics M₁–M₁₉, the 27-cell sensitivity grid, the bridge to the rival valuation (`bridge.json`), the reverse DCF to the live price (`reverse_dcf.json`), and the peer/competitor benchmarks — all from the cache, no network.
- `src/charts.py` renders the 10 charts as PNGs (+ SVG twins) from the model outputs.
- `src/build_dashboard.py` renders `dashboard/index.html` from `data/processed/*.json`. Every number on the page is formatted from those JSONs — nothing is hardcoded — so re-running the pipeline and this script regenerates a dashboard that always matches the model.

## Reproduce in one command

```bash
python3 src/fetch.py && python3 src/build.py && python3 src/build_dashboard.py
```

Requirements: Python 3.12; pinned versions in `requirements.txt` (`pip install -r requirements.txt`). No API keys, no paid services, no server. Then open `docs/index.html` in any browser (or `python3 -m http.server` from `docs/`).

Verified: a clean re-run (`rm -rf data && python3 src/fetch.py && python3 src/build.py`) reproduces the fee-derived numbers exactly (F₃₀ $5,807,392, capture 33.37%, R₀ $23,255,121, DCF $0.4093/token); price-dependent numbers move only with the live price tick. See `data/processed/BUILD_NOTES.md` and `dashboard/BUILD_NOTES.md`.

## Quick verify (no network needed)

```bash
python3 -m unittest discover -s tests -v   # 32 tests, stdlib unittest only
```

Then open `docs/index.html` in any browser — it is the live dashboard, committed in this repo.

The committed `data/` reproduces every number in this README and on the dashboard: the tests check the README and dashboard against `data/processed/*.json` and recompute the model arithmetic from them. No test calls any live API — the only step that touches the network is a fresh fetch (`python3 src/fetch.py`). Dependencies, if needed, are pinned in `requirements.txt` (`pip install -r requirements.txt`).

## Tests

Run the suite as in Quick verify above. Stdlib `unittest` only — no new dependencies. 32 tests, grouped by what they guard:

- **Model & DCF math.** Every `data/processed/*.json` exists and parses; F₃₀/capture/R₀/DCF arithmetic is internally consistent (R₀ = F₃₀ × 12 × capture; Gordon growth; value/token = Value ÷ supply); the sensitivity grid is 3 × 3 × 3 = 27 cells with invalid g ≥ r cells null and valid cells matching the formula; the growth-assumption check (DCF at the measured trailing-365d growth rate and at g=0%) recomputes via Gordon growth and sits below the base case; buyback-vs-issuance arithmetic; M₁₂–M₁₇ sanity (peaks above current, percentages in range, volume positive, implied fee rate 1–100 bps, correlation in [−1, 1], Metcalfe slope/R² in range).
- **Predictions & falsification.** M₁₈ dated predictions (thresholds and dates match the committed `data/predictions.json`, live values sane and traced to the metrics they come from, statuses consistent with the thresholds); M₁₉ falsification (thresholds match the committed `data/falsification.json`, live values sane and traced to the metrics they come from, statuses consistent with thresholds and persistence windows, dashboard renders all 6 conditions with live values and statuses).
- **Bridge & reverse DCF.** The bridge to the rival $2.05 valuation (dollar and per-token components sum to the rival base case, our side traces to `dcf.json`, chain value is the majority of the rival total, no sensitivity cell reaches the rival base case, dashboard renders it); the reverse DCF to the live price (required R₀, volume, 30d fees and capture recompute from the inputs, capture-alone is impossible, the 100%-capture ceiling is below the price, and the `reverse_dcf.json` title carries the live price).
- **Dashboard & parity.** All 10 charts exist as PNG + SVG; the dashboard references all 10 SVGs and renders all 7 predictions with live values and statuses; the dashboard renders the one-line verdict (overvalued on retained revenue, with the live DCF, price, break-even multiple and net issuance); the verdict keeps the two conditions separate — the revenue the price implies (reverse DCF) and the buyback break-even appear as separate sentences, with both numbers traced to the model, in the dashboard verdict and in the README verdict; `docs/` mirrors `dashboard/index.html` byte-for-byte; the dashboard uses subscripted F₃₀ throughout (no unsubscripted form) and the headline capture card renders the live M₄ windows; the dashboard contains no stale hardcoded figures (Chart 7's title carries the live price, Charts 1/8 carry the live day/point counts, the 365d growth rate and fee-anomaly date are live, and the only $3.60 on the page is Toll Audit's quoted price in the bridge); the README contains the headline numbers (fee-stable figures + the all-time activity peaks + the live price and market cap), the falsification section, and the descriptive figures for charts #1/#8/#9 and Assumptions matched to `metrics.json`.

## GitHub Pages

**Live dashboard: https://topeseun.github.io/near-intents-investment-thesis/**

The dashboard is published from `docs/`: copy `dashboard/index.html` + `dashboard/assets/*.svg` into `docs/` (same content — the SVGs are text, so they push through text-only tooling; PNGs stay local). It is enabled in the repo at **Settings → Pages → Build and deployment → Deploy from a branch → branch `main`, folder `/docs`**. Re-copy `docs/` after any dashboard rebuild so Pages stays in sync with `dashboard/`.

## The 10 charts

1. Intents daily fees, May 2025 → Nov 2026 (552 pts, log scale + 30d moving average)
2. Intents fees vs base-chain gas fees (same log axis)
3. NEAR price vs trailing-30d Intents fees, indexed to 100 (365d)
4. Valuation multiples — mcap/annualised fees: NEAR (gross + retained) vs SOL/AVAX/ETH
5. Buyback vs issuance — NEAR bought/yr vs issued/yr under 3 capture scenarios
6. Staking economics — APY 4.91% vs inflation 2.5% vs real yield, stake + validators
7. Sensitivity heatmap — implied value/token across capture (15/25/35%) × growth (0/10/20%) at r=12%, invalid g≥r zone marked
8. Daily transactions & daily active accounts, 2020 → today (log scale, all-time peaks marked) — the usage collapse: txns 93.6% and active accounts 96.2% below peak
9. Intents daily volume & daily fees (log scale, two panels) — volume 30d $3.77B, implied gross fee rate 15.39 bps
10. Metcalfe check — log-log price vs daily active accounts, monthly (74 months, Oct 2020 – Nov 2026) + cumulative-txns partial check: slope 0.02, R² 0.005 — no Metcalfe law (strict Metcalfe needs slope ≈ 2.0); a fellow entry (NEAR Demand Ledger) reports 0.21 / 0.28 on 73 months, same disconnect

## Data sources

| Source | What it gives | URL |
|---|---|---|
| DefiLlama API | NEAR Intents daily fees + aggregates; base-chain fees; peer/competitor fees; NEAR TVL | https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees |
| DefiLlama API | NEAR Intents daily volume (703 pts, 2024-12-10 → today) | https://api.llama.fi/summary/dexs/near-intents |
| NEARBlocks API | Daily activity series — txns, active/new accounts, gas fees, price (2,306 pts, 2020-07-21 → today) | https://api.nearblocks.io/v1/charts |
| revenue.near.org | Measured capture rate (30d net revenue ÷ gross fees, cross-checked vs per-mechanism split) | https://revenue.near.org/ |
| CoinGecko free API | Prices/market caps (NEAR, SOL, AVAX, ETH); 365d price/mcap history | https://api.coingecko.com/api/v3/simple/price |
| NEARBlocks API | Chain stats, validators (APY, stake, concentration) | https://api.nearblocks.io/v1/stats |
| NEAR mainnet RPC | Protocol config — max inflation cap 2.5% ([1,40]) | https://rpc.mainnet.near.org |

Every cached response is listed with its source URL and fetch timestamp in `data/manifest.json`; every metric carries its source + `fetched_at_utc` in `data/processed/metrics.json`.

## Assumptions

All model assumptions live in one file: [`src/assumptions.yaml`](src/assumptions.yaml). The DCF base case is r=15% (discount rate, WACC proxy), g=10% (perpetual growth of retained revenue — a forward assumption, *not* a trend extrapolation: trailing-30d **fees** are −29.1% vs the prior 30 days — the −21.6% figure in the headline table is **volume**, not fees, a different series — and the 365-day log-regression growth is +0.8%/yr), capture scenarios 15/25/35% (the measured 30d rate, 33.37%, is the base case). Gordon growth requires g < r; cells with g ≥ r are null and shown as invalid.

**Growth-assumption check:** the base case assumes g=10%/yr, but the measured trailing-365d log-regression growth is +0.8%/yr — essentially flat. At the measured growth rate (r=15%, measured capture) the DCF is $0.13/token; at g=0% it is $0.12/token (base case $0.41). The 10% base case is a forward assumption about the future, not a read of the trend. The full check (recomputed by the pipeline into `data/processed/sensitivity.json`) is rendered on the dashboard under the sensitivity grid.

Note on two near-identical figures: the −31.6% Oct 1–4 2026 outage drop (F₃, Limitations) is a different number from the −29.1% trailing-30d fees vs prior 30 days above — 4-day Intents *volume* vs the prior matching week, not 30-day *fees* vs the prior 30 days. They are close by coincidence (both are ~30% declines in related series), not by construction; the outage figure was verified against the raw DefiLlama volume series (Oct 1–4 $390,161,724 vs Sep 24–27 $570,480,703).

## Limitations

- **Daily activity is measured — and it is weak.** The research-phase claim that "NEARBlocks has no public daily-stats endpoint" was wrong: the bare `/v1/charts` path (never tested — only suffixed paths like `/v1/charts/daily-txns`, all 404) returns the full daily series from 21 Jul 2020 (2,306 points). Daily txns are 93.6% below their 1 Dec 2023 peak (13,935,402/day) and daily active accounts 96.2% below their 22 Apr 2024 peak (2,256,512/day) — this **confirms** the ">90% decline from peak" claim, it does not contradict it. Early rows have gaps: `multichain_txns` is null before 14 Nov 2024 and `txn_volume` is null on 11 days in Jul–Aug 2020; neither field is used in any metric. Paging `/v1/txns` backwards stays cut (measured: ~10,400 pages / ~4.6 h for one day) — now unnecessary.
- **Volume is measured, with a shorter window.** DefiLlama `summary/dexs/near-intents` gives a daily Intents *volume* series (703 points from 10 Dec 2024): 30d volume $3,774,153,452 from the daily series, agreeing exactly with the endpoint's own 30d total. The implied gross fee rate (30d fees ÷ 30d volume) is 15.39 bps, matching the ~15 bps quoted in secondary sources — two independent series agreeing. The volume series starts Dec 2024, so it covers a shorter window than the fee series (May 2025) and the activity series (Jul 2020).
- **365-day price cap.** CoinGecko's free tier limits history to 365 days.
- **24-hour fee anomaly.** Intents fees for 12 Nov 2026 were $16,604 vs a 7-day daily average of ~$206,697 — a full-day value, so either a real one-day drop or a DefiLlama reporting lag. No single day is ever annualised; all annualisation uses 7d/30d trailing figures.
- **Fees are volatile, not a ramp.** Trailing-30d fees peaked at $8,236,902 on 14 Oct 2026 and are −29.5% below that peak. The full-series launch-ramp CAGR is a May–Aug 2025 artefact and is not quoted anywhere.
- **Revenue-dashboard caveats.** Its headline revenue figure ($11.79M) has an unlabelled window in the page payload and is never used as a model input. Its wallet table is partial: the live NEARBlocks balance of buybacks.multisignature.near (2,274,249 NEAR) exceeds the dashboard's traced all-time inflow (1,771,956.8 NEAR).
- **TVL endpoints disagree.** DefiLlama's NEAR historical-series last point ($163.3M) vs its /chains headline ($349.8M). The auditable series value is used.
- **Peer fees undercount.** DefiLlama chain-fee totals can miss revenue other methodologies include (notably Solana). Benchmarks rank within this dataset only.
- **LI.FI dropped from the benchmark.** DefiLlama returns 404 ("Fees for lifi not found").
- **Intents flow is concentrated in one routing provider.** [Faultline](https://github.com/Dare0x/Faultline) (a fellow Investment Thesis entry) measured from NearStats routing data, 30 days to 8 Nov 2026, that a single provider, SwapKit, carried $260.99M of $765.65M observed 1Click volume (34.1%, across 48 apps). An outage or pause at that provider is a concentration risk to the Intents flow — and therefore to the fee capture this thesis values: its simulation displaces 10.2% of total observed volume even if 70% of SwapKit's flow reroutes. The Oct 1 service pause is the live precedent: Oct 1–4 volume ran 31.6% below the prior matching week.
- **Model limitations.** The DCF is a single-stage Gordon model: one perpetual growth rate (g=10%) applied forever, so it cannot represent a ramp, a plateau, or a regime change in fees. Buybacks reduce issuance rather than paying holders directly — the DCF values the buyback stream as if it were a dividend, which overstates what a holder receives in cash. And the capture rate is a point-in-time measurement from a single 30-day window, not a contracted rate; it has moved 19% → 33% across windows and can fall as fast as it rose.

Full detail: `data/processed/BUILD_NOTES.md`.

## Judging

Built for the NEAR Hackathon 2026 Investment Thesis track — "build a long-term investment thesis for NEAR and back it with data: onchain analytics, live dashboards and models anyone can re-run. Judged on the evidence, not the conviction." $250K prize pool paid in NEAR; per-track 1st $10K, 2nd $3K, 3rd $2K. Payout account (if awarded): `topeseun20.near`.

## AI assistance (Q-005 disclosure)

Built with AI assistance, as the hackathon rules allow (HACKATHON.md Q-005): the code, analysis and dashboard were produced by an AI coding agent (Muse Spark, working as "Rio") under the author's direction. All data is fetched live from the cited public sources, and every figure is reproducible with the one-command pipeline above; the thesis, conclusions and dated predictions are the author's.

*Not investment advice. All figures are as fetched on 2026-11-13 ~11:05 UTC; re-run the pipeline for current data.*
