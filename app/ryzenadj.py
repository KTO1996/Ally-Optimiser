"""RyzenAdj integration: build the command line, apply a profile, reset.

RyzenAdj is an external, unsigned GPL tool that is **not bundled** with this
app (see README). The user downloads it and points ``ryzenadj_path`` in
config.json at it.

RyzenAdj takes power limits in **milliwatts**, so watts are multiplied by
1000. We map a profile onto the three relevant limits:

  * ``--stapm-limit``  sustained (long-term) power   -> tdp_sustained
  * ``--slow-limit``   medium window power           -> tdp_sustained
  * ``--fast-limit``   short boost power             -> tdp_boost

If the configured exe can't be found we fall back to **dry-run** mode: the
command that *would* run is returned instead of being executed, so the UI
remains usable/testable off-device.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import winproc


@dataclass
class ApplyResult:
    ok: bool
    command: List[str]
    message: str
    dry_run: bool = False


def watts_to_mw(watts: float) -> int:
    """Convert watts to milliwatts for RyzenAdj (W x 1000)."""
    return int(round(float(watts) * 1000))


def clamp_tdp(watts: float, min_tdp: int, max_tdp: int) -> int:
    """Clamp a wattage into the configured safe band."""
    return int(max(min_tdp, min(max_tdp, round(float(watts)))))


def resolve_exe(ryzenadj_path: str) -> Optional[str]:
    """Return an absolute path to ryzenadj.exe, or None if not found.

    Accepts an absolute path, a path relative to cwd, or a bare name found on
    PATH.
    """
    if not ryzenadj_path:
        return None
    if os.path.isfile(ryzenadj_path):
        return os.path.abspath(ryzenadj_path)
    found = shutil.which(ryzenadj_path)
    return found


def build_command(
    exe: str,
    tdp_sustained: float,
    tdp_boost: float,
    min_tdp: int = 5,
    max_tdp: int = 40,
) -> List[str]:
    """Build the RyzenAdj argv for the given sustained/boost wattages."""
    sustained = clamp_tdp(tdp_sustained, min_tdp, max_tdp)
    boost = clamp_tdp(tdp_boost, min_tdp, max_tdp)
    # Boost should never be below sustained.
    boost = max(boost, sustained)
    return [
        exe,
        f"--stapm-limit={watts_to_mw(sustained)}",
        f"--slow-limit={watts_to_mw(sustained)}",
        f"--fast-limit={watts_to_mw(boost)}",
    ]


def build_reset_command(exe: str, plugged_default_tdp: int) -> List[str]:
    """Build a command that restores a safe default (plugged) limit.

    RyzenAdj has no universal "factory reset" flag across all platforms, so we
    re-apply the configured plugged-in default as a known-good baseline.
    """
    mw = watts_to_mw(plugged_default_tdp)
    return [
        exe,
        f"--stapm-limit={mw}",
        f"--slow-limit={mw}",
        f"--fast-limit={mw}",
    ]


def _run(cmd: List[str]) -> ApplyResult:
    try:
        proc = winproc.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return ApplyResult(False, cmd, "RyzenAdj executable not found.")
    except subprocess.TimeoutExpired:
        return ApplyResult(False, cmd, "RyzenAdj timed out.")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return ApplyResult(False, cmd, f"RyzenAdj failed: {detail}")
    return ApplyResult(True, cmd, (proc.stdout or "Applied.").strip())


def apply_profile(profile: Dict, config: Dict) -> ApplyResult:
    """Apply a profile dict (tdp_sustained/tdp_boost) using config settings."""
    exe = resolve_exe(config.get("ryzenadj_path", "ryzenadj.exe"))
    min_tdp = int(config.get("min_tdp", 5))
    max_tdp = int(config.get("max_tdp", 40))
    sustained = profile.get("tdp_sustained", config.get("plugged_default_tdp", 25))
    boost = profile.get("tdp_boost", sustained)

    if exe is None:
        cmd = build_command("ryzenadj.exe", sustained, boost, min_tdp, max_tdp)
        return ApplyResult(
            False, cmd,
            "RyzenAdj not found — showing the command that would run "
            "(dry-run). Set its path via the 'RyzenAdj…' button.",
            dry_run=True,
        )
    cmd = build_command(exe, sustained, boost, min_tdp, max_tdp)
    return _run(cmd)


def reset(config: Dict) -> ApplyResult:
    exe = resolve_exe(config.get("ryzenadj_path", "ryzenadj.exe"))
    plugged = int(config.get("plugged_default_tdp", 25))
    if exe is None:
        cmd = build_reset_command("ryzenadj.exe", plugged)
        return ApplyResult(False, cmd, "RyzenAdj not found (dry-run).", dry_run=True)
    return _run(build_reset_command(exe, plugged))
