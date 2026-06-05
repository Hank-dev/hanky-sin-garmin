"""AI analysis via the Anthropic API.

Sends the compact metrics summary (NOT raw time-series) to Claude and asks for
three things: a plain-English readiness summary, flagged trends/anomalies, and
concrete training advice grounded in the HRV / RHR / sleep / load signals.
"""
import json
import anthropic
import config

SYSTEM = """You are an evidence-based endurance and recovery coach analysing one
athlete's Garmin data. You receive a JSON summary of recent metrics, not raw
signals. Be specific, quantitative, and honest.

Ground every claim in the data provided. Reason like a physiologist:
- Suppressed overnight HRV and/or resting HR elevated >~5% above baseline,
  especially together, indicate under-recovery, accumulated fatigue, illness
  onset, or high life stress -> bias toward easier training or rest.
- Balanced/rising HRV with stable/low RHR and good sleep -> the body can absorb
  hard training.
- Chronic sleep debt blunts adaptation and elevates injury/illness risk
  regardless of how training 'feels'.
- ACWR is one input, not truth: ~0.8-1.3 is the often-cited sweet spot, >1.5 is
  a load spike worth respecting, but the metric is statistically contested.

Output exactly these three sections as markdown:
## Readiness today
One short paragraph: train hard / train easy / rest, and why, citing the numbers.
## Trends & anomalies (last ~2 weeks)
Bullet points. Flag anything moving the wrong way or out of pattern. If a metric
is missing, say so rather than inventing it.
## What to do
2-4 concrete, actionable recommendations for the next few days.

Do not pad. Do not give medical disclaimers. If data is too sparse to judge,
say that plainly."""

QUESTION_SYSTEM = """You answer an athlete's health and training questions using
only the compact Garmin metrics, capacity-envelope model, stress-leak map,
computed grappling metrics, pre-sleep discovery patterns, and check-in context
provided. You are not a doctor and you must not diagnose disease.

Rules:
- Ground every claim in the provided numbers. If the data does not answer the
  question, say what is missing.
- If the question is a broad "analyse my health" request, give a concise
  whole-system readout across recovery, sleep, stress, load, and correlations.
- Distinguish clearly between data-supported recovery/load patterns and
  symptoms the user reports.
- Be practical: give 2-4 concrete next steps for the next 24-72 hours when the
  data supports it.
- If the question mentions chest pain, fainting, severe shortness of breath,
  neurological symptoms, or rapidly worsening symptoms, tell the user to seek
  urgent medical care.
- Keep the answer concise.

Output markdown with these sections:
## Answer
Direct answer to the question.
## What the metrics say
Bullets with the relevant numbers and caveats.
## Next steps
2-4 concrete actions."""


def analyze(summary: dict, model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI analysis._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=1200,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": "Here is my recent Garmin summary as JSON:\n\n"
                       + json.dumps(summary, indent=2)
                       + "\n\nAnalyse it.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def answer_question(
    question: str,
    summary: dict,
    capacity: dict | None = None,
    stress_leak_map: dict | None = None,
    grappling_sessions: list[dict] | None = None,
    prebed_discovery: dict | None = None,
    chat_history: list[dict] | None = None,
    model: str | None = None,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI questions._"
    question = (question or "").strip()
    if not question:
        return "_Ask a question first._"
    payload = {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "previous_chat": chat_history or [],
    }
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=1000,
        system=QUESTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Answer my question using this compact local health context:\n\n"
                       + json.dumps(payload, indent=2)
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
