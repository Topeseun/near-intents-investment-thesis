# BUILD NOTES — Pipeline + model

## 2026-11-10 ~04:00–04:30 WAT — Upgrade: daily activity + Intents volume (M12–M16, charts 8–9)

### What changed and why
A competitor repo exposed two endpoints the research phase had missed:
1. **NEARBlocks `GET /v1/charts`** — the research phase tested 12 suffixed paths
   (`/v1/charts/daily-txns`, `/v1/stats/daily`, … — all 404) but never the bare
   `/v1/charts` path. It returns the FULL daily series, 2020-07-21 → today.
2. **DefiLlama `GET /v1/summary/dexs/near-intents`** — daily Intents VOLUME
   (the `dexs` dimension), 2024-12-10 → today. Not previously tested.

Both verified live 2026-11-10 ~03:01 UTC before any code was written:
- `/v1/charts`: **200, 1,541,993 B, 2,303 daily points, 2020-07-21 → 2026-11-09.**
  All 20 fields present in the latest rows. Gaps in early rows only:
  `multichain_txns` null in 1,577 rows before 2024-11-14; `txn_volume` null in
  11 rows (Jul–Aug 2020). Neither field is used by any metric. Values arrive
  as decimal strings (supplies in yocto); `model.py:charts_daily()` parses
  per-field and skips nulls per field, never the whole row.
- `summary/dexs/near-intents`: **200, 50,347 B, `totalDataChart` 699 daily
  points (strict 86,400 s spacing, no zeros), 2024-12-10 → 2026-11-08.**
  Totals: 24h $87,673,580; 7d $756,895,669; 30d $3,561,518,211;
  1y $32,700,193,219; all-time $37,005,533,919 — and the all-time total equals
  the sum of the daily points exactly. The 1y figure ($32.7B) also matches the
  secondary "$32.5B LTM volume" quote the research notes had flagged
  unverified — it is now a measured figure, not a secondary one.

### New metrics (M1–M11 untouched, DCF inputs untouched)
- **M12 daily txns:** 895,302/day (2026-11-09), 30d avg 662,520, all-time peak
  **13,935,402 on 2023-12-01 — 93.6% below peak**.
- **M13 daily active accounts:** 77,752/day, 30d avg 58,223, all-time peak
  **2,256,512 on 2024-04-22 — 96.6% below peak**.
- **M14 new accounts:** 287,194 in 30d (−18.9% vs prior 30d); net +265,067
  after 22,127 deletions (prior 30d deletions were 564,320 — a one-off
  purge-scale spike, not a trend; reported, not interpreted).
- **M15 Intents volume:** 30d $3,714,703,671 from the daily series (−22.0% vs
  prior 30d), peak day $303,419,794 on 2026-09-17. Endpoint 30d total is
  $3,561,518,211 (+4.3% difference: the endpoint's rolling window ends at
  fetch time, after the last daily point of 8 Nov — both figures are stored).
  **Implied gross fee rate = 30d fees ÷ 30d volume = 15.02 bps**, matching the
  ~15 bps secondary quote: two independent series agreeing.
- **M16 price-vs-fees correlation:** Pearson r of weekly log-changes, last
  365d, n=366: **price vs Intents fees r = 0.055** (essentially no weekly
  co-movement), price vs base gas fees r = 0.566. Contemporaneous co-movement
  ONLY — no lead-lag test (deliberately not copied from the competitor), no
  causation claim. The low Intents-fee correlation is itself a finding: the
  fee series is extremely spiky week to week (it includes the $16,790 day).

### The ">90% decline" check
The competitor's public claim of ">90% decline from peak" is **confirmed by
our own data, and stronger than claimed**: txns −93.6%, active accounts
−96.6% from their all-time peaks. The thesis now states this as its bear leg
instead of leaving the usage chapter unmeasured. No agreement was forced —
the numbers are computed from the cached `/v1/charts` response.

