import pytest

import telegram_bot


def test_parse_allowed_user_ids_accepts_commas_and_semicolons():
    assert telegram_bot.parse_allowed_user_ids("123, 456;bad;789") == {
        123,
        456,
        789,
    }


def test_command_parts_strips_bot_username():
    assert telegram_bot.command_parts("/today@HankyCoachBot now") == ("/today", "now")


def test_parse_sync_days_defaults_and_validates_range():
    assert telegram_bot.parse_sync_days("") == 7
    assert telegram_bot.parse_sync_days("30") == 30
    with pytest.raises(ValueError):
        telegram_bot.parse_sync_days("0")
    with pytest.raises(ValueError):
        telegram_bot.parse_sync_days("366")
    with pytest.raises(ValueError):
        telegram_bot.parse_sync_days("later")


def test_format_today_handles_missing_data():
    assert "No Garmin data" in telegram_bot.format_today({"error": "no data"})


def test_format_today_includes_core_snapshot_fields():
    text = telegram_bot.format_today({
        "as_of": "2026-06-15",
        "latest": {
            "training_readiness": 78,
            "hrv_overnight": 64.2,
            "hrv_flag": "balanced",
            "resting_hr": 48,
            "rhr_28d_baseline": 50,
            "sleep_hours": 8.1,
            "sleep_score": 86,
            "body_battery_high": 91,
            "stress_avg": 22,
        },
        "trends_14d": {
            "avg_sleep_hours": 7.6,
            "sleep_debt_total_h": 5.4,
            "hrv_trend": "rising",
            "rhr_trend": "stable",
            "suppressed_hrv_days": 1,
        },
    })
    assert "Recovery snapshot (2026-06-15)" in text
    assert "Readiness: 78" in text
    assert "HRV: 64.2 ms (balanced)" in text
