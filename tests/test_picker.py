from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import (
    changes,
    in_context,
    one_workspace,
    open_workspaces,
    registry_for,
    registry_path,
    run_plugin,
    toasts,
    ws,
)
from herdr_projects import cli, picker
from herdr_projects.herdr import Workspace
from herdr_projects.picker import cell_width
from herdr_projects.registry import Group, Project, Registry, load

ACTIVE, OPEN, MISSING = "", "", "\U000f0338"


def workspace(focused: bool = False) -> Workspace:
    return Workspace(id="w", label="", focused=focused, active_tab_id="t", linked_worktree=False)


def visible(row: str) -> str:
    return row.split("\t")[0]


# rows


def test_cell_width():
    assert cell_width("abc") == 3
    assert cell_width("") == 1  # nerd-font glyph, private use
    assert cell_width("\U000f0338") == 1  # md-* glyph, supplementary private use
    assert cell_width("🚀") == 2
    assert cell_width("日本") == 4
    assert cell_width("é") == 1
    assert cell_width("⚙️") == 1
    assert cell_width("👩‍💻") == 4


def test_rows_sorted_by_group_then_name_with_every_status(root):
    registry = registry_for(root)
    projects = {p.bare_label: p for p in registry.projects}
    found = {projects["work/api"]: workspace(focused=True), projects["work/web"]: workspace()}
    assert picker.rows(registry, found) == [
        f"G  gone      ~/gone      {MISSING}\tgone",
        "N  notes     ~/notes\tnotes",
        "H  home/web  ~/home-web\thome/web",
        f"W  work/api  ~/api       {ACTIVE}\twork/api",
        f"W  work/web  ~/web       {OPEN}\twork/web",
    ]


def test_missing_wins_over_open(root):
    registry = registry_for(root)
    gone = next(p for p in registry.projects if p.name == "gone")
    assert picker.rows(registry, {gone: workspace(focused=True)})[0].endswith(f"{MISSING}\tgone")


def test_rows_align_after_wide_glyphs(tmp_path):
    registry = Registry(
        (Group(name="日本", icon="🚀"),),
        (
            Project(name="a", icon="", path=str(tmp_path / "a")),
            Project(name="bb", icon=MISSING, path=str(tmp_path)),
            Project(name="c", group="日本", path=str(tmp_path / "long/path")),
            Project(name="d", icon="👩‍💻", path=str(tmp_path)),
        ),
    )
    lines = [visible(row) for row in picker.rows(registry, {})]
    # Icons are 4 cells at most (the ZWJ sequence), labels 6 ("日本/c").
    path_column = 4 + 2 + 6 + 2
    for line, project in zip(lines, registry.projects, strict=True):
        assert cell_width(line[: line.index(project.path)]) == path_column
    status_column = path_column + len(str(tmp_path / "long/path")) + 2
    missing = [line for line in lines if line.endswith(MISSING)]
    assert len(missing) == 2
    assert {cell_width(line[:-1]) for line in missing} == {status_column}


def test_rows_of_an_empty_registry():
    assert picker.rows(Registry(), {}) == []


def test_build_asks_herdr_for_statuses(root, herdr):
    open_workspaces(herdr, (ws("w1", focused=True), root / "notes"))
    rows, valid = picker.build()
    assert valid
    assert rows[1] == f"N  notes     ~/notes     {ACTIVE}\tnotes"


def test_build_without_herdr_still_lists(root, fake_herdr):
    fake_herdr.respond("workspace list", fake_herdr.error("no server"))
    rows, valid = picker.build()
    assert valid
    assert len(rows) == 5
    assert not any(ACTIVE in row or OPEN in row for row in rows)


def test_build_an_invalid_registry_is_one_error_row(root, herdr):
    registry_path().write_text('[[projects]]\nname = "a"\n\n[[projects]]\nname = "b"\n')
    rows, valid = picker.build()
    assert not valid
    assert len(rows) == 1
    assert rows[0].startswith("projects[0]: missing required")
    assert rows[0].endswith("\t")
    assert herdr.calls() == []


# keys


def test_enter_opens_the_project_and_closes(root, herdr):
    open_workspaces(herdr)
    assert picker.handle("", "notes") is None
    real = str((root / "notes").resolve())
    assert changes(herdr) == [
        ["workspace", "create", "--cwd", real, "--label", "N notes", "--focus"]
    ]


def test_enter_focuses_an_open_project(root, herdr):
    open_workspaces(herdr, (ws("w1"), root / "api/src"))
    assert picker.handle("", "work/api") is None
    assert changes(herdr) == [["workspace", "focus", "w1"]]


