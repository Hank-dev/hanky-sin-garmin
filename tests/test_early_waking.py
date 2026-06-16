import pandas as pd

import analysis


def test_personal_sleep_need_learns_from_good_recovery_nights():
    start = pd.Timestamp("2026-06-01")
    daily_rows = []
    checkins = []
    for i in range(12):
        date = start + pd.Timedelta(days=i)
        good = i not in (2, 7)
        sleep_h = 7.5 + (i % 3) * 0.15 if good else 6.2
        daily_rows.append({
            "date": date,
            "sleep_seconds": sleep_h * 3600,
            "sleep_score": 86 if good else 58,
            "hrv_overnight_avg": 62 if good else 44,
            "resting_hr": 50 if good else 58,
            "body_battery_start": 72 if good else 40,
            "hrv_flag": "balanced" if good else "suppressed",
        })
        checkins.append({
            "date": date,
            "energy": 7 if good else 3,
            "fatigue": 3 if good else 7,
        })

    model = analysis.compute_personal_sleep_need(
        pd.DataFrame(daily_rows),
        pd.DataFrame(checkins),
        default_sleep_need_h=8.0,
        min_ready_nights=5,
    )

    assert model["status"] == "ready"
    assert model["source"] == "personal_recovery_nights"
    assert model["nights_used"] >= 5
    assert 7.4 <= model["sleep_need_h"] <= 7.8


def test_personal_sleep_need_respects_minimum_floor():
    start = pd.Timestamp("2026-06-01")
    rows = []
    for i in range(8):
        rows.append({
            "date": start + pd.Timedelta(days=i),
            "sleep_seconds": 6.5 * 3600,
            "sleep_score": 88,
            "hrv_overnight_avg": 60,
            "resting_hr": 50,
            "body_battery_start": 75,
            "hrv_flag": "balanced",
        })

    model = analysis.compute_personal_sleep_need(
        pd.DataFrame(rows),
        default_sleep_need_h=8.0,
        min_sleep_need_h=7.25,
        min_ready_nights=5,
    )

    assert model["status"] == "ready"
    assert model["sleep_need_h"] == 7.25
    assert model["min_sleep_need_h"] == 7.25


def test_early_waking_uses_sleep_debt_and_body_battery_at_sleep_start():
    daily = pd.DataFrame([
        {"date": "2026-06-01", "sleep_seconds": 8.0 * 3600, "sleep_score": 86},
        {"date": "2026-06-02", "sleep_seconds": 7.0 * 3600, "sleep_score": 62, "awake_seconds": 50 * 60},
        {"date": "2026-06-03", "sleep_seconds": 7.5 * 3600, "sleep_score": 74},
    ])
    sleep_timing = pd.DataFrame([
        {
            "date": "2026-06-01",
            "sleep_start": pd.Timestamp("2026-05-31 23:00"),
            "sleep_end": pd.Timestamp("2026-06-01 07:00"),
        },
        {
            "date": "2026-06-02",
            "sleep_start": pd.Timestamp("2026-06-01 23:00"),
            "sleep_end": pd.Timestamp("2026-06-02 06:00"),
        },
        {
            "date": "2026-06-03",
            "sleep_start": pd.Timestamp("2026-06-02 23:00"),
            "sleep_end": pd.Timestamp("2026-06-03 06:30"),
        },
    ])
    body_battery = pd.DataFrame([
        {"date": "2026-06-01", "timestamp": pd.Timestamp("2026-06-01 22:55"), "value": 20},
        {"date": "2026-06-01", "timestamp": pd.Timestamp("2026-06-01 23:10"), "value": 30},
        {"date": "2026-06-02", "timestamp": pd.Timestamp("2026-06-02 22:50"), "value": 60},
    ])

    model = analysis.compute_early_waking_model(
        daily, sleep_timing, body_battery, sleep_need_h=8.0
    )

    assert model["status"] == "ready"
    by_date = {row["date"]: row for row in model["rows"]}

    jun2 = by_date["2026-06-02"]
    assert jun2["body_battery_at_sleep_start"] == 20
    assert jun2["body_battery_sample_delta_min"] == -5
    assert jun2["body_battery_repay_h"] == 0.45
    assert jun2["recovery_need_h"] == 8.45
    assert jun2["early_waking_minutes"] == 87
    assert jun2["severity"] == "meaningful"
    assert jun2["confidence"] == "high"
    assert jun2["pattern"] == "low_body_battery_early"
    assert "low Body Battery at sleep start" in jun2["evidence"]
    assert "low sleep score" in jun2["evidence"]
    assert "high awake time during sleep" in jun2["evidence"]

    jun3 = by_date["2026-06-03"]
    assert jun3["prior_sleep_debt_h_7d"] == 1.0
    assert jun3["sleep_debt_repay_h"] == 0.25
    assert jun3["early_waking_minutes"] == 45
    assert jun3["pattern"] == "recovery_debt_early"


