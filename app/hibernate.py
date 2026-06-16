"""Hibernation control for the ROG Ally.

The Ally (like most Windows handhelds) uses *modern standby* for sleep, which
quietly drains the battery overnight. Hibernation writes RAM to disk and draws
~zero power, so these helpers let the user:

  * see whether hibernation is available/enabled, and toggle it;
  * make the power button hibernate instead of sleep;
  * auto-hibernate after N minutes of sleep (hybrid);
  * hibernate right now.

All actions go through powercfg (dry-run off-Windows). powercfg power-setting
GUIDs are spelled out so the intent is readable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import wincmd

# powercfg subgroup / setting GUIDs.
SUB_BUTTONS = "4f971e89-eebd-4455-a8de-9e59040e7347"
PBUTTON_ACTION = "7648efa3-dd9c-4e3e-b566-50f929386280"   # power button action
SLEEP_BUTTON_ACTION = "96996bc0-ad50-47ec-923b-6f41874dd9eb"
SUB_SLEEP = "238c9fa8-0aad-41ed-83f4-97be242c8f20"
HIBERNATE_AFTER = "9d7815a6-7ee4-497e-8888-515a05f02364"  # idle->hibernate timeout

# Power-button action indices used by powercfg.
ACTION_SLEEP = "1"
ACTION_HIBERNATE = "2"


@dataclass
class HibernateState:
    available: bool = False
    enabled: bool = False
    detail: str = ""

    def summary(self) -> str:
        if not self.available:
            return "Hibernation unavailable on this system"
        return "Hibernation: ON" if self.enabled else "Hibernation: OFF"


def get_state() -> HibernateState:
    """Read hibernation availability/enabled via ``powercfg /a``."""
    out = wincmd.query_text(["powercfg", "/a"])
    if not out:
        return HibernateState(available=False, enabled=False,
                              detail="(powercfg not available here)")
    low = out.lower()
    # If 'Hibernate' appears under the "available" section it's enabled; powercfg
    # lists unavailable states separately under "not available".
    enabled = "hibernate" in low.split("following sleep states are not available")[0]
    available = "hibernate" in low
    return HibernateState(available=available, enabled=enabled, detail=out.strip())


def set_enabled(enabled: bool, dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Enable or disable hibernation (``powercfg /hibernate on|off``)."""
    return wincmd.run_commands(
        [["powercfg", "/hibernate", "on" if enabled else "off"]], dry_run)


def set_power_button_hibernate(dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Make the power and sleep buttons hibernate (both AC and battery)."""
    cmds = []
    for action_guid in (PBUTTON_ACTION, SLEEP_BUTTON_ACTION):
        cmds.append(["powercfg", "/setdcvalueindex", "scheme_current",
                     SUB_BUTTONS, action_guid, ACTION_HIBERNATE])
        cmds.append(["powercfg", "/setacvalueindex", "scheme_current",
                     SUB_BUTTONS, action_guid, ACTION_HIBERNATE])
    cmds.append(["powercfg", "/setactive", "scheme_current"])
    return wincmd.run_commands(cmds, dry_run)


def restore_power_button_sleep(dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Revert the power/sleep buttons back to sleep."""
    cmds = []
    for action_guid in (PBUTTON_ACTION, SLEEP_BUTTON_ACTION):
        cmds.append(["powercfg", "/setdcvalueindex", "scheme_current",
                     SUB_BUTTONS, action_guid, ACTION_SLEEP])
        cmds.append(["powercfg", "/setacvalueindex", "scheme_current",
                     SUB_BUTTONS, action_guid, ACTION_SLEEP])
    cmds.append(["powercfg", "/setactive", "scheme_current"])
    return wincmd.run_commands(cmds, dry_run)


def set_auto_hibernate_timeout(minutes: int, dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Auto-hibernate after ``minutes`` of sleep (0 disables). On battery + AC."""
    cmds = [
        ["powercfg", "/setdcvalueindex", "scheme_current", SUB_SLEEP,
         HIBERNATE_AFTER, str(int(minutes))],
        ["powercfg", "/setacvalueindex", "scheme_current", SUB_SLEEP,
         HIBERNATE_AFTER, str(int(minutes))],
        ["powercfg", "/setactive", "scheme_current"],
    ]
    return wincmd.run_commands(cmds, dry_run)


def hibernate_now(dry_run: Optional[bool] = None) -> wincmd.CmdResult:
    """Hibernate the machine immediately."""
    return wincmd.run_commands([["shutdown", "/h"]], dry_run)
