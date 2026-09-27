"""The picker popup: fzf over the registry, whose keys run the same operations as the CLI.

The `popup` action does the slow work, asking herdr what is open, before it opens the
popup, and hands the statuses over in a file along with the theme. The popup renders the
rows itself, at its own width.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import tty
import unicodedata
from collections.abc import Collection
from pathlib import Path
from shlex import quote

from herdr_projects import flow, herdr, theme
from herdr_projects.cli import (
    Failure,
    fail,
    find,
    find_group,
    load_registry,
    open_project,
    open_projects,
    relabel,
    state_dir,
    status,
    store,
    toast,
)
from herdr_projects.herdr import HerdrError, PopupBusy
from herdr_projects.registry import (
    Group,
    Project,
    Registry,
    RegistryError,
    collapse_home,
    default_path,
    load,
)
from herdr_projects.theme import Palette, paint

WIDTH, HEIGHT = "70%", "60%"
STATUS_ENV = "HERDR_PROJECTS_STATUS"
ADD_ENV = "HERDR_PROJECTS_ADD"
POPUP_RETRY_SECONDS = 3.0
# Measured against fzf 0.74 without a preview or --multi: the pointer, the marker
# column and the scrollbar column.
LIST_CHROME = 3
MIN_WIDTH = 20

ICO_ACTIVE = "\uf111"  # nf-fa-circle
ICO_OPEN = "\uf4aa"  # nf-oct-circle
ICO_MISSING = "\U000f0338"  # nf-md-link_off
ICO_ERROR = "\uf421"  # nf-oct-alert
ICO_ENTER = "\u21b5"  # downwards arrow with corner leftwards
ICO_SHOWN = "\uf47c"  # nf-oct-chevron_down
ICO_FOLDED = "\uf460"  # nf-oct-chevron_right
ICO_GROUP = "\uf413"  # nf-oct-file_directory, for a group without an icon
SPINE = "\u2502"  # box drawings light vertical
SPINE_END = "\u2514"  # box drawings light up and right
ELLIPSIS = "\u2026"
# Glyph, palette colour, bold.
STATUS_STYLES = {
    "active": (ICO_ACTIVE, "green", True),
    "open": (ICO_OPEN, "blue", False),
    "missing": (ICO_MISSING, "red", False),
}
GAP = "  "
INDENT = 2  # a spine glyph and a space
NAME_ROOM = 6  # a header's name keeps this much before the counts go
# A row's fields: what fzf shows before the label, the label, what it shows after, and the
# row's id. fzf matches only the label, which only rows listed while searching fill in;
# the others show everything in the first field. A tab shows as one cell. Ties go to the
# shorter label, not the shorter row, then to the list's order.
SEARCH = (
    *("--delimiter", "\t", "--with-nth", "1..3", "--nth", "2", "--tabstop", "1"),
    *("--tiebreak", "chunk,index"),
)
UNSEARCHED = "\t\t\t"

KEYS = ("ctrl-r", "ctrl-a", "ctrl-e", "ctrl-d", "ctrl-o")
PILLS = ((ICO_ENTER, "open"), ("^a", "add"), ("^e", "edit"))
HINTS = "^r rename · ^d delete · ^o edit file · esc close"
INVALID_PILLS = (("^o", "edit projects.toml"),)
INVALID_HINTS = "esc close"


class Problem(str):
    """A notice that reports a failure."""


def cell_width(text: str) -> int:
    """Terminal cells, counted as wcwidth and fzf count them.

    Nerd-font glyphs are private-use characters, which count as one cell even where a
    font draws them wider; the gap after the icon column absorbs that overhang.
    """
    width = 0
    for char in text:
        if unicodedata.category(char) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def visible_width(text: str) -> int:
    return cell_width(theme.strip(text))


def pad(text: str, width: int) -> str:
    return text + " " * (width - cell_width(text))


def clip(text: str, width: int, left: bool = False) -> str:
    """`text` cut to `width` cells, an ellipsis marking the cut: at the end, or the start."""
    if cell_width(text) <= width:
        return text
    if width < 1:
        return ""
    kept, used = [], 0
    for char in reversed(text) if left else text:
        used += cell_width(char)
        if used > width - 1:
            break
        kept.append(char)
    return ELLIPSIS + "".join(reversed(kept)) if left else "".join(kept) + ELLIPSIS


def justify(left: str, right: str, width: int) -> str:
    """`left`, then `right` ending at cell `width`."""
    return left + " " * max(width - visible_width(left) - visible_width(right), 0) + right


def list_width() -> int:
    """Cells a row may take: the popup's columns less what fzf keeps."""
    try:
        columns = int(os.environ.get("FZF_COLUMNS") or 0)
    except ValueError:
        columns = 0
    columns = columns or shutil.get_terminal_size().columns
    return max(columns - LIST_CHROME, MIN_WIDTH)


