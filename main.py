"""Ally Optimizer — entry point.

On Windows we self-elevate to Administrator (RyzenAdj needs it). If elevation
is declined we still launch, but warn that Apply/Reset will fail until the app
is run as admin — we never fail silently.
"""
from __future__ import annotations

import sys

from app import APP_NAME
from app.elevation import is_admin, relaunch_as_admin


def main() -> int:
    if sys.platform.startswith("win") and not is_admin():
        # Try to relaunch elevated. If the relaunch starts, exit this instance.
        if relaunch_as_admin():
            return 0
        # Elevation unavailable/declined — continue but warn the user.
        try:
            import tkinter.messagebox as mb
            mb.showwarning(
                APP_NAME,
                "Not running as Administrator.\n\n"
                "RyzenAdj needs admin rights, so Apply and Reset will fail "
                "until you relaunch this app as Administrator.",
            )
        except Exception:
            print("WARNING: not elevated — RyzenAdj Apply/Reset will fail.")

    # Import GUI lazily so the elevation check happens before any Tk window.
    from app.gui import AllyOptimizerApp

    app = AllyOptimizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
