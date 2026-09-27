"""The picker's add/edit flow and icon picker: chained fzf prompts in the popup.

Esc at any step raises Cancelled, which discards the whole flow.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from herdr_projects import theme
from herdr_projects.cli import (
    Failure,
    addable,
    find,
    find_group,
    load_registry,
    registered,
    store,
)
from herdr_projects.registry import Group, Project, Registry, collapse_home
from herdr_projects.theme import Palette

GLYPHS = Path(__file__).with_name("glyphs.tsv")
LAYOUT = (
    "--layout=reverse",
    "--height=100%",
    "--border=none",
    "--margin=0",
    "--padding=0",
    "--no-info",
)
NONE, NEW = "", "+"
HINTS = "\u21b5 accept · esc discards"


class Cancelled(Exception):
    pass


def icon_rows(
    registry: Registry, fallback: str | None = None, skip: bool = False, keep: str | None = None
) -> list[str]:
    """The rows before glyphs.tsv's: `<glyph>\\t<text>`, with a third field for a row's value
    when it isn't the glyph."""
    rows = [f"{keep}\tkeep current"] if keep else []
    if skip:
        rows.append(" \tno icon\t")
    if fallback:
        rows.append(f"{fallback}\tuse group icon\t")
    users: dict[str, list[str]] = {}
    for icon, name in [(g.icon, g.name) for g in registry.groups] + [
        (p.icon, p.bare_label) for p in registry.projects
    ]:
        if icon:
            users.setdefault(icon, []).append(name)
    return rows + [f"{icon}\tused by {', '.join(names)}" for icon, names in users.items()]


def icon_value(row: str) -> str | None:
    fields = row.split("\t")
    return (fields[2] if len(fields) > 2 else fields[0]) or None


def group_rows(registry: Registry) -> list[str]:
    """`<icon>  <name>\\t<value>`: `=<name>`, NONE, or NEW."""
    rows = [f"{g.icon or ' '}  {g.name}\t={g.name}" for g in registry.groups]
    return [*rows, f"   none\t{NONE}", f"   + new group\t{NEW}"]


def group_value(row: str) -> str:
    return row.rpartition("\t")[2]


def position(rows: list[str], value: Callable[[str], str | None], current: str | None) -> int:
    """fzf's 1-based position of the first row whose value is `current`, else 0."""
    return next((i for i, row in enumerate(rows, 1) if value(row) == current), 0)


def updated(
    registry: Registry, project: Project, old: Project | None = None, group: Group | None = None
) -> Registry:
    projects = tuple(p for p in registry.projects if p != old)
    groups = (*registry.groups, group) if group else registry.groups
    return Registry(groups, (*projects, project))


def regrouped(registry: Registry, old: Group, group: Group) -> Registry:
    """`old` replaced by `group`, its projects moved along with it."""
    groups = tuple(group if g == old else g for g in registry.groups)
    projects = tuple(
        replace(p, group=group.name) if p.group == old.name else p for p in registry.projects
    )
    return Registry(groups, projects)


def add(pal: Palette = theme.LATTE) -> str:
    registry = load_registry()
    path = addable()
    return change(registry, path, registered(registry, path), pal)


def edit(label: str, pal: Palette = theme.LATTE) -> str:
    registry = load_registry()
    project = find(registry, label)
    return change(registry, project.path, project, pal)


def change(
    registry: Registry, path: str, old: Project | None = None, pal: Palette = theme.LATTE
) -> str:
    """Run the flow for a new project at `path`, or for `old`; returns the notice."""
    title = f"{'Edit' if old else 'Add'} {collapse_home(path)}"
    header = theme.header(pal, HINTS, title=title)
    try:
        name = ask(header, "Name: ", old.name if old else os.path.basename(path))
        group, new = pick_group(registry, header, old.group if old else None)
        found = new or (registry.group(group) if group else None)
        icon = pick_icon(
            registry, header, "Icon: ", fallback=found and found.icon, current=old and old.icon
        )
    except Cancelled:
        return ""
    project = Project(name=name, group=group, icon=icon, path=path)
    result = updated(registry, project, old, new)
    if result == registry:
        return ""
    store(result)
    return f"{'Updated' if old else 'Added'} {result.label(project)}"


def edit_group(name: str, pal: Palette = theme.LATTE) -> str:
    registry = load_registry()
    old = find_group(registry, name)
    header = theme.header(pal, HINTS, title=f"Edit group {old.name}")
    try:
        name = ask(header, "Name: ", old.name)
        icon = pick_icon(registry, header, "Icon: ", skip=True, keep=old.icon, current=old.icon)
    except Cancelled:
        return ""
    result = regrouped(registry, old, Group(name=name, icon=icon))
    if result == registry:
        return ""
    store(result)
    return f"Updated {icon} {name}" if icon else f"Updated {name}"


def pick_group(
    registry: Registry, header: str, current: str | None
) -> tuple[str | None, Group | None]:
    """The chosen group's name, and the group itself when it is new."""
    rows = group_rows(registry)
    at = position(rows, group_value, f"={current}" if current else NONE)
    value = group_value(select(rows, header, "Group: ", at, "--delimiter", "\t", "--with-nth", "1"))
    if value != NEW:
        return value[1:] or None, None
    name = ask(header, "New group: ")
    if registry.group(name):
        return name, None
    return name, Group(name=name, icon=pick_icon(registry, header, f"{name} icon: ", skip=True))


def pick_icon(
    registry: Registry,
    header: str,
    prompt: str,
    fallback: str | None = None,
    skip: bool = False,
    current: str | None = None,
    keep: str | None = None,
) -> str | None:
    rows = icon_rows(registry, fallback, skip, keep)
    at = position(rows, icon_value, current)
    glyphs = GLYPHS.read_text(encoding="utf-8").partition("\n")[2]
    text = "".join(f"{row}\n" for row in rows) + glyphs
    args = ("--delimiter", "\t", "--nth", "2", "--tabstop", "3")
    return icon_value(select(text, header, prompt, at, *args))


def ask(header: str, prompt: str, default: str = "") -> str:
    """A line of input, prefilled with `default`; blank means `default`, asked again if none."""
    while True:
        query = fzf("", header, prompt, "--print-query", "--disabled", "--query", default)
        answer = query.strip() or default
        if answer:
            return answer


def select(rows: list[str] | str, header: str, prompt: str, at: int = 0, *args: str) -> str:
    text = rows if isinstance(rows, str) else "".join(f"{row}\n" for row in rows)
    if at > 1:
        args = (*args, "--bind", f"load:pos({at})")
    row = fzf(text, header, prompt, "--bind", "enter:accept-non-empty", *args)
    if not row:
        raise Cancelled
    return row


def fzf(text: str, header: str, prompt: str, *args: str) -> str:
    """The first line fzf prints: the selection, or the query with --print-query."""
    command = ["fzf", "--ansi", "--header", header, "--prompt", prompt, *LAYOUT, *args]
    done = subprocess.run(command, input=text, stdout=subprocess.PIPE, encoding="utf-8")
    if done.returncode == 130:
        raise Cancelled
    # 1 is no match, which a prompt over no rows always ends with.
    if done.returncode not in (0, 1):
        raise Failure(f"fzf exited with status {done.returncode}")
    return done.stdout.partition("\n")[0]
