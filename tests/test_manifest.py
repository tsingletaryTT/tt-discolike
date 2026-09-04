# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from pathlib import Path

import pytest

from discolike.manifest import AppManifest, ManifestError, parse_manifest


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


def test_parse_manifest_rejects_name_with_slash(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "broken",
        "name: ../../foo\ndescription: d\nport: 1\nlaunch: run\n",
    )

    with pytest.raises(ManifestError, match="name"):
        parse_manifest(manifest_path)


def test_parse_manifest_rejects_name_with_quote(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "broken",
        'name: foo"bar\ndescription: d\nport: 1\nlaunch: run\n',
    )

    with pytest.raises(ManifestError, match="name"):
        parse_manifest(manifest_path)


def test_parse_manifest_non_integer_port(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        "broken",
        "name: broken\ndescription: bad port\nport: not-a-number\nlaunch: run.sh\n",
    )

    with pytest.raises(ManifestError, match="port must be an integer"):
        parse_manifest(manifest_path)


from discolike.manifest import BrokenManifest, discover_apps, find_manifests


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


def test_discover_apps_flags_duplicate_names_as_broken(tmp_path):
    first_path = write_manifest(
        tmp_path,
        "animatediff",
        "name: shared\ndescription: first\nport: 1\nlaunch: run\n",
    )
    write_manifest(
        tmp_path,
        "vjepa2",
        "name: shared\ndescription: second\nport: 2\nlaunch: run\n",
    )

    results = discover_apps(tmp_path)

    valid = [r for r in results if isinstance(r, AppManifest)]
    broken = [r for r in results if isinstance(r, BrokenManifest)]

    # "animatediff" sorts before "vjepa2", so it wins the name.
    assert len(valid) == 1
    assert valid[0].name == "shared"
    assert valid[0].description == "first"

    assert len(broken) == 1
    assert "duplicate app name 'shared'" in broken[0].error
    assert str(first_path) in broken[0].error
