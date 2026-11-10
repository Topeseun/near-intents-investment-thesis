# On-chain revenue reconciliation — NEAR Intents retained revenue

**Status: 30-day window RECONSTRUCTED and reconciled (2026-11-10); all-time
census COMPLETE (§6) — 5,188 sweeps, 3,011,961.80 NEAR, reconciled to
100.06% of revenue.near.org's wallet totals. GAP DECOMPOSED (§8, fresh
run 2026-11-10 ~19:30 UTC): the ~9–11% gap vs revenue.near.org's 30D net
is the pp_qi (quote-improvement) leg — counted in the dashboard's net
revenue but not received in the revenue wallets. Cash capture is ~32.8%
(30D) / ~31.5% (7D); thesis numbers unchanged, conclusion unchanged.**
Reproduce: `python3 src/reconstruct_intents.py [--days 30] [--all-time]`
Output: `data/processed/reconstruction_intents.json` (+ `--all-time` writes
`data/processed/reconstruction_intents_alltime.json`); raw sweeps cached in
`data/raw/reconstruction_intents_receipts.json`.

## 1. Why this exists

The thesis's capture rate (35.97%) and annualised retained revenue R0
($24,077,777/yr) rest on one third-party aggregator, revenue.near.org,
cross-checked only against DefiLlama — another aggregator. This document
rebuilds the **retained leg** (the NEAR that actually lands in the Intents
revenue wallets) independently from on-chain receipts, and reconciles it
against both aggregators. It does **not** rebuild *gross* fees from swap
events — see §7 for why, and what that would need.

## 2. Method

1. **Enumerate receipts.** For each of the three revenue wallets named by
   revenue.near.org's own wallet table —
   `fefundsadmin.sputnik-dao.near`, `buybacks.multisignature.near`,
   `1csfundsadmin.sputnik-dao.near` — page the NEARBlocks indexer
   (`GET /v1/account/{wallet}/txns?page=N&per_page=100&order=desc`) back
   past the window start. NEARBlocks is an indexer, not the chain itself;
   step 4 below verifies sampled receipts against archival RPC directly.
2. **Filter to fee sweeps.** Keep only receipts with
   `predecessor_account_id == "intents.near"` and first action `TRANSFER`.
   Each such receipt is one fee sweep. Spot-checked on archival RPC, the
   underlying transaction is: `intents.near` calls `near_withdraw` on
   `wrap.near` (unwrapping wNEAR), and the resulting NEAR is forwarded to
   the revenue wallet — e.g. tx
   `BP3yv6G5h6EYKshGXHwfxKo5nQ9Z6v8AKEvdhCJGs5F9` moves exactly
   1,258.8617731061112 NEAR from `wrap.near` → `intents.near` → 
   `buybacks.multisignature.near` (see §4).
3. **Convert to USD.** Each sweep × that UTC day's NEAR **close** (CoinGecko
   `/coins/near/market_chart`, hourly points → last point per UTC day).
   Sensitivity: valuing at the daily **mean** instead moves the 30d total
   by +0.53% — price method is not a material source of disagreement.
4. **Verify against archival RPC.** Sampled sweeps (spread across the
   window) are re-fetched with `EXPERIMENTAL_tx_status` on the public
   archival RPC (`https://archival-rpc.mainnet.near.org`): the transaction
   must be `FINAL` and contain a receipt to the wallet whose `Transfer`
   deposit matches the NEARBlocks deposit. NEARBlocks `deposit` is a JSON
   float (~16 significant digits) while archival RPC returns the exact
   yocto integer, so the match uses 1e-9 relative tolerance (observed
   differences are ~1e-17 — pure float noise).
5. **Reconcile.** Compare the summed USD against, for the same dates:
   revenue.near.org (live SSR parse, same method as `src/fetch.py`) and
   DefiLlama `summary/fees/near-intents` (`dailyFees` and `dailyRevenue`,
   headline trailing totals **and** sums of the daily series over the exact
   window dates).

## 3. Result — 30-day window, 2026-10-12 → 2026-11-10

Run at 2026-11-10T15:54:06Z (Nov 10 is a partial day — sweeps after ~15:54
UTC are not in this run).

