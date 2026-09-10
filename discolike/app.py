# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from discolike import gozer_status, units
from discolike.manifest import AppManifest, BrokenManifest, discover_apps

TEMPLATES_DIR = Path(__file__).parent / "templates"


def scan_root() -> Path:
    return Path(os.environ.get("DISCOLIKE_SCAN_ROOT", str(Path.home() / "code")))


def _mark_row_failed(rows: list[dict], name: str, stderr: str) -> None:
    """Mutate the row for `name` in-place to show a start/stop command failure.

    Reuses the "broken" row rendering path (the same one used for a
    BrokenManifest) so the catalog table surfaces the immediate command
    failure instead of silently leaving the row's prior status displayed.
    """
    message = stderr.strip() or "command failed with no output"
    for row in rows:
        if row.get("name") == name:
            row["broken"] = True
            row["error"] = f"command failed: {message}"
            return
    # App disappeared from discovery between the request and the response
    # (e.g. manifest removed mid-flight) -- still surface the failure.
    rows.append({"name": name, "broken": True, "error": f"command failed: {message}"})


def create_app() -> FastAPI:
    app = FastAPI()
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def catalog_rows() -> list[dict]:
        rows: list[dict] = []
        for entry in discover_apps(scan_root()):
            if isinstance(entry, BrokenManifest):
                rows.append(
                    {
                        "name": entry.manifest_path.parent.parent.name,
                        "broken": True,
                        "error": entry.error,
                    }
                )
            else:
                if entry.hidden:
                    # Not listed, but still fully controllable via its own
                    # direct routes (start/stop/view) -- "hidden" means "not
                    # in the menu", not "disabled". The catalog cataloging
                    # itself (tt-discolike's own .disco/app.yaml, dogfooding
                    # the manifest convention) is the motivating case: it
                    # shouldn't appear as a card in its own listing.
                    continue
                rows.append(
                    {
                        "name": entry.name,
                        "description": entry.description,
                        "port": entry.port,
                        "broken": False,
                        "status": units.app_status(entry.name),
                    }
                )
        return rows

    def find_app(name: str) -> AppManifest | None:
        for entry in discover_apps(scan_root()):
            if isinstance(entry, AppManifest) and entry.name == name:
                return entry
        return None

    def app_view_row(name: str, target: AppManifest | None) -> dict:
        if target is None:
            return {"name": name, "description": "", "port": None, "status": "unknown"}
        return {
            "name": target.name,
            "description": target.description,
            "port": target.port,
            "status": units.app_status(target.name),
        }

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"apps": catalog_rows(), "gozer": gozer_status.get_status()},
        )

    @app.get("/gozer-status", response_class=HTMLResponse)
    def gozer_status_fragment(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "_gozer_status.html", {"gozer": gozer_status.get_status()}
        )

    @app.post("/apps/{name}/start", response_class=HTMLResponse)
    def start(request: Request, name: str) -> HTMLResponse:
        rows = catalog_rows()
        target = find_app(name)
        if target is not None:
            result = units.start_app(target)
            if result.returncode != 0:
                _mark_row_failed(rows, name, result.stderr)
            else:
                rows = catalog_rows()
        return templates.TemplateResponse(
            request, "_catalog.html", {"apps": rows}
        )

    @app.post("/apps/{name}/stop", response_class=HTMLResponse)
    def stop(request: Request, name: str) -> HTMLResponse:
        rows = catalog_rows()
        result = units.stop_app(name)
        if result.returncode != 0:
            _mark_row_failed(rows, name, result.stderr)
        else:
            rows = catalog_rows()
        return templates.TemplateResponse(
            request, "_catalog.html", {"apps": rows}
        )

    @app.get("/apps/{name}/view", response_class=HTMLResponse)
    def app_view(request: Request, name: str) -> HTMLResponse:
        target = find_app(name)
        if target is None:
            return PlainTextResponse(f"no such app: {name!r}", status_code=404)
        return templates.TemplateResponse(
            request,
            "view.html",
            {"app": app_view_row(name, target), "gozer": gozer_status.get_status()},
        )

    @app.post("/apps/{name}/view/start", response_class=HTMLResponse)
    def app_view_start(request: Request, name: str) -> HTMLResponse:
        target = find_app(name)
        error = None
        if target is not None:
            result = units.start_app(target)
            if result.returncode != 0:
                error = result.stderr.strip() or "command failed with no output"
        return templates.TemplateResponse(
            request,
            "_app_view.html",
            {"app": app_view_row(name, find_app(name)), "error": error},
        )

    @app.post("/apps/{name}/view/stop", response_class=HTMLResponse)
    def app_view_stop(request: Request, name: str) -> HTMLResponse:
        result = units.stop_app(name)
        error = None
        if result.returncode != 0:
            error = result.stderr.strip() or "command failed with no output"
        return templates.TemplateResponse(
            request,
            "_app_view.html",
            {"app": app_view_row(name, find_app(name)), "error": error},
        )

    return app
