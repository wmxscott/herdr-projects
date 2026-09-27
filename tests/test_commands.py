from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from herdr_projects import cli
from herdr_projects.registry import Group, Project, Registry, load, save


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


def registry_path() -> Path:
    return Path(os.environ["HERDR_PLUGIN_CONFIG_DIR"]) / "projects.toml"


def ws(workspace_id: str, label: str = "", focused: bool = False, linked: bool | None = None):
    record = {
        "workspace_id": workspace_id,
        "label": label,
        "focused": focused,
        "active_tab_id": f"{workspace_id}:t1",
    }
    if linked is not None:
        record["worktree"] = {"is_linked_worktree": linked}
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


def outside_herdr(monkeypatch) -> None:
    monkeypatch.delenv("HERDR_PLUGIN_ROOT")


def toasts(fake) -> list[str]:
    return [call[4] for call in fake.calls() if call[:2] == ["notification", "show"]]


def changes(fake) -> list[list[str]]:
    kinds = (["workspace", "focus"], ["workspace", "create"], ["workspace", "rename"])
    return [call for call in fake.calls() if call[:2] in kinds]


# list


def test_list(root, herdr, capsys):
    open_workspaces(
        herdr,
        (ws("wT", linked=True), root / "notes"),
        (ws("w1", focused=True), root / "api/src"),
        (ws("w2"), root / "web"),
        (ws("w3"), root / "api"),
        (ws("w4"), None),
    )
    assert cli.main(["list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "gone\t~/gone\tmissing",
        "notes\t~/notes\t-",
        "home/web\t~/home-web\t-",
        "work/api\t~/api\tactive",
        "work/web\t~/web\topen",
    ]
    assert changes(herdr) == []


def test_list_without_herdr_still_lists(root, fake_herdr, monkeypatch, capsys):
    outside_herdr(monkeypatch)
    fake_herdr.respond("pane list", fake_herdr.error("can't reach the herdr server"))
    assert cli.main(["list"]) == 0
    out, err = capsys.readouterr()
    assert [line.split("\t")[2] for line in out.splitlines()] == ["missing", "-", "-", "-", "-"]
    assert "can't reach the herdr server" in err


def test_list_empty_registry(env, fake_herdr, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(tmp_path / "none"))
    open_workspaces(fake_herdr)
    assert cli.main(["list"]) == 0
    assert capsys.readouterr().out == ""


def test_an_invalid_registry_reports_every_error(root, herdr, capsys):
    registry_path().write_text('[[projects]]\nname = "a"\n\n[[projects]]\nname = "b"\n')
    assert cli.main(["list"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 2
    assert all(
        line.startswith("herdr-projects: ~/") and "projects.toml: " in line for line in lines
    )
    assert "projects[0]: missing required key" in lines[0]
    assert "projects[1]: missing required key" in lines[1]
    assert toasts(herdr) == [lines[0].removeprefix("herdr-projects: ") + " (+1 more)"]


# open


def test_open_focuses_the_open_instance(root, herdr):
    open_workspaces(
        herdr,
        (ws("wT", linked=True), root / "api"),
        (ws("w1"), root / "web"),
        (ws("w2"), root / "api/src"),
        (ws("w3", focused=True), root / "api"),
    )
    assert cli.main(["open", "work/api"]) == 0
    assert changes(herdr) == [["workspace", "focus", "w2"]]
    assert toasts(herdr) == []


def test_open_creates_a_workspace(root, herdr, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(root / "unregistered")
    registry = load(registry_path())
    project = Project(name="linked", icon="L", path=str(link))
    save(Registry(registry.groups, (*registry.projects, project)), registry_path())
    open_workspaces(herdr, (ws("wT", linked=True), link), (ws("w1"), root / "notes"))
    assert cli.main(["open", "linked"]) == 0
    real = str((root / "unregistered").resolve())
    assert changes(herdr) == [
        ["workspace", "create", "--cwd", real, "--label", "L linked", "--focus"]
    ]


def test_open_by_unambiguous_name(root, herdr):
    open_workspaces(herdr)
    assert cli.main(["open", "api"]) == 0
    assert changes(herdr)[0][4:6] == ["--label", "W work/api"]


def test_open_by_exact_bare_label_wins_over_a_name(root, herdr):
    registry = load(registry_path())
    project = Project(name="api", icon="A", path=str(root / "unregistered"))
    save(Registry(registry.groups, (*registry.projects, project)), registry_path())
    open_workspaces(herdr)
    assert cli.main(["open", "api"]) == 0
    assert changes(herdr)[0][4:6] == ["--label", "A api"]


def test_open_an_ambiguous_name(root, herdr, capsys):
    assert cli.main(["open", "web"]) == 1
    message = "web is ambiguous: home/web, work/web"
    assert capsys.readouterr().err == f"herdr-projects: {message}\n"
    assert toasts(herdr) == [message]
    assert changes(herdr) == []


@pytest.mark.parametrize("target", ["nope", "home/api", "W work/api"])
def test_open_an_unknown_project(root, herdr, capsys, target):
    assert cli.main(["open", target]) == 1
    assert capsys.readouterr().err == f"herdr-projects: No project {target}\n"
    assert changes(herdr) == []


def test_open_a_missing_path(root, herdr, capsys):
    open_workspaces(herdr, (ws("w1"), root / "api"))
    assert cli.main(["open", "gone"]) == 1
    assert capsys.readouterr().err == "herdr-projects: No such directory: ~/gone\n"
    assert toasts(herdr) == ["No such directory: ~/gone"]
    assert changes(herdr) == []


def test_open_reports_herdrs_error(root, herdr, capsys):
    open_workspaces(herdr)
    herdr.respond("workspace create", herdr.error("no server"))
    assert cli.main(["open", "notes"]) == 1
    assert capsys.readouterr().err == "herdr-projects: no server\n"
    assert toasts(herdr) == ["no server"]


def test_a_failed_toast_keeps_the_original_error(root, herdr, capsys):
    open_workspaces(herdr)
    herdr.respond("workspace create", herdr.error("no server"))
    herdr.respond("notification show", herdr.error("no toasts either"))
    assert cli.main(["open", "notes"]) == 1
    assert capsys.readouterr().err == "herdr-projects: no server\n"


def test_no_toasts_outside_herdr(root, herdr, monkeypatch, capsys):
    outside_herdr(monkeypatch)
    assert cli.main(["open", "nope"]) == 1
    assert capsys.readouterr().err == "herdr-projects: No project nope\n"
    assert herdr.calls() == []


# rename


def test_rename_the_contexts_pane(root, herdr, monkeypatch, capsys):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "api/src")
    assert cli.main(["rename"]) == 0
    assert changes(herdr) == [["workspace", "rename", "w1", "W work/api"]]
    assert ["pane", "current"] not in herdr.calls()
    assert toasts(herdr) == ["Renamed to W work/api"]
    assert capsys.readouterr().out == "Renamed to W work/api\n"


def test_rename_outside_a_plugin_uses_the_current_pane(root, herdr, monkeypatch, capsys):
    outside_herdr(monkeypatch)
    one_workspace(herdr, ws("w1", label="old"), root / "notes")
    assert cli.main(["rename"]) == 0
    assert ["pane", "current"] in herdr.calls()
    assert changes(herdr) == [["workspace", "rename", "w1", "N notes"]]
    assert toasts(herdr) == []
    assert capsys.readouterr().out == "Renamed to N notes\n"


def test_rename_a_given_workspace(root, herdr):
    one_workspace(herdr, ws("w7", label="old"), root / "web")
    assert cli.main(["rename", "--workspace", "w7"]) == 0
    assert ["pane", "list", "--workspace", "w7"] in herdr.calls()
    assert changes(herdr) == [["workspace", "rename", "w7", "W work/web"]]


def test_rename_when_already_labelled(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="W work/api"), root / "api")
    assert cli.main(["rename"]) == 0
    assert changes(herdr) == []
    assert toasts(herdr) == ["Already W work/api"]


def test_rename_without_a_project(root, herdr, monkeypatch, capsys):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "unregistered/deep")
    assert cli.main(["rename"]) == 1
    assert capsys.readouterr().err == "herdr-projects: No project for ~/unregistered/deep\n"
    assert toasts(herdr) == ["No project for ~/unregistered/deep"]
    assert changes(herdr) == []


def test_rename_never_touches_a_linked_worktree(root, herdr):
    one_workspace(herdr, ws("w1", label="wt", linked=True), root / "api")
    assert cli.main(["rename", "--workspace", "w1"]) == 1
    assert changes(herdr) == []


def test_rename_a_pane_without_a_cwd(root, herdr, capsys):
    one_workspace(herdr, ws("w1", label="old"), None)
    assert cli.main(["rename", "--workspace", "w1"]) == 1
    assert capsys.readouterr().err == "herdr-projects: No working directory for workspace w1\n"


def test_rename_reports_herdrs_error(root, herdr, capsys):
    one_workspace(herdr, ws("w1", label="old"), root / "api")
    herdr.respond("workspace rename", herdr.error("workspace w1 not found"))
    assert cli.main(["rename", "--workspace", "w1"]) == 1
    assert capsys.readouterr().err == "herdr-projects: workspace w1 not found\n"
    assert toasts(herdr) == ["workspace w1 not found"]


# add


def added(root: Path) -> list[Project]:
    return [p for p in load(registry_path()).projects if p not in registry_for(root).projects]


def test_add_a_path_with_flags(root, herdr, capsys):
    path = root / "unregistered"
    assert cli.main(["add", str(path), "--name", "u", "--group", "home", "--icon", "U"]) == 0
    assert added(root) == [Project(name="u", group="home", icon="U", path=str(path))]
    assert 'path = "~/unregistered"' in registry_path().read_text()
    assert capsys.readouterr().out == "Added U home/u\n"
    assert toasts(herdr) == ["Added U home/u"]


def test_add_a_relative_path(root, herdr, monkeypatch):
    monkeypatch.chdir(root / "unregistered")
    assert cli.main(["add", "deep", "--icon", "D"]) == 0
    assert added(root) == [Project(name="deep", icon="D", path=str(root / "unregistered/deep"))]


def test_add_the_current_pane_with_its_groups_icon(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), root / "unregistered/deep")
    assert cli.main(["add", "--group", "work"]) == 0
    path = str(root / "unregistered/deep")
    assert added(root) == [Project(name="deep", group="work", path=path)]
    assert toasts(herdr) == ["Added W work/deep"]