| Wallet | Sweeps | NEAR | Notes |
|---|---|---|---|
| fefundsadmin.sputnik-dao.near | 334 | 118,505.04 | 400 receipts scanned, 4 pages |
| buybacks.multisignature.near | 780 | 283,017.89 | 800 receipts scanned, 8 pages; 1 non-`intents.near` receipt in window, excluded |
| 1csfundsadmin.sputnik-dao.near | 0 | 0.00 | **No activity since 2026-09-26** — its last receipt predates the window |
| **Total** | **1,114** | **401,522.93** | 0 duplicate tx hashes (one sweep tx = one wallet receipt) |

- **Reconstructed retained revenue (30d): $1,790,279 at daily close**
  ($1,799,322 at daily mean, +0.53%). Daily range $28,687–$164,429.
  NEAR fell ~30% across the window (close $5.06 on Oct 12 → $3.51 on Nov 10),
  so the USD total is price-sensitive; the NEAR total (401,523) is the
  price-independent fact.
- **7-day check (Nov 4–10): $361,298** (97 sweeps, 97,577.3 NEAR).

- **Fresh re-run (2026-11-10 ~19:30 UTC): 1,125 sweeps, 406,488.36 NEAR,
  $1,807,930 at daily close** ($1,817,088 at daily mean). The runner
  enumerated all three wallets but ended silently before writing output
  (no traceback; cause not determinable); the totals were assembled from
  its per-wallet checkpoints with the identical filter and pricing — see
  the method note in `data/processed/reconstruction_intents_30d.json`.
  The extra 11 sweeps / 4,965 NEAR / $17,651 vs the 15:54 UTC run are
  late-Nov-10 sweeps (Nov 10 total now 31 sweeps, 13,725.06 NEAR); 2 of
  them re-verified TRUE on archival RPC. Per wallet: fefundsadmin 337
  sweeps / 119,767.52 NEAR; buybacks 788 / 286,720.84 NEAR; 1cs 0.
  Nov 1–10: 303 sweeps, 129,158.14 NEAR, $484,301. Nov 4–10 (7d):
  219 sweeps, 102,542.71 NEAR, $378,949.

## 4. Archival RPC verification (5 sampled sweeps)

| Date | Wallet | Tx | Status | Rel. diff. vs NEARBlocks |
|---|---|---|---|---|
| 2026-10-12 | fefundsadmin | `FcNgyF6XxNToczgiubaz3etw7CB9wZFTtBxJjDgtNLjR` | FINAL | 2.5e-17 ✓ |
| 2026-10-19 | fefundsadmin | `4dUbA9Ad2RqVVJng5xutnEsdC6qzv6E3MVFVz4Z26Ph9` | FINAL | 3.9e-17 ✓ |
| 2026-10-26 | buybacks | `5w53NQc25GHsLAc6kqyw4e6vb3e3i6guJ4Pev6AroDPh` | FINAL | 3.5e-17 ✓ |
| 2026-11-01 | buybacks | `A2kSt2edq4vAcpai5WeDymkRqK6Nx321ZCfXB6o7xmLe` | FINAL | 4.4e-17 ✓ |
| 2026-11-10 | buybacks | `9Hfu9pto1UCAwcwSr7cbeJaza2qrSB9nwaoeyvycm3hy` | FINAL | 4.3e-17 ✓ |

All 5 verified, including the oldest (Oct 12) — the public archival RPC
retains `EXPERIMENTAL_tx_status` at least that far back. Note its `status`
endpoint reports `earliest_block_height` 223,746,737 (~2026-11-09 09:13 UTC);
that bound applies to block data, **not** to `tx_status`, which answered for
Oct 12 transactions. Do not assume it reaches back 30 days for every method.

## 5. Reconciliation

| Comparator (same 30d window) | Value | Reconstruction / comparator |
|---|---|---|
| **DefiLlama `dailyRevenue`, daily-series sum (exact window dates)** | $1,756,771 | **101.9%** |
| DefiLlama `dailyRevenue`, headline trailing-30d total | $1,838,057 | 97.4% |
| DefiLlama `dailyRevenue`, 7d headline (vs my 7d $361,298) | $372,840 | 96.9% |
| revenue.near.org 30D net revenue (displayed, 3 sig. figs.) | $1,970,000 | **90.9%** |
| revenue.near.org 30D gross fees (displayed) | $5,460,000 | — |
| DefiLlama `dailyFees`, daily-series sum (exact window dates) | $5,456,771 | — |
| DefiLlama `dailyFees`, headline trailing-30d total | $5,619,218 | — |

