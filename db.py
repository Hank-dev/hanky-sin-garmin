"""SQLite persistence. Idempotent upserts keyed on date / activity id."""
import sqlite3
import json
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


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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
