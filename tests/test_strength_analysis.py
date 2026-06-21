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


def test_strength_recent_overview_rolls_up_latest_session_and_trends():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "name": "Lower",
         "started_at": "2026-06-01T10:00:00", "ended_at": "2026-06-01T11:00:00",
         "bodyweight_kg": 80, "recovery_score": 70},
        {"session_id": "s2", "date": "2026-06-08", "name": "Lower heavy",
         "started_at": "2026-06-08T10:00:00", "ended_at": "2026-06-08T11:15:00",
         "bodyweight_kg": 80, "recovery_score": 62, "recovery_zone": "yellow"},
    ])
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "set_index": 1, "side": "both", "reps": 5, "weight_kg": 100.0,
         "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s2", "exercise_id": "bench-press",
         "set_index": 1, "side": "both", "reps": 5, "weight_kg": 105.0,
         "is_warmup": 0, "completed": 1},
        {"set_id": "c", "session_id": "s2", "exercise_id": "pull-up",
         "set_index": 1, "side": "both", "reps": 6, "weight_kg": 10.0,
         "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press", "is_bodyweight": 0, "is_unilateral": 0},
        {"exercise_id": "pull-up", "name": "Pull-up", "is_bodyweight": 1, "is_unilateral": 0},
    ])

    out = analysis.compute_strength_recent_overview(sessions, sets, exercises)

    assert out["status"] == "ok"
    assert out["latest_session"]["name"] == "Lower heavy"
    assert out["latest_session"]["duration_min"] == 75
    assert out["latest_summary"]["working_sets"] == 2
    assert out["trend_rows"][-1]["session_id"] == "s2"
    assert out["trend"]["volume_delta_pct"] > 0
    bench = [r for r in out["exercise_rows"] if r["exercise_id"] == "bench-press"][0]
    assert bench["name"] == "Bench Press"
    assert bench["is_pr"] is True
    assert "set_id" not in str(out)


def test_strength_recent_overview_empty():
    out = analysis.compute_strength_recent_overview(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert out["status"] == "no_data"
    assert out["latest_session"] is None


def test_summarize_session_exercises_rolls_up_working_sets_and_prs():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-08", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "position": 0, "set_index": 1, "reps": 5, "weight_kg": 40.0,
         "is_warmup": 1, "completed": 1},
        {"set_id": "b", "session_id": "s1", "exercise_id": "bench-press",
         "position": 0, "set_index": 2, "reps": 5, "weight_kg": 100.0,
         "is_warmup": 0, "completed": 1},
        {"set_id": "c", "session_id": "s1", "exercise_id": "bench-press",
         "position": 0, "set_index": 3, "reps": 3, "weight_kg": 105.0,
         "is_warmup": 0, "completed": 1},
        {"set_id": "d", "session_id": "s2", "exercise_id": "bench-press",
         "position": 0, "set_index": 1, "reps": 5, "weight_kg": 95.0,
         "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press", "is_bodyweight": 0},
    ])

    out = analysis.summarize_session_exercises(sessions, sets, exercises)

    bench_s1 = out[out["session_id"] == "s1"].iloc[0]
    bench_s2 = out[out["session_id"] == "s2"].iloc[0]
    assert bench_s1["name"] == "Bench Press"
    assert bench_s1["working_sets"] == 2
    assert bench_s1["volume_kg"] == 815
    assert bench_s1["best_set"] == "100 kg x 5"
    assert bool(bench_s1["is_pr"]) is True
    assert bool(bench_s2["is_pr"]) is False
    assert "set_id" not in str(out.to_dict("records"))


def test_summarize_session_exercises_can_filter_one_session():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-08", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press",
         "position": 0, "reps": 5, "weight_kg": 100.0,
         "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "pull-up",
         "position": 0, "reps": 5, "weight_kg": 10.0,
         "is_warmup": 0, "completed": 1},
    ])

    out = analysis.summarize_session_exercises(
        sessions, sets, _exercises(), session_id="s2")

    assert list(out["session_id"]) == ["s2"]
    assert list(out["exercise_id"]) == ["pull-up"]


