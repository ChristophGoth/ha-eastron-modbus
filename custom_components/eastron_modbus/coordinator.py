"""Polling coordinator for one Eastron meter."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .hub import EastronHub, EastronModbusError, MeterIdentity
from .registers import REGISTER_MAPS, EastronRegister

_LOGGER = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_INVALID = "invalid"
STATUS_ERROR = "error"


# "Slave 12 returned 2 of 8 registers at 24" - a truncated frame, as opposed to
# "Slave 12 returned an error for 8 registers at 24", which is a meter answering
# correctly with a Modbus exception. Only the former means the wire is confused.
_TRUNCATED_FRAME = re.compile(r"returned \d+ of \d+ registers")


def _classify(err: EastronModbusError) -> str:
    """Sort a failure into the buckets a user can act on.

    A timeout means nothing answered; an invalid response means something did
    answer but the frame was unusable, which on this bus almost always means a
    second master is talking over us.
    """
    text = str(err).lower()
    if _TRUNCATED_FRAME.search(text):
        return STATUS_INVALID
    if "timeout" in text or "no response" in text or "cannot reach" in text:
        return STATUS_TIMEOUT
    return STATUS_ERROR


@dataclass
class MeterDiagnostics:
    """Rolling health record for one meter, surfaced as diagnostic sensors."""

    last_status: str = STATUS_OK
    last_duration: float | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def total_polls(self) -> int:
        """Every poll attempted since Home Assistant started."""
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float | None:
        """Share of polls that succeeded, as a percentage."""
        if not self.total_polls:
            return None
        return self.success_count / self.total_polls * 100


class EastronMeterCoordinator(DataUpdateCoordinator[dict[str, float]]):
    """Polls a single meter on the shared bus."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: EastronHub,
        *,
        name: str,
        slave_id: int,
        model: str,
        identity: MeterIdentity,
        scan_interval: int,
    ) -> None:
        """Set up polling for one meter."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.hub = hub
        self.meter_name = name
        self.slave_id = slave_id
        self.model = model
        self.identity = identity
        self.registers: tuple[EastronRegister, ...] = REGISTER_MAPS[model]
        self.diagnostics = MeterDiagnostics()

    async def _async_update_data(self) -> dict[str, float]:
        """Read every register for this meter, recording how it went."""
        diag = self.diagnostics
        started = time.monotonic()
        try:
            values = await self.hub.async_read_registers(self.slave_id, self.registers)
        except EastronModbusError as err:
            diag.last_duration = time.monotonic() - started
            diag.last_status = _classify(err)
            diag.last_error = str(err)
            diag.consecutive_failures += 1
            diag.failure_count += 1
            raise UpdateFailed(str(err)) from err

        diag.last_duration = time.monotonic() - started
        diag.last_status = STATUS_OK
        diag.last_success = dt_util.utcnow()
        diag.last_error = None
        diag.consecutive_failures = 0
        diag.success_count += 1
        return values
