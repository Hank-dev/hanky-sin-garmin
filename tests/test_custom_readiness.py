"""Custom readiness: HRV trend + RHR + sleep, no load, REST needs agreement."""
import numpy as np
import pandas as pd

import analysis
import fitness_agent


def make_daily(n=80, hrv=55.0, rhr=55.0, sleep_h=7.5, tail=None, seed=1):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "date": [d.date().isoformat() for d in pd.date_range("2026-06-01", periods=n)],
        "hrv_overnight_avg": hrv * np.exp(rng.normal(0, 0.1, n)),
        "resting_hr": rhr + rng.normal(0, 1.0, n),
        "sleep_seconds": np.full(n, sleep_h * 3600.0),
        "hrv_baseline_low": np.full(n, hrv * 0.85),
        "hrv_baseline_high": np.full(n, hrv * 1.2),
        "respiration_avg": 16 + rng.normal(0, 0.3, n),
    })
    for col, values in (tail or {}).items():
        df.loc[df.index[-len(values):], col] = values
    return analysis.enrich_daily(df)


def score(daily, acts=None):
    return fitness_agent.compute_custom_readiness(daily, acts if acts is not None else pd.DataFrame(), sleep_need=7.25)


def test_steady_signals_score_high():
    r = score(make_daily())
    assert r["label"] in ("PRIMED", "READY")
    assert set(r["components"]) == {"hrv", "rhr", "sleep"}
    assert r["flags"] == []


def test_rest_week_does_not_lower_readiness():
    daily = make_daily()
    acts = pd.DataFrame({"date": ["2026-06-10", "2026-06-20"], "training_load": [80.0, 90.0]})
    assert score(daily, acts)["score"] == score(daily)["score"]


def test_low_hrv_alone_is_not_rest():
    r = score(make_daily(tail={"hrv_overnight_avg": [30.0] * 7}))
    assert "HRV below range" in r["flags"]
    assert r["score"] >= 50
    assert r["drivers"][0].startswith("HRV 7-night")


def test_hrv_low_and_rhr_high_together_cap_at_rest():
    r = score(make_daily(tail={"hrv_overnight_avg": [30.0] * 7, "resting_hr": [64.0] * 7}))
    assert {"HRV below range", "RHR elevated"} <= set(r["flags"])
    assert r["score"] <= 45 and r["label"] == "LOW"
    assert "together" in r["drivers"][0]


def test_single_low_night_keeps_hrv_flag_balanced():
    daily = make_daily(tail={"hrv_overnight_avg": [30.0]})
    assert daily.iloc[-1]["hrv_flag"] == "balanced"


def test_rhr_flag_needs_more_than_five_percent():
    # RHR alternating 52/58 (mean 55, SD 3): 58.5 is >5 % over 55, the old rule,
    # but only +1.2 SD.
    daily = make_daily(tail={"resting_hr": [52.0, 58.0] * 30 + [58.5]})
    last = daily.iloc[-1]
    assert last["resting_hr"] > 1.05 * last["rhr_baseline_28d"]
    assert last["rhr_z"] < 1.5
    assert not bool(last["rhr_elevated"])


def test_sleep_debt_counts_in_score_and_drivers():
    r = score(make_daily(sleep_h=6.25))
    assert r["sleep_debt_h"] == 7.0
    assert any(d.startswith("7-night sleep debt 7.0 h") for d in r["drivers"])


def test_rolling_sleep_debt_pays_back_half_of_surplus():
    assert analysis.rolling_sleep_debt([6.0, 6.0, 9.25], 7.25) == 1.5  # 2.5 short - 0.5 * 2.0 surplus
    assert analysis.rolling_sleep_debt([9.0, 9.0], 7.25) == 0.0
    assert analysis.rolling_sleep_debt([None, float("nan")], 7.25) is None
