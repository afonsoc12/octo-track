from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from octo_track.dashboard.data import OCTOPUS_ORANGE, OFGEM_CAP_P_PER_KWH, fetch_rates, rate_band
from octo_track.dashboard.shared import check_env, load_tariff, meter_selector, refresh_button

LONDON_TZ = ZoneInfo("Europe/London")


def _fetch_day_df(agile_product, agile_tariff, d: date) -> pd.DataFrame:
    period_from = datetime(d.year, d.month, d.day, tzinfo=LONDON_TZ).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_to = (datetime(d.year, d.month, d.day, tzinfo=LONDON_TZ) + timedelta(days=1)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rates = fetch_rates(agile_product, agile_tariff, period_from, period_to)

    if rates:
        raw = pd.DataFrame(rates)
        raw["valid_from"] = pd.to_datetime(raw["valid_from"], utc=True)
        raw["valid_from_london"] = raw["valid_from"].dt.tz_convert(LONDON_TZ)
        df = raw[["valid_from_london", "value_inc_vat", "value_exc_vat"]].copy()
    else:
        df = pd.DataFrame(columns=["valid_from_london", "value_inc_vat", "value_exc_vat"])

    return df.sort_values("valid_from_london").reset_index(drop=True)


def _rate_colors(vals: pd.Series) -> list[str]:
    return ["lightgray" if pd.isna(v) else "#2196f3" if v < 0 else "#4caf50" if v < 15 else "#ff9800" if v < 25 else "#f44336" for v in vals]


def _date_label(d: date) -> str:
    today = datetime.now(LONDON_TZ).date()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%A, %d %b %Y")


def _day_tab(agile_product, agile_tariff):
    today = datetime.now(LONDON_TZ).date()
    tomorrow = today + timedelta(days=1)

    if "ar_date" not in st.session_state:
        st.session_state["ar_date"] = today

    col_prev, col_cal, col_next = st.columns([1, 8, 1], vertical_alignment="bottom")
    with col_prev:
        if st.button("◀", key="ar_prev", width="stretch"):
            if st.session_state["ar_date"] > date(2024, 10, 1):
                st.session_state["ar_date"] -= timedelta(days=1)
                st.rerun()
    with col_next:
        if st.button("▶", key="ar_next", width="stretch"):
            if st.session_state["ar_date"] <= tomorrow:
                st.session_state["ar_date"] += timedelta(days=1)
                st.rerun()
    with col_cal:
        st.markdown(
            f"<p style='text-align:center;font-size:1.1rem;font-weight:600;margin-bottom:0'>{_date_label(st.session_state['ar_date'])}</p>",
            unsafe_allow_html=True,
        )
        picked = st.date_input(
            "Date",
            value=st.session_state["ar_date"],
            min_value=date(2024, 10, 1),
            max_value=tomorrow,
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        if picked != st.session_state["ar_date"]:
            st.session_state["ar_date"] = picked
            st.rerun()

    selected = st.session_state["ar_date"]
    df = _fetch_day_df(agile_product, agile_tariff, selected)
    now_utc = datetime.now(UTC)
    is_today = selected == today
    is_future = selected > today

    published = df["value_inc_vat"].notna().sum()

    if published == 0:
        if is_future:
            st.info("Rates not published yet. Octopus publishes next-day rates at **~4pm UK time**.", icon="⏳")
        else:
            st.warning(f"No rates found for {selected.strftime('%d %b %Y')}.")
        return

    vals = df["value_inc_vat"]
    known = df.dropna(subset=["value_inc_vat"])

    # Current / next slot (today only)
    if is_today:
        now_ts = pd.Timestamp(now_utc).tz_convert(LONDON_TZ)
        past = df[df["valid_from_london"] <= now_ts].dropna(subset=["value_inc_vat"])
        future = df[df["valid_from_london"] > now_ts].dropna(subset=["value_inc_vat"])
        cur = past.iloc[-1] if not past.empty else None
        nxt = future.iloc[0] if not future.empty else None

        c1, c2, c3 = st.columns(3)
        if cur is not None:
            c1.metric(f"Current ({cur['valid_from_london'].strftime('%H:%M')})", f"{cur['value_inc_vat']:.2f} p/kWh")
        if nxt is not None:
            c2.metric(f"Next ({nxt['valid_from_london'].strftime('%H:%M')})", f"{nxt['value_inc_vat']:.2f} p/kWh")
            if cur is not None and cur["value_inc_vat"] != 0:
                pct = (nxt["value_inc_vat"] - cur["value_inc_vat"]) / cur["value_inc_vat"] * 100
                c3.metric("Current → next", f"{pct:+.1f}%", delta_color="inverse")
        st.divider()

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg rate", f"{known['value_inc_vat'].mean():.2f} p/kWh")
    min_row = known.loc[known["value_inc_vat"].idxmin()]
    max_row = known.loc[known["value_inc_vat"].idxmax()]
    m2.metric(
        "Cheapest",
        f"{min_row['value_inc_vat']:.2f} p/kWh",
        delta=f"↓ {min_row['valid_from_london'].strftime('%H:%M')}",
        delta_color="normal",
    )
    m3.metric(
        "Most expensive",
        f"{max_row['value_inc_vat']:.2f} p/kWh",
        delta=f"↑ {max_row['valid_from_london'].strftime('%H:%M')}",
        delta_color="inverse",
    )
    m4.metric("Slots published", f"{published} / 48")

    # Bar chart — full 48 slots, grey for unpublished
    y_known = known["value_inc_vat"]
    y_lo = min(y_known.min() - 2, -1)
    y_hi = y_known.max() + 3

    fig = go.Figure()
    if y_lo < 0:
        fig.add_hrect(y0=y_lo, y1=0, fillcolor="#2196f3", opacity=0.06, line_width=0)
    fig.add_hrect(y0=max(y_lo, 0), y1=min(15, y_hi), fillcolor="#4caf50", opacity=0.06, line_width=0)
    if y_hi > 15:
        fig.add_hrect(y0=max(y_lo, 15), y1=min(25, y_hi), fillcolor="#ff9800", opacity=0.06, line_width=0)
    if y_hi > 25:
        fig.add_hrect(y0=max(y_lo, 25), y1=y_hi, fillcolor="#f44336", opacity=0.06, line_width=0)
    fig.add_hline(
        y=OFGEM_CAP_P_PER_KWH,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Ofgem cap {OFGEM_CAP_P_PER_KWH}p",
        annotation_position="top right",
    )
    fig.add_trace(
        go.Bar(
            x=df["valid_from_london"],
            y=vals,
            marker_color=_rate_colors(vals),
            hovertemplate="%{x|%H:%M}<br>%{y:.2f} p/kWh<extra></extra>",
            customdata=df["value_inc_vat"].isna(),
        )
    )
    if is_today or is_future:
        fig.add_vline(x=int(now_utc.timestamp() * 1000), line_dash="dash", line_color="gray", annotation_text="Now")
    day_start = datetime(selected.year, selected.month, selected.day, tzinfo=LONDON_TZ)
    fig.update_layout(
        xaxis=dict(
            title="Time (London)",
            range=[day_start - timedelta(minutes=15), day_start + timedelta(hours=23, minutes=45)],
            tickformat="%H:%M",
            dtick=7200000,  # 2-hour ticks in ms
        ),
        yaxis=dict(title="p/kWh (inc. VAT)", range=[y_lo, y_hi]),
        showlegend=False,
        margin=dict(t=10),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("🔵 negative · 🟢 <15p · 🟡 15–25p · 🔴 >25p")

    tbl = known[["valid_from_london", "value_inc_vat", "value_exc_vat"]].copy()
    tbl["Time"] = tbl["valid_from_london"].dt.strftime("%H:%M")
    tbl["Band"] = tbl["value_inc_vat"].apply(rate_band)
    tbl["Rate (p/kWh inc. VAT)"] = tbl["value_inc_vat"].round(2)
    tbl["vs Ofgem cap"] = (tbl["value_inc_vat"] - OFGEM_CAP_P_PER_KWH).round(2).apply(lambda x: f"{x:+.2f}p")
    st.dataframe(tbl[["Band", "Time", "Rate (p/kWh inc. VAT)", "vs Ofgem cap"]], width="stretch", hide_index=True)


def _week_tab(agile_product, agile_tariff):
    today = datetime.now(LONDON_TZ).date()
    week_start = today - timedelta(days=today.weekday())

    if "ar_week" not in st.session_state:
        st.session_state["ar_week"] = week_start

    col_prev, col_lbl, col_next = st.columns([1, 8, 1], vertical_alignment="bottom")
    ws = st.session_state["ar_week"]
    we = ws + timedelta(days=6)
    with col_prev:
        if st.button("◀", key="ar_wprev", width="stretch"):
            st.session_state["ar_week"] -= timedelta(weeks=1)
            st.rerun()
    with col_next:
        if st.button("▶", key="ar_wnext", width="stretch"):
            if st.session_state["ar_week"] < week_start:
                st.session_state["ar_week"] += timedelta(weeks=1)
                st.rerun()
    with col_lbl:
        st.markdown(
            f"<p style='text-align:center;font-size:1.1rem;font-weight:600;margin-bottom:0'>{ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}</p>",
            unsafe_allow_html=True,
        )

    # Collect all 7 days of half-hourly slots
    frames = []
    for i in range(7):
        d = ws + timedelta(days=i)
        if d > today + timedelta(days=1):
            continue
        frames.append(_fetch_day_df(agile_product, agile_tariff, d))

    if not frames:
        st.info("No data for this week.")
        return

    all_df = pd.concat(frames, ignore_index=True).sort_values("valid_from_london")
    vals = all_df["value_inc_vat"]
    known = all_df.dropna(subset=["value_inc_vat"])

    y_lo = min(known["value_inc_vat"].min() - 2, -1) if not known.empty else -1
    y_hi = known["value_inc_vat"].max() + 3 if not known.empty else 30

    now_utc = datetime.now(UTC)
    fig = go.Figure()
    if y_lo < 0:
        fig.add_hrect(y0=y_lo, y1=0, fillcolor="#2196f3", opacity=0.06, line_width=0)
    fig.add_hrect(y0=max(y_lo, 0), y1=min(15, y_hi), fillcolor="#4caf50", opacity=0.06, line_width=0)
    if y_hi > 15:
        fig.add_hrect(y0=max(y_lo, 15), y1=min(25, y_hi), fillcolor="#ff9800", opacity=0.06, line_width=0)
    if y_hi > 25:
        fig.add_hrect(y0=max(y_lo, 25), y1=y_hi, fillcolor="#f44336", opacity=0.06, line_width=0)
    fig.add_hline(
        y=OFGEM_CAP_P_PER_KWH,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Ofgem cap {OFGEM_CAP_P_PER_KWH}p",
        annotation_position="top right",
    )
    # Day boundary vlines
    for i in range(8):
        boundary = datetime(ws.year, ws.month, ws.day, tzinfo=LONDON_TZ) + timedelta(days=i)
        fig.add_vline(x=int(boundary.timestamp() * 1000), line_color="rgba(0,0,0,0.15)", line_width=1)
    fig.add_trace(
        go.Bar(
            x=all_df["valid_from_london"],
            y=vals,
            marker_color=_rate_colors(vals),
            hovertemplate="%{x|%a %d %b %H:%M}<br>%{y:.2f} p/kWh<extra></extra>",
        )
    )
    fig.add_vline(x=int(now_utc.timestamp() * 1000), line_dash="dash", line_color="gray", annotation_text="Now")
    week_start_dt = datetime(ws.year, ws.month, ws.day, tzinfo=LONDON_TZ)
    week_end_dt = datetime(we.year, we.month, we.day, tzinfo=LONDON_TZ) + timedelta(hours=23, minutes=45)
    fig.update_layout(
        xaxis=dict(
            title="",
            range=[week_start_dt - timedelta(minutes=15), week_end_dt],
            tickformat="%a %d",
            dtick=86400000,  # 1-day ticks in ms
        ),
        yaxis=dict(title="p/kWh (inc. VAT)", range=[y_lo, y_hi]),
        showlegend=False,
        margin=dict(t=10),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("🔵 negative · 🟢 <15p · 🟡 15–25p · 🔴 >25p")


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _prev_month(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def _month_tab(agile_product, agile_tariff):
    today = datetime.now(LONDON_TZ).date()
    agile_epoch = date(2024, 10, 1)  # Agile data available from Oct 2024

    if "ar_month" not in st.session_state:
        st.session_state["ar_month"] = _month_start(today)

    col_prev, col_lbl, col_next = st.columns([1, 8, 1], vertical_alignment="bottom")
    month_start = st.session_state["ar_month"]
    month_end = _next_month(month_start)
    with col_prev:
        if st.button("◀", key="ar_mprev", width="stretch"):
            prev = _prev_month(st.session_state["ar_month"])
            if prev >= agile_epoch:
                st.session_state["ar_month"] = prev
                st.rerun()
    with col_next:
        if st.button("▶", key="ar_mnext", width="stretch"):
            nxt = _next_month(st.session_state["ar_month"])
            if nxt <= _month_start(today):
                st.session_state["ar_month"] = nxt
                st.rerun()
    with col_lbl:
        st.markdown(
            f"<p style='text-align:center;font-size:1.1rem;font-weight:600;margin-bottom:0'>{month_start.strftime('%B %Y')}</p>",
            unsafe_allow_html=True,
        )

    rows = []
    d = month_start
    while d < month_end and d <= today + timedelta(days=1):
        df = _fetch_day_df(agile_product, agile_tariff, d)
        known = df.dropna(subset=["value_inc_vat"])
        if not known.empty:
            rows.append(
                {
                    "date": d,
                    "avg": known["value_inc_vat"].mean(),
                    "min": known["value_inc_vat"].min(),
                    "max": known["value_inc_vat"].max(),
                    "slots": len(known),
                }
            )
        d += timedelta(days=1)

    if not rows:
        st.info("No rates data for this month.")
        return

    month_df = pd.DataFrame(rows)
    month_df["label"] = pd.to_datetime(month_df["date"]).dt.strftime("%d %b")

    fig = go.Figure()
    fig.add_hline(
        y=OFGEM_CAP_P_PER_KWH,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Ofgem cap {OFGEM_CAP_P_PER_KWH}p",
        annotation_position="top right",
    )
    fig.add_trace(
        go.Scatter(
            name="Avg rate",
            x=month_df["label"],
            y=month_df["avg"],
            mode="lines+markers",
            line=dict(color=OCTOPUS_ORANGE, width=2),
            marker=dict(size=4),
            hovertemplate="%{x}<br>avg %{y:.2f} p/kWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Min",
            x=month_df["label"],
            y=month_df["min"],
            mode="lines",
            line=dict(color="#4caf50", width=1, dash="dot"),
            hovertemplate="%{x}<br>min %{y:.2f} p/kWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Max",
            x=month_df["label"],
            y=month_df["max"],
            mode="lines",
            line=dict(color="#f44336", width=1, dash="dot"),
            hovertemplate="%{x}<br>max %{y:.2f} p/kWh<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="Day",
        yaxis_title="p/kWh (inc. VAT)",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10),
    )
    st.plotly_chart(fig, width="stretch")

    overall_avg = month_df["avg"].mean()
    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Monthly avg rate",
        f"{overall_avg:.2f} p/kWh",
        delta=f"{overall_avg - OFGEM_CAP_P_PER_KWH:+.2f}p vs Ofgem cap",
        delta_color="inverse",
    )
    m2.metric(
        "Lowest daily avg",
        f"{month_df['avg'].min():.2f} p/kWh",
        delta=pd.to_datetime(month_df.loc[month_df["avg"].idxmin(), "date"]).strftime("%d %b"),
        delta_color="off",
    )
    m3.metric(
        "Highest daily avg",
        f"{month_df['avg'].max():.2f} p/kWh",
        delta=pd.to_datetime(month_df.loc[month_df["avg"].idxmax(), "date"]).strftime("%d %b"),
        delta_color="off",
    )


def page_agile_rates():
    st.header("⚡ Agile Rates")
    check_env()
    refresh_button()
    mpan, _ = meter_selector()

    _, _, agile_tariff, agile_product = load_tariff(mpan)
    if not agile_tariff:
        st.error("Cannot resolve Agile tariff. Ensure account is accessible via API key.")
        st.stop()

    st.caption(f"Tariff: `{agile_tariff}`")

    tab_day, tab_week, tab_month = st.tabs(["Day", "Week", "Month"])
    with tab_day:
        _day_tab(agile_product, agile_tariff)
    with tab_week:
        _week_tab(agile_product, agile_tariff)
    with tab_month:
        _month_tab(agile_product, agile_tariff)
