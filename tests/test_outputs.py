#!/usr/bin/env python3
"""Output checks for the NEAR Investment Thesis repo — stdlib unittest only.

Run from the repo root:
    python3 -m unittest discover -s tests -v

What it checks (no network, no new dependencies):
  * every data/processed/*.json exists and parses
  * F30 / capture / R0 / DCF arithmetic is internally consistent
    (R0 = F30 * 12 * capture; Gordon growth; value/token = Value / supply)
  * the sensitivity grid is 3 x 3 x 3 = 27 cells and invalid (g >= r) cells
    are null, valid cells match the Gordon formula
  * all 9 dashboard charts exist as PNG + SVG twins
  * the README contains the headline numbers (fee-stable figures that
    reproduce exactly across re-runs, plus the all-time activity peaks)
  * the new M12-M16 metrics are sane (peaks above current, percentages in
    range, volume positive, correlation in [-1, 1])
  * the two new raw responses are in the manifest with status 200
  * docs/ (GitHub Pages) mirrors dashboard/index.html + the SVGs

Nothing here re-fetches: it reads the committed/built outputs only.
"""
import json
import math
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROC = REPO / "data" / "processed"
RAW = REPO / "data" / "raw"
ASSETS = REPO / "dashboard" / "assets"

PROCESSED_JSONS = [
    "metrics.json", "dcf.json", "sensitivity.json", "benchmarks.json",
    "chart_01_data.json", "chart_02_data.json", "chart_03_data.json",
    "chart_04_data.json", "chart_05_data.json", "chart_06_data.json",
    "chart_07_data.json", "chart_08_data.json", "chart_09_data.json",
]

CHARTS = [
    "chart01_intents_daily_fees",
    "chart02_intents_vs_base_fees",
    "chart03_price_vs_fees_divergence",
    "chart04_valuation_multiples",
    "chart05_buyback_vs_issuance",
    "chart06_staking_economics",
    "chart07_sensitivity_heatmap",
    "chart08_daily_activity",
    "chart09_intents_volume_and_fees",
]


def load_processed(name):
    return json.loads((PROC / name).read_text())