@pytest.mark.parametrize(
    ("label", "notice"),
    [("gone", "No such directory: ~/gone"), ("nope", "No project nope")],
)
def test_enter_that_fails_stays_open_with_the_reason(root, herdr, label, notice):
    open_workspaces(herdr)
    assert picker.handle("", label) == notice
    assert changes(herdr) == []


def test_enter_reports_herdrs_error(root, herdr):
    open_workspaces(herdr)
    herdr.respond("workspace create", herdr.error("no server"))
    assert picker.handle("", "notes") == "no server"


def test_ctrl_r_renames_the_users_workspace_and_closes(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "api/src")
    assert picker.handle("ctrl-r", "notes") is None
    assert changes(herdr) == [["workspace", "rename", "w1", "W work/api"]]
    assert toasts(herdr) == ["Renamed to W work/api"]


def test_ctrl_r_without_a_project_stays_open(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "unregistered")
    assert picker.handle("ctrl-r", None) == "No project for ~/unregistered"
    assert changes(herdr) == []


@pytest.mark.parametrize(("key", "notice"), [("ctrl-a", "Add"), ("ctrl-e", "Edit")])
def test_add_and_edit_are_not_here_yet(root, herdr, key, notice):
    assert picker.handle(key, "notes") == f"{notice}: coming in A7"
    assert herdr.calls() == []


@pytest.mark.parametrize("answer", ["y", "Y"])
def test_ctrl_d_deletes_after_a_yes(root, herdr, monkeypatch, capsys, answer):
    monkeypatch.setattr(picker, "read_key", lambda: answer)
    assert picker.handle("ctrl-d", "work/web") == "Deleted W work/web"
    assert capsys.readouterr().out.startswith("Delete W work/web? [y/N] ")
    labels = [p.bare_label for p in load(registry_path()).projects]
    assert labels == ["gone", "notes", "home/web", "work/api"]
    assert changes(herdr) == []


@pytest.mark.parametrize("answer", ["n", "", "\r", "\x1b", "\x03"])
def test_ctrl_d_keeps_the_project_otherwise(root, herdr, monkeypatch, answer):
    before = registry_path().read_text()
    monkeypatch.setattr(picker, "read_key", lambda: answer)
    assert picker.handle("ctrl-d", "work/web") == ""
    assert registry_path().read_text() == before


def test_ctrl_d_reports_a_registry_it_cannot_write(root, herdr, monkeypatch):
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    config = registry_path().parent
    config.chmod(0o500)
    try:
        notice = picker.handle("ctrl-d", "work/web")
    finally:
        config.chmod(0o700)
    assert notice.startswith("can't write ~/")


@pytest.fixture
def editor(tmp_path, monkeypatch):
    """An $EDITOR that logs the file it was given and exits with $EDITOR_EXIT."""
    log = tmp_path / "editor.log"
    script = tmp_path / "bin/fake-editor"
    script.parent.mkdir()
    script.write_text(f'#!/bin/sh\necho "$0 $*" >> {log}\nexit ${{EDITOR_EXIT:-0}}\n')
    script.chmod(0o755)
    monkeypatch.setenv("EDITOR", f"{script} --wait")
    return log


def test_ctrl_o_edits_the_registry_and_reloads(root, herdr, editor):
    assert picker.handle("ctrl-o", None) == ""
    assert editor.read_text().split()[1:] == ["--wait", str(registry_path())]


def test_ctrl_o_falls_back_to_vi(root, herdr, editor, monkeypatch, tmp_path):
    monkeypatch.delenv("EDITOR")
    (tmp_path / "bin/fake-editor").rename(tmp_path / "bin/vi")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert picker.handle("ctrl-o", None) == ""
    assert editor.read_text().split() == [str(tmp_path / "bin/vi"), str(registry_path())]


def test_ctrl_o_makes_the_config_directory(env, herdr, editor, tmp_path, monkeypatch):
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(tmp_path / "new/dir"))
    assert picker.handle("ctrl-o", None) == ""
    assert (tmp_path / "new/dir").is_dir()


def test_ctrl_o_reports_an_editor_that_fails(root, herdr, editor, monkeypatch):
    monkeypatch.setenv("EDITOR_EXIT", "3")
    notice = picker.handle("ctrl-o", None)
    assert notice.endswith("fake-editor --wait exited with status 3")


@pytest.mark.parametrize("key", ["", "ctrl-d", "ctrl-e"])
def test_keys_that_need_a_selection_do_nothing_without_one(root, herdr, key):
    assert picker.handle(key, None) == ""
    assert herdr.calls() == []


