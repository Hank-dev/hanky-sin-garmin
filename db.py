"""SQLite persistence. Idempotent upserts keyed on date / activity id."""
import sqlite3
import json
from datetime import datetime, timezone
from contextlib import contextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    resting_hr REAL,
    hr_overnight_low REAL,
    hr_bedtime REAL,
    hrv_overnight_avg REAL,
    hrv_weekly_avg REAL,
    hrv_status TEXT,
    hrv_baseline_low REAL,
    hrv_baseline_high REAL,
    sleep_seconds REAL,
    deep_seconds REAL,
    light_seconds REAL,
    rem_seconds REAL,
    awake_seconds REAL,
    sleep_score REAL,
    body_battery_high REAL,
    body_battery_low REAL,
    body_battery_start REAL,
    body_battery_current REAL,
    stress_avg REAL,
    stress_high_minutes REAL,
    stress_total_minutes REAL,
    steps REAL,
    intensity_minutes REAL,
    vo2max REAL,
    spo2_avg REAL,
    respiration_avg REAL,
    training_readiness_score REAL,
    training_readiness_level TEXT,
    training_status TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    date TEXT,
    name TEXT,
    type TEXT,
    duration_s REAL,
    distance_m REAL,
    avg_hr REAL,
    max_hr REAL,
    training_load REAL,
    aerobic_te REAL,
    anaerobic_te REAL
);

CREATE TABLE IF NOT EXISTS raw_json (
    date TEXT,
    endpoint TEXT,
    payload TEXT,
    PRIMARY KEY (date, endpoint)
);

