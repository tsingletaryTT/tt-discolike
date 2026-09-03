from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from disco import units
from disco.manifest import AppManifest, BrokenManifest, discover_apps

TEMPLATES_DIR = Path(__file__).parent / "templates"


def scan_root() -> Path:
    return Path(os.environ.get("DISCO_SCAN_ROOT", str(Path.home() / "code")))


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

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "index.html", {"apps": catalog_rows()}
        )

    @app.post("/apps/{name}/start", response_class=HTMLResponse)
    def start(request: Request, name: str) -> HTMLResponse:
        target = find_app(name)
        if target is not None:
            units.start_app(target)
        return templates.TemplateResponse(
            request, "_catalog.html", {"apps": catalog_rows()}
        )

    @app.post("/apps/{name}/stop", response_class=HTMLResponse)
    def stop(request: Request, name: str) -> HTMLResponse:
        units.stop_app(name)
        return templates.TemplateResponse(
            request, "_catalog.html", {"apps": catalog_rows()}
        )

    return app
