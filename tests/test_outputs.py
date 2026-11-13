#!/usr/bin/env python3
"""Output checks for the NEAR Investment Thesis repo — stdlib unittest only.

Run from the repo root:
    python3 -m unittest discover -s tests -v

What it checks (no network, no new dependencies):
  * every data/processed/*.json exists and parses
  * F₃₀ / capture / R₀ / DCF arithmetic is internally consistent
    (R₀ = F₃₀ * 12 * capture; Gordon growth; value/token = Value / supply)
  * the sensitivity grid is 3 x 3 x 3 = 27 cells and invalid (g >= r) cells
    are null, valid cells match the Gordon formula
  * all 10 dashboard charts exist as PNG + SVG twins
  * the README contains the headline numbers (fee-stable figures that
    reproduce exactly across re-runs, plus the all-time activity peaks)
  * the new M12-M17 metrics are sane (peaks above current, percentages in
    range, volume positive, correlation in [-1, 1], Metcalfe slope/R² in range)
  * the 7 dated predictions (M18) match the committed PREDICTIONS.md /
    data/predictions.json thresholds and dates, their live values are sane
    and agree with the metrics they come from, and the dashboard renders
    all 7 with live values and statuses
  * the 6 falsification conditions (M19) match the committed
    data/falsification.json thresholds, their live values are sane and agree
    with the metrics they come from, their statuses are consistent with the
    thresholds and persistence windows, and the dashboard renders all 6
    with live values and statuses (plus the README section)
  * the two new raw responses are in the manifest with status 200
  * docs/ (GitHub Pages) mirrors dashboard/index.html + the SVGs

Nothing here re-fetches: it reads the committed/built outputs only.
"""
import html
import json
import math
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROC = REPO / "data" / "processed"
RAW = REPO / "data" / "raw"
ASSETS = REPO / "dashboard" / "assets"

