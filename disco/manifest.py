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
