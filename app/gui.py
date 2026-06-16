"""Tkinter UI for Ally Optimizer (ROG red/black theme).

Three tabs:
  * Games          — per-game RyzenAdj TDP profiles (scan, add/edit, suggest)
  * System Tweaks  — reversible Windows optimisation tweaks for the Ally
  * Armoury Crate  — guided checklist + deep links (AC has no public API)

A toolbar (scan / add / RyzenAdj path / power mode) sits above the tabs and a
status bar (battery / temp / detected model) below them.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

from . import APP_NAME, __version__, config as cfg, power, profiles as prof
from . import armoury, pcgamingwiki, ryzenadj, sysinfo, theme, weblinks
from . import systweaks as st
from .hotkey import HotkeyManager
from .paths import ICON_ICO, ICON_PNG
from .scanners import DetectedGame, scan_all
from .tray import TrayIcon
from .tweakengine import TweakEngine

POWER_MODES = ("Auto", "Battery", "Plugged in")


class ScrollFrame(ttk.Frame):
    """A vertically scrollable container (Canvas + inner Frame)."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.body.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width)
        )
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class AllyOptimizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{__version__}")
        self.geometry("960x640")
        self.minsize(820, 560)

        self.config_data: Dict = cfg.load_config()
        self.theme_mode: str = self.config_data.get("theme", "dark")
        theme.apply_theme(self, self.theme_mode)
        self._set_window_icon()

        self.games_doc: Dict = prof.load_games()
        self.detected: Dict[str, DetectedGame] = {}
        self.power_mode = tk.StringVar(value="Auto")
        self.selected_game: Optional[str] = None

        self.device = sysinfo.detect_device(self.config_data.get("device_override"))
        self.engine = TweakEngine()

        self.hotkeys = HotkeyManager()
        self.tray: Optional[TrayIcon] = None

        self._build_ui()
        self._refresh_game_list()
        self._tick_status()
        self._setup_hotkey()
        self._setup_tray()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        try:
            if os.path.isfile(ICON_ICO):
                self.iconbitmap(ICON_ICO)
        except Exception:
            pass
        try:
            if os.path.isfile(ICON_PNG):
                self._icon_img = tk.PhotoImage(file=ICON_PNG)
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        self._toolbar = toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="⟳ Scan games",
                   command=self._on_scan).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="＋ Add game",
                   command=lambda: self._open_edit_form()).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="RyzenAdj…",
                   command=self._choose_ryzenadj).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="⟲ Reset TDP",
                   command=self._on_reset).pack(side=tk.LEFT, padx=4)
        ttk.Label(toolbar, text="Power:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(16, 2))
        ttk.OptionMenu(toolbar, self.power_mode, "Auto", *POWER_MODES,
                       command=lambda _=None: self._render_detail()).pack(side=tk.LEFT)
        sun_moon = "☀ Light" if self.theme_mode == "dark" else "🌙 Dark"
        ttk.Button(toolbar, text=sun_moon,
                   command=self._toggle_theme).pack(side=tk.RIGHT)

        self._notebook = self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.tab_games = ttk.Frame(self.notebook, padding=8)
        self.tab_tweaks = ttk.Frame(self.notebook, padding=8)
        self.tab_armoury = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_games, text="  Games  ")
        self.notebook.add(self.tab_tweaks, text="  System Tweaks  ")
        self.notebook.add(self.tab_armoury, text="  Armoury Crate  ")

        self._build_games_tab()
        self._build_tweaks_tab()
        self._build_armoury_tab()

        # Bottom status bar
        self.status_var = tk.StringVar(value="")
        self._statusbar = status = ttk.Frame(self, padding=(10, 5))
        status.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.LEFT)
        self.applied_var = tk.StringVar(value="No profile applied this session.")
        ttk.Label(status, textvariable=self.applied_var, style="Muted.TLabel").pack(side=tk.RIGHT)

    # --------------------------------------------------------- Games tab ----
    def _build_games_tab(self) -> None:
        left = ttk.Frame(self.tab_games)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Games", style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 4))
        self.listbox = tk.Listbox(left, width=32)
        theme.style_listbox(self.listbox)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y, expand=True)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        self.detail = ttk.Frame(self.tab_games, padding=(14, 0))
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # --------------------------------------------------------- lists --
    def _all_entries(self) -> List[str]:
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
            ttk.Label(self.detail, text="Select a game from the list.",
                      style="Muted.TLabel").pack(anchor=tk.W)
            return

        ttk.Label(self.detail, text=name, style="Header.TLabel").pack(anchor=tk.W)
        game = prof.find_game(self.games_doc, name)
        self._add_find_settings(name)

        if not game or not game.get("profiles"):
            ttk.Label(self.detail, text="No saved profile for this game yet.",
                      style="Muted.TLabel").pack(anchor=tk.W, pady=(10, 4))
            btns = ttk.Frame(self.detail)
            btns.pack(anchor=tk.W)
            ttk.Button(btns, text="＋ Add profile",
                       command=lambda: self._open_edit_form(name)).pack(side=tk.LEFT)
            ttk.Button(btns, text="✨ Suggest from PCGamingWiki",
                       command=lambda: self._suggest(name)).pack(side=tk.LEFT, padx=6)
            return

        ttk.Label(self.detail, text=f"Process: {game.get('process_name', '—')}",
                  style="Muted.TLabel").pack(anchor=tk.W)
        if game.get("source"):
            ttk.Label(self.detail, text=f"Source: {game['source']}",
                      style="Muted.TLabel").pack(anchor=tk.W)

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
                   style="Accent.TButton", width=26,
                   command=lambda p=profile: self._apply(game_name, p)).pack(side=tk.LEFT)
        ttk.Label(row, text=meta, style="Muted.TLabel").pack(side=tk.LEFT, padx=8)
        if profile.get("notes"):
            ttk.Label(self.detail, text=f"   {profile['notes']}",
                      style="Muted.TLabel", wraplength=480).pack(anchor=tk.W)

    def _add_find_settings(self, name: str) -> None:
        bar = ttk.Frame(self.detail)
        bar.pack(anchor=tk.W, pady=(6, 0))
        mb = ttk.Menubutton(bar, text="🔎 Find settings ▾")
        menu = tk.Menu(mb, tearoff=False, bg=theme.PANEL, fg=theme.FG,
                       activebackground=theme.ACCENT, activeforeground="#fff")
        for label, url in weblinks.build_links(name, self.config_data):
            menu.add_command(label=label, command=lambda u=url: weblinks.open_link(u))
        mb["menu"] = menu
        mb.pack(side=tk.LEFT)

    # --------------------------------------------------- System Tweaks tab --
    def _build_tweaks_tab(self) -> None:
        head = ttk.Frame(self.tab_tweaks)
        head.pack(fill=tk.X)
        ttk.Label(head, text="Windows optimisation", style="SubHeader.TLabel").pack(side=tk.LEFT)
        ttk.Button(head, text="🛡 Create restore point",
                   command=self._create_restore_point).pack(side=tk.RIGHT)
        ttk.Button(head, text="✓ Apply all safe",
                   style="Accent.TButton",
                   command=self._apply_all_safe).pack(side=tk.RIGHT, padx=6)

        note = ("Tweaks are reversible — Apply records the previous value; Revert "
                "restores it. Create a restore point first to be safe.")
        if self.engine.dry_run:
            note = "DRY-RUN (not on Windows): actions are shown, nothing is changed.\n" + note
        ttk.Label(self.tab_tweaks, text=note, style="Muted.TLabel",
                  wraplength=900).pack(anchor=tk.W, pady=(2, 6))

        scroller = ScrollFrame(self.tab_tweaks)
        scroller.pack(fill=tk.BOTH, expand=True)
        self._tweak_status_vars: Dict[str, tk.StringVar] = {}

        last_cat = None
        for tw in st.all_tweaks():
            if tw.category != last_cat:
                ttk.Label(scroller.body, text=tw.category,
                          style="SubHeader.TLabel").pack(anchor=tk.W, pady=(10, 2))
                last_cat = tw.category
            self._add_tweak_row(scroller.body, tw)

    def _add_tweak_row(self, parent, tw: st.Tweak) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        card.pack(fill=tk.X, pady=4, padx=2)

        top = ttk.Frame(card, style="Panel.TFrame")
        top.pack(fill=tk.X)
        title = tk.Label(top, text=tw.title, bg=theme.PANEL, fg=theme.FG,
                         font=(theme.FONT, 10, "bold"))
        title.pack(side=tk.LEFT)
        badge = tk.Label(top, text=f" {tw.risk.upper()} ", bg=theme.PANEL,
                         fg=theme.RISK_COLORS.get(tw.risk, theme.FG),
                         font=(theme.FONT, 8, "bold"))
        badge.pack(side=tk.LEFT, padx=8)
        status = tk.StringVar(value="● applied" if self.engine.is_applied(tw) else "")
        self._tweak_status_vars[tw.id] = status
        tk.Label(top, textvariable=status, bg=theme.PANEL, fg=theme.RISK_COLORS["safe"],
                 font=(theme.FONT, 8, "bold")).pack(side=tk.RIGHT)

        desc = tk.Label(card, text=tw.description, bg=theme.PANEL, fg=theme.FG_MUTED,
                        font=(theme.FONT, 9), justify=tk.LEFT, wraplength=720)
        desc.pack(anchor=tk.W, pady=(2, 6))
        if not tw.reversible:
            tk.Label(card, text="⚠ " + (tw.revert_note or "Not auto-reversible."),
                     bg=theme.PANEL, fg=theme.RISK_COLORS["aggressive"],
                     font=(theme.FONT, 8)).pack(anchor=tk.W)

        btns = ttk.Frame(card, style="Panel.TFrame")
        btns.pack(anchor=tk.W)
        ttk.Button(btns, text="Apply", style="Accent.TButton",
                   command=lambda t=tw: self._apply_tweak(t)).pack(side=tk.LEFT)
        ttk.Button(btns, text="Revert",
                   command=lambda t=tw: self._revert_tweak(t)).pack(side=tk.LEFT, padx=6)

    def _refresh_tweak_status(self, tw: st.Tweak) -> None:
        var = self._tweak_status_vars.get(tw.id)
        if var is not None:
            var.set("● applied" if self.engine.is_applied(tw) else "")

    def _apply_tweak(self, tw: st.Tweak) -> None:
        res = self.engine.apply(tw)
        self._refresh_tweak_status(tw)
        self._report_tweak(tw.title, res)

    def _revert_tweak(self, tw: st.Tweak) -> None:
        res = self.engine.revert(tw)
        self._refresh_tweak_status(tw)
        self._report_tweak(tw.title, res)

    def _apply_all_safe(self) -> None:
        safe = [t for t in st.all_tweaks() if t.risk == st.SAFE]
        if not messagebox.askyesno(
            "Apply all safe tweaks",
            f"Apply {len(safe)} low-risk tweaks now? Each is individually "
            "reversible from this tab."):
            return
        failures = [t.title for t in safe if not self.engine.apply(t).ok]
        for t in safe:
            self._refresh_tweak_status(t)
        if failures:
            messagebox.showwarning("Done with warnings",
                                   "Some tweaks couldn't apply:\n- " + "\n- ".join(failures))
        else:
            messagebox.showinfo("Done", f"Applied {len(safe)} safe tweaks.")

    def _create_restore_point(self) -> None:
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            res = self.engine.create_restore_point()
        finally:
            self.config(cursor="")
        (messagebox.showinfo if res.ok else messagebox.showerror)(
            "System Restore", res.message)

    def _report_tweak(self, title: str, res: st.TweakResult) -> None:
        body = res.message
        if res.actions:
            body += "\n\n" + "\n".join(res.actions[:8])
        if res.ok:
            self.applied_var.set(f"{title}: {res.message}")
            if res.dry_run:
                messagebox.showinfo(title + " (dry-run)", body)
        else:
            messagebox.showerror(title, body)

    # --------------------------------------------------- Armoury Crate tab --
    def _build_armoury_tab(self) -> None:
        ttk.Label(self.tab_armoury,
                  text=f"Armoury Crate guidance — {self.device.summary()}",
                  style="SubHeader.TLabel").pack(anchor=tk.W)
        ttk.Label(self.tab_armoury,
                  text="Armoury Crate has no public API, so these can't be toggled "
                       "from here. Use the links to jump to the right place; items "
                       "marked ✓ can be done natively in the Games tab instead.",
                  style="Muted.TLabel", wraplength=900).pack(anchor=tk.W, pady=(2, 6))

        links = ttk.Frame(self.tab_armoury)
        links.pack(fill=tk.X, pady=(0, 8))
        for dl in armoury.deep_links():
            ttk.Button(links, text=dl.label,
                       command=lambda d=dl: armoury.open_link(d)).pack(
                           side=tk.LEFT, padx=(0, 6), pady=2)

        scroller = ScrollFrame(self.tab_armoury)
        scroller.pack(fill=tk.BOTH, expand=True)
        for item in armoury.checklist(self.device):
            self._add_checklist_item(scroller.body, item)

    def _add_checklist_item(self, parent, item: armoury.ChecklistItem) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        card.pack(fill=tk.X, pady=4, padx=2)
        tk.Label(card, text=item.title, bg=theme.PANEL, fg=theme.FG,
                 font=(theme.FONT, 10, "bold")).pack(anchor=tk.W)
        tk.Label(card, text="→ " + item.recommended, bg=theme.PANEL, fg=theme.ACCENT,
                 font=(theme.FONT, 9, "bold"), justify=tk.LEFT,
                 wraplength=820).pack(anchor=tk.W, pady=(2, 0))
        tk.Label(card, text=item.why, bg=theme.PANEL, fg=theme.FG_MUTED,
                 font=(theme.FONT, 9), justify=tk.LEFT, wraplength=820).pack(anchor=tk.W)
        if item.native:
            mark = "✓ " if item.native.lower().startswith("yes") else "• "
            tk.Label(card, text=mark + item.native, bg=theme.PANEL,
                     fg=theme.RISK_COLORS["safe"], font=(theme.FONT, 8),
                     justify=tk.LEFT, wraplength=820).pack(anchor=tk.W, pady=(2, 0))

    # ------------------------------------------------------------- actions --
    def _effective_profile(self, profile: Dict) -> Dict:
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
            self.applied_var.set(f"Applied: {game_name} — {profile.get('label', '')}")
        elif result.dry_run:
            messagebox.showinfo("Dry-run (RyzenAdj not found)",
                                f"{result.message}\n\nWould run:\n{cmd_str}")
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
                "Use 'Find settings' to look up tested values, then Add profile.")
            return
        detected = self.detected.get(name)
        proc = (detected.process_name if detected else None) or ""
        if not proc:
            proc = simpledialog.askstring(
                "Process name", f"Executable for {name} (e.g. game.exe):",
                parent=self) or ""
        prof.upsert_game(self.games_doc, name, proc, [suggestion],
                         source="PCGamingWiki (algorithmic suggestion)")
        prof.save_games(self.games_doc)
        self._refresh_game_list()
        self._render_detail()

    def _choose_ryzenadj(self) -> None:
        path = filedialog.askopenfilename(
            title="Locate ryzenadj.exe",
            filetypes=[("RyzenAdj", "ryzenadj.exe"), ("Executable", "*.exe"), ("All", "*.*")])
        if path:
            self.config_data["ryzenadj_path"] = path
            cfg.save_config(self.config_data)
            messagebox.showinfo("RyzenAdj", f"RyzenAdj path set to:\n{path}")

    def _open_edit_form(self, name: Optional[str] = None) -> None:
        EditGameDialog(self, name)

    def _toggle_theme(self) -> None:
        """Switch dark/light, persist the choice, and rebuild the widgets."""
        self.theme_mode = theme.toggle(self.theme_mode)
        self.config_data["theme"] = self.theme_mode
        cfg.save_config(self.config_data)
        theme.apply_theme(self, self.theme_mode)
        # Rebuild the widget tree so explicitly-coloured tk widgets repaint.
        for frame in (self._toolbar, self._notebook, self._statusbar):
            frame.destroy()
        self._build_ui()
        self._refresh_game_list()
        if self.selected_game:
            self._render_detail()

    # ----------------------------------------------------------- lifecycle --
    def _tick_status(self) -> None:
        self.status_var.set(power.get_status().summary() + "   •   " + self.device.summary())
        self.after(5000, self._tick_status)

    def _setup_hotkey(self) -> None:
        if self.config_data.get("enable_hotkey", True):
            self.hotkeys.register(
                self.config_data.get("reapply_hotkey", "ctrl+alt+a"),
                lambda: self.after(0, self.reapply_last))

    def _setup_tray(self) -> None:
        if not self.config_data.get("minimize_to_tray", True):
            return
        self.tray = TrayIcon(
            APP_NAME,
            on_show=lambda: self.after(0, self._restore),
            on_reapply=lambda: self.after(0, self.reapply_last),
            on_quit=lambda: self.after(0, self._quit))
        if not self.tray.start():
            self.tray = None

    def _restore(self) -> None:
        self.deiconify()
        self.lift()

    def _on_close(self) -> None:
        if self.tray is not None and self.config_data.get("minimize_to_tray", True):
            self.withdraw()
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
        self.configure(bg=theme.BG)
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
        self.notes = tk.Text(self, width=34, height=4, bg=theme.PANEL, fg=theme.FG,
                             insertbackground=theme.FG, relief="flat")
        self.notes.insert("1.0", first.get("notes", ""))
        self.notes.grid(row=len(rows), column=1, padx=8, pady=3)

        btns = ttk.Frame(self)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Save", style="Accent.TButton",
                   command=self._save).pack(side=tk.LEFT, padx=4)
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
            messagebox.showerror("Invalid number", "TDP and FPS must be numbers.", parent=self)
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
        if existing and existing.get("profiles"):
            profiles = list(existing["profiles"])
            profiles[0] = profile
            source = existing.get("source", "manual entry")
        else:
            profiles = [profile]
            source = "manual entry"
        prof.upsert_game(self.app.games_doc, name,
                         self.vars["process_name"].get().strip(), profiles, source=source)
        prof.save_games(self.app.games_doc)
        self.app.selected_game = name
        self.app._refresh_game_list()
        self.app._render_detail()
        self.destroy()
