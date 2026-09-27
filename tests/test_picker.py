from __future__ import annotations

import json
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
from herdr_projects import cli, flow, picker, theme
from herdr_projects.herdr import Workspace
from herdr_projects.picker import cell_width, visible_width
from herdr_projects.registry import Group, Project, Registry, load
from herdr_projects.theme import LATTE, MACCHIATO, paint, strip

ACTIVE, OPEN, MISSING = "\uf444", "\uf4c3", "\U000f0338"
SHOWN, FOLDED = "\uf47c", "\uf460"
STATUSES = {"gone": "missing", "notes": "active", "work/web": "open"}


def workspace(focused: bool = False) -> Workspace:
    return Workspace(id="w", label="", focused=focused, active_tab_id="t", linked_worktree=False)


def visible(row: str) -> str:
    return strip(row.split("\t")[0])


def ids(rows: list[str]) -> list[str]:
    return [row.rpartition("\t")[2] for row in rows]


def line(left: str, right: str, width: int) -> str:
    return left + " " * (width - cell_width(left) - cell_width(right)) + right


def wide(tmp_path) -> Registry:
    return Registry(
        (Group(name="日本", icon="🚀"),),
        (
            Project(name="a", icon="\uf444", path=str(tmp_path / "a")),
            Project(name="bb", icon=MISSING, path=str(tmp_path)),
            Project(name="c", group="日本", path=str(tmp_path / "日本語/long/path")),
            Project(name="d", icon="👩‍💻", path=str(tmp_path)),
        ),
    )


# rows


def test_cell_width():
    assert cell_width("abc") == 3
    assert cell_width("\uf444") == 1  # nerd-font glyph, private use
    assert cell_width("\U000f0338") == 1  # md-* glyph, supplementary private use
    assert cell_width("🚀") == 2
    assert cell_width("日本") == 4
    assert cell_width("é") == 1
    assert cell_width("⚙️") == 1
    assert cell_width("👩‍💻") == 4
    assert visible_width(paint("日本", LATTE["red"])) == 4


@pytest.mark.parametrize(
    ("text", "width", "left", "clipped"),
    [
        ("abcdef", 6, False, "abcdef"),
        ("abcdef", 4, False, "abc…"),
        ("abcdef", 4, True, "…def"),
        ("日本語", 4, False, "日…"),
        ("日本語", 4, True, "…語"),
        ("abc", 1, True, "…"),
        ("abc", 0, False, ""),
    ],
)
def test_clip(text, width, left, clipped):
    assert picker.clip(text, width, left) == clipped


def test_rows_are_groups_with_their_projects_then_the_ungrouped(root):
    rows = picker.rows(registry_for(root), STATUSES, LATTE, 40)
    assert [visible(row) for row in rows] == [
        line(f"{SHOWN} H  home", "1 project · 0 open", 40),
        line("└ H  web  ~/home-web", "", 40),
        line(f"{SHOWN} W  work", "2 projects · 1 open", 40),
        line("│ W  api  ~/api", "", 40),
        line("└ W  web  ~/web", OPEN, 40),
        line("G  gone   ~/gone", MISSING, 40),
        line("N  notes  ~/notes", ACTIVE, 40),
    ]
    assert ids(rows) == [
        "g:home",
        "p:home/web",
        "g:work",
        "p:work/api",
        "p:work/web",
        "p:gone",
        "p:notes",
    ]


def test_a_folded_group_hides_its_projects(root):
    rows = picker.rows(registry_for(root), STATUSES, LATTE, 40, folded={"work"})
    assert ids(rows) == ["g:home", "p:home/web", "g:work", "p:gone", "p:notes"]
    assert visible(rows[2]) == line(f"{FOLDED} W  work", "2 projects · 1 open", 40)
    # Columns are sized over every project, so folding moves nothing.
    assert visible(rows[3]) == line("G  gone   ~/gone", MISSING, 40)


