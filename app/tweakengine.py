"""Apply / revert engine for the Windows tweak catalogue.

Responsibilities:
  * Apply a tweak, recording the previous registry values so it can be undone
    exactly (including deleting values that didn't exist before).
  * Revert a tweak using the recorded values (registry) or its paired inverse
    commands (services / powercfg).
  * Persist state to ``profiles/tweak_state.json`` so revert survives restarts.
  * Optionally drop a System Restore point before the first change.

Off-Windows (or when winreg/commands can't run) everything is **dry-run**:
the planned actions are reported and nothing is changed, so the UI and logic
stay testable on any platform.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict, List, Optional

from . import systweaks as st
from . import winproc
from .paths import PROFILES_DIR

STATE_FILE = os.path.join(PROFILES_DIR, "tweak_state.json")


def is_windows() -> bool:
    return sys.platform.startswith("win")


class TweakEngine:
    def __init__(self, dry_run: Optional[bool] = None) -> None:
        # Default to dry-run whenever we're not on Windows.
        self.dry_run = (not is_windows()) if dry_run is None else dry_run
        self.state: Dict[str, dict] = self._load_state()

    # ---------------------------------------------------------------- state --
    def _load_state(self) -> Dict[str, dict]:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(self) -> None:
        os.makedirs(PROFILES_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=2)
        os.replace(tmp, STATE_FILE)

    def is_applied(self, tweak: st.Tweak) -> bool:
        """Best-effort: read registry to confirm, else fall back to state flag."""
        if tweak.reg and not self.dry_run:
            try:
                return all(st.read_reg(s) == s.value for s in tweak.reg)
            except Exception:
                pass
        return bool(self.state.get(tweak.id, {}).get("applied"))

    def applied_tweaks(self) -> List[st.Tweak]:
        """Tweaks currently recorded as applied (per saved state)."""
        return [t for t in st.all_tweaks() if self.state.get(t.id, {}).get("applied")]

    def revert_all(self) -> List[st.TweakResult]:
        """Revert every tweak currently marked applied. Returns each result."""
        return [self.revert(t) for t in self.applied_tweaks()]

    # --------------------------------------------------------------- actions --
    def _run_cmds(self, cmds: List[List[str]], actions: List[str]) -> Optional[str]:
        """Run command list; return an error string on first failure else None."""
        for cmd in cmds:
            actions.append(" ".join(cmd))
            if self.dry_run:
                continue
            try:
                proc = winproc.run(cmd, capture_output=True, text=True, timeout=120)
            except FileNotFoundError:
                return f"Command not found: {cmd[0]}"
            except subprocess.TimeoutExpired:
                return f"Timed out: {' '.join(cmd)}"
            # `sc stop` on an already-stopped service returns non-zero; tolerate.
            if proc.returncode not in (0, 1056, 1062, 2):
                detail = (proc.stderr or proc.stdout or "").strip()
                return f"Failed ({proc.returncode}): {' '.join(cmd)}\n{detail}"
        return None

    def apply(self, tweak: st.Tweak) -> st.TweakResult:
        actions: List[str] = []
        reg_prev: Dict[str, object] = {}

        # Registry: capture previous values for an exact revert, then write.
        for i, spec in enumerate(tweak.reg):
            key = f"{i}"
            prev = None if self.dry_run else st.read_reg(spec)
            reg_prev[key] = prev
            actions.append(
                f"{spec.hive}\\{spec.path}\\{spec.name} = {spec.value} "
                f"(was {prev!r})"
            )
            if not self.dry_run:
                try:
                    st.write_reg(spec, spec.value)
                except Exception as exc:
                    return st.TweakResult(False, tweak.id, f"Registry write failed: {exc}",
                                          actions, self.dry_run)

        err = self._run_cmds(tweak.apply_cmds, actions)
        if err:
            return st.TweakResult(False, tweak.id, err, actions, self.dry_run)

        self.state[tweak.id] = {"applied": True, "reg_prev": reg_prev}
        if not self.dry_run:
            self._save_state()
        msg = "Planned (dry-run)." if self.dry_run else "Applied."
        return st.TweakResult(True, tweak.id, msg, actions, self.dry_run)

    def revert(self, tweak: st.Tweak) -> st.TweakResult:
        actions: List[str] = []
        saved = self.state.get(tweak.id, {})
        reg_prev: Dict[str, object] = saved.get("reg_prev", {})

        # Registry: restore the captured previous value, or delete if absent.
        for i, spec in enumerate(tweak.reg):
            prev = reg_prev.get(str(i))
            if prev is None:
                actions.append(f"delete {spec.hive}\\{spec.path}\\{spec.name}")
                if not self.dry_run:
                    st.delete_reg_value(spec)
            else:
                actions.append(f"{spec.hive}\\{spec.path}\\{spec.name} = {prev!r}")
                if not self.dry_run:
                    try:
                        st.write_reg(spec, prev)
                    except Exception as exc:
                        return st.TweakResult(False, tweak.id,
                                              f"Registry restore failed: {exc}",
                                              actions, self.dry_run)

        err = self._run_cmds(tweak.revert_cmds, actions)
        if err:
            return st.TweakResult(False, tweak.id, err, actions, self.dry_run)

        self.state[tweak.id] = {"applied": False, "reg_prev": {}}
        if not self.dry_run:
            self._save_state()
        if not tweak.reversible and not tweak.revert_cmds:
            return st.TweakResult(
                True, tweak.id,
                tweak.revert_note or "Marked reverted (manual undo may be needed).",
                actions, self.dry_run,
            )
        msg = "Planned revert (dry-run)." if self.dry_run else "Reverted."
        return st.TweakResult(True, tweak.id, msg, actions, self.dry_run)

    # -------------------------------------------------------- restore point --
    def create_restore_point(self, description: str = "Ally Optimizer tweaks") -> st.TweakResult:
        """Create a Windows System Restore point (best effort)."""
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            f"Checkpoint-Computer -Description '{description}' "
            "-RestorePointType 'MODIFY_SETTINGS'",
        ]
        if self.dry_run:
            return st.TweakResult(True, "restore_point",
                                  "Planned restore point (dry-run).",
                                  [" ".join(cmd)], True)
        try:
            proc = winproc.run(cmd, capture_output=True, text=True, timeout=180)
        except Exception as exc:
            return st.TweakResult(False, "restore_point", f"Restore point failed: {exc}")
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return st.TweakResult(False, "restore_point",
                                  "Could not create a restore point. System "
                                  "Protection may be off for this drive.\n" + detail)
        return st.TweakResult(True, "restore_point", "System Restore point created.")
