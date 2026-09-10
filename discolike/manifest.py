# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("name", "description", "port", "launch")

# A manifest's `name` flows straight into a systemd unit filename
# (disco-<name>.service) and into a shell-quoted gozer --who argument
# ("disco:<name>"). Restrict it to a conservative safe charset so it can
# never smuggle in path traversal (e.g. "../../foo") or break out of the
# surrounding double quotes (e.g. a bare `"`).
NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


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
    hidden: bool = False


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

    name = str(raw["name"])
    if not re.fullmatch(NAME_PATTERN, name):
        raise ManifestError(
            f"name {name!r} must match [A-Za-z0-9_.-]+ "
            "(it is used in a systemd unit filename and a shell-quoted argument)"
        )

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

    hidden = bool(raw.get("hidden", False))

    # manifest lives at <app repo root>/.disco/app.yaml. Resolve symlinks so a
    # symlinked alias directory (e.g. an old repo name kept as a symlink to
    # the real one) and the real directory both launch from the same,
    # canonical (destination) path -- never from the symlink's own path,
    # which systemd's ExecStart would otherwise treat as a distinct cwd.
    source_dir = (manifest_path.parent.parent).resolve()

    return AppManifest(
        name=name,
        description=str(raw["description"]),
        port=port,
        launch=str(raw["launch"]),
        source_dir=source_dir,
        manifest_path=manifest_path,
        chips=chips,
        hidden=hidden,
    )


@dataclasses.dataclass(frozen=True)
class BrokenManifest:
    manifest_path: Path
    error: str


def find_manifests(root: Path) -> list[Path]:
    return sorted(root.glob("*/.disco/app.yaml"))


def discover_apps(root: Path) -> list[AppManifest | BrokenManifest]:
    results: list[AppManifest | BrokenManifest] = []
    seen_names: dict[str, Path] = {}
    seen_real_dirs: dict[Path, Path] = {}
    for manifest_path in find_manifests(root):
        try:
            manifest = parse_manifest(manifest_path)
        except ManifestError as exc:
            results.append(BrokenManifest(manifest_path=manifest_path, error=str(exc)))
            continue

        if manifest.source_dir in seen_real_dirs:
            # A symlinked alias directory resolving to an app dir already
            # discovered (e.g. an old repo name kept as a symlink to its
            # current one) -- not a real conflict, just the same app found
            # twice. Silently skip the alias; the destination directory's
            # entry (already in `results`) is the sole, canonical one.
            continue
        seen_real_dirs[manifest.source_dir] = manifest_path

        if manifest.name in seen_names:
            # Two repos declaring the same name would otherwise collide on
            # one systemd unit (disco-<name>.service) -- Start on either
            # row would silently start/control the same underlying app.
            # Only the first manifest (by find_manifests' sort order) wins;
            # every later one is surfaced as broken instead of silently
            # colliding.
            results.append(
                BrokenManifest(
                    manifest_path=manifest_path,
                    error=(
                        f"duplicate app name '{manifest.name}' "
                        f"(already declared by {seen_names[manifest.name]})"
                    ),
                )
            )
            continue

        seen_names[manifest.name] = manifest_path
        results.append(manifest)
    return results
