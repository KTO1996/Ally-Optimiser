"""Built-in profile presets, scaled to the detected console.

Quick one-click starting points (Silent / Balanced / Turbo / Max) derived from
the model's TDP band in :mod:`sysinfo`, so they're always sensible for the
actual hardware. Pure data — unit-testable.
"""
from __future__ import annotations

from typing import Dict, List

from . import sysinfo

# Native panel on both Ally models.
_RES = "1920x1080"
_FPS = 120


def presets_for(model: str) -> List[Dict]:
    band = sysinfo.TDP_PROFILES.get(model, sysinfo.TDP_PROFILES[sysinfo.UNKNOWN])
    return [
        {"label": "Silent", "tdp_sustained": band["silent"],
         "tdp_boost": band["silent"] + 2, "resolution": _RES, "fps_cap": 60,
         "notes": "Quietest/coolest — light or 2D games, max battery."},
        {"label": "Balanced", "tdp_sustained": band["performance"],
         "tdp_boost": band["turbo"], "resolution": _RES, "fps_cap": _FPS,
         "notes": "Good FPS-per-watt for most games."},
        {"label": "Turbo", "tdp_sustained": band["turbo"],
         "tdp_boost": band["max"], "resolution": _RES, "fps_cap": _FPS,
         "notes": "High performance, plugged in or short sessions."},
        {"label": "Max", "tdp_sustained": band["max"],
         "tdp_boost": band["max"], "resolution": _RES, "fps_cap": _FPS,
         "notes": "Everything the APU will give — hottest, shortest battery."},
    ]
