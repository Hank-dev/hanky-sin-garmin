"""Experiment lab — run N-of-1 before/after self-experiments and see whether a
habit or supplement actually moved your recovery metrics."""
import importlib
import html
from datetime import date

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

db.init_db()

_daily_raw = db.load_daily_df()
daily = analysis.enrich_daily(_daily_raw) if not _daily_raw.empty else _daily_raw
checkins = db.load_checkins_df()
acts = db.load_activities_df()
sleep_timing = db.load_sleep_timing_df()
body_battery = db.load_body_battery_df()
stress_loader = getattr(db, "load_stress_df", None)
stress = (
    stress_loader()
    if stress_loader is not None
    else pd.DataFrame(columns=["date", "timestamp", "value"])
)
hr_loader = getattr(db, "load_heart_rate_df", None)
hr_intraday = (
    hr_loader()
    if hr_loader is not None
    else pd.DataFrame(columns=["date", "timestamp", "value"])
)
prebed_discovery = analysis.compute_prebed_discovery(
    daily, acts, sleep_timing, body_battery=body_battery,
    stress_intraday=stress, hr_intraday=hr_intraday,
)
health_research = analysis.compute_health_research_panels(daily, acts, sleep_timing)
stress_leaks = analysis.compute_stress_leak_map(daily, stress)

METRIC_LABELS = {m["key"]: m["label"] for m in analysis.EXPERIMENT_METRICS}
METRIC_KEYS = [m["key"] for m in analysis.EXPERIMENT_METRICS]

