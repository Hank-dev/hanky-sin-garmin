import unittest

import pandas as pd

import analysis


def stress_samples(days=6, windows=None):
    windows = windows or []
    rows = []
    start = pd.Timestamp("2026-05-20")
    for day_idx in range(days):
        day = start + pd.Timedelta(days=day_idx)
        for minute in range(8 * 60, 24 * 60, 3):
            value = 24
            for lo, hi, high_value in windows:
                if lo <= minute < hi:
                    value = high_value
                    break
            rows.append({
                "date": day.strftime("%Y-%m-%d"),
                "timestamp": day + pd.Timedelta(minutes=minute),
                "value": value,
            })
    return pd.DataFrame(rows)


def next_day_recovery_flags(days=6):
    start = pd.Timestamp("2026-05-21")
    return pd.DataFrame([
        {
            "date": start + pd.Timedelta(days=i),
            "hrv_flag": "suppressed",
            "rhr_elevated": True,
            "sleep_hours": 5.7,
            "body_battery_current": 28,
            "stress_avg": 64,
        }
        for i in range(days)
    ])


class StressLeakMapTest(unittest.TestCase):
    def test_evening_leak_ranks_above_workday_leak(self):
        stress = stress_samples(
            windows=[
                (10 * 60 + 30, 12 * 60, 66),
                (22 * 60, 24 * 60, 70),
            ]
        )

        model = analysis.compute_stress_leak_map(next_day_recovery_flags(), stress)

        self.assertEqual(model["status"], "ready")
        self.assertIsNotNone(model["top_leak"])
        self.assertEqual(model["top_leak"]["label"], "pre-bed / evening")
        self.assertEqual(model["top_leak"]["time_range"], "22:00-00:00")
        self.assertIn("Highest-impact intervention", model["message"])

    def test_learning_state_before_minimum_days(self):
        stress = stress_samples(days=1, windows=[(22 * 60, 24 * 60, 72)])

        model = analysis.compute_stress_leak_map(pd.DataFrame(), stress, min_days=5)

        self.assertEqual(model["status"], "learning")
        self.assertEqual(model["days_analyzed"], 1)
        self.assertIn("4 more synced days", model["missing"][0])

    def test_low_stress_has_no_clear_leak(self):
        model = analysis.compute_stress_leak_map(
            pd.DataFrame(),
            stress_samples(days=6),
        )

        self.assertEqual(model["status"], "ready")
        self.assertIsNone(model["top_leak"])
        self.assertEqual(model["leaks"], [])

    def test_empty_stress_returns_no_data(self):
        model = analysis.compute_stress_leak_map(pd.DataFrame(), pd.DataFrame())

        self.assertEqual(model["status"], "no_data")
        self.assertEqual(model["leaks"], [])


if __name__ == "__main__":
    unittest.main()
