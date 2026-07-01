"""The single aggregate meter and its per-inverter source states.

Each inverter relies on Home Assistant entities; its parsed values are held in an
``InverterState``. The :class:`Meter` sums all inverter states into one SunSpec
register image that the Fronius reads as a single meter:

  * power / current  -> summed per phase (stale inverters contribute 0)
  * energy           -> summed lifetime kWh -> Wh in TotWhExp (always counted,
                        even when an inverter is idle/stale, so totals never drop)
  * voltage / Hz     -> averaged across the inverters reporting them
"""

from __future__ import annotations

import logging
import time

from . import sunspec
from .config import InverterConfig, MeterConfig

_LOGGER = logging.getLogger(__name__)

_PHASES = ("L1", "L2", "L3")
_PHASE_SUFFIX = {"L1": "phA", "L2": "phB", "L3": "phC"}


class InverterState:
    """Latest normalized values parsed from one inverter's Home Assistant metrics."""

    def __init__(self, cfg: InverterConfig) -> None:
        self.cfg = cfg
        self.last_update: float | None = None
        self.energy_kwh: float = 0.0  # lifetime; retained across stale periods
        self.frequency: float | None = None
        self.phase_w = dict.fromkeys(_PHASES, 0.0)
        self.phase_a = dict.fromkeys(_PHASES, 0.0)
        self.phase_v: dict[str, float | None] = dict.fromkeys(_PHASES)

    def apply_metrics(self, metrics: dict) -> None:
        """Apply already-normalized metrics (W, kWh, V, A, Hz) to this state."""

        def get(key):
            return _num(metrics.get(key))

        energy = get("energy_total")
        if energy is not None:
            self.energy_kwh = energy
        self.frequency = get("frequency")

        self.phase_w = dict.fromkeys(_PHASES, 0.0)
        self.phase_a = dict.fromkeys(_PHASES, 0.0)
        self.phase_v = dict.fromkeys(_PHASES)

        if self.cfg.phases == "three":
            for phase, n in (("L1", 1), ("L2", 2), ("L3", 3)):
                self.phase_w[phase] = get(f"power_l{n}") or 0.0
                self.phase_a[phase] = get(f"current_l{n}") or 0.0
                self.phase_v[phase] = get(f"voltage_l{n}")
        else:
            phase = self.cfg.phase
            self.phase_w[phase] = get("power") or 0.0
            self.phase_a[phase] = get("current") or 0.0
            self.phase_v[phase] = get("voltage")

        self.last_update = time.monotonic()

    def is_stale(self, timeout: int) -> bool:
        if timeout <= 0:
            return False
        if self.last_update is None:
            return True
        return (time.monotonic() - self.last_update) > timeout


class Meter:
    """One SunSpec meter image aggregating all inverter states."""

    def __init__(self, cfg: MeterConfig, inverters: list[InverterConfig]) -> None:
        self.cfg = cfg
        self.inverters = [InverterState(i) for i in inverters]
        self._sign = -1.0 if cfg.power_sign == "export" else 1.0
        self.registers = sunspec.build_base_registers(
            model_id=sunspec.MODEL_THREE_PHASE,
            manufacturer=cfg.manufacturer,
            model_name=cfg.model_name,
            serial=cfg.serial,
            device_address=cfg.device_address,
        )
        self.recompute()

    def apply_inverter_metrics(self, inv: InverterState, metrics: dict) -> None:
        """Apply metrics from a Home Assistant source, rebuild the aggregate."""
        inv.apply_metrics(metrics)
        self._after_update(inv)

    def _after_update(self, inv: InverterState) -> None:
        self.recompute()
        _LOGGER.debug(
            "%s updated; aggregate now %.0f W, %.1f kWh",
            inv.cfg.name,
            self._total_w(),
            self._total_kwh(),
        )

    def recompute(self) -> None:
        """Rebuild the SunSpec register image from all inverter states."""
        timeout = self.cfg.stale_timeout
        w = dict.fromkeys(_PHASES, 0.0)
        a = dict.fromkeys(_PHASES, 0.0)
        v_sum = dict.fromkeys(_PHASES, 0.0)
        v_cnt = dict.fromkeys(_PHASES, 0)
        freqs: list[float] = []
        energy_wh = 0.0

        for inv in self.inverters:
            # Energy is a lifetime counter: always include the last known value
            # so the aggregate total never regresses when an inverter goes idle.
            energy_wh += inv.energy_kwh * 1000.0
            if inv.is_stale(timeout):
                continue  # no live power/current contribution from a stale source
            for p in _PHASES:
                w[p] += inv.phase_w[p]
                a[p] += inv.phase_a[p]
                if inv.phase_v[p] is not None:
                    v_sum[p] += inv.phase_v[p]
                    v_cnt[p] += 1
            if inv.frequency is not None:
                freqs.append(inv.frequency)

        sign = self._sign
        sunspec.set_float(self.registers, "W", sum(w.values()) * sign)
        sunspec.set_float(self.registers, "A", sum(a.values()))
        phase_volts = []
        for p in _PHASES:
            suffix = _PHASE_SUFFIX[p]
            sunspec.set_float(self.registers, f"W{suffix}", w[p] * sign)
            sunspec.set_float(self.registers, f"A{suffix}", a[p])
            volt = v_sum[p] / v_cnt[p] if v_cnt[p] else 0.0
            sunspec.set_float(self.registers, f"PhV{suffix}", volt)
            if v_cnt[p]:
                phase_volts.append(volt)

        sunspec.set_float(
            self.registers,
            "PhV",
            sum(phase_volts) / len(phase_volts) if phase_volts else 0.0,
        )
        sunspec.set_float(
            self.registers, "Hz", sum(freqs) / len(freqs) if freqs else 0.0
        )
        sunspec.set_float(self.registers, "TotWhExp", energy_wh)
        sunspec.set_float(self.registers, "TotWhImp", 0.0)

    def _total_w(self) -> float:
        return sum(
            sum(inv.phase_w.values())
            for inv in self.inverters
            if not inv.is_stale(self.cfg.stale_timeout)
        )

    def _total_kwh(self) -> float:
        return sum(inv.energy_kwh for inv in self.inverters)


def _num(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
