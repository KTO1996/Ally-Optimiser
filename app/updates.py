"""Check GitHub Releases for a newer version.

Hits the public Releases API and compares the latest tag to the running
version. Network-light and fully optional — any failure returns "no update"
rather than raising.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

LATEST_RELEASE_API = "https://api.github.com/repos/KTO1996/Ally-Optimiser/releases/latest"
RELEASES_PAGE = "https://github.com/KTO1996/Ally-Optimiser/releases"
_UA = {"User-Agent": "AllyOptimizer/1.0", "Accept": "application/vnd.github+json"}


@dataclass
class UpdateInfo:
    current: str
    latest: str
    url: str
    update_available: bool
    asset_url: str = ""      # browser_download_url of the windows zip, if present
    asset_name: str = ""


def _parse(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True if version string ``latest`` is greater than ``current``."""
    a, b = _parse(latest), _parse(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def check_for_update(current_version: str, timeout: int = 8) -> Optional[UpdateInfo]:
    """Return UpdateInfo, or None if the check couldn't run."""
    try:
        req = urllib.request.Request(LATEST_RELEASE_API, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(200_000).decode("utf-8", "ignore"))
    except Exception:
        return None
    latest = data.get("tag_name") or data.get("name") or ""
    if not latest:
        return None
    url = data.get("html_url") or RELEASES_PAGE
    asset_url = asset_name = ""
    for asset in data.get("assets") or []:
        nm = asset.get("name", "")
        if nm.lower().endswith(".zip"):
            asset_url = asset.get("browser_download_url", "")
            asset_name = nm
            break
    return UpdateInfo(current=current_version, latest=latest, url=url,
                      update_available=is_newer(latest, current_version),
                      asset_url=asset_url, asset_name=asset_name)


def download_update(info: "UpdateInfo", dest_dir: str, timeout: int = 120) -> Optional[str]:
    """Download the release zip into ``dest_dir``; return the saved path or None."""
    if not info.asset_url:
        return None
    try:
        import os
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, info.asset_name or "AllyOptimizer-windows.zip")
        req = urllib.request.Request(info.asset_url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest
    except Exception:
        return None
