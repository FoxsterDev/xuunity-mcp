#!/usr/bin/env python3
"""Scaffold a clean Unity consumer project for package CI test runs.

The generated project references the in-repo package through a `file:`
dependency and lists it in `testables`, so a batch `-runTests` invocation (or
the Unity Package CI workflow) discovers the shipped EditMode/PlayMode
self-tests without any registry access.

Lanes:
- `ugui`: installs `com.unity.ugui` (plus `com.unity.textmeshpro` on pre-6000
  lines) so the capability-gated uGUI/TMP test assemblies compile and run.
- `no-ugui`: installs neither, proving the package and its core test
  assemblies compile and pass in a project without uGUI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePath

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_setup_common import (  # noqa: E402
    LIGHT_MCP_PACKAGE_NAME,
    TEST_FRAMEWORK_PACKAGE_NAME,
    recommended_test_framework_version,
    unity_major,
)

LANES = ("ugui", "no-ugui")
DEFAULT_PACKAGE_DIR = REPO_ROOT / "packages" / LIGHT_MCP_PACKAGE_NAME


def ugui_lane_dependencies(unity_version: str) -> dict[str, str]:
    if unity_major(unity_version) >= 6000:
        return {"com.unity.ugui": "2.0.0"}
    return {"com.unity.ugui": "1.0.0", "com.unity.textmeshpro": "3.0.6"}


def add_ugui_lane_dependencies(manifest_path: Path, unity_version: str) -> list[str]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependencies = payload.setdefault("dependencies", {})
    missing = {name: version for name, version in ugui_lane_dependencies(unity_version).items() if name not in dependencies}
    if missing:
        dependencies.update(missing)
        manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sorted(missing)


def package_dependency_value(package_dir: PurePath, packages_dir: PurePath) -> str:
    if package_dir.anchor != packages_dir.anchor:
        return "file:" + package_dir.as_posix()
    package_parts = package_dir.parts
    base_parts = packages_dir.parts
    common = 0
    for package_part, base_part in zip(package_parts, base_parts):
        if package_part != base_part:
            break
        common += 1
    relative_parts = [".."] * (len(base_parts) - common) + list(package_parts[common:])
    if not relative_parts:
        relative_parts = ["."]
    return "file:" + "/".join(relative_parts)


def build_manifest_payload(unity_version: str, lane: str, package_dependency: str) -> dict:
    if lane not in LANES:
        raise ValueError(f"unsupported lane: {lane}")
    dependencies = {
        LIGHT_MCP_PACKAGE_NAME: package_dependency,
        TEST_FRAMEWORK_PACKAGE_NAME: recommended_test_framework_version(unity_version),
    }
    if lane == "ugui":
        dependencies.update(ugui_lane_dependencies(unity_version))
    return {
        "dependencies": dict(sorted(dependencies.items())),
        "testables": [LIGHT_MCP_PACKAGE_NAME],
    }


def scaffold_project(project_root: Path, unity_version: str, lane: str, package_dir: Path, force: bool) -> dict:
    if project_root.exists() and any(project_root.iterdir()):
        if not force:
            raise SystemExit(
                f"project root already exists and is not empty: {project_root}. "
                "Pass --force to overwrite its manifest and project version."
            )

    packages_dir = project_root / "Packages"
    settings_dir = project_root / "ProjectSettings"
    assets_dir = project_root / "Assets"
    for directory in (packages_dir, settings_dir, assets_dir):
        directory.mkdir(parents=True, exist_ok=True)

    dependency_value = package_dependency_value(package_dir.resolve(), packages_dir.resolve())
    manifest_payload = build_manifest_payload(unity_version, lane, dependency_value)
    manifest_path = packages_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    project_version_path = settings_dir / "ProjectVersion.txt"
    project_version_path.write_text(f"m_EditorVersion: {unity_version}\n", encoding="utf-8")

    return {
        "status": "ok",
        "project_root": project_root.as_posix(),
        "unity_version": unity_version,
        "lane": lane,
        "package_dependency": dependency_value,
        "test_framework_version": recommended_test_framework_version(unity_version),
        "manifest_path": manifest_path.as_posix(),
        "project_version_path": project_version_path.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--unity-version", required=True)
    parser.add_argument("--lane", choices=LANES)
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--add-ugui-to-existing",
        action="store_true",
        help="Add the ugui lane packages missing from an existing project's manifest and change nothing else.",
    )
    args = parser.parse_args(argv)

    if args.add_ugui_to_existing:
        manifest_path = Path(args.project_root) / "Packages" / "manifest.json"
        if not manifest_path.is_file():
            parser.error(f"--add-ugui-to-existing needs an existing manifest: {manifest_path}")
        added = add_ugui_lane_dependencies(manifest_path, args.unity_version)
        print(json.dumps({"status": "ok", "manifest_path": manifest_path.as_posix(), "added": added}, indent=2))
        return 0
    if args.lane is None:
        parser.error("--lane is required unless --add-ugui-to-existing is given")

    package_dir = Path(args.package_dir)
    if not (package_dir / "package.json").is_file():
        parser.error(f"--package-dir does not contain a package.json: {package_dir}")

    summary = scaffold_project(
        project_root=Path(args.project_root),
        unity_version=args.unity_version,
        lane=args.lane,
        package_dir=package_dir,
        force=args.force,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
