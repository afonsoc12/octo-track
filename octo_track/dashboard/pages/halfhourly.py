from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo as _ZoneInfo

import plotly.graph_objects as go
import streamlit as st

from octo_track.dashboard.data import (
    OCTOPUS_BLUE,
    OCTOPUS_ORANGE,
    OFGEM_CAP_P_PER_KWH,
    build_rate_index,
    fetch_actual_rate_index,
    fetch_rates,
    fetch_standing_charge,
)
from octo_track.dashboard.shared import (
    add_cost_columns,
    check_env,
    load_consumption_df,
    load_tariff,
    meter_selector,
    refresh_button,
)

_LONDON = _ZoneInfo("Europe/London")


def page_halfhourly():
    st.header("⏱️ Half-hourly Detail")
    check_env()
    refresh_button()
    mpan, sn = meter_selector()

    _today = datetime.now(_LONDON).date()
    # Fetch rolling 6 months of data
    _period_start_dt = (_today.replace(day=1) - timedelta(days=150)).replace(day=1)
    _period_end_dt = _today + timedelta(days=2)
    _period_from = datetime(_period_start_dt.year, _period_start_dt.month, 1, tzinfo=_LONDON).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _period_to = datetime(_period_end_dt.year, _period_end_dt.month, _period_end_dt.day, tzinfo=_LONDON).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    df = load_consumption_df(mpan, sn, _period_from, _period_to)
    current_tariff, current_product, agile_tariff, agile_product = load_tariff(mpan)
    has_current = current_tariff is not None
    has_agile = agile_tariff is not None

    with st.spinner("Fetching rates…"):
        current_timestamps, current_values = fetch_actual_rate_index(mpan, _period_from, _period_to)

    agile_timestamps, agile_values = [], []
    if has_agile:
        with st.spinner("Fetching Agile rates…"):
            agile_timestamps, agile_values = build_rate_index(fetch_rates(agile_product, agile_tariff, _period_from, _period_to))

    df = add_cost_columns(df, current_timestamps, current_values, agile_timestamps, agile_values)

    standing_p_per_day: float | None = None
    if has_agile:
        with st.spinner("Fetching standing charge…"):
            standing_p_per_day = fetch_standing_charge(agile_product, agile_tariff)

    # ── date selector ─────────────────────────────────────────────────────────

    today = _today

    def _date_label(d) -> str:
        if d == today:
            return "Today"
        if d == today - timedelta(days=1):
            return "Yesterday"
        if d == today + timedelta(days=1):
            return "Tomorrow"
        return d.strftime("%A, %d %b %Y")

    date_options = sorted(df["date"].unique())
    min_date, max_date = date_options[0], date_options[-1]

    # Default to most recent day with enough slots
    if "hh_date" not in st.session_state or st.session_state["hh_date"] not in date_options:
        for d in reversed(date_options):
            if len(df[df["date"] == d]) >= 10:
                st.session_state["hh_date"] = d
                break

    col_prev, col_cal, col_next = st.columns([1, 8, 1], vertical_alignment="center")
    with col_prev:
        if st.button("◀", key="hh_prev", width="stretch", help="Previous day"):
            idx = date_options.index(st.session_state["hh_date"])
            if idx > 0:
                st.session_state["hh_date"] = date_options[idx - 1]
                st.rerun()
    with col_next:
        if st.button("▶", key="hh_next", width="stretch", help="Next day"):
            idx = date_options.index(st.session_state["hh_date"])
            if idx < len(date_options) - 1:
                st.session_state["hh_date"] = date_options[idx + 1]
                st.rerun()
    with col_cal:
        st.markdown(
            f"<p style='text-align:center;font-size:1.1rem;font-weight:600;margin-bottom:0'>{_date_label(st.session_state['hh_date'])}</p>",
            unsafe_allow_html=True,
        )
        picked = st.date_input(
            "Date",
            value=st.session_state["hh_date"],
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        if picked != st.session_state["hh_date"]:
            st.session_state["hh_date"] = picked
            st.rerun()

    selected_date = st.session_state["hh_date"]
    day_df = df[df["date"] == selected_date].sort_values("interval_start_london")

    # Default to most recent day with enough slots (only on initial load)
    if len(day_df) < 10 and "hh_defaulted" not in st.session_state:
        idx = date_options.index(selected_date)
        for d in reversed(date_options[:idx]):
            candidate = df[df["date"] == d]
            if len(candidate) >= 10:
                st.session_state["hh_date"] = d
                st.session_state["hh_defaulted"] = True
                st.rerun()

    if len(day_df) < 10:
        st.info("Data for this day has not been published yet by Octopus. Showing partial data.", icon="⏳")

    prev_week_date = selected_date - timedelta(days=7)
    prev_df = df[df["date"] == prev_week_date].sort_values("interval_start_london")
    has_prev_week = not prev_df.empty

    day_kwh = day_df["consumption"].sum()
    day_agile_energy_p = day_df["agile_cost_p"].sum() if has_agile else None
    day_agile_total_p = (day_agile_energy_p + standing_p_per_day) if (day_agile_energy_p is not None and standing_p_per_day) else day_agile_energy_p
    day_current_energy_p = day_df["current_cost_p"].sum() if has_current else None
    day_current_total_p = (day_current_energy_p + standing_p_per_day) if (day_current_energy_p is not None and standing_p_per_day) else day_current_energy_p

    # ── metrics ───────────────────────────────────────────────────────────────

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Consumption", f"{day_kwh:.3f} kWh")
    if has_agile and day_agile_total_p is not None:
        prev_agile_total = (prev_df["agile_cost_p"].sum() + (standing_p_per_day or 0)) if has_prev_week else None
        delta_str = f"WoW {(day_agile_total_p - prev_agile_total) / 100:+.2f} £" if prev_agile_total is not None else None
        m3.metric("Agile total (inc. standing)", f"£{day_agile_total_p / 100:.2f}", delta=delta_str, delta_color="inverse")
    if has_current and day_current_total_p is not None:
        prev_curr_total = (prev_df["current_cost_p"].sum() + (standing_p_per_day or 0)) if has_prev_week else None
        delta_str = f"WoW {(day_current_total_p - prev_curr_total) / 100:+.2f} £" if prev_curr_total is not None else None
        m2.metric("Current tariff total", f"£{day_current_total_p / 100:.2f}", delta=delta_str, delta_color="inverse")
    if standing_p_per_day is not None:
        m4.metric("Standing charge", f"{standing_p_per_day:.2f} p/day")

    st.divider()

    # ── rate stats ────────────────────────────────────────────────────────────

    if has_agile and day_df["agile_rate_p"].notna().any():
        st.subheader("Rate stats — Agile")
        rated = day_df.dropna(subset=["agile_rate_p"])
        total_cons = rated["consumption"].sum()
        avg_rate_weighted = (rated["consumption"] * rated["agile_rate_p"]).sum() / total_cons if total_cons > 0 else float("nan")
        min_row = rated.loc[rated["agile_rate_p"].idxmin()]
        max_row = rated.loc[rated["agile_rate_p"].idxmax()]

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Avg rate paid (weighted)", f"{avg_rate_weighted:.2f} p/kWh")
        r2.metric(
            "Min rate",
            f"{min_row['agile_rate_p']:.2f} p/kWh",
            delta=min_row["interval_start_london"].strftime("%H:%M"),
            delta_color="off",
        )
        r3.metric(
            "Max rate",
            f"{max_row['agile_rate_p']:.2f} p/kWh",
            delta=max_row["interval_start_london"].strftime("%H:%M"),
            delta_color="off",
        )
        r4.metric("Rate spread", f"{max_row['agile_rate_p'] - min_row['agile_rate_p']:.2f} p/kWh")

    # ── main chart ────────────────────────────────────────────────────────────

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Consumption (kWh)",
            x=day_df["interval_start_london"],
            y=day_df["consumption"],
            marker_color=OCTOPUS_ORANGE,
            opacity=0.75,
            hovertemplate="%{x|%H:%M}<br>%{y:.3f} kWh<extra></extra>",
        )
    )
    if has_agile and day_df["agile_rate_p"].notna().any():
        fig.add_trace(
            go.Scatter(
                name="Agile rate (p/kWh)",
                x=day_df["interval_start_london"],
                y=day_df["agile_rate_p"],
                yaxis="y2",
                line=dict(color="#e63946", width=2),
                mode="lines+markers",
                marker=dict(size=4),
                hovertemplate="%{x|%H:%M}<br>%{y:.2f} p/kWh<extra>Agile</extra>",
            )
        )
    if has_current and day_df["current_rate_p"].notna().any():
        fig.add_trace(
            go.Scatter(
                name="Current rate (p/kWh)",
                x=day_df["interval_start_london"],
                y=day_df["current_rate_p"],
                yaxis="y2",
                line=dict(color=OCTOPUS_BLUE, width=2, dash="dot"),
                mode="lines",
                hovertemplate="%{x|%H:%M}<br>%{y:.2f} p/kWh<extra>Current</extra>",
            )
        )
    fig.add_hline(
        y=OFGEM_CAP_P_PER_KWH,
        yref="y2",
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Ofgem cap {OFGEM_CAP_P_PER_KWH}p",
        annotation_position="top right",
    )
    _day_start = datetime(selected_date.year, selected_date.month, selected_date.day, tzinfo=_LONDON)
    fig.update_layout(
        xaxis=dict(
            title="Time (London)",
            range=[_day_start - timedelta(minutes=15), _day_start + timedelta(hours=23, minutes=45)],
            tickformat="%H:%M",
            dtick=7200000,
        ),
        yaxis=dict(title="kWh"),
        yaxis2=dict(title="p/kWh", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.12),
        margin=dict(t=30),
    )
    st.plotly_chart(fig, width="stretch")

    # ── usage vs rate scatter ─────────────────────────────────────────────────

    st.subheader("Usage vs rate — cost efficiency")
    active_rates = day_df["current_rate_p"].dropna()
    is_agile_day = active_rates.nunique() > 1  # fixed tariff = single rate all day
    if not is_agile_day:
        st.info("This day used a fixed tariff — scatter only available for Agile days.", icon="ℹ️")
    else:
        rated = day_df.dropna(subset=["current_rate_p", "consumption"])
        rated = rated[rated["consumption"] > 0]
        if rated.empty:
            st.info("No consumption data with rate for this day.")
        else:
            scatter_colors = ["#2196f3" if r < 0 else "#4caf50" if r < 15 else "#ff9800" if r < 25 else "#f44336" for r in rated["current_rate_p"]]
            scatter_fig = go.Figure(
                go.Scatter(
                    x=rated["current_rate_p"],
                    y=rated["current_cost_p"] / 100,
                    mode="markers+text",
                    marker=dict(
                        size=(rated["consumption"] / rated["consumption"].max() * 30 + 6).clip(6, 36),
                        color=scatter_colors,
                        opacity=0.8,
                        line=dict(width=1, color="white"),
                    ),
                    text=rated["interval_start_london"].dt.strftime("%H:%M"),
                    textposition="top center",
                    textfont=dict(size=9),
                    hovertemplate=("%{text}<br>Rate: %{x:.2f} p/kWh<br>Cost: £%{y:.4f}<br>Usage: %{customdata:.3f} kWh<extra></extra>"),
                    customdata=rated["consumption"],
                )
            )
            scatter_fig.add_vline(
                x=OFGEM_CAP_P_PER_KWH,
                line_dash="dot",
                line_color="gray",
                annotation_text=f"Ofgem cap {OFGEM_CAP_P_PER_KWH}p",
                annotation_position="top right",
            )
            scatter_fig.update_layout(
                xaxis_title="Rate (p/kWh)",
                yaxis_title="Cost (£)",
                margin=dict(t=10),
            )
            st.plotly_chart(scatter_fig, width="stretch")
            st.caption("Bubble size = usage (kWh). Large bubble at low rate = efficient. Large bubble at high rate = costly slot.")
