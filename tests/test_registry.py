from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path

import pytest
from herdr_projects import registry
from herdr_projects.registry import Group, Project, Registry, RegistryError

GLYPH = "\U000f0338"
SAMPLE = f"""\
[[groups]]
name = "swb"
icon = "{GLYPH}"

[[projects]]
name = "edge"
group = "swb"
path = "~/Developer/switchbit-dev/edge"

[[projects]]
name = "notes"
icon = "N"
path = "/srv/notes"
"""


@pytest.fixture
def home(env) -> Path:
    path = Path(env["HOME"])
    path.mkdir()
    return path


def errors(data: dict) -> list[str]:
    with pytest.raises(RegistryError) as raised:
        registry.parse(data)
    assert raised.value.messages == registry.validate(data)
    return raised.value.messages


def roundtrip(reg: Registry) -> Registry:
    return registry.parse(tomllib.loads(registry.serialize(reg)))


# --- default path -------------------------------------------------------------


def test_default_path_uses_herdr_plugin_config_dir(env, monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(tmp_path / "cfg"))
    assert registry.default_path() == tmp_path / "cfg" / "projects.toml"


def test_default_path_without_herdr_uses_xdg(env, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    expected = tmp_path / "xdg/herdr/plugins/config/herdr-projects/projects.toml"
    assert registry.default_path() == expected


def test_default_path_without_xdg_uses_home(env, home):
    expected = home / ".config/herdr/plugins/config/herdr-projects/projects.toml"
    assert registry.default_path() == expected


# --- load ---------------------------------------------------------------------


def test_load_missing_file_is_an_empty_registry(env, tmp_path):
    assert registry.load(tmp_path / "projects.toml") == Registry()


def test_load_dangling_symlink_is_an_empty_registry(env, tmp_path):
    link = tmp_path / "projects.toml"
    link.symlink_to(tmp_path / "gone.toml")
    assert registry.load(link) == Registry()


def test_load(env, home, tmp_path):
    path = tmp_path / "projects.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    assert registry.load(path) == Registry(
        groups=(Group(name="swb", icon=GLYPH),),
        projects=(
            Project(name="edge", group="swb", path=str(home / "Developer/switchbit-dev/edge")),
            Project(name="notes", icon="N", path="/srv/notes"),
        ),
    )


def test_load_invalid_toml(env, tmp_path):
    path = tmp_path / "projects.toml"
    path.write_text("[[projects]\n")
    with pytest.raises(RegistryError) as raised:
        registry.load(path)
    [message] = raised.value.messages
    assert message.startswith("invalid TOML: ")
    assert str(raised.value) == message


def test_load_non_utf8(env, tmp_path):
    path = tmp_path / "projects.toml"
    path.write_bytes(b'[[groups]]\nname = "\xff"\n')
    with pytest.raises(RegistryError) as raised:
        registry.load(path)
    assert raised.value.messages == [f"can't read {path}: not UTF-8"]


def test_load_unreadable(env, tmp_path):
    with pytest.raises(RegistryError) as raised:
        registry.load(tmp_path)
    [message] = raised.value.messages
    assert message.startswith(f"can't read {tmp_path}: ")


def test_load_reports_every_validation_error(env, tmp_path):
    path = tmp_path / "projects.toml"
    path.write_text('[[projects]]\nname = "a"\n\n[[projects]]\npath = "/b"\nicon = ""\n')
    with pytest.raises(RegistryError) as raised:
        registry.load(path)
    assert raised.value.messages == [
        'projects[0]: missing required key "path"',
        'projects[1]: missing required key "name"',
        'projects[1]: "icon" must not be empty',
    ]
    assert str(raised.value) == "\n".join(raised.value.messages)


# --- validation ---------------------------------------------------------------


def test_empty_data_is_an_empty_registry():
    assert registry.parse({}) == Registry()
    assert registry.validate({}) == []


