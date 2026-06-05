import strength_catalog as sc


REQUIRED = {
    "exercise_id", "name", "category", "movement_pattern",
    "primary_muscle", "is_unilateral", "is_bodyweight", "is_main_lift",
}


def test_exercise_ids_unique():
    ids = [e["exercise_id"] for e in sc.EXERCISE_SEED]
    assert len(ids) == len(set(ids))


def test_every_exercise_has_required_keys_and_valid_pattern():
    for e in sc.EXERCISE_SEED:
        assert REQUIRED <= set(e), e
        assert e["movement_pattern"] in sc.MOVEMENT_PATTERNS, e
        for flag in ("is_unilateral", "is_bodyweight", "is_main_lift"):
            assert e[flag] in (0, 1), e


def test_has_the_main_barbell_lifts():
    ids = {e["exercise_id"] for e in sc.EXERCISE_SEED}
    assert {"back-squat", "bench-press", "deadlift", "overhead-press"} <= ids
