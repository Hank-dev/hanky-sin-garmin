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

st.set_page_config(page_title="Hankø Fitness Hub", page_icon="🏃", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)


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
    activity_details = db.load_activity_raw_payloads("activity_details")
    activity_zones = db.load_activity_raw_payloads("activity_hr_zones")
    grappling = analysis.compute_grappling_sessions(
        daily, acts, activity_details, activity_zones
    )
    stress_leaks = analysis.compute_stress_leak_map(daily, stress)
    prebed_discovery = analysis.compute_prebed_discovery(daily, acts, sleep_timing)
    health_research = analysis.compute_health_research_panels(daily, acts, sleep_timing)
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
    return (daily, acts, checkins, body_battery, stress, grappling,
            stress_leaks, prebed_discovery, health_research, strength_summary)


(daily, acts, checkins, body_battery, stress, grappling, stress_leaks,
 prebed_discovery, health_research, strength_summary) = load(config.LOCAL_TIMEZONE)

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

# ── top bar + sync + window control ──────────────────────────────────────────
st.markdown(cockpit.topbar(date_str, sparse), unsafe_allow_html=True)

latest_sync_day = str(latest["date"])[:10] if latest is not None else None
planned_sync_days = ingest.smart_sync_days(latest_sync_day)

spacer, sync_col, win_col = st.columns([5, 1.5, 2])
with sync_col:
    sync_clicked = st.button("⟳ Sync", width="stretch",
                             help=(
                                 "Smart sync: pulls a small overlap for late Garmin updates, "
                                 f"or catches up if the local DB is behind. Next pull: {planned_sync_days} day(s)."
                             ))
win = 30
with win_col:
    if not daily.empty:
        win = st.segmented_control(
            "Window", [7, 30, 60], default=30, key="win",
            format_func=lambda d: f"{d}d", label_visibility="collapsed") or 30

# A sync is the ONLY path that writes / touches the network. garminconnect is
# imported lazily here so normal (read-only) dashboard loads stay light.
if sync_clicked:
    with st.spinner(f"Smart syncing {planned_sync_days} day(s) from Garmin…"):
        try:
            import garmin_client
            client = garmin_client.get_client(interactive=False)
            ingest.backfill(client, days=planned_sync_days)
            load.clear()  # drop the 5-min cache so fresh data shows immediately
            st.session_state["sync_msg"] = (
                "ok",
                f"Synced ✓ — smart pull covered {planned_sync_days} day(s).",
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


# ── weekly summary (auto, cached once per completed ISO week) ─────────────────
if not daily.empty:
    week = analysis.summarize_week(daily, acts, checkins)
    if week.get("status") == "ready":
        ws = week["week_start"]
        st.markdown(cockpit.section_label("Weekly summary"), unsafe_allow_html=True)
        if not config.ANTHROPIC_API_KEY:
            st.caption("Set `ANTHROPIC_API_KEY` in .env to enable the weekly summary.")
        else:
            regenerate = st.button("↻ Regenerate weekly summary", key="regen_week")
            cached = None if regenerate else db.load_weekly_summary(ws)
            if cached is None:
                with st.spinner("Writing your weekly summary…"):
                    md = ai.weekly_summary(week, coach_memory=coach_memory_digest,
                                           active_experiments=active_experiments)
                db.save_weekly_summary(ws, config.ANTHROPIC_MODEL, md)
                cached = db.load_weekly_summary(ws)
            meta_label = _week_label(week["week_start"], week["week_end"])
            meta_label += f' · generated {cached["generated_at"][:10]}'
            st.markdown(cockpit.weekly_summary_card(cached["summary_md"], meta_label),
                        unsafe_allow_html=True)


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
        "batt": val(latest, bb_col), "stress": val(latest, "stress_avg"),
    }
    sparks = {
        "hrv": list(view.get("hrv_overnight_avg", [])),
        "rhr": list(view.get("resting_hr", [])),
        "sleep_h": list(view.get("sleep_hours", [])),
        "acwr": list(view.get("acwr", [])),
        "batt": list(view.get(bb_col, [])),
        "stress": list(view.get("stress_avg", [])),
    }
    base = {
        "hrv": base28["hrv_overnight_avg"].mean() if "hrv_overnight_avg" in base28 else None,
        "rhr": base28["resting_hr"].mean() if "resting_hr" in base28 else None,
        "sleep_h": base28["sleep_hours"].mean() if "sleep_hours" in base28 else None,
        "batt": base28[bb_col].mean() if bb_col in base28 else None,
        "stress": base28["stress_avg"].mean() if "stress_avg" in base28 else None,
    }
    base = {k: (None if v is None or pd.isna(v) else float(v)) for k, v in base.items()}
    st.markdown(cockpit.tiles(today, sparks, base, sparse=False), unsafe_allow_html=True)

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


