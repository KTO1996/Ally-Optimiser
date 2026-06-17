"""Small shared helper for running Windows commands with a dry-run fallback.

Used by the hibernation and boost modules. Off-Windows (or when ``dry_run`` is
forced) the planned commands are returned and nothing is executed, mirroring
the RyzenAdj/tweak-engine pattern so logic stays testable on any platform.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from . import winproc


def is_windows() -> bool:
    return sys.platform.startswith("win")


@dataclass
class CmdResult:
    ok: bool
    message: str
    actions: List[str] = field(default_factory=list)
    dry_run: bool = False


def run_commands(
    cmds: Sequence[Sequence[str]],
    dry_run: Optional[bool] = None,
    ok_returncodes: Sequence[int] = (0,),
    timeout: int = 60,
) -> CmdResult:
    """Run each command in order; stop and report on the first failure."""
    dry = (not is_windows()) if dry_run is None else dry_run
    actions: List[str] = []
    for cmd in cmds:
        actions.append(" ".join(cmd))
        if dry:
            continue
        try:
            proc = winproc.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return CmdResult(False, f"Command not found: {cmd[0]}", actions, dry)
        except subprocess.TimeoutExpired:
            return CmdResult(False, f"Timed out: {' '.join(cmd)}", actions, dry)
        if proc.returncode not in ok_returncodes:
            detail = (proc.stderr or proc.stdout or "").strip()
            return CmdResult(False, f"Failed ({proc.returncode}): {' '.join(cmd)}\n{detail}",
                             actions, dry)
    return CmdResult(True, "Planned (dry-run)." if dry else "Done.", actions, dry)


def query_text(cmd: Sequence[str], timeout: int = 15) -> str:
    """Run a command and return stdout (empty string off-Windows or on error)."""
    if not is_windows():
        return ""
    try:
        return winproc.run(list(cmd), capture_output=True, text=True,
                           timeout=timeout).stdout
    except Exception:
        return ""
