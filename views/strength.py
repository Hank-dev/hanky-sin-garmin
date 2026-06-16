"""Strength logger — Strong-style live workout logging on its own page.

Live state lives in st.session_state["active"] until you press Finish, which
persists the session + sets and stamps the readiness snapshot for the day.
"""
import html
import uuid
import importlib
from datetime import datetime, date

import pandas as pd
import streamlit as st

import config
import db
import analysis
import cockpit
import strength_catalog

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
cockpit = importlib.reload(cockpit)
strength_catalog = importlib.reload(strength_catalog)

st.set_page_config(page_title="Strength — Hankø", page_icon="🏋️", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)
st.markdown("""
<style>
.st-key-strong_logger{
  max-width:720px;margin:0 auto 22px!important;padding:0 22px 18px!important;background:#020303;
  border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;
  box-shadow:0 22px 70px -36px rgba(0,0,0,.9);
}
.st-key-strong_logger [data-testid="stVerticalBlock"]{gap:.45rem;}
.st-key-strong_topbar{
  position:sticky;top:0;z-index:10;margin:0 -22px 8px!important;
  padding:10px 18px!important;background:#080909;
  border-bottom:1px solid rgba(255,255,255,.04);
}
.strong-top{
  position:sticky;top:0;z-index:10;display:grid;grid-template-columns:64px 64px 1fr 104px;
  align-items:center;gap:8px;padding:10px 18px;background:#080909;
  border-bottom:1px solid rgba(255,255,255,.04);
}
.strong-top-cell{
  min-height:44px;display:flex;align-items:center;justify-content:center;
  background:#080909;color:#fff;
}
.strong-top .icon{
  min-height:44px;display:grid;place-items:center;color:#fff;font-size:28px;line-height:1;
}
.strong-top-cell.icon{font-size:28px;line-height:1;}
.strong-top .timer,.strong-top-cell.timer{
  text-align:center;color:#c9c9c9;font-size:22px;font-variant-numeric:tabular-nums;
}
.strong-finish{
  color:#35aaff;text-align:right;font-size:20px;font-weight:700;letter-spacing:.16em;
}
.strong-head{padding:26px 22px 16px;}
.strong-title{font-size:28px;line-height:1.08;font-weight:800;color:#fff;letter-spacing:-.01em;}
.strong-duration{margin-top:14px;color:#b8b8b8;font-size:24px;font-variant-numeric:tabular-nums;}
.strong-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:0 22px 18px;}
.strong-stat{background:#151515;border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:9px 11px;}
.strong-stat .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:#8a8a8a;}
.strong-stat .val{margin-top:3px;font-size:18px;color:#fff;font-weight:750;font-variant-numeric:tabular-nums;}
.strong-section{padding:0 22px 18px;}
.strong-ex-head{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;margin-top:18px;}
.strong-ex-title{color:#2da8ff;font-size:22px;font-weight:800;letter-spacing:.01em;}
.strong-ex-tools{display:flex;align-items:center;gap:8px;color:#2da8ff;font-weight:800;}
.strong-note{
  margin:12px 0 10px;padding:11px 14px;background:#4c3e07;color:#fff;
  font-size:17px;line-height:1.25;border-radius:0;
}
.strong-col-head{
  display:grid;grid-template-columns:.72fr 1.55fr 1fr 1fr .72fr;gap:10px;
  padding:8px 2px 6px;font-family:var(--font-mono);font-size:12px;font-weight:800;
  letter-spacing:.22em;color:#fff;text-transform:uppercase;
}
.strong-row-label{
  display:flex;align-items:center;min-height:42px;font-size:20px;font-weight:800;
}
.strong-row-label.warm{color:#ffb234;}
.strong-row-label.done{color:#fff;}
.strong-prev{
  min-height:42px;display:flex;align-items:center;color:#7f8c84;font-size:18px;
  font-variant-numeric:tabular-nums;white-space:nowrap;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"]{
  padding:2px 0!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] [data-testid="stHorizontalBlock"]{
  flex-wrap:nowrap!important;align-items:center!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] [data-testid="stHorizontalBlock"] > div{
  flex:0 0 auto!important;width:auto!important;min-width:0!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] .strong-prev{
  min-width:86px;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] div[data-testid="stTextInput"]{
  width:74px!important;min-width:58px!important;
}
.st-key-strong_logger [class*="st-key-kg_txt_"],
.st-key-strong_logger [class*="st-key-reps_txt_"]{
  width:74px!important;min-width:58px!important;flex:0 0 74px!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] div.stButton > button{
  min-width:40px!important;padding-left:0!important;padding-right:0!important;
}
.strong-done-strip{
  height:5px;margin:-2px 0 6px;border-radius:999px;background:#073d1f;
}
.strong-rest{
  display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
  align-items:center;gap:12px;margin:4px 0 10px;color:#25aefe;
  font-size:20px;font-variant-numeric:tabular-nums;
}
.strong-rest::before,.strong-rest::after{
  content:"";height:4px;border-radius:999px;background:#062539;
}
.strong-rest.active::before{background:#25aefe;}
.strong-help{color:#777;font-size:12px;margin-top:4px;}
.strong-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 22px 22px;}
.st-key-strong_logger div[data-testid="stNumberInput"] input{
  background:#292929;color:#fff;border:0;border-radius:8px;min-height:42px;
  text-align:center;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;
}
.st-key-strong_logger div[data-testid="stTextInput"] input{
  background:#292929;color:#fff;border:1px solid rgba(255,255,255,.08);border-radius:8px;
}
.st-key-strong_logger div.stButton > button{
  min-height:42px;border-radius:10px;border-color:rgba(255,255,255,.08);
  background:#2b2b2b;color:#35aaff;font-weight:800;
}
.st-key-strong_logger div.stButton > button[kind="primary"]{
  background:#2ecc71;border-color:#2ecc71;color:#fff;
}
@media (max-width:640px){
  .block-container{padding-left:.45rem;padding-right:.45rem;}
  .st-key-strong_logger{border-left:0;border-right:0;border-radius:0;margin-left:-.45rem!important;margin-right:-.45rem!important;padding-left:14px!important;padding-right:14px!important;}
  .st-key-strong_topbar{margin-left:-14px!important;margin-right:-14px!important;padding:8px 12px!important;}
  .strong-top{grid-template-columns:42px 48px 1fr 92px;padding:8px 12px;}
  .strong-top .timer{font-size:18px}.strong-finish{font-size:17px}
  .strong-head,.strong-section{padding-left:14px;padding-right:14px;}
  .strong-stats{padding-left:14px;padding-right:14px;}
  .strong-title{font-size:25px}.strong-duration{font-size:22px}
  .strong-ex-title{font-size:20px}
  .strong-col-head{grid-template-columns:.62fr 1.4fr .86fr .86fr .62fr;gap:6px;font-size:10px;}
  .strong-prev{font-size:15px}.strong-row-label{font-size:18px}
  .st-key-strong_logger div[data-testid="stNumberInput"] input{font-size:19px;min-height:40px;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] .strong-prev{min-width:28px;font-size:13px;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] div[data-testid="stTextInput"]{width:44px!important;min-width:44px!important;}
  .st-key-strong_logger [class*="st-key-kg_txt_"],
  .st-key-strong_logger [class*="st-key-reps_txt_"]{width:44px!important;min-width:44px!important;flex-basis:44px!important;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] div.stButton > button{min-width:36px!important;width:36px!important;}
}
</style>
""", unsafe_allow_html=True)

