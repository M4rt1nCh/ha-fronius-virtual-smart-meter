"""Tests for the Home Assistant source's unit normalization.

These exercise the pure helpers (``_normalize`` / ``_metrics_for``); the network
polling loop itself is left to the integration path.
"""

from __future__ import annotations

import pytest

from app import ha_source as ha
from app.config import InverterConfig
from app.meter import InverterState


def _state(value, unit=None):
    attrs = {"unit_of_measurement": unit} if unit is not None else {}
    return {"state": str(value), "attributes": attrs}


@pytest.mark.parametrize(
    "key,value,unit,expected",
    [
        ("power", "1000", "W", 1000.0),
        ("power", "1.5", "kW", 1500.0),
        ("power", "0.001", "MW", 1000.0),
        ("power_l2", "2", "kW", 2000.0),
        ("energy_total", "5000", "Wh", 5.0),
        ("energy_total", "5", "kWh", 5.0),
        ("energy_total", "0.005", "MWh", 5.0),
        ("voltage", "230", "V", 230.0),
        ("frequency", "50", "Hz", 50.0),
    ],
)
def test_normalize_units(key, value, unit, expected):
    assert ha._normalize(key, _state(value, unit)) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["unknown", "unavailable", "none", "", "not_a_number"])
def test_normalize_unusable_returns_none(raw):
    assert ha._normalize("power", _state(raw, "W")) is None


def test_power_without_unit_passes_through():
    # Missing unit -> multiplier 1.0 (value used as-is).
    assert ha._normalize("power", _state("42")) == pytest.approx(42.0)


def test_energy_without_unit_passes_through():
    assert ha._normalize("energy_total", _state("7")) == pytest.approx(7.0)


def _inv_state(entities):
    cfg = InverterConfig(
        name="A",
        source="homeassistant",
        phases="single",
        phase="L1",
        entities=entities,
    )
    return InverterState(cfg)


def test_metrics_for_maps_and_converts_entities():
    inv = _inv_state({"power": "sensor.p", "energy_total": "sensor.e"})
    states = {
        "sensor.p": _state("1.5", "kW"),
        "sensor.e": _state("10", "kWh"),
    }
    assert ha._metrics_for(inv, states) == {"power": 1500.0, "energy_total": 10.0}


def test_metrics_for_skips_missing_entity():
    inv = _inv_state({"power": "sensor.p", "energy_total": "sensor.missing"})
    states = {"sensor.p": _state("1000", "W")}
    assert ha._metrics_for(inv, states) == {"power": 1000.0}


def test_metrics_for_skips_unusable_value():
    inv = _inv_state({"power": "sensor.p", "energy_total": "sensor.e"})
    states = {
        "sensor.p": _state("unavailable", "W"),
        "sensor.e": _state("10", "kWh"),
    }
    assert ha._metrics_for(inv, states) == {"energy_total": 10.0}
