"""Auto-apply a game's profile when its process starts (and revert on exit).

A lightweight background poller (psutil) watches running process names. When a
known game's executable appears, it fires an ``on_start`` callback with the
game name; when it goes away, ``on_stop``. The GUI uses these to set the TDP
profile automatically and reset it afterwards — "set and forget".

``match_process`` (the name→game mapping) is pure and unit-tested; the thread
just wraps it.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


def process_name_map(games_doc: Dict) -> Dict[str, str]:
    """Map lower-cased process_name -> game name for games that declare one."""
    out: Dict[str, str] = {}
    for name, game in (games_doc.get("games") or {}).items():
        proc = (game or {}).get("process_name") or ""
        if proc:
            out[proc.strip().lower()] = name
    return out


def match_process(proc_name: str, proc_map: Dict[str, str]) -> Optional[str]:
    """Return the game a running process belongs to, or None."""
    if not proc_name:
        return None
    return proc_map.get(proc_name.strip().lower())


def _running_process_names() -> List[str]:
    if psutil is None:
        return []
    names: List[str] = []
    for p in psutil.process_iter(["name"]):
        try:
            n = p.info.get("name")
            if n:
                names.append(n)
        except Exception:
            continue
    return names


class GameWatcher:
    """Polls for known game processes and fires start/stop callbacks."""

    def __init__(self, get_proc_map: Callable[[], Dict[str, str]],
                 on_start: Callable[[str], None],
                 on_stop: Callable[[str], None],
                 interval: float = 5.0) -> None:
        self._get_proc_map = get_proc_map
        self._on_start = on_start
        self._on_stop = on_stop
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._active: Dict[str, str] = {}   # proc_name -> game currently running

    def available(self) -> bool:
        return psutil is not None

    def start(self) -> bool:
        if self._thread is not None or psutil is None:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._poll_once()
            except Exception:
                continue

    def _poll_once(self) -> None:
        proc_map = self._get_proc_map()
        running = {n.lower() for n in _running_process_names()}
        # Newly started games.
        for proc, game in proc_map.items():
            if proc in running and proc not in self._active:
                self._active[proc] = game
                self._on_start(game)
        # Games that have exited.
        for proc in list(self._active):
            if proc not in running:
                game = self._active.pop(proc)
                self._on_stop(game)
