"""Import a game profile from pasted text or a link.

Two inputs are supported:

  * **Pasted text** — settings you copied from any guide. We parse TDP,
    resolution and FPS out of it. Always safe (you did the lookup).
  * **A URL** —
      - PCGamingWiki links use their public API (allowed) to derive a profile.
      - Any other URL is fetched best-effort and parsed. This is opt-in and
        carries a warning: many community sites (ROG Ally Life, rogally.games)
        block automated access (HTTP 403) and their terms disallow scraping, so
        it will often fail — copy the text and paste that instead.

Parsing is pure/regex-based so it's unit-testable; only fields actually found
are returned, and the user reviews them before saving.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional

from . import pcgamingwiki

_UA = {"User-Agent": "AllyOptimizer/1.0 (personal use)"}
_TIMEOUT = 12

_RES_WORDS = {"720p": "1280x720", "900p": "1600x900",
              "1080p": "1920x1080", "1440p": "2560x1440"}

# Sites we know block bots / forbid scraping — warn specifically.
_BLOCKED_HINTS = ("rogallylife.com", "rogally.games")


@dataclass
class ImportResult:
    ok: bool
    fields: Dict[str, object] = field(default_factory=dict)
    cover_url: Optional[str] = None
    message: str = ""
    warning: str = ""
    source: str = ""


def is_url(text: str) -> bool:
    return bool(re.match(r"\s*https?://", text or "", re.IGNORECASE))


def needs_fetch_warning(text: str) -> bool:
    """True if pasting this would trigger a non-API web fetch (show a warning)."""
    return is_url(text) and "pcgamingwiki.com" not in text.lower()


def _clamp_tdp(n: int) -> Optional[int]:
    return n if 3 <= n <= 60 else None


def parse_settings_text(text: str) -> Dict[str, object]:
    """Extract {tdp_sustained, tdp_boost, resolution, fps_cap, label} from text."""
    fields: Dict[str, object] = {}
    low = text.lower()

    # --- TDP -------------------------------------------------------------- #
    sustained = boost = None
    m = re.search(r"sustain\w*[^0-9]{0,16}(\d{1,2})", low)
    if m:
        sustained = _clamp_tdp(int(m.group(1)))
    m = re.search(r"boost[^0-9]{0,16}(\d{1,2})", low)
    if m:
        boost = _clamp_tdp(int(m.group(1)))
    if sustained is None and boost is None:
        # "15/20 W" style.
        m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*w", low)
        if m:
            sustained = _clamp_tdp(int(m.group(1)))
            boost = _clamp_tdp(int(m.group(2)))
    if sustained is None and boost is None:
        # A single TDP/SPL/watt figure.
        m = re.search(r"(?:tdp|spl|wattage|watts?)\D{0,16}(\d{1,2})", low)
        if not m:
            m = re.search(r"\b(\d{1,2})\s*w(?:atts?)?\b", low)
        if m:
            sustained = boost = _clamp_tdp(int(m.group(1)))
    if sustained is not None:
        fields["tdp_sustained"] = sustained
    if boost is not None:
        fields["tdp_boost"] = boost

    # --- Resolution ------------------------------------------------------- #
    m = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", low)
    if m:
        fields["resolution"] = f"{m.group(1)}x{m.group(2)}"
    else:
        for word, res in _RES_WORDS.items():
            if word in low:
                fields["resolution"] = res
                break

    # --- FPS -------------------------------------------------------------- #
    m = re.search(r"(\d{2,3})\s*fps", low) or re.search(r"fps[^0-9]{0,8}(\d{2,3})", low)
    if m:
        fps = int(m.group(1))
        if 15 <= fps <= 360:
            fields["fps_cap"] = fps

    # --- Label hint ------------------------------------------------------- #
    for word in ("battery", "balanced", "performance", "quality", "turbo", "silent"):
        if word in low:
            fields["label"] = word.capitalize()
            break

    return fields


def _fetch_text_and_cover(url: str) -> tuple[str, Optional[str]]:
    """Fetch a page, return (visible_text, og_image_url)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(800_000).decode("utf-8", "ignore")
    cover = None
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                  raw, re.IGNORECASE)
    if m:
        cover = m.group(1)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text, cover


def _pcgw_title_from_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return urllib.parse.unquote(tail).replace("_", " ")


def import_from_input(text: str, config: Dict) -> ImportResult:
    """Build a profile from pasted text or a URL."""
    text = (text or "").strip()
    if not text:
        return ImportResult(False, message="Nothing to import — paste a link or settings text.")

    if is_url(text):
        if "pcgamingwiki.com" in text.lower():
            title = _pcgw_title_from_url(text)
            profile = pcgamingwiki.suggest_profile(title, config)
            if profile:
                return ImportResult(True, fields=profile, source="PCGamingWiki API",
                                    message=f"Derived a starting profile for “{title}”.")
            return ImportResult(False, source="PCGamingWiki API",
                                message="PCGamingWiki had nothing usable for that page.")
        # Generic third-party URL — opt-in fetch with a warning.
        warning = ("Fetched a third-party page. Some sites (e.g. ROG Ally Life, "
                   "rogally.games) block automated access and forbid scraping — "
                   "if this fails or looks wrong, copy the settings text and paste "
                   "that instead.")
        try:
            page_text, cover = _fetch_text_and_cover(text)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403) or any(h in text.lower() for h in _BLOCKED_HINTS):
                return ImportResult(False, warning=warning,
                                    message=f"That site blocked automated access "
                                            f"(HTTP {exc.code}). Copy the settings "
                                            "text from the page and paste that instead.")
            return ImportResult(False, warning=warning, message=f"Couldn't fetch the page (HTTP {exc.code}).")
        except Exception as exc:
            return ImportResult(False, warning=warning, message=f"Couldn't fetch the page: {exc}")
        fields = parse_settings_text(page_text)
        ok = bool(fields)
        msg = ("Parsed settings from the page." if ok else
               "Fetched the page but found no recognisable TDP/resolution/FPS. "
               "Try copying just the settings text.")
        return ImportResult(ok, fields=fields, cover_url=cover, warning=warning,
                            source=text, message=msg)

    # Plain pasted text.
    fields = parse_settings_text(text)
    if fields:
        return ImportResult(True, fields=fields, source="pasted text",
                            message="Parsed settings from the pasted text.")
    return ImportResult(False, source="pasted text",
                        message="Couldn't find any TDP / resolution / FPS in that text.")


# urllib.parse is only needed by _pcgw_title_from_url; import lazily-safe here.
import urllib.parse  # noqa: E402
