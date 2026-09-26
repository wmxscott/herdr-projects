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


@pytest.mark.parametrize(
    "argv",
    [
        ["list"],
        ["open", "work/api"],
        ["open", "api"],
        ["rename"],
        ["rename", "--workspace", "w-1"],
        ["add"],
        ["add", ".", "--name", "api", "--group", "work", "--icon", "x"],
        ["picker"],
        ["picker", "--add"],
        ["popup"],
        ["popup", "--add"],
    ],
)
def test_unimplemented_commands_exit_2(env, capsys, argv):
    assert cli.main(argv) == 2
    assert capsys.readouterr().err == f"herdr-projects: {argv[0]}: not implemented\n"


@pytest.mark.parametrize(
    "argv", [[], ["bogus"], ["open"], ["open", "a", "b"], ["list", "--bogus"], ["event", "x"]]
)
def test_usage_errors_exit_2(env, capsys, argv):
    assert cli.main(argv) == 2
    assert "usage: herdr-projects" in capsys.readouterr().err


def log_records(path: Path) -> list[list[str]]:
    return [line.split("\t") for line in path.read_text().splitlines()]


def test_event_appends_to_the_hook_log(env, monkeypatch):
    state_dir = Path(env["HERDR_PLUGIN_STATE_DIR"])
    monkeypatch.setenv("HERDR_PLUGIN_EVENT", "workspace.created")
    monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", EVENT_JSON)
    assert cli.main(["event"]) == 0
    monkeypatch.setenv("HERDR_PLUGIN_EVENT", "workspace.focused")
    assert cli.main(["event"]) == 0

    records = log_records(state_dir / "hook.log")
    assert [record[1:] for record in records] == [
        ["workspace.created", EVENT_JSON],
        ["workspace.focused", EVENT_JSON],
    ]
    for record in records:
        assert record[0][:4].isdigit()


def test_event_without_herdr_uses_herdrs_default_state_dir(env, monkeypatch, tmp_path):
    monkeypatch.delenv("HERDR_PLUGIN_STATE_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert cli.main(["event"]) == 0
    log = tmp_path / "xdg/herdr/plugins/herdr-projects/hook.log"
    assert log_records(log)[0][1:] == ["", ""]


def test_event_exits_0_when_it_cannot_log(env, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setenv("HERDR_PLUGIN_STATE_DIR", str(blocker))
    assert cli.main(["event"]) == 0


def test_shim_runs_the_cli(env):
    result = run_plugin(env, "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"herdr-projects {VERSION}\n"

    result = run_plugin(
        env, "event", HERDR_PLUGIN_EVENT="workspace.created", HERDR_PLUGIN_EVENT_JSON=EVENT_JSON
    )
    assert result.returncode == 0, result.stderr
    log = Path(env["HERDR_PLUGIN_STATE_DIR"]) / "hook.log"
    assert log_records(log)[0][1:] == ["workspace.created", EVENT_JSON]

    assert run_plugin(env, "list").returncode == 2


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