class TestProcessedOutputs(unittest.TestCase):
    def test_processed_jsons_exist_and_parse(self):
        for name in PROCESSED_JSONS:
            p = PROC / name
            self.assertTrue(p.exists(), f"missing {name}")
            try:
                json.loads(p.read_text())
            except json.JSONDecodeError as e:
                self.fail(f"{name} does not parse: {e}")

    def test_manifest_lists_new_raw_files(self):
        manifest = json.loads((REPO / "data" / "manifest.json").read_text())
        for name in ("nearblocks_charts.json", "defillama_dexs_near-intents.json"):
            self.assertIn(name, manifest, f"{name} not in manifest")
            self.assertEqual(manifest[name].get("status"), 200, name)
            self.assertGreater(manifest[name].get("bytes", 0), 1000, name)

    def test_f30_capture_r0_dcf_consistent(self):
        m = load_processed("metrics.json")
        dcf = load_processed("dcf.json")
        f30 = m["M1_intents_gross_fees"]["total_30d_usd_F30"]
        capture = m["M3_retained_revenue"]["capture_rate_30d_measured"]
        r0 = m["M3_retained_revenue"]["retained_revenue_annualised_base_usd_R0"]
        # R0 = F30 * 12 * capture
        self.assertAlmostEqual(r0, f30 * 12 * capture, delta=1.0)
        # DCF base case: R1 = R0 * (1+g); Value = R1 / (r-g); per-token = / supply
        inp = dcf["inputs"]
        base = dcf["base_case"]
        r, g = inp["discount_rate_r_base"], inp["growth_rate_g_base"]
        r1 = r0 * (1 + g)
        self.assertAlmostEqual(base["R1_next_year_retained_revenue_usd"], r1, delta=1.0)
        value = r1 / (r - g)
        self.assertAlmostEqual(base["equity_value_usd"], value, delta=1.0)
        self.assertAlmostEqual(
            base["value_per_token_usd"], value / inp["circulating_supply_near"],
            delta=1e-6)
        self.assertAlmostEqual(inp["F30_trailing_30d_gross_fees_usd"], f30, delta=0.01)
        self.assertAlmostEqual(inp["capture_base_measured_30d"], capture, delta=1e-9)
        # F30 cross-check: endpoint total30d vs sum of last 30 daily points
        self.assertLessEqual(
            abs(m["M1_intents_gross_fees"]["f30_cross_check_diff_pct"] or 0), 5.0)

    def test_sensitivity_grid_shape_and_formula(self):
        sens = load_processed("sensitivity.json")
        dcf = load_processed("dcf.json")
        grid = sens["grid"]
        self.assertEqual(len(grid), 27, "grid must be 3 captures x 3 growth x 3 discounts")
        caps = sorted({c["capture"] for c in grid})
        grows = sorted({c["growth"] for c in grid})
        discs = sorted({c["discount"] for c in grid})
        self.assertEqual((len(caps), len(grows), len(discs)), (3, 3, 3))
        self.assertEqual(sens["axes"]["capture"], caps)
        f30 = dcf["inputs"]["F30_trailing_30d_gross_fees_usd"]
        supply = dcf["inputs"]["circulating_supply_near"]
        for cell in grid:
            r0 = f30 * 12 * cell["capture"]
            self.assertAlmostEqual(cell["R0_usd"], r0, delta=1.0)
            if cell["growth"] >= cell["discount"]:
                self.assertIsNone(cell["value_per_token_usd"],
                                  f"invalid g>=r cell must be null: {cell}")
                self.assertEqual(cell["invalid_reason"], "g >= r")
            else:
                v = r0 * (1 + cell["growth"]) / (cell["discount"] - cell["growth"])
                self.assertAlmostEqual(cell["value_per_token_usd"], v / supply,
                                       delta=1e-3)
                self.assertIsNone(cell["invalid_reason"])

    def test_buyback_vs_issuance_consistent(self):
        m = load_processed("metrics.json")
        m6 = m["M6_buyback_vs_issuance"]
        issued = m6["issued_per_year_near"]
        bought = m6["bought_per_year_base_near"]
        self.assertAlmostEqual(m6["net_supply_change_base_near_per_year"],
                               issued - bought, delta=1.0)
        self.assertAlmostEqual(
            m6["break_even_retained_revenue_usd_per_year"],
            issued * m6["near_price_usd"], delta=1.0)
        self.assertGreater(issued, bought, "thesis must stay net-inflationary at base")

    def test_new_activity_metrics_sane(self):
        m = load_processed("metrics.json")
        m12, m13, m14 = m["M12_daily_txns"], m["M13_daily_active_accounts"], m["M14_new_accounts_trend"]
        for metric in (m12, m13, m14):
            self.assertTrue(metric.get("available"), metric)
            self.assertGreater(metric["daily_points"], 2000)
            self.assertGreater(metric["all_time_peak"]["value"],
                               metric["current_last_day"])
            self.assertGreaterEqual(metric["current_pct_below_peak"], 0)
            self.assertLessEqual(metric["current_pct_below_peak"], 100)
            self.assertGreater(metric["daily_avg_last_30d"], 0)
        # The competitor's ">90% decline from peak" claim, checked on our data:
        self.assertGreater(m12["current_pct_below_peak"], 90)
        self.assertGreater(m13["current_pct_below_peak"], 90)
        self.assertEqual(m12["first_date"], "2020-07-21")
        self.assertEqual(m12["all_time_peak"]["date"], "2023-12-01")
        self.assertEqual(m13["all_time_peak"]["date"], "2024-04-22")
        self.assertGreater(m14["sum_last_30d"], 0)

    def test_intents_volume_metric_sane(self):
        m = load_processed("metrics.json")
        m15 = m["M15_intents_daily_volume"]
        self.assertTrue(m15.get("available"), m15.get("reason"))
        self.assertGreater(m15["daily_points"], 600)
        self.assertEqual(m15["first_daily_date"], "2024-12-10")
        self.assertGreater(m15["total_30d_usd_from_daily_series"], 1e9)
        self.assertGreater(m15["total_all_time_usd_from_daily_series"], 1e10)
        # Endpoint total vs series sum: same 30d window give or take the
        # 1-2 days of reporting lag between the last daily point and fetch.
        self.assertLessEqual(
            abs(m15["total_30d_series_vs_endpoint_diff_pct"] or 0), 10.0)
        # Implied gross fee rate must be a plausible swap fee (1-100 bps).
        bps = m15["implied_gross_fee_rate_30d_bps"]
        self.assertGreater(bps, 1)
        self.assertLess(bps, 100)
        # Peak day is a real day inside the series window.
        self.assertLessEqual(m15["peak_daily_volume"]["date"], m15["last_daily_date"])

    def test_price_vs_fees_correlation_sane(self):
        m = load_processed("metrics.json")
        m16 = m["M16_price_vs_fees_correlation"]
        r = m16["pearson_price_vs_intents_fees_weekly_log_changes"]
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r, -1)
        self.assertLessEqual(r, 1)
        self.assertGreaterEqual(m16["n_weekly_pairs_price_vs_intents_fees"], 300)
        r2 = m16["pearson_price_vs_base_gas_fees_weekly_log_changes"]
        self.assertGreaterEqual(r2, -1)
        self.assertLessEqual(r2, 1)
        # Correlation only: the metric must not claim a lead-lag result.
        self.assertIn("no lead-lag", m16["definition"].lower())

    def test_chart_data_matches_metrics(self):
        m = load_processed("metrics.json")
        c8 = load_processed("chart_08_data.json")
        c9 = load_processed("chart_09_data.json")
        self.assertTrue(c8.get("available"))
        self.assertEqual(c8["txns_peak"]["value"],
                         m["M12_daily_txns"]["all_time_peak"]["value"])
        self.assertEqual(c8["accounts_peak"]["value"],
                         m["M13_daily_active_accounts"]["all_time_peak"]["value"])
        self.assertEqual(len(c8["daily_txns"]), m["M12_daily_txns"]["daily_points"])
        self.assertTrue(c9.get("available"))
        self.assertEqual(len(c9["daily_volume_usd"]),
                         m["M15_intents_daily_volume"]["daily_points"])
        self.assertAlmostEqual(c9["volume_30d_usd"],
                               m["M15_intents_daily_volume"]["total_30d_usd_from_daily_series"],
                               delta=1.0)


