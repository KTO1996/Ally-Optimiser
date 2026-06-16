"""'Find settings' links — open the user's browser to per-game lookups.

Per BRIEF.md these are **manual, single-lookup links only**. We do not scrape
or auto-import from these sites; the user reads the page and types numbers into
the Add/Edit form themselves.
"""
from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Dict, List, Tuple


def build_links(game_name: str, config: Dict) -> List[Tuple[str, str]]:
    """Return a list of (label, url) lookup links for a game."""
    q = urllib.parse.quote_plus(game_name)
    rogallylife_base = config.get("rogallylife_base_url", "https://rogallylife.com/?s=")

    # NOTE: rogally.games uses the standard WordPress search query param. If the
    # site changes its search pattern, update this single URL. We never request
    # it programmatically — it only ever opens in the user's browser.
    rogally_games = f"https://rogally.games/?s={q}"

    generic = (
        "https://www.google.com/search?q="
        + urllib.parse.quote_plus(f"{game_name} ROG Ally settings")
    )
    return [
        ("ROG Ally Life", f"{rogallylife_base}{q}"),
        ("rogally.games", rogally_games),
        ("Web search", generic),
    ]


def open_link(url: str) -> None:
    webbrowser.open(url, new=2)
