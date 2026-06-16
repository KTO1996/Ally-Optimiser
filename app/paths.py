"""Filesystem locations used across the app.

Resolves paths relative to the project root so the app works whether it's
run from source (``python main.py``) or frozen into an .exe later.
"""
from __future__ import annotations

import os
import sys


def _base_dir() -> str:
    # When frozen by PyInstaller, data sits next to the executable.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # Otherwise: project root = parent of this app/ package.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base_dir()
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
GAMES_FILE = os.path.join(PROFILES_DIR, "games.json")
CONFIG_FILE = os.path.join(PROFILES_DIR, "config.json")
CACHE_FILE = os.path.join(PROFILES_DIR, "pcgw_cache.json")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_ICO = os.path.join(ASSETS_DIR, "allyoptimizer.ico")
ICON_PNG = os.path.join(ASSETS_DIR, "allyoptimizer.png")
