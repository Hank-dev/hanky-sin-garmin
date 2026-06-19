"""Import a Strong app CSV export into the strength tables.

Strong exports one row per *set*, semicolon-delimited. This groups rows into
workouts (one `strength_sessions` row each) and sets (`strength_sets`), mapping
Strong's exercise names onto the app catalog where possible and minting custom
exercises for the rest. IDs are deterministic (`strong-<workout#>[-<n>]`) so a
re-run upserts in place instead of duplicating. Strength analytics in app.py /
analysis.py then work on the imported history with no further changes.

Usage:
    python import_strong.py docs/strong4443032665897967968.csv
    python import_strong.py docs/strong<...>.csv --dry-run
"""

import argparse
import csv
import re
import sys
from datetime import datetime, timedelta

import db

# Strong "Exercise Name" → app catalog exercise_id. Anything not listed here
# (and not force-fit) becomes a custom exercise, described in CUSTOM below.
NAME_TO_ID = {
    "Bench Press (Barbell)": "bench-press",
    "Deadlift (Barbell)": "deadlift",
    "Overhead Press (Barbell)": "overhead-press",
    "Bicep Curl (Barbell)": "barbell-curl",
    "Chin Up": "chin-up",
    "Bent Over Row (Barbell)": "barbell-row",
    "Squat (Barbell)": "back-squat",
    "Trap Bar Deadlift": "trap-bar-deadlift",
    "Hex bar deadlift": "trap-bar-deadlift",        # hex bar == trap bar
    "Triceps Dip": "dip",
    "Chest Dip": "dip",
    "Bicep Curl (Dumbbell)": "dumbbell-curl",
    "Pull Up": "pull-up",
    "Wide Pull Up": "pull-up",                       # grip variation of pull-up
    "Incline Bench Press (Dumbbell)": "incline-dumbbell-press",
    "Incline Bench Press (Barbell)": "incline-bench-press",
    "Seated Row (Cable)": "seated-cable-row",
    "Seated Row (Machine)": "seated-cable-row",
    "Bench Press (Dumbbell)": "dumbbell-bench-press",
    "Chest press dumbell": "dumbbell-bench-press",
    "Lateral Raise (Dumbbell)": "lateral-raise",
    "Triceps Extension": "overhead-tricep-extension",
    "Triceps Extension (Cable)": "tricep-pushdown",
    "Triceps Pushdown (Cable - Straight Bar)": "tricep-pushdown",
    "Lat Pulldown (Cable)": "lat-pulldown",
    "Lat Pulldown (Machine)": "lat-pulldown",
    "Lunge (Dumbbell)": "walking-lunge",
    "Lunge (Barbell)": "walking-lunge",
    "Back Extension": "back-extension",
    "Rygghev": "back-extension",                     # Norwegian: back extension
    "Russian Twist": "russian-twist",
    "Ab Wheel": "ab-wheel-rollout",
    "Skullcrusher (Barbell)": "skullcrusher",
    "Overhead Press (Dumbbell)": "dumbbell-shoulder-press",
    "Over head press kettlebell": "overhead-press",
    "Shoulder Press (Machine)": "machine-shoulder-press",
    "Face Pull (Cable)": "face-pull",
    "Chest Press (Machine)": "machine-chest-press",
    "Chest press 1": "machine-chest-press",
    "Chest Fly": "dumbbell-fly",
    "Chest Fly (Band)": "cable-fly",
    "Plank": "plank",
    "Hip Thrust (Barbell)": "hip-thrust",
    "Preacher Curl (Barbell)": "preacher-curl",
    "Seated Calf Raise (Plate Loaded)": "seated-calf-raise",
    "Standing Calf Raise (Dumbbell)": "standing-calf-raise",
    "Hammer Curl (Dumbbell)": "hammer-curl",
    "Shrug (Barbell)": "barbell-shrug",
    "Shrug (Dumbbell)": "dumbbell-shrug",
    "Push Up": "push-up",
    "Crunch": "sit-up",
    "Hamstring curl": "leg-curl",
    "Lying Leg Curl (Machine)": "leg-curl",
    "Reverse Fly (Dumbbell)": "rear-delt-fly",
    "Front squat kettlebell": "front-squat",
    "Goblet Squat (Kettlebell)": "goblet-squat",
    "Seated Palms Up Wrist Curl (Dumbbell)": "wrist-curl",
    "Barbell wrist curl standing": "wrist-curl",
}

# Implausible source rows (fat-finger entries in the Strong log) are kept
# verbatim but marked completed=0 so the working-set analytics (1RM, volume,
# PRs) skip them. Highest *legit* values in this export are 44 reps / 152 kg;
# the corrupt rows are >=70 reps / 300 kg, so these thresholds isolate them.
MAX_PLAUSIBLE_REPS = 50
MAX_PLAUSIBLE_WEIGHT_KG = 250


def is_implausible(weight_kg: float, reps: int) -> bool:
    return reps > MAX_PLAUSIBLE_REPS or weight_kg > MAX_PLAUSIBLE_WEIGHT_KG


