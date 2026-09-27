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
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                location,
                "rev-parse",
                "--path-format=absolute",
                "--git-dir",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    dirs = done.stdout.splitlines()
    if done.returncode != 0 or len(dirs) != 2:
        return False
    git_dir, common_dir = (os.path.realpath(d) for d in dirs)
    return git_dir != common_dir


def open_instances(
    registry: Registry,
    workspaces: Iterable[Workspace],
    location: Callable[[Workspace], str | None],
) -> dict[Project, Workspace]:
    """Each project's open workspace: the first, in herdr's order, that resolves to it."""
    found: dict[Project, Workspace] = {}
    for workspace in workspaces:
        if workspace.linked_worktree:
            continue
        where = location(workspace)
        project = where and project_for(registry, where, workspace.linked_worktree)
        if project:
            found.setdefault(project, workspace)
    return found
