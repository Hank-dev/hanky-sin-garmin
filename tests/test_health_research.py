import pandas as pd
import plotly.graph_objects as go

import analysis
import cockpit


def _daily_rows():
    start = pd.Timestamp("2026-05-01")
    rows = []
    for i in range(20):
        rows.append({
            "date": start + pd.Timedelta(days=i),
            "hrv_overnight_avg": 58 + (i % 4),
            "resting_hr": 50 + (i % 2),
            "sleep_seconds": 8 * 3600,
            "sleep_score": 84,
            "stress_avg": 24 + (i % 3),
            "steps": 7000 + i * 25,
            "intensity_minutes": 30,
            "body_battery_current": 72,
            "spo2_avg": 97.5,
            "respiration_avg": 14.0 + (i % 2) * 0.2,
            "hrv_baseline_low": None,
            "hrv_baseline_high": None,
        })
    rows[-1].update({
        "hrv_overnight_avg": 38,
        "resting_hr": 62,
        "sleep_seconds": 6 * 3600,
        "sleep_score": 55,
        "stress_avg": 72,
        "body_battery_current": 24,
        "spo2_avg": 91,
        "respiration_avg": 18.5,
    })
    return rows


def _sleep_timing():
    start = pd.Timestamp("2026-05-01")
    rows = []
    for i in range(20):
        jitter = 0 if i < 15 else i * 12
        sleep_start = start + pd.Timedelta(days=i, hours=23, minutes=jitter)
        sleep_end = sleep_start + pd.Timedelta(hours=8)
        rows.append({
            "date": start + pd.Timedelta(days=i),
            "sleep_start": sleep_start,
            "sleep_end": sleep_end,
            "sleep_midpoint": sleep_start + pd.Timedelta(hours=4),
        })
    return pd.DataFrame(rows)


def _activities():
    start = pd.Timestamp("2026-05-01")
    return pd.DataFrame([
        {
            "date": start + pd.Timedelta(days=i * 3),
            "name": "Easy Run",
            "type": "running",
            "duration_s": 1800 + i * 45,
            "distance_m": 5000,
            "avg_hr": 138 + i,
            "training_load": 45 + i * 4,
        }
        for i in range(7)
    ])


def test_enrich_daily_adds_prior_baseline_z_scores():
    daily = analysis.enrich_daily(pd.DataFrame(_daily_rows()))

    latest = daily.iloc[-1]

    assert latest["hrv_z"] < -1
    assert latest["rhr_z"] > 1
    assert latest["respiration_z"] > 1


def test_health_research_panels_flag_recovery_and_respiratory_watchlist():
    daily = analysis.enrich_daily(pd.DataFrame(_daily_rows()))
    activities = _activities()
    daily = analysis.compute_acwr(activities, daily)

    model = analysis.compute_health_research_panels(daily, activities, _sleep_timing())

    assert model["status"] == "ready"
    assert model["recovery"]["zone"] == "red"
    assert "HRV below personal baseline" in model["recovery"]["flags"]
    assert model["respiratory"]["zone"] == "red"
    assert any("SpO2" in flag for flag in model["respiratory"]["flags"])
    assert model["sleep_regularity"]["status"] == "ready"
    assert model["fitness"]["activity"]["sessions_28d"] == 7
    assert model["rows"]


def test_health_research_card_and_charts_render():
    daily = analysis.enrich_daily(pd.DataFrame(_daily_rows()))
    model = analysis.compute_health_research_panels(daily, _activities(), _sleep_timing())
    html = cockpit.health_research_card(model)

    assert "Health Lab" in html
    assert "Recovery and resilience" in html
    assert isinstance(cockpit.chart_recovery_deviation(pd.DataFrame(model["rows"])), go.Figure)
    assert isinstance(cockpit.chart_sleep_regularity(pd.DataFrame(model["rows"])), go.Figure)
    assert isinstance(cockpit.chart_respiratory_watchlist(pd.DataFrame(model["rows"])), go.Figure)
    assert isinstance(cockpit.chart_foot_pace(model), go.Figure)
