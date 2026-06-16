"""Rough battery-runtime estimates per profile.

Very approximate: total system draw ≈ APU TDP + a fixed platform overhead
(screen, RAM, fans, controllers). Runtime = battery capacity / draw. Meant as a
relative guide between profiles, not a precise battery meter.
"""
from __future__ import annotations

from typing import Dict, Optional

from . import sysinfo

# Battery capacity in watt-hours per model.
BATTERY_WH = {
    sysinfo.ALLY: 40.0,     # original Ally
    sysinfo.ALLY_X: 80.0,   # Ally X — roughly double
    sysinfo.UNKNOWN: 40.0,
}
# Everything that draws power besides the APU package (screen, RAM, fans, etc.).
PLATFORM_OVERHEAD_W = 6.0


def estimate_hours(tdp_sustained_w: float, model: str) -> Optional[float]:
    """Estimated runtime in hours at a given sustained TDP, or None if invalid."""
    try:
        draw = float(tdp_sustained_w) + PLATFORM_OVERHEAD_W
    except (TypeError, ValueError):
        return None
    if draw <= 0:
        return None
    wh = BATTERY_WH.get(model, BATTERY_WH[sysinfo.UNKNOWN])
    return round(wh / draw, 1)


def estimate_text(profile: Dict, model: str) -> str:
    """Short label like '~1.8 h' for a profile's sustained TDP."""
    hrs = estimate_hours(profile.get("tdp_sustained", 0), model)
    return f"~{hrs} h battery" if hrs else ""
