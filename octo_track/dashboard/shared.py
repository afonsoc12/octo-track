"""Shared UI components used across dashboard pages."""

from __future__ import annotations

import importlib.metadata
import os

import pandas as pd
import streamlit as st

from .data import (
    fetch_account_data,
    fetch_consumption,
    fetch_tariff_info,
    lookup_rate,
)


def check_env() -> None:
    if not os.getenv("OCTOPUS_API_KEY"):
        st.error("Set `OCTOPUS_API_KEY` — everything else is auto-discovered.")
        st.stop()


def refresh_button() -> None:
    from octo_track.dashboard.cache import CACHE_DIR

    _, col = st.columns([9, 1])
    if col.button("↺ Refresh", width="stretch"):
        # Clear in-process cache
        st.cache_data.clear()
        # Delete all parquet files so next render re-fetches from API
        if CACHE_DIR.exists():
            for f in CACHE_DIR.glob("*.parquet"):
                f.unlink(missing_ok=True)
        st.rerun()


def meter_selector() -> tuple[str, str]:
    """Sidebar MPAN/meter dropdown. Returns (mpan, meter_sn)."""
    with st.sidebar:
        st.markdown("### Meter")
        try:
            account_info = fetch_account_data()
            meter_points = account_info["meter_points"]
            acct = account_info["account_number"]
        except Exception as e:
            st.error(f"Could not load account: {e}")
            st.stop()

        labels = [mp["label"] for mp in meter_points]
        if "selected_meter_idx" not in st.session_state:
            st.session_state["selected_meter_idx"] = 0

        chosen_label = st.selectbox(
            "MPAN / Meter SN",
            labels,
            index=st.session_state["selected_meter_idx"],
            key="meter_selector_widget",
        )
        idx = labels.index(chosen_label)
        st.session_state["selected_meter_idx"] = idx
        mp = meter_points[idx]

        st.caption(f"Account: `{acct}`")
        if mp.get("address"):
            st.caption(f"Address: {mp['address']}")

        from zoneinfo import ZoneInfo

        from .data import parse_dt

        LONDON_TZ = ZoneInfo("Europe/London")
        agile_start = next(
            (ag["valid_from"] for ag in sorted(mp["agreements"], key=lambda a: a["valid_from"]) if "AGILE" in ag.get("tariff_code", "")),
            None,
        )
        if agile_start:
            agile_dt = parse_dt(agile_start).astimezone(LONDON_TZ)
            st.caption(f"On Agile since: {agile_dt.strftime('%d %b %Y')}")

        st.sidebar.markdown("---")
        version = importlib.metadata.version("octo-track")
        st.caption("Mode: ☁️ Stateless (API)", help="Data fetched from the Octopus API in real time and cached locally. No database required.")
        st.caption(f"[octo-track](https://github.com/afonsoc12/octo-track)@[v{version}](https://github.com/afonsoc12/octo-track/releases/tag/v{version})")
        st.caption("Made with 🤖 by [Afonso Costa](https://github.com/afonsoc12)")

    return mp["mpan"], mp["meter_sn"]


def load_consumption_df(mpan: str, sn: str, period_from: str, period_to: str) -> pd.DataFrame:
    with st.spinner("Fetching consumption…"):
        records = fetch_consumption(mpan, sn, period_from, period_to)
    if not records:
        st.warning("No consumption data found for this period.")
        st.stop()
    df = pd.DataFrame(records)
    df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
    df["interval_end"] = pd.to_datetime(df["interval_end"], utc=True)
    df["interval_start_london"] = df["interval_start"].dt.tz_convert("Europe/London")
    df["date"] = df["interval_start_london"].dt.date
    return df


def load_tariff(mpan: str):
    with st.spinner("Resolving tariff info…"):
        return fetch_tariff_info(mpan)


def add_cost_columns(
    df: pd.DataFrame,
    current_timestamps: list,
    current_values: list,
    agile_timestamps: list,
    agile_values: list,
) -> pd.DataFrame:
    df["current_rate_p"] = df["interval_start"].apply(lambda t: lookup_rate(current_timestamps, current_values, t.to_pydatetime()))
    df["agile_rate_p"] = df["interval_start"].apply(lambda t: lookup_rate(agile_timestamps, agile_values, t.to_pydatetime()))
    df["current_rate_p"] = pd.to_numeric(df["current_rate_p"], errors="coerce")
    df["agile_rate_p"] = pd.to_numeric(df["agile_rate_p"], errors="coerce")
    df["current_cost_p"] = df["consumption"] * df["current_rate_p"]
    df["agile_cost_p"] = df["consumption"] * df["agile_rate_p"]
    return df
