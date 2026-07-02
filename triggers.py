"""Proactive recovery trigger engine.

Runs after morning sync, evaluates conditions against today's enriched
metrics, and prints any fired triggers to stdout. Empty output = silent
(no Telegram message sent). Uses a JSON state file to deduplicate —
each trigger fires at most once per date.

Usage:
    cd /home/johannes/apps/hanky-sin-garmin
    .venv/bin/python triggers.py
"""
import sys
import os
import json
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import db
import analysis
import config

STATE_PATH = Path(__file__).resolve().parent / ".trigger_state.json"
# Don't fire if data is older than this many hours (sync didn't run)
MAX_DATA_AGE_HOURS = 18


# ─── helpers ─────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


def _already_fired(state: dict, trigger_id: str, today: str) -> bool:
    return state.get(trigger_id) == today


def _mark_fired(state: dict, trigger_id: str, today: str) -> None:
    state[trigger_id] = today


def _num(row, key):
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _consecutive_true(series, key) -> int:
    """Count trailing consecutive True values in a boolean column."""
    count = 0
    for v in reversed(series[key].tolist()):
        if v is True or v == 1:
            count += 1
        else:
            break
    return count


# ─── trigger conditions ──────────────────────────────────────────────
# Each returns (should_fire: bool, message: str | None)


def _check_hrv_crash(df, latest, today_str):
    """HRV crashed >1.5 SD below personal baseline."""
    hrv_z = _num(latest, "hrv_z")
    hrv = _num(latest, "hrv_overnight_avg")
    baseline = _num(latest, "hrv_baseline_mid")
    if hrv_z is not None and hrv_z <= -1.5:
        sd_below = abs(hrv_z)
        msg = (
            f"HRV krasjet til {hrv:.0f} ms "
            f"({sd_below:.1f} SD under din normal). "
        )
        if baseline:
            msg += f"Din baseline er ~{baseline:.0f} ms. "
        msg += "Vurder rolig aktivitet eller hvile i dag."
        return True, msg
    return False, None


def _check_recovery_green(df, latest, today_str):
    """All signals green — exceptional recovery, push day."""
    hrv_flag = latest.get("hrv_flag")
    rhr_elevated = latest.get("rhr_elevated")
    sleep_h = _num(latest, "sleep_hours")
    stress = _num(latest, "stress_avg")
    bb = _num(latest, "body_battery_high")
    bb_current = _num(latest, "body_battery_current")
    bb_eff = bb_current if bb_current is not None else bb

    conditions = [
        hrv_flag in ("balanced", "elevated"),
        rhr_elevated is not True,
        sleep_h is not None and sleep_h >= 7.0,
        stress is not None and stress < 40,
        bb_eff is not None and bb_eff >= 75,
    ]
    if all(conditions):
        msg = (
            f"Grønt lys! HRV {hrv_flag} "
            f"({_num(latest, 'hrv_overnight_avg'):.0f} ms), "
            f"sov {sleep_h:.1f}t, stress {stress:.0f}, "
            f"body battery {bb_eff:.0f}. "
            "Dette er et vindu for hard trening."
        )
        return True, msg
    return False, None


def _check_sleep_debt(df, latest, today_str):
    """3+ consecutive nights under 7h."""
    sleep_need = config.SLEEP_NEED_HOURS
    recent = df.tail(5)
    if "sleep_hours" not in recent:
        return False, None
    under = recent["sleep_hours"].apply(
        lambda x: x is not None and x == x and float(x) < (sleep_need - 0.75)
    )
    streak = _consecutive_true_from_series(under)
    if streak >= 3:
        avg = recent["sleep_hours"].tail(streak).mean()
        debt = (sleep_need - avg) * streak
        msg = (
            f"Søvngjeld: {streak} netter på rad under "
            f"{sleep_need - 0.75:.1f}t (snitt {avg:.1f}t). "
            f"Akkumulert underskudd ~{debt:.1f}t. "
            "Prioriter tidlig leggetid i kveld."
        )
        return True, msg
    return False, None


