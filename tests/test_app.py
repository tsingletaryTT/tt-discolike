# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

import discolike.app as app_mod
from discolike.manifest import AppManifest, BrokenManifest


def completed(returncode=0, stderr="", stdout=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def make_app(name="vjepa2", chips=None) -> AppManifest:
    return AppManifest(
        name=name,
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=Path(f"/home/ttuser/code/tt-{name}"),
        manifest_path=Path(f"/home/ttuser/code/tt-{name}/.disco/app.yaml"),
        chips=chips,
    )


def test_index_lists_discovered_apps(monkeypatch):
    monkeypatch.setattr(
        app_mod, "discover_apps", lambda root: [make_app()]
    )
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "inactive")

    client = TestClient(app_mod.create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "vjepa2" in response.text
    assert "V-JEPA2 demo" in response.text
    assert "inactive" in response.text


def test_index_shows_broken_manifest_error(monkeypatch):
    broken = BrokenManifest(
        manifest_path=Path("/home/ttuser/code/broken/.disco/app.yaml"),
        error="missing required field(s): port",
    )
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [broken])

    client = TestClient(app_mod.create_app())
    response = client.get("/")

    assert "broken" in response.text
    assert "missing required field(s): port" in response.text


def test_start_endpoint_calls_units_start_app(monkeypatch):
    target = make_app()
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [target])
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "active")
    calls = []

    def fake_start(app):
        calls.append(app)
        return completed(returncode=0)

    monkeypatch.setattr(app_mod.units, "start_app", fake_start)

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/start")

    assert response.status_code == 200
    assert calls == [target]
    assert "active" in response.text


def test_stop_endpoint_calls_units_stop_app(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "inactive")
    calls = []

    def fake_stop(name):
        calls.append(name)
        return completed(returncode=0)

    monkeypatch.setattr(app_mod.units, "stop_app", fake_stop)

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/stop")

    assert response.status_code == 200
    assert calls == ["vjepa2"]


def test_start_endpoint_shows_error_on_failure(monkeypatch):
    target = make_app()
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [target])
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "inactive")
    monkeypatch.setattr(
        app_mod.units,
        "start_app",
        lambda app: completed(returncode=1, stderr="Failed to start discolike-vjepa2.service: bad unit"),
    )

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/start")

    assert response.status_code == 200
    assert "vjepa2" in response.text
    assert "Failed to start discolike-vjepa2.service: bad unit" in response.text


def test_stop_endpoint_shows_error_on_failure(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "active")
    monkeypatch.setattr(
        app_mod.units,
        "stop_app",
        lambda name: completed(returncode=1, stderr="Failed to stop discolike-vjepa2.service: unit not loaded"),
    )

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/stop")

    assert response.status_code == 200
    assert "vjepa2" in response.text
    assert "Failed to stop discolike-vjepa2.service: unit not loaded" in response.text
