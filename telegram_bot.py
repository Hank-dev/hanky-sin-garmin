"""Private Telegram command interface for the Hanky fitness app.

Run beside Streamlit:

    python telegram_bot.py

Required environment:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_ALLOWED_USER_IDS=123456789

The bot uses long polling, so it does not require a public webhook URL.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import ai
import analysis
import config  # noqa: F401 - imports .env via load_dotenv()
import db


BASE_DIR = Path(__file__).resolve().parent
MAX_MESSAGE_LEN = 3900
DEFAULT_SYNC_DAYS = 7
MAX_SYNC_DAYS = 365


class TelegramConfigError(RuntimeError):
    pass


class TelegramApiError(RuntimeError):
    pass


def parse_allowed_user_ids(raw: str | None = None) -> set[int]:
    """Parse TELEGRAM_ALLOWED_USER_IDS as comma/semicolon-separated integers."""
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "") if raw is None else raw
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def command_parts(text: str) -> tuple[str, str]:
    """Return (command, argument), stripping optional @BotUsername suffix."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", text
    head, _, arg = text.partition(" ")
    command = head.split("@", 1)[0].lower()
    return command, arg.strip()


def parse_sync_days(arg: str) -> int:
    arg = (arg or "").strip()
    if not arg:
        return DEFAULT_SYNC_DAYS
    first = arg.split()[0]
    try:
        days = int(first)
    except ValueError as exc:
        raise ValueError("Usage: /sync or /sync 30") from exc
    if days < 1 or days > MAX_SYNC_DAYS:
        raise ValueError(f"Choose a day count from 1 to {MAX_SYNC_DAYS}.")
    return days


def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramConfigError("Set TELEGRAM_BOT_TOKEN in .env.")
    return token


def _api_request(method: str, payload: dict[str, Any] | None = None,
                 timeout: int = 60) -> Any:
    url = f"https://api.telegram.org/bot{_bot_token()}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    obj = json.loads(body)
    if not obj.get("ok"):
        raise TelegramApiError(obj.get("description", "Telegram API request failed"))
    return obj.get("result")


def _message_chunks(text: str) -> list[str]:
    text = str(text or "").strip() or "(empty response)"
    chunks = []
    while len(text) > MAX_MESSAGE_LEN:
        split_at = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        if split_at < 1000:
            split_at = MAX_MESSAGE_LEN
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    chunks.append(text)
    return chunks


