"""Detect which ROG Ally model we're running on.

The Windows tweaks and TDP ceilings differ a little between the original
ROG Ally, the ROG Ally X, and the 2025 Z2 refresh. We read the motherboard /
system model string (via WMI on Windows) and classify it. Everything degrades
gracefully off-Windows so the rest of the app stays testable.

Model strings seen in the wild (board "Product" / system "Model"):
  * ROG Ally (2023, Z1 / Z1 Extreme)      -> "RC71L"
  * ROG Ally X (2024, Z1 Extreme)         -> "RC72LA"
  * ROG Ally / Ally X (2025, Z2 / Z2 Ex.) -> "RC73" family
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import winproc

# Canonical model keys used across the app.
ALLY = "ROG Ally"
ALLY_X = "ROG Ally X"
UNKNOWN = "Unknown handheld"

# Per-model TDP guidance (watts). The Z1/Z2 Extreme APUs are happy across this
# band; the X models carry a bigger battery so they sustain the top end longer.
TDP_PROFILES: Dict[str, Dict[str, int]] = {
    ALLY:    {"silent": 10, "performance": 17, "turbo": 25, "max": 30},
    ALLY_X:  {"silent": 13, "performance": 20, "turbo": 30, "max": 35},
    UNKNOWN: {"silent": 10, "performance": 17, "turbo": 25, "max": 30},
}


@dataclass
class DeviceInfo:
    model: str = UNKNOWN
    raw_model: str = ""
    total_ram_gb: Optional[int] = None
    detected: bool = False

    @property
    def tdp_profile(self) -> Dict[str, int]:
        return TDP_PROFILES.get(self.model, TDP_PROFILES[UNKNOWN])

    def summary(self) -> str:
        ram = f" · {self.total_ram_gb}GB RAM" if self.total_ram_gb else ""
        if not self.detected:
            return f"{self.model} (not auto-detected)"
        return f"{self.model}{ram}"


# Both Ally and Ally X ship the same 7" 1080p120 panel.
NATIVE_WIDTH = 1920
NATIVE_HEIGHT = 1080
PANEL_HZ = 120


def validate_profile(profile: Dict, model: str) -> List[str]:
    """Return human-readable warnings if a profile won't suit this console.

    Pure function (no I/O) so it's unit-testable. An empty list means the
    profile looks applicable to the detected handheld.
    """
    warnings: List[str] = []
    band = TDP_PROFILES.get(model, TDP_PROFILES[UNKNOWN])
    floor, ceil = band["silent"] - 5, band["max"]

    sustained = profile.get("tdp_sustained")
    boost = profile.get("tdp_boost")
    if isinstance(sustained, (int, float)) and sustained > ceil:
        warnings.append(f"Sustained TDP {sustained}W exceeds this model's ~{ceil}W ceiling.")
    if isinstance(sustained, (int, float)) and sustained < max(3, floor):
        warnings.append(f"Sustained TDP {sustained}W is unusually low for this model.")
    if (isinstance(boost, (int, float)) and isinstance(sustained, (int, float))
            and boost < sustained):
        warnings.append("Boost TDP is below sustained — boost should be ≥ sustained.")
    if isinstance(boost, (int, float)) and boost > ceil:
        warnings.append(f"Boost TDP {boost}W exceeds this model's ~{ceil}W ceiling.")

    res = profile.get("resolution")
    if isinstance(res, str) and "x" in res.lower():
        try:
            w, h = (int(p) for p in re.split(r"[x×]", res.lower())[:2])
            if w > NATIVE_WIDTH or h > NATIVE_HEIGHT:
                warnings.append(f"{res} is above the Ally's native "
                                f"{NATIVE_WIDTH}x{NATIVE_HEIGHT} panel.")
        except ValueError:
            pass

    fps = profile.get("fps_cap")
    if isinstance(fps, (int, float)) and fps > PANEL_HZ:
        warnings.append(f"{fps} fps is above the {PANEL_HZ}Hz panel — cap at {PANEL_HZ}.")

    return warnings


def classify_model(raw_model: str, ram_gb: Optional[int] = None) -> str:
    """Map a raw WMI model/board string to a canonical model key.

    Pure function (no I/O) so it can be unit-tested with sample strings.
    """
    s = (raw_model or "").upper().replace(" ", "")
    if "RC72" in s:                      # Ally X (2024)
        return ALLY_X
    if "RC73" in s:                      # 2025 Z2 refresh
        # The X variant ships with notably more RAM (24GB); use that to split.
        return ALLY_X if (ram_gb or 0) >= 24 else ALLY
    if "RC71" in s:                      # original Ally (2023)
        return ALLY
    if "ALLYX" in s:
        return ALLY_X
    if "ALLY" in s:
        return ALLY
    return UNKNOWN


def _query_windows() -> tuple[str, Optional[int]]:
    """Return (raw_model, ram_gb) from WMI. Empty/None off-Windows or on error."""
    if not sys.platform.startswith("win"):
        return "", None
    ps = (
        "$cs = Get-CimInstance Win32_ComputerSystem; "
        "$bb = Get-CimInstance Win32_BaseBoard; "
        "Write-Output ($bb.Product + '|' + $cs.Model + '|' + "
        "[math]::Round($cs.TotalPhysicalMemory/1GB))"
    )
    try:
        out = winproc.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except Exception:
        return "", None
    parts = (out.split("|") + ["", "", ""])[:3]
    board, model, ram = parts
    raw = board or model
    try:
        ram_gb: Optional[int] = int(float(ram)) if ram else None
    except ValueError:
        ram_gb = None
    # Prefer the more descriptive of the two strings.
    raw_model = (model if "RC" in (model or "").upper() else raw) or raw or model
    return raw_model, ram_gb


def detect_device(override: Optional[str] = None) -> DeviceInfo:
    """Detect the handheld model, honouring a manual override if given."""
    if override in (ALLY, ALLY_X):
        return DeviceInfo(model=override, raw_model=override, detected=True)
    raw_model, ram_gb = _query_windows()
    model = classify_model(raw_model, ram_gb)
    return DeviceInfo(
        model=model,
        raw_model=raw_model,
        total_ram_gb=ram_gb,
        detected=bool(raw_model) and model != UNKNOWN,
    )