def test_an_empty_group_is_a_header_alone():
    registry = Registry((Group(name="later"),), (Project(name="p", icon="P", path="/p"),))
    rows = picker.rows(registry, {}, LATTE, 30)
    assert [visible(row) for row in rows] == [
        line(f"{SHOWN} {picker.ICO_GROUP}  later", "0 projects", 30),
        line("P  p  /p", "", 30),
    ]
    assert ids(rows) == ["g:later", "p:p"]


def test_open_counts_active_and_open_projects(tmp_path):
    registry = Registry(
        (Group(name="g", icon="G"),),
        tuple(Project(name=n, group="g", path=str(tmp_path / n)) for n in "abcd"),
    )
    known = {"g/a": "active", "g/b": "open", "g/c": "missing"}
    [head, *_] = picker.rows(registry, known, LATTE, 40)
    assert visible(head).endswith("4 projects · 2 open")


@pytest.mark.parametrize(
    ("width", "tail"),
    [(29, "2 projects · 1 open"), (28, "2 projects"), (20, "2 projects"), (19, "")],
)
def test_a_narrow_header_drops_the_open_count_then_the_project_count(root, width, tail):
    head = picker.rows(registry_for(root), STATUSES, LATTE, width)[2]
    assert visible(head) == line(f"{SHOWN} W  work", tail, width)


def test_a_long_group_name_is_clipped_before_the_counts_go():
    registry = Registry((Group(name="a-long-group-name", icon="G"),), ())
    assert visible(picker.rows(registry, {}, LATTE, 24)[0]) == f"{SHOWN} G  a-long-… 0 projects"


@pytest.mark.parametrize("pal", [LATTE, MACCHIATO])
def test_header_and_spine_colours(root, pal):
    rows = picker.rows(registry_for(root), STATUSES, pal, 60)
    home, work = rows[0], rows[2]
    assert work.startswith(paint(SHOWN, pal["overlay1"]) + " " + paint("W", pal["mauve"]))
    assert paint("work", pal["text"], bold=True) in work
    assert work.endswith(
        paint("2 projects", pal["subtext"])
        + paint(" · ", pal["overlay0"], dim=True)
        + paint("1 open", pal["green"])
        + "\tg:work"
    )
    assert paint("0 open", pal["overlay1"]) in home
    assert rows[3].startswith(paint("\u2502", pal["overlay0"], dim=True) + " ")
    assert rows[4].startswith(paint("\u2514", pal["overlay0"], dim=True) + " ")
    folded = picker.rows(registry_for(root), STATUSES, pal, 60, folded={"work"})[2]
    assert folded.startswith(paint(FOLDED, pal["overlay1"]))
    empty = picker.rows(Registry((Group(name="e"),), ()), {}, pal, 60)[0]
    assert paint(picker.ICO_GROUP, pal["overlay1"]) in empty


@pytest.mark.parametrize("width", [20, 33, 40, 57, 80, 137])
def test_rows_fill_the_width(root, tmp_path, width):
    empty = Registry((Group(name="a-rather-long-empty-group"),), ())
    for registry in (registry_for(root), wide(tmp_path), empty):
        for folded in (set(), {"work", "日本"}):
            rows = picker.rows(registry, STATUSES, LATTE, width, folded)
            assert [visible_width(row.split("\t")[0]) for row in rows] == [width] * len(rows)


def test_rows_align_after_wide_glyphs(tmp_path):
    registry = wide(tmp_path)
    rows = picker.rows(registry, {"bb": "missing"}, LATTE, 200)
    assert ids(rows) == ["g:日本", "p:日本/c", "p:a", "p:bb", "p:d"]
    lines = [visible(row) for row in rows]
    # Icons are 4 cells at most (the ZWJ sequence); labels end 3 cells in (spine and "c").
    path_column = 4 + 2 + 3 + 2
    paths = {f"p:{p.bare_label}": p.path for p in registry.projects}
    for row, text in zip(rows[1:], lines[1:], strict=True):
        assert cell_width(text[: text.index(paths[ids([row])[0]])]) == path_column
    assert lines[0].startswith(f"{SHOWN} 🚀    日本 ")
    assert cell_width(lines[3][:-1]) == 199
    assert lines[3].endswith(MISSING)


