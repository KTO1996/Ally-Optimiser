"""Administrator self-elevation (Windows).

RyzenAdj needs to run elevated to write power limits. On launch we check
whether we're already admin; if not, we re-launch the same script with the
"runas" verb (UAC prompt). We do **not** fail silently: if elevation is
declined or unavailable, the caller surfaces a clear message.
"""
from __future__ import annotations

import ctypes
import sys


def is_admin() -> bool:
    """True if the current process has Administrator rights (Windows)."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        # Non-Windows or no shell32 — treat as "not admin" but don't crash.
        return False


def relaunch_as_admin() -> bool:
    """Attempt to relaunch this program elevated.

    Returns True if a relaunch was triggered (caller should exit), False if
    elevation isn't possible on this platform.
    """
    try:
        params = " ".join(f'"{a}"' for a in sys.argv)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        # ShellExecuteW returns >32 on success.
        return int(rc) > 32
    except Exception:
        return False
