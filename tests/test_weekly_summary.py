import os
import tempfile
import unittest

import pandas as pd

import analysis


def _two_week_daily():
    # Prior week Mon–Sun 2026-05-25..05-31, target week Mon–Sun 06-01..06-07,
    # plus a couple of current-week days so "last completed week" = 06-01..06-07.
    dates = pd.date_range("2026-05-25", "2026-06-10", freq="D")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d,
            "hrv_overnight_avg": 40 + (i % 5),
            "resting_hr": 58 + (i % 3),
            "sleep_hours": 7.0 - (i % 3) * 0.5,
            "sleep_debt_h": (i % 3) * 0.5,
            "stress_avg": 30 + (i % 4),
            "body_battery_current": 60 + (i % 5),
            "acwr": 1.0 + (i % 3) * 0.2,
            "hrv_flag": "suppressed" if d.day in (2, 4) else "balanced",
            "rhr_elevated": d.day in (2, 5),
        })
    return pd.DataFrame(rows)


class SummarizeWeekTest(unittest.TestCase):
    def test_selects_last_completed_week_and_aggregates(self):
        daily = _two_week_daily()
        out = analysis.summarize_week(daily, pd.DataFrame(), pd.DataFrame())

        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["week_start"], "2026-06-01")
        self.assertEqual(out["week_end"], "2026-06-07")
        self.assertEqual(out["days_with_data"], 7)
        # HRV avg over 06-01..06-07 is a real number with a delta vs prior week.
        self.assertIsInstance(out["hrv"]["avg"], float)
        self.assertIsInstance(out["hrv"]["delta_vs_prior"], float)
        # Recovery flags: 06-02 suppressed+elevated, 06-04 suppressed, 06-05 elevated.
        self.assertEqual(out["recovery_flags"]["suppressed_days"], 2)
        self.assertEqual(out["recovery_flags"]["rhr_elevated_days"], 2)
        self.assertEqual(out["recovery_flags"]["red_days"], 1)
        self.assertIn(out["notable"]["best_recovery_day"],
                      [d.strftime("%Y-%m-%d") for d in pd.date_range("2026-06-01", "2026-06-07")])

    def test_no_completed_week_when_only_current_week(self):
        daily = pd.DataFrame({
            "date": pd.date_range("2026-06-08", "2026-06-10", freq="D"),  # only current week
            "hrv_overnight_avg": [40, 41, 42],
            "resting_hr": [58, 59, 60],
        })
        out = analysis.summarize_week(daily, pd.DataFrame(), pd.DataFrame())
        self.assertEqual(out["status"], "no_complete_week")

    def test_empty_daily_is_no_complete_week(self):
        out = analysis.summarize_week(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        self.assertEqual(out["status"], "no_complete_week")


if __name__ == "__main__":
    unittest.main()
