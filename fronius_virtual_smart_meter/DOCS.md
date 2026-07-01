# Fronius Virtual Smart Meter

Aggregates inverter data into a **single virtual Fronius SunSpec smart meter**,
so a Fronius GEN24 / Symo GEN24 Plus can discover it over Modbus TCP and count
that generation.

Each inverter's data can come from **Home Assistant** source:

- **Home Assistant entities**— point at existing sensors like
  `sensor.growatt1_power`.

## The problem it solves

A Fronius system only "sees" the inverters and meters wired into it. If you have
extra generators — e.g. small inverters — their production never shows up
in Solar.web. This bridge sums all of them into one meter the Fronius reads as
additional production (category _Generator_).

```
Inverter 1 ┐
Inverter 2 ┼─ Home Assistant entities
Inverter N ┘                      │
                                  ▼
                  Fronius Virtual Meter Bridge   (sums all inverters)
                                  │  one SunSpec Modbus TCP server, port 502
                                  ▼
                  Fronius GEN24 ← polls HA's IP:502 as Modbus client
```

## How it works

- Reads each inverter from its source: **HA entity states** (polled from the HA
  Core API, with automatic unit conversion — kW→W, Wh→kWh, etc.)
- **Sums** all inverters into one SunSpec meter model **213** (three-phase
  float), using the Fronius-compatible register layout (SunS marker at register
  40001, meter model at 40070, big-endian). Single-phase inverters contribute to
  their assigned phase; three-phase inverters contribute per phase.
- Runs **one Modbus TCP server on port 502, bound to Home Assistant's own IP** —
  no dedicated or alias IP needed.
- A freshness **watchdog** drops an inverter from the live power total if its
  data goes stale (lifetime energy is retained so totals never drop).

## Requirements

- A Fronius **GEN24 / Symo GEN24 Plus** with firmware **≥ 1.22.2-1** (TCP meter
  support). Older Symo + Datamanager 2.0 systems use a different (non-SunSpec)
  meter protocol and are **not** supported.
- Inverter data available in Home Assistant as entities.
- Port **502** free on the Home Assistant host.

> **Why one meter?** The Fronius will not poll more than one meter per IP, and
> only on port 502. Rather than juggle extra IP addresses, this add-on presents
> a single combined meter on HA's existing IP. You lose the per-inverter
> breakdown in Solar.web, but total generation is counted correctly.

## Configuration

### Example

```yaml
log_level: info
ha_poll_interval: 5
meter:
  serial: GROWATT_COMBINED
  power_sign: production
  stale_timeout: 120
inverters:
  - name: Growatt Garage
    source: homeassistant
    phases: single
    phase: L1
    entities:
      power: sensor.growatt1_ac_power # any power unit (W/kW) — auto-converted
      energy_total: sensor.growatt1_total_energy # any energy unit (Wh/kWh)
      # optional: voltage, current, frequency (and *_l1/_l2/_l3 for three-phase)
  - name: Growatt Shed
    source: homeassistant
    phases: single
    phase: L2
    entities:
      power: sensor.growatt2_ac_power
      energy_total: sensor.growatt2_total_energy
```

Add as many `inverters` entries as you like - they all feed
the one meter.

### Options reference

| Option                                    | Meaning                                                                                                                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ha_poll_interval`                        | Seconds between HA Core API polls (for `homeassistant` inverters). Default 5.                                                                                                              |
| `inverters[].source`                      | `homeassistant`                                                                                                                                                                            |
| `inverters[].entities`                    | For `homeassistant`: map of metric → entity id. `power` and `energy_total` required; `voltage`/`current`/`frequency` and `*_l1/_l2/_l3` optional. Units auto-detected from each entity.    |
| `meter.serial`                            | Unique, **stable** serial for the virtual meter. Don't reuse your real Smart Meter's serial, and don't change it once Fronius has registered it.                                           |
| `meter.manufacturer` / `meter.model_name` | Advertised identity. Defaults `Fronius` / `Smart Meter 63A`.                                                                                                                               |
| `meter.power_sign`                        | `production` → generation reported as positive watts (what a GEN24 Generator meter expects). `export` → negative watts (classic meter convention). Flip if Solar.web shows the sign wrong. |
| `meter.stale_timeout`                     | Seconds without fresh data before an inverter drops from the live power total. `0` disables.                                                                                               |
| `meter.device_address`                    | SunSpec Common-block device address. Default 240; rarely needs changing.                                                                                                                   |
| `inverters[].phases`                      | `single` or `three`.                                                                                                                                                                       |
| `inverters[].phase`                       | For single-phase: which phase the inverter feeds (`L1`/`L2`/`L3`).                                                                                                                         |
| `inverters[].fields`                      | Override individual field names if your gateway/protocol differs (e.g. `power: AcPower`).                                                                                                  |

## Setting up the meter in Fronius

1. Browse to the inverter's IP → log in as **Technician/Installer**.
2. **Device configuration → Components → Add component → Meter**.
3. Choose **Modbus TCP**, enter **Home Assistant's IP**, port **502**, Modbus
   address **2**.
4. Set it as a **secondary meter**, category **Generator/Producer**.
5. Save; the generation should appear in Solar.web within a minute.

## Troubleshooting

- **Meter registers but shows no values / blank:** make sure you're on the
  latest add-on version (early versions advertised SunSpec model 211, which
  GEN24 firmware won't read; it must be 213). Rebuild the add-on and remove +
  re-add the meter in Fronius so it re-reads the model.
- **Generation is subtracted from PV instead of added (or shows as
  consumption):** switch `meter.power_sign`. A GEN24 Generator meter wants
  `production` (positive); `export` (negative) gets subtracted.
- **Local inverter web UI doesn't show the extra generation:** expected. That UI
  shows the inverter's _own_ PV; external generator meters are aggregated at the
  Solar.web / app level, not the inverter's local PV tile. Check the meters /
  energy-flow view locally.
- **No values at all:** set `log_level: debug` and check for HA API errors (HA source), and
  `… updated; aggregate now …` lines confirming data is flowing.
