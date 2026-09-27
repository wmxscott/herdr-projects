from __future__ import annotations

import os

import pytest
from conftest import (
    in_context,
    one_workspace,
    registry_for,
    registry_path,
    with_empty_group,
    ws,
)
from herdr_projects import cli, flow, picker, theme
from herdr_projects.flow import Cancelled
from herdr_projects.registry import Group, Project, Registry, load

GLYPH_ROW = "\U000f024b\tmd-folder"


# icon rows


def icons() -> Registry:
    return Registry(
        (Group(name="work", icon="W"), Group(name="home", icon="H"), Group(name="bare")),
        (
            Project(name="api", group="work", path="/a"),
            Project(name="web", group="work", icon="H", path="/b"),
            Project(name="z", icon="Z", path="/c"),
            Project(name="notes", icon="N", path="/d"),
            Project(name="x", group="bare", icon="W", path="/e"),
        ),
    )


def test_icon_rows_list_each_registry_icon_once_groups_first():
    assert flow.icon_rows(icons()) == [
        "H\tused by home, work/web",
        "W\tused by work, bare/x",
        "N\tused by notes",
        "Z\tused by z",
    ]


def test_icon_rows_offer_the_group_icon_first():
    rows = flow.icon_rows(icons(), fallback="W")
    assert rows[0] == "W\tuse group icon\t"
    assert rows[1:] == flow.icon_rows(icons())


def test_icon_rows_offer_no_icon_first_when_skippable():
    rows = flow.icon_rows(Registry(), skip=True)
    assert rows == [" \tno icon\t"]


@pytest.mark.parametrize(
    ("row", "value"),
    [
        (GLYPH_ROW, "\U000f024b"),
        ("W\tused by work", "W"),
        ("W\tuse group icon\t", None),
        (" \tno icon\t", None),
    ],
)
def test_icon_value(row, value):
    assert flow.icon_value(row) == value


def test_icon_list_is_registry_icons_then_the_glyph_file(monkeypatch):
    seen = []
    monkeypatch.setattr(flow, "fzf", lambda text, *args: seen.append((text, args)) or GLYPH_ROW)
    assert flow.pick_icon(icons(), "head", "Icon: ", fallback="W") == "\U000f024b"
    [(text, args)] = seen
    lines = text.split("\n")
    assert lines[:5] == flow.icon_rows(icons(), fallback="W")
    glyphs = flow.GLYPHS.read_text(encoding="utf-8").splitlines()
    assert glyphs[0].startswith("# nerd-fonts ")
    assert lines[5:] == [*glyphs[1:], ""]
    assert args[args.index("--nth") + 1] == "2"
    assert args[args.index("--delimiter") + 1] == "\t"


def test_icon_picker_starts_on_the_current_icon(monkeypatch):
    seen = []
    monkeypatch.setattr(flow, "fzf", lambda text, *args: seen.append(args) or "Z\tused by z")
    assert flow.pick_icon(icons(), "head", "Icon: ", fallback="W", current="Z") == "Z"
    assert "load:pos(5)" in seen[0]


# group rows and the result


def test_group_rows_then_none_then_new():
    assert flow.group_rows(icons()) == [
        "   bare\t=bare",
        "H  home\t=home",
        "W  work\t=work",
        "   none\t",
        "   + new group\t+",
    ]


def test_updated_adds_a_project_and_a_new_group():
    project = Project(name="n", group="new", path="/n")
    group = Group(name="new", icon="Q")
    result = flow.updated(icons(), project, group=group)
    assert result.group("new") == group
    assert project in result.projects
    assert len(result.projects) == len(icons().projects) + 1


def test_updated_replaces_the_edited_project():
    old = icons().projects[-1]
    project = Project(name="renamed", icon="R", path=old.path)
    result = flow.updated(icons(), project, old)
    assert old not in result.projects
    assert project in result.projects
    assert result.groups == icons().groups


# the flow, with scripted fzf answers


