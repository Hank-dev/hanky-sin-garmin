"""Strength analytics page.

Strength logging happens outside this app. This page focuses on imported
sessions, recovery context, trends, standards, and history.
"""
import html
import importlib
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import db
import analysis
import cockpit

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
cockpit = importlib.reload(cockpit)

st.markdown("""
<style>
.strength-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin:4px 0 18px;}
.strength-page-title{font-family:var(--font-serif);font-size:34px;line-height:1.05;color:var(--text);font-weight:400;}
.strength-page-sub{color:var(--text-faint);font-size:13px;margin-top:4px;}
.strength-overview{display:grid;gap:14px;container-type:inline-size;}
.strength-hero{
  border:1px solid var(--border);border-top-color:var(--brass);border-radius:8px;
  background:linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#0a0a0a);
  width:100%;box-sizing:border-box;overflow:hidden;
  padding:18px 20px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  gap:18px;align-items:stretch;
}
.strength-hero > div{min-width:0;}
.strength-hero h2{font-family:var(--font-serif);font-size:31px;font-weight:400;line-height:1.05;margin:0;color:var(--text);}
.strength-hero .meta{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-bottom:8px;}
.strength-hero .sub{color:var(--text-dim);font-size:13px;margin-top:8px;}
.strength-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(132px,1fr));gap:10px;width:100%;min-width:0;}
.strength-kpi{min-width:0;overflow:hidden;background:var(--surface-2);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:11px 12px;min-height:86px;}
.strength-kpi *{word-break:normal;overflow-wrap:normal;hyphens:manual;}
.strength-kpi .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--text-faint);white-space:nowrap;}
.strength-kpi .val{margin-top:7px;font-size:22px;color:var(--text);font-weight:750;font-variant-numeric:tabular-nums;line-height:1.08;white-space:nowrap;}
.strength-kpi .sub{margin-top:5px;font-size:11px;color:var(--text-faint);line-height:1.25;}
.strength-panel{
  border:1px solid var(--border);border-radius:8px;background:var(--surface);padding:14px 16px;
}
.strength-panel h3{font-family:var(--font-serif);font-size:22px;font-weight:400;margin:0 0 10px;color:var(--text);}
.strength-table{display:grid;gap:7px;}
.strength-row{display:grid;grid-template-columns:minmax(0,1.7fr) .7fr .9fr .9fr .55fr;gap:10px;align-items:center;
  padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.strength-row:last-child{border-bottom:0;}
.strength-row.head{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);padding-top:0;}
.strength-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-row .num{font-family:var(--font-mono);font-size:13px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-pr{display:inline-flex;align-items:center;border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);
  color:var(--accent);border-radius:999px;padding:3px 8px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;}
.strength-history-rollup{display:grid;gap:0;margin:8px 0 10px;border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;}
.strength-history-row{display:grid;grid-template-columns:minmax(0,1.5fr) .55fr .8fr .78fr .78fr .45fr;gap:10px;align-items:center;
  padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);background:rgba(255,255,255,.018);}
.strength-history-row:last-child{border-bottom:0;}
.strength-history-row.head{background:rgba(255,255,255,.035);font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-history-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-history-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-momentum-counts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:2px 0 12px;}
.strength-momentum-count{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:9px 10px;}
.strength-momentum-count .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-momentum-count .val{margin-top:4px;font-size:21px;font-weight:800;color:var(--text);font-variant-numeric:tabular-nums;}
.strength-momentum-section{margin-top:10px;}
.strength-momentum-title{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px;}
.strength-momentum-row{display:grid;grid-template-columns:minmax(0,1.25fr) .65fr .55fr minmax(0,1.4fr);gap:10px;align-items:center;
  padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.strength-momentum-row:last-child{border-bottom:0;}
.strength-momentum-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-momentum-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-momentum-row .note{color:var(--text-faint);font-size:12px;line-height:1.3;}
.strength-leaderboard{display:grid;gap:0;margin-top:8px;border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;}
.strength-leaderboard-row{display:grid;grid-template-columns:.36fr minmax(0,1.2fr) .72fr .86fr .82fr .78fr .7fr;gap:10px;align-items:center;
  padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);background:rgba(255,255,255,.018);}
.strength-leaderboard-row:last-child{border-bottom:0;}
.strength-leaderboard-row.head{background:rgba(255,255,255,.035);font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-leaderboard-row .rank{font-family:var(--font-mono);font-size:12px;color:var(--text-faint);font-variant-numeric:tabular-nums;}
.strength-leaderboard-row .name{font-weight:750;color:var(--text);min-width:0;}
.strength-leaderboard-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.st-key-strength_trend_card,
.st-key-strength_pr_card{min-height:450px!important;box-sizing:border-box;}
.st-key-strength_trend_card [data-testid="stVerticalBlockBorderWrapper"],
.st-key-strength_pr_card [data-testid="stVerticalBlockBorderWrapper"]{min-height:450px;padding:18px 18px 16px!important;}
.st-key-strength_trend_card [data-testid="stVerticalBlock"],
.st-key-strength_pr_card [data-testid="stVerticalBlock"]{gap:.45rem!important;}
.strength-pr-list{display:grid;gap:0;margin-top:4px;}
.strength-pr-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:baseline;
  padding:10px 0;border-bottom:1px solid rgba(255,255,255,.055);}
.strength-pr-row:last-child{border-bottom:0;}
.strength-pr-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:750;font-size:14.5px;}
.strength-pr-value{white-space:nowrap;color:var(--text);font-size:14px;font-variant-numeric:tabular-nums;}
.strength-pr-date{grid-column:1/-1;color:var(--text-faint);font-size:11.5px;font-variant-numeric:tabular-nums;}
@container (max-width:900px){
  .strength-hero{grid-template-columns:1fr;}
}
@media (max-width:820px){
  .strength-hero{grid-template-columns:1fr;}
  .strength-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
  .strength-row{grid-template-columns:minmax(0,1.4fr) .6fr .8fr .8fr .45fr;gap:6px;}
  .strength-history-row{grid-template-columns:minmax(0,1.4fr) .45fr .7fr .7fr .72fr .42fr;gap:6px;}
  .strength-momentum-counts{grid-template-columns:repeat(2,minmax(0,1fr));}
  .strength-momentum-row{grid-template-columns:minmax(0,1.1fr) .6fr .5fr minmax(0,1fr);gap:6px;}
  .strength-leaderboard-row{grid-template-columns:.3fr minmax(0,1.1fr) .64fr .74fr .7fr .7fr .58fr;gap:6px;}
}
@media (max-width:560px){
  .strength-hero{padding:14px;}
  .strength-kpi-grid{grid-template-columns:1fr 1fr;}
  .strength-kpi{padding:10px;min-height:82px;}
  .strength-kpi .val{font-size:20px;}
  .strength-row{font-size:13px;}
  .strength-row .num{font-size:11px;}
  .strength-history-row{font-size:12px;padding:7px 8px;}
  .strength-history-row .num{font-size:10px;}
  .strength-momentum-row{font-size:12px;}
  .strength-momentum-row .num,.strength-momentum-row .note{font-size:10px;}
  .strength-leaderboard-row{font-size:11px;padding:7px 8px;}
  .strength-leaderboard-row .num,.strength-leaderboard-row .rank{font-size:10px;}
/* ── Key Lifts ── */
.key-lifts-section{margin:0 0 24px;}
.key-lifts-header{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px;}
.key-lifts-title{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.key-lifts-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}
.key-lift-card{background:var(--surface);border:1px solid var(--border);border-top:2px solid var(--accent);border-radius:8px;padding:14px 16px;min-width:0;overflow:hidden;}
.key-lift-card .kl-name{font-weight:700;font-size:15px;color:var(--text);margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.key-lift-card .kl-1rm-lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px;}
.key-lift-card .kl-1rm{font-size:28px;font-weight:800;color:var(--text);font-variant-numeric:tabular-nums;line-height:1;}
.key-lift-card .kl-1rm-unit{font-size:13px;color:var(--text-faint);font-weight:500;margin-left:2px;}
.key-lift-card .kl-recent{margin-top:10px;display:flex;justify-content:space-between;align-items:baseline;}
.key-lift-card .kl-recent-val{font-family:var(--font-mono);font-size:13px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.key-lift-card .kl-recent-lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);}
.key-lift-card .kl-delta{font-family:var(--font-mono);font-size:11px;font-variant-numeric:tabular-nums;}
.key-lift-card .kl-delta.up{color:var(--good);}
.key-lift-card .kl-delta.down{color:var(--red);}
.key-lift-card .kl-delta.flat{color:var(--text-faint);}
.key-lift-card .kl-last{margin-top:6px;font-family:var(--font-mono);font-size:10px;color:var(--text-faint);}
@media(max-width:820px){.key-lifts-grid{grid-template-columns:repeat(2,1fr);}}
@media(max-width:560px){.key-lifts-grid{grid-template-columns:1fr;}}
}
</style>
""", unsafe_allow_html=True)

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


