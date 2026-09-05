"""Telegram-first fitness command center for Hermes.

This module is deliberately deterministic: it wraps the existing Garmin Coach
analytics into compact commands that can run from Telegram or the shell without
calling an LLM. Hermes can still use the same commands as a substrate for richer
agentic coaching.
"""
from __future__ import annotations

import argparse
import re
from datetime import date, timedelta
from typing import Any

import pandas as pd

import analysis
import config
import db


def _today() -> str:
    return date.today().isoformat()


def _num(value: Any, digits: int | None = None) -> float | int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if digits is None:
        return int(f) if f.is_integer() else f
    return round(f, digits)


def _fmt(value: Any, suffix: str = "", digits: int | None = None, missing: str = "-") -> str:
    n = _num(value, digits)
    if n is None:
        return missing
    return f"{n}{suffix}"


def _strip_model(model: Any) -> Any:
    if isinstance(model, dict):
        return {k: _strip_model(v) for k, v in model.items() if k not in {"rows", "chart_rows", "backtest_rows"}}
    if isinstance(model, list):
        return [_strip_model(v) for v in model[:8]]
    return model


def parse_fitness_command(text: str) -> tuple[str, str]:
    """Return (subcommand, argument) from a /fitness payload."""
    text = (text or "").strip()
    if not text:
        return "help", ""
    head, _, tail = text.partition(" ")
    aliases = {
        "today": "status",
        "readiness": "status",
        "coach": "plan",
        "scenario": "simulate",
        "sim": "simulate",
        "why": "why",
        "log": "log",
        "note": "note",
        "notes": "notes",
        "session": "session",
        "workout": "session",
        "train": "session",
        "lift": "session",
        "response": "response",
        "respond": "response",
        "recovery": "recovery",
        "recover": "recovery",
        "experiment": "experiment",
        "exp": "experiment",
        "våknet": "våknet",
        "woke": "våknet",
        "early_wake": "våknet",
        "tidlig": "våknet",
    }
    cmd = aliases.get(head.lower(), head.lower())
    if cmd not in {"help", "status", "plan", "simulate", "log", "note", "notes", "session", "response", "recovery", "experiment", "why", "våknet"}:
        return "help", text
    return cmd, tail.strip()


EVENT_LABELS = {
    "late_dinner": "late dinner",
    "alcohol": "alcohol",
    "travel": "travel",
    "hotel_sleep": "hotel sleep",
    "caffeine_late": "late caffeine",
    "illness": "illness",
    "work_stress": "work stress",
    "poor_food": "poor food",
    "high_salt": "high salt",
    "sauna": "sauna",
    "breathwork": "breathwork",
    "pain_event": "pain event",
    "supplement": "supplement",
    "note": "note",
}

RECOVERY_CONFOUNDERS = {
    "alcohol", "late_dinner", "travel", "hotel_sleep", "caffeine_late",
    "illness", "work_stress", "poor_food", "high_salt",
}


def _iso_days_ago(days: int, anchor: str | None = None) -> str:
    base = pd.to_datetime(anchor or _today(), errors="coerce")
    if pd.isna(base):
        base_date = date.today()
    else:
        base_date = base.date()
    return (base_date - timedelta(days=days)).isoformat()


def _fmt_event_type(event_type: str) -> str:
    return EVENT_LABELS.get(str(event_type or ""), str(event_type or "").replace("_", " "))


def _format_event_row(row: Any, include_date: bool = False) -> str:
    getter = row.get if hasattr(row, "get") else lambda k, default=None: getattr(row, k, default)
    label = _fmt_event_type(getter("event_type"))
    text = str(getter("text") or "").strip()
    value = getter("value")
    try:
        value = None if pd.isna(value) else value
    except (TypeError, ValueError):
        pass
    if value is not None and not text:
        text = _fmt(value)
    prefix = ""
    if include_date:
        prefix = f"{str(getter('date'))[:10]}: "
    suffix = f" — {text}" if text and text.lower() != label.lower() else ""
    event_id = getter("id")
    id_text = f"#{int(event_id)} " if event_id is not None else ""
    return f"{prefix}{id_text}{label}{suffix}"


