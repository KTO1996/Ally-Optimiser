# Changelog

All notable changes to Ally Optimizer. Dates are when the release was cut.

## v1.6.1
- **Clearer RyzenAdj errors:** when an Apply fails, the app now explains the
  usual causes — missing `WinRing0x64.dll`/`WinRing0x64.sys` next to
  `ryzenadj.exe`, or not running as Administrator — and shows RyzenAdj's exit
  code/output.

## v1.6.0
- **Fix:** the Xbox/Game Pass scanner now detects only actual games (those with
  a `MicrosoftGame.config`), instead of every Store-signed app — this was the
  source of the huge inflated counts.
- **Steam** scan now skips soundtracks, dedicated servers, Proton, runtimes, SDKs
  and other non-game entries.
- **Scan results now show a per-source breakdown** (Steam/Xbox/Epic/GOG counts)
  so unexpected numbers are easy to diagnose.
- **More cover art:** if a game has no Steam appid, the app now searches the
  Steam store by name to find its cover (cached) — so non-Steam games get art
  too, not just the handful that matched before.

## v1.5.2
- **Fix:** the list of detected games is now remembered between launches
  (cached to `profiles/detected.json` and reloaded on startup) — no more
  rescanning every time you open the app.

## v1.5.1 — on-device fixes
- **Fix:** no more PowerShell/console windows flashing — every system call now
  runs hidden.
- **Fix:** scanning no longer returns hundreds of non-games. The generic
  "every installed program + Start-menu shortcut" sweep is now **off by default**
  (opt-in via `scan_include_generic` in config); only real game libraries
  (Steam, Xbox/Game Pass, Epic, GOG) are scanned.
- **Fix:** the app no longer freezes during a scan or when clicking a game —
  scanning, cover-art and placeholder generation, and PCGamingWiki lookups all
  run off the UI thread now.

## v1.5.0
- **Auto-fill all** — one button to fetch cover art for the whole library and
  suggest a starting profile (PCGamingWiki) for any game without one.

## v1.4.0
- **Gamepad navigation** (Xbox controller via XInput): D-pad/stick to move, A to
  select, B back to Games, LB/RB to switch tabs. Toggle in Settings.
- **Placeholder cover art** — a grey gradient box with the game name when no real
  cover is found.

## v1.3.0
- **Auto-apply on game launch** (and reset on exit).
- **Quick presets** (Silent/Balanced/Turbo/Max), **battery-life estimates**,
  **TDP slider**, optional **display-resolution apply**.
- **Settings page** — device override, RyzenAdj path, hotkey/tray toggles,
  config **export/import**, **revert all tweaks**, **update check**.
- **List/grid library** with cover art; per-console **profile validation**
  (✓ fits / ⚠ check); **import settings** from a pasted link or text.

## v1.2.0
- **System Tweaks** (reversible Windows optimisations with restore point),
  **Boost** tab (AFMF/RSR/FSR guidance, Fullscreen-Exclusive toggle, Lossless
  Scaling / AnyFSE detect-launch), **Hibernation** controls, and **Armoury Crate**
  guided checklist.
- **CustomTkinter** redesign with dark/light themes; auto-detect Ally vs Ally X.

## v1.0.0
- Initial release: per-game TDP profiles via RyzenAdj, installed-games scanning
  (Steam/Xbox/Epic/GOG), PCGamingWiki suggestions, tray + hotkey, packaged exe.
