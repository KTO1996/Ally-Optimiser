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
import json
import os
import urllib.parse
import urllib.request
from typing import Optional

from .paths import PROFILES_DIR

COVERS_DIR = os.path.join(PROFILES_DIR, "covers")
PLACEHOLDERS_DIR = os.path.join(COVERS_DIR, "placeholders")
APPID_CACHE = os.path.join(COVERS_DIR, "appid_cache.json")
_UA = {"User-Agent": "AllyOptimizer/1.0 (personal use)"}
_TIMEOUT = 12

# Steam's storefront search — maps a game name to an appid (no API key needed).
_STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/?"


def _load_appid_cache() -> dict:
    try:
        with open(APPID_CACHE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_appid_cache(cache: dict) -> None:
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
        tmp = APPID_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, APPID_CACHE)
    except OSError:
        pass


def _name_variants(name: str):
    """Search terms to try, broadest match last (raw → cleaned → first words)."""
    try:
        from .scanners import clean_title
        cleaned = clean_title(name)
    except Exception:
        cleaned = name
    variants = [name.strip(), cleaned]
    words = cleaned.split()
    if len(words) > 3:
        variants.append(" ".join(words[:3]))   # drop trailing subtitle/edition
    seen, out = set(), []
    for v in variants:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def _steam_search_once(term: str) -> Optional[str]:
    try:
        url = _STEAM_SEARCH + urllib.parse.urlencode({"term": term, "cc": "us", "l": "en"})
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read(200_000).decode("utf-8", "ignore"))
        items = data.get("items") or []
        if items:
            return str(items[0].get("id") or "") or None
    except Exception:
        return None
    return None


def search_steam_appid(name: str) -> Optional[str]:
    """Find a Steam appid for a game name via the public store search.

    Tries the raw name, then a cleaned version (trademarks / edition words
    stripped), then just the first words — so partial/imperfect names still
    match. Cached (including misses) so repeat/auto-fill runs don't re-query.
    """
    if not name:
        return None
    cache = _load_appid_cache()
    key = name.strip().lower()
    if key in cache:
        return cache[key] or None
    appid = None
    for term in _name_variants(name):
        appid = _steam_search_once(term)
        if appid:
            break
    cache[key] = appid or ""
    _save_appid_cache(cache)
    return appid


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
                  name: Optional[str] = None, allow_network: bool = True) -> Optional[str]:
    """Return a local cover-image path for a game, downloading/caching if needed.

    Resolution order: a saved ``cover`` (path or URL) → the scanner's Steam
    ``appid`` → a Steam store search by ``name`` (so non-Steam games still get
    art). Returns None if nothing is found.
    """
    cover = (game or {}).get("cover") if game else None
    if cover:
        if not is_url(cover):
            return cover if os.path.isfile(cover) else None
        if allow_network:
            return download_cover(cover)
        return None
    if not allow_network:
        return None
    # Known Steam appid, else look one up by name.
    aid = appid or (search_steam_appid(name) if name else None)
    if aid:
        for url in (steam_cover_url(aid), steam_header_url(aid)):
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


def _wrap(draw, text: str, font, max_width: int):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def placeholder_for(name: str, grey: bool = True) -> Optional[str]:
    """Generate (and cache) a simple gradient placeholder with the game name.

    A grey (default) or red vertical gradient box with the game's name centred —
    enough to tell games apart when no real cover is available. Returns None if
    Pillow isn't installed (the UI then falls back to text).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    key = hashlib.sha1((f"ph::{grey}::" + name).encode("utf-8")).hexdigest()[:16]
    dest = os.path.join(PLACEHOLDERS_DIR, key + ".png")
    if os.path.isfile(dest):
        return dest
    try:
        os.makedirs(PLACEHOLDERS_DIR, exist_ok=True)
        W, H = 600, 900
        top, bot = ((70, 72, 78), (28, 28, 32)) if grey else ((150, 24, 30), (28, 10, 12))
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)],
                   fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))

        def _font(size):
            for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                         "C:\\Windows\\Fonts\\segoeuib.ttf",
                         "C:\\Windows\\Fonts\\arialbd.ttf"):
                if os.path.isfile(path):
                    return ImageFont.truetype(path, size)
            return ImageFont.load_default()

        font = _font(54)
        lines = _wrap(d, name, font, W - 80)
        line_h = d.textbbox((0, 0), "Ag", font=font)[3] + 12
        y = (H - line_h * len(lines)) / 2
        for line in lines:
            w = d.textbbox((0, 0), line, font=font)[2]
            d.text(((W - w) / 2, y), line, fill=(245, 245, 248), font=font)
            y += line_h
        d.rectangle([0, 0, W - 1, H - 1], outline=(44, 44, 52), width=6)
        img.save(dest, "PNG")
        return dest
    except Exception:
        return None
