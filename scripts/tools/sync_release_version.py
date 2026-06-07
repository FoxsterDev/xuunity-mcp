#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PACKAGE_NAME = "com.xuunity.light-mcp"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

PACKAGE_JSON = Path("packages") / PACKAGE_NAME / "package.json"
PACKAGE_MANIFESTS = (
    Path("templates") / "package-manifests" / "unity-package-2021_2022.json",
    Path("templates") / "package-manifests" / "unity-package-6000.json",
)
SERVER_TEMPLATE = Path("templates") / "server.py"
CHANGELOG = Path("CHANGELOG.md")

RELEASE_DOCS = (
    Path("README.md"),
    Path("INSTALL.md"),
    Path("SECURITY.md"),
    Path("templates") / "workflows" / "README.md",
    Path("templates") / "unity-package" / "README.md",
    Path("docs") / "README.md",
    Path("docs") / "index.html",
    Path("docs") / "install.html",
    Path("docs") / "agents" / "AGENT_WORKFLOWS.md",
    Path("docs") / "agents" / "AI_INTEGRATION.md",
    Path("docs") / "operations" / "BUILD_AUTOMATION.md",
    Path("docs") / "operations" / "DEVMODE_VALIDATION.md",
    Path("docs") / "operations" / "PACKAGE_PATH_MIGRATION.md",
    Path("docs") / "operations" / "SMOKE_TESTS.md",
    Path("docs") / "reference" / "COMPARISON.md",
    Path("docs") / "reference" / "DISCOVERY.md",
    Path("docs") / "reference" / "FEATURES.md",
    Path("docs") / "reference" / "GLOSSARY.md",
    Path("docs") / "reference" / "LISTING_KIT.md",
    Path("docs") / "reference" / "STATUS.md",
    Path("packages") / PACKAGE_NAME / "Documentation~" / "README.md",
    Path("packages") / PACKAGE_NAME / "Documentation~" / "AI_INTEGRATION.md",
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> bool:
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if before == after:
        return False
    path.write_text(after, encoding="utf-8")
    return True


def package_version(source_root: Path) -> str:
    payload = read_json(source_root / PACKAGE_JSON)
    return str(payload.get("version") or "").strip()


def validate_version(value: str) -> str:
    version = value.strip()
    if not VERSION_RE.match(version):
        raise SystemExit(f"invalid version '{value}'; expected MAJOR.MINOR.PATCH")
    return version


def update_package_metadata(source_root: Path, version: str) -> list[Path]:
    changed: list[Path] = []
    for relative_path in (PACKAGE_JSON, *PACKAGE_MANIFESTS):
        path = source_root / relative_path
        if not path.is_file():
            continue
        payload = read_json(path)
        payload["version"] = version
        if write_json(path, payload):
            changed.append(relative_path)
    return changed


def update_server_info(source_root: Path, old_version: str, version: str) -> list[Path]:
    path = source_root / SERVER_TEMPLATE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(SERVER_INFO\s*=\s*\{\s*"name":\s*"xuunity-mcp",\s*"version":\s*")'
        + re.escape(old_version)
        + r'(")',
        re.MULTILINE,
    )
    updated, count = pattern.subn(rf"\g<1>{version}\2", text, count=1)
    if count == 0:
        raise SystemExit(f"could not update SERVER_INFO version in {SERVER_TEMPLATE}")
    if updated == text:
        return []
    path.write_text(updated, encoding="utf-8")
    return [SERVER_TEMPLATE]


def update_release_doc_text(text: str, old_version: str, version: str) -> str:
    old_tag = f"v{old_version}"
    new_tag = f"v{version}"
    updated_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        candidate = line
        if "Status: `current for" in candidate:
            candidate = candidate.replace(old_tag, new_tag)
            candidate = candidate.replace(old_version, version)
        if f"#v{old_version}" in candidate:
            candidate = candidate.replace(f"#v{old_version}", f"#v{version}")
        for marker in (
            "Package mode: Git UPM release ",
            "current source line is `",
            "Latest source validation for `",
            "host Python tests for `",
            "For package-level verification after upgrading to `",
            "Release tag `",
            "Source package is `",
            "Production Git UPM path is `",
            '"packageVersion": "',
            '"softwareVersion": "',
            "git push origin ",
        ):
            if marker in candidate:
                candidate = candidate.replace(old_tag, new_tag)
                candidate = candidate.replace(old_version, version)
        if f"version={old_version}" in candidate:
            candidate = candidate.replace(f"version={old_version}", f"version={version}")
        if f"`{old_version}`" in candidate and PACKAGE_JSON.as_posix() in candidate:
            candidate = candidate.replace(f"`{old_version}`", f"`{version}`")
        updated_lines.append(candidate)
    return "".join(updated_lines)


def update_release_docs(source_root: Path, old_version: str, version: str) -> list[Path]:
    changed: list[Path] = []
    for relative_path in RELEASE_DOCS:
        path = source_root / relative_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = update_release_doc_text(text, old_version, version)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(relative_path)
    return changed


def update_top_changelog_section(source_root: Path, old_version: str, version: str) -> list[Path]:
    path = source_root / CHANGELOG
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^## " + re.escape(version) + r"$", text):
        return []

    insertion_marker = "## Unreleased\n"
    if insertion_marker not in text:
        return []
    release_section = (
        f"\n## {version}\n\n"
        f"Release tag: `v{version}`\n\n"
        "Current Git UPM install URL:\n\n"
        "```text\n"
        "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp"
        f"#v{version}\n"
        "```\n\n"
        "### Changed\n\n"
        f"- Released `v{version}` package metadata, server metadata, package manifests, and Git UPM examples.\n"
    )
    updated = text.replace(insertion_marker, insertion_marker + release_section, 1)
    path.write_text(updated, encoding="utf-8")
    return [CHANGELOG]


def sync_release_version(source_root: Path, version: str | None) -> list[Path]:
    old_version = validate_version(package_version(source_root))
    next_version = validate_version(version or old_version)
    changed: list[Path] = []
    changed.extend(update_package_metadata(source_root, next_version))
    changed.extend(update_server_info(source_root, old_version, next_version))
    changed.extend(update_release_docs(source_root, old_version, next_version))
    changed.extend(update_top_changelog_section(source_root, old_version, next_version))
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize release-facing MCP version references.")
    parser.add_argument("--source-root", type=Path, default=repo_root_from_script())
    parser.add_argument("--version", default="", help="Release version, for example 0.3.17.")
    args = parser.parse_args(argv)

    changed = sync_release_version(args.source_root.resolve(), args.version or None)
    for path in changed:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
