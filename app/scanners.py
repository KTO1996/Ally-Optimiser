"""Installed-game scanners for multiple sources.

The ROG Xbox Ally runs full Windows, so games come from many places. This
module detects installed games from:

  * Steam        — parse ``appmanifest_*.acf`` files (lightweight key-value,
                   no VDF dependency)
  * Xbox / Game Pass — ``Get-AppxPackage`` via PowerShell (UWP/MSIX)
  * Epic Games   — JSON manifests under ProgramData
  * GOG Galaxy   — its local SQLite database
  * Generic      — Windows uninstall registry keys + Start-menu shortcuts
                   (catches EA, Ubisoft, Battle.net and standalone installers)

Every scanner is defensive: Windows-only sources return ``[]`` on other
platforms or on any error, so a single failing source never breaks the scan.
Results are de-duplicated by normalised name.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import winproc
from .paths import PROFILES_DIR

IS_WINDOWS = sys.platform.startswith("win")

# Where the most recent scan results are remembered between launches.
DETECTED_CACHE = os.path.join(PROFILES_DIR, "detected.json")

# Folders that are common but never actual games — skip during sweeps.
_NON_GAME_NAMES = {
    "steamworks shared", "steamworks common redistributables",
    "soundtrack", "proton", "directx", "vcredist",
}


@dataclass(frozen=True)
class DetectedGame:
    name: str
    process_name: Optional[str]
    source: str
    appid: Optional[str] = None   # Steam appid, when known (used for cover art)


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


# --------------------------------------------------------------------------- #
# Steam
# --------------------------------------------------------------------------- #
def scan_steam(steamapps_common_paths: List[str]) -> List[DetectedGame]:
    """Parse appmanifest_*.acf next to each steamapps/common path."""
    results: List[DetectedGame] = []
    for common in steamapps_common_paths or []:
        steamapps = os.path.dirname(common.rstrip("\\/"))  # .../steamapps
        if not os.path.isdir(steamapps):
            continue
        for acf in glob.glob(os.path.join(steamapps, "appmanifest_*.acf")):
            try:
                with open(acf, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            m = re.search(r'"name"\s+"([^"]+)"', text)
            if not m:
                continue
            name = m.group(1).strip()
            if _normalise(name) in _NON_GAME_NAMES:
                continue
            appid_m = re.search(r'"appid"\s+"(\d+)"', text)
            results.append(DetectedGame(
                name=name, process_name=None, source="Steam",
                appid=appid_m.group(1) if appid_m else None))
    return results


# --------------------------------------------------------------------------- #
# Xbox / Game Pass (UWP/MSIX)
# --------------------------------------------------------------------------- #
def scan_xbox() -> List[DetectedGame]:
    if not IS_WINDOWS:
        return []
    import subprocess
    # Gaming-related packages tend to live under these publishers/families.
    ps = (
        "Get-AppxPackage | Where-Object { $_.IsFramework -eq $false -and "
        "$_.SignatureKind -eq 'Store' } | "
        "Select-Object Name, PackageFamilyName | ConvertTo-Json -Compress"
    )
    try:
        out = winproc.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    results: List[DetectedGame] = []
    for pkg in data:
        raw = str(pkg.get("Name", "")).strip()
        if not raw:
            continue
        # Names look like "PublisherName.GameName"; show the last segment.
        pretty = raw.split(".")[-1]
        pretty = re.sub(r"(?<!^)(?=[A-Z])", " ", pretty).strip()
        results.append(DetectedGame(name=pretty or raw, process_name=None, source="Xbox"))
    return results


# --------------------------------------------------------------------------- #
# Epic Games
# --------------------------------------------------------------------------- #
def scan_epic() -> List[DetectedGame]:
    if not IS_WINDOWS:
        return []
    manifests = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "Epic", "EpicGamesLauncher", "Data", "Manifests",
    )
    if not os.path.isdir(manifests):
        return []
    results: List[DetectedGame] = []
    for item in glob.glob(os.path.join(manifests, "*.item")):
        try:
            with open(item, "r", encoding="utf-8", errors="ignore") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        name = (data.get("DisplayName") or "").strip()
        if not name:
            continue
        exe = (data.get("LaunchExecutable") or "").strip()
        proc = os.path.basename(exe) if exe else None
        results.append(DetectedGame(name=name, process_name=proc, source="Epic"))
    return results


# --------------------------------------------------------------------------- #
# GOG Galaxy
# --------------------------------------------------------------------------- #
def scan_gog() -> List[DetectedGame]:
    if not IS_WINDOWS:
        return []
    db = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "GOG.com", "Galaxy", "storage", "galaxy-2.0.db",
    )
    if not os.path.isfile(db):
        return []
    import sqlite3
    results: List[DetectedGame] = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "SELECT value FROM GamePieces WHERE value LIKE '%\"title\"%'"
            )
            for (value,) in cur.fetchall():
                try:
                    title = json.loads(value).get("title")
                except (json.JSONDecodeError, AttributeError):
                    title = None
                if title:
                    results.append(
                        DetectedGame(name=str(title), process_name=None, source="GOG")
                    )
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return results


# --------------------------------------------------------------------------- #
# Generic: Windows uninstall registry + Start-menu shortcuts
# --------------------------------------------------------------------------- #
def scan_registry_uninstall() -> List[DetectedGame]:
    """Read display names from the uninstall registry hives.

    Catches launcher-less installs and storefronts we don't parse directly
    (EA app, Ubisoft Connect, Battle.net titles, standalone installers).
    """
    if not IS_WINDOWS:
        return []
    try:
        import winreg  # type: ignore
    except ImportError:
        return []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    results: List[DetectedGame] = []
    for hive, subkey in roots:
        try:
            key = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(key)[0]):
            try:
                sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                name, _ = winreg.QueryValueEx(sub, "DisplayName")
            except OSError:
                continue
            try:
                system_component, _ = winreg.QueryValueEx(sub, "SystemComponent")
                if system_component:
                    continue
            except OSError:
                pass
            name = str(name).strip()
            if name and _normalise(name) not in _NON_GAME_NAMES:
                results.append(
                    DetectedGame(name=name, process_name=None, source="Installed")
                )
    return results


def scan_start_menu() -> List[DetectedGame]:
    """List Start-menu .lnk shortcuts as a last-resort catch-all."""
    if not IS_WINDOWS:
        return []
    dirs = [
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                     r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs"),
    ]
    results: List[DetectedGame] = []
    for base in dirs:
        if not base or not os.path.isdir(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            stem = os.path.splitext(os.path.basename(lnk))[0].strip()
            if stem and not stem.lower().startswith(("uninstall", "readme")):
                results.append(
                    DetectedGame(name=stem, process_name=None, source="Shortcut")
                )
    return results


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def scan_all(config: Dict, include_generic: Optional[bool] = None) -> List[DetectedGame]:
    """Run the game-library scanners and return de-duplicated results.

    De-dup keeps the *first* (more specific) source for a given name, so a
    Steam/Epic/GOG hit wins over a generic registry/shortcut hit.

    The generic Windows uninstall-registry + Start-menu sweep is **off by
    default** — it lists every installed program/shortcut (hundreds of
    non-games), not just games. Enable it with ``scan_include_generic: true`` in
    config.json if you want launcher-less titles (EA/Ubisoft/etc.) too.
    """
    steam_paths = list(config.get("steam_library_paths", []))
    steam_paths += list(config.get("extra_library_paths", []))
    if include_generic is None:
        include_generic = bool(config.get("scan_include_generic", False))

    ordered: List[DetectedGame] = []
    ordered += _safe(scan_steam, steam_paths)
    ordered += _safe(scan_xbox)
    ordered += _safe(scan_epic)
    ordered += _safe(scan_gog)
    if include_generic:
        ordered += _safe(scan_registry_uninstall)
        ordered += _safe(scan_start_menu)

    seen: Dict[str, DetectedGame] = {}
    for game in ordered:
        key = _normalise(game.name)
        if key and key not in seen:
            seen[key] = game
    return sorted(seen.values(), key=lambda g: g.name.lower())


# --------------------------------------------------------------------------- #
# Persist the most recent scan so the library survives a restart
# --------------------------------------------------------------------------- #
def save_detected(games: List[DetectedGame]) -> None:
    """Cache scan results to ``profiles/detected.json`` (atomic write)."""
    data = [{"name": g.name, "process_name": g.process_name,
             "source": g.source, "appid": g.appid} for g in games]
    try:
        os.makedirs(PROFILES_DIR, exist_ok=True)
        tmp = DETECTED_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, DETECTED_CACHE)
    except OSError:
        pass


def load_detected() -> List[DetectedGame]:
    """Reload the last cached scan results (empty list if none/invalid)."""
    if not os.path.isfile(DETECTED_CACHE):
        return []
    try:
        with open(DETECTED_CACHE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    out: List[DetectedGame] = []
    for d in data if isinstance(data, list) else []:
        try:
            out.append(DetectedGame(name=d["name"], process_name=d.get("process_name"),
                                    source=d.get("source", "Installed"),
                                    appid=d.get("appid")))
        except (KeyError, TypeError):
            continue
    return out


def _safe(fn, *args) -> List[DetectedGame]:
    try:
        return fn(*args)
    except Exception:
        return []