def test_strength_best_set_leaderboard_tracks_records_without_raw_set_ids():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-01-01", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-01", "bodyweight_kg": 80.0},
        {"session_id": "s3", "date": "2026-06-15", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"set_id": "warm", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 120.0, "is_warmup": 1, "completed": 1},
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s2", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "c", "session_id": "s3", "exercise_id": "bench-press",
         "reps": 3, "weight_kg": 110.0, "is_warmup": 0, "completed": 1},
        {"set_id": "miss", "session_id": "s3", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 150.0, "is_warmup": 0, "completed": 0},
        {"set_id": "p", "session_id": "s3", "exercise_id": "pull-up",
         "reps": 5, "weight_kg": 10.0, "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press",
         "movement_pattern": "horizontal_push", "is_bodyweight": 0},
        {"exercise_id": "pull-up", "name": "Pull-up",
         "movement_pattern": "vertical_pull", "is_bodyweight": 1},
    ])

    out = analysis.compute_strength_best_set_leaderboard(
        sessions, sets, exercises, recent_days=10)
    bench = out[out["exercise_id"] == "bench-press"].iloc[0]
    pull = out[out["exercise_id"] == "pull-up"].iloc[0]

    assert bench["name"] == "Bench Press"
    assert bench["best_est_1rm_set"] == "110 kg x 3"
    assert bench["heaviest_set"] == "110 kg x 3"
    assert bench["best_volume_set"] == "100 kg x 5"
    assert bench["recent_best_est_1rm_set"] == "110 kg x 3"
    assert bench["last_pr_date"] == "2026-06-15"
    assert pull["best_est_1rm_set"] == "90 kg x 5"
    assert "set_id" not in str(out.to_dict("records"))


def test_strength_best_set_leaderboard_empty():
    out = analysis.compute_strength_best_set_leaderboard(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert out.empty
    assert "best_est_1rm_kg" in out.columns


def test_weekly_strength_load_groups_patterns_and_excludes_non_work_sets():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-02", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-08", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "barbell-row",
         "reps": 5, "weight_kg": 80.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "deadlift",
         "reps": 5, "weight_kg": 60.0, "is_warmup": 1, "completed": 1},
        {"session_id": "s2", "exercise_id": "deadlift",
         "reps": 3, "weight_kg": 150.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "walking-lunge",
         "reps": 10, "weight_kg": 20.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 110.0, "is_warmup": 0, "completed": 0},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press",
         "movement_pattern": "horizontal_push", "primary_muscle": "chest", "is_bodyweight": 0},
        {"exercise_id": "barbell-row", "name": "Barbell Row",
         "movement_pattern": "horizontal_pull", "primary_muscle": "back", "is_bodyweight": 0},
        {"exercise_id": "deadlift", "name": "Deadlift",
         "movement_pattern": "hinge", "primary_muscle": "hamstrings", "is_bodyweight": 0},
        {"exercise_id": "walking-lunge", "name": "Walking Lunge",
         "movement_pattern": "lunge", "primary_muscle": "quads", "is_bodyweight": 0},
    ])

    out = analysis.compute_weekly_strength_load(sessions, sets, exercises)
    rows = {
        (row["week_start"], row["group"]): row
        for row in out.to_dict("records")
    }

    assert rows[("2026-06-01", "Push")]["total_volume_kg"] == 500
    assert rows[("2026-06-01", "Pull")]["total_volume_kg"] == 400
    assert ("2026-06-01", "Hinge") not in rows
    assert rows[("2026-06-08", "Hinge")]["total_volume_kg"] == 450
    assert rows[("2026-06-08", "Squat")]["total_volume_kg"] == 200


def test_weekly_strength_load_can_group_by_primary_muscle():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-02", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "overhead-press",
         "reps": 5, "weight_kg": 50.0, "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press",
         "movement_pattern": "horizontal_push", "primary_muscle": "chest", "is_bodyweight": 0},
        {"exercise_id": "overhead-press", "name": "Overhead Press",
         "movement_pattern": "vertical_push", "primary_muscle": "shoulders", "is_bodyweight": 0},
    ])

    out = analysis.compute_weekly_strength_load(
        sessions, sets, exercises, group_by="muscle")

    assert set(out["group"]) == {"Chest", "Shoulders"}


