# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from pathlib import Path

from discolike.manifest import AppManifest
from discolike.units import build_launch_command, render_unit_file, unit_name
import discolike.units as units_mod


def make_app(chips=None) -> AppManifest:
    return AppManifest(
        name="vjepa2",
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=Path("/home/ttuser/code/tt-vjepa2"),
        manifest_path=Path("/home/ttuser/code/tt-vjepa2/.disco/app.yaml"),
        chips=chips,
    )


def test_unit_name():
    assert unit_name("vjepa2") == "discolike-vjepa2.service"


def test_build_launch_command_without_gozer():
    app = make_app(chips=1)
    expected = str(app.source_dir) + "/.venv/bin/python app.py"
    assert build_launch_command(app, use_gozer=False) == expected


def test_build_launch_command_without_chips_declared():
    app = make_app(chips=None)
    expected = str(app.source_dir) + "/.venv/bin/python app.py"
    assert build_launch_command(app, use_gozer=True) == expected


def test_build_launch_command_with_gozer_and_chips(monkeypatch):
    monkeypatch.setattr(units_mod.shutil, "which",
                        lambda name: "/home/ttuser/.local/bin/gozer" if name == "gozer" else None)
    app = make_app(chips=1)
    result = build_launch_command(app, use_gozer=True)
    resolved_launch = str(app.source_dir) + "/.venv/bin/python app.py"
    assert result == (
        '/home/ttuser/.local/bin/gozer run --chips 1 --who "discolike:vjepa2" '
        f'--reason "gradio demo" -- {resolved_launch}'
    )


def test_build_launch_command_falls_back_to_bare_name_if_which_fails(monkeypatch):
    monkeypatch.setattr(units_mod.shutil, "which", lambda name: None)
    app = make_app(chips=1)
    result = build_launch_command(app, use_gozer=True)
    assert result.startswith("gozer run")


def test_render_unit_file_contains_working_directory_and_exec_start(monkeypatch):
    monkeypatch.setattr(units_mod.shutil, "which",
                        lambda name: "/home/ttuser/.local/bin/gozer" if name == "gozer" else None)
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=True)
    assert "WorkingDirectory=/home/ttuser/code/tt-vjepa2" in content
    assert 'ExecStart=/home/ttuser/.local/bin/gozer run --chips 1 --who "discolike:vjepa2"' in content
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content


def test_render_unit_file_pins_gozer_reset_cmd_when_tt_smi_resolves(monkeypatch):
    """Regression test for the auto-release reset_ok=false bug: without a
    pinned GOZER_RESET_CMD, gozer's own `tt-smi -r` call fails under
    systemd's restricted PATH every single time."""
    resolved = {"gozer": "/home/ttuser/.local/bin/gozer",
                "tt-smi": "/home/ttuser/.local/bin/tt-smi"}
    monkeypatch.setattr(units_mod.shutil, "which", lambda name: resolved.get(name))
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=True)
    assert "Environment=GOZER_RESET_CMD=/home/ttuser/.local/bin/tt-smi" in content
    # placed in [Service], before ExecStart, not leaked into [Unit]/[Install]
    assert content.index("Environment=GOZER_RESET_CMD=") > content.index("[Service]")
    assert content.index("Environment=GOZER_RESET_CMD=") < content.index("ExecStart=")


def test_render_unit_file_omits_reset_cmd_when_tt_smi_not_found(monkeypatch):
    monkeypatch.setattr(units_mod.shutil, "which",
                        lambda name: "/home/ttuser/.local/bin/gozer" if name == "gozer" else None)
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=True)
    assert "GOZER_RESET_CMD" not in content


def test_render_unit_file_omits_reset_cmd_when_not_using_gozer(monkeypatch):
    resolved = {"gozer": "/home/ttuser/.local/bin/gozer",
                "tt-smi": "/home/ttuser/.local/bin/tt-smi"}
    monkeypatch.setattr(units_mod.shutil, "which", lambda name: resolved.get(name))
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=False)
    assert "GOZER_RESET_CMD" not in content


def test_render_unit_file_omits_reset_cmd_when_app_declares_no_chips(monkeypatch):
    resolved = {"gozer": "/home/ttuser/.local/bin/gozer",
                "tt-smi": "/home/ttuser/.local/bin/tt-smi"}
    monkeypatch.setattr(units_mod.shutil, "which", lambda name: resolved.get(name))
    app = make_app(chips=None)
    content = render_unit_file(app, use_gozer=True)
    assert "GOZER_RESET_CMD" not in content


import shutil as _shutil

import pytest


@pytest.mark.skipif(
    _shutil.which("systemd-analyze") is None,
    reason="systemd-analyze not available on this system",
)
def test_render_unit_file_is_loadable_by_systemd_without_gozer(tmp_path, monkeypatch):
    """Regression test for the no-gozer relative-path ExecStart bug.

    systemd-analyze verify rejects a unit whose ExecStart= first token is a
    relative path containing a slash. This renders a real unit file (via the
    same render_unit_file() the app uses) with gozer unavailable, and checks
    that systemd itself considers it loadable.
    """
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)

    # systemd-analyze verify also checks that the ExecStart= executable
    # actually exists and is executable -- give it a real one, rooted in a
    # real source_dir, so the only thing under test is path *resolution*
    # (relative-with-slash -> absolute), not executable presence.
    source_dir = tmp_path / "tt-vjepa2"
    venv_bin = source_dir / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 0\n")
    fake_python.chmod(0o755)

    app = AppManifest(
        name="vjepa2",
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=source_dir,
        manifest_path=source_dir / ".disco" / "app.yaml",
        chips=None,
    )
    content = render_unit_file(app, use_gozer=False)

    unit_path = tmp_path / "discolike-vjepa2.service"
    unit_path.write_text(content)

    result = units_mod.subprocess.run(
        ["systemd-analyze", "verify", str(unit_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"systemd-analyze verify failed:\nstdout={result.stdout}\nstderr={result.stderr}\n"
        f"unit content:\n{content}"
    )


import discolike.units as units_mod
from discolike.units import app_status, start_app, stop_app, write_unit_file


class FakeCompletedProcess:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_write_unit_file_writes_rendered_content(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    app = make_app(chips=1)

    path = write_unit_file(app)

    assert path == tmp_path / "discolike-vjepa2.service"
    expected_exec_start = "ExecStart=" + str(app.source_dir) + "/.venv/bin/python app.py"
    assert expected_exec_start in path.read_text()


def test_start_app_writes_unit_reloads_and_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    start_app(make_app())

    assert (tmp_path / "discolike-vjepa2.service").exists()
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "start", "discolike-vjepa2.service"],
    ]


def test_stop_app_calls_systemctl_stop(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    stop_app("vjepa2")

    assert calls == [["systemctl", "--user", "stop", "discolike-vjepa2.service"]]


def test_app_status_returns_stripped_stdout(monkeypatch):
    monkeypatch.setattr(
        units_mod.subprocess, "run", lambda cmd, **kwargs: FakeCompletedProcess(stdout="active\n")
    )

    assert app_status("vjepa2") == "active"


def test_app_status_returns_unknown_for_empty_stdout(monkeypatch):
    monkeypatch.setattr(
        units_mod.subprocess, "run", lambda cmd, **kwargs: FakeCompletedProcess(stdout="")
    )

    assert app_status("vjepa2") == "unknown"