# ── grappling recovery mode ──────────────────────────────────────────────────
st.markdown(cockpit.section_label("Grappling"), unsafe_allow_html=True)
st.markdown(cockpit.grappling_card(grappling), unsafe_allow_html=True)


# ── AI coach readout ─────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Coach"), unsafe_allow_html=True)
st.markdown(cockpit.coach_memory_peek(coach_memory_digest), unsafe_allow_html=True)
with st.form("coach_quickadd", clear_on_submit=True):
    qa_cols = st.columns([1, 3, 1])
    with qa_cols[0]:
        qcat = st.selectbox("Remember a",
                            ["note", "goal", "injury", "pattern", "coaching"],
                            key="qa_cat")
    with qa_cols[1]:
        qtext = st.text_input("Tell the coach something",
                              placeholder="e.g. tweaked left knee in BJJ", key="qa_text")
    with qa_cols[2]:
        qa_submit = st.form_submit_button("Remember", width="stretch")
    if qa_submit and qtext.strip():
        db.add_memory({"category": qcat, "text": qtext.strip(), "source": "user"})
        st.rerun()
st.page_link("pages/02_Coach.py", label="Manage everything the coach knows →")
if "health_chat" not in st.session_state:
    st.session_state.health_chat = []

question_summary = analysis.summarize(daily, acts, lookback=14) if not daily.empty else {"error": "no data"}
question_payload = {
    "metrics_summary": question_summary,
    "capacity_envelope": capacity,
    "stress_leak_map": stress_leaks,
    "grappling_sessions": grappling[:3],
    "prebed_discovery": {
        "status": prebed_discovery.get("status"),
        "message": prebed_discovery.get("message"),
        "relationships": prebed_discovery.get("relationships", []),
    },
    "health_research": {k: v for k, v in health_research.items() if k != "rows"},
    "strength_profile": strength_summary,
    "selected_day": selected_day,
}
have_key = bool(config.ANTHROPIC_API_KEY)

if not have_key:
    st.caption("Set `ANTHROPIC_API_KEY` in .env to enable the health chat.")

pending_prompt = None
coach_actions = st.columns([1.4, 1, 4])
with coach_actions[0]:
    if st.button("Analyse my health", disabled=not have_key or daily.empty, width="stretch"):
        pending_prompt = "Analyse my health"
with coach_actions[1]:
    if st.button("Clear chat", disabled=not st.session_state.health_chat, width="stretch"):
        st.session_state.health_chat = []
        st.rerun()

with st.container(border=True):
    if not st.session_state.health_chat:
        st.caption("Press `Analyse my health` or ask a specific question about sleep, stress, recovery, training load, or correlations.")
    for msg in st.session_state.health_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

with st.form("health_chat_form", clear_on_submit=True):
    chat_question = st.text_input(
        "Message",
        placeholder="Ask about sleep, stress, recovery, training load, or correlations…",
        label_visibility="collapsed",
        disabled=not have_key,
    )
    send_clicked = st.form_submit_button("Send", disabled=not have_key, width="stretch")

