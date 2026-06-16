"""System tray icon / minimize-to-tray.

Uses the optional ``pystray`` + ``Pillow`` packages. If they're missing, the
tray feature is disabled gracefully and the window simply behaves normally.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pystray = None  # type: ignore
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore


def _make_icon_image():
    # Simple 64x64 icon: green rounded square with "A".
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(34, 139, 76, 255))
    d.text((24, 20), "A", fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    def __init__(
        self,
        app_name: str,
        on_show: Callable[[], None],
        on_reapply: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._icon: Optional["pystray.Icon"] = None  # type: ignore
        self._thread: Optional[threading.Thread] = None
        self.app_name = app_name
        self.on_show = on_show
        self.on_reapply = on_reapply
        self.on_quit = on_quit

    @property
    def available(self) -> bool:
        return pystray is not None and Image is not None

    def start(self) -> bool:
        if not self.available:
            return False
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.on_show(), default=True),
            pystray.MenuItem("Reapply last profile", lambda: self.on_reapply()),
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        self._icon = pystray.Icon(self.app_name, _make_icon_image(), self.app_name, menu)
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
