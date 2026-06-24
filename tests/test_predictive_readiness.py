import pandas as pd

import analysis


def _readiness_history(days=46):
    start = pd.Timestamp("2026-04-01")
    loads = [0, 18, 35, 62, 95, 25, 8]
    sleep_hours = [8.0, 7.8, 7.4, 7.1, 6.6, 7.6, 8.1]
    daily_rows = []
    activity_rows = []
    hrv_values = []
    for i in range(days):
        date = start + pd.Timedelta(days=i)
        load = loads[i % len(loads)]
        sleep = sleep_hours[i % len(sleep_hours)]
        prior_load = loads[(i - 1) % len(loads)] if i > 0 else 20
        prior_sleep = sleep_hours[(i - 1) % len(sleep_hours)] if i > 0 else 7.8
        trend = -3 if i % 13 in (10, 11, 12) else 2
        hrv = 55 - 0.13 * prior_load - 2.2 * max(0, 8.0 - prior_sleep) + trend
        hrv_values.append(hrv)
        daily_rows.append({
            "date": date,
            "hrv_overnight_avg": hrv,
            "resting_hr": 52 + (1 if hrv < 45 else 0),
            "sleep_seconds": sleep * 3600,
            "sleep_score": 92 - max(0, 8.0 - sleep) * 9,
            "hrv_baseline_low": None,
            "hrv_baseline_high": None,
        })
        activity_rows.append({
            "activity_id": f"a{i}",
            "date": date,
            "training_load": load,
            "duration_s": 3600,
            "avg_hr": 135,
        })
    return analysis.enrich_daily(pd.DataFrame(daily_rows)), pd.DataFrame(activity_rows)


def test_predictive_readiness_scenarios_and_accuracy():
    daily, activities = _readiness_history()

    model = analysis.compute_predictive_readiness(daily, activities, sleep_need_h=8.0, min_days=14)

    assert model["status"] == "ready"
    assert model["accuracy"]["pairs"] >= 5
    assert model["accuracy"]["mae"] is not None
    assert model["accuracy"]["rmse"] is not None
    by_label = {s["label"]: s for s in model["scenarios"]}
    assert by_label["Hard sparring tonight"]["predicted_hrv"] < by_label["Technique-only"]["predicted_hrv"]
    assert by_label["Hard sparring tonight"]["zone"] in {"suppressed", "balanced", "elevated"}
    assert {f["key"] for f in model["features_used"]} >= {"training_load_today", "hrv_slope_7d"}
    assert model["load_guidance"]["status"] == "ready"
    assert model["load_guidance"]["safe_load"] is not None
    assert model["load_guidance"]["suppression_floor"] is not None


def test_predictive_readiness_learning_with_sparse_history():
    daily, activities = _readiness_history(days=6)

    model = analysis.compute_predictive_readiness(daily, activities, sleep_need_h=8.0, min_days=14)

    assert model["status"] == "learning"
    assert model["accuracy"]["pairs"] == 0
    assert model["scenarios"]
