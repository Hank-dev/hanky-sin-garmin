import unittest

import pandas as pd

import cockpit


class ChartRenderingTest(unittest.TestCase):
    def test_hrv_chart_single_point_uses_marker(self):
        view = pd.DataFrame([{
            "date": "2026-06-04",
            "hrv_overnight_avg": 43,
        }])

        fig = cockpit.chart_hrv(view, (None, None))

        self.assertIn("lines+markers", [trace.mode for trace in fig.data])

    def test_bedtime_hr_chart_single_point_uses_marker(self):
        view = pd.DataFrame([{
            "date": "2026-06-04",
            "hr_bedtime": 65,
        }])

        fig = cockpit.chart_bedtime_hr(view)

        self.assertIn("lines+markers", [trace.mode for trace in fig.data])

    def test_body_battery_and_stress_tiles_are_number_only(self):
        html = cockpit.tiles(
            {"hrv": 43, "rhr": 59, "sleep_h": 7.1, "acwr": 1.0, "batt": 72, "stress": 31},
            {"hrv": [40, 43], "rhr": [61, 59], "sleep_h": [6.8, 7.1], "acwr": [1.0, 1.0], "batt": [50, 72], "stress": [38, 31]},
            {"hrv": 42, "rhr": 60, "sleep_h": 7.0, "batt": 60, "stress": 35},
            sparse=False,
        )

        start = html.index("Body Battery")
        end = html.index("Stress", start)
        battery_block = html[start:end]
        self.assertIn(">72<", battery_block)
        self.assertNotIn("spark", battery_block)
        self.assertNotIn("vs 28d", battery_block)

        stress_block = html[html.index("Stress"):]
        self.assertIn(">31<", stress_block)
        self.assertNotIn("spark", stress_block)
        self.assertNotIn("vs 28d", stress_block)


if __name__ == "__main__":
    unittest.main()
