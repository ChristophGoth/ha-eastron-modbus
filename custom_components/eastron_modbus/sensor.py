"""Sensor platform for Eastron SDM meters."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EastronConfigEntry
from .const import DOMAIN
from .coordinator import EastronMeterCoordinator
from .registers import EastronRegister

MANUFACTURER = "Eastron"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EastronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a sensor per register for every configured meter."""
    entities: list[EastronSensor] = []
    for coordinator in entry.runtime_data.coordinators:
        entities.extend(
            EastronSensor(coordinator, register) for register in coordinator.registers
        )
    async_add_entities(entities)


class EastronSensor(CoordinatorEntity[EastronMeterCoordinator], SensorEntity):
    """One measured value from one meter."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EastronMeterCoordinator, register: EastronRegister
    ) -> None:
        """Bind a sensor to a register on its meter."""
        super().__init__(coordinator)
        self._register = register

        # The hardware serial keeps ids stable even if the meter is later
        # readdressed on the bus.
        serial = coordinator.identity.serial
        self._attr_unique_id = f"{serial}_{register.key}"
        self.entity_description = SensorEntityDescription(
            key=register.key,
            name=register.name,
            native_unit_of_measurement=register.unit,
            device_class=register.device_class,
            state_class=register.state_class,
            suggested_display_precision=register.precision,
            entity_registry_enabled_default=register.enabled_default,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            name=coordinator.meter_name,
            manufacturer=MANUFACTURER,
            model=coordinator.model,
            serial_number=str(serial),
            sw_version=f"{coordinator.identity.software_version:04X}",
            via_device=(DOMAIN, coordinator.hub.target),
        )

    @property
    def available(self) -> bool:
        """Available while the last poll succeeded and returned this value."""
        return super().available and self._register.key in (self.coordinator.data or {})

    @property
    def native_value(self) -> float | None:
        """Latest value for this register."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._register.key)
