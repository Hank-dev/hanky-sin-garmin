"""Strength logger — Strong-style live workout logging on its own page.

Live state lives in st.session_state["active"] until you press Finish, which
persists the session + sets and stamps the readiness snapshot for the day.
"""
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

db.init_db()


@st.cache_data(ttl=60)
def load_catalog():
    return db.load_exercises_df()


def today_str():
    return date.today().isoformat()


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
    """Build active-state exercise entries (empty sets) from a saved routine."""
    rex = db.load_routine_exercises_df()
    rex = rex[rex["routine_id"] == routine_id].sort_values("position")
    cat = db.load_exercises_df()
    out = []
    for pos, (_, r) in enumerate(rex.iterrows()):
        m = cat[cat["exercise_id"] == r["exercise_id"]]
        if m.empty:
            continue
        ex = m.iloc[0]
        out.append({
            "position": pos,
            "exercise_id": ex["exercise_id"],
            "name": ex["name"],
            "is_unilateral": int(ex["is_unilateral"]),
            "is_bodyweight": int(ex["is_bodyweight"]),
            "sets": [],
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

tab_log, tab_history, tab_body = st.tabs(["Log workout", "History", "Bodyweight"])

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
                                    "weight_kg", "rpe", "is_warmup"]])
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
    st.subheader(f"🟢 {active['name']} — {active['date']}")
    sessions_df, sets_df = active_to_frames(active)
    summary = analysis.summarize_sessions(sessions_df, sets_df, catalog,
                                          config.ONE_RM_FORMULA)
    s = summary.iloc[0] if not summary.empty else {}
    c1, c2, c3 = st.columns(3)
    c1.metric("Volume", f"{(s.get('total_volume_kg') or 0):,.0f} kg")
    c2.metric("Working sets", int(s.get("working_sets") or 0))
    top = s.get("top_est_1rm_kg")
    c3.metric("Top est-1RM", f"{top:,.0f} kg" if top else "—")

    # add exercise
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
            "Category", ["barbell", "dumbbell", "machine", "cable", "bodyweight"],
            key="cx_cat")
        cx_pat = st.selectbox("Movement pattern",
                              list(strength_catalog.MOVEMENT_PATTERNS), key="cx_pat")
        cx_muscle = st.text_input("Primary muscle", key="cx_muscle")
        cx_uni = st.checkbox("Unilateral (log left/right)", key="cx_uni")
        cx_bw = st.checkbox("Bodyweight exercise", key="cx_bw")
        if st.button("Create exercise") and cx_name.strip():
            slug = "custom-" + "".join(
                c if c.isalnum() else "-" for c in cx_name.strip().lower()
            ).strip("-")
            db.upsert_exercise({
                "exercise_id": slug, "name": cx_name.strip(), "category": cx_cat,
                "movement_pattern": cx_pat, "primary_muscle": cx_muscle.strip(),
                "is_unilateral": int(cx_uni), "is_bodyweight": int(cx_bw),
                "is_main_lift": 0, "is_custom": 1,
            })
            load_catalog.clear()
            st.success(f"Added {cx_name.strip()}.")
            st.rerun()

    # per-exercise set logging
    for ei, ex in enumerate(active["exercises"]):
        st.markdown(f"**{ex['name']}**")
        if ex["sets"]:
            st.table(pd.DataFrame([{
                "set": s["set_index"], "side": s["side"], "reps": s["reps"],
                "kg": s["weight_kg"], "rpe": s.get("rpe"),
                "warmup": bool(s["is_warmup"]),
            } for s in ex["sets"]]))
        cols = st.columns([1, 1, 1, 1, 1])
        reps = cols[0].number_input("reps", 0, 100, 5, key=f"r{ei}")
        wt = cols[1].number_input("kg", 0.0, 500.0, 20.0, step=1.0, key=f"w{ei}")
        rpe = cols[2].number_input("RPE", 0.0, 10.0, 0.0, step=0.5, key=f"e{ei}")
        warm = cols[3].checkbox("warmup", key=f"wu{ei}")
        side = "both"
        if ex["is_unilateral"]:
            side = cols[4].selectbox("side", ["left", "right"], key=f"sd{ei}")
        if st.button("Add set", key=f"add{ei}"):
            ex["sets"].append({
                "set_id": str(uuid.uuid4()),
                "set_index": len(ex["sets"]) + 1, "side": side,
                "reps": int(reps), "weight_kg": float(wt),
                "rpe": (float(rpe) or None), "is_warmup": int(warm),
                "completed": 1,
            })
            st.rerun()
        if ex["sets"] and st.button("Remove last set", key=f"rm{ei}"):
            ex["sets"].pop()
            st.rerun()

    st.divider()
    with st.expander("💾 Save this workout as a routine"):
        rname = st.text_input("Routine name", value=active["name"], key="save_rt")
        if st.button("Save routine") and active["exercises"] and rname.strip():
            save_active_as_routine(active, rname.strip())
            st.success(f"Saved routine '{rname.strip()}'.")

    fcol1, fcol2 = st.columns(2)
    if fcol1.button("✅ Finish & save", type="primary"):
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
        del st.session_state["active"]
        st.success("Workout saved.")
        st.rerun()
    if fcol2.button("🗑 Discard"):
        del st.session_state["active"]
        st.rerun()
