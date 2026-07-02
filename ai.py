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
feels known. Notes and injuries can include metadata_date/metadata_time; use
that timing context when judging recency. They are curated facts, not raw data.

The athlete may also be running self-experiments (before/after tests of a habit
or supplement). When experiments are provided, factor them in, but do not
attribute changes to an intervention beyond what the data supports."""

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
feels known. Notes and injuries can include metadata_date/metadata_time; use
that timing context when judging recency. They are curated facts, not raw data.

The athlete may also be running self-experiments (before/after tests of a habit
or supplement). When experiments are provided, factor them in, but do not
attribute changes to an intervention beyond what the data supports."""


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
feels known. Notes and injuries can include metadata_date/metadata_time; use
that timing context when judging recency. They are curated facts, not raw data.

The athlete may also be running self-experiments (before/after tests of a habit
or supplement). When experiments are provided, factor them in, but do not
attribute changes to an intervention beyond what the data supports."""

SLEEP_QUESTION_SYSTEM = """You answer one athlete's sleep questions using only a
compact derived sleep context: daily aggregate sleep metrics, personal sleep
need, recommended bedtime, early-for-recovery model, sleep timing regularity,
overnight HR/HRV, and prior chat. You do not receive raw Garmin payloads or raw
time-series data.

Rules:
- Ground every claim in the provided numbers. If the data does not answer the
  question, say what is missing.
- Do not present overlapping heuristic tags as proven causes. Use language like
  "signal", "consistent with", and "most visible factor".
- For early-for-recovery, explain that it estimates whether sleep ended before
  the modeled recovery window was covered; it is not a literal wake-up detector.
- Keep the answer practical and focused on tonight/tomorrow.
- If symptoms suggest sleep apnea, severe insomnia, chest pain, fainting, or
  rapidly worsening health, say this needs medical evaluation.

Output markdown with these sections:
## Answer
Direct answer to the question.
## What the sleep data says
Bullets with the relevant numbers and caveats.
## Tonight
2-4 concrete actions."""


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


INTERPRET_SYSTEM = """You interpret one N-of-1 self-experiment result for an
athlete. You receive a computed result: per-metric mean-before, mean-after, the
change, its 95% confidence interval, sample sizes, and a verdict. You do NOT see
raw daily data.

Be concise and honest. For each metric with a verdict, say in plain language what
the numbers suggest. Stress N-of-1 caveats: a before/after change can be caused by
confounders (seasonality, training load, life stress, sleep debt), and a wide or
zero-crossing confidence interval means the effect is not established. Do not
overclaim. If everything is 'insufficient_data', say more days are needed.
You are not a doctor; do not diagnose or prescribe.

Output two short markdown sections:
## What this suggests
## Caveats"""


COACH_NOTE_SYSTEM = (
    "You are a concise strength coach. Given today's recovery verdict, the "
    "linear-progression plan, and a compact strength summary, write ONE or TWO "
    "sentences of practical guidance for today's session. Be specific about "
    "which lifts to push, hold, or back off, and why (tie to recovery). No "
    "lists, no preamble, no diagnosis. Plain text. You may also receive "
    "coach_memory: durable, user-approved facts about the athlete. Honor goals, "
    "injuries, constraints, observed patterns, and prior coaching when relevant."
)

STRENGTH_FEEDBACK_SYSTEM = """You are a concise strength coach reviewing one
athlete's latest completed strength session. You receive compact derived
strength data only: latest-session totals, exercise rollups, recent trend
deltas, recent PRs, standards/balance/readiness summaries, and recovery context.
You do not receive raw set ids or raw Garmin time-series data.

Ground every claim in the supplied numbers. Keep it practical and specific.
You may also receive coach_memory: durable, user-approved facts about this
athlete. When present, honor goals, injuries, constraints, observed patterns,
and prior coaching. Reference these facts naturally when relevant.

Output exactly these markdown sections:
## Session read
One short paragraph on what the latest session shows.
## Trend signals
2-4 bullets covering volume, top estimated 1RM, PRs, recovery/readiness, or
balance flags when present.
## Next session
2-3 concrete coaching actions."""


