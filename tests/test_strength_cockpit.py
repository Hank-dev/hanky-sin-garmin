import pandas as pd
import plotly.graph_objects as go

import cockpit


def test_readiness_badge_renders_value():
    html = cockpit.strength_readiness_badge({
        "readiness_score": 72, "readiness_level": "READY",
        "hrv_status": "BALANCED", "body_battery_start": 84,
    })
    assert isinstance(html, str)
    assert "72" in html
    assert "READY" in html


def test_readiness_badge_handles_empty():
    html = cockpit.strength_readiness_badge({})
    assert isinstance(html, str)
    assert "—" in html or "-" in html


def test_session_card_renders_tonnage():
    html = cockpit.strength_session_card(
        {"name": "Push Day", "date": "2026-06-05"},
        {"total_volume_kg": 5000.0, "working_sets": 12, "top_est_1rm_kg": 120.0},
    )
    assert "Push Day" in html
    assert "5000" in html or "5,000" in html


def test_onerm_trend_returns_figure():
    df = pd.DataFrame([
        {"date": "2026-06-01", "best_est_1rm_kg": 100.0, "is_pr": True},
        {"date": "2026-06-05", "best_est_1rm_kg": 105.0, "is_pr": True},
    ])
    fig = cockpit.strength_onerm_trend(df, "Bench Press")
    assert isinstance(fig, go.Figure)
