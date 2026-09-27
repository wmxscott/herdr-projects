from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import bare_layout, git
from herdr_projects.herdr import Workspace
from herdr_projects.registry import Project, Registry
from herdr_projects.resolve import (
    is_linked_worktree,
    open_instances,
    present_projects,
    project_for,
)


@pytest.fixture
def root(env, tmp_path: Path) -> Path:
    path = tmp_path / "root"
    path.mkdir()
    return path


@pytest.fixture
def repo(root: Path) -> Path:
    """A git repo at root/repo with a linked worktree inside it and one beside it."""
    path = root / "repo"
    (path / "src").mkdir(parents=True)
    git("init", "-q", str(path))
    git("-C", str(path), "commit", "-q", "--allow-empty", "-m", "init")
    git("-C", str(path), "worktree", "add", "-q", "-b", "inside", str(path / "wt"))
    git("-C", str(path), "worktree", "add", "-q", "-b", "beside", str(root / "repo-wt"))
    (path / "wt" / "src").mkdir()
    return path


def make(*projects: tuple[str, Path | str]) -> Registry:
    return Registry((), tuple(Project(name=n, icon="x", path=str(p)) for n, p in projects))


def dirs(root: Path, *names: str) -> None:
    for name in names:
        (root / name).mkdir(parents=True)


def test_exact_path(root):
    dirs(root, "a")
    assert project_for(make(("a", root / "a")), str(root / "a")).name == "a"


def test_subfolder(root):
    dirs(root, "a/deep/er")
    assert project_for(make(("a", root / "a")), str(root / "a/deep/er")).name == "a"


def test_longest_path_wins(root):
    dirs(root, "a/b/c", "a/x")
    registry = make(("outer", root / "a"), ("inner", root / "a/b"))
    assert project_for(registry, str(root / "a/b/c")).name == "inner"
    assert project_for(registry, str(root / "a/b")).name == "inner"
    assert project_for(registry, str(root / "a/x")).name == "outer"


def test_a_shared_name_prefix_is_not_an_ancestor(root):
    dirs(root, "ab", "a")
    assert project_for(make(("a", root / "a")), str(root / "ab")) is None


def test_no_match(root):
    dirs(root, "a", "b")
    assert project_for(make(("a", root / "a")), str(root / "b")) is None
    assert project_for(make(), str(root / "b")) is None


def test_symlinked_project_path(root):
    dirs(root, "real/sub")
    os.symlink(root / "real", root / "link")
    assert project_for(make(("p", root / "link")), str(root / "real/sub")).name == "p"


def test_symlinked_location(root):
    dirs(root, "real/sub")
    os.symlink(root / "real/sub", root / "link")
    assert project_for(make(("p", root / "real")), str(root / "link")).name == "p"


def test_tilde_project_path(env, root):
    home = Path(env["HOME"])
    (home / "code/p/sub").mkdir(parents=True)
    assert project_for(make(("p", "~/code/p")), str(home / "code/p/sub")).name == "p"


def test_missing_location_still_matches_by_path(root):
    dirs(root, "a")
    assert project_for(make(("a", root / "a")), str(root / "a/gone")).name == "a"


def test_is_linked_worktree(root, repo):
    assert not is_linked_worktree(str(repo))
    assert not is_linked_worktree(str(repo / "src"))
    assert is_linked_worktree(str(repo / "wt"))
    assert is_linked_worktree(str(repo / "wt/src"))
    assert is_linked_worktree(str(root / "repo-wt"))
    assert not is_linked_worktree(str(root))
    assert not is_linked_worktree(str(root / "missing"))


def test_main_checkout_matches(repo):
    registry = make(("repo", repo))
    assert project_for(registry, str(repo)).name == "repo"
    assert project_for(registry, str(repo / "src")).name == "repo"


def test_linked_worktree_never_matches(root, repo):
    registry = make(("repo", repo), ("root", root))
    assert project_for(registry, str(repo / "wt")) is None
    assert project_for(registry, str(repo / "wt/src")) is None
    assert project_for(registry, str(root / "repo-wt")) is None


def test_herdrs_worktree_hint_is_preferred(root, repo):
    registry = make(("repo", repo))
    assert project_for(registry, str(repo / "wt"), linked_worktree=False).name == "repo"
    assert project_for(registry, str(repo), linked_worktree=True) is None