db.init_db()


@st.cache_data(ttl=60)
def load_catalog():
    return db.load_exercises_df()


def today_str():
    return date.today().isoformat()


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.now()


def duration_label(started_at: str) -> str:
    seconds = max(0, int((datetime.now() - parse_dt(started_at)).total_seconds()))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def set_previous_label(prev: list[dict], index: int) -> str:
    if index >= len(prev):
        return "—"
    p = prev[index]
    try:
        weight = float(p["weight_kg"])
        reps = int(p["reps"])
    except (KeyError, TypeError, ValueError):
        return "—"
    return f"{weight:g} kg × {reps}"


def ensure_active_shape(active: dict):
    """Backfill active workout state as the UI evolves across reruns."""
    active.setdefault("started_at", datetime.now().isoformat(timespec="seconds"))
    active.setdefault("exercises", [])
    for pos, ex in enumerate(active["exercises"]):
        ex.setdefault("position", pos)
        ex.setdefault("sets", [])
        ex.setdefault("note", "")
        for idx, stt in enumerate(ex["sets"]):
            stt.setdefault("set_id", str(uuid.uuid4()))
            stt.setdefault("set_index", idx + 1)
            stt.setdefault("side", "left" if ex.get("is_unilateral") else "both")
            stt.setdefault("reps", 5)
            stt.setdefault("weight_kg", 20.0)
            stt.setdefault("rpe", None)
            stt.setdefault("is_warmup", 0)
            stt.setdefault("completed", 0)


