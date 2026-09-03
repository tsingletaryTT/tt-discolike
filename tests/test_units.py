from pathlib import Path

from disco.manifest import AppManifest
from disco.units import build_launch_command, render_unit_file, unit_name


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
    assert unit_name("vjepa2") == "disco-vjepa2.service"


def test_build_launch_command_without_gozer():
    app = make_app(chips=1)
    assert build_launch_command(app, use_gozer=False) == ".venv/bin/python app.py"


def test_build_launch_command_without_chips_declared():
    app = make_app(chips=None)
    assert build_launch_command(app, use_gozer=True) == ".venv/bin/python app.py"


def test_build_launch_command_with_gozer_and_chips():
    app = make_app(chips=1)
    result = build_launch_command(app, use_gozer=True)
    assert result == (
        'gozer run --chips 1 --who "disco:vjepa2" '
        '--reason "gradio demo" -- .venv/bin/python app.py'
    )


def test_render_unit_file_contains_working_directory_and_exec_start():
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=True)
    assert "WorkingDirectory=/home/ttuser/code/tt-vjepa2" in content
    assert 'ExecStart=gozer run --chips 1 --who "disco:vjepa2"' in content
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content


import disco.units as units_mod
from disco.units import app_status, start_app, stop_app, write_unit_file


class FakeCompletedProcess:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_write_unit_file_writes_rendered_content(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    app = make_app(chips=1)

    path = write_unit_file(app)

    assert path == tmp_path / "disco-vjepa2.service"
    assert "ExecStart=.venv/bin/python app.py" in path.read_text()


def test_start_app_writes_unit_reloads_and_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    start_app(make_app())

    assert (tmp_path / "disco-vjepa2.service").exists()
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "start", "disco-vjepa2.service"],
    ]


def test_stop_app_calls_systemctl_stop(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    stop_app("vjepa2")

    assert calls == [["systemctl", "--user", "stop", "disco-vjepa2.service"]]


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
