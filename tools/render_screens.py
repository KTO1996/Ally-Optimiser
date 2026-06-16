"""Headless render of the GUI pages in both themes (for review screenshots).

Run under a virtual display, e.g.:
    xvfb-run -s "-screen 0 1100x740x24" /usr/bin/python3.12 tools/render_screens.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import ImageGrab  # noqa: E402

from app import gui  # noqa: E402

# Don't spawn tray/hotkey threads during rendering.
gui.AllyOptimizerApp._setup_tray = lambda self: None
gui.AllyOptimizerApp._setup_hotkey = lambda self: None

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
W, H = 1040, 680
PAGES = list(gui.NAV_ITEMS)


def shot(app, path):
    app.update_idletasks()
    app.update()
    time.sleep(0.5)
    app.update()
    ImageGrab.grab(bbox=(0, 0, W, H)).save(path)
    print("wrote", path)


def select_first_game(app):
    entries = app._all_entries()
    if entries:
        app._select_game(app._entry_to_name(entries[0]))


def capture_all(app, tag):
    for name in PAGES:
        app._show_page(name)
        if name == "Games":
            select_first_game(app)
        slug = name.lower().replace(" ", "")
        shot(app, os.path.join(OUT, f"screenshot_{tag}_{slug}.png"))


def main():
    app = gui.AllyOptimizerApp()
    app.geometry(f"{W}x{H}+0+0")
    capture_all(app, app.theme_mode)

    # Toggle to the other theme and recapture.
    app.theme_switch.select() if app.theme_mode == "dark" else app.theme_switch.deselect()
    app._toggle_theme()
    capture_all(app, app.theme_mode)

    app.destroy()


if __name__ == "__main__":
    main()
