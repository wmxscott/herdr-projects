from __future__ import annotations

import argparse
import contextlib
import os
import sys
from datetime import datetime
from pathlib import Path

from herdr_projects import PLUGIN_ID, VERSION, herdr
from herdr_projects.herdr import HerdrError, Workspace
from herdr_projects.registry import (
    Group,
    Project,
    Registry,
    RegistryError,
    collapse_home,
    default_path,
    load,
    save,
)
from herdr_projects.resolve import is_linked_worktree, open_instances, project_for

TOAST_TITLE = "Projects"


class Failure(Exception):
    """A user-facing failure: each line goes to stderr, and a summary to a toast."""

    def __init__(self, *lines: str) -> None:
        super().__init__("; ".join(lines))
        self.lines = lines


class NoProject(Failure):
    pass


def state_dir() -> Path:
    explicit = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if explicit:
        return Path(explicit)
    # herdr's own default for this plugin id, for runs outside herdr.
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "herdr" / "plugins" / PLUGIN_ID


def toast(body: str) -> None:
    if os.environ.get("HERDR_PLUGIN_ROOT") or os.environ.get("HERDR_PLUGIN_CONTEXT_JSON"):
        with contextlib.suppress(HerdrError):
            herdr.notify(TOAST_TITLE, body)


def say(message: str) -> None:
    print(message)
    toast(message)


def fail(*lines: str) -> int:
    for line in lines:
        print(f"herdr-projects: {line}", file=sys.stderr)
    toast(lines[0] if len(lines) == 1 else f"{lines[0]} (+{len(lines) - 1} more)")
    return 1


def load_registry() -> Registry:
    path = default_path()
    try:
        return load(path)
    except RegistryError as err:
        raise Failure(*(f"{collapse_home(str(path))}: {m}" for m in err.messages)) from None


def open_projects(registry: Registry) -> dict[Project, Workspace]:
    panes = herdr.panes()
    return open_instances(
        registry, herdr.workspaces(), lambda w: (p := herdr.active_pane(w, panes)) and p.cwd
    )


def find(registry: Registry, target: str) -> Project:
    for project in registry.projects:
        if project.bare_label == target:
            return project
    named = [p for p in registry.projects if p.name == target]
    if len(named) > 1:
        raise Failure(f"{target} is ambiguous: " + ", ".join(p.bare_label for p in named))
    if not named:
        raise Failure(f"No project {target}")
    return named[0]


def find_group(registry: Registry, name: str) -> Group:
    group = registry.group(name)
    if not group:
        raise Failure(f'No group "{name}"')
    return group


def status(project: Project, found: dict[Project, Workspace]) -> str | None:
    if not os.path.isdir(project.path):
        return "missing"
    if project in found:
        return "active" if found[project].focused else "open"
    return None


def open_project(registry: Registry, project: Project) -> None:
    workspace = open_projects(registry).get(project)
    if workspace:
        herdr.focus(workspace.id)
    elif not os.path.isdir(project.path):
        raise Failure(f"No such directory: {collapse_home(project.path)}")
    else:
        herdr.create(project.real_path, registry.label(project))


def store(registry: Registry) -> None:
    target = default_path()
    try:
        save(registry, target)
    except RegistryError as err:
        raise Failure(*err.messages) from None
    except OSError as err:
        raise Failure(f"can't write {collapse_home(str(target))}: {err.strerror}") from None


def relabel(registry: Registry, workspace_id: str | None = None) -> str:
    """Label a workspace after its project, by default the user's; returns what happened."""
    if workspace_id:
        workspace = herdr.workspace(workspace_id)
        pane = herdr.active_pane(workspace)
    else:
        pane = herdr.current_pane()
        workspace = herdr.workspace(pane.workspace_id)
    location = pane and pane.cwd
    if not location:
        raise Failure(f"No working directory for workspace {workspace.id}")
    project = project_for(registry, location, workspace.linked_worktree)
    if not project:
        raise NoProject(f"No project for {collapse_home(location)}")
    label = registry.label(project)
    if workspace.label == label:
        return f"Already {label}"
    herdr.rename(workspace.id, label)
    return f"Renamed to {label}"


