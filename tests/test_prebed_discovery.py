import unittest

import pandas as pd

import analysis
import cockpit


class PrebedDiscoveryTest(unittest.TestCase):
    def test_prebed_hr_links_to_same_night_sleep_and_next_day_stress(self):
        start = pd.Timestamp("2026-05-01")
        rows = []
        for i in range(8):
            high = i >= 4
            rows.append({
                "date": start + pd.Timedelta(days=i),
                "hr_bedtime": 72 if high else 58,
                "sleep_score": 62 if high else 86,
                "sleep_seconds": (6.1 if high else 8.0) * 3600,
                "stress_avg": 55 if high else 25,
                "resting_hr": 55,
                "hrv_overnight_avg": 45,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        daily = analysis.enrich_daily(pd.DataFrame(rows))

        model = analysis.compute_prebed_discovery(daily, min_pairs=5)

        self.assertEqual(model["status"], "ready")
        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        self.assertLess(by_pair[("hr_bedtime", "sleep_score")]["correlation"], 0)
        self.assertGreater(by_pair[("hr_bedtime", "next_day_stress")]["correlation"], 0)
        self.assertEqual(by_pair[("hr_bedtime", "next_day_stress")]["pairs"], 7)
        self.assertIn("Strongest correlation pattern", model["message"])

    def test_overnight_hrv_links_to_next_day_stress(self):
        start = pd.Timestamp("2026-05-01")
        rows = []
        for i in range(8):
            high_hrv = i < 4
            rows.append({
                "date": start + pd.Timedelta(days=i),
                "hrv_overnight_avg": 62 if high_hrv else 38,
                "stress_avg": 25 if high_hrv else 58,
                "sleep_seconds": None,
                "resting_hr": 55,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        daily = analysis.enrich_daily(pd.DataFrame(rows))

        model = analysis.compute_prebed_discovery(daily, min_pairs=5)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        rel = by_pair[("hrv_overnight_avg", "next_day_stress")]
        self.assertLess(rel["correlation"], 0)
        self.assertEqual(rel["pairs"], 7)

    def test_cardio_load_links_to_next_day_stress(self):
        start = pd.Timestamp("2026-05-01")
        daily_rows = []
        activity_rows = []
        loads = [20, 20, 20, 20, 95, 95, 95, 95]
        for i in range(9):
            prev_load = loads[i - 1] if i > 0 else 20
            daily_rows.append({
                "date": start + pd.Timedelta(days=i),
                "hrv_overnight_avg": 45,
                "stress_avg": 62 if prev_load >= 90 else 24,
                "sleep_seconds": None,
                "resting_hr": 55,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        for i, load in enumerate(loads):
            activity_rows.append({
                "date": start + pd.Timedelta(days=i),
                "training_load": load,
            })
        daily = analysis.enrich_daily(pd.DataFrame(daily_rows))
        activities = pd.DataFrame(activity_rows)

        model = analysis.compute_prebed_discovery(daily, activities, min_pairs=5)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        rel = by_pair[("cardio_load", "next_day_stress")]
        self.assertGreater(rel["correlation"], 0)
        self.assertEqual(rel["pairs"], 8)

    def test_cardio_load_falls_back_to_duration_and_avg_hr(self):
        start = pd.Timestamp("2026-05-01")
        daily_rows = []
        activity_rows = []
        avg_hrs = [105, 106, 107, 108, 155, 156, 157, 158]
        for i in range(9):
            prev_high = i > 0 and avg_hrs[i - 1] >= 150
            daily_rows.append({
                "date": start + pd.Timedelta(days=i),
                "hrv_overnight_avg": 45,
                "stress_avg": 64 if prev_high else 22,
                "sleep_seconds": None,
                "resting_hr": 55,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        for i, avg_hr in enumerate(avg_hrs):
            activity_rows.append({
                "date": start + pd.Timedelta(days=i),
                "duration_s": 3600,
                "avg_hr": avg_hr,
            })
        daily = analysis.enrich_daily(pd.DataFrame(daily_rows))
        activities = pd.DataFrame(activity_rows)

        model = analysis.compute_prebed_discovery(daily, activities, min_pairs=5)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        self.assertGreater(by_pair[("cardio_load", "next_day_stress")]["correlation"], 0)

    def test_bedtime_hr_delta_links_to_sleep_quality_hrv_and_resting_hr(self):
        start = pd.Timestamp("2026-05-01")
        rows = []
        for i in range(10):
            elevated = i >= 5
            rows.append({
                "date": start + pd.Timedelta(days=i),
                "hr_bedtime": 72 if elevated else 58,
                "sleep_score": 60 if elevated else 88,
                "hrv_overnight_avg": 35 if elevated else 55,
                "resting_hr": 64 if elevated else 52,
                "stress_avg": 30,
                "sleep_seconds": 8 * 3600,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        daily = analysis.enrich_daily(pd.DataFrame(rows))

        model = analysis.compute_prebed_discovery(daily, min_pairs=3)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        self.assertLess(by_pair[("bedtime_hr_delta", "sleep_score")]["correlation"], 0)
        self.assertLess(by_pair[("bedtime_hr_delta", "hrv_overnight_avg")]["correlation"], 0)
        self.assertGreater(by_pair[("bedtime_hr_delta", "resting_hr")]["correlation"], 0)

    def test_sleep_midpoint_variability_links_to_next_day_stress(self):
        start = pd.Timestamp("2026-05-01")
        daily_rows = []
        timing_rows = []
        offsets = [0, 5, 10, 15, 80, 100, 120, 140, 150]
        for i, offset in enumerate(offsets):
            daily_rows.append({
                "date": start + pd.Timedelta(days=i),
                "hrv_overnight_avg": 60 - i,
                "stress_avg": 25 + i * 3,
                "sleep_seconds": 8 * 3600,
                "resting_hr": 55,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
            sleep_start = start + pd.Timedelta(days=i, hours=23, minutes=offset)
            sleep_end = sleep_start + pd.Timedelta(hours=8)
            timing_rows.append({
                "date": start + pd.Timedelta(days=i),
                "sleep_start": sleep_start,
                "sleep_end": sleep_end,
                "sleep_midpoint": sleep_start + pd.Timedelta(hours=4),
            })
        daily = analysis.enrich_daily(pd.DataFrame(daily_rows))
        sleep_timing = pd.DataFrame(timing_rows)

        model = analysis.compute_prebed_discovery(daily, sleep_timing=sleep_timing, min_pairs=3)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        self.assertIn(("sleep_midpoint_variability_7d", "next_day_stress"), by_pair)
        self.assertGreater(by_pair[("sleep_midpoint_variability_7d", "next_day_stress")]["pairs"], 0)

    def test_activity_bucket_relationships_are_added(self):
        start = pd.Timestamp("2026-05-01")
        daily_rows = []
        activity_rows = []
        loads = [5, 20, 35, 50, 90, 5, 20, 35, 50, 90]
        for i in range(11):
            prev = loads[i - 1] if i > 0 else 20
            daily_rows.append({
                "date": start + pd.Timedelta(days=i),
                "hrv_overnight_avg": 62 if 20 <= prev <= 50 else 45,
                "stress_avg": 26 if 20 <= prev <= 50 else 58,
                "body_battery_start": 70 if 20 <= prev <= 50 else 45,
                "body_battery_low": 30,
                "sleep_seconds": 8 * 3600,
                "resting_hr": 55,
                "hrv_baseline_low": None,
                "hrv_baseline_high": None,
            })
        for i, load in enumerate(loads):
            activity_rows.append({
                "date": start + pd.Timedelta(days=i),
                "training_load": load,
            })
        daily = analysis.enrich_daily(pd.DataFrame(daily_rows))
        activities = pd.DataFrame(activity_rows)

        model = analysis.compute_prebed_discovery(daily, activities, min_pairs=3)

        by_pair = {(r["x_col"], r["y_col"]): r for r in model["relationships"]}
        self.assertIn(("activity_bucket_code", "next_day_stress"), by_pair)
        self.assertIn(("activity_bucket_code", "next_day_hrv"), by_pair)
        self.assertIn(("activity_bucket_code", "next_day_body_battery_recharge"), by_pair)

    def test_discovery_chart_renders_marker_points(self):
        model = {
            "relationships": [{
                "y_col": "next_day_stress",
                "y_label": "Next-day avg stress",
                "rows": [
                    {"date": "2026-05-01", "prebed_hr": 58, "value": 25},
                    {"date": "2026-05-02", "prebed_hr": 72, "value": 55},
                ],
            }],
        }

        fig = cockpit.chart_prebed_relationship(model, "next_day_stress")

        self.assertIn("markers", [trace.mode for trace in fig.data])


if __name__ == "__main__":
    unittest.main()
