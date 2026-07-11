from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLOR_BG = "#f5f0e6"
COLOR_PANEL = "#fffaf0"
COLOR_INK = "#17201a"
COLOR_MUTED = "#5f6b61"
COLOR_BORDER = "#d7cbb8"
COLOR_HEADER = "#18392f"
COLOR_BUTTON = "#1f5f4b"
COLOR_BUTTON_ACTIVE = "#17483a"
COLOR_SAFE = "#0f766e"
COLOR_WARNING = "#b45309"
COLOR_BLOCKED = "#991b1b"

FONT_DISPLAY = ("Aptos Display", 20, "bold")
FONT_TITLE = ("Aptos Display", 13, "bold")
FONT_BODY = ("Aptos", 10)
FONT_SMALL = ("Aptos", 9)
FONT_MONO = ("Cascadia Mono", 9)

BADGE_COLORS = {
    "safe": COLOR_SAFE,
    "warning": COLOR_WARNING,
    "blocked": COLOR_BLOCKED,
}


def configure_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        style.theme_use(style.theme_use())
    style.configure("TCombobox", fieldbackground="#fffdf7", background="#fffdf7")
