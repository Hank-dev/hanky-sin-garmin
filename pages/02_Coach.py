"""Coach memory — view and curate what the coach knows about you, and approve
AI-suggested memories. Manual entries save instantly; AI suggestions require
your approval before they are stored."""
import importlib
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _local_now():
    try:
        return datetime.now(ZoneInfo(config.LOCAL_TIMEZONE))
    except ZoneInfoNotFoundError:
        return datetime.now()


def _present(value) -> bool:
    return pd.notna(value) and str(value or "").strip() != ""


def _clean_text(value) -> str:
    return "" if not _present(value) else str(value).strip()


def _timestamp_label(value) -> str:
    return _clean_text(value).replace("T", " ")[:16]


def _memory_meta(r) -> list[str]:
    meta = []
    if _present(r.get("target_date")):
        meta.append(f"target {r['target_date']}")
    if _present(r.get("body_part")):
        meta.append(str(r["body_part"]))
    if r.get("category") in ("injury", "note"):
        metadata_date = _clean_text(r.get("metadata_date"))
        metadata_time = _clean_text(r.get("metadata_time"))
        if metadata_date and metadata_time:
            meta.append(f"{metadata_date} {metadata_time}")
        elif metadata_date:
            meta.append(metadata_date)
        elif metadata_time:
            meta.append(metadata_time)
        if _present(r.get("created_at")):
            meta.append(f"added {_timestamp_label(r.get('created_at'))}")
        if _present(r.get("updated_at")) and r.get("updated_at") != r.get("created_at"):
            meta.append(f"updated {_timestamp_label(r.get('updated_at'))}")
    if r.get("source") == "ai":
        meta.append("ai")
    return meta


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
        metadata_date = metadata_time = None
        if cat in ("injury", "note"):
            now = _local_now()
            metadata = st.columns(2)
            with metadata[0]:
                metadata_date = st.date_input("Date", value=now.date())
            with metadata[1]:
                metadata_time = st.time_input(
                    "Time",
                    value=now.replace(second=0, microsecond=0, tzinfo=None).time(),
                )
        if st.form_submit_button("Save") and text.strip():
            rec = {"category": cat, "text": text.strip(), "source": "user"}
            if target_date.strip():
                rec["target_date"] = target_date.strip()
            if body_part.strip():
                rec["body_part"] = body_part.strip()
            if cat in ("injury", "note"):
                rec["metadata_date"] = metadata_date.isoformat()
                rec["metadata_time"] = metadata_time.strftime("%H:%M")
            db.add_memory(rec)
            st.rerun()

# ── grouped list with edit / archive / delete ────────────────────────────────
if memory.empty:
    st.caption("No active memories yet. Add one above, or use **Find things to "
               "remember** below.")
else:
    for cat in CATEGORIES:
        rows = memory[memory["category"] == cat]
        if cat == "coaching":
            rows = rows.sort_values("created_at", ascending=False)
        if rows.empty:
            continue
        st.markdown(f"#### {LABELS[cat]}")
        for _, r in rows.iterrows():
            mid = int(r["id"])
            cols = st.columns([6, 1, 1])
            with cols[0]:
                meta = _memory_meta(r)
                suffix = f"  ·  _{', '.join(meta)}_" if meta else ""
                new_text = st.text_input(f"edit-{mid}", value=str(r["text"]),
                                         label_visibility="collapsed")
                if suffix:
                    st.caption(suffix)
                if new_text.strip() and new_text.strip() != str(r["text"]):
                    db.update_memory(mid, {"text": new_text.strip()})
                    st.rerun()
                if cat in ("injury", "note"):
                    metadata = st.columns(2)
                    with metadata[0]:
                        new_date = st.text_input(
                            "Metadata date",
                            value=_clean_text(r.get("metadata_date")),
                            key=f"memory_metadata_date_{mid}",
                            placeholder="YYYY-MM-DD",
                        )
                    with metadata[1]:
                        new_time = st.text_input(
                            "Metadata time",
                            value=_clean_text(r.get("metadata_time")),
                            key=f"memory_metadata_time_{mid}",
                            placeholder="HH:MM",
                        )
                    new_date = new_date.strip()
                    new_time = new_time.strip()
                    old_date = _clean_text(r.get("metadata_date"))
                    old_time = _clean_text(r.get("metadata_time"))
                    if new_date != old_date or new_time != old_time:
                        db.update_memory(mid, {
                            "metadata_date": new_date or None,
                            "metadata_time": new_time or None,
                        })
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
        body_metrics = db.load_body_metrics_df()
        bodyweight = None
        if not body_metrics.empty:
            bw = body_metrics.dropna(subset=["weight_kg"]).sort_values("date")
            if not bw.empty:
                bodyweight = float(bw.iloc[-1]["weight_kg"])
        strength = analysis.summarize_strength(
            db.load_strength_sessions_df(), db.load_strength_sets_df(),
            db.load_exercises_df(), db.load_profile(), bodyweight,
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
