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
