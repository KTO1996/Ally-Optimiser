"""Export / import the user's configuration as a single zip.

Bundles the editable JSON under ``profiles/`` (games, config, and the tweak
state used for reverts) so a reinstall — or moving to another Ally — isn't a
fresh start. Cover-art cache is intentionally excluded (it re-downloads).
"""
from __future__ import annotations

import os
import zipfile
from typing import List

from .paths import CONFIG_FILE, GAMES_FILE, PROFILES_DIR

# Files included in a backup (basenames under profiles/).
_BACKUP_FILES = ["games.json", "config.json", "tweak_state.json"]


def export_config(dest_zip: str) -> List[str]:
    """Write a backup zip to ``dest_zip``; return the basenames included."""
    included: List[str] = []
    os.makedirs(os.path.dirname(os.path.abspath(dest_zip)) or ".", exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for base in _BACKUP_FILES:
            path = os.path.join(PROFILES_DIR, base)
            if os.path.isfile(path):
                zf.write(path, arcname=base)
                included.append(base)
    return included


def import_config(src_zip: str) -> List[str]:
    """Restore JSON files from a backup zip into ``profiles/``.

    Only known, safe filenames are extracted (no path traversal). Returns the
    basenames restored.
    """
    restored: List[str] = []
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with zipfile.ZipFile(src_zip, "r") as zf:
        for member in zf.namelist():
            base = os.path.basename(member)
            if base in _BACKUP_FILES and base == member:  # reject nested/traversal
                with zf.open(member) as src:
                    data = src.read()
                dest = os.path.join(PROFILES_DIR, base)
                tmp = dest + ".tmp"
                with open(tmp, "wb") as out:
                    out.write(data)
                os.replace(tmp, dest)
                restored.append(base)
    return restored
