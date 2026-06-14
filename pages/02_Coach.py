"""Coach memory — view and curate what the coach knows about you, and approve
AI-suggested memories. Manual entries save instantly; AI suggestions require
your approval before they are stored."""
import importlib

import pandas as pd
import streamlit as st

import config
import db
import analysis
import ai
import cockpit

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
ai = importlib.reload(ai)
cockpit = importlib.reload(cockpit)

st.set_page_config(page_title="Coach — Hankø", page_icon="🧠", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)

db.init_db()

CATEGORIES = ["goal", "injury", "pattern", "coaching", "note"]
LABELS = {"goal": "🎯 Goals", "injury": "🩹 Injuries", "pattern": "🔁 Patterns",
          "coaching": "🗒️ Coaching log", "note": "📌 Notes"}

st.markdown(cockpit.section_label("What the coach knows"), unsafe_allow_html=True)

memory = db.load_memory_df()           # active only

# ── add a memory ─────────────────────────────────────────────────────────────
with st.expander("➕ Add a memory", expanded=memory.empty):
    with st.form("add_memory", clear_on_submit=True):
        c = st.columns([1, 3])
        with c[0]:
            cat = st.selectbox("Category", CATEGORIES)
        with c[1]:
            text = st.text_input("What should the coach remember?")
        extra = st.columns(2)
        with extra[0]:
            target_date = st.text_input("Target date (goals, YYYY-MM-DD)", "")
        with extra[1]:
            body_part = st.text_input("Body part (injuries)", "")
        if st.form_submit_button("Save") and text.strip():
            rec = {"category": cat, "text": text.strip(), "source": "user"}
            if target_date.strip():
                rec["target_date"] = target_date.strip()
            if body_part.strip():
                rec["body_part"] = body_part.strip()
            db.add_memory(rec)
            st.rerun()

# ── grouped list with edit / archive / delete ────────────────────────────────
if memory.empty:
    st.caption("No active memories yet. Add one above, or use **Find things to "
               "remember** below.")
else:
    for cat in CATEGORIES:
        rows = memory[memory["category"] == cat]
        if rows.empty:
            continue
        st.markdown(f"#### {LABELS[cat]}")
        for _, r in rows.iterrows():
            mid = int(r["id"])
            cols = st.columns([6, 1, 1])
            with cols[0]:
                meta = []
                if pd.notna(r.get("target_date")) and str(r.get("target_date") or "").strip():
                    meta.append(f"target {r['target_date']}")
                if pd.notna(r.get("body_part")) and str(r.get("body_part") or "").strip():
                    meta.append(str(r["body_part"]))
                if r.get("source") == "ai":
                    meta.append("ai")
                suffix = f"  ·  _{', '.join(meta)}_" if meta else ""
                new_text = st.text_input(f"edit-{mid}", value=str(r["text"]),
                                         label_visibility="collapsed")
                if suffix:
                    st.caption(suffix)
                if new_text.strip() and new_text.strip() != str(r["text"]):
                    db.update_memory(mid, {"text": new_text.strip()})
                    st.rerun()
            with cols[1]:
                if st.button("Archive", key=f"arch-{mid}", width="stretch"):
                    db.archive_memory(mid)
                    st.rerun()
            with cols[2]:
                if st.button("Delete", key=f"del-{mid}", width="stretch"):
                    db.delete_memory(mid)
                    st.rerun()

# ── AI suggestions (button-triggered, approve before save) ────────────────────
st.markdown(cockpit.section_label("Find things to remember"), unsafe_allow_html=True)

if not config.ANTHROPIC_API_KEY:
    st.caption("Set `ANTHROPIC_API_KEY` in .env to enable AI suggestions.")
else:
    if st.button("✨ Find things to remember"):
        daily = db.load_daily_df()
        acts = db.load_activities_df()
        summary = (analysis.summarize(daily, acts, lookback=14)
                   if not daily.empty else {})
        strength = analysis.summarize_strength(
            db.load_strength_sessions_df(), db.load_strength_sets_df(),
            db.load_exercises_df(), db.load_profile(), None,
            formula=config.ONE_RM_FORMULA)
        digest = analysis.build_coach_memory_digest(memory)
        with st.spinner("Looking for durable patterns worth remembering…"):
            st.session_state["mem_candidates"] = ai.suggest_memories(
                summary, strength, digest)

    candidates = st.session_state.get("mem_candidates", [])
    if not candidates:
        st.caption("No pending suggestions. Press the button to generate some.")
    for i, cand in enumerate(candidates):
        with st.container(border=True):
            st.markdown(f"**{cand['category']}** — {cand['text']}")
            if cand.get("rationale"):
                st.caption(cand["rationale"])
            b = st.columns([1, 1, 4])
            with b[0]:
                if st.button("Approve", key=f"appr-{i}", width="stretch"):
                    rec = {"category": cand["category"], "text": cand["text"],
                           "source": "ai"}
                    for k in ("confidence", "target_date", "body_part"):
                        if cand.get(k):
                            rec[k] = cand[k]
                    db.add_memory(rec)
                    st.session_state["mem_candidates"] = [
                        c for j, c in enumerate(candidates) if j != i]
                    st.rerun()
            with b[1]:
                if st.button("Reject", key=f"rej-{i}", width="stretch"):
                    st.session_state["mem_candidates"] = [
                        c for j, c in enumerate(candidates) if j != i]
                    st.rerun()
