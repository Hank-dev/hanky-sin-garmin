"""AI analysis via the Anthropic API.

Sends the compact metrics summary (NOT raw time-series) to Claude and asks for
three things: a plain-English readiness summary, flagged trends/anomalies, and
concrete training advice grounded in the HRV / RHR / sleep / load signals.
"""
import json
import re
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
say that plainly.

You may also receive coach_memory — durable, user-approved facts about this
athlete (goals, injuries, observed patterns, prior coaching). When present,
honor injuries when advising load, orient advice toward the athlete's goals,
build on prior coaching, and reference these facts naturally so the athlete
feels known. They are curated facts, not raw data."""

QUESTION_SYSTEM = """You answer an athlete's health and training questions using
only the compact Garmin metrics, capacity-envelope model, stress-leak map,
computed grappling metrics, pre-sleep discovery patterns, strength-training
profile (standards vs population, muscle-balance flags, lifting load, and any
readiness-vs-performance link), Health Lab panels (baseline-normalized recovery,
sleep regularity, respiratory watchlist, and fitness adaptation), and check-in
context provided. You are not a doctor and you must not diagnose disease.

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
2-4 concrete actions.

You may also receive coach_memory — durable, user-approved facts about this
athlete (goals, injuries, observed patterns, prior coaching). When present,
honor injuries when advising load, orient advice toward the athlete's goals,
build on prior coaching, and reference these facts naturally so the athlete
feels known. They are curated facts, not raw data."""


WEEKLY_SYSTEM = """You are an evidence-based endurance and recovery coach writing a
short weekly recap for one athlete from a compact JSON summary of the last
completed week (Mon–Sun) versus the prior week. Ground every claim in the
numbers. Be specific and concise; do not pad; give no medical disclaimers.

Output exactly these two markdown sections:
## Week in review
One short paragraph: what moved this week and why — cite HRV / RHR / sleep /
stress / load numbers and their deltas vs the prior week, the recovery-flag day
counts, and any notable best/worst day. If a metric is missing or the week is
sparse (low days_with_data), say so rather than inventing it.
## Focus next week
1-2 concrete priorities for the coming week, grounded in the data.

If the week is too sparse to judge, say that plainly in one line.

You may also receive coach_memory — durable, user-approved facts about this
athlete (goals, injuries, observed patterns, prior coaching). When present,
honor injuries when advising load, orient advice toward the athlete's goals,
build on prior coaching, and reference these facts naturally so the athlete
feels known. They are curated facts, not raw data."""


SUGGEST_SYSTEM = """You help maintain a coach's long-term memory of one athlete.
Given a compact metrics summary, the athlete's strength profile, and the memories
the coach ALREADY has, propose between 0 and 5 NEW durable facts worth remembering
for weeks or months. Never duplicate an existing memory. Never record transient
day-to-day noise (a single night's HRV, today's readiness). Only propose what a
good coach would want to remember long-term: stable patterns, goals, injuries, or
constraints implied by the data. If nothing durable stands out, return [].

Respond with ONLY a JSON array (no prose). Each item:
{"category": "goal|injury|pattern|coaching|note",
 "text": "<short fact>",
 "confidence": "low|med|high",   // optional
 "target_date": "YYYY-MM-DD",    // optional, goals
 "body_part": "<area>",          // optional, injuries
 "rationale": "<one short clause on why>"}"""


_MEMORY_CATEGORIES = ("goal", "injury", "pattern", "coaching", "note")


def _parse_memory_candidates(text: str) -> list[dict]:
    """Extract a JSON array of memory candidates from a model response.

    Tolerates ```json fences and surrounding prose. Drops items that aren't
    objects, lack a non-empty 'text', or carry an unknown 'category'. Keeps
    only known fields. Returns [] on any failure.
    """
    if not text:
        return []
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("["):
        span = re.search(r"\[.*\]", raw, re.DOTALL)
        raw = span.group(0) if span else raw
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category", "")).strip().lower()
        txt = str(it.get("text", "")).strip()
        if cat not in _MEMORY_CATEGORIES or not txt:
            continue
        cand = {"category": cat, "text": txt}
        for opt in ("confidence", "target_date", "body_part", "rationale"):
            v = it.get(opt)
            if v not in (None, ""):
                cand[opt] = str(v).strip()
        out.append(cand)
    return out


def suggest_memories(summary: dict, strength: dict | None = None,
                     existing_memories: dict | None = None,
                     model: str | None = None) -> list[dict]:
    if not config.ANTHROPIC_API_KEY:
        return []
    payload = {
        "metrics_summary": summary or {},
        "strength_profile": strength or {},
        "existing_memories": existing_memories or {},
    }
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=700,
        system=SUGGEST_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Propose new coach memories from this context:\n\n"
                       + json.dumps(payload, indent=2),
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_memory_candidates(text)


def _memory_block(coach_memory: dict | None) -> str:
    if not coach_memory:
        return ""
    return ("\n\nCoach memory (durable, user-approved facts about this athlete):\n\n"
            + json.dumps(coach_memory, indent=2))


def analyze(summary: dict, strength: dict | None = None,
            coach_memory: dict | None = None, model: str | None = None) -> str:
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
                       + "\n\nStrength-training profile:\n\n"
                       + json.dumps(strength or {}, indent=2)
                       + _memory_block(coach_memory)
                       + "\n\nAnalyse it.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def weekly_summary(week_payload: dict, coach_memory: dict | None = None,
                   model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable the weekly summary._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=900,
        system=WEEKLY_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Here is my completed-week summary as JSON:\n\n"
                       + json.dumps(week_payload, indent=2)
                       + _memory_block(coach_memory)
                       + "\n\nWrite the recap.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _question_payload(question, summary, capacity, stress_leak_map,
                      grappling_sessions, prebed_discovery, chat_history,
                      strength=None, health_research=None, coach_memory=None):
    return {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "health_research": health_research or {},
        "strength_profile": strength or {},
        "previous_chat": chat_history or [],
        "coach_memory": coach_memory or {},
    }


def answer_question(
    question: str,
    summary: dict,
    capacity: dict | None = None,
    stress_leak_map: dict | None = None,
    grappling_sessions: list[dict] | None = None,
    prebed_discovery: dict | None = None,
    chat_history: list[dict] | None = None,
    strength: dict | None = None,
    health_research: dict | None = None,
    coach_memory: dict | None = None,
    model: str | None = None,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI questions._"
    question = (question or "").strip()
    if not question:
        return "_Ask a question first._"
    payload = _question_payload(question, summary, capacity, stress_leak_map,
                                grappling_sessions, prebed_discovery, chat_history,
                                strength, health_research, coach_memory)
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
