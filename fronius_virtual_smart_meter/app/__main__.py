"""Entry point: the Modbus server, and the watchdog."""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import ConfigError, load_config
from .meter import Meter
from .modbus_server import serve_meter
from .source import build_sources
from .watchdog import run_watchdog

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def _configure_logging(level: str) -> None:
    # Map Supervisor's extra levels onto stdlib logging.
    mapping = {
        "trace": logging.DEBUG,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "notice": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "fatal": logging.CRITICAL,
    }
    logging.basicConfig(
        level=mapping.get(level.lower(), logging.INFO), format=_LOG_FORMAT
    )


async def _run() -> None:
    config = load_config()
    _configure_logging(config.log_level)
    log = logging.getLogger("fronius_meter_bridge")

    meter = Meter(config.meter, config.inverters)
    sources = build_sources(config, meter)
    log.info(
        "Starting: 1 aggregate meter '%s' from %d inverter(s) [sources=%s]",
        config.meter.serial,
        len(config.inverters),
        sorted(s.name for s in sources),
    )

    # Dispatch the Modbus server, the watchdog, and one task per data source.
    tasks = [
        asyncio.create_task(serve_meter(meter), name="modbus"),
        asyncio.create_task(run_watchdog(meter), name="watchdog"),
    ]
    for source in sources:
        tasks.append(asyncio.create_task(source.run(), name=f"source:{source.name}"))

    # If any long-running task dies, surface it and tear everything down.
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc:
            log.error("Task %s failed: %s", task.get_name(), exc)
            raise exc


def main() -> None:
    try:
        asyncio.run(_run())
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR, format=_LOG_FORMAT)
        logging.getLogger("fronius_meter_bridge").error("Configuration error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
