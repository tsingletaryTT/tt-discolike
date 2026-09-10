# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
"""Optional live gozer (chip-leasing) status for the catalog's status bar.

gozer is a soft dependency for tt-discolike as a whole (see CLAUDE.md) --
this module follows the same rule: if the `gozer` binary isn't on PATH, or
`gozer status --json` doesn't behave, callers get `None` and render nothing,
rather than the catalog page failing to load.

Resolves gozer via units.resolve_binary(), not a bare shutil.which("gozer")
-- tt-discolike itself runs as a systemd --user unit (its own self-manifest),
whose default PATH excludes ~/.local/bin the same way any unit it generates
for another app does. A bare shutil.which() call here returns None from
*inside* that unit even though gozer is genuinely installed, which is
exactly what silently hid this status bar the day that regression landed.
"""
from __future__ import annotations

import json
import subprocess

from discolike.units import resolve_binary

STATUS_TIMEOUT_SECONDS = 3


def get_status() -> dict | None:
    """Return parsed `gozer status --json` output, or None if unavailable."""
    gozer_bin = resolve_binary("gozer")
    if gozer_bin is None:
        return None
    try:
        result = subprocess.run(
            [gozer_bin, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