def summarize_recent_events(events: pd.DataFrame, anchor: str | None = None, days: int = 2) -> dict[str, Any]:
    if events is None or events.empty:
        return {"items": [], "confounders": [], "summary": ""}
    start = _iso_days_ago(days, anchor)
    frame = events.copy()
    frame["date_key"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    recent = frame[frame["date_key"] >= start].tail(12)
    items = [r.to_dict() for _, r in recent.iterrows()]
    confounders = [r for r in items if r.get("event_type") in RECOVERY_CONFOUNDERS]
    if confounders:
        summary = ", ".join(_fmt_event_type(r.get("event_type")) for r in confounders[-4:])
    else:
        summary = ", ".join(_fmt_event_type(r.get("event_type")) for r in items[-4:])
    return {"items": items, "confounders": confounders, "summary": summary}


def build_context() -> dict[str, Any]:
    """Load fresh DB data and run the existing deterministic analytics."""
    db.init_db()
    daily_raw = db.load_daily_df()
    if daily_raw.empty:
        return {"error": "no_data"}

    daily = analysis.enrich_daily(daily_raw)
    activities = db.load_activities_df()
    checkins = db.load_checkins_df()
    sleep_timing = db.load_sleep_timing_df()
    body_battery = db.load_body_battery_df()
    stress = db.load_stress_df()
    if not daily.empty:
        daily = analysis.compute_acwr(activities, daily)

    latest = daily.iloc[-1]
    as_of = str(latest.get("date"))[:10]
    coach_memory = analysis.build_coach_memory_digest(db.load_memory_df())
    recent_events = summarize_recent_events(db.load_daily_events_df(start=_iso_days_ago(7, as_of)), anchor=as_of, days=2)
    return {
        "as_of": as_of,
        "latest": {
            "hrv_overnight_avg": _num(latest.get("hrv_overnight_avg")),
            "resting_hr": _num(latest.get("resting_hr")),
            "sleep_hours": _num(latest.get("sleep_hours"), 1),
            "sleep_score": _num(latest.get("sleep_score")),
            "body_battery_high": _num(latest.get("body_battery_high")),
            "body_battery_current": _num(latest.get("body_battery_current")),
            "stress_avg": _num(latest.get("stress_avg")),
            "steps": _num(latest.get("steps")),
            "hr_bedtime": _num(latest.get("hr_bedtime")),
        },
        "summary": _strip_model(analysis.summarize(daily, activities)),
        "readiness": _strip_model(analysis.recovery_readiness(daily)),
        "capacity": _strip_model(analysis.compute_capacity_envelope(daily, activities, checkins)),
        "prebed_discovery": _strip_model(
            analysis.compute_prebed_discovery(daily, activities, sleep_timing, body_battery=body_battery, min_pairs=5)
        ),
        "predictive_readiness": _strip_model(analysis.compute_predictive_readiness(daily, activities)),
        "personal_sleep_need": _strip_model(analysis.compute_personal_sleep_need(daily, checkins)),
        "early_waking": _strip_model(analysis.compute_early_waking_model(daily, sleep_timing, body_battery)),
        "recommended_bedtime": _strip_model(analysis.compute_recommended_bedtime(daily, sleep_timing)),
        "stress_leaks": _strip_model(analysis.compute_stress_leak_map(daily, stress)),
        "recent_events": recent_events,
        "coach_memory": coach_memory,
        "strength_recent": _strip_model(_strength_context()),
        "active_experiments": _strip_model(
            analysis.summarize_active_experiments(db.load_experiments_df(status="active"), daily)
        ),
    }


def format_status(ctx: dict[str, Any]) -> str:
    if ctx.get("error"):
        return "No Garmin data found. Run sync first."
    latest = ctx.get("latest") or {}
    readiness = ctx.get("readiness") or {}
    capacity = ctx.get("capacity") or {}
    zone = str(readiness.get("zone") or "unknown").upper()
    cap_zone = str(capacity.get("zone") or "unknown").upper()
    reasons = (readiness.get("reasons") or capacity.get("flags") or [])[:3]
    lines = [
        f"Status {ctx.get('as_of', '-')}: {zone} ({_fmt(readiness.get('value'))}/100)",
        (
            f"HRV {_fmt(latest.get('hrv_overnight_avg'), ' ms')} · "
            f"RHR {_fmt(latest.get('resting_hr'), ' bpm')} · "
            f"Sleep {_fmt(latest.get('sleep_hours'), 'h', 1)}/{_fmt(latest.get('sleep_score'))}"
        ),
        (
            f"BB high {_fmt(latest.get('body_battery_high'))} · "
            f"Stress {_fmt(latest.get('stress_avg'))} · "
            f"Steps {_fmt(latest.get('steps'))}"
        ),
        f"Capacity {cap_zone}: " + ", ".join(capacity.get("flags") or []) if capacity.get("flags") else f"Capacity {cap_zone}",
    ]
    if reasons:
        lines.append("Limiter: " + "; ".join(str(r) for r in reasons))
    events = ctx.get("recent_events") or {}
    if events.get("summary"):
        label = "Confounders" if events.get("confounders") else "Context"
        lines.append(f"{label}: {events['summary']}")
    return "\n".join(lines[:6])


def _injury_text(ctx: dict[str, Any]) -> str:
    memory = ctx.get("coach_memory") or {}
    injuries = memory.get("injuries") or memory.get("injury") or []
    if isinstance(injuries, str):
        injuries = [injuries]
    return " ".join(str(x) for x in injuries).lower()


def format_plan(ctx: dict[str, Any]) -> str:
    if ctx.get("error"):
        return "No Garmin data found. Run sync first."
    readiness = ctx.get("readiness") or {}
    capacity = ctx.get("capacity") or {}
    predictive = ctx.get("predictive_readiness") or {}
    load_guidance = predictive.get("load_guidance") or {}
    r_zone = str(readiness.get("zone") or "unknown").lower()
    c_zone = str(capacity.get("zone") or "unknown").lower()
    injuries = _injury_text(ctx)
    safe_load = load_guidance.get("safe_load")

    rehab_bias = c_zone == "red" or r_zone == "red" or any(w in injuries for w in ("hip", "knee", "crutch"))
    if rehab_bias:
        headline = "Today: RECOVERY / REHAB"
        actions = [
            "No BJJ sparring; no hip/knee-irritating lifts.",
            "Upper-body rehab, easy walk, breathwork, or full rest.",
        ]
    elif r_zone == "green" and c_zone in {"green", "ready", "unknown"}:
        headline = "Today: PUSH WINDOW"
        actions = ["Train, but keep one clean stop-rule: no grinders.", "Good slot for strength progression or controlled conditioning."]
    else:
        headline = "Today: HOLD / TECHNIQUE"
        actions = ["Keep intensity moderate; prefer volume/skill over max effort.", "Stop if RPE drifts or pain changes mechanics."]

    if safe_load is not None:
        actions.append(f"If using Garmin load, cap load ~{_fmt(safe_load)} today.")
    events = ctx.get("recent_events") or {}
    if events.get("confounders"):
        actions.append(f"Interpret recovery with context: {events.get('summary')} logged recently.")
    if any(w in injuries for w in ("hip", "knee")):
        actions.append("Bias around hip/knee tolerance, not ego or old BJJ identity.")
    reasons = "; ".join((readiness.get("reasons") or capacity.get("flags") or [])[:2])
    if reasons:
        actions.append("Why: " + reasons)
    return headline + "\n" + "\n".join(f"- {a}" for a in actions[:6])


SESSION_GOALS = {
    "": "best",
    "best": "best",
    "today": "best",
    "upper": "upper",
    "upper body": "upper",
    "push": "push",
    "pull": "pull",
    "lower": "lower",
    "legs": "lower",
    "leg": "lower",
    "rehab": "rehab",
    "recovery": "rehab",
    "bjj": "bjj",
    "jiujitsu": "bjj",
    "grappling": "bjj",
    "conditioning": "conditioning",
    "cardio": "conditioning",
}


def _strength_context() -> dict[str, Any]:
    try:
        return analysis.compute_strength_recent_overview(
            db.load_strength_sessions_df(),
            db.load_strength_sets_df(),
            db.load_exercises_df(),
            formula=config.ONE_RM_FORMULA,
        )
    except Exception as e:  # keep /fitness session robust if strength tables are mid-migration
        return {"status": "error", "message": str(e), "latest_session": None, "exercise_rows": []}


def _session_goal(arg: str) -> str:
    raw = (arg or "").strip().lower()
    return SESSION_GOALS.get(raw, SESSION_GOALS.get(raw.replace("-", " "), raw or "best"))


def _session_mode(ctx: dict[str, Any]) -> str:
    readiness = str((ctx.get("readiness") or {}).get("zone") or "unknown").lower()
    capacity = str((ctx.get("capacity") or {}).get("zone") or "unknown").lower()
    latest = ctx.get("latest") or {}
    events = ctx.get("recent_events") or {}
    if readiness == "red" or capacity == "red":
        return "recovery"
    if events.get("confounders") and any(
        e.get("event_type") in {"illness", "travel", "alcohol", "caffeine_late"}
        for e in events.get("confounders") or []
    ):
        return "conservative"
    if latest.get("sleep_hours") is not None and float(latest.get("sleep_hours") or 0) < 6:
        return "conservative"
    if readiness == "green" and capacity in {"green", "ready", "unknown"}:
        return "progression"
    return "moderate"


def _has_lower_body_constraint(ctx: dict[str, Any]) -> bool:
    injuries = _injury_text(ctx)
    event_text = " ".join(
        str(e.get("text") or "") + " " + str(e.get("event_type") or "")
        for e in ((ctx.get("recent_events") or {}).get("items") or [])
    ).lower()
    return any(w in (injuries + " " + event_text) for w in ("hip", "knee", "crutch", "pain_event"))


def _recent_exercise_targets(strength: dict[str, Any]) -> dict[str, str]:
    targets: dict[str, str] = {}
    for row in (strength or {}).get("exercise_rows") or []:
        name = str(row.get("name") or row.get("exercise_id") or "").lower()
        best = row.get("best_set")
        if not name or not best:
            continue
        for key in ("bench", "press", "row", "pulldown", "pull", "squat", "deadlift"):
            if key in name and key not in targets:
                targets[key] = str(best)
    return targets


def _line_exercise(name: str, prescription: str, note: str | None = None) -> str:
    suffix = f" ({note})" if note else ""
    return f"- {name} — {prescription}{suffix}"


def _session_exercises(goal: str, mode: str, lower_limited: bool, strength: dict[str, Any]) -> tuple[str, list[str]]:
    targets = _recent_exercise_targets(strength)
    intensity = {
        "progression": "RPE 7-8",
        "moderate": "RPE 6-7",
        "conservative": "RPE 5-6",
        "recovery": "RPE 4-6",
    }.get(mode, "RPE 6")
    if mode == "recovery" or goal == "rehab":
        return "Recovery / rehab session", [
            _line_exercise("Easy walk or bike", "15-30 min zone 1-2", "nasal/easy pace"),
            _line_exercise("Hip/knee rehab circuit", "2-3 easy rounds", "pain-free ROM only"),
            _line_exercise("Upper-body pump", "2-3 movements x 2-3 sets", "leave very fresh"),
            _line_exercise("Breathwork downshift", "8-10 min"),
        ]
    if goal == "bjj":
        if lower_limited or mode in {"conservative", "recovery"}:
            return "BJJ return-to-mats technique only", [
                _line_exercise("Solo drilling / movement prep", "15-20 min", "no scrambles"),
                _line_exercise("Technique rounds", "3-5 x 3 min", "cooperative only"),
                _line_exercise("Mobility + breathwork", "10 min"),
            ]
        return "Controlled BJJ session", [
            _line_exercise("Warm-up + mobility", "10 min"),
            _line_exercise("Technique rounds", "4-6 x 4 min"),
            _line_exercise("Positional sparring", "2-3 light rounds", "no ego rounds"),
        ]
    if goal == "conditioning":
        return "Low-impact conditioning", [
            _line_exercise("Bike / incline walk", "25-40 min zone 2" if mode == "progression" else "20-30 min zone 1-2"),
            _line_exercise("Core / carries", "2-3 easy rounds"),
            _line_exercise("Cooldown breathwork", "5-8 min"),
        ]
    if goal == "lower" and not lower_limited and mode == "progression":
        return "Lower-body strength", [
            _line_exercise("Squat or leg press", "4x4-6 @ " + intensity, targets.get("squat")),
            _line_exercise("Romanian deadlift", "3x6-8 @ RPE 6-7", targets.get("deadlift")),
            _line_exercise("Split squat / step-up", "2-3x8 each side", "stop if hip/knee talks"),
            _line_exercise("Hamstring curl + calves", "2-3x10-15"),
        ]
    if goal == "lower":
        return "Lower-body rehab bias", [
            _line_exercise("Bike warm-up", "8-12 min easy"),
            _line_exercise("Goblet squat / leg press", "3x8 @ RPE 5-6", "pain-free only"),
            _line_exercise("Hip hinge pattern", "2-3x8 light"),
            _line_exercise("Hip/knee rehab circuit", "2 rounds"),
        ]
    if goal == "push":
        return "Upper push strength", [
            _line_exercise("Bench press", "4x4-6 @ " + intensity, targets.get("bench")),
            _line_exercise("Incline DB press", "3x8-10 @ RPE 6-7"),
            _line_exercise("Overhead press", "2-3x5-8", "skip if shoulder/neck off"),
            _line_exercise("Triceps + lateral raises", "2-3x10-15"),
        ]
    if goal == "pull":
        return "Upper pull strength", [
            _line_exercise("Chest-supported row", "4x6-10 @ " + intensity, targets.get("row")),
            _line_exercise("Lat pulldown / pull-up", "4x6-10 @ RPE 6-7", targets.get("pulldown") or targets.get("pull")),
            _line_exercise("Rear delt / face pull", "3x12-15"),
            _line_exercise("Curls", "2-3x8-12"),
        ]
    # best / upper / unknown default: safest high-value session around current constraints.
    return "Upper-body strength / rehab bias", [
        _line_exercise("Bench press", "4x5 @ " + intensity, targets.get("bench")),
        _line_exercise("Chest-supported row", "4x8-10 @ RPE 6-7", targets.get("row")),
        _line_exercise("Lat pulldown", "3x10-12 @ RPE 6-7", targets.get("pulldown")),
        _line_exercise("DB incline or machine press", "2-3x8-10 easy"),
        _line_exercise("Hip/knee rehab circuit", "2 rounds", "if currently relevant"),
    ]


def format_session(ctx: dict[str, Any], arg: str = "") -> str:
    if ctx.get("error"):
        return "No Garmin data found. Run sync first."
    goal = _session_goal(arg)
    if goal not in {"best", "upper", "push", "pull", "lower", "rehab", "bjj", "conditioning"}:
        return "Usage: /fitness session [best|upper|push|pull|lower|rehab|bjj|conditioning]"
    mode = _session_mode(ctx)
    lower_limited = _has_lower_body_constraint(ctx)
    strength = ctx.get("strength_recent") or _strength_context()
    title, exercises = _session_exercises(goal, mode, lower_limited, strength)
    readiness = ctx.get("readiness") or {}
    capacity = ctx.get("capacity") or {}
    events = ctx.get("recent_events") or {}
    load_guidance = (ctx.get("predictive_readiness") or {}).get("load_guidance") or {}
    lines = [
        f"Session: {title}",
        f"Readiness: {str(readiness.get('zone') or 'unknown').upper()} · Capacity {str(capacity.get('zone') or 'unknown').upper()} · Mode {mode}",
    ]
    if events.get("summary"):
        label = "Confounders" if events.get("confounders") else "Context"
        lines.append(f"{label}: {events['summary']}")
    lines.extend(exercises[:5])
    rules = []
    if load_guidance.get("safe_load") is not None:
        rules.append(f"cap Garmin load ~{_fmt(load_guidance.get('safe_load'))}")
    if lower_limited:
        rules.append("no hip/knee-irritating movements")
    if mode in {"conservative", "recovery"}:
        rules.append("no grinders; leave 3+ reps in reserve")
    else:
        rules.append("stop before form breaks")
    reasons = (readiness.get("reasons") or capacity.get("flags") or [])[:2]
    if reasons:
        rules.append("why: " + "; ".join(str(r) for r in reasons))
    lines.append("Rules: " + "; ".join(rules[:4]) + ".")
    return "\n".join(lines[:9])


def format_simulation(ctx: dict[str, Any], arg: str) -> str:
    predictive = ctx.get("predictive_readiness") or {}
    if predictive.get("status") != "ready":
        return predictive.get("message") or "Simulation needs more paired training/recovery data."
    scenarios = predictive.get("scenarios") or []
    guidance = predictive.get("load_guidance") or {}
    arg_l = (arg or "").lower()
    preferred = None
    if any(w in arg_l for w in ("hard", "spar", "bjj", "lift")):
        preferred = next((s for s in scenarios if "hard" in str(s.get("label", "")).lower()), None)
    elif any(w in arg_l for w in ("tech", "easy", "rest")):
        preferred = next((s for s in scenarios if "tech" in str(s.get("label", "")).lower()), None)
    rows = [preferred] if preferred else scenarios[:2]
    lines = [f"Simulation for `{arg or 'today'}`:"]
    for s in [r for r in rows if r]:
        lines.append(
            f"- {s.get('label')}: HRV ~{_fmt(s.get('predicted_hrv'), ' ms')} tomorrow ({s.get('zone', '-')}, load {s.get('training_load', '-')})"
        )
    if guidance:
        lines.append(f"Guidance: {str(guidance.get('zone', '-')).upper()} · safe load ~{_fmt(guidance.get('safe_load'))}")
    return "\n".join(lines)


def _extract_int(label: str, text: str) -> int | None:
    m = re.search(rf"\b{re.escape(label)}\s*[:=]?\s*(\d{{1,2}})\b", text, flags=re.I)
    if not m:
        return None
    value = int(m.group(1))
    return max(0, min(10, value))


def _extract_time_decimal(text: str) -> float | None:
    m = re.search(r"\b([01]?\d|2[0-3])(?::|\.)([0-5]\d)\b", text)
    if m:
        return round(int(m.group(1)) + int(m.group(2)) / 60, 2)
    m = re.search(r"\b([01]?\d|2[0-3])\b", text)
    if m and re.search(r"\b(time|at|kl|dinner|caffeine|coffee|espresso)\b", text, re.I):
        return float(m.group(1))
    return None


def parse_lifestyle_event(arg: str) -> dict[str, Any]:
    text = (arg or "").strip()
    lower = text.lower()
    event_type = "note"
    value = None
    severity = 1
    metadata: dict[str, Any] = {}

    if re.search(r"\b(alcohol|beer|beers|wine|wines|drink|drinks|cocktail|whisky|vodka|øl)\b", lower):
        event_type = "alcohol"
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(beer|beers|wine|wines|drink|drinks|unit|units|glass|glasses|øl)?\b", lower)
        value = float(m.group(1)) if m else None
        severity = 3 if value and value >= 3 else 2
    elif re.search(r"\b(late dinner|dinner late|ate late|food late|late food|meal late|pizza late)\b", lower):
        event_type = "late_dinner"
        value = _extract_time_decimal(lower)
        severity = 3 if value and value >= 22 else 2
    elif re.search(r"\b(caffeine|coffee|espresso|preworkout|pre-workout)\b", lower):
        event_type = "caffeine_late"
        value = _extract_time_decimal(lower)
        severity = 3 if value and value >= 17 else 2
    elif re.search(r"\b(travel|flight|flew|airport|train|drive|driving|trip)\b", lower):
        event_type = "travel"
        severity = 2
    elif re.search(r"\b(hotel|airbnb)\b", lower):
        event_type = "hotel_sleep"
        severity = 2
    elif re.search(r"\b(sick|ill|illness|cold|fever|flu|covid|throat)\b", lower):
        event_type = "illness"
        severity = 3
    elif re.search(r"\b(work stress|stressful|stressor|deadline|argument|anxiety)\b", lower):
        event_type = "work_stress"
        severity = 2
    elif re.search(r"\b(poor food|junk|fast food|airport food|bad food)\b", lower):
        event_type = "poor_food"
        severity = 1
    elif re.search(r"\b(salt|salty|high sodium)\b", lower):
        event_type = "high_salt"
        severity = 1
    elif re.search(r"\b(sauna)\b", lower):
        event_type = "sauna"
        severity = 1
    elif re.search(r"\b(breathwork|breathing|meditation|downshift)\b", lower):
        event_type = "breathwork"
        value = _extract_int("min", lower) or _extract_int("minutes", lower)
        severity = 1
    elif re.search(r"\b(pain|hip|knee|back|shoulder|injur|irritat|ache|vondt)\b", lower):
        event_type = "pain_event"
        value = _extract_int("pain", lower)
        severity = int(value) if value is not None else 2
    elif re.search(r"\b(magnesium|supplement|creatine|melatonin|vitamin)\b", lower):
        event_type = "supplement"
        severity = 1
    elif re.search(r"\b(våknet|woke|oppvåkning|early wake|tidlig opp)\b", lower):
        event_type = "early_wake"
        m = re.search(r"(\d{1,2}):(\d{2})", text)
        if m:
            value = float(m.group(1)) + float(m.group(2)) / 60
        severity = 2

    if value is not None:
        metadata["parsed_value"] = value
    return {
        "date": _today(),
        "event_type": event_type,
        "value": value,
        "text": text,
        "severity": max(0, min(10, int(severity))),
        "metadata": metadata,
        "source": "telegram",
    }


def handle_note(arg: str) -> str:
    arg = (arg or "").strip()
    if not arg:
        return "Usage: /fitness note alcohol 2 beers | late dinner 22:30 | travel flight Oslo"
    record = parse_lifestyle_event(arg)
    db.init_db()
    event_id = db.add_daily_event(record)
    label = _fmt_event_type(record["event_type"])
    extra = f" · value {_fmt(record.get('value'))}" if record.get("value") is not None else ""
    return f"Logged event #{event_id} for {record['date']}: {label}{extra}."


def handle_notes(arg: str) -> str:
    raw = (arg or "").strip().lower()
    db.init_db()
    if raw.startswith("delete "):
        token = raw.split(maxsplit=1)[1].strip().lstrip("#")
        if not token.isdigit():
            return "Usage: /fitness notes delete 42"
        ok = db.delete_daily_event(int(token))
        return f"Deleted event #{token}." if ok else f"Event #{token} not found."

    days = 1 if raw in {"", "today"} else 7
    if raw in {"week", "weekly", "7d", "7 days"}:
        days = 7
    start = _iso_days_ago(days - 1)
    events = db.load_daily_events_df(start=start)
    if events.empty:
        return f"No lifestyle notes in the last {days} day{'s' if days != 1 else ''}."
    title = "Today's notes" if days == 1 else "Lifestyle notes this week"
    rows = [_format_event_row(r, include_date=days > 1) for _, r in events.tail(12).iterrows()]
    return title + ":\n" + "\n".join(f"- {row}" for row in rows)


def _date_key(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _prep_daily(daily_df: pd.DataFrame) -> pd.DataFrame:
    if daily_df is None or daily_df.empty:
        return pd.DataFrame()
    daily = daily_df.copy()
    if "sleep_hours" not in daily and "sleep_seconds" in daily:
        daily["sleep_hours"] = pd.to_numeric(daily["sleep_seconds"], errors="coerce") / 3600.0
    daily["date_key"] = daily["date"].apply(_date_key)
    daily = daily.dropna(subset=["date_key"]).sort_values("date_key").reset_index(drop=True)
    return daily


def _stimulus_by_date(activities_df: pd.DataFrame, strength_sessions_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if activities_df is not None and not activities_df.empty:
        acts = activities_df.copy()
        acts["date_key"] = acts["date"].apply(_date_key)
        for day, grp in acts.dropna(subset=["date_key"]).groupby("date_key"):
            load = pd.to_numeric(grp.get("training_load"), errors="coerce").fillna(0).sum()
            duration = pd.to_numeric(grp.get("duration_s"), errors="coerce").fillna(0).sum() / 60.0
            names = [str(x) for x in grp.get("name", pd.Series(dtype=str)).dropna().tail(3)]
            out.setdefault(day, {"date": day, "training_load": 0.0, "duration_min": 0.0, "strength_sessions": 0, "names": []})
            out[day]["training_load"] += float(load)
            out[day]["duration_min"] += float(duration)
            out[day]["names"].extend(names)
    if strength_sessions_df is not None and not strength_sessions_df.empty:
        ss = strength_sessions_df.copy()
        ss["date_key"] = ss["date"].apply(_date_key)
        for day, grp in ss.dropna(subset=["date_key"]).groupby("date_key"):
            out.setdefault(day, {"date": day, "training_load": 0.0, "duration_min": 0.0, "strength_sessions": 0, "names": []})
            out[day]["strength_sessions"] += int(len(grp))
            names = [str(x) for x in grp.get("name", pd.Series(dtype=str)).dropna().tail(3)]
            out[day]["names"].extend(names)
    return out


def _baseline_before(daily: pd.DataFrame, day: str, lookback: int = 7) -> dict[str, float | None]:
    idx = daily.index[daily["date_key"] == day]
    if len(idx) == 0:
        return {}
    prior = daily.iloc[max(0, int(idx[0]) - lookback):int(idx[0])]
    out: dict[str, float | None] = {}
    for col in ("hrv_overnight_avg", "resting_hr", "sleep_hours", "sleep_score", "body_battery_high"):
        if col in prior and not prior[col].dropna().empty:
            out[col] = _num(pd.to_numeric(prior[col], errors="coerce").median(), 1)
        else:
            out[col] = None
    return out


def _row_for_day(daily: pd.DataFrame, day: str, offset: int = 0) -> pd.Series | None:
    idx = daily.index[daily["date_key"] == day]
    if len(idx) == 0:
        return None
    pos = int(idx[0]) + offset
    if pos < 0 or pos >= len(daily):
        return None
    return daily.iloc[pos]


def _event_confounders_for(events_df: pd.DataFrame, days: set[str]) -> list[dict[str, Any]]:
    if events_df is None or events_df.empty:
        return []
    ev = events_df.copy()
    ev["date_key"] = ev["date"].apply(_date_key)
    rows = ev[ev["date_key"].isin(days)]
    return [r.to_dict() for _, r in rows.iterrows() if r.get("event_type") in RECOVERY_CONFOUNDERS]


def compute_session_response(
    daily_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    strength_sessions_df: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Compare the morning after the latest training stimulus to the prior baseline."""
    daily = _prep_daily(daily_df)
    if daily.empty:
        return {"status": "no_data", "message": "No daily metrics available."}
    stimuli = _stimulus_by_date(activities_df, strength_sessions_df)
    if not stimuli:
        return {"status": "no_training", "message": "No training sessions/activities found."}
    available_days = set(daily["date_key"])
    candidates = []
    for day, stim in stimuli.items():
        next_day = (pd.to_datetime(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if next_day in available_days and (target_date is None or day == target_date or next_day == target_date):
            candidates.append((day, stim, next_day))
    if not candidates:
        return {"status": "pending", "message": "Need the next morning's Garmin metrics after a logged session."}
    day, stim, next_day = sorted(candidates, key=lambda x: x[0])[-1]
    baseline = _baseline_before(daily, day)
    next_row = _row_for_day(daily, day, 1)
    if next_row is None:
        return {"status": "pending", "message": "Need the next morning's Garmin metrics after the session."}
    metrics = {}
    for col in ("hrv_overnight_avg", "resting_hr", "sleep_hours", "sleep_score", "body_battery_high"):
        base = baseline.get(col)
        value = _num(next_row.get(col), 1)
        delta = _num(float(value) - float(base), 1) if value is not None and base is not None else None
        metrics[col] = {"baseline": base, "next": value, "delta": delta}
    hrv_delta = metrics["hrv_overnight_avg"]["delta"]
    rhr_delta = metrics["resting_hr"]["delta"]
    sleep_delta = metrics["sleep_hours"]["delta"]
    confounders = _event_confounders_for(events_df, {day, next_day})
    hit_score = 0
    if hrv_delta is not None and hrv_delta <= -8:
        hit_score += 2
    elif hrv_delta is not None and hrv_delta <= -4:
        hit_score += 1
    if rhr_delta is not None and rhr_delta >= 5:
        hit_score += 2
    elif rhr_delta is not None and rhr_delta >= 3:
        hit_score += 1
    if sleep_delta is not None and sleep_delta <= -1:
        hit_score += 1
    if confounders:
        verdict = "confounded"
    elif hit_score >= 3:
        verdict = "hard_hit"
    elif hit_score >= 1:
        verdict = "acceptable_load"
    else:
        verdict = "good_response"
    return {
        "status": "ready",
        "session_date": day,
        "next_date": next_day,
        "stimulus": stim,
        "metrics": metrics,
        "verdict": verdict,
        "confounders": confounders,
    }


def compute_recovery_speed_model(
    daily_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    strength_sessions_df: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    max_days: int = 5,
) -> dict[str, Any]:
    """Estimate how many mornings it typically takes to return to baseline after training."""
    daily = _prep_daily(daily_df)
    if daily.empty:
        return {"status": "no_data", "samples": []}
    stimuli = _stimulus_by_date(activities_df, strength_sessions_df)
    samples = []
    for day, stim in sorted(stimuli.items()):
        row = _row_for_day(daily, day, 0)
        if row is None:
            continue
        baseline = _baseline_before(daily, day)
        base_hrv = baseline.get("hrv_overnight_avg")
        base_rhr = baseline.get("resting_hr")
        if base_hrv is None and base_rhr is None:
            continue
        recovered_day = None
        worst_hrv_delta = None
        worst_rhr_delta = None
        for offset in range(1, max_days + 1):
            after = _row_for_day(daily, day, offset)
            if after is None:
                break
            hrv = _num(after.get("hrv_overnight_avg"), 1)
            rhr = _num(after.get("resting_hr"), 1)
            hrv_delta = float(hrv) - float(base_hrv) if hrv is not None and base_hrv is not None else None
            rhr_delta = float(rhr) - float(base_rhr) if rhr is not None and base_rhr is not None else None
            if hrv_delta is not None:
                worst_hrv_delta = hrv_delta if worst_hrv_delta is None else min(worst_hrv_delta, hrv_delta)
            if rhr_delta is not None:
                worst_rhr_delta = rhr_delta if worst_rhr_delta is None else max(worst_rhr_delta, rhr_delta)
            hrv_ok = hrv_delta is None or hrv_delta >= -2
            rhr_ok = rhr_delta is None or rhr_delta <= 2
            if hrv_ok and rhr_ok:
                recovered_day = offset
                break
        if recovered_day is None:
            continue
        load = float(stim.get("training_load") or 0)
        bucket = "strength" if stim.get("strength_sessions") and load == 0 else ("low" if load < 50 else "medium" if load < 120 else "high")
        confounders = _event_confounders_for(events_df, {day})
        samples.append({
            "date": day,
            "days_to_recover": int(recovered_day),
            "training_load": _num(load, 0),
            "bucket": bucket,
            "strength_sessions": stim.get("strength_sessions", 0),
            "worst_hrv_delta": _num(worst_hrv_delta, 1),
            "worst_rhr_delta": _num(worst_rhr_delta, 1),
            "confounded": bool(confounders),
        })
    clean = [s for s in samples if not s.get("confounded")]
    basis = clean or samples
    if not basis:
        return {"status": "learning", "samples": samples, "message": "Need more post-session recovery pairs."}
    avg = sum(float(s["days_to_recover"]) for s in basis) / len(basis)
    if avg <= 1.5:
        speed = "fast"
    elif avg <= 2.5:
        speed = "moderate"
    else:
        speed = "slow"
    by_bucket = {}
    for bucket in sorted({s["bucket"] for s in basis}):
        rows = [s for s in basis if s["bucket"] == bucket]
        by_bucket[bucket] = _num(sum(float(r["days_to_recover"]) for r in rows) / len(rows), 1)
    return {
        "status": "ready" if len(basis) >= 3 else "learning",
        "speed": speed,
        "avg_days": _num(avg, 1),
        "samples": samples[-12:],
        "n": len(basis),
        "by_bucket": by_bucket,
        "excluded_confounders": len(samples) - len(clean),
    }


def compute_recovery_score(response: dict[str, Any], capacity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert response metrics into an explainable 0-100 current recovery score."""
    if response.get("status") != "ready":
        return {"status": "learning", "score": None, "zone": "learning", "drivers": [response.get("message") or "Need more response data."]}
    metrics = response.get("metrics") or {}
    penalties: list[tuple[str, float]] = []

    def delta(col: str) -> float | None:
        value = (metrics.get(col) or {}).get("delta")
        try:
            return None if value is None or pd.isna(value) else float(value)
        except (TypeError, ValueError):
            return None

    hrv_delta = delta("hrv_overnight_avg")
    rhr_delta = delta("resting_hr")
    sleep_delta = delta("sleep_hours")
    bb_delta = delta("body_battery_high")
    if hrv_delta is not None and hrv_delta < 0:
        penalties.append((f"HRV {hrv_delta:+g} ms vs baseline", min(35.0, abs(hrv_delta) * 2.0)))
    if rhr_delta is not None and rhr_delta > 0:
        penalties.append((f"RHR {rhr_delta:+g} bpm vs baseline", min(25.0, rhr_delta * 5.0)))
    if sleep_delta is not None and sleep_delta < 0:
        penalties.append((f"Sleep {sleep_delta:+g}h vs baseline", min(15.0, abs(sleep_delta) * 10.0)))
    if bb_delta is not None and bb_delta < 0:
        penalties.append((f"Body Battery {bb_delta:+g} vs baseline", min(25.0, abs(bb_delta) * 0.5)))

    score = max(0.0, min(100.0, 100.0 - sum(p for _, p in penalties)))
    cap_zone = str((capacity or {}).get("zone") or "").lower()
    if cap_zone == "red":
        score = min(score, 45.0)
    elif cap_zone == "yellow":
        score = min(score, 70.0)
    if response.get("verdict") == "hard_hit":
        score = min(score, 49.0)
    elif response.get("verdict") == "acceptable_load":
        score = min(score, 69.0)

    if score >= 85:
        zone = "highly recovered"
    elif score >= 70:
        zone = "recovered"
    elif score >= 50:
        zone = "partial"
    elif score >= 30:
        zone = "under-recovered"
    else:
        zone = "poor"
    drivers = [label for label, _ in sorted(penalties, key=lambda item: item[1], reverse=True)[:4]]
    if response.get("confounders"):
        drivers.append("confounded by " + ", ".join(_fmt_event_type(e.get("event_type")) for e in response["confounders"][:3]))
    return {"status": "ready", "score": int(round(score)), "zone": zone, "drivers": drivers}


def compute_custom_readiness(
    daily_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    strength_sessions_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Deterministic 0-100 readiness score from personal Garmin data.

    Replaces Garmin's ``training_readiness_score`` for watches that don't
    provide it. Blends four orthogonal signals, each scored 0-100:

    **Recovery (45 %)** — how well did last night's sleep actually restore
    the system?  Penalises HRV below baseline, RHR above baseline, sleep
    hours below personal need, and Body Battery peak below recent average.

    **Sleep debt (20 %)** — rolling 7-day sleep deficit.  Chronic
    short-changing blunts adaptation regardless of how a single night
    looks.

    **Stress (20 %)** — average psychological/physiological stress over
    the last 3 days plus high-stress minutes.  Sustained stress suppresses
    parasympathetic recovery.

    **Load balance / ACWR (15 %)** — acute:chronic workload ratio.
    Sweet-spot 0.8–1.3; both spikes (>1.5) and dips (<0.6) hurt.

    Hard caps: if recovery zone is poor → max 45; under-recovered → max
    60; ACWR > 1.5 → max 55.
    """
    empty: dict[str, Any] = {
        "score": None,
        "zone": "learning",
        "label": "Learning",
        "components": {},
        "drivers": ["Need more data — sync Garmin metrics for a few days."],
    }

    if daily_df is None or daily_df.empty:
        return empty

    df = daily_df.sort_values("date").copy()
    latest = df.iloc[-1]
    n_days = len(df)

    if n_days < 7:
        return empty

    # ── baselines (28-day where possible, fallback to 14d, then 7d) ──────
    window = min(28, n_days)
    bw = df.tail(window)
    base_hrv = _num(bw["hrv_overnight_avg"].mean()) if "hrv_overnight_avg" in bw else None
    base_rhr = _num(bw["resting_hr"].mean()) if "resting_hr" in bw else None
    base_bb  = _num(bw["body_battery_high"].mean()) if "body_battery_high" in bw else None
    base_sleep = _num(bw["sleep_hours"].mean()) if "sleep_hours" in bw else None

    drivers: list[str] = []
    sub_scores: dict[str, float] = {}

    # ═══ 1. Recovery state (45 %) ════════════════════════════════════════
    penalties: list[tuple[str, float]] = []

    hrv_now = _num(latest.get("hrv_overnight_avg"))
    rhr_now = _num(latest.get("resting_hr"))
    sleep_now = _num(latest.get("sleep_hours"))
    bb_now = _num(latest.get("body_battery_high"))

    if hrv_now is not None and base_hrv is not None and hrv_now < base_hrv:
        d = base_hrv - hrv_now
        penalties.append((f"HRV {hrv_now:.0f} vs {base_hrv:.0f} ms baseline", min(35.0, d * 2.0)))
    elif hrv_now is not None and base_hrv is not None:
        drivers.append(f"HRV {hrv_now:.0f} ms at/above baseline")

    if rhr_now is not None and base_rhr is not None and rhr_now > base_rhr:
        d = rhr_now - base_rhr
        penalties.append((f"RHR {rhr_now:.0f} vs {base_rhr:.0f} bpm baseline", min(25.0, d * 5.0)))
    elif rhr_now is not None and base_rhr is not None:
        drivers.append(f"RHR {rhr_now:.0f} bpm at/below baseline")

    if sleep_now is not None and base_sleep is not None and sleep_now < base_sleep:
        d = base_sleep - sleep_now
        penalties.append((f"Sleep {sleep_now:.1f}h vs {base_sleep:.1f}h baseline", min(15.0, d * 10.0)))

    if bb_now is not None and base_bb is not None and bb_now < base_bb:
        d = base_bb - bb_now
        penalties.append((f"Body Battery {bb_now:.0f} vs {base_bb:.0f} peak", min(25.0, d * 0.5)))

    recovery_score = max(0.0, min(100.0, 100.0 - sum(p for _, p in penalties)))
    sub_scores["recovery"] = recovery_score
    if penalties:
        for label, _p in sorted(penalties, key=lambda item: item[1], reverse=True):
            drivers.append(label)

    # ═══ 2. Sleep debt (20 %) ════════════════════════════════════════════
    sleep_need = getattr(config, "SLEEP_NEED_HOURS", 8.0)
    recent_sleep = df.tail(7)
    if "sleep_hours" in recent_sleep and recent_sleep["sleep_hours"].notna().any():
        avg_sleep = _num(recent_sleep["sleep_hours"].mean()) or 0
        debt = max(0.0, sleep_need - avg_sleep)
        # 0 debt → 100; 1h debt → ~70; 2h+ debt → ~30
        debt_score = max(0.0, 100.0 - debt * 35.0)
        sub_scores["sleep_debt"] = min(100.0, debt_score)
        if debt >= 1.0:
            drivers.append(f"7-day sleep debt {debt:.1f}h vs need {sleep_need:.0f}h")
        else:
            drivers.append(f"7-day sleep {avg_sleep:.1f}h avg — on target")
    else:
        sub_scores["sleep_debt"] = 50.0

    # ═══ 3. Stress (20 %) ════════════════════════════════════════════════
    if "stress_avg" in df and df["stress_avg"].notna().any():
        recent_stress = df.tail(3)
        stress_now = _num(recent_stress["stress_avg"].mean())
        # 0 stress → 100; 30 → ~55; 45 → ~32; 60+ → floor
        stress_score = max(0.0, 100.0 - (stress_now or 0) * 1.5)
        sub_scores["stress"] = min(100.0, stress_score)
        if stress_now is not None and stress_now >= 30:
            drivers.append(f"3-day avg stress {stress_now:.0f} (elevated)")
        elif stress_now is not None:
            drivers.append(f"3-day avg stress {stress_now:.0f} (ok)")
    else:
        sub_scores["stress"] = 50.0

    # ═══ 4. Load balance / ACWR (15 %) ══════════════════════════════════
    acwr = _num(latest.get("acwr"))
    if acwr is not None and not pd.isna(acwr) and acwr > 0:
        # Sweet spot 0.8–1.3
        if 0.8 <= acwr <= 1.3:
            load_score = 100.0
        elif acwr < 0.8:
            load_score = max(40.0, 100.0 - (0.8 - acwr) * 100.0)
        else:  # > 1.3
            load_score = max(0.0, 100.0 - (acwr - 1.3) * 120.0)
        sub_scores["load"] = min(100.0, load_score)
        zone_word = "spike" if acwr > 1.3 else ("dip" if acwr < 0.6 else "balanced")
        drivers.append(f"ACWR {acwr:.2f} ({zone_word})")
    elif not activities_df.empty and "training_load" in activities_df:
        # Fallback: compute simple 7d vs 28d ratio
        acts = activities_df.dropna(subset=["date", "training_load"]).copy()
        acts["date"] = pd.to_datetime(acts["date"], errors="coerce")
        acts = acts[acts["date"].notna()]
        if not acts.empty:
            today = pd.Timestamp(latest["date"]).normalize()
            acute = acts[acts["date"] >= today - pd.Timedelta(days=7)]["training_load"].sum()
            chronic_raw = acts[acts["date"] >= today - pd.Timedelta(days=28)]["training_load"].sum()
            chronic = chronic_raw / 4.0
            if chronic > 0:
                ratio = float(acute) / float(chronic)
                if 0.8 <= ratio <= 1.3:
                    sub_scores["load"] = 100.0
                elif ratio < 0.8:
                    sub_scores["load"] = max(40.0, 100.0 - (0.8 - ratio) * 100.0)
                else:
                    sub_scores["load"] = max(0.0, 100.0 - (ratio - 1.3) * 120.0)
                drivers.append(f"ACWR {ratio:.2f} (computed)")
            else:
                sub_scores["load"] = 70.0  # no chronic load → neutral-positive
    else:
        sub_scores["load"] = 70.0

    # ═══ Weighted blend ══════════════════════════════════════════════════
    score = (
        sub_scores.get("recovery", 50.0) * 0.45
        + sub_scores.get("sleep_debt", 50.0) * 0.20
        + sub_scores.get("stress", 50.0) * 0.20
        + sub_scores.get("load", 50.0) * 0.15
    )
    score = max(0.0, min(100.0, score))

    # ═══ Hard caps ═══════════════════════════════════════════════════════
    rec_zone_label = ""
    if recovery_score < 30:
        rec_zone_label = "poor"
        score = min(score, 45.0)
    elif recovery_score < 50:
        rec_zone_label = "under-recovered"
        score = min(score, 60.0)

    if acwr is not None and not pd.isna(acwr) and acwr > 1.5:
        score = min(score, 55.0)

    score_int = int(round(score))

    # ═══ Zone + label ════════════════════════════════════════════════════
    if score_int >= 85:
        zone_out, label_out = "highly_recovered", "PRIMED"
    elif score_int >= 70:
        zone_out, label_out = "recovered", "READY"
    elif score_int >= 50:
        zone_out, label_out = "partial", "MODERATE"
    elif score_int >= 30:
        zone_out, label_out = "under_recovered", "LOW"
    else:
        zone_out, label_out = "poor", "CRITICAL"

    return {
        "score": score_int,
        "zone": zone_out,
        "label": label_out,
        "components": {
            "recovery": round(sub_scores.get("recovery", 50.0)),
            "sleep_debt": round(sub_scores.get("sleep_debt", 50.0)),
            "stress": round(sub_scores.get("stress", 50.0)),
            "load": round(sub_scores.get("load", 50.0)),
        },
        "drivers": drivers[:6],
    }


def format_session_response(result: dict[str, Any]) -> str:
    if result.get("status") != "ready":
        return result.get("message") or "Session response is not ready yet."
    labels = {
        "good_response": "GOOD RESPONSE",
        "acceptable_load": "ACCEPTABLE LOAD",
        "hard_hit": "HARD HIT",
        "confounded": "CONFOUNDED",
    }
    metrics = result.get("metrics") or {}
    stim = result.get("stimulus") or {}
    names = ", ".join((stim.get("names") or [])[:2]) or "training"
    verdict_key = str(result.get("verdict") or "unknown")
    recovery_score = compute_recovery_score(result)
    lines = [
        f"Session response {result.get('session_date')} → {result.get('next_date')}: {labels.get(verdict_key, verdict_key)}",
        f"Recovery score: {recovery_score.get('score')}/100 ({recovery_score.get('zone')})",
        f"Stimulus: {names} · load {_fmt(stim.get('training_load'))} · strength sessions {_fmt(stim.get('strength_sessions'))}",
    ]
    for col, label, suffix in (
        ("hrv_overnight_avg", "HRV", " ms"),
        ("resting_hr", "RHR", " bpm"),
        ("sleep_hours", "Sleep", "h"),
        ("body_battery_high", "BB high", ""),
    ):
        m = metrics.get(col) or {}
        if m.get("next") is not None:
            delta = m.get("delta")
            delta_text = f" ({delta:+g}{suffix})" if delta is not None else ""
            lines.append(f"- {label}: {_fmt(m.get('next'), suffix, 1)} vs baseline {_fmt(m.get('baseline'), suffix, 1)}{delta_text}")
    if result.get("confounders"):
        lines.append("Confounders: " + ", ".join(_fmt_event_type(e.get("event_type")) for e in result["confounders"][:3]))
    if result.get("verdict") == "hard_hit":
        lines.append("Action: reduce next similar session or add an extra recovery day.")
    elif result.get("verdict") == "good_response":
        lines.append("Action: this dose looks absorbable if pain stayed quiet.")
    else:
        lines.append("Action: hold dose; watch the next similar response.")
    return "\n".join(lines[:8])


def format_recovery_speed(model: dict[str, Any]) -> str:
    if model.get("status") not in {"ready", "learning"}:
        return model.get("message") or "Recovery-speed model needs more data."
    if not model.get("samples"):
        return model.get("message") or "Need more post-session recovery pairs."
    lines = [
        f"Recovery speed: {str(model.get('speed') or 'learning').upper()} · avg {_fmt(model.get('avg_days'), ' days', 1)} · n={model.get('n', 0)}",
    ]
    if model.get("status") == "learning":
        lines.append("Status: learning — useful, but needs more clean sessions.")
    if model.get("by_bucket"):
        bucket_text = ", ".join(f"{k} {_fmt(v, 'd', 1)}" for k, v in model["by_bucket"].items())
        lines.append("By dose: " + bucket_text)
    if model.get("excluded_confounders"):
        lines.append(f"Excluded confounded sessions: {model['excluded_confounders']}")
    samples = model.get("samples") or []
    recent = samples[-3:]
    if recent:
        lines.append("Recent: " + "; ".join(f"{s['date']} {s['days_to_recover']}d" for s in recent))
    lines.append("Rule learned: prescribe harder work only when expected recovery fits the next 24-72h window.")
    return "\n".join(lines[:6])


def handle_response(arg: str = "") -> str:
    db.init_db()
    daily = analysis.enrich_daily(db.load_daily_df())
    target = (arg or "").strip() or None
    result = compute_session_response(
        daily,
        db.load_activities_df(),
        db.load_strength_sessions_df(),
        db.load_daily_events_df(start=_iso_days_ago(30)),
        target_date=target,
    )
    return format_session_response(result)


def handle_recovery(arg: str = "") -> str:
    db.init_db()
    daily = analysis.enrich_daily(db.load_daily_df())
    model = compute_recovery_speed_model(
        daily,
        db.load_activities_df(),
        db.load_strength_sessions_df(),
        db.load_daily_events_df(start=_iso_days_ago(120)),
    )
    return format_recovery_speed(model)



def handle_log(arg: str) -> str:
    arg = (arg or "").strip()
    if not arg:
        return "Usage: /fitness log pain 4 fatigue 3 energy 6 hip ok"
    day = _today()
    pain = _extract_int("pain", arg)
    fatigue = _extract_int("fatigue", arg)
    energy = _extract_int("energy", arg)
    note = re.sub(r"\b(pain|fatigue|energy)\s*[:=]?\s*\d{1,2}\b", "", arg, flags=re.I).strip(" ,;-")
    record = {"date": day, "pain": pain, "fatigue": fatigue, "energy": energy, "note": note or None}
    db.init_db()
    db.upsert_checkin(record)
    saved_memory = None
    if note:
        category = "injury" if re.search(r"\b(pain|injur|hip|knee|irritat|ache|vondt)\b", note, re.I) else "note"
        saved_memory = db.add_memory({"category": category, "text": note, "source": "telegram"})
    bits = [f"Logged check-in for {day}"]
    if pain is not None:
        bits.append(f"pain {pain}/10")
    if fatigue is not None:
        bits.append(f"fatigue {fatigue}/10")
    if energy is not None:
        bits.append(f"energy {energy}/10")
    if saved_memory:
        bits.append(f"memory #{saved_memory}")
    return " · ".join(bits) + "."


EXPERIMENT_TEMPLATES = {
    "prebed": {
        "name": "Pre-bed downshift",
        "hypothesis": "10 min breathwork plus no food in the last 2h before bed lowers pre-sleep HR and improves sleep score/HRV.",
        "metrics": ["hrv_overnight_avg", "sleep_score", "resting_hr"],
        "baseline_days": 14,
        "duration_days": 7,
        "protocol": "7 nights: 10 min breathwork + no food 2h pre-bed. Track HRV, sleep score, RHR.",
    },
    "caffeine": {
        "name": "Caffeine cutoff",
        "hypothesis": "No caffeine after 14:00 lowers pre-sleep activation and improves sleep score/HRV.",
        "metrics": ["hrv_overnight_avg", "sleep_score", "resting_hr"],
        "baseline_days": 14,
        "duration_days": 10,
        "protocol": "10 days: no caffeine after 14:00. Keep training roughly normal.",
    },
    "walk": {
        "name": "Easy morning walk",
        "hypothesis": "A short easy morning walk improves stress and Body Battery without aggravating hip/knee symptoms.",
        "metrics": ["stress_avg", "body_battery_high", "pain", "energy"],
        "baseline_days": 14,
        "duration_days": 7,
        "protocol": "7 days: 10-20 min easy morning walk only if hip/knee mechanics stay clean.",
    },
}


def _experiment_template(key: str) -> dict[str, Any] | None:
    key = (key or "").strip().lower()
    aliases = {"sleep": "prebed", "downshift": "prebed", "coffee": "caffeine", "morning-walk": "walk"}
    return EXPERIMENT_TEMPLATES.get(aliases.get(key, key))


def _active_experiment_rows():
    db.init_db()
    return db.load_experiments_df(status="active")


def _days_since(start_date: Any) -> int | None:
    start = pd.to_datetime(str(start_date)[:10], errors="coerce")
    today = pd.to_datetime(_today(), errors="coerce")
    if pd.isna(start) or pd.isna(today):
        return None
    return max(0, int((today.normalize() - start.normalize()).days))


def _start_experiment(template_key: str) -> str:
    template = _experiment_template(template_key) or EXPERIMENT_TEMPLATES["prebed"]
    exp_id = db.add_experiment({
        "name": template["name"],
        "hypothesis": template["hypothesis"],
        "metrics": template["metrics"],
        "baseline_days": template["baseline_days"],
        "start_date": _today(),
    })
    return f"Started experiment #{exp_id}: {template['name']}.\nProtocol: {template['protocol']}"


def _suggest_experiment(ctx: dict[str, Any] | None = None) -> str:
    ctx = ctx or build_context()
    active = ctx.get("active_experiments") or []
    if active:
        first = active[0]
        return f"Active experiment already running: {first.get('name')}. Use `/fitness experiment status`."

    rel_text = " ".join(
        str(r.get("label", "")) + " " + str(r.get("summary", ""))
        for r in ((ctx.get("prebed_discovery") or {}).get("relationships") or [])[:3]
    ).lower()
    reasons = " ".join(str(r) for r in ((ctx.get("readiness") or {}).get("reasons") or [])).lower()
    if "pre-sleep" in rel_text or "sleep" in rel_text or "sleep debt" in reasons:
        key = "prebed"
        evidence = "Your current limiting pattern points at sleep debt / pre-sleep activation."
    elif "stress" in rel_text:
        key = "walk"
        evidence = "Your strongest current pattern points at stress regulation."
    else:
        key = "prebed"
        evidence = "Defaulting to the highest-leverage recovery experiment."
    template = EXPERIMENT_TEMPLATES[key]
    return (
        f"Recommended experiment: {template['name']}\n"
        f"Hypothesis: {template['hypothesis']}\n"
        f"Protocol: {template['protocol']}\n"
        f"Evidence: {evidence}\n"
        f"Start: `/fitness experiment start {key}`"
    )


def _experiment_status() -> str:
    active = _active_experiment_rows()
    if active.empty:
        return "No active experiment. Use `/fitness experiment suggest`."
    row = active.iloc[0]
    day = _days_since(row.get("start_date"))
    metrics = row.get("metrics") or []
    metric_text = ", ".join(str(m) for m in metrics[:4]) if isinstance(metrics, list) else str(metrics)
    return (
        f"Active experiment: {row.get('name')} (day {day if day is not None else '-'})\n"
        f"Hypothesis: {row.get('hypothesis') or '-'}\n"
        f"Metrics: {metric_text}\n"
        "Keep protocol; don't change multiple variables mid-run."
    )


def _complete_experiment(arg: str = "") -> str:
    active = _active_experiment_rows()
    if active.empty:
        return "No active experiment to complete."
    row = active.iloc[0]
    exp_id = int(row.get("id"))
    db.update_experiment(exp_id, {"status": "complete", "end_date": _today()})
    return f"Completed experiment #{exp_id}: {row.get('name')} (end {_today()}). Use `/fitness experiment result {exp_id}`."


def _experiment_result(arg: str = "") -> str:
    db.init_db()
    experiments = db.load_experiments_df(status=None)
    if experiments.empty:
        return "No experiments found."
    tokens = (arg or "").split()
    exp_id = int(tokens[0]) if tokens and tokens[0].isdigit() else None
    if exp_id is not None:
        rows = experiments[experiments["id"] == exp_id]
        if rows.empty:
            return f"Experiment #{exp_id} not found."
        row = rows.iloc[0]
    else:
        row = experiments.iloc[-1]
    daily = analysis.enrich_daily(db.load_daily_df())
    result = analysis.compute_experiment_result(row.to_dict(), daily, db.load_checkins_df())
    lines = [f"Experiment result: {result.get('name')} ({result.get('status')})"]
    for key, metric in (result.get("metrics") or {}).items():
        verdict = metric.get("verdict")
        delta = metric.get("delta")
        label = metric.get("label") or key
        if delta is None:
            lines.append(f"- {label}: {verdict} ({metric.get('n_before')} baseline / {metric.get('n_after')} intervention days)")
        else:
            lines.append(f"- {label}: {verdict}, delta {delta:+g}")
    notes = result.get("notes") or []
    if notes:
        lines.append("Note: " + notes[0])
    return "\n".join(lines[:6])


def handle_experiment(arg: str, ctx: dict[str, Any] | None = None) -> str:
    raw = (arg or "").strip()
    lower = raw.lower()
    db.init_db()
    if not lower or lower == "suggest":
        return _suggest_experiment(ctx)
    if lower == "status":
        return _experiment_status()
    if lower.startswith("start "):
        return _start_experiment(lower.split(maxsplit=1)[1])
    if lower in {"prebed", "sleep", "downshift", "caffeine", "walk"}:
        return _start_experiment(lower)
    if lower.startswith("complete") or lower.startswith("stop"):
        return _complete_experiment(raw)
    if lower.startswith("result"):
        return _experiment_result(raw.partition(" ")[2])
    return "Supported: `/fitness experiment suggest|status|start prebed|complete|result`."


def format_why(ctx: dict[str, Any], arg: str) -> str:
    latest = ctx.get("latest") or {}
    discovery = ctx.get("prebed_discovery") or {}
    relationships = discovery.get("relationships") or []
    top = relationships[0] if relationships else {}
    early = ((ctx.get("early_waking") or {}).get("latest") or {})
    lines = [f"Likely cause chain for {arg or 'latest recovery'}:"]
    if latest.get("sleep_hours") is not None and float(latest["sleep_hours"]) < 6.5:
        lines.append(f"- Short sleep: {_fmt(latest.get('sleep_hours'), 'h', 1)} with score {_fmt(latest.get('sleep_score'))}.")
    if latest.get("hrv_overnight_avg") is not None:
        lines.append(f"- HRV now {_fmt(latest.get('hrv_overnight_avg'), ' ms')}; readiness flags: {', '.join((ctx.get('readiness') or {}).get('reasons') or []) or '-'}.")
    if early.get("pattern"):
        lines.append(f"- Early-waking model: {str(early.get('pattern')).replace('_', ' ')}; evidence: {', '.join(early.get('evidence') or [])}.")
    if top:
        lines.append(f"- Strongest personal relationship: {top.get('summary') or top.get('label')}.")
    events = ctx.get("recent_events") or {}
    confounders = events.get("confounders") or []
    if confounders:
        event_text = "; ".join(_format_event_row(e) for e in confounders[-3:])
        lines.append(f"- Recent context/confounders: {event_text}.")
    return "\n".join(lines[:6])


def help_text() -> str:
    return (
        "Fitness commands:\n"
        "- `/fitness status` recovery snapshot\n"
        "- `/fitness plan` exact training decision\n"
        "- `/fitness simulate hard lift` scenario forecast\n"
        "- `/fitness session [best|upper|push|pull|lower|rehab|bjj|conditioning]`\n"
        "- `/fitness response` next-morning session response\n"
        "- `/fitness recovery` learned recovery-speed model\n"
        "- `/fitness log pain 4 fatigue 3 energy 6 hip ok`\n"
        "- `/fitness note alcohol 2 beers | late dinner 22:30 | travel`\n"
        "- `/fitness notes today|week|delete 42`\n"
        "- `/fitness experiment suggest|status|start prebed|complete|result`\n"
        "- `/fitness why hrv` causal forensic read"
    )


def handle_fitness_command(text: str) -> str:
    cmd, arg = parse_fitness_command(text)
    if cmd == "help":
        return help_text()
    if cmd == "log":
        return handle_log(arg)
    if cmd == "note":
        return handle_note(arg)
    if cmd == "notes":
        return handle_notes(arg)
    if cmd == "response":
        return handle_response(arg)
    if cmd == "recovery":
        return handle_recovery(arg)
    if cmd == "experiment":
        return handle_experiment(arg)
    ctx = build_context()
    if cmd == "status":
        return format_status(ctx)
    if cmd == "plan":
        return format_plan(ctx)
    if cmd == "session":
        return format_session(ctx, arg)
    if cmd == "simulate":
        return format_simulation(ctx, arg)
    if cmd == "why":
        return format_why(ctx, arg)
    if cmd in ["våknet", "woke", "early_wake", "tidlig"]:
        return handle_early_wake(arg)
    return help_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes fitness command center")
    parser.add_argument("command", nargs="*", help="fitness command, e.g. status | plan | simulate hard lift")
    args = parser.parse_args(argv)
    print(handle_fitness_command(" ".join(args.command)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



def handle_early_wake(arg: str) -> str:
    """Log an early wake event with full context from daily_metrics."""
    arg = (arg or "").strip()
    if not arg:
        return "Usage: /fitness våknet 06:12"

    record = parse_lifestyle_event(arg)
    if record["event_type"] != "early_wake":
        return "Could not parse wake time. Use format: våknet 06:12"

    db.init_db()
    
    # Get yesterday's metrics for context
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    daily = db.load_daily_df()
    row = daily[daily["date"] == yesterday]
    
    context = {}
    if not row.empty:
        r = row.iloc[0]
        context = {
            "sleep_seconds": r.get("sleep_seconds"),
            "hrv_overnight_avg": r.get("hrv_overnight_avg"),
            "resting_hr": r.get("resting_hr"),
            "hr_bedtime": r.get("hr_bedtime"),
            "stress_prev_day": r.get("stress_avg"),
            "sleep_score": r.get("sleep_score"),
            "body_battery_start": r.get("body_battery_start"),
        }
    
    wake_record = {
        "date": _today(),
        "wake_time": arg,
        "note": arg,
        **{k: v for k, v in context.items() if v is not None}
    }
    
    event_id = db.add_early_wake(wake_record)
    
    hrv = context.get("hrv_overnight_avg")
    rhr = context.get("resting_hr")
    extra = f" | HRV {hrv}ms, RHR {rhr}" if hrv and rhr else ""
    
    return f"Logged early wake #{event_id} at {arg}{extra}"
