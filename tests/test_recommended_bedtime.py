import unittest

import pandas as pd

import analysis


def _timing(dates, wake_hour=7, wake_minute=0, bed_hour=23, bed_minute=0):
    rows = []
    for d in dates:
        d = pd.Timestamp(d).normalize()
        sleep_end = d + pd.Timedelta(hours=wake_hour, minutes=wake_minute)
        sleep_start = (d - pd.Timedelta(days=1)) + pd.Timedelta(hours=bed_hour, minutes=bed_minute)
        rows.append({
            "date": d,
            "sleep_start": sleep_start,
            "sleep_end": sleep_end,
            "sleep_midpoint": sleep_start + (sleep_end - sleep_start) / 2,
        })
    return pd.DataFrame(rows)


class RecommendedBedtimeTest(unittest.TestCase):
    def test_anchors_on_wake_time_minus_need_minus_onset_when_no_debt(self):
        dates = pd.date_range("2026-06-01", periods=10, freq="D")
        timing = _timing(dates, wake_hour=7)
        daily = pd.DataFrame({"date": dates, "sleep_debt_h": [0.0] * 10})

        out = analysis.compute_recommended_bedtime(daily, timing, sleep_need_h=8.0)

        self.assertEqual(out["status"], "ready")
        # wake 07:00 (420) - need 480 - onset 15 = -75 => 22:45
        self.assertEqual(out["implied_wake"], "07:00")
        self.assertEqual(out["bedtime_center"], "22:45")
        self.assertEqual(out["debt_pull_min"], 0)

    def test_recent_sleep_debt_pulls_bedtime_earlier_capped(self):
        dates = pd.date_range("2026-06-01", periods=10, freq="D")
        timing = _timing(dates, wake_hour=7)
        # 1.0h recent debt -> 0.25 * 60 = 15 min pull (under the 30 min cap)
        daily = pd.DataFrame({"date": dates, "sleep_debt_h": [1.0] * 10})

        out = analysis.compute_recommended_bedtime(daily, timing, sleep_need_h=8.0)

        self.assertEqual(out["debt_pull_min"], 15)
        # 15 min earlier than the no-debt 22:45
        self.assertEqual(out["bedtime_center"], "22:30")
        self.assertTrue(any("debt" in r.lower() for r in out["reasons"]))

    def test_debt_pull_is_capped(self):
        dates = pd.date_range("2026-06-01", periods=10, freq="D")
        timing = _timing(dates, wake_hour=7)
        daily = pd.DataFrame({"date": dates, "sleep_debt_h": [4.0] * 10})

        out = analysis.compute_recommended_bedtime(daily, timing, sleep_need_h=8.0)

        # 0.25 * 4.0h * 60 = 60 min, capped at 30
        self.assertEqual(out["debt_pull_min"], 30)

    def test_window_is_symmetric_around_center_within_bounds(self):
        dates = pd.date_range("2026-06-01", periods=10, freq="D")
        timing = _timing(dates, wake_hour=7)
        daily = pd.DataFrame({"date": dates, "sleep_debt_h": [0.0] * 10})

        out = analysis.compute_recommended_bedtime(daily, timing, sleep_need_h=8.0)

        self.assertTrue(15 <= out["half_width_min"] <= 40)
        self.assertIn("window_start", out)
        self.assertIn("window_end", out)

    def test_no_data_without_wake_history(self):
        out = analysis.compute_recommended_bedtime(
            pd.DataFrame({"date": [], "sleep_debt_h": []}),
            pd.DataFrame(columns=["date", "sleep_start", "sleep_end", "sleep_midpoint"]),
            sleep_need_h=8.0,
        )
        self.assertEqual(out["status"], "no_data")


if __name__ == "__main__":
    unittest.main()
