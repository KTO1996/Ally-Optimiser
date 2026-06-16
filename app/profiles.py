"""Load/save ``profiles/games.json`` and small profile helpers.

The on-disk shape (see seed file) is::

    {
      "_readme": "...",
      "games": {
        "<Game Name>": {
          "process_name": "game.exe",
          "source": "...",
          "profiles": [
            {"label": "...", "tdp_sustained": 30, "tdp_boost": 35,
             "resolution": "1920x1080", "fps_cap": 120, "notes": "..."}
          ]
        }
      }
    }
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .paths import GAMES_FILE

_DEFAULT_README = (
    "Per-game profiles. 'tdp' fields are watts for RyzenAdj (sustained/boost). "
    "'source' notes where values came from. Edit this file directly, or use "
    "the app's 'Add / Edit Game' button. Add your own games freely — this "
    "file is yours."
)


def load_games() -> Dict[str, Any]:
    """Return the full games document, creating an empty skeleton if missing."""
    if not os.path.exists(GAMES_FILE):
        return {"_readme": _DEFAULT_README, "games": {}}
    try:
        with open(GAMES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {"_readme": _DEFAULT_README, "games": {}}
    data.setdefault("_readme", _DEFAULT_README)
    data.setdefault("games", {})
    return data


def save_games(doc: Dict[str, Any]) -> None:
    """Persist the games document atomically, preserving the _readme key."""
    doc.setdefault("_readme", _DEFAULT_README)
    doc.setdefault("games", {})
    os.makedirs(os.path.dirname(GAMES_FILE), exist_ok=True)
    tmp = GAMES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, GAMES_FILE)


def upsert_game(
    doc: Dict[str, Any],
    name: str,
    process_name: str,
    profiles: List[Dict[str, Any]],
    source: str = "manual entry",
) -> None:
    """Add or update a game entry in-place."""
    doc.setdefault("games", {})[name] = {
        "process_name": process_name,
        "source": source,
        "profiles": profiles,
    }


def find_game(doc: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    return doc.get("games", {}).get(name)
