import unittest

import pandas as pd

import cockpit


class DayRailTest(unittest.TestCase):
    def test_day_rail_renders_selected_day_and_activity_badges(self):
        days = pd.DataFrame([{
            "date": "2026-06-03",
            "sleep_hours": 6.2,
            "hrv_flag": "suppressed",
            "resting_hr": 58,
            "rhr_elevated": True,
            "stress_avg": 55,
            "body_battery_start": 70,
            "body_battery_end": 30,
            "steps": 4200,
        }])
        activities = pd.DataFrame([{
            "date": "2026-06-03",
            "name": "BJJ open mat",
            "type": "cardio",
        }])

        html = cockpit.day_rail(days, activities, "2026-06-03")

        self.assertIn("day-card", html)
        self.assertIn("selected", html)
        self.assertIn("BJJ", html)
        self.assertIn("?day=2026-06-03", html)


if __name__ == "__main__":
    unittest.main()
