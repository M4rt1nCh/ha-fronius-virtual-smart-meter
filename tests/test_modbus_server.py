"""Tests for the Modbus server.

The datablock is tested directly (fast, no socket, no root). A single opt-in
integration test starts a real Modbus TCP server on an ephemeral localhost port
and reads it back exactly as the Fronius would -- guarding against pymodbus API
churn. Run just it with ``pytest -m integration``; skip it with
``pytest -m "not integration"``.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import struct

import pytest

from app import sunspec
from app.modbus_server import _MeterDataBlock, build_server_context


def _marker(regs: list[int]) -> int:
    return struct.unpack(">I", struct.pack(">HH", regs[0], regs[1]))[0]


def _f32(regs: list[int], idx: int) -> float:
    return struct.unpack(">f", struct.pack(">HH", regs[idx], regs[idx + 1]))[0]


def test_datablock_returns_suns_marker(meter_factory):
    block = _MeterDataBlock(meter_factory())
    # +1 because ModbusDeviceContext adds 1 to the wire address before calling getValues.
    regs = block.getValues(sunspec.BASE_ADDRESS + 1, 2)
    assert _marker(regs) == sunspec.SUNS_MARKER


def test_datablock_validate_accepts_any_address(meter_factory):
    block = _MeterDataBlock(meter_factory())
    # Accept anything so SunSpec base-address probing never errors.
    assert block.validate(0, 1) is True
    assert block.validate(sunspec.BASE_ADDRESS, sunspec.TOTAL_REGISTERS) is True


def test_datablock_out_of_range_returns_zeros(meter_factory):
    block = _MeterDataBlock(meter_factory())
    # +1 offset mirrors what ModbusDeviceContext passes to getValues.
    regs = block.getValues(sunspec.BASE_ADDRESS + sunspec.TOTAL_REGISTERS + 1, 4)
    assert regs == [0, 0, 0, 0]


def test_datablock_reflects_live_updates(meter_factory):
    meter = meter_factory()
    block = _MeterDataBlock(meter)
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 1234.0, "energy_total": 1.0}
    )
    # +1 offset mirrors what ModbusDeviceContext passes to getValues.
    regs = block.getValues(sunspec.BASE_ADDRESS + 1, sunspec.TOTAL_REGISTERS)
    assert _f32(regs, sunspec.FIELD_INDEX["W"]) == pytest.approx(1234.0)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.integration
def test_modbus_tcp_roundtrip(meter_factory):
    from pymodbus.client import ModbusTcpClient
    from pymodbus.server import ServerAsyncStop, StartAsyncTcpServer

    meter = meter_factory()
    meter.apply_inverter_metrics(
        meter.inverters[0], {"power": 2500.0, "energy_total": 7.0}
    )
    port = _free_port()

    def _read() -> list[int]:
        client = ModbusTcpClient("127.0.0.1", port=port)
        assert client.connect()
        try:
            regs: list[int] = []
            offset = 0
            total = sunspec.TOTAL_REGISTERS
            # Chunk to 125 registers per request, exactly like the Fronius.
            while offset < total:
                count = min(125, total - offset)
                rr = client.read_holding_registers(
                    address=sunspec.BASE_ADDRESS + offset, count=count, device_id=1
                )
                assert not rr.isError(), rr
                regs += rr.registers
                offset += count
            return regs
        finally:
            client.close()

    async def _run() -> list[int]:
        # Drive StartAsyncTcpServer directly (not serve_meter, whose retry loop
        # never returns) with the same context the production path builds. The
        # sync client runs in a worker thread so it can't deadlock the async
        # server sharing this event loop (see CLAUDE.md).
        context = build_server_context(meter)
        server = asyncio.create_task(
            StartAsyncTcpServer(context=context, address=("127.0.0.1", port))
        )
        await asyncio.sleep(0.4)  # let the server bind
        try:
            return await asyncio.to_thread(_read)
        finally:
            await ServerAsyncStop()
            server.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server

    regs = asyncio.run(_run())
    assert _marker(regs) == sunspec.SUNS_MARKER
    assert _f32(regs, sunspec.FIELD_INDEX["W"]) == pytest.approx(2500.0)
    assert _f32(regs, sunspec.FIELD_INDEX["TotWhExp"]) == pytest.approx(7000.0)
