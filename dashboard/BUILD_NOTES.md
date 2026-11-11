# BUILD NOTES — Dashboard + README

Built: Tue 10 Nov 2026, ~03:55–04:20 WAT (02:55–03:20 UTC). Data: clean
re-run of the pipeline, fetched 2026-11-10 ~02:54 UTC (run 3).

## What was built

- `dashboard/index.html` — static single page, no build step, no server, no
  external JS/CSS (all CSS inline; charts are local PNGs). Dark theme,
  responsive (single-column, mobile-readable). Contents: one-paragraph thesis
  + honest verdict box; 8-card headline-metrics strip (F30, capture, R0, DCF
  vs price, break-even, mcap/retained, bought/yr, staking APY); the model in
  one paragraph; all 7 charts, each with a plain-language takeaway + source
  line + fetch timestamp; NEAR vs SOL/AVAX/ETH benchmark table; Intents
  competitors table; sensitivity heatmap table (r=12% slice, invalid g≥r zone
  marked n/a); capture-trend section; Limitations section; Sources.
- `src/build_dashboard.py` — renders `index.html` from
  `data/processed/metrics.json`, `dcf.json`, `sensitivity.json`,
  `benchmarks.json`, `chart_07_data.json`. Every number on the page is
  formatted from those JSONs; nothing is hardcoded, so re-running the
  pipeline + this script regenerates a dashboard that always matches the
  model. (It does NOT touch `fetch.py`, `model.py`, `charts.py`, `build.py`
  or `assumptions.yaml`.)
- `README.md` (repo root) — title + thesis, file map, one-command reproduce,
  headline results with the honest bear framing, data-sources table with
  URLs, assumptions link, limitations, track + deadline.

## How to regenerate

```bash
cd repo
python3 src/fetch.py && python3 src/build.py && python3 src/build_dashboard.py
```

View: open `dashboard/index.html` directly in a browser, or
`python3 -m http.server --directory dashboard` and visit
http://127.0.0.1:8000/index.html.

## What was verified (2026-11-10 ~03:00–03:20 UTC)

- Clean re-run PASS: `rm -rf data && python3 src/fetch.py && python3 src/build.py`
  — all sources 200 except the expected LI.FI 400 (dropped benchmark).
  Fee-derived numbers reproduced exactly vs run 2 (F30 $5,578,208, capture
  35.97%, R0 $24,077,777, DCF $0.4238/token). Price-dependent numbers moved
  only with the live price tick ($3.60 → $3.61: break-even $118.02M →
  $118.34M/yr, mcap/R0 195.9× → 196.5×, bought 6,688,271 → 6,669,744 NEAR/yr).
  README headline table was updated to the fresh run; the dashboard
  regenerated from the fresh JSONs.
- Automated check (`/tmp/verify_dashboard.py`, 47 assertions, 0 failures):
  all 7 chart images referenced exactly once, exist, valid PNGs >10 KB;
  every headline/benchmark/competitor/heatmap value in the HTML matches the
  fresh JSONs; invalid g≥r cells marked; no launch-ramp CAGR quoted
  anywhere; no annualised single-day figure; no external JS/CSS/CDN
  references; HTML tag-balance parse clean.
- Live serve check: `python3 -m http.server` in `dashboard/` — index.html
  200, all 7 chart PNGs 200 with correct byte sizes.
- External link check: DefiLlama fees endpoint 200, revenue.near.org 200,
  CoinGecko API page 200 (with browser UA; bare curl gets 403 from
  Cloudflare), NEARBlocks stats 200, CoinGecko simple/price with params 200.
  rpc.mainnet.near.org returns 405 to GET (JSON-RPC POST-only) — expected,
  not a broken link.

## Known cosmetic issues

- The matplotlib PNGs have white chart backgrounds inside a dark page — the
  charts are readable and this matches how `charts.py` renders them; a dark
  chart style would need a `charts.py` change (out of scope for this slice).
- The sensitivity table shows only the r=12% slice (matching Chart 7); the
  full 27-cell grid lives in `data/processed/sensitivity.json` and is linked
  from the page.
- README headline numbers are a snapshot of the 02:54 UTC fetch; they drift
  with the live price on the next `fetch.py` run — re-run
  `build_dashboard.py` (and update the README table) after any re-fetch.

