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


def test_answer_question_accepts_strength_kwarg_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.answer_question("q", {"a": 1}, strength={"x": 1})
    assert "ANTHROPIC_API_KEY" in out
