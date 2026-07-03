# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant **add-on** (Docker container, not a custom integration) that
bridges Home Assistant entities to Modbus and expose a
**single virtual Fronius SunSpec smart meter** (aggregating any number of
inverters) over Modbus TCP, so a Fronius GEN24 can discover it as a secondary
"Generator" meter.

An add-on is required (not an integration) because the process must run a
long-lived Modbus TCP **server** bound to port 502 — something HA integrations
cannot do.

**Why a single aggregate meter:** the Fronius will not poll more than one meter
per IP, and only on port 502. Rather than allocate extra host IPs (the v0.1
design, since removed), the add-on sums all inverters into one meter on HA's own
IP. Per-inverter breakdown is lost; total generation is correct.

## Architecture

Data flow: `data source (HA entities) → InverterState (per inverter)
→ Meter.recompute() sums into one SunSpec register image → one Modbus TCP server
→ Fronius polls HA's IP:502 as a client`.

Each inverter has one `source`. Sources are pluggable via the `DataSource`
interface in `source.py`; `homeassistant` (poll the HA Core API for entity
states) is currently the only implementation. Its `run()` loop normalizes each
inverter's entities to a metric dict and calls `meter.apply_inverter_metrics`. A
pure-HA setup needs no broker — only `homeassistant_api: true` in the manifest.

All application code lives in `fronius_virtual_smart_meter/app/`:

- `__main__.py` — asyncio orchestration. Builds sources via `build_sources`, then
  spawns `serve_meter`, `run_watchdog`, and one `source.run()` task per data
  source; tears down if any exits.
- `source.py` — the `DataSource` ABC (`async run()`), a name→builder registry
  (`register_source`), and `build_sources(config, meter)` which groups
  `meter.inverters` by `cfg.source` and instantiates one source per type. To add
  a source (e.g. MQTT), implement `DataSource` and register it — and add its name
  to `config._VALID_SOURCE` (parse-time validation is intentionally separate).
- `config.py` — parses/validates `/data/options.json` (path overridable via
  `OPTIONS_FILE` env, read at call time). One `MeterConfig` (identity/sign/stale)
  + N `InverterConfig` (each with an `entities` map of metric → HA entity id).
  `AppConfig.uses_homeassistant` reports whether any inverter uses that source.
- `meter.py` — `InverterState` holds one inverter's latest parsed values (per
  phase, plus retained lifetime energy). `Meter` aggregates all states in
  `recompute()`: power/current summed per phase, voltage/Hz averaged, energy
  summed (stale inverters drop from power but keep their energy).
  `apply_inverter_metrics` applies a metric dict to one state then recomputes.
- `sunspec.py` — **the core**. Builds the Fronius-compatible SunSpec register
  image and exposes `FIELD_INDEX` (field name → list index) + `set_float`.
- `ha_source.py` — `HomeAssistantSource(DataSource)`: polls the HA Core API
  (`http://supervisor/core/api/states` with `SUPERVISOR_TOKEN`) every
  `ha_poll_interval`s; normalizes units (kW→W, Wh→kWh) and calls
  `meter.apply_inverter_metrics`. Needs `homeassistant_api: true`.
- `modbus_server.py` — `_MeterDataBlock` serves the meter's live registers;
  `serve_meter` runs one pymodbus async TCP server on `0.0.0.0:502`.
- `watchdog.py` — periodically calls `meter.recompute()` so stale inverters drop
  from the live power total (safety: never feed frozen generation data into the
  Fronius export-control loop).

Packaging: `config.yaml` (add-on manifest: options schema, `host_network: true`,
`build.yaml` (Python 3.12 base images), `Dockerfile`, `run.sh` (bashio entrypoint).

## Critical domain constants (don't "fix" these without re-checking the Fronius spec)

These match the well-known GEN24-tested Fronius float meter map and are verified
by the round-trip test:

- SunSpec base = **wire/PDU address 40000** (register 40001). The Modbus
  datastore uses `zero_mode=True` so a client read of address 40000 returns the
  SunS marker (`sunspec.BASE_ADDRESS`).
- Layout: SunS `0x53756E53` → Common model 1 (**length 65**, Fronius variant —
  no trailing pad, DeviceAddress is the last register at 40069) → meter model
  **213** (length **124**) at 40070 → End `0xFFFF` at 40196. Total **197** registers.
  Always model 213 (three-phase float) — GEN24 firmware would not read model 211,
  which was the v0.1 single-phase bug (registered the meter but showed no values).
- Big-endian, most-significant-word first. Unpopulated floats = **0.0**, NOT the
  SunSpec NaN — Fronius treats NaN as an invalid reading and shows blank.
- Key field registers: `W`=40098, `TotWhExp`=40130, `TotWhImp`=40138.
- Power sign: `export` → negative watts (meter convention); `production` → positive.
- Fronius reads at most **125 registers per Modbus request** — any client/tool
  must chunk reads (see `tools/scan.py`).
- One meter **per IP** (Fronius limitation) is why the bridge aggregates all
  inverters into a single meter on HA's IP rather than serving one each.

Tests use **pytest** (`tests/`, config in `pyproject.toml`). Run `pytest` from
the repo root — `pythonpath = ["fronius_virtual_smart_meter"]` lets tests
`import app.*` with no install step. The suite is mostly fast pure-unit tests
(sunspec/meter/config/ha_source) plus datablock tests. One end-to-end Modbus TCP
round-trip is tagged `@pytest.mark.integration` (run just it with
`pytest -m integration`, skip with `pytest -m "not integration"`).

`tools/scan.py` remains for ad-hoc manual verification against a running server.

Two gotchas the tests encode:
- **When exercising a Modbus server in-process, run the client in a worker
  thread** (`asyncio.to_thread`) — a synchronous client in the same event loop
  deadlocks the async server (no response).
- `serve_meter`'s `while True` retry loop never returns and swallows
  cancellation, so tests drive `StartAsyncTcpServer` directly via
  `build_server_context(meter)` and stop it with `ServerAsyncStop()`.

## Conventions

- Pure-stdlib SunSpec encoding via `struct` (no `BinaryPayloadBuilder`) to stay
  independent of pymodbus API churn across versions.
- When adding a SunSpec field, append to `_METER_FLOAT_POINTS` only if it changes
  the model layout — offsets are derived from list position, so order matters and
  must match the SunSpec model 211/213 spec exactly.
