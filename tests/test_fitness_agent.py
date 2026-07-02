import importlib

import config
import db
import pandas as pd
import pytest


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "fitness-agent.db"
    monkeypatch.setattr(config, "DB_PATH", str(dbfile))
    importlib.reload(db)
    db.config.DB_PATH = str(dbfile)
    db.init_db()
    yield dbfile
    importlib.reload(db)


def test_parse_fitness_command_routes_subcommands():
    import fitness_agent

    assert fitness_agent.parse_fitness_command("status") == ("status", "")
    assert fitness_agent.parse_fitness_command("plan today") == ("plan", "today")
    assert fitness_agent.parse_fitness_command("simulate hard lift") == ("simulate", "hard lift")
    assert fitness_agent.parse_fitness_command("session upper") == ("session", "upper")
    assert fitness_agent.parse_fitness_command("workout bjj") == ("session", "bjj")
    assert fitness_agent.parse_fitness_command("response") == ("response", "")
    assert fitness_agent.parse_fitness_command("recover") == ("recovery", "")
    assert fitness_agent.parse_fitness_command("") == ("help", "")


def test_format_status_uses_recovery_and_capacity_context():
    import fitness_agent

    text = fitness_agent.format_status({
        "as_of": "2026-06-26",
        "latest": {
            "hrv_overnight_avg": 31,
            "resting_hr": 63,
            "sleep_hours": 5.9,
            "sleep_score": 70,
            "body_battery_high": 44,
            "stress_avg": 31,
        },
        "readiness": {"zone": "yellow", "value": 60, "reasons": ["HRV low", "sleep debt"]},
        "capacity": {"zone": "red", "flags": ["HRV suppressed", "short sleep"]},
    })

    assert "Status 2026-06-26: YELLOW" in text
    assert "HRV 31 ms" in text
    assert "Sleep 5.9h/70" in text
    assert "Capacity RED" in text
    assert "HRV low" in text


def test_plan_today_biases_to_rehab_when_capacity_red_and_injury_memory_present():
    import fitness_agent

    text = fitness_agent.format_plan({
        "as_of": "2026-06-26",
        "readiness": {"zone": "yellow", "value": 60, "reasons": ["HRV low vs baseline"]},
        "capacity": {"zone": "red", "flags": ["short sleep"]},
        "coach_memory": {"injuries": ["hip irritation", "knee inflammation"]},
        "predictive_readiness": {"load_guidance": {"safe_load": 33, "zone": "green"}},
    })

    assert "Today: RECOVERY / REHAB" in text
    assert "No BJJ sparring" in text
    assert "cap load ~33" in text
    assert "hip/knee" in text


