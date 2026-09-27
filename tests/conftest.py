from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A from-scratch plugin environment, applied to this process and returned for children."""
    for name in list(os.environ):
        if name.startswith(("HERDR_", "XDG_")):
            monkeypatch.delenv(name)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    values = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join([str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
        "HERDR_PLUGIN_ID": "herdr-projects",
        "HERDR_PLUGIN_ROOT": str(ROOT),
        "HERDR_PLUGIN_STATE_DIR": str(state_dir),
    }
    for name, value in values.items():
        if name != "PATH":
            monkeypatch.setenv(name, value)
    return values


def run_plugin(env: dict[str, str], *args: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(ROOT / "bin/herdr-projects"), *args],
        cwd=ROOT,
        env={**env, **extra},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )
