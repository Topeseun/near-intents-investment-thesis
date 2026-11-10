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
— 14 tests, stdlib unittest only. Full clean re-run in a /tmp copy: see
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
