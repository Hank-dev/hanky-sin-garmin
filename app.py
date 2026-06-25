"""Streamlit entry point / router for the Hankø Fitness Hub.

Thin router only: sets page config, injects the shared cockpit (Material Dark Teal) CSS and
the sidebar brand mark, then hands off to the selected page via ``st.navigation``.
Each page body lives in ``views/`` (cockpit, sleep, activities, strength, coach, experiments). Because
``nav.run()`` executes the chosen view inline within this same script run, the CSS
injected here applies to whichever page renders.

Run with:  streamlit run app.py
"""
import importlib

import streamlit as st

import cockpit

cockpit = importlib.reload(cockpit)

st.set_page_config(page_title="Hankø Fitness Hub", page_icon="🏃", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)

# Brand lockup pinned at the top of the sidebar (st.logo's slot sits above the
# nav). It also renders in the app header; cockpit.CSS hides that duplicate so the
# mark only shows in the sidebar.
_BRAND = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 40" fill="none">'
    '<path d="M20 6L33 28H7L20 6Z" fill="#ededed"/>'
    '<text x="44" y="19" font-family="Geist,system-ui,Helvetica,Arial,sans-serif" '
    'font-size="16" font-weight="700" letter-spacing="0.4" fill="#ededed">HANKØ</text>'
    '<text x="45" y="32" font-family="\'Geist Mono\',ui-monospace,monospace" '
    'font-size="6.5" font-weight="500" letter-spacing="2.4" fill="#8f8f8f">FITNESS HUB</text>'
    '</svg>'
)
st.logo(_BRAND, size="large")

pages = [
    st.Page("views/cockpit.py", title="Cockpit", icon=":material/monitor_heart:", default=True),
    st.Page("views/sleep.py", title="Sleep", icon=":material/bedtime:"),
    st.Page("views/activities.py", title="Activities", icon=":material/directions_run:"),
    st.Page("views/strength.py", title="Strength", icon=":material/exercise:"),
    st.Page("views/coach.py", title="Coach", icon=":material/psychology:"),
    st.Page("views/experiments.py", title="Lab", icon=":material/science:"),
]
st.navigation(pages).run()