### DCF headline numbers — unchanged
Fee-derived numbers reproduce **exactly** vs the 2026-11-10 ~02:54 UTC run:
F30 $5,578,208, capture 35.97%, R0 $24,077,777, DCF $0.4238/token.
Price-dependent numbers moved only with the live price tick
($3.61 → $3.60: break-even $118.34M → $118.02M/yr, mcap/R0 196.5× → 196.2×,
bought 6,669,744 → 6,688,271 NEAR/yr). No DCF input or assumption was altered.

### Fetch incident (2026-11-10 ~03:05 UTC) — CoinGecko 429
`coingecko_market_chart_ethereum_365.json` returned **429** on the first pass
and the pre-existing `fetch.py` behaviour overwrote the good cached file with
the 187-byte 429 body. Recovered with a manual re-fetch after a 75 s backoff
(200, 366 points) and a manifest patch. Fix applied in this upgrade:
`fetch.py` now retries once after a 60 s backoff on 429 **before** saving, so
a 429 body never clobbers a good cache again. The LI.FI 400 is expected and
unchanged (dropped benchmark, as before).

### Graceful degradation (designed, not yet triggered)
- If `/v1/charts` fails, M12–M14 carry `"available": false` with a reason,
  `chart_08_data.json` is `available: false`, `charts.py` skips chart 8 and
  the dashboard prints a fallback paragraph. No activity figure is fabricated.
- If the dexs endpoint 404s or returns no series, M15/chart 9 degrade the
  same way and the volume leg is dropped (the old "fees, not volume"
  limitation returns). Both paths are covered by `tests/test_outputs.py`
  only in their available form — the unavailable form is untested by design
  (it has never occurred live).

### Corrections to the research notes
- §3 "NEARBlocks has *no* public daily-stats endpoint" — **wrong**. The bare
  `/v1/charts` path was never tested. Corrected in README + dashboard
  limitations; the `/v1/txns` paging workaround stays cut (now unnecessary).
- §9 risk #2 "No free daily Intents VOLUME series" — **closed**. The dexs
  endpoint provides it from 10 Dec 2024. The remaining volume caveat is the
  shorter window (Dec 2024 vs May 2025 fees / Jul 2020 activity).
- The research-notes §4 secondary volume figures ($32.5B LTM) are now
  superseded by the measured dexs series ($32.7B 1y).

### Reproducibility
`rm -rf data && python3 src/fetch.py && python3 src/build.py &&
python3 src/build_dashboard.py && python3 -m unittest discover -s tests -v`
— 15 tests, stdlib unittest only. Full clean re-run in a /tmp copy: see
"Verification" below (filled in at commit time).

## Verification (clean re-run, /tmp copy)

Run 2026-11-10 ~03:09–03:10 UTC in `/tmp/near-thesis-clean` (repo copied
without `.git`/`data`/`docs`; then `rm -rf data && python3 src/fetch.py &&
python3 src/build.py && python3 src/build_dashboard.py &&
python3 -m unittest discover -s tests -v`):
- **Fetches:** 29 files, all HTTP 200 except the expected LI.FI 400. No
  CoinGecko 429 on this run (the retry fix was not exercised).
- **Fee-derived numbers reproduce exactly** (3rd consecutive run):
  F30 $5,578,208, capture 35.97%, R0 $24,077,777, DCF $0.4238/token.
  `dcf.json` base_case is byte-identical to the repo run; inputs differ only
  in `near_price_usd`/`market_cap_usd`.
- **New metrics identical** between the repo run (03:05 UTC) and the clean
  run (03:09 UTC): M12/M13/M14/M15 values and M16 correlations unchanged.
  A leaf-by-leaf diff of `metrics.json` (59/281 leaves) shows only
  `fetched_at_utc` timestamps, price-derived values (price $3.60 → $3.59:
  break-even $118.02M → $117.69M/yr, mcap/R0 196.2× → 195.7×), and live
  chain state (height, total txns, avg block time, supply drift ~2 NEAR).
