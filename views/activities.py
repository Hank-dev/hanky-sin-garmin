"""Activities page."""
import importlib

import streamlit as st

import analysis
import cockpit
import db

analysis = importlib.reload(analysis)
db = importlib.reload(db)
cockpit = importlib.reload(cockpit)

db.init_db()

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

st.markdown(cockpit.section_label("Activities"), unsafe_allow_html=True)

st.markdown(cockpit.section_label("Grappling"), unsafe_allow_html=True)
st.markdown(cockpit.grappling_card(grappling), unsafe_allow_html=True)

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