class TestDashboardAndReadme(unittest.TestCase):
    def test_all_chart_files_exist(self):
        for name in CHARTS:
            for ext in ("png", "svg"):
                p = ASSETS / f"{name}.{ext}"
                self.assertTrue(p.exists(), f"missing {p}")
                self.assertGreater(p.stat().st_size, 1000, f"{p} suspiciously small")

    def test_dashboard_references_all_charts(self):
        html = (REPO / "dashboard" / "index.html").read_text()
        for name in CHARTS:
            self.assertIn(f"assets/{name}.svg", html, f"{name}.svg not in dashboard")
        self.assertIn("Network activity", html)
        self.assertIn("Intents volume", html)

    def test_docs_mirror_dashboard(self):
        docs = REPO / "docs"
        self.assertTrue((docs / "index.html").exists(), "docs/index.html missing")
        self.assertEqual((docs / "index.html").read_bytes(),
                         (REPO / "dashboard" / "index.html").read_bytes(),
                         "docs/index.html differs from dashboard/index.html")
        for name in CHARTS:
            self.assertTrue((docs / "assets" / f"{name}.svg").exists(),
                            f"docs/assets/{name}.svg missing")

    def test_readme_contains_headline_numbers(self):
        readme = (REPO / "README.md").read_text()
        m = load_processed("metrics.json")
        dcf = load_processed("dcf.json")
        f30 = m["M1_intents_gross_fees"]["total_30d_usd_F30"]
        capture = m["M3_retained_revenue"]["capture_rate_30d_measured"]
        r0 = m["M3_retained_revenue"]["retained_revenue_annualised_base_usd_R0"]
        vpt = dcf["base_case"]["value_per_token_usd"]
        # Fee-stable figures: reproduce exactly across re-runs.
        self.assertIn(f"${f30:,.0f}", readme)
        self.assertIn(f"{capture * 100:.2f}%", readme)
        self.assertIn(f"${r0:,.0f}", readme)
        self.assertIn(f"${vpt:.2f}", readme)
        # All-time activity peaks (stable — peaks are in 2023/2024).
        m12, m13 = m["M12_daily_txns"], m["M13_daily_active_accounts"]
        self.assertIn(f"{m12['all_time_peak']['value']:,.0f}", readme)
        self.assertIn(m12["all_time_peak"]["date"], readme)
        self.assertIn(f"{m13['all_time_peak']['value']:,.0f}", readme)
        self.assertIn(m13["all_time_peak"]["date"], readme)
        # The corrected limitations + test command are documented.
        self.assertIn("python3 -m unittest discover -s tests -v", readme)
        self.assertIn("/v1/charts", readme)
        self.assertIn("GitHub Pages", readme)

    def test_no_hardcoded_dcf_drift(self):
        """README headline DCF value must match dcf.json to 2dp."""
        readme = (REPO / "README.md").read_text()
        dcf = load_processed("dcf.json")
        vpt = dcf["base_case"]["value_per_token_usd"]
        self.assertIn(f"${vpt:.2f}", readme)


if __name__ == "__main__":
    unittest.main()
