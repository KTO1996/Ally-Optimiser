"""Tkinter single-window UI for Ally Optimizer.

Layout:
  * Top toolbar  — Scan, Add game, RyzenAdj path, Reset
  * Left pane    — game list (saved profiles + detected installs)
  * Right pane   — selected game's profile buttons, or an "Add profile" prompt
  * Bottom bar   — power status + currently applied profile
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

from . import APP_NAME, __version__, config as cfg, power, profiles as prof
from . import pcgamingwiki, ryzenadj, weblinks
from .hotkey import HotkeyManager
from .scanners import DetectedGame, scan_all
from .tray import TrayIcon

POWER_MODES = ("Auto", "Battery", "Plugged in")


class AllyOptimizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{__version__}")
        self.geometry("860x560")
        self.minsize(720, 460)

        self.config_data: Dict = cfg.load_config()
        self.games_doc: Dict = prof.load_games()
        self.detected: Dict[str, DetectedGame] = {}
        self.power_mode = tk.StringVar(value="Auto")
        self.selected_game: Optional[str] = None

        self.hotkeys = HotkeyManager()
        self.tray: Optional[TrayIcon] = None

        self._build_ui()
        self._refresh_game_list()
        self._tick_status()
        self._setup_hotkey()
        self._setup_tray()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="⟳ Scan installed games",
                   command=self._on_scan).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="＋ Add game",
                   command=lambda: self._open_edit_form()).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="RyzenAdj…",
                   command=self._choose_ryzenadj).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="⟲ Reset to default",
                   command=self._on_reset).pack(side=tk.LEFT, padx=4)

        ttk.Label(toolbar, text="Power:").pack(side=tk.LEFT, padx=(16, 2))
        ttk.OptionMenu(toolbar, self.power_mode, "Auto", *POWER_MODES,
                       command=lambda _=None: self._render_detail()).pack(side=tk.LEFT)

        body = ttk.Frame(self, padding=8)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: game list
        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Games").pack(anchor=tk.W)
        self.listbox = tk.Listbox(left, width=34, activestyle="dotbox")
        self.listbox.pack(side=tk.LEFT, fill=tk.Y, expand=True)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Right: detail
        self.detail = ttk.Frame(body, padding=(12, 0))
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bottom status bar
        self.status_var = tk.StringVar(value="")
        status = ttk.Frame(self, relief=tk.GROOVE, padding=(8, 4))
        status.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status, textvariable=self.status_var).pack(side=tk.LEFT)
        self.applied_var = tk.StringVar(value="No profile applied this session.")
        ttk.Label(status, textvariable=self.applied_var).pack(side=tk.RIGHT)

    # --------------------------------------------------------------- lists --
    def _all_entries(self) -> List[str]:
        """Saved games first, then detected-but-unsaved games."""
        saved = sorted(self.games_doc.get("games", {}).keys(), key=str.lower)
        saved_lower = {s.lower() for s in saved}
        detected_only = sorted(
            (d.name for d in self.detected.values() if d.name.lower() not in saved_lower),
            key=str.lower,
        )
        return [f"{g}" for g in saved] + [f"{g}  (detected)" for g in detected_only]

    def _entry_to_name(self, entry: str) -> str:
        return entry[:-len("  (detected)")] if entry.endswith("  (detected)") else entry

    def _refresh_game_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for entry in self._all_entries():
            self.listbox.insert(tk.END, entry)

    def _on_select(self, _event=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self.selected_game = self._entry_to_name(self.listbox.get(sel[0]))
        self._render_detail()

    # -------------------------------------------------------------- detail --
    def _clear_detail(self) -> None:
        for child in self.detail.winfo_children():
            child.destroy()

    def _render_detail(self) -> None:
        self._clear_detail()
        name = self.selected_game
        if not name:
            ttk.Label(self.detail, text="Select a game from the list.").pack(anchor=tk.W)
            return

        ttk.Label(self.detail, text=name, font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
        game = prof.find_game(self.games_doc, name)

        # Find-settings dropdown is always available.
        self._add_find_settings(name)

        if not game or not game.get("profiles"):
            ttk.Label(
                self.detail,
                text="No saved profile for this game yet.",
                foreground="#555",
            ).pack(anchor=tk.W, pady=(10, 4))
            btns = ttk.Frame(self.detail)
            btns.pack(anchor=tk.W)
            ttk.Button(btns, text="＋ Add profile",
                       command=lambda: self._open_edit_form(name)).pack(side=tk.LEFT)
            ttk.Button(btns, text="✨ Suggest from PCGamingWiki",
                       command=lambda: self._suggest(name)).pack(side=tk.LEFT, padx=6)
            return

        ttk.Label(self.detail, text=f"Process: {game.get('process_name', '—')}",
                  foreground="#555").pack(anchor=tk.W)
        if game.get("source"):
            ttk.Label(self.detail, text=f"Source: {game['source']}",
                      foreground="#777", font=("Segoe UI", 8)).pack(anchor=tk.W)

        ttk.Separator(self.detail).pack(fill=tk.X, pady=8)
        for profile in game["profiles"]:
            self._add_profile_row(name, profile)

        edit = ttk.Frame(self.detail)
        edit.pack(anchor=tk.W, pady=(10, 0))
        ttk.Button(edit, text="✎ Edit game",
                   command=lambda: self._open_edit_form(name)).pack(side=tk.LEFT)

    def _add_profile_row(self, game_name: str, profile: Dict) -> None:
        row = ttk.Frame(self.detail, padding=(0, 4))
        row.pack(fill=tk.X, anchor=tk.W)
        s = profile.get("tdp_sustained", "?")
        b = profile.get("tdp_boost", "?")
        meta = (f"{profile.get('resolution', '?')} · {s}/{b}W · "
                f"{profile.get('fps_cap', 0) or '∞'} fps")
        ttk.Button(row, text=f"▶ Apply: {profile.get('label', 'Profile')}",
                   width=28,
                   command=lambda p=profile: self._apply(game_name, p)).pack(side=tk.LEFT)
        ttk.Label(row, text=meta, foreground="#555").pack(side=tk.LEFT, padx=8)
        if profile.get("notes"):
            ttk.Label(self.detail, text=f"   {profile['notes']}",
                      foreground="#777", wraplength=480,
                      font=("Segoe UI", 8)).pack(anchor=tk.W)

    def _add_find_settings(self, name: str) -> None:
        bar = ttk.Frame(self.detail)
        bar.pack(anchor=tk.W, pady=(6, 0))
        mb = ttk.Menubutton(bar, text="🔎 Find settings ▾")
        menu = tk.Menu(mb, tearoff=False)
        for label, url in weblinks.build_links(name, self.config_data):
            menu.add_command(label=label, command=lambda u=url: weblinks.open_link(u))
        mb["menu"] = menu
        mb.pack(side=tk.LEFT)

    # ------------------------------------------------------------- actions --
    def _effective_profile(self, profile: Dict) -> Dict:
        """Apply the power-mode toggle to a profile before sending it.

        Battery -> flatten boost down to sustained (lower, quieter).
        Plugged -> use the profile as authored.
        Auto    -> detect via psutil; fall back to Plugged if unknown.
        """
        mode = self.power_mode.get()
        if mode == "Auto":
            plugged = power.is_plugged_in()
            mode = "Plugged in" if (plugged is None or plugged) else "Battery"
        eff = dict(profile)
        if mode == "Battery":
            eff["tdp_boost"] = eff.get("tdp_sustained", eff.get("tdp_boost"))
        return eff

    def _apply(self, game_name: str, profile: Dict) -> None:
        eff = self._effective_profile(profile)
        result = ryzenadj.apply_profile(eff, self.config_data)
        cmd_str = " ".join(result.command)
        if result.ok:
            self.config_data["last_applied"] = {
                "game": game_name, "profile_label": profile.get("label", ""),
            }
            cfg.save_config(self.config_data)
            self.applied_var.set(
                f"Applied: {game_name} — {profile.get('label', '')}"
            )
        elif result.dry_run:
            messagebox.showinfo(
                "Dry-run (RyzenAdj not found)",
                f"{result.message}\n\nWould run:\n{cmd_str}",
            )
        else:
            messagebox.showerror("Apply failed", f"{result.message}\n\n{cmd_str}")

    def _on_reset(self) -> None:
        result = ryzenadj.reset(self.config_data)
        if result.ok:
            self.applied_var.set("Reset to default power limit.")
        elif result.dry_run:
            messagebox.showinfo("Dry-run", f"{result.message}\n\n{' '.join(result.command)}")
        else:
            messagebox.showerror("Reset failed", result.message)

    def reapply_last(self) -> None:
        last = self.config_data.get("last_applied")
        if not last:
            return
        game = prof.find_game(self.games_doc, last.get("game", ""))
        if not game:
            return
        for p in game.get("profiles", []):
            if p.get("label") == last.get("profile_label"):
                self._apply(last["game"], p)
                return

    def _on_scan(self) -> None:
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            found = scan_all(self.config_data)
        finally:
            self.config(cursor="")
        self.detected = {d.name: d for d in found}
        self._refresh_game_list()
        messagebox.showinfo("Scan complete", f"Detected {len(found)} installed game(s).")

    def _suggest(self, name: str) -> None:
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            suggestion = pcgamingwiki.suggest_profile(name, self.config_data)
        finally:
            self.config(cursor="")
        if not suggestion:
            messagebox.showinfo(
                "No suggestion",
                "Couldn't derive a starting profile from PCGamingWiki.\n"
                "Use 'Find settings' to look up tested values, then Add profile.",
            )
            return
        detected = self.detected.get(name)
        proc = (detected.process_name if detected else None) or ""
        if not proc:
            proc = simpledialog.askstring(
                "Process name",
                f"Executable for {name} (e.g. game.exe):", parent=self
            ) or ""
        prof.upsert_game(
            self.games_doc, name, proc, [suggestion],
            source="PCGamingWiki (algorithmic suggestion)",
        )
        prof.save_games(self.games_doc)
        self._refresh_game_list()
        self._render_detail()

    def _choose_ryzenadj(self) -> None:
        path = filedialog.askopenfilename(
            title="Locate ryzenadj.exe",
            filetypes=[("RyzenAdj", "ryzenadj.exe"), ("Executable", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.config_data["ryzenadj_path"] = path
            cfg.save_config(self.config_data)
            messagebox.showinfo("RyzenAdj", f"RyzenAdj path set to:\n{path}")

    # --------------------------------------------------------- add/edit UI --
    def _open_edit_form(self, name: Optional[str] = None) -> None:
        EditGameDialog(self, name)

    # ----------------------------------------------------------- lifecycle --
    def _tick_status(self) -> None:
        self.status_var.set(power.get_status().summary())
        self.after(5000, self._tick_status)

    def _setup_hotkey(self) -> None:
        if self.config_data.get("enable_hotkey", True):
            self.hotkeys.register(
                self.config_data.get("reapply_hotkey", "ctrl+alt+a"),
                lambda: self.after(0, self.reapply_last),
            )

    def _setup_tray(self) -> None:
        if not self.config_data.get("minimize_to_tray", True):
            return
        self.tray = TrayIcon(
            APP_NAME,
            on_show=lambda: self.after(0, self._restore),
            on_reapply=lambda: self.after(0, self.reapply_last),
            on_quit=lambda: self.after(0, self._quit),
        )
        if not self.tray.start():
            self.tray = None

    def _restore(self) -> None:
        self.deiconify()
        self.lift()

    def _on_close(self) -> None:
        if self.tray is not None and self.config_data.get("minimize_to_tray", True):
            self.withdraw()  # hide to tray instead of quitting
        else:
            self._quit()

    def _quit(self) -> None:
        self.hotkeys.unregister()
        if self.tray is not None:
            self.tray.stop()
        self.destroy()


class EditGameDialog(tk.Toplevel):
    """Add/Edit a game and one profile. Writes back to games.json."""

    def __init__(self, app: AllyOptimizerApp, name: Optional[str]) -> None:
        super().__init__(app)
        self.app = app
        self.title("Edit game" if name else "Add game")
        self.transient(app)
        self.resizable(False, False)
        existing = prof.find_game(app.games_doc, name) if name else None
        first = (existing or {}).get("profiles", [{}])
        first = first[0] if first else {}

        self.vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Game name", "name", name or ""),
            ("Process .exe", "process_name", (existing or {}).get("process_name", "")),
            ("Profile label", "label", first.get("label", "Custom")),
            ("TDP sustained (W)", "tdp_sustained", str(first.get("tdp_sustained", 15))),
            ("TDP boost (W)", "tdp_boost", str(first.get("tdp_boost", 20))),
            ("Resolution", "resolution", first.get("resolution", "1920x1080")),
            ("FPS cap (0 = none)", "fps_cap", str(first.get("fps_cap", 0))),
        ]
        for r, (label, key, value) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=r, column=0, sticky=tk.W, padx=8, pady=3)
            var = tk.StringVar(value=value)
            ttk.Entry(self, textvariable=var, width=34).grid(row=r, column=1, padx=8, pady=3)
            self.vars[key] = var

        ttk.Label(self, text="Notes").grid(row=len(rows), column=0, sticky=tk.NW, padx=8)
        self.notes = tk.Text(self, width=34, height=4)
        self.notes.insert("1.0", first.get("notes", ""))
        self.notes.grid(row=len(rows), column=1, padx=8, pady=3)

        btns = ttk.Frame(self)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)
        if name:
            self.vars["name"].set(name)

    def _save(self) -> None:
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showerror("Missing name", "Game name is required.", parent=self)
            return
        try:
            tdp_s = int(float(self.vars["tdp_sustained"].get()))
            tdp_b = int(float(self.vars["tdp_boost"].get()))
            fps = int(float(self.vars["fps_cap"].get() or 0))
        except ValueError:
            messagebox.showerror("Invalid number",
                                 "TDP and FPS must be numbers.", parent=self)
            return
        profile = {
            "label": self.vars["label"].get().strip() or "Custom",
            "tdp_sustained": tdp_s,
            "tdp_boost": tdp_b,
            "resolution": self.vars["resolution"].get().strip(),
            "fps_cap": fps,
            "notes": self.notes.get("1.0", tk.END).strip(),
        }
        existing = prof.find_game(self.app.games_doc, name)
        # Preserve any additional profiles already saved; replace the first.
        if existing and existing.get("profiles"):
            profiles = list(existing["profiles"])
            profiles[0] = profile
            source = existing.get("source", "manual entry")
        else:
            profiles = [profile]
            source = "manual entry"
        prof.upsert_game(
            self.app.games_doc, name,
            self.vars["process_name"].get().strip(), profiles, source=source,
        )
        prof.save_games(self.app.games_doc)
        self.app.selected_game = name
        self.app._refresh_game_list()
        self.app._render_detail()
        self.destroy()
