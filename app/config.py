"""Load/save ``profiles/config.json``.

The seed config ships a minimal set of keys. We layer sensible defaults on
top at load time so older config files keep working when new keys are added,
and we only persist what differs from / extends the seed.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from .paths import CONFIG_FILE

# Defaults applied on top of whatever is on disk. Keys already present in the
# seed config.json (ryzenadj_path, steam_library_paths, etc.) are preserved.
DEFAULTS: Dict[str, Any] = {
    "ryzenadj_path": "ryzenadj.exe",
    "steam_library_paths": [
        "C:\\Program Files (x86)\\Steam\\steamapps\\common",
    ],
    "extra_library_paths": [],
    "battery_default_tdp": 12,
    "plugged_default_tdp": 25,
    "rogallylife_base_url": "https://rogallylife.com/?s=",
    # --- keys added by the app (v1) ---
    "reapply_hotkey": "ctrl+alt+a",   # global hotkey: reapply last profile
    "last_applied": None,             # {"game": str, "profile_label": str}
    "minimize_to_tray": True,
    "enable_hotkey": True,
    "enable_pcgamingwiki": True,
    "theme": "dark",                  # "dark" or "light"
    "device_override": None,          # force "ROG Ally" / "ROG Ally X" if mis-detected
    "anyfse_path": None,              # optional path to AnyFSE.exe for the Boost tab
    "auto_hibernate_minutes": 30,     # default timeout for the auto-hibernate control
    "auto_apply": False,              # auto-apply a game's profile when it launches
    "library_view": "list",           # "list" or "grid" for the Games library
    "seen_welcome": False,            # first-run onboarding shown?
    "enable_gamepad": False,          # Xbox-controller navigation
    "scan_include_generic": False,    # also list every installed program (noisy)
    "scan_shortcuts": True,           # detect games from Desktop shortcuts
    "game_folders": [],               # extra folders to scan for non-launcher games
    "ignored_games": [],              # names rejected in review — never re-added
    # Safety clamps (watts) sent to RyzenAdj. The Z2/Z2 Extreme is comfortable
    # in roughly this band; clamp keeps a bad profile from doing harm.
    "min_tdp": 5,
    "max_tdp": 40,
}


def load_config() -> Dict[str, Any]:
    """Return config with defaults filled in for any missing keys."""
    data: Dict[str, Any] = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            data = {}
    merged = dict(DEFAULTS)
    merged.update(data or {})
    return merged


def save_config(config: Dict[str, Any]) -> None:
    """Persist config atomically (write to temp, then replace)."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    os.replace(tmp, CONFIG_FILE)
