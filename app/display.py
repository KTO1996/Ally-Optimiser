"""Display resolution / refresh-rate control (Windows, via ctypes).

The one in-game-style setting we *can* apply system-side: switch the display
mode before launching a game and restore it after. Uses the Win32
``ChangeDisplaySettings`` API. Off-Windows everything is a dry-run so the rest
of the app stays testable.

This is intentionally simple: it targets the primary display and stores the
previous mode in memory so it can be restored.
"""
from __future__ import annotations

import re
import sys
from typing import Optional, Tuple

from .wincmd import CmdResult, is_windows

_prev_mode: Optional[Tuple[int, int, int]] = None


def parse_resolution(res: str) -> Optional[Tuple[int, int]]:
    """'1920x1080' -> (1920, 1080); None if unparseable."""
    if not res:
        return None
    m = re.match(r"\s*(\d{3,4})\s*[x×]\s*(\d{3,4})\s*$", res.lower())
    return (int(m.group(1)), int(m.group(2))) if m else None


def current_mode() -> Optional[Tuple[int, int, int]]:
    """Return (width, height, hz) of the primary display, or None."""
    if not is_windows():
        return None
    try:
        import ctypes

        class DEVMODE(ctypes.Structure):
            _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                        ("dmSpecVersion", ctypes.c_ushort),
                        ("dmDriverVersion", ctypes.c_ushort),
                        ("dmSize", ctypes.c_ushort),
                        ("dmDriverExtra", ctypes.c_ushort),
                        ("dmFields", ctypes.c_ulong),
                        ("dmOrientation", ctypes.c_short),
                        ("dmPaperSize", ctypes.c_short),
                        ("dmPaperLength", ctypes.c_short),
                        ("dmPaperWidth", ctypes.c_short),
                        ("dmScale", ctypes.c_short),
                        ("dmCopies", ctypes.c_short),
                        ("dmDefaultSource", ctypes.c_short),
                        ("dmPrintQuality", ctypes.c_short),
                        ("dmColor", ctypes.c_short),
                        ("dmDuplex", ctypes.c_short),
                        ("dmYResolution", ctypes.c_short),
                        ("dmTTOption", ctypes.c_short),
                        ("dmCollate", ctypes.c_short),
                        ("dmFormName", ctypes.c_wchar * 32),
                        ("dmLogPixels", ctypes.c_ushort),
                        ("dmBitsPerPel", ctypes.c_ulong),
                        ("dmPelsWidth", ctypes.c_ulong),
                        ("dmPelsHeight", ctypes.c_ulong),
                        ("dmDisplayFlags", ctypes.c_ulong),
                        ("dmDisplayFrequency", ctypes.c_ulong),
                        ("dmICMMethod", ctypes.c_ulong),
                        ("dmICMIntent", ctypes.c_ulong),
                        ("dmMediaType", ctypes.c_ulong),
                        ("dmDitherType", ctypes.c_ulong),
                        ("dmReserved1", ctypes.c_ulong),
                        ("dmReserved2", ctypes.c_ulong),
                        ("dmPanningWidth", ctypes.c_ulong),
                        ("dmPanningHeight", ctypes.c_ulong)]

        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        ENUM_CURRENT_SETTINGS = -1
        if ctypes.windll.user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS,
                                                     ctypes.byref(dm)):
            return (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency)
    except Exception:
        return None
    return None


def _change(width: int, height: int, hz: Optional[int]) -> CmdResult:
    plan = f"set display to {width}x{height}" + (f"@{hz}Hz" if hz else "")
    if not is_windows():
        return CmdResult(True, "Planned (dry-run).", [plan], True)
    try:
        return _apply_devmode(width, height, hz, plan)
    except Exception as exc:  # pragma: no cover - Windows only
        return CmdResult(False, f"Display change failed: {exc}", [plan], False)


def _apply_devmode(width: int, height: int, hz: Optional[int], plan: str) -> CmdResult:
    import ctypes
    user32 = ctypes.windll.user32
    DM_PELSWIDTH = 0x80000
    DM_PELSHEIGHT = 0x100000
    DM_DISPLAYFREQUENCY = 0x400000
    CDS_UPDATEREGISTRY = 0x01
    DISP_CHANGE_SUCCESSFUL = 0

    # Re-declare DEVMODE locally (kept identical to current_mode()).
    class DEVMODE(ctypes.Structure):
        _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                    ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort),
                    ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort),
                    ("dmFields", ctypes.c_ulong),
                    ("dmOrientation", ctypes.c_short),
                    ("dmPaperSize", ctypes.c_short),
                    ("dmPaperLength", ctypes.c_short),
                    ("dmPaperWidth", ctypes.c_short),
                    ("dmScale", ctypes.c_short),
                    ("dmCopies", ctypes.c_short),
                    ("dmDefaultSource", ctypes.c_short),
                    ("dmPrintQuality", ctypes.c_short),
                    ("dmColor", ctypes.c_short),
                    ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short),
                    ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_wchar * 32),
                    ("dmLogPixels", ctypes.c_ushort),
                    ("dmBitsPerPel", ctypes.c_ulong),
                    ("dmPelsWidth", ctypes.c_ulong),
                    ("dmPelsHeight", ctypes.c_ulong),
                    ("dmDisplayFlags", ctypes.c_ulong),
                    ("dmDisplayFrequency", ctypes.c_ulong),
                    ("dmICMMethod", ctypes.c_ulong),
                    ("dmICMIntent", ctypes.c_ulong),
                    ("dmMediaType", ctypes.c_ulong),
                    ("dmDitherType", ctypes.c_ulong),
                    ("dmReserved1", ctypes.c_ulong),
                    ("dmReserved2", ctypes.c_ulong),
                    ("dmPanningWidth", ctypes.c_ulong),
                    ("dmPanningHeight", ctypes.c_ulong)]

    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    dm.dmPelsWidth = width
    dm.dmPelsHeight = height
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT
    if hz:
        dm.dmDisplayFrequency = hz
        dm.dmFields |= DM_DISPLAYFREQUENCY
    rc = user32.ChangeDisplaySettingsW(ctypes.byref(dm), CDS_UPDATEREGISTRY)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return CmdResult(False, f"Display did not accept that mode (code {rc}).",
                         [plan], False)
    return CmdResult(True, "Display mode applied.", [plan], False)


def set_mode(width: int, height: int, hz: Optional[int] = None) -> CmdResult:
    """Set the primary display mode, remembering the previous one for restore."""
    global _prev_mode
    if is_windows() and _prev_mode is None:
        _prev_mode = current_mode()
    return _change(width, height, hz)


def restore() -> CmdResult:
    """Restore the display mode captured before the last :func:`set_mode`."""
    global _prev_mode
    if _prev_mode is None:
        return CmdResult(True, "Nothing to restore.", [], not is_windows())
    w, h, hz = _prev_mode
    res = _change(w, h, hz)
    if res.ok and not res.dry_run:
        _prev_mode = None
    return res
