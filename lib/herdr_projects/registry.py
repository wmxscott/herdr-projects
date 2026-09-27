from __future__ import annotations

import contextlib
import os
import stat
import tempfile
import tomllib
from dataclasses import MISSING, dataclass, fields
from pathlib import Path

from herdr_projects import PLUGIN_ID

FILE_NAME = "projects.toml"


class RegistryError(Exception):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages


# Field order is the schema's key order; fields without a default are required.
@dataclass(frozen=True, kw_only=True)
class Group:
    name: str
    icon: str | None = None


@dataclass(frozen=True, kw_only=True)
class Project:
    name: str
    group: str | None = None
    icon: str | None = None
    path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", os.path.expanduser(self.path))

    @property
    def bare_label(self) -> str:
        return f"{self.group}/{self.name}" if self.group else self.name

    @property
    def real_path(self) -> str:
        return os.path.realpath(self.path)


# Kept in save order, so a registry's equality ignores the order it was built in.
@dataclass(frozen=True)
class Registry:
    groups: tuple[Group, ...] = ()
    projects: tuple[Project, ...] = ()

    def __post_init__(self) -> None:
        groups = sorted(self.groups, key=lambda g: g.name)
        projects = sorted(self.projects, key=lambda p: (p.group or "", p.name))
        object.__setattr__(self, "groups", tuple(groups))
        object.__setattr__(self, "projects", tuple(projects))

    def group(self, name: str) -> Group | None:
        return next((g for g in self.groups if g.name == name), None)

    def icon(self, project: Project) -> str | None:
        group = self.group(project.group) if project.group else None
        return project.icon or (group.icon if group else None)

    def label(self, project: Project) -> str:
        return f"{self.icon(project)} {project.bare_label}"


SECTIONS: dict[str, type[Group] | type[Project]] = {"groups": Group, "projects": Project}


def default_path() -> Path:
    explicit = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if explicit:
        return Path(explicit) / FILE_NAME
    # herdr's own default for this plugin id, for runs outside herdr.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "herdr" / "plugins" / "config" / PLUGIN_ID / FILE_NAME


def load(path: Path) -> Registry:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return Registry()
    except UnicodeDecodeError:
        raise RegistryError([f"can't read {path}: not UTF-8"]) from None
    except OSError as err:
        raise RegistryError([f"can't read {path}: {err.strerror}"]) from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise RegistryError([f"invalid TOML: {err}"]) from None
    return parse(data)


def parse(data: dict) -> Registry:
    errors, groups, projects = _read(data)
    if errors:
        raise RegistryError(errors)
    return Registry(tuple(groups.values()), tuple(projects.values()))


def validate(data: dict) -> list[str]:
    return _read(data)[0]


def _read(data: dict) -> tuple[list[str], dict[int, Group], dict[int, Project]]:
    errors = [f'unknown key "{key}"' for key in data if key not in SECTIONS]
    groups = _entries(data, "groups", errors)
    projects = _entries(data, "projects", errors)

    first_group: dict[str, int] = {}
    for i, group in groups.items():
        if (first := first_group.setdefault(group.name, i)) != i:
            errors.append(f'groups[{i}]: duplicate name "{group.name}" (also groups[{first}])')

    first_label: dict[str, int] = {}
    first_path: dict[str, int] = {}
    for i, project in projects.items():
        where = f"projects[{i}]"
        group = groups[first_group[project.group]] if project.group in first_group else None
        if project.group and not group:
            errors.append(f'{where}: group "{project.group}" not found')
        if not (project.icon or (group and group.icon)):
            errors.append(f"{where}: no icon")
        label, path = project.bare_label, project.real_path
        if (first := first_label.setdefault(label, i)) != i:
            errors.append(f'{where}: duplicate label "{label}" (also projects[{first}])')
        if (first := first_path.setdefault(path, i)) != i:
            errors.append(f'{where}: duplicate path "{path}" (also projects[{first}])')
    return errors, groups, projects


def _entries(data: dict, section: str, errors: list[str]) -> dict:
    tables = data.get(section, [])
    if not isinstance(tables, list):
        errors.append(f'"{section}" must be an array of tables')
        return {}
    cls = SECTIONS[section]
    required = {f.name: f.default is MISSING for f in fields(cls)}
    built = {}
    for i, table in enumerate(tables):
        where = f"{section}[{i}]"
        if not isinstance(table, dict):
            errors.append(f"{where}: must be a table")
            continue
        problems = [f'{where}: unknown key "{key}"' for key in table if key not in required]
        for key in required:
            value = table.get(key)
            if key not in table:
                if required[key]:
                    problems.append(f'{where}: missing required key "{key}"')
            elif not isinstance(value, str):
                problems.append(f'{where}: "{key}" must be a string')
            elif not value.strip():
                problems.append(f'{where}: "{key}" must not be empty')
            elif "\0" in value and key == "path":
                problems.append(f'{where}: "path" must not contain NUL')
        errors.extend(problems)
        if not problems:
            built[i] = cls(**table)
    return built


def collapse_home(path: str) -> str:
    home = os.path.expanduser("~").rstrip("/")
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home) :]
    return path


_ESCAPES = {code: f"\\u{code:04X}" for code in [*range(0x20), 0x7F]} | str.maketrans(
    {"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r", '"': '\\"', "\\": "\\\\"}
)


def _quote(text: str) -> str:
    return f'"{text.translate(_ESCAPES)}"'


def serialize(registry: Registry) -> str:
    blocks = []
    for section in SECTIONS:
        for item in getattr(registry, section):
            lines = [f"[[{section}]]"]
            for field in fields(item):
                value = getattr(item, field.name)
                if value is not None:
                    value = collapse_home(value) if field.name == "path" else value
                    lines.append(f"{field.name} = {_quote(value)}")
            blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def save(registry: Registry, path: Path) -> None:
    text = serialize(registry)
    errors = validate(tomllib.loads(text))
    if errors:
        raise RegistryError(errors)
    target = os.path.realpath(path)
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    try:
        mode = stat.S_IMODE(os.stat(target).st_mode)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, temp = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(target)}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fchmod(file.fileno(), mode)
            os.fsync(file.fileno())
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise
