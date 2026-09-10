# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

from discolike.manifest import AppManifest

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
LOCAL_BIN_DIR = Path.home() / ".local" / "bin"


def unit_name(app_name: str) -> str:
    return f"discolike-{app_name}.service"


def unit_file_path(app_name: str) -> Path:
    return UNIT_DIR / unit_name(app_name)


def resolve_binary(name: str) -> str | None:
    """Resolve `name` to an absolute path without relying solely on the
    calling process's own $PATH.

    systemd --user's default PATH excludes ~/.local/bin (where both `gozer`
    and `tt-smi` actually live on this box) -- that's exactly why
    build_launch_command below resolves gozer to an absolute path before
    writing it into a generated unit's ExecStart. But tt-discolike itself
    now also runs as a systemd --user unit (see the self-manifest), so its
    own process PATH is just as restricted as any app it launches: a plain
    `shutil.which(name)` called from *inside* tt-discolike silently returns
    None here too, not just inside a unit tt-discolike generates for
    someone else. That broke two things at once the day this was caught:
    the live gozer status bar (always rendered hidden) and this same
    gozer/tt-smi resolution for wrapping *other* apps' launch commands
    (silently falling back to a bare, unresolvable name again -- the
    original 203/EXEC bug, reintroduced).
    """
    found = shutil.which(name)
    if found:
        return found
    fallback = LOCAL_BIN_DIR / name
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    return None


def gozer_available() -> bool:
    return resolve_binary("gozer") is not None


def _resolve_tt_smi() -> str | None:
    return resolve_binary("tt-smi")


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
        gozer_bin = resolve_binary("gozer") or "gozer"
        return (
            f'{gozer_bin} run --chips {app.chips} --who "discolike:{app.name}" '
            f'--reason "gradio demo" -- {launch}'
        )
    return launch


def render_unit_file(app: AppManifest, use_gozer: bool) -> str:
    exec_start = build_launch_command(app, use_gozer)

    # systemd user-manager services do not inherit an interactive shell's
    # PATH (it defaults to something like /usr/bin:/bin), so `gozer run`'s
    # own internal `tt-smi -r` call -- resolved by bare name -- fails to find
    # the binary and every auto-release under discolike reports a failed
    # reset (gozer's own history.jsonl shows this: reset_ok is false for
    # every discolike-launched lease and true for every other one). Pin
    # gozer's reset command to an absolute path via its documented
    # GOZER_RESET_CMD override so the unit's restricted PATH can't break it.
    reset_cmd_line = ""
    if use_gozer and app.chips is not None:
        tt_smi = _resolve_tt_smi()
        if tt_smi:
            reset_cmd_line = f"Environment=GOZER_RESET_CMD={tt_smi}\n"

    return (
        "[Unit]\n"
        f"Description=tt-discolike managed app: {app.name}\n"
        "\n"
        "[Service]\n"
        f"WorkingDirectory={app.source_dir}\n"
        f"{reset_cmd_line}"
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


def port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def effective_status(app: AppManifest) -> str:
    """Fold systemd's raw is-active state and an actual port check into a
    single UI-facing status.

    systemd marks a Type=simple unit "active" the instant the process forks,
    not when the gradio server inside it is actually listening -- these
    demos routinely spend seconds to minutes loading a model or waiting on a
    gozer chip lease after the process starts. Treat "active" as merely
    "loading" until the declared port actually accepts a connection.
    """
    raw = app_status(app.name)
    if raw == "active":
        return "ready" if port_open("127.0.0.1", app.port) else "loading"
    if raw == "activating":
        return "loading"
    if raw == "deactivating":
        return "stopping"
    if raw == "inactive":
        return "stopped"
    if raw == "failed":
        return "failed"
    return "unknown"