def ws(
    workspace_id: str,
    focused: bool = False,
    linked: bool | None = None,
    checkout: Path | None = None,
    repo_root: Path | None = None,
) -> Workspace:
    return Workspace(
        id=workspace_id,
        label="",
        focused=focused,
        active_tab_id=f"{workspace_id}:t1",
        linked_worktree=linked,
        checkout_path=checkout and str(checkout),
        repo_root=repo_root and str(repo_root),
    )


def test_open_instances(root):
    dirs(root, "a/sub", "b", "c")
    registry = make(("a", root / "a"), ("b", root / "b"), ("c", root / "c"))
    a, b, _ = registry.projects
    locations = {
        "w1": str(root / "a/sub"),
        "w2": str(root / "b"),
        "w3": str(root / "a"),
        "w4": None,
        "w5": str(root),
    }
    workspaces = [ws("w1"), ws("w2", focused=True), ws("w3"), ws("w4"), ws("w5")]
    found = open_instances(registry, workspaces, lambda w: locations[w.id])
    assert found == {a: workspaces[0], b: workspaces[1]}


def test_open_instances_skip_linked_worktrees(root, repo):
    registry = make(("repo", repo))
    workspaces = [ws("w1", linked=True), ws("w2", linked=False)]
    locations = {"w1": str(repo), "w2": str(repo)}
    found = open_instances(registry, workspaces, lambda w: locations[w.id])
    assert found == {registry.projects[0]: workspaces[1]}


def test_a_workspace_without_a_worktree_record_resolves_by_path(root):
    edge = bare_layout(root / "edge")
    registry = make(("edge", edge))
    workspaces = [ws("w1")]
    found = open_instances(registry, workspaces, lambda w: str(edge / "main"))
    assert found == {registry.projects[0]: workspaces[0]}
    assert present_projects(registry, workspaces, lambda w: str(edge / "main")) == {
        registry.projects[0]: False
    }


def test_worktree_workspaces_are_present_not_open(root, repo):
    registry = make(("repo", repo))
    worktree = ws("w1", focused=True, linked=True, checkout=repo / "wt", repo_root=repo)
    locations = {"w1": str(repo / "wt"), "w2": str(repo)}
    assert open_instances(registry, [worktree], lambda w: locations[w.id]) == {}
    assert present_projects(registry, [worktree], lambda w: locations[w.id]) == {
        registry.projects[0]: True
    }
    main = ws("w2")
    assert present_projects(registry, [main, worktree], lambda w: locations[w.id]) == {
        registry.projects[0]: True
    }
    unfocused = ws("w1", linked=True, checkout=repo / "wt", repo_root=repo)
    assert present_projects(registry, [unfocused], lambda w: locations[w.id]) == {
        registry.projects[0]: False
    }


def test_only_the_open_instance_makes_a_project_active(root, repo):
    registry = make(("repo", repo))
    workspaces = [ws("w1"), ws("w2", focused=True)]
    assert present_projects(registry, workspaces, lambda w: str(repo)) == {
        registry.projects[0]: False
    }


def test_a_worktree_maps_by_repo_root_ancestry_not_its_location(root, repo):
    registry = make(("src", repo / "src"), ("root", root))
    worktree = ws("w1", linked=True, checkout=root / "repo-wt", repo_root=repo)
    found = present_projects(registry, [worktree], lambda w: str(repo / "src"))
    assert {p.name: f for p, f in found.items()} == {"root": False}


@pytest.mark.parametrize("reported", [".bare", ""])
def test_a_bare_repos_worktree_maps_to_its_container(root, reported):
    edge = bare_layout(root / "edge")
    registry = make(("edge", edge))
    worktree = ws("w1", linked=True, checkout=edge / "main", repo_root=edge / reported)
    assert present_projects(registry, [worktree], lambda w: None) == {registry.projects[0]: False}


def test_without_repo_root_git_finds_the_main_checkout(root, repo):
    edge = bare_layout(root / "edge")
    registry = make(("repo", repo), ("edge", edge))
    locations = {"w1": str(root / "repo-wt"), "w2": str(edge / "main"), "w3": None}
    workspaces = [
        ws("w1", focused=True, linked=True),
        ws("w2", linked=True),
        ws("w3", linked=True),
    ]
    found = present_projects(registry, workspaces, lambda w: locations[w.id])
    assert {p.name: f for p, f in found.items()} == {"repo": True, "edge": False}
    checkout = ws("w1", linked=True, checkout=repo / "wt")
    found = present_projects(registry, [checkout], lambda w: None)
    assert {p.name: f for p, f in found.items()} == {"repo": False}