@pytest.fixture
def script(monkeypatch):
    """Answers for `flow.fzf` in order: a string, a callable on the rows, or Cancelled."""
    answers: list = []
    calls: list[dict] = []

    def fzf(text, header, prompt, *args):
        calls.append({"text": text, "header": header, "prompt": prompt, "args": args})
        answer = answers.pop(0)
        if answer is Cancelled:
            raise Cancelled
        return answer(text) if callable(answer) else answer

    monkeypatch.setattr(flow, "fzf", fzf)
    return answers, calls


def row(match: str):
    return lambda text: next(line for line in text.split("\n") if match in line)


@pytest.fixture
def here(root, herdr, monkeypatch):
    """The user's pane is in ~/unregistered."""
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), root / "unregistered")
    return root / "unregistered"


def added(root) -> list[Project]:
    return [p for p in load(registry_path()).projects if p not in registry_for(root).projects]


def test_add_with_a_group_and_its_icon(root, here, script):
    answers, calls = script
    answers += ["", row("=work"), row("use group icon")]
    assert flow.add() == "Added W work/unregistered"
    assert added(root) == [Project(name="unregistered", group="work", path=str(here))]
    assert calls[0]["prompt"] == "Name: "
    assert calls[0]["args"][-2:] == ("--query", "unregistered")
    assert calls[0]["header"] == theme.header(
        theme.LATTE, [theme.pill("Add", "~/unregistered", theme.LATTE)], flow.HINTS
    )
    assert calls[1]["text"].split("\n")[2] == "   none\t"
    assert "load:pos(3)" in calls[1]["args"]


def test_add_with_a_new_group_and_a_searched_icon(root, here, script):
    answers, calls = script
    answers += ["proj", row("new group"), "play", row("\tmd-folder"), row("\toct-zap")]
    assert flow.add() == "Added \u26a1 play/proj"
    registry = load(registry_path())
    assert registry.group("play") == Group(name="play", icon="\U000f024b")
    assert added(root) == [Project(name="proj", group="play", icon="\u26a1", path=str(here))]
    assert calls[3]["text"].startswith(" \tno icon\t\n")
    assert calls[4]["text"].startswith("\U000f024b\tuse group icon\t\n")


def test_a_new_group_may_have_no_icon(root, here, script):
    answers, calls = script
    answers += ["", row("new group"), "play", row("no icon"), row("used by notes")]
    assert flow.add() == "Added N play/unregistered"
    assert load(registry_path()).group("play") == Group(name="play")
    assert "use group icon" not in calls[4]["text"]


def test_a_new_group_that_exists_is_that_group(root, here, script):
    answers, _ = script
    answers += ["", row("new group"), "work", row("use group icon")]
    assert flow.add() == "Added W work/unregistered"
    assert len(load(registry_path()).groups) == 2


@pytest.mark.parametrize("group", ["none", "=home"])
def test_use_group_icon_only_when_the_group_has_one(root, here, script, group):
    answers, calls = script
    answers += ["", row(group), row("used by notes")]
    flow.add()
    assert ("use group icon" in calls[2]["text"]) == (group != "none")


def test_prompts_fall_back_to_the_default_and_repeat_without_one(root, here, script):
    answers, calls = script
    answers += ["  ", row("new group"), "", " ", "play", row("no icon"), row("used by notes")]
    assert flow.add() == "Added N play/unregistered"
    assert [c["prompt"] for c in calls[2:5]] == ["New group: "] * 3


@pytest.mark.parametrize("step", range(5))
def test_esc_at_any_step_discards_everything(root, here, script, step):
    answers, calls = script
    answers += ["proj", row("new group"), "play", row("no icon"), row("used by notes")]
    answers.insert(step, Cancelled)
    before = registry_path().read_text()
    assert flow.add() == ""
    assert registry_path().read_text() == before
    assert len(calls) == min(step + 1, 5)


def test_add_on_a_registered_path_edits_it(root, herdr, monkeypatch, script):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), root / "notes")
    answers, calls = script
    answers += ["", row("=home"), row("used by gone")]
    assert flow.add() == "Updated G home/notes"
    assert theme.pill("Edit", "~/notes", theme.LATTE) in calls[0]["header"]
    assert calls[0]["args"][-2:] == ("--query", "notes")
    assert "load:pos(3)" in calls[1]["args"]
    assert "load:pos(5)" in calls[2]["args"]
    labels = [p.bare_label for p in load(registry_path()).projects]
    assert labels == ["gone", "home/notes", "home/web", "work/api", "work/web"]


