from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import FAKE_HERDR
from herdr_projects import herdr
from herdr_projects.herdr import Event, HerdrError, Pane, PopupBusy, Workspace


def pane_record(pane_id: str, tab_id: str, cwd: str | None = "/p", **extra) -> dict:
    workspace_id = tab_id.split(":")[0]
    return {"pane_id": pane_id, "tab_id": tab_id, "workspace_id": workspace_id, "cwd": cwd, **extra}


def test_workspaces_keeps_herdr_order_and_worktree_hint(fake_herdr):
    fake_herdr.respond("workspace list", fake_herdr.fixture("workspace-list"))
    workspaces = herdr.workspaces()
    assert [(w.id, w.focused, w.linked_worktree) for w in workspaces] == [
        ("wD", False, False),
        ("wS", False, None),
        ("wV", False, True),
        ("w1F", True, True),
    ]
    assert workspaces[1] == Workspace(
        id="wS",
        label="wmxsct/dotfiles-private",
        focused=False,
        active_tab_id="wS:t1",
        linked_worktree=None,
    )
    assert (workspaces[2].checkout_path, workspaces[2].repo_root) == (
        "/home/me/.herdr/worktrees/app/plan-phase-0",
        "/home/me/Developer/onethingapp/app",
    )
    assert fake_herdr.calls() == [["workspace", "list"]]


def test_workspace(fake_herdr):
    fake_herdr.respond("workspace get wS", fake_herdr.fixture("workspace-get"))
    assert herdr.workspace("wS").active_tab_id == "wS:t1"
    assert fake_herdr.calls() == [["workspace", "get", "wS"]]


def test_pane(fake_herdr):
    fake_herdr.respond("pane get wS:p1", fake_herdr.fixture("pane-get"))
    assert herdr.pane("wS:p1") == Pane(
        id="wS:p1",
        workspace_id="wS",
        tab_id="wS:t1",
        cwd="/home/me/Developer/wmxscott/dotfiles-private",
    )


def test_pane_cwd_falls_back_to_foreground_cwd(fake_herdr):
    record = pane_record("w1:p1", "w1:t1", cwd=None, foreground_cwd="/fg")
    fake_herdr.respond("pane get", fake_herdr.ok({"type": "pane_info", "pane": record}))
    assert herdr.pane("w1:p1").cwd == "/fg"


def test_panes(fake_herdr):
    fake_herdr.respond("pane list", fake_herdr.fixture("pane-list"))
    assert [p.id for p in herdr.panes("wS")] == ["wS:p1", "wS:p3"]
    assert [p.id for p in herdr.panes()] == ["wS:p1", "wS:p3"]
    assert fake_herdr.calls() == [["pane", "list", "--workspace", "wS"], ["pane", "list"]]


def test_current_pane_is_the_contexts_focused_pane(fake_herdr, monkeypatch):
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps({"focused_pane_id": "wS:p1"}))
    fake_herdr.respond("pane get wS:p1", fake_herdr.fixture("pane-get"))
    assert herdr.current_pane().id == "wS:p1"
    assert fake_herdr.calls() == [["pane", "get", "wS:p1"]]


def test_current_pane_outside_a_plugin_asks_herdr(fake_herdr):
    fake_herdr.respond("pane current", fake_herdr.fixture("pane-current"))
    assert herdr.current_pane().id == "w1B:p1"
    assert fake_herdr.calls() == [["pane", "current"]]


WORKSPACE = Workspace(
    id="w1", label="x", focused=False, active_tab_id="w1:t2", linked_worktree=None
)


def test_active_pane_of_a_single_pane_tab_needs_no_layout(fake_herdr):
    panes = [Pane("w1:p1", "w1", "w1:t1", "/a"), Pane("w1:p2", "w1", "w1:t2", "/b")]
    assert herdr.active_pane(WORKSPACE, panes) == panes[1]
    assert fake_herdr.calls() == []


def test_active_pane_of_a_split_tab_is_its_focused_pane(fake_herdr):
    fake_herdr.respond("pane layout --pane wS:p1", fake_herdr.fixture("pane-layout"))
    fake_herdr.respond("pane list --workspace wS", fake_herdr.fixture("pane-list"))
    workspace = Workspace(
        id="wS", label="x", focused=False, active_tab_id="wS:t1", linked_worktree=None
    )
    assert herdr.active_pane(workspace).id == "wS:p3"
    assert fake_herdr.calls() == [
        ["pane", "list", "--workspace", "wS"],
        ["pane", "layout", "--pane", "wS:p1"],
    ]


def test_active_pane_of_an_empty_tab_is_none(fake_herdr):
    assert herdr.active_pane(WORKSPACE, []) is None


def test_focus(fake_herdr):
    fake_herdr.respond("workspace focus", fake_herdr.ok())
    herdr.focus("w1")
    assert fake_herdr.calls() == [["workspace", "focus", "w1"]]


def test_create_focuses_and_returns_the_workspace(fake_herdr):
    fake_herdr.respond("workspace create", fake_herdr.fixture("workspace-create"))
    workspace = herdr.create("/home/me/p q", " wmxsct/dotfiles-private")
    assert workspace.id == "w20"
    assert fake_herdr.calls() == [
        [
            "workspace",
            "create",
            "--cwd",
            "/home/me/p q",
            "--label",
            " wmxsct/dotfiles-private",
            "--focus",
        ]
    ]


def test_rename(fake_herdr):
    fake_herdr.respond("workspace rename", fake_herdr.ok())
    herdr.rename("w1", " work/api")
    assert fake_herdr.calls() == [["workspace", "rename", "w1", " work/api"]]