def test_path_that_does_not_exist_is_not_an_error(tmp_path):
    data = {"projects": [{"name": "a", "icon": "A", "path": str(tmp_path / "nope")}]}
    assert registry.parse(data).projects[0].path == str(tmp_path / "nope")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"extra": 1}, ['unknown key "extra"']),
        ({"groups": {"name": "a"}}, ['"groups" must be an array of tables']),
        ({"projects": "a"}, ['"projects" must be an array of tables']),
        ({"groups": ["a"]}, ["groups[0]: must be a table"]),
        ({"groups": [{"name": "a", "colour": "red"}]}, ['groups[0]: unknown key "colour"']),
        (
            {"projects": [{"name": "a", "icon": "A", "path": "/a", "tags": []}]},
            ['projects[0]: unknown key "tags"'],
        ),
        ({"groups": [{"name": 1}]}, ['groups[0]: "name" must be a string']),
        ({"groups": [{"name": "a", "icon": True}]}, ['groups[0]: "icon" must be a string']),
        (
            {"projects": [{"name": "a", "icon": "A", "path": ["/a"]}]},
            ['projects[0]: "path" must be a string'],
        ),
        (
            {"projects": [{"name": "a", "group": 2, "icon": "A", "path": "/a"}]},
            ['projects[0]: "group" must be a string'],
        ),
        ({"groups": [{"icon": "A"}]}, ['groups[0]: missing required key "name"']),
        ({"projects": [{"icon": "A", "path": "/a"}]}, ['projects[0]: missing required key "name"']),
        ({"projects": [{"name": "a", "icon": "A"}]}, ['projects[0]: missing required key "path"']),
        ({"groups": [{"name": ""}]}, ['groups[0]: "name" must not be empty']),
        ({"groups": [{"name": "a", "icon": " "}]}, ['groups[0]: "icon" must not be empty']),
        (
            {"projects": [{"name": "a", "icon": "A", "path": ""}]},
            ['projects[0]: "path" must not be empty'],
        ),
        (
            {"projects": [{"name": "a", "group": "", "icon": "A", "path": "/a"}]},
            ['projects[0]: "group" must not be empty'],
        ),
        (
            {"groups": [{"name": "a"}, {"name": "b"}, {"name": "a", "icon": "A"}]},
            ['groups[2]: duplicate name "a" (also groups[0])'],
        ),
        (
            {"projects": [{"name": "a", "group": "g", "icon": "A", "path": "/a"}]},
            ['projects[0]: group "g" not found'],
        ),
        ({"projects": [{"name": "a", "path": "/a"}]}, ["projects[0]: no icon"]),
        (
            {"groups": [{"name": "g"}], "projects": [{"name": "a", "group": "g", "path": "/a"}]},
            ["projects[0]: no icon"],
        ),
        (
            {
                "groups": [{"name": "g", "icon": "G"}],
                "projects": [
                    {"name": "a", "group": "g", "path": "/a"},
                    {"name": "b", "icon": "B", "path": "/b"},
                    {"name": "a", "group": "g", "icon": "X", "path": "/c"},
                ],
            },
            ['projects[2]: duplicate label "g/a" (also projects[0])'],
        ),
    ],
)
def test_validation_errors(data, expected):
    assert errors(data) == expected


def test_duplicate_resolved_path(home, tmp_path):
    real = home / "code"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    data = {
        "projects": [
            {"name": "a", "icon": "A", "path": "~/code"},
            {"name": "b", "icon": "B", "path": str(real) + "/"},
            {"name": "c", "icon": "C", "path": str(tmp_path / "link")},
            {"name": "d", "icon": "D", "path": "~/code/sub"},
        ]
    }
    real = os.path.realpath(real)
    assert errors(data) == [
        f'projects[1]: duplicate path "{real}" (also projects[0])',
        f'projects[2]: duplicate path "{real}" (also projects[0])',
    ]


def test_same_name_in_different_groups_is_not_a_duplicate():
    data = {
        "groups": [{"name": "g", "icon": "G"}, {"name": "h", "icon": "H"}],
        "projects": [
            {"name": "a", "group": "g", "path": "/a"},
            {"name": "a", "group": "h", "path": "/b"},
            {"name": "a", "icon": "A", "path": "/c"},
        ],
    }
    assert len(registry.parse(data).projects) == 3


