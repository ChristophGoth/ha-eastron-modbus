"""The Eastron SDM Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_METERS,
    CONF_MODEL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import EastronMeterCoordinator
from .hub import EastronHub, EastronModbusError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type EastronConfigEntry = ConfigEntry["EastronRuntimeData"]


class EastronRuntimeData:
    """Everything one gateway entry owns at runtime."""

    def __init__(
        self, hub: EastronHub, coordinators: list[EastronMeterCoordinator]
    ) -> None:
        """Hold the shared hub and one coordinator per meter."""
        self.hub = hub
        self.coordinators = coordinators


async def async_setup_entry(hass: HomeAssistant, entry: EastronConfigEntry) -> bool:
    """Set up one gateway and all the meters behind it."""
    hub = EastronHub(entry.data[CONF_HOST], entry.data[CONF_PORT], DEFAULT_TIMEOUT)
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    coordinators: list[EastronMeterCoordinator] = []
    for meter in entry.data[CONF_METERS]:
        slave_id = meter[CONF_SLAVE_ID]
        try:
            identity = await hub.async_read_identity(slave_id)
        except EastronModbusError as err:
            await hub.async_close()
            raise ConfigEntryNotReady(
                f"Meter '{meter[CONF_NAME]}' (slave {slave_id}) did not answer: {err}"
            ) from err

        # Trust the stored model if the meter reports something unfamiliar,
        # so a firmware quirk cannot strand an already working entry.
        model = identity.model or meter[CONF_MODEL]
        if identity.model and identity.model != meter[CONF_MODEL]:
            _LOGGER.warning(
                "Meter '%s' (slave %s) reports model %s but was configured as %s; using %s",
                meter[CONF_NAME],
                slave_id,
                identity.model,
                meter[CONF_MODEL],
                identity.model,
            )

        coordinator = EastronMeterCoordinator(
            hass,
            hub,
            name=meter[CONF_NAME],
            slave_id=slave_id,
            model=model,
            identity=identity,
            scan_interval=scan_interval,
        )
        await coordinator.async_config_entry_first_refresh()
        coordinators.append(coordinator)

    entry.runtime_data = EastronRuntimeData(hub, coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EastronConfigEntry) -> bool:
    """Tear down the platforms and close the shared socket."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.hub.async_close()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: EastronConfigEntry) -> None:
    """Reload when the poll interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)
