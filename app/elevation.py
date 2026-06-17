"""Administrator self-elevation (Windows).

RyzenAdj needs to run elevated to write power limits. On launch we check
whether we're already admin; if not, we re-launch the same script with the
"runas" verb (UAC prompt). We do **not** fail silently: if elevation is
declined or unavailable, the caller surfaces a clear message.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    """True if the current process has Administrator rights (Windows)."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        # Non-Windows or no shell32 — treat as "not admin" but don't crash.
        return False


def relaunch_as_admin() -> bool:
    """Re-launch this program elevated via a UAC prompt.

    Handles both the packaged exe and running from source:
      * frozen exe → re-run the exe itself with our extra args (argv[0] is the
        exe, so it must NOT be passed as an argument), and
      * source     → re-run Python with the script path + args.

    Returns True if the elevated launch started (caller should exit), False if
    elevation isn't possible / was declined.
    """
    try:
        if getattr(sys, "frozen", False):
            target = sys.executable                      # the .exe
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            target = sys.executable                      # python
            script = os.path.abspath(sys.argv[0])
            params = subprocess.list2cmdline([script, *sys.argv[1:]])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", target, params, None, 1
        )
        # ShellExecuteW returns >32 on success.
        return int(rc) > 32
    except Exception:
        return False