def _coach_session_note_prompt(
    strength_summary: dict,
    verdict: dict,
    plan: list,
    coach_memory: dict | None = None,
) -> str:
    return (
        "Recovery verdict:\n\n" + json.dumps(verdict or {}, indent=2)
        + "\n\nToday's progression plan (per main lift):\n\n"
        + json.dumps(plan or [], indent=2)
        + "\n\nStrength summary:\n\n"
        + json.dumps(strength_summary or {}, indent=2)
        + _memory_block(coach_memory)
        + "\n\nWrite the session note."
    )


def coach_session_note(strength_summary: dict, verdict: dict,
                       plan: list, model: str | None = None,
                       coach_memory: dict | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return ""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=model or config.ANTHROPIC_MODEL,
            max_tokens=160,
            system=COACH_NOTE_SYSTEM,
            messages=[{
                "role": "user",
                "content": _coach_session_note_prompt(
                    strength_summary, verdict, plan, coach_memory=coach_memory),
            }],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except Exception:
        return ""


def _strength_overview_feedback_prompt(
    context: dict,
    coach_memory: dict | None = None,
) -> str:
    return (
        "Strength context:\n\n"
        + json.dumps(context or {}, indent=2)
        + _memory_block(coach_memory)
        + "\n\nWrite the feedback."
    )


def strength_overview_feedback(context: dict, model: str | None = None,
                               coach_memory: dict | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI strength feedback._"
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=model or config.ANTHROPIC_MODEL,
            max_tokens=420,
            system=STRENGTH_FEEDBACK_SYSTEM,
            messages=[{
                "role": "user",
                "content": _strength_overview_feedback_prompt(
                    context, coach_memory=coach_memory),
            }],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except Exception as e:
        return f"_Strength feedback failed: {e}_"


_MEMORY_CATEGORIES = ("goal", "injury", "pattern", "coaching", "note")


def _parse_memory_candidates(text: str) -> list[dict]:
    """Extract a JSON array of memory candidates from a model response.

    Tolerates ```json fences, leading/trailing prose, and stray brackets in
    prose: it tries a straight parse first, then scans each '[' with a JSON
    decoder that ignores trailing content and returns the first valid array.
    Drops items that aren't objects, lack a non-empty 'text', or carry an
    unknown 'category'. Keeps only known fields. Returns [] on any failure.
    """
    if not text:
        return []
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    items = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            items = parsed
    except (ValueError, TypeError):
        pass
    if items is None:
        decoder = json.JSONDecoder()
        idx = raw.find("[")
        while idx != -1:
            try:
                parsed, _ = decoder.raw_decode(raw, idx)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, list):
                items = parsed
                break
            idx = raw.find("[", idx + 1)
    if items is None:
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


def _suggest_memories_payload(
    summary: dict,
    strength: dict | None = None,
    existing_memories: dict | None = None,
) -> dict:
    return {
        "metrics_summary": summary or {},
        "strength_profile": strength or {},
        "existing_memories": existing_memories or {},
    }


def suggest_memories(summary: dict, strength: dict | None = None,
                     existing_memories: dict | None = None,
                     model: str | None = None) -> list[dict]:
    if not config.ANTHROPIC_API_KEY:
        return []
    payload = _suggest_memories_payload(summary, strength, existing_memories)
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


def _experiment_block(active_experiments: list | None) -> str:
    if not active_experiments:
        return ""
    return ("\n\nActive experiments the athlete is currently running:\n\n"
            + json.dumps(active_experiments, indent=2))


def analyze(summary: dict, strength: dict | None = None,
            coach_memory: dict | None = None, active_experiments: list | None = None,
            model: str | None = None) -> str:
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
                       + _experiment_block(active_experiments)
                       + "\n\nAnalyse it.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


DAILY_BRIEF_SYSTEM = """You write a ultra-compact daily recovery brief for one athlete.
Given a compact JSON metrics summary, output EXACTLY this format (in Norwegian):

One line: **VERDICT** — one short sentence (train hard / hold / rest + why).
Then max 3 bullets with the most important signals (only what's unusual or actionable).
Then 1-2 bullets: "Gjør:" with concrete next steps.

Rules:
- Max 8 lines total. No headers. No paragraphs. No disclaimers.
- Only flag what matters today — skip restating normal values.
- Cite the key number inline. If nothing is unusual, say so plainly.
- Norwegian only.

You may receive coach_memory and active_experiments — factor in injuries
and goals, but keep it to the format above."""


def daily_brief(summary: dict, strength: dict | None = None,
                coach_memory: dict | None = None,
                active_experiments: list | None = None,
                model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI analysis._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=350,
        system=DAILY_BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Metrics summary:\n\n"
                       + json.dumps(summary, indent=2)
                       + "\n\nStrength profile:\n\n"
                       + json.dumps(strength or {}, indent=2)
                       + _memory_block(coach_memory)
                       + _experiment_block(active_experiments),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def weekly_summary(week_payload: dict, coach_memory: dict | None = None,
                   active_experiments: list | None = None,
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
                       + _experiment_block(active_experiments)
                       + "\n\nWrite the recap.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _sleep_question_payload(question, sleep_context, chat_history,
                            coach_memory=None, active_experiments=None):
    return {
        "question": question,
        "sleep_context": sleep_context or {},
        "previous_chat": chat_history or [],
        "coach_memory": coach_memory or {},
        "active_experiments": active_experiments or [],
    }


def answer_sleep_question(
    question: str,
    sleep_context: dict,
    chat_history: list[dict] | None = None,
    coach_memory: dict | None = None,
    active_experiments: list | None = None,
    model: str | None = None,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI sleep questions._"
    question = (question or "").strip()
    if not question:
        return "_Ask a sleep question first._"
    payload = _sleep_question_payload(
        question,
        sleep_context,
        chat_history,
        coach_memory=coach_memory,
        active_experiments=active_experiments,
    )
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=900,
        system=SLEEP_QUESTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Answer my sleep question using this compact local context:\n\n"
                       + json.dumps(payload, indent=2)
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _question_payload(question, summary, capacity, stress_leak_map,
                      grappling_sessions, prebed_discovery, chat_history,
                      strength=None, health_research=None, coach_memory=None,
                      active_experiments=None, early_waking=None,
                      personal_sleep_need=None, predictive_readiness=None):
    return {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "personal_sleep_need": personal_sleep_need or {},
        "early_waking": early_waking or {},
        "health_research": health_research or {},
        "predictive_readiness": predictive_readiness or {},
        "strength_profile": strength or {},
        "previous_chat": chat_history or [],
        "coach_memory": coach_memory or {},
        "active_experiments": active_experiments or [],
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
    active_experiments: list | None = None,
    model: str | None = None,
    early_waking: dict | None = None,
    personal_sleep_need: dict | None = None,
    predictive_readiness: dict | None = None,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI questions._"
    question = (question or "").strip()
    if not question:
        return "_Ask a question first._"
    payload = _question_payload(
        question, summary, capacity, stress_leak_map,
        grappling_sessions, prebed_discovery, chat_history,
        strength=strength,
        health_research=health_research,
        coach_memory=coach_memory,
        active_experiments=active_experiments,
        early_waking=early_waking,
        personal_sleep_need=personal_sleep_need,
        predictive_readiness=predictive_readiness,
    )
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


def interpret_experiment(result: dict, model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable experiment interpretation._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=600,
        system=INTERPRET_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Interpret this experiment result:\n\n"
                       + json.dumps(result, indent=2),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