def test_strength_momentum_flags_classify_exercise_buckets():
    sessions = pd.DataFrame([
        {"session_id": "b1", "date": "2026-06-15", "bodyweight_kg": 80.0},
        {"session_id": "b2", "date": "2026-06-22", "bodyweight_kg": 80.0},
        {"session_id": "b3", "date": "2026-06-29", "bodyweight_kg": 80.0},
        {"session_id": "s1", "date": "2026-06-08", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-15", "bodyweight_kg": 80.0},
        {"session_id": "s3", "date": "2026-06-22", "bodyweight_kg": 80.0},
        {"session_id": "d1", "date": "2026-06-10", "bodyweight_kg": 80.0},
        {"session_id": "d2", "date": "2026-06-17", "bodyweight_kg": 80.0},
        {"session_id": "d3", "date": "2026-06-24", "bodyweight_kg": 80.0},
        {"session_id": "r1", "date": "2026-05-15", "bodyweight_kg": 80.0},
        {"session_id": "r2", "date": "2026-06-01", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"session_id": "b1", "exercise_id": "bench-press", "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"session_id": "b2", "exercise_id": "bench-press", "reps": 1, "weight_kg": 102.0, "is_warmup": 0, "completed": 1},
        {"session_id": "b3", "exercise_id": "bench-press", "reps": 1, "weight_kg": 105.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "back-squat", "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "back-squat", "reps": 1, "weight_kg": 101.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s3", "exercise_id": "back-squat", "reps": 1, "weight_kg": 100.5, "is_warmup": 0, "completed": 1},
        {"session_id": "d1", "exercise_id": "deadlift", "reps": 1, "weight_kg": 150.0, "is_warmup": 0, "completed": 1},
        {"session_id": "d2", "exercise_id": "deadlift", "reps": 1, "weight_kg": 145.0, "is_warmup": 0, "completed": 1},
        {"session_id": "d3", "exercise_id": "deadlift", "reps": 1, "weight_kg": 140.0, "is_warmup": 0, "completed": 1},
        {"session_id": "r1", "exercise_id": "barbell-row", "reps": 1, "weight_kg": 80.0, "is_warmup": 0, "completed": 1},
        {"session_id": "r2", "exercise_id": "barbell-row", "reps": 1, "weight_kg": 82.5, "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press",
         "movement_pattern": "horizontal_push", "is_bodyweight": 0},
        {"exercise_id": "back-squat", "name": "Back Squat",
         "movement_pattern": "squat", "is_bodyweight": 0},
        {"exercise_id": "deadlift", "name": "Deadlift",
         "movement_pattern": "hinge", "is_bodyweight": 0},
        {"exercise_id": "barbell-row", "name": "Barbell Row",
         "movement_pattern": "horizontal_pull", "is_bodyweight": 0},
    ])

    out = analysis.compute_strength_momentum_flags(
        sessions, sets, exercises, as_of="2026-06-29")
    cats = out["categories"]

    assert out["status"] == "ok"
    assert [item["exercise_id"] for item in cats["progressing"]] == ["bench-press"]
    assert [item["exercise_id"] for item in cats["flat"]] == ["back-squat"]
    assert [item["exercise_id"] for item in cats["regressing"]] == ["deadlift"]
    assert [item["group"] for item in cats["undertrained"]] == ["Pull"]
    assert "exercise_id" not in cats["undertrained"][0]
    assert out["summary"] == {
        "progressing": 1,
        "flat": 1,
        "regressing": 1,
        "undertrained": 1,
    }
    assert "set_id" not in str(out)


def test_strength_momentum_flags_learning_when_no_clear_flags():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-29", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
    ])

    out = analysis.compute_strength_momentum_flags(
        sessions, sets, _exercises(), as_of="2026-06-29")

    assert out["status"] == "learning"
    assert sum(out["summary"].values()) == 0


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