CREATE TABLE IF NOT EXISTS daily_checkins (
    date TEXT PRIMARY KEY,
    pain INTEGER,
    fatigue INTEGER,
    energy INTEGER,
    note TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_summaries (
    week_start TEXT PRIMARY KEY,
    generated_at TEXT,
    model TEXT,
    summary_md TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    exercise_id TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    movement_pattern TEXT,
    primary_muscle TEXT,
    is_unilateral INTEGER DEFAULT 0,
    is_bodyweight INTEGER DEFAULT 0,
    is_main_lift INTEGER DEFAULT 0,
    is_custom INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routines (
    routine_id TEXT PRIMARY KEY,
    name TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routine_exercises (
    routine_id TEXT,
    position INTEGER,
    exercise_id TEXT,
    target_sets INTEGER,
    target_reps INTEGER,
    target_weight REAL,
    PRIMARY KEY (routine_id, position)
);

CREATE TABLE IF NOT EXISTS strength_sessions (
    session_id TEXT PRIMARY KEY,
    date TEXT,
    started_at TEXT,
    ended_at TEXT,
    routine_id TEXT,
    name TEXT,
    bodyweight_kg REAL,
    notes TEXT,
    readiness_score REAL,
    readiness_level TEXT,
    hrv_status TEXT,
    hrv_overnight_avg REAL,
    body_battery_start REAL,
    sleep_score REAL,
    resting_hr REAL,
    acwr REAL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strength_sets (
    set_id TEXT PRIMARY KEY,
    session_id TEXT,
    exercise_id TEXT,
    position INTEGER,
    set_index INTEGER,
    side TEXT DEFAULT 'both',
    reps INTEGER,
    weight_kg REAL,
    rpe REAL,
    is_warmup INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 1,
    logged_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS body_metrics (
    date TEXT PRIMARY KEY,
    weight_kg REAL,
    bmi REAL,
    body_fat_pct REAL,
    muscle_mass_kg REAL,
    body_water_pct REAL,
    bone_mass_kg REAL,
    source TEXT DEFAULT 'garmin',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY,
    sex TEXT,
    birth_year INTEGER,
    height_cm REAL,
    source TEXT DEFAULT 'garmin',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coach_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL,
    confidence TEXT,
    target_date TEXT,
    body_part TEXT,
    metadata_date TEXT,
    metadata_time TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hypothesis TEXT,
    metrics TEXT NOT NULL,
    baseline_days INTEGER NOT NULL DEFAULT 14,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DAILY_COLS = [
    "date", "resting_hr", "hr_overnight_low", "hr_bedtime",
    "hrv_overnight_avg", "hrv_weekly_avg", "hrv_status",
    "hrv_baseline_low", "hrv_baseline_high", "sleep_seconds", "deep_seconds",
    "light_seconds", "rem_seconds", "awake_seconds", "sleep_score",
    "body_battery_high", "body_battery_low", "body_battery_start",
    "body_battery_current", "stress_avg", "stress_high_minutes",
    "stress_total_minutes", "steps",
    "intensity_minutes", "vo2max", "spo2_avg", "respiration_avg",
    "training_readiness_score", "training_readiness_level", "training_status",
]

ACTIVITY_COLS = [
    "activity_id", "date", "name", "type", "duration_s", "distance_m",
    "avg_hr", "max_hr", "training_load", "aerobic_te", "anaerobic_te",
]

CHECKIN_COLS = ["date", "pain", "fatigue", "energy", "note"]

WEEKLY_SUMMARY_COLS = ["week_start", "generated_at", "model", "summary_md"]

EXERCISE_COLS = [
    "exercise_id", "name", "category", "movement_pattern", "primary_muscle",
    "is_unilateral", "is_bodyweight", "is_main_lift", "is_custom",
]
ROUTINE_COLS = ["routine_id", "name", "notes"]
ROUTINE_EX_COLS = [
    "routine_id", "position", "exercise_id", "target_sets",
    "target_reps", "target_weight",
]
SESSION_COLS = [
    "session_id", "date", "started_at", "ended_at", "routine_id", "name",
    "bodyweight_kg", "notes", "readiness_score", "readiness_level",
    "hrv_status", "hrv_overnight_avg", "body_battery_start", "sleep_score",
    "resting_hr", "acwr",
]
SET_COLS = [
    "set_id", "session_id", "exercise_id", "position", "set_index", "side",
    "reps", "weight_kg", "rpe", "is_warmup", "completed", "logged_at",
]
BODY_METRIC_COLS = [
    "date", "weight_kg", "bmi", "body_fat_pct", "muscle_mass_kg",
    "body_water_pct", "bone_mass_kg", "source",
]
PROFILE_COLS = ["id", "sex", "birth_year", "height_cm", "source"]

COACH_MEMORY_COLS = [
    "id", "category", "text", "status", "source",
    "confidence", "target_date", "body_part", "metadata_date",
    "metadata_time", "created_at", "updated_at",
]

EXPERIMENT_COLS = [
    "id", "name", "hypothesis", "metrics", "baseline_days",
    "start_date", "end_date", "status", "created_at", "updated_at",
]


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _local_now():
    try:
        return datetime.now(ZoneInfo(config.LOCAL_TIMEZONE))
    except ZoneInfoNotFoundError:
        return datetime.now()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Add columns introduced after a DB was first created (CREATE TABLE
        # IF NOT EXISTS won't add them to an existing table).
        existing = {r[1] for r in conn.execute("PRAGMA table_info(daily_metrics)")}
        for col in DAILY_COLS:
            if col != "date" and col not in existing:
                kind = "TEXT" if col in ("hrv_status", "training_readiness_level",
                                         "training_status") else "REAL"
                conn.execute(f"ALTER TABLE daily_metrics ADD COLUMN {col} {kind}")
        existing = {r[1] for r in conn.execute("PRAGMA table_info(coach_memory)")}
        for col in ("metadata_date", "metadata_time"):
            if col not in existing:
                conn.execute(f"ALTER TABLE coach_memory ADD COLUMN {col} TEXT")
    # Seed the strength library + apply any .env profile override. Done AFTER
    # the schema `with connect()` transaction has committed, so these nested
    # connections don't contend with an open write transaction (which on an
    # older DB mid-ALTER would otherwise risk "database is locked").
    seed_exercises()
    prof = {k: v for k, v in (
        ("sex", config.PROFILE_SEX),
        ("birth_year", config.PROFILE_BIRTH_YEAR),
        ("height_cm", config.PROFILE_HEIGHT_CM),
    ) if v is not None}
    if prof:
        upsert_profile({**prof, "source": "manual"})


def upsert_daily(record: dict):
    """record: dict with any subset of DAILY_COLS. Must include 'date'."""
    cols = [c for c in DAILY_COLS if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "date")
    sql = (
        f"INSERT INTO daily_metrics ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}, updated_at=datetime('now')"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_activity(record: dict):
    cols = [c for c in ACTIVITY_COLS if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "activity_id")
    sql = (
        f"INSERT INTO activities ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT(activity_id) DO UPDATE SET {updates}"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_checkin(record: dict):
    """Persist the user's daily subjective load response. Must include 'date'."""
    cols = [c for c in CHECKIN_COLS if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "date")
    sql = (
        f"INSERT INTO daily_checkins ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}, updated_at=datetime('now')"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def save_raw(date: str, endpoint: str, payload):
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO raw_json (date, endpoint, payload) VALUES (?,?,?)",
            (date, endpoint, json.dumps(payload)),
        )


def _upsert(table, cols_def, record, pk, touch_updated=True):
    cols = [c for c in cols_def if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    tail = ", updated_at=datetime('now')" if touch_updated else ""
    sql = (
        f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk}) DO UPDATE SET {updates}{tail}"
        if updates else
        f"INSERT OR IGNORE INTO {table} ({collist}) VALUES ({placeholders})"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_exercise(record: dict):
    _upsert("exercises", EXERCISE_COLS, record, "exercise_id", touch_updated=False)


def upsert_routine(record: dict):
    _upsert("routines", ROUTINE_COLS, record, "routine_id")


def upsert_routine_exercise(record: dict):
    cols = [c for c in ROUTINE_EX_COLS if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols
                        if c not in ("routine_id", "position"))
    sql = (
        f"INSERT INTO routine_exercises ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT(routine_id, position) DO UPDATE SET {updates}"
        if updates else
        f"INSERT OR IGNORE INTO routine_exercises ({collist}) VALUES ({placeholders})"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_strength_session(record: dict):
    _upsert("strength_sessions", SESSION_COLS, record, "session_id")


def upsert_strength_set(record: dict):
    _upsert("strength_sets", SET_COLS, record, "set_id", touch_updated=False)


def delete_strength_set(set_id: str):
    with connect() as conn:
        conn.execute("DELETE FROM strength_sets WHERE set_id=?", (set_id,))


def delete_strength_session(session_id: str) -> bool:
    """Delete one saved strength workout and all of its logged sets."""
    with connect() as conn:
        conn.execute("DELETE FROM strength_sets WHERE session_id=?", (session_id,))
        cur = conn.execute(
            "DELETE FROM strength_sessions WHERE session_id=?", (session_id,)
        )
        return cur.rowcount > 0


def upsert_body_metric(record: dict):
    """Garmin writes won't overwrite a row whose existing source is 'manual'."""
    source = (record.get("source") or "garmin")
    if source == "garmin":
        with connect() as conn:
            existing = conn.execute(
                "SELECT source FROM body_metrics WHERE date=?", (record["date"],)
            ).fetchone()
        if existing is not None and existing["source"] == "manual":
            return
    _upsert("body_metrics", BODY_METRIC_COLS, record, "date")


def upsert_profile(record: dict):
    """Single-row profile (id=1). Garmin source won't overwrite a manual row."""
    record = {**record, "id": 1}
    source = (record.get("source") or "garmin")
    if source == "garmin":
        with connect() as conn:
            existing = conn.execute(
                "SELECT source FROM profile WHERE id=1"
            ).fetchone()
        if existing is not None and existing["source"] == "manual":
            return
    _upsert("profile", PROFILE_COLS, record, "id")


def seed_exercises():
    """Insert the starter library if absent. INSERT OR IGNORE preserves any
    user edits to seeded rows and any custom exercises."""
    import strength_catalog
    with connect() as conn:
        for e in strength_catalog.EXERCISE_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO exercises "
                "(exercise_id, name, category, movement_pattern, primary_muscle, "
                " is_unilateral, is_bodyweight, is_main_lift, is_custom) "
                "VALUES (?,?,?,?,?,?,?,?,0)",
                (e["exercise_id"], e["name"], e["category"], e["movement_pattern"],
                 e["primary_muscle"], e["is_unilateral"], e["is_bodyweight"],
                 e["is_main_lift"]),
            )


def load_daily_df():
    import pandas as pd
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM daily_metrics ORDER BY date", conn, parse_dates=["date"]
        )
    return df


def load_activities_df():
    import pandas as pd
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM activities ORDER BY date", conn, parse_dates=["date"]
        )
    return df


def load_checkins_df():
    import pandas as pd
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM daily_checkins ORDER BY date", conn, parse_dates=["date"]
        )
    return df


def save_weekly_summary(week_start: str, model: str, summary_md: str):
    """Upsert one weekly summary keyed by ISO-week Monday. Overwrites on
    conflict so the Regenerate button replaces the cached text."""
    _upsert("weekly_summaries", WEEKLY_SUMMARY_COLS, {
        "week_start": week_start,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "summary_md": summary_md,
    }, "week_start", touch_updated=False)


def load_weekly_summary(week_start: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM weekly_summaries WHERE week_start=?", (week_start,)
        ).fetchone()
    return dict(row) if row else None


def load_exercises_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM exercises ORDER BY name", conn)


def load_routines_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM routines ORDER BY name", conn)


def load_routine_exercises_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM routine_exercises ORDER BY routine_id, position", conn
        )


def load_strength_sessions_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM strength_sessions ORDER BY date, started_at", conn
        )


def load_strength_sets_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM strength_sets ORDER BY session_id, position, set_index", conn
        )


def load_body_metrics_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM body_metrics ORDER BY date", conn)


def load_profile() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
    return dict(row) if row is not None else {}


def add_memory(record: dict) -> int:
    """Insert one coach memory. Returns the new row id. `category` and `text`
    are required; `status` defaults to 'active', `source` to 'user'."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    category = record["category"]
    metadata_date = record.get("metadata_date")
    metadata_time = record.get("metadata_time")
    if category in ("injury", "note") and (not metadata_date or not metadata_time):
        local = _local_now()
        metadata_date = metadata_date or local.date().isoformat()
        metadata_time = metadata_time or local.strftime("%H:%M")
    fields = {
        "category": category,
        "text": record["text"],
        "status": record.get("status", "active"),
        "source": record.get("source", "user"),
        "confidence": record.get("confidence"),
        "target_date": record.get("target_date"),
        "body_part": record.get("body_part"),
        "metadata_date": metadata_date,
        "metadata_time": metadata_time,
        "created_at": now,
        "updated_at": now,
    }
    cols = list(fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO coach_memory ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [fields[c] for c in cols],
        )
        return int(cur.lastrowid)


def update_memory(memory_id: int, fields: dict):
    """Update editable fields of one memory and bump updated_at."""
    allowed = ("category", "text", "status", "confidence",
               "target_date", "body_part", "metadata_date", "metadata_time")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    sets["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{k}=?" for k in sets)
    with connect() as conn:
        conn.execute(f"UPDATE coach_memory SET {assignments} WHERE id=?",
                     [*sets.values(), memory_id])


def archive_memory(memory_id: int):
    update_memory(memory_id, {"status": "archived"})


def delete_memory(memory_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM coach_memory WHERE id=?", (memory_id,))


def load_memory_df(status: str | None = "active"):
    """Load coach memories. status=None loads all; otherwise filters by status."""
    import pandas as pd
    with connect() as conn:
        if status is None:
            df = pd.read_sql_query(
                "SELECT * FROM coach_memory ORDER BY created_at", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM coach_memory WHERE status=? ORDER BY created_at",
                conn, params=(status,))
    return df


def add_experiment(record: dict) -> int:
    """Insert one experiment. `name`, `metrics` (list), `start_date` required.
    `metrics` is stored as a JSON string; status defaults to 'active'."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fields = {
        "name": record["name"],
        "hypothesis": record.get("hypothesis"),
        "metrics": json.dumps(list(record.get("metrics", []))),
        "baseline_days": int(record.get("baseline_days", 14)),
        "start_date": record["start_date"],
        "end_date": record.get("end_date"),
        "status": record.get("status", "active"),
        "created_at": now,
        "updated_at": now,
    }
    cols = list(fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO experiments ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [fields[c] for c in cols],
        )
        return int(cur.lastrowid)


def update_experiment(experiment_id: int, fields: dict):
    """Update editable experiment fields and bump updated_at. `metrics` (if
    present) is re-encoded to JSON."""
    allowed = ("name", "hypothesis", "metrics", "baseline_days",
               "start_date", "end_date", "status")
    sets = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets[k] = json.dumps(list(v)) if k == "metrics" else v
    if not sets:
        return
    sets["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{k}=?" for k in sets)
    with connect() as conn:
        conn.execute(f"UPDATE experiments SET {assignments} WHERE id=?",
                     [*sets.values(), experiment_id])


def set_experiment_status(experiment_id: int, status: str):
    update_experiment(experiment_id, {"status": status})


def delete_experiment(experiment_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM experiments WHERE id=?", (experiment_id,))


def load_experiments_df(status: str | None = "active"):
    """Load experiments. status=None loads all. `metrics` is decoded to a list."""
    import pandas as pd
    with connect() as conn:
        if status is None:
            df = pd.read_sql_query(
                "SELECT * FROM experiments ORDER BY created_at", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM experiments WHERE status=? ORDER BY created_at",
                conn, params=(status,))
    if not df.empty:
        df["metrics"] = df["metrics"].apply(
            lambda s: json.loads(s) if isinstance(s, str) and s else [])
    return df


def load_body_battery_df(date: str | None = None):
    """Return Garmin Body Battery intraday samples parsed from raw_json."""
    import pandas as pd

    sql = (
        "SELECT date, payload FROM raw_json "
        "WHERE endpoint IN ('all_day_stress', 'body_battery')"
    )
    params = []
    if date is not None:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY date"

    records = []
    with connect() as conn:
        for row in conn.execute(sql, params):
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            records.extend(_body_battery_points(payload, row["date"]))

    if not records:
        return pd.DataFrame(columns=["date", "timestamp", "value"])

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    df = df[(df["value"] >= 0) & (df["value"] <= 100)]
    if df.empty:
        return pd.DataFrame(columns=["date", "timestamp", "value"])
    df["date"] = df["date"].astype(str)
    return df.drop_duplicates(["date", "timestamp", "value"]).sort_values(["date", "timestamp"])


def load_stress_df(date: str | None = None):
    """Return Garmin intraday stress samples parsed from all_day_stress raw_json."""
    import pandas as pd

    sql = "SELECT date, payload FROM raw_json WHERE endpoint='all_day_stress'"
    params = []
    if date is not None:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY date"

    records = []
    with connect() as conn:
        for row in conn.execute(sql, params):
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            records.extend(_stress_points(payload, row["date"]))

    if not records:
        return pd.DataFrame(columns=["date", "timestamp", "value"])

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    # Garmin uses negative stress codes for unavailable/rest states; chart
    # only the measured 0-100 stress level.
    df = df[(df["value"] >= 0) & (df["value"] <= 100)]
    if df.empty:
        return pd.DataFrame(columns=["date", "timestamp", "value"])
    df["date"] = df["date"].astype(str)
    return df.drop_duplicates(["date", "timestamp", "value"]).sort_values(["date", "timestamp"])


def load_sleep_timing_df():
    """Return local sleep start/end/midpoint timestamps parsed from raw sleep JSON."""
    import pandas as pd

    records = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT date, payload FROM raw_json WHERE endpoint='sleep' ORDER BY date"
        )
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                continue
            node = payload.get("dailySleepDTO") if isinstance(payload, dict) else None
            node = node if isinstance(node, dict) else payload if isinstance(payload, dict) else {}
            start = _parse_sleep_local_timestamp(
                _first_present(node, "sleepStartTimestampLocal", "sleepStartLocal"),
                _first_present(node, "sleepStartTimestampGMT", "sleepStartGMT"),
            )
            end = _parse_sleep_local_timestamp(
                _first_present(node, "sleepEndTimestampLocal", "sleepEndLocal"),
                _first_present(node, "sleepEndTimestampGMT", "sleepEndGMT"),
            )
            if start is None or end is None:
                continue
            midpoint = start + (end - start) / 2
            records.append({
                "date": str(row["date"]),
                "sleep_start": start,
                "sleep_end": end,
                "sleep_midpoint": midpoint,
            })

    if not records:
        return pd.DataFrame(columns=["date", "sleep_start", "sleep_end", "sleep_midpoint"])
    df = pd.DataFrame(records)
    for col in ("sleep_start", "sleep_end", "sleep_midpoint"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df.dropna(subset=["sleep_start", "sleep_end", "sleep_midpoint"])


def load_activity_raw_payloads(prefix: str) -> dict[str, dict]:
    """Load activity-scoped raw Garmin payloads keyed by activity id.

    `prefix` is the endpoint prefix before the colon, e.g.
    "activity_details" for endpoints like "activity_details:12345".
    """
    out = {}
    like = f"{prefix}:%"
    with connect() as conn:
        rows = conn.execute(
            "SELECT endpoint, payload FROM raw_json WHERE endpoint LIKE ?", (like,)
        )
        for row in rows:
            try:
                activity_id = row["endpoint"].split(":", 1)[1]
                out[activity_id] = json.loads(row["payload"])
            except (IndexError, TypeError, json.JSONDecodeError):
                continue
    return out


def _stress_points(payload, fallback_date: str):
    records = []

    def add_point(ts, value, day):
        parsed_ts = _parse_bb_timestamp(ts)
        if parsed_ts is None or value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        records.append({"date": str(day or fallback_date), "timestamp": parsed_ts, "value": v})

    def walk(node, day):
        if isinstance(node, dict):
            day_hint = (
                node.get("calendarDate")
                or node.get("date")
                or node.get("day")
                or day
                or fallback_date
            )
            values = node.get("stressValuesArray")
            if isinstance(values, list):
                for sample in values:
                    if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                        add_point(sample[0], sample[1], day_hint)
                    elif isinstance(sample, dict):
                        add_point(
                            _first_present(sample, "timestampGMT", "timestampLocal", "timestamp", "time"),
                            _first_present(sample, "stressLevel", "stress", "value", "level"),
                            day_hint,
                        )
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value, day_hint)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item, day)

    walk(payload, fallback_date)
    return records


def _body_battery_points(payload, fallback_date: str):
    records = []

    def add_point(ts, value, day):
        parsed_ts = _parse_bb_timestamp(ts)
        if parsed_ts is None or value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if 0 <= v <= 100:
            records.append({"date": str(day or fallback_date), "timestamp": parsed_ts, "value": v})

    def parse_sample(sample, day):
        if isinstance(sample, dict):
            ts = _first_present(
                sample,
                "timestampGMT", "timestampLocal", "startTimestampGMT", "startTimestampLocal",
                "dateTimeGMT", "dateTimeLocal", "dateTime", "timestamp", "time",
            )
            value = _first_present(
                sample,
                "bodyBatteryLevel", "bodyBatteryValue", "bodyBattery", "batteryBody",
                "value", "level",
            )
            add_point(ts, value, day)
            return
        if isinstance(sample, (list, tuple)):
            ts = None
            value = None
            for item in sample:
                if ts is None and _looks_like_timestamp(item):
                    ts = item
                    continue
                if value is None and _looks_like_body_battery_value(item):
                    value = item
            add_point(ts, value, day)

    def is_body_battery_key(key) -> bool:
        low = str(key).lower()
        return "bodybattery" in low or ("body" in low and "battery" in low)

    def walk(node, day, parse_arrays=False):
        if isinstance(node, dict):
            day_hint = (
                node.get("calendarDate")
                or node.get("date")
                or node.get("day")
                or day
                or fallback_date
            )
            if parse_arrays or any(is_body_battery_key(k) for k in node):
                parse_sample(node, day_hint)
            for key, value in node.items():
                low = str(key).lower()
                if "descriptor" in low:
                    continue
                if isinstance(value, list):
                    is_bb = is_body_battery_key(key)
                    if is_bb:
                        for sample in value:
                            parse_sample(sample, day_hint)
                    walk(value, day_hint, parse_arrays=is_bb)
                elif isinstance(value, dict):
                    walk(value, day_hint, parse_arrays=parse_arrays)
        elif isinstance(node, list):
            if parse_arrays:
                for item in node:
                    parse_sample(item, day)
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item, day, parse_arrays=False)

    walk(payload, fallback_date)
    seen = set()
    unique = []
    for rec in records:
        key = (rec["date"], str(rec["timestamp"]), rec["value"])
        if key not in seen:
            unique.append(rec)
            seen.add(key)
    return unique