def mark_rest_started(active: dict, set_id: str):
    st.session_state["strong_rest"] = {
        "session_id": active["session_id"],
        "set_id": set_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "target_s": 120,
    }


def rest_state(active: dict) -> dict | None:
    rest = st.session_state.get("strong_rest")
    if not rest or rest.get("session_id") != active.get("session_id"):
        return None
    elapsed = max(0, int((datetime.now() - parse_dt(rest.get("started_at"))).total_seconds()))
    target = int(rest.get("target_s") or 120)
    remaining = max(0, target - elapsed)
    rest["elapsed_s"] = elapsed
    rest["remaining_s"] = remaining
    rest["progress"] = min(1.0, elapsed / target) if target else 0.0
    return rest


def rest_label(seconds: int) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{sec:02d}"


def finish_active_workout(active: dict):
    snap = todays_readiness_snapshot(active["date"])
    db.upsert_strength_session({
        "session_id": active["session_id"], "date": active["date"],
        "started_at": active["started_at"],
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
        "routine_id": active.get("routine_id"),
        **snap,
    })
    for ex in active["exercises"]:
        for stt in ex["sets"]:
            db.upsert_strength_set({
                "set_id": stt["set_id"], "session_id": active["session_id"],
                "exercise_id": ex["exercise_id"], "position": ex["position"],
                "set_index": stt["set_index"], "side": stt["side"],
                "reps": stt["reps"], "weight_kg": stt["weight_kg"],
                "rpe": stt.get("rpe"), "is_warmup": stt["is_warmup"],
                "completed": stt["completed"],
            })
    st.session_state.pop("active", None)
    st.session_state.pop("strong_rest", None)


def workout_completion_status(active: dict) -> dict:
    working = 0
    completed = 0
    for ex in active.get("exercises", []):
        for stt in ex.get("sets", []):
            if stt.get("is_warmup"):
                continue
            working += 1
            completed += int(bool(int(stt.get("completed") or 0)))
    return {
        "working_sets": working,
        "completed_working_sets": completed,
        "pending_working_sets": max(0, working - completed),
    }


def resolve_bodyweight(day: str):
    """Bodyweight for `day` from body_metrics, forward-filled from the most
    recent prior weigh-in."""
    bm = db.load_body_metrics_df()
    if bm.empty:
        return None
    bm = bm.copy()
    bm["date"] = bm["date"].astype(str).str[:10]
    bm = bm[bm["date"] <= day].sort_values("date")
    if bm.empty:
        return None
    val = bm.iloc[-1]["weight_kg"]
    return None if pd.isna(val) else float(val)


def todays_readiness_snapshot(day: str) -> dict:
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(db.load_activities_df(), daily)
    if daily.empty:
        return analysis.readiness_snapshot_from_daily(None)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    match = daily[daily["date"].dt.strftime("%Y-%m-%d") == day]
    row = match.iloc[-1] if not match.empty else None
    return analysis.readiness_snapshot_from_daily(row)


