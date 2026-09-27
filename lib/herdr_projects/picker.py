"""The picker popup: fzf over the registry, whose keys run the same operations as the CLI.

The `popup` action does the slow work, reading the registry and asking herdr what is
open, before it opens the popup, and hands the rows over in a file. The popup's first
render then only has to start fzf.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from pathlib import Path

from herdr_projects import herdr
from herdr_projects.cli import (
    Failure,
    fail,
    find,
    load_registry,
    open_project,
    open_projects,
    relabel,
    state_dir,
    status,
    store,
    toast,
)
from herdr_projects.herdr import HerdrError, PopupBusy, Workspace
from herdr_projects.registry import (
    Project,
    Registry,
    RegistryError,
    collapse_home,
    default_path,
    load,
)

WIDTH, HEIGHT = "70%", "60%"
ROWS_ENV = "HERDR_PROJECTS_ROWS"
ADD_ENV = "HERDR_PROJECTS_ADD"
POPUP_RETRY_SECONDS = 3.0
STATUS_GLYPHS = {"active": "", "open": "", "missing": "\U000f0338"}
GAP = "  "
KEYS = ("ctrl-r", "ctrl-a", "ctrl-e", "ctrl-d", "ctrl-o")
HELP = "enter open · ^r rename · ^a add · ^e edit · ^d delete · ^o edit file"
INVALID_HELP = "^o edit projects.toml · esc close"
COMING = "{}: coming in A7"


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


def pad(text: str, width: int) -> str:
    return text + " " * (width - cell_width(text))


def rows(registry: Registry, found: dict[Project, Workspace]) -> list[str]:
    """fzf input, `<icon>  <bare label>  <~path>  <status>`, then a tab and the bare label."""
    cells = [
        (registry.icon(p) or "", p.bare_label, collapse_home(p.path)) for p in registry.projects
    ]
    widths = [max((cell_width(c[i]) for c in cells), default=0) for i in range(3)]
    lines = []
    for project, cell in zip(registry.projects, cells, strict=True):
        columns = [pad(text, width) for text, width in zip(cell, widths, strict=True)]
        columns.append(STATUS_GLYPHS.get(status(project, found) or "", ""))
        lines.append(GAP.join(columns).rstrip() + "\t" + project.bare_label)
    return lines


def build() -> tuple[list[str], bool]:
    """The list's rows and whether the registry is valid; if not, one row with its first error."""
    try:
        registry = load(default_path())
    except RegistryError as err:
        return [f"{err.messages[0]}\t"], False
    try:
        found = open_projects(registry)
    except HerdrError:
        found = {}
    return rows(registry, found), True


def popup(add: bool = False) -> int:
    env = {ADD_ENV: "1"} if add else {}
    lines, valid = build()
    # An invalid registry is left for the picker to read and show.
    path = write_rows(lines) if valid else None
    if path:
        env[ROWS_ENV] = str(path)
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


def write_rows(lines: list[str]) -> Path | None:
    directory = state_dir()
    path = directory / f"picker-{os.getpid()}.txt"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    except OSError:
        return None
    return path


def read_rows() -> list[str] | None:
    """Rows the popup action built for this popup. The file is single-use."""
    name = os.environ.get(ROWS_ENV)
    if not name:
        return None
    path = Path(name)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    path.unlink(missing_ok=True)
    return [line for line in text.split("\n") if line]


def run(add: bool = False) -> int:
    if not shutil.which("fzf"):
        return fail_in_popup("the picker needs fzf on PATH: https://github.com/junegunn/fzf")
    lines, valid = read_rows(), True
    notice = COMING.format("Add") if add or os.environ.get(ADD_ENV) else None
    while True:
        if lines is None:
            lines, valid = build()
        help_ = HELP if valid else INVALID_HELP
        try:
            picked = choose(lines, f"{notice}\n{help_}" if notice else help_)
        except Failure as err:
            return fail_in_popup(str(err))
        if picked is None:
            return 0
        notice = handle(*picked, valid=valid)
        if notice is None:
            return 0
        lines = None


def choose(lines: list[str], header: str) -> tuple[str, str | None] | None:
    """Run fzf: None when cancelled, else the key pressed and the selected bare label."""
    args = ["fzf", "--delimiter", "\t", "--with-nth", "1", "--expect", ",".join(KEYS)]
    args += ["--header", header, "--prompt", "> ", "--layout", "reverse", "--height", "100%"]
    args += ["--border=none", "--margin=0", "--padding=0", "--no-info"]
    done = subprocess.run(
        args,
        input="".join(f"{line}\n" for line in lines),
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    if done.returncode == 130:
        return None
    # 1 is no selection, which --expect keys can still end with.
    if done.returncode not in (0, 1):
        raise Failure(f"fzf exited with status {done.returncode}")
    key, _, selection = done.stdout.partition("\n")
    return key, selection.rstrip("\n").rpartition("\t")[2] or None


def handle(key: str, label: str | None, valid: bool = True) -> str | None:
    """Carry out a key: None to close the popup, else a notice to show over the reloaded list."""
    try:
        if key == "ctrl-o":
            return edit_registry()
        if not valid:
            return ""
        if key == "ctrl-r":
            toast(relabel(load_registry()))
            return None
        if key == "ctrl-a":
            return COMING.format("Add")
        if label is None:
            return ""
        if key == "ctrl-e":
            return COMING.format("Edit")
        registry = load_registry()
        project = find(registry, label)
        if key == "ctrl-d":
            return delete(registry, project)
        open_project(registry, project)
        return None
    except (Failure, HerdrError) as err:
        return str(err)


def delete(registry: Registry, project: Project) -> str:
    label = registry.label(project)
    print(f"Delete {label}? [y/N] ", end="", flush=True)
    answer = read_key()
    print("\r\x1b[K", end="", flush=True)
    if answer not in ("y", "Y"):
        return ""
    store(Registry(registry.groups, tuple(p for p in registry.projects if p != project)))
    return f"Deleted {label}"


def edit_registry() -> str:
    path = default_path()
    editor = os.environ.get("EDITOR") or "vi"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return f"can't make {collapse_home(str(path.parent))}: {err.strerror}"
    # Through the shell, as git runs $EDITOR, so it may carry arguments.
    done = subprocess.run(["sh", "-c", 'exec ${EDITOR:-vi} "$1"', "sh", str(path)])
    return f"{editor} exited with status {done.returncode}" if done.returncode else ""


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
