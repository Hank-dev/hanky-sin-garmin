"""Pull Garmin data for a date range and write it to SQLite.

The JSON field names below are best-effort against Garmin Connect's current
payloads. Garmin changes these without notice. Every endpoint's raw response
is also stored verbatim in the raw_json table, so if a derived column comes up
empty you can inspect the raw payload and adjust the `dig()` paths here.
"""
from datetime import date, datetime, timedelta
import db

GRAPPLING_PATTERNS = (
    "bjj", "jiu-jitsu", "jiu jitsu", "grappling", "martial",
    "combat", "wrestling", "submission",
)


def dig(obj, *paths, default=None):
    """Try several key-paths against a nested dict/list. Each path is a
    dot/index string, e.g. 'dailySleepDTO.sleepTimeSeconds' or
    'sleepScores.overall.value'. Returns the first that resolves."""
    for path in paths:
        cur = obj
        ok = True
        for key in path.split("."):
            try:
                if isinstance(cur, list):
                    cur = cur[int(key)]
                else:
                    cur = cur[key]
            except (KeyError, IndexError, TypeError, ValueError):
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default


def safe(fn, *args):
    """Call a Garmin getter, returning None on any error (missing data, etc.)."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"   ! {fn.__name__}({args}) -> {type(e).__name__}: {e}")
        return None


def _call_first(client, names, *args):
    """Call the first existing client method from `names` (handles garminconnect
    version drift — the names are aliases for the same endpoint). Returns None if
    no name is callable, or if the first callable one errors."""
    for name in names:
        fn = getattr(client, name, None)
        if callable(fn):
            return safe(fn, *args)
    return None


def _grams_to_kg(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # Garmin reports body weights in grams. Tolerate already-kg payloads.
    return v / 1000.0 if v > 1000 else v


def _norm_sex(value):
    if not value:
        return None
    low = str(value).strip().lower()
    if low.startswith("m"):
        return "male"
    if low.startswith("f") or low.startswith("w"):
        return "female"
    return None


def _year_from(value):
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _duration_minutes(value):
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # Garmin wellness durations are normally seconds; tolerate millisecond
    # payloads if an endpoint changes shape.
    if v > 24 * 60 * 60:
        v = v / 1000.0
    return v / 60.0


def is_grappling_activity(record: dict) -> bool:
    text = f"{record.get('name') or ''} {record.get('type') or ''}".lower()
    return any(p in text for p in GRAPPLING_PATTERNS)


def _sleep_hr(series, sleep_start, sleep_end, day_min):
    """Derive (lowest_overnight_hr, bedtime_hr) from a day's HR time-series.

    `series` is Garmin's heartRateValues: a list of [epoch_ms, bpm] pairs (bpm
    may be None). `sleep_start`/`sleep_end` are GMT epoch-ms or None. Pure and
    deterministic — no I/O — so it can be unit-tested with a synthetic series.

    overnight low: min HR inside the sleep window; falls back to the day's
    minHeartRate when the sleep window is unknown. bedtime HR: the sample
    nearest to (and preferentially at/just before) sleep start, within 30 min;
    None when there is no sleep-start time or no nearby sample.
    """
    pts = [(p[0], p[1]) for p in (series or [])
           if isinstance(p, (list, tuple)) and len(p) == 2 and p[1] is not None]

    overnight = None
    if sleep_start and sleep_end:
        window = [hr for ts, hr in pts if sleep_start <= ts <= sleep_end]
        if window:
            overnight = min(window)
    if overnight is None:
        overnight = day_min  # fallback (may itself be None)

    bedtime = None
    if sleep_start and pts:
        guard = 30 * 60 * 1000  # 30 minutes in ms
        before = [(ts, hr) for ts, hr in pts if sleep_start - guard <= ts <= sleep_start]
        near = before or [(ts, hr) for ts, hr in pts if abs(ts - sleep_start) <= guard]
        if near:
            bedtime = min(near, key=lambda p: abs(p[0] - sleep_start))[1]

    return overnight, bedtime


def ingest_day(client, d: str):
    """Fetch and store everything for a single date string 'YYYY-MM-DD'."""
    rec = {"date": d}

    sleep = safe(client.get_sleep_data, d)
    if sleep:
        db.save_raw(d, "sleep", sleep)
        rec["sleep_seconds"] = dig(sleep, "dailySleepDTO.sleepTimeSeconds")
        rec["deep_seconds"] = dig(sleep, "dailySleepDTO.deepSleepSeconds")
        rec["light_seconds"] = dig(sleep, "dailySleepDTO.lightSleepSeconds")
        rec["rem_seconds"] = dig(sleep, "dailySleepDTO.remSleepSeconds")
        rec["awake_seconds"] = dig(sleep, "dailySleepDTO.awakeSleepSeconds")
        rec["sleep_score"] = dig(
            sleep, "dailySleepDTO.sleepScores.overall.value", "sleepScores.overall.value"
        )

    hrv = safe(client.get_hrv_data, d)
    if hrv:
        db.save_raw(d, "hrv", hrv)
        rec["hrv_overnight_avg"] = dig(hrv, "hrvSummary.lastNightAvg")
        rec["hrv_weekly_avg"] = dig(hrv, "hrvSummary.weeklyAvg")
        rec["hrv_status"] = dig(hrv, "hrvSummary.status")
        rec["hrv_baseline_low"] = dig(hrv, "hrvSummary.baseline.lowUpper", "hrvSummary.baseline.balancedLow")
        rec["hrv_baseline_high"] = dig(hrv, "hrvSummary.baseline.balancedUpper")

    rhr = safe(client.get_rhr_day, d)
    if rhr:
        db.save_raw(d, "rhr", rhr)
        rec["resting_hr"] = dig(
            rhr,
            "allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE.0.value",
            "restingHeartRate",
        )

    stats = safe(client.get_stats, d)
    if stats:
        db.save_raw(d, "stats", stats)
        rec.setdefault("resting_hr", dig(stats, "restingHeartRate"))
        rec["steps"] = dig(stats, "totalSteps")
        rec["stress_avg"] = dig(stats, "averageStressLevel")
        rec["body_battery_high"] = dig(stats, "bodyBatteryHighestValue")
        rec["body_battery_low"] = dig(stats, "bodyBatteryLowestValue")
        rec["body_battery_start"] = dig(stats, "bodyBatteryAtWakeTime")
        # The number Garmin Connect headlines is the *current* battery, not the
        # day's peak — store it so the dashboard can match what you see there.
        rec["body_battery_current"] = dig(
            stats, "bodyBatteryMostRecentValue", "currentBodyBattery")
        rec["stress_high_minutes"] = _duration_minutes(dig(stats, "highStressDuration"))
        rec["stress_total_minutes"] = _duration_minutes(
            dig(stats, "totalStressDuration", "stressDuration"))
        mod = dig(stats, "moderateIntensityMinutes", default=0) or 0
        vig = dig(stats, "vigorousIntensityMinutes", default=0) or 0
        rec["intensity_minutes"] = mod + 2 * vig  # Garmin weights vigorous x2

    stress = safe(client.get_all_day_stress, d)
    if stress:
        db.save_raw(d, "all_day_stress", stress)
        rec.setdefault("stress_avg", dig(stress, "avgStressLevel", "averageStressLevel"))

    bb = safe(client.get_body_battery, d, d)
    if bb:
        db.save_raw(d, "body_battery", bb)

    tr = safe(client.get_training_readiness, d)
    if tr:
        db.save_raw(d, "training_readiness", tr)
        node = tr[0] if isinstance(tr, list) and tr else tr
        rec["training_readiness_score"] = dig(node, "score")
        rec["training_readiness_level"] = dig(node, "level")

    ts = safe(client.get_training_status, d)
    if ts:
        db.save_raw(d, "training_status", ts)
        rec["training_status"] = dig(
            ts, "mostRecentTrainingStatus.latestTrainingStatusData.trainingStatusFeedbackPhrase"
        )

    vo2 = safe(client.get_max_metrics, d)
    if vo2:
        db.save_raw(d, "max_metrics", vo2)
        node = vo2[0] if isinstance(vo2, list) and vo2 else vo2
        rec["vo2max"] = dig(node, "generic.vo2MaxPreciseValue", "generic.vo2MaxValue")

    spo2 = safe(client.get_spo2_data, d)
    if spo2:
        db.save_raw(d, "spo2", spo2)
        rec["spo2_avg"] = dig(spo2, "averageSpO2", "averageSpo2")

    resp = safe(client.get_respiration_data, d)
    if resp:
        db.save_raw(d, "respiration", resp)
        rec["respiration_avg"] = dig(resp, "avgSleepRespirationValue", "avgWakingRespirationValue")

    # Sleeping heart rate (Bryan-Johnson-style "resting HR before bed"). Garmin
    # has no direct field, so derive it from the daily HR time-series + the sleep
    # window stored above. See _sleep_hr().
    hrates = safe(client.get_heart_rates, d)
    if hrates:
        db.save_raw(d, "heart_rates", hrates)
        sleep_start = dig(sleep, "dailySleepDTO.sleepStartTimestampGMT",
                          "sleepStartTimestampGMT") if sleep else None
        sleep_end = dig(sleep, "dailySleepDTO.sleepEndTimestampGMT",
                        "sleepEndTimestampGMT") if sleep else None
        low, bed = _sleep_hr(dig(hrates, "heartRateValues") or [],
                             sleep_start, sleep_end, dig(hrates, "minHeartRate"))
        rec["hr_overnight_low"] = low
        rec["hr_bedtime"] = bed

    db.upsert_daily(rec)
    return rec


def ingest_activities(client, start: str, end: str):
    acts = safe(client.get_activities_by_date, start, end) or []
    for a in acts:
        rec = {
            "activity_id": str(dig(a, "activityId")),
            "date": (dig(a, "startTimeLocal", "startTimeGMT") or "")[:10],
            "name": dig(a, "activityName"),
            "type": dig(a, "activityType.typeKey"),
            "duration_s": dig(a, "duration"),
            "distance_m": dig(a, "distance"),
            "avg_hr": dig(a, "averageHR"),
            "max_hr": dig(a, "maxHR"),
            "training_load": dig(a, "activityTrainingLoad"),
            "aerobic_te": dig(a, "aerobicTrainingEffect"),
            "anaerobic_te": dig(a, "anaerobicTrainingEffect"),
        }
        if rec["activity_id"] and rec["activity_id"] != "None":
            db.upsert_activity(rec)
            if is_grappling_activity(rec):
                details = safe(client.get_activity_details, rec["activity_id"])
                if details:
                    db.save_raw(rec["date"], f"activity_details:{rec['activity_id']}", details)
                zones = safe(client.get_activity_hr_in_timezones, rec["activity_id"])
                if zones:
                    db.save_raw(rec["date"], f"activity_hr_zones:{rec['activity_id']}", zones)
    return len(acts)


def ingest_body_metrics(client, start: str, end: str) -> int:
    """Pull Garmin weigh-ins / body composition for a date range into
    body_metrics. Stores the raw payload and dig()s out per-day values."""
    data = _call_first(client, ["get_body_composition", "get_weigh_ins"], start, end)
    if not data:
        return 0
    # Range response: stored once under the window's end date (per-day weight
    # rows below carry their own calendarDate). To inspect a specific day's raw
    # weigh-in, look at the body_composition payload for the window that covers it.
    db.save_raw(end, "body_composition", data)
    entries = dig(data, "dateWeightList", "dailyWeightSummaries") or []
    if not isinstance(entries, list):
        entries = []
    n = 0
    for e in entries:
        cal = dig(e, "calendarDate", "date", "summaryDate")
        grams = dig(e, "weight", "weightInGrams")
        if cal is None or grams is None:
            continue
        db.upsert_body_metric({
            "date": str(cal)[:10],
            "weight_kg": _grams_to_kg(grams),
            "bmi": dig(e, "bmi"),
            "body_fat_pct": dig(e, "bodyFat.bodyFatPercentage", "bodyFatPercentage", "bodyFat"),
            "muscle_mass_kg": _grams_to_kg(dig(e, "muscleMass")),
            "body_water_pct": dig(e, "bodyWater"),
            "bone_mass_kg": _grams_to_kg(dig(e, "boneMass")),
            "source": "garmin",
        })
        n += 1
    return n


def ingest_profile(client) -> None:
    """Pull the Garmin user profile (sex / birth year / height) into profile.
    Won't overwrite a manual/.env profile (db.upsert_profile enforces this)."""
    data = _call_first(client, ["get_user_profile", "get_userprofile",
                                "get_personal_information"])
    if not data:
        return
    db.save_raw(date.today().isoformat(), "user_profile", data)
    db.upsert_profile({
        "sex": _norm_sex(dig(data, "userData.gender", "gender")),
        "birth_year": _year_from(dig(data, "userData.birthDate", "birthDate")),
        "height_cm": dig(data, "userData.height", "height"),
        "source": "garmin",
    })