def test_a_narrow_row_clips_the_path_from_the_left_then_the_label():
    registry = Registry(
        (),
        (
            Project(name="a-much-longer-name", icon="L", path="/y"),
            Project(name="short", icon="S", path="/x/some/long/way/short"),
        ),
    )

    def at(width):
        return [visible(row) for row in picker.rows(registry, {}, LATTE, width)]

    # Icon, gap, 18-cell label column, gap, the path; then two cells before the status.
    assert at(1 + 2 + 18 + 2 + 8 + 3) == [
        "L  a-much-longer-name  /y         ",
        "S  short               …y/short   ",
    ]
    assert at(1 + 2 + 18 + 2 + 1 + 3)[1] == "S  short               …   "
    assert at(1 + 2 + 10 + 3) == ["L  a-much-lo…   ", "S  short        "]


@pytest.mark.parametrize("pal", [LATTE, MACCHIATO])
@pytest.mark.parametrize(
    ("status", "glyph", "colour", "bold"),
    [
        ("active", ACTIVE, "green", True),
        ("open", OPEN, "blue", False),
        ("missing", MISSING, "red", False),
    ],
)
def test_colour_spans(root, pal, status, glyph, colour, bold):
    registry = Registry((), (Project(name="p", icon="P", path=str(root / "notes")),))
    [row] = picker.rows(registry, {"p": status}, pal, 40)
    assert paint("p", pal["text"], bold=True) in row
    assert paint("~/notes", pal["overlay0"], dim=True) in row
    assert row.endswith(paint(glyph, pal[colour], bold=bold) + "\tp:p")


def test_rows_of_an_empty_registry():
    assert picker.rows(Registry(), {}, LATTE, 80) == []


def test_invalid_row_is_red_and_selects_nothing():
    row = picker.invalid_row("x" * 50, MACCHIATO, 30)
    assert row == paint(f"{picker.ICO_ERROR}  {'x' * 26}…", MACCHIATO["red"]) + "\t"


@pytest.mark.parametrize(("cols", "width"), [(57, 54), (80, 77), (100, 97), (131, 128), (22, 20)])
def test_list_width_is_what_fzf_leaves(monkeypatch, cols, width):
    # Measured against fzf 0.74.4 in tmux: the widest row it shows whole, with and
    # without a scrollbar.
    monkeypatch.delenv("FZF_COLUMNS", raising=False)
    monkeypatch.setenv("COLUMNS", str(cols))
    assert picker.list_width() == width


