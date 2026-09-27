from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT

SCRIPT = ROOT / "scripts" / "gen-glyphs.py"
FIXTURE = ROOT / "tests" / "fixtures" / "glyphnames.json"
COMMITTED = ROOT / "lib" / "herdr_projects" / "glyphs.tsv"


def generate(source: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(source), "-o", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generates_sorted_tsv_without_metadata(tmp_path):
    output = tmp_path / "glyphs.tsv"
    result = generate(FIXTURE, output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes().decode("utf-8") == (
        "# nerd-fonts 9.8.7\n"
        "\tcod-account\n"
        "\tcod-add\n"
        "\tcod-add_small\n"
        "\U000f07d8\tmd-zodiac_leo\n"
        "\toct-zap\n"
    )


def test_output_is_deterministic(tmp_path):
    first, second = tmp_path / "a.tsv", tmp_path / "b.tsv"
    assert generate(FIXTURE, first).returncode == 0
    assert generate(FIXTURE, second).returncode == 0
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"cod-add": {"char": "", "code": "ea60"}}, "no METADATA version"),
        ({"METADATA": {"version": "1 2"}}, "no METADATA version"),
        ({"METADATA": {"version": "1"}, "a\tb": {"char": "x"}}, "bad name"),
        ({"METADATA": {"version": "1"}, "a": {"char": "xy"}}, "a: bad char"),
        ({"METADATA": {"version": "1"}, "a": {"char": "#"}}, "a: bad char"),
        ({"METADATA": {"version": "1"}, "a": {"code": "ea60"}}, "a: bad char"),
    ],
)
def test_rejects_malformed_input(tmp_path, data, message):
    source = tmp_path / "glyphnames.json"
    source.write_text(json.dumps(data))
    output = tmp_path / "glyphs.tsv"
    result = generate(source, output)
    assert result.returncode == 1
    assert message in result.stderr
    assert not output.exists()


def test_committed_tsv():
    lines = COMMITTED.read_text(encoding="utf-8").split("\n")
    assert re.fullmatch(r"# nerd-fonts \d+\.\d+\.\d+", lines[0])
    assert lines[-1] == ""
    rows = [line.split("\t") for line in lines[1:-1]]
    assert all(len(row) == 2 and len(row[0]) == 1 for row in rows)
    names = [name for _, name in rows]
    assert names == sorted(names)
    assert "METADATA" not in names