# Genuinely distinct movements with no clean catalog match → custom exercises.
# (exercise_id, name, category, movement_pattern, primary_muscle, unilateral, bodyweight)
CUSTOM = {
    "Bench Press - Wide Grip (Barbell)": (
        "Bench Press - Wide Grip", "barbell", "horizontal_push", "chest", 0, 0),
    "Close grip push up": (
        "Close-Grip Push-up", "bodyweight", "horizontal_push", "triceps", 0, 1),
    "V Up": ("V-Up", "bodyweight", "core", "core", 0, 1),
    "Upright Row (Barbell)": (
        "Upright Row", "barbell", "vertical_pull", "shoulders", 0, 0),
    "Crunch (Machine)": ("Machine Crunch", "machine", "core", "core", 0, 0),
}


def _slug(name: str) -> str:
    return "custom-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def resolve_exercise(name: str) -> str:
    """Return the catalog/custom exercise_id for a Strong exercise name."""
    key = name.strip()
    if key in NAME_TO_ID:
        return NAME_TO_ID[key]
    if key in CUSTOM:
        return _slug(CUSTOM[key][0])
    raise KeyError(f"Unmapped exercise: {name!r}")


def ensure_customs(seen_names, dry_run=False):
    """Create custom exercise rows for any Strong names mapped to CUSTOM."""
    for raw in seen_names:
        spec = CUSTOM.get(raw.strip())
        if not spec:
            continue
        cname, cat, pattern, muscle, uni, bw = spec
        record = {
            "exercise_id": _slug(cname), "name": cname, "category": cat,
            "movement_pattern": pattern, "primary_muscle": muscle,
            "is_unilateral": uni, "is_bodyweight": bw, "is_main_lift": 0,
            "is_custom": 1, "increment_kg": None, "target_reps": None,
        }
        if not dry_run:
            db.upsert_exercise(record)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse(csv_path):
    """Read the CSV into ordered workouts: list of (header, [set-rows])."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    workouts = {}
    order = []
    for row in rows:
        wid = row["Workout #"]
        if wid not in workouts:
            workouts[wid] = []
            order.append(wid)
        workouts[wid].append(row)
    return [(wid, workouts[wid]) for wid in order]


def import_csv(csv_path, dry_run=False):
    workouts = parse(csv_path)
    all_names = {r["Exercise Name"] for _, rows in workouts for r in rows}

    unmapped = [n for n in all_names
                if n.strip() not in NAME_TO_ID and n.strip() not in CUSTOM]
    if unmapped:
        print("ERROR: unmapped exercises (add to NAME_TO_ID or CUSTOM):",
              file=sys.stderr)
        for n in sorted(unmapped):
            print(f"  {n!r}", file=sys.stderr)
        sys.exit(1)

    ensure_customs(all_names, dry_run=dry_run)

    n_sessions = n_sets = n_voided = 0
    for wid, rows in workouts:
        head = rows[0]
        started = head["Date"]
        try:
            start_dt = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start_dt = datetime.fromisoformat(started)
        ended_dt = start_dt + timedelta(seconds=_i(head["Duration (sec)"]))

        session = {
            "session_id": f"strong-{wid}",
            "date": start_dt.date().isoformat(),
            "started_at": start_dt.isoformat(timespec="seconds"),
            "ended_at": ended_dt.isoformat(timespec="seconds"),
            "routine_id": None,
            "name": head["Workout Name"] or "Workout",
            "bodyweight_kg": None,
            "notes": (head.get("Workout Notes") or "").strip() or None,
            "readiness_score": None, "readiness_level": None,
            "hrv_status": None, "hrv_overnight_avg": None,
            "body_battery_start": None, "sleep_score": None,
            "resting_hr": None, "acwr": None,
            "recovery_score": None, "recovery_zone": None,
        }
        if not dry_run:
            db.upsert_strength_session(session)
        n_sessions += 1

        # exercise appearance order within the workout → position
        positions = {}
        for idx, r in enumerate(rows):
            ex_id = resolve_exercise(r["Exercise Name"])
            if ex_id not in positions:
                positions[ex_id] = len(positions)
            rpe = r.get("RPE")
            reps = _i(r["Reps"])
            weight = _f(r["Weight (kg)"])
            voided = is_implausible(weight, reps)
            set_row = {
                "set_id": f"strong-{wid}-{idx}",
                "session_id": f"strong-{wid}",
                "exercise_id": ex_id,
                "position": positions[ex_id],
                "set_index": _i(r["Set Order"]),
                "side": "both",
                "reps": reps,
                "weight_kg": weight,
                "rpe": _f(rpe) if (rpe or "").strip() else None,
                "is_warmup": 0,
                "completed": 0 if voided else 1,
                "logged_at": start_dt.isoformat(timespec="seconds"),
            }
            if not dry_run:
                db.upsert_strength_set(set_row)
            n_sets += 1
            n_voided += voided

    return n_sessions, n_sets, n_voided, all_names


def main():
    ap = argparse.ArgumentParser(description="Import a Strong CSV export.")
    ap.add_argument("csv_path")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and validate mapping without writing to the DB.")
    args = ap.parse_args()

    db.init_db()
    n_sessions, n_sets, n_voided, names = import_csv(args.csv_path,
                                                     dry_run=args.dry_run)
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}{n_sessions} workouts, {n_sets} sets across "
          f"{len(names)} distinct exercises "
          f"({sum(1 for n in names if n.strip() in CUSTOM)} custom). "
          f"{n_voided} implausible sets voided (completed=0).")


if __name__ == "__main__":
    main()
