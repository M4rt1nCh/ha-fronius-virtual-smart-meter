"""Freshness watchdog.

This periodic task recomputes the aggregate so stale inverters drop out of
the live power total (their lifetime energy is retained). Feeding frozen
generation data into the Fronius export-control loop would be unsafe, so
staleness must be acted on actively.
"""

from __future__ import annotations

import asyncio
import logging

from .meter import Meter

_LOGGER = logging.getLogger(__name__)

_CHECK_INTERVAL = 5  # seconds


async def run_watchdog(meter: Meter) -> None:
    stale_state = {id(inv): False for inv in meter.inverters}
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        timeout = meter.cfg.stale_timeout
        for inv in meter.inverters:
            stale = inv.is_stale(timeout)
            was_stale = stale_state[id(inv)]
            if stale and not was_stale:
                _LOGGER.warning(
                    "Inverter '%s' data is stale (no update for >%ss); dropping "
                    "it from the live power total.",
                    inv.cfg.name,
                    timeout,
                )
            elif not stale and was_stale:
                _LOGGER.info("Inverter '%s' data is fresh again.", inv.cfg.name)
            stale_state[id(inv)] = stale
        meter.recompute()
