# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from discolike.manifest import AppManifest

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"


def unit_name(app_name: str) -> str:
    return f"discolike-{app_name}.service"


def unit_file_path(app_name: str) -> Path:
    return UNIT_DIR / unit_name(app_name)


def gozer_available() -> bool:
    return shutil.which("gozer") is not None


def _resolve_launch(app: AppManifest) -> str:
    """Resolve a relative launch command's executable against source_dir.

    systemd's ExecStart= requires its first token to be either an absolute
    path or a bare filename with no slashes -- it rejects a relative path
    containing a slash outright. Manifests commonly declare launch commands
    like ".venv/bin/python app.py" (relative to the app's source_dir), which
    is exactly the form systemd can't load. Resolve that first token to an
    absolute path so the rendered unit is always loadable, regardless of
    whether gozer ends up wrapping it.
    """
    head, sep, rest = app.launch.partition(" ")
    if "/" in head and not head.startswith("/"):
        head = str(app.source_dir / head)
    return f"{head}{sep}{rest}" if sep else head


def build_launch_command(app: AppManifest, use_gozer: bool) -> str:
    launch = _resolve_launch(app)
    if use_gozer and app.chips is not None:
        gozer_bin = shutil.which("gozer") or "gozer"
        return (
            f'{gozer_bin} run --chips {app.chips} --who "discolike:{app.name}" '
            f'--reason "gradio demo" -- {launch}'
        )
    return launch


def render_unit_file(app: AppManifest, use_gozer: bool) -> str:
    exec_start = build_launch_command(app, use_gozer)
    return (
        "[Unit]\n"
        f"Description=tt-discolike managed app: {app.name}\n"
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
