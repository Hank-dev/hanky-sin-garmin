"""Streamlit dashboard — Garmin Coach "Recovery Cockpit".

Single-page dark dashboard ported from the Claude Design handoff. Orchestration
only: it loads the enriched data, derives the display state (nominal / alert /
sparse), and assembles the page from `cockpit.py` helpers + a few Streamlit
widgets (window control, Recovery/Training toggle, the AI Analyse button).

Run with:  streamlit run app.py
"""
import pandas as pd
import streamlit as st
import importlib

import db
import analysis
import ai
import config
import cockpit
import ingest

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
ai = importlib.reload(ai)
cockpit = importlib.reload(cockpit)


@st.cache_data(ttl=300)
def load(local_timezone: str):
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
    predictive_readiness = analysis.compute_predictive_readiness(
        daily,
        acts,
        sleep_need_h=personal_sleep_need.get("sleep_need_h"),
    )
    strength_sessions = db.load_strength_sessions_df()
    strength_sets = db.load_strength_sets_df()
    exercises = db.load_exercises_df()
    profile = db.load_profile()
    body_metrics = db.load_body_metrics_df()
    bodyweight = None
    if not body_metrics.empty:
        bw = body_metrics.dropna(subset=["weight_kg"]).sort_values("date")
        if not bw.empty:
            bodyweight = float(bw.iloc[-1]["weight_kg"])
    strength_summary = analysis.summarize_strength(
        strength_sessions, strength_sets, exercises, profile, bodyweight,
        formula=config.ONE_RM_FORMULA)
    return (daily, acts, checkins, body_battery, stress,
            stress_leaks, prebed_discovery, personal_sleep_need, early_waking,
            health_research, predictive_readiness, strength_summary)


(daily, acts, checkins, body_battery, stress, stress_leaks,
 prebed_discovery, personal_sleep_need, early_waking, health_research,
 predictive_readiness, strength_summary) = load(config.LOCAL_TIMEZONE)

coach_memory_df = db.load_memory_df()                       # fresh: not cached
coach_memory_digest = analysis.build_coach_memory_digest(coach_memory_df)
active_experiments = analysis.summarize_active_experiments(
    db.load_experiments_df(status="active"), daily)


# ── helpers ──────────────────────────────────────────────────────────────────
def val(row, key):
    """Scalar from a Series cell, or None if missing/NaN."""
    if row is None or key not in row:
        return None
    v = row.get(key)
    return None if v is None or pd.isna(v) else v


def fmt_date(ts) -> str:
    d = pd.Timestamp(ts)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


def query_day(default_day: str | None, valid_days: set[str]) -> str | None:
    if default_day is None:
        return None
    try:
        raw = st.query_params.get("day")
    except Exception:
        raw = None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    day = str(raw)[:10] if raw else default_day
    return day if day in valid_days else default_day


def _week_label(start: str, end: str) -> str:
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    return f"Week of {s.strftime('%b %-d')} – {e.strftime('%b %-d')}"


def verdict_for(readiness, suppressed, rhr_elevated):
    """Rule-based hero call (the full prose comes from the AI card on demand)."""
    if suppressed and rhr_elevated:
        return "REST", "HRV is suppressed and resting HR is up — back off and let the system settle."
    if readiness is not None:
        if readiness >= 70 and not suppressed and not rhr_elevated:
            return "TRAIN HARD", "The body looks primed to absorb a quality session."
        if readiness >= 45:
            if suppressed or rhr_elevated:
                return "TRAIN EASY", "Readiness is okay but recovery markers are off — keep it controlled."
            return "TRAIN MODERATE", "Solid but not peak — a steady session fits; hold back from max efforts."
        return "REST", "Recovery is lagging — prioritise rest and sleep today."
    # no Garmin readiness score available
    if suppressed or rhr_elevated:
        return "TRAIN EASY", "Recovery markers are off and readiness isn't synced — train to feel, easy."
    return "STEADY", "Readiness isn't synced yet — train to feel and keep something in reserve."


# ── derive display state ─────────────────────────────────────────────────────
if daily.empty:
    sparse, latest = True, None
    n_days = 0
    date_str = fmt_date(pd.Timestamp.today())
