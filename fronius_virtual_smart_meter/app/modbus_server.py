"""The single Modbus TCP server, serving the aggregate meter's SunSpec image.

The Fronius GEN24 connects as Modbus client to the Home Assistant host's IP on
port 502 and walks the SunSpec map via holding-register reads (FC03). It
addresses the SunS marker at wire/PDU address 40000, so the datablock is
anchored there with ``zero_mode=True`` (pymodbus passes the address through
unchanged). Binding 0.0.0.0 serves on whatever IP HA already has - no dedicated
or alias IP needed.
"""

from __future__ import annotations

import asyncio
import logging

from pymodbus.datastore import (
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSparseDataBlock,
)
from pymodbus.server import StartAsyncTcpServer

from . import sunspec
from .meter import Meter

_LOGGER = logging.getLogger(__name__)

MODBUS_PORT = 502
BIND_HOST = "0.0.0.0"


class _MeterDataBlock(ModbusSparseDataBlock):
    """Read-only datablock backed live by the meter's register list."""

    def __init__(self, meter: Meter) -> None:
        self._meter = meter
        super().__init__({sunspec.BASE_ADDRESS: list(meter.registers)})

    def validate(self, address: int, count: int = 1) -> bool:
        # Accept any read so SunSpec base-address probing never errors; reads
        # outside our map return zeros (see getValues).
        return True

    def getValues(self, address: int, count: int = 1) -> list[int]:
        regs = self._meter.registers
        start = address - sunspec.BASE_ADDRESS
        if start < 0 or start + count > len(regs):
            return [0] * count
        return regs[start : start + count]


def build_server_context(meter: Meter) -> ModbusServerContext:
    """Wrap the meter's live registers in a Modbus server context.

    Split out from :func:`serve_meter` so tests can start a server on an
    ephemeral port without the production retry loop (which never returns).
    """
    block = _MeterDataBlock(meter)
    slave = ModbusSlaveContext(hr=block, zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


async def serve_meter(
    meter: Meter, host: str = BIND_HOST, port: int = MODBUS_PORT
) -> None:
    """Start (and keep) the Modbus TCP server. Never returns.

    ``host``/``port`` default to the production bind (0.0.0.0:502); tests
    override them to bind an ephemeral port on localhost without root.
    """
    context = build_server_context(meter)

    while True:
        try:
            _LOGGER.info(
                "Serving aggregate meter '%s' on %s:%d (%d inverter(s))",
                meter.cfg.serial,
                host,
                port,
                len(meter.inverters),
            )
            await StartAsyncTcpServer(context=context, address=(host, port))
        except OSError as exc:
            _LOGGER.error(
                "Cannot bind %s:%d (%s). Is port 502 free on the host? "
                "Retrying in 15s.",
                host,
                port,
                exc,
            )
            await asyncio.sleep(15)
