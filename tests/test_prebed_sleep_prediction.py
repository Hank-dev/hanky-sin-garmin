import unittest

import pandas as pd

import analysis


def _prediction_history(days=42):
    start = pd.Timestamp("2026-04-01")
    daily_rows = []
    activity_rows = []
    for i in range(days):
        date = start + pd.Timedelta(days=i)
        hr = 56 + (i % 8) * 2
        stress = 18 + (i % 6) * 8
        load = [0, 20, 45, 70, 95, 30][i % 6]
        score = max(35, min(98, 96 - 1.15 * (hr - 56) - 0.28 * stress - 0.07 * load))
        daily_rows.append({
            "date": date,
            "hr_bedtime": hr,
            "sleep_score": score,
            "sleep_seconds": (7.9 - max(0, 76 - score) / 60.0) * 3600,
            "stress_avg": stress,
            "resting_hr": 54,
            "hrv_overnight_avg": 52,
            "hrv_baseline_low": None,
            "hrv_baseline_high": None,
            "body_battery_current": 82 - stress * 0.4,
        })
        activity_rows.append({
            "date": date,
            "training_load": load,
        })
    return analysis.enrich_daily(pd.DataFrame(daily_rows)), pd.DataFrame(activity_rows)


class PrebedSleepPredictionTest(unittest.TestCase):
    def test_bad_prebed_inputs_predict_lower_sleep_score(self):
        daily, activities = _prediction_history()
        target = pd.Timestamp("2026-05-20")

        good = analysis.compute_prebed_sleep_score_prediction(
            daily,
            activities,
            target_date=target,
            prebed_hr=56,
            stress_avg=20,
            cardio_load=5,
            body_battery_current=85,
            min_training_days=7,
        )
        bad = analysis.compute_prebed_sleep_score_prediction(
            daily,
            activities,
            target_date=target,
            prebed_hr=76,
            stress_avg=70,
            cardio_load=100,
            body_battery_current=35,
            min_training_days=7,
        )

        self.assertIn(good["status"], ("ready", "learning"))
        self.assertGreater(good["prediction"], bad["prediction"])
        self.assertGreaterEqual(good["prediction"] - bad["prediction"], 8)
        self.assertGreaterEqual(good["training_days"], 35)
        self.assertTrue(good["features_used"])

    def test_sparse_sleep_scores_return_learning_status(self):
        daily, activities = _prediction_history(days=4)

        model = analysis.compute_prebed_sleep_score_prediction(
            daily,
            activities,
            prebed_hr=60,
            stress_avg=25,
            min_training_days=7,
        )

        self.assertEqual(model["status"], "learning")
        self.assertLess(model["training_days"], 7)
        self.assertIn("more nights", model["missing"][0])

    def test_target_sleep_score_is_not_used_for_prediction(self):
        daily, activities = _prediction_history(days=28)
        target = daily["date"].max() + pd.Timedelta(days=1)
        leaked = pd.DataFrame([{
            "date": target,
            "hr_bedtime": 56,
            "sleep_score": 20,
            "sleep_seconds": 5 * 3600,
            "stress_avg": 15,
            "resting_hr": 54,
            "hrv_overnight_avg": 52,
            "hrv_baseline_low": None,
            "hrv_baseline_high": None,
            "body_battery_current": 90,
        }])
        with_target = analysis.enrich_daily(pd.concat([daily, leaked], ignore_index=True, sort=False))

        model = analysis.compute_prebed_sleep_score_prediction(
            with_target,
            activities,
            target_date=target,
            prebed_hr=56,
            stress_avg=15,
            cardio_load=0,
            body_battery_current=90,
            min_training_days=7,
        )

        self.assertGreater(model["prediction"], 70)
        self.assertNotEqual(model["prediction"], 20)


if __name__ == "__main__":
    unittest.main()
