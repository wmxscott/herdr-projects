from __future__ import annotations

import subprocess
import sys

import pytest
from herdr_projects import theme


@pytest.fixture
def appearance(tmp_path, monkeypatch):
    """The theme-monitor file under a scratch XDG_DATA_HOME, and a macOS answer to fall back to."""
    trigger = tmp_path / "data/theme-monitor/theme-change.trigger"
    trigger.parent.mkdir(parents=True)
    answer = {"stdout": ""}

    def defaults(args, **kwargs):
        assert args == ["defaults", "read", "-g", "AppleInterfaceStyle"]
        return subprocess.CompletedProcess(args, 0, answer["stdout"], "")

    monkeypatch.setattr(theme.subprocess, "run", defaults)
    monkeypatch.setattr(sys, "platform", "darwin")
    env = {"HOME": str(tmp_path / "home"), "XDG_DATA_HOME": str(tmp_path / "data")}
    return trigger, answer, env


@pytest.mark.parametrize(
    ("choice", "trigger", "macos", "expected"),
    [
        ("dark", "light", "", "dark"),
        ("LIGHT", "dark", "Dark", "light"),
        ("auto", "dark", "", "dark"),
        (None, "light", "Dark", "light"),
        (None, None, "Dark", "dark"),
        (None, None, "", "light"),
        ("bogus", "sepia", "Dark", "dark"),
    ],
)
def test_theme_precedence(appearance, choice, trigger, macos, expected):
    path, answer, env = appearance
    if choice:
        env[theme.ENV] = choice
    if trigger:
        path.write_text(f"{trigger}\n")
    answer["stdout"] = macos
    assert theme.resolve(env) == expected


def test_light_off_macos(appearance, monkeypatch):
    _, answer, env = appearance
    answer["stdout"] = "Dark"
    monkeypatch.setattr(sys, "platform", "linux")
    assert theme.resolve(env) == "light"


def test_light_when_defaults_fails(appearance, monkeypatch):
    _, _, env = appearance

    def broken(*args, **kwargs):
        raise OSError("no defaults")

    monkeypatch.setattr(theme.subprocess, "run", broken)
    assert theme.resolve(env) == "light"


def test_theme_file_honours_only_an_absolute_xdg_data_home(tmp_path):
    home = {"HOME": str(tmp_path)}
    trigger = "theme-monitor/theme-change.trigger"
    assert theme.theme_file(home) == tmp_path / ".local/share" / trigger
    assert theme.theme_file({**home, "XDG_DATA_HOME": "rel"}) == tmp_path / ".local/share" / trigger
    assert theme.theme_file({**home, "XDG_DATA_HOME": "/x"}) == theme.Path("/x") / trigger


def test_palette():
    assert theme.palette("dark") is theme.MACCHIATO
    assert theme.palette("light") is theme.LATTE
    assert theme.LATTE.keys() == theme.MACCHIATO.keys()


def test_paint_and_strip():
    text = theme.paint("hi", (1, 2, 3), bold=True, dim=True)
    assert text == "\x1b[1;2;38;2;1;2;3mhi\x1b[0m"
    assert theme.strip(text + theme.bg((4, 5, 6)) + "!") == "hi!"


def test_pill_is_key_then_label_between_caps():
    text = theme.pill("^a", "add", theme.LATTE)
    assert theme.strip(text) == f"{theme.PILL_L} ^a {theme.PILL_SEP} add {theme.PILL_R}"
    assert theme.bg(theme.LATTE["surface1"]) in text


def test_header_is_blank_pills_hints_then_notice_or_blank():
    pills = [theme.pill("^a", "add", theme.LATTE), theme.pill("^e", "edit", theme.LATTE)]
    lines = theme.header(theme.LATTE, pills, "esc close").split("\n")
    assert [theme.strip(line) for line in lines] == [
        " ",
        theme.strip("  ".join(pills)),
        "esc close",
        " ",
    ]
    assert lines[2] == theme.paint("esc close", theme.LATTE["overlay0"], dim=True)
    assert theme.header(theme.LATTE, pills, "esc close", "Added").split("\n")[3] == "Added"


def test_glyphs_are_single_codepoints():
    glyphs = [value for name, value in vars(theme).items() if name.startswith("PILL_")]
    assert len(glyphs) == 3
    assert all(len(g) == 1 for g in glyphs)
