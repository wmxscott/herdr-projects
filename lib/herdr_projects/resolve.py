from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable

from herdr_projects.herdr import Workspace
from herdr_projects.registry import Project, Registry


def project_for(
    registry: Registry, location: str, linked_worktree: bool | None = None
) -> Project | None:
    """The project a location belongs to; never one for a linked worktree.

    `linked_worktree` is herdr's hint for the location's workspace; without it, git decides.
    """
    real = os.path.realpath(location)
    best = None
    for project in registry.projects:
        path = project.real_path
        inside = real == path or real.startswith(path.rstrip("/") + "/")
        if inside and (best is None or len(path) > len(best.real_path)):
            best = project
    if best is None:
        return None
    if linked_worktree is None:
        linked_worktree = is_linked_worktree(real)
    return None if linked_worktree else best


def is_linked_worktree(location: str) -> bool:
    dirs = _git_dirs(location, "--git-dir", "--git-common-dir")
    return bool(dirs) and dirs[0] != dirs[1]


def main_checkout(location: str) -> str | None:
    """Where the repo of the checkout at location lives: its main checkout, or the directory
    holding a bare repo (a `.bare` layout's container)."""
    dirs = _git_dirs(location, "--git-common-dir")
    return os.path.dirname(dirs[0]) if dirs else None


def _git_dirs(location: str, *flags: str) -> list[str] | None:
    try:
        done = subprocess.run(
            ["git", "-C", location, "rev-parse", "--path-format=absolute", *flags],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    dirs = done.stdout.splitlines()
    if done.returncode != 0 or len(dirs) != len(flags):
        return None
    return [os.path.realpath(d) for d in dirs]


def open_instances(
    registry: Registry,
    workspaces: Iterable[Workspace],
    location: Callable[[Workspace], str | None],
) -> dict[Project, Workspace]:
    """Each project's open workspace: the first, in herdr's order, that resolves to it.

    A workspace herdr reports no worktree for is not a git checkout at its root, so its
    location resolves by path alone, even inside a linked worktree.
    """
    found: dict[Project, Workspace] = {}
    for workspace in workspaces:
        if workspace.linked_worktree:
            continue
        where = location(workspace)
        project = where and project_for(registry, where, linked_worktree=False)
        if project:
            found.setdefault(project, workspace)
    return found


def present_projects(
    registry: Registry,
    workspaces: Iterable[Workspace],
    location: Callable[[Workspace], str | None],
) -> dict[Project, bool]:
    """Each project with an open workspace or a linked worktree workspace of its repo, and
    whether one of them is focused.

    A worktree belongs to the project whose path is or holds its repo's root.
    """
    workspaces = list(workspaces)
    found = {p: w.focused for p, w in open_instances(registry, workspaces, location).items()}
    for workspace in workspaces:
        if not workspace.linked_worktree:
            continue
        root = workspace.repo_root
        if not root:
            where = workspace.checkout_path or location(workspace)
            root = where and main_checkout(where)
        project = root and project_for(registry, root, linked_worktree=False)
        if project:
            found[project] = found.get(project, False) or workspace.focused
    return found
