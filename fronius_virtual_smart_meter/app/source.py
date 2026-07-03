"""Pluggable data-source interface for feeding the aggregate meter.

Home Assistant is currently the only source, but it's conceptually just one of
several (MQTT, a direct inverter poll, ...). A :class:`DataSource` owns the
inverters whose ``cfg.source`` matches its :attr:`name` and, in its :meth:`run`
coroutine, feeds their normalized metrics into the meter via
``meter.apply_inverter_metrics(...)`` for as long as the app runs.

Polling sources loop with sleeps; event-driven sources (e.g. MQTT) await
messages — both simply implement ``run()``.

Adding a source: implement ``DataSource`` (usually in its own module) and call
:func:`register_source` with a builder. Note that valid source *names* are also
enforced at config-parse time by ``config._VALID_SOURCE`` — keep the two in sync.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .config import AppConfig
    from .meter import InverterState, Meter

# Builds one source instance from the app config, the meter, and the inverter
# states that belong to this source (already grouped by build_sources).
SourceBuilder = Callable[["AppConfig", "Meter", "list[InverterState]"], "DataSource"]


class DataSource(ABC):
    """A long-lived provider of inverter metrics for the aggregate meter."""

    #: Matches ``InverterConfig.source`` for the inverters this source owns.
    name: ClassVar[str]

    @abstractmethod
    async def run(self) -> None:
        """Feed owned inverters into the meter until cancelled. Never returns."""


_REGISTRY: dict[str, SourceBuilder] = {}


def register_source(name: str, builder: SourceBuilder) -> None:
    """Register ``builder`` as the factory for the source called ``name``."""
    _REGISTRY[name] = builder


def build_sources(config: AppConfig, meter: Meter) -> list[DataSource]:
    """Instantiate one :class:`DataSource` per source type present in the config.

    Inverters are grouped by ``cfg.source`` so each source gets exactly the
    inverter states it owns.
    """
    # Import built-in sources for their registration side effect. Deferred to
    # avoid a circular import (ha_source imports this module).
    from . import ha_source  # noqa: F401

    groups: dict[str, list[InverterState]] = defaultdict(list)
    for inv in meter.inverters:
        groups[inv.cfg.source].append(inv)

    sources: list[DataSource] = []
    for name, inverters in groups.items():
        builder = _REGISTRY.get(name)
        if builder is None:
            raise ValueError(f"No data source registered for '{name}'")
        sources.append(builder(config, meter, inverters))
    return sources
