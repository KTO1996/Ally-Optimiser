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

# Exact names that are never actual games.
_NON_GAME_NAMES = {
    "steamworks shared", "steamworks common redistributables",
    "soundtrack", "proton", "directx", "vcredist",
}

# Substrings that mark a Steam entry as a tool/extra rather than a game.
_NON_GAME_SUBSTRINGS = (
    "soundtrack", "dedicated server", "steam linux runtime", "proton",
    "steamvr", "sdk", "benchmark", "redistributable", "wallpaper engine helper",
    "blender", "audio production",
)


def _looks_non_game(name: str) -> bool:
    norm = _normalise(name)
    if norm in _NON_GAME_NAMES:
        return True
    return any(sub in norm for sub in _NON_GAME_SUBSTRINGS)


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
            if _looks_non_game(name):
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
    """Detect Xbox / Game Pass PC games (not every Store app).

    An installed Xbox PC game has a ``MicrosoftGame.config`` in its install
    folder — filtering on that excludes the dozens of inbox/system Store apps
    that the old ``SignatureKind='Store'`` filter wrongly picked up.
    """
    if not IS_WINDOWS:
        return []
    ps = (
        "Get-AppxPackage | Where-Object { $_.InstallLocation -and "
        "(Test-Path (Join-Path $_.InstallLocation 'MicrosoftGame.config')) } | "
        "Select-Object Name | ConvertTo-Json -Compress"
    )
    try:
        out = winproc.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=90,
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
    """Installed GOG Galaxy games only.

    Reads the local Galaxy DB but joins on ``InstalledBaseProducts`` so we get
    only games that are actually installed — not every title Galaxy knows about
    (the old ``GamePieces`` query returned the whole owned/known library).
    """
    if not IS_WINDOWS:
        return []
    db = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "GOG.com", "Galaxy", "storage", "galaxy-2.0.db",
    )
    if not os.path.isfile(db):
        return []
    return _gog_installed_from_db(db)


def _gog_installed_from_db(db: str) -> List[DetectedGame]:
    import sqlite3
    results: List[DetectedGame] = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        # Title lives in LimitedDetails; install state in InstalledBaseProducts.
        queries = [
            "SELECT ld.title FROM InstalledBaseProducts ip "
            "JOIN LimitedDetails ld ON ld.productId = ip.productId",
            "SELECT ld.title FROM InstalledBaseProducts ip "
            "JOIN LimitedDetails ld ON ld.id = ip.productId",
        ]
        rows = None
        for q in queries:
            try:
                rows = con.execute(q).fetchall()
                break
            except sqlite3.Error:
                continue
        for row in rows or []:
            title = (row[0] or "").strip() if row and row[0] else ""
            if title and not _looks_non_game(title):
                results.append(DetectedGame(name=title, process_name=None, source="GOG"))
    finally:
        con.close()
    return results



# --------------------------------------------------------------------------- #
# Local folder scan (games installed outside any launcher)
# --------------------------------------------------------------------------- #
# Executable name fragments that are never the game itself.
_NON_GAME_EXE = (
    "unins", "setup", "install", "redist", "vcredist", "vc_redist", "dxsetup",
    "dotnet", "directx", "oalinst", "crashpad", "crashhandler", "crashreport",
    "unitycrashhandler", "ueprereqsetup", "prerequisites", "helper", "config",
    "cleanup", "report", "diag", "benchmark", "launcher", "updater", "update",
    "server", "editor", "touchup", "notification", "easyanticheat", "battleye",
)


def _is_game_exe(filename: str) -> bool:
    low = filename.lower()
    if not low.endswith(".exe"):
        return False
    stem = low[:-4]
    return not any(frag in stem for frag in _NON_GAME_EXE)


def _pick_main_exe(folder: str, max_depth: int = 2) -> Optional[str]:
    """Choose the most likely game executable inside a folder.

    Prefers an .exe whose name matches the folder, else the largest candidate.
    """
    folder_key = _normalise(os.path.basename(folder)).replace(" ", "")
    base_depth = folder.rstrip("\\/").count(os.sep)
    candidates = []
    for root, _dirs, files in os.walk(folder):
        if root.count(os.sep) - base_depth >= max_depth:
            _dirs[:] = []
        for f in files:
            if _is_game_exe(f):
                path = os.path.join(root, f)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                name_match = _normalise(f[:-4]).replace(" ", "") == folder_key
                candidates.append((name_match, size, path))
    if not candidates:
        return None
    # Name match wins; otherwise the biggest executable.
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return candidates[0][2]


def scan_folder(path: str, max_depth: int = 2) -> List[DetectedGame]:
    """Treat each immediate subfolder of ``path`` as a game; find its main exe."""
    if not path or not os.path.isdir(path):
        return []
    results: List[DetectedGame] = []
    try:
        entries = list(os.scandir(path))
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name.strip()
        if not name or _looks_non_game(name):
            continue
        exe = _pick_main_exe(entry.path, max_depth)
        if exe:
            results.append(DetectedGame(name=name, process_name=os.path.basename(exe),
                                        source="Folder"))
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
    # User-chosen folders for games installed outside any launcher.
    for folder in config.get("game_folders", []) or []:
        ordered += _safe(scan_folder, folder)
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
