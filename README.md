<p align="center">
  <img src="assets/allyoptimizer.png" width="96" alt="Ally Optimizer icon">
</p>

<h1 align="center">Ally Optimizer</h1>

A one-click optimiser for the **ROG Xbox Ally** and **ROG Xbox Ally X**
(AMD Z2 / Z2 Extreme APU) on Windows 11. Set per-game TDP profiles, apply the
Windows tweaks people recommend for handhelds (reversibly), boost FPS, fix the
overnight sleep drain, and follow a guided Armoury Crate checklist — all from one
app with a modern dark/light, ROG red/black UI.

### Screenshots

| Games | System Tweaks |
| --- | --- |
| ![Games](assets/screenshot_dark_games.png) | ![System Tweaks](assets/screenshot_dark_systemtweaks.png) |

| Boost | Hibernation |
| --- | --- |
| ![Boost](assets/screenshot_dark_boost.png) | ![Hibernation](assets/screenshot_dark_hibernation.png) |

| Armoury Crate | Light theme |
| --- | --- |
| ![Armoury Crate](assets/screenshot_dark_armourycrate.png) | ![Light theme](assets/screenshot_light_hibernation.png) |

## Tabs

- **Games** — per-game power/performance profiles applied via
  [RyzenAdj](https://github.com/FlyGoat/RyzenAdj).
- **System Tweaks** — reversible Windows optimisation tweaks (power, gaming,
  latency, visuals, debloat) with risk badges and one-click revert.
- **Boost** — native AMD AFMF/RSR/FSR guidance, a per-game Fullscreen-Exclusive
  toggle, and detect/launch for Lossless Scaling + AnyFSE.
- **Hibernation** — enable/disable, hibernate-instead-of-sleep, auto-hibernate
  timeout, and hibernate-now (fixes overnight battery drain).
- **Armoury Crate** — guided checklist + deep links (Armoury Crate has no public
  API, so these can't be toggled directly).

## Features

- **Auto-detects Ally vs Ally X** (model string + RAM) and tunes the recommended
  TDP band per model; manual override via `device_override` in config.
- **Dark & light themes** — toggle in the toolbar (remembered between launches).
- **System Tweaks** — the "power-user" set commonly recommended for handhelds:
  High Performance power plan, disable hibernation/USB-suspend, Game Mode,
  disable Game DVR, HAGS, MPO fix, MMCSS/network-throttling/foreground-priority,
  visual-effects-for-performance, telemetry/SysMain off, and a curated debloat.
  **Every tweak is reversible** — Apply records the prior value, Revert restores
  it, and you can drop a **System Restore point** first.
- **Game list** from `profiles/games.json` plus an **installed-games scan** of
  Steam, Xbox/Game Pass, Epic, GOG, and a catch-all Windows registry + Start-menu
  sweep (covers EA, Ubisoft, Battle.net and standalone installers).
- **Profile buttons** — each game's saved profiles (TDP sustained/boost,
  resolution, FPS cap, notes) as one-click Apply buttons.
- **Apply via RyzenAdj** — converts watts → milliwatts and sets the sustained
  (`--stapm-limit` / `--slow-limit`) and boost (`--fast-limit`) power limits,
  with a safety clamp on wattage.
- **Battery / Plugged toggle** — `Auto` follows the charger; `Battery` flattens
  boost down to the sustained value for quieter, cooler runs.
- **Add / Edit game form** — writes new games and profiles straight back to
  `games.json`.
- **Find settings** — opens browser lookups for the selected game (ROG Ally Life,
  rogally.games, generic web search). *Manual lookups only — the app never
  scrapes these sites.*
- **PCGamingWiki suggestions** — for a game with no saved profile, derives an
  *algorithmic starting guess* from objective facts (FSR support, Steam Deck
  status) via the public PCGamingWiki API. Clearly labelled "untested".
- **Reset** to a safe default power limit.
- **System tray** (minimize-to-tray) and a **global hotkey** to reapply the last
  profile.
- **Status bar** — battery %, plugged state, and CPU temperature via `psutil`.

## Requirements

- Windows 11 (the Ally's OS). Admin rights — the app self-elevates via UAC
  because RyzenAdj needs them.
- Python 3.10+ with Tkinter (included in the python.org Windows installer).
- Python packages: `pip install -r requirements.txt`
  (`psutil`, plus optional `pystray`/`Pillow` for the tray and `keyboard` for the
  hotkey — the app runs fine without the optional ones).

## RyzenAdj setup (required, not bundled)

RyzenAdj is **not included** in this repo. It's a separate GPL tool that does the
actual power-limit setting.

1. Download a RyzenAdj release from the official project:
   <https://github.com/FlyGoat/RyzenAdj/releases>
2. Unzip it somewhere (e.g. `C:\Tools\RyzenAdj\ryzenadj.exe`).
3. In the app, click **RyzenAdj…** and point it at `ryzenadj.exe`
   (this saves the path into `profiles/config.json`). Or edit
   `"ryzenadj_path"` in that file directly.

If RyzenAdj isn't found, the app runs in **dry-run mode**: Apply shows you the
exact command it *would* run instead of failing, so you can still explore the UI.

### "Windows Defender / SmartScreen flagged it"

RyzenAdj.exe is **unsigned**, so Windows SmartScreen and Microsoft Defender may
warn about it (an unrecognized publisher) — this is expected for the unsigned
binary, not a sign the app did anything to it. **This app does not, and will
not, try to suppress or bypass that warning.** Verify you downloaded RyzenAdj
from the official link above, then allow it through if you trust it. Setting
APU power limits is also why admin rights are needed.

> ⚠️ Changing power limits affects your hardware. The clamp keeps values in a
> sane band, but use sensible numbers. This tool is provided as-is.

## First run on the Ally — sanity check

The logic, UI and read-only Windows calls are validated automatically on a
Windows CI runner, but the parts that actually touch hardware can only be
confirmed on the device. Run through this once on your Ally:

1. **Launch & elevate** — start the app, accept the UAC prompt. The sidebar
   should show your model (e.g. *ROG Ally X*) and the status bar should show a
   real battery % / plugged state. _(If the model says "Unknown handheld", set
   `device_override` in `profiles/config.json` to `"ROG Ally"` or `"ROG Ally X"`.)_
2. **TDP apply (RyzenAdj)** — point the app at `ryzenadj.exe`, pick a game, and
   Apply a profile. Confirm it reports success (not dry-run). Sanity-check the
   wattage actually changed in your monitoring overlay / Armoury Crate.
3. **One tweak + revert** — on **System Tweaks**, click **🛡 Create restore
   point** first, then Apply a single *SAFE* tweak (e.g. *Disable hibernation*),
   confirm the "● applied" badge, then **Revert** and confirm it clears. This
   proves the apply→record→revert round-trip works on your machine.
4. **Hibernation** — on the **Hibernation** page, check the state line reads
   correctly, try **Buttons → hibernate** then **Buttons → sleep** to confirm
   both directions work. *(Test "Hibernate now" only when you're ready for the
   Ally to actually hibernate.)*
5. **Boost / FSE** — pick a game's `.exe` with **Force FSE for .exe…**, then
   **Remove FSE for .exe…**, to confirm the per-game Fullscreen-Exclusive toggle
   writes and clears. AFMF/RSR/FSR are guidance — enable those in AMD Software.

If any **write** action fails, it'll surface the exact command and error rather
than failing silently — note that down so it can be fixed. Everything is
reversible, and the restore point from step 3 is your safety net.

## Build a standalone .exe (recommended for the Ally)

So you can just double-click an icon on the Ally instead of running Python, build
a standalone `AllyOptimizer.exe` with [PyInstaller](https://pyinstaller.org).

> A Windows `.exe` must be built **on Windows** (PyInstaller can't cross-compile).
> Build it once on the Ally itself, or on any Windows PC, then copy the folder.

```bat
build_exe.bat
```

That installs the dependencies + PyInstaller and runs the bundled
`AllyOptimizer.spec`. When it finishes you'll have:

```
dist\AllyOptimizer\AllyOptimizer.exe
dist\AllyOptimizer\profiles\        (your editable games.json / config.json)
```

Then:

1. Drop `ryzenadj.exe` into `dist\AllyOptimizer\` (or point the app at it via the
   **RyzenAdj…** button).
2. Right-click `AllyOptimizer.exe` → **Send to → Desktop (create shortcut)**, or
   pin it to Start. Double-click to launch (it'll prompt for admin via UAC).

The exe is built with `uac_admin`, so Windows asks for Administrator rights on
launch — that's required for RyzenAdj. SmartScreen may warn about your freshly
built, unsigned exe (same as RyzenAdj); that's expected for an unsigned binary.

### Or download a pre-built exe (no Python needed)

A GitHub Actions workflow builds the exe on a Windows runner automatically:

- **Every push to `main`** uploads `AllyOptimizer-windows.zip` as a build
  artifact (Actions tab → latest run → Artifacts).
- **Tagging a release** publishes a GitHub Release with the zip attached:

  ```sh
  git tag v1.0.0 && git push origin v1.0.0
  ```

Download the zip on the Ally, unzip it, drop `ryzenadj.exe` in the folder, and
double-click `AllyOptimizer.exe`. No Python install required.

## Run from source (for development)

```sh
pip install -r requirements.txt
python main.py
```

Accept the UAC prompt (needed for RyzenAdj). Then:

1. **Scan installed games** to merge detected installs into the list.
2. Select a game. If it has profiles, click one to **Apply**. If not, use
   **Add profile** or **Suggest from PCGamingWiki**, or **Find settings** to look
   up tested numbers and enter them yourself.
3. Use the **Power** dropdown to bias toward battery or plugged-in behaviour.
4. **Reset to default** restores a safe baseline limit.

## Adding games manually

Use the **＋ Add game** / **✎ Edit game** buttons, or edit `profiles/games.json`
directly. Each game has a `process_name`, a `source` note, and a list of
`profiles`, where each profile has `label`, `tdp_sustained`, `tdp_boost`,
`resolution`, `fps_cap`, and `notes`. The file is yours — add freely.

## How "Find settings" works (and why there's no scraping)

The Find settings dropdown just opens search URLs in your browser for the
selected game. It's the intended path to pull in real, human-tested numbers:
read the page, then type the values into the Add/Edit form.

The app deliberately **does not** bulk-scrape or auto-import from ROG Ally Life,
rogally.games, or similar settings databases (including their `wp-json`
endpoints). Those are community resources; automated bulk access typically
violates their terms and is unkind to small sites. For *automated* suggestions
the app uses the PCGamingWiki API instead (public, CC BY-NC-SA, attributed),
which produces an algorithmic starting guess from objective facts — not copied
tested values.

## Project layout

```
main.py              entry point + admin self-elevation
app/gui.py           Tkinter UI
app/ryzenadj.py      command building, apply/reset, W->mW, clamps, dry-run
app/scanners.py      Steam/Xbox/Epic/GOG/registry/Start-menu scanners
app/profiles.py      games.json load/save
app/config.py        config.json load/save
app/power.py         psutil battery/temp readout
app/pcgamingwiki.py  algorithmic suggestion via PCGamingWiki API
app/weblinks.py      Find-settings browser links
app/tray.py          system tray (optional)
app/hotkey.py        reapply-last global hotkey (optional)
profiles/            games.json + config.json (yours to edit)
tests/test_logic.py  smoke tests for the pure-Python logic
```

## Tests

```sh
python tests/test_logic.py      # or: python -m pytest
```

Tests cover the platform-independent logic (W→mW conversion, clamps, command
building, `.acf` parsing, web-link building, seed JSON validity). The GUI,
RyzenAdj execution, and Windows-only scanners are exercised on the device.

## License / credits

- RyzenAdj — GPL, © its authors. Downloaded separately, not redistributed here.
- Game-fact suggestions — PCGamingWiki, CC BY-NC-SA.
- Seed profile numbers in `games.json` — illustrative examples sourced from
  rogallylife.com.