def test_add_creates_the_registry(env, herdr, tmp_path, monkeypatch):
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(tmp_path / "new"))
    assert cli.main(["add", str(tmp_path), "--icon", "T"]) == 0
    assert load(registry_path()).projects == (
        Project(name=tmp_path.name, icon="T", path=str(tmp_path)),
    )


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["{root}/api"], "Already registered as W work/api"),
        (["{link}"], "Already registered as N notes"),
        (["{root}/nowhere", "--icon", "X"], "No such directory: ~/nowhere"),
        (["{root}/unregistered", "--group", "play", "--icon", "X"], 'No group "play"'),
        (["{root}/unregistered"], "No icon: pass --icon, or a --group that has one"),
        (["{root}/unregistered", "--name", "notes", "--icon", "X"], "notes already exists"),
        (["{root}/unregistered", "--group", "work", "--name", "api"], "work/api already exists"),
    ],
)
def test_add_failures(root, herdr, tmp_path, capsys, argv, message):
    (tmp_path / "link").symlink_to(root / "notes")
    before = registry_path().read_text()
    argv = [a.format(root=root, link=tmp_path / "link") for a in argv]
    assert cli.main(["add", *argv]) == 1
    assert capsys.readouterr().err == f"herdr-projects: {message}\n"
    assert toasts(herdr) == [message]
    assert registry_path().read_text() == before


