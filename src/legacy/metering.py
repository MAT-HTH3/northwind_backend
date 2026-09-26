"""Metering: meter points and their reading history.

Keyed by meter point (MPAN for electricity, SPID for water). Electricity registers in kWh,
water in litres.
"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from src.legacy._fixtures import load_fixture


class MeterRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    read_at: datetime
    value: int
    source: Literal["CUSTOMER", "AGENT", "ESTIMATE"]


class MeterPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    mpxn: str
    service: Literal["electricity", "water"]
    meter_serial: str
    smart: bool
    register_unit: Literal["kWh", "litres"]
    reads: list[MeterRead]  # oldest first


class Metering(Protocol):
    async def get_meter_point(self, mpxn: str) -> MeterPoint | None: ...


class MockMetering:
    def __init__(self, fixture: str = "metering.json") -> None:
        points = [MeterPoint.model_validate(p) for p in load_fixture(fixture)["meter_points"]]
        self._points = {point.mpxn: point for point in points}

    async def get_meter_point(self, mpxn: str) -> MeterPoint | None:
        return self._points.get(mpxn)