else:
    n_days = len(daily)
    latest = daily.iloc[-1]
    date_str = fmt_date(latest["date"])
    core_present = any(val(latest, k) is not None for k in
                       ("hrv_overnight_avg", "resting_hr", "sleep_hours"))
    sparse = (n_days < 7) or (not core_present)

suppressed = (not sparse) and val(latest, "hrv_flag") == "suppressed"
rhr_elevated = (not sparse) and bool(val(latest, "rhr_elevated"))
state_alert = (not sparse) and (suppressed or rhr_elevated)

latest_sync_day = str(latest["date"])[:10] if latest is not None else None
planned_sync_days = ingest.smart_sync_days(latest_sync_day)
win = st.session_state.get("win", 30) or 30

with st.container(key="cockpit_header"):
    head_l, head_sync, head_win = st.columns([1, 0.001, 0.001], gap="small", vertical_alignment="center")
    with head_l:
        st.markdown(cockpit.topbar(date_str, sparse), unsafe_allow_html=True)
    with head_sync:
        sync_clicked = st.button(
            "",
            key="sync_btn",
            icon=":material/sync:",
            width="stretch",
            help=(
                "Smart sync: pulls a small overlap for late Garmin updates, "
                f"or catches up if the local DB is behind. Next pull: {planned_sync_days} day(s)."
            ),
        )
    with head_win:
        if not daily.empty:
            window_clicked = st.button(
                "",
                key="window_btn",
                icon=":material/calendar_month:",
                width="stretch",
                help=f"Trend window: {win}d. Click to cycle 7d / 30d / 60d.",
            )
            if window_clicked:
                options = [7, 30, 60]
                win = options[(options.index(win) + 1) % len(options)] if win in options else 30
                st.session_state["win"] = win
                st.rerun()

if sync_clicked:
    with st.spinner(f"Smart syncing {planned_sync_days} day(s) from Garmin..."):
        try:
            import garmin_client
            client = garmin_client.get_client(interactive=False)
            ingest.backfill(client, days=planned_sync_days)
            load.clear()
            st.session_state["sync_msg"] = (
                "ok",
                f"Synced - smart pull covered {planned_sync_days} day(s).",
            )
        except RuntimeError as e:
            st.session_state["sync_msg"] = ("err", str(e))
        except Exception as e:
            st.session_state["sync_msg"] = ("err", f"Sync failed: {e}")
    st.rerun()

_msg = st.session_state.pop("sync_msg", None)
if _msg:
    (st.success if _msg[0] == "ok" else st.error)(_msg[1])

