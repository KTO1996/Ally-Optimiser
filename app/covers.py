"""Game cover-art resolution and caching.

Covers make the library easy to scan at a glance. We resolve art in priority
order and cache it locally under ``profiles/covers/`` so it loads instantly and
works offline afterwards:

  1. A ``cover`` already saved on the game (local file → used as-is; URL →
     downloaded and cached).
  2. A Steam appid (from the scanner) → Steam's official library art.

Everything degrades gracefully: no network, a 404, or a missing appid simply
yields ``None`` and the UI falls back to a placeholder.
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from typing import Optional

from .paths import PROFILES_DIR

COVERS_DIR = os.path.join(PROFILES_DIR, "covers")
_UA = {"User-Agent": "AllyOptimizer/1.0 (personal use)"}
_TIMEOUT = 12


def steam_cover_url(appid: str) -> str:
    """Tall 600x900 library capsule (preferred portrait art)."""
    return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900.jpg"


def steam_header_url(appid: str) -> str:
    """Wide header capsule — fallback if the portrait one 404s."""
    return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"


def is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


def _cache_path(key: str, ext: str = ".jpg") -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(COVERS_DIR, digest + ext)


def download_cover(url: str) -> Optional[str]:
    """Download an image to the cache; return its local path, or None on failure."""
    dest = _cache_path(url)
    if os.path.isfile(dest):
        return dest
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            data = resp.read(4_000_000)  # cap at ~4 MB
        if not data:
            return None
        tmp = dest + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
        return dest
    except Exception:
        return None


def resolve_cover(game: Optional[dict], appid: Optional[str] = None,
                  allow_network: bool = True) -> Optional[str]:
    """Return a local cover-image path for a game, downloading/caching if needed.

    ``game`` is the saved profile dict (may carry a ``cover``); ``appid`` is the
    Steam id from the scanner when available.
    """
    cover = (game or {}).get("cover") if game else None
    if cover:
        if not is_url(cover):
            return cover if os.path.isfile(cover) else None
        if allow_network:
            return download_cover(cover)
        return None
    if appid and allow_network:
        for url in (steam_cover_url(appid), steam_header_url(appid)):
            path = download_cover(url)
            if path:
                return path
    return None


def cached_cover(game: Optional[dict]) -> Optional[str]:
    """Return a cover path only if it's already a local file (no network)."""
    cover = (game or {}).get("cover") if game else None
    if cover and not is_url(cover) and os.path.isfile(cover):
        return cover
    return None
