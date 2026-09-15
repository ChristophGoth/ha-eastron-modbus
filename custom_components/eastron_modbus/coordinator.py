"""Polling coordinator for one Eastron meter."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .hub import EastronHub, EastronModbusError, MeterIdentity
from .registers import REGISTER_MAPS, EastronRegister

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, float]:
        """Read every register for this meter."""
        try:
            return await self.hub.async_read_registers(self.slave_id, self.registers)
        except EastronModbusError as err:
            raise UpdateFailed(str(err)) from err
