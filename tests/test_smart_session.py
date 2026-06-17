import pandas as pd
import analysis


def _green_daily():
    return pd.DataFrame({
        "date": pd.date_range("2026-05-20", periods=14, freq="D"),
        "hrv_overnight_avg": [60] * 14, "resting_hr": [50] * 14,
        "sleep_hours": [8.0] * 14, "hrv_flag": ["balanced"] * 14,
        "rhr_elevated": [False] * 14, "sleep_debt_h": [0.0] * 14,
        "stress_avg": [30] * 14, "body_battery_current": [70] * 14,
    })


def _red_daily():
    df = _green_daily()
    df["hrv_flag"] = ["suppressed"] * 14
    df["rhr_elevated"] = [True] * 14
    df["sleep_debt_h"] = [2.0] * 14
    df["stress_avg"] = [70] * 14
    df["body_battery_current"] = [20] * 14
    return df


def test_recovery_readiness_green():
    r = analysis.recovery_readiness(_green_daily())
    assert r["status"] == "ready"
    assert r["zone"] == "green"
    assert r["value"] == 100


def test_recovery_readiness_red_has_reasons():
    r = analysis.recovery_readiness(_red_daily())
    assert r["zone"] == "red"
    assert r["value"] < 100
    assert len(r["reasons"]) >= 1


def test_recovery_readiness_no_data():
    r = analysis.recovery_readiness(pd.DataFrame())
    assert r["status"] == "no_data"
    assert r["zone"] == "green"


def test_recovery_readiness_as_of_slices():
    df = _green_daily()
    df.loc[df.index[-1], "hrv_flag"] = "suppressed"  # only the last day is bad
    early = analysis.recovery_readiness(df, as_of="2026-05-25")
    assert early["zone"] == "green"  # the bad last day is excluded


def test_verdict_green_is_push():
    v = analysis.readiness_verdict({"status": "ready", "zone": "green", "value": 95, "reasons": []})
    assert v["day_type"] == "Push"
    assert v["zone"] == "green"

def test_verdict_red_is_back_off():
    v = analysis.readiness_verdict({"status": "ready", "zone": "red", "value": 30,
                                    "reasons": ["HRV below personal baseline"]})
    assert v["day_type"] == "Back off"
    assert "HRV below personal baseline" in v["reasons"]

def test_verdict_no_data_is_neutral():
    v = analysis.readiness_verdict({"status": "no_data", "zone": "green", "value": 100, "reasons": []})
    assert v["day_type"] == "Log normally"
