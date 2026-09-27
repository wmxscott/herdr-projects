"""The herdr CLI as typed calls. The only module that runs `herdr`."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from herdr_projects import PLUGIN_ID

TIMEOUT = 5


class HerdrError(Exception):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class PopupBusy(HerdrError):
    """herdr shows one popup at a time; the caller may retry once it closes."""


@dataclass(frozen=True)
class Workspace:
    id: str
    label: str
    focused: bool
    active_tab_id: str
    # herdr's `worktree.is_linked_worktree`; None when it reports no git checkout.
    linked_worktree: bool | None
    # herdr's `worktree.checkout_path` and `worktree.repo_root` (the repo's main checkout).
    checkout_path: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True)
class Pane:
    id: str
    workspace_id: str
    tab_id: str
    cwd: str | None


@dataclass(frozen=True)
class Event:
    name: str
    workspace_id: str | None


def run(*args: str) -> dict:
    """Run one herdr command and return its `result` object."""
    command = [os.environ.get("HERDR_BIN_PATH") or "herdr", *args]
    name = "herdr " + " ".join(args[:2])
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise HerdrError(f"{name} timed out") from None
    except OSError as err:
        raise HerdrError(f"can't run herdr: {err.strerror}") from None
    for stream in (done.stdout, done.stderr):
        error = _json(stream).get("error")
        if isinstance(error, dict):
            raise HerdrError(str(error.get("message") or error), error.get("code"))
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip()
        raise HerdrError(message or f"{name} exited with status {done.returncode}")
    result = _json(done.stdout).get("result")
    if not isinstance(result, dict):
        raise HerdrError(f"unexpected output from {name}")
    return result


def _json(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _record(result: dict, key: str) -> dict:
    record = result.get(key)
    if not isinstance(record, dict):
        raise HerdrError(f"unexpected output from herdr: no {key}")
    return record


def _workspace(record: dict) -> Workspace:
    worktree = record.get("worktree")
    fields = worktree if isinstance(worktree, dict) else {}
    try:
        return Workspace(
            id=record["workspace_id"],
            label=record.get("label", ""),
            focused=bool(record.get("focused")),
            active_tab_id=record["active_tab_id"],
            linked_worktree=bool(fields.get("is_linked_worktree"))
            if isinstance(worktree, dict)
            else None,
            checkout_path=_text(fields.get("checkout_path")),
            repo_root=_text(fields.get("repo_root")),
        )
    except (AttributeError, KeyError, TypeError):
        raise HerdrError("unexpected output from herdr: bad workspace record") from None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _pane(record: dict) -> Pane:
    try:
        return Pane(
            id=record["pane_id"],
            workspace_id=record["workspace_id"],
            tab_id=record["tab_id"],
            # The shell's directory, which stays put while a tool it runs moves around.
            cwd=record.get("cwd") or record.get("foreground_cwd"),
        )
    except (AttributeError, KeyError, TypeError):
        raise HerdrError("unexpected output from herdr: bad pane record") from None


def _list(result: dict, key: str) -> list[dict]:
    records = result.get(key)
    if not isinstance(records, list):
        raise HerdrError(f"unexpected output from herdr: no {key}")
    return records


def workspaces() -> list[Workspace]:
    return [_workspace(r) for r in _list(run("workspace", "list"), "workspaces")]


def workspace(workspace_id: str) -> Workspace:
    return _workspace(_record(run("workspace", "get", workspace_id), "workspace"))


def pane(pane_id: str) -> Pane:
    return _pane(_record(run("pane", "get", pane_id), "pane"))


def panes(workspace_id: str | None = None) -> list[Pane]:
    scope = ("--workspace", workspace_id) if workspace_id else ()
    return [_pane(r) for r in _list(run("pane", "list", *scope), "panes")]


def current_pane() -> Pane:
    """The user's pane: the plugin context's focused pane, else herdr's current pane."""
    pane_id = context().get("focused_pane_id")
    if isinstance(pane_id, str) and pane_id:
        return pane(pane_id)
    return _pane(_record(run("pane", "current"), "pane"))


def active_pane(workspace: Workspace, all_panes: list[Pane] | None = None) -> Pane | None:
    """The focused pane of the workspace's active tab.

    Pass `all_panes` (from `panes()`) to share one listing across workspaces.
    """
    if all_panes is None:
        all_panes = panes(workspace.id)
    in_tab = [p for p in all_panes if p.tab_id == workspace.active_tab_id]
    if len(in_tab) > 1:
        layout = _record(run("pane", "layout", "--pane", in_tab[0].id), "layout")
        focused = layout.get("focused_pane_id")
        in_tab = [p for p in in_tab if p.id == focused] or in_tab
    return in_tab[0] if in_tab else None


def focus(workspace_id: str) -> None:
    run("workspace", "focus", workspace_id)


def create(cwd: str, label: str) -> Workspace:
    result = run("workspace", "create", "--cwd", cwd, "--label", label, "--focus")
    return _workspace(_record(result, "workspace"))


def rename(workspace_id: str, label: str) -> None:
    run("workspace", "rename", workspace_id, label)


def notify(title: str, body: str) -> None:
    run("notification", "show", title, "--body", body)


def open_popup(
    entrypoint: str, width: int | str, height: int | str, env: dict[str, str] | None = None
) -> None:
    args = ["plugin", "pane", "open", "--plugin", os.environ.get("HERDR_PLUGIN_ID") or PLUGIN_ID]
    args += ["--entrypoint", entrypoint, "--placement", "popup"]
    args += ["--width", str(width), "--height", str(height), "--focus"]
    for name, value in (env or {}).items():
        args += ["--env", f"{name}={value}"]
    try:
        run(*args)
    except HerdrError as err:
        if "popup already open" in str(err):
            raise PopupBusy(str(err), err.code) from None
        raise


def context() -> dict:
    return _json(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "")


def event() -> Event | None:
    payload = _json(os.environ.get("HERDR_PLUGIN_EVENT_JSON") or "")
    if not payload:
        return None
    data = payload.get("data")
    data = data if isinstance(data, dict) else {}
    record = data.get("workspace")
    record = record if isinstance(record, dict) else {}
    candidates = (record.get("workspace_id"), record.get("id"), data.get("workspace_id"))
    workspace_id = next((c for c in candidates if isinstance(c, str) and c), None)
    return Event(name=os.environ.get("HERDR_PLUGIN_EVENT", ""), workspace_id=workspace_id)