def test_notify(fake_herdr):
    fake_herdr.respond("notification show", fake_herdr.ok())
    herdr.notify("Projects", "-renamed")
    assert fake_herdr.calls() == [["notification", "show", "Projects", "--body", "-renamed"]]


def test_open_popup(fake_herdr):
    fake_herdr.respond("plugin pane open", fake_herdr.ok())
    herdr.open_popup("picker", "70%", 60, env={"A": "1", "B": "x=y"})
    assert fake_herdr.calls() == [
        [
            "plugin",
            "pane",
            "open",
            "--plugin",
            "herdr-projects",
            "--entrypoint",
            "picker",
            "--placement",
            "popup",
            "--width",
            "70%",
            "--height",
            "60",
            "--focus",
            "--env",
            "A=1",
            "--env",
            "B=x=y",
        ]
    ]


def test_open_popup_while_one_is_open_raises_popup_busy(fake_herdr):
    busy = fake_herdr.error("popup already open", code="plugin_pane_open_failed")
    fake_herdr.respond("plugin pane open", busy, fake_herdr.ok())
    with pytest.raises(PopupBusy, match="popup already open"):
        herdr.open_popup("picker", 10, 10)
    herdr.open_popup("picker", 10, 10)
    assert len(fake_herdr.calls()) == 2


def test_other_popup_failures_are_not_popup_busy(fake_herdr):
    fake_herdr.respond("plugin pane open", fake_herdr.error("no such entrypoint"))
    with pytest.raises(HerdrError) as caught:
        herdr.open_popup("picker", 10, 10)
    assert type(caught.value) is HerdrError


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_error_json_carries_herdrs_message(fake_herdr, stream):
    error = fake_herdr.error("workspace w9 not found", code="workspace_not_found", stream=stream)
    fake_herdr.respond("workspace get", error)
    with pytest.raises(HerdrError) as caught:
        herdr.workspace("w9")
    assert str(caught.value) == "workspace w9 not found"
    assert caught.value.code == "workspace_not_found"


def test_real_error_fixture(fake_herdr):
    fake_herdr.respond("pane get", {**fake_herdr.fixture("error"), "exit": 1})
    with pytest.raises(HerdrError, match=r"^pane nope not found$"):
        herdr.pane("nope")


def test_plain_text_failure(fake_herdr):
    fake_herdr.respond("workspace get", {"stderr": "usage: herdr workspace get <id>\n", "exit": 2})
    with pytest.raises(HerdrError, match=r"^usage: herdr workspace get <id>$"):
        herdr.workspace("w1")


def test_silent_failure(fake_herdr):
    fake_herdr.respond("workspace focus", {"exit": 3})
    with pytest.raises(HerdrError, match="exited with status 3"):
        herdr.focus("w1")


@pytest.mark.parametrize(
    "stdout", ["", "not json", "[]", '{"id": "x"}', '{"result": {"type": "pane_info"}}']
)
def test_unexpected_output(fake_herdr, stdout):
    fake_herdr.respond("pane get", {"stdout": stdout})
    with pytest.raises(HerdrError, match="unexpected output"):
        herdr.pane("w1:p1")


def test_timeout(fake_herdr, monkeypatch):
    monkeypatch.setattr(herdr, "TIMEOUT", 0.2)
    fake_herdr.respond("workspace list", {"sleep": 5})
    with pytest.raises(HerdrError, match="timed out"):
        herdr.workspaces()


def test_herdr_missing(env, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(HerdrError, match="herdr"):
        herdr.workspaces()


def test_herdr_bin_path_wins(fake_herdr, env, monkeypatch):
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))
    monkeypatch.setenv("HERDR_BIN_PATH", str(FAKE_HERDR / "herdr"))
    fake_herdr.respond("workspace focus", fake_herdr.ok())
    herdr.focus("w1")
    assert fake_herdr.calls() == [["workspace", "focus", "w1"]]


def test_context(env, monkeypatch):
    assert herdr.context() == {}
    for bad in ("", "not json", "[1]"):
        monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", bad)
        assert herdr.context() == {}
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", '{"focused_pane_id": "w1:p1"}')
    assert herdr.context() == {"focused_pane_id": "w1:p1"}


def test_event_absent(env, monkeypatch):
    assert herdr.event() is None
    for bad in ("", "not json", "[1]"):
        monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", bad)
        assert herdr.event() is None


REAL_CREATED = {
    "event": "workspace_created",
    "data": {
        "type": "workspace_created",
        "workspace": {
            "workspace_id": "w1D",
            "number": 14,
            "label": "s10-cli-test",
            "focused": False,
            "pane_count": 1,
            "tab_count": 1,
            "active_tab_id": "w1D:t1",
            "agent_status": "unknown",
        },
    },
}


@pytest.mark.parametrize(
    "payload",
    [
        REAL_CREATED,
        {"event": "x", "data": {"workspace": {"id": "w1D"}}},
        {"event": "x", "data": {"workspace_id": "w1D"}},
        {"event": "x", "data": {"workspace": {"workspace_id": "w1D", "id": "no"}}},
    ],
)
def test_event_workspace_id(env, monkeypatch, payload):
    monkeypatch.setenv("HERDR_PLUGIN_EVENT", "workspace.created")
    monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", json.dumps(payload))
    assert herdr.event() == Event(name="workspace.created", workspace_id="w1D")


def test_event_without_a_workspace(env, monkeypatch):
    monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", json.dumps({"event": "x", "data": {}}))
    assert herdr.event() == Event(name="", workspace_id=None)
