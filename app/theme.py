"""ROG-inspired themes for the Tkinter UI — dark and light.

Both palettes share the ROG-red accent. The active palette's colours are
mirrored onto module-level names (``theme.BG`` etc.) so widgets can read them
at build time. Call :func:`apply_theme` with ``"dark"`` or ``"light"``; the
GUI rebuilds its widgets when the user toggles, so the change is immediate.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

ACCENT = "#ff1421"       # ROG red (shared)
ACCENT_HI = "#ff3a45"
FONT = "Segoe UI"

PALETTES = {
    "dark": {
        "BG": "#0d0d0f", "PANEL": "#16161a", "PANEL_HI": "#1f1f25",
        "FG": "#e8e8ea", "FG_MUTED": "#9a9aa2", "BORDER": "#2a2a30",
        "RISK_COLORS": {"safe": "#36c26b", "aggressive": "#ffb020",
                        "experimental": "#ff5964"},
    },
    "light": {
        "BG": "#f4f4f6", "PANEL": "#ffffff", "PANEL_HI": "#ececf0",
        "FG": "#1a1a1f", "FG_MUTED": "#5f5f6b", "BORDER": "#d6d6de",
        "RISK_COLORS": {"safe": "#1f9d57", "aggressive": "#c97a00",
                        "experimental": "#d11425"},
    },
}

# Active palette mirrored to module globals (defaults to dark).
MODE = "dark"
BG = PALETTES["dark"]["BG"]
PANEL = PALETTES["dark"]["PANEL"]
PANEL_HI = PALETTES["dark"]["PANEL_HI"]
FG = PALETTES["dark"]["FG"]
FG_MUTED = PALETTES["dark"]["FG_MUTED"]
BORDER = PALETTES["dark"]["BORDER"]
RISK_COLORS = PALETTES["dark"]["RISK_COLORS"]


def _set_globals(mode: str) -> None:
    global MODE, BG, PANEL, PANEL_HI, FG, FG_MUTED, BORDER, RISK_COLORS
    pal = PALETTES.get(mode, PALETTES["dark"])
    MODE = mode if mode in PALETTES else "dark"
    BG, PANEL, PANEL_HI = pal["BG"], pal["PANEL"], pal["PANEL_HI"]
    FG, FG_MUTED, BORDER = pal["FG"], pal["FG_MUTED"], pal["BORDER"]
    RISK_COLORS = pal["RISK_COLORS"]


def toggle(mode: str) -> str:
    return "light" if mode == "dark" else "dark"


def apply_theme(root: tk.Tk, mode: str = "dark") -> None:
    _set_globals(mode)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG,
                    fieldbackground=PANEL, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=(FONT, 9))
    style.configure("Header.TLabel", background=BG, foreground=FG, font=(FONT, 15, "bold"))
    style.configure("SubHeader.TLabel", background=BG, foreground=ACCENT, font=(FONT, 11, "bold"))

    style.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER,
                    focuscolor=ACCENT, padding=(10, 5), relief="flat")
    style.map("TButton",
              background=[("active", PANEL_HI), ("pressed", PANEL_HI)],
              foreground=[("disabled", FG_MUTED)])

    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                    padding=(12, 6), relief="flat", font=(FONT, 10, "bold"))
    style.map("Accent.TButton", background=[("active", ACCENT_HI), ("pressed", ACCENT_HI)])

    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=FG_MUTED,
                    padding=(16, 8), font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])

    style.configure("TSeparator", background=BORDER)
    style.configure("TMenubutton", background=PANEL, foreground=FG, padding=(8, 4), relief="flat")
    style.map("TMenubutton", background=[("active", PANEL_HI)])
    style.configure("TEntry", fieldbackground=PANEL, foreground=FG, bordercolor=BORDER)
    style.configure("TScrollbar", background=PANEL, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_MUTED)


def style_listbox(listbox: tk.Listbox) -> None:
    """Apply the active palette to a classic tk.Listbox (not themable via ttk)."""
    listbox.configure(
        bg=PANEL, fg=FG, selectbackground=ACCENT, selectforeground="#ffffff",
        highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        borderwidth=0, activestyle="none", font=(FONT, 10),
    )
