"""Strength norms for the Phase 2 intelligence layer. Pure data, no imports.

All values are approximate, population-level references (StrengthLevel / ExRx
style) expressed as lift ÷ bodyweight ratios. They are tuning parameters: adjust
here without touching analysis code. No age adjustment (open/adult standards).
"""

LEVELS = ("Untrained", "Novice", "Intermediate", "Advanced", "Elite")

# Percentile band each level maps to (contiguous, 0..100).
LEVEL_PERCENTILE_BANDS = {
    "Untrained": (0, 20),
    "Novice": (20, 50),
    "Intermediate": (50, 80),
    "Advanced": (80, 95),
    "Elite": (95, 100),
}

MAIN_LIFT_NAMES = {
    "back-squat": "Back Squat",
    "bench-press": "Bench Press",
    "deadlift": "Deadlift",
    "overhead-press": "Overhead Press",
    "barbell-row": "Barbell Row",
}

# {sex: {exercise_id: (novice, intermediate, advanced, elite)}} minimum
# lift÷bodyweight ratio to reach each level; below novice = Untrained.
STANDARDS = {
    "male": {
        "back-squat": (0.75, 1.25, 1.75, 2.25),
        "bench-press": (0.5, 1.0, 1.5, 2.0),
        "deadlift": (1.0, 1.5, 2.25, 2.75),
        "overhead-press": (0.35, 0.6, 0.9, 1.2),
        "barbell-row": (0.5, 0.85, 1.15, 1.5),
    },
    "female": {
        "back-squat": (0.5, 0.9, 1.35, 1.8),
        "bench-press": (0.3, 0.6, 0.95, 1.35),
        "deadlift": (0.6, 1.1, 1.6, 2.1),
        "overhead-press": (0.2, 0.4, 0.6, 0.85),
        "barbell-row": (0.3, 0.55, 0.8, 1.1),
    },
}

# Cross-movement strength-ratio targets (numerator 1RM ÷ denominator 1RM).
BALANCE_TARGETS = [
    {"numerator": "bench-press", "denominator": "back-squat",
     "label": "Bench : Squat", "low": 0.5, "ideal": 0.66, "high": 0.8,
     "reason": "upper vs lower push balance"},
    {"numerator": "overhead-press", "denominator": "bench-press",
     "label": "OHP : Bench", "low": 0.5, "ideal": 0.6, "high": 0.7,
     "reason": "vertical vs horizontal push"},
    {"numerator": "barbell-row", "denominator": "bench-press",
     "label": "Row : Bench", "low": 0.8, "ideal": 0.9, "high": 1.05,
     "reason": "horizontal pull vs push"},
    {"numerator": "deadlift", "denominator": "back-squat",
     "label": "Deadlift : Squat", "low": 1.1, "ideal": 1.2, "high": 1.35,
     "reason": "posterior vs anterior chain"},
]

# Flag a unilateral lift when |L-R| / max(L,R) * 100 exceeds this.
ASYMMETRY_FLAG_PCT = 10.0