def test_add_refuses_a_linked_worktree(root, herdr, monkeypatch, capsys):
    repo = root / "unregistered"
    git = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "-C", str(repo)]
    git += ["-c", "commit.gpgsign=false"]
    for args in (
        ["init", "-q"],
        ["commit", "-q", "--allow-empty", "-m", "i"],
        ["worktree", "add", "-q", "-b", "b", str(root / "wt")],
    ):
        subprocess.run([*git, *args], check=True, capture_output=True)
    (root / "wt/sub").mkdir()
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), root / "wt/sub")
    before = registry_path().read_text()
    assert cli.main(["add", "--icon", "X"]) == 1
    message = "Linked worktrees can't be projects: ~/wt/sub"
    assert capsys.readouterr().err == f"herdr-projects: {message}\n"
    assert toasts(herdr) == [message]
    assert cli.main(["add", str(repo), "--icon", "X"]) == 0
    assert registry_path().read_text() != before


def test_add_a_pane_without_a_cwd(root, herdr, monkeypatch, capsys):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), None)
    assert cli.main(["add", "--icon", "X"]) == 1
    assert capsys.readouterr().err == "herdr-projects: The current pane has no working directory\n"


def test_add_reports_a_registry_it_cannot_write(root, herdr, capsys):
    config = registry_path().parent
    config.chmod(0o500)
    try:
        assert cli.main(["add", str(root / "unregistered"), "--icon", "U"]) == 1
    finally:
        config.chmod(0o700)
    assert capsys.readouterr().err.startswith("herdr-projects: can't write ~/")


