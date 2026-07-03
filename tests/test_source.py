"""Tests for the pluggable data-source layer (source.py)."""

from __future__ import annotations

import pytest

from app.config import AppConfig
from app.ha_source import HomeAssistantSource
from app.source import DataSource, build_sources


def _config(make_meter_cfg, inverters):
    return AppConfig(
        log_level="info",
        meter=make_meter_cfg(),
        inverters=inverters,
        ha_poll_interval=5,
    )


def test_build_sources_returns_one_ha_source(
    meter_factory, make_inverter_cfg, make_meter_cfg
):
    invs = [make_inverter_cfg(name="A"), make_inverter_cfg(name="B")]
    meter = meter_factory(inverters=invs)
    config = _config(make_meter_cfg, invs)

    sources = build_sources(config, meter)

    assert len(sources) == 1
    (source,) = sources
    assert isinstance(source, DataSource)
    assert isinstance(source, HomeAssistantSource)
    assert source.name == "homeassistant"
    # It owns both HA inverter states.
    assert source._inverters == meter.inverters


def test_build_sources_uses_poll_interval(
    meter_factory, make_inverter_cfg, make_meter_cfg
):
    invs = [make_inverter_cfg()]
    meter = meter_factory(inverters=invs)
    config = _config(make_meter_cfg, invs)
    config.ha_poll_interval = 17

    (source,) = build_sources(config, meter)
    assert source._poll_interval == 17


def test_build_sources_unknown_source_raises(
    meter_factory, make_inverter_cfg, make_meter_cfg
):
    inv = make_inverter_cfg()
    meter = meter_factory(inverters=[inv])
    # Bypass config validation to simulate an unregistered source reaching runtime.
    meter.inverters[0].cfg.source = "mqtt"
    config = _config(make_meter_cfg, [inv])

    with pytest.raises(ValueError, match="No data source registered for 'mqtt'"):
        build_sources(config, meter)