def cmd_list(args: argparse.Namespace) -> int:
    registry = load_registry()
    try:
        found = open_projects(registry)
    except HerdrError as err:
        print(f"herdr-projects: no open/active status: {err}", file=sys.stderr)
        found = {}
    for project in registry.projects:
        print(
            f"{project.bare_label}\t{collapse_home(project.path)}\t{status(project, found) or '-'}"
        )
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    registry = load_registry()
    open_project(registry, find(registry, args.project))
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    say(relabel(load_registry(), args.workspace))
    return 0


def addable(path: str | None = None) -> str:
    """The absolute path to add, by default the user's pane's cwd; refuses non-projects."""
    if path:
        path = os.path.abspath(os.path.expanduser(path))
    else:
        path = herdr.current_pane().cwd
        if not path:
            raise Failure("The current pane has no working directory")
    if not os.path.isdir(path):
        raise Failure(f"No such directory: {collapse_home(path)}")
    if is_linked_worktree(path):
        raise Failure(f"Linked worktrees can't be projects: {collapse_home(path)}")
    return path


def registered(registry: Registry, path: str) -> Project | None:
    real = os.path.realpath(path)
    return next((p for p in registry.projects if p.real_path == real), None)


def cmd_add(args: argparse.Namespace) -> int:
    registry = load_registry()
    path = addable(args.path)
    existing = registered(registry, path)
    if existing:
        raise Failure(f"Already registered as {registry.label(existing)}")
    if args.group:
        find_group(registry, args.group)
    project = Project(
        name=args.name or os.path.basename(path),
        group=args.group or None,
        icon=args.icon or None,
        path=path,
    )
    if not registry.icon(project):
        raise Failure("No icon: pass --icon, or a --group that has one")
    if any(p.bare_label == project.bare_label for p in registry.projects):
        raise Failure(f"{project.bare_label} already exists")
    store(Registry(registry.groups, (*registry.projects, project)))
    say(f"Added {registry.label(project)}")
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    workspace_id = None
    try:
        event = herdr.event()
        workspace_id = event and event.workspace_id
        if not workspace_id:
            payload = os.environ.get("HERDR_PLUGIN_EVENT_JSON", "")
            raise Failure(f"no workspace id in {payload}")
        with contextlib.suppress(NoProject):
            relabel(load_registry(), workspace_id)
    # A hook must never fail: whatever goes wrong is logged, and a log it can't write is dropped.
    except Exception as err:
        with contextlib.suppress(Exception):
            directory = state_dir()
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            message = f"{type(err).__name__}: {err}".replace("\n", " ")
            with open(directory / "hook.log", "a", encoding="utf-8") as log:
                log.write(f"{stamp}\t{workspace_id or '-'}\t{message}\n")
    return 0


# picker imports this module, so it is imported only when needed.
def cmd_picker(args: argparse.Namespace) -> int:
    from herdr_projects import picker

    return picker.run(args.add)


def cmd_popup(args: argparse.Namespace) -> int:
    from herdr_projects import picker

    return picker.popup(args.add)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="herdr-projects",
        description="Open, add and label herdr workspaces from a curated project list.",
    )
    parser.add_argument("--version", action="version", version=f"herdr-projects {VERSION}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    commands.add_parser("list", help="print projects as label, path and status")

    open_ = commands.add_parser("open", help="focus or create a project's workspace")
    open_.add_argument("project", help="group/name, or a bare name if it is unambiguous")

    rename = commands.add_parser("rename", help="relabel a workspace after its project")
    rename.add_argument("--workspace", metavar="ID")

    add = commands.add_parser("add", help="register a project")
    add.add_argument("path", nargs="?")
    add.add_argument("--name", help="default: the directory's name")
    add.add_argument("--group")
    add.add_argument("--icon")

    picker = commands.add_parser("picker", help="the picker itself (runs inside the popup)")
    picker.add_argument("--add", action="store_true", help="start in the add flow")

    popup = commands.add_parser("popup", help="open the picker popup")
    popup.add_argument("--add", action="store_true", help="start in the add flow")

    commands.add_parser("event", help="handle a herdr event (run by herdr)")
    return parser


HANDLERS = {
    "list": cmd_list,
    "open": cmd_open,
    "rename": cmd_rename,
    "add": cmd_add,
    "picker": cmd_picker,
    "popup": cmd_popup,
    "event": cmd_event,
}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:
        return 0 if exit_.code is None else int(exit_.code)
    try:
        return HANDLERS[args.command](args)
    except HerdrError as err:
        return fail(str(err))
    except Failure as err:
        return fail(*err.lines)
