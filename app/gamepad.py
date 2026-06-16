"""Xbox-controller (XInput) navigation — for driving the UI on the Ally itself.

Polls controller 0 via XInput (built into Windows, no extra dependency) on a
background thread and emits high-level navigation actions with edge detection
(one action per press) so the whole app can be used without touching the
screen:

  * D-pad / left stick → move focus (up/down/left/right)
  * A                  → activate the focused control
  * B                  → back to Games
  * LB / RB            → previous / next page (sidebar tab)

The button-decoding, edge-detection and index maths are pure and unit-tested.
The polling thread is Windows-only and simply never starts elsewhere.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional, Set

# XInput wButtons bitmasks.
BUTTONS = {
    "dpad_up": 0x0001, "dpad_down": 0x0002, "dpad_left": 0x0004, "dpad_right": 0x0008,
    "start": 0x0010, "back": 0x0020, "l_thumb": 0x0040, "r_thumb": 0x0080,
    "lb": 0x0100, "rb": 0x0200, "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}

# Raw input -> high-level navigation action.
ACTION_FOR = {
    "dpad_up": "up", "dpad_down": "down", "dpad_left": "left", "dpad_right": "right",
    "a": "activate", "b": "back", "lb": "prev_tab", "rb": "next_tab",
}

# Left-stick deflection (out of 32767) that counts as a direction press.
STICK_THRESHOLD = 18000


def decode(buttons: int) -> Set[str]:
    """Decode an XInput wButtons value into the set of pressed button names."""
    return {name for name, mask in BUTTONS.items() if buttons & mask}


def stick_directions(lx: int, ly: int) -> Set[str]:
    """Translate a left-stick position into d-pad-style direction names."""
    out: Set[str] = set()
    if lx <= -STICK_THRESHOLD:
        out.add("dpad_left")
    elif lx >= STICK_THRESHOLD:
        out.add("dpad_right")
    if ly >= STICK_THRESHOLD:
        out.add("dpad_up")
    elif ly <= -STICK_THRESHOLD:
        out.add("dpad_down")
    return out


def actions_from(pressed: Set[str]) -> Set[str]:
    """Map a set of raw button/direction names to navigation actions."""
    return {ACTION_FOR[p] for p in pressed if p in ACTION_FOR}


def newly_pressed(prev: Set[str], cur: Set[str]) -> Set[str]:
    """Edge detection: names present now but not in the previous poll."""
    return cur - prev


def next_index(current: int, delta: int, count: int) -> int:
    """Wrap-around index movement for focus navigation."""
    if count <= 0:
        return 0
    return (current + delta) % count


class GamepadPoller:
    """Background XInput poller that fires navigation actions via a callback."""

    def __init__(self, on_action: Callable[[str], None], interval: float = 0.08) -> None:
        self._on_action = on_action
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._prev: Set[str] = set()
        self._xinput = self._load_xinput()

    @staticmethod
    def _load_xinput():
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes
            for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    return ctypes.windll.LoadLibrary(dll)
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def available(self) -> bool:
        return self._xinput is not None

    def start(self) -> bool:
        if self._thread is not None or self._xinput is None:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _read_pressed(self) -> Set[str]:
        import ctypes

        class _PAD(ctypes.Structure):
            _fields_ = [("wButtons", ctypes.c_ushort),
                        ("bLeftTrigger", ctypes.c_ubyte),
                        ("bRightTrigger", ctypes.c_ubyte),
                        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                        ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

        class _STATE(ctypes.Structure):
            _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _PAD)]

        state = _STATE()
        if self._xinput.XInputGetState(0, ctypes.byref(state)) != 0:
            return set()   # no controller connected
        pad = state.Gamepad
        pressed = decode(pad.wButtons)
        pressed |= stick_directions(pad.sThumbLX, pad.sThumbLY)
        return pressed

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                cur = self._read_pressed()
            except Exception:
                continue
            for raw in newly_pressed(self._prev, cur):
                action = ACTION_FOR.get(raw)
                if action:
                    self._on_action(action)
            self._prev = cur
