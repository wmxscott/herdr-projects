from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from herdr_projects.registry import Group, Project, Registry, save  # noqa: E402


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A from-scratch plugin environment, applied to this process and returned for children."""
    for name in list(os.environ):
        if name.startswith(("HERDR_", "XDG_")):
            monkeypatch.delenv(name)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    values = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join([str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
        "HERDR_PLUGIN_ID": "herdr-projects",
        "HERDR_PLUGIN_ROOT": str(ROOT),
        "HERDR_PLUGIN_STATE_DIR": str(state_dir),
        "HERDR_PROJECTS_THEME": "light",
    }
    for name, value in values.items():
        if name != "PATH":
            monkeypatch.setenv(name, value)
    return values


FAKE_HERDR = ROOT / "tests" / "fake_herdr"


class FakeHerdr:
    """Drives tests/fake_herdr/herdr: set its answers, then read back its calls."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.responses: dict[str, list[dict]] = {}

    def respond(self, prefix: str, *answers: dict) -> None:
        self.responses[prefix] = list(answers)
        (self.dir / "responses.json").write_text(json.dumps(self.responses))

    def calls(self) -> list[list[str]]:
        log = self.dir / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    @staticmethod
    def ok(result: object = None) -> dict:
        body = {"type": "ok"} if result is None else result
        return {"stdout": json.dumps({"id": "cli:fake", "result": body}) + "\n"}

    @staticmethod
    def fixture(name: str) -> dict:
        return {"stdout": (FAKE_HERDR / "fixtures" / f"{name}.json").read_text(encoding="utf-8")}

    @staticmethod
    def error(message: str, code: str = "fake_error", stream: str = "stderr") -> dict:
        body = {"id": "cli:fake", "error": {"code": code, "message": message}}
        return {stream: json.dumps(body) + "\n", "exit": 1}


@pytest.fixture
def fake_herdr(env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeHerdr:
    """Puts the fake first on PATH, here and in `env` for child processes."""
    directory = tmp_path / "fake-herdr"
    directory.mkdir()
    values = {
        "FAKE_HERDR_DIR": str(directory),
        # Should anything still find the real herdr, it has no server to reach.
        "HERDR_SOCKET_PATH": str(tmp_path / "no-herdr.sock"),
    }
    env.update(values, PATH=os.pathsep.join([str(FAKE_HERDR), env["PATH"]]))
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", os.pathsep.join([str(FAKE_HERDR), os.environ["PATH"]]))
    return FakeHerdr(directory)


def run_plugin(env: dict[str, str], *args: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(ROOT / "bin/herdr-projects"), *args],
        cwd=ROOT,
        env={**env, **extra},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )


@pytest.fixture
def root(env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Project dirs under $HOME, and a registry at $HERDR_PLUGIN_CONFIG_DIR naming them."""
    home = Path(env["HOME"])
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(home / ".config/projects"))
    for name in ("api/src", "web", "home-web", "notes", "unregistered/deep"):
        (home / name).mkdir(parents=True)
    save(registry_for(home), registry_path())
    return home


def registry_for(home: Path) -> Registry:
    return Registry(
        (Group(name="work", icon="W"), Group(name="home", icon="H")),
        (
            Project(name="api", group="work", path=str(home / "api")),
            Project(name="web", group="work", path=str(home / "web")),
            Project(name="web", group="home", path=str(home / "home-web")),
            Project(name="notes", icon="N", path=str(home / "notes")),
            Project(name="gone", icon="G", path=str(home / "gone")),
        ),
    )


def with_empty_group(home: Path, icon: str | None = "E") -> None:
    """The root registry, plus a group `empty`."""
    registry = registry_for(home)
    groups = (*registry.groups, Group(name="empty", icon=icon))
    save(Registry(groups, registry.projects), registry_path())


def git(*args: str) -> None:
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    subprocess.run(
        ["git", *identity, "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )


def bare_layout(path: Path) -> Path:
    """A `.bare` layout at path: a non-git container of a bare repo and its worktree `main`."""
    source = path.parent / f"{path.name}-source"
    git("init", "-q", "-b", "main", str(source))
    git("-C", str(source), "commit", "-q", "--allow-empty", "-m", "init")
    git("clone", "-q", "--bare", str(source), str(path / ".bare"))
    (path / ".git").write_text("gitdir: ./.bare\n")
    git("-C", str(path), "worktree", "add", "-q", str(path / "main"), "main")
    return path


def registry_path() -> Path:
    return Path(os.environ["HERDR_PLUGIN_CONFIG_DIR"]) / "projects.toml"


def ws(
    workspace_id: str,
    label: str = "",
    focused: bool = False,
    linked: bool | None = None,
    **worktree: Path | str,
):
    """A workspace record; `worktree` adds herdr's `checkout_path`/`repo_root`."""
    record = {
        "workspace_id": workspace_id,
        "label": label,
        "focused": focused,
        "active_tab_id": f"{workspace_id}:t1",
    }
    if linked is not None:
        record["worktree"] = {"is_linked_worktree": linked}
        record["worktree"].update((k, str(v)) for k, v in worktree.items())
    return record


def pn(workspace_id: str, cwd: Path | str | None) -> dict:
    return {
        "pane_id": f"{workspace_id}:p1",
        "tab_id": f"{workspace_id}:t1",
        "workspace_id": workspace_id,
        "cwd": None if cwd is None else str(cwd),
    }


@pytest.fixture
def herdr(fake_herdr):
    """The fake, answering toasts and the commands that change herdr."""
    for command in ("notification show", "workspace focus", "workspace rename"):
        fake_herdr.respond(command, fake_herdr.ok())
    fake_herdr.respond("workspace create", fake_herdr.ok({"workspace": ws("wNew", focused=True)}))
    return fake_herdr


def open_workspaces(fake, *entries: tuple[dict, Path | str | None]) -> None:
    fake.respond("workspace list", fake.ok({"workspaces": [w for w, _ in entries]}))
    fake.respond(
        "pane list", fake.ok({"panes": [pn(w["workspace_id"], cwd) for w, cwd in entries]})
    )


def one_workspace(fake, record: dict, cwd: Path | str | None) -> None:
    """`workspace get` and its pane, found through the plugin context or `--workspace`."""
    workspace_id = record["workspace_id"]
    fake.respond(f"workspace get {workspace_id}", fake.ok({"workspace": record}))
    fake.respond(
        f"pane list --workspace {workspace_id}", fake.ok({"panes": [pn(workspace_id, cwd)]})
    )
    fake.respond(f"pane get {workspace_id}:p1", fake.ok({"pane": pn(workspace_id, cwd)}))
    fake.respond("pane current", fake.ok({"pane": pn(workspace_id, cwd)}))


def in_context(monkeypatch, pane_id: str) -> None:
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps({"focused_pane_id": pane_id}))


def toasts(fake) -> list[str]:
    return [call[4] for call in fake.calls() if call[:2] == ["notification", "show"]]


def changes(fake) -> list[list[str]]:
    kinds = (["workspace", "focus"], ["workspace", "create"], ["workspace", "rename"])
    return [call for call in fake.calls() if call[:2] in kinds]
