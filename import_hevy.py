"""Import a Hevy workout into the strength tables.

Fetches the public Hevy workout page, parses exercises/sets, maps them onto
the app catalog, and writes strength_sessions + strength_sets rows. Optionally
links to an existing Garmin strength_training activity if one is found for the
same day.

Usage:
    python import_hevy.py https://hevy.com/workout/<uuid> --workout-date YYYY-MM-DD
    python import_hevy.py https://hevy.com/workout/<uuid> --dry-run --workout-date YYYY-MM-DD

The script is idempotent: re-running the same URL upserts in place.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

import db

HEVY_HOSTS = {"hevy.com", "www.hevy.com"}
HEVY_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
MAX_HEVY_BYTES = 2_000_000

# Hevy exercise name → app catalog exercise_id.
# Keep synchronized with import_strong.py NAME_TO_ID where names overlap.
HEVY_NAME_MAP = {
    "Deadlift (Trap bar)": "trap-bar-deadlift",
    "Trap Bar Deadlift": "trap-bar-deadlift",
    "Deadlift (Barbell)": "deadlift",
    "Deadlift": "deadlift",
    "Squat (Barbell)": "back-squat",
    "Back Squat": "back-squat",
    "Bench Press (Barbell)": "bench-press",
    "Bench Press": "bench-press",
    "Overhead Press (Barbell)": "overhead-press",
    "Overhead Press": "overhead-press",
    "Bicep Curl (Barbell)": "barbell-curl",
    "Bicep Curl (Dumbbell)": "dumbbell-curl",
    "Chin Up": "chin-up",
    "Pull Up": "pull-up",
    "Bent Over Row (Barbell)": "barbell-row",
    "Lunge (Dumbbell)": "walking-lunge",
    "Lying Leg Curl (Machine)": "leg-curl",
    "Hamstring curl": "leg-curl",
    "Standing Calf Raise (Machine)": "standing-calf-raise",
    "Standing Calf Raise (Dumbbell)": "standing-calf-raise",
    "Seated Calf Raise (Plate Loaded)": "seated-calf-raise",
    "Leg Press": "leg-press",
    "Leg Extension": "leg-extension",
    "Hip Thrust (Barbell)": "hip-thrust",
    "Romanian Deadlift": "romanian-deadlift",
    "Goblet Squat (Kettlebell)": "goblet-squat",
    "Lat Pulldown (Cable)": "lat-pulldown",
    "Seated Row (Cable)": "seated-cable-row",
    "Face Pull (Cable)": "face-pull",
    "Lateral Raise (Dumbbell)": "lateral-raise",
    "Triceps Pushdown (Cable)": "tricep-pushdown",
    "Skullcrusher (Barbell)": "skullcrusher",
    "Hammer Curl (Dumbbell)": "hammer-curl",
    "Plank": "plank",
    "Push Up": "push-up",
    "Dip": "dip",
    "Triceps Dip": "dip",
    "Chest Dip": "dip",
    "Barbell Row": "barbell-row",
    "Lat Pulldown (Machine)": "lat-pulldown",
    "Reverse Grip Lat Pulldown (Cable)": "lat-pulldown",
    "Incline Bench Press (Dumbbell)": "incline-dumbbell-press",
    "Bench Press (Dumbbell)": "dumbbell-bench-press",
    "Step Up": "step-up",
    "Step Up Luge Step On Higher Plane": "step-up",
    "Shoulder Press (Dumbbell)": "dumbbell-shoulder-press",
    "Shoulder Press (Machine)": "machine-shoulder-press",
    "Face Pull": "face-pull",
    "Seated Cable Row - V Grip (Cable)": "seated-cable-row",
}


class HevyRedirectError(ValueError):
    pass


class HevyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, expected_uuid: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_uuid = expected_uuid

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _canonical, uuid = validate_hevy_url(newurl)
        except ValueError as exc:
            raise HevyRedirectError(str(exc)) from exc
        if uuid != self.expected_uuid:
            raise HevyRedirectError("Hevy redirect changed workout id")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_hevy_url(url: str) -> tuple[str, str]:
    """Return (canonical https://hevy.com/workout/<uuid>, uuid). Reject SSRF."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Hevy URL must use https")
    if parsed.username or parsed.password:
        raise ValueError("Hevy URL must not include userinfo")
    if parsed.port not in (None, 443):
        raise ValueError("Hevy URL must use port 443")
    host = (parsed.hostname or "").lower()
    if host not in HEVY_HOSTS:
        raise ValueError("Hevy URL host must be hevy.com")
    path = parsed.path.rstrip("/")
    parts = path.split("/")
    if len(parts) != 3 or parts[1] != "workout" or parsed.query or parsed.fragment:
        raise ValueError("Hevy URL must be https://hevy.com/workout/<uuid>")
    workout_uuid = parts[2]
    if not HEVY_UUID_RE.fullmatch(workout_uuid):
        raise ValueError("Hevy workout id must be a UUID")
    canonical = f"https://hevy.com/workout/{workout_uuid.lower()}"
    return canonical, workout_uuid.lower()


def fetch_hevy_page(url: str) -> str:
    canonical, uuid = validate_hevy_url(url)
    req = Request(
        canonical,
        headers={"User-Agent": "Mozilla/5.0 (compatible; HevySync/1.0)"},
    )
    opener = build_opener(HevyRedirectHandler(uuid))
    with opener.open(req, timeout=15) as resp:
        final_url = resp.geturl()
        validate_hevy_url(final_url)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if ctype and not any(
            token in ctype for token in ("text/html", "text/plain", "application/json", "text/")
        ):
            raise ValueError(f"Unexpected Hevy content type: {ctype}")
        blob = resp.read(MAX_HEVY_BYTES + 1)
        if len(blob) > MAX_HEVY_BYTES:
            raise ValueError("Hevy response exceeds size cap")
        return blob.decode("utf-8", errors="replace")


def _slug(name: str) -> str:
    return "custom-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def resolve_exercise(name: str) -> str:
    """Return exercise_id for a Hevy exercise name, creating a custom if needed."""
    key = name.strip()
    if key in HEVY_NAME_MAP:
        return HEVY_NAME_MAP[key]
    lower_map = {k.lower(): v for k, v in HEVY_NAME_MAP.items()}
    if key.lower() in lower_map:
        return lower_map[key.lower()]
    return _slug(key)


def ensure_custom_exercise(name: str, conn=None):
    """Create a custom exercise row if the name isn't in the catalog."""
    ex_id = resolve_exercise(name)
    if not ex_id.startswith("custom-"):
        return
    def _ensure(c):
        existing = c.execute(
            "SELECT exercise_id FROM exercises WHERE exercise_id=?", (ex_id,)
        ).fetchone()
        if existing:
            return
        record = {
            "exercise_id": ex_id,
            "name": name.strip(),
            "category": "machine",
            "movement_pattern": "isolation",
            "primary_muscle": "unknown",
            "is_unilateral": 0,
            "is_bodyweight": 0,
            "is_main_lift": 0,
            "is_custom": 1,
            "increment_kg": None,
            "target_reps": None,
        }
        db.upsert_exercise(record, conn=c)

    if conn is None:
        with db.connect() as c:
            _ensure(c)
    else:
        _ensure(conn)


def _parse_workout_date(html: str) -> str | None:
    for pattern in (
        r'"(?:startTime|workoutDate|date|performedAt)"\s*:\s*"(20\d{2}-\d{2}-\d{2})',
        r"\b(20\d{2}-\d{2}-\d{2})T",
    ):
        match = re.search(pattern, html)
        if match:
            try:
                return date.fromisoformat(match.group(1)).isoformat()
            except ValueError:
                continue
    return None


def parse_hevy_page(html: str):
    """Parse the Hevy workout page HTML into structured data.

    Returns: (workout_name, duration_text, volume_text, exercises, workout_date)
    exercises = [(exercise_name, [(weight_kg, reps), ...]), ...]
    """
    name_match = re.search(r"\*\*(.+?)\\n\\nDuration", html)
    workout_name = name_match.group(1).strip() if name_match else "Workout"

    dur_match = re.search(r"Duration\\n\\n(\d+h \d+m|\d+m)", html)
    duration = dur_match.group(1) if dur_match else None

    vol_match = re.search(r"Volume\\n\\n([\d,]+)\s*kg", html)
    volume = vol_match.group(1) if vol_match else None

    exercises = []
    current_exercise = None
    current_sets = []
    set_pattern = re.compile(r"(\d+(?:\.\d+)?)kg\s*x\s*(\d+)\s*reps")
    lines = html.split("\n")
    in_sets = False

    for line in lines:
        ex_match = re.search(r"#####\s+(.+?)(?:\\n|$)", line)
        if ex_match:
            if current_exercise and current_sets:
                exercises.append((current_exercise, current_sets))
            current_exercise = ex_match.group(1).strip()
            current_sets = []
            in_sets = True
            continue

        if in_sets:
            set_match = set_pattern.search(line)
            if set_match:
                weight = float(set_match.group(1))
                reps = int(set_match.group(2))
                current_sets.append((weight, reps))

    if current_exercise and current_sets:
        exercises.append((current_exercise, current_sets))

    return workout_name, duration, volume, exercises, _parse_workout_date(html)


def _require_workout_date(parsed_date: str | None, workout_date: str | None) -> str:
    raw = workout_date or parsed_date
    if not raw:
        raise ValueError(
            "Workout date not found on the Hevy page. Pass --workout-date YYYY-MM-DD."
        )
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("workout date must be YYYY-MM-DD") from exc


def import_workout(url: str, dry_run: bool = False, workout_date: str | None = None):
    """Fetch and import a Hevy workout. Returns (session_id, n_sets, volume, name)."""
    canonical, workout_uuid = validate_hevy_url(url)
    html = fetch_hevy_page(canonical)
    workout_name, _duration, _volume, exercises, parsed_date = parse_hevy_page(html)

    if not exercises:
        raise ValueError(
            "Could not parse exercises from Hevy page. "
            "The page may be private or require JS rendering."
        )

    session_day = _require_workout_date(parsed_date, workout_date)
    session_id = f"hevy:{workout_uuid}"

    n_sets = 0
    total_volume = 0.0
    set_rows = []
    for position, (ex_name, sets_data) in enumerate(exercises):
        ex_id = resolve_exercise(ex_name)
        for set_idx, (weight, reps) in enumerate(sets_data, 1):
            set_rows.append(
                (
                    ex_name,
                    {
                        "set_id": f"{session_id}:{ex_id}:{position}:{set_idx}",
                        "session_id": session_id,
                        "exercise_id": ex_id,
                        "position": position,
                        "set_index": set_idx,
                        "side": "both",
                        "reps": reps,
                        "weight_kg": weight,
                        "rpe": None,
                        "is_warmup": 0,
                        "completed": 1,
                        "logged_at": f"{session_day}T00:00:00",
                    },
                )
            )
            n_sets += 1
            total_volume += weight * reps

    if dry_run:
        return session_id, n_sets, total_volume, workout_name

    session = {
        "session_id": session_id,
        "date": session_day,
        "started_at": f"{session_day}T00:00:00",
        "ended_at": None,
        "routine_id": None,
        "name": f"{workout_name} (Hevy)",
        "source": "hevy",
        "external_id": workout_uuid,
        "garmin_activity_id": None,
        "workout_type": "strength",
    }

    with db.transaction() as conn:
        seen = set()
        for ex_name, _row in set_rows:
            if ex_name in seen:
                continue
            seen.add(ex_name)
            ensure_custom_exercise(ex_name, conn=conn)
        db.upsert_strength_session(session, conn=conn)
        keep_ids = [row["set_id"] for _name, row in set_rows]
        for _name, row in set_rows:
            db.upsert_strength_set(row, conn=conn)
        if keep_ids:
            placeholders = ",".join("?" for _ in keep_ids)
            conn.execute(
                f"DELETE FROM strength_sets WHERE session_id=? AND set_id NOT IN ({placeholders})",
                [session_id, *keep_ids],
            )
        else:
            conn.execute(
                "DELETE FROM strength_sets WHERE session_id=?",
                (session_id,),
            )

    return session_id, n_sets, total_volume, workout_name


def _activity_local_date(activity) -> str | None:
    import ingest

    for key in ("startTimeLocal", "startTimeGMT", "startTime", "date"):
        raw = ingest.dig(activity, key)
        if not raw:
            continue
        text = str(raw)
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            continue
    return None


def link_garmin_activity(session_id: str, dry_run: bool = False) -> str | None:
    """Sync Garmin activities for the session date, then link an unambiguous
    same-day strength activity. Returns the Garmin activity_id if found.
    """
    import garmin_client
    import ingest

    with db.connect() as conn:
        row = conn.execute(
            "SELECT date FROM strength_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    if not row:
        return None

    sess_date = row["date"]
    client = garmin_client.get_client(interactive=False)

    d = date.fromisoformat(sess_date)
    sync_start = (d - timedelta(days=2)).isoformat()
    sync_end = (d + timedelta(days=1)).isoformat()
    if not dry_run:
        n = ingest.ingest_activities(client, sync_start, sync_end)
        print(f"  Garmin sync: {n} activities pulled for {sync_start} → {sync_end}")

    start = (d - timedelta(days=1)).isoformat()
    end = (d + timedelta(days=1)).isoformat()
    acts = ingest.safe(client.get_activities_by_date, start, end) or []

    matches = []
    for a in acts:
        typ = ingest.dig(a, "activityType.typeKey")
        if typ not in ("strength_training", "fitness_equipment", "training"):
            continue
        act_date = _activity_local_date(a)
        if act_date != sess_date:
            continue
        aid = ingest.dig(a, "activityId")
        if aid is None:
            continue
        matches.append(str(aid))

    if len(matches) != 1:
        if len(matches) > 1:
            print(f"  Ambiguous Garmin strength activities on {sess_date}: {matches}")
        return None

    aid = matches[0]
    if not dry_run:
        with db.connect() as conn:
            conn.execute(
                "UPDATE strength_sessions SET garmin_activity_id=? WHERE session_id=?",
                (aid, session_id),
            )
    return aid


def main():
    ap = argparse.ArgumentParser(description="Import a Hevy workout.")
    ap.add_argument("url", help="Hevy workout URL")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--workout-date",
        help="YYYY-MM-DD. Required when the Hevy page does not include a date.",
    )
    ap.add_argument(
        "--no-link",
        action="store_true",
        help="Skip Garmin activity auto-linking.",
    )
    args = ap.parse_args()

    validate_hevy_url(args.url)
    if not args.dry_run:
        db.init_db()
    session_id, n_sets, volume, name = import_workout(
        args.url, dry_run=args.dry_run, workout_date=args.workout_date
    )
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}Imported: {name}")
    print(f"{tag}{n_sets} sets, {volume:,.0f} kg total volume")
    print(f"{tag}Session ID: {session_id}")

    if not args.no_link:
        garmin_id = link_garmin_activity(session_id, dry_run=args.dry_run)
        if garmin_id:
            print(f"{tag}Linked Garmin activity: {garmin_id}")
        else:
            print(f"{tag}No Garmin activity found yet — will link on next sync.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, URLError, HevyRedirectError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
