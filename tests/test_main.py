# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from fastapi import FastAPI

from discolike.main import app


def test_main_exposes_fastapi_app():
    assert isinstance(app, FastAPI)