def test_validation_collects_every_error():
    data = {
        "groups": [{"name": "g"}, {"name": "h", "shade": 1}, {"name": "g"}],
        "projects": [
            {"name": "", "path": "/a"},
            {"name": "b", "group": "nope", "path": "/a"},
            {"name": "c", "icon": "C", "path": "/a"},
        ],
        "extra": True,
    }
    assert errors(data) == [
        'unknown key "extra"',
        'groups[1]: unknown key "shade"',
        'projects[0]: "name" must not be empty',
        'groups[2]: duplicate name "g" (also groups[0])',
        'projects[1]: group "nope" not found',
        "projects[1]: no icon",
        'projects[2]: duplicate path "/a" (also projects[1])',
    ]


# --- labels -------------------------------------------------------------------

LABELLED = Registry(
    groups=(Group(name="swb", icon="S"), Group(name="bare")),
    projects=(
        Project(name="edge", group="swb", path="/e"),
        Project(name="core", group="swb", icon="C", path="/c"),
        Project(name="tool", group="bare", icon="T", path="/t"),
        Project(name="notes", icon="N", path="/n"),
    ),
)


@pytest.mark.parametrize(
    ("name", "label", "bare"),
    [
        ("edge", "S swb/edge", "swb/edge"),
        ("core", "C swb/core", "swb/core"),
        ("tool", "T bare/tool", "bare/tool"),
        ("notes", "N notes", "notes"),
    ],
)
def test_labels(name, label, bare):
    [project] = [p for p in LABELLED.projects if p.name == name]
    assert LABELLED.label(project) == label
    assert project.bare_label == bare


def test_label_with_a_nerd_font_glyph():
    reg = Registry(
        groups=(Group(name="swb", icon=GLYPH),),
        projects=(Project(name="edge", group="swb", path="/e"),),
    )
    assert reg.label(reg.projects[0]) == f"{GLYPH} swb/edge"


def test_group_lookup():
    assert LABELLED.group("swb") == Group(name="swb", icon="S")
    assert LABELLED.group("nope") is None


# --- serialize ----------------------------------------------------------------


def test_registry_keeps_save_order():
    reg = Registry(
        groups=(Group(name="b"), Group(name="a")),
        projects=(
            Project(name="z", group="b", path="/1"),
            Project(name="y", icon="Y", path="/2"),
            Project(name="x", group="a", path="/3"),
            Project(name="w", group="b", path="/4"),
        ),
    )
    assert [g.name for g in reg.groups] == ["a", "b"]
    assert [p.bare_label for p in reg.projects] == ["y", "a/x", "b/w", "b/z"]
    assert reg == Registry(groups=reg.groups[::-1], projects=reg.projects[::-1])


def test_serialize(home):
    reg = registry.parse(tomllib.loads(SAMPLE))
    reg = Registry(
        groups=(*reg.groups, Group(name="aaa")),
        projects=(*reg.projects, Project(name="z", group="aaa", icon="Z", path=str(home))),
    )
    assert (
        registry.serialize(reg)
        == f"""\
[[groups]]
name = "aaa"

[[groups]]
name = "swb"
icon = "{GLYPH}"

[[projects]]
name = "notes"
icon = "N"
path = "/srv/notes"

[[projects]]
name = "z"
group = "aaa"
icon = "Z"
path = "~"

[[projects]]
name = "edge"
group = "swb"
path = "~/Developer/switchbit-dev/edge"
"""
    )


def test_serialize_empty_registry():
    assert registry.serialize(Registry()) == ""
    assert roundtrip(Registry()) == Registry()


@pytest.mark.parametrize(
    ("path", "written"),
    [
        ("{home}", "~"),
        ("{home}/", "~/"),
        ("{home}/a/b", "~/a/b"),
        ("{home}x/a", "{home}x/a"),
        ("/elsewhere/{home}", "/elsewhere/{home}"),
    ],
)
def test_serialize_collapses_home(home, path, written):
    path, written = path.format(home=home), written.format(home=home)
    reg = Registry(projects=(Project(name="a", icon="A", path=path),))
    assert tomllib.loads(registry.serialize(reg))["projects"][0]["path"] == written
    assert roundtrip(reg) == reg


TRICKY = [
    'quote " and backslash \\',
    "tab\tnewline\nreturn\rform\fbackspace\b",
    "nul\x00 unit\x1f del\x7f",
    "c1 \x80\x9f and bmp  and astral \U000f0338 \U0001f600",
    "\\u0041 not an escape",
    "'''\"\"\"",
]


