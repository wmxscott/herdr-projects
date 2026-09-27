from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import run_plugin
from herdr_projects import VERSION, cli

EVENT_JSON = json.dumps({"data": {"workspace": {"workspace_id": "w-1"}}})


def test_version(env, capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out == f"herdr-projects {VERSION}\n"


def test_help_names_every_command(env, capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    for command in ("list", "open", "rename", "add", "picker", "popup", "event"):
        assert command in out


@pytest.mark.parametrize("argv", [["picker"], ["picker", "--add"], ["popup"], ["popup", "--add"]])
def test_unimplemented_commands_exit_2(env, capsys, argv):
    assert cli.main(argv) == 2
    assert capsys.readouterr().err == f"herdr-projects: {argv[0]}: not implemented\n"


@pytest.mark.parametrize(
    "argv", [[], ["bogus"], ["open"], ["open", "a", "b"], ["list", "--bogus"], ["event", "x"]]
)
def test_usage_errors_exit_2(env, capsys, argv):
    assert cli.main(argv) == 2
    assert "usage: herdr-projects" in capsys.readouterr().err


def test_shim_runs_the_cli(env, fake_herdr, tmp_path):
    result = run_plugin(env, "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"herdr-projects {VERSION}\n"

    result = run_plugin(env, "event", HERDR_PLUGIN_EVENT_JSON=EVENT_JSON)
    assert result.returncode == 0, result.stderr
    assert (Path(env["HERDR_PLUGIN_STATE_DIR"]) / "hook.log").exists()

    result = run_plugin(env, "list", HERDR_PLUGIN_CONFIG_DIR=str(tmp_path / "config"))
    assert result.returncode == 0, result.stderr
    assert fake_herdr.calls()[0] == ["workspace", "get", "w-1"]


def test_shim_caches_the_interpreter(env, tmp_path):
    cache = Path(env["HERDR_PLUGIN_STATE_DIR"]) / "python"
    result = run_plugin(env, "--version")
    assert result.returncode == 0, result.stderr
    cached = cache.read_text().strip()
    assert Path(cached).is_absolute()
    assert os.access(cached, os.X_OK)

    marker = tmp_path / "used-cache"
    wrapper = tmp_path / "python-wrapper"
    wrapper.write_text(f'#!/bin/sh\ntouch {marker}\nexec {cached} "$@"\n')
    wrapper.chmod(0o755)
    cache.write_text(f"{wrapper}\n")
    result = run_plugin(env, "--version")
    assert result.stdout == f"herdr-projects {VERSION}\n"
    assert marker.exists()


def test_shim_ignores_a_stale_cache(env, tmp_path):
    cache = Path(env["HERDR_PLUGIN_STATE_DIR"]) / "python"
    cache.write_text(f"{tmp_path / 'gone'}\n")
    result = run_plugin(env, "--version")
    assert result.stdout == f"herdr-projects {VERSION}\n"
    assert cache.read_text().strip() != str(tmp_path / "gone")
