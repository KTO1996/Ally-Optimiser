"""Headless render of the GUI tabs in both themes (for review screenshots).

Run under a virtual display, e.g.:
    xvfb-run -s "-screen 0 1000x760x24" /usr/bin/python3.12 tools/render_screens.py
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
W, H = 960, 640


def shot(app, path):
    app.update_idletasks()
    app.update()
    time.sleep(0.4)
    app.update()
    ImageGrab.grab(bbox=(0, 0, W, H)).save(path)
    print("wrote", path)


def select_game(app):
    if app.listbox.size():
        app.listbox.selection_clear(0, "end")
        app.listbox.selection_set(0)
        app.selected_game = app._entry_to_name(app.listbox.get(0))
        app._render_detail()


def main():
    app = gui.AllyOptimizerApp()
    app.geometry(f"{W}x{H}+0+0")
    select_game(app)

    for tab, label in ((app.tab_games, "games"),
                        (app.tab_tweaks, "tweaks"),
                        (app.tab_armoury, "armoury")):
        app.notebook.select(tab)
        shot(app, os.path.join(OUT, f"screenshot_{app.theme_mode}_{label}.png"))

    # Toggle to light and capture the same tabs.
    app._toggle_theme()
    select_game(app)
    for tab, label in ((app.tab_games, "games"),
                        (app.tab_tweaks, "tweaks"),
                        (app.tab_armoury, "armoury")):
        app.notebook.select(tab)
        shot(app, os.path.join(OUT, f"screenshot_{app.theme_mode}_{label}.png"))

    app.destroy()


if __name__ == "__main__":
    main()
