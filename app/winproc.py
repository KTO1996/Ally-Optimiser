"""Subprocess helpers that never flash a console window.

In a windowed (no-console) PyInstaller build, each ``subprocess.run`` of a
console program (powercfg, sc, PowerShell, RyzenAdj) briefly pops up a black
console window. These wrappers pass the Win32 flags that keep it hidden, and are
plain pass-throughs off Windows.
"""
from __future__ import annotations

import subprocess
import sys


def _no_window_kwargs() -> dict:
    if not sys.platform.startswith("win"):
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW   # honour wShowWindow (hidden)
    return {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW


def run(cmd, **kwargs):
    """subprocess.run with the console window suppressed on Windows."""
    merged = {**_no_window_kwargs(), **kwargs}
    return subprocess.run(cmd, **merged)


def popen(cmd, **kwargs):
    """subprocess.Popen with the console window suppressed on Windows."""
    merged = {**_no_window_kwargs(), **kwargs}
    return subprocess.Popen(cmd, **merged)