if send_clicked and chat_question.strip():
    pending_prompt = chat_question.strip()

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
                grappling[:3],
                question_payload["prebed_discovery"],
                history,
                strength=strength_summary,
                health_research=question_payload["health_research"],
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
            f'<div class="chart-title" style="font-family:\'Instrument Serif\',Georgia,serif;'
            f'font-weight:400;font-size:21px;margin:2px 0 -4px">'
            f'{title} <em style="font-style:normal;font-family:\'IBM Plex Mono\',monospace;'
            f'color:{cockpit.TEXT_FAINT};font-size:10px;letter-spacing:.04em">{unit}</em></div>',
            unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_prebed_discovery():
    st.markdown(cockpit.discovery_card(prebed_discovery), unsafe_allow_html=True)
    rels = prebed_discovery.get("relationships", [])

    def rel_for(x_col, y_col):
        return next((r for r in rels if r.get("x_col") == x_col and r.get("y_col") == y_col), None)

    sleep_rel = next(
        (r for r in rels if r.get("x_col") == "hr_bedtime" and r.get("y_col") in ("sleep_score", "sleep_hours")),
        None,
    )
    chart_specs = [
        ("Bedtime HR deviation vs sleep quality", "sleep score", "bedtime_hr_delta", "sleep_score"),
        ("Bedtime HR deviation vs overnight HRV", "ms", "bedtime_hr_delta", "hrv_overnight_avg"),
        ("Bedtime HR deviation vs resting HR", "bpm", "bedtime_hr_delta", "resting_hr"),
        ("Pre-sleep HR vs sleep quality", sleep_rel.get("y_label", "") if sleep_rel else "", "hr_bedtime", sleep_rel.get("y_col") if sleep_rel else "sleep_score"),
        ("Pre-sleep HR vs next-day stress", "avg stress", "hr_bedtime", "next_day_stress"),
        ("Overnight HRV vs next-day stress", "avg stress", "hrv_overnight_avg", "next_day_stress"),
        ("Sleep midpoint variability vs next-day stress", "avg stress", "sleep_midpoint_variability_7d", "next_day_stress"),
        ("Sleep midpoint variability vs overnight HRV", "ms", "sleep_midpoint_variability_7d", "hrv_overnight_avg"),
        ("Cardiovascular load vs next-day stress", "avg stress", "cardio_load", "next_day_stress"),
        ("Activity sweet spot vs next-day stress", "avg stress", "activity_bucket_code", "next_day_stress"),
        ("Activity sweet spot vs next-day HRV", "ms", "activity_bucket_code", "next_day_hrv"),
        ("Activity sweet spot vs Body Battery recharge", "score", "activity_bucket_code", "next_day_body_battery_recharge"),
    ]

    for i in range(0, len(chart_specs), 2):
        cols = st.columns(2)
        for col, (title, unit, x_col, y_col) in zip(cols, chart_specs[i:i + 2]):
            with col:
                rel = rel_for(x_col, y_col)
                if rel:
                    chart_card(
                        title,
                        unit,
                        cockpit.chart_prebed_relationship(prebed_discovery, y_col, x_col),
                    )
                else:
                    st.caption(f"No paired data yet for {title.lower()}.")


st.markdown('<div class="section-label">Trends</div>', unsafe_allow_html=True)
if not daily.empty:
    st.markdown(cockpit.day_rail(view, acts, selected_day), unsafe_allow_html=True)
    if selected_day and selected_day != default_day:
        st.caption(f"Daily graphs are focused on `{selected_day}`. Click the latest day card to return to today.")

recovery_tab, health_tab, training_tab, discovery_tab, experimental_tab = st.tabs(
    ["Recovery", "Health Lab", "Training", "Correlations", "Experimental"]
)

with recovery_tab:
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
        c1, c2 = st.columns(2)
        with c1:
            chart_card("Resting heart rate", "bpm", cockpit.chart_rhr(view))
        with c2:
            chart_card("Sleep duration", "h", cockpit.chart_sleep(view, config.SLEEP_NEED_HOURS))
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
        if "deep_seconds" in view and view["deep_seconds"].notna().any():
            chart_card("Sleep composition", "", cockpit.chart_sleep_comp(view))
        sleep_hr_col, bedtime_hr_col = st.columns(2)
        with sleep_hr_col:
            if "hr_overnight_low" in view and view["hr_overnight_low"].notna().any():
                chart_card("Lowest overnight heart rate", "bpm", cockpit.chart_sleeping_hr(view))
            else:
                st.caption("No lowest-overnight heart-rate trend stored yet.")
        with bedtime_hr_col:
            if "hr_bedtime" in view and view["hr_bedtime"].notna().any():
                chart_card("Pre-sleep heart rate", "bpm", cockpit.chart_bedtime_hr(view))
                bedtime_points = int(view["hr_bedtime"].notna().sum())
                if bedtime_points < 2:
                    st.caption("Only one pre-sleep HR value is synced in this window, so the chart shows it as a single point for now.")
            else:
                st.caption("No pre-sleep heart-rate values stored yet. Sync days that include sleep start plus all-day HR samples.")

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
        c1, c2 = st.columns(2)
        with c1:
            if not health_view.empty and any(
                col in health_view and health_view[col].notna().any()
                for col in ("sleep_midpoint_variability_7d", "bedtime_variability_7d", "wake_time_variability_7d")
            ):
                chart_card("Sleep timing regularity", "rolling SD", cockpit.chart_sleep_regularity(health_view))
            else:
                st.caption("Sleep timing regularity needs raw sleep start/end data from synced sleep payloads.")
        with c2:
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

with discovery_tab:
    render_prebed_discovery()


with experimental_tab:
    render_capacity_experimental()


# ── recent activities ────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Recent activities"), unsafe_allow_html=True)
st.markdown(cockpit.activities_table(acts, sparse=acts is None or acts.empty),
            unsafe_allow_html=True)


# ── stress leak map ──────────────────────────────────────────────────────────
st.markdown(cockpit.section_label("Stress leak map"), unsafe_allow_html=True)
st.markdown(cockpit.stress_leak_card(stress_leaks), unsafe_allow_html=True)
