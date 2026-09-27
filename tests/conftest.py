from __future__ import annotations

import json
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


FAKE_HERDR = ROOT / "tests" / "fake_herdr"


class FakeHerdr:
    """Drives tests/fake_herdr/herdr: set its answers, then read back its calls."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.responses: dict[str, list[dict]] = {}

    def respond(self, prefix: str, *answers: dict) -> None:
        self.responses[prefix] = list(answers)
        (self.dir / "responses.json").write_text(json.dumps(self.responses))

    def calls(self) -> list[list[str]]:
        log = self.dir / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    @staticmethod
    def ok(result: object = None) -> dict:
        body = {"type": "ok"} if result is None else result
        return {"stdout": json.dumps({"id": "cli:fake", "result": body}) + "\n"}

    @staticmethod
    def fixture(name: str) -> dict:
        return {"stdout": (FAKE_HERDR / "fixtures" / f"{name}.json").read_text(encoding="utf-8")}

    @staticmethod
    def error(message: str, code: str = "fake_error", stream: str = "stderr") -> dict:
        body = {"id": "cli:fake", "error": {"code": code, "message": message}}
        return {stream: json.dumps(body) + "\n", "exit": 1}


@pytest.fixture
def fake_herdr(env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeHerdr:
    """Puts the fake first on PATH, here and in `env` for child processes."""
    directory = tmp_path / "fake-herdr"
    directory.mkdir()
    values = {
        "FAKE_HERDR_DIR": str(directory),
        # Should anything still find the real herdr, it has no server to reach.
        "HERDR_SOCKET_PATH": str(tmp_path / "no-herdr.sock"),
    }
    env.update(values, PATH=os.pathsep.join([str(FAKE_HERDR), env["PATH"]]))
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", os.pathsep.join([str(FAKE_HERDR), os.environ["PATH"]]))
    return FakeHerdr(directory)


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