def todays_recovery_verdict(day: str) -> tuple[dict, dict]:
    daily = analysis.enrich_daily(db.load_daily_df())
    readiness = analysis.recovery_readiness(daily, as_of=day)
    return analysis.readiness_verdict(readiness), readiness


@st.cache_data(ttl=30)
def load_strength_sessions_with_context():
    sessions = db.load_strength_sessions_df()
    if sessions.empty:
        return sessions
    acts = db.load_activities_df()
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(acts, daily)
    merged = analysis.merge_strength_session_context(sessions, acts, daily)
    persist_strength_session_context(sessions, merged)
    return merged


def _missing_context_value(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def persist_strength_session_context(original, merged):
    """Persist compact Garmin/daily context discovered during merge.

    This only fills missing session columns; user/import-provided values win.
    """
    if original is None or merged is None or original.empty or merged.empty:
        return
    if "session_id" not in original or "session_id" not in merged:
        return
    backfill_cols = [
        "garmin_activity_id", "garmin_readiness_score",
        "readiness_score", "readiness_level", "hrv_status",
        "hrv_overnight_avg", "body_battery_start", "sleep_score",
        "resting_hr", "acwr", "recovery_score", "recovery_zone",
    ]
    original_by_session = {
        row["session_id"]: row
        for _, row in original.iterrows()
        if not _missing_context_value(row.get("session_id"))
    }
    for _, row in merged.iterrows():
        sid = row.get("session_id")
        if _missing_context_value(sid):
            continue
        prior = original_by_session.get(sid)
        if prior is None:
            continue
        record = {"session_id": sid}
        for col in backfill_cols:
            if col not in merged:
                continue
            value = row.get(col)
            if _missing_context_value(value):
                continue
            if col in original and not _missing_context_value(prior.get(col)):
                continue
            record[col] = value.item() if hasattr(value, "item") else value
        if len(record) > 1:
            db.upsert_strength_session(record)


def fmt_num(value, digits: int = 0, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    text = f"{n:,.0f}" if digits == 0 else f"{n:,.{digits}f}"
    return f"{text}{suffix}"


def fmt_signed(value, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{n:+.{digits}f}{suffix}"


def fmt_recovery_label(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none", "not tagged"}:
        return "Not tagged"
    return text.replace("_", " ").title()


def strength_kpi(label: str, value: str, sub: str = "") -> str:
    title = f"{label}: {value}"
    if sub:
        title = f"{title} ({sub})"
    return (
        f"<div class='strength-kpi' title='{html.escape(title, quote=True)}'>"
        f"<div class='lab'>{html.escape(label)}</div>"
        f"<div class='val'>{html.escape(value)}</div>"
        f"<div class='sub'>{html.escape(sub)}</div></div>"
    )


def strength_trend_chart(rows: list[dict]) -> go.Figure:
    fig = go.Figure()
    data = pd.DataFrame(rows or [])
    if data.empty:
        return fig
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date")
    if data.empty:
        return fig
    data = data.reset_index(drop=True)
    data["x_pos"] = list(range(len(data)))
    date_label_fmt = "%b %-d '%y" if data["date"].dt.year.nunique() > 1 else "%b %-d"
    data["date_label"] = data["date"].dt.strftime(date_label_fmt)
    data["date_full"] = data["date"].dt.strftime("%Y-%m-%d")
    data["name"] = data.get("name", "Workout")
    custom = data[["date_full", "name"]].fillna("").to_numpy()
    x_range = [-0.5, max(0.5, len(data) - 0.5)]
    fig.add_trace(go.Bar(
        x=data["x_pos"],
        y=pd.to_numeric(data["total_volume_kg"], errors="coerce"),
        name="Volume",
        marker_color=cockpit.ACCENT,
        opacity=0.68,
        width=0.42,
        yaxis="y",
        customdata=custom,
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>Volume %{y:,.0f} kg<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=data["x_pos"],
        y=pd.to_numeric(data["top_est_1rm_kg"], errors="coerce"),
        name="Top est 1RM",
        mode="lines+markers",
        line=dict(color=cockpit.SERIES2, width=2),
        marker=dict(size=7, color=cockpit.SERIES2, line=dict(width=1, color=cockpit.BG)),
        yaxis="y2",
        connectgaps=False,
        customdata=custom,
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>Top est 1RM %{y:.1f} kg<extra></extra>",
    ))
    fig.update_layout(
        height=340,
        margin=dict(l=44, r=44, t=44, b=34),
        paper_bgcolor=cockpit.BG,
        plot_bgcolor=cockpit.BG,
        font=dict(family="Geist, sans-serif", color=cockpit.TEXT),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5,
            bgcolor="rgba(0,0,0,0)", font=dict(size=12)
        ),
        xaxis=dict(
            tickmode="array", tickvals=list(data["x_pos"]), ticktext=list(data["date_label"]),
            range=x_range, gridcolor="rgba(255,255,255,.04)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
        yaxis=dict(
            title=None, gridcolor="rgba(255,255,255,.06)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
        yaxis2=dict(
            title=None, overlaying="y", side="right", showgrid=False,
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
    )
    return fig


def weekly_strength_load_chart(rows, metric: str = "total_volume_kg") -> go.Figure:
    fig = go.Figure()
    data = pd.DataFrame(rows or [])
    if data.empty:
        return fig
    data["week_start"] = pd.to_datetime(data["week_start"], errors="coerce")
    data = data.dropna(subset=["week_start"]).sort_values(["week_start", "group"])
    if data.empty:
        return fig
    metric = metric if metric in data.columns else "total_volume_kg"
    data[metric] = pd.to_numeric(data[metric], errors="coerce").fillna(0)
    preferred = ["Push", "Pull", "Squat", "Hinge", "Core", "Other"]
    groups = [g for g in preferred if g in set(data["group"])]
    groups.extend(sorted(g for g in data["group"].dropna().unique() if g not in groups))
    colors = {
        "Push": cockpit.ACCENT,
        "Pull": cockpit.SERIES2,
        "Squat": cockpit.AMBER,
        "Hinge": "#8FA7FF",
        "Core": "#D98BD2",
        "Other": cockpit.TEXT_FAINT,
    }
    fallback = ["#B7C3D0", "#73BBA3", "#E2A6A1", "#C7A7F2", "#D7C27C", "#9FB6D8"]
    for idx, group in enumerate(groups):
        sub = data[data["group"] == group]
        fig.add_trace(go.Bar(
            x=sub["week_start"],
            y=sub[metric],
            name=str(group),
            marker_color=colors.get(group, fallback[idx % len(fallback)]),
            hovertemplate="%{x|%b %d}<br>%{y:,.0f}<extra>" + html.escape(str(group)) + "</extra>",
        ))
    ytitle = "kg volume" if metric == "total_volume_kg" else "working sets"
    fig.update_layout(
        height=320,
        barmode="stack",
        margin=dict(l=42, r=20, t=18, b=36),
        paper_bgcolor=cockpit.BG,
        plot_bgcolor=cockpit.BG,
        font=dict(family="Geist, sans-serif", color=cockpit.TEXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="rgba(255,255,255,.04)", tickfont=dict(color=cockpit.TEXT_FAINT, size=10)),
        yaxis=dict(title=ytitle, gridcolor="rgba(255,255,255,.06)", tickfont=dict(color=cockpit.TEXT_FAINT, size=10)),
    )
    return fig


def render_strength_overview(overview: dict, strength_summary: dict):
    if (overview or {}).get("status") != "ok":
        st.info("Import strength workouts to build the recent-session cockpit.")
        return

    latest = overview["latest_session"]
    summ = overview.get("latest_summary") or {}
    trend = overview.get("trend") or {}
    exercises = overview.get("exercise_rows") or []
    prs = overview.get("recent_prs") or []
    name = html.escape(latest.get("name") or "Workout")
    date_txt = html.escape(latest.get("date") or "")
    duration = fmt_num(latest.get("duration_min"), 0, " min") if latest.get("duration_min") is not None else "-"
    recovery = fmt_recovery_label(latest.get("recovery_zone") or latest.get("readiness_level"))
    recovery_score = fmt_num(latest.get("recovery_score"), 0)
    recovery_sub = f"score {recovery_score}" if recovery_score != "-" else "no score"
    kpis = [
        strength_kpi("Volume", fmt_num(summ.get("total_volume_kg"), 0, " kg"), fmt_signed(trend.get("volume_delta_pct"), 1, "% vs prior")),
        strength_kpi("Working sets", fmt_num(summ.get("working_sets"), 0), fmt_signed(trend.get("working_sets_delta"), 1, " sets")),
        strength_kpi("Top est 1RM", fmt_num(summ.get("top_est_1rm_kg"), 1, " kg"), fmt_signed(trend.get("top_est_1rm_delta_kg"), 1, " kg")),
        strength_kpi("Recovery", recovery, recovery_sub),
    ]

    st.markdown(
        cockpit._collapse_html(
            f"""
            <div class='strength-overview'>
              <div class='strength-hero'>
                <div>
                  <div class='meta'>Latest completed session</div>
                  <h2>{name}</h2>
                  <div class='sub'>{date_txt} · {html.escape(duration)} · {len(exercises)} exercises tracked</div>
                </div>
                <div class='strength-kpi-grid'>{''.join(kpis)}</div>
              </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(key="strength_trend_card", border=True):
            st.markdown("#### Session trend")
            rows = overview.get("trend_rows") or []
            if rows:
                st.plotly_chart(strength_trend_chart(rows), width="stretch", config={"displayModeBar": False, "scrollZoom": False})
                basis = trend.get("basis")
                if basis:
                    st.caption(basis)
            else:
                st.caption("Import a few sessions to see volume and top-estimated-1RM trends.")

        with st.container(border=True):
            st.markdown("#### Latest exercises")
            if not exercises:
                st.caption("No completed working sets were saved for the latest session.")
            else:
                table_rows = [
                    "<div class='strength-row head'><span>Exercise</span><span>Sets</span><span>Volume</span><span>Best</span><span>PR</span></div>"
                ]
                for row in exercises[:8]:
                    pr = "<span class='strength-pr'>PR</span>" if row.get("is_pr") else ""
                    table_rows.append(
                        "<div class='strength-row'>"
                        f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
                        f"<span class='num'>{fmt_num(row.get('working_sets'), 0)}</span>"
                        f"<span class='num'>{fmt_num(row.get('volume_kg'), 0, ' kg')}</span>"
                        f"<span class='num'>{html.escape(str(row.get('best_set') or '-'))}</span>"
                        f"<span>{pr}</span></div>"
                    )
                st.markdown("<div class='strength-table'>" + "".join(table_rows) + "</div>", unsafe_allow_html=True)

    with right:
        with st.container(key="strength_pr_card", border=True):
            st.markdown("#### Recent PRs")
            latest_prs = [p for p in prs if p.get("latest_session")]
            visible_prs = latest_prs or prs[-5:]
            if visible_prs:
                pr_rows = []
                for pr in reversed(visible_prs[-5:]):
                    marker = "latest" if pr.get("latest_session") else pr.get("date")
                    exercise = str(pr.get("exercise") or "Exercise")
                    pr_rows.append(
                        "<div class='strength-pr-row'>"
                        f"<div class='strength-pr-name' title='{html.escape(exercise, quote=True)}'>{html.escape(exercise)}</div>"
                        f"<div class='strength-pr-value'>{fmt_num(pr.get('est_1rm_kg'), 1, ' kg')}</div>"
                        f"<div class='strength-pr-date'>{html.escape(str(marker))}</div>"
                        "</div>"
                    )
                st.markdown("<div class='strength-pr-list'>" + "".join(pr_rows) + "</div>", unsafe_allow_html=True)
            else:
                st.caption("No PRs detected yet.")

        with st.container(border=True):
            st.markdown("#### Strength profile")
            standards = (strength_summary or {}).get("standards") or {}
            recent = (strength_summary or {}).get("recent") or {}
            readiness = (strength_summary or {}).get("readiness_link") or {}
            if standards.get("overall"):
                st.metric("Standards", standards["overall"].get("level"), f"~{standards['overall'].get('percentile')} pct")
            else:
                st.caption(f"Standards: {standards.get('status', 'learning')}")
            st.metric("28d tonnage", fmt_num(recent.get("tonnage_kg"), 0, " kg"), f"{recent.get('sessions_per_week', 0)} sessions/wk")
            st.caption(readiness.get("insight") or f"Readiness link: {readiness.get('status', 'learning')}")


def render_history_exercise_rollup(rows):
    if rows is None or len(rows) == 0:
        st.caption("No completed working sets for this session.")
        return
    table_rows = [
        "<div class='strength-history-row head'>"
        "<span>Exercise</span><span>Sets</span><span>Volume</span>"
        "<span>Best</span><span>Est 1RM</span><span>PR</span></div>"
    ]
    for row in rows:
        pr = "<span class='strength-pr'>PR</span>" if row.get("is_pr") else ""
        table_rows.append(
            "<div class='strength-history-row'>"
            f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
            f"<span class='num'>{fmt_num(row.get('working_sets'), 0)}</span>"
            f"<span class='num'>{fmt_num(row.get('volume_kg'), 0, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('best_set') or '-'))}</span>"
            f"<span class='num'>{fmt_num(row.get('best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span>{pr}</span></div>"
        )
    st.markdown(
        "<div class='strength-history-rollup'>" + "".join(table_rows) + "</div>",
        unsafe_allow_html=True,
    )


def render_strength_momentum_panel(momentum: dict):
    momentum = momentum or {}
    if momentum.get("status") in (None, "no_data"):
        st.caption("Import completed working sets to classify exercise momentum.")
        return
    categories = momentum.get("categories") or {}
    summary = momentum.get("summary") or {}
    order = [
        ("progressing", "Progressing", cockpit.SERIES2),
        ("flat", "Flat", cockpit.AMBER),
        ("regressing", "Regressing", cockpit.RED),
        ("undertrained", "Undertrained areas", cockpit.TEXT_FAINT),
    ]
    count_html = []
    for key, label, color in order:
        count_html.append(
            "<div class='strength-momentum-count'>"
            f"<div class='lab' style='color:{color}'>{html.escape(label)}</div>"
            f"<div class='val'>{int(summary.get(key) or 0)}</div></div>"
        )
    st.markdown(
        "<div class='strength-momentum-counts'>" + "".join(count_html) + "</div>",
        unsafe_allow_html=True,
    )
    if momentum.get("status") == "learning":
        st.caption("No clear momentum flags yet.")
        return
    for key, label, color in order:
        items = categories.get(key) or []
        if not items:
            continue
        rows = [
            f"<div class='strength-momentum-title' style='color:{color}'>{html.escape(label)}</div>"
        ]
        for item in items[:6]:
            if key == "undertrained":
                change = f"{int(item.get('days_since') or 0)}d"
                metric = f"{int(item.get('recent_working_sets') or 0)} sets"
            elif key == "flat":
                change = fmt_num(item.get("delta_pct"), 1, "%")
                metric = fmt_num(item.get("last_best_est_1rm_kg"), 1, " kg")
            else:
                change = fmt_signed(item.get("delta_pct"), 1, "%")
                metric = fmt_num(item.get("last_best_est_1rm_kg"), 1, " kg")
            rows.append(
                "<div class='strength-momentum-row'>"
                f"<span class='name'>{html.escape(str(item.get('name') or 'Exercise'))}</span>"
                f"<span class='num'>{html.escape(metric)}</span>"
                f"<span class='num' style='color:{color}'>{html.escape(change)}</span>"
                f"<span class='note'>{html.escape(str(item.get('note') or ''))}</span>"
                "</div>"
            )
        st.markdown(
            "<div class='strength-momentum-section'>" + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )
    if momentum.get("as_of"):
        st.caption(f"Momentum as of {momentum['as_of']}.")


def render_best_set_leaderboard(rows, limit: int = 12):
    if rows is None or len(rows) == 0:
        st.caption("Import completed working sets to build the best-set leaderboard.")
        return
    visible = list(rows)[:max(1, int(limit or 12))]
    table_rows = [
        "<div class='strength-leaderboard-row head'>"
        "<span>#</span><span>Exercise</span><span>Top 1RM</span>"
        "<span>Best set</span><span>Heaviest</span><span>Recent</span><span>Last PR</span></div>"
    ]
    for idx, row in enumerate(visible, start=1):
        table_rows.append(
            "<div class='strength-leaderboard-row'>"
            f"<span class='rank'>{idx}</span>"
            f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
            f"<span class='num'>{fmt_num(row.get('best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('best_est_1rm_set') or '-'))}</span>"
            f"<span class='num'>{html.escape(str(row.get('heaviest_set') or '-'))}</span>"
            f"<span class='num'>{fmt_num(row.get('recent_best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('last_pr_date') or '-'))}</span>"
            "</div>"
        )
    st.markdown(
        "<div class='strength-leaderboard'>" + "".join(table_rows) + "</div>",
        unsafe_allow_html=True,
    )


# ── Key Lifts tracking ──────────────────────────────────────────────────────
KEY_LIFTS = ["lat-pulldown", "seated-cable-row", "leg-press", "bench-press"]
KEY_LIFT_NAMES = {
    "lat-pulldown": "Lat Pulldown",
    "seated-cable-row": "Seated Row",
    "leg-press": "Leg Press",
    "bench-press": "Bench Press",
}


def _epley_1rm(weight_kg: float, reps: int) -> float:
    """Epley formula: 1RM = w × (1 + r/30)."""
    if not weight_kg or not reps or reps >= 35:
        return 0.0
    return float(weight_kg) * (1.0 + float(reps) / 30.0)


def compute_key_lift_trend(sets_df, sessions_df, since: str = "2026-06-01"):
    """Return per-lift list of {date, est_1rm, weight, reps} filtered to `since`."""
    if sets_df is None or sets_df.empty or sessions_df is None or sessions_df.empty:
        return {}
    result = {}
    merged = sets_df.merge(
        sessions_df[["session_id", "date"]], on="session_id", how="left"
    )
    merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
    merged = merged.dropna(subset=["date"])
    cutoff = pd.Timestamp(since)
    for ex_id in KEY_LIFTS:
        rows = merged[
            (merged["exercise_id"] == ex_id)
            & (merged["completed"] == 1)
            & (merged.get("is_warmup", 0) != 1)
            & (merged["date"] >= cutoff)
        ].copy()
        if rows.empty:
            result[ex_id] = []
            continue
        rows["est_1rm"] = rows.apply(
            lambda r: _epley_1rm(r.get("weight_kg"), r.get("reps")), axis=1
        )
        rows = rows[rows["est_1rm"] > 0].sort_values("date")
        if rows.empty:
            result[ex_id] = []
            continue
        per_session = rows.groupby("date").agg(
            est_1rm=("est_1rm", "max"),
            weight=("weight_kg", "max"),
            reps=("reps", "first"),
        ).reset_index()
        result[ex_id] = per_session.to_dict("records")
    return result


def _key_lift_chart(name: str, data: list[dict]) -> go.Figure:
    """Single est-1RM line chart for one key lift."""
    fig = go.Figure()
    if not data:
        fig.update_layout(
            height=220, margin=dict(l=0, r=0, t=30, b=0),
            paper_bgcolor=cockpit.BG, plot_bgcolor=cockpit.BG,
            annotations=[dict(text="No sessions yet", showarrow=False,
                              xref="paper", yref="paper", x=0.5, y=0.5,
                              font=dict(color=cockpit.TEXT_FAINT, size=12))],
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig
    df = pd.DataFrame(data)
    df["set_str"] = df.apply(lambda r: f"{r['weight']:.0f}×{int(r['reps'])}", axis=1)
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["est_1rm"],
        mode="lines+markers+text",
        line=dict(color=cockpit.ACCENT, width=2.5, shape="spline"),
        marker=dict(size=9, color=cockpit.ACCENT, line=dict(width=1.5, color=cockpit.BG)),
        text=[f"{v:.0f}" for v in df["est_1rm"]],
        textposition="top center",
        textfont=dict(size=10, color=cockpit.TEXT),
        customdata=df[["set_str"]].to_numpy(),
        hovertemplate="%{x|%b %-d}<br>%{y:.1f} kg<br>%{customdata[0]}<extra></extra>",
    ))
    fig.update_layout(
        height=220, margin=dict(l=36, r=16, t=30, b=24),
        paper_bgcolor=cockpit.BG, plot_bgcolor=cockpit.BG,
        font=dict(family="Geist, sans-serif", color=cockpit.TEXT),
        showlegend=False,
        xaxis=dict(
            gridcolor="rgba(255,255,255,.04)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=9),
            fixedrange=True,
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,.06)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=9),
            fixedrange=True,
            rangemode="tozero",
        ),
    )
    return fig


def render_key_lifts(trends: dict):
    """Render 4 est-1RM trend charts (2×2 grid) at the top of Overview."""
    st.markdown(
        "<div class='key-lifts-section'>"
        "<div class='key-lifts-header'>"
        "<div class='key-lifts-title'>Key Lifts · This Summer</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
    for i, ex_id in enumerate(KEY_LIFTS):
        row, col = positions[i]
        with cols[col]:
            data = trends.get(ex_id, [])
            recent_val = data[-1]["est_1rm"] if data else None
            delta_str = ""
            if data and len(data) >= 2:
                delta = data[-1]["est_1rm"] - data[-2]["est_1rm"]
                if abs(delta) < 0.3:
                    delta_str = " → flat"
                elif delta > 0:
                    delta_str = f" ↑{delta:+.1f}"
                else:
                    delta_str = f" ↓{delta:+.1f}"
            label = KEY_LIFT_NAMES.get(ex_id, ex_id)
            if recent_val:
                label = f"{label} · {recent_val:.0f} kg{delta_str}"
            st.markdown(f"**{label}**")
            st.plotly_chart(
                _key_lift_chart(label, data),
                use_container_width=True,
                config={"displayModeBar": False, "scrollZoom": False},
            )


# ── page ──────────────────────────────────────────────────────────────────────
st.markdown(
    "<div class='strength-page-head'><div><div class='strength-page-title'>Strength</div>"
    "<div class='strength-page-sub'>Imported sessions, trends, recovery context, and performance flags.</div></div></div>",
    unsafe_allow_html=True,
)

catalog = load_catalog()

tab_overview, tab_history, tab_insights, tab_body = st.tabs(
    ["Overview", "History", "Insights", "Bodyweight"])

with tab_overview:
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if not sessions.empty:
        key_lift_trends = compute_key_lift_trend(sets, sessions)
        render_key_lifts(key_lift_trends)
        bodyweight = resolve_bodyweight(today_str())
        verdict, _readiness = todays_recovery_verdict(today_str())
        overview = analysis.compute_strength_recent_overview(
            sessions, sets, catalog, config.ONE_RM_FORMULA
        )
        strength_summary = analysis.summarize_strength(
            sessions, sets, catalog, db.load_profile(), bodyweight,
            formula=config.ONE_RM_FORMULA, verdict=verdict,
        )
        render_strength_overview(overview, strength_summary)
    else:
        st.info("No completed strength sessions yet. Import strength history to build analytics.")

with tab_history:
    st.subheader("History")
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("No workouts logged yet.")
    else:
        date_values = pd.to_datetime(sessions.get("date"), errors="coerce").dropna()
        start_filter = end_filter = None
        workout_filter = None
        exercise_filter = None
        query_filter = ""
        pr_only = False

        with st.container(border=True):
            dcol, wcol, ecol = st.columns([1.25, 1, 1], gap="medium")
            if not date_values.empty:
                min_day = date_values.min().date()
                max_day = date_values.max().date()
                picked = dcol.date_input(
                    "Date range",
                    value=(min_day, max_day),
                    min_value=min_day,
                    max_value=max_day,
                    key="strength_history_date_range",
                )
                if isinstance(picked, (list, tuple)):
                    if len(picked) >= 2:
                        start_filter, end_filter = picked[0], picked[1]
                    elif len(picked) == 1:
                        start_filter = end_filter = picked[0]
                elif picked:
                    start_filter = end_filter = picked
            else:
                dcol.caption("No valid session dates.")

            workout_names = []
            if "name" in sessions.columns:
                workout_names = sorted({
                    str(name).strip()
                    for name in sessions["name"].dropna()
                    if str(name).strip()
                })
            workout_label = wcol.selectbox(
                "Workout",
                ["All workouts"] + workout_names,
                key="strength_history_workout_filter",
            )
            if workout_label != "All workouts":
                workout_filter = workout_label

            name_map = (
                dict(zip(catalog["exercise_id"], catalog["name"]))
                if catalog is not None and not catalog.empty and "name" in catalog.columns
                else {}
            )
            used_ids = []
            if sets is not None and not sets.empty and "exercise_id" in sets.columns:
                used_ids = [ex_id for ex_id in sets["exercise_id"].dropna().unique()]
            exercise_options = {"All exercises": None}
            for ex_id in sorted(used_ids, key=lambda value: str(name_map.get(value, value)).lower()):
                exercise_options[str(name_map.get(ex_id, ex_id))] = ex_id
            exercise_label = ecol.selectbox(
                "Exercise",
                list(exercise_options.keys()),
                key="strength_history_exercise_filter",
            )
            exercise_filter = exercise_options.get(exercise_label)

            qcol, pcol = st.columns([3, 1], gap="medium")
            query_filter = qcol.text_input(
                "Search",
                placeholder="Workout, date, or exercise",
                key="strength_history_search",
            )
            pr_only = pcol.checkbox("PR only", key="strength_history_pr_only")

        filtered_sessions = analysis.filter_strength_history_sessions(
            sessions,
            sets,
            catalog,
            start_date=start_filter,
            end_date=end_filter,
            exercise_id=exercise_filter,
            workout_name=workout_filter,
            query=query_filter,
            pr_only=pr_only,
            formula=config.ONE_RM_FORMULA,
        )
        if filtered_sessions.empty:
            st.info("No strength sessions match the current filters.")
        else:
            st.caption(f"Showing {len(filtered_sessions)} of {len(sessions)} sessions.")

            summaries = analysis.summarize_sessions(sessions, sets, catalog,
                                                    config.ONE_RM_FORMULA)
            sm = {r["session_id"]: r for _, r in summaries.iterrows()}
            exercise_rollups = analysis.summarize_session_exercises(
                sessions, sets, catalog, config.ONE_RM_FORMULA
            )
            rollups_by_session = {}
            if not exercise_rollups.empty:
                for sid, grp in exercise_rollups.groupby("session_id", sort=False):
                    rollups_by_session[str(sid)] = grp.to_dict("records")
            for _, sess in filtered_sessions.sort_values("date", ascending=False).iterrows():
                session_id = str(sess["session_id"])
                summ = sm.get(sess["session_id"], {})
                st.markdown(cockpit.strength_session_card(dict(sess), dict(summ)),
                            unsafe_allow_html=True)
                snap = {k: sess.get(k) for k in (
                    "readiness_score", "garmin_readiness_score",
                    "readiness_level", "hrv_status", "hrv_overnight_avg",
                    "resting_hr", "body_battery_start")}
                st.markdown(cockpit.strength_readiness_badge(snap),
                            unsafe_allow_html=True)
                render_history_exercise_rollup(rollups_by_session.get(session_id, []))
                with st.expander("Raw sets"):
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
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})

with tab_insights:
    st.subheader("Insights")
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("Log a few workouts (especially the main lifts) to unlock standards, balance, and readiness insights.")
    else:
        profile = db.load_profile()
        bodyweight = resolve_bodyweight(today_str())
        prs = analysis.compute_pr_timeline(sets, sessions, catalog, config.ONE_RM_FORMULA)
        best_map = (prs.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                    if not prs.empty else {})

        st.markdown("##### Weekly strength load")
        with st.container(border=True):
            lcol, mcol, wcol = st.columns([1.25, 1, 0.75], gap="medium")
            group_label = lcol.selectbox(
                "Group by",
                ["Training pattern", "Primary muscle"],
                key="strength_weekly_load_group",
            )
            metric_label = mcol.selectbox(
                "Metric",
                ["Volume", "Working sets"],
                key="strength_weekly_load_metric",
            )
            weeks = wcol.selectbox(
                "Weeks",
                [8, 12, 16, 24],
                index=1,
                key="strength_weekly_load_weeks",
            )
            group_mode = "muscle" if group_label == "Primary muscle" else "pattern"
            metric = "working_sets" if metric_label == "Working sets" else "total_volume_kg"
            load_rows = analysis.compute_weekly_strength_load(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
                weeks=int(weeks),
                group_by=group_mode,
            )
            if load_rows.empty:
                st.caption("Log completed working sets to see weekly strength load.")
            else:
                st.plotly_chart(
                    weekly_strength_load_chart(load_rows.to_dict("records"), metric),
                    width="stretch",
                    config={"displayModeBar": False, "scrollZoom": False},
                )
                latest_week = load_rows["week_start"].max()
                recent_load = load_rows[load_rows["week_start"] == latest_week].copy()
                if not recent_load.empty:
                    total = recent_load[metric].sum()
                    top = recent_load.sort_values(metric, ascending=False).iloc[0]
                    unit = "sets" if metric == "working_sets" else "kg"
                    st.caption(
                        f"Latest week {latest_week}: {fmt_num(total, 0, ' ' + unit)} total, "
                        f"largest bucket {top['group']}."
                    )

        st.divider()
        st.markdown("##### Plateau and momentum")
        with st.container(border=True):
            momentum = analysis.compute_strength_momentum_flags(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
            )
            render_strength_momentum_panel(momentum)

        st.divider()
        st.markdown("##### Best set leaderboard")
        with st.container(border=True):
            sort_col, limit_col = st.columns([1.4, .7], gap="medium")
            sort_label = sort_col.selectbox(
                "Rank by",
                ["Estimated 1RM", "Heaviest load", "Set volume", "Recent 90d 1RM"],
                key="strength_best_set_rank_by",
            )
            limit_label = limit_col.selectbox(
                "Rows",
                [10, 20, 50],
                key="strength_best_set_limit",
            )
            leaderboard = analysis.compute_strength_best_set_leaderboard(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
                recent_days=90,
            )
            if leaderboard.empty:
                st.caption("Log completed working sets to build the best-set leaderboard.")
            else:
                sort_map = {
                    "Estimated 1RM": "best_est_1rm_kg",
                    "Heaviest load": "heaviest_load_kg",
                    "Set volume": "best_volume_kg",
                    "Recent 90d 1RM": "recent_best_est_1rm_kg",
                }
                metric = sort_map.get(sort_label, "best_est_1rm_kg")
                leaderboard = leaderboard.copy()
                leaderboard[metric] = pd.to_numeric(leaderboard[metric], errors="coerce")
                leaderboard = leaderboard.sort_values(metric, ascending=False, na_position="last")
                render_best_set_leaderboard(leaderboard.to_dict("records"), int(limit_label))

        st.divider()
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
            st.plotly_chart(panel, width="stretch", config={"displayModeBar": False, "scrollZoom": False})
            if corr.get("insight"):
                st.caption(corr["insight"])

        st.divider()
        st.markdown("##### Recovery-sensitive lifts")
        sens = analysis.compute_lift_recovery_sensitivity(
            sessions, sets, catalog, formula=config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_recovery_sensitivity_panel(sens),
                    unsafe_allow_html=True)

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
