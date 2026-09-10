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


def make_app(name="vjepa2", chips=None, hidden=False) -> AppManifest:
    return AppManifest(
        name=name,
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=Path(f"/home/ttuser/code/tt-{name}"),
        manifest_path=Path(f"/home/ttuser/code/tt-{name}/.disco/app.yaml"),
        chips=chips,
        hidden=hidden,
    )


def test_index_lists_discovered_apps(monkeypatch):
    monkeypatch.setattr(
        app_mod, "discover_apps", lambda root: [make_app()]
    )
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "stopped")

    client = TestClient(app_mod.create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "vjepa2" in response.text
    assert "V-JEPA2 demo" in response.text
    assert "stopped" in response.text


def test_index_excludes_hidden_app_but_view_still_reaches_it(monkeypatch):
    hidden = make_app(name="discolike", hidden=True)
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [hidden])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "ready")

    client = TestClient(app_mod.create_app())
    index_response = client.get("/")
    view_response = client.get("/apps/discolike/view")

    assert "V-JEPA2 demo" not in index_response.text  # the hidden app's own description
    assert view_response.status_code == 200
    assert "V-JEPA2 demo" in view_response.text


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
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "ready")
    calls = []

    def fake_start(app):
        calls.append(app)
        return completed(returncode=0)

    monkeypatch.setattr(app_mod.units, "start_app", fake_start)

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/start")

    assert response.status_code == 200
    assert calls == [target]
    assert "ready" in response.text


def test_stop_endpoint_calls_units_stop_app(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "stopped")
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
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "stopped")
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
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "ready")
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


def test_view_endpoint_shows_iframe_when_active(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "ready")
    monkeypatch.setattr(app_mod.gozer_status, "get_status", lambda: None)

    client = TestClient(app_mod.create_app())
    response = client.get("/apps/vjepa2/view")

    assert response.status_code == 200
    assert "vjepa2" in response.text
    assert 'id="visor-frame-vjepa2"' in response.text
    assert '+ ":7860"' in response.text  # port set client-side via location.hostname
    assert 'href="/"' in response.text  # menu link back to the catalog


def test_view_endpoint_shows_placeholder_when_not_active(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "stopped")
    monkeypatch.setattr(app_mod.gozer_status, "get_status", lambda: None)

    client = TestClient(app_mod.create_app())
    response = client.get("/apps/vjepa2/view")

    assert response.status_code == 200
    assert "not running" in response.text
    assert "<iframe" not in response.text


def test_view_endpoint_404s_for_unknown_app(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [])

    client = TestClient(app_mod.create_app())
    response = client.get("/apps/nonexistent/view")

    assert response.status_code == 404


def test_view_start_swaps_in_iframe(monkeypatch):
    target = make_app()
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [target])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "ready")
    calls = []
    monkeypatch.setattr(
        app_mod.units,
        "start_app",
        lambda app: (calls.append(app), completed(returncode=0))[1],
    )

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/view/start")

    assert response.status_code == 200
    assert calls == [target]
    assert 'id="visor-frame-vjepa2"' in response.text
    assert '+ ":7860"' in response.text  # port set client-side via location.hostname


def test_view_stop_swaps_in_placeholder(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "effective_status", lambda app: "stopped")
    monkeypatch.setattr(app_mod.units, "stop_app", lambda name: completed(returncode=0))

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/view/stop")

    assert response.status_code == 200
    assert "not running" in response.text
