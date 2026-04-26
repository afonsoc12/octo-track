"""Cached data fetching and pure helpers for the dashboard (stateless / API-only)."""

from __future__ import annotations

import bisect
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octo_track.dashboard.cache import cache_key, load_or_fetch
from octo_track.octopus import Octopus

LONDON_TZ = ZoneInfo("Europe/London")
OCTOPUS_ORANGE = "#f58b00"
OCTOPUS_BLUE = "#4c78a8"

OFGEM_CAP_HISTORY: list[tuple[date, float]] = [
    (date(2024, 1, 1), 28.62),
    (date(2024, 4, 1), 24.50),
    (date(2024, 7, 1), 22.36),
    (date(2024, 10, 1), 24.50),
    (date(2025, 1, 1), 24.50),
    (date(2025, 4, 1), 23.73),
    (date(2025, 7, 1), 22.36),
    (date(2025, 10, 1), 21.47),
    (date(2026, 1, 1), 21.90),
    (date(2026, 4, 1), 24.94),
]


def ofgem_cap_at(d: date) -> float:
    cap = OFGEM_CAP_HISTORY[0][1]
    for cap_date, cap_val in OFGEM_CAP_HISTORY:
        if d >= cap_date:
            cap = cap_val
    return cap


OFGEM_CAP_P_PER_KWH = ofgem_cap_at(datetime.now(LONDON_TZ).date())

# Ofgem SVT standing charge cap (p/day inc. VAT) — typical domestic, England/Wales
OFGEM_SC_HISTORY: list[tuple[date, float]] = [
    (date(2024, 1, 1), 53.37),
    (date(2024, 4, 1), 61.64),
    (date(2024, 7, 1), 61.64),
    (date(2024, 10, 1), 61.64),
    (date(2025, 1, 1), 61.64),
    (date(2025, 4, 1), 53.22),
    (date(2025, 7, 1), 51.37),
    (date(2025, 10, 1), 51.37),
    (date(2026, 1, 1), 51.47),
    (date(2026, 4, 1), 61.64),
]


def ofgem_sc_at(d: date) -> float:
    sc = OFGEM_SC_HISTORY[0][1]
    for cap_date, cap_val in OFGEM_SC_HISTORY:
        if d >= cap_date:
            sc = cap_val
    return sc


OFGEM_SC_P_PER_DAY = ofgem_sc_at(datetime.now(LONDON_TZ).date())


# ── pure helpers ──────────────────────────────────────────────────────────────


def product_code_from_tariff(tariff_code: str) -> str:
    parts = tariff_code.split("-")
    if len(parts) < 5:
        raise ValueError(f"Unexpected tariff code format: {tariff_code}")
    return "-".join(parts[2:-1])


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def tariff_at(agreements: list[dict], at: datetime) -> str | None:
    for ag in sorted(agreements, key=lambda a: a["valid_from"], reverse=True):
        vf = parse_dt(ag["valid_from"])
        vt = parse_dt(ag["valid_to"]) if ag.get("valid_to") else None
        if vf <= at and (vt is None or at < vt):
            return ag["tariff_code"]
    return None


def build_rate_index(rates: list[dict]) -> tuple[list[datetime], list[float]]:
    items = sorted(
        (
            (parse_dt(r["valid_from"]) if isinstance(r["valid_from"], str) else r["valid_from"]),
            float(r["value_inc_vat"]),
        )
        for r in rates
    )
    return [i[0] for i in items], [i[1] for i in items]


def lookup_rate(timestamps: list[datetime], values: list[float], at: datetime) -> float | None:
    if not timestamps:
        return None
    idx = bisect.bisect_right(timestamps, at) - 1
    return values[idx] if idx >= 0 else None


def rate_band(rate: float) -> str:
    if rate < 0:
        return "🔵 negative"
    if rate < 15:
        return "🟢 cheap"
    if rate < 25:
        return "🟡 moderate"
    return "🔴 expensive"


# ── cached fetchers ───────────────────────────────────────────────────────────


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_account_data() -> dict:
    """Auto-discover account number + all meter points. Only OCTOPUS_API_KEY required."""
    octopus = Octopus()
    account_number = octopus.account_number_from_api_key()
    account = octopus.account(account_number)

    meter_points = []
    for prop in account.get("properties", []):
        address = prop.get("address_line_1", "") or prop.get("address", "")
        for mp in prop.get("electricity_meter_points", []):
            mpan = mp["mpan"]
            agreements = sorted(mp.get("agreements", []), key=lambda a: a["valid_from"])
            sn = None
            if mp.get("meters"):
                sn = mp["meters"][0].get("serial_number") or mp["meters"][0].get("serialNumber")
            meter_points.append(
                {
                    "mpan": mpan,
                    "meter_sn": sn,
                    "agreements": agreements,
                    "label": f"{mpan} / {sn}" if sn else mpan,
                    "address": address,
                }
            )

    return {"account_number": account_number, "meter_points": meter_points}


def _fetch_consumption_api(mpan: str, sn: str, period_from: str, period_to: str) -> pd.DataFrame:
    octopus = Octopus(mpan=mpan, sn=sn)
    records = octopus.consumption(period_from=period_from, period_to=period_to)
    return pd.DataFrame([{"interval_start": r.interval_start, "interval_end": r.interval_end, "consumption": r.consumption} for r in records])