**Implied capture rate (retained ÷ gross) from the reconstruction:**

| Gross denominator | Implied capture |
|---|---|
| DefiLlama fees, daily-series sum ($5,456,771) | **32.8%** |
| DefiLlama fees, headline total ($5,619,218) | 31.9% |
| revenue.near.org gross, displayed ($5,460,000) | 32.8% |

**Reading.** The retained leg is confirmed by two independent routes that
agree within ~2–3%: the on-chain wallet census ($1.79M at 15:54 UTC,
$1.81M fresh at ~19:30 UTC) and DefiLlama's revenue series ($1.76M
series sum / $1.84M headline). revenue.near.org's displayed 30D net
revenue ($1.97M at 15:54 UTC, $2.01M at 19:24 UTC) sits ~7% above
DefiLlama's revenue and ~10–11% above the census. The gap is **not**
explained by window alignment (tested: shifting the window ±2 days moves
the census total by at most ~$35k — Oct 9–11 sweeps total $154,972, and
the alternative windows Oct 11–Nov 9 / Oct 10–Nov 8 / Oct 9–Nov 7 give
$1.77–1.82M) nor by price method (daily mean vs close: +0.53%) nor by
display rounding ($1.97M is 3 significant figures, ±$5k). **The gap is
now decomposed — see §8: it is the pp_qi (quote-improvement) leg, which
the dashboard counts in net revenue but which does not land in the
revenue wallets.** The earlier hypotheses are resolved there: accrual-vs-
cash timing is not the driver (the Nov 1–10 same-window test still shows
the gap), and the B2B leg *does* arrive in the wallets — only pp_qi does
not.

**What this means for the thesis.** The thesis's capture rate, 35.97%,
comes from revenue.near.org alone (its 30D net/gross card pair on
2026-11-10 ~03:05 UTC) and sits at the **top** of the range the evidence
supports: the reconstruction implies **~32–33%** against DefiLlama's gross
fees, and revenue.near.org's own current pp-split sums to 36.14% for 30D.
If capture were 32.8% instead of 35.97%, R0 would be ~$21.9M/yr instead
of $24.08M/yr and the base DCF ~$0.38/token instead of $0.42 — the same
honest conclusion (retained revenue supports ~11–12% of the price), just
slightly weaker. **No thesis number has been changed on this evidence:**
the gap is a single-source discrepancy of ~9% on one input, the
reconstruction window ends on a partial day, and revenue.near.org's exact
window/valuation basis is not public. The 32–36% range is now stated here
so a reader can see the sensitivity; the model keeps its sourced 35.97%
until a longer or accrual-matched run resolves the gap.

## 6. All-time census cross-check — COMPLETE

Run `python3 src/reconstruct_intents.py --all-time`, 2026-11-10T16:26:15Z.
Full output: `data/processed/reconstruction_intents_alltime.json`.

Target (revenue.near.org live wallet table, RSC `nearAmount`, 2026-11-10):
fefundsadmin 1,994,013.62 NEAR (46.6%), buybacks 1,730,368.02 NEAR (40.4%),
1csfundsadmin 555,348.27 NEAR (13.0%) — total **4,279,729.92 NEAR**.
Note the wallet table counts **genuinely-new inflows** to each wallet, not
just `intents.near` transfers — the comparison below is done on that basis.

| Wallet | Receipts scanned | `intents.near` sweeps | `intents.near` NEAR | vs dashboard target |
|---|---|---|---|---|
| fefundsadmin.sputnik-dao.near | 1,551 (17 pp., back to 2025-09-22) | 1,433 (first 2026-04-24) | 727,724.27 | 36.5% — see below |
| buybacks.multisignature.near | 3,319 (35 pp., back to 2026-03-18) | 3,271 | 1,728,897.55 | **99.92%** |
| 1csfundsadmin.sputnik-dao.near | 547 (7 pp., back to 2025-10-02) | 484 | 555,339.97 | **100.00%** |
| **Total** | **5,417** | **5,188** | **3,011,961.80** | — |

