# Eastron SDM Modbus for Home Assistant

Home Assistant integration for Eastron SDM energy meters reached over a
Modbus-to-Ethernet gateway (RTU over TCP). Several meters share one gateway;
each is addressed by its Modbus slave address and appears in Home Assistant as
its own device under a name you choose.

Supported meters:

| Model  | Meter code | Phases |
| ------ | ---------- | ------ |
| SDM120 | `0x0020`   | 1P2W   |
| SDM630 | `0x0070`   | 3P4W   |

## Installation

### HACS

Add this repository as a custom repository of type *Integration*, install
**Eastron SDM Modbus**, then restart Home Assistant.

### Manual

Copy `custom_components/eastron_modbus` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

*Settings → Devices & Services → Add Integration → Eastron SDM Modbus*

1. Enter the gateway's host and port (default `8899`) and the poll interval.
   The gateway must be configured for **RTU over TCP** — not Modbus TCP.
2. For each meter, enter its Modbus slave address and a name. The integration
   probes the address, detects the model from the meter's own identity
   registers, and refuses addresses where nothing answers.
3. Repeat until every meter is added.

The poll interval can be changed later under the entry's *Configure* option.

## How it works

All meters behind one gateway share a single TCP connection, because the
gateway funnels them onto one RS485 bus. Requests are serialised with a lock
and spaced slightly apart, so frames from different meters cannot interleave
and corrupt each other on the wire.

Each meter is polled by its own coordinator. Reads are grouped into blocks of
adjacent registers — the meters cap one response at 40 registers, so a full
SDM630 refresh costs a handful of round trips instead of one per value.

Entities are keyed by the meter's hardware serial number rather than its slave
address, so history survives readdressing a meter on the bus.

### Only one master per bus

RS485 has no arbitration between masters. If something else polls the same
meters — a leftover `modbus:` block in `configuration.yaml`, another gateway
client, a vendor tool — the two masters' frames interleave and each sees
truncated replies and timeouts. Truncated reads are rejected rather than
decoded into wrong values, and the log then asks whether another master is on
the bus. Remove the other poller; there is no setting that makes sharing work.

Values that are mostly of interest when diagnosing a problem — THD, demand
figures, per-phase energy counters, phase angles — are created but disabled by
default. Enable them per entity if you want them.

## Entities

The SDM120 exposes voltage, current, active/apparent/reactive power, power
factor, frequency, the four energy counters and the totals. The SDM630 adds
per-phase values for each of those, line-to-line voltages, neutral current and
system-wide totals.

Energy counters are `total_increasing` with the `energy` device class, so
import and export can be used directly in the Energy dashboard.

## Register documentation

The register maps were transcribed from the Eastron protocol specifications in
this repository and verified against live hardware:

- `SDM120-MODBUS_Protocol.pdf` — SDM120 V2.4
- `SDM630_MODBUS_Protocol.pdf` — SDM630 V1.8

All measured values are 32-bit IEEE-754 floats spanning two input registers,
read with function code 04, most significant register first.
