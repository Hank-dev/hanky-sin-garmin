"""Coach page: chat-first interface plus curated coach memories."""
import html
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
import fitness_agent

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
ai = importlib.reload(ai)
cockpit = importlib.reload(cockpit)

CATEGORIES = ["goal", "injury", "pattern", "coaching", "note"]
COACH_CHAT_SEED_VERSION = "coach-chat-v3"
CATEGORY_LABELS = {
    "goal": "Goals",
    "injury": "Injuries",
    "pattern": "Patterns",
    "coaching": "Coaching log",
    "note": "Notes",
}


st.markdown(
    """
    <style>
    .coach-page-head{margin:4px 0 22px;}
    .coach-page-title{font-family:var(--font-serif);font-size:34px;line-height:1.05;
      color:var(--text);font-weight:400;}
    .coach-page-sub{color:var(--text-dim);font-size:14px;line-height:1.45;margin-top:8px;
      max-width:72ch;}
    .coach-chat-titlebar{display:flex;align-items:center;gap:14px;min-width:0;}
    .coach-chat-face{width:52px;height:52px;border-radius:50%;flex:0 0 auto;overflow:hidden;
      border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);
      box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 9%,transparent);}
    .coach-chat-face img{width:100%;height:100%;object-fit:cover;display:block;}
    .coach-chat-title{display:grid;gap:4px;min-width:0;}
    .coach-chat-title .kicker{font-family:var(--font-mono);font-size:10px;font-weight:500;
      letter-spacing:.16em;text-transform:uppercase;color:var(--text-faint);}
    .coach-chat-title .name{font-size:22px;font-weight:700;color:var(--text);line-height:1.15;}
    .coach-chat-title .meta{font-size:13px;color:var(--text-dim);line-height:1.4;}
    .coach-memory-card{display:grid;gap:7px;padding:2px 0 0;min-width:0;}
    .coach-memory-kicker{font-family:var(--font-mono);font-size:10px;font-weight:500;
      letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
    .coach-memory-text{font-size:16px;line-height:1.5;color:var(--text);max-width:82ch;
      overflow-wrap:anywhere;}
    .coach-memory-meta{font-size:13px;line-height:1.45;color:var(--text-faint);
      overflow-wrap:anywhere;}
    .coach-memory-meta:empty{display:none;}
    .coach-candidate{display:grid;gap:6px;padding-top:2px;min-width:0;}
    .coach-candidate .category{font-family:var(--font-mono);font-size:10px;
      letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
    .coach-candidate .text{font-size:15px;line-height:1.5;color:var(--text);
      overflow-wrap:anywhere;}
    .coach-candidate .why{font-size:13px;line-height:1.45;color:var(--text-faint);}
    .coach-memory-note{color:var(--text-dim);font-size:13.5px;line-height:1.45;margin:0;}

    .st-key-coach_chat_shell [data-testid="stVerticalBlockBorderWrapper"]{
      padding:0!important;overflow:hidden!important;border-color:var(--border)!important;
      background:linear-gradient(180deg,var(--surface-2),var(--surface) 70%,#0a0a0a)!important;}
    .st-key-coach_chat_shell [data-testid="stVerticalBlock"]{gap:0!important;}
    .st-key-coach_chat_header{padding:18px 20px 14px;border-bottom:1px solid var(--hairline);}
    .st-key-coach_chat_header [data-testid="stHorizontalBlock"]{
      display:grid!important;grid-template-columns:minmax(0,1fr) 42px 42px!important;
      gap:8px!important;align-items:center!important;}
    .st-key-coach_chat_header [data-testid="column"]{width:auto!important;min-width:0!important;}
    .st-key-coach_chat_header [data-testid="column"]:nth-child(2),
    .st-key-coach_chat_header [data-testid="column"]:nth-child(3){
      width:42px!important;min-width:42px!important;max-width:42px!important;flex:0 0 42px!important;}
    .st-key-coach_chat_header .stButton>button{
      width:42px!important;min-width:42px!important;height:42px!important;min-height:42px!important;
      padding:0!important;border-radius:var(--r-md)!important;background:var(--surface)!important;
      border:1px solid var(--border)!important;color:var(--text-dim)!important;
      box-shadow:inset 0 1px 0 var(--inset-hi)!important;filter:none!important;}
    .st-key-coach_chat_header .stButton>button:hover{
      background:var(--surface-2)!important;border-color:var(--border-2)!important;color:var(--text)!important;}
    .st-key-coach_chat_header .stButton>button p{display:none!important;}
    .st-key-coach_chat_header .stButton>button [data-testid="stIconMaterial"]{
      margin:0!important;font-size:19px!important;}
    .st-key-coach_quick_prompts{padding:14px 20px 2px;}
    .st-key-coach_quick_prompts [data-testid="stHorizontalBlock"]{gap:8px!important;}
    .st-key-coach_quick_prompts .stButton>button{
      background:var(--surface)!important;border:1px solid var(--border)!important;
      color:var(--text-dim)!important;box-shadow:inset 0 1px 0 var(--inset-hi)!important;
      border-radius:999px!important;font-size:13px!important;padding:7px 12px!important;min-height:0!important;}
    .st-key-coach_quick_prompts .stButton>button:hover{
      background:var(--surface-2)!important;border-color:var(--border-2)!important;color:var(--text)!important;}
    .st-key-coach_messages{padding:12px 20px 18px;min-height:420px;}
    .st-key-coach_messages [data-testid="stChatMessage"]{
      border-radius:var(--r-md);background:rgba(255,255,255,.018);border:1px solid transparent;
      margin-bottom:10px;}
    .st-key-coach_messages [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
      background:color-mix(in srgb,var(--accent) 7%,transparent);
      border-color:color-mix(in srgb,var(--accent) 18%,transparent);}
    .st-key-coach_memory_suggestions_bar [data-testid="stHorizontalBlock"]{align-items:center!important;}
    .st-key-coach_memory_suggestions_bar [data-testid="column"]:nth-child(2){
      min-width:190px!important;max-width:230px!important;}
    .st-key-coach_memory_suggestions_bar .stButton>button{
      min-height:40px!important;border-radius:var(--r-md)!important;}
    .st-key-coach_memory_list [data-testid="stHorizontalBlock"],
    .st-key-coach_candidates_list [data-testid="stHorizontalBlock"]{align-items:start!important;}
    .st-key-coach_memory_list [data-testid="column"]:nth-child(2),
    .st-key-coach_memory_list [data-testid="column"]:nth-child(3),
    .st-key-coach_candidates_list [data-testid="column"]:nth-child(2),
    .st-key-coach_candidates_list [data-testid="column"]:nth-child(3){
      min-width:112px!important;max-width:128px!important;}
    @media (max-width:680px){
      .coach-page-title{font-size:30px;}
      .st-key-coach_chat_header [data-testid="stHorizontalBlock"]{
        grid-template-columns:minmax(0,1fr) 38px 38px!important;}
      .st-key-coach_chat_header [data-testid="column"]:nth-child(2),
      .st-key-coach_chat_header [data-testid="column"]:nth-child(3){
        width:38px!important;min-width:38px!important;max-width:38px!important;flex-basis:38px!important;}
      .st-key-coach_chat_header .stButton>button{width:38px!important;min-width:38px!important;height:38px!important;min-height:38px!important;}
      .st-key-coach_quick_prompts [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:1fr!important;}
      .st-key-coach_memory_suggestions_bar [data-testid="stHorizontalBlock"],
      .st-key-coach_memory_list [data-testid="stHorizontalBlock"],
      .st-key-coach_candidates_list [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:1fr!important;}
      .st-key-coach_memory_suggestions_bar [data-testid="column"],
      .st-key-coach_memory_list [data-testid="column"],
      .st-key-coach_candidates_list [data-testid="column"]{width:100%!important;max-width:none!important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, str(category or "").replace("_", " ").title())


def _format_date(value) -> str:
    value = _clean_text(value)
    if not value:
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.strftime("%b %d, %Y")


def _format_date_time(date_value, time_value=None) -> str:
    date_text = _format_date(date_value)
    time_text = _clean_text(time_value)
    if date_text and time_text:
        return f"{date_text} {time_text}"
    return date_text or time_text


def _optional_text(value) -> str | None:
    value = _clean_text(value)
    return value or None


def _memory_meta(r) -> list[str]:
    meta = []
    if _present(r.get("target_date")):
        meta.append(f"target {_format_date(r['target_date'])}")
    if _present(r.get("body_part")):
        meta.append(str(r["body_part"]))
    if r.get("category") in ("injury", "note"):
        when = _format_date_time(r.get("metadata_date"), r.get("metadata_time"))
        if when:
            meta.append(when)
        if _present(r.get("created_at")):
            meta.append(f"added {_timestamp_label(r.get('created_at'))}")
        if _present(r.get("updated_at")) and r.get("updated_at") != r.get("created_at"):
            meta.append(f"updated {_timestamp_label(r.get('updated_at'))}")
    if r.get("source") == "ai":
        meta.append("ai")
    return meta


def _memory_card_html(r) -> str:
    meta = " · ".join(html.escape(item) for item in _memory_meta(r))
    return (
        '<div class="coach-memory-card">'
        f'<div class="coach-memory-kicker">{html.escape(_category_label(r.get("category")))}</div>'
        f'<div class="coach-memory-text">{html.escape(_clean_text(r.get("text")))}</div>'
        f'<div class="coach-memory-meta">{meta}</div>'
        '</div>'
    )


def _candidate_card_html(candidate: dict) -> str:
    rationale = _clean_text(candidate.get("rationale"))
    rationale_html = (
        f'<div class="why">{html.escape(rationale)}</div>' if rationale else ""
    )
    return (
        '<div class="coach-candidate">'
        f'<div class="category">{html.escape(_category_label(candidate.get("category")))}</div>'
        f'<div class="text">{html.escape(_clean_text(candidate.get("text")))}</div>'
        f'{rationale_html}'
        '</div>'
    )


def _sort_memories(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    order = {cat: idx for idx, cat in enumerate(CATEGORIES)}
    out["_category_order"] = out["category"].map(order).fillna(len(CATEGORIES))
    out["_updated_sort"] = pd.to_datetime(
        out["updated_at"].fillna(out["created_at"]), errors="coerce"
    )
    return out.sort_values(
        ["_category_order", "_updated_sort", "created_at"],
        ascending=[True, False, False],
    )


def _latest_bodyweight_kg() -> float | None:
    body_metrics = db.load_body_metrics_df()
    if body_metrics.empty:
        return None
    bw = body_metrics.dropna(subset=["weight_kg"]).sort_values("date")
    if bw.empty:
        return None
    return float(bw.iloc[-1]["weight_kg"])


def _compact_early_waking(model: dict) -> dict:
    latest = (model or {}).get("latest") or {}
    keep_latest = {
        key: latest.get(key)
        for key in (
            "date",
            "early_waking_minutes",
            "severity",
            "confidence",
            "pattern",
            "evidence",
            "sleep_debt_h",
            "prior_sleep_debt_h_7d",
            "body_battery_at_sleep_start",
            "recovery_need_h",
        )
        if latest.get(key) is not None
    }
    out = {
        key: value
        for key, value in (model or {}).items()
        if key not in ("rows", "latest")
    }
    if keep_latest:
        out["latest"] = keep_latest
    return out


@st.cache_data(ttl=300)
def load_coach_context(local_timezone: str) -> dict:
    db.init_db()
    daily = analysis.enrich_daily(db.load_daily_df())
    acts = db.load_activities_df()
    checkins = db.load_checkins_df()
    sleep_timing = db.load_sleep_timing_df()
    body_battery = db.load_body_battery_df()
    stress_loader = getattr(db, "load_stress_df", None)
    stress = (
        stress_loader()
        if stress_loader is not None
        else pd.DataFrame(columns=["date", "timestamp", "value"])
    )
    daily = analysis.compute_acwr(acts, daily) if not daily.empty else daily
    capacity = analysis.compute_capacity_envelope(daily, acts, checkins)
    stress_leaks = analysis.compute_stress_leak_map(daily, stress)
    prebed_discovery = analysis.compute_prebed_discovery(
        daily, acts, sleep_timing, body_battery=body_battery
    )
    personal_sleep_need = analysis.compute_personal_sleep_need(daily, checkins)
    early_waking = analysis.compute_early_waking_model(
        daily,
        sleep_timing,
        body_battery,
        sleep_need_h=personal_sleep_need.get("sleep_need_h"),
    )
    health_research = analysis.compute_health_research_panels(daily, acts, sleep_timing)
    strength = analysis.summarize_strength(
        db.load_strength_sessions_df(),
        db.load_strength_sets_df(),
        db.load_exercises_df(),
        db.load_profile(),
        _latest_bodyweight_kg(),
        formula=config.ONE_RM_FORMULA,
    )
    active_experiments = analysis.summarize_active_experiments(
        db.load_experiments_df(status="active"), daily
    )
    summary = analysis.summarize(daily, acts, lookback=14) if not daily.empty else {"error": "no data"}
    latest_day = str(daily.iloc[-1]["date"])[:10] if not daily.empty else None
    return {
        "daily_empty": bool(daily.empty),
        "latest_day": latest_day,
        "summary": summary,
        "capacity": capacity,
        "stress_leaks": stress_leaks,
        "prebed_discovery": {
            "status": prebed_discovery.get("status"),
            "message": prebed_discovery.get("message"),
            "relationships": prebed_discovery.get("relationships", []),
        },
        "personal_sleep_need": {
            key: value for key, value in personal_sleep_need.items() if key != "rows"
        },
        "early_waking": _compact_early_waking(early_waking),
        "health_research": {key: value for key, value in health_research.items() if key != "rows"},
        "strength": strength,
        "active_experiments": active_experiments,
    }


def _coach_intro_message(context: dict, memory_count: int) -> str:
    if context.get("daily_empty"):
        return (
            "I do not have enough synced Garmin data yet. Once daily metrics are available, "
            "I will ground answers in your compact recovery, sleep, training, strength, and memory context."
        )
    day = context.get("latest_day") or "latest sync"
    memory_line = (
        f"I will also use {memory_count} stored memor{'y' if memory_count == 1 else 'ies'}."
        if memory_count else
        "No stored memories are active yet."
    )
    return f"I have your compact health context through {day}. {memory_line.strip()} What should we solve first?"


def _ensure_chat_seed(context: dict, memory_count: int):
    day_key = context.get("latest_day") or "no-data"
    if (
        st.session_state.get("coach_chat_day") != day_key
        or st.session_state.get("coach_chat_seed_version") != COACH_CHAT_SEED_VERSION
        or "coach_chat" not in st.session_state
    ):
        st.session_state["coach_chat_day"] = day_key
        st.session_state["coach_chat_seed_version"] = COACH_CHAT_SEED_VERSION
        st.session_state["coach_chat"] = [
            {"role": "assistant", "content": _coach_intro_message(context, memory_count)}
        ]


def _answer_coach_prompt(prompt: str, context: dict, memory_digest: dict) -> str:
    return ai.answer_question(
        prompt,
        context["summary"],
        context["capacity"],
        context["stress_leaks"],
        [],
        context["prebed_discovery"],
        st.session_state.coach_chat[-8:],
        strength=context["strength"],
        personal_sleep_need=context["personal_sleep_need"],
        early_waking=context["early_waking"],
        health_research=context["health_research"],
        coach_memory=memory_digest,
        active_experiments=context["active_experiments"],
    )


def _render_edit_memory(mid: int, r):
    current_category = _clean_text(r.get("category")) or "note"
    category_index = CATEGORIES.index(current_category) if current_category in CATEGORIES else 0
    confidence_options = ["", "low", "med", "high"]
    current_confidence = _clean_text(r.get("confidence"))
    confidence_index = (
        confidence_options.index(current_confidence)
        if current_confidence in confidence_options else 0
    )

    with st.form(f"edit_memory_{mid}"):
        category = st.selectbox(
            "Category",
            CATEGORIES,
            index=category_index,
            format_func=_category_label,
            key=f"memory_category_{mid}",
        )
        text = st.text_area(
            "Memory",
            value=_clean_text(r.get("text")),
            height=110,
            key=f"memory_text_{mid}",
        )
        details = st.columns(2)
        with details[0]:
            target_date = st.text_input(
                "Target date",
                value=_clean_text(r.get("target_date")),
                placeholder="YYYY-MM-DD",
                key=f"memory_target_date_{mid}",
            )
        with details[1]:
            body_part = st.text_input(
                "Body part",
                value=_clean_text(r.get("body_part")),
                key=f"memory_body_part_{mid}",
            )
        metadata = st.columns(3)
        with metadata[0]:
            metadata_date = st.text_input(
                "Metadata date",
                value=_clean_text(r.get("metadata_date")),
                placeholder="YYYY-MM-DD",
                key=f"memory_metadata_date_{mid}",
            )
        with metadata[1]:
            metadata_time = st.text_input(
                "Metadata time",
                value=_clean_text(r.get("metadata_time")),
                placeholder="HH:MM",
                key=f"memory_metadata_time_{mid}",
            )
        with metadata[2]:
            confidence = st.selectbox(
                "Confidence",
                confidence_options,
                index=confidence_index,
                format_func=lambda c: c or "none",
                key=f"memory_confidence_{mid}",
            )
        if st.form_submit_button("Save changes", width="stretch"):
            clean_text = text.strip()
            if not clean_text:
                st.warning("Memory text is required.")
                return
            candidates = {
                "category": category,
                "text": clean_text,
                "target_date": _optional_text(target_date),
                "body_part": _optional_text(body_part),
                "metadata_date": _optional_text(metadata_date),
                "metadata_time": _optional_text(metadata_time),
                "confidence": _optional_text(confidence),
            }
            updates = {}
            for key, value in candidates.items():
                if (value or "") != _clean_text(r.get(key)):
                    updates[key] = value
            if updates:
                db.update_memory(mid, updates)
                st.rerun()


def render_chat_tab(context: dict, memory_digest: dict, memory_count: int):
    have_key = bool(config.ANTHROPIC_API_KEY)
    _ensure_chat_seed(context, memory_count)

    pending_prompt = None
    with st.container(key="coach_chat_shell", border=True):
        with st.container(key="coach_chat_header"):
            header = st.columns([1, 0.07, 0.07], gap="small", vertical_alignment="center")
            with header[0]:
                day = html.escape(context.get("latest_day") or "no synced day")
                meta = f"{day} - {memory_count} active memor{'y' if memory_count == 1 else 'ies'}"
                _face = (
                    f'<span class="coach-chat-face"><img src="{cockpit._COACH_AVATAR_URI}" alt="coach"/></span>'
                    if cockpit._COACH_AVATAR_URI else ""
                )
                st.markdown(
                    '<div class="coach-chat-titlebar">'
                    f'{_face}'
                    '<div class="coach-chat-title">'
                    '<div class="kicker">Coach</div>'
                    '<div class="name">Chat with your health context</div>'
                    f'<div class="meta">{html.escape(meta)}</div>'
                    '</div></div>',
                    unsafe_allow_html=True,
                )
            with header[1]:
                if st.button(
                    "",
                    key="coach_analyze_now",
                    icon=":material/auto_awesome:",
                    help="Analyse current context",
                    disabled=not have_key,
                    width="stretch",
                ):
                    pending_prompt = "Analyse my current health, recovery, sleep, training load, and strength context."
            with header[2]:
                if st.button(
                    "",
                    key="coach_clear_chat",
                    icon=":material/delete_sweep:",
                    help="Clear chat",
                    disabled=not st.session_state.get("coach_chat"),
                    width="stretch",
                ):
                    st.session_state["coach_chat"] = [
                        {"role": "assistant", "content": _coach_intro_message(context, memory_count)}
                    ]
                    st.rerun()

        with st.container(key="coach_quick_prompts"):
            quick = st.columns(3)
            quick_prompts = [
                ("Today", "What should I do today based on recovery and training load?"),
                ("Sleep", "What is the most important sleep signal right now?"),
                ("Training", "How should I train around my current constraints and readiness?"),
            ]
            for col, (label, prompt) in zip(quick, quick_prompts):
                with col:
                    if st.button(label, disabled=not have_key, width="stretch"):
                        pending_prompt = prompt

        with st.container(key="coach_messages"):
            if not have_key:
                st.caption("Set `ANTHROPIC_API_KEY` in .env to enable coach chat.")
            _coach_av = cockpit._COACH_AVATAR_URI or None
            for msg in st.session_state.coach_chat:
                _av = _coach_av if msg["role"] == "assistant" else None
                with st.chat_message(msg["role"], avatar=_av):
                    st.markdown(msg["content"])

    typed_prompt = st.chat_input(
        "Message Coach...",
        key="coach_chat_input",
        disabled=not have_key,
    )
    if typed_prompt and typed_prompt.strip():
        pending_prompt = typed_prompt.strip()

    if pending_prompt:
        history = st.session_state.coach_chat[-8:]
        st.session_state.coach_chat.append({"role": "user", "content": pending_prompt})
        with st.spinner("Reading your metrics and memories..."):
            try:
                answer = ai.answer_question(
                    pending_prompt,
                    context["summary"],
                    context["capacity"],
                    context["stress_leaks"],
                    [],
                    context["prebed_discovery"],
                    history,
                    strength=context["strength"],
                    personal_sleep_need=context["personal_sleep_need"],
                    early_waking=context["early_waking"],
                    health_research=context["health_research"],
                    coach_memory=memory_digest,
                    active_experiments=context["active_experiments"],
                )
            except Exception as e:
                answer = f"## Answer\n\nQuestion failed: {e}"
        st.session_state.coach_chat.append({"role": "assistant", "content": answer})
        st.rerun()


def render_add_memory(memory: pd.DataFrame):
    with st.expander("Add memory", expanded=memory.empty):
        with st.form("add_memory", clear_on_submit=True):
            c = st.columns([1, 3])
            with c[0]:
                cat = st.selectbox("Category", CATEGORIES, format_func=_category_label)
            with c[1]:
                text = st.text_area("Memory", height=90)
            details = st.columns(3)
            with details[0]:
                target_date = st.text_input("Target date", "", placeholder="YYYY-MM-DD")
            with details[1]:
                body_part = st.text_input("Body part", "")
            with details[2]:
                confidence = st.selectbox(
                    "Confidence",
                    ["", "low", "med", "high"],
                    format_func=lambda c: c or "none",
                )
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
            save = st.form_submit_button("Save memory", width="stretch")
            if save:
                if not text.strip():
                    st.warning("Memory text is required.")
                    return
                rec = {"category": cat, "text": text.strip(), "source": "user"}
                if target_date.strip():
                    rec["target_date"] = target_date.strip()
                if body_part.strip():
                    rec["body_part"] = body_part.strip()
                if confidence.strip():
                    rec["confidence"] = confidence.strip()
                if cat in ("injury", "note"):
                    rec["metadata_date"] = metadata_date.isoformat()
                    rec["metadata_time"] = metadata_time.strftime("%H:%M")
                db.add_memory(rec)
                st.rerun()


def render_active_memories(memory: pd.DataFrame):
    st.markdown(cockpit.section_label("Active memories"), unsafe_allow_html=True)

    if memory.empty:
        st.caption("No active memories yet.")
        return

    filter_labels = ["All"] + [
        f"{_category_label(cat)} ({len(memory[memory['category'] == cat])})"
        for cat in CATEGORIES
    ]
    label_to_category = {"All": None}
    label_to_category.update({
        label: cat for label, cat in zip(filter_labels[1:], CATEGORIES)
    })
    selected_filter = (
        st.segmented_control(
            "Memory category",
            filter_labels,
            default="All",
            key="coach_memory_category_filter",
            label_visibility="collapsed",
        )
        or "All"
    )
    selected_category = label_to_category[selected_filter]
    rows = memory if selected_category is None else memory[memory["category"] == selected_category]

    with st.container(key="coach_memory_list"):
        for _, r in _sort_memories(rows).iterrows():
            mid = int(r["id"])
            with st.container(border=True):
                actions = st.columns([1, 0.14, 0.14], gap="small", vertical_alignment="top")
                with actions[0]:
                    st.markdown(_memory_card_html(r), unsafe_allow_html=True)
                with actions[1]:
                    with st.popover("Edit", icon=":material/edit:", use_container_width=True):
                        _render_edit_memory(mid, r)
                with actions[2]:
                    with st.popover("More", icon=":material/more_horiz:", use_container_width=True):
                        if st.button("Archive", key=f"arch-{mid}", width="stretch"):
                            db.archive_memory(mid)
                            st.rerun()
                        st.divider()
                        confirm_delete = st.checkbox("Confirm delete", key=f"confirm_del_{mid}")
                        if st.button(
                            "Delete",
                            key=f"del-{mid}",
                            width="stretch",
                            disabled=not confirm_delete,
                        ):
                            db.delete_memory(mid)
                            st.rerun()


def render_memory_suggestions(memory: pd.DataFrame, context: dict, memory_digest: dict):
    st.markdown(cockpit.section_label("Find things to remember"), unsafe_allow_html=True)

    if not config.ANTHROPIC_API_KEY:
        st.caption("Set `ANTHROPIC_API_KEY` in .env to enable AI suggestions.")
        return

    with st.container(key="coach_memory_suggestions_bar"):
        cols = st.columns([1, 0.28], gap="small", vertical_alignment="center")
        with cols[0]:
            st.markdown(
                '<p class="coach-memory-note">Generate durable facts from recent metrics and strength context.</p>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            find_clicked = st.button(
                "Find",
                key="coach_find_memories",
                icon=":material/search:",
                width="stretch",
            )

    if find_clicked:
        with st.spinner("Looking for durable patterns worth remembering..."):
            st.session_state["mem_candidates"] = ai.suggest_memories(
                context["summary"],
                context["strength"],
                memory_digest,
            )

    candidates = st.session_state.get("mem_candidates", [])
    if not candidates:
        st.caption("No pending suggestions.")
        return

    with st.container(key="coach_candidates_list"):
        for i, cand in enumerate(candidates):
            with st.container(border=True):
                b = st.columns([1, 0.16, 0.14], gap="small", vertical_alignment="top")
                with b[0]:
                    st.markdown(_candidate_card_html(cand), unsafe_allow_html=True)
                with b[1]:
                    with st.popover("Approve", icon=":material/check:", use_container_width=True):
                        cand_category = cand.get("category") if cand.get("category") in CATEGORIES else "note"
                        with st.form(f"approve_candidate_{i}"):
                            category = st.selectbox(
                                "Category",
                                CATEGORIES,
                                index=CATEGORIES.index(cand_category),
                                format_func=_category_label,
                                key=f"candidate_category_{i}",
                            )
                            text = st.text_area(
                                "Memory",
                                value=_clean_text(cand.get("text")),
                                height=100,
                                key=f"candidate_text_{i}",
                            )
                            details = st.columns(3)
                            with details[0]:
                                target_date = st.text_input(
                                    "Target date",
                                    value=_clean_text(cand.get("target_date")),
                                    placeholder="YYYY-MM-DD",
                                    key=f"candidate_target_date_{i}",
                                )
                            with details[1]:
                                body_part = st.text_input(
                                    "Body part",
                                    value=_clean_text(cand.get("body_part")),
                                    key=f"candidate_body_part_{i}",
                                )
                            with details[2]:
                                confidence_options = ["", "low", "med", "high"]
                                cand_confidence = _clean_text(cand.get("confidence"))
                                confidence = st.selectbox(
                                    "Confidence",
                                    confidence_options,
                                    index=(
                                        confidence_options.index(cand_confidence)
                                        if cand_confidence in confidence_options else 0
                                    ),
                                    format_func=lambda c: c or "none",
                                    key=f"candidate_confidence_{i}",
                                )
                            if st.form_submit_button("Save memory", width="stretch"):
                                clean_text = text.strip()
                                if not clean_text:
                                    st.warning("Memory text is required.")
                                else:
                                    rec = {
                                        "category": category,
                                        "text": clean_text,
                                        "source": "ai",
                                    }
                                    for key, value in (
                                        ("confidence", confidence),
                                        ("target_date", target_date),
                                        ("body_part", body_part),
                                    ):
                                        clean_value = _optional_text(value)
                                        if clean_value:
                                            rec[key] = clean_value
                                    db.add_memory(rec)
                                    st.session_state["mem_candidates"] = [
                                        c for j, c in enumerate(candidates) if j != i
                                    ]
                                    st.rerun()
                with b[2]:
                    if st.button(
                        "Reject",
                        key=f"rej-{i}",
                        icon=":material/close:",
                        width="stretch",
                    ):
                        st.session_state["mem_candidates"] = [
                            c for j, c in enumerate(candidates) if j != i
                        ]
                        st.rerun()


def render_memory_tab(memory: pd.DataFrame, context: dict, memory_digest: dict):
    render_add_memory(memory)
    render_active_memories(memory)
    render_memory_suggestions(memory, context, memory_digest)


def render_session_tab():
    st.markdown(cockpit.section_label("Session generator"), unsafe_allow_html=True)
    st.caption("Deterministic workout suggestions from readiness, capacity, recent strength work, injury memory, and lifestyle context.")

    options = ["best", "upper", "push", "pull", "lower", "rehab", "bjj", "conditioning"]
    goal = st.segmented_control(
        "Goal",
        options,
        default="best",
        key="coach_session_goal",
    ) or "best"
    if st.button("Generate session", key="coach_generate_session", width="stretch"):
        with st.spinner("Reading readiness and strength context..."):
            st.session_state["coach_generated_session"] = fitness_agent.format_session(
                fitness_agent.build_context(),
                goal,
            )
    generated = st.session_state.get("coach_generated_session")
    if generated:
        st.markdown(generated)
    else:
        st.caption("Equivalent Telegram command: `/fitness session upper` or `/fitness session bjj`.")

    st.divider()
    st.markdown(cockpit.section_label("Response and recovery learning"), unsafe_allow_html=True)
    cols = st.columns(2)
    with cols[0]:
        if st.button("Analyze last response", key="coach_session_response", width="stretch"):
            with st.spinner("Comparing next-morning metrics to baseline..."):
                st.session_state["coach_session_response_text"] = fitness_agent.handle_response("")
    with cols[1]:
        if st.button("Learn recovery speed", key="coach_recovery_speed", width="stretch"):
            with st.spinner("Estimating personal recovery speed..."):
                st.session_state["coach_recovery_speed_text"] = fitness_agent.handle_recovery("")
    if st.session_state.get("coach_session_response_text"):
        st.markdown(st.session_state["coach_session_response_text"])
    if st.session_state.get("coach_recovery_speed_text"):
        st.markdown(st.session_state["coach_recovery_speed_text"])



def render_context_tab():
    st.markdown(cockpit.section_label("Lifestyle context"), unsafe_allow_html=True)
    st.caption("Timestamped notes for things Garmin cannot know: late dinner, alcohol, travel, hotel sleep, illness, stress, caffeine, supplements, sauna, breathwork.")

    with st.form("add_lifestyle_event", clear_on_submit=True):
        cols = st.columns([0.28, 1])
        with cols[0]:
            event_date = st.date_input("Date", value=_local_now().date())
        with cols[1]:
            event_text = st.text_input(
                "Note",
                placeholder="late dinner 22:30, alcohol 2 beers, travel flight Oslo, caffeine 17:00",
            )
        if st.form_submit_button("Save context note", width="stretch"):
            clean = event_text.strip()
            if not clean:
                st.warning("Write a note first.")
            else:
                rec = fitness_agent.parse_lifestyle_event(clean)
                rec["date"] = event_date.isoformat()
                rec["source"] = "app"
                db.add_daily_event(rec)
                st.rerun()

    start = (_local_now().date() - pd.Timedelta(days=13)).isoformat()
    events = db.load_daily_events_df(start=start)
    if events.empty:
        st.caption("No lifestyle context notes yet.")
        return

    st.markdown(cockpit.section_label("Recent notes"), unsafe_allow_html=True)
    for _, r in events.sort_values(["date", "id"], ascending=[False, False]).head(30).iterrows():
        event_id = int(r["id"])
        with st.container(border=True):
            cols = st.columns([1, 0.16], vertical_alignment="center")
            with cols[0]:
                st.markdown(
                    f"**{html.escape(fitness_agent._fmt_event_type(r.get('event_type')))}** · "
                    f"{str(r.get('date'))[:10]}  \n"
                    f"{html.escape(_clean_text(r.get('text')))}",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if st.button("Delete", key=f"delete_event_{event_id}", width="stretch"):
                    db.delete_daily_event(event_id)
                    st.rerun()


context = load_coach_context(config.LOCAL_TIMEZONE)
memory = db.load_memory_df()
memory_digest = analysis.build_coach_memory_digest(memory)

st.markdown(
    """
    <div class="coach-page-head">
      <div class="coach-page-title">Coach</div>
      <div class="coach-page-sub">A metrics-grounded chat backed by your curated long-term context.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

chat_tab, session_tab, context_tab, memory_tab = st.tabs(["Chat", "Session", "Context", "Memories"])

with chat_tab:
    render_chat_tab(context, memory_digest, len(memory))

with session_tab:
    render_session_tab()

with context_tab:
    render_context_tab()

with memory_tab:
    render_memory_tab(memory, context, memory_digest)
