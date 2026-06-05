import importlib
import tempfile

import config
import db


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name           # db.connect() reads this at call time
    importlib.reload(db)                 # rebind db.config.DB_PATH
    db.config.DB_PATH = tmp.name
    db.init_db()
    return tmp.name


def test_seed_is_idempotent_and_preserves_edits():
    _fresh_db()
    db.seed_exercises()
    df = db.load_exercises_df()
    assert "back-squat" in set(df["exercise_id"])
    n = len(df)
    # user edits a seeded row
    db.upsert_exercise({"exercise_id": "back-squat", "name": "My Squat",
                        "category": "barbell", "movement_pattern": "squat",
                        "primary_muscle": "quads", "is_unilateral": 0,
                        "is_bodyweight": 0, "is_main_lift": 1, "is_custom": 0})
    db.seed_exercises()                  # re-seed must not clobber the edit
    df2 = db.load_exercises_df()
    assert len(df2) == n
    row = df2[df2["exercise_id"] == "back-squat"].iloc[0]
    assert row["name"] == "My Squat"


def test_session_and_set_upserts_idempotent():
    _fresh_db()
    db.upsert_strength_session({"session_id": "s1", "date": "2026-06-05",
                                "name": "Push", "bodyweight_kg": 80.0})
    db.upsert_strength_session({"session_id": "s1", "date": "2026-06-05",
                                "name": "Push Day", "bodyweight_kg": 80.0})
    sessions = db.load_strength_sessions_df()
    assert len(sessions) == 1
    assert sessions.iloc[0]["name"] == "Push Day"

    db.upsert_strength_set({"set_id": "x1", "session_id": "s1",
                            "exercise_id": "bench-press", "position": 0,
                            "set_index": 1, "side": "both", "reps": 5,
                            "weight_kg": 100.0, "is_warmup": 0, "completed": 1})
    db.upsert_strength_set({"set_id": "x1", "session_id": "s1",
                            "exercise_id": "bench-press", "position": 0,
                            "set_index": 1, "side": "both", "reps": 6,
                            "weight_kg": 100.0, "is_warmup": 0, "completed": 1})
    sets = db.load_strength_sets_df()
    assert len(sets) == 1
    assert int(sets.iloc[0]["reps"]) == 6


def test_garmin_body_metric_does_not_overwrite_manual():
    _fresh_db()
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 81.0, "source": "manual"})
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 79.0, "source": "garmin"})
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert row["weight_kg"] == 81.0
    assert row["source"] == "manual"
    # but manual can still overwrite
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 80.0, "source": "manual"})
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert row["weight_kg"] == 80.0


def test_routine_exercise_pk_only_record_does_not_crash():
    _fresh_db()
    db.upsert_routine({"routine_id": "r1", "name": "Push"})
    # a record with only the composite PK columns must not raise
    db.upsert_routine_exercise({"routine_id": "r1", "position": 0})
    rex = db.load_routine_exercises_df()
    assert len(rex) == 1
    # a full record on the same PK updates in place
    db.upsert_routine_exercise({"routine_id": "r1", "position": 0,
                                "exercise_id": "bench-press", "target_sets": 3})
    rex = db.load_routine_exercises_df()
    assert len(rex) == 1
    assert rex.iloc[0]["exercise_id"] == "bench-press"


def test_garmin_profile_does_not_overwrite_manual():
    _fresh_db()
    db.upsert_profile({"sex": "male", "birth_year": 1995, "source": "manual"})
    db.upsert_profile({"sex": "female", "birth_year": 1980, "source": "garmin"})
    prof = db.load_profile()
    assert prof["sex"] == "male"
    assert prof["birth_year"] == 1995
    assert prof["source"] == "manual"
    # manual still overwrites manual
    db.upsert_profile({"sex": "male", "birth_year": 1996, "source": "manual"})
    assert db.load_profile()["birth_year"] == 1996
