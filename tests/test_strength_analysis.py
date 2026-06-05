import math

import pandas as pd

import analysis


def _exercises():
    return pd.DataFrame([
        {"exercise_id": "bench-press", "is_bodyweight": 0},
        {"exercise_id": "pull-up", "is_bodyweight": 1},
    ])


def _sessions(bodyweight=80.0):
    return pd.DataFrame([{"session_id": "s1", "date": "2026-06-05",
                          "bodyweight_kg": bodyweight}])


# estimate_1rm
def test_estimate_1rm_single_rep_is_weight():
    assert analysis.estimate_1rm(100, 1) == 100


def test_estimate_1rm_epley():
    assert math.isclose(analysis.estimate_1rm(100, 5), 100 * (1 + 5 / 30))


def test_estimate_1rm_brzycki():
    assert math.isclose(analysis.estimate_1rm(100, 5, "brzycki"), 112.5)


def test_estimate_1rm_invalid_returns_none():
    assert analysis.estimate_1rm(100, 0) is None
    assert analysis.estimate_1rm(0, 5) is None
    assert analysis.estimate_1rm(None, 5) is None
    assert analysis.estimate_1rm(100, None) is None


# enrich_strength_sets
def test_enrich_adds_effective_load_and_1rm():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s1", "exercise_id": "pull-up",
         "reps": 5, "weight_kg": 10.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.enrich_strength_sets(sets, _sessions(), _exercises())
    bench = out[out["exercise_id"] == "bench-press"].iloc[0]
    pull = out[out["exercise_id"] == "pull-up"].iloc[0]
    assert bench["effective_load_kg"] == 100.0
    assert pull["effective_load_kg"] == 90.0   # 80 bodyweight + 10 added
    assert bench["est_1rm_kg"] > 100


def test_enrich_warmup_has_no_1rm():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 10, "weight_kg": 40.0, "is_warmup": 1, "completed": 1},
    ])
    out = analysis.enrich_strength_sets(sets, _sessions(), _exercises())
    assert pd.isna(out.iloc[0]["est_1rm_kg"])


def test_enrich_empty_returns_empty_with_columns():
    out = analysis.enrich_strength_sets(pd.DataFrame(), _sessions(), _exercises())
    assert out.empty
    assert "effective_load_kg" in out.columns
    assert "est_1rm_kg" in out.columns


# summarize_sessions
def test_summarize_sessions_tonnage_and_top():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 60.0, "is_warmup": 1, "completed": 1},  # warmup excluded
    ])
    out = analysis.summarize_sessions(_sessions(), sets, _exercises())
    row = out.iloc[0]
    assert row["working_sets"] == 1
    assert row["total_volume_kg"] == 500.0     # 5 * 100 (warmup excluded)
    assert row["top_est_1rm_kg"] > 100


def test_summarize_sessions_empty():
    out = analysis.summarize_sessions(pd.DataFrame(), pd.DataFrame(), _exercises())
    assert out.empty


# compute_pr_timeline
def test_pr_timeline_flags_new_records():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-03", "bodyweight_kg": 80.0},
        {"session_id": "s3", "date": "2026-06-05", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s2", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 95.0, "is_warmup": 0, "completed": 1},   # not a PR
        {"set_id": "c", "session_id": "s3", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 105.0, "is_warmup": 0, "completed": 1},  # PR
    ])
    out = analysis.compute_pr_timeline(sets, sessions, _exercises()).sort_values("date")
    flags = list(out["is_pr"])
    assert flags == [True, False, True]


# readiness_snapshot_from_daily
def test_readiness_snapshot_maps_fields():
    row = pd.Series({
        "training_readiness_score": 72,
        "training_readiness_level": "READY",
        "hrv_status": "BALANCED",
        "hrv_overnight_avg": 58,
        "body_battery_start": 84,
        "sleep_score": 80,
        "resting_hr": 48,
        "acwr": 1.1,
    })
    snap = analysis.readiness_snapshot_from_daily(row)
    assert snap["readiness_score"] == 72
    assert snap["readiness_level"] == "READY"
    assert snap["acwr"] == 1.1


def test_readiness_snapshot_handles_none_and_nan():
    snap = analysis.readiness_snapshot_from_daily(None)
    assert snap["readiness_score"] is None
    row = pd.Series({"training_readiness_score": float("nan")})
    assert analysis.readiness_snapshot_from_daily(row)["readiness_score"] is None


def test_enrich_none_sets_returns_empty_with_columns():
    out = analysis.enrich_strength_sets(None, _sessions(), _exercises())
    assert out.empty
    assert "effective_load_kg" in out.columns
    assert "est_1rm_kg" in out.columns


def test_summarize_handles_sets_missing_completed_column():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0},  # no 'completed' column
    ])
    out = analysis.summarize_sessions(_sessions(), sets, _exercises())
    row = out.iloc[0]
    assert row["working_sets"] == 1
    assert row["total_volume_kg"] == 500.0
