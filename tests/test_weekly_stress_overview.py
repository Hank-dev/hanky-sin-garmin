import unittest

import pandas as pd

import analysis
import cockpit


class WeeklyStressOverviewTest(unittest.TestCase):
    def test_latest_rolling_week_mean_and_sd_bands(self):
        daily = pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=10, freq="D"),
            "stress_avg": [20, 25, 30, 35, 40, 45, 50, 55, 60, 65],
        })

        out = analysis.compute_weekly_stress_overview(daily)

        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["week_start"], "2026-06-04")
        self.assertEqual(out["week_end"], "2026-06-10")
        self.assertEqual(out["days_with_data"], 7)
        self.assertEqual(out["mean"], 50.0)
        self.assertEqual(out["std"], 10.0)
        self.assertEqual(out["band_1sd_low"], 40.0)
        self.assertEqual(out["band_1sd_high"], 60.0)
        self.assertEqual(out["band_2sd_low"], 30.0)
        self.assertEqual(out["band_2sd_high"], 70.0)

    def test_calendar_week_keeps_missing_days_as_gaps(self):
        daily = pd.DataFrame({
            "date": ["2026-06-10", "2026-06-12"],
            "stress_avg": [30, 50],
        })

        out = analysis.compute_weekly_stress_overview(daily, anchor_date="2026-06-13")

        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["days_with_data"], 2)
        self.assertEqual(len(out["rows"]), 7)
        self.assertEqual(out["rows"][0]["date"], "2026-06-07")
        self.assertIsNone(out["rows"][0]["stress_avg"])
        self.assertEqual(out["rows"][3]["stress_avg"], 30.0)
        self.assertEqual(out["rows"][5]["stress_avg"], 50.0)


class WeeklyStressChartTest(unittest.TestCase):
    def test_chart_renders_daily_stress_and_sd_bands(self):
        model = analysis.compute_weekly_stress_overview(pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=7, freq="D"),
            "stress_avg": [30, 35, 40, 45, 50, 55, 60],
        }))

        fig = cockpit.chart_weekly_stress_overview(model)

        self.assertIn("Daily avg", [trace.name for trace in fig.data])
        self.assertIn("Week avg", [trace.name for trace in fig.data])
        self.assertEqual(len([shape for shape in fig.layout.shapes if shape.type == "rect"]), 2)
        self.assertEqual(len([shape for shape in fig.layout.shapes if shape.type == "line"]), 1)
        self.assertEqual(fig.layout.yaxis.title.text, "avg stress")


if __name__ == "__main__":
    unittest.main()
