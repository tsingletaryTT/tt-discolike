# tt-disco Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tt-disco — a local FastAPI catalog/launcher that discovers gradio demo apps via a `.disco/app.yaml` manifest convention and runs them as `systemd --user` units, optionally chip-leased via `gozer`.

**Architecture:** A `disco` Python package with three pure-logic modules (`manifest.py` for discovery/parsing, `units.py` for systemd unit rendering/control) and one thin web layer (`app.py`, a FastAPI app with Jinja2+htmx templates), plus a `main.py` entrypoint. Manifest parsing and unit-file rendering are pure functions tested without any real systemd/gozer calls; `units.py`'s `systemctl()` wrapper is the one seam that shells out, and it's tested by monkeypatching `subprocess.run`.

**Tech Stack:** Python 3.10+, FastAPI, Jinja2, htmx (via CDN script tag), PyYAML, uvicorn, pytest, httpx (for FastAPI's TestClient).

**Spec:** `docs/superpowers/specs/2026-09-03-tt-disco-design.md`

## Global Constraints

- Manifest file: `.disco/app.yaml` at each app repo's root, required fields `name`, `description`, `port`, `launch`; optional field `chips` (int).
- Discovery root defaults to `~/code`, overridable via `DISCO_SCAN_ROOT` env var; scans exactly `<root>/*/.disco/app.yaml` (one level deep).
- systemd unit name: `disco-<name>.service`, written to `~/.config/systemd/user/`.
- gozer is a soft dependency: wrap `ExecStart` with `gozer run --chips <N> --who "disco:<name>" --reason "gradio demo" -- <launch>` only if `shutil.which("gozer")` succeeds AND the manifest declares `chips`; otherwise run `launch` unmodified.
- No Docker, no reverse proxy, no custom hostnames — links are plain `http://localhost:<port>`.
- Catalog web UI runs on its own port (`DISCO_CATALOG_PORT`, default `8760`), distinct from any app's gradio port.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `disco/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: an importable `disco` package installable in editable mode.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_import_package():
    import disco  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco'`

- [ ] **Step 3: Create the package and project files**

```toml
# pyproject.toml
[project]
name = "disco"
version = "0.1.0"
description = "Local catalog and launcher for gradio demo apps"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.30",
  "jinja2>=3.1",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[project.scripts]
disco = "disco.main:run"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["disco*"]
```

```python
# disco/__init__.py
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install the package in editable mode with dev deps**

Run: `pip install -e ".[dev]"`

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml disco/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "Scaffold disco package"
```

---

### Task 2: Manifest parsing

**Files:**
- Create: `disco/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `class ManifestError(Exception)`
  - `@dataclass(frozen=True) class AppManifest`: fields `name: str`, `description: str`, `port: int`, `launch: str`, `source_dir: Path`, `manifest_path: Path`, `chips: int | None = None`
  - `def parse_manifest(manifest_path: Path) -> AppManifest` — raises `ManifestError` on invalid input

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_manifest.py
from pathlib import Path

import pytest

from disco.manifest import AppManifest, ManifestError, parse_manifest


def write_manifest(tmp_path: Path, name: str, content: str) -> Path:
    app_dir = tmp_path / name
    disco_dir = app_dir / ".disco"
    disco_dir.mkdir(parents=True)
    manifest_path = disco_dir / "app.yaml"
    manifest_path.write_text(content)
    return manifest_path


def test_parse_valid_manifest(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "vjepa2",
        "name: vjepa2\n"
        "description: V-JEPA2 demo\n"
        "port: 7860\n"
        "chips: 1\n"
        "launch: .venv/bin/python app.py\n",
    )

    result = parse_manifest(manifest_path)

    assert result == AppManifest(
        name="vjepa2",
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=manifest_path.parent.parent,
        manifest_path=manifest_path,
        chips=1,
    )


def test_parse_manifest_without_optional_chips(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "animatediff",
        "name: animatediff\n"
        "description: AnimateDiff demo\n"
        "port: 7861\n"
        "launch: .venv/bin/python app.py\n",
    )

    result = parse_manifest(manifest_path)

    assert result.chips is None


def test_parse_manifest_missing_required_field(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "broken",
        "name: broken\ndescription: no port or launch\n",
    )

    with pytest.raises(ManifestError, match="missing required field"):
        parse_manifest(manifest_path)


def test_parse_manifest_invalid_yaml(tmp_path):
    manifest_path = write_manifest(tmp_path, "broken", "name: [unterminated\n")

    with pytest.raises(ManifestError, match="invalid YAML"):
        parse_manifest(manifest_path)


def test_parse_manifest_non_integer_port(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "broken",
        "name: broken\ndescription: bad port\nport: not-a-number\nlaunch: run.sh\n",
    )

    with pytest.raises(ManifestError, match="port must be an integer"):
        parse_manifest(manifest_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco.manifest'`

- [ ] **Step 3: Write the implementation**

```python
# disco/manifest.py
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("name", "description", "port", "launch")


class ManifestError(Exception):
    """Raised when a .disco/app.yaml manifest fails to parse or validate."""


@dataclasses.dataclass(frozen=True)
class AppManifest:
    name: str
    description: str
    port: int
    launch: str
    source_dir: Path
    manifest_path: Path
    chips: int | None = None


def parse_manifest(manifest_path: Path) -> AppManifest:
    try:
        raw = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a YAML mapping")

    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ManifestError(f"missing required field(s): {', '.join(missing)}")

    try:
        port = int(raw["port"])
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"port must be an integer: {raw['port']!r}") from exc

    chips = raw.get("chips")
    if chips is not None:
        try:
            chips = int(chips)
        except (TypeError, ValueError) as exc:
            raise ManifestError(f"chips must be an integer: {chips!r}") from exc

    # manifest lives at <app repo root>/.disco/app.yaml
    source_dir = manifest_path.parent.parent

    return AppManifest(
        name=str(raw["name"]),
        description=str(raw["description"]),
        port=port,
        launch=str(raw["launch"]),
        source_dir=source_dir,
        manifest_path=manifest_path,
        chips=chips,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add disco/manifest.py tests/test_manifest.py
git commit -m "Add manifest parsing"
```

---

### Task 3: App discovery

**Files:**
- Modify: `disco/manifest.py`
- Modify: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `parse_manifest`, `ManifestError`, `AppManifest` from Task 2
- Produces:
  - `@dataclass(frozen=True) class BrokenManifest`: fields `manifest_path: Path`, `error: str`
  - `def find_manifests(root: Path) -> list[Path]`
  - `def discover_apps(root: Path) -> list[AppManifest | BrokenManifest]`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_manifest.py
from disco.manifest import BrokenManifest, discover_apps, find_manifests


def test_find_manifests_one_level_deep(tmp_path):
    write_manifest(
        tmp_path,
        "vjepa2",
        "name: vjepa2\ndescription: d\nport: 1\nlaunch: run\n",
    )
    write_manifest(
        tmp_path,
        "animatediff",
        "name: animatediff\ndescription: d\nport: 2\nlaunch: run\n",
    )
    # a manifest nested too deep should not be found
    deep_dir = tmp_path / "other" / "nested" / ".disco"
    deep_dir.mkdir(parents=True)
    (deep_dir / "app.yaml").write_text("name: nested\ndescription: d\nport: 3\nlaunch: run\n")

    found = find_manifests(tmp_path)

    assert found == sorted(
        [
            tmp_path / "animatediff" / ".disco" / "app.yaml",
            tmp_path / "vjepa2" / ".disco" / "app.yaml",
        ]
    )


def test_discover_apps_mixes_valid_and_broken(tmp_path):
    write_manifest(
        tmp_path,
        "vjepa2",
        "name: vjepa2\ndescription: d\nport: 1\nlaunch: run\n",
    )
    write_manifest(tmp_path, "broken", "name: broken\n")

    results = discover_apps(tmp_path)

    valid = [r for r in results if not isinstance(r, BrokenManifest)]
    broken = [r for r in results if isinstance(r, BrokenManifest)]
    assert len(valid) == 1
    assert valid[0].name == "vjepa2"
    assert len(broken) == 1
    assert "missing required field" in broken[0].error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL with `ImportError: cannot import name 'BrokenManifest'`

- [ ] **Step 3: Write the implementation**

```python
# append to disco/manifest.py

@dataclasses.dataclass(frozen=True)
class BrokenManifest:
    manifest_path: Path
    error: str


def find_manifests(root: Path) -> list[Path]:
    return sorted(root.glob("*/.disco/app.yaml"))


def discover_apps(root: Path) -> list[AppManifest | BrokenManifest]:
    results: list[AppManifest | BrokenManifest] = []
    for manifest_path in find_manifests(root):
        try:
            results.append(parse_manifest(manifest_path))
        except ManifestError as exc:
            results.append(BrokenManifest(manifest_path=manifest_path, error=str(exc)))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add disco/manifest.py tests/test_manifest.py
git commit -m "Add app discovery over manifest files"
```

---

### Task 4: systemd unit rendering

**Files:**
- Create: `disco/units.py`
- Test: `tests/test_units.py`

**Interfaces:**
- Consumes: `AppManifest` from Task 2
- Produces:
  - `def unit_name(app_name: str) -> str`
  - `def build_launch_command(app: AppManifest, use_gozer: bool) -> str`
  - `def render_unit_file(app: AppManifest, use_gozer: bool) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_units.py
from pathlib import Path

from disco.manifest import AppManifest
from disco.units import build_launch_command, render_unit_file, unit_name


def make_app(chips=None) -> AppManifest:
    return AppManifest(
        name="vjepa2",
        description="V-JEPA2 demo",
        port=7860,
        launch=".venv/bin/python app.py",
        source_dir=Path("/home/ttuser/code/tt-vjepa2"),
        manifest_path=Path("/home/ttuser/code/tt-vjepa2/.disco/app.yaml"),
        chips=chips,
    )


def test_unit_name():
    assert unit_name("vjepa2") == "disco-vjepa2.service"


def test_build_launch_command_without_gozer():
    app = make_app(chips=1)
    assert build_launch_command(app, use_gozer=False) == ".venv/bin/python app.py"


def test_build_launch_command_without_chips_declared():
    app = make_app(chips=None)
    assert build_launch_command(app, use_gozer=True) == ".venv/bin/python app.py"


def test_build_launch_command_with_gozer_and_chips():
    app = make_app(chips=1)
    result = build_launch_command(app, use_gozer=True)
    assert result == (
        'gozer run --chips 1 --who "disco:vjepa2" '
        '--reason "gradio demo" -- .venv/bin/python app.py'
    )


def test_render_unit_file_contains_working_directory_and_exec_start():
    app = make_app(chips=1)
    content = render_unit_file(app, use_gozer=True)
    assert "WorkingDirectory=/home/ttuser/code/tt-vjepa2" in content
    assert 'ExecStart=gozer run --chips 1 --who "disco:vjepa2"' in content
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_units.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco.units'`

- [ ] **Step 3: Write the implementation**

```python
# disco/units.py
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from disco.manifest import AppManifest

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"


def unit_name(app_name: str) -> str:
    return f"disco-{app_name}.service"


def unit_file_path(app_name: str) -> Path:
    return UNIT_DIR / unit_name(app_name)


def gozer_available() -> bool:
    return shutil.which("gozer") is not None


def build_launch_command(app: AppManifest, use_gozer: bool) -> str:
    if use_gozer and app.chips is not None:
        return (
            f'gozer run --chips {app.chips} --who "disco:{app.name}" '
            f'--reason "gradio demo" -- {app.launch}'
        )
    return app.launch


def render_unit_file(app: AppManifest, use_gozer: bool) -> str:
    exec_start = build_launch_command(app, use_gozer)
    return (
        "[Unit]\n"
        f"Description=tt-disco managed app: {app.name}\n"
        "\n"
        "[Service]\n"
        f"WorkingDirectory={app.source_dir}\n"
        f"ExecStart={exec_start}\n"
        "Restart=no\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_units.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add disco/units.py tests/test_units.py
git commit -m "Add systemd unit file rendering"
```

---

### Task 5: systemd control (start/stop/status)

**Files:**
- Modify: `disco/units.py`
- Modify: `tests/test_units.py`

**Interfaces:**
- Consumes: `unit_name`, `render_unit_file`, `gozer_available`, `AppManifest` from Task 4
- Produces:
  - `def write_unit_file(app: AppManifest) -> Path`
  - `def systemctl(*args: str) -> subprocess.CompletedProcess`
  - `def start_app(app: AppManifest) -> subprocess.CompletedProcess`
  - `def stop_app(app_name: str) -> subprocess.CompletedProcess`
  - `def app_status(app_name: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_units.py
import disco.units as units_mod
from disco.units import app_status, start_app, stop_app, write_unit_file


class FakeCompletedProcess:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_write_unit_file_writes_rendered_content(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    app = make_app(chips=1)

    path = write_unit_file(app)

    assert path == tmp_path / "disco-vjepa2.service"
    assert "ExecStart=.venv/bin/python app.py" in path.read_text()


def test_start_app_writes_unit_reloads_and_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(units_mod, "gozer_available", lambda: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    start_app(make_app())

    assert (tmp_path / "disco-vjepa2.service").exists()
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "start", "disco-vjepa2.service"],
    ]


def test_stop_app_calls_systemctl_stop(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(units_mod.subprocess, "run", fake_run)

    stop_app("vjepa2")

    assert calls == [["systemctl", "--user", "stop", "disco-vjepa2.service"]]


def test_app_status_returns_stripped_stdout(monkeypatch):
    monkeypatch.setattr(
        units_mod.subprocess, "run", lambda cmd, **kwargs: FakeCompletedProcess(stdout="active\n")
    )

    assert app_status("vjepa2") == "active"


def test_app_status_returns_unknown_for_empty_stdout(monkeypatch):
    monkeypatch.setattr(
        units_mod.subprocess, "run", lambda cmd, **kwargs: FakeCompletedProcess(stdout="")
    )

    assert app_status("vjepa2") == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_units.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_unit_file'`

- [ ] **Step 3: Write the implementation**

```python
# append to disco/units.py

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
```

Note: `write_unit_file` calls `UNIT_DIR.mkdir` directly (a module-level `Path`), so the test's `monkeypatch.setattr(units_mod, "UNIT_DIR", tmp_path)` must run before `write_unit_file`/`start_app` is called — it is, in every test above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_units.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add disco/units.py tests/test_units.py
git commit -m "Add systemd start/stop/status control"
```

---

### Task 6: FastAPI catalog app

**Files:**
- Create: `disco/app.py`
- Create: `disco/templates/index.html`
- Create: `disco/templates/_catalog.html`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `discover_apps`, `AppManifest`, `BrokenManifest` (Task 3); `units.app_status`, `units.start_app`, `units.stop_app` (Task 5)
- Produces:
  - `def scan_root() -> Path`
  - `def create_app() -> FastAPI`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco.app'`

- [ ] **Step 3: Write the implementation**

```python
# disco/app.py
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
            "index.html", {"request": request, "apps": catalog_rows()}
        )

    @app.post("/apps/{name}/start", response_class=HTMLResponse)
    def start(request: Request, name: str) -> HTMLResponse:
        target = find_app(name)
        if target is not None:
            units.start_app(target)
        return templates.TemplateResponse(
            "_catalog.html", {"request": request, "apps": catalog_rows()}
        )

    @app.post("/apps/{name}/stop", response_class=HTMLResponse)
    def stop(request: Request, name: str) -> HTMLResponse:
        units.stop_app(name)
        return templates.TemplateResponse(
            "_catalog.html", {"request": request, "apps": catalog_rows()}
        )

    return app
```

```html
<!-- disco/templates/index.html -->
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>tt-disco</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border: 1px solid #ccc; padding: 0.5rem; text-align: left; }
    .broken { color: #a00; }
  </style>
</head>
<body>
  <h1>tt-disco</h1>
  <div id="catalog">
    {% include "_catalog.html" %}
  </div>
</body>
</html>
```

```html
<!-- disco/templates/_catalog.html -->
<table>
  <thead>
    <tr><th>Name</th><th>Description</th><th>Status</th><th>Actions</th></tr>
  </thead>
  <tbody>
    {% for a in apps %}
    <tr>
      {% if a.broken %}
      <td>{{ a.name }}</td>
      <td class="broken" colspan="3">broken manifest: {{ a.error }}</td>
      {% else %}
      <td>{{ a.name }}</td>
      <td>{{ a.description }}</td>
      <td>{{ a.status }}</td>
      <td>
        <button hx-post="/apps/{{ a.name }}/start" hx-target="#catalog" hx-swap="innerHTML">Start</button>
        <button hx-post="/apps/{{ a.name }}/stop" hx-target="#catalog" hx-swap="innerHTML">Stop</button>
        {% if a.status == "active" %}
        <a href="http://localhost:{{ a.port }}" target="_blank">Open</a>
        {% endif %}
      </td>
      {% endif %}
    </tr>
    {% endfor %}
  </tbody>
</table>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add disco/app.py disco/templates/index.html disco/templates/_catalog.html tests/test_app.py
git commit -m "Add FastAPI catalog app with htmx start/stop"
```

---

### Task 7: Entrypoint

**Files:**
- Create: `disco/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `create_app` from Task 6
- Produces: `app` (module-level FastAPI instance in `disco.main`), `def run() -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
from fastapi import FastAPI

from disco.main import app


def test_main_exposes_fastapi_app():
    assert isinstance(app, FastAPI)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco.main'`

- [ ] **Step 3: Write the implementation**

```python
# disco/main.py
from __future__ import annotations

import os

import uvicorn

from disco.app import create_app

app = create_app()


def run() -> None:
    host = os.environ.get("DISCO_HOST", "127.0.0.1")
    port = int(os.environ.get("DISCO_CATALOG_PORT", "8760"))
    uvicorn.run("disco.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add disco/main.py tests/test_main.py
git commit -m "Add disco entrypoint"
```

---

### Task 8: Onboard tt-vjepa2 and tt-animatediff, manual smoke test

**Files:**
- Create: `~/code/tt-vjepa2/.disco/app.yaml`
- Create: `~/code/tt-animatediff/.disco/app.yaml`

**Interfaces:**
- Consumes: the manifest schema from the Global Constraints section.

- [ ] **Step 1: Inspect each app's actual launch command**

Read `~/code/tt-vjepa2/models/autoports/facebook_vjepa2_vitg_fpc64_384/gradio_app/app.py` and `~/code/tt-animatediff/app.py` (and any README in each repo) to confirm: the venv path each app expects to run under, the port each app binds by default (or the flag to fix one), and whether either script already wraps itself in `gozer`. If a script already calls `gozer` internally, set `chips` to `null`/omit it in that app's manifest so tt-disco does not double-wrap the launch command.

- [ ] **Step 2: Write `~/code/tt-vjepa2/.disco/app.yaml`**

```yaml
name: vjepa2
description: V-JEPA2 video embedding demo
port: 7860
chips: 1
launch: .venv/bin/python models/autoports/facebook_vjepa2_vitg_fpc64_384/gradio_app/app.py
```

Adjust `port` and `launch` to match what Step 1 found if they differ from this default.

- [ ] **Step 3: Write `~/code/tt-animatediff/.disco/app.yaml`**

```yaml
name: animatediff
description: AnimateDiff video generation demo
port: 7861
chips: 1
launch: .venv/bin/python app.py
```

Adjust `port` and `launch` to match what Step 1 found if they differ from this default.

- [ ] **Step 4: Run the catalog**

Run: `disco` (from an activated environment with the `disco` package installed per Task 1)
Expected: server starts on `http://127.0.0.1:8760`

- [ ] **Step 5: Verify both apps appear in the catalog**

Open `http://127.0.0.1:8760` in a browser. Expected: a table listing `vjepa2` and `animatediff` with status `inactive` (or `unknown` if this is the very first run before any unit file exists) and Start buttons.

- [ ] **Step 6: Start each app and confirm it comes up**

Click Start for `vjepa2`. Expected: status flips to `active` (allow a few seconds if `gozer` has to wait for a chip — check with `journalctl --user -u disco-vjepa2.service -f` if it stays `inactive`/`failed`), and an Open link appears pointing at `http://localhost:7860`. Click it and confirm the gradio UI loads. Repeat for `animatediff` on port 7861.

- [ ] **Step 7: Stop each app and confirm it comes down**

Click Stop for each app. Expected: status returns to `inactive` and the Open link disappears.

- [ ] **Step 8: Commit**

```bash
cd ~/code/tt-vjepa2 && git add .disco/app.yaml && git commit -m "Add tt-disco manifest"
cd ~/code/tt-animatediff && git add .disco/app.yaml && git commit -m "Add tt-disco manifest"
```

(These are separate repos from `tt-disco` — commit within each one, not from `tt-disco`.)
