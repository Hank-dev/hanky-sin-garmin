import unittest

import pandas as pd

import analysis


def activity(name="BJJ open mat", date="2026-06-02", duration_s=3600, avg_hr=145, max_hr=175):
    return pd.DataFrame([{
        "activity_id": "a1",
        "date": date,
        "name": name,
        "type": "cardio",
        "duration_s": duration_s,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "training_load": 100,
    }])


def details(points):
    return {"heartRateValues": points}


def zones(z4_s=0, z5_s=0):
    return {"zones": [
        {"zoneNumber": 4, "durationSeconds": z4_s},
        {"zoneNumber": 5, "durationSeconds": z5_s},
    ]}


class GrapplingAnalysisTest(unittest.TestCase):
    def test_detects_clear_five_round_rolling_session(self):
        pts = []
        t = 0
        for _ in range(5):
            for i in range(20):
                pts.append([t, 164 + (i % 4)])
                t += 15
            for i in range(8):
                pts.append([t, 118 + i])
                t += 15

        sessions = analysis.compute_grappling_sessions(
            pd.DataFrame(),
            activity(duration_s=t),
            {"a1": details(pts)},
            {"a1": zones(600, 300)},
        )

        self.assertEqual(sessions[0]["round_count"], 5)
        self.assertEqual(sessions[0]["classification"], "rolling")
        self.assertEqual(sessions[0]["threshold_source"], "garmin_zones")
        self.assertGreaterEqual(sessions[0]["mat_stress_cost"], 50)

    def test_drilling_session_has_no_rounds(self):
        pts = [[i * 15, 112 + (i % 12)] for i in range(80)]

        sessions = analysis.compute_grappling_sessions(
            pd.DataFrame(),
            activity(name="BJJ drilling", duration_s=1200, avg_hr=118, max_hr=130),
            {"a1": details(pts)},
            {},
        )

        self.assertEqual(sessions[0]["round_count"], 0)
        self.assertEqual(sessions[0]["classification"], "drilling")
        self.assertEqual(sessions[0]["threshold_source"], "session_estimate")

    def test_short_noisy_spikes_do_not_count_as_rounds(self):
        pts = [[i * 15, 112] for i in range(80)]
        pts[20][1] = 182
        pts[50][1] = 176

        sessions = analysis.compute_grappling_sessions(
            pd.DataFrame(),
            activity(name="BJJ noisy strap", duration_s=1200, avg_hr=114, max_hr=182),
            {"a1": details(pts)},
            {},
        )

        self.assertEqual(sessions[0]["round_count"], 0)

    def test_missing_hr_detail_keeps_summary_only(self):
        sessions = analysis.compute_grappling_sessions(
            pd.DataFrame(),
            activity(name="Grappling"),
            {},
            {},
        )

        self.assertEqual(sessions[0]["round_detection"], "unavailable")
        self.assertEqual(sessions[0]["classification"], "summary only")

    def test_next_day_impact_flags_recovery_hit(self):
        pts = []
        t = 0
        for _ in range(3):
            for _ in range(20):
                pts.append([t, 166])
                t += 15
            for _ in range(8):
                pts.append([t, 132])
                t += 15
        daily = pd.DataFrame([{
            "date": pd.Timestamp("2026-06-03"),
            "hrv_flag": "suppressed",
            "rhr_elevated": True,
            "sleep_hours": 5.8,
            "body_battery_current": 25,
            "stress_avg": 68,
        }])

        sessions = analysis.compute_grappling_sessions(
            daily,
            activity(date="2026-06-02", duration_s=t),
            {"a1": details(pts)},
            {"a1": zones(900, 300)},
        )

        self.assertTrue(sessions[0]["next_day"]["available"])
        self.assertIn("HRV suppressed", sessions[0]["next_day"]["flags"])
        self.assertIsNotNone(sessions[0]["warning"])

    def test_next_day_impact_handles_missing_next_day(self):
        sessions = analysis.compute_grappling_sessions(
            pd.DataFrame(),
            activity(date="2026-06-02"),
            {"a1": details([[0, 120], [15, 125], [30, 123]])},
            {},
        )

        self.assertFalse(sessions[0]["next_day"]["available"])


if __name__ == "__main__":
    unittest.main()
