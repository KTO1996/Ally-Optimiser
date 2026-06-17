"""FPS-boost / enhancement tools.

Covers what the Ally community uses to squeeze out more frames:

  * Native AMD equivalents of Lossless Scaling — AFMF (driver frame generation),
    RSR (driver upscaling) and in-game FSR. AMD Adrenalin has no public API, so
    these are *guided* (with the few that can be nudged via registry noted).
  * Fullscreen Exclusive — what AnyFSE forces. We can replicate the key part
    natively by disabling "fullscreen optimizations" per game .exe via a registry
    compatibility layer (no third-party tool needed).
  * Detect + launch the actual apps (Lossless Scaling on Steam, AnyFSE) if the
    user has them.

Registry/launch actions are Windows-only and dry-run elsewhere.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from typing import List, Optional

from . import winproc

from . import wincmd

# Steam app id for Lossless Scaling.
LOSSLESS_SCALING_APPID = "993090"
LOSSLESS_SCALING_STORE = "https://store.steampowered.com/app/993090/Lossless_Scaling/"
ANYFSE_RELEASES = "https://github.com/Avoidently/AnyFSE/releases"

# Registry compatibility-layer string that disables fullscreen optimizations
# (forces Fullscreen-Exclusive-style behaviour). Applied per .exe path.
_FSE_LAYER = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
_LAYERS_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"


# --------------------------------------------------------------------------- #
#  Native "Lossless Scaling alternative" guidance (AMD)
# --------------------------------------------------------------------------- #
@dataclass
class GuideCard:
    title: str
    body: str
    native: bool          # True = built into the Ally's GPU/Windows, free
    link: str = ""


def native_boost_guides() -> List[GuideCard]:
    return [
        GuideCard(
            title="AFMF 2 — AMD Fluid Motion Frames (driver frame-gen)",
            body="The free native answer to Lossless Scaling's frame generation. "
                 "Enable in AMD Software → Graphics → toggle AFMF (or per-game). "
                 "Best at 1080p with a stable 50–60 fps base.",
            native=True),
        GuideCard(
            title="RSR — Radeon Super Resolution (driver upscaling)",
            body="Driver-level upscaler: run the game at a lower resolution and let "
                 "RSR upscale to native. Enable globally in AMD Software. Use when a "
                 "game has no built-in FSR.",
            native=True),
        GuideCard(
            title="FSR — in-game upscaling",
            body="If the game exposes FSR/upscaling, prefer it over RSR for sharper "
                 "results. FSR 3 also adds in-game frame generation in supported "
                 "titles.",
            native=True),
        GuideCard(
            title="Lossless Scaling (third-party, paid)",
            body="Window-level frame-gen + upscaling that works on any game. Useful "
                 "when AFMF/FSR aren't available. Detect/launch below if installed.",
            native=False, link=LOSSLESS_SCALING_STORE),
    ]


# --------------------------------------------------------------------------- #
#  App detection + launch
# --------------------------------------------------------------------------- #
@dataclass
class ToolStatus:
    name: str
    installed: bool
    path: str = ""          # exe path or steam:// uri
    install_link: str = ""


def detect_lossless_scaling(steam_common_paths: List[str]) -> ToolStatus:
    """Detect Lossless Scaling via its Steam appmanifest."""
    for common in steam_common_paths or []:
        steamapps = os.path.dirname(common.rstrip("\\/"))
        acf = os.path.join(steamapps, f"appmanifest_{LOSSLESS_SCALING_APPID}.acf")
        if os.path.isfile(acf):
            return ToolStatus("Lossless Scaling", True,
                              path=f"steam://rungameid/{LOSSLESS_SCALING_APPID}",
                              install_link=LOSSLESS_SCALING_STORE)
    return ToolStatus("Lossless Scaling", False, install_link=LOSSLESS_SCALING_STORE)


def detect_anyfse(extra_path: Optional[str] = None) -> ToolStatus:
    """Detect AnyFSE at a configured path or common locations."""
    candidates = [extra_path] if extra_path else []
    candidates += [
        os.path.expandvars(r"%LOCALAPPDATA%\AnyFSE\AnyFSE.exe"),
        os.path.expandvars(r"%ProgramFiles%\AnyFSE\AnyFSE.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return ToolStatus("AnyFSE", True, path=c, install_link=ANYFSE_RELEASES)
    return ToolStatus("AnyFSE", False, install_link=ANYFSE_RELEASES)


def launch_tool(tool: ToolStatus) -> bool:
    """Launch a detected tool (steam:// uri or exe). Returns True if attempted."""
    if not tool.installed or not tool.path:
        return False
    try:
        if tool.path.startswith("steam://"):
            if sys.platform.startswith("win"):
                os.startfile(tool.path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(tool.path)
        else:
            winproc.popen([tool.path])
        return True
    except Exception:
        return False


def open_install_link(tool: ToolStatus) -> None:
    if tool.install_link:
        webbrowser.open(tool.install_link)


# --------------------------------------------------------------------------- #
#  Native Fullscreen-Exclusive toggle (replicates AnyFSE's core effect)
# --------------------------------------------------------------------------- #
def _winreg():
    try:
        import winreg  # type: ignore
        return winreg
    except Exception:
        return None


def fse_is_forced(exe_path: str) -> bool:
    winreg = _winreg()
    if winreg is None or not exe_path:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _LAYERS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, exe_path)
            return "DISABLEDXMAXIMIZEDWINDOWEDMODE" in str(value)
    except OSError:
        return False


def set_fse(exe_path: str, enabled: bool, dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Force (or stop forcing) Fullscreen Exclusive for a game .exe.

    Implemented via the per-app compatibility 'Layers' registry value — the same
    mechanism as the "Disable fullscreen optimizations" checkbox.
    """
    dry = (not wincmd.is_windows()) if dry_run is None else dry_run
    if not exe_path:
        return wincmd.CmdResult(False, "No executable path given.", [], dry)
    action = (f'set HKCU\\{_LAYERS_KEY}\n  "{exe_path}" = "{_FSE_LAYER}"'
              if enabled else f'remove layer for "{exe_path}"')
    if dry:
        return wincmd.CmdResult(True, "Planned (dry-run).", [action], True)
    winreg = _winreg()
    if winreg is None:
        return wincmd.CmdResult(False, "winreg unavailable.", [action], False)
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _LAYERS_KEY, 0,
                                 winreg.KEY_SET_VALUE | winreg.KEY_READ)
        try:
            if enabled:
                winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, _FSE_LAYER)
            else:
                try:
                    winreg.DeleteValue(key, exe_path)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except OSError as exc:
        return wincmd.CmdResult(False, f"Registry write failed: {exc}", [action], False)
    return wincmd.CmdResult(True, "Fullscreen Exclusive "
                            + ("forced." if enabled else "reverted."), [action], False)
