"""Load and validate app configuration.

Configuration comes from:
  * ``/data/options.json`` - the app options written by the Supervisor.
  * ``SUPERVISOR_TOKEN`` - injected by the Supervisor; used by the
    ``homeassistant`` source to read entity states from the HA Core API.

The bridge exposes a SINGLE virtual SunSpec meter (on the Home Assistant host's
own IP, port 502) that aggregates any number of inverters. Each inverter is one
data source (Home Assistant entities) and their power/energy are summed into the
one meter.

For local development outside Home Assistant, set ``OPTIONS_FILE`` to a custom
path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

DEFAULT_OPTIONS_FILE = "/data/options.json"

_VALID_PHASES = {"single", "three"}
_VALID_PHASE = {"L1", "L2", "L3"}
_VALID_SIGN = {"export", "production"}
_VALID_SOURCE = {"homeassistant"}

# Metric keys the meter understands (also the valid keys for an HA entity map).
_ENTITY_KEYS = (
    "power",
    "energy_total",
    "voltage",
    "current",
    "frequency",
    "power_l1",
    "power_l2",
    "power_l3",
    "current_l1",
    "current_l2",
    "current_l3",
    "voltage_l1",
    "voltage_l2",
    "voltage_l3",
)


class ConfigError(Exception):
    """Raised when the app configuration is invalid."""


@dataclass
class InverterConfig:
    """One data source feeding the aggregate meter."""

    name: str
    source: str
    phases: str  # "single" | "three"
    phase: str  # "L1" | "L2" | "L3" (used when phases == "single")
    entities: dict[str, str] = field(default_factory=dict)  # homeassistant source


@dataclass
class MeterConfig:
    """Identity and behaviour of the single aggregate meter."""

    serial: str
    manufacturer: str
    model_name: str
    power_sign: str  # "export" | "production"
    stale_timeout: int
    device_address: int = 240


@dataclass
class AppConfig:
    log_level: str
    meter: MeterConfig
    inverters: list[InverterConfig]
    ha_poll_interval: int

    @property
    def uses_homeassistant(self) -> bool:
        return any(i.source == "homeassistant" for i in self.inverters)


def _inverter_from_options(idx: int, raw: dict) -> InverterConfig:
    def require(key: str) -> str:
        value = str(raw.get(key, "")).strip()
        if not value:
            raise ConfigError(f"inverters[{idx}]: missing required field '{key}'")
        return value

    source = raw.get("source", "homeassistant")
    if source not in _VALID_SOURCE:
        raise ConfigError(f"inverters[{idx}].source must be one of {_VALID_SOURCE}")

    phases = raw.get("phases", "single")
    if phases not in _VALID_PHASES:
        raise ConfigError(f"inverters[{idx}].phases must be one of {_VALID_PHASES}")

    phase = raw.get("phase", "L1")
    if phase not in _VALID_PHASE:
        raise ConfigError(f"inverters[{idx}].phase must be one of {_VALID_PHASE}")

    name = require("name")

    # homeassistant source
    entities = {k: str(v).strip() for k, v in (raw.get("entities") or {}).items() if v}
    bad = set(entities) - set(_ENTITY_KEYS)
    if bad:
        raise ConfigError(f"inverters[{idx}].entities: unknown keys {sorted(bad)}")
    if not entities.get("power") or not entities.get("energy_total"):
        raise ConfigError(
            f"inverters[{idx}]: source 'homeassistant' requires 'power' and "
            "'energy_total' entity ids under 'entities'."
        )
    return InverterConfig(
        name=name,
        source=source,
        phases=phases,
        phase=phase,
        entities=entities,
    )


def _meter_from_options(raw: dict) -> MeterConfig:
    serial = str(raw.get("serial", "")).strip()
    if not serial:
        raise ConfigError("meter.serial is required and must be unique/stable.")

    power_sign = raw.get("power_sign", "export")
    if power_sign not in _VALID_SIGN:
        raise ConfigError(f"meter.power_sign must be one of {_VALID_SIGN}")

    return MeterConfig(
        serial=serial,
        manufacturer=str(raw.get("manufacturer") or "Fronius"),
        model_name=str(raw.get("model_name") or "Smart Meter 63A"),
        power_sign=power_sign,
        stale_timeout=int(raw.get("stale_timeout", 120)),
        device_address=int(raw.get("device_address", 240)),
    )


def load_config() -> AppConfig:
    options_file = os.environ.get("OPTIONS_FILE", DEFAULT_OPTIONS_FILE)
    try:
        with open(options_file, encoding="utf-8") as handle:
            options = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Options file not found: {options_file}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Options file is not valid JSON: {exc}") from exc

    raw_inverters = options.get("inverters") or []
    if not raw_inverters:
        raise ConfigError("No inverters configured. Add at least one inverter.")

    inverters = [_inverter_from_options(i, m) for i, m in enumerate(raw_inverters)]

    config = AppConfig(
        log_level=str(options.get("log_level", "info")),
        meter=_meter_from_options(options.get("meter") or {}),
        inverters=inverters,
        ha_poll_interval=int(options.get("ha_poll_interval", 5)),
    )
    return config
