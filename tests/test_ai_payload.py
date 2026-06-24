import ai


def test_question_payload_includes_strength_and_question():
    payload = ai._question_payload(
        question="how is my bench?",
        summary={"a": 1},
        capacity={"c": 2},
        stress_leak_map={"s": 3},
        grappling_sessions=[{"g": 4}],
        prebed_discovery={"p": 5},
        chat_history=[{"role": "user", "content": "hi"}],
        strength={"standards": {"overall": {"level": "Intermediate"}}},
    )
    assert payload["question"] == "how is my bench?"
    assert payload["metrics_summary"] == {"a": 1}
    assert payload["strength_profile"] == {"standards": {"overall": {"level": "Intermediate"}}}


def test_question_payload_defaults_strength_to_empty():
    payload = ai._question_payload("q", {}, None, None, None, None, None, None)
    assert payload["strength_profile"] == {}


def test_question_payload_includes_early_waking_summary():
    payload = ai._question_payload(
        "q", {}, None, None, None, None, None,
        early_waking={"status": "ready", "recent_meaningful_days": 2},
    )

    assert payload["early_waking"] == {"status": "ready", "recent_meaningful_days": 2}


def test_question_payload_includes_personal_sleep_need_summary():
    payload = ai._question_payload(
        "q", {}, None, None, None, None, None,
        personal_sleep_need={"status": "ready", "sleep_need_h": 7.6},
    )

    assert payload["personal_sleep_need"] == {"status": "ready", "sleep_need_h": 7.6}


def test_question_payload_includes_predictive_readiness_summary():
    payload = ai._question_payload(
        "q", {}, None, None, None, None, None,
        predictive_readiness={"status": "ready", "accuracy": {"mae": 4.2}},
    )

    assert payload["predictive_readiness"] == {"status": "ready", "accuracy": {"mae": 4.2}}


def test_answer_question_accepts_strength_kwarg_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.answer_question("q", {"a": 1}, strength={"x": 1})
    assert "ANTHROPIC_API_KEY" in out


def test_sleep_question_payload_is_sleep_scoped():
    payload = ai._sleep_question_payload(
        "why did I wake early?",
        {"latest": {"sleep_hours": 7.1}},
        [{"role": "user", "content": "hi"}],
        coach_memory={"patterns": [{"text": "late caffeine hurts sleep"}]},
    )

    assert payload["question"] == "why did I wake early?"
    assert payload["sleep_context"] == {"latest": {"sleep_hours": 7.1}}
    assert payload["previous_chat"] == [{"role": "user", "content": "hi"}]
    assert payload["coach_memory"] == {"patterns": [{"text": "late caffeine hurts sleep"}]}


def test_answer_sleep_question_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.answer_sleep_question("q", {"latest": {"sleep_hours": 7.1}})
    assert "ANTHROPIC_API_KEY" in out


def test_coach_session_note_no_key_returns_empty(monkeypatch):
    import config, ai, importlib
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    importlib.reload(ai)
    out = ai.coach_session_note({"status": "ok"}, {"day_type": "Push"}, [])
    assert out == ""


def test_coach_session_note_prompt_includes_coach_memory():
    prompt = ai._coach_session_note_prompt(
        {"status": "ok"},
        {"day_type": "Push"},
        [{"exercise": "Bench Press", "state": "hold"}],
        coach_memory={"injuries": [{"text": "left shoulder irritated"}]},
    )

    assert "Coach memory" in prompt
    assert "left shoulder irritated" in prompt


def test_strength_overview_feedback_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.strength_overview_feedback({"latest_session": {"name": "Lower"}})
    assert "ANTHROPIC_API_KEY" in out


def test_strength_overview_feedback_prompt_includes_coach_memory():
    prompt = ai._strength_overview_feedback_prompt(
        {"latest_session": {"name": "Lower"}},
        coach_memory={"goals": [{"text": "improve deadlift"}]},
    )

    assert "Coach memory" in prompt
    assert "improve deadlift" in prompt
