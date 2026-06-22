"""Activities page."""
import importlib
from datetime import date

import streamlit as st

import analysis
import cockpit
import db

analysis = importlib.reload(analysis)
db = importlib.reload(db)
cockpit = importlib.reload(cockpit)

db.init_db()

ACTIVITY_TYPES = [
    ("running", "Running"),
    ("cycling", "Cycling"),
    ("walking", "Walking"),
    ("strength_training", "Strength"),
    ("cardio", "Cardio"),
    ("bjj", "BJJ / grappling"),
    ("swimming", "Swimming"),
    ("hiking", "Hiking"),
    ("yoga", "Mobility / yoga"),
    ("other", "Other"),
]
ACTIVITY_TYPE_LABELS = dict(ACTIVITY_TYPES)


def _optional_number(value):
    return None if value is None or float(value) <= 0 else float(value)


def _manual_activity_record(
    activity_date,
    name,
    activity_type,
    duration_hours,
    duration_minutes,
    distance_km,
    avg_hr,
    max_hr,
    training_load,
    aerobic_te,
    anaerobic_te,
):
    duration_s = int(duration_hours) * 3600 + int(duration_minutes) * 60
    return {
        "date": activity_date.isoformat(),
        "name": name.strip() or None,
        "type": activity_type,
        "duration_s": float(duration_s),
        "distance_m": None if float(distance_km) <= 0 else float(distance_km) * 1000,
        "avg_hr": _optional_number(avg_hr),
        "max_hr": _optional_number(max_hr),
        "training_load": _optional_number(training_load),
        "aerobic_te": _optional_number(aerobic_te),
        "anaerobic_te": _optional_number(anaerobic_te),
    }


daily = analysis.enrich_daily(db.load_daily_df())
acts = db.load_activities_df()
activity_details = db.load_activity_raw_payloads("activity_details")
activity_zones = db.load_activity_raw_payloads("activity_hr_zones")
grappling = analysis.compute_grappling_sessions(
    daily,
    acts,
    activity_details,
    activity_zones,
)

st.markdown(
    """
    <style>
    .activities-page-head{margin:4px 0 22px;}
    .activities-page-title{font-family:var(--font-serif);font-size:34px;line-height:1.05;
      color:var(--text);font-weight:400;}
    .activities-page-sub{margin-top:7px;color:var(--text-dim);font-size:14px;line-height:1.45;}
    </style>
    <div class="activities-page-head">
      <div class="activities-page-title">Activities</div>
      <div class="activities-page-sub">Garmin sessions and manual training logs in one timeline.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.pop("manual_activity_added", False):
    st.success("Activity added.")

st.markdown(cockpit.section_label("Grappling"), unsafe_allow_html=True)
st.markdown(cockpit.grappling_card(grappling), unsafe_allow_html=True)

st.markdown(cockpit.section_label("Add activity"), unsafe_allow_html=True)
with st.expander("Manual activity", expanded=acts is None or acts.empty):
    with st.form("manual_activity", clear_on_submit=True):
        top = st.columns([1, 1, 1.4])
        with top[0]:
            activity_date = st.date_input("Date", value=date.today())
        with top[1]:
            selected_type = st.selectbox(
                "Type",
                [key for key, _label in ACTIVITY_TYPES],
                format_func=lambda key: ACTIVITY_TYPE_LABELS[key],
            )
        with top[2]:
            name = st.text_input("Name", placeholder="Easy run, open mat, lift")

        custom_type = ""
        if selected_type == "other":
            custom_type = st.text_input("Custom type", placeholder="Rowing")

        duration_cols = st.columns([1, 1, 1])
        with duration_cols[0]:
            duration_hours = st.number_input("Hours", min_value=0, max_value=24, value=0, step=1)
        with duration_cols[1]:
            duration_minutes = st.number_input("Minutes", min_value=0, max_value=59, value=45, step=5)
        with duration_cols[2]:
            distance_km = st.number_input("Distance km", min_value=0.0, value=0.0, step=0.1, format="%.1f")

        metric_cols = st.columns(3)
        with metric_cols[0]:
            avg_hr = st.number_input("Avg HR", min_value=0, max_value=260, value=0, step=1)
        with metric_cols[1]:
            max_hr = st.number_input("Max HR", min_value=0, max_value=260, value=0, step=1)
        with metric_cols[2]:
            training_load = st.number_input("Load", min_value=0.0, value=0.0, step=1.0, format="%.0f")

        effect_cols = st.columns(2)
        with effect_cols[0]:
            aerobic_te = st.number_input("Aerobic TE", min_value=0.0, max_value=5.0, value=0.0, step=0.1, format="%.1f")
        with effect_cols[1]:
            anaerobic_te = st.number_input("Anaerobic TE", min_value=0.0, max_value=5.0, value=0.0, step=0.1, format="%.1f")

        submitted = st.form_submit_button("Add activity", icon=":material/add:", width="stretch")
        if submitted:
            activity_type = custom_type.strip().lower().replace(" ", "_") if selected_type == "other" else selected_type
            duration_s = int(duration_hours) * 3600 + int(duration_minutes) * 60
            if not activity_type:
                st.error("Choose an activity type.")
            elif duration_s <= 0:
                st.error("Duration must be greater than zero.")
            elif avg_hr and max_hr and avg_hr > max_hr:
                st.error("Avg HR cannot be higher than max HR.")
            else:
                db.add_manual_activity(
                    _manual_activity_record(
                        activity_date,
                        name,
                        activity_type,
                        duration_hours,
                        duration_minutes,
                        distance_km,
                        avg_hr,
                        max_hr,
                        training_load,
                        aerobic_te,
                        anaerobic_te,
                    )
                )
                st.session_state["manual_activity_added"] = True
                st.rerun()

st.markdown(cockpit.section_label("Activity log"), unsafe_allow_html=True)

row_limit = 12
if acts is not None and not acts.empty:
    row_limit = (
        st.segmented_control(
            "Rows",
            [12, 25, 50],
            default=25,
            key="activities_rows",
            format_func=lambda n: f"{n}",
        )
        or 25
    )

st.markdown(
    cockpit.activities_table(acts, sparse=acts is None or acts.empty, limit=row_limit),
    unsafe_allow_html=True,
)
