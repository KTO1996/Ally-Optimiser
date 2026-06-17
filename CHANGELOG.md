# Changelog

All notable changes to Ally Optimizer. Dates are when the release was cut.

## v1.9.1
- **Kept games stick:** anything you Keep in Review (or add manually) is
  remembered as a known game and is never sent back to Review on later scans.
  Removing a game forgets it and ignores it so it won't reappear either.

## v1.9.0 — library management + review queue
- **Review queue:** uncertain detections (from folders/shortcuts) are now checked
  against Steam; anything that can't be confirmed as a game is held in a
  **Review** list instead of cluttering your library. Keep or Remove each — and
  removed items are remembered so they never come back.
- **Library filter:** a search box to quickly find a game in a big library.
- **Trusted vs. uncertain:** Steam/Xbox/Epic/GOG are added straight away; only
  heuristic finds go through review.
- Builds on the existing **Add / Edit / 🗑 Remove** so the whole library is yours
  to curate.

## v1.8.0
- **New: detect games from Desktop shortcuts** — resolves each shortcut to its
  real `.exe` and keeps the game-like ones (high precision; on by default).
- **Tighter folder scan** — skips Windows/system folders (so pointing it at a
  drive root no longer adds junk) and ignores tiny stub executables.
- **Fewer false positives** — common apps (browsers, Discord, launchers, etc.)
  and system executables are filtered out of folder/shortcut results.
- **New: "🗑 Remove"** button on a game to prune anything mis-detected.
- **Better cover matching** — names are cleaned (trademarks, edition words,
  "(detected)") and tried as variants against Steam search, so partial/imperfect
  names still find art.
- **Settings:** toggles for Desktop-shortcut detection and the deep (Start-menu +
  all-programs) scan.

## v1.7.0
- **Fix:** GOG now lists only **installed** games (via `InstalledBaseProducts`),
  not your entire owned/known GOG library.
- **New: "Scan folder…"** — point the app at the folder where you keep games
  installed outside any launcher; it finds each game's main executable. The
  folder is remembered and re-scanned with the normal Scan.
- **Fix:** long game titles now show in full in the list view (they wrap instead
  of being cut off).

## v1.6.2
- **Reliable admin elevation:** fixed the self-elevation fallback for the
  packaged exe (it previously passed the exe's own path as an argument and
  failed). The exe already requests admin via its manifest; now the fallback
  works too.
- **Admin visibility:** Settings shows whether you're running as Administrator,
  with a **"Relaunch as administrator"** button, and the status bar warns when
  you're not elevated (since Apply needs it).

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