def test_fzf_columns_wins_when_set(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("FZF_COLUMNS", "120")
    assert picker.list_width() == 117
    monkeypatch.setenv("FZF_COLUMNS", "0")
    assert picker.list_width() == 77


def test_glyphs_are_single_codepoints():
    glyphs = [value for name, value in vars(picker).items() if name.startswith("ICO_")]
    glyphs += [glyph for glyph, _, _ in picker.STATUS_STYLES.values()]
    assert len(glyphs) > 5
    assert all(isinstance(g, str) and len(g) == 1 for g in glyphs)


# header


def test_header_pills_the_main_keys_and_dims_the_rest():
    lines = picker.header(LATTE, True).split("\n")
    pills = [theme.pill(key, label, LATTE) for key, label in picker.PILLS]
    assert lines == [" ", "  ".join(pills), paint(picker.HINTS, LATTE["overlay0"], dim=True), " "]
    assert [strip(p).split()[1:4:2] for p in pills] == [
        ["\u21b5", "open"],
        ["^a", "add"],
        ["^e", "edit"],
    ]


def test_header_fits_a_narrow_popup():
    # A 70% popup of a 100-column terminal, less fzf's two-column header indent.
    for line in picker.header(LATTE, True, "x").split("\n"):
        assert visible_width(line) <= 70 - 2


def test_header_of_an_invalid_registry():
    header = strip(picker.header(LATTE, False))
    assert "^o" in header and "edit projects.toml" in header and "^a" not in header


@pytest.mark.parametrize("pal", [LATTE, MACCHIATO])
def test_notices_are_green_and_problems_red(pal):
    done = picker.header(pal, True, "Deleted x").split("\n")[3]
    assert done == paint("Deleted x", pal["green"])
    failed = picker.header(pal, True, picker.Problem("no server")).split("\n")[3]
    assert failed == paint("no server", pal["red"])


# statuses


def test_statuses_ask_herdr(root, herdr):
    open_workspaces(herdr, (ws("w1", focused=True), root / "notes"), (ws("w2"), root / "web"))
    assert picker.statuses(registry_for(root)) == STATUSES


def test_build_asks_herdr_for_statuses(root, herdr):
    open_workspaces(herdr, (ws("w1", focused=True), root / "notes"))
    rows, valid, _ = picker.build(LATTE, 40)
    assert valid
    assert visible(rows[6]) == line("N  notes  ~/notes", ACTIVE, 40)


def test_build_with_known_statuses_leaves_herdr_alone(root, herdr):
    rows, valid, _ = picker.build(LATTE, 40, {"work/api": "open"})
    assert valid
    assert visible(rows[3]).endswith(OPEN)
    assert herdr.calls() == []


def test_build_without_herdr_still_lists(root, fake_herdr):
    fake_herdr.respond("workspace list", fake_herdr.error("no server"))
    rows, valid, _ = picker.build(LATTE, 40)
    assert valid
    assert len(rows) == 7
    assert not any(ACTIVE in row or OPEN in row for row in rows)
    assert visible(rows[5]).endswith(MISSING)


def test_build_an_invalid_registry_is_one_error_row(root, herdr):
    registry_path().write_text('[[projects]]\nname = "a"\n\n[[projects]]\nname = "b"\n')
    rows, valid, _ = picker.build(LATTE, 80)
    assert not valid
    assert len(rows) == 1
    assert visible(rows[0]).startswith(f"{picker.ICO_ERROR}  projects[0]: missing required")
    assert rows[0].endswith("\t")
    assert herdr.calls() == []


# keys


def test_enter_opens_the_project_and_closes(root, herdr):
    open_workspaces(herdr)
    assert picker.handle("", "p:notes") is None
    real = str((root / "notes").resolve())
    assert changes(herdr) == [
        ["workspace", "create", "--cwd", real, "--label", "N notes", "--focus"]
    ]


def test_enter_focuses_an_open_project(root, herdr):
    open_workspaces(herdr, (ws("w1"), root / "api/src"))
    assert picker.handle("", "p:work/api") is None
    assert changes(herdr) == [["workspace", "focus", "w1"]]


@pytest.mark.parametrize(
    ("label", "notice"),
    [("gone", "No such directory: ~/gone"), ("nope", "No project nope")],
)
def test_enter_that_fails_stays_open_with_the_reason(root, herdr, label, notice):
    open_workspaces(herdr)
    problem = picker.handle("", f"p:{label}")
    assert problem == notice
    assert isinstance(problem, picker.Problem)
    assert changes(herdr) == []


def test_enter_reports_herdrs_error(root, herdr):
    open_workspaces(herdr)
    herdr.respond("workspace create", herdr.error("no server"))
    assert picker.handle("", "p:notes") == "no server"


def test_ctrl_r_renames_the_users_workspace_and_closes(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "api/src")
    assert picker.handle("ctrl-r", "p:notes") is None
    assert changes(herdr) == [["workspace", "rename", "w1", "W work/api"]]
    assert toasts(herdr) == ["Renamed to W work/api"]


def test_ctrl_r_without_a_project_stays_open(root, herdr, monkeypatch):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "unregistered")
    assert picker.handle("ctrl-r", None) == "No project for ~/unregistered"
    assert changes(herdr) == []


def test_ctrl_a_adds_and_ctrl_e_edits_the_selection(root, herdr, monkeypatch):
    monkeypatch.setattr(flow, "add", lambda pal: f"Added in {pal['base']}")
    monkeypatch.setattr(flow, "edit", lambda label, pal: f"Updated {label} in {pal['base']}")
    assert picker.handle("ctrl-a", "p:notes") == f"Added in {LATTE['base']}"
    edited = picker.handle("ctrl-e", "p:notes", pal=MACCHIATO)
    assert edited == f"Updated notes in {MACCHIATO['base']}"