def grouped(registry: Registry) -> tuple[dict[str, list[Project]], list[Project]]:
    """Each group's projects, and the ungrouped ones."""
    members = {g.name: [p for p in registry.projects if p.group == g.name] for g in registry.groups}
    return members, [p for p in registry.projects if p.group not in members]


def icon_column(registry: Registry) -> tuple[dict[Project, str], int]:
    """Each project's icon, and the width of the icon column."""
    icons = {p: registry.icon(p) or "" for p in registry.projects}
    group_icons = [g.icon or ICO_GROUP for g in registry.groups]
    return icons, max(map(cell_width, [*icons.values(), *group_icons]), default=0)


def rows(
    registry: Registry,
    statuses: dict[str, str],
    pal: Palette,
    width: int,
    folded: Collection[str] = (),
) -> list[str]:
    """fzf's list without a query: each group's header, then its projects on a spine unless
    folded, then the ungrouped projects. Ids are `g:<group>` or `p:<bare label>`."""
    members, loose = grouped(registry)
    icons, icon_width = icon_column(registry)
    label_end = max(
        [INDENT + cell_width(p.name) for group in members.values() for p in group]
        + [cell_width(p.bare_label) for p in loose],
        default=0,
    )
    columns = (icon_width, label_end)

    def row(project: Project, lead: str = "") -> str:
        state = statuses.get(project.bare_label)
        return project_row(project, icons[project], state, pal, width, columns, lead)

    lines = []
    for group in registry.groups:
        shut = group.name in folded
        lines.append(group_row(group, members[group.name], statuses, pal, width, icon_width, shut))
        if not shut:
            for i, project in enumerate(members[group.name], 1):
                glyph = SPINE_END if i == len(members[group.name]) else SPINE
                lines.append(row(project, paint(glyph, pal["overlay0"], dim=True) + " "))
    return lines + [row(p) for p in loose]


def found_rows(registry: Registry, statuses: dict[str, str], pal: Palette, width: int) -> list[str]:
    """fzf's list while searching: every project in the list's order, labelled `group/name`."""
    members, loose = grouped(registry)
    icons, icon_width = icon_column(registry)
    columns = (icon_width, max((cell_width(p.bare_label) for p in registry.projects), default=0))
    projects = [p for group in members.values() for p in group] + loose
    return [
        project_row(p, icons[p], statuses.get(p.bare_label), pal, width, columns, found=True)
        for p in projects
    ]


def group_row(
    group: Group,
    members: list[Project],
    statuses: dict[str, str],
    pal: Palette,
    width: int,
    icon_width: int,
    folded: bool,
) -> str:
    """A group's header: its name, then `k / N`, k of its N projects open, at the end of
    `width` cells, which give way to the name in a narrow popup."""
    icon = group.icon or ICO_GROUP
    head = paint(ICO_FOLDED if folded else ICO_SHOWN, pal["overlay1"]) + " "
    head += paint(icon, pal["mauve"] if group.icon else pal["overlay1"])
    head += " " * (icon_width - cell_width(icon)) + GAP
    opened = sum(statuses.get(p.bare_label) in ("active", "open") for p in members)
    counts = paint(str(opened), pal["green"] if opened else pal["overlay1"])
    counts += paint(f" / {len(members)}", pal["overlay0"], dim=True)
    for tail in (counts, ""):
        room = width - visible_width(head) - visible_width(tail) - 1
        if room >= min(cell_width(group.name), NAME_ROOM):
            break
    name = paint(clip(group.name, room), pal["text"], bold=True)
    return justify(head + name, tail, width) + UNSEARCHED + "g:" + group.name