def _consecutive_true_from_series(s) -> int:
    count = 0
    for v in reversed(s.tolist()):
        if v:
            count += 1
        else:
            break
    return count


def _check_rhr_streak(df, latest, today_str):
    """Resting HR elevated for 2+ consecutive days."""
    if "rhr_elevated" not in df:
        return False, None
    streak = _consecutive_true(df, "rhr_elevated")
    if streak >= 2:
        rhr = _num(latest, "resting_hr")
        baseline = _num(latest, "rhr_28d")
        msg = f"Hvilepuls forhøyet {streak} dager på rad"
        if rhr and baseline:
            pct = ((rhr - baseline) / baseline) * 100
            msg += f" ({rhr:.0f} vs {baseline:.0f} bpm, +{pct:.0f}%)"
        msg += ". Kroppen samler tretthet — vurder deload eller hviledag."
        return True, msg
    return False, None


def _check_load_spike(df, latest, today_str):
    """ACWR above 1.5 — load spike risk."""
    acwr = _num(latest, "acwr")
    if acwr is not None and acwr > 1.5:
        msg = (
            f"Belastningsspytt: ACWR {acwr:.2f} "
            "(akutt vs kronisk load >1.5). "
            "Kroppen tar mer straff enn den er vant til."
        )
        return True, msg
    return False, None


def _check_stress_spike(df, latest, today_str):
    """Daily stress >1.5 SD above baseline."""
    stress_z = _num(latest, "stress_z")
    stress = _num(latest, "stress_avg")
    if stress_z is not None and stress_z >= 1.5:
        msg = (
            f"Høyt stressnivå i går: {stress:.0f} "
            f"({stress_z:.1f} SD over normal). "
            "Dette kan trykke ned HRV i natt."
        )
        return True, msg
    return False, None


TRIGGERS = [
    ("hrv_crash", "📉", _check_hrv_crash),
    ("recovery_green", "🔥", _check_recovery_green),
    ("sleep_debt", "😴", _check_sleep_debt),
    ("rhr_streak", "❤️", _check_rhr_streak),
    ("load_spike", "⚡", _check_load_spike),
    ("stress_spike", "😰", _check_stress_spike),
]


# ─── main ────────────────────────────────────────────────────────────

def main():
    try:
        db.init_db()
        raw_daily = db.load_daily_df()
        if raw_daily.empty:
            return  # No data at all — silent

        daily = analysis.enrich_daily(raw_daily)
        activities = db.load_activities_df()
        if not daily.empty:
            daily = analysis.compute_acwr(activities, daily)

        latest = daily.iloc[-1]
        latest_date_str = str(latest["date"])[:10]

        # Freshness check: skip if data is stale
        today = date.today().isoformat()
        try:
            data_date = datetime.fromisoformat(latest_date_str).date()
            age_hours = (datetime.now() - datetime.combine(
                data_date, datetime.min.time()
            )).total_seconds() / 3600
            if age_hours > MAX_DATA_AGE_HOURS + 24:
                # Data is from more than ~2 days ago — sync likely broken
                return
        except (ValueError, TypeError):
            pass

        state = _load_state()
        fired = []
        df_tail = daily.tail(14)

        for trigger_id, emoji, check_fn in TRIGGERS:
            if _already_fired(state, trigger_id, latest_date_str):
                continue
            try:
                should_fire, message = check_fn(df_tail, latest, latest_date_str)
            except Exception:
                should_fire, message = False, None
            if should_fire and message:
                fired.append(f"{emoji} {message}")
                _mark_fired(state, trigger_id, latest_date_str)

        _save_state(state)

        if not fired:
            return  # Silent — no triggers

        header = f"**Triggervarsel ({latest_date_str})**"
        print(header)
        print()
        for f in fired:
            print(f)
            print()

    except Exception as e:
        print(f"❌ Trigger-feil: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
