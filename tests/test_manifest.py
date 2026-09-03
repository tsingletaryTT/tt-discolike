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
