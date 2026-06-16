# ROG Xbox Ally Game Optimizer — Project Brief

## Context
Handheld: ROG Xbox Ally (Z2 / Z2 Extreme APU), Windows 11.
Goal: a simple local GUI app to apply per-game power/performance profiles with one click.

## Stack
- Python 3 + Tkinter (single-window GUI)
- RyzenAdj (external .exe, not bundled by default — user downloads separately) for TDP/power control
- `psutil` for battery/plugged-in detection and temp readout
- Standard library `subprocess`, `json`, `ctypes` (for admin elevation), `webbrowser`

## Core features (v1)
1. **Game list** — left pane, populated from `profiles/games.json` (seed file provided) plus auto-scan of Steam library folders (read `.acf` files in `steamapps/common` for installed app names/IDs — simple key-value parse, not full VDF library).
2. **Profile buttons** — selecting a game shows its saved profiles (e.g. "Max Quality", "Battery Saver") as buttons, pulled from JSON. Each profile has: tdp_sustained, tdp_boost, resolution, fps_cap, notes.
3. **Apply button** — runs RyzenAdj via subprocess with the selected profile's wattages (convert W → mW, ×1000). Needs admin: self-elevate via `ctypes.windll.shell32.ShellExecuteW(None, "runas", ...)` re-launch pattern, don't fail silently if not elevated.
4. **Add/Edit Game form** — manual entry UI (name, process exe, TDP sustained/boost, resolution, FPS cap, notes) that writes back into `games.json`.
5. **"Find settings" button** — dropdown/menu with three options, each opens default browser via `webbrowser.open()`:
   - `https://rogallylife.com/?s=<game name>`
   - `https://rogally.games/?s=<game name>` (verify actual search URL pattern at build time)
   - generic web search for "<game name> ROG Ally settings"
   This is the intended path for the user to pull real numbers in manually — do not scrape these sites in app code.
6. **Battery vs Plugged-in toggle** — detect via `psutil.sensors_battery().power_plugged`, switch which TDP value in a profile is suggested/applied.
7. **Revert/Reset button** — reset RyzenAdj to default/max limits (check RyzenAdj `--reset` or re-apply Windows default plan).
8. **Status readout** — small panel showing current battery %, plugged state, CPU temp if available via psutil.

## Optional / stretch
- PCGamingWiki API integration (`https://www.pcgamingwiki.com/w/api.php`, free, no key, CC BY-NC-SA) to auto-suggest a *starting* profile based on objective facts (FSR/DLSS support, Steam Deck Verified status) when a game has no saved profile yet. This generates an algorithmic default guess — not copied human-tested numbers — so it's safe to automate/cache freely.
- System tray icon / minimize-to-tray.
- Hotkey to reapply last-used profile.

## Explicit constraints
- **Do not bulk-scrape or bulk-import data from rogallylife.com, rogally.games, or any similar settings-database site** — including via their WordPress `wp-json` REST endpoints. These are fine as manual single-lookup links for the user, not as an automated data source. The local `games.json` grows via the manual Add/Edit form, not via scraping.
- RyzenAdj is unsigned — Defender/SmartScreen may flag it. Note this in the README, don't try to suppress/bypass the warning programmatically.
- `.acf` parsing: simple regex/key-value is sufficient, don't add a heavy VDF dependency unless one's already in use.
- Single-file `main.py` is fine for v1; split into modules only if it gets unwieldy.

## Provided seed files
- `profiles/games.json` — 3 example entries (Forza Horizon 6, Left 4 Dead 2, Wo Long: Fallen Dynasty) with real TDP/resolution/FPS values sourced from rogallylife.com, used here as illustrative seed/examples only.
- `profiles/config.json` — RyzenAdj path, Steam library paths, default TDP fallbacks.

## Not yet decided / ask the user if unclear
- Exact rogally.games search URL pattern (verify when building the Find Settings button).
- Whether to bundle RyzenAdj.exe in the repo or require separate download (licensing/distribution question for an open-source repo — RyzenAdj itself is GPL-licensed and redistributable, but confirm before bundling).