def active_to_frames(active: dict):
    """Build (sessions_df, sets_df) from in-memory active state for live totals."""
    sessions = pd.DataFrame([{
        "session_id": active["session_id"], "date": active["date"],
        "bodyweight_kg": active.get("bodyweight_kg") or 0.0,
    }])
    rows = []
    for ex in active["exercises"]:
        for s in ex["sets"]:
            rows.append({
                "set_id": s["set_id"], "session_id": active["session_id"],
                "exercise_id": ex["exercise_id"], "position": ex["position"],
                "set_index": s["set_index"], "side": s["side"],
                "reps": s["reps"], "weight_kg": s["weight_kg"],
                "rpe": s.get("rpe"), "is_warmup": s["is_warmup"],
                "completed": s["completed"],
            })
    sets = pd.DataFrame(rows)
    return sessions, sets


def routine_to_exercises(routine_id: str):
    """Build active-state exercise entries from a saved routine."""
    rex = db.load_routine_exercises_df()
    rex = rex[rex["routine_id"] == routine_id].sort_values("position")
    cat = db.load_exercises_df()
    out = []
    for pos, (_, r) in enumerate(rex.iterrows()):
        m = cat[cat["exercise_id"] == r["exercise_id"]]
        if m.empty:
            continue
        ex = m.iloc[0]
        sets = []
        target_sets = r.get("target_sets")
        try:
            target_sets = int(target_sets) if pd.notna(target_sets) else 0
        except (TypeError, ValueError):
            target_sets = 0
        target_reps = r.get("target_reps")
        target_weight = r.get("target_weight")
        for idx in range(max(0, target_sets)):
            sets.append({
                "set_id": str(uuid.uuid4()),
                "set_index": idx + 1,
                "side": "left" if int(ex["is_unilateral"]) else "both",
                "reps": int(target_reps) if pd.notna(target_reps) else 5,
                "weight_kg": float(target_weight) if pd.notna(target_weight) else 20.0,
                "rpe": None,
                "is_warmup": 0,
                "completed": 0,
            })
        out.append({
            "position": pos,
            "exercise_id": ex["exercise_id"],
            "name": ex["name"],
            "is_unilateral": int(ex["is_unilateral"]),
            "is_bodyweight": int(ex["is_bodyweight"]),
            "sets": sets,
        })
    return out


def save_active_as_routine(active: dict, routine_name: str) -> str:
    """Persist the active workout's exercises as a reusable routine."""
    rid = str(uuid.uuid4())
    db.upsert_routine({"routine_id": rid, "name": routine_name})
    for pos, ex in enumerate(active["exercises"]):
        work = [s for s in ex["sets"] if not s["is_warmup"]]
        first = work[0] if work else (ex["sets"][0] if ex["sets"] else None)
        db.upsert_routine_exercise({
            "routine_id": rid, "position": pos,
            "exercise_id": ex["exercise_id"],
            "target_sets": (len(work) or len(ex["sets"]) or None),
            "target_reps": (first["reps"] if first else None),
            "target_weight": (first["weight_kg"] if first else None),
        })
    return rid


# ── page ──────────────────────────────────────────────────────────────────────
st.title("🏋️ Strength")

catalog = load_catalog()

tab_log, tab_history, tab_insights, tab_body = st.tabs(
    ["Log workout", "History", "Insights", "Bodyweight"])

