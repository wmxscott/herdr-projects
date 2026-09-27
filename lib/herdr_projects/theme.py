"""The picker's look, copied from pr-tracker: Catppuccin Latte or Macchiato, a dim hint line.

Hue is for status only; chrome draws from the neutral ramp.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ENV = "HERDR_PROJECTS_THEME"

RGB = tuple[int, int, int]
Palette = dict[str, RGB]

LATTE: Palette = {
    "base": (239, 241, 245),
    "surface": (204, 208, 218),  # surface0
    "surface1": (188, 192, 204),
    "surface2": (172, 176, 190),
    "overlay0": (156, 160, 176),
    "overlay1": (140, 143, 161),
    "subtext": (108, 111, 133),  # subtext0
    "text": (76, 79, 105),
    "green": (64, 160, 43),
    "red": (210, 15, 57),
    "yellow": (223, 142, 29),
    "peach": (254, 100, 11),
    "mauve": (136, 57, 239),
    "blue": (30, 102, 245),
}
MACCHIATO: Palette = {
    "base": (36, 39, 58),
    "surface": (54, 58, 79),
    "surface1": (73, 77, 100),
    "surface2": (91, 96, 120),
    "overlay0": (110, 115, 141),
    "overlay1": (128, 135, 162),
    "subtext": (165, 173, 203),
    "text": (202, 211, 245),
    "green": (166, 218, 149),
    "red": (237, 135, 150),
    "yellow": (238, 212, 159),
    "peach": (245, 169, 127),
    "mauve": (198, 160, 246),
    "blue": (138, 173, 244),
}

RESET = "\x1b[0m"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def sgr(rgb: RGB, bold: bool = False, dim: bool = False) -> str:
    attrs = ["1"] if bold else []
    if dim:
        attrs.append("2")
    attrs.append(f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}")
    return f"\x1b[{';'.join(attrs)}m"


def paint(text: str, rgb: RGB, bold: bool = False, dim: bool = False) -> str:
    return f"{sgr(rgb, bold, dim)}{text}{RESET}"


def strip(text: str) -> str:
    return ANSI_RE.sub("", text)


def _base(env: Mapping[str, str], var: str, fallback: Path) -> Path:
    value = env.get(var, "")
    return Path(value) if value.startswith("/") else fallback


def theme_file(env: Mapping[str, str] = os.environ) -> Path:
    """The file theme-monitor keeps the system appearance in."""
    home = _base(env, "HOME", Path.home())
    return _base(env, "XDG_DATA_HOME", home / ".local/share") / "theme-monitor/theme-change.trigger"


def system_appearance(env: Mapping[str, str] = os.environ) -> str:
    """'light' or 'dark', from theme-monitor's file if it is running, else macOS itself."""
    try:
        value = theme_file(env).read_text().strip()
        if value in ("light", "dark"):
            return value
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return "dark" if result.stdout.strip() == "Dark" else "light"
        except (OSError, subprocess.SubprocessError):
            pass
    return "light"


def resolve(env: Mapping[str, str] = os.environ) -> str:
    """$HERDR_PROJECTS_THEME if it is light or dark, else the system appearance."""
    choice = (env.get(ENV) or "auto").lower()
    return choice if choice in ("light", "dark") else system_appearance(env)


def palette(theme: str) -> Palette:
    return MACCHIATO if theme == "dark" else LATTE


def header(pal: Palette, hints: str, notice: str = "", title: str = "") -> str:
    """A blank row, the dim hints after the title if there is one, then the notice or another
    blank row."""
    line = paint(f" · {hints}" if title else hints, pal["overlay0"], dim=True)
    if title:
        line = paint(title, pal["text"], bold=True) + line
    return "\n".join([" ", line, notice or " "])