- **Tests: 14/14 OK** in the repo and in the /tmp copy. (One intermediate
  13/14 in /tmp was a copy-order artifact: `docs/` had been copied from the
  repo's older dashboard build, so the byte-equality check failed until
  `docs/` was re-copied from the freshly built dashboard — the documented
  workflow is "rebuild, then re-copy docs".)
- **Charts:** chart08/chart09 PNGs valid, 1500×1050, 181 KB / 196 KB;
  SVG twins present. Dashboard HTML 24,149 bytes in both runs.

## 2026-11-11 ~10:13 WAT — Metcalfe check (M17, chart 10)

- Prompt: a fellow Investment Thesis entry, NEAR Demand Ledger (gallery #42,
  @0xhannnx), reports a Metcalfe disconnect — log(price) on log(users) slope
  0.21, R² 0.28 over 73 months, verdict "hypothesis is unproven". This slice
  runs the SAME test on our series over the FULL window and reports the real
  numbers, whatever they show.
- `src/model.py` adds M17 (log-log OLS, NEARBlocks `/v1/charts` daily series,
  price and users on the same daily grid — no source mixing, no CoinGecko
  365-day cap involved) and `chart_10_data.json`. Primary: MONTHLY (month-end
  price vs monthly mean active accounts, 74 months, Oct 2020 – Nov 2026);
  daily log-log is the robustness line; market-cap version and the
  cumulative-txns leg (labelled PARTIAL — a monotonically increasing stock is
  trend-dominated by construction) complete the set. A 2024-onwards
  sub-window is reported as an honest caveat. Rows with price <= 0 (85) or
  users <= 0 (11) are dropped before taking logs — all pre-launch Jul–Oct
  2020; no in-window day is dropped. Strict Metcalfe predicts slope ≈ 2.0.
- Results (data vintage 2026-11-10 03:05 UTC, the README headline vintage):
  monthly slope 0.0215 (SE 0.0376), R² 0.0045, r 0.067 — statistically zero.
  Daily slope 0.0112, R² 0.0012, n=2,218 days. Market cap on users: slope
  0.1856, R² 0.2696, n=73. Cumulative txns: slope −0.0122, R² 0.0021
  (total 5.479B txns). Sub-window 2024–2026: slope 0.323, r 0.634, n=35 —
  co-movement in the recent window, driven by the joint fall from the Apr
  2024 activity peak; the relation flips sign across sub-periods, so it is
  not a stable law. Net: value NEAR on fees, not users. The rival's slope
  (0.21) is stronger than ours (0.02) — the gap is itself a finding about
  sensitivity to the activity definition; the shared conclusion (disconnect)
  is what matters. Nov 2026 is a partial month (data to 9 Nov).
- `src/charts.py` adds chart 10 (two-panel log-log: price vs users, price vs
  cumulative txns, OLS fits drawn). Dashboard gains chart 10 + a "Metcalfe
  check" section stating the numbers, the rival comparison, and the
  2024-onwards caveat. README gains a headline-table row + chart-10 entry.
  Tests: 15 (new `test_metcalfe_sane` + chart-10 checks in
  `test_chart_data_matches_metrics`).
- No other figure, chart, or prediction changed. M1–M16, F30 $5,578,208,
  capture 35.97%, R0 $24,077,777, DCF $0.4238/token reproduce exactly.
- Data-vintage note: this build ran on the local 03:05 UTC cache (no re-fetch),
  so the pushed processed files carry 03:05 values, reverting the 17:02 UTC
  auto-refresh values (F30 $5,619,218 → $5,578,208, DCF $0.4332 → $0.4238)
  — a 14-hour rollback to the figures the README states. The next daily
  auto-refresh (06:00 UTC) re-applies freshness; the full processed set stays
  mutually consistent in the meantime.
