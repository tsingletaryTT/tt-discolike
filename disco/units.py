from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from disco.manifest import AppManifest

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"


def unit_name(app_name: str) -> str:
    return f"disco-{app_name}.service"


def unit_file_path(app_name: str) -> Path:
    return UNIT_DIR / unit_name(app_name)


def gozer_available() -> bool:
    return shutil.which("gozer") is not None


def build_launch_command(app: AppManifest, use_gozer: bool) -> str:
    if use_gozer and app.chips is not None:
        return (
            f'gozer run --chips {app.chips} --who "disco:{app.name}" '
            f'--reason "gradio demo" -- {app.launch}'
        )
    return app.launch


def render_unit_file(app: AppManifest, use_gozer: bool) -> str:
    exec_start = build_launch_command(app, use_gozer)
    return (
        "[Unit]\n"
        f"Description=tt-disco managed app: {app.name}\n"
        "\n"
        "[Service]\n"
        f"WorkingDirectory={app.source_dir}\n"
        f"ExecStart={exec_start}\n"
        "Restart=no\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def write_unit_file(app: AppManifest) -> Path:
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    path = unit_file_path(app.name)
    path.write_text(render_unit_file(app, use_gozer=gozer_available()))
    return path


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def start_app(app: AppManifest) -> subprocess.CompletedProcess:
    write_unit_file(app)
    systemctl("daemon-reload")
    return systemctl("start", unit_name(app.name))


def stop_app(app_name: str) -> subprocess.CompletedProcess:
    return systemctl("stop", unit_name(app_name))


def app_status(app_name: str) -> str:
    result = systemctl("is-active", unit_name(app_name))
    return result.stdout.strip() or "unknown"
