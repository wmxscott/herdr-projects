"""Checks herdr-plugin.toml against the rules herdr applies when it links a plugin."""

from __future__ import annotations

import os
import re
import tomllib

import pytest
from conftest import ROOT
from herdr_projects import PLUGIN_ID, VERSION

MANIFEST = tomllib.loads((ROOT / "herdr-plugin.toml").read_text())
PLUGIN_ID_RE = re.compile(r"[A-Za-z0-9:._-]{1,120}")
LOCAL_ID_RE = re.compile(r"[A-Za-z0-9:_-]{1,120}")
SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
PLATFORMS = {"linux", "macos", "windows"}
PLACEMENTS = {"overlay", "popup", "split", "tab", "zoomed"}
# The herdr the plan's herdr facts (S9) were checked against.
OLDEST_SUPPORTED_HERDR = (0, 9, 1)
SHIM = ["sh", "bin/herdr-projects"]


def version_tuple(value):
    match = SEMVER_RE.fullmatch(value)
    assert match, value
    return tuple(int(part) for part in match.groups())


def test_metadata():
    assert PLUGIN_ID_RE.fullmatch(MANIFEST["id"])
    assert MANIFEST["id"] == PLUGIN_ID
    assert MANIFEST["name"].strip()
    assert MANIFEST["description"].strip()
    assert set(MANIFEST["platforms"]) == {"linux", "macos"}


def test_versions_agree():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    [locked] = [p["version"] for p in lock["package"] if p["name"] == PLUGIN_ID]
    assert MANIFEST["version"] == VERSION == pyproject["project"]["version"] == locked
    version_tuple(MANIFEST["version"])
    assert version_tuple(MANIFEST["min_herdr_version"]) == OLDEST_SUPPORTED_HERDR


@pytest.mark.parametrize("kind", ["actions", "panes"])
def test_local_ids_are_valid_and_unique(kind):
    ids = [item["id"] for item in MANIFEST[kind]]
    assert all(LOCAL_ID_RE.fullmatch(i) for i in ids)
    assert len(ids) == len(set(ids))


def test_actions():
    actions = {action["id"]: action["command"] for action in MANIFEST["actions"]}
    assert actions == {
        "open": [*SHIM, "popup"],
        "rename": [*SHIM, "rename"],
        "add": [*SHIM, "popup", "--add"],
    }
    for action in MANIFEST["actions"]:
        assert action["title"].strip()
        assert action["contexts"] == ["workspace"]


def test_panes():
    panes = {pane["id"]: pane for pane in MANIFEST["panes"]}
    assert set(panes) == {"picker"}
    assert panes["picker"]["title"].strip()
    assert panes["picker"]["placement"] == "popup"
    assert panes["picker"]["command"] == [*SHIM, "picker"]


def test_events():
    events = [(event["on"], event["command"]) for event in MANIFEST["events"]]
    assert events == [("workspace.created", [*SHIM, "event"])]


def test_commands_point_at_the_shim():
    for item in MANIFEST["actions"] + MANIFEST["panes"] + MANIFEST["events"]:
        assert item["command"][:2] == SHIM
    assert (ROOT / SHIM[1]).is_file()
    assert os.access(ROOT / SHIM[1], os.X_OK)


def test_no_unknown_manifest_fields():
    top = {"id", "name", "version", "min_herdr_version", "description", "platforms"}
    assert set(MANIFEST) <= top | {"actions", "panes", "events"}
    for action in MANIFEST["actions"]:
        assert set(action) <= {"id", "title", "description", "contexts", "platforms", "command"}
    for pane in MANIFEST["panes"]:
        assert set(pane) <= {
            "id",
            "title",
            "description",
            "platforms",
            "placement",
            "width",
            "height",
            "command",
        }
        assert pane["placement"] in PLACEMENTS
    for event in MANIFEST["events"]:
        assert set(event) <= {"on", "platforms", "command"}