- Verification: clean-copy re-run in `/tmp/near-thesis-clean-metcalfe`
  (repo copied without `.git`/`docs`, cache `data/` included, NO re-fetch):
  `python3 src/build.py && python3 src/build_dashboard.py && python3 -m
  unittest discover -s tests` — 15/15 OK. M17 identical to the repo run
  (slope 0.0215, R² 0.0045, r 0.0671); full `metrics.json` identical except
  the `generated_at_utc` build timestamp; dashboard HTML identical except
  its generated-time lines; chart-10 SVG 144,117 bytes in both runs (SVGs
  differ only in matplotlib's creation-date metadata and random clip IDs).
- KNOWN GAP (pre-existing, NOT fixed here): the WS2 dated-predictions section
  renders nowhere on the live dashboard — `build_dashboard.py` has no
  predictions rendering, so the auto-refresh wiped the WS2 dashboard changes.
  `PREDICTIONS.md` + `data/predictions.json` exist on the repo but render
  nowhere. Flagged for a separate fix.

## 2026-11-11 ~10:35 WAT — Dated predictions render on the dashboard (M18) + fresh fetch
- CLOSED the pre-existing gap flagged in both BUILD_NOTES files: the 7 dated
  predictions (PREDICTIONS.md + data/predictions.json, committed 2026-11-10)
  rendered nowhere. `src/model.py` now computes M18 (live value per prediction
  from the same figures the model already computes; thresholds are the numeric
  form of data/predictions.json, enforced by tests), writes
  `data/processed/predictions.json`, and `src/build_dashboard.py` renders a
  "Dated predictions" section (ID, title, threshold, resolves date, live
  value, status) after the Metcalfe section. Status is a point-in-time read:
  on track / off track / not yet measurable; no prediction has resolved yet
  (earliest 2026-12-31). The daily auto-refresh keeps the section current
  (it re-runs fetch + build + build_dashboard and commits data/ + docs/).
- PREDICTIONS.md + data/predictions.json were missing from the local working
  tree (only on the remote); copied from the remote verbatim (byte-identical
  after a trailing-newline normalisation) so the local tree matches.
- Fresh fetch 2026-11-11 ~09:25 UTC (all sources 200 except the known LI.FI
  400; CoinGecko ETH market-chart 429 recovered on the 60 s retry):
  F30 $5,458,382 (was $5,578,208), capture 33.92% (was 35.97%),
  R0 $22,217,798/yr, DCF $0.3911/token vs $3.58 (10.9% of price),
  break-even $117.37M/yr (5.28x R0). M18 tally: 5 on track, 2 off track —
  P1 ($5,458,382 vs $5,578,208) and P2 (33.92% vs 35.97%) are OFF TRACK:
  fees and capture both moved against the thesis in one day. Reported
  honestly on the dashboard and in README; thresholds unchanged (committed).
- Two hardcoded "~36%" capture strings in model.py (M4 trend_reading, DCF
  reading) are now computed from the live capture rate (~34% today) so they
  cannot go stale again.
- README fully re-synced to the fresh fetch (headline table, honest framing
  ~11%, best valid grid cell $1.01, dated-predictions section, assumptions
  -31.6% / -0.4% / 33.92%, limitations: 24h fee $1,611 vs $168,409 7d avg,
  -33.7% below peak, volume $3.76B / 14.53 bps, revenue headline $11.64M,
  buybacks balance 2,245,764 NEAR vs traced 1,742,346.3 NEAR, TVL $168.9M
  vs $363.0M).
- Tests: 18 (new test_predictions_match_committed,
  test_predictions_live_values_sane, test_dashboard_renders_predictions).
  The two M18 metric tests are already covered by the workflow blocking
  gate (it runs the whole TestProcessedOutputs class). Adding
  test_dashboard_renders_predictions to the gate is still PENDING — the
  GitHub App cannot edit .github/workflows/ via the API (403 on tree
  creation), so that one-line change must be made in the web UI; the local
  copy of the workflow file was reverted to match the remote until then.
- Verification: full pipeline re-run + `python3 -m unittest discover -s
  tests` — 18/18 OK.

## 2026-11-11 ~11:15 WAT — Falsification section (M19, F1–F6)

### What changed and why
The thesis now states what would prove it wrong: six kill conditions
(F1–F6), committed 2026-11-11 in `data/falsification.json` and rendered in
README + dashboard (M19). Three overlap the dated predictions on purpose —
F1 tests the same revenue base as P1 (at the kill level, $2M, not the
November level), F2 the same capture rate as P2 (at the 15% floor, not
35.97%), F4 the same competitive lead as P5 (at parity, not 1.5×). A
prediction going off track is a warning; a falsification condition
triggering is the thesis failing. Status is "triggered" only when the live
value breaches the threshold AND the persistence window has been met.
Live values today (fetch 2026-11-11 ~09:25 UTC): F1 $5,458,382 vs $2M bar;
F2 33.92% vs 15% floor; F3 31.6% precedent vs 50% bar; F4 1.92× vs 1.0;
F5 10.9% of price vs 100% bar; F6 fees 66.3% of the $8,236,902 peak and
volume 79.3% of prior 30d vs the 50% bars. Tally: 0 triggered, 6 not
triggered. No thesis number, prediction threshold or existing metric changed.

### Persistence — what the data supports, honestly
Persistence is counted from the commitment date (2026-11-11) forward, and
each condition uses only the history its data actually carries:
- **F1 (90 days): measured from the stored daily fee series.** The model
  counts consecutive post-commitment days where the trailing-30d sum is
  below $2M, straight from the DefiLlama daily series (550 points). The
  series ends 2026-11-10, one day before the commitment date, so the count
  is 0 today and becomes real as the daily refresh extends the series. The
  May–Aug 2025 launch ramp (trailing-30d below $2M for months) does NOT
  count: it predates the commitment.
- **F2 (90 days): carried forward through the state file.** The capture
  rate is a point-in-time fetch — revenue.near.org returns windows
  (all-time/YTD/7d/30d), not a daily history — so no stored series can
  measure a 90-day run. Instead `src/model.py` reads the previous run's
  `data/processed/falsification.json` and carries `breach_since` forward
  across daily refreshes. Limitation, stated plainly: if that file is ever
  deleted, the 90-day clock restarts from the next breach. No breach today,
  so the clock is at 0 either way.
- **F3 (7+ days): event-based, not measurable from any stored series.**
  The live value is the Oct 1–4 2026 pause precedent (31.6% below the prior
  matching week, Faultline via NearStats routing data, cited in README
  Limitations) — the largest single-provider outage drop on record. The
  daily fee/volume series cannot detect routing-provider outages, so the
  condition is re-evaluated when a new outage is reported, not by the
  refresh. Its status_reason says so on the dashboard.
- **F4 (3 calendar months): measured from aligned daily trailing series.**
  NEAR vs Chainflip trailing-30d fees, computed day by day from both
  DefiLlama daily series (1,043 Chainflip points) and counted
  post-commitment; months are whole calendar months elapsed since the run
  started. Count is 0 today (series ends before the commitment date).
- **F5: no persistence window by design.** A single recomputation at or
  above 100% of price triggers; the claim is about the current level, not a
  trend.
- **F6 (90 days, both legs): measured from the stored daily series.**
  Fees leg: trailing-30d vs the fixed $8,236,902 peak of 14 Oct 2026.
  Volume leg: trailing-30d volume vs its own prior 30d, from the DefiLlama
  dexs daily series (701 points). Both legs must breach on the same day for
  the day to count. Count is 0 today.

### Verification
- Full pipeline re-run (`python3 src/build.py` regenerates metrics,
  predictions + falsification from the same cached fetch) +
  `python3 -m unittest discover -s tests` — 22/22 OK (4 new M19 tests:
  test_falsification_match_committed, test_falsification_live_values_sane,
  test_dashboard_renders_falsification,
  test_readme_contains_falsification_section).
- The two M19 metric tests are in TestProcessedOutputs, so they are already
  covered by the workflow blocking gate (it runs the whole class).
  test_dashboard_renders_falsification is NOT yet in the gate — the gate
  names test_dashboard_renders_predictions explicitly, so adding the new
  test needs the same web-UI edit as commit 99fa40d (API returns 403 on
  workflow files).
