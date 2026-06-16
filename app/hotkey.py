"""Global hotkey to reapply the last-used profile.

Uses the optional ``keyboard`` package. It's Windows-friendly and works under
our already-elevated process. If the package isn't installed or registration
fails, hotkey support silently no-ops (the rest of the app is unaffected).
"""
from __future__ import annotations

from typing import Callable, Optional

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyboard = None  # type: ignore


class HotkeyManager:
    def __init__(self) -> None:
        self._registered: Optional[str] = None

    @property
    def available(self) -> bool:
        return keyboard is not None

    def register(self, hotkey: str, callback: Callable[[], None]) -> bool:
        if keyboard is None or not hotkey:
            return False
        self.unregister()
        try:
            keyboard.add_hotkey(hotkey, callback)
            self._registered = hotkey
            return True
        except Exception:
            self._registered = None
            return False

    def unregister(self) -> None:
        if keyboard is None or self._registered is None:
            return
        try:
            keyboard.remove_hotkey(self._registered)
        except Exception:
            pass
        self._registered = None
