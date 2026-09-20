"""Constants for the Eastron SDM Modbus integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "eastron_modbus"

CONF_METERS: Final = "meters"
CONF_SLAVE_ID: Final = "slave_id"
CONF_MODEL: Final = "model"

DEFAULT_PORT: Final = 8899
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_TIMEOUT: Final = 5

# Holding register block holding the immutable meter identity.
# 0xFC00/0xFC01 = serial number (uint32), 0xFC02 = meter code, 0xFC03 = sw version.
REG_IDENT: Final = 0xFC00
REG_IDENT_COUNT: Final = 4

# Meter code -> model key, as reported by the hardware at holding register 0xFC02.
METER_CODE_SDM120: Final = 0x0020
METER_CODE_SDM630: Final = 0x0070

MODEL_SDM120: Final = "SDM120"
MODEL_SDM630: Final = "SDM630"

METER_CODE_TO_MODEL: Final[dict[int, str]] = {
    METER_CODE_SDM120: MODEL_SDM120,
    METER_CODE_SDM630: MODEL_SDM630,
}


def slave_identifier(slave_id: int) -> tuple[str, str]:
    """Device registry identifier carrying a meter's slave address.

    A meter's primary identifier is its hardware serial, which only a running
    coordinator can read. This second identifier records the bus address the
    meter was configured under, so it stays resolvable while the entry is
    unloaded - which is exactly when a meter that no longer answers has to be
    removed.
    """
    return (DOMAIN, f"slave:{slave_id}")
