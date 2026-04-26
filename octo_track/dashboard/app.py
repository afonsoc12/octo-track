import streamlit as st

from octo_track.dashboard.pages.agile_rates import page_agile_rates
from octo_track.dashboard.pages.daily_overview import page_daily_overview
from octo_track.dashboard.pages.halfhourly import page_halfhourly

st.set_page_config(
    page_title="Octopus Energy",
    page_icon="🐙",
    layout="wide",
)

pg = st.navigation(
    [
        st.Page(page_daily_overview, title="Overview", icon="📊", default=True),
        st.Page(page_halfhourly, title="Half-hourly Detail", icon="⏱️"),
        st.Page(page_agile_rates, title="Agile Rates", icon="⚡"),
    ]
)
pg.run()
