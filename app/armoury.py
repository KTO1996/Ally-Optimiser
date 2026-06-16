"""Armoury Crate guidance.

Armoury Crate is ASUS's closed app with **no public API**, so we can't flip its
toggles directly. Instead this module provides three things the user asked for:

  1. A guided checklist of the AC settings worth changing, with recommended
     values per model (and *why*).
  2. A note on which items this app can replicate natively (e.g. TDP via
     RyzenAdj) so AC isn't strictly required for them.
  3. Deep links / launchers: open Armoury Crate, or jump straight to the
     relevant Windows settings page via ``ms-settings:`` URIs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from typing import List, Optional

from . import sysinfo


@dataclass
class ChecklistItem:
    title: str
    recommended: str          # recommended value/action
    why: str
    native: Optional[str] = None   # how the app can replicate it, if at all


def checklist(device: sysinfo.DeviceInfo) -> List[ChecklistItem]:
    """Recommended Armoury Crate settings for the detected model."""
    tdp = device.tdp_profile
    items = [
        ChecklistItem(
            title="Operating Mode → Manual",
            recommended="Set the performance mode to Manual/Custom",
            why="Unlocks the custom TDP slider and fan curve instead of the "
                "fixed Silent/Performance/Turbo presets.",
        ),
        ChecklistItem(
            title="Custom TDP (SPL / sustained)",
            recommended=f"~{tdp['performance']} W docked-light, "
                        f"{tdp['silent']} W for battery, up to {tdp['max']} W plugged",
            why="The single biggest lever for FPS vs battery vs heat on the Ally.",
            native="Yes — Ally Optimizer sets TDP per-game via RyzenAdj "
                   "(Games tab), so you don't need AC for this.",
        ),
        ChecklistItem(
            title="Fan curve",
            recommended="Custom curve: quiet under ~60°C, ramping hard past 80°C",
            why="Keeps the APU off its thermal limit so sustained clocks hold up.",
            native="No — fan control is firmware-level and only AC exposes it.",
        ),
        ChecklistItem(
            title="AMD / GPU settings",
            recommended="Leave GPU allocation on Auto unless a game needs more VRAM",
            why="Auto handles the shared memory split well for most titles.",
            native="Partial — VRAM split is a BIOS/AC setting, not changeable here.",
        ),
        ChecklistItem(
            title="Disable AC overlay / hotkey hijack (optional)",
            recommended="Turn off the Armoury Crate overlay if you use this app's "
                        "hotkeys",
            why="Avoids two tools fighting over the same Command Center buttons.",
        ),
    ]
    if device.model == sysinfo.ALLY_X:
        items.append(ChecklistItem(
            title="Take advantage of the larger battery (Ally X)",
            recommended=f"You can sustain ~{tdp['turbo']}–{tdp['max']} W on battery "
                        "for longer than the base Ally",
            why="The Ally X's 80Wh pack tolerates higher sustained TDP per hour.",
            native="Yes — pick a higher per-game TDP in the Games tab.",
        ))
    return items


# --------------------------------------------------------------------------- #
#  Deep links / launchers
# --------------------------------------------------------------------------- #
@dataclass
class DeepLink:
    label: str
    target: str       # ms-settings: URI, http(s) URL, or executable name
    kind: str         # "settings" | "url" | "app"


def deep_links() -> List[DeepLink]:
    return [
        DeepLink("Open Armoury Crate", "armourycrate", "app"),
        DeepLink("Windows: Power & battery", "ms-settings:powersleep", "settings"),
        DeepLink("Windows: Graphics settings", "ms-settings:display-advancedgraphics", "settings"),
        DeepLink("Windows: Game Mode", "ms-settings:gaming-gamemode", "settings"),
        DeepLink("Windows: Display / refresh rate", "ms-settings:display-advanced", "settings"),
        DeepLink("ASUS support: ROG Ally drivers",
                 "https://rog.asus.com/support/", "url"),
    ]


def open_link(link: DeepLink) -> bool:
    """Open a deep link. Returns True if a launch was attempted."""
    try:
        if link.kind == "url":
            webbrowser.open(link.target)
            return True
        if link.kind == "settings":
            if sys.platform.startswith("win"):
                os.startfile(link.target)  # type: ignore[attr-defined]
            else:
                webbrowser.open(link.target)
            return True
        if link.kind == "app":
            return _launch_armoury_crate()
    except Exception:
        return False
    return False


def _launch_armoury_crate() -> bool:
    """Best-effort launch of Armoury Crate via its shell app id / exe."""
    if not sys.platform.startswith("win"):
        return False
    # Try the UWP/Store launch first, then the classic exe path.
    candidates = [
        ["explorer.exe", "shell:AppsFolder\\"
         "B9ECED6F.ArmouryCrate_qmba6cd70vzyy!ArmouryCrate"],
        [r"C:\Program Files\ASUS\ARMOURY CRATE Service\ArmouryCrate.exe"],
    ]
    for cmd in candidates:
        try:
            if cmd[0].endswith(".exe") and not os.path.isfile(cmd[0]):
                continue
            subprocess.Popen(cmd)
            return True
        except Exception:
            continue
    return False