def smart_sync_days(
    latest_date,
    today: date | None = None,
    initial_days: int = 7,
    min_days: int = 2,
    max_days: int = 14,
) -> int:
    """Calendar days to sync from the dashboard button.

    Keep a small overlap because Garmin can finalize sleep, HRV, stress, and
    Body Battery after midnight. If the DB is behind, catch up from the newest
    stored day through today, capped so one click stays responsive.
    """
    if today is None:
        today = date.today()
    if latest_date is None:
        return int(initial_days)
    try:
        if isinstance(latest_date, datetime):
            latest = latest_date.date()
        elif isinstance(latest_date, date):
            latest = latest_date
        else:
            latest = date.fromisoformat(str(latest_date)[:10])
    except (TypeError, ValueError):
        return int(initial_days)

    gap = max(0, (today - latest).days)
    days = max(int(min_days), gap + 1)
    return min(int(max_days), days)


def backfill(client, days: int = 7):
    db.init_db()
    days = max(1, int(days))
    today = date.today()
    start = today - timedelta(days=days - 1)
    print(f"Syncing {days} day(s): {start} -> {today}")
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        print(f" - {d}")
        ingest_day(client, d)
    n = ingest_activities(client, start.isoformat(), today.isoformat())
    print(f"Stored {n} activities.")
    n_bm = ingest_body_metrics(client, start.isoformat(), today.isoformat())
    print(f"Stored {n_bm} body-metric day(s).")
    ingest_profile(client)
    print("Done.")
