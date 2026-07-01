"""Tests for the aggregation logic in meter.py.

Every assertion reads the resulting SunSpec float points back out of the live
register image, so these also exercise the meter -> sunspec round-trip.
"""

from __future__ import annotations

import pytest


def test_single_phase_production_positive(meter_factory, read_float):
    meter = meter_factory()
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1000.0, "energy_total": 5.0}
    )
    assert read_float(meter.registers, "W") == pytest.approx(1000.0)
    assert read_float(meter.registers, "WphA") == pytest.approx(1000.0)
    assert read_float(meter.registers, "WphB") == 0.0
    assert read_float(meter.registers, "WphC") == 0.0
    assert read_float(meter.registers, "TotWhExp") == pytest.approx(5000.0)


def test_export_sign_is_negative(meter_factory, make_meter_cfg, read_float):
    meter = meter_factory(meter_cfg=make_meter_cfg(power_sign="export"))
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1000.0, "energy_total": 0.0}
    )
    assert read_float(meter.registers, "W") == pytest.approx(-1000.0)
    assert read_float(meter.registers, "WphA") == pytest.approx(-1000.0)


def test_two_inverters_summed_on_same_phase(
    meter_factory, make_inverter_cfg, read_float
):
    invs = [
        make_inverter_cfg(name="A", phase="L1"),
        make_inverter_cfg(name="B", phase="L1"),
    ]
    meter = meter_factory(inverters=invs)
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1000.0, "energy_total": 1.0}
    )
    meter.apply_inverter_metrics(
        meter.inverters[1], {"power": 500.0, "energy_total": 2.0}
    )
    assert read_float(meter.registers, "WphA") == pytest.approx(1500.0)
    assert read_float(meter.registers, "W") == pytest.approx(1500.0)
    assert read_float(meter.registers, "TotWhExp") == pytest.approx(3000.0)


def test_single_phase_inverters_land_on_their_phase(
    meter_factory, make_inverter_cfg, read_float
):
    invs = [
        make_inverter_cfg(name="A", phase="L1"),
        make_inverter_cfg(name="B", phase="L2"),
        make_inverter_cfg(name="C", phase="L3"),
    ]
    meter = meter_factory(inverters=invs)
    for inv_state, watts in zip(meter.inverters, (100.0, 200.0, 300.0), strict=True):
        meter.apply_inverter_metrics(inv_state, {"power": watts, "energy_total": 0.0})
    assert read_float(meter.registers, "WphA") == pytest.approx(100.0)
    assert read_float(meter.registers, "WphB") == pytest.approx(200.0)
    assert read_float(meter.registers, "WphC") == pytest.approx(300.0)
    assert read_float(meter.registers, "W") == pytest.approx(600.0)


def test_three_phase_inverter_per_phase(meter_factory, make_inverter_cfg, read_float):
    inv = make_inverter_cfg(phases="three")
    meter = meter_factory(inverters=[inv])
    meter.apply_inverter_metrics(
        meter.inverters[0],
        {
            "power_l1": 100.0,
            "power_l2": 200.0,
            "power_l3": 300.0,
            "current_l1": 1.0,
            "current_l2": 2.0,
            "current_l3": 3.0,
            "voltage_l1": 230.0,
            "voltage_l2": 231.0,
            "voltage_l3": 232.0,
            "frequency": 50.0,
            "energy_total": 10.0,
        },
    )
    assert read_float(meter.registers, "WphA") == pytest.approx(100.0)
    assert read_float(meter.registers, "WphB") == pytest.approx(200.0)
    assert read_float(meter.registers, "WphC") == pytest.approx(300.0)
    assert read_float(meter.registers, "W") == pytest.approx(600.0)
    assert read_float(meter.registers, "AphA") == pytest.approx(1.0)
    assert read_float(meter.registers, "A") == pytest.approx(6.0)
    assert read_float(meter.registers, "PhVphA") == pytest.approx(230.0)
    assert read_float(meter.registers, "Hz") == pytest.approx(50.0)
    assert read_float(meter.registers, "TotWhExp") == pytest.approx(10000.0)


def test_voltage_and_frequency_are_averaged(
    meter_factory, make_inverter_cfg, read_float
):
    invs = [
        make_inverter_cfg(name="A", phase="L1"),
        make_inverter_cfg(name="B", phase="L1"),
    ]
    meter = meter_factory(inverters=invs)
    meter.apply_inverter_metrics(
        meter.inverters[0],
        {"power": 0.0, "energy_total": 0.0, "voltage": 230.0, "frequency": 50.0},
    )
    meter.apply_inverter_metrics(
        meter.inverters[1],
        {"power": 0.0, "energy_total": 0.0, "voltage": 240.0, "frequency": 60.0},
    )
    assert read_float(meter.registers, "PhVphA") == pytest.approx(235.0)
    assert read_float(meter.registers, "PhV") == pytest.approx(235.0)
    assert read_float(meter.registers, "Hz") == pytest.approx(55.0)


def test_stale_inverter_drops_power_but_keeps_energy(
    clock, meter_factory, make_meter_cfg, read_float
):
    meter = meter_factory(meter_cfg=make_meter_cfg(stale_timeout=10))
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1000.0, "energy_total": 5.0}
    )
    assert read_float(meter.registers, "W") == pytest.approx(1000.0)

    clock.advance(100)  # now well past the 10s stale timeout
    meter.recompute()
    assert read_float(meter.registers, "W") == 0.0  # power drops
    assert read_float(meter.registers, "TotWhExp") == pytest.approx(5000.0)  # kept


def test_stale_timeout_zero_never_goes_stale(
    clock, meter_factory, make_meter_cfg, read_float
):
    meter = meter_factory(meter_cfg=make_meter_cfg(stale_timeout=0))
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1000.0, "energy_total": 5.0}
    )
    clock.advance(10_000)
    meter.recompute()
    assert read_float(meter.registers, "W") == pytest.approx(1000.0)
