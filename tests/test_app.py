from pathlib import Path

from fastapi.testclient import TestClient

import disco.app as app_mod
from disco.manifest import AppManifest, BrokenManifest


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
    monkeypatch.setattr(app_mod.units, "start_app", lambda app: calls.append(app))

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/start")

    assert response.status_code == 200
    assert calls == [target]
    assert "active" in response.text


def test_stop_endpoint_calls_units_stop_app(monkeypatch):
    monkeypatch.setattr(app_mod, "discover_apps", lambda root: [make_app()])
    monkeypatch.setattr(app_mod.units, "app_status", lambda name: "inactive")
    calls = []
    monkeypatch.setattr(app_mod.units, "stop_app", lambda name: calls.append(name))

    client = TestClient(app_mod.create_app())
    response = client.post("/apps/vjepa2/stop")

    assert response.status_code == 200
    assert calls == ["vjepa2"]