@st.cache_data(ttl=300, show_spinner=False)
def fetch_consumption(mpan: str, sn: str, period_from: str, period_to: str) -> list[dict]:
    key = cache_key("consumption", mpan, period_from, period_to)
    df = load_or_fetch(key, lambda: _fetch_consumption_api(mpan, sn, period_from, period_to))
    return df.to_dict("records")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_current_agile_product() -> str:
    try:
        octopus = Octopus()
        req = octopus._request("GET", "products/", params={"is_variable": True, "brand": "OCTOPUS_ENERGY"})
        agile = [p["code"] for p in req.json().get("results", []) if "AGILE" in p.get("code", "") and "OUTGOING" not in p.get("code", "")]
        if agile:
            return sorted(agile)[-1]
    except Exception:
        pass
    return "AGILE-24-10-01"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_tariff_info(mpan: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (current_tariff, current_product, agile_tariff, agile_product)."""
    agile_product = fetch_current_agile_product()
    current_tariff: str | None = None
    region: str | None = None

    try:
        account_info = fetch_account_data()
        for mp in account_info["meter_points"]:
            if mp["mpan"] == mpan:
                current_tariff = tariff_at(mp["agreements"], datetime.now(UTC))
                break
    except Exception:
        pass

    if current_tariff:
        region = current_tariff.split("-")[-1]
    else:
        try:
            mp_data = Octopus(mpan=mpan)._request("GET", f"electricity-meter-points/{mpan}/").json()
            region = mp_data.get("gsp", "").lstrip("_") or None
        except Exception:
            pass

    if not region:
        return None, None, None, None

    agile_tariff = f"E-1R-{agile_product}-{region}"
    current_product = product_code_from_tariff(current_tariff) if current_tariff else None
    return current_tariff, current_product, agile_tariff, agile_product


def _fetch_rates_api(product_code: str, tariff_code: str, period_from: str, period_to: str) -> pd.DataFrame:
    octopus = Octopus()
    raw = octopus.standard_unit_rates(product_code=product_code, tariff_code=tariff_code, period_from=period_from, period_to=period_to)
    rows = []
    for r in raw:
        vf = r["valid_from"]
        if isinstance(vf, str):
            vf = parse_dt(vf)
        rows.append(
            {
                "valid_from": vf,
                "valid_to": r.get("valid_to"),
                "value_inc_vat": float(r["value_inc_vat"]),
                "value_exc_vat": float(r.get("value_exc_vat", 0)),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_rates(product_code: str, tariff_code: str, period_from: str, period_to: str) -> list[dict]:
    key = cache_key("rates", tariff_code, period_from, period_to)
    df = load_or_fetch(key, lambda: _fetch_rates_api(product_code, tariff_code, period_from, period_to))
    return df.to_dict("records")


def _fetch_standing_charge_api(product_code: str, tariff_code: str) -> pd.DataFrame:
    octopus = Octopus()
    try:
        charges = octopus.standing_charges(product_code, tariff_code)
        if charges:
            return pd.DataFrame([{"value_inc_vat": float(charges[0]["value_inc_vat"])}])
    except Exception:
        pass
    return pd.DataFrame([{"value_inc_vat": None}])


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_standing_charge(product_code: str, tariff_code: str) -> float | None:
    key = cache_key("standing_charge", tariff_code)
    df = load_or_fetch(key, lambda: _fetch_standing_charge_api(product_code, tariff_code))
    val = df["value_inc_vat"].iloc[0] if not df.empty else None
    return float(val) if val is not None else None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_actual_rate_index(mpan: str, period_from: str, period_to: str) -> tuple[list, list]:
    try:
        account_info = fetch_account_data()
        mp_info = next((m for m in account_info["meter_points"] if m["mpan"] == mpan), None)
    except Exception:
        return [], []

    if not mp_info:
        return [], []

    pf = parse_dt(period_from)
    pt = parse_dt(period_to)
    all_rates: list[dict] = []

    for ag in mp_info["agreements"]:
        ag_from = parse_dt(ag["valid_from"])
        ag_to = parse_dt(ag["valid_to"]) if ag.get("valid_to") else None
        if ag_from >= pt or (ag_to is not None and ag_to <= pf):
            continue
        tc = ag["tariff_code"]
        pc = product_code_from_tariff(tc)
        fetch_from = max(pf, ag_from).strftime("%Y-%m-%dT%H:%M:%SZ")
        fetch_to = (min(pt, ag_to) if ag_to else pt).strftime("%Y-%m-%dT%H:%M:%SZ")
        rates = fetch_rates(pc, tc, fetch_from, fetch_to)
        all_rates.extend(rates)

    return build_rate_index(all_rates)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_standing_charge_for_date(mpan: str, d: date) -> float | None:
    """Return standing charge (p/day) for the tariff active on date d."""
    try:
        account_info = fetch_account_data()
        mp_info = next((m for m in account_info["meter_points"] if m["mpan"] == mpan), None)
    except Exception:
        return None
    if not mp_info:
        return None

    at = datetime(d.year, d.month, d.day, 12, tzinfo=UTC)
    tc = tariff_at(mp_info["agreements"], at)
    if not tc:
        return None
    try:
        pc = product_code_from_tariff(tc)
    except ValueError:
        return None
    return fetch_standing_charge(pc, tc)
