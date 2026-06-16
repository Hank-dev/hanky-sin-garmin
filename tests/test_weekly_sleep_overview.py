import unittest

import pandas as pd

import analysis
import cockpit


class WeeklySleepOverviewTest(unittest.TestCase):
    def test_latest_rolling_week_mean_and_sd_bands(self):
        daily = pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=10, freq="D"),
            "sleep_score": [55, 60, 65, 70, 75, 80, 85, 90, 95, 100],
        })

        out = analysis.compute_weekly_sleep_overview(daily)

        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["week_start"], "2026-06-04")
        self.assertEqual(out["week_end"], "2026-06-10")
        self.assertEqual(out["days_with_data"], 7)
        self.assertEqual(out["mean"], 85.0)
        self.assertEqual(out["std"], 10.0)
        self.assertEqual(out["band_1sd_low"], 75.0)
        self.assertEqual(out["band_1sd_high"], 95.0)
        self.assertEqual(out["band_2sd_low"], 65.0)
        # bands are clamped to the 0-100 sleep-score range
        self.assertEqual(out["band_2sd_high"], 100.0)

    def test_calendar_week_keeps_missing_days_as_gaps(self):
        daily = pd.DataFrame({
            "date": ["2026-06-10", "2026-06-12"],
            "sleep_score": [70, 90],
        })

        out = analysis.compute_weekly_sleep_overview(daily, anchor_date="2026-06-13")

        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["days_with_data"], 2)
        self.assertEqual(len(out["rows"]), 7)
        self.assertEqual(out["rows"][0]["date"], "2026-06-07")
        self.assertIsNone(out["rows"][0]["sleep_score"])
        self.assertEqual(out["rows"][3]["sleep_score"], 70.0)
        self.assertEqual(out["rows"][5]["sleep_score"], 90.0)

    def test_no_data_when_sleep_score_missing(self):
        daily = pd.DataFrame({"date": ["2026-06-10"], "stress_avg": [40]})

        out = analysis.compute_weekly_sleep_overview(daily)

        self.assertEqual(out["status"], "no_data")


class WeeklySleepChartTest(unittest.TestCase):
    def test_chart_renders_daily_scores_and_sd_bands(self):
        model = analysis.compute_weekly_sleep_overview(pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=7, freq="D"),
            "sleep_score": [70, 72, 75, 80, 85, 88, 90],
        }))

        fig = cockpit.chart_weekly_sleep_score(model)

        self.assertIn("Daily score", [trace.name for trace in fig.data])
        self.assertIn("Week avg", [trace.name for trace in fig.data])
        self.assertEqual(len([s for s in fig.layout.shapes if s.type == "rect"]), 2)
        self.assertEqual(len([s for s in fig.layout.shapes if s.type == "line"]), 1)
        self.assertEqual(fig.layout.yaxis.title.text, "sleep score")
        self.assertEqual(tuple(fig.layout.yaxis.range), (0, 100))


if __name__ == "__main__":
    unittest.main()
