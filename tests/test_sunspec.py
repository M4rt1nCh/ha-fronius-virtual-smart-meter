"""Tests for the SunSpec register-image builder.

These lock in the Fronius-compatible layout constants documented in CLAUDE.md
("don't fix these without re-checking the Fronius spec"): total length, model
headers, key field offsets, and the deliberate use of 0.0 (not NaN) for
unpopulated float points.
"""

from __future__ import annotations

import math
import struct

import pytest

from app import sunspec


def _build(**overrides) -> list[int]:
    params = {
        "model_id": sunspec.MODEL_THREE_PHASE,
        "manufacturer": "Fronius",
        "model_name": "Smart Meter 63A",
        "serial": "ABC123",
    }
    params.update(overrides)
    return sunspec.build_base_registers(**params)


def _decode_str(regs: list[int]) -> str:
    raw = b"".join(struct.pack(">H", r) for r in regs)
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


def _decode_f32(regs: list[int], idx: int) -> float:
    return struct.unpack(">f", struct.pack(">HH", regs[idx], regs[idx + 1]))[0]


def test_total_register_count():
    assert sunspec.TOTAL_REGISTERS == 197
    assert len(_build()) == 197


def test_suns_marker():
    regs = _build()
    marker = struct.unpack(">I", struct.pack(">HH", regs[0], regs[1]))[0]
    assert marker == sunspec.SUNS_MARKER == 0x53756E53


def test_common_model_header():
    regs = _build()
    assert regs[2] == sunspec.COMMON_MODEL_ID == 1
    # Fronius variant: length 65, DeviceAddress is the last register (no pad).
    assert regs[3] == sunspec.COMMON_MODEL_LEN == 65


def test_meter_model_header_three_phase():
    regs = _build()
    assert regs[69] == sunspec.MODEL_THREE_PHASE == 213
    assert regs[70] == sunspec.METER_MODEL_LEN == 124


def test_meter_model_header_single_phase():
    # 211 is the documented single-phase model id (production always uses 213).
    regs = _build(model_id=sunspec.MODEL_SINGLE_PHASE)
    assert regs[69] == sunspec.MODEL_SINGLE_PHASE == 211


def test_end_model():
    regs = _build()
    assert regs[195] == sunspec.END_MODEL_ID == 0xFFFF
    assert regs[196] == 0


def test_common_strings_and_device_address():
    regs = _build(
        manufacturer="Acme", model_name="Meter9", serial="SN-42", device_address=200
    )
    assert _decode_str(regs[4:20]) == "Acme"
    assert _decode_str(regs[20:36]) == "Meter9"
    assert _decode_str(regs[52:68]) == "SN-42"
    assert regs[68] == 200  # DeviceAddress, list index 68 == reg 40069


def test_key_field_offsets_match_spec():
    # wire address = BASE_ADDRESS + list index; Modicon reg number = wire + 1.
    assert sunspec.BASE_ADDRESS == 40000
    assert sunspec.FIELD_INDEX["W"] == 97  # reg 40098
    assert sunspec.FIELD_INDEX["TotWhExp"] == 129  # reg 40130
    assert sunspec.FIELD_INDEX["TotWhImp"] == 137  # reg 40138


@pytest.mark.parametrize("value", [0.0, 1.0, -1234.5, 230.0, 999999.0, -0.5])
def test_f32_roundtrip(value):
    hi, lo = sunspec.f32_to_regs(value)
    back = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
    assert back == pytest.approx(value)


def test_none_encodes_as_zero_not_nan():
    hi, lo = sunspec.f32_to_regs(None)
    back = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
    assert back == 0.0
    assert not math.isnan(back)


def test_unpopulated_floats_are_zero():
    regs = _build()
    for name in ("W", "A", "Hz", "TotWhExp", "TotWhImp", "PhV"):
        assert _decode_f32(regs, sunspec.FIELD_INDEX[name]) == 0.0


def test_set_float_writes_readable_value():
    regs = _build()
    sunspec.set_float(regs, "W", -1500.0)
    assert _decode_f32(regs, sunspec.FIELD_INDEX["W"]) == pytest.approx(-1500.0)
