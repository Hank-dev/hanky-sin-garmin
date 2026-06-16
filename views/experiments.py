"""Experiment lab — run N-of-1 before/after self-experiments and see whether a
habit or supplement actually moved your recovery metrics."""
import importlib
from datetime import date

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

METRIC_LABELS = {m["key"]: m["label"] for m in analysis.EXPERIMENT_METRICS}
METRIC_KEYS = [m["key"] for m in analysis.EXPERIMENT_METRICS]

st.markdown(cockpit.section_label("Experiment lab"), unsafe_allow_html=True)

# ── create ───────────────────────────────────────────────────────────────────
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


def _render(exp_row, completed=False):
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


active = db.load_experiments_df(status="active")
if active.empty:
    st.caption("No active experiments. Create one above to start testing.")
else:
    for _, row in active.iterrows():
        _render(row)

completed = db.load_experiments_df(status="complete")
if not completed.empty:
    st.markdown(cockpit.section_label("Completed"), unsafe_allow_html=True)
    for _, row in completed.iterrows():
        _render(row, completed=True)