st.markdown(
    """
    <style>
    .experiments-page-head{margin:4px 0 22px;}
    .experiments-page-title{font-family:var(--font-serif);font-size:34px;line-height:1.05;
      color:var(--text);font-weight:400;}
    .experiments-page-sub{margin-top:7px;color:var(--text-dim);font-size:14px;line-height:1.45;}
    </style>
    <div class="experiments-page-head">
      <div class="experiments-page-title">Lab</div>
      <div class="experiments-page-sub">Test interventions and inspect recovery correlations.</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def _rel_stats_line(rel):
    if not rel:
        return []
    bits = []
    corr = rel.get("correlation")
    spearman = rel.get("spearman")
    if corr is not None:
        bits.append(f"r {float(corr):+.2f}")
    if spearman is not None:
        bits.append(f"rho {float(spearman):+.2f}")
    if rel.get("corr_ci_low") is not None and rel.get("corr_ci_high") is not None:
        bits.append(f"95% CI {float(rel['corr_ci_low']):+.2f} to {float(rel['corr_ci_high']):+.2f}")
    if rel.get("p_adjusted") is not None:
        bits.append(f"FDR p {float(rel['p_adjusted']):.3f}")
    if rel.get("evidence"):
        bits.append(str(rel["evidence"]))
    sensitivity = rel.get("outlier_sensitivity")
    if sensitivity and sensitivity != "unknown":
        bits.append(str(sensitivity))
    return bits


def chart_card(title, unit, fig, rel=None):
    stats = _rel_stats_line(rel)
    rank = rel.get("rank") if rel else None
    evidence = str(rel.get("evidence") or "").title() if rel else ""
    fig.update_layout(height=220, margin=dict(t=10, b=28, l=46, r=12))
    with st.container(border=True):
        rank_html = (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'min-width:34px;height:22px;border-radius:5px;background:color-mix(in srgb,{cockpit.ACCENT} 14%,transparent);'
            f'border:1px solid color-mix(in srgb,{cockpit.ACCENT} 34%,transparent);'
            f'color:{cockpit.ACCENT};font-family:\'Geist Mono\',ui-monospace,monospace;'
            f'font-size:11px;font-weight:700">#{int(rank)}</span>'
            if rank is not None else ""
        )
        evidence_html = (
            f'<span style="display:inline-flex;align-items:center;height:22px;border-radius:999px;'
            f'padding:0 8px;border:1px solid {cockpit.GRID};color:{cockpit.TEXT_DIM};'
            f'font-family:\'Geist Mono\',ui-monospace,monospace;font-size:10px;'
            f'text-transform:uppercase;letter-spacing:.08em">{html.escape(evidence)}</span>'
            if evidence else ""
        )
        st.markdown(
            f'<div style="display:flex;align-items:flex-start;gap:9px;margin:0 0 7px;min-width:0">'
            f'{rank_html}<div style="min-width:0;flex:1">'
            f'<div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:4px">'
            f'{evidence_html}'
            f'<span style="font-family:\'Geist Mono\',ui-monospace,monospace;'
            f'font-size:10px;color:{cockpit.TEXT_FAINT};letter-spacing:.08em;text-transform:uppercase">'
            f'{html.escape(unit)}</span></div>'
            f'<div style="font-family:\'Geist\',system-ui,sans-serif;font-size:16px;'
            f'line-height:1.25;font-weight:700;color:{cockpit.TEXT};letter-spacing:0">'
            f'{html.escape(title)}</div></div></div>',
            unsafe_allow_html=True,
        )
        if stats:
            chips = "".join(
                f'<span style="display:inline-flex;align-items:center;border:1px solid {cockpit.GRID};'
                f'border-radius:5px;padding:3px 6px;color:{cockpit.TEXT_DIM};'
                f'font-family:\'Geist Mono\',ui-monospace,monospace;font-size:10px;line-height:1.1">'
                f'{html.escape(bit)}</span>'
                for bit in stats
            )
            st.markdown(
                f'<div style="display:flex;flex-wrap:wrap;gap:5px;margin:0 0 4px">{chips}</div>',
                unsafe_allow_html=True,
            )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})


# ── render functions ─────────────────────────────────────────────────────────

def render_health_lab():
    st.markdown(cockpit.section_label("Health Lab"), unsafe_allow_html=True)
    if daily.empty:
        st.info("Sync Garmin history to build the Health Lab panels.")
        return
    st.markdown(cockpit.health_research_card(health_research), unsafe_allow_html=True)
    health_rows = pd.DataFrame(health_research.get("rows") or [])
    if not health_rows.empty and "date" in health_rows:
        health_rows["date"] = pd.to_datetime(health_rows["date"], errors="coerce")
        health_view = health_rows.dropna(subset=["date"]).tail(30)
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


def render_stress_leak_map():
    st.markdown(cockpit.section_label("Stress leak map"), unsafe_allow_html=True)
    st.markdown(cockpit.stress_leak_card(stress_leaks), unsafe_allow_html=True)


def render_correlations():
    st.markdown(cockpit.section_label("Correlations"), unsafe_allow_html=True)
    with st.expander("Correlation summary", expanded=False):
        st.markdown(cockpit.discovery_card(prebed_discovery), unsafe_allow_html=True)
    rels = prebed_discovery.get("relationships", [])
    if not rels:
        st.caption("No paired correlation data yet.")
        return
    st.caption("Charts are sorted by evidence label, then FDR-adjusted p-value, absolute correlation strength, and paired-day count.")
    ranked_rels = [{**rel, "rank": idx} for idx, rel in enumerate(rels, start=1)]

    for i in range(0, len(ranked_rels), 2):
        cols = st.columns(2)
        for col, rel in zip(cols, ranked_rels[i:i + 2]):
            with col:
                chart_card(
                    rel.get("label") or f"{rel.get('x_label', 'Metric')} vs {rel.get('y_label', 'outcome')}",
                    rel.get("y_unit") or rel.get("y_label") or "",
                    cockpit.chart_prebed_relationship(prebed_discovery, rel.get("y_col"), rel.get("x_col")),
                    rel,
                )


def _render_experiment(exp_row, completed=False):
    exp = exp_row.to_dict()
    eid = int(exp["id"])
    result = analysis.compute_experiment_result(exp, daily, checkins)
    st.markdown(cockpit.experiment_result_card(result), unsafe_allow_html=True)
    cols = st.columns([1, 1, 1, 3])
    if not completed:
        with cols[0]:
            if st.button("Mark complete", key=f"done-{eid}", width="stretch"):
                db.set_experiment_status(eid, "complete")
                st.rerun()
    with cols[1]:
        if st.button("Interpret", key=f"interpbtn-{eid}", width="stretch"):
            with st.spinner("Reading the result…"):
                st.session_state[f"interptext-{eid}"] = ai.interpret_experiment(result)
    with cols[2]:
        if st.button("Delete", key=f"del-{eid}", width="stretch"):
            db.delete_experiment(eid)
            st.rerun()
    if st.session_state.get(f"interptext-{eid}"):
        st.markdown(st.session_state[f"interptext-{eid}"])
    if not completed:
        with st.expander("✎ Edit"):
            with st.form(f"edit-{eid}"):
                en = st.text_input("Name", value=exp.get("name") or "")
                eh = st.text_input("Hypothesis", value=exp.get("hypothesis") or "")
                em = st.multiselect(
                    "Metrics", METRIC_KEYS, format_func=lambda k: METRIC_LABELS[k],
                    default=[m for m in (exp.get("metrics") or []) if m in METRIC_LABELS])
                ec = st.columns(2)
                with ec[0]:
                    eb = st.number_input("Baseline days", min_value=3, max_value=90,
                                         value=int(exp.get("baseline_days") or 14))
                with ec[1]:
                    ee = st.text_input("End date (YYYY-MM-DD, blank=ongoing)",
                                       value=exp.get("end_date") or "")
                if st.form_submit_button("Save changes") and en.strip() and em:
                    db.update_experiment(eid, {
                        "name": en.strip(), "hypothesis": eh.strip() or None,
                        "metrics": em, "baseline_days": int(eb),
                        "end_date": ee.strip() or None,
                    })
                    st.rerun()


# ── page layout with tabs ────────────────────────────────────────────────────

lab_tab, stress_tab, corr_tab, exp_tab = st.tabs(
    ["Health Lab", "Stress", "Correlations", "Experiments"]
)

with lab_tab:
    render_health_lab()

with stress_tab:
    render_stress_leak_map()

with corr_tab:
    render_correlations()

with exp_tab:
    st.markdown(cockpit.section_label("Experiment lab"), unsafe_allow_html=True)

    # ── create ───────────────────────────────────────────────────────────────
    with st.expander("➕ New experiment", expanded=db.load_experiments_df().empty):
        with st.form("new_experiment", clear_on_submit=True):
            name = st.text_input("Name", placeholder="Magnesium before bed")
            hypothesis = st.text_input("Hypothesis (optional)",
                                       placeholder="expect higher HRV, better sleep")
            metric_keys = st.multiselect("Metrics to watch", METRIC_KEYS,
                                         format_func=lambda k: METRIC_LABELS[k],
                                         default=["hrv_overnight_avg", "sleep_hours"])
            c = st.columns(3)
            with c[0]:
                start_date = st.date_input("Intervention start", value=date.today())
            with c[1]:
                baseline_days = st.number_input("Baseline days", min_value=3,
                                                max_value=90, value=14)
            with c[2]:
                use_end = st.checkbox("Set end date")
                end_date = st.date_input("End", value=date.today()) if use_end else None
            if st.form_submit_button("Start experiment") and name.strip() and metric_keys:
                db.add_experiment({
                    "name": name.strip(), "hypothesis": hypothesis.strip() or None,
                    "metrics": metric_keys, "baseline_days": int(baseline_days),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat() if end_date else None,
                })
                st.rerun()

    active = db.load_experiments_df(status="active")
    if active.empty:
        st.caption("No active experiments. Create one above to start testing.")
    else:
        for _, row in active.iterrows():
            _render_experiment(row)

    completed = db.load_experiments_df(status="complete")
    if not completed.empty:
        st.markdown(cockpit.section_label("Completed"), unsafe_allow_html=True)
        for _, row in completed.iterrows():
            _render_experiment(row, completed=True)