def project_row(
    project: Project,
    icon: str,
    state: str | None,
    pal: Palette,
    width: int,
    columns: tuple[int, int],
    lead: str = "",
    found: bool = False,
) -> str:
    """One project's row, after `lead`: its spine under a group's header, where the label is
    just its name. `columns` are the icon width and the cell the label column ends at, counted
    from the row's start. The path gives way first. A `found` row's label is searched."""
    icon_width, label_end = columns
    room = width - icon_width - len(GAP) - len(GAP) - 1
    label_end = min(label_end, room)
    label_width = label_end - visible_width(lead)
    name = clip(project.name if lead else project.bare_label, label_width)
    path = clip(collapse_home(project.path), room - label_end - len(GAP), left=True)
    head, label = lead + pad(icon, icon_width) + GAP, paint(name, pal["text"])
    tail = ""
    if path:
        tail = " " * (label_width - cell_width(name)) + GAP + paint(path, pal["overlay0"], dim=True)
    glyph, colour, bold = STATUS_STYLES.get(state or "", (" ", "text", False))
    row = justify(head + label + tail, paint(glyph, pal[colour], bold=bold), width)
    ident = "p:" + project.bare_label
    if not found:
        return row + UNSEARCHED + ident
    # Spaces either side of the label, which tabs stand in for.
    tail = row[len(head + label) + 1 :]
    return head[:-1] + "\t" + label + "\t" + tail + "\t" + ident


def invalid_row(message: str, pal: Palette, width: int) -> str:
    return paint(f"{ICO_ERROR}  {clip(message, width - 3)}", pal["red"]) + "\t"


def header(pal: Palette, valid: bool, notice: str = "") -> str:
    pills = [theme.pill(key, label, pal) for key, label in (PILLS if valid else INVALID_PILLS)]
    if notice:
        notice = paint(notice, pal["red"] if isinstance(notice, Problem) else pal["green"])
    return theme.header(pal, pills, HINTS if valid else INVALID_HINTS, notice)


def statuses(registry: Registry) -> dict[str, str]:
    """Bare label → status, for projects that have one; none from herdr if it can't say."""
    try:
        found = open_projects(registry)
    except HerdrError:
        found = {}
    return {p.bare_label: s for p in registry.projects if (s := status(p, found))}


def build(
    pal: Palette,
    width: int,
    known: dict[str, str] | None = None,
    folded: Collection[str] = (),
) -> tuple[list[str], list[str], bool, dict[str, str]]:
    """The list's rows, without a query and while searching, whether the registry is valid, and
    the statuses they show. An invalid registry is one row with its first error.

    Statuses are asked for unless `known`.
    """
    try:
        registry = load(default_path())
    except RegistryError as err:
        return [invalid_row(err.messages[0], pal, width)], [], False, {}
    known = statuses(registry) if known is None else known
    found = found_rows(registry, known, pal, width)
    return rows(registry, known, pal, width, folded), found, True, known


def popup(add: bool = False) -> int:
    env = {theme.ENV: theme.resolve()}
    if add:
        env[ADD_ENV] = "1"
    path = None
    # An invalid registry is left for the picker to read and show.
    with contextlib.suppress(RegistryError):
        path = write_statuses(statuses(load(default_path())))
    if path:
        env[STATUS_ENV] = str(path)
    deadline = time.monotonic() + POPUP_RETRY_SECONDS
    try:
        while True:
            try:
                herdr.open_popup("picker", WIDTH, HEIGHT, env)
                return 0
            except PopupBusy:
                if time.monotonic() >= deadline:
                    raise
            time.sleep(0.1)
    except HerdrError as err:
        if path:
            path.unlink(missing_ok=True)
        raise Failure(f"Can't open the picker: {err}") from None


def write_statuses(known: dict[str, str]) -> Path | None:
    directory = state_dir()
    path = directory / f"picker-{os.getpid()}.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known), encoding="utf-8")
    except OSError:
        return None
    return path


def read_statuses() -> dict[str, str] | None:
    """Statuses the popup action found for this popup. The file is single-use."""
    name = os.environ.get(STATUS_ENV)
    if not name:
        return None
    path = Path(name)
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    finally:
        path.unlink(missing_ok=True)
    return known if isinstance(known, dict) else None


def run(add: bool = False) -> int:
    if not shutil.which("fzf"):
        return fail_in_popup("the picker needs fzf on PATH: https://github.com/junegunn/fzf")
    pal = theme.palette(theme.resolve())
    known, notice = read_statuses(), ""
    if add or os.environ.get(ADD_ENV):
        known, notice = None, handle("ctrl-a", None, pal=pal)
    folded: set[str] = set()
    cursor = None
    while True:
        lines, found, valid, known = build(pal, list_width(), known, folded)
        at = flow.position(lines, lambda row: row.rpartition("\t")[2], cursor) if cursor else 0
        try:
            picked = choose(lines, header(pal, valid, notice), at, found)
        except Failure as err:
            return fail_in_popup(str(err))
        if picked is None:
            return 0
        key, selected = picked
        if key == "" and selected and selected.startswith("g:"):
            folded ^= {selected[2:]}
            cursor, notice = selected, ""
            continue
        known, cursor = None, None
        notice = handle(key, selected, valid=valid, pal=pal)
        if notice is None:
            return 0