def test_log_checkin_writes_daily_checkin_and_note(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-06-26")
    text = fitness_agent.handle_log("pain 4 fatigue 3 energy 6 hip irritated after walk")

    checkins = db.load_checkins_df()
    memories = db.load_memory_df(status="active")
    assert "Logged check-in for 2026-06-26" in text
    assert int(checkins.iloc[0]["pain"]) == 4
    assert int(checkins.iloc[0]["fatigue"]) == 3
    assert int(checkins.iloc[0]["energy"]) == 6
    assert "hip irritated" in checkins.iloc[0]["note"]
    assert len(memories) == 1
    assert memories.iloc[0]["category"] == "injury"


def test_start_default_experiment_creates_prebed_downshift(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-06-26")
    text = fitness_agent.handle_experiment("prebed")

    experiments = db.load_experiments_df(status="active")
    assert "Started experiment #" in text
    assert experiments.iloc[0]["name"] == "Pre-bed downshift"
    assert "hrv_overnight_avg" in experiments.iloc[0]["metrics"]
    assert experiments.iloc[0]["start_date"] == "2026-06-26"


def test_experiment_autopilot_suggests_prebed_when_no_active_experiments(temp_db):
    import fitness_agent

    text = fitness_agent.handle_experiment("suggest", ctx={
        "active_experiments": [],
        "readiness": {"zone": "yellow", "reasons": ["sleep debt 2.1h"]},
        "prebed_discovery": {
            "relationships": [{
                "label": "Pre-sleep HR median deviation vs sleep quality",
                "summary": "High pre-sleep HR costs sleep score.",
            }]
        },
    })

    assert "Recommended experiment: Pre-bed downshift" in text
    assert "/fitness experiment start prebed" in text
    assert "Hypothesis:" in text


def test_experiment_autopilot_status_reports_active_experiment(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-06-30")
    db.add_experiment({
        "name": "Pre-bed downshift",
        "hypothesis": "test",
        "metrics": ["hrv_overnight_avg", "sleep_score"],
        "baseline_days": 14,
        "start_date": "2026-06-26",
    })

    text = fitness_agent.handle_experiment("status")

    assert "Active experiment: Pre-bed downshift" in text
    assert "day 4" in text
    assert "Keep protocol" in text


def test_experiment_autopilot_complete_marks_active_complete(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-07-03")
    exp_id = db.add_experiment({
        "name": "Pre-bed downshift",
        "hypothesis": "test",
        "metrics": ["hrv_overnight_avg", "sleep_score"],
        "baseline_days": 14,
        "start_date": "2026-06-26",
    })

    text = fitness_agent.handle_experiment("complete")
    completed = db.load_experiments_df(status="complete")

    assert f"Completed experiment #{exp_id}" in text
    assert completed.iloc[0]["end_date"] == "2026-07-03"


def test_note_command_writes_structured_daily_event(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-06-26")
    text = fitness_agent.handle_note("late dinner 22:30 pizza")

    events = db.load_daily_events_df()
    assert "Logged event #" in text
    assert events.iloc[0]["event_type"] == "late_dinner"
    assert float(events.iloc[0]["value"]) == 22.5
    assert int(events.iloc[0]["severity"]) == 3
    assert "pizza" in events.iloc[0]["text"]


def test_notes_week_lists_and_deletes_events(temp_db, monkeypatch):
    import fitness_agent

    monkeypatch.setattr(fitness_agent, "_today", lambda: "2026-06-26")
    fitness_agent.handle_note("alcohol 3 beers")
    listing = fitness_agent.handle_notes("week")
    assert "Lifestyle notes this week" in listing
    assert "alcohol" in listing
    assert "#1" in listing

    deleted = fitness_agent.handle_notes("delete 1")
    assert deleted == "Deleted event #1."
    assert db.load_daily_events_df().empty


def test_status_plan_and_why_include_recent_event_context():
    import fitness_agent

    recent_events = {
        "summary": "alcohol, late dinner",
        "confounders": [
            {"id": 1, "date": "2026-06-25", "event_type": "alcohol", "text": "3 beers"},
            {"id": 2, "date": "2026-06-25", "event_type": "late_dinner", "text": "22:30 pizza"},
        ],
    }
    ctx = {
        "as_of": "2026-06-26",
        "latest": {"hrv_overnight_avg": 31, "resting_hr": 63, "sleep_hours": 5.9, "sleep_score": 70},
        "readiness": {"zone": "yellow", "value": 60, "reasons": ["HRV low"]},
        "capacity": {"zone": "yellow", "flags": []},
        "predictive_readiness": {"load_guidance": {}},
        "recent_events": recent_events,
        "prebed_discovery": {"relationships": []},
        "early_waking": {"latest": {}},
    }

    assert "Confounders: alcohol, late dinner" in fitness_agent.format_status(ctx)
    assert "Interpret recovery with context" in fitness_agent.format_plan(ctx)
    assert "Recent context/confounders" in fitness_agent.format_why(ctx, "hrv")


def test_session_generator_upper_uses_readiness_context_and_strength_targets():
    import fitness_agent

    ctx = {
        "readiness": {"zone": "green", "reasons": ["good recovery"]},
        "capacity": {"zone": "green", "flags": []},
        "latest": {"sleep_hours": 7.5},
        "predictive_readiness": {"load_guidance": {"safe_load": 88}},
        "coach_memory": {},
        "recent_events": {"items": [], "confounders": [], "summary": ""},
        "strength_recent": {
            "status": "ok",
            "exercise_rows": [
                {"name": "Bench Press", "best_set": "80 kg x 5"},
                {"name": "Chest-supported Row", "best_set": "70 kg x 8"},
                {"name": "Lat Pulldown", "best_set": "65 kg x 10"},
            ],
        },
    }

    text = fitness_agent.format_session(ctx, "upper")

    assert "Session: Upper-body strength / rehab bias" in text
    assert "Readiness: GREEN" in text
    assert "Bench press" in text
    assert "80 kg x 5" in text
    assert "cap Garmin load ~88" in text


def test_session_generator_rehab_when_capacity_red_and_hip_context():
    import fitness_agent

    ctx = {
        "readiness": {"zone": "yellow", "reasons": ["HRV low"]},
        "capacity": {"zone": "red", "flags": ["short sleep"]},
        "latest": {"sleep_hours": 5.8},
        "predictive_readiness": {"load_guidance": {}},
        "coach_memory": {"injuries": ["hip irritation"]},
        "recent_events": {
            "summary": "alcohol",
            "items": [{"event_type": "alcohol", "text": "2 beers"}],
            "confounders": [{"event_type": "alcohol", "text": "2 beers"}],
        },
        "strength_recent": {"status": "ok", "exercise_rows": []},
    }

    text = fitness_agent.format_session(ctx, "bjj")

    assert "Recovery / rehab session" in text
    assert "Mode recovery" in text
    assert "Confounders: alcohol" in text
    assert "no hip/knee-irritating movements" in text
    assert "no grinders" in text


def _daily_rows(hrv_values, rhr_values=None):
    rhr_values = rhr_values or [60] * len(hrv_values)
    return pd.DataFrame([
        {
            "date": f"2026-06-{i + 1:02d}",
            "hrv_overnight_avg": hrv,
            "resting_hr": rhr_values[i],
            "sleep_hours": 7.5,
            "sleep_score": 82,
            "body_battery_high": 80,
        }
        for i, hrv in enumerate(hrv_values)
    ])


def test_session_response_detects_hard_hit_after_training():
    import fitness_agent

    daily = _daily_rows([50, 51, 49, 50, 52, 50, 51, 50, 39], [60, 60, 61, 60, 60, 59, 60, 60, 66])
    activities = pd.DataFrame([
        {"date": "2026-06-08", "name": "Hard lifting", "training_load": 130, "duration_s": 3600},
    ])
    result = fitness_agent.compute_session_response(daily, activities, pd.DataFrame(), pd.DataFrame())
    text = fitness_agent.format_session_response(result)

    assert result["verdict"] == "hard_hit"
    assert "HARD HIT" in text
    assert "HRV" in text
    assert "reduce next similar session" in text


def test_recovery_speed_model_learns_average_days_to_recover():
    import fitness_agent

    daily = _daily_rows(
        [50, 51, 49, 50, 52, 50, 51, 50, 42, 50, 51, 49, 50, 41, 49, 50],
        [60, 60, 61, 60, 60, 59, 60, 60, 64, 61, 60, 60, 60, 65, 62, 60],
    )
    activities = pd.DataFrame([
        {"date": "2026-06-08", "name": "Hard lifting", "training_load": 130, "duration_s": 3600},
        {"date": "2026-06-13", "name": "BJJ", "training_load": 125, "duration_s": 3600},
    ])

    model = fitness_agent.compute_recovery_speed_model(daily, activities, pd.DataFrame(), pd.DataFrame())
    text = fitness_agent.format_recovery_speed(model)

    assert model["n"] == 2
    assert model["avg_days"] >= 2
    assert "Recovery speed" in text
    assert "Recent:" in text


def test_recovery_score_converts_hard_hit_to_low_score():
    import fitness_agent

    response = {
        "status": "ready",
        "verdict": "hard_hit",
        "metrics": {
            "hrv_overnight_avg": {"delta": -17},
            "resting_hr": {"delta": 4},
            "sleep_hours": {"delta": -1.2},
            "body_battery_high": {"delta": -40},
        },
        "confounders": [],
    }

    score = fitness_agent.compute_recovery_score(response, {"zone": "red"})

    assert score["status"] == "ready"
    assert score["score"] <= 45
    assert score["zone"] in {"poor", "under-recovered"}
    assert any("HRV" in d for d in score["drivers"])


def test_telegram_bot_routes_fitness_command(monkeypatch):
    import sys
    import types

    anthropic_stub = types.ModuleType("anthropic")
    setattr(anthropic_stub, "Anthropic", lambda *a, **k: None)
    sys.modules.setdefault("anthropic", anthropic_stub)
    import telegram_bot

    calls = []
    monkeypatch.setattr(telegram_bot, "send_chat_action", lambda chat_id: None)
    monkeypatch.setattr(telegram_bot.fitness_agent, "handle_fitness_command", lambda arg: calls.append(arg) or "ok")

    assert telegram_bot.handle_authorized_command("/fitness", "status", 123) == "ok"
    assert calls == ["status"]
