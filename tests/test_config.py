"""Tests for options.json parsing and validation."""

from __future__ import annotations

import copy
import json

import pytest

from app.config import ConfigError, load_config

_VALID = {
    "log_level": "debug",
    "ha_poll_interval": 10,
    "meter": {
        "serial": "SN1",
        "manufacturer": "Acme",
        "model_name": "Meter9",
        "power_sign": "production",
        "stale_timeout": 60,
        "device_address": 200,
    },
    "inverters": [
        {
            "name": "A",
            "source": "homeassistant",
            "phases": "single",
            "phase": "L1",
            "entities": {"power": "sensor.p", "energy_total": "sensor.e"},
        }
    ],
}


def _load(tmp_path, monkeypatch, options) -> object:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(options))
    monkeypatch.setenv("OPTIONS_FILE", str(path))
    return load_config()


def _valid(**meter_or_top):
    """A deep copy of the valid options, optionally mutated at the top level."""
    opts = copy.deepcopy(_VALID)
    opts.update(meter_or_top)
    return opts


def test_valid_config(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, _valid())
    assert cfg.log_level == "debug"
    assert cfg.ha_poll_interval == 10
    assert cfg.meter.serial == "SN1"
    assert cfg.meter.manufacturer == "Acme"
    assert cfg.meter.power_sign == "production"
    assert cfg.meter.device_address == 200
    assert len(cfg.inverters) == 1
    assert cfg.inverters[0].entities["power"] == "sensor.p"
    assert cfg.uses_homeassistant is True


def test_defaults_applied(tmp_path, monkeypatch):
    opts = {
        "meter": {"serial": "SN1"},
        "inverters": copy.deepcopy(_VALID["inverters"]),
    }
    cfg = _load(tmp_path, monkeypatch, opts)
    assert cfg.meter.manufacturer == "Fronius"
    assert cfg.meter.model_name == "Smart Meter 63A"
    assert cfg.meter.device_address == 240
    assert cfg.meter.stale_timeout == 120
    assert cfg.meter.power_sign == "export"  # default sign
    assert cfg.ha_poll_interval == 5
    assert cfg.log_level == "info"


def test_no_inverters_rejected(tmp_path, monkeypatch):
    with pytest.raises(ConfigError, match="No inverters"):
        _load(tmp_path, monkeypatch, _valid(inverters=[]))


def test_missing_power_entity_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["inverters"][0]["entities"] = {"energy_total": "sensor.e"}
    with pytest.raises(ConfigError, match="requires 'power'"):
        _load(tmp_path, monkeypatch, opts)


def test_missing_energy_entity_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["inverters"][0]["entities"] = {"power": "sensor.p"}
    with pytest.raises(ConfigError, match="energy_total"):
        _load(tmp_path, monkeypatch, opts)


def test_unknown_entity_key_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["inverters"][0]["entities"]["bogus"] = "sensor.x"
    with pytest.raises(ConfigError, match="unknown keys"):
        _load(tmp_path, monkeypatch, opts)


def test_missing_serial_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["meter"].pop("serial")
    with pytest.raises(ConfigError, match="serial"):
        _load(tmp_path, monkeypatch, opts)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("source", "mqtt", "source"),
        ("phases", "double", "phases"),
        ("phase", "L4", "phase"),
    ],
)
def test_bad_inverter_enums_rejected(tmp_path, monkeypatch, field, value, match):
    opts = _valid()
    opts["inverters"][0][field] = value
    with pytest.raises(ConfigError, match=match):
        _load(tmp_path, monkeypatch, opts)


def test_bad_power_sign_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["meter"]["power_sign"] = "sideways"
    with pytest.raises(ConfigError, match="power_sign"):
        _load(tmp_path, monkeypatch, opts)


def test_missing_name_rejected(tmp_path, monkeypatch):
    opts = _valid()
    opts["inverters"][0].pop("name")
    with pytest.raises(ConfigError, match="name"):
        _load(tmp_path, monkeypatch, opts)


def test_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONS_FILE", str(tmp_path / "does_not_exist.json"))
    with pytest.raises(ConfigError, match="not found"):
        load_config()


def test_invalid_json(tmp_path, monkeypatch):
    path = tmp_path / "options.json"
    path.write_text("{not valid json")
    monkeypatch.setenv("OPTIONS_FILE", str(path))
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config()
