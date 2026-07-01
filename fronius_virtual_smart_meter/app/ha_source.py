"""Home Assistant entity data source.

Polls the Home Assistant Core API (proxied through the Supervisor) for the
entity states configured per inverter, normalizes their units to W / kWh / V /
A / Hz, and feeds them into the aggregate meter. This needs no data provider / broker -
only ``homeassistant_api: true`` in config.yaml, which gives the add-on a
``SUPERVISOR_TOKEN`` to call ``http://supervisor/core/api``.

Units are read from each entity's ``unit_of_measurement`` attribute and
converted, so it doesn't matter whether the source integration reports W or kW,
Wh or kWh, etc.
"""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

from .meter import InverterState, Meter

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "http://supervisor/core/api"
_UNUSABLE = {"unknown", "unavailable", "none", ""}

# Multipliers to normalize a value to the meter's canonical unit.
_POWER_TO_W = {"w": 1.0, "kw": 1000.0, "mw": 1_000_000.0}
_ENERGY_TO_KWH = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}

# Which entity-map keys are power vs energy (the rest pass through unscaled).
_POWER_KEYS = {"power", "power_l1", "power_l2", "power_l3"}
_ENERGY_KEYS = {"energy_total"}


async def run_ha_poller(meter: Meter, poll_interval: int) -> None:
    """Poll HA entity states for all homeassistant-source inverters forever."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        _LOGGER.error(
            "SUPERVISOR_TOKEN is not set; cannot read Home Assistant entities. "
            "Is 'homeassistant_api: true' set in the add-on config?"
        )
        return

    ha_inverters = [i for i in meter.inverters if i.cfg.source == "homeassistant"]
    headers = {"Authorization": f"Bearer {token}"}
    interval = max(1, poll_interval)

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            try:
                states = await _fetch_states(session)
                for inv in ha_inverters:
                    metrics = _metrics_for(inv, states)
                    meter.apply_inverter_metrics(inv, metrics)
            except aiohttp.ClientError as exc:
                _LOGGER.warning("Home Assistant API request failed: %s", exc)
            await asyncio.sleep(interval)


async def _fetch_states(session: aiohttp.ClientSession) -> dict[str, dict]:
    """Return {entity_id: state_object} for all HA entities."""
    async with session.get(f"{_BASE_URL}/states", timeout=10) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return {item["entity_id"]: item for item in data}


def _metrics_for(inv: InverterState, states: dict[str, dict]) -> dict:
    metrics: dict[str, float] = {}
    for key, entity_id in inv.cfg.entities.items():
        state = states.get(entity_id)
        if state is None:
            _LOGGER.warning("%s: entity '%s' not found", inv.cfg.name, entity_id)
            continue
        value = _normalize(key, state)
        if value is not None:
            metrics[key] = value
    return metrics


def _normalize(key: str, state: dict) -> float | None:
    raw = str(state.get("state", "")).strip().lower()
    if raw in _UNUSABLE:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None

    unit = (
        str(state.get("attributes", {}).get("unit_of_measurement", "")).strip().lower()
    )
    if key in _POWER_KEYS:
        return value * _POWER_TO_W.get(unit, 1.0)
    if key in _ENERGY_KEYS:
        return value * _ENERGY_TO_KWH.get(unit, 1.0)
    return value
