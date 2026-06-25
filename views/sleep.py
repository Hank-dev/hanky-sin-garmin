"""Sleep dashboard page.

Detailed sleep timing, quality, and physiology panels live here so the Cockpit
can stay focused on top-level recovery and training decisions.
"""
import importlib

import pandas as pd
import streamlit as st

import ai
import analysis
import config
import cockpit
import db

config = importlib.reload(config)
db = importlib.reload(db)
ai = importlib.reload(ai)
analysis = importlib.reload(analysis)
cockpit = importlib.reload(cockpit)

st.markdown(
    """
    <style>
    .sleep-metric{
      border:1px solid var(--border);border-radius:var(--r-lg);
      padding:26px 28px 28px;background:rgba(255,255,255,.015);
      min-height:180px;display:flex;flex-direction:column;justify-content:flex-start;
    }
    .sleep-metric .lab{
      font-family:var(--font-mono);font-size:10px;letter-spacing:.16em;
      text-transform:uppercase;color:var(--text-faint);font-weight:500;
    }
    .sleep-metric .val{
      font-family:var(--font-serif);font-size:40px;font-weight:400;
      font-variant-numeric:tabular-nums;margin-top:24px;line-height:1;
    }
    .sleep-metric .sub{
      font-size:13px;color:var(--text-dim);margin-top:24px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    }
    .sleep-overview-spacer{height:22px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def load(local_timezone: str):
    db.init_db()
    daily = analysis.enrich_daily(db.load_daily_df())
    checkins = db.load_checkins_df()
    sleep_timing = db.load_sleep_timing_df()
    body_battery = db.load_body_battery_df()
    acts = db.load_activities_df()

    personal_sleep_need = analysis.compute_personal_sleep_need(daily, checkins)
    sleep_need_h = personal_sleep_need.get("sleep_need_h")
    early_waking = analysis.compute_early_waking_model(
        daily,
        sleep_timing,
        body_battery,
        sleep_need_h=sleep_need_h,
    )
    recommended_bedtime = analysis.compute_recommended_bedtime(
        daily,
        sleep_timing,
        sleep_need_h=sleep_need_h,
    )
    weekly_sleep = analysis.compute_weekly_sleep_overview(daily)
    health_research = analysis.compute_health_research_panels(daily, acts, sleep_timing)
    return (
        daily,
        sleep_timing,
        acts,
        personal_sleep_need,
        early_waking,
        recommended_bedtime,
        weekly_sleep,
        health_research,
    )


def fmt_date(ts) -> str:
    d = pd.Timestamp(ts)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


def _week_label(start: str, end: str) -> str:
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    return f"Week of {s.strftime('%b %-d')} - {e.strftime('%b %-d')}"


def chart_card(title, unit, fig):
    with st.container(border=True):
        st.markdown(
            f'<div class="chart-title" style="font-family:\'Geist\',Georgia,serif;'
            f'font-weight:400;font-size:21px;margin:2px 0 -4px">'
            f'{title} <em style="font-style:normal;font-family:\'Geist Mono\',monospace;'
            f'color:{cockpit.TEXT_FAINT};font-size:10px;letter-spacing:.04em">{unit}</em></div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def metric_panel(label: str, value: str, sub: str = ""):
    st.markdown(
        f'<div class="sleep-metric"><div class="lab">{label}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def sleep_prediction_panel(model: dict):
    model = model or {}
    pred = model.get("prediction")
    status = model.get("status") or "no_data"
    confidence = model.get("confidence") or "low"
    target = model.get("target_date") or "tonight"
    with st.container(border=True):
        st.markdown(
            f'<div class="chart-title" style="font-family:\'Geist\',Georgia,serif;'
            f'font-weight:400;font-size:21px;margin:2px 0 6px">Tonight sleep score '
            f'<em style="font-style:normal;font-family:\'Geist Mono\',monospace;'
            f'color:{cockpit.TEXT_FAINT};font-size:10px;letter-spacing:.04em">'
            f'{status} / {confidence}</em></div>',
            unsafe_allow_html=True,
        )
        if pred is None:
            st.caption(model.get("message") or "More scored sleep history is needed.")
            missing = model.get("missing") or []
            if missing:
                st.caption("Missing: " + ", ".join(str(m) for m in missing[:3]))
            return

        rng = ""
        if model.get("range_low") is not None and model.get("range_high") is not None:
            rng = f"{model['range_low']}-{model['range_high']}"
        c1, c2, c3 = st.columns([1.15, 1.15, 2.7], vertical_alignment="top")
        with c1:
            metric_panel("Predicted", f"{pred:.0f}", f"sleep date {target}")
        with c2:
            metric_panel("Likely range", rng or "-", f"{model.get('training_days', 0)} nights")
        with c3:
            reasons = model.get("reasons") or [model.get("message") or ""]
            for reason in reasons[:3]:
                st.caption(reason)

        features = model.get("features_used") or []
        if features:
            rows = []
            for feature in features[:5]:
                unit = feature.get("unit") or ""
                unit_txt = f" {unit}" if unit else ""
                value = feature.get("value")
                baseline = feature.get("baseline")
                impact = feature.get("impact_points")
                rows.append({
                    "signal": feature.get("label"),
                    "now": f"{value}{unit_txt}" if value is not None else "-",
                    "baseline": f"{baseline}{unit_txt}" if baseline is not None else "-",
                    "impact": f"{impact:+.1f} pts" if impact is not None else "-",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _value(value, digits: int | None = None):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if digits is None:
        return value
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


def _minutes_from_seconds(value):
    value = _value(value)
    if value is None:
        return None
    try:
        return round(float(value) / 60.0)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    value = _value(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_cardio_load(activities: pd.DataFrame, date_value) -> float | None:
    if activities is None or activities.empty or "date" not in activities:
        return None
    date = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(date):
        return None
    a = activities.copy()
    a["date"] = pd.to_datetime(a["date"], errors="coerce").dt.normalize()
    a = a[a["date"] == date.normalize()]
    if a.empty:
        return None
    if "training_load" in a and pd.to_numeric(a["training_load"], errors="coerce").notna().any():
        return _float_or_none(pd.to_numeric(a["training_load"], errors="coerce").sum())
    if {"duration_s", "avg_hr"}.issubset(a.columns):
        load = pd.to_numeric(a["duration_s"], errors="coerce").div(60.0) * pd.to_numeric(
            a["avg_hr"], errors="coerce"
        ).div(100.0)
        return _float_or_none(load.sum())
    return None


def _next_sleep_date(latest_row) -> str | None:
    if latest_row is None:
        return None
    date = pd.to_datetime(latest_row.get("date"), errors="coerce")
    if pd.isna(date):
        return None
    score = latest_row.get("sleep_score")
    if score is None or pd.isna(score):
        return date.normalize().strftime("%Y-%m-%d")
    return (date.normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def compact_early_waking(model: dict) -> dict:
    latest = (model or {}).get("latest") or {}
    keep_latest = {
        key: latest.get(key)
        for key in (
            "date", "early_waking_minutes", "severity", "confidence",
            "pattern", "evidence", "sleep_debt_h", "prior_sleep_debt_h_7d",
            "body_battery_at_sleep_start", "recovery_need_h",
        )
        if latest.get(key) is not None
    }
    return {
        key: value
        for key, value in (model or {}).items()
        if key not in ("rows", "latest")
    } | ({"latest": keep_latest} if keep_latest else {})


def recent_sleep_rows(daily: pd.DataFrame, days: int = 14) -> list[dict]:
    if daily is None or daily.empty:
        return []
    rows = []
    cols = [
        "date", "sleep_hours", "sleep_score", "sleep_debt_h", "awake_seconds",
        "hrv_overnight_avg", "resting_hr", "stress_avg", "body_battery_start",
        "hr_overnight_low", "hr_bedtime",
    ]
    for _, row in daily.tail(days).iterrows():
        rec = {}
        for col in cols:
            if col not in row:
                continue
            if col == "date":
                rec[col] = str(row[col])[:10]
            elif col == "awake_seconds":
                rec["awake_minutes"] = _minutes_from_seconds(row[col])
            elif col in ("sleep_hours", "sleep_debt_h"):
                rec[col] = _value(row[col], 1)
            elif col in ("sleep_score", "hrv_overnight_avg", "resting_hr", "stress_avg", "body_battery_start", "hr_overnight_low", "hr_bedtime"):
                rec[col] = _value(row[col], 0)
        rows.append({k: v for k, v in rec.items() if v is not None})
    return rows


def sleep_context(
    daily: pd.DataFrame,
    personal_sleep_need: dict,
    early_waking: dict,
    recommended_bedtime: dict,
    weekly_sleep: dict,
    health_research: dict,
) -> dict:
    recent = recent_sleep_rows(daily)
    latest = recent[-1] if recent else {}
    sleep_hours = [
        float(r["sleep_hours"]) for r in recent
        if r.get("sleep_hours") is not None
    ]
    sleep_scores = [
        float(r["sleep_score"]) for r in recent
        if r.get("sleep_score") is not None
    ]
    sleep_debt = [
        max(0.0, float(r["sleep_debt_h"])) for r in recent
        if r.get("sleep_debt_h") is not None
    ]
    summary = {
        "days": len(recent),
        "avg_sleep_hours": _value(sum(sleep_hours) / len(sleep_hours), 1) if sleep_hours else None,
        "avg_sleep_score": _value(sum(sleep_scores) / len(sleep_scores), 0) if sleep_scores else None,
        "sleep_debt_total_h": _value(sum(sleep_debt), 1) if sleep_debt else None,
        "short_nights": sum(1 for h in sleep_hours if h < 6.5),
        "low_score_nights": sum(1 for s in sleep_scores if s < 70),
    }
    health_sleep = (health_research or {}).get("sleep_regularity") or {}
    return {
        "latest": latest,
        "recent_summary": {k: v for k, v in summary.items() if v is not None},
        "recent_rows": recent,
        "personal_sleep_need": {
            key: value for key, value in (personal_sleep_need or {}).items()
            if key != "rows"
        },
        "recommended_bedtime": {
            key: value for key, value in (recommended_bedtime or {}).items()
            if key != "rows"
        },
        "weekly_sleep": {
            key: value for key, value in (weekly_sleep or {}).items()
            if key != "rows"
        },
        "early_waking": compact_early_waking(early_waking),
        "sleep_regularity": health_sleep,
    }


def daily_sleep_message(context: dict) -> str:
    latest = context.get("latest") or {}
    need = (context.get("personal_sleep_need") or {}).get("sleep_need_h")
    early = ((context.get("early_waking") or {}).get("latest") or {})
    bedtime = context.get("recommended_bedtime") or {}
    weekly = context.get("weekly_sleep") or {}

    if not latest:
        return (
            "## Sleep coach\n"
            "Sync Garmin sleep history to get a daily sleep readout.\n\n"
            "## Tonight\n"
            "- Keep the sleep window consistent.\n"
            "- Ask a question once sleep data is available."
        )

    date = latest.get("date") or "latest night"
    sleep_h = latest.get("sleep_hours")
    score = latest.get("sleep_score")
    debt = latest.get("sleep_debt_h")
    lines = [f"## Sleep coach\nFor `{date}`: "]
    facts = []
    if sleep_h is not None:
        target = f" vs {float(need):.1f}h need" if need is not None else ""
        facts.append(f"{sleep_h}h sleep{target}")
    if score is not None:
        facts.append(f"sleep score {score}")
    if debt is not None and float(debt) > 0:
        facts.append(f"{debt}h sleep debt")
    if facts:
        lines.append(", ".join(facts) + ".")
    else:
        lines.append("sleep metrics are sparse.")

    early_min = early.get("early_waking_minutes")
    if early_min is not None and float(early_min) >= 20:
        pattern = str(early.get("pattern") or "unclear").replace("_", " ")
        confidence = early.get("confidence") or "low"
        lines.append(
            f"\n\nEarly-for-recovery shows {early_min} min early, with "
            f"`{pattern}` as the visible signal ({confidence} confidence). "
            "Treat that as a signal, not a proven cause."
        )
    elif early_min is not None:
        lines.append("\n\nThe modeled recovery window looks covered for the latest night.")

    tonight = []
    if bedtime.get("status") == "ready":
        tonight.append(
            f"Aim for the {bedtime.get('window_start')}-{bedtime.get('window_end')} bedtime window."
        )
    elif need is not None:
        tonight.append(f"Protect roughly {float(need):.1f}h of sleep opportunity.")
    if weekly.get("mean") is not None:
        tonight.append(f"Use the weekly sleep score average ({weekly.get('mean')}) as the trend anchor.")
    if early_min is not None and float(early_min) >= 45:
        tonight.append("Bias toward a calmer pre-bed block and avoid adding more recovery debt.")
    if not tonight:
        tonight.append("Keep the sleep and wake window stable tonight.")

    lines.append("\n\n## Tonight\n" + "\n".join(f"- {item}" for item in tonight[:4]))
    return "".join(lines)


(
    daily,
    sleep_timing,
    acts,
    personal_sleep_need,
    early_waking,
    recommended_bedtime,
    weekly_sleep,
    health_research,
) = load(config.LOCAL_TIMEZONE)

coach_memory_digest = analysis.build_coach_memory_digest(db.load_memory_df())
active_experiments = analysis.summarize_active_experiments(
    db.load_experiments_df(status="active"),
    daily,
)
latest = daily.iloc[-1] if not daily.empty else None
date_str = fmt_date(latest["date"]) if latest is not None else fmt_date(pd.Timestamp.today())

st.markdown(cockpit.section_label("Sleep"), unsafe_allow_html=True)

win = st.session_state.get("sleep_win", 30) or 30
head_l, head_win = st.columns([8, 1.2], vertical_alignment="center")
with head_l:
    st.markdown(
        f"<div style=\"font-family:'Geist',Georgia,serif;font-size:34px;line-height:1.05;\">Sleep</div>"
        f"<div style=\"color:{cockpit.TEXT_FAINT};font-size:13px;margin-top:4px\">{date_str}</div>",
        unsafe_allow_html=True,
    )
with head_win:
    if not daily.empty:
        with st.popover(
            f"{win}d",
            icon=":material/calendar_month:",
            use_container_width=True,
            help="Time horizon for sleep trend charts",
        ):
            win = (
                st.segmented_control(
                    "Window",
                    [7, 30, 60],
                    default=30,
                    key="sleep_win",
                    format_func=lambda d: f"{d}d",
                    label_visibility="collapsed",
                )
                or 30
            )

if daily.empty:
    st.info("Sync Garmin sleep history to build the sleep dashboard.")
    st.stop()

view = daily.tail(win)
sleep_need = personal_sleep_need.get("sleep_need_h") or config.SLEEP_NEED_HOURS
sleep_ctx = sleep_context(
    daily,
    personal_sleep_need,
    early_waking,
    recommended_bedtime,
    weekly_sleep,
    health_research,
)
sleep_day = str(latest["date"])[:10] if latest is not None else "no-data"
daily_message = daily_sleep_message(sleep_ctx)

if st.session_state.get("sleep_chat_day") != sleep_day:
    st.session_state.sleep_chat_day = sleep_day
    st.session_state.sleep_chat = [{"role": "assistant", "content": daily_message}]
if "sleep_chat" not in st.session_state:
    st.session_state.sleep_chat = [{"role": "assistant", "content": daily_message}]

overview_tab, prediction_tab, recovery_tab, physiology_tab, coach_tab = st.tabs(
    ["Overview", "Prediction", "Early for Recovery", "Physiology & Timing", "Coach"]
)

with coach_tab:
    have_key = bool(config.ANTHROPIC_API_KEY)
    if not have_key:
        st.caption("Set `ANTHROPIC_API_KEY` in .env to ask sleep questions.")

    pending_sleep_prompt = None
    coach_actions = st.columns([1, 1, 4])
    with coach_actions[0]:
        if st.button("Analyse sleep", disabled=not have_key, width="stretch"):
            pending_sleep_prompt = "Analyse my latest sleep and tell me what to do tonight."
    with coach_actions[1]:
        if st.button("Clear", disabled=not st.session_state.sleep_chat, width="stretch"):
            st.session_state.sleep_chat = [{"role": "assistant", "content": daily_message}]
            st.rerun()

    with st.container(border=True):
        for msg in st.session_state.sleep_chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    with st.form("sleep_chat_form", clear_on_submit=True):
        sleep_question = st.text_input(
            "Sleep question",
            placeholder="Ask about last night, early waking, sleep score, bedtime, or what to change tonight...",
            label_visibility="collapsed",
            disabled=not have_key,
        )
        send_sleep = st.form_submit_button("Send", disabled=not have_key, width="stretch")

    if send_sleep and sleep_question.strip():
        pending_sleep_prompt = sleep_question.strip()

    if pending_sleep_prompt:
        history = st.session_state.sleep_chat[-8:]
        st.session_state.sleep_chat.append({"role": "user", "content": pending_sleep_prompt})
        with st.spinner("Reading your sleep context..."):
            try:
                answer = ai.answer_sleep_question(
                    pending_sleep_prompt,
                    sleep_ctx,
                    history,
                    coach_memory=coach_memory_digest,
                    active_experiments=active_experiments,
                )
            except Exception as e:
                answer = f"## Answer\n\nQuestion failed: {e}"
        st.session_state.sleep_chat.append({"role": "assistant", "content": answer})
        st.rerun()

with overview_tab:
    m1, m2, m3 = st.columns(3)
    with m1:
        metric_panel(
            "Personal sleep need",
            f"{sleep_need:.1f}h",
            str(personal_sleep_need.get("source") or "learning"),
        )
    with m2:
        metric_panel(
            "Recent early nights",
            f"{early_waking.get('recent_meaningful_days', 0)}/7",
            ">=45 min early for recovery",
        )
    with m3:
        weekly_label = (
            f"{weekly_sleep.get('mean'):.0f}"
            if weekly_sleep.get("status") == "ready" and weekly_sleep.get("mean") is not None
            else "-"
        )
        metric_panel("Weekly sleep score", weekly_label, "latest rolling week")

    st.markdown('<div class="sleep-overview-spacer"></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        chart_card("Sleep duration", f"target {sleep_need:.1f}h", cockpit.chart_sleep(view, sleep_need))
        if personal_sleep_need.get("source") != "personal_recovery_nights":
            st.caption(personal_sleep_need.get("message", "Learning personal sleep need."))
    with c2:
        if weekly_sleep.get("status") == "ready":
            sleep_meta = _week_label(weekly_sleep["week_start"], weekly_sleep["week_end"])
            if weekly_sleep.get("mean") is not None:
                sleep_meta += f" - avg {weekly_sleep['mean']:.0f}"
            if weekly_sleep.get("std") is not None:
                sleep_meta += f" - SD {weekly_sleep['std']:.1f}"
            chart_card("Weekly sleep score", sleep_meta, cockpit.chart_weekly_sleep_score(weekly_sleep))
            if weekly_sleep.get("days_with_data", 0) < 2:
                st.caption("Only one sleep score is synced for this week so far.")
        else:
            st.caption("No sleep scores are synced for the latest week yet.")

with prediction_tab:
    target_sleep_date = _next_sleep_date(latest)
    latest_load = _latest_cardio_load(acts, latest["date"])
    battery_default = _float_or_none(latest.get("body_battery_current"))
    if battery_default is None:
        battery_default = _float_or_none(latest.get("body_battery_low"))
    default_bedtime = (
        str(recommended_bedtime.get("bedtime_center"))
        if recommended_bedtime.get("status") == "ready" and recommended_bedtime.get("bedtime_center")
        else ""
    )
    with st.expander("Pre-bed inputs", expanded=False):
        i1, i2, i3, i4, i5 = st.columns(5)
        with i1:
            prebed_hr_input = st.number_input(
                "Pre-bed HR",
                min_value=30.0,
                max_value=130.0,
                value=_float_or_none(latest.get("hr_bedtime")),
                step=1.0,
                format="%.0f",
            )
        with i2:
            stress_input = st.number_input(
                "Avg stress",
                min_value=0.0,
                max_value=100.0,
                value=_float_or_none(latest.get("stress_avg")),
                step=1.0,
                format="%.0f",
            )
        with i3:
            load_input = st.number_input(
                "Training load",
                min_value=0.0,
                value=latest_load,
                step=5.0,
                format="%.0f",
            )
        with i4:
            battery_input = st.number_input(
                "Body Battery",
                min_value=0.0,
                max_value=100.0,
                value=battery_default,
                step=1.0,
                format="%.0f",
            )
        with i5:
            bedtime_input = st.text_input("Planned bedtime", value=default_bedtime, placeholder="23:00")

    prebed_prediction = analysis.compute_prebed_sleep_score_prediction(
        daily,
        acts,
        sleep_timing,
        target_date=target_sleep_date,
        sleep_need_h=sleep_need,
        prebed_hr=prebed_hr_input,
        stress_avg=stress_input,
        cardio_load=load_input,
        body_battery_current=battery_input,
        planned_bedtime=bedtime_input,
    )
    sleep_prediction_panel(prebed_prediction)

    if recommended_bedtime.get("status") == "ready":
        with st.container(border=True):
            st.markdown(cockpit.bedtime_card(recommended_bedtime), unsafe_allow_html=True)
    elif recommended_bedtime.get("status") == "learning":
        st.caption("Recommended bedtime is warming up - sync a few more nights of sleep timing.")
    else:
        st.caption("Recommended bedtime needs raw sleep start/end data.")

with recovery_tab:
    st.markdown(cockpit.early_waking_classifier_card(early_waking), unsafe_allow_html=True)
    if (early_waking or {}).get("rows"):
        early_meta = (
            f"need {early_waking.get('sleep_need_h', sleep_need):.1f}h - "
            f"{early_waking.get('recent_meaningful_days', 0)}/7 >=45 min"
        )
        if early_waking.get("recent_mean_early_minutes") is not None:
            early_meta += f" - avg {early_waking['recent_mean_early_minutes']:.0f} min"
        chart_card("Early for recovery", early_meta, cockpit.chart_early_waking(early_waking))

with physiology_tab:
    c1, c2 = st.columns(2)
    with c1:
        chart_card("Sleep composition", "", cockpit.chart_sleep_comp(view))
    with c2:
        health_rows = pd.DataFrame(health_research.get("rows") or [])
        if not health_rows.empty and "date" in health_rows:
            health_rows["date"] = pd.to_datetime(health_rows["date"], errors="coerce")
            health_view = health_rows.dropna(subset=["date"]).tail(win)
        else:
            health_view = pd.DataFrame()

        if not health_view.empty and any(
            col in health_view and health_view[col].notna().any()
            for col in ("sleep_midpoint_variability_7d", "bedtime_variability_7d", "wake_time_variability_7d")
        ):
            chart_card("Sleep timing regularity", "rolling SD", cockpit.chart_sleep_regularity(health_view))
        else:
            st.caption("Sleep timing regularity needs raw sleep start/end data from synced sleep payloads.")

    sleep_hr_col, bedtime_hr_col = st.columns(2)
    with sleep_hr_col:
        if "hr_overnight_low" in view and view["hr_overnight_low"].notna().any():
            chart_card("Lowest overnight heart rate", "bpm", cockpit.chart_sleeping_hr(view))
        else:
            st.caption("No lowest-overnight heart-rate trend stored yet.")
    with bedtime_hr_col:
        if "hr_bedtime" in view and view["hr_bedtime"].notna().any():
            chart_card("Pre-sleep HR median", "10m before sleep", cockpit.chart_bedtime_hr(view))
            bedtime_points = int(view["hr_bedtime"].notna().sum())
            if bedtime_points < 2:
                st.caption("Only one pre-sleep HR median is synced in this window, so the chart shows it as a single point for now.")
        else:
            st.caption("No pre-sleep heart-rate medians stored yet. Sync days that include sleep start plus all-day HR samples.")