with tab_history:
    st.subheader("History")
    sessions = db.load_strength_sessions_df()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("No workouts logged yet.")
    else:
        summaries = analysis.summarize_sessions(sessions, sets, catalog,
                                                config.ONE_RM_FORMULA)
        sm = {r["session_id"]: r for _, r in summaries.iterrows()}
        for _, sess in sessions.sort_values("date", ascending=False).iterrows():
            session_id = str(sess["session_id"])
            summ = sm.get(sess["session_id"], {})
            st.markdown(cockpit.strength_session_card(dict(sess), dict(summ)),
                        unsafe_allow_html=True)
            snap = {k: sess.get(k) for k in (
                "readiness_score", "readiness_level", "hrv_status",
                "body_battery_start")}
            st.markdown(cockpit.strength_readiness_badge(snap),
                        unsafe_allow_html=True)
            with st.expander("Sets"):
                ssets = sets[sets["session_id"] == sess["session_id"]]
                if ssets.empty:
                    st.caption("No sets.")
                else:
                    named = ssets.merge(
                        catalog[["exercise_id", "name"]], on="exercise_id",
                        how="left")
                    st.table(named[["name", "set_index", "side", "reps",
                                    "weight_kg", "rpe", "is_warmup",
                                    "completed"]])
            with st.expander("Delete workout"):
                st.caption("This removes the saved workout and all of its sets.")
                label = f"{sess.get('date')} — {sess.get('name') or 'Workout'}"
                confirmed = st.checkbox(
                    f"Delete {label}",
                    key=f"confirm_delete_workout_{session_id}",
                )
                if st.button(
                    "Delete workout",
                    key=f"delete_workout_{session_id}",
                    disabled=not confirmed,
                ):
                    db.delete_strength_session(session_id)
                    st.cache_data.clear()
                    st.success("Workout deleted.")
                    st.rerun()
            st.write("")

        st.divider()
        st.subheader("Estimated 1RM progress")
        prs = analysis.compute_pr_timeline(sets, sessions, catalog,
                                           config.ONE_RM_FORMULA)
        if prs.empty:
            st.caption("Log a few working sets to see 1RM trends.")
        else:
            id_to_name = dict(zip(catalog["exercise_id"], catalog["name"])) \
                if not catalog.empty else {}
            ex_ids = list(prs["exercise_id"].unique())
            choices = {id_to_name.get(i, i): i for i in ex_ids}
            label = st.selectbox("Exercise", list(choices.keys()))
            ex_id = choices[label]
            fig = cockpit.strength_onerm_trend(
                prs[prs["exercise_id"] == ex_id], label)
            st.plotly_chart(fig, use_container_width=True)

