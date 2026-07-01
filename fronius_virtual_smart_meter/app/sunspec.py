"""Build the SunSpec holding-register image of a virtual Fronius smart meter.

The Fronius GEN24 walks a SunSpec map starting at register 40001 (wire/PDU
address 40000, 0x9C40). The map this module produces matches the well-known,
GEN24-tested Fronius float meter layout:

    reg 40001-40002  SunS marker (0x53756E53)
    reg 40003        Common model ID = 1
    reg 40004        Common model length = 65   (Fronius variant, no trailing pad)
    reg 40005-40069  Common model body (Mn, Md, Opt, Vr, SN, DA)
    reg 40070        Meter model ID (213 three-phase / 211 single-phase, float)
    reg 40071        Meter model length = 124
    reg 40072-40195  Meter model body (61 float32 points + Evt bitfield32)
    reg 40196-40197  End model (0xFFFF, 0x0000)

All values are big-endian, most-significant-word first. Unimplemented float
points carry the SunSpec "not implemented" NaN (0x7FC00000).

Offsets in this module are 0-based indices into the register list returned by
:func:`build_base_registers`. The list begins at ``BASE_ADDRESS``.
"""

from __future__ import annotations

import struct

# Wire/PDU address of the first register (the SunS marker high word).
# Register 40001 in 1-based Modicon notation == wire address 40000.
BASE_ADDRESS = 40000

SUNS_MARKER = 0x53756E53
NOT_IMPL_FLOAT = 0x7FC00000
NOT_IMPL_UINT16 = 0x8000

COMMON_MODEL_ID = 1
COMMON_MODEL_LEN = 65  # Fronius variant: DA is the last register, no pad.
END_MODEL_ID = 0xFFFF

MODEL_SINGLE_PHASE = 211
MODEL_THREE_PHASE = 213
METER_MODEL_LEN = 124

# --- list-index offsets (relative to BASE_ADDRESS) of the fixed blocks -------
_COMMON_ID_OFF = 2
_COMMON_BODY_OFF = 4  # Mn starts here
_METER_ID_OFF = 69  # == reg 40070
_METER_BODY_OFF = 71  # == reg 40072, first float point (meter-relative offset 2)
_END_OFF = 195  # == reg 40196

TOTAL_REGISTERS = 197

# Ordered float32 points of meter models 211/212/213. Index i sits at
# meter-relative offset 2 + 2*i, i.e. list index _METER_BODY_OFF + 2*i.
_METER_FLOAT_POINTS = [
    "A",
    "AphA",
    "AphB",
    "AphC",
    "PhV",
    "PhVphA",
    "PhVphB",
    "PhVphC",
    "PPV",
    "PPVphAB",
    "PPVphBC",
    "PPVphCA",
    "Hz",
    "W",
    "WphA",
    "WphB",
    "WphC",
    "VA",
    "VAphA",
    "VAphB",
    "VAphC",
    "VAR",
    "VARphA",
    "VARphB",
    "VARphC",
    "PF",
    "PFphA",
    "PFphB",
    "PFphC",
    "TotWhExp",
    "TotWhExpPhA",
    "TotWhExpPhB",
    "TotWhExpPhC",
    "TotWhImp",
    "TotWhImpPhA",
    "TotWhImpPhB",
    "TotWhImpPhC",
    "TotVAhExp",
    "TotVAhExpPhA",
    "TotVAhExpPhB",
    "TotVAhExpPhC",
    "TotVAhImp",
    "TotVAhImpPhA",
    "TotVAhImpPhB",
    "TotVAhImpPhC",
    "TotVArhImpQ1",
    "TotVArhImpQ1PhA",
    "TotVArhImpQ1PhB",
    "TotVArhImpQ1PhC",
    "TotVArhImpQ2",
    "TotVArhImpQ2PhA",
    "TotVArhImpQ2PhB",
    "TotVArhImpQ2PhC",
    "TotVArhExpQ3",
    "TotVArhExpQ3PhA",
    "TotVArhExpQ3PhB",
    "TotVArhExpQ3PhC",
    "TotVArhExpQ4",
    "TotVArhExpQ4PhA",
    "TotVArhExpQ4PhB",
    "TotVArhExpQ4PhC",
]  # 61 points -> 122 registers; + Evt bitfield32 (2 regs) = 124 = METER_MODEL_LEN

# field name -> list index (relative to BASE_ADDRESS) of its high word
FIELD_INDEX = {
    name: _METER_BODY_OFF + 2 * i for i, name in enumerate(_METER_FLOAT_POINTS)
}


def f32_to_regs(value: float | None) -> list[int]:
    """Encode a float32 into [high_word, low_word] (MSW first).

    Missing values (None) are encoded as 0.0 rather than the SunSpec NaN, which
    Fronius firmware rejects as an invalid reading.
    """
    if value is None:
        value = 0.0
    hi, lo = struct.unpack(">HH", struct.pack(">f", float(value)))
    return [hi, lo]


def u32_to_regs(value: int) -> list[int]:
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def _str_to_regs(text: str, registers: int) -> list[int]:
    raw = text.encode("ascii", "replace")[: registers * 2]
    raw = raw + b"\x00" * (registers * 2 - len(raw))
    return list(struct.unpack(">" + "H" * registers, raw))


def build_base_registers(
    *,
    model_id: int,
    manufacturer: str,
    model_name: str,
    serial: str,
    version: str = "1.0",
    device_address: int = 240,
) -> list[int]:
    """Build the full register image with all meter floats zeroed.

    Callers patch live values in with :func:`set_float`. We use 0.0 (not the
    SunSpec "not implemented" NaN) for unpopulated points: a real Fronius Smart
    Meter always returns valid floats, and Fronius firmware treats NaN as an
    invalid reading and shows no values.
    """
    regs = [0] * TOTAL_REGISTERS

    # SunS marker
    regs[0], regs[1] = u32_to_regs(SUNS_MARKER)

    # Common model
    regs[_COMMON_ID_OFF] = COMMON_MODEL_ID
    regs[_COMMON_ID_OFF + 1] = COMMON_MODEL_LEN
    off = _COMMON_BODY_OFF
    for text, size in (
        (manufacturer, 16),
        (model_name, 16),
        ("", 8),  # Options
        (version, 8),
        (serial, 16),
    ):
        regs[off : off + size] = _str_to_regs(text, size)
        off += size
    regs[off] = device_address & 0xFFFF  # DA, list index 68 / reg 40069

    # Meter model header
    regs[_METER_ID_OFF] = model_id
    regs[_METER_ID_OFF + 1] = METER_MODEL_LEN

    # Meter model body: float points default to 0.0 (see docstring).
    for name in _METER_FLOAT_POINTS:
        idx = FIELD_INDEX[name]
        regs[idx], regs[idx + 1] = f32_to_regs(0.0)
    # Evt bitfield32 (meter-relative offset 124) -> list index 193, left as 0.

    # End model
    regs[_END_OFF] = END_MODEL_ID
    regs[_END_OFF + 1] = 0x0000

    return regs


def set_float(regs: list[int], field: str, value: float | None) -> None:
    """Write a float32 meter point into the register image in place."""
    idx = FIELD_INDEX[field]
    regs[idx], regs[idx + 1] = f32_to_regs(value)
