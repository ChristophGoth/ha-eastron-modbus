"""Register maps for Eastron SDM meters.

All measured values are 32-bit IEEE-754 floats held in two consecutive input
registers, read with function code 04. Addresses below are zero-based Modbus
offsets; the documentation numbers them as 3x30001 = offset 0.

The maps were transcribed from the Eastron protocol PDFs and then verified
against live hardware (SDM630 on slave 11, SDM120 on slaves 12-15); registers
the hardware does not populate are omitted.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
)

from .const import MODEL_SDM120, MODEL_SDM630

TOTAL = SensorStateClass.TOTAL
TOTAL_INCREASING = SensorStateClass.TOTAL_INCREASING
MEASUREMENT = SensorStateClass.MEASUREMENT


@dataclass(frozen=True, kw_only=True)
class EastronRegister:
    """A single float measurement exposed by a meter."""

    key: str
    name: str
    address: int
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass = MEASUREMENT
    precision: int = 2
    enabled_default: bool = True

    @property
    def count(self) -> int:
        """Registers occupied - every value is a 32-bit float."""
        return 2


def _v(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        **kw,  # type: ignore[arg-type]
    )


def _a(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=3,
        **kw,  # type: ignore[arg-type]
    )


def _w(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
        **kw,  # type: ignore[arg-type]
    )


def _va(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        precision=1,
        **kw,  # type: ignore[arg-type]
    )


def _var(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        precision=1,
        **kw,  # type: ignore[arg-type]
    )


def _kwh(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=TOTAL_INCREASING,
        precision=3,
        **kw,  # type: ignore[arg-type]
    )


def _kvarh(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR,
        device_class=SensorDeviceClass.REACTIVE_ENERGY,
        state_class=TOTAL_INCREASING,
        precision=3,
        **kw,  # type: ignore[arg-type]
    )


def _pf(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        device_class=SensorDeviceClass.POWER_FACTOR,
        precision=3,
        **kw,  # type: ignore[arg-type]
    )


def _angle(key: str, name: str, address: int, **kw: object) -> EastronRegister:
    return EastronRegister(
        key=key, name=name, address=address, unit=DEGREE, precision=1, **kw  # type: ignore[arg-type]
    )


def _thd(key: str, name: str, address: int) -> EastronRegister:
    return EastronRegister(
        key=key,
        name=name,
        address=address,
        unit=PERCENTAGE,
        precision=2,
        enabled_default=False,
    )


# --------------------------------------------------------------------------
# SDM120 - single phase, two wire
# --------------------------------------------------------------------------
SDM120_REGISTERS: tuple[EastronRegister, ...] = (
    _v("voltage", "Voltage", 0),
    _a("current", "Current", 6),
    _w("active_power", "Power", 12),
    _va("apparent_power", "Apparent power", 18, enabled_default=False),
    _var("reactive_power", "Reactive power", 24, enabled_default=False),
    _pf("power_factor", "Power factor", 30),
    EastronRegister(
        key="frequency",
        name="Frequency",
        address=70,
        unit=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
    ),
    _kwh("import_active_energy", "Import energy", 72),
    _kwh("export_active_energy", "Export energy", 74),
    _kvarh("import_reactive_energy", "Import reactive energy", 76, enabled_default=False),
    _kvarh("export_reactive_energy", "Export reactive energy", 78, enabled_default=False),
    _w("power_demand", "Total system power demand", 84, enabled_default=False),
    _w("power_demand_max", "Maximum total system power demand", 86, enabled_default=False),
    _w("import_power_demand", "Import system power demand", 88, enabled_default=False),
    _a("current_demand", "Current demand", 258, enabled_default=False),
    _a("current_demand_max", "Maximum current demand", 264, enabled_default=False),
    _kwh("total_active_energy", "Total active energy", 342, enabled_default=False),
    _kvarh("total_reactive_energy", "Total reactive energy", 344, enabled_default=False),
)

# --------------------------------------------------------------------------
# SDM630 - three phase, four wire
# --------------------------------------------------------------------------
SDM630_REGISTERS: tuple[EastronRegister, ...] = (
    # Per-phase voltage / current / power
    _v("voltage_l1", "Voltage L1", 0),
    _v("voltage_l2", "Voltage L2", 2),
    _v("voltage_l3", "Voltage L3", 4),
    _a("current_l1", "Current L1", 6),
    _a("current_l2", "Current L2", 8),
    _a("current_l3", "Current L3", 10),
    _w("active_power_l1", "Power L1", 12),
    _w("active_power_l2", "Power L2", 14),
    _w("active_power_l3", "Power L3", 16),
    _va("apparent_power_l1", "Apparent power L1", 18, enabled_default=False),
    _va("apparent_power_l2", "Apparent power L2", 20, enabled_default=False),
    _va("apparent_power_l3", "Apparent power L3", 22, enabled_default=False),
    _var("reactive_power_l1", "Reactive power L1", 24, enabled_default=False),
    _var("reactive_power_l2", "Reactive power L2", 26, enabled_default=False),
    _var("reactive_power_l3", "Reactive power L3", 28, enabled_default=False),
    _pf("power_factor_l1", "Power factor L1", 30),
    _pf("power_factor_l2", "Power factor L2", 32),
    _pf("power_factor_l3", "Power factor L3", 34),
    _angle("phase_angle_l1", "Phase angle L1", 36, enabled_default=False),
    _angle("phase_angle_l2", "Phase angle L2", 38, enabled_default=False),
    _angle("phase_angle_l3", "Phase angle L3", 40, enabled_default=False),
    # System totals
    _v("voltage_avg", "Average voltage L-N", 42),
    _a("current_avg", "Average current", 46),
    _a("current_sum", "Sum of line currents", 48, enabled_default=False),
    _w("total_active_power", "Total power", 52),
    _va("total_apparent_power", "Total apparent power", 56, enabled_default=False),
    _var("total_reactive_power", "Total reactive power", 60, enabled_default=False),
    _pf("total_power_factor", "Total power factor", 62),
    _angle("total_phase_angle", "Total phase angle", 66, enabled_default=False),
    EastronRegister(
        key="frequency",
        name="Frequency",
        address=70,
        unit=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
    ),
    # Energy totals
    _kwh("import_active_energy", "Import energy", 72),
    _kwh("export_active_energy", "Export energy", 74),
    _kvarh("import_reactive_energy", "Import reactive energy", 76, enabled_default=False),
    _kvarh("export_reactive_energy", "Export reactive energy", 78, enabled_default=False),
    # Home Assistant has no apparent-energy device class and no ampere-hour
    # unit, so these two carry a bare unit string and no device class.
    EastronRegister(
        key="total_apparent_energy",
        name="Total apparent energy",
        address=80,
        unit="kVAh",
        state_class=TOTAL_INCREASING,
        precision=3,
        enabled_default=False,
    ),
    EastronRegister(
        key="total_ampere_hours",
        name="Total ampere hours",
        address=82,
        unit="Ah",
        state_class=TOTAL_INCREASING,
        precision=3,
        enabled_default=False,
    ),
    _w("power_demand", "Total system power demand", 84, enabled_default=False),
    _w("power_demand_max", "Maximum total system power demand", 86, enabled_default=False),
    # Line to line voltages
    _v("voltage_l1_l2", "Voltage L1-L2", 200, enabled_default=False),
    _v("voltage_l2_l3", "Voltage L2-L3", 202, enabled_default=False),
    _v("voltage_l3_l1", "Voltage L3-L1", 204, enabled_default=False),
    _v("voltage_ll_avg", "Average voltage L-L", 206, enabled_default=False),
    _a("neutral_current", "Neutral current", 224, enabled_default=False),
    # Harmonic distortion - diagnostic, off by default
    _thd("voltage_thd_l1", "Voltage THD L1", 234),
    _thd("voltage_thd_l2", "Voltage THD L2", 236),
    _thd("voltage_thd_l3", "Voltage THD L3", 238),
    _thd("current_thd_l1", "Current THD L1", 240),
    _thd("current_thd_l2", "Current THD L2", 242),
    _thd("current_thd_l3", "Current THD L3", 244),
    _thd("voltage_thd_avg", "Average voltage THD", 248),
    _thd("current_thd_avg", "Average current THD", 250),
    # Per-phase demand
    _a("current_demand_l1", "Current demand L1", 258, enabled_default=False),
    _a("current_demand_l2", "Current demand L2", 260, enabled_default=False),
    _a("current_demand_l3", "Current demand L3", 262, enabled_default=False),
    # Per-phase energy
    _kwh("total_active_energy", "Total active energy", 342, enabled_default=False),
    _kvarh("total_reactive_energy", "Total reactive energy", 344, enabled_default=False),
    _kwh("import_active_energy_l1", "Import active energy L1", 346, enabled_default=False),
    _kwh("import_active_energy_l2", "Import active energy L2", 348, enabled_default=False),
    _kwh("import_active_energy_l3", "Import active energy L3", 350, enabled_default=False),
    _kwh("export_active_energy_l1", "Export active energy L1", 352, enabled_default=False),
    _kwh("export_active_energy_l2", "Export active energy L2", 354, enabled_default=False),
    _kwh("export_active_energy_l3", "Export active energy L3", 356, enabled_default=False),
)

REGISTER_MAPS: dict[str, tuple[EastronRegister, ...]] = {
    MODEL_SDM120: SDM120_REGISTERS,
    MODEL_SDM630: SDM630_REGISTERS,
}