with tab_insights:
    st.subheader("Insights")
    sessions = db.load_strength_sessions_df()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("Log a few workouts (especially the main lifts) to unlock standards, balance, and readiness insights.")
    else:
        profile = db.load_profile()
        bodyweight = resolve_bodyweight(today_str())
        prs = analysis.compute_pr_timeline(sets, sessions, catalog, config.ONE_RM_FORMULA)
        best_map = (prs.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                    if not prs.empty else {})

        st.markdown("##### Strength standards")
        standards = analysis.compute_strength_standards(best_map, profile, bodyweight)
        st.markdown(cockpit.strength_standards_panel(standards), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Muscle balance")
        balance = analysis.compute_balance(best_map, sets, catalog, config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_balance_panel(balance), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Readiness vs performance")
        corr = analysis.compute_readiness_performance(sessions, sets, catalog,
                                                      formula=config.ONE_RM_FORMULA)
        panel = cockpit.strength_correlation_panel(corr)
        if isinstance(panel, str):
            st.caption(panel)
        else:
            st.plotly_chart(panel, use_container_width=True)
            if corr.get("insight"):
                st.caption(corr["insight"])

with tab_body:
    st.subheader("Bodyweight")
    day = today_str()
    current = resolve_bodyweight(day)
    st.caption("Synced from Garmin weigh-ins; override manually below if needed.")
    st.metric("Current bodyweight", f"{current:.1f} kg" if current else "—")
    with st.form("bw_form"):
        manual = st.number_input("Manual bodyweight (kg)", min_value=0.0,
                                 max_value=400.0, step=0.1,
                                 value=float(current or 0.0))
        if st.form_submit_button("Save manual weight") and manual > 0:
            db.upsert_body_metric({"date": day, "weight_kg": float(manual),
                                   "source": "manual"})
            st.success(f"Saved {manual:.1f} kg for {day}.")
            st.rerun()

with tab_log:
    active = st.session_state.get("active")

    if active is None:
        st.subheader("Start a workout")
        name = st.text_input("Workout name", value="Workout")
        routines = db.load_routines_df()
        routine_names = routines["name"].tolist() if not routines.empty else []
        chosen = st.selectbox("From routine (optional)",
                              ["— blank —"] + routine_names)
        if st.button("▶ Start", type="primary"):
            exercises, routine_id, start_name = [], None, (name or "Workout")
            if chosen != "— blank —" and not routines.empty:
                rrow = routines[routines["name"] == chosen].iloc[0]
                routine_id = rrow["routine_id"]
                start_name = chosen
                exercises = routine_to_exercises(routine_id)
            st.session_state["active"] = {
                "session_id": str(uuid.uuid4()),
                "name": start_name,
                "date": today_str(),
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "bodyweight_kg": resolve_bodyweight(today_str()),
                "routine_id": routine_id,
                "exercises": exercises,
            }
            st.rerun()
        st.stop()

    # ── active workout ──
    ensure_active_shape(active)
    elapsed = duration_label(active["started_at"])
    rest = rest_state(active)
    finish_requested = False

    with st.container(key="strong_logger"):
        with st.container(
            key="strong_topbar",
            horizontal=True,
            horizontal_alignment="center",
            vertical_alignment="center",
            gap="small",
        ):
            st.markdown("<div class='strong-top-cell icon'>⌄</div>",
                        unsafe_allow_html=True)
            if st.button("↻", key="strong_rest_reset", help="Restart rest timer"):
                st.session_state["strong_rest"] = {
                    "session_id": active["session_id"],
                    "set_id": None,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "target_s": 120,
                }
                st.rerun()
            st.markdown(f"<div class='strong-top-cell timer'>{elapsed}</div>",
                        unsafe_allow_html=True)
            if st.button("FINISH", key="finish_top", help="Finish and save workout"):
                finish_requested = True

        sessions_df, sets_df = active_to_frames(active)
        summary = analysis.summarize_sessions(sessions_df, sets_df, catalog,
                                              config.ONE_RM_FORMULA)
        s = summary.iloc[0] if not summary.empty else {}
        top_1rm = s.get("top_est_1rm_kg")
        workout_name_html = html.escape(str(active.get("name") or "Workout"))
        volume_html = f"{(s.get('total_volume_kg') or 0):,.0f} kg"
        sets_html = str(int(s.get("working_sets") or 0))
        top_html = f"{top_1rm:,.0f} kg" if top_1rm else "—"
        st.markdown(
            f"""
            <div class='strong-head'>
              <div class='strong-title'>{workout_name_html}</div>
              <div class='strong-duration'>{elapsed}</div>
            </div>
            <div class='strong-stats'>
              <div class='strong-stat'><div class='lab'>Volume</div><div class='val'>{volume_html}</div></div>
              <div class='strong-stat'><div class='lab'>Sets</div><div class='val'>{sets_html}</div></div>
              <div class='strong-stat'><div class='lab'>Top 1RM</div><div class='val'>{top_html}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        names = catalog["name"].tolist() if not catalog.empty else []
        pick = st.selectbox("Add exercise", [""] + names)
        if st.button("➕ Add to workout") and pick:
            ex_row = catalog[catalog["name"] == pick].iloc[0]
            active["exercises"].append({
                "position": len(active["exercises"]),
                "exercise_id": ex_row["exercise_id"],
                "name": ex_row["name"],
                "is_unilateral": int(ex_row["is_unilateral"]),
                "is_bodyweight": int(ex_row["is_bodyweight"]),
                "sets": [],
            })
            st.rerun()

        with st.expander("➕ New custom exercise"):
            cx_name = st.text_input("Name", key="cx_name")
            cx_cat = st.selectbox(
                "Category",
                ["barbell", "dumbbell", "machine", "cable", "bodyweight"],
                key="cx_cat")
            cx_pat = st.selectbox("Movement pattern",
                                  list(strength_catalog.MOVEMENT_PATTERNS),
                                  key="cx_pat")
            cx_muscle = st.text_input("Primary muscle", key="cx_muscle")
            cx_uni = st.checkbox("Unilateral (log left/right)", key="cx_uni")
            cx_bw = st.checkbox("Bodyweight exercise", key="cx_bw")
            if st.button("Create exercise") and cx_name.strip():
                slug = "custom-" + "".join(
                    c if c.isalnum() else "-" for c in cx_name.strip().lower()
                ).strip("-")
                db.upsert_exercise({
                    "exercise_id": slug, "name": cx_name.strip(),
                    "category": cx_cat, "movement_pattern": cx_pat,
                    "primary_muscle": cx_muscle.strip(),
                    "is_unilateral": int(cx_uni),
                    "is_bodyweight": int(cx_bw),
                    "is_main_lift": 0, "is_custom": 1,
                })
                load_catalog.clear()
                st.success(f"Added {cx_name.strip()}.")
                st.rerun()

        hist_sessions = db.load_strength_sessions_df()
        hist_sets = db.load_strength_sets_df()

        for ei, ex in enumerate(active["exercises"]):
            ex_name_html = html.escape(str(ex.get("name") or "Exercise"))
            st.markdown(
                f"""
                <div class='strong-ex-head'>
                  <div class='strong-ex-title'>{ex_name_html}</div>
                  <div class='strong-ex-tools'>•••</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            note_key = f"note_{active['session_id']}_{ex['exercise_id']}_{ei}"
            ex["note"] = st.text_input(
                "Exercise note",
                value=str(ex.get("note") or ""),
                key=note_key,
                placeholder="Exercise note",
                label_visibility="collapsed",
            )
            if str(ex.get("note") or "").strip():
                note_html = html.escape(str(ex.get("note") or ""))
                st.markdown(f"<div class='strong-note'>{note_html}</div>",
                            unsafe_allow_html=True)

            uni = bool(ex["is_unilateral"])
            prev = analysis.last_session_sets(
                ex["exercise_id"], hist_sessions, hist_sets)
            st.markdown(
                "<div class='strong-col-head'><span>Set</span><span>Previous</span>"
                "<span>Kg</span><span>Reps</span><span>✓</span></div>",
                unsafe_allow_html=True,
            )

            work_n = 0
            for si, stt in enumerate(ex["sets"]):
                completed = bool(int(stt.get("completed") or 0))
                if stt["is_warmup"]:
                    badge = "W"
                    badge_class = "warm"
                    prev_label = "—"
                else:
                    work_n += 1
                    badge = str(work_n)
                    badge_class = "done" if completed else "work"
                    prev_label = set_previous_label(prev, work_n - 1)
                with st.container(
                    key=f"strong_setrow_{stt['set_id']}",
                    horizontal=True,
                    vertical_alignment="center",
                    gap="small",
                ):
                    if st.button(badge, key=f"badge_{stt['set_id']}",
                                 help="Tap to toggle warmup"):
                        stt["is_warmup"] = 0 if stt["is_warmup"] else 1
                        st.rerun()
                    st.markdown(f"<div class='strong-prev'>{prev_label}</div>",
                                unsafe_allow_html=True)
                    kg_raw = st.text_input(
                        "kg", value=f"{float(stt['weight_kg']):g}",
                        key=f"kg_txt_{stt['set_id']}",
                        label_visibility="collapsed")
                    reps_raw = st.text_input(
                        "reps", value=str(int(stt["reps"])),
                        key=f"reps_txt_{stt['set_id']}",
                        label_visibility="collapsed")
                    try:
                        stt["weight_kg"] = max(
                            0.0, float(kg_raw.replace(",", ".")))
                    except (TypeError, ValueError):
                        pass
                    try:
                        stt["reps"] = max(
                            0, int(float(reps_raw.replace(",", "."))))
                    except (TypeError, ValueError):
                        pass
                    check_label = "✓" if completed else "○"
                    check_type = "primary" if completed else "secondary"
                    if st.button(check_label, key=f"done_{stt['set_id']}",
                                 type=check_type, help="Toggle completed"):
                        stt["completed"] = 0 if completed else 1
                        if stt["completed"]:
                            mark_rest_started(active, stt["set_id"])
                        st.rerun()
                if completed:
                    st.markdown("<div class='strong-done-strip'></div>",
                                unsafe_allow_html=True)
                if rest and rest.get("set_id") == stt["set_id"]:
                    st.markdown(
                        f"<div class='strong-rest active'><span>{rest_label(rest['remaining_s'])}</span></div>",
                        unsafe_allow_html=True,
                    )

            if st.button("➕ Add Set", key=f"addset_{ei}"):
                last = ex["sets"][-1] if ex["sets"] else None
                work_count = len(
                    [s for s in ex["sets"] if not s.get("is_warmup")])
                next_prev = prev[work_count] if len(prev) > work_count else None
                reps = 5
                weight = 20.0
                if last:
                    reps = int(last["reps"])
                    weight = float(last["weight_kg"])
                elif next_prev:
                    reps = int(next_prev["reps"])
                    weight = float(next_prev["weight_kg"])
                ex["sets"].append({
                    "set_id": str(uuid.uuid4()),
                    "set_index": len(ex["sets"]) + 1,
                    "side": (last["side"] if last else ("left" if uni else "both")),
                    "reps": reps,
                    "weight_kg": weight,
                    "rpe": None, "is_warmup": 0, "completed": 0,
                })
                st.rerun()

            with st.expander("Set details"):
                for si, stt in enumerate(ex["sets"]):
                    drow = st.columns([0.7, 1.0, 1.0, 0.7])
                    drow[0].caption(f"Set {si + 1}")
                    rpe_val = drow[1].number_input(
                        "RPE", min_value=0.0, max_value=10.0, step=0.5,
                        value=float(stt.get("rpe") or 0.0),
                        key=f"rpe_{stt['set_id']}")
                    stt["rpe"] = rpe_val or None
                    if uni:
                        stt["side"] = drow[2].selectbox(
                            "Side", ["left", "right"],
                            index=(1 if stt.get("side") == "right" else 0),
                            key=f"side_{stt['set_id']}")
                    else:
                        drow[2].caption("Both sides")
                    if drow[3].button("Remove", key=f"del_{stt['set_id']}"):
                        ex["sets"].pop(si)
                        for j, t in enumerate(ex["sets"]):
                            t["set_index"] = j + 1
                        st.rerun()

        st.divider()
        with st.expander("💾 Save this workout as a routine"):
            rname = st.text_input("Routine name", value=active["name"],
                                  key="save_rt")
            if st.button("Save routine") and active["exercises"] and rname.strip():
                save_active_as_routine(active, rname.strip())
                st.success(f"Saved routine '{rname.strip()}'.")

        completion = workout_completion_status(active)
        confirm_pending = True
        if completion["pending_working_sets"]:
            st.warning(
                f"{completion['pending_working_sets']} working set(s) are still "
                "unchecked. They will save as incomplete and will not count in "
                "volume or PR analytics."
            )
            confirm_pending = st.checkbox(
                "Save unchecked sets as incomplete",
                key="confirm_finish_pending",
            )

        fcol1, fcol2 = st.columns(2)
        if fcol1.button("✅ Finish & save", type="primary"):
            finish_requested = True
        has_content = any(ex.get("sets") for ex in active["exercises"])
        discard_ok = True
        if has_content:
            discard_ok = st.checkbox("Confirm discard",
                                     key="confirm_discard_active")
        if fcol2.button("🗑 Discard", disabled=has_content and not discard_ok):
            del st.session_state["active"]
            st.session_state.pop("strong_rest", None)
            st.rerun()
        if finish_requested:
            if confirm_pending:
                finish_active_workout(active)
                st.success("Workout saved.")
                st.rerun()
            else:
                st.warning("Check off the pending sets or confirm incomplete save.")
