from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st

from octo_track.dashboard.data import (
    OCTOPUS_BLUE,
    OCTOPUS_ORANGE,
    fetch_actual_rate_index,
    fetch_standing_charge_for_date,
    ofgem_cap_at,
    ofgem_sc_at,
)
from octo_track.dashboard.shared import (
    add_cost_columns,
    check_env,
    load_consumption_df,
    load_tariff,
    meter_selector,
    refresh_button,
)

LONDON_TZ = ZoneInfo("Europe/London")


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _prev_month(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def page_daily_overview():
    st.header("📊 Overview")
    check_env()
    refresh_button()
    mpan, sn = meter_selector()

    today = datetime.now(LONDON_TZ).date()

    if "ov_month" not in st.session_state:
        st.session_state["ov_month"] = _month_start(today)

    col_prev, col_lbl, col_next = st.columns([1, 8, 1], vertical_alignment="center")
    with col_prev:
        if st.button("◀", key="ov_mprev", width="stretch"):
            st.session_state["ov_month"] = _prev_month(st.session_state["ov_month"])
            st.rerun()
    with col_next:
        if st.button("▶", key="ov_mnext", width="stretch"):
            nxt = _next_month(st.session_state["ov_month"])
            if nxt <= _month_start(today):
                st.session_state["ov_month"] = nxt
                st.rerun()

    month_start = st.session_state["ov_month"]
    month_end = _next_month(month_start)
    col_lbl.markdown(
        f"<p style='text-align:center;font-size:1.1rem;font-weight:600;margin:0'>{month_start.strftime('%B %Y')}</p>",
        unsafe_allow_html=True,
    )

    period_from = datetime(month_start.year, month_start.month, 1, tzinfo=LONDON_TZ).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_to = datetime(month_end.year, month_end.month, 1, tzinfo=LONDON_TZ).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    df = load_consumption_df(mpan, sn, period_from, period_to)
    current_tariff, current_product, agile_tariff, agile_product = load_tariff(mpan)

    with st.spinner("Fetching rates…"):
        current_timestamps, current_values = fetch_actual_rate_index(mpan, period_from, period_to)

    df = add_cost_columns(df, current_timestamps, current_values, [], [])

    # SVT cap for this month (unit rate + standing charge)
    svt_unit = ofgem_cap_at(month_start)
    svt_sc = ofgem_sc_at(month_start)
    df["svt_cost_p"] = df["consumption"] * svt_unit

    has_current = current_tariff is not None

    # ── daily aggregation ─────────────────────────────────────────────────────

    daily = (
        df.groupby("date")
        .agg(
            consumption=("consumption", "sum"),
            current_cost_p=("current_cost_p", "sum"),
            svt_cost_p=("svt_cost_p", "sum"),
        )
        .reset_index()
    )

    # Per-day standing charge based on which tariff was active that day
    with st.spinner("Fetching standing charges…"):
        daily["actual_sc_p"] = daily["date"].apply(lambda d: fetch_standing_charge_for_date(mpan, d) or 0.0)
    daily["svt_sc_p"] = svt_sc
    daily["actual_total_p"] = daily["current_cost_p"] + daily["actual_sc_p"]
    daily["svt_total_p"] = daily["svt_cost_p"] + daily["svt_sc_p"]

    has_rates = has_current and daily["current_cost_p"].notna().any()
    total_kwh = df["consumption"].sum()
    total_actual_p = daily["actual_total_p"].sum() if has_rates else None
    total_svt_p = daily["svt_total_p"].sum()

    # ── top metrics ───────────────────────────────────────────────────────────

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{month_start.strftime('%B')} consumption", f"{total_kwh:.2f} kWh")
    if has_rates and total_actual_p is not None:
        m2.metric("Cost — actual tariff", f"£{total_actual_p / 100:.2f}", help="Energy + standing charge")
    m3.metric(
        f"Cost — SVT cap ({svt_unit}p + {svt_sc:.0f}p/day SC)",
        f"£{total_svt_p / 100:.2f}",
        help="Ofgem price cap unit rate × consumption + standing charge cap",
    )
    if has_rates and total_actual_p is not None:
        savings_p = total_svt_p - total_actual_p
        m4.metric(
            "vs SVT cap",
            f"£{savings_p / 100:+.2f}",
            delta=f"{'saving' if savings_p > 0 else 'extra'} £{abs(savings_p) / 100:.2f}",
            delta_color="normal" if savings_p > 0 else "inverse",
        )

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Daily consumption (kWh)")
        fig = go.Figure(
            go.Bar(
                x=daily["date"],
                y=daily["consumption"].round(3),
                marker_color=OCTOPUS_ORANGE,
                hovertemplate="%{x}<br>%{y:.3f} kWh<extra></extra>",
            )
        )
        fig.update_layout(xaxis_title="Date", yaxis_title="kWh", margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")

    with col_r:
        st.subheader("Daily cost (£)")
        fig2 = go.Figure()
        if has_rates:
            fig2.add_trace(
                go.Bar(
                    name="Standing charge",
                    x=daily["date"],
                    y=(daily["actual_sc_p"] / 100).round(4),
                    marker_color=OCTOPUS_BLUE,
                    hovertemplate="%{x}<br>£%{y:.4f} standing charge<extra></extra>",
                )
            )
            fig2.add_trace(
                go.Bar(
                    name="Energy",
                    x=daily["date"],
                    y=(daily["current_cost_p"] / 100).round(4),
                    marker_color=OCTOPUS_ORANGE,
                    hovertemplate="%{x}<br>£%{y:.4f} energy<extra></extra>",
                )
            )
        else:
            st.info("Auto-detected tariff required for cost data.")
        fig2.update_layout(
            barmode="stack",
            xaxis_title="Date",
            yaxis_title="£",
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=10),
        )
        st.plotly_chart(fig2, width="stretch")

    # ── daily cost table ──────────────────────────────────────────────────────

    st.subheader("Daily cost table")
    disp = daily.copy()
    disp["Date"] = disp["date"]
    disp["Consumption (kWh)"] = disp["consumption"].round(3)
    disp["Avg rate (p/kWh)"] = (disp["current_cost_p"] / disp["consumption"].replace(0, float("nan"))).round(2) if has_rates else None
    disp["Energy cost (£)"] = (disp["current_cost_p"] / 100).round(4) if has_rates else None
    disp["Standing charge (£)"] = (disp["actual_sc_p"] / 100).round(4) if has_rates else None
    disp["Total (£)"] = (disp["actual_total_p"] / 100).round(4) if has_rates else None
    disp["SVT total (£)"] = (disp["svt_total_p"] / 100).round(4)
    disp["vs SVT (£)"] = ((disp["svt_total_p"] - disp["actual_total_p"]) / 100).round(4) if has_rates else None

    cols = ["Date", "Consumption (kWh)"]
    if has_rates:
        cols += [
            "Avg rate (p/kWh)",
            "Energy cost (£)",
            "Standing charge (£)",
            "Total (£)",
            "SVT total (£)",
            "vs SVT (£)",
        ]
    else:
        cols += ["SVT total (£)"]

    st.dataframe(disp[cols], width="stretch", hide_index=True)
