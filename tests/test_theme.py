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
    assert theme.strip(text + "\x1b[48;2;4;5;6m!") == "hi!"


def test_header_is_blank_dim_hints_then_notice_or_blank():
    hints = theme.paint("^a add · esc close", theme.LATTE["overlay0"], dim=True)
    assert theme.header(theme.LATTE, "^a add · esc close").split("\n") == [" ", hints, " "]
    assert theme.header(theme.LATTE, "^a add · esc close", "Added").split("\n")[2] == "Added"


@pytest.mark.parametrize("pal", [theme.LATTE, theme.MACCHIATO])
def test_a_title_leads_the_hints_in_text_colour(pal):
    line = theme.header(pal, "esc discards", title="Add ~/api").split("\n")[1]
    assert line == (
        theme.paint("Add ~/api", pal["text"], bold=True)
        + theme.paint(" · esc discards", pal["overlay0"], dim=True)
    )