## 2026-11-10 ~04:30 WAT — Upgrade: daily activity + Intents volume (M12–M16, charts 8–9)
- `src/fetch.py` now fetches NEARBlocks `/v1/charts` (2,303 daily pts, 2020-07-21 → today) and DefiLlama `summary/dexs/near-intents` (699 daily volume pts, 2024-12-10 → today); both verified live 200 before coding. Also: one 60 s-backoff retry on CoinGecko 429 before saving (a 429 had clobbered the good ETH market-chart cache this run; recovered manually, then fixed).
- `src/model.py` adds M12 daily txns (895,302/day, peak 13,935,402 on 2023-12-01, −93.6%), M13 daily active accounts (77,752/day, peak 2,256,512 on 2024-04-22, −96.6%), M14 new accounts (287,194/30d, −18.9%), M15 Intents volume (30d $3.71B, implied fee rate 15.02 bps), M16 price-vs-fees weekly Pearson r = 0.06 (correlation only, no lead-lag). M1–M11 and all DCF inputs untouched; fee-derived numbers reproduce exactly (F30 $5,578,208, capture 35.97%, R0 $24,077,777, DCF $0.4238/token).
- `src/charts.py` adds chart 8 (daily txns + active accounts, log scale, peaks marked) and chart 9 (Intents volume + fees, two panels) as PNG + SVG twins. Dashboard gains both charts, a "Network activity" section, two headline cards, and rewritten limitations (the old "no DAU series" and "fees, not volume" gaps are closed; the remaining caveats are the weak activity levels and the volume series' shorter window).
- `tests/test_outputs.py` (14 tests, stdlib unittest only) + `docs/` mirror for GitHub Pages (Settings → Pages → deploy from `/docs` on main). See `data/processed/BUILD_NOTES.md` for the full upgrade notes, endpoint verification figures, and the >90%-decline check.

## 2026-11-10 ~04:20 WAT — SVG twins (coordinator)
`src/charts.py` now writes an SVG twin next to every PNG (same figure, same
numbers). `src/build_dashboard.py` references the SVGs: SVG is UTF-8 text, so
the charts can be published through text-only push tooling (GitHub push_files
rejects binary PNGs). PNGs stay in the local tree for demo screenshots and
are git-ignored (`dashboard/assets/*.png`).

## 2026-11-11 ~10:13 WAT — Metcalfe check (chart 10, M17)
- Dashboard gains chart 10 (`chart10_metcalfe_price_vs_users.svg`, two-panel
  log-log: price vs users + price vs cumulative txns) and a "Metcalfe check"
  section: monthly slope 0.02, R² 0.005, n=74 months (Oct 2020 – Nov 2026)
  vs strict-Metcalfe 2.0; daily agrees (0.01 / 0.001); market-cap version
  0.19 / 0.27; rival NEAR Demand Ledger's 0.21 / 0.28 on 73 months noted with
  the same "disconnect" conclusion; the Jan-2024-onwards slope (0.32, r 0.63)
  stated as a caveat, not buried. Net reading: value NEAR on fees, not users.
  No other section, figure, or prediction changed. See
  `data/processed/BUILD_NOTES.md` for the full M17 notes and the data-vintage
  note (this push reverts the 17:02 UTC auto-refresh values to the 03:05 UTC
  README vintage; the next daily refresh re-applies freshness).

## 2026-11-11 ~10:35 WAT — Dated predictions section (M18) + fresh data
- Dashboard gains a "Dated predictions" section after the Metcalfe section:
  all 7 predictions with exact threshold, resolution date, live value, and
  status (on track green / off track red / not yet measurable grey),
  rendered from data/processed/predictions.json by src/build_dashboard.py —
  nothing hardcoded. Fallback paragraph if predictions.json is missing.
  Live values as of the latest fetch: P1 off track ($5,458,382 vs
  $5,578,208), P2 off track (33.92% vs 35.97%), P3–P7 on track. This closes
  the gap flagged in the Metcalfe notes (predictions existed on the repo but
  rendered nowhere).
- Fresh data 2026-11-11 ~09:25 UTC: F30 $5,458,382, capture 33.92%,
  R0 $22.22M/yr, DCF $0.39 vs $3.58. All 10 charts regenerated from the
  fresh cache; Metcalfe chart #10 intact (monthly slope 0.02, R² 0.005).
- Tests: 18/18 OK (new test_dashboard_renders_predictions + two M18
  metric tests). See data/processed/BUILD_NOTES.md for the full notes.
