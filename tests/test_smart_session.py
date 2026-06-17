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


def _ex_df():
    return pd.DataFrame([
        {"exercise_id": "back-squat", "is_main_lift": 1, "increment_kg": 2.5, "target_reps": 5},
        {"exercise_id": "barbell-curl", "is_main_lift": 0, "increment_kg": None, "target_reps": None},
    ])

def _sess(*dates):
    return pd.DataFrame([{"session_id": f"s{i}", "date": d} for i, d in enumerate(dates)])

def _set(session_id, weight, reps, completed=1, warmup=0, exercise_id="back-squat"):
    return {"session_id": session_id, "exercise_id": exercise_id, "weight_kg": weight,
            "reps": reps, "completed": completed, "is_warmup": warmup}

def test_progression_progresses_when_all_sets_hit():
    sets = pd.DataFrame([_set("s0", 100, 5), _set("s0", 100, 5), _set("s0", 100, 5)])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    assert out["state"] == "progress"
    assert out["suggested_weight_kg"] == 102.5

def test_progression_holds_when_a_set_short():
    sets = pd.DataFrame([_set("s0", 100, 5), _set("s0", 100, 3)])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    assert out["state"] == "hold"
    assert out["suggested_weight_kg"] == 100

def test_progression_deloads_after_three_stalls():
    sets = pd.DataFrame([
        _set("s0", 100, 3), _set("s1", 100, 3), _set("s2", 100, 3),
    ])
    sess = _sess("2026-06-01", "2026-06-03", "2026-06-05")
    out = analysis.compute_progression_suggestion("back-squat", sess, sets, _ex_df())
    assert out["state"] == "deload"
    assert out["stalls"] == 3
    assert out["suggested_weight_kg"] == 90.0  # round(100*0.9 / 2.5)*2.5

def test_progression_no_deload_at_two_stalls():
    sets = pd.DataFrame([_set("s0", 100, 3), _set("s1", 100, 3)])
    sess = _sess("2026-06-01", "2026-06-03")
    out = analysis.compute_progression_suggestion("back-squat", sess, sets, _ex_df())
    assert out["state"] == "hold"

def test_progression_none_for_accessory():
    sets = pd.DataFrame([_set("s0", 30, 10, exercise_id="barbell-curl")])
    out = analysis.compute_progression_suggestion("barbell-curl", _sess("2026-06-01"), sets, _ex_df())
    assert out is None

def test_progression_none_with_no_history():
    out = analysis.compute_progression_suggestion(
        "back-squat", pd.DataFrame(columns=["session_id", "date"]),
        pd.DataFrame(columns=["session_id", "exercise_id", "weight_kg", "reps", "completed", "is_warmup"]),
        _ex_df())
    assert out is None

def test_progression_ignores_warmups_and_incomplete():
    sets = pd.DataFrame([
        _set("s0", 60, 5, warmup=1), _set("s0", 100, 5), _set("s0", 100, 5, completed=0),
    ])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    # only the one completed working set at 100×5 counts → all hit → progress
    assert out["state"] == "progress"


def test_lift_recovery_sensitivity_flags_drop():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    # green days lift heavier than low-recovery days
    sess = pd.DataFrame([
        {"session_id": "g1", "date": "2026-06-01", "bodyweight_kg": 80, "recovery_zone": "green"},
        {"session_id": "g2", "date": "2026-06-03", "bodyweight_kg": 80, "recovery_zone": "green"},
        {"session_id": "r1", "date": "2026-06-05", "bodyweight_kg": 80, "recovery_zone": "red"},
        {"session_id": "r2", "date": "2026-06-07", "bodyweight_kg": 80, "recovery_zone": "yellow"},
    ])
    def row(sid, w):
        return {"session_id": sid, "exercise_id": "back-squat", "weight_kg": w,
                "reps": 5, "completed": 1, "is_warmup": 0}
    sets = pd.DataFrame([row("g1", 100), row("g2", 100), row("r1", 90), row("r2", 90)])
    out = analysis.compute_lift_recovery_sensitivity(sess, sets, ex, min_pairs=4)
    squat = [o for o in out if o["exercise"] == "Back Squat"]
    assert squat and squat[0]["flagged"] is True
    assert squat[0]["delta_pct"] < 0

def test_lift_recovery_sensitivity_gated_by_sample():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    sess = pd.DataFrame([{"session_id": "g1", "date": "2026-06-01", "bodyweight_kg": 80,
                          "recovery_zone": "green"}])
    sets = pd.DataFrame([{"session_id": "g1", "exercise_id": "back-squat", "weight_kg": 100,
                          "reps": 5, "completed": 1, "is_warmup": 0}])
    assert analysis.compute_lift_recovery_sensitivity(sess, sets, ex, min_pairs=4) == []


def test_summarize_strength_carries_verdict():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    sess = pd.DataFrame([{"session_id": "s0", "date": "2026-06-01", "bodyweight_kg": 80,
                          "recovery_score": 80}])
    sets = pd.DataFrame([{"session_id": "s0", "exercise_id": "back-squat", "weight_kg": 100,
                          "reps": 5, "completed": 1, "is_warmup": 0}])
    verdict = {"zone": "yellow", "day_type": "Hold / volume", "value": 60,
               "headline": "Hold / volume — recovery yellow", "reasons": ["sleep debt >1h"]}
    out = analysis.summarize_strength(sess, sets, ex, profile=None, bodyweight_kg=80, verdict=verdict)
    assert out["recovery_verdict"]["day_type"] == "Hold / volume"
