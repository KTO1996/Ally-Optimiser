"""Modern CustomTkinter UI for Ally Optimizer.

An app-shell layout: a left sidebar (logo, navigation, power mode, theme switch)
and a main content area that swaps between pages:

  * Games          — per-game RyzenAdj TDP profiles
  * System Tweaks  — reversible Windows optimisation tweaks
  * Boost          — AFMF/RSR/FSR guidance, Fullscreen-Exclusive, app launchers
  * Hibernation    — enable/disable, hibernate-instead-of-sleep, auto-timeout
  * Armoury Crate  — guided checklist + deep links

ROG red accent over CustomTkinter's dark/light appearance modes.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from . import APP_NAME, __version__, armoury, backup, batteryest, boost, config as cfg
from . import covers, display, gamepad, hibernate, importer, pcgamingwiki, power
from . import presets, profiles as prof, ryzenadj, sysinfo, updates, weblinks
from . import systweaks as st
from .watcher import GameWatcher, process_name_map
from .hotkey import HotkeyManager
from .paths import ICON_ICO, ICON_PNG
from .scanners import DetectedGame, scan_all
from .tray import TrayIcon
from .tweakengine import TweakEngine

POWER_MODES = ("Auto", "Battery", "Plugged in")

# ROG red accent (works on both light and dark appearance).
ACCENT = "#e2001a"
ACCENT_HOVER = "#b3001a"
RISK_COLORS = {"safe": "#2ea043", "aggressive": "#d29922", "experimental": "#f85149"}

NAV_ITEMS = ("Games", "System Tweaks", "Boost", "Hibernation", "Armoury Crate", "Settings")

try:
    from PIL import Image  # for the sidebar logo
except Exception:  # pragma: no cover
    Image = None


class AllyOptimizerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.config_data: Dict = cfg.load_config()
        self.theme_mode: str = self.config_data.get("theme", "dark")
        ctk.set_appearance_mode(self.theme_mode)
        ctk.set_default_color_theme("dark-blue")
        # Make default (non-accent) button text/border adapt to light & dark so
        # outlined "ghost" buttons stay readable on light backgrounds.
        bt = ctk.ThemeManager.theme["CTkButton"]
        bt["text_color"] = ["gray10", "gray90"]
        bt["border_color"] = ["gray65", "gray45"]
        bt["hover_color"] = ["gray85", "gray25"]

        self.title(f"{APP_NAME} v{__version__}")
        self.geometry("1040x680")
        self.minsize(900, 600)
        self._set_window_icon()

        self.games_doc: Dict = prof.load_games()
        self.detected: Dict[str, DetectedGame] = {}
        self._img_refs: List = []          # keep CTkImage refs alive
        self.power_mode = ctk.StringVar(value="Auto")
        self.selected_game: Optional[str] = None
        self.active_page: str = "Games"

        self.device = sysinfo.detect_device(self.config_data.get("device_override"))
        self.engine = TweakEngine()
        self.library_view = self.config_data.get("library_view", "list")

        self.hotkeys = HotkeyManager()
        self.tray: Optional[TrayIcon] = None
        self.watcher = GameWatcher(
            get_proc_map=lambda: process_name_map(self.games_doc),
            on_start=lambda g: self.after(0, lambda: self._auto_apply(g)),
            on_stop=lambda g: self.after(0, lambda: self._auto_revert(g)))
        self.pad = gamepad.GamepadPoller(
            on_action=lambda a: self.after(0, lambda: self._gamepad_action(a)))
        self._focusables: List = []
        self._focus_idx: int = 0

        self._build_shell()
        self._show_page("Games")
        self._tick_status()
        self._setup_hotkey()
        self._setup_tray()
        self._setup_watcher()
        self._setup_gamepad()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._maybe_onboard)

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

    # ------------------------------------------------------------- shell ----
    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=210, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_rowconfigure(99, weight=1)
        sidebar.grid_propagate(False)

        # Logo + title.
        logo_holder = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_holder.grid(row=0, column=0, padx=16, pady=(18, 8), sticky="w")
        if Image is not None and os.path.isfile(ICON_PNG):
            img = ctk.CTkImage(Image.open(ICON_PNG), size=(34, 34))
            ctk.CTkLabel(logo_holder, image=img, text="").pack(side="left")
        ctk.CTkLabel(logo_holder, text=" Ally\n Optimizer",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     justify="left").pack(side="left")

        # Navigation buttons.
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        for i, name in enumerate(NAV_ITEMS):
            btn = ctk.CTkButton(
                sidebar, text=name, anchor="w", corner_radius=8,
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray25"),
                command=lambda n=name: self._show_page(n))
            btn.grid(row=1 + i, column=0, padx=12, pady=4, sticky="ew")
            self.nav_buttons[name] = btn

        # Bottom controls: power mode, theme switch, device.
        ctk.CTkLabel(sidebar, text="Power mode",
                     font=ctk.CTkFont(size=11)).grid(row=90, column=0, padx=16,
                                                     pady=(8, 0), sticky="w")
        ctk.CTkOptionMenu(sidebar, values=list(POWER_MODES), variable=self.power_mode,
                          fg_color=ACCENT, button_color=ACCENT_HOVER,
                          button_hover_color=ACCENT_HOVER, width=170).grid(
                              row=91, column=0, padx=16, pady=(2, 8))

        self.theme_switch = ctk.CTkSwitch(
            sidebar, text="Light mode", command=self._toggle_theme,
            progress_color=ACCENT)
        if self.theme_mode == "light":
            self.theme_switch.select()
        self.theme_switch.grid(row=92, column=0, padx=16, pady=8, sticky="w")

        self.device_label = ctk.CTkLabel(
            sidebar, text=self.device.summary(), font=ctk.CTkFont(size=10),
            text_color="gray60", wraplength=180, justify="left")
        self.device_label.grid(row=100, column=0, padx=16, pady=(8, 14), sticky="sw")

        # Main area: header + body + status bar.
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(main, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        self.body = ctk.CTkFrame(main, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)

        statusbar = ctk.CTkFrame(main, height=28, corner_radius=0)
        statusbar.grid(row=2, column=0, sticky="ew")
        self.status_var = ctk.StringVar(value="")
        ctk.CTkLabel(statusbar, textvariable=self.status_var,
                     font=ctk.CTkFont(size=11), text_color="gray60").pack(side="left", padx=12)
        self.applied_var = ctk.StringVar(value="No profile applied this session.")
        ctk.CTkLabel(statusbar, textvariable=self.applied_var,
                     font=ctk.CTkFont(size=11), text_color="gray60").pack(side="right", padx=12)

    def _accent_button(self, parent, text, command, **kw) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, command=command, fg_color=ACCENT,
                             hover_color=ACCENT_HOVER, text_color="white", **kw)

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, corner_radius=10)

    def _cover_image(self, path: str, size) -> Optional["ctk.CTkImage"]:
        if Image is None or not path or not os.path.isfile(path):
            return None
        try:
            img = ctk.CTkImage(Image.open(path), size=size)
            self._img_refs.append(img)
            return img
        except Exception:
            return None

    def _load_cover_into(self, name: str, label: ctk.CTkLabel, size=(150, 225),
                         guard_selected: bool = True) -> None:
        """Resolve cover art off the UI thread.

        Tries real art (saved cover URL or Steam appid) and persists it; if none
        is available, falls back to a generated placeholder. All of it — image
        generation included — runs on a worker thread so the UI never blocks.
        """
        game = prof.find_game(self.games_doc, name)
        if covers.cached_cover(game):
            return  # real art already shown synchronously
        det = self.detected.get(name)
        appid = det.appid if det else None

        def work():
            path = None
            if (game and game.get("cover")) or appid:
                path = covers.resolve_cover(game, appid, allow_network=True)
                if path and game is not None and game.get("cover") != path:
                    prof.upsert_game(self.games_doc, name,
                                     game.get("process_name", ""),
                                     game.get("profiles", []),
                                     source=game.get("source", "manual entry"),
                                     cover=path)
                    prof.save_games(self.games_doc)
            if not path:
                path = covers.placeholder_for(name)   # generated + cached on disk
            if path:
                self.after(0, lambda: self._apply_cover(label, path, name, size,
                                                        guard_selected))

        threading.Thread(target=work, daemon=True).start()

    def _apply_cover(self, label, path, name, size, guard_selected) -> None:
        if guard_selected and self.selected_game != name:
            return
        try:
            if not label.winfo_exists():
                return
        except Exception:
            return
        img = self._cover_image(path, size)
        if img is not None:
            label.configure(image=img, text="")

    # -------------------------------------------------------- navigation ----
    def _show_page(self, name: str) -> None:
        self.active_page = name
        for n, btn in self.nav_buttons.items():
            btn.configure(fg_color=ACCENT if n == name else "transparent",
                          text_color="white" if n == name else ("gray10", "gray90"))
        for w in self.header.winfo_children():
            w.destroy()
        for w in self.body.winfo_children():
            w.destroy()
        builder = {
            "Games": self._page_games,
            "System Tweaks": self._page_tweaks,
            "Boost": self._page_boost,
            "Hibernation": self._page_hibernation,
            "Armoury Crate": self._page_armoury,
            "Settings": self._page_settings,
        }[name]
        builder()
        if self.config_data.get("enable_gamepad"):
            self.after(50, self._refresh_focusables)

    def _header_title(self, title: str, subtitle: str = "") -> None:
        ctk.CTkLabel(self.header, text=title,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        if subtitle:
            ctk.CTkLabel(self.header, text="   " + subtitle, text_color="gray60",
                         font=ctk.CTkFont(size=12)).pack(side="left", pady=(8, 0))

    # ============================================================ Games ======
    def _page_games(self) -> None:
        self._header_title("Games")
        self._accent_button(self.header, "⟳ Scan", self._on_scan, width=90).pack(side="right")
        ctk.CTkButton(self.header, text="✨ Auto-fill all", command=self._auto_fill_all,
                      width=120, fg_color=("gray75", "gray30"),
                      hover_color=("gray65", "gray38"),
                      text_color=("gray10", "gray90")).pack(side="right", padx=6)
        ctk.CTkButton(self.header, text="＋ Add game",
                      command=lambda: self._open_edit_form(), width=100,
                      fg_color=("gray75", "gray30"), hover_color=("gray65", "gray38"),
                      text_color=("gray10", "gray90")).pack(side="right", padx=6)
        view = ctk.CTkSegmentedButton(
            self.header, values=["List", "Grid"], command=self._set_library_view,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER, width=120)
        view.set("Grid" if self.library_view == "grid" else "List")
        view.pack(side="right", padx=10)

        if self.library_view == "grid":
            self._build_games_grid()
        else:
            self._build_games_split()

    def _set_library_view(self, value: str) -> None:
        self.library_view = "grid" if value == "Grid" else "list"
        self.config_data["library_view"] = self.library_view
        cfg.save_config(self.config_data)
        self._show_page("Games")   # clears header/body before rebuilding

    def _build_games_split(self) -> None:
        wrap = ctk.CTkFrame(self.body, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        self.game_list = ctk.CTkScrollableFrame(wrap, width=240, label_text="Library")
        self.game_list.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.detail = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        self.detail.grid(row=0, column=1, sticky="nsew")
        self._refresh_game_list()
        self._render_detail()

    def _build_games_grid(self) -> None:
        grid = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        grid.grid(row=0, column=0, sticky="nsew")
        cols = 5
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1)
        for i, entry in enumerate(self._all_entries()):
            name = self._entry_to_name(entry)
            tile = ctk.CTkFrame(grid, corner_radius=10)
            tile.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="n")
            game = prof.find_game(self.games_doc, name)
            cover_lbl = ctk.CTkLabel(tile, text=name, width=150, height=225,
                                     font=ctk.CTkFont(size=12), wraplength=140)
            cached = covers.cached_cover(game)
            img = self._cover_image(cached, (150, 225)) if cached else None
            if img is not None:
                cover_lbl.configure(image=img, text="")
            cover_lbl.pack(padx=8, pady=(8, 4))
            # Real art or placeholder generated off-thread to keep the UI smooth.
            self._load_cover_into(name, cover_lbl, (150, 225), guard_selected=False)
            self._accent_button(tile, "Open", lambda n=name: self._open_from_grid(n),
                                width=130).pack(pady=(0, 10))

    def _open_from_grid(self, name: str) -> None:
        self.selected_game = name
        self.library_view = "list"
        self.config_data["library_view"] = "list"
        cfg.save_config(self.config_data)
        self._show_page("Games")   # clears header/body before rebuilding

    def _all_entries(self) -> List[str]:
        saved = sorted(self.games_doc.get("games", {}).keys(), key=str.lower)
        saved_lower = {s.lower() for s in saved}
        detected_only = sorted(
            (d.name for d in self.detected.values() if d.name.lower() not in saved_lower),
            key=str.lower)
        return [f"{g}" for g in saved] + [f"{g}  (detected)" for g in detected_only]

    def _entry_to_name(self, entry: str) -> str:
        return entry[:-len("  (detected)")] if entry.endswith("  (detected)") else entry

    def _refresh_game_list(self) -> None:
        for w in self.game_list.winfo_children():
            w.destroy()
        for entry in self._all_entries():
            name = self._entry_to_name(entry)
            active = name == self.selected_game
            # Small thumbnail: only already-cached local art (cheap). Generating
            # placeholders here would block the UI for large libraries.
            g = prof.find_game(self.games_doc, name)
            thumb = self._cover_image(covers.cached_cover(g), (22, 33))
            ctk.CTkButton(
                self.game_list, text=entry, anchor="w", corner_radius=6,
                image=thumb, compound="left",
                fg_color=ACCENT if active else "transparent",
                text_color="white" if active else ("gray10", "gray90"),
                hover_color=("gray80", "gray25"),
                command=lambda n=name: self._select_game(n)).pack(fill="x", pady=2, padx=2)

    def _select_game(self, name: str) -> None:
        self.selected_game = name
        self._refresh_game_list()
        self._render_detail()

    def _render_detail(self) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        name = self.selected_game
        if not name:
            ctk.CTkLabel(self.detail, text="Select a game from the library.",
                         text_color="gray60").pack(anchor="w", pady=20)
            return
        game = prof.find_game(self.games_doc, name)

        # Header: cover art (left) + title/find-settings (right).
        head = ctk.CTkFrame(self.detail, fg_color="transparent")
        head.pack(fill="x", anchor="w")
        cover_label = ctk.CTkLabel(head, text="", width=150)
        cached = covers.cached_cover(game)   # cheap; real art only
        img = self._cover_image(cached, (150, 225)) if cached else None
        if img is not None:
            cover_label.configure(image=img)
        cover_label.pack(side="left", padx=(0, 14), pady=(0, 6))
        # Real art (network) or a generated placeholder — resolved off-thread.
        self._load_cover_into(name, cover_label)

        info = ctk.CTkFrame(head, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, anchor="n")
        ctk.CTkLabel(info, text=name,
                     font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        self._add_find_settings(name, info)

        # Quick presets (apply instantly, scaled to this console).
        ctk.CTkLabel(info, text="Quick presets", text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 0))
        prow = ctk.CTkFrame(info, fg_color="transparent")
        prow.pack(anchor="w")
        for preset in presets.presets_for(self.device.model):
            ctk.CTkButton(prow, text=preset["label"], width=70, height=26,
                          fg_color=("gray75", "gray30"), hover_color=("gray65", "gray38"),
                          text_color=("gray10", "gray90"),
                          command=lambda p=preset, n=name: self._apply(n, p)).pack(
                              side="left", padx=(0, 6), pady=2)

        if not game or not game.get("profiles"):
            ctk.CTkLabel(self.detail, text="No saved profile for this game yet.",
                         text_color="gray60").pack(anchor="w", pady=(8, 6))
            row = ctk.CTkFrame(self.detail, fg_color="transparent")
            row.pack(anchor="w")
            self._accent_button(row, "＋ Add profile",
                                lambda: self._open_edit_form(name)).pack(side="left")
            ctk.CTkButton(row, text="✨ Suggest from PCGamingWiki",
                          command=lambda: self._suggest(name),
                          fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(side="left", padx=8)
            return

        ctk.CTkLabel(self.detail, text=f"Process: {game.get('process_name', '—')}",
                     text_color="gray60", font=ctk.CTkFont(size=12)).pack(anchor="w")
        if game.get("source"):
            ctk.CTkLabel(self.detail, text=f"Source: {game['source']}",
                         text_color="gray50", font=ctk.CTkFont(size=11)).pack(anchor="w")

        for profile in game["profiles"]:
            self._add_profile_card(name, profile)
        ctk.CTkButton(self.detail, text="✎ Edit game",
                      command=lambda: self._open_edit_form(name),
                      fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(anchor="w", pady=(10, 0))

    def _add_profile_card(self, game_name: str, profile: Dict) -> None:
        card = self._card(self.detail)
        card.pack(fill="x", pady=6)
        s = profile.get("tdp_sustained", "?")
        b = profile.get("tdp_boost", "?")
        batt = batteryest.estimate_text(profile, self.device.model)
        meta = (f"{profile.get('resolution', '?')}  ·  {s}/{b} W  ·  "
                f"{profile.get('fps_cap', 0) or '∞'} fps"
                + (f"  ·  {batt}" if batt else ""))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        self._accent_button(top, f"▶ {profile.get('label', 'Profile')}",
                            lambda p=profile: self._apply(game_name, p),
                            width=180).pack(side="left")
        ctk.CTkLabel(top, text=meta, text_color="gray60",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=12)

        # Validate the profile against the detected console.
        issues = sysinfo.validate_profile(profile, self.device.model)
        if issues:
            ctk.CTkLabel(top, text=" ⚠ check ", text_color=RISK_COLORS["aggressive"],
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="right")
            for w in issues:
                ctk.CTkLabel(card, text="⚠ " + w, text_color=RISK_COLORS["aggressive"],
                             font=ctk.CTkFont(size=11), justify="left",
                             wraplength=560).pack(anchor="w", padx=12)
        else:
            ctk.CTkLabel(top, text=" ✓ fits ", text_color=RISK_COLORS["safe"],
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="right")
        if profile.get("notes"):
            ctk.CTkLabel(card, text=profile["notes"], text_color="gray55",
                         font=ctk.CTkFont(size=11), justify="left",
                         wraplength=560).pack(anchor="w", padx=12, pady=(0, 10))

    def _add_find_settings(self, name: str, parent=None) -> None:
        parent = parent or self.detail
        links = weblinks.build_links(name, self.config_data)
        mapping = {label: url for label, url in links}
        var = ctk.StringVar(value="🔎 Find settings")
        ctk.CTkOptionMenu(
            parent, variable=var, values=list(mapping.keys()),
            width=200, fg_color=ACCENT, button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
            command=lambda choice: weblinks.open_link(mapping[choice])).pack(
                anchor="w", pady=(8, 4))

    # ===================================================== System Tweaks =====
    def _page_tweaks(self) -> None:
        self._header_title("System Tweaks")
        self._accent_button(self.header, "✓ Apply all safe",
                            self._apply_all_safe, width=130).pack(side="right")
        ctk.CTkButton(self.header, text="🛡 Restore point",
                      command=self._create_restore_point, width=120,
                      fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(side="right", padx=8)

        note = ("Reversible — Apply records the previous value, Revert restores it. "
                "Make a restore point first to be safe.")
        if self.engine.dry_run:
            note = "DRY-RUN (not on Windows): actions are shown, nothing changes.  " + note

        scroller = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        scroller.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(scroller, text=note, text_color="gray60",
                     font=ctk.CTkFont(size=12), wraplength=720,
                     justify="left").pack(anchor="w", pady=(0, 2))
        self._tweak_status: Dict[str, ctk.CTkLabel] = {}

        last_cat = None
        for tw in st.all_tweaks():
            if tw.category != last_cat:
                ctk.CTkLabel(scroller, text=tw.category,
                             font=ctk.CTkFont(size=14, weight="bold"),
                             text_color=ACCENT).pack(anchor="w", pady=(12, 2))
                last_cat = tw.category
            self._add_tweak_card(scroller, tw)

    def _add_tweak_card(self, parent, tw: st.Tweak) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=5)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(top, text=tw.title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text=f" {tw.risk.upper()} ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=RISK_COLORS.get(tw.risk)).pack(side="left", padx=8)
        status = ctk.CTkLabel(top, text="● applied" if self.engine.is_applied(tw) else "",
                              font=ctk.CTkFont(size=10, weight="bold"),
                              text_color=RISK_COLORS["safe"])
        status.pack(side="right")
        self._tweak_status[tw.id] = status

        ctk.CTkLabel(card, text=tw.description, text_color="gray60",
                     font=ctk.CTkFont(size=12), justify="left",
                     wraplength=700).pack(anchor="w", padx=12, pady=(2, 4))
        if not tw.reversible:
            ctk.CTkLabel(card, text="⚠ " + (tw.revert_note or "Not auto-reversible."),
                         text_color=RISK_COLORS["aggressive"],
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(anchor="w", padx=12, pady=(2, 10))
        self._accent_button(btns, "Apply", lambda t=tw: self._apply_tweak(t),
                            width=90).pack(side="left")
        ctk.CTkButton(btns, text="Revert", command=lambda t=tw: self._revert_tweak(t),
                      width=90, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(side="left", padx=8)

    def _refresh_tweak_status(self, tw: st.Tweak) -> None:
        lbl = self._tweak_status.get(tw.id)
        if lbl is not None:
            lbl.configure(text="● applied" if self.engine.is_applied(tw) else "")

    def _apply_tweak(self, tw: st.Tweak) -> None:
        res = self.engine.apply(tw)
        self._refresh_tweak_status(tw)
        self._report(tw.title, res.ok, res.message, res.actions, res.dry_run)

    def _revert_tweak(self, tw: st.Tweak) -> None:
        res = self.engine.revert(tw)
        self._refresh_tweak_status(tw)
        self._report(tw.title, res.ok, res.message, res.actions, res.dry_run)

    def _apply_all_safe(self) -> None:
        safe = [t for t in st.all_tweaks() if t.risk == st.SAFE]
        if not messagebox.askyesno("Apply all safe tweaks",
                                   f"Apply {len(safe)} low-risk tweaks now? "
                                   "Each is individually reversible."):
            return
        failures = [t.title for t in safe if not self.engine.apply(t).ok]
        for t in safe:
            self._refresh_tweak_status(t)
        if failures:
            messagebox.showwarning("Done with warnings",
                                   "Couldn't apply:\n- " + "\n- ".join(failures))
        else:
            messagebox.showinfo("Done", f"Applied {len(safe)} safe tweaks.")

    def _create_restore_point(self) -> None:
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            res = self.engine.create_restore_point()
        finally:
            self.configure(cursor="")
        (messagebox.showinfo if res.ok else messagebox.showerror)("System Restore", res.message)

    # ============================================================ Boost ======
    def _page_boost(self) -> None:
        self._header_title("Boost", "frame-gen · upscaling · fullscreen exclusive")
        scroller = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        scroller.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(scroller, text="Native AMD boosters (free, built-in)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(anchor="w", pady=(4, 2))
        for g in boost.native_boost_guides():
            self._add_guide_card(scroller, g)

        ctk.CTkLabel(scroller, text="Apps", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(anchor="w", pady=(14, 2))
        steam_paths = self.config_data.get("steam_library_paths", [])
        self._add_tool_row(scroller, boost.detect_lossless_scaling(steam_paths))
        self._add_tool_row(scroller, boost.detect_anyfse(self.config_data.get("anyfse_path")))

        ctk.CTkLabel(scroller, text="Force Fullscreen Exclusive (replaces AnyFSE)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(anchor="w", pady=(14, 2))
        card = self._card(scroller)
        card.pack(fill="x", pady=5)
        ctk.CTkLabel(card, text="Disables fullscreen optimizations for a game's .exe "
                     "(via a compatibility flag) so it runs true fullscreen — better "
                     "VRR and latency. Pick the game's executable:",
                     text_color="gray60", font=ctk.CTkFont(size=12),
                     justify="left", wraplength=700).pack(anchor="w", padx=12, pady=(10, 6))
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(anchor="w", padx=12, pady=(0, 10))
        self._accent_button(btns, "Force FSE for .exe…",
                            lambda: self._force_fse(True), width=160).pack(side="left")
        ctk.CTkButton(btns, text="Remove FSE for .exe…",
                      command=lambda: self._force_fse(False), width=160,
                      fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(side="left", padx=8)

    def _add_guide_card(self, parent, g: boost.GuideCard) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=5)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(top, text=g.title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        tag = "NATIVE" if g.native else "THIRD-PARTY"
        ctk.CTkLabel(top, text=f"  {tag}", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=RISK_COLORS["safe"] if g.native
                     else RISK_COLORS["aggressive"]).pack(side="left", padx=6)
        ctk.CTkLabel(card, text=g.body, text_color="gray60",
                     font=ctk.CTkFont(size=12), justify="left",
                     wraplength=700).pack(anchor="w", padx=12, pady=(2, 10 if not g.link else 4))
        if g.link:
            ctk.CTkButton(card, text="Open store page",
                          command=lambda u=g.link: weblinks.open_link(u),
                          width=130, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(
                              anchor="w", padx=12, pady=(0, 10))

    def _add_tool_row(self, parent, tool: boost.ToolStatus) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=5)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)
        dot = "🟢" if tool.installed else "⚪"
        ctk.CTkLabel(row, text=f"{dot}  {tool.name}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        state = "Installed" if tool.installed else "Not detected"
        ctk.CTkLabel(row, text=f"   {state}", text_color="gray60",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        if tool.installed:
            self._accent_button(row, "Launch", lambda t=tool: boost.launch_tool(t),
                                width=90).pack(side="right")
        else:
            ctk.CTkButton(row, text="Get it", width=90, fg_color="transparent",
                          border_width=1, text_color=("gray10", "gray90"),
                          border_color=("gray65", "gray45"), hover_color=("gray85", "gray25"),
                          command=lambda t=tool: boost.open_install_link(t)).pack(side="right")

    def _force_fse(self, enable: bool) -> None:
        path = filedialog.askopenfilename(title="Select the game's .exe",
                                          filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if not path:
            return
        res = boost.set_fse(path, enable)
        self._report("Fullscreen Exclusive", res.ok, res.message, res.actions, res.dry_run)

    # ========================================================= Hibernation ===
    def _page_hibernation(self) -> None:
        self._header_title("Hibernation", "fix overnight battery drain")
        scroller = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        scroller.grid(row=0, column=0, sticky="nsew")

        state = hibernate.get_state()
        # State card.
        card = self._card(scroller)
        card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text=state.summary(),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(card, text="The Ally uses modern-standby sleep, which slowly "
                     "drains the battery. Hibernation saves to disk and uses ~no "
                     "power.", text_color="gray60", font=ctk.CTkFont(size=12),
                     justify="left", wraplength=700).pack(anchor="w", padx=12, pady=(0, 6))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=(0, 12))
        self._accent_button(row, "Enable hibernation",
                            lambda: self._hib(hibernate.set_enabled(True), "Enable hibernation"),
                            width=160).pack(side="left")
        ctk.CTkButton(row, text="Disable hibernation", width=160, fg_color="transparent",
                      border_width=1,
                      command=lambda: self._hib(hibernate.set_enabled(False),
                                                "Disable hibernation")).pack(side="left", padx=8)

        # Hibernate-instead-of-sleep card.
        card2 = self._card(scroller)
        card2.pack(fill="x", pady=6)
        ctk.CTkLabel(card2, text="Hibernate instead of sleep",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(card2, text="Make the power and sleep buttons hibernate (AC + "
                     "battery) so closing the Ally won't drain it overnight.",
                     text_color="gray60", font=ctk.CTkFont(size=12), justify="left",
                     wraplength=700).pack(anchor="w", padx=12, pady=(0, 6))
        row2 = ctk.CTkFrame(card2, fg_color="transparent")
        row2.pack(anchor="w", padx=12, pady=(0, 12))
        self._accent_button(row2, "Buttons → hibernate",
                            lambda: self._hib(hibernate.set_power_button_hibernate(),
                                              "Power buttons"), width=170).pack(side="left")
        ctk.CTkButton(row2, text="Buttons → sleep", width=150, fg_color="transparent",
                      border_width=1,
                      command=lambda: self._hib(hibernate.restore_power_button_sleep(),
                                                "Power buttons")).pack(side="left", padx=8)

        # Auto-hibernate timeout card.
        card3 = self._card(scroller)
        card3.pack(fill="x", pady=6)
        ctk.CTkLabel(card3, text="Auto-hibernate after sleeping",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(card3, text="Automatically move from sleep to hibernation after "
                     "this many minutes (0 = never).", text_color="gray60",
                     font=ctk.CTkFont(size=12), justify="left",
                     wraplength=700).pack(anchor="w", padx=12, pady=(0, 6))
        row3 = ctk.CTkFrame(card3, fg_color="transparent")
        row3.pack(anchor="w", padx=12, pady=(0, 12))
        self.hib_minutes = ctk.StringVar(
            value=str(self.config_data.get("auto_hibernate_minutes", 30)))
        ctk.CTkEntry(row3, textvariable=self.hib_minutes, width=80).pack(side="left")
        ctk.CTkLabel(row3, text="minutes").pack(side="left", padx=6)
        self._accent_button(row3, "Apply timeout", self._apply_hib_timeout,
                            width=130).pack(side="left", padx=8)

        # Hibernate now.
        self._accent_button(scroller, "⏻ Hibernate now",
                            lambda: self._hib(hibernate.hibernate_now(), "Hibernate now"),
                            width=160).pack(anchor="w", pady=10)

    def _hib(self, res, title: str) -> None:
        self._report(title, res.ok, res.message, res.actions, res.dry_run)

    def _apply_hib_timeout(self) -> None:
        try:
            minutes = int(self.hib_minutes.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter a whole number of minutes.")
            return
        self.config_data["auto_hibernate_minutes"] = minutes
        cfg.save_config(self.config_data)
        res = hibernate.set_auto_hibernate_timeout(minutes)
        self._hib(res, "Auto-hibernate")

    # ========================================================= Armoury =======
    def _page_armoury(self) -> None:
        self._header_title("Armoury Crate", self.device.summary())
        scroller = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        scroller.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(scroller, text="Armoury Crate has no public API, so these can't be "
                     "toggled from here. Use the links to jump to the right place; "
                     "items marked ✓ can be done natively in the Games tab instead.",
                     text_color="gray60", font=ctk.CTkFont(size=12), justify="left",
                     wraplength=720).pack(anchor="w", pady=(0, 8))

        links = ctk.CTkFrame(scroller, fg_color="transparent")
        links.pack(fill="x", pady=(0, 8))
        for dl in armoury.deep_links():
            ctk.CTkButton(links, text=dl.label, command=lambda d=dl: armoury.open_link(d),
                          fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25"), width=150).pack(
                              side="left", padx=(0, 6), pady=2)

        for item in armoury.checklist(self.device):
            card = self._card(scroller)
            card.pack(fill="x", pady=5)
            ctk.CTkLabel(card, text=item.title,
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(card, text="→ " + item.recommended, text_color=ACCENT,
                         font=ctk.CTkFont(size=12, weight="bold"), justify="left",
                         wraplength=720).pack(anchor="w", padx=12, pady=(2, 0))
            ctk.CTkLabel(card, text=item.why, text_color="gray60",
                         font=ctk.CTkFont(size=12), justify="left",
                         wraplength=720).pack(anchor="w", padx=12, pady=(0, 4))
            if item.native:
                mark = "✓ " if item.native.lower().startswith("yes") else "• "
                ctk.CTkLabel(card, text=mark + item.native, text_color=RISK_COLORS["safe"],
                             font=ctk.CTkFont(size=11), justify="left",
                             wraplength=720).pack(anchor="w", padx=12, pady=(0, 10))

    # ============================================================ shared =====
    def _report(self, title: str, ok: bool, message: str,
                actions: Optional[List[str]] = None, dry_run: bool = False) -> None:
        body = message
        if actions:
            body += "\n\n" + "\n".join(actions[:8])
        if ok:
            self.applied_var.set(f"{title}: {message}")
            if dry_run:
                messagebox.showinfo(title + " (dry-run)", body)
        else:
            messagebox.showerror(title, body)

    def _effective_profile(self, profile: Dict) -> Dict:
        mode = self.power_mode.get()
        if mode == "Auto":
            plugged = power.is_plugged_in()
            mode = "Plugged in" if (plugged is None or plugged) else "Battery"
        eff = dict(profile)
        if mode == "Battery":
            eff["tdp_boost"] = eff.get("tdp_sustained", eff.get("tdp_boost"))
        return eff

    def _apply(self, game_name: str, profile: Dict, announce: bool = True) -> None:
        eff = self._effective_profile(profile)
        result = ryzenadj.apply_profile(eff, self.config_data)
        cmd_str = " ".join(result.command)
        if result.ok:
            self.config_data["last_applied"] = {
                "game": game_name, "profile_label": profile.get("label", "")}
            cfg.save_config(self.config_data)
            self.applied_var.set(f"Applied: {game_name} — {profile.get('label', '')}")
            self._maybe_apply_resolution(profile)
        elif result.dry_run and announce:
            messagebox.showinfo("Dry-run (RyzenAdj not found)",
                                f"{result.message}\n\nWould run:\n{cmd_str}")
        elif announce:
            messagebox.showerror("Apply failed", f"{result.message}\n\n{cmd_str}")

    def _maybe_apply_resolution(self, profile: Dict) -> None:
        """If the profile opts in, switch the display to its resolution."""
        if not profile.get("apply_resolution"):
            return
        parsed = display.parse_resolution(profile.get("resolution", ""))
        if parsed:
            display.set_mode(parsed[0], parsed[1], sysinfo.PANEL_HZ)

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
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.applied_var.set("Scanning installed games…")

        def work():
            try:
                found = scan_all(self.config_data)
            except Exception:
                found = []
            self.after(0, lambda: self._scan_done(found))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, found) -> None:
        self._scanning = False
        self.detected = {d.name: d for d in found}
        if self.active_page == "Games":
            self._refresh_game_list()
        self.applied_var.set(f"Scan complete — {len(found)} game(s) detected.")
        messagebox.showinfo("Scan complete", f"Detected {len(found)} installed game(s).")

    def _auto_fill_all(self) -> None:
        """Background pass over the library: fetch cover art for everything and
        suggest a PCGamingWiki profile for games that don't have one yet.

        Skips games you've already customised (keeps their profiles), only adds
        a suggested profile where none exists, and never overwrites saved art.
        """
        if getattr(self, "_autofill_running", False):
            return
        names = [self._entry_to_name(e) for e in self._all_entries()]
        if not names:
            messagebox.showinfo("Auto-fill", "No games yet — Scan or Add a game first.")
            return
        if not messagebox.askyesno(
            "Auto-fill all",
            f"Fetch cover art for {len(names)} game(s) and suggest a starting "
            "profile for any without one?\n\nSuggestions come from the public "
            "PCGamingWiki API and are labelled untested. Existing profiles are "
            "kept."):
            return
        self._autofill_running = True

        def work():
            suggested = covered = 0
            for i, name in enumerate(names, 1):
                self.after(0, lambda i=i, n=name:
                           self.applied_var.set(f"Auto-filling {i}/{len(names)}: {n}…"))
                game = prof.find_game(self.games_doc, name)
                det = self.detected.get(name)
                # 1) Suggest a profile if there isn't one.
                if not (game and game.get("profiles")):
                    try:
                        sugg = pcgamingwiki.suggest_profile(name, self.config_data)
                    except Exception:
                        sugg = None
                    if sugg:
                        proc = (det.process_name if det else None) or \
                               (game or {}).get("process_name", "")
                        prof.upsert_game(self.games_doc, name, proc, [sugg],
                                         source="PCGamingWiki (algorithmic suggestion)")
                        game = prof.find_game(self.games_doc, name)
                        suggested += 1
                # 2) Fetch + persist cover art (Steam appid or a saved cover URL).
                appid = det.appid if det else None
                try:
                    path = covers.resolve_cover(game, appid, allow_network=True)
                except Exception:
                    path = None
                if path and game is not None and game.get("cover") != path:
                    prof.upsert_game(self.games_doc, name,
                                     game.get("process_name", ""),
                                     game.get("profiles", []),
                                     source=game.get("source", "manual entry"),
                                     cover=path)
                    covered += 1
            try:
                prof.save_games(self.games_doc)
            except Exception:
                pass
            self.after(0, lambda: self._auto_fill_done(suggested, covered))

        threading.Thread(target=work, daemon=True).start()

    def _auto_fill_done(self, suggested: int, covered: int) -> None:
        self._autofill_running = False
        self.applied_var.set(f"Auto-fill done — {suggested} suggested, {covered} covers.")
        if self.active_page == "Games":
            self._show_page("Games")
        messagebox.showinfo("Auto-fill complete",
                            f"Suggested {suggested} profile(s) and fetched "
                            f"{covered} cover(s).\n\nSuggestions are untested "
                            "starting points — tweak them per game.")

    def _suggest(self, name: str) -> None:
        if getattr(self, "_suggesting", False):
            return
        self._suggesting = True
        self.applied_var.set(f"Looking up {name} on PCGamingWiki…")

        def work():
            try:
                suggestion = pcgamingwiki.suggest_profile(name, self.config_data)
            except Exception:
                suggestion = None
            self.after(0, lambda: self._suggest_done(name, suggestion))

        threading.Thread(target=work, daemon=True).start()

    def _suggest_done(self, name: str, suggestion) -> None:
        self._suggesting = False
        self.applied_var.set("")
        if not suggestion:
            messagebox.showinfo("No suggestion",
                                "Couldn't derive a starting profile from PCGamingWiki.\n"
                                "Use 'Find settings' to look up tested values, then Add profile.")
            return
        detected = self.detected.get(name)
        proc = (detected.process_name if detected else None) or ""
        if not proc:
            proc = simpledialog.askstring("Process name",
                                          f"Executable for {name} (e.g. game.exe):",
                                          parent=self) or ""
        prof.upsert_game(self.games_doc, name, proc, [suggestion],
                         source="PCGamingWiki (algorithmic suggestion)")
        prof.save_games(self.games_doc)
        self.selected_game = name
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

    # =========================================================== Settings ====
    def _page_settings(self) -> None:
        self._header_title("Settings")
        scroller = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        scroller.grid(row=0, column=0, sticky="nsew")

        # --- Automation ---
        card = self._card(scroller)
        card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text="Automation", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=12, pady=(10, 4))
        self.auto_apply_switch = ctk.CTkSwitch(
            card, text="Auto-apply a game's profile when it launches "
            "(and reset on exit)", progress_color=ACCENT, command=self._toggle_auto_apply)
        if self.config_data.get("auto_apply"):
            self.auto_apply_switch.select()
        self.auto_apply_switch.pack(anchor="w", padx=12, pady=(0, 4))
        if not self.watcher.available():
            ctk.CTkLabel(card, text="(psutil not available — auto-apply disabled)",
                         text_color="gray60", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
        self._toggle_row(card, "enable_hotkey", "Global hotkey to reapply last profile")
        self._toggle_row(card, "minimize_to_tray", "Minimise to system tray on close")
        self.gamepad_switch = ctk.CTkSwitch(
            card, text="Gamepad navigation (Xbox controller: D-pad move, A select, "
            "LB/RB switch tabs)", progress_color=ACCENT, command=self._toggle_gamepad)
        if self.config_data.get("enable_gamepad"):
            self.gamepad_switch.select()
        self.gamepad_switch.pack(anchor="w", padx=12, pady=2)
        if not self.pad.available():
            ctk.CTkLabel(card, text="(no controller / XInput unavailable here)",
                         text_color="gray60", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
        ctk.CTkLabel(card, text="", height=4).pack()

        # --- Hardware / paths ---
        card2 = self._card(scroller)
        card2.pack(fill="x", pady=6)
        ctk.CTkLabel(card2, text="Hardware & paths", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=12, pady=(10, 4))
        row = ctk.CTkFrame(card2, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=4)
        ctk.CTkLabel(row, text="Console model:").pack(side="left", padx=(0, 8))
        self.device_var = ctk.StringVar(
            value=self.config_data.get("device_override") or "Auto-detect")
        ctk.CTkOptionMenu(row, variable=self.device_var, width=180,
                          values=["Auto-detect", sysinfo.ALLY, sysinfo.ALLY_X],
                          fg_color=ACCENT, button_color=ACCENT_HOVER,
                          button_hover_color=ACCENT_HOVER,
                          command=self._set_device_override).pack(side="left")
        rrow = ctk.CTkFrame(card2, fg_color="transparent")
        rrow.pack(anchor="w", padx=12, pady=(4, 10))
        ctk.CTkLabel(rrow, text=f"RyzenAdj: {self.config_data.get('ryzenadj_path', '—')}",
                     text_color="gray60", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(rrow, text="Set RyzenAdj…", width=120, command=self._choose_ryzenadj,
                      fg_color=("gray75", "gray30"), hover_color=("gray65", "gray38"),
                      text_color=("gray10", "gray90")).pack(side="left")

        # --- Backup / safety ---
        card3 = self._card(scroller)
        card3.pack(fill="x", pady=6)
        ctk.CTkLabel(card3, text="Backup & safety", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=12, pady=(10, 4))
        brow = ctk.CTkFrame(card3, fg_color="transparent")
        brow.pack(anchor="w", padx=12, pady=(0, 10))
        self._accent_button(brow, "Export config…", self._export_config, width=130).pack(side="left")
        ctk.CTkButton(brow, text="Import config…", command=self._import_config, width=130,
                      fg_color=("gray75", "gray30"), hover_color=("gray65", "gray38"),
                      text_color=("gray10", "gray90")).pack(side="left", padx=8)
        ctk.CTkButton(brow, text="⟲ Revert ALL tweaks", command=self._revert_all_tweaks,
                      width=160, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), border_color=("gray65", "gray45"),
                      hover_color=("gray85", "gray25")).pack(side="left", padx=8)

        # --- About / updates ---
        card4 = self._card(scroller)
        card4.pack(fill="x", pady=6)
        ctk.CTkLabel(card4, text=f"Ally Optimizer v{__version__}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self._accent_button(card4, "Check for updates", self._check_updates,
                            width=150).pack(anchor="w", padx=12, pady=(0, 12))

    def _toggle_row(self, parent, key: str, label: str) -> None:
        sw = ctk.CTkSwitch(parent, text=label, progress_color=ACCENT,
                           command=lambda: self._set_config_flag(key, sw.get()))
        if self.config_data.get(key, True):
            sw.select()
        sw.pack(anchor="w", padx=12, pady=2)

    def _set_config_flag(self, key: str, value) -> None:
        self.config_data[key] = bool(value)
        cfg.save_config(self.config_data)

    def _set_device_override(self, choice: str) -> None:
        self.config_data["device_override"] = None if choice == "Auto-detect" else choice
        cfg.save_config(self.config_data)
        self.device = sysinfo.detect_device(self.config_data.get("device_override"))
        self.device_label.configure(text=self.device.summary())

    def _toggle_auto_apply(self) -> None:
        on = bool(self.auto_apply_switch.get())
        self.config_data["auto_apply"] = on
        cfg.save_config(self.config_data)
        if on:
            self.watcher.start()
        else:
            self.watcher.stop()

    def _export_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export config", defaultextension=".zip",
            initialfile="ally-optimizer-backup.zip",
            filetypes=[("Zip", "*.zip")])
        if not path:
            return
        included = backup.export_config(path)
        messagebox.showinfo("Export", "Saved backup with: " + ", ".join(included))

    def _import_config(self) -> None:
        path = filedialog.askopenfilename(title="Import config",
                                          filetypes=[("Zip", "*.zip"), ("All", "*.*")])
        if not path:
            return
        restored = backup.import_config(path)
        # Reload from disk.
        self.config_data = cfg.load_config()
        self.games_doc = prof.load_games()
        messagebox.showinfo("Import", "Restored: " + ", ".join(restored)
                            + "\n\nSome changes may need a restart.")
        self._show_page("Games")

    def _revert_all_tweaks(self) -> None:
        applied = self.engine.applied_tweaks()
        if not applied:
            messagebox.showinfo("Revert all", "No tweaks are currently applied.")
            return
        if not messagebox.askyesno("Revert all tweaks",
                                   f"Revert all {len(applied)} applied tweaks now?"):
            return
        results = self.engine.revert_all()
        failed = [r.tweak_id for r in results if not r.ok]
        if failed:
            messagebox.showwarning("Revert all", "Some failed: " + ", ".join(failed))
        else:
            messagebox.showinfo("Revert all", f"Reverted {len(results)} tweaks.")

    def _check_updates(self) -> None:
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            info = updates.check_for_update(__version__)
        finally:
            self.configure(cursor="")
        if info is None:
            messagebox.showinfo("Updates", "Couldn't reach GitHub to check for updates.")
        elif info.update_available:
            if messagebox.askyesno("Update available",
                                   f"v{info.latest} is available (you have v{info.current}).\n\n"
                                   "Open the releases page?"):
                weblinks.open_link(info.url)
        else:
            messagebox.showinfo("Updates", f"You're on the latest version (v{info.current}).")

    # ----------------------------------------------- auto-apply / onboarding -
    def _setup_watcher(self) -> None:
        if self.config_data.get("auto_apply") and self.watcher.available():
            self.watcher.start()

    def _auto_apply(self, game_name: str) -> None:
        game = prof.find_game(self.games_doc, game_name)
        if game and game.get("profiles"):
            self._apply(game_name, game["profiles"][0], announce=False)
            self.applied_var.set(f"Auto-applied {game_name} (launch detected).")

    def _auto_revert(self, game_name: str) -> None:
        ryzenadj.reset(self.config_data)
        display.restore()
        self.applied_var.set(f"{game_name} closed — reset to default.")

    def _maybe_onboard(self) -> None:
        if self.config_data.get("seen_welcome"):
            return
        self.config_data["seen_welcome"] = True
        cfg.save_config(self.config_data)
        WelcomeDialog(self)

    # ------------------------------------------------------ gamepad nav ------
    def _setup_gamepad(self) -> None:
        if self.config_data.get("enable_gamepad") and self.pad.available():
            self.pad.start()
            self._refresh_focusables()

    def _toggle_gamepad(self) -> None:
        on = bool(self.gamepad_switch.get())
        self.config_data["enable_gamepad"] = on
        cfg.save_config(self.config_data)
        if on and self.pad.available():
            self.pad.start()
            self._refresh_focusables()
        else:
            self.pad.stop()

    def _walk_focusables(self, widget, out: List) -> None:
        focus_types = (ctk.CTkButton, ctk.CTkSwitch, ctk.CTkSegmentedButton,
                       ctk.CTkOptionMenu)
        for child in widget.winfo_children():
            if isinstance(child, focus_types):
                out.append(child)
            self._walk_focusables(child, out)

    def _refresh_focusables(self) -> None:
        items: List = list(self.nav_buttons.values())
        self._walk_focusables(self.header, items)
        self._walk_focusables(self.body, items)
        self._focusables = [w for w in items if w.winfo_exists()]
        self._focus_idx = min(self._focus_idx, max(0, len(self._focusables) - 1))
        self._highlight_focus()

    def _highlight_focus(self) -> None:
        for i, w in enumerate(self._focusables):
            try:
                if i == self._focus_idx:
                    w.configure(border_width=3, border_color="#ffd400")
                else:
                    # Leave accent/ghost borders alone; only clear our highlight.
                    if str(w.cget("border_color")) == "#ffd400":
                        w.configure(border_width=0)
            except Exception:
                continue

    def _gamepad_action(self, action: str) -> None:
        if not self.config_data.get("enable_gamepad") or not self._focusables:
            if action in ("next_tab", "prev_tab"):
                pass
            else:
                return
        if action in ("down", "right"):
            self._focus_idx = gamepad.next_index(self._focus_idx, 1, len(self._focusables))
            self._highlight_focus()
            self._scroll_into_view()
        elif action in ("up", "left"):
            self._focus_idx = gamepad.next_index(self._focus_idx, -1, len(self._focusables))
            self._highlight_focus()
            self._scroll_into_view()
        elif action == "activate":
            self._activate_focused()
        elif action == "back":
            self._show_page("Games")
        elif action in ("next_tab", "prev_tab"):
            order = list(NAV_ITEMS)
            cur = order.index(self.active_page) if self.active_page in order else 0
            self._show_page(order[(cur + (1 if action == "next_tab" else -1)) % len(order)])

    def _activate_focused(self) -> None:
        if not (0 <= self._focus_idx < len(self._focusables)):
            return
        w = self._focusables[self._focus_idx]
        try:
            if isinstance(w, ctk.CTkButton):
                cmd = getattr(w, "_command", None)
                if cmd:
                    cmd()
            elif isinstance(w, ctk.CTkSwitch):
                w.toggle()
        except Exception:
            pass

    def _scroll_into_view(self) -> None:
        try:
            self._focusables[self._focus_idx].focus_set()
        except Exception:
            pass

    # ----------------------------------------------------------- lifecycle --
    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_switch.get() else "dark"
        self.config_data["theme"] = self.theme_mode
        cfg.save_config(self.config_data)
        ctk.set_appearance_mode(self.theme_mode)

    def _tick_status(self) -> None:
        self.status_var.set(power.get_status().summary())
        if hasattr(self, "device_label"):
            self.device_label.configure(text=self.device.summary())
        self.after(5000, self._tick_status)

    def _setup_hotkey(self) -> None:
        if self.config_data.get("enable_hotkey", True):
            self.hotkeys.register(self.config_data.get("reapply_hotkey", "ctrl+alt+a"),
                                  lambda: self.after(0, self.reapply_last))

    def _setup_tray(self) -> None:
        if not self.config_data.get("minimize_to_tray", True):
            return
        self.tray = TrayIcon(APP_NAME,
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
        self.watcher.stop()
        self.pad.stop()
        self.destroy()


class WelcomeDialog(ctk.CTkToplevel):
    """First-run onboarding: a quick orientation + RyzenAdj prompt."""

    def __init__(self, app: "AllyOptimizerApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Welcome to Ally Optimizer")
        self.geometry("520x420")
        self.transient(app)
        ctk.CTkLabel(self, text="Welcome to Ally Optimizer 👋",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=20, pady=(20, 6))
        steps = (
            "• Games — set a per-game TDP profile and Apply it (RyzenAdj).\n"
            "• System Tweaks — reversible Windows optimisations (make a restore point).\n"
            "• Boost — AFMF/RSR/FSR guidance + Fullscreen-Exclusive.\n"
            "• Hibernation — stop overnight battery drain.\n"
            "• Settings — auto-apply on launch, backups, updates.\n\n"
            "To actually set power limits you need RyzenAdj (free, separate). "
            "Point the app at ryzenadj.exe to get started."
        )
        ctk.CTkLabel(self, text=steps, justify="left", font=ctk.CTkFont(size=12),
                     wraplength=480).pack(anchor="w", padx=20)
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=18)
        ctk.CTkButton(btns, text="Set RyzenAdj path", fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=lambda: (self.app._choose_ryzenadj(), self.destroy())).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="I'll do it later", command=self.destroy,
                      fg_color=("gray75", "gray30"), hover_color=("gray65", "gray38"),
                      text_color=("gray10", "gray90")).pack(side="left", padx=6)
        self.after(60, self.lift)


class EditGameDialog(ctk.CTkToplevel):
    """Add/Edit a game and one profile. Writes back to games.json."""

    def __init__(self, app: AllyOptimizerApp, name: Optional[str]) -> None:
        super().__init__(app)
        self.app = app
        self.title("Edit game" if name else "Add game")
        self.geometry("460x740")
        self.transient(app)
        existing = prof.find_game(app.games_doc, name) if name else None
        first = (existing or {}).get("profiles", [{}])
        first = first[0] if first else {}
        self.imported_cover: Optional[str] = None
        self._tdp_max = app.device.tdp_profile["max"] + 5

        # --- Import from link / text --------------------------------------- #
        imp = ctk.CTkFrame(self, corner_radius=10)
        imp.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(imp, text="Import from link or pasted settings",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 0))
        self.import_box = ctk.CTkTextbox(imp, height=56, width=400)
        self.import_box.pack(padx=10, pady=4)
        ctk.CTkLabel(imp, text="Paste a PCGamingWiki link, any guide URL, or the "
                     "settings text you copied. Some sites (ROG Ally Life, "
                     "rogally.games) block automated fetch — paste the text if a "
                     "link fails.", text_color="gray60", font=ctk.CTkFont(size=10),
                     justify="left", wraplength=400).pack(anchor="w", padx=10)
        ctk.CTkButton(imp, text="Import", command=self._import, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, width=100).pack(anchor="w", padx=10, pady=(4, 10))

        self.vars: Dict[str, ctk.StringVar] = {}
        text_rows = [
            ("Game name", "name", name or ""),
            ("Process .exe", "process_name", (existing or {}).get("process_name", "")),
            ("Profile label", "label", first.get("label", "Custom")),
        ]
        for label, key, value in text_rows:
            ctk.CTkLabel(self, text=label).pack(anchor="w", padx=16, pady=(6, 0))
            var = ctk.StringVar(value=value)
            ctk.CTkEntry(self, textvariable=var, width=420).pack(padx=16)
            self.vars[key] = var

        # TDP sliders (snapped to the console's band).
        self._tdp_slider("TDP sustained", "tdp_sustained", int(first.get("tdp_sustained", 15)))
        self._tdp_slider("TDP boost", "tdp_boost", int(first.get("tdp_boost", 20)))

        for label, key, value in (("Resolution", "resolution",
                                    first.get("resolution", "1920x1080")),
                                   ("FPS cap (0 = none)", "fps_cap",
                                    str(first.get("fps_cap", 0)))):
            ctk.CTkLabel(self, text=label).pack(anchor="w", padx=16, pady=(6, 0))
            var = ctk.StringVar(value=str(value))
            ctk.CTkEntry(self, textvariable=var, width=420).pack(padx=16)
            self.vars[key] = var

        self.apply_res_var = ctk.BooleanVar(value=bool(first.get("apply_resolution")))
        ctk.CTkSwitch(self, text="Also set the display to this resolution on Apply",
                      variable=self.apply_res_var, progress_color=ACCENT).pack(
                          anchor="w", padx=16, pady=(10, 2))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=14)
        ctk.CTkButton(btns, text="Save", command=self._save, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", command=self.destroy,
                      fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), border_color=("gray65", "gray45"), hover_color=("gray85", "gray25")).pack(side="left", padx=6)
        if name:
            self.vars["name"].set(name)
        self.after(50, self.lift)

    def _tdp_slider(self, label: str, key: str, value: int) -> None:
        var = ctk.StringVar(value=str(value))
        self.vars[key] = var
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(6, 0))
        ctk.CTkLabel(head, text=label).pack(side="left")
        val_lbl = ctk.CTkLabel(head, textvariable=var, text_color=ACCENT,
                               font=ctk.CTkFont(weight="bold"))
        val_lbl.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(head, text="W").pack(side="left")
        slider = ctk.CTkSlider(self, from_=5, to=self._tdp_max,
                               number_of_steps=self._tdp_max - 5,
                               progress_color=ACCENT, button_color=ACCENT,
                               button_hover_color=ACCENT_HOVER,
                               command=lambda v: var.set(str(int(float(v)))))
        slider.set(max(5, min(self._tdp_max, value)))
        slider.pack(fill="x", padx=16)

    def _import(self) -> None:
        text = self.import_box.get("1.0", "end").strip()
        if not text:
            return
        if importer.needs_fetch_warning(text):
            if not messagebox.askyesno(
                "Fetch a web page?",
                "This will try to download that page and read settings from it.\n\n"
                "Some community sites (ROG Ally Life, rogally.games) block "
                "automated access and forbid scraping, so it may fail — in that "
                "case, copy the settings text and paste that instead.\n\nContinue?",
                parent=self):
                return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            result = importer.import_from_input(text, self.app.config_data)
        finally:
            self.configure(cursor="")
        if not result.ok:
            messagebox.showinfo("Import", result.message, parent=self)
            return
        # Populate only the fields we found; leave the rest as-is.
        applied = []
        for key in ("tdp_sustained", "tdp_boost", "resolution", "fps_cap", "label"):
            if key in result.fields and key in self.vars:
                self.vars[key].set(str(result.fields[key]))
                applied.append(key)
        if result.cover_url:
            self.imported_cover = result.cover_url
        msg = result.message + (f"\n\nFilled: {', '.join(applied)}." if applied else "")
        if result.warning:
            msg += "\n\n" + result.warning
        messagebox.showinfo("Import", msg, parent=self)

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
            "tdp_sustained": tdp_s, "tdp_boost": tdp_b,
            "resolution": self.vars["resolution"].get().strip(),
            "fps_cap": fps,
            "apply_resolution": bool(self.apply_res_var.get()),
            "notes": "",
        }
        existing = prof.find_game(self.app.games_doc, name)
        if existing and existing.get("profiles"):
            profiles = list(existing["profiles"])
            profiles[0] = profile
            profile["notes"] = existing["profiles"][0].get("notes", "")
            source = existing.get("source", "manual entry")
        else:
            profiles = [profile]
            source = "manual entry"
        prof.upsert_game(self.app.games_doc, name,
                         self.vars["process_name"].get().strip(), profiles, source=source,
                         cover=self.imported_cover)
        prof.save_games(self.app.games_doc)
        self.app.selected_game = name
        self.app._refresh_game_list()
        self.app._render_detail()
        self.destroy()
