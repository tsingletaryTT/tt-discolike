# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
"""Optional live gozer (chip-leasing) status for the catalog's status bar.

gozer is a soft dependency for tt-discolike as a whole (see CLAUDE.md) --
this module follows the same rule: if the `gozer` binary isn't on PATH, or
`gozer status --json` doesn't behave, callers get `None` and render nothing,
rather than the catalog page failing to load.
"""
from __future__ import annotations

import json
import shutil
import subprocess

STATUS_TIMEOUT_SECONDS = 3


def get_status() -> dict | None:
    """Return parsed `gozer status --json` output, or None if unavailable."""
    if shutil.which("gozer") is None:
        return None
    try:
        result = subprocess.run(
            ["gozer", "status", "--json"],
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
