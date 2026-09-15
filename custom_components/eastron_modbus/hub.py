"""Modbus transport shared by every meter behind one gateway.

A Modbus-to-Ethernet gateway multiplexes a single RS485 bus onto one TCP
socket, so all meters share one client and one lock: overlapping requests on
the same socket would interleave RTU frames on the wire and corrupt replies.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.framer import FramerType

from .const import METER_CODE_TO_MODEL, REG_IDENT, REG_IDENT_COUNT
from .registers import EastronRegister

_LOGGER = logging.getLogger(__name__)

# Meters ignore frames that arrive too close together on a shared RS485 bus.
_INTER_REQUEST_DELAY = 0.05


class EastronModbusError(Exception):
    """Raised when the gateway or a meter fails to answer correctly."""


@dataclass(frozen=True)
class MeterIdentity:
    """Immutable identity read from a meter's holding registers."""

    serial: int
    meter_code: int
    software_version: int

    @property
    def model(self) -> str | None:
        """Model name, or None if the meter code is not one we know."""
        return METER_CODE_TO_MODEL.get(self.meter_code)


class EastronHub:
    """Owns the TCP connection to the gateway and serialises bus access."""

    def __init__(self, host: str, port: int, timeout: int) -> None:
        """Set up a hub for one gateway; the socket opens on first use."""
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()
        self._client = AsyncModbusTcpClient(
            host,
            port=port,
            framer=FramerType.RTU,
            timeout=timeout,
            retries=3,
        )

    async def _async_ensure_connected(self) -> None:
        """Open the socket to the gateway if it is not already up."""
        if not self._client.connected:
            await self._client.connect()
            if not self._client.connected:
                raise EastronModbusError(f"Cannot reach gateway at {self.target}")

    @property
    def target(self) -> str:
        """Human readable gateway address, for logs and error messages."""
        return f"{self._host}:{self._port}"

    async def async_close(self) -> None:
        """Close the shared socket."""
        self._client.close()

    async def _read(self, address: int, count: int, slave_id: int) -> list[int]:
        """Read raw input registers from one meter, serialised against others."""
        async with self._lock:
            await self._async_ensure_connected()
            try:
                result = await self._client.read_input_registers(
                    address=address, count=count, device_id=slave_id
                )
            except Exception as err:  # pymodbus raises a wide range here
                raise EastronModbusError(
                    f"Read of {count} registers at {address} from slave {slave_id} failed: {err}"
                ) from err
            await asyncio.sleep(_INTER_REQUEST_DELAY)

        if result.isError():
            raise EastronModbusError(
                f"Slave {slave_id} returned an error for {count} registers at {address}: {result}"
            )

        registers = list(result.registers)
        # A truncated reply would index past the end when decoded. This shows up
        # when something else is polling the same RS485 bus and the two masters'
        # frames interleave, so fail loudly rather than returning junk values.
        if len(registers) != count:
            raise EastronModbusError(
                f"Slave {slave_id} returned {len(registers)} of {count} registers "
                f"at {address}; is another master polling the same bus?"
            )
        return registers

    async def async_read_identity(self, slave_id: int) -> MeterIdentity:
        """Read serial number, meter code and firmware version from a meter."""
        async with self._lock:
            await self._async_ensure_connected()
            try:
                result = await self._client.read_holding_registers(
                    address=REG_IDENT, count=REG_IDENT_COUNT, device_id=slave_id
                )
            except Exception as err:
                raise EastronModbusError(
                    f"Identity read from slave {slave_id} failed: {err}"
                ) from err
            await asyncio.sleep(_INTER_REQUEST_DELAY)

        if result.isError():
            raise EastronModbusError(
                f"No meter answered at slave id {slave_id}: {result}"
            )

        regs = result.registers
        return MeterIdentity(
            serial=(regs[0] << 16) | regs[1],
            meter_code=regs[2],
            software_version=regs[3],
        )

    async def async_read_registers(
        self, slave_id: int, registers: tuple[EastronRegister, ...]
    ) -> dict[str, float]:
        """Read every register for one meter, coalescing adjacent addresses.

        Eastron meters cap a single response at 40 registers, and the register
        map has wide gaps, so requests are grouped into runs of adjacent
        addresses rather than issued one value at a time.
        """
        values: dict[str, float] = {}
        for block in _build_blocks(registers):
            raw = await self._read(block.start, block.count, slave_id)
            for register in block.registers:
                offset = register.address - block.start
                values[register.key] = _decode_float(raw[offset], raw[offset + 1])
        return values


@dataclass(frozen=True)
class _Block:
    """A contiguous run of registers fetched in one request."""

    start: int
    count: int
    registers: tuple[EastronRegister, ...]


# Eastron limits one response to 40 registers (20 float values).
_MAX_BLOCK_REGISTERS = 40


def _build_blocks(registers: tuple[EastronRegister, ...]) -> list[_Block]:
    """Group registers into the fewest requests the meters will accept."""
    if not registers:
        return []

    ordered = sorted(registers, key=lambda reg: reg.address)
    blocks: list[_Block] = []
    current: list[EastronRegister] = [ordered[0]]

    for register in ordered[1:]:
        start = current[0].address
        span = register.address + register.count - start
        # A gap costs a wasted read; a new request costs a round trip. Keep
        # reading through gaps until the block hits the meter's size limit.
        if span <= _MAX_BLOCK_REGISTERS:
            current.append(register)
            continue
        blocks.append(_finish_block(current))
        current = [register]

    blocks.append(_finish_block(current))
    return blocks


def _finish_block(registers: list[EastronRegister]) -> _Block:
    start = registers[0].address
    end = max(reg.address + reg.count for reg in registers)
    return _Block(start=start, count=end - start, registers=tuple(registers))


def _decode_float(high: int, low: int) -> float:
    """Decode two registers as a big-endian IEEE-754 float."""
    return struct.unpack(">f", struct.pack(">HH", high, low))[0]