**fefundsadmin is the exception that proves the rule.** Its `intents.near`
leg is only 727,724.27 NEAR (36.5% of its dashboard total) — but its
**total inflows** are 1,998,084.31 NEAR vs the dashboard's 1,994,013.62
(**100.2%**). The extra 1,270,360.03 NEAR arrived as five monthly
`TRANSFER`s from `auroraliqsupport.near` (Nov 2025–Mar 2026: 319,044 /
108,468 / 206,812 / 406,644 / 229,390 NEAR) — the early Intents revenue
route, before the contract started sweeping directly to the wallet on
2026-04-24. Monthly `intents.near` sweeps since: Apr 2026 8,121 → May
95,895 → Jun 68,796 → Jul 79,349 → Aug 127,261 → Sep 159,831 → Oct
154,227 → Nov (partial) 34,245 NEAR.

**Grand reconciliation.** `intents.near` sweeps (3,011,961.80 NEAR) +
fefundsadmin's `auroraliqsupport.near` leg (1,270,360.03 NEAR) =
**4,282,321.83 NEAR** vs the dashboard's 4,279,729.92 NEAR — **100.06%**
(+2,592 NEAR, 0.06%; the dashboard figure was fetched ~40 min before the
enumeration finished, and the dashboard rounds to 0.1 NEAR). The remaining
non-sweep inflows are correctly **excluded** by the dashboard because they
are not new revenue: 510,068 NEAR of `1csfundsadmin` → `buybacks` transfers
(internal reshuffling between revenue wallets), 555,079 NEAR of
`1csfundsadmin` → `1csfundsadmin` self-transfers, 12,025 NEAR of buybacks
self-transfers, and dust. **Conclusion: the three-wallet census is
complete. No fourth fee-collector wallet is hiding in the totals.**

**Caveats on the all-time run.**
- The all-time USD total in the JSON ($2,311,393) is **partial**: CoinGecko's
  free `market_chart` only returns 35 days of prices, so sweeps before
  ~2026-10-06 have no price (`missing_price_days` lists 247 days). The NEAR
  totals above are the price-independent census facts; the USD figure is
  only the last-35-days slice.
- One paging artefact was found and corrected: NEARBlocks returned the same
  buybacks receipt twice on adjacent pages (receipt
  `2fZe1oad5NFftw6VFGWKtupf6gfHTDyy5x1jh8uRBqqE`, 2026-04-23, 1,314.37
  NEAR). The delivered script now dedupes by `receipt_id` (a single tx
  yielding two *distinct* receipts is still counted twice, as it should
  be); the JSON records the correction. The 30d run had 0 duplicates and
  is unaffected.
- All-time archival verification (5 samples spread Jan 31 → Nov 10, 2026):
  **5/5 TRUE**, including the oldest (2026-01-31) — the public archival RPC
  answers `EXPERIMENTAL_tx_status` at least that far back.
- Also note the README's existing caveat (buybacks' live NEARBlocks balance,
  2,229,769 NEAR, vs the dashboard's traced inflow): the balance counts
  **all** inflows minus outflows (the wallet spends NEAR on buybacks), so
  balance ≠ traced inflow is expected, not evidence of a missing leg.

## 7. What a full reconstruction would still need

- **Gross fees from swap events (not done).** Rebuilding gross fees means
  parsing DIP-4 `token_diff` settlement events on `intents.near` for every
  swap, pricing both legs, and attributing the fee — that needs a
  full-history indexer (FastNear, NEAR Lake, or a self-run indexer), not
  the public archival RPC: enumerating blocks via RPC is ~86,400
  blocks/day and the public endpoint is rate-limited. The retained leg
  rebuilt here is the leg the thesis's DCF actually uses, so this gap
  does not block the valuation; it blocks an independent check of the
  *gross* denominator and of the capture mechanisms' split (pp_fe /
  pp_b2b / pp_qi).
