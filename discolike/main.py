# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from __future__ import annotations

import os

import uvicorn

from discolike.app import create_app

app = create_app()


def run() -> None:
    host = os.environ.get("DISCOLIKE_HOST", "127.0.0.1")
    port = int(os.environ.get("DISCOLIKE_CATALOG_PORT", "8760"))
    uvicorn.run("discolike.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