PROCESSED_JSONS = [
    "metrics.json", "dcf.json", "sensitivity.json", "bridge.json",
    "reverse_dcf.json",
    "benchmarks.json",
    "predictions.json", "falsification.json",
    "chart_01_data.json", "chart_02_data.json", "chart_03_data.json",
    "chart_04_data.json", "chart_05_data.json", "chart_06_data.json",
    "chart_07_data.json", "chart_08_data.json", "chart_09_data.json",
    "chart_10_data.json",
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
    "chart10_metcalfe_price_vs_users",
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

    def test_growth_assumption_check(self):
        """Sensitivity output carries a growth-assumption check: the DCF at
        the measured trailing-365d growth rate and at g=0% (both at base r
        and measured capture). Both recompute via Gordon growth and sit
        well below the base case, since the measured trend is ~flat."""
        sens = load_processed("sensitivity.json")
        m = load_processed("metrics.json")
        dcf = load_processed("dcf.json")
        gac = sens["growth_assumption_check"]
        m2 = m["M2_intents_fee_growth"]
        g_meas = m2["log_regression_cagr_last_365d"]["cagr"]
        self.assertAlmostEqual(
            gac["measured_growth_rate_365d_log_regression"], g_meas, delta=1e-12)
        self.assertAlmostEqual(gac["base_growth_rate"], 0.10, delta=1e-12)
        self.assertLess(g_meas, gac["base_growth_rate"],
                        "measured trailing growth must be below the 10% base assumption")
        r0 = dcf["inputs"]["F30_trailing_30d_gross_fees_usd"] * 12 * gac["capture_rate_30d"]
        supply = dcf["inputs"]["circulating_supply_near"]
        r = gac["discount_rate_r"]
        for key, g in (("dcf_value_per_token_at_measured_growth_usd", g_meas),
                       ("dcf_value_per_token_at_zero_growth_usd", 0.0)):
            v = r0 * (1 + g) / (r - g) / supply
            self.assertAlmostEqual(gac[key], v, delta=1e-3)
            self.assertLess(gac[key], dcf["base_case"]["value_per_token_usd"])

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

    def test_metcalfe_sane(self):
        m = load_processed("metrics.json")
        m17 = m["M17_metcalfe_check"]
        self.assertTrue(m17.get("available"), m17.get("reason"))
        # Full window: Oct 2020 (first positive price) to the last series day.
        self.assertEqual(m17["window"].split(" to ")[0], "2020-10-14")
        self.assertGreaterEqual(m17["usable_daily_points"], 2000)
        self.assertGreaterEqual(m17["n_months"], 60)
        for key in ("price_vs_active_accounts_monthly",
                    "price_vs_active_accounts_daily",
                    "market_cap_vs_active_accounts_monthly",
                    "price_vs_cumulative_txns_monthly",
                    "subwindow_2024_onwards_monthly"):
            reg = m17[key]
            self.assertIsNotNone(reg, key)
            self.assertGreaterEqual(reg["slope"], -1)
            self.assertLessEqual(reg["slope"], 3)
            self.assertGreaterEqual(reg["r_squared"], 0)
            self.assertLessEqual(reg["r_squared"], 1)
            self.assertGreaterEqual(reg["pearson_r"], -1)
            self.assertLessEqual(reg["pearson_r"], 1)
            self.assertGreaterEqual(reg["n"], 10)
        # The cumulative-txns leg must stay labelled partial.
        self.assertTrue(m17["price_vs_cumulative_txns_monthly"]["partial"])
        # Dropped rows are only the pre-launch zero-price / zero-user rows.
        self.assertGreater(m17["dropped_rows"]["zero_price_rows"], 0)
        # The rival's reported numbers are recorded as reported, not verified.
        self.assertEqual(m17["rival_reported"]["slope"], 0.21)
        self.assertEqual(m17["rival_reported"]["r_squared"], 0.28)
        # Reading must state the Metcalfe benchmark and the verdict.
        self.assertIn("2.0", m17["reading"])
        self.assertIn("not a stable law", m17["reading"])

    def test_predictions_match_committed(self):
        """M18 thresholds/dates must be the committed PREDICTIONS.md text."""
        committed = json.loads((REPO / "data" / "predictions.json").read_text())
        processed = load_processed("predictions.json")
        self.assertEqual(committed["committed"], "2026-11-10")
        self.assertEqual([p["id"] for p in committed["predictions"]],
                         ["P1", "P2", "P3", "P4", "P5", "P6", "P7"])
        rows = {p["id"]: p for p in processed["predictions"]}
        self.assertEqual(sorted(rows), ["P1", "P2", "P3", "P4", "P5", "P6", "P7"])
        for p in committed["predictions"]:
            row = rows[p["id"]]
            self.assertEqual(row["threshold"], p["threshold"])
            self.assertEqual(row["resolves"], p["resolves"])
            self.assertEqual(row["title"], p["title"])
            # The numeric threshold must be a number that appears in the
            # committed threshold text (P2/P3 are percentages -> /100).
            nums = [float(x.replace(",", ""))
                    for x in re.findall(r"\d[\d,]*\.?\d*", p["threshold"])]
            expected = row["threshold_value"]
            if p["id"] in ("P2", "P3"):
                self.assertIn(expected * 100, nums, p["id"])
            else:
                self.assertIn(expected, nums, p["id"])
            self.assertEqual(row["threshold_op"],
                             ">=" if "≥" in p["threshold"] else "<")

    def test_predictions_live_values_sane(self):
        """M18 live values sane, status consistent, and traced to metrics."""
        m = load_processed("metrics.json")
        processed = load_processed("predictions.json")
        m18 = m["M18_dated_predictions"]
        self.assertTrue(m18.get("available"), m18.get("reason"))
        self.assertEqual(m18["committed"], "2026-11-10")
        self.assertEqual(len(m18["predictions"]), 7)
        self.assertEqual(processed["predictions"], m18["predictions"])
        self.assertEqual(processed["counts"], m18["counts"])
        self.assertEqual(sum(m18["counts"].values()), 7)
        ranges = {
            "P1": (1, 1e9), "P2": (0, 1), "P3": (0, 1), "P4": (1, 1e12),
            "P5": (0, 100), "P6": (0, 1e7), "P7": (0, 1),
        }
        for row in m18["predictions"]:
            self.assertIn(row["status"],
                          ("on track", "off track", "not yet measurable"))
            lv = row["live_value"]
            if lv is None:
                self.assertEqual(row["status"], "not yet measurable")
                self.assertIsNotNone(row["status_reason"])
                continue
            lo, hi = ranges[row["id"]]
            self.assertGreater(lv, lo, row["id"])
            self.assertLess(lv, hi, row["id"])
            if row["threshold_op"] == ">=":
                expect = "on track" if lv >= row["threshold_value"] else "off track"
            else:
                expect = "on track" if lv < row["threshold_value"] else "off track"
            self.assertEqual(row["status"], expect, row["id"])
            self.assertIsNotNone(row["live_value_display"])
        # Live values must agree with the metrics they come from.
        self.assertAlmostEqual(
            m18["predictions"][0]["live_value"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"], delta=0.01)
        self.assertAlmostEqual(
            m18["predictions"][1]["live_value"],
            m["M3_retained_revenue"]["capture_rate_30d_measured"], delta=1e-9)
        dcf = load_processed("dcf.json")
        self.assertAlmostEqual(
            m18["predictions"][2]["live_value"],
            dcf["base_case"]["value_per_token_usd"] / m["snapshot"]["near_price_usd"],
            delta=1e-6)
        self.assertAlmostEqual(
            m18["predictions"][3]["live_value"],
            m["M15_intents_daily_volume"]["total_30d_usd_from_daily_series"],
            delta=1.0)
        bench = load_processed("benchmarks.json")
        self.assertAlmostEqual(
            m18["predictions"][4]["live_value"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"]
            / bench["intents_competitors"]["chainflip"]["fees_30d_usd"],
            delta=1e-6)
        self.assertAlmostEqual(
            m18["predictions"][5]["live_value"],
            m["M13_daily_active_accounts"]["daily_avg_last_30d"], delta=0.01)
        self.assertAlmostEqual(
            m18["predictions"][6]["live_value"],
            abs(m["M16_price_vs_fees_correlation"]
                ["pearson_price_vs_intents_fees_weekly_log_changes"]),
            delta=1e-9)

    def test_falsification_match_committed(self):
        """M19 thresholds must be the committed data/falsification.json text."""
        committed = json.loads((REPO / "data" / "falsification.json").read_text())
        processed = load_processed("falsification.json")
        self.assertEqual(committed["committed"], "2026-11-11")
        self.assertEqual([c["id"] for c in committed["conditions"]],
                         ["F1", "F2", "F3", "F4", "F5", "F6"])
        rows = {c["id"]: c for c in processed["conditions"]}
        self.assertEqual(sorted(rows), ["F1", "F2", "F3", "F4", "F5", "F6"])
        expected_ops = {"F1": "<", "F2": "<", "F3": ">", "F4": "<",
                        "F5": ">=", "F6": "<"}
        for c in committed["conditions"]:
            row = rows[c["id"]]
            self.assertEqual(row["threshold"], c["threshold"])
            self.assertEqual(row["title"], c["title"])
            self.assertEqual(row["persistence"], c["persistence"])
            self.assertEqual(row["threshold_op"], expected_ops[c["id"]])
            # The numeric threshold must be a number that appears in the
            # committed threshold text (F2/F3/F5/F6 are percentages -> /100).
            nums = [float(x.replace(",", ""))
                    for x in re.findall(r"\d[\d,]*\.?\d*", c["threshold"])]
            expected = row["threshold_value"]
            if c["id"] in ("F2", "F3", "F5", "F6"):
                self.assertIn(expected * 100, nums, c["id"])
            else:
                self.assertIn(expected, nums, c["id"])
        # F6 is a two-leg condition: both legs and the fixed peak are stored.
        self.assertEqual(rows["F6"]["threshold_value_secondary"], 0.5)
        self.assertEqual(rows["F6"]["peak_usd"], 8236902.0)
        self.assertIn(8236902.0,
                      [float(x.replace(",", ""))
                       for x in re.findall(r"\d[\d,]*\.?\d*",
                                           committed["conditions"][5]["threshold"])])

    def test_falsification_live_values_sane(self):
        """M19 live values sane, status consistent, and traced to metrics."""
        m = load_processed("metrics.json")
        processed = load_processed("falsification.json")
        m19 = m["M19_falsification"]
        self.assertTrue(m19.get("available"), m19.get("reason"))
        self.assertEqual(m19["committed"], "2026-11-11")
        self.assertEqual(len(m19["conditions"]), 6)
        self.assertEqual(processed["conditions"], m19["conditions"])
        self.assertEqual(processed["counts"], m19["counts"])
        self.assertEqual(sum(m19["counts"].values()), 6)
        ranges = {
            "F1": (1, 1e9), "F2": (0, 1), "F3": (0, 1), "F4": (0, 100),
            "F5": (0, 1), "F6": (0, 1),
        }
        persistence_windows = {"F1": 90, "F2": 90, "F6": 90}
        for row in m19["conditions"]:
            self.assertIn(row["status"],
                          ("triggered", "not triggered", "not yet measurable"))
            # M19 always writes an explanatory reason.
            self.assertIsNotNone(row["status_reason"], row["id"])
            lv = row["live_value"]
            if lv is None:
                self.assertEqual(row["status"], "not yet measurable")
                continue
            lo, hi = ranges[row["id"]]
            self.assertGreater(lv, lo, row["id"])
            self.assertLess(lv, hi, row["id"])
            self.assertIsNotNone(row["live_value_display"])
            op = row["threshold_op"]
            if op == ">=":
                breach = lv >= row["threshold_value"]
            elif op == ">":
                breach = lv > row["threshold_value"]
            else:
                breach = lv < row["threshold_value"]
            if row["id"] == "F6":
                lv2 = row["live_value_secondary"]
                self.assertIsNotNone(lv2, "F6 second leg")
                self.assertGreater(lv2, 0)
                self.assertLess(lv2, 1)
                breach = breach and lv2 < row["threshold_value_secondary"]
            if not breach:
                self.assertEqual(row["status"], "not triggered", row["id"])
                self.assertIsNone(row["breach_since"], row["id"])
                self.assertEqual(row["persistence_days_observed"], 0, row["id"])
            else:
                # A breach only becomes "triggered" once its persistence
                # window is met (F5 has no window; F3 is event-based and
                # cannot trigger from stored data alone).
                if row["id"] == "F5":
                    self.assertEqual(row["status"], "triggered", row["id"])
                elif row["id"] == "F3":
                    self.assertIn(row["status"],
                                  ("triggered", "not triggered"), row["id"])
                elif row["id"] == "F4":
                    expect = ("triggered"
                              if row["persistence_months_observed"] >= 3
                              else "not triggered")
                    self.assertEqual(row["status"], expect, row["id"])
                else:
                    expect = ("triggered"
                              if row["persistence_days_observed"]
                              >= persistence_windows[row["id"]]
                              else "not triggered")
                    self.assertEqual(row["status"], expect, row["id"])
        # Live values must agree with the metrics they come from.
        self.assertAlmostEqual(
            m19["conditions"][0]["live_value"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"], delta=0.01)
        self.assertAlmostEqual(
            m19["conditions"][1]["live_value"],
            m["M3_retained_revenue"]["capture_rate_30d_measured"], delta=1e-9)
        # F3 is the cited outage precedent, not a live series value.
        self.assertAlmostEqual(m19["conditions"][2]["live_value"], 0.316,
                               delta=1e-9)
        self.assertIn("Faultline",
                      [c["source_short"] for c in
                       json.loads((REPO / "data" / "falsification.json")
                                  .read_text())["conditions"]][2])
        bench = load_processed("benchmarks.json")
        self.assertAlmostEqual(
            m19["conditions"][3]["live_value"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"]
            / bench["intents_competitors"]["chainflip"]["fees_30d_usd"],
            delta=1e-6)
        dcf = load_processed("dcf.json")
        self.assertAlmostEqual(
            m19["conditions"][4]["live_value"],
            dcf["base_case"]["value_per_token_usd"] / m["snapshot"]["near_price_usd"],
            delta=1e-6)
        self.assertAlmostEqual(
            m19["conditions"][5]["live_value"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"]
            / m["M2_intents_fee_growth"]["trailing_30d_peak"]["trailing_30d_usd"],
            delta=1e-9)
        # F6 second leg: 30d volume / prior 30d volume, recomputed from the
        # raw DefiLlama dexs daily series (independent of the model).
        dexs = json.loads((RAW / "defillama_dexs_near-intents.json").read_text())
        pts = [float(v) for _, v in dexs["totalDataChart"]]
        self.assertAlmostEqual(
            m19["conditions"][5]["live_value_secondary"],
            sum(pts[-30:]) / sum(pts[-60:-30]), delta=1e-9)

    def test_reverse_dcf_arithmetic(self):
        """Reverse DCF recomputes from its own inputs; capture-alone is
        impossible (>100%) and the 100%-capture ceiling is below price."""
        rev = load_processed("reverse_dcf.json")
        m = load_processed("metrics.json")
        dcf = load_processed("dcf.json")
        inp = rev["inputs"]
        price = m["snapshot"]["near_price_usd"]
        self.assertAlmostEqual(inp["price_usd"], price, delta=1e-9)
        self.assertAlmostEqual(
            inp["capture_rate_30d"],
            m["M3_retained_revenue"]["capture_rate_30d_measured"], delta=1e-9)
        self.assertAlmostEqual(
            inp["f30_trailing_30d_gross_fees_usd"],
            m["M1_intents_gross_fees"]["total_30d_usd_F30"], delta=1.0)
        self.assertAlmostEqual(
            inp["dcf_value_per_token_usd"],
            dcf["base_case"]["value_per_token_usd"], delta=1e-9)
        r, g = inp["discount_rate_r"], inp["growth_rate_g"]
        req_r0 = (price * inp["supply_near"] * (r - g) / (1 + g))
        self.assertAlmostEqual(
            rev["required_r0_annualised_retained_revenue_usd"], req_r0,
            delta=1.0)
        fee_rate = inp["fee_rate_30d_bps"] / 10000.0
        req_vol = req_r0 / inp["capture_rate_30d"] / fee_rate
        self.assertAlmostEqual(
            rev["a_required_annual_gross_volume_usd"], req_vol, delta=1.0)
        req_f30 = req_r0 / 12.0 / inp["capture_rate_30d"]
        self.assertAlmostEqual(
            rev["b_required_30d_gross_fees_usd"], req_f30, delta=1.0)
        req_cap = req_r0 / (inp["f30_trailing_30d_gross_fees_usd"] * 12.0)
        self.assertAlmostEqual(
            rev["c_required_capture_rate_if_volume_flat"], req_cap, delta=1e-9)
        # Both volume and fee multiples are the same number (req R0 / R0).
        self.assertAlmostEqual(
            rev["a_required_multiple_of_current_volume"],
            rev["b_required_multiple_of_current_f30"], delta=0.01)
        self.assertGreater(
            rev["c_required_capture_rate_if_volume_flat"], 1.0,
            "capture alone must be impossible, else the thesis is wrong")
        self.assertFalse(rev["c_feasible"])
        ceil = rev["ceiling_at_100pct_capture_flat_volume"]
        self.assertLess(ceil["value_per_token_usd"], price)
        self.assertLess(ceil["value_per_token_vs_price_pct"], 100.0)

    def test_chart_data_matches_metrics(self):
        m = load_processed("metrics.json")
        c8 = load_processed("chart_08_data.json")
        c9 = load_processed("chart_09_data.json")
        c10 = load_processed("chart_10_data.json")
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
        self.assertTrue(c10.get("available"))
        m17 = m["M17_metcalfe_check"]
        self.assertEqual(len(c10["monthly_users_mean"]), m17["n_months"])
        self.assertEqual(len(c10["monthly_price_month_end"]), m17["n_months"])
        self.assertEqual(len(c10["monthly_cum_txns_month_end"]), m17["n_months"])
        self.assertAlmostEqual(c10["slope_monthly"],
                               m17["price_vs_active_accounts_monthly"]["slope"],
                               delta=1e-9)
        self.assertAlmostEqual(c10["r_squared_monthly"],
                               m17["price_vs_active_accounts_monthly"]["r_squared"],
                               delta=1e-9)


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

    def test_dashboard_renders_predictions(self):
        html_text = (REPO / "dashboard" / "index.html").read_text()
        self.assertIn("Dated predictions", html_text)
        committed = json.loads((REPO / "data" / "predictions.json").read_text())
        for p in committed["predictions"]:
            self.assertIn(p["id"].translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")), html_text, f"{p['id']} missing from dashboard")
            # Thresholds/titles are HTML-escaped when rendered ("<" -> "&lt;").
            self.assertIn(html.escape(p["threshold"]), html_text,
                          f"{p['id']} threshold missing")
            self.assertIn(p["resolves"], html_text, f"{p['id']} resolves date missing")
            self.assertIn(html.escape(p["title"]), html_text,
                          f"{p['id']} title missing")
        processed = load_processed("predictions.json")
        for row in processed["predictions"]:
            if row["live_value_display"]:
                self.assertIn(html.escape(row["live_value_display"]), html_text,
                              f"{row['id']} live value missing")
            self.assertIn(row["status"], html_text, f"{row['id']} status missing")
        # No raw "<" from a threshold may survive into the rendered HTML.
        self.assertNotIn("value/token < 25%", html_text)
        self.assertNotIn("accounts < 100,000", html_text)
        self.assertNotIn("Pearson |r| < 0.30", html_text)

    def test_dashboard_renders_falsification(self):
        html_text = (REPO / "dashboard" / "index.html").read_text()
        self.assertIn("Falsification", html_text)
        committed = json.loads((REPO / "data" / "falsification.json").read_text())
        for c in committed["conditions"]:
            self.assertIn(c["id"].translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")), html_text, f"{c['id']} missing from dashboard")
            # Thresholds/titles are HTML-escaped when rendered ("<" -> "&lt;").
            self.assertIn(html.escape(c["threshold"]), html_text,
                          f"{c['id']} threshold missing")
            self.assertIn(html.escape(c["title"]), html_text,
                          f"{c['id']} title missing")
        processed = load_processed("falsification.json")
        for row in processed["conditions"]:
            if row["live_value_display"]:
                self.assertIn(html.escape(row["live_value_display"]), html_text,
                              f"{row['id']} live value missing")
            if row["live_value_secondary_display"]:
                self.assertIn(html.escape(row["live_value_secondary_display"]),
                              html_text, f"{row['id']} second leg missing")
            self.assertIn(row["status"], html_text, f"{row['id']} status missing")
            self.assertIn(html.escape(row["status_reason"]), html_text,
                          f"{row['id']} status reason missing")
        # No raw "<" from a threshold may survive into the rendered HTML.
        self.assertNotIn("ratio < 1.0", html_text)

    def test_bridge_arithmetic_consistent(self):
        """Bridge components must sum to the rival base case, on both bases."""
        br = load_processed("bridge.json")
        dcf = load_processed("dcf.json")
        sens = load_processed("sensitivity.json")
        b = br["bridge_to_rival_base_usd"]
        pt = br["bridge_per_token_on_rival_supply_basis_usd"]
        # Dollar bridge: ours + chain + residual == rival base total.
        self.assertAlmostEqual(
            b["retained_revenue_dcf"] + b["plus_chain_value"]
            + b["plus_exit_value_and_horizon_difference"],
            b["equals_rival_base_total"], delta=1.0)
        self.assertAlmostEqual(b["gap_usd"],
                               b["equals_rival_base_total"]
                               - b["retained_revenue_dcf"], delta=1.0)
        # Per-token bridge on the rival supply basis sums to the base case.
        self.assertAlmostEqual(
            pt["retained_revenue_dcf"] + pt["plus_chain_value"]
            + pt["plus_exit_value_and_horizon_difference"],
            pt["equals_rival_base"], delta=1e-6)
        # Our side traces to dcf.json.
        self.assertAlmostEqual(b["retained_revenue_dcf"],
                               dcf["base_case"]["equity_value_usd"], delta=1.0)
        self.assertAlmostEqual(
            pt["retained_revenue_dcf"],
            br["our_dcf"]["value_per_token_on_rival_supply_basis_usd"],
            delta=1e-9)
        # Chain value is the majority of the rival base case.
        self.assertGreater(
            br["rival_base_case"]["chain_value_share_of_total_pct"], 50)
        self.assertLess(
            br["rival_base_case"]["chain_value_share_of_total_pct"], 100)
        # Weighted case exceeds the base case.
        self.assertGreater(
            br["rival_weighted_case"]["value_per_token_usd"],
            br["rival_base_case"]["value_per_token_usd"])
        # No sensitivity cell reaches the rival base case (structural gap).
        sens_max = max(c["value_per_token_usd"] for c in sens["grid"]
                       if c["value_per_token_usd"] is not None)
        self.assertAlmostEqual(
            br["sensitivity_grid_max_valid_value_per_token_usd"],
            sens_max, delta=1e-9)
        self.assertLess(sens_max,
                        br["rival_base_case"]["value_per_token_usd"])

    def test_dashboard_renders_bridge(self):
        html_text = (REPO / "dashboard" / "index.html").read_text()
        self.assertIn("The bridge", html_text)
        br = load_processed("bridge.json")
        self.assertIn("NEAR Toll Audit", html_text)
        self.assertIn("swiftbotlab", html_text)
        self.assertIn("$2.05", html_text)
        self.assertIn("$2.91", html_text)
        self.assertIn(br["source_url"], html_text)

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
        # Price-dependent figures: the live price and market cap move with
        # every fetch, so the README must be re-aligned after each refresh
        # (this is what drifted to $3.50 on 2026-11-13 while the price was $3.49).
        price = m["snapshot"]["near_price_usd"]
        mcap = m["snapshot"]["market_cap_usd"]
        self.assertIn(f"${price:,.2f}", readme)
        self.assertIn(f"${mcap / 1e9:.2f}B", readme)
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

    def test_readme_contains_falsification_section(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("Falsification", readme)
        for fid in ("F1", "F2", "F3", "F4", "F5", "F6"):
            self.assertIn(fid.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")),
                          readme, f"{fid} subscript missing from README")
        self.assertIn("$2,000,000", readme)
        self.assertIn("8,236,902", readme)
        self.assertIn("0 triggered, 6 not triggered", readme)
        # The overlap with the dated predictions is stated, not hidden.
        self.assertIn("P₁", readme)
        self.assertIn("P₂", readme)
        self.assertIn("P₅", readme)

    def test_no_hardcoded_dcf_drift(self):
        """README headline DCF value must match dcf.json to 2dp."""
        readme = (REPO / "README.md").read_text()
        dcf = load_processed("dcf.json")
        vpt = dcf["base_case"]["value_per_token_usd"]
        self.assertIn(f"${vpt:.2f}", readme)

    def test_readme_descriptive_figures_match_metrics(self):
        """README descriptive figures (charts #1/#8/#9, Assumptions) must
        match metrics.json — the drift that bit #8/#9 on 2026-11-13."""
        readme = (REPO / "README.md").read_text().replace("−", "-")
        m = load_processed("metrics.json")
        c1 = load_processed("chart_01_data.json")
        m2 = m["M2_intents_fee_growth"]
        m12, m13 = m["M12_daily_txns"], m["M13_daily_active_accounts"]
        m15 = m["M15_intents_daily_volume"]
        # Chart #1 point count.
        self.assertIn(f"({len(c1['dates'])} pts", readme)
        # Chart #8 usage-collapse percentages.
        self.assertIn(f"{m12['current_pct_below_peak']:.1f}%", readme)
        self.assertIn(f"{m13['current_pct_below_peak']:.1f}%", readme)
        # Chart #9 volume + fee rate.
        self.assertIn(
            f"${m15['total_30d_usd_from_daily_series']:,.0f}", readme)
        self.assertIn(
            f"{m15['implied_gross_fee_rate_30d_bps']:.2f} bps", readme)
        # Assumptions: fees vs prior 30d (not volume) + headline volume row.
        self.assertIn(
            f"{m2['trailing_30d_vs_prior_30d_pct']:.1f}%", readme)
        self.assertIn(
            f"{m15['total_30d_vs_prior_30d_pct']:.1f}%", readme)

    def test_dashboard_no_bare_f30(self):
        """Dashboard + docs mirror must use subscripted F₃₀ everywhere —
        no bare 'F30' token in rendered display text."""
        for name in ("dashboard/index.html", "docs/index.html"):
            html = (REPO / name).read_text()
            self.assertNotIn("F30", html, f"bare F30 in {name}")
            self.assertIn("F₃₀", html, f"F₃₀ missing from {name}")

    def test_dashboard_capture_card_matches_metrics(self):
        """Headline capture card must render the M4 windows, not a stale
        hardcoded string (it said 36.0% 30d on 2026-11-13; live is 33.4%)."""
        html = (REPO / "dashboard/index.html").read_text()
        m = load_processed("metrics.json")
        w = m["M4_capture_rate_trend"]["capture_rate_by_window"]
        expected = (f"{w['all_time'] * 100:.1f}% all-time → "
                    f"{w['ytd'] * 100:.1f}% YTD → "
                    f"{w['d30'] * 100:.1f}% 30d")
        self.assertIn(expected, html)
        self.assertNotIn("36.0% 30d", html)

    def test_dashboard_renders_verdict(self):
        """The one-line verdict under the title states the thesis is
        overvalued on retained revenue and cites the live DCF, price,
        break-even multiple and net issuance — all traced to the model."""
        html = (REPO / "dashboard/index.html").read_text()
        m = load_processed("metrics.json")
        dcf = load_processed("dcf.json")
        m6 = m["M6_buyback_vs_issuance"]
        price = m["snapshot"]["near_price_usd"]
        vpt = dcf["base_case"]["value_per_token_usd"]
        self.assertIn("Verdict: overvalued on retained revenue", html)
        self.assertIn(f"${vpt:.2f}", html)
        self.assertIn(f"${price:,.2f}", html)
        self.assertIn(f"{m6['break_even_multiple_of_current_R0']:.1f}", html)
        self.assertIn(f"+{m6['net_supply_change_base_near_per_year']:,.0f} NEAR/yr", html)

    def test_dashboard_no_stale_hardcoded_figures(self):
        """Chart titles/descriptions must render live data, not stale
        hardcoded strings (Chart 7 said $3.60 while the price was $3.50;
        Charts 1/8 said 549 days / 2,303 points — both out of date; the
        reverse-DCF title said $3.51; the growth figure said -0.7% and the
        fee-anomaly date said 9 Nov 2026 — all stale). One legitimate
        exception: the bridge quotes Toll Audit's published $3.60 price,
        which is their constant, not our live price."""
        for name in ("dashboard/index.html", "docs/index.html"):
            html = (REPO / name).read_text()
            self.assertNotIn("what has to be true for $3.60?", html,
                             f"stale Chart 7 price in {name}")
            self.assertNotIn("$3.51", html, f"stale reverse-DCF price in {name}")
            self.assertNotIn("2,303", html, f"stale point count in {name}")
            self.assertNotIn("549 days", html, f"stale day count in {name}")
            self.assertNotIn("9 Nov 2026", html, f"stale anomaly date in {name}")
            self.assertIn("$3.60 needs", html,
                          f"Toll Audit $3.60 quote missing from {name}")
        html = (REPO / "dashboard/index.html").read_text()
        m = load_processed("metrics.json")
        price = m["snapshot"]["near_price_usd"]
        self.assertIn(f"what has to be true for ${price:,.2f}?", html)
        rev = load_processed("reverse_dcf.json")
        self.assertIn(f"${price:,.2f}", rev["title"],
                      "reverse_dcf.json title must carry the live price")
        self.assertNotIn("−0.7%", html, "stale 365d growth figure in dashboard")
        self.assertNotIn("−0.4%", html, "stale 365d growth figure in dashboard")
        self.assertIn(
            f"{m['M2_intents_fee_growth']['log_regression_cagr_last_365d']['cagr'] * 100:+.1f}%/yr",
            html, "dashboard must render the live 365d growth rate")
        c1 = load_processed("chart_01_data.json")
        self.assertIn(f"({len(c1['dates'])} days, log scale)", html)
        m12 = m["M12_daily_txns"]
        self.assertIn(f"{m12['daily_points']:,} daily points", html)


if __name__ == "__main__":
    unittest.main()
