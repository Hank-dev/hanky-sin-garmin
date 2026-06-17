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


def test_standards_panel_renders_levels_and_need_profile():
    ok = cockpit.strength_standards_panel({
        "status": "ok",
        "overall": {"level": "Intermediate", "percentile": 55.0},
        "lifts": [{"name": "Back Squat", "level": "Intermediate", "percentile": 50.0,
                   "est_1rm_kg": 125.0, "ratio": 1.25}],
    })
    assert "Back Squat" in ok and "Intermediate" in ok
    need = cockpit.strength_standards_panel({"status": "need_profile",
                                             "missing": ["bodyweight"]})
    assert isinstance(need, str) and "bodyweight" in need.lower()


def test_balance_panel_renders_ratio_and_flag():
    html_out = cockpit.strength_balance_panel({
        "ratios": [{"label": "Bench : Squat", "ratio": 0.4, "low": 0.5,
                    "ideal": 0.66, "high": 0.8, "status": "under",
                    "weak_side": "bench-press", "reason": "upper vs lower"}],
        "left_right": [{"name": "Split Squat", "left_1rm_kg": 40.0,
                        "right_1rm_kg": 50.0, "diff_pct": 20.0, "flagged": True,
                        "stronger_side": "right"}],
    })
    assert "Bench : Squat" in html_out and "Split Squat" in html_out


def test_correlation_panel_ok_and_insufficient():
    fig = cockpit.strength_correlation_panel({
        "status": "ok", "n": 12, "correlation": 0.4,
        "insight": "Better lifts on higher-readiness days.",
        "buckets": {"Low": {"n": 4, "avg_rel_perf": 0.9, "pr_rate": 0.0, "avg_tonnage": 3000},
                    "High": {"n": 8, "avg_rel_perf": 0.98, "pr_rate": 0.25, "avg_tonnage": 4000}},
    })
    assert isinstance(fig, go.Figure)
    msg = cockpit.strength_correlation_panel({"status": "insufficient", "have": 3, "need": 8})
    assert isinstance(msg, str) and "8" in msg


def test_recovery_chip_renders_day_type():
    html = cockpit.strength_recovery_chip(
        {"zone": "red", "day_type": "Back off", "value": 30,
         "headline": "Back off — recovery red", "reasons": ["HRV below personal baseline"]})
    assert "Back off" in html
    assert "red" in html


def test_suggestion_hint_progress():
    html = cockpit.strength_suggestion_hint(
        {"state": "progress", "suggested_weight_kg": 102.5, "target_reps": 5,
         "last_weight_kg": 100.0, "stalls": 0, "reason": "all sets hit 5 reps at 100kg"})
    assert "102.5" in html
    assert "5" in html


def test_suggestion_hint_none_is_empty():
    assert cockpit.strength_suggestion_hint(None) == ""


def test_sensitivity_panel_lists_flagged():
    html = cockpit.strength_recovery_sensitivity_panel(
        [{"exercise": "Back Squat", "n": 6, "delta_pct": -8.0, "flagged": True,
          "note": "8% lower on low-recovery days"}])
    assert "Back Squat" in html
