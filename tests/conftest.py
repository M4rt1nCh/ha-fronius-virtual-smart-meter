"""Shared fixtures and helpers for the test suite.

The app package is imported as ``app.*`` (pytest adds
``fronius_virtual_smart_meter/`` to ``sys.path`` via the ``pythonpath`` setting
in pyproject.toml), so tests can ``from app import ...`` with no install step.
"""

from __future__ import annotations

import struct

import pytest

from app import sunspec
from app.config import InverterConfig, MeterConfig
from app.meter import Meter


def decode_float(regs: list[int], field: str) -> float:
    """Decode a SunSpec float32 point out of a register image by field name."""
    idx = sunspec.FIELD_INDEX[field]
    return struct.unpack(">f", struct.pack(">HH", regs[idx], regs[idx + 1]))[0]


@pytest.fixture
def read_float():
    """Return the :func:`decode_float` helper for asserting on register images."""
    return decode_float


class FakeClock:
    """A controllable stand-in for ``time.monotonic`` used in staleness tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    """Freeze ``app.meter``'s monotonic clock so staleness is deterministic."""
    fake = FakeClock()
    monkeypatch.setattr("app.meter.time.monotonic", fake)
    return fake


def _make_meter_cfg(**overrides) -> MeterConfig:
    params = {
        "serial": "TEST_SERIAL",
        "manufacturer": "Fronius",
        "model_name": "Smart Meter 63A",
        "power_sign": "production",
        "stale_timeout": 120,
        "device_address": 240,
    }
    params.update(overrides)
    return MeterConfig(**params)


def _make_inverter_cfg(**overrides) -> InverterConfig:
    params = {
        "name": "Inv",
        "source": "homeassistant",
        "phases": "single",
        "phase": "L1",
        "entities": {"power": "sensor.p", "energy_total": "sensor.e"},
    }
    params.update(overrides)
    return InverterConfig(**params)


@pytest.fixture
def make_meter_cfg():
    """Factory fixture: build a MeterConfig with sensible defaults + overrides."""
    return _make_meter_cfg


@pytest.fixture
def make_inverter_cfg():
    """Factory fixture: build an InverterConfig with sensible defaults + overrides."""
    return _make_inverter_cfg


@pytest.fixture
def meter_factory():
    """Factory fixture: build a Meter from optional cfg/inverter overrides."""

    def _make(
        meter_cfg: MeterConfig | None = None,
        inverters: list[InverterConfig] | None = None,
    ) -> Meter:
        return Meter(
            meter_cfg or _make_meter_cfg(),
            inverters or [_make_inverter_cfg()],
        )

    return _make