# event


def hook_log() -> list[str]:
    path = Path(os.environ["HERDR_PLUGIN_STATE_DIR"]) / "hook.log"
    return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def created(monkeypatch):
    def fire(workspace_id: str | None = "w5") -> int:
        data = {"workspace": {"workspace_id": workspace_id}} if workspace_id else {}
        monkeypatch.setenv("HERDR_PLUGIN_EVENT", "workspace.created")
        monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", json.dumps({"data": data}))
        return cli.main(["event"])

    return fire


def test_event_renames_the_new_workspace(root, herdr, created, capsys):
    one_workspace(herdr, ws("w5", label="5"), root / "api")
    assert created() == 0
    assert changes(herdr) == [["workspace", "rename", "w5", "W work/api"]]
    assert ["pane", "list", "--workspace", "w5"] in herdr.calls()
    assert toasts(herdr) == []
    assert capsys.readouterr() == ("", "")
    assert hook_log() == []


def test_event_handles_every_creation_even_of_a_reused_id(root, herdr, created):
    one_workspace(herdr, ws("w5", label="5"), root / "api")
    assert created() == 0
    assert created() == 0
    assert len(changes(herdr)) == 2


def test_event_is_silent_without_a_project(root, herdr, created):
    one_workspace(herdr, ws("w5", label="5"), root / "unregistered")
    assert created() == 0
    assert changes(herdr) == []
    assert toasts(herdr) == []
    assert hook_log() == []


def test_event_is_silent_when_already_labelled(root, herdr, created):
    one_workspace(herdr, ws("w5", label="W work/api"), root / "api/src")
    assert created() == 0
    assert changes(herdr) == []
    assert toasts(herdr) == []


def test_event_never_renames_a_linked_worktree(root, herdr, created):
    one_workspace(herdr, ws("w5", label="wt", linked=True), root / "api")
    assert created() == 0
    assert changes(herdr) == []
    assert hook_log() == []


def test_event_logs_herdrs_error_and_exits_0(root, herdr, created, capsys):
    herdr.respond("workspace get w5", herdr.error("workspace w5 not found"))
    assert created() == 0
    assert capsys.readouterr() == ("", "")
    assert toasts(herdr) == []
    [line] = hook_log()
    assert line.split("\t")[1:] == ["w5", "HerdrError: workspace w5 not found"]
    assert line[:4].isdigit()


def test_event_logs_an_invalid_registry_and_exits_0(root, herdr, created):
    registry_path().write_text("[[projects]]\n")
    one_workspace(herdr, ws("w5", label="5"), root / "api")
    assert created() == 0
    assert changes(herdr) == []
    [line] = hook_log()
    assert "missing required key" in line


def test_event_logs_a_payload_without_a_workspace(root, herdr, created):
    assert created(None) == 0
    assert herdr.calls() == []
    [line] = hook_log()
    assert line.split("\t")[1] == "-"
    assert '{"data": {}}' in line


def test_event_exits_0_when_it_cannot_log(root, herdr, created, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setenv("HERDR_PLUGIN_STATE_DIR", str(blocker))
    herdr.respond("workspace get w5", herdr.error("workspace w5 not found"))
    assert created() == 0


def test_event_outside_herdr_logs_to_herdrs_default_state_dir(
    root, herdr, created, monkeypatch, tmp_path
):
    monkeypatch.delenv("HERDR_PLUGIN_STATE_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    herdr.respond("workspace get w5", herdr.error("workspace w5 not found"))
    assert created() == 0
    assert (tmp_path / "xdg/herdr/plugins/herdr-projects/hook.log").exists()