def choose(
    lines: list[str], header: str, at: int = 0, found: Collection[str] = ()
) -> tuple[str, str | None] | None:
    """Run fzf on `lines`, starting on row `at` (1-based), and on `found` while there is a
    query: None when cancelled, else the key pressed and the selected row's id."""
    listed = "".join(f"{line}\n" for line in lines)
    with tempfile.TemporaryDirectory(prefix="herdr-projects-") as scratch:
        unsearched, searched = Path(scratch) / "lines", Path(scratch) / "found"
        unsearched.write_text(listed, encoding="utf-8")
        searched.write_text("".join(f"{line}\n" for line in found), encoding="utf-8")
        reload = (
            f'test -n "$FZF_QUERY" && cat {quote(str(searched))} || cat {quote(str(unsearched))}'
        )
        args = ["fzf", "--ansi", *SEARCH, "--expect", ",".join(KEYS), "--with-shell", "sh -c"]
        args += ["--header", header, "--prompt", "> ", *flow.LAYOUT]
        args += ["--bind", f"change:reload-sync:{reload}"]
        if at > 1:
            # load comes again after each reload.
            args += ["--bind", f"load:pos({at})+unbind(load)"]
        done = subprocess.run(args, input=listed, stdout=subprocess.PIPE, encoding="utf-8")
    if done.returncode == 130:
        return None
    # 1 is no selection, which --expect keys can still end with.
    if done.returncode not in (0, 1):
        raise Failure(f"fzf exited with status {done.returncode}")
    key, _, selection = done.stdout.partition("\n")
    return key, selection.rstrip("\n").rpartition("\t")[2] or None


def handle(
    key: str, selected: str | None, valid: bool = True, pal: Palette = theme.LATTE
) -> str | None:
    """Carry out a key on the selected row's id: None to close the popup, else a notice to
    show over the reloaded list."""
    try:
        if key == "ctrl-o":
            return edit_registry()
        if not valid:
            return ""
        if key == "ctrl-r":
            toast(relabel(load_registry()))
            return None
        if key == "ctrl-a":
            return flow.add(pal)
        if selected is None:
            return ""
        kind, _, label = selected.partition(":")
        if kind == "g" and key == "ctrl-e":
            return flow.edit_group(label, pal)
        if kind == "g" and key == "ctrl-d":
            return delete_group(load_registry(), label)
        if kind != "p":
            return "Select a project"
        if key == "ctrl-e":
            return flow.edit(label, pal)
        registry = load_registry()
        project = find(registry, label)
        if key == "ctrl-d":
            return delete(registry, project)
        open_project(registry, project)
        return None
    except (Failure, HerdrError) as err:
        return Problem(str(err))


def delete(registry: Registry, project: Project) -> str:
    label = registry.label(project)
    if not confirm(f"Delete {label}?"):
        return ""
    store(Registry(registry.groups, tuple(p for p in registry.projects if p != project)))
    return f"Deleted {label}"


def delete_group(registry: Registry, name: str) -> str:
    group = find_group(registry, name)
    count = sum(p.group == name for p in registry.projects)
    if count:
        noun = "project" if count == 1 else "projects"
        return Problem(f"{name} has {count} {noun}; move or delete them first")
    if not confirm(f"Delete group {name}?"):
        return ""
    store(Registry(tuple(g for g in registry.groups if g != group), registry.projects))
    return f"Deleted group {name}"


def confirm(question: str) -> bool:
    print(f"{question} [y/N] ", end="", flush=True)
    answer = read_key()
    print("\r\x1b[K", end="", flush=True)
    return answer in ("y", "Y")


def edit_registry() -> str:
    path = default_path()
    editor = os.environ.get("EDITOR") or "vi"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return Problem(f"can't make {collapse_home(str(path.parent))}: {err.strerror}")
    # Through the shell, as git runs $EDITOR, so it may carry arguments.
    done = subprocess.run(["sh", "-c", 'exec ${EDITOR:-vi} "$1"', "sh", str(path)])
    return Problem(f"{editor} exited with status {done.returncode}") if done.returncode else ""


def read_key() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read(1)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # A key can send several bytes; only the first counts.
        return os.read(fd, 32).decode(errors="replace")[:1]
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)


def fail_in_popup(message: str) -> int:
    fail(message)
    if sys.stdin.isatty():
        print("\npress any key to close", end="", flush=True)
        read_key()
    return 1