@pytest.mark.parametrize("text", TRICKY)
def test_serialize_escapes_strings(home, text):
    path = text.replace("\x00", "")
    reg = Registry(
        groups=(Group(name=text, icon=text),),
        projects=(Project(name=text, group=text, icon=text, path=f"~/{path}"),),
    )
    serialized = registry.serialize(reg)
    for char in serialized:
        assert char in "\t\n" or not (ord(char) < 0x20 or ord(char) == 0x7F)
    assert roundtrip(reg) == reg
    assert roundtrip(reg).projects[0].path == f"{home}/{path}"


@pytest.mark.parametrize("path", ["relative/dir", ".", "./a", "~no-such-user-xyz/a"])
def test_relative_path_is_an_error(path):
    data = {"projects": [{"name": "a", "path": path}, {"name": "a", "icon": "A", "path": "/a"}]}
    assert errors(data) == ['projects[0]: "path" must be absolute or start with ~']


@pytest.mark.parametrize("path", ["/a\x00b", "~a\x00b/c", "~\x00"])
def test_path_with_nul_is_an_error(path):
    data = {"projects": [{"name": "a", "icon": "A", "path": path}]}
    assert errors(data) == ['projects[0]: "path" must not contain NUL']


def test_roundtrip_sample(home):
    reg = registry.parse(tomllib.loads(SAMPLE))
    assert roundtrip(reg) == reg
    assert registry.serialize(roundtrip(reg)) == registry.serialize(reg)


# --- save ---------------------------------------------------------------------


def test_save_and_load(home, tmp_path):
    reg = registry.parse(tomllib.loads(SAMPLE))
    path = tmp_path / "config" / "projects.toml"
    registry.save(reg, path)
    assert path.read_text(encoding="utf-8") == registry.serialize(reg)
    assert registry.load(path) == reg
    assert os.listdir(path.parent) == ["projects.toml"]


def test_save_through_a_symlink_keeps_the_symlink(home, tmp_path):
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "projects.toml"
    target.write_text("")
    config = tmp_path / "config"
    config.mkdir()
    link = config / "projects.toml"
    link.symlink_to(os.path.relpath(target, config))
    before = os.readlink(link)

    reg = registry.parse(tomllib.loads(SAMPLE))
    registry.save(reg, link)

    assert link.is_symlink()
    assert os.readlink(link) == before
    assert target.read_text(encoding="utf-8") == registry.serialize(reg)
    assert os.listdir(config) == ["projects.toml"]
    assert os.listdir(dotfiles) == ["projects.toml"]


def test_save_through_a_dangling_symlink_creates_the_target(home, tmp_path):
    target = tmp_path / "dotfiles" / "projects.toml"
    link = tmp_path / "projects.toml"
    link.symlink_to(target)
    reg = registry.parse(tomllib.loads(SAMPLE))
    registry.save(reg, link)
    assert link.is_symlink()
    assert registry.load(link) == reg


def test_save_keeps_the_file_mode(home, tmp_path):
    path = tmp_path / "projects.toml"
    path.write_text("")
    path.chmod(0o640)
    registry.save(registry.parse(tomllib.loads(SAMPLE)), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_save_new_file_respects_umask(home, tmp_path):
    path = tmp_path / "projects.toml"
    old = os.umask(0o027)
    try:
        registry.save(Registry(), path)
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_save_fsyncs_before_replacing(home, tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd)))
    monkeypatch.setattr(os, "replace", lambda *a: (calls.append("replace"), real_replace(*a)))
    registry.save(Registry(), tmp_path / "projects.toml")
    assert calls == ["fsync", "replace"]


def test_failed_save_leaves_the_file_alone(home, tmp_path, monkeypatch):
    path = tmp_path / "config" / "projects.toml"
    path.parent.mkdir()
    path.write_text("old")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        registry.save(registry.parse(tomllib.loads(SAMPLE)), path)
    assert path.read_text() == "old"
    assert os.listdir(path.parent) == ["projects.toml"]


def test_save_refuses_an_invalid_registry(tmp_path):
    path = tmp_path / "projects.toml"
    path.write_text("old")
    reg = Registry(projects=(Project(name="a", path="/a"),))
    with pytest.raises(RegistryError) as raised:
        registry.save(reg, path)
    assert raised.value.messages == ["projects[0]: no icon"]
    assert path.read_text() == "old"
