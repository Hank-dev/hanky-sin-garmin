"""Seed exercise library + movement-pattern vocabulary for the strength logger.

Pure data, no imports. db.seed_exercises() inserts these on init (insert-if-
absent, so user edits to seeded rows are preserved). movement_pattern is stored
now and consumed by the Phase 2 balance/asymmetry analytics.
"""

MOVEMENT_PATTERNS = (
    "squat", "hinge", "horizontal_push", "vertical_push",
    "horizontal_pull", "vertical_pull", "lunge", "carry", "core", "isolation",
)


def _ex(exercise_id, name, category, pattern, muscle,
        unilateral=0, bodyweight=0, main=0, increment_kg=None, target_reps=None):
    return {
        "exercise_id": exercise_id,
        "name": name,
        "category": category,
        "movement_pattern": pattern,
        "primary_muscle": muscle,
        "is_unilateral": unilateral,
        "is_bodyweight": bodyweight,
        "is_main_lift": main,
        "increment_kg": increment_kg,
        "target_reps": target_reps,
    }


EXERCISE_SEED = [
    _ex("back-squat", "Back Squat", "barbell", "squat", "quads", main=1, increment_kg=2.5, target_reps=5),
    _ex("front-squat", "Front Squat", "barbell", "squat", "quads"),
    _ex("leg-press", "Leg Press", "machine", "squat", "quads"),
    _ex("deadlift", "Deadlift", "barbell", "hinge", "hamstrings", main=1, increment_kg=2.5, target_reps=5),
    _ex("romanian-deadlift", "Romanian Deadlift", "barbell", "hinge", "hamstrings"),
    _ex("leg-curl", "Leg Curl", "machine", "isolation", "hamstrings"),
    _ex("bench-press", "Bench Press", "barbell", "horizontal_push", "chest", main=1, increment_kg=2.5, target_reps=5),
    _ex("incline-bench-press", "Incline Bench Press", "barbell", "horizontal_push", "chest"),
    _ex("dumbbell-bench-press", "Dumbbell Bench Press", "dumbbell", "horizontal_push", "chest"),
    _ex("overhead-press", "Overhead Press", "barbell", "vertical_push", "shoulders", main=1, increment_kg=2.5, target_reps=5),
    _ex("dumbbell-shoulder-press", "Dumbbell Shoulder Press", "dumbbell", "vertical_push", "shoulders"),
    _ex("dip", "Dip", "bodyweight", "vertical_push", "triceps", bodyweight=1),
    _ex("barbell-row", "Barbell Row", "barbell", "horizontal_pull", "back", main=1, increment_kg=2.5, target_reps=5),
    _ex("seated-cable-row", "Seated Cable Row", "cable", "horizontal_pull", "back"),
    _ex("pull-up", "Pull-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("chin-up", "Chin-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("lat-pulldown", "Lat Pulldown", "cable", "vertical_pull", "back"),
    _ex("bulgarian-split-squat", "Bulgarian Split Squat", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("walking-lunge", "Walking Lunge", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("barbell-curl", "Barbell Curl", "barbell", "isolation", "biceps"),
    _ex("tricep-pushdown", "Tricep Pushdown", "cable", "isolation", "triceps"),
    _ex("plank", "Plank", "bodyweight", "core", "core", bodyweight=1),
]