@pytest.mark.parametrize("answer", ["y", "Y"])
def test_ctrl_d_deletes_after_a_yes(root, herdr, monkeypatch, capsys, answer):
    monkeypatch.setattr(picker, "read_key", lambda: answer)
    notice = picker.handle("ctrl-d", "p:work/web")
    assert notice == "Deleted W work/web"
    assert not isinstance(notice, picker.Problem)
    assert capsys.readouterr().out.startswith("Delete W work/web? [y/N] ")
    labels = [p.bare_label for p in load(registry_path()).projects]
    assert labels == ["gone", "notes", "home/web", "work/api"]
    assert changes(herdr) == []


@pytest.mark.parametrize("answer", ["n", "", "\r", "\x1b", "\x03"])
def test_ctrl_d_keeps_the_project_otherwise(root, herdr, monkeypatch, answer):
    before = registry_path().read_text()
    monkeypatch.setattr(picker, "read_key", lambda: answer)
    assert picker.handle("ctrl-d", "p:work/web") == ""
    assert registry_path().read_text() == before


def test_ctrl_d_reports_a_registry_it_cannot_write(root, herdr, monkeypatch):
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    config = registry_path().parent
    config.chmod(0o500)
    try:
        notice = picker.handle("ctrl-d", "p:work/web")
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
    assert isinstance(notice, picker.Problem)


@pytest.mark.parametrize("key", ["", "ctrl-d", "ctrl-e"])
def test_keys_that_need_a_selection_do_nothing_without_one(root, herdr, key):
    assert picker.handle(key, None) == ""
    assert herdr.calls() == []


@pytest.mark.parametrize("key", ["", "ctrl-d", "ctrl-e"])
def test_project_keys_on_a_group_header_do_nothing(root, herdr, monkeypatch, key):
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    monkeypatch.setattr(flow, "edit", lambda label, pal: pytest.fail("edited"))
    before = registry_path().read_text()
    assert picker.handle(key, "g:work") == "Select a project"
    assert registry_path().read_text() == before
    assert herdr.calls() == []


def test_keys_that_need_no_project_work_on_a_group_header(root, herdr, monkeypatch, editor):
    in_context(monkeypatch, "w1:p1")
    one_workspace(herdr, ws("w1", label="old"), root / "api/src")
    monkeypatch.setattr(flow, "add", lambda pal: "Added")
    assert picker.handle("ctrl-a", "g:work") == "Added"
    assert picker.handle("ctrl-o", "g:work") == ""
    assert editor.exists()
    assert picker.handle("ctrl-r", "g:work") is None
    assert changes(herdr) == [["workspace", "rename", "w1", "W work/api"]]


@pytest.mark.parametrize("key", ["", "ctrl-r", "ctrl-a", "ctrl-e", "ctrl-d"])
def test_an_invalid_registry_ignores_all_but_ctrl_o(root, herdr, monkeypatch, key):
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    before = registry_path().read_text()
    assert picker.handle(key, "p:notes", valid=False) == ""
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
    assert "--ansi" in args
    assert args[args.index("--expect") + 1] == "ctrl-r,ctrl-a,ctrl-e,ctrl-d,ctrl-o"
    assert args[args.index("--delimiter") + 1] == "\t"
    assert args[args.index("--with-nth") + 1] == "1"
    assert args[args.index("--header") + 1 : args.index("--header") + 3] == ["notice", "keys"]
    assert (fzf / "input").read_text() == "row a\twork/a\nrow b\twork/b\n"


@pytest.mark.parametrize(("at", "bind"), [(0, None), (1, None), (3, "load:pos(3)")])
def test_choose_starts_on_a_row(fzf, monkeypatch, at, bind):
    monkeypatch.setenv("FZF_OUT", "\\n")
    picker.choose(["a\tp:a", "b\tp:b", "c\tg:c"], "keys", at)
    args = (fzf / "args").read_text().split("\n")
    binds = [args[i + 1] for i, arg in enumerate(args) if arg == "--bind"]
    assert binds == ([bind] if bind else [])


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
def positions() -> list[int]:
    return []


