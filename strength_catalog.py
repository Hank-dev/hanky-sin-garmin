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
    # ── Squat ───────────────────────────────────────────────────────────────
    _ex("back-squat", "Back Squat", "barbell", "squat", "quads", main=1, increment_kg=2.5, target_reps=5),
    _ex("front-squat", "Front Squat", "barbell", "squat", "quads"),
    _ex("goblet-squat", "Goblet Squat", "dumbbell", "squat", "quads"),
    _ex("hack-squat", "Hack Squat", "machine", "squat", "quads"),
    _ex("leg-press", "Leg Press", "machine", "squat", "quads"),
    _ex("pistol-squat", "Pistol Squat", "bodyweight", "squat", "quads", unilateral=1, bodyweight=1),
    # ── Hinge ───────────────────────────────────────────────────────────────
    _ex("deadlift", "Deadlift", "barbell", "hinge", "hamstrings", main=1, increment_kg=2.5, target_reps=5),
    _ex("sumo-deadlift", "Sumo Deadlift", "barbell", "hinge", "hamstrings"),
    _ex("trap-bar-deadlift", "Trap Bar Deadlift", "barbell", "hinge", "hamstrings"),
    _ex("romanian-deadlift", "Romanian Deadlift", "barbell", "hinge", "hamstrings"),
    _ex("single-leg-rdl", "Single-Leg RDL", "dumbbell", "hinge", "hamstrings", unilateral=1),
    _ex("good-morning", "Good Morning", "barbell", "hinge", "hamstrings"),
    _ex("hip-thrust", "Hip Thrust", "barbell", "hinge", "glutes"),
    _ex("glute-bridge", "Glute Bridge", "bodyweight", "hinge", "glutes", bodyweight=1),
    _ex("kettlebell-swing", "Kettlebell Swing", "dumbbell", "hinge", "glutes"),
    _ex("back-extension", "Back Extension", "bodyweight", "hinge", "lower back", bodyweight=1),
    # ── Horizontal push ───────────────────────────────────────────────────────
    _ex("bench-press", "Bench Press", "barbell", "horizontal_push", "chest", main=1, increment_kg=2.5, target_reps=5),
    _ex("incline-bench-press", "Incline Bench Press", "barbell", "horizontal_push", "chest"),
    _ex("decline-bench-press", "Decline Bench Press", "barbell", "horizontal_push", "chest"),
    _ex("dumbbell-bench-press", "Dumbbell Bench Press", "dumbbell", "horizontal_push", "chest"),
    _ex("incline-dumbbell-press", "Incline Dumbbell Press", "dumbbell", "horizontal_push", "chest"),
    _ex("machine-chest-press", "Machine Chest Press", "machine", "horizontal_push", "chest"),
    _ex("close-grip-bench-press", "Close-Grip Bench Press", "barbell", "horizontal_push", "triceps"),
    _ex("push-up", "Push-up", "bodyweight", "horizontal_push", "chest", bodyweight=1),
    _ex("cable-fly", "Cable Fly", "cable", "isolation", "chest"),
    _ex("dumbbell-fly", "Dumbbell Fly", "dumbbell", "isolation", "chest"),
    _ex("pec-deck", "Pec Deck", "machine", "isolation", "chest"),
    # ── Vertical push ─────────────────────────────────────────────────────────
    _ex("overhead-press", "Overhead Press", "barbell", "vertical_push", "shoulders", main=1, increment_kg=2.5, target_reps=5),
    _ex("push-press", "Push Press", "barbell", "vertical_push", "shoulders"),
    _ex("dumbbell-shoulder-press", "Dumbbell Shoulder Press", "dumbbell", "vertical_push", "shoulders"),
    _ex("arnold-press", "Arnold Press", "dumbbell", "vertical_push", "shoulders"),
    _ex("machine-shoulder-press", "Machine Shoulder Press", "machine", "vertical_push", "shoulders"),
    _ex("dip", "Dip", "bodyweight", "vertical_push", "triceps", bodyweight=1),
    # ── Horizontal pull ───────────────────────────────────────────────────────
    _ex("barbell-row", "Barbell Row", "barbell", "horizontal_pull", "back", main=1, increment_kg=2.5, target_reps=5),
    _ex("pendlay-row", "Pendlay Row", "barbell", "horizontal_pull", "back"),
    _ex("t-bar-row", "T-Bar Row", "barbell", "horizontal_pull", "back"),
    _ex("dumbbell-row", "Dumbbell Row", "dumbbell", "horizontal_pull", "back", unilateral=1),
    _ex("seated-cable-row", "Seated Cable Row", "cable", "horizontal_pull", "back"),
    _ex("chest-supported-row", "Chest-Supported Row", "machine", "horizontal_pull", "back"),
    _ex("inverted-row", "Inverted Row", "bodyweight", "horizontal_pull", "back", bodyweight=1),
    _ex("face-pull", "Face Pull", "cable", "horizontal_pull", "rear delts"),
    # ── Vertical pull ─────────────────────────────────────────────────────────
    _ex("pull-up", "Pull-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("chin-up", "Chin-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("assisted-pull-up", "Assisted Pull-up", "machine", "vertical_pull", "back"),
    _ex("lat-pulldown", "Lat Pulldown", "cable", "vertical_pull", "back"),
    _ex("neutral-grip-pulldown", "Neutral-Grip Pulldown", "cable", "vertical_pull", "back"),
    _ex("straight-arm-pulldown", "Straight-Arm Pulldown", "cable", "isolation", "back"),
    # ── Lunge ───────────────────────────────────────────────────────────────
    _ex("walking-lunge", "Walking Lunge", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("reverse-lunge", "Reverse Lunge", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("bulgarian-split-squat", "Bulgarian Split Squat", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("split-squat", "Split Squat", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("step-up", "Step-up", "dumbbell", "lunge", "quads", unilateral=1),
    # ── Carry ───────────────────────────────────────────────────────────────
    _ex("farmers-carry", "Farmer's Carry", "dumbbell", "carry", "core"),
    _ex("suitcase-carry", "Suitcase Carry", "dumbbell", "carry", "core", unilateral=1),
    # ── Core ────────────────────────────────────────────────────────────────
    _ex("plank", "Plank", "bodyweight", "core", "core", bodyweight=1),
    _ex("side-plank", "Side Plank", "bodyweight", "core", "core", unilateral=1, bodyweight=1),
    _ex("hanging-leg-raise", "Hanging Leg Raise", "bodyweight", "core", "core", bodyweight=1),
    _ex("sit-up", "Sit-up", "bodyweight", "core", "core", bodyweight=1),
    _ex("ab-wheel-rollout", "Ab Wheel Rollout", "bodyweight", "core", "core", bodyweight=1),
    _ex("cable-crunch", "Cable Crunch", "cable", "core", "core"),
    _ex("russian-twist", "Russian Twist", "bodyweight", "core", "core", bodyweight=1),
    _ex("pallof-press", "Pallof Press", "cable", "core", "core", unilateral=1),
    # ── Isolation — arms ──────────────────────────────────────────────────────
    _ex("barbell-curl", "Barbell Curl", "barbell", "isolation", "biceps"),
    _ex("dumbbell-curl", "Dumbbell Curl", "dumbbell", "isolation", "biceps"),
    _ex("hammer-curl", "Hammer Curl", "dumbbell", "isolation", "biceps"),
    _ex("incline-dumbbell-curl", "Incline Dumbbell Curl", "dumbbell", "isolation", "biceps"),
    _ex("preacher-curl", "Preacher Curl", "barbell", "isolation", "biceps"),
    _ex("cable-curl", "Cable Curl", "cable", "isolation", "biceps"),
    _ex("tricep-pushdown", "Tricep Pushdown", "cable", "isolation", "triceps"),
    _ex("overhead-tricep-extension", "Overhead Tricep Extension", "dumbbell", "isolation", "triceps"),
    _ex("skullcrusher", "Skullcrusher", "barbell", "isolation", "triceps"),
    _ex("tricep-kickback", "Tricep Kickback", "dumbbell", "isolation", "triceps"),
    # ── Isolation — shoulders / back / legs ───────────────────────────────────
    _ex("lateral-raise", "Lateral Raise", "dumbbell", "isolation", "shoulders"),
    _ex("cable-lateral-raise", "Cable Lateral Raise", "cable", "isolation", "shoulders"),
    _ex("front-raise", "Front Raise", "dumbbell", "isolation", "shoulders"),
    _ex("rear-delt-fly", "Rear Delt Fly", "dumbbell", "isolation", "rear delts"),
    _ex("reverse-pec-deck", "Reverse Pec Deck", "machine", "isolation", "rear delts"),
    _ex("barbell-shrug", "Barbell Shrug", "barbell", "isolation", "traps"),
    _ex("dumbbell-shrug", "Dumbbell Shrug", "dumbbell", "isolation", "traps"),
    _ex("leg-extension", "Leg Extension", "machine", "isolation", "quads"),
    _ex("leg-curl", "Leg Curl", "machine", "isolation", "hamstrings"),
    _ex("standing-calf-raise", "Standing Calf Raise", "machine", "isolation", "calves"),
    _ex("seated-calf-raise", "Seated Calf Raise", "machine", "isolation", "calves"),
    _ex("wrist-curl", "Wrist Curl", "dumbbell", "isolation", "forearms"),
]
