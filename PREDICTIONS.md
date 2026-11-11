# Dated predictions — score this thesis against reality

**Committed 2026-11-10.** These predictions are committed predictions, timestamped
by the git history of this file: the commit that adds them is the commitment.
They are derived from the thesis's own numbers (data fetched 2026-11-10 ~03:05 UTC;
see `README.md` and `data/processed/*.json`) — no threshold here is invented.
**A missed prediction counts against the thesis.** That is the point: a thesis
that cannot be wrong is not evidence. When a resolution date arrives, re-run
`python3 src/fetch.py && python3 src/build.py` and compare the fresh model
outputs against the thresholds below; record the outcome in this file.

## Baselines (2026-11-10 ~03:05 UTC)

| Figure | Baseline |
|---|---|
| NEAR Intents trailing-30d gross fees (F30) | $5,578,208 (DefiLlama) — −30.5% vs prior 30d ($8,023,326); −32.3% below the $8,236,902 peak of 2026-10-14; +44.9% vs a year ago ($3,849,427) |
| Measured 30d capture rate (retained ÷ gross) | 35.97% (revenue.near.org) — rising: 19.1% all-time → 23.0% YTD → 36.0% 30d; 7d rate 32.23% |
| R0 — annualised retained revenue | $24,077,777/yr |
| DCF base value/token (r=15%, g=10%, c=35.97%) | $0.4238 vs $3.60 price — 11.8% of the price |
| Break-even retained revenue | $118,016,377/yr — 4.90× current R0 |
| Intents trailing-30d volume | $3,714,703,671 (DefiLlama dexs daily series) — −22.0% vs prior 30d; implied gross fee rate 15.02 bps |
| NEAR Intents vs Chainflip, 30d fees | $5,578,208 vs $2,787,929 — NEAR 2.00× Chainflip (deBridge $436,379; THORChain $18,967) |
| Daily active accounts, 30d average | 58,223/day (last day 77,752) — 96.6% below the 2,256,512 peak of 2024-04-22 |
| Price vs Intents fees, weekly Pearson r | 0.06 (n=366 weeks, weekly log-changes; M16) |

## The predictions

### P1 — Intents fees recover to their November level
- **Statement:** NEAR Intents trailing-30d gross fees recover to at least the
  level measured when this thesis was written.
- **Threshold:** trailing-30d gross fees **≥ $5,578,208** on 2026-12-31.
- **Resolves:** 2026-12-31.
- **Resolution rule:** DefiLlama `summary/fees/near-intents` `total30d`
  (cross-checked against the sum of the last 30 daily points, as in M1).
  Pass if ≥ $5,578,208, fail otherwise.
- **What a miss means:** the −30.5% fall vs the prior 30 days was a trend, not
  volatility, and the DCF's 10% perpetual-growth assumption rests on a
  shrinking base.

### P2 — The capture rate holds its level
- **Statement:** the measured 30d capture rate — the thesis's one rising trend —
  does not fall back below the level measured on 2026-11-10.
- **Threshold:** 30d capture rate (retained ÷ gross) **≥ 35.97%** on 2027-01-31.
- **Resolves:** 2027-01-31.
- **Resolution rule:** revenue.near.org 30d window (net revenue ÷ gross fees
  from its server-rendered payload, the same extraction as M3/M4). Pass if
  ≥ 35.97%, fail otherwise.
- **What a miss means:** the 19.1% → 23.0% → 36.0% climb has stalled or
  reversed; the base-case capture in the DCF is no longer the measured rate.

### P3 — The DCF gap persists (retained revenue still supports only a fraction of the price)
- **Statement:** recomputing the thesis's own base-case DCF on the resolution
  date — same formula, r=15%, g=10%, measured capture, trailing-30d fees,
  current circulating supply — still leaves the value per token far below the
  price. The market keeps paying mainly for the option, not for today's
  retained cash flow.
