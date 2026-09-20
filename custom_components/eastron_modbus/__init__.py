"""The Eastron SDM Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_METERS,
    CONF_MODEL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    slave_identifier,
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
    unreachable: list[str] = []
    for meter in entry.data[CONF_METERS]:
        slave_id = meter[CONF_SLAVE_ID]
        try:
            identity = await hub.async_read_identity(slave_id)
        except EastronModbusError as err:
            # One dead meter must not take the gateway down with it: the others
            # are on the same bus and still answering, and a meter that is gone
            # for good can only be removed while the entry is usable.
            _LOGGER.warning(
                "Meter '%s' (slave %s) did not answer and is skipped: %s",
                meter[CONF_NAME],
                slave_id,
                err,
            )
            unreachable.append(f"'{meter[CONF_NAME]}' (slave {slave_id})")
            continue

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

    if not coordinators:
        # Nothing answered at all, which points at the gateway rather than at
        # the meters: retry instead of loading an entry that has no devices.
        await hub.async_close()
        raise ConfigEntryNotReady(
            f"No meter behind {hub.target} answered: {', '.join(unreachable)}"
        )

    if unreachable:
        _LOGGER.warning(
            "%s of %s meters behind %s are unreachable: %s. "
            "Remove a meter that is gone for good from its device page or the "
            "entry's options.",
            len(unreachable),
            len(entry.data[CONF_METERS]),
            hub.target,
            ", ".join(unreachable),
        )

    entry.runtime_data = EastronRuntimeData(hub, coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EastronConfigEntry) -> bool:
    """Tear down the platforms and close the shared socket."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # A setup that raised before storing its runtime data has no hub to close.
    runtime = getattr(entry, "runtime_data", None)
    if unloaded and runtime is not None:
        await runtime.hub.async_close()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: EastronConfigEntry) -> None:
    """Reload when the poll interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)


def _slave_id_for_device(entry: EastronConfigEntry, device: dr.DeviceEntry) -> int | None:
    """Work out which configured meter a device stands for.

    Devices created since 0.2.1 carry their slave id as a second identifier,
    which resolves without the entry being loaded. Older devices only have the
    hardware serial, so fall back to the running coordinators and then to the
    device name, which is the meter name the entry still stores.
    """
    meters = entry.data[CONF_METERS]

    for meter in meters:
        if slave_identifier(meter[CONF_SLAVE_ID]) in device.identifiers:
            return meter[CONF_SLAVE_ID]

    serials = {
        identifier
        for domain, identifier in device.identifiers
        if domain == DOMAIN and not identifier.startswith("slave:")
    }
    if not serials:
        return None

    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        for coordinator in runtime.coordinators:
            if str(coordinator.identity.serial) in serials:
                return coordinator.slave_id

    # Unloaded, and the device predates the slave identifier: the device name
    # is the meter name the entry stores, so match on it as long as it is not
    # shared by two meters. Deliberately not name_by_user - a device the user
    # renamed no longer carries the configured name.
    named = [meter for meter in meters if meter[CONF_NAME] == device.name]
    if len(named) == 1:
        return named[0][CONF_SLAVE_ID]

    return None


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: EastronConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Let a single meter be deleted from its device page.

    This has to work while the entry is unloaded: a meter that no longer
    answers keeps the whole entry from starting, and removing it is how the
    user fixes that, so nothing here may depend on runtime state.
    """
    slave_id = _slave_id_for_device(entry, device)
    if slave_id is None:
        # Not a meter of this entry, or one no longer in its data: the device
        # is an orphan either way, so let it go.
        return True

    meters = [
        meter for meter in entry.data[CONF_METERS] if meter[CONF_SLAVE_ID] != slave_id
    ]
    if not meters:
        _LOGGER.warning(
            "Refusing to remove the last meter of %s; delete the integration entry instead",
            entry.title,
        )
        return False

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_METERS: meters}
    )
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
    return True