def test_filter_strength_history_sessions_combines_history_filters():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "name": "Upper", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-05", "name": "Lower", "bodyweight_kg": 80.0},
        {"session_id": "s3", "date": "2026-06-10", "name": "Upper", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s2", "exercise_id": "back-squat",
         "reps": 1, "weight_kg": 120.0, "is_warmup": 0, "completed": 1},
        {"set_id": "c", "session_id": "s3", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 95.0, "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press", "is_bodyweight": 0},
        {"exercise_id": "back-squat", "name": "Back Squat", "is_bodyweight": 0},
    ])

    out = analysis.filter_strength_history_sessions(
        sessions,
        sets,
        exercises,
        start_date="2026-06-01",
        end_date="2026-06-10",
        exercise_id="bench-press",
        workout_name="Upper",
        pr_only=True,
    )

    assert list(out["session_id"]) == ["s1"]


def test_filter_strength_history_sessions_searches_exercise_names():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "name": "Upper"},
        {"session_id": "s2", "date": "2026-06-05", "name": "Lower"},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "back-squat",
         "reps": 5, "weight_kg": 120.0, "is_warmup": 0, "completed": 1},
    ])
    exercises = pd.DataFrame([
        {"exercise_id": "bench-press", "name": "Bench Press", "is_bodyweight": 0},
        {"exercise_id": "back-squat", "name": "Back Squat", "is_bodyweight": 0},
    ])

    out = analysis.filter_strength_history_sessions(
        sessions, sets, exercises, query="squat")

    assert list(out["session_id"]) == ["s2"]


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


def test_last_session_sets_picks_most_recent_and_orders():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "started_at": "2026-06-01T10:00"},
        {"session_id": "s2", "date": "2026-06-03", "started_at": "2026-06-03T10:00"},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press", "set_index": 1,
         "weight_kg": 80.0, "reps": 8, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 2,
         "weight_kg": 100.0, "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 1,
         "weight_kg": 90.0, "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 0,
         "weight_kg": 40.0, "reps": 10, "is_warmup": 1, "completed": 1},  # warmup excluded
    ])
    out = analysis.last_session_sets("bench-press", sessions, sets)
    assert out == [{"weight_kg": 90.0, "reps": 5}, {"weight_kg": 100.0, "reps": 5}]


def test_last_session_sets_unlogged_and_empty():
    assert analysis.last_session_sets("squat", pd.DataFrame(), pd.DataFrame()) == []
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-01"}])
    sets = pd.DataFrame([{"session_id": "s1", "exercise_id": "bench-press",
                          "set_index": 1, "weight_kg": 80.0, "reps": 8,
                          "is_warmup": 0, "completed": 1}])
    assert analysis.last_session_sets("deadlift", sessions, sets) == []


def test_last_session_sets_excludes_nan_weight_and_incomplete():
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-01"}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press", "set_index": 1,
         "weight_kg": 100.0, "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bench-press", "set_index": 2,
         "weight_kg": float("nan"), "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bench-press", "set_index": 3,
         "weight_kg": 110.0, "reps": 3, "is_warmup": 0, "completed": 0},  # incomplete
    ])
    out = analysis.last_session_sets("bench-press", sessions, sets)
    assert out == [{"weight_kg": 100.0, "reps": 5}]


def test_readiness_performance_uses_recovery_score():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0}])
    rows, sets = [], []
    for i in range(8):
        sid = f"s{i}"
        rec = 90 if i % 2 == 0 else 40
        w = 105 if rec == 90 else 95
        rows.append({"session_id": sid, "date": f"2026-06-0{i+1}", "bodyweight_kg": 80,
                     "recovery_score": rec, "readiness_score": None,
                     "hrv_overnight_avg": rec, "sleep_score": rec, "resting_hr": 50 if i % 2 == 0 else 55})
        sets.append({"session_id": sid, "exercise_id": "back-squat", "weight_kg": w,
                     "reps": 5, "completed": 1, "is_warmup": 0})
    out = analysis.compute_readiness_performance(pd.DataFrame(rows), pd.DataFrame(sets), ex,
                                                 min_sessions=8)
    assert out["status"] == "ok"
    assert "signals" in out