def _first_present(obj: dict, *keys):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _parse_bb_timestamp(value):
    import pandas as pd

    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            return _utc_to_local_naive(pd.to_datetime(value, unit="ms", utc=True, errors="coerce"))
        if value > 1_000_000_000:
            return _utc_to_local_naive(pd.to_datetime(value, unit="s", utc=True, errors="coerce"))
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        return _utc_to_local_naive(ts)
    return ts


def _parse_sleep_local_timestamp(local_value, gmt_value=None):
    import pandas as pd

    if local_value is not None:
        if isinstance(local_value, (int, float)):
            if local_value > 1_000_000_000_000:
                return pd.to_datetime(local_value, unit="ms", errors="coerce")
            if local_value > 1_000_000_000:
                return pd.to_datetime(local_value, unit="s", errors="coerce")
        ts = pd.to_datetime(local_value, errors="coerce")
        if pd.notna(ts):
            return ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else ts
    return _parse_bb_timestamp(gmt_value)


def _utc_to_local_naive(ts):
    import pandas as pd

    if ts is None or pd.isna(ts):
        return None
    try:
        tz = ZoneInfo(config.LOCAL_TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = None
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert(tz) if tz is not None else ts.tz_convert(None)
    return local.tz_localize(None)


def _looks_like_timestamp(value) -> bool:
    if isinstance(value, (int, float)):
        return value > 1_000_000_000
    if isinstance(value, str):
        return any(mark in value for mark in ("T", ":", "-"))
    return False


def _looks_like_body_battery_value(value) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return 0 <= float(value) <= 100
