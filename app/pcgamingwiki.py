"""PCGamingWiki auto-suggest (the safe-to-automate data source).

PCGamingWiki exposes a public MediaWiki API (no key required). Content is
CC BY-NC-SA — we attribute it in the suggestion notes. We query *objective
facts* about a game (FSR/DLSS support, Steam Deck status) and turn them into
an **algorithmic starting-point profile** when a game has no saved profile.

This is explicitly NOT the same as copying human-tested settings tables from
community sites: we derive a guess from facts, and we cache results so we
don't re-hit the API.

All network use is single-request, on-demand, and best-effort: any failure
returns ``None`` and the UI falls back to config defaults.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Dict, Optional

from .paths import CACHE_FILE

API = "https://www.pcgamingwiki.com/w/api.php"
USER_AGENT = "AllyOptimizer/1.0 (personal use; +https://github.com/)"
ATTRIBUTION = "Starting guess derived from PCGamingWiki facts (CC BY-NC-SA). Untested — tune to taste."


def _load_cache() -> Dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_cache(cache: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
    except OSError:
        pass


def _api_get(params: Dict[str, str]) -> Optional[Dict]:
    params = dict(params)
    params.setdefault("format", "json")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _fetch_page_text(game_name: str) -> Optional[str]:
    """Best-effort fetch of a game's wiki page wikitext (single request)."""
    data = _api_get({
        "action": "query",
        "titles": game_name,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
    })
    if not data:
        return None
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        revs = page.get("revisions")
        if not revs:
            continue
        slot = revs[0].get("slots", {}).get("main", {})
        return slot.get("*") or revs[0].get("*")
    return None


def suggest_profile(game_name: str, config: Dict) -> Optional[Dict]:
    """Return an algorithmic starting profile, or None if nothing usable.

    The shape matches a normal profile entry so it can be saved as-is.
    """
    if not config.get("enable_pcgamingwiki", True):
        return None

    cache = _load_cache()
    key = game_name.strip().lower()
    if key in cache:
        return cache[key]

    text = _fetch_page_text(game_name)
    facts_blob = (text or "").lower()

    has_fsr = "fsr" in facts_blob or "fidelityfx" in facts_blob
    has_dlss = "dlss" in facts_blob  # informational; Ally APU has no DLSS
    deck_verified = "verified" in facts_blob and "steam deck" in facts_blob

    plugged = int(config.get("plugged_default_tdp", 25))
    battery = int(config.get("battery_default_tdp", 12))

    # Heuristic: upscaling-capable and/or Deck-verified games tend to run well
    # at lower sustained power; otherwise lean toward the plugged default.
    if has_fsr or deck_verified:
        sustained, boost = battery + 3, plugged
    else:
        sustained, boost = plugged, plugged + 5

    note_bits = []
    if has_fsr:
        note_bits.append("FSR available")
    if has_dlss:
        note_bits.append("DLSS (PC only)")
    if deck_verified:
        note_bits.append("Steam Deck Verified")
    facts = ", ".join(note_bits) if note_bits else "no upscaling facts found"

    profile = {
        "label": "Suggested (untested)",
        "tdp_sustained": sustained,
        "tdp_boost": boost,
        "resolution": "1920x1080" if (has_fsr or deck_verified) else "1600x900",
        "fps_cap": 60,
        "notes": f"{ATTRIBUTION} Facts: {facts}.",
    }

    cache[key] = profile
    _save_cache(cache)
    return profile