@pytest.fixture
def session(fzf, monkeypatch, positions):
    """Scripted fzf results for `picker.run`; records the rows and header of each call, and
    the row it starts on in `positions`."""
    calls: list[tuple[list[str], str]] = []
    answers: list = []

    def choose(lines, header, at=0):
        calls.append((list(lines), header))
        positions.append(at)
        return answers.pop(0)

    monkeypatch.setattr(picker, "choose", choose)
    return answers, calls


def precomputed(monkeypatch, known: dict[str, str]) -> Path:
    path = Path(os.environ["HERDR_PLUGIN_STATE_DIR"]) / "statuses.json"
    path.write_text(json.dumps(known))
    monkeypatch.setenv(picker.STATUS_ENV, str(path))
    return path


def test_run_starts_from_precomputed_statuses_then_asks_herdr(root, herdr, session, monkeypatch):
    answers, calls = session
    path = precomputed(monkeypatch, {"notes": "open"})
    open_workspaces(herdr)
    monkeypatch.setattr(flow, "add", lambda pal: "Added")
    answers += [("ctrl-a", "p:notes"), None]
    assert picker.run() == 0
    width = picker.list_width()
    assert calls[0] == (
        picker.build(LATTE, width, {"notes": "open"})[0],
        picker.header(LATTE, True),
    )
    assert not path.exists()
    assert calls[1] == (picker.build(LATTE, width)[0], picker.header(LATTE, True, "Added"))
    assert calls[0][0] != calls[1][0]


@pytest.mark.parametrize("known", ["not json", "[]"])
def test_run_asks_herdr_when_the_statuses_are_unreadable(root, herdr, session, monkeypatch, known):
    answers, calls = session
    path = precomputed(monkeypatch, {})
    path.write_text(known)
    open_workspaces(herdr, (ws("w1"), root / "notes"))
    answers += [None]
    assert picker.run() == 0
    assert visible(calls[0][0][6]).endswith(OPEN)
    assert not path.exists()


def test_run_renders_at_the_popups_width(root, herdr, session, monkeypatch):
    answers, calls = session
    open_workspaces(herdr)
    monkeypatch.setenv("COLUMNS", "61")
    answers += [None]
    assert picker.run() == 0
    assert {visible_width(row.split("\t")[0]) for row in calls[0][0]} == {58}


def test_run_uses_the_theme_it_is_given(root, herdr, session, monkeypatch):
    answers, calls = session
    monkeypatch.setenv(theme.ENV, "dark")
    open_workspaces(herdr)
    seen = []
    monkeypatch.setattr(flow, "add", lambda pal: seen.append(pal) or "Added")
    answers += [("ctrl-a", None), None]
    assert picker.run() == 0
    assert seen == [MACCHIATO]
    assert calls[0] == (
        picker.build(MACCHIATO, picker.list_width())[0],
        picker.header(MACCHIATO, True),
    )


def test_run_closes_after_open(root, herdr, session):
    answers, calls = session
    open_workspaces(herdr)
    answers += [("", "p:notes")]
    assert picker.run() == 0
    assert len(calls) == 1
    assert changes(herdr)[0][:2] == ["workspace", "create"]


def test_run_reloads_after_a_delete(root, herdr, session, monkeypatch):
    answers, calls = session
    monkeypatch.setattr(picker, "read_key", lambda: "y")
    open_workspaces(herdr)
    answers += [("ctrl-d", "p:notes"), None]
    assert picker.run() == 0
    assert len(calls[0][0]) == 7
    assert ids(calls[1][0]) == [
        "g:home",
        "p:home/web",
        "g:work",
        "p:work/api",
        "p:work/web",
        "p:gone",
    ]
    assert calls[1][1] == picker.header(LATTE, True, "Deleted N notes")