- **Accrual-vs-cash timing — RESOLVED, not the driver (§8).** The
  follow-up gap chase (2026-11-10 ~19:30 UTC) decomposed the gap
  exactly: it is the pp_qi leg, not timing. The Nov 1–10 same-window
  test still shows the gap (+14.5% fresh), which a timing difference
  cannot produce, and valuing sweeps at swap-time prices instead of the
  daily close would move the total by ~1%, not 9–11%.
- **Fee-collector census beyond the three wallets.** The census is exactly
  the three wallets revenue.near.org's own table names. A different
  collector wallet would be missed; the all-time cross-check in §6 is the
  test for that.
- **A note on the existing fetch — FIXED 2026-11-10 (commit 478b7ce7).**
  `src/fetch.py`'s wallet-table regex used to misattribute values across
  rows: it reported buybacks = 555,348.3 NEAR — that is 1csfundsadmin's
  value; the true buybacks all-time inflow is 1,730,368.0 NEAR. It now
  parses the unambiguous RSC `nearAmount` JSON objects instead (same
  method as this reconstruction script), verified by manual refresh run
  #2. The misattributed figure was never used by the model.

## 8. Gap decomposition — RESOLVED 2026-11-10 ~19:30 UTC

Fresh re-derivation of **both** sides, same evening: the dashboard
re-fetched live at ~19:24 UTC, DefiLlama re-fetched live, and the census
re-run for the same Oct 12–Nov 10 window (1,125 sweeps, 406,488.36 NEAR,
$1,807,930 at daily close — §3). All figures below are from that fresh
run unless labelled otherwise.

### 8.1 The dashboard's net revenue is gross × pp-split, not a cash sum

revenue.near.org's 30D net revenue is a **derived** figure: gross fees ×
the capture-mechanism split (pp_fe + pp_b2b + pp_qi). Evidence:

- The 30D card pair gives the same capture as the pp-split sum:
  $2.01M / $5.46M = 36.81% vs pp-split d30 sum 36.79%
  (pp_fe 0.21925 + pp_b2b 0.11034 + pp_qi 0.03830).
- The 30D net moved **$1.97M → $2.01M (+$40k) between the 15:54 and
  19:24 UTC fetches while the wallet table did not move at all**
  (fefundsadmin 1,994,013.6 / buybacks 1,730,368.0 / 1cs 555,348.3 NEAR,
  identical to 0.1 NEAR). A cash sum of wallet sweeps cannot move while
  the wallets stand still; a modelled figure can.
- The dashboard's own daily fees series (`totalFeesSeries`, in the same
  RSC payload) had only $1,611 of gross fees for Nov 10 at 19:24 UTC —
  the day is ~99% missing there — yet the 30D net card kept moving. The
  dashboard's figures lag the chain by hours and are computed on
  different refresh cadences per component; they are not a real-time
  cash sum.

### 8.2 The cash census equals pp_fe + pp_b2b — two window-matched tests

The split is published per window, so it can be tested exactly on the
windows it is defined for, using the gross-fees NEAR totals from the
dashboard's own daily series (which agrees with DefiLlama's daily fees
to 0.03% over Oct 12–Nov 9 — the gross denominator is not in dispute).

| Window | Gross (NEAR) | Census (NEAR) | pp_fe+pp_b2b implied | Census vs fe+b2b | Full split implied |
|---|---|---|---|---|---|
| 30D, Oct 12–Nov 10 (orig run, like-for-like timing) | 1,222,601 | 401,523 | 402,957 | **−0.36%** | 449,783 |
| 7D, Nov 4–10 (orig run, like-for-like timing) | 311,153 | 97,577 | 97,976 | **−0.41%** | 113,213 |

Two independent windows, both matching to **under 0.5%**: the wallets
receive pp_fe + pp_b2b, and essentially nothing else. The full split
(pp_fe + pp_b2b + pp_qi) overstates the cash by 48,260 NEAR (30D) and
15,636 NEAR (7D). The residuals (−0.36%, −0.41%; census a touch below
fe+b2b) are a few hours of unswept accrual plus price/window noise —
the sign flips between runs (fresh census: +0.87% on 30D), which is
exactly what timing noise looks like.

### 8.3 Component decomposition of the 30D gap (fresh numbers)