view = daily.tail(win) if not daily.empty else daily
base28 = daily.tail(28) if not daily.empty else daily
capacity = analysis.compute_capacity_envelope(daily, acts, checkins)
weekly_stress = analysis.compute_weekly_stress_overview(daily)
valid_days = set(pd.to_datetime(daily["date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna()) if not daily.empty else set()
default_day = str(latest["date"])[:10] if latest is not None else None
selected_day = query_day(default_day, valid_days)


# ── hero ─────────────────────────────────────────────────────────────────────
if sparse:
    chips_html = cockpit.chips(None, None, None, None)
    st.markdown(
        cockpit.hero(None, "NO SCORE YET",
                     "Training readiness needs a few more days of overnight data to "
                     "establish your personal baseline.",
                     chips_html, sparse=True),
        unsafe_allow_html=True)
else:
    readiness = val(latest, "training_readiness_score")
    verdict, tagline = verdict_for(readiness, suppressed, rhr_elevated)
    chips_html = cockpit.chips(
        val(latest, "hrv_flag"), val(latest, "resting_hr"),
        val(latest, "rhr_28d"), val(latest, "sleep_hours"))
    ribbon_html = ""
    if state_alert:
        if suppressed and rhr_elevated:
            ribbon_html = cockpit.ribbon(
                "Overnight HRV is suppressed vs baseline and resting HR is elevated "
                ">5% above your 28-day average — bias toward easier training or rest.")
        elif suppressed:
            ribbon_html = cockpit.ribbon(
                "Overnight HRV is suppressed vs your baseline — a marker of under-recovery, "
                "stress, or illness onset.")
        else:
            ribbon_html = cockpit.ribbon(
                "Resting HR is elevated >5% above your 28-day baseline.", amber=True)
    st.markdown(
        cockpit.hero(readiness, verdict, tagline, chips_html, ribbon_html),
        unsafe_allow_html=True)


def render_weekly_summary():
    """Render cached weekly summary below the signal tiles, compact by default."""
    if daily.empty:
        return
    week = analysis.summarize_week(daily, acts, checkins)
    if week.get("status") != "ready":
        return
    ws = week["week_start"]
    st.markdown(cockpit.section_label("Weekly summary"), unsafe_allow_html=True)
    if not config.ANTHROPIC_API_KEY:
        st.caption("Set `ANTHROPIC_API_KEY` in .env to enable the weekly summary.")
        return

    full_key = f"weekly_summary_full_{ws}"
    show_full = bool(st.session_state.get(full_key, False))
    regen_key = f"weekly_summary_regen_{ws}"
    regenerate = bool(st.session_state.pop(regen_key, False))

    def toggle_weekly_summary():
        st.session_state[full_key] = not bool(st.session_state.get(full_key, False))

    def request_weekly_regenerate():
        st.session_state[regen_key] = True

    cached = None if regenerate else db.load_weekly_summary(ws)
    if cached is None:
        with st.spinner("Writing your weekly summary..."):
            md = ai.weekly_summary(
                week,
                coach_memory=coach_memory_digest,
                active_experiments=active_experiments,
            )
        db.save_weekly_summary(ws, config.ANTHROPIC_MODEL, md)
        cached = db.load_weekly_summary(ws)
    meta_label = _week_label(week["week_start"], week["week_end"])
    meta_label += f' - generated {cached["generated_at"][:10]}'
    summary_md = cached["summary_md"] if show_full else cockpit.weekly_summary_preview(cached["summary_md"])
    with st.container(key="weekly_summary_card", border=True):
        with st.container(key="weekly_summary_header"):
            header_cols = st.columns([1, 0.12, 0.12], gap="small", vertical_alignment="center")
            with header_cols[0]:
                st.markdown(cockpit.weekly_summary_meta(meta_label), unsafe_allow_html=True)
            with header_cols[1]:
                st.button(
                    "",
                    key=f"toggle_week_{ws}",
                    icon=":material/close_fullscreen:" if show_full else ":material/open_in_full:",
                    help="Hide full summary" if show_full else "Show full summary",
                    on_click=toggle_weekly_summary,
                )
            with header_cols[2]:
                st.button(
                    "",
                    key="regen_week",
                    icon=":material/refresh:",
                    help="Regenerate weekly summary",
                    on_click=request_weekly_regenerate,
                )
        st.markdown(cockpit.weekly_summary_content(summary_md), unsafe_allow_html=True)


# ── key-stat tiles ───────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Today's signals"), unsafe_allow_html=True)
if sparse:
    st.markdown(cockpit.tiles({}, {}, {}, sparse=True), unsafe_allow_html=True)
else:
    # Body Battery: prefer the *current* value (matches Garmin Connect's
    # headline); fall back to the day's peak for older rows synced before the
    # body_battery_current column existed.
    bb_col = ("body_battery_current"
              if "body_battery_current" in daily and daily["body_battery_current"].notna().any()
              else "body_battery_high")
    today = {
        "hrv": val(latest, "hrv_overnight_avg"), "rhr": val(latest, "resting_hr"),
        "sleep_h": val(latest, "sleep_hours"), "acwr": val(latest, "acwr"),
        "batt": val(latest, bb_col), "sleep_score": val(latest, "sleep_score"),
    }
    sparks = {
        "hrv": list(view.get("hrv_overnight_avg", [])),
        "rhr": list(view.get("resting_hr", [])),
        "sleep_h": list(view.get("sleep_hours", [])),
        "acwr": list(view.get("acwr", [])),
        "batt": list(view.get(bb_col, [])),
    }
    base = {
        "hrv": base28["hrv_overnight_avg"].mean() if "hrv_overnight_avg" in base28 else None,
        "rhr": base28["resting_hr"].mean() if "resting_hr" in base28 else None,
        "sleep_h": base28["sleep_hours"].mean() if "sleep_hours" in base28 else None,
        "batt": base28[bb_col].mean() if bb_col in base28 else None,
    }
    base = {k: (None if v is None or pd.isna(v) else float(v)) for k, v in base.items()}
    st.markdown(cockpit.tiles(today, sparks, base, sparse=False), unsafe_allow_html=True)

render_weekly_summary()

# ── capacity envelope + subjective check-in ──────────────────────────────────
checkin_date = str(latest["date"])[:10] if latest is not None else pd.Timestamp.today().strftime("%Y-%m-%d")
existing_checkin = None
if checkins is not None and not checkins.empty:
    rows = checkins[checkins["date"].dt.strftime("%Y-%m-%d") == checkin_date]
    if not rows.empty:
        existing_checkin = rows.iloc[-1]


def checkin_default(key, fallback):
    if existing_checkin is None or key not in existing_checkin or pd.isna(existing_checkin[key]):
        return fallback
    return int(existing_checkin[key])


def render_capacity_experimental():
    st.markdown(cockpit.capacity_card(capacity), unsafe_allow_html=True)
    with st.form("daily_capacity_checkin"):
        st.caption(f"Daily check-in for `{checkin_date}`")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            pain = st.slider("Pain", 1, 10, checkin_default("pain", 1))
        with c2:
            fatigue = st.slider("Fatigue", 1, 10, checkin_default("fatigue", 4))
        with c3:
            energy = st.slider("Energy", 1, 10, checkin_default("energy", 6))
        with c4:
            note_default = "" if existing_checkin is None or pd.isna(existing_checkin.get("note")) else str(existing_checkin.get("note"))
            note = st.text_input("Note", value=note_default, placeholder="optional")
        saved_checkin = st.form_submit_button("Save check-in", width="stretch")

    if saved_checkin:
        db.upsert_checkin({
            "date": checkin_date,
            "pain": int(pain),
            "fatigue": int(fatigue),
            "energy": int(energy),
            "note": note.strip(),
        })
        load.clear()
        st.session_state["checkin_msg"] = f"Saved check-in for {checkin_date}."
        st.rerun()

    _checkin_msg = st.session_state.pop("checkin_msg", None)
    if _checkin_msg:
        st.success(_checkin_msg)


# ── AI coach readout ─────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Coach"), unsafe_allow_html=True)
if "health_chat" not in st.session_state:
    st.session_state.health_chat = []

question_summary = analysis.summarize(daily, acts, lookback=14) if not daily.empty else {"error": "no data"}


def compact_early_waking(model: dict) -> dict:
    latest = (model or {}).get("latest") or {}
    keep_latest = {
        key: latest.get(key)
        for key in (
            "date", "early_waking_minutes", "severity", "confidence",
            "pattern", "evidence",
            "sleep_debt_h", "prior_sleep_debt_h_7d",
            "body_battery_at_sleep_start", "recovery_need_h",
        )
        if latest.get(key) is not None
    }
    return {
        key: (keep_latest if key == "latest" else value)
        for key, value in (model or {}).items()
        if key not in ("rows", "latest")
    } | ({"latest": keep_latest} if keep_latest else {})


question_payload = {
    "metrics_summary": question_summary,
    "capacity_envelope": capacity,
    "stress_leak_map": stress_leaks,
    "grappling_sessions": [],
    "prebed_discovery": {
        "status": prebed_discovery.get("status"),
        "message": prebed_discovery.get("message"),
        "relationships": prebed_discovery.get("relationships", []),
    },
    "personal_sleep_need": {k: v for k, v in personal_sleep_need.items() if k != "rows"},
    "early_waking": compact_early_waking(early_waking),
    "health_research": {k: v for k, v in health_research.items() if k != "rows"},
    "predictive_readiness": predictive_readiness,
    "strength_profile": strength_summary,
    "selected_day": selected_day,
}
have_key = bool(config.ANTHROPIC_API_KEY)

for msg in st.session_state.health_chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

def submit_health_chat():
    raw = str(st.session_state.get("health_chat_entry", "")).strip()
    if raw:
        st.session_state["health_chat_pending"] = raw
        st.session_state["health_chat_entry"] = ""


st.text_input(
    "Coach chat",
    placeholder=(
        "Ask about sleep, stress, recovery, training load, or correlations..."
        if have_key else
        "Set ANTHROPIC_API_KEY in .env to enable coach chat"
    ),
    label_visibility="collapsed",
    disabled=not have_key,
    key="health_chat_entry",
    on_change=submit_health_chat,
)
pending_prompt = st.session_state.pop("health_chat_pending", None)

if pending_prompt:
    history = st.session_state.health_chat[-8:]
    st.session_state.health_chat.append({"role": "user", "content": pending_prompt})
    with st.spinner("Reading your health context…"):
        try:
            answer = ai.answer_question(
                pending_prompt,
                question_summary,
                capacity,
                stress_leaks,
                [],
                question_payload["prebed_discovery"],
                history,
                strength=strength_summary,
                personal_sleep_need=question_payload["personal_sleep_need"],
                early_waking=question_payload["early_waking"],
                health_research=question_payload["health_research"],
                predictive_readiness=predictive_readiness,
                coach_memory=coach_memory_digest,
                active_experiments=active_experiments,
            )
        except Exception as e:
            answer = f"## Answer\n\nQuestion failed: {e}"
    st.session_state.health_chat.append({"role": "assistant", "content": answer})
    st.rerun()


# ── trends ───────────────────────────────────────────────────────────────────
def chart_card(title, unit, fig):
    with st.container(border=True):
        st.markdown(
            f'<div class="chart-title" style="font-family:\'Spectral\',Georgia,serif;'
            f'font-weight:400;font-size:21px;margin:2px 0 -4px">'
            f'{title} <em style="font-style:normal;font-family:\'JetBrains Mono\',monospace;'
            f'color:{cockpit.TEXT_FAINT};font-size:10px;letter-spacing:.04em">{unit}</em></div>',
            unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


st.markdown('<div class="section-label">Trends</div>', unsafe_allow_html=True)
if not daily.empty:
    st.markdown(cockpit.day_rail(view, acts, selected_day), unsafe_allow_html=True)
    if selected_day and selected_day != default_day:
        st.caption(f"Daily graphs are focused on `{selected_day}`. Click the latest day card to return to today.")

recovery_tab, health_tab, training_tab, experimental_tab = st.tabs(
    ["Recovery", "Health Lab", "Training", "Experimental"]
)

with recovery_tab:
    if weekly_stress.get("status") == "ready":
        stress_meta = _week_label(weekly_stress["week_start"], weekly_stress["week_end"])
        if weekly_stress.get("mean") is not None:
            stress_meta += f" · avg {weekly_stress['mean']:.0f}"
        if weekly_stress.get("std") is not None:
            stress_meta += f" · SD {weekly_stress['std']:.1f}"
        chart_card("Weekly stress overview", stress_meta, cockpit.chart_weekly_stress_overview(weekly_stress))
        if weekly_stress.get("days_with_data", 0) < 2:
            st.caption("Standard deviation bands need at least two synced daily stress averages.")
    elif not daily.empty:
        st.caption("No daily stress averages are synced for the latest week yet.")

    if sparse:
        st.info("Sync more history (`python sync.py --days 90`) to plot your trends.")
    else:
        band = (val(latest, "hrv_baseline_low"), val(latest, "hrv_baseline_high"))
        if band[0] is None or band[1] is None:  # fall back to most recent non-null band in view
            bl = view["hrv_baseline_low"].dropna() if "hrv_baseline_low" in view else pd.Series(dtype=float)
            bh = view["hrv_baseline_high"].dropna() if "hrv_baseline_high" in view else pd.Series(dtype=float)
            band = (bl.iloc[-1] if not bl.empty else None, bh.iloc[-1] if not bh.empty else None)
        chart_card("Overnight HRV", "ms", cockpit.chart_hrv(view, band))
        hrv_points = int(view["hrv_overnight_avg"].notna().sum()) if "hrv_overnight_avg" in view else 0
        if hrv_points < 2:
            st.caption("Only one overnight HRV value is synced in this window, so the chart shows it as a single point until more nights are available.")
        chart_card("Resting heart rate", "bpm", cockpit.chart_rhr(view))
        intraday_days = set()
        if body_battery is not None and not body_battery.empty and "date" in body_battery:
            intraday_days.update(body_battery["date"].astype(str).unique())
        if stress is not None and not stress.empty and "date" in stress:
            intraday_days.update(stress["date"].astype(str).unique())
        graph_options = sorted(intraday_days, reverse=True) or sorted(valid_days, reverse=True)
        query_graph_day = selected_day or str(latest["date"])[:10]
        graph_index = graph_options.index(query_graph_day) if query_graph_day in graph_options else 0
        graph_day = st.selectbox(
            "Daily graph day",
            graph_options,
            index=graph_index,
            key=f"daily_graph_day_{query_graph_day}_{len(graph_options)}",
            help="Only days with synced intraday Body Battery or stress samples are listed.",
        ) if graph_options else query_graph_day
        bb_chart_col, stress_chart_col = st.columns(2)
        with bb_chart_col:
            if body_battery is not None and not body_battery.empty:
                bb_day = body_battery[body_battery["date"] == graph_day]
                if not bb_day.empty:
                    chart_card("Body Battery", f"{graph_day} daily graph", cockpit.chart_body_battery_daily(bb_day))
                else:
                    st.caption(f"No Body Battery graph stored for `{graph_day}`.")
            else:
                st.caption("No Body Battery daily graph stored yet. Click Sync once to pull Garmin's body-battery curve.")
        with stress_chart_col:
            if stress is not None and not stress.empty:
                stress_day = stress[stress["date"] == graph_day]
                if not stress_day.empty:
                    chart_card("Stress level", f"{graph_day} daily graph", cockpit.chart_stress_daily(stress_day))
                else:
                    st.caption(f"No stress-level graph stored for `{graph_day}`.")
            else:
                st.caption("No stress-level graph stored yet. Click Sync once to pull Garmin's all-day stress curve.")
with health_tab:
    if daily.empty:
        st.info("Sync Garmin history to build the Health Lab panels.")
    else:
        st.markdown(cockpit.health_research_card(health_research), unsafe_allow_html=True)
        health_rows = pd.DataFrame(health_research.get("rows") or [])
        if not health_rows.empty and "date" in health_rows:
            health_rows["date"] = pd.to_datetime(health_rows["date"], errors="coerce")
            health_view = health_rows.dropna(subset=["date"]).tail(win)
        else:
            health_view = pd.DataFrame()

        chart_card("Primitive baseline deviations", "z-score", cockpit.chart_recovery_deviation(health_view))
        if not health_view.empty and any(
            col in health_view and health_view[col].notna().any()
            for col in ("spo2_avg", "respiration_avg")
        ):
            chart_card("Respiratory watchlist", "SpO₂ / respiration", cockpit.chart_respiratory_watchlist(health_view))
        else:
            st.caption("Respiratory watchlist needs SpO₂ or respiration summaries.")

        if ((health_research.get("fitness") or {}).get("activity") or {}).get("rows"):
            chart_card("Run/walk adaptation", "pace + HR", cockpit.chart_foot_pace(health_research))
        else:
            st.caption("Run/walk adaptation unlocks after Garmin activities include distance and duration.")

with training_tab:
    if sparse:
        st.info("Sync more history (`python sync.py --days 90`) to plot your training trends.")
    else:
        if "acwr" in view and view["acwr"].notna().any():
            chart_card("Acute : Chronic workload", "ratio", cockpit.chart_acwr(view))
        if "vo2max" in view and view["vo2max"].notna().any():
            chart_card("VO₂max estimate", "ml/kg/min", cockpit.chart_vo2(view))
        else:
            st.caption("No VO₂max estimates stored for this window.")

with experimental_tab:
    st.markdown(cockpit.predictive_readiness_card(predictive_readiness), unsafe_allow_html=True)
    render_capacity_experimental()


# ── stress leak map ──────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Stress leak map"), unsafe_allow_html=True)
st.markdown(cockpit.stress_leak_card(stress_leaks), unsafe_allow_html=True)