- **Threshold:** DCF value per token **< 25% of the NEAR price** on 2027-02-28.
- **Resolves:** 2027-02-28.
- **Resolution rule:** re-run `src/fetch.py` + `src/model.py` on the date and
  read `data/processed/dcf.json` (`base_case.value_per_token_usd`) against the
  CoinGecko NEAR price the same run fetched. Pass if value/token ÷ price
  < 0.25, fail otherwise.
- **What a miss means:** retained revenue has grown enough — or the price has
  fallen enough — that the "honest verdict" section of this thesis no longer
  holds and must be rewritten. (Baseline: $0.4238 vs $3.60 = 11.8%.)

### P4 — Intents volume holds above $3B
- **Statement:** NEAR Intents trailing-30d swap volume stays above $3B — the
  growth x-axis of the DCF does not keep sliding.
- **Threshold:** trailing-30d volume **≥ $3,000,000,000** on 2026-12-31.
- **Resolves:** 2026-12-31.
- **Resolution rule:** DefiLlama `summary/dexs/near-intents`, sum of the last
  30 daily points (the M15 method). Pass if ≥ $3.0B, fail otherwise.
- **What a miss means:** volume — and therefore the fee base at a ~15 bps fee
  rate — is contracting; the DCF growth assumption is a bet against the
  observed direction.

### P5 — NEAR keeps its lead over Chainflip
- **Statement:** NEAR Intents still grosses materially more in 30d fees than
  its closest cross-chain competitor.
- **Threshold:** NEAR Intents trailing-30d fees **≥ 1.5× Chainflip**
  trailing-30d fees on 2027-01-31.
- **Resolves:** 2027-01-31.
- **Resolution rule:** DefiLlama `summary/fees/near-intents` vs
  `summary/fees/chainflip`, `total30d` for each. Pass if the ratio ≥ 1.5,
  fail otherwise.
- **What a miss means:** the "toll road" is losing share in its own category;
  the moat claim in the thesis weakens. (Baseline: 2.00×.)

### P6 — Base-layer usage stays collapsed
- **Statement:** daily active accounts do not recover — the bear leg of the
  thesis persists, and the Intents product (not base-layer activity) remains
  the only live part of NEAR.
- **Threshold:** 30d average of daily active accounts **< 100,000/day**
  on 2027-02-28.
- **Resolves:** 2027-02-28.
- **Resolution rule:** NEARBlocks `/v1/charts` daily series (the M13 method):
  mean of the last 30 daily active-account values. Pass if < 100,000/day,
  fail otherwise.
- **What a miss means:** usage has recovered to more than ~1.7× its November
  level (though still 95%+ below the 2,256,512 peak) — good news for NEAR,
  but the thesis's usage-collapse chapter would need revising. A miss here is
  the one prediction whose failure would be welcome.

### P7 — The price still does not track Intents fees
- **Statement:** NEAR's price keeps showing essentially no weekly co-movement
  with Intents fees — the market does not (yet) price NEAR on its Intents
  revenue.
- **Threshold:** weekly Pearson r between NEAR price and trailing-30d Intents
  fees, over the 52 weeks ending 2026-12-31, satisfies **|r| < 0.30**.
- **Resolves:** 2026-12-31.
- **Resolution rule:** same method as M16 — Pearson correlation of weekly
  log-changes, CoinGecko NEAR price history vs DefiLlama Intents daily fees.
  Pass if |r| < 0.30, fail otherwise.
- **What a miss means:** the market has started pricing NEAR on Intents fees
  (or both have begun moving on a common driver) — the "price ignores the
  toll road" observation no longer holds. (Baseline: r = 0.06, n=366 weeks.)

## Resolution log

| ID | Resolution date | Outcome | Resolved value | Source |
|---|---|---|---|---|
| P1 | 2026-12-31 | — | — | — |
| P2 | 2027-01-31 | — | — | — |
| P3 | 2027-02-28 | — | — | — |
| P4 | 2026-12-31 | — | — | — |
| P5 | 2027-01-31 | — | — | — |
| P6 | 2027-02-28 | — | — | — |
| P7 | 2026-12-31 | — | — | — |

*Not investment advice. Baselines are as fetched on 2026-11-10 ~03:05 UTC;
re-run the pipeline for current data.*