| Component | $ | Share of gap | Verdict |
|---|---|---|---|
| Dashboard 30D net revenue (19:24 UTC) | $2,010,000 | — | Modelled: gross × 36.79% split |
| Cash census, 1,125 sweeps (19:30 UTC) | $1,807,930 | — | On-chain receipts, 7/7 archival-verified |
| **Gap** | **$202,070** | 100% | Census = 90.0% of dashboard |
| of which: pp_qi leg (0.03830 × $5.46M gross) | ~$209,000 | ~103% | Counted by dashboard, **not in wallets** |
| of which: residual (timing / price / window noise) | ~−$7,000 | ~−3% | Census slightly above fe+b2b on the fresh run |
| Price method (daily close vs daily mean) | +$9,158 (+0.51%) | — | Moves census up; not a driver |
| Window alignment (±2-day shifts) | ≤ $35,000 | — | Tested in §5; not a driver |
| Missing sweeps | $0 | — | Proven complete (§8.4) |
| Gross-fee denominator | $0 | — | Dashboard vs DefiLlama agree to 0.03% |

The Nov 1–10 same-window test confirms it is not a window artefact:
their November revenue is 147,932 NEAR / $564,132 vs the fresh census
129,158 NEAR / $484,301 — a +14.5% gap in the same ten days
(+19.1% on the 15:54 UTC census, before the late-Nov-10 sweeps landed).
The gap is **growing** because pp_qi's share is rising (d30 3.83% →
d7 4.90%; November's implied pp_qi share is ~4.4%).

### 8.4 The census is complete — no missing sweeps

The fresh per-wallet checkpoints contain **every** receipt to the three
wallets in the window, tabulated by (predecessor, first action):

| Wallet | Predecessor | Action | Receipts | NEAR |
|---|---|---|---|---|
| buybacks | intents.near | TRANSFER | 788 | 286,720.84 |
| fefundsadmin | intents.near | TRANSFER | 337 | 119,767.52 |
| buybacks | `52435fe9…` (implicit account) | TRANSFER | 1 | 531.04 |

There is exactly **one** non-`intents.near` receipt in the window: a
single 531.04 NEAR transfer from an implicit account to buybacks
(≈$1,900, 0.13% of the census) — correctly excluded by the sweep
filter; it is not a fee sweep and is immaterial to the gap. No
fourth fee-collector route, no non-TRANSFER sweep action, no missed
leg. The all-time cross-check (§6) independently confirms completeness:
their cumulative accrued revenue is 5,027,785 NEAR vs 4,279,730 NEAR
ever received by the wallets — a 748,055 NEAR (14.9%) difference on
their own figures, i.e. the dashboard's accrued revenue has always
exceeded wallet inflows, by a similar share.

### 8.5 What pp_qi is — and what we cannot determine from outside

pp_qi is the dashboard's quote-improvement mechanism share: the value
attributed to fills executed at a better price than quoted. The
dashboard counts it as retained revenue (3.83% of gross in 30D,
4.90% in 7D). The cash evidence says it does not land in the three
revenue wallets. From public data alone we **cannot** determine whether
it settles elsewhere (e.g. to solvers), settles with a long lag, or is
a paper accrual with no cash counterpart — that needs the Intents
contracts or the revenue.near.org team. What is determined is the cash
fact: over two window-matched tests the wallets receive pp_fe + pp_b2b
to within 0.5%, and pp_qi accounts for the whole ~$202k gap.

### 8.6 What this means for the thesis — numbers unchanged

The thesis keeps its sourced capture rate (35.97%, from
revenue.near.org's card pair) and its headline numbers (R0 $24.08M/yr,
base DCF $0.42/token). The cash-verified capture is **~32.8% (30D) /
~31.5% (7D)**; on a cash basis R0 would be ~$21.9M/yr and the base DCF
~$0.38/token — the same conclusion (retained revenue supports ~11% of
the $3.60 price), slightly weaker, and already inside the dashboard's
sensitivity grid. The 32–36% range is the honest statement of the
capture rate; the predictions (P1/P2) are defined against
revenue.near.org's own figures and stand as written. No model input
was changed on this evidence because the conclusion does not move.
