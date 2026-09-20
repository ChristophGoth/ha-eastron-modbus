"""Sensor platform for Eastron SDM meters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EastronConfigEntry
from .const import DOMAIN, slave_identifier
from .coordinator import (
    STATUS_ERROR,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_TIMEOUT,
    EastronMeterCoordinator,
)
from .registers import EastronRegister

MANUFACTURER = "Eastron"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EastronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a sensor per register, plus the diagnostics, for every meter."""
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.coordinators:
        entities.extend(
            EastronSensor(coordinator, register) for register in coordinator.registers
        )
        entities.extend(
            EastronDiagnosticSensor(coordinator, description)
            for description in DIAGNOSTIC_SENSORS
        )
    async_add_entities(entities)


def _device_info(coordinator: EastronMeterCoordinator) -> DeviceInfo:
    """Describe the meter this coordinator polls."""
    serial = coordinator.identity.serial
    return DeviceInfo(
        # The serial keeps the device stable across readdressing; the slave id
        # is carried alongside it so a meter can still be identified when the
        # entry is not loaded and no coordinator exists to ask.
        identifiers={(DOMAIN, str(serial)), slave_identifier(coordinator.slave_id)},
        name=coordinator.meter_name,
        manufacturer=MANUFACTURER,
        model=coordinator.model,
        serial_number=str(serial),
        sw_version=f"{coordinator.identity.software_version:04X}",
        via_device=(DOMAIN, coordinator.hub.target),
    )


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
        self._attr_unique_id = f"{coordinator.identity.serial}_{register.key}"
        self.entity_description = SensorEntityDescription(
            key=register.key,
            name=register.name,
            native_unit_of_measurement=register.unit,
            device_class=register.device_class,
            state_class=register.state_class,
            suggested_display_precision=register.precision,
            entity_registry_enabled_default=register.enabled_default,
        )
        self._attr_device_info = _device_info(coordinator)

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


@dataclass(frozen=True, kw_only=True)
class EastronDiagnosticDescription(SensorEntityDescription):
    """A diagnostic sensor fed from the coordinator's health record."""

    value_fn: Callable[[EastronMeterCoordinator], str | int | float | datetime | None]


DIAGNOSTIC_SENSORS: tuple[EastronDiagnosticDescription, ...] = (
    EastronDiagnosticDescription(
        key="poll_status",
        name="Poll status",
        device_class=SensorDeviceClass.ENUM,
        options=[STATUS_OK, STATUS_TIMEOUT, STATUS_INVALID, STATUS_ERROR],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.diagnostics.last_status,
    ),
    EastronDiagnosticDescription(
        key="poll_duration",
        name="Poll duration",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: (
            None
            if c.diagnostics.last_duration is None
            else c.diagnostics.last_duration * 1000
        ),
    ),
    EastronDiagnosticDescription(
        key="last_successful_poll",
        name="Last successful poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.diagnostics.last_success,
    ),
    EastronDiagnosticDescription(
        key="consecutive_failures",
        name="Consecutive failures",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.diagnostics.consecutive_failures,
    ),
    EastronDiagnosticDescription(
        key="failed_polls",
        name="Failed polls",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.diagnostics.failure_count,
    ),
    EastronDiagnosticDescription(
        key="poll_success_rate",
        name="Poll success rate",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.diagnostics.success_rate,
    ),
)


class EastronDiagnosticSensor(
    CoordinatorEntity[EastronMeterCoordinator], SensorEntity
):
    """Reports how the polling of one meter is actually going."""

    _attr_has_entity_name = True
    entity_description: EastronDiagnosticDescription

    def __init__(
        self,
        coordinator: EastronMeterCoordinator,
        description: EastronDiagnosticDescription,
    ) -> None:
        """Bind a diagnostic sensor to its meter."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.identity.serial}_{description.key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def available(self) -> bool:
        """Always available: these report the failure, so they outlive it."""
        return True

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Current value of this diagnostic."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Attach the last error text to the status sensor."""
        if self.entity_description.key != "poll_status":
            return None
        error = self.coordinator.diagnostics.last_error
        return {"last_error": error} if error else None
