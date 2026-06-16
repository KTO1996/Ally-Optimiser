"""Windows optimisation tweaks for the ROG Ally / Ally X.

This is the "everything, power-user" catalogue people commonly recommend for
handhelds: power plan, gaming, latency, visual-responsiveness and debloat
tweaks. Every tweak is **reversible** — before applying we record the previous
value (registry tweaks) or pair it with an explicit inverse command (service /
powercfg tweaks), and the engine can also drop a System Restore point first.

Design notes:
  * Tweaks are declared as data so the catalogue can be unit-tested off-Windows.
  * Registry changes use ``winreg`` (typed) and capture the prior value for an
    exact revert (including "value was absent" -> delete on revert).
  * Command tweaks (services, powercfg, appx) carry apply+revert command lists.
  * Off-Windows, or when RyzenAdj-style execution isn't possible, apply/revert
    run in **dry-run**: the planned actions are returned, nothing is changed.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Risk tiers — surfaced in the UI as coloured badges.
SAFE = "safe"
AGGRESSIVE = "aggressive"
EXPERIMENTAL = "experimental"

# Categories for grouping in the UI.
CAT_POWER = "Power & Performance"
CAT_GAMING = "Gaming"
CAT_RESPONSIVENESS = "Responsiveness & Visuals"
CAT_LATENCY = "Latency & Scheduling"
CAT_DEBLOAT = "Debloat & Background"


@dataclass(frozen=True)
class RegSpec:
    """A single registry value to set when a tweak is applied."""
    hive: str            # "HKCU" or "HKLM"
    path: str            # subkey path
    name: str            # value name
    type: str            # "REG_DWORD" or "REG_SZ"
    value: object        # value to write when optimised


@dataclass
class Tweak:
    id: str
    title: str
    description: str
    category: str
    risk: str = SAFE
    reversible: bool = True
    reg: List[RegSpec] = field(default_factory=list)
    apply_cmds: List[List[str]] = field(default_factory=list)
    revert_cmds: List[List[str]] = field(default_factory=list)
    # Optional human note shown when revert is imperfect (e.g. appx removal).
    revert_note: str = ""


@dataclass
class TweakResult:
    ok: bool
    tweak_id: str
    message: str
    actions: List[str] = field(default_factory=list)
    dry_run: bool = False


# --------------------------------------------------------------------------- #
#  Catalogue
# --------------------------------------------------------------------------- #
def all_tweaks() -> List[Tweak]:
    """Return the full ordered tweak catalogue."""
    t: List[Tweak] = []

    # ---- Power & Performance ------------------------------------------------
    t.append(Tweak(
        id="power_high_performance",
        title="Use High Performance power plan",
        description="Switches Windows to the High Performance power scheme so "
                    "the CPU/GPU aren't down-clocked by the OS governor.",
        category=CAT_POWER, risk=SAFE,
        apply_cmds=[["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"]],
        revert_cmds=[["powercfg", "/setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"]],
    ))
    t.append(Tweak(
        id="power_disable_hibernate",
        title="Disable hibernation",
        description="Frees several GB by removing hiberfil.sys. Handhelds use "
                    "modern standby, so hibernation is rarely needed.",
        category=CAT_POWER, risk=SAFE,
        apply_cmds=[["powercfg", "/hibernate", "off"]],
        revert_cmds=[["powercfg", "/hibernate", "on"]],
    ))
    t.append(Tweak(
        id="power_usb_suspend_off",
        title="Disable USB selective suspend",
        description="Stops Windows powering down USB devices (controllers, "
                    "docks) which can cause input hitches.",
        category=CAT_POWER, risk=SAFE,
        apply_cmds=[
            ["powercfg", "/setacvalueindex", "scheme_current", "sub_usb",
             "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "0"],
            ["powercfg", "/setactive", "scheme_current"],
        ],
        revert_cmds=[
            ["powercfg", "/setacvalueindex", "scheme_current", "sub_usb",
             "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "1"],
            ["powercfg", "/setactive", "scheme_current"],
        ],
    ))

    # ---- Gaming -------------------------------------------------------------
    t.append(Tweak(
        id="game_mode_on",
        title="Enable Windows Game Mode",
        description="Prioritises the foreground game and suppresses background "
                    "interruptions (updates, notifications).",
        category=CAT_GAMING, risk=SAFE,
        reg=[
            RegSpec("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", "REG_DWORD", 1),
            RegSpec("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", "REG_DWORD", 1),
        ],
    ))
    t.append(Tweak(
        id="game_dvr_off",
        title="Disable Game DVR / background recording",
        description="Turns off the Xbox Game Bar background recorder, which "
                    "otherwise steals GPU time and adds latency.",
        category=CAT_GAMING, risk=SAFE,
        reg=[
            RegSpec("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", "REG_DWORD", 0),
            RegSpec("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
                    "AllowGameDVR", "REG_DWORD", 0),
        ],
    ))
    t.append(Tweak(
        id="gpu_hags_on",
        title="Hardware-accelerated GPU scheduling",
        description="Lets the GPU manage its own memory/queues — can lower "
                    "latency on RDNA APUs. Requires a reboot to take effect.",
        category=CAT_GAMING, risk=AGGRESSIVE,
        reg=[RegSpec("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                     "HwSchMode", "REG_DWORD", 2)],
    ))
    t.append(Tweak(
        id="mpo_disable",
        title="Disable Multi-Plane Overlay (MPO)",
        description="A common fix for screen flicker/stutter on Windows + AMD. "
                    "Disables MPO via OverlayTestMode. Reboot to apply.",
        category=CAT_GAMING, risk=EXPERIMENTAL,
        reg=[RegSpec("HKLM", r"SOFTWARE\Microsoft\Windows\Dwm",
                     "OverlayTestMode", "REG_DWORD", 5)],
    ))

    # ---- Responsiveness & Visuals ------------------------------------------
    t.append(Tweak(
        id="visual_fx_performance",
        title="Visual effects: adjust for best performance",
        description="Disables animations/shadows/fades for a snappier UI and a "
                    "few extra frames.",
        category=CAT_RESPONSIVENESS, risk=SAFE,
        reg=[RegSpec("HKCU",
                     r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                     "VisualFXSetting", "REG_DWORD", 2)],
    ))
    t.append(Tweak(
        id="transparency_off",
        title="Disable transparency effects",
        description="Turns off acrylic/blur transparency, saving a little GPU.",
        category=CAT_RESPONSIVENESS, risk=SAFE,
        reg=[RegSpec("HKCU",
                     r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                     "EnableTransparency", "REG_DWORD", 0)],
    ))
    t.append(Tweak(
        id="menu_show_delay",
        title="Remove menu show delay",
        description="Drops MenuShowDelay to make menus open instantly.",
        category=CAT_RESPONSIVENESS, risk=SAFE,
        reg=[RegSpec("HKCU", r"Control Panel\Desktop", "MenuShowDelay", "REG_SZ", "0")],
    ))
    t.append(Tweak(
        id="mouse_accel_off",
        title="Disable mouse acceleration",
        description="Turns off 'enhance pointer precision' for 1:1 aiming with a "
                    "mouse or trackpad.",
        category=CAT_RESPONSIVENESS, risk=SAFE,
        reg=[
            RegSpec("HKCU", r"Control Panel\Mouse", "MouseSpeed", "REG_SZ", "0"),
            RegSpec("HKCU", r"Control Panel\Mouse", "MouseThreshold1", "REG_SZ", "0"),
            RegSpec("HKCU", r"Control Panel\Mouse", "MouseThreshold2", "REG_SZ", "0"),
        ],
    ))

    # ---- Latency & Scheduling ----------------------------------------------
    t.append(Tweak(
        id="mmcss_gaming",
        title="MMCSS: maximise gaming responsiveness",
        description="Tunes the multimedia scheduler (SystemResponsiveness=0) and "
                    "raises the Games task priority for smoother frame delivery.",
        category=CAT_LATENCY, risk=AGGRESSIVE,
        reg=[
            RegSpec("HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                    "SystemResponsiveness", "REG_DWORD", 0),
            RegSpec("HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
                    "GPU Priority", "REG_DWORD", 8),
            RegSpec("HKLM",
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
                    "Priority", "REG_DWORD", 6),
        ],
    ))
    t.append(Tweak(
        id="network_throttling_off",
        title="Disable network throttling",
        description="Sets NetworkThrottlingIndex to off — recommended for "
                    "low-latency online play.",
        category=CAT_LATENCY, risk=AGGRESSIVE,
        reg=[RegSpec("HKLM",
                     r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
                     "NetworkThrottlingIndex", "REG_DWORD", 0xFFFFFFFF)],
    ))
    t.append(Tweak(
        id="win32_priority_separation",
        title="Boost foreground app priority",
        description="Sets Win32PrioritySeparation=38 so the focused game gets "
                    "longer, more frequent CPU quanta.",
        category=CAT_LATENCY, risk=EXPERIMENTAL,
        reg=[RegSpec("HKLM", r"SYSTEM\CurrentControlSet\Control\PriorityControl",
                     "Win32PrioritySeparation", "REG_DWORD", 38)],
    ))

    # ---- Debloat & Background ----------------------------------------------
    t.append(Tweak(
        id="svc_diagtrack",
        title="Disable telemetry (DiagTrack) service",
        description="Stops the Connected User Experiences and Telemetry service "
                    "from running in the background.",
        category=CAT_DEBLOAT, risk=AGGRESSIVE,
        apply_cmds=[["sc", "stop", "DiagTrack"], ["sc", "config", "DiagTrack", "start=", "disabled"]],
        revert_cmds=[["sc", "config", "DiagTrack", "start=", "auto"], ["sc", "start", "DiagTrack"]],
    ))
    t.append(Tweak(
        id="svc_sysmain",
        title="Disable SysMain (Superfetch)",
        description="On an NVMe handheld SysMain mostly causes idle disk churn; "
                    "disabling it frees CPU and I/O.",
        category=CAT_DEBLOAT, risk=AGGRESSIVE,
        apply_cmds=[["sc", "stop", "SysMain"], ["sc", "config", "SysMain", "start=", "disabled"]],
        revert_cmds=[["sc", "config", "SysMain", "start=", "auto"], ["sc", "start", "SysMain"]],
    ))
    t.append(Tweak(
        id="disable_consumer_features",
        title="Stop auto-installed 'suggested' apps",
        description="Disables Windows consumer features that silently install "
                    "promoted apps and games.",
        category=CAT_DEBLOAT, risk=AGGRESSIVE,
        reg=[RegSpec("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
                     "DisableWindowsConsumerFeatures", "REG_DWORD", 1)],
    ))
    t.append(Tweak(
        id="debloat_appx",
        title="Remove common pre-installed bloat apps",
        description="Uninstalls a curated set of rarely-used preinstalled apps "
                    "(Solitaire, Bing News/Weather, Clipchamp, etc.). Does NOT "
                    "touch Xbox/Game Pass apps.",
        category=CAT_DEBLOAT, risk=EXPERIMENTAL, reversible=False,
        revert_note="Removed apps can be reinstalled from the Microsoft Store.",
        apply_cmds=[
            ["powershell", "-NoProfile", "-Command", _appx_remove_script()],
        ],
    ))

    return t


# Bloat packages safe to remove on a gaming handheld. Deliberately excludes
# anything Xbox / Game Pass / GameBar related so Game Pass keeps working.
_BLOAT_APPX = [
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.BingNews",
    "Microsoft.BingWeather",
    "Microsoft.BingFinance",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.WindowsFeedbackHub",
    "Microsoft.MicrosoftOfficeHub",
    "Microsoft.People",
    "Microsoft.Todos",
    "Clipchamp.Clipchamp",
    "Microsoft.PowerAutomateDesktop",
]


def _appx_remove_script() -> str:
    names = ",".join(f"'{n}'" for n in _BLOAT_APPX)
    return (
        f"$pkgs=@({names}); foreach($p in $pkgs)"
        "{Get-AppxPackage -Name $p | Remove-AppxPackage -ErrorAction SilentlyContinue}"
    )


# --------------------------------------------------------------------------- #
#  Registry helpers (Windows only)
# --------------------------------------------------------------------------- #
_HIVES = {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE"}


def _winreg():
    try:
        import winreg  # type: ignore
        return winreg
    except Exception:
        return None


def _hive_const(winreg, hive: str):
    return getattr(winreg, _HIVES[hive])


def read_reg(spec: RegSpec):
    """Return the current value, or None if the value/key is absent."""
    winreg = _winreg()
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(_hive_const(winreg, spec.hive), spec.path) as key:
            value, _ = winreg.QueryValueEx(key, spec.name)
            return value
    except FileNotFoundError:
        return None
    except OSError:
        return None


def write_reg(spec: RegSpec, value) -> None:
    winreg = _winreg()
    if winreg is None:
        raise RuntimeError("winreg unavailable")
    reg_type = getattr(winreg, spec.type)
    key = winreg.CreateKeyEx(_hive_const(winreg, spec.hive), spec.path, 0,
                             winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, spec.name, 0, reg_type, value)
    finally:
        winreg.CloseKey(key)


def delete_reg_value(spec: RegSpec) -> None:
    winreg = _winreg()
    if winreg is None:
        return
    try:
        with winreg.OpenKey(_hive_const(winreg, spec.hive), spec.path, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, spec.name)
    except FileNotFoundError:
        pass
    except OSError:
        pass