def send_message(chat_id: int, text: str) -> None:
    for chunk in _message_chunks(text):
        _api_request("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        })


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    try:
        _api_request("sendChatAction", {"chat_id": chat_id, "action": action})
    except Exception:
        pass


def format_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isnan(value):
        return "-"
    text = str(value)
    if text.lower() in {"nan", "none", "nat"}:
        return "-"
    return f"{text}{suffix}"


def build_context() -> dict[str, Any]:
    """Build the same compact context used by the Streamlit coach surfaces."""
    db.init_db()
    daily = analysis.enrich_daily(db.load_daily_df())
    activities = db.load_activities_df()
    checkins = db.load_checkins_df()
    sleep_timing = db.load_sleep_timing_df()
    stress = db.load_stress_df()

    if not daily.empty:
        daily = analysis.compute_acwr(activities, daily)

    activity_details = db.load_activity_raw_payloads("activity_details")
    activity_zones = db.load_activity_raw_payloads("activity_hr_zones")
    grappling = analysis.compute_grappling_sessions(
        daily, activities, activity_details, activity_zones
    )
    stress_leaks = analysis.compute_stress_leak_map(daily, stress)
    prebed_discovery = analysis.compute_prebed_discovery(daily, activities, sleep_timing)
    health_research = analysis.compute_health_research_panels(
        daily, activities, sleep_timing
    )

    sessions = db.load_strength_sessions_df()
    sets = db.load_strength_sets_df()
    exercises = db.load_exercises_df()
    profile = db.load_profile()
    body_metrics = db.load_body_metrics_df()
    bodyweight = None
    if not body_metrics.empty:
        weights = body_metrics.dropna(subset=["weight_kg"]).sort_values("date")
        if not weights.empty:
            bodyweight = float(weights.iloc[-1]["weight_kg"])

    strength = analysis.summarize_strength(
        sessions, sets, exercises, profile, bodyweight, formula=config.ONE_RM_FORMULA
    )
    coach_memory = analysis.build_coach_memory_digest(db.load_memory_df())
    active_experiments = analysis.summarize_active_experiments(
        db.load_experiments_df(status="active"), daily
    )

    return {
        "daily": daily,
        "activities": activities,
        "summary": analysis.summarize(daily, activities),
        "capacity": analysis.compute_capacity_envelope(daily, activities, checkins),
        "stress_leaks": stress_leaks,
        "grappling": grappling,
        "prebed_discovery": prebed_discovery,
        "health_research": health_research,
        "strength": strength,
        "coach_memory": coach_memory,
        "active_experiments": active_experiments,
    }


def format_today(summary: dict[str, Any], capacity: dict[str, Any] | None = None,
                 strength: dict[str, Any] | None = None) -> str:
    if summary.get("error"):
        return "No Garmin data found yet. Run sync first: /sync 30"

    latest = summary.get("latest") or {}
    trends = summary.get("trends_14d") or {}
    lines = [
        f"Recovery snapshot ({summary.get('as_of', '-')})",
        "",
        f"Readiness: {format_value(latest.get('training_readiness'))}",
        (
            "HRV: "
            f"{format_value(latest.get('hrv_overnight'), ' ms')} "
            f"({latest.get('hrv_flag') or latest.get('hrv_status') or '-'})"
        ),
        (
            "Resting HR: "
            f"{format_value(latest.get('resting_hr'), ' bpm')} "
            f"(28d {format_value(latest.get('rhr_28d_baseline'), ' bpm')})"
        ),
        (
            "Sleep: "
            f"{format_value(latest.get('sleep_hours'), ' h')} "
            f"(score {format_value(latest.get('sleep_score'))})"
        ),
        f"Body battery high: {format_value(latest.get('body_battery_high'))}",
        f"Stress avg: {format_value(latest.get('stress_avg'))}",
        "",
        "14d trend:",
        (
            "Sleep avg "
            f"{format_value(trends.get('avg_sleep_hours'), ' h')}, "
            f"debt {format_value(trends.get('sleep_debt_total_h'), ' h')}"
        ),
        (
            f"HRV trend: {format_value(trends.get('hrv_trend'))}; "
            f"RHR trend: {format_value(trends.get('rhr_trend'))}"
        ),
        f"Suppressed HRV days: {format_value(trends.get('suppressed_hrv_days'))}",
    ]

    if capacity:
        zone = str(capacity.get("zone") or "-").upper()
        message = capacity.get("message") or ""
        lines.extend(["", f"Capacity: {zone}", message])

    if strength and strength.get("status") == "ok":
        recent = strength.get("recent") or {}
        lines.extend([
            "",
            "Strength:",
            (
                f"{format_value(recent.get('sessions'))} sessions in "
                f"{format_value(recent.get('lookback_days'))} days, "
                f"{format_value(recent.get('tonnage_kg'), ' kg')} tonnage"
            ),
        ])

    return "\n".join(lines)


def run_sync(days: int) -> str:
    cmd = [sys.executable, str(BASE_DIR / "sync.py"), "--days", str(days)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            "Sync timed out. If Garmin needs login/MFA, run this over SSH first:\n"
            ".venv/bin/python sync.py --login"
        )
    tail = (proc.stdout or "").strip()[-2500:]
    if proc.returncode != 0:
        return f"Sync failed with exit code {proc.returncode}.\n\n{tail}"
    return f"Synced the last {days} day(s)." + (f"\n\n{tail}" if tail else "")


HELP_TEXT = """Hanky Telegram bot commands:

/whoami
Show your Telegram user ID for TELEGRAM_ALLOWED_USER_IDS.

/today
Show the latest recovery snapshot.

/sync [days]
Run Garmin sync. Example: /sync 30

/note text
Save a timestamped coach note.

/injury text
Save a timestamped injury note.

/ask question
Ask the AI coach using your local Garmin, strength, notes, and experiment context.
"""


def _unauthorized_text(user_id: int | None) -> str:
    return (
        "This bot is private and your user ID is not allowed yet.\n\n"
        f"Your Telegram user ID: {user_id or '-'}\n\n"
        "Add it to .env on the VPS:\n"
        f"TELEGRAM_ALLOWED_USER_IDS={user_id or '<your_id>'}\n\n"
        "Then restart the Telegram bot service."
    )


def handle_authorized_command(command: str, arg: str, chat_id: int) -> str | None:
    if command == "/today":
        send_chat_action(chat_id)
        ctx = build_context()
        return format_today(ctx["summary"], ctx["capacity"], ctx["strength"])

    if command == "/sync":
        days = parse_sync_days(arg)
        send_message(chat_id, f"Starting Garmin sync for the last {days} day(s)...")
        return run_sync(days)

    if command == "/note":
        if not arg:
            return "Usage: /note Left knee felt good after squats"
        db.init_db()
        memory_id = db.add_memory({
            "category": "note",
            "text": arg,
            "source": "telegram",
        })
        return f"Saved note #{memory_id}."

    if command == "/injury":
        if not arg:
            return "Usage: /injury Left knee pain during warmup"
        db.init_db()
        memory_id = db.add_memory({
            "category": "injury",
            "text": arg,
            "source": "telegram",
        })
        return f"Saved injury #{memory_id}."

    if command == "/ask":
        if not arg:
            return "Usage: /ask Should I train hard today?"
        send_chat_action(chat_id)
        ctx = build_context()
        return ai.answer_question(
            arg,
            ctx["summary"],
            ctx["capacity"],
            ctx["stress_leaks"],
            ctx["grappling"],
            ctx["prebed_discovery"],
            chat_history=[],
            strength=ctx["strength"],
            health_research=ctx["health_research"],
            coach_memory=ctx["coach_memory"],
            active_experiments=ctx["active_experiments"],
        )

    return None


def handle_update(update: dict[str, Any], allowed_ids: set[int]) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = user.get("id")
    if chat_id is None or not text:
        return

    command, arg = command_parts(text)
    if command in {"/start", "/help", ""}:
        send_message(chat_id, HELP_TEXT)
        if command == "/start":
            send_message(chat_id, f"Your Telegram user ID: {user_id or '-'}")
        return
    if command == "/whoami":
        send_message(chat_id, f"Your Telegram user ID: {user_id or '-'}")
        return

    if user_id not in allowed_ids:
        send_message(chat_id, _unauthorized_text(user_id))
        return

    try:
        reply = handle_authorized_command(command, arg, chat_id)
    except ValueError as exc:
        reply = str(exc)
    except Exception:
        traceback.print_exc()
        reply = "Command failed. Check the bot logs on the VPS."

    if reply is None:
        reply = "Unknown command. Send /help for options."
    send_message(chat_id, reply)


def poll_forever() -> None:
    allowed_ids = parse_allowed_user_ids()
    if not allowed_ids:
        print("WARNING: TELEGRAM_ALLOWED_USER_IDS is empty. Only /whoami is usable.")

    _api_request("deleteWebhook", {"drop_pending_updates": "false"})
    offset = None
    timeout_s = int(os.getenv("TELEGRAM_POLL_TIMEOUT", "50"))
    print("Telegram bot started.")

    while True:
        try:
            payload: dict[str, Any] = {"timeout": timeout_s}
            if offset is not None:
                payload["offset"] = offset
            updates = _api_request("getUpdates", payload, timeout=timeout_s + 15)
            for update in updates:
                offset = int(update["update_id"]) + 1
                handle_update(update, allowed_ids)
        except TelegramConfigError:
            raise
        except Exception:
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    poll_forever()
