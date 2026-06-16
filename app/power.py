"""Battery / power / temperature readout via psutil.

All functions degrade gracefully: on platforms or machines where psutil can't
read a value (no battery, no temp sensor), they return None rather than raise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil should be installed
    psutil = None  # type: ignore


@dataclass
class PowerStatus:
    percent: Optional[float]
    plugged: Optional[bool]
    cpu_temp_c: Optional[float]

    def summary(self) -> str:
        parts = []
        if self.percent is not None:
            parts.append(f"Battery {self.percent:.0f}%")
        if self.plugged is not None:
            parts.append("Plugged in" if self.plugged else "On battery")
        if self.cpu_temp_c is not None:
            parts.append(f"CPU {self.cpu_temp_c:.0f}°C")
        return "  |  ".join(parts) if parts else "Power status unavailable"


def _read_cpu_temp() -> Optional[float]:
    if psutil is None or not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    if not temps:
        return None
    # Prefer a CPU-ish sensor; otherwise take the first reading available.
    preferred_keys = ("k10temp", "coretemp", "cpu_thermal", "acpitz")
    for key in preferred_keys:
        if key in temps and temps[key]:
            return temps[key][0].current
    for readings in temps.values():
        if readings:
            return readings[0].current
    return None


def get_status() -> PowerStatus:
    percent: Optional[float] = None
    plugged: Optional[bool] = None
    if psutil is not None and hasattr(psutil, "sensors_battery"):
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                percent = batt.percent
                plugged = batt.power_plugged
        except Exception:
            pass
    return PowerStatus(percent=percent, plugged=plugged, cpu_temp_c=_read_cpu_temp())


def is_plugged_in() -> Optional[bool]:
    return get_status().plugged
