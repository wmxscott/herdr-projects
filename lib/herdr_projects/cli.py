from __future__ import annotations

import argparse
import contextlib
import os
import sys
from datetime import datetime
from pathlib import Path

from herdr_projects import PLUGIN_ID, VERSION


def state_dir() -> Path:
    explicit = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if explicit:
        return Path(explicit)
    # herdr's own default for this plugin id, for runs outside herdr.
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "herdr" / "plugins" / PLUGIN_ID


def cmd_event(args: argparse.Namespace) -> int:
    # A hook must never fail, so a log it can't write is dropped.
    with contextlib.suppress(Exception):
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        event = os.environ.get("HERDR_PLUGIN_EVENT", "")
        payload = os.environ.get("HERDR_PLUGIN_EVENT_JSON", "")
        with open(directory / "hook.log", "a", encoding="utf-8") as log:
            log.write(f"{stamp}\t{event}\t{payload}\n")
    return 0


def not_implemented(args: argparse.Namespace) -> int:
    print(f"herdr-projects: {args.command}: not implemented", file=sys.stderr)
    return 2


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


HANDLERS = {"event": cmd_event}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:
        return 0 if exit_.code is None else int(exit_.code)
    return HANDLERS.get(args.command, not_implemented)(args)