def test_early_waking_recomputes_debt_from_personal_sleep_need():
    daily = pd.DataFrame([
        {
            "date": "2026-06-01",
            "sleep_seconds": 7.0 * 3600,
            "sleep_hours": 7.0,
            "sleep_debt_h": 1.0,  # stale/default-based value should be ignored
            "sleep_score": 82,
        },
    ])
    sleep_timing = pd.DataFrame([
        {
            "date": "2026-06-01",
            "sleep_start": pd.Timestamp("2026-05-31 23:00"),
            "sleep_end": pd.Timestamp("2026-06-01 06:30"),
        },
    ])

    model = analysis.compute_early_waking_model(
        daily, sleep_timing, body_battery=None, sleep_need_h=7.5
    )

    row = model["rows"][0]
    assert row["sleep_debt_h"] == 0.5
    assert row["early_waking_minutes"] == 0


def test_early_waking_classifies_stress_activation_pattern():
    start = pd.Timestamp("2026-06-01")
    daily_rows = []
    timing_rows = []
    battery_rows = []
    for i in range(5):
        date = start + pd.Timedelta(days=i)
        stressed = i == 4
        daily_rows.append({
            "date": date,
            "sleep_seconds": (7.0 if stressed else 8.0) * 3600,
            "sleep_score": 78,
            "stress_avg": 62 if stressed else 24,
            "hr_bedtime": 70 if stressed else 60,
            "hrv_overnight_avg": 45 if stressed else 60,
        })
        sleep_start = date - pd.Timedelta(hours=1)
        sleep_end = sleep_start + pd.Timedelta(hours=7 if stressed else 8)
        timing_rows.append({
            "date": date,
            "sleep_start": sleep_start,
            "sleep_end": sleep_end,
        })
        battery_rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "timestamp": sleep_start - pd.Timedelta(minutes=5),
            "value": 65,
        })

    model = analysis.compute_early_waking_model(
        pd.DataFrame(daily_rows),
        pd.DataFrame(timing_rows),
        pd.DataFrame(battery_rows),
        sleep_need_h=8.0,
    )

    latest = model["latest"]
    assert latest["early_waking_minutes"] == 60
    assert latest["pattern"] == "stress_activation_early"
    assert "high daily stress" in latest["evidence"]
    assert "pre-sleep HR above baseline" in latest["evidence"]
    assert "overnight HRV below baseline" in latest["evidence"]


def test_early_waking_can_learn_without_body_battery_samples():
    daily = pd.DataFrame([
        {"date": "2026-06-01", "sleep_seconds": 7.0 * 3600, "sleep_score": 70},
    ])
    sleep_timing = pd.DataFrame([
        {
            "date": "2026-06-01",
            "sleep_start": pd.Timestamp("2026-05-31 23:00"),
            "sleep_end": pd.Timestamp("2026-06-01 06:00"),
        },
    ])

    model = analysis.compute_early_waking_model(
        daily, sleep_timing, body_battery=None, sleep_need_h=8.0
    )

    assert model["status"] == "learning"
    assert model["rows"][0]["early_waking_minutes"] == 60
    assert "intraday Body Battery samples near sleep start" in model["missing"]


def test_early_waking_needs_sleep_timing():
    daily = pd.DataFrame([
        {"date": "2026-06-01", "sleep_seconds": 7.0 * 3600, "sleep_score": 70},
    ])

    model = analysis.compute_early_waking_model(daily, None, sleep_need_h=8.0)

    assert model["status"] == "no_data"
    assert model["rows"] == []