def test_edit_renames_and_takes_the_group_icon(root, herdr, script):
    answers, calls = script
    answers += ["api2", row("=work"), row("use group icon")]
    assert flow.edit("work/api") == "Updated W work/api2"
    assert calls[1]["args"][-1] == "load:pos(2)"
    projects = load(registry_path()).projects
    assert Project(name="api2", group="work", path=str(root / "api")) in projects
    assert "work/api" not in [p.bare_label for p in projects]


def test_the_flow_is_drawn_in_the_popups_palette(root, herdr, script):
    answers, calls = script
    answers += [Cancelled]
    assert flow.edit("work/api", theme.MACCHIATO) == ""
    assert theme.pill("Edit", "~/api", theme.MACCHIATO) in calls[0]["header"]


def test_edit_that_changes_nothing_leaves_the_file_alone(root, herdr, script):
    registry_path().write_text(registry_path().read_text() + "# a comment\n")
    before = registry_path().read_text()
    answers, _ = script
    answers += ["", row("=work"), row("use group icon")]
    assert flow.edit("work/web") == ""
    assert registry_path().read_text() == before


def test_a_save_that_fails_validation_is_reported_and_discarded(root, here, script):
    answers, _ = script
    answers += ["api", row("=work"), row("use group icon")]
    before = registry_path().read_text()
    notice = picker.handle("ctrl-a", None)
    assert notice.startswith("projects[")
    assert 'duplicate label "work/api"' in notice
    assert registry_path().read_text() == before


def test_add_refuses_what_the_cli_refuses(root, herdr, monkeypatch, script):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1"), root / "nowhere")
    with pytest.raises(cli.Failure, match="No such directory: ~/nowhere"):
        flow.add()
    assert script[1] == []


# fzf itself


@pytest.fixture
def fzf_bin(tmp_path, monkeypatch):
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


def test_ask_reads_the_query(fzf_bin, monkeypatch):
    monkeypatch.setenv("FZF_OUT", "typed\\n")
    monkeypatch.setenv("FZF_EXIT", "1")
    assert flow.ask("head", "Name: ", "default") == "typed"
    args = (fzf_bin / "args").read_text().split("\n")
    assert {"--print-query", "--disabled", "--ansi"} <= set(args)
    assert (fzf_bin / "input").read_text() == ""


def test_select_returns_the_row(fzf_bin, monkeypatch):
    monkeypatch.setenv("FZF_OUT", "b\\tx\\n")
    assert flow.select(["a\ty", "b\tx"], "head", "> ") == "b\tx"
    args = (fzf_bin / "args").read_text().split("\n")
    assert args[args.index("--bind") + 1] == "enter:accept-non-empty"
    assert (fzf_bin / "input").read_text() == "a\ty\nb\tx\n"


@pytest.mark.parametrize("code", [1, 130])
def test_select_without_a_row_is_cancelled(fzf_bin, monkeypatch, code):
    monkeypatch.setenv("FZF_EXIT", str(code))
    with pytest.raises(Cancelled):
        flow.select(["a"], "head", "> ")


def test_fzf_failing_is_a_failure(fzf_bin, monkeypatch):
    monkeypatch.setenv("FZF_EXIT", "2")
    with pytest.raises(cli.Failure, match="fzf exited with status 2"):
        flow.ask("head", "Name: ")


# group editing


def test_icon_rows_offer_keep_current_before_no_icon():
    rows = flow.icon_rows(icons(), skip=True, keep="W")
    assert rows[:2] == ["W\tkeep current", " \tno icon\t"]
    assert flow.icon_value(rows[0]) == "W"
    assert rows[2:] == flow.icon_rows(icons())


