Build a Python desktop GUI app for Windows called "Ally Optimizer" — a one-click game performance/power profile switcher for the ROG Xbox Ally handheld (AMD Z2 APU).

Read BRIEF.md first for full context, constraints, and architecture decisions. The two seed files (profiles/games.json, profiles/config.json) are already in this folder — use them as-is, don't regenerate them.

Build order:
1. Set up the project structure (main.py, profiles/ folder already exists, requirements.txt).
2. Build the core GUI shell: left pane game list (read from games.json), right pane showing selected game's profile buttons.
3. Wire up the Apply button to call RyzenAdj via subprocess with the right wattage conversion, including the admin self-elevation pattern.
4. Add the Steam library auto-scan (.acf parsing) to merge detected installed games into the list (games not yet in games.json show with an "Add profile" prompt instead of profile buttons).
5. Build the Add/Edit Game form that writes back to games.json.
6. Add the "Find settings" dropdown button (opens browser links per BRIEF.md — do not scrape).
7. Add battery/plugged toggle and status readout via psutil.
8. Add the Revert/Reset button.
9. Write a README.md covering: RyzenAdj download/setup (not bundled, link to source), Defender/SmartScreen warning explanation, how to add games manually, how the Find Settings button works.

Ask me if anything in BRIEF.md's "not yet decided" section blocks you. Otherwise make reasonable judgment calls and flag them in comments.