@pytest.mark.parametrize("key", ["", "ctrl-r", "ctrl-a", "ctrl-e", "ctrl-d"])
def test_an_invalid_registry_ignores_all_but_ctrl_o(root, herdr, monkeypatch, key):
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    before = registry_path().read_text()
    assert picker.handle(key, "notes", valid=False) == ""
    assert herdr.calls() == []
    assert registry_path().read_text() == before


def test_an_invalid_registry_can_still_be_edited(root, herdr, editor):
    assert picker.handle("ctrl-o", None, valid=False) == ""
    assert editor.exists()


# fzf


@pytest.fixture
def fzf(tmp_path, monkeypatch):
    """A fake fzf on PATH: prints $FZF_OUT, exits $FZF_EXIT, and logs its argv and input."""
    directory = tmp_path / "fzf"
    directory.mkdir()
    script = directory / "fzf"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > {directory}/args\n'
        f"cat > {directory}/input\n"
        'printf "%b" "$FZF_OUT"\n'
        "exit ${FZF_EXIT:-0}\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return directory


def test_choose_runs_fzf_with_the_expected_keys(fzf, monkeypatch):
    monkeypatch.setenv("FZF_OUT", "ctrl-d\\nrow b\\twork/b\\n")
    assert picker.choose(["row a\twork/a", "row b\twork/b"], "notice\nkeys") == ("ctrl-d", "work/b")
    args = (fzf / "args").read_text().split("\n")
    assert args[args.index("--expect") + 1] == "ctrl-r,ctrl-a,ctrl-e,ctrl-d,ctrl-o"
    assert args[args.index("--delimiter") + 1] == "\t"
    assert args[args.index("--with-nth") + 1] == "1"
    assert args[args.index("--header") + 1 : args.index("--header") + 3] == ["notice", "keys"]
    assert (fzf / "input").read_text() == "row a\twork/a\nrow b\twork/b\n"


@pytest.mark.parametrize(
    ("out", "code", "picked"),
    [
        ("\\nrow\\twork/a\\n", 0, ("", "work/a")),
        ("ctrl-r\\n", 1, ("ctrl-r", None)),
        ("\\n", 1, ("", None)),
        ("ctrl-o\\nerror\\t\\n", 0, ("ctrl-o", None)),
        ("", 130, None),
    ],
)
def test_choose_reads_the_key_and_the_selection(fzf, monkeypatch, out, code, picked):
    monkeypatch.setenv("FZF_OUT", out)
    monkeypatch.setenv("FZF_EXIT", str(code))
    assert picker.choose(["row\twork/a"], "keys") == picked


def test_choose_fails_when_fzf_does(fzf, monkeypatch):
    monkeypatch.setenv("FZF_EXIT", "2")
    with pytest.raises(cli.Failure, match="fzf exited with status 2"):
        picker.choose([], "keys")


# the popup's loop


@pytest.fixture
def session(fzf, monkeypatch):
    """Scripted fzf results for `picker.run`; records the rows and header of each call."""
    calls: list[tuple[list[str], str]] = []
    answers: list = []

    def choose(lines, header):
        calls.append((list(lines), header))
        return answers.pop(0)

    monkeypatch.setattr(picker, "choose", choose)
    return answers, calls


def precomputed(monkeypatch, rows: list[str]) -> Path:
    path = Path(os.environ["HERDR_PLUGIN_STATE_DIR"]) / "rows.txt"
    path.write_text("".join(f"{row}\n" for row in rows))
    monkeypatch.setenv(picker.ROWS_ENV, str(path))
    return path


def test_run_starts_from_precomputed_rows_then_rebuilds(root, herdr, session, monkeypatch):
    answers, calls = session
    path = precomputed(monkeypatch, ["cached\tnotes"])
    open_workspaces(herdr)
    answers += [("ctrl-a", "notes"), None]
    assert picker.run() == 0
    assert calls[0] == (["cached\tnotes"], picker.HELP)
    assert not path.exists()
    assert calls[1][0] == picker.build()[0]
    assert calls[1][1] == f"Add: coming in A7\n{picker.HELP}"


def test_run_closes_after_open(root, herdr, session):
    answers, calls = session
    open_workspaces(herdr)
    answers += [("", "notes")]
    assert picker.run() == 0
    assert len(calls) == 1
    assert changes(herdr)[0][:2] == ["workspace", "create"]


def test_run_reloads_after_a_delete(root, herdr, session, monkeypatch):
    answers, calls = session
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    open_workspaces(herdr)
    answers += [("ctrl-d", "notes"), None]
    assert picker.run() == 0
    assert len(calls[0][0]) == 5
    assert [row.split("\t")[1] for row in calls[1][0]] == [
        "gone",
        "home/web",
        "work/api",
        "work/web",
    ]
    assert calls[1][1].startswith("Deleted N notes\n")


