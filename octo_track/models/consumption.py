from __future__ import annotations

from datetime import UTC, datetime


class ElectricityConsumption:
    """Electricity consumption record from the Octopus Energy API."""

    def __init__(
        self,
        mpan: str,
        meter_sn: str,
        consumption: float,
        interval_start: datetime,
        interval_end: datetime,
        unit: str = "kWh",
    ):
        self.mpan = mpan
        self.meter_sn = meter_sn
        self.consumption = consumption
        self.interval_start = _as_utc_datetime(interval_start)
        self.interval_end = _as_utc_datetime(interval_end)
        self.unit = unit

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ElectricityConsumption):
            return NotImplemented
        return (self.mpan, self.meter_sn, self.interval_start, self.consumption) == (
            other.mpan,
            other.meter_sn,
            other.interval_start,
            other.consumption,
        )

    @classmethod
    def from_dict(cls, data: dict) -> ElectricityConsumption:
        payload = dict(data)
        if "meter_sn" not in payload and payload.get("serial_number"):
            payload["meter_sn"] = payload["serial_number"]
        return cls(
            mpan=payload["mpan"],
            meter_sn=payload["meter_sn"],
            consumption=float(payload["consumption"]),
            interval_start=payload["interval_start"],
            interval_end=payload["interval_end"],
            unit=payload.get("unit", "kWh"),
        )


def _as_utc_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