def test_run_folds_a_group_on_enter_and_stays_on_its_header(
    root, herdr, session, positions, monkeypatch
):
    answers, calls = session
    known = {"work/web": "open"}
    precomputed(monkeypatch, known)
    answers += [("", "g:work"), ("", "g:work"), None]
    assert picker.run() == 0
    width = picker.list_width()
    assert [rows for rows, _ in calls] == [
        picker.build(LATTE, width, known)[0],
        picker.build(LATTE, width, known, {"work"})[0],
        picker.build(LATTE, width, known)[0],
    ]
    assert positions == [0, 3, 3]
    assert {header for _, header in calls} == {picker.header(LATTE, True)}
    # Folding reuses the statuses it has rather than asking herdr again.
    assert herdr.calls() == []


def test_run_keeps_groups_folded_across_other_keys(root, herdr, session, positions):
    answers, calls = session
    open_workspaces(herdr)
    answers += [("", "g:home"), ("ctrl-e", "g:home"), None]
    assert picker.run() == 0
    assert ids(calls[2][0])[:3] == ["g:home", "g:work", "p:work/api"]
    assert calls[2][1] == picker.header(LATTE, True, "Select a project")
    assert positions == [0, 1, 0]


def test_run_shows_a_failure_in_red(root, herdr, session):
    answers, calls = session
    open_workspaces(herdr)
    answers += [("", "p:gone"), None]
    assert picker.run() == 0
    assert calls[1][1].split("\n")[3] == paint("No such directory: ~/gone", LATTE["red"])


def test_run_shows_an_invalid_registry(root, herdr, session):
    answers, calls = session
    registry_path().write_text("nonsense")
    answers += [("", None), None]
    assert picker.run() == 0
    assert len(calls[0][0]) == 1
    assert calls[0][1] == picker.header(LATTE, False)


@pytest.mark.parametrize("how", ["flag", "env"])
def test_run_for_add_starts_in_the_add_flow(root, herdr, session, monkeypatch, how):
    answers, calls = session
    path = precomputed(monkeypatch, {"notes": "open"})
    open_workspaces(herdr)
    if how == "env":
        monkeypatch.setenv(picker.ADD_ENV, "1")
    monkeypatch.setattr(flow, "add", lambda pal: "Added")
    answers += [None]
    assert picker.run(add=how == "flag") == 0
    assert not path.exists()
    rows = picker.build(LATTE, picker.list_width())[0]
    assert calls == [(rows, picker.header(LATTE, True, "Added"))]


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


def test_popup_hands_statuses_and_the_theme_to_the_picker(root, herdr):
    open_workspaces(herdr, (ws("w1"), root / "web"))
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup"]) == 0
    [call] = popup_calls(herdr)
    assert call[call.index("--entrypoint") + 1] == "picker"
    assert call[call.index("--width") + 1] == "70%"
    assert call[call.index("--height") + 1] == "60%"
    env = popup_env(call)
    assert set(env) == {picker.STATUS_ENV, theme.ENV}
    assert env[theme.ENV] == "light"
    path = Path(env[picker.STATUS_ENV])
    assert path.parent == Path(os.environ["HERDR_PLUGIN_STATE_DIR"])
    assert json.loads(path.read_text()) == {"gone": "missing", "work/web": "open"}


def test_popup_resolves_auto_to_the_system_theme(root, herdr, tmp_path, monkeypatch):
    open_workspaces(herdr)
    monkeypatch.setenv(theme.ENV, "auto")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    theme.theme_file().parent.mkdir(parents=True)
    theme.theme_file().write_text("dark\n")
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup"]) == 0
    assert popup_env(popup_calls(herdr)[0])[theme.ENV] == "dark"


def test_popup_for_add(root, herdr):
    open_workspaces(herdr)
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup", "--add"]) == 0
    assert popup_env(popup_calls(herdr)[0])[picker.ADD_ENV] == "1"


def test_popup_leaves_an_invalid_registry_to_the_picker(root, herdr):
    registry_path().write_text("nonsense")
    herdr.respond("plugin pane open", herdr.ok())
    assert cli.main(["popup"]) == 0
    assert popup_env(popup_calls(herdr)[0]) == {theme.ENV: "light"}


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