def test_run_shows_an_invalid_registry(root, herdr, session):
    answers, calls = session
    registry_path().write_text("nonsense")
    answers += [("", None), None]
    assert picker.run() == 0
    assert len(calls[0][0]) == 1
    assert calls[0][1] == picker.INVALID_HELP


@pytest.mark.parametrize("how", ["flag", "env"])
def test_run_for_add_says_it_is_coming(root, herdr, session, monkeypatch, how):
    answers, calls = session
    open_workspaces(herdr)
    if how == "env":
        monkeypatch.setenv(picker.ADD_ENV, "1")
    answers += [None]
    assert picker.run(add=how == "flag") == 0
    assert calls[0][1] == f"Add: coming in A7\n{picker.HELP}"


def test_picker_needs_fzf(root, herdr, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert cli.main(["picker"]) == 1
    assert "the picker needs fzf on PATH" in capsys.readouterr().err


def test_picker_reports_fzf_failing(root, herdr, fzf, monkeypatch, capsys):
    open_workspaces(herdr)
    monkeypatch.setenv("FZF_EXIT", "2")
    assert cli.main(["picker"]) == 1
    assert "fzf exited with status 2" in capsys.readouterr().err


# the popup action


def popup_env(call: list[str]) -> dict[str, str]:
    values = [call[i + 1] for i, arg in enumerate(call) if arg == "--env"]
    return dict(value.split("=", 1) for value in values)


def popup_calls(fake) -> list[list[str]]:
    return [call for call in fake.calls() if call[:3] == ["plugin", "pane", "open"]]


def test_popup_hands_precomputed_rows_to_the_picker(root, herdr):
    open_workspaces(herdr, (ws("w1"), root / "web"))
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup"]) == 0
    [call] = popup_calls(herdr)
    assert call[call.index("--entrypoint") + 1] == "picker"
    assert call[call.index("--width") + 1] == "70%"
    assert call[call.index("--height") + 1] == "60%"
    env = popup_env(call)
    assert set(env) == {picker.ROWS_ENV}
    path = Path(env[picker.ROWS_ENV])
    assert path.parent == Path(os.environ["HERDR_PLUGIN_STATE_DIR"])
    assert path.read_text().splitlines() == picker.build()[0]


def test_popup_for_add(root, herdr):
    open_workspaces(herdr)
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup", "--add"]) == 0
    assert popup_env(popup_calls(herdr)[0])[picker.ADD_ENV] == "1"


def test_popup_leaves_an_invalid_registry_to_the_picker(root, herdr):
    registry_path().write_text("nonsense")
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup"]) == 0
    assert popup_env(popup_calls(herdr)[0]) == {}


def test_popup_retries_while_another_is_open(root, herdr):
    open_workspaces(herdr)
    busy = herdr.error("popup already open", code="plugin_pane_open_failed")
    herdr.respond("plugin pane open", busy, busy, herdr.ok())
    assert cli.main(["popup"]) == 0
    assert len(popup_calls(herdr)) == 3
    assert toasts(herdr) == []


def test_popup_gives_up_eventually(root, herdr, monkeypatch, capsys):
    monkeypatch.setattr(picker, "POPUP_RETRY_SECONDS", 0.3)
    open_workspaces(herdr)
    herdr.respond("plugin pane open", herdr.error("popup already open"))
    assert cli.main(["popup"]) == 1
    message = "Can't open the picker: popup already open"
    assert capsys.readouterr().err == f"herdr-projects: {message}\n"
    assert toasts(herdr) == [message]
    assert len(popup_calls(herdr)) > 1
    assert list(Path(os.environ["HERDR_PLUGIN_STATE_DIR"]).iterdir()) == []


def test_popup_does_not_retry_other_failures(root, herdr):
    open_workspaces(herdr)
    herdr.respond("plugin pane open", herdr.error("no such plugin"))
    assert cli.main(["popup"]) == 1
    assert len(popup_calls(herdr)) == 1
    assert toasts(herdr) == ["Can't open the picker: no such plugin"]


def test_popup_through_the_shim(root, herdr, env):
    open_workspaces(herdr)
    herdr.respond("plugin pane open", herdr.ok())
    config = os.environ["HERDR_PLUGIN_CONFIG_DIR"]
    result = run_plugin(env, "popup", HERDR_PLUGIN_CONFIG_DIR=config)
    assert result.returncode == 0, result.stderr
    assert len(popup_calls(herdr)) == 1
