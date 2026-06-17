"""System tray icon / minimize-to-tray.

Uses the optional ``pystray`` + ``Pillow`` packages. If they're missing, the
tray feature is disabled gracefully and the window simply behaves normally.
"""
from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional

from .paths import ICON_PNG

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pystray = None  # type: ignore
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore


def _make_icon_image():
    # Prefer the bundled app icon; fall back to a simple drawn badge.
    try:
        if os.path.isfile(ICON_PNG):
            return Image.open(ICON_PNG)
    except Exception:
        pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(226, 0, 26, 255))
    d.text((26, 20), "A", fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    def __init__(
        self,
        app_name: str,
        on_show: Callable[[], None],
        on_reapply: Callable[[], None],
        on_quit: Callable[[], None],
        presets: Optional[List[str]] = None,
        on_preset: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._icon: Optional["pystray.Icon"] = None  # type: ignore
        self._thread: Optional[threading.Thread] = None
        self.app_name = app_name
        self.on_show = on_show
        self.on_reapply = on_reapply
        self.on_quit = on_quit
        self.presets = presets or []
        self.on_preset = on_preset

    @property
    def available(self) -> bool:
        return pystray is not None and Image is not None

    def start(self) -> bool:
        if not self.available:
            return False
        items = [
            pystray.MenuItem("Show", lambda: self.on_show(), default=True),
            pystray.MenuItem("Reapply last profile", lambda: self.on_reapply()),
        ]
        if self.presets and self.on_preset:
            preset_items = [
                pystray.MenuItem(label, (lambda lb: lambda: self.on_preset(lb))(label))
                for label in self.presets
            ]
            items.append(pystray.MenuItem("Power preset", pystray.Menu(*preset_items)))
        items.append(pystray.MenuItem("Quit", lambda: self._quit()))
        self._icon = pystray.Icon(self.app_name, _make_icon_image(), self.app_name,
                                  pystray.Menu(*items))
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def _quit(self) -> None:
        self.stop()
        self.on_quit()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