def test_regrouped_renames_the_group_and_its_members():
    result = flow.regrouped(icons(), icons().group("work"), Group(name="job", icon="J"))
    assert result.groups == (Group(name="bare"), Group(name="home", icon="H"), result.group("job"))
    assert result.group("job") == Group(name="job", icon="J")
    labels = [p.bare_label for p in result.projects]
    assert labels == ["notes", "z", "bare/x", "job/api", "job/web"]


def test_edit_group_renames_it_and_its_projects(root, herdr, script):
    answers, calls = script
    answers += ["job", row("keep current")]
    assert flow.edit_group("work") == "Updated W job"
    registry = load(registry_path())
    assert registry.group("work") is None
    assert registry.group("job") == Group(name="job", icon="W")
    labels = [p.bare_label for p in registry.projects]
    assert labels == ["gone", "notes", "home/web", "job/api", "job/web"]
    assert [c["prompt"] for c in calls] == ["Name: ", "Icon: "]
    assert calls[0]["args"][-2:] == ("--query", "work")
    assert calls[0]["header"] == theme.header(
        theme.LATTE, [theme.pill("Edit group", "work", theme.LATTE)], flow.HINTS
    )


def test_edit_group_starts_on_keep_current(root, herdr, script):
    answers, calls = script
    answers += ["", row("keep current")]
    flow.edit_group("work")
    assert calls[1]["text"].startswith("W\tkeep current\n \tno icon\t\n")
    assert not [arg for arg in calls[1]["args"] if arg.startswith("load:pos")]


def test_edit_group_without_an_icon_has_nothing_to_keep(root, herdr, script):
    with_empty_group(root, icon=None)
    answers, calls = script
    answers += ["", row("no icon")]
    assert flow.edit_group("empty") == ""
    assert calls[1]["text"].startswith(" \tno icon\t\n")
    assert "keep current" not in calls[1]["text"]


def test_edit_group_that_changes_nothing_leaves_the_file_alone(root, herdr, script):
    registry_path().write_text(registry_path().read_text() + "# a comment\n")
    before = registry_path().read_text()
    answers, _ = script
    answers += ["  ", row("keep current")]
    assert flow.edit_group("work") == ""
    assert registry_path().read_text() == before


def test_edit_group_to_no_icon(root, herdr, script):
    with_empty_group(root)
    answers, _ = script
    answers += ["", row("no icon")]
    assert flow.edit_group("empty") == "Updated empty"
    assert load(registry_path()).group("empty") == Group(name="empty")


def test_edit_group_to_a_new_icon(root, herdr, script):
    answers, _ = script
    answers += ["", row("\toct-zap")]
    assert flow.edit_group("work") == "Updated ⚡ work"
    registry = load(registry_path())
    assert registry.group("work") == Group(name="work", icon="⚡")
    assert registry.label(registry.projects[-1]) == "⚡ work/web"


@pytest.mark.parametrize("step", range(2))
def test_esc_while_editing_a_group_discards_everything(root, herdr, script, step):
    answers, calls = script
    answers += ["job", row("\toct-zap")]
    answers.insert(step, Cancelled)
    before = registry_path().read_text()
    assert flow.edit_group("work") == ""
    assert registry_path().read_text() == before
    assert len(calls) == step + 1


def test_renaming_a_group_to_another_groups_name_is_refused(root, herdr, script):
    answers, _ = script
    answers += ["home", row("keep current")]
    before = registry_path().read_text()
    notice = picker.handle("ctrl-e", "g:work")
    assert isinstance(notice, picker.Problem)
    assert 'duplicate name "home"' in notice
    assert registry_path().read_text() == before


def test_removing_the_icon_its_projects_rely_on_is_refused(root, herdr, script):
    answers, _ = script
    answers += ["", row("no icon")]
    before = registry_path().read_text()
    notice = picker.handle("ctrl-e", "g:work")
    assert isinstance(notice, picker.Problem)
    assert "no icon" in notice
    assert registry_path().read_text() == before


def test_edit_group_that_is_gone(root, herdr, script):
    with pytest.raises(cli.Failure, match='No group "nope"'):
        flow.edit_group("nope")
    assert script[1] == []
