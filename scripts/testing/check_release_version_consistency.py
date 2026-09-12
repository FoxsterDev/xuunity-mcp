#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE_NAME = "com.xuunity.light-mcp"
VERSION_RE = re.compile(r"\b(?:v)?(\d+\.\d+\.\d+)\b")

ROOT_PACKAGE_JSON = Path("package.json")
ROOT_PACKAGE_LOCK = Path("package-lock.json")
PACKAGE_JSON = Path("packages") / PACKAGE_NAME / "package.json"
PACKAGE_MANIFESTS = (
    Path("templates") / "package-manifests" / "unity-package-2021_2022.json",
    Path("templates") / "package-manifests" / "unity-package-6000.json",
)
SERVER_INFO_TEMPLATES = (
    Path("templates") / "server.py",
    Path("templates") / "server_batch_orchestrator.py",
)
CHANGELOG = Path("CHANGELOG.md")

CLAIM_PATTERNS = (
    re.compile(r"Status: `current for(?: package)? v(\d+\.\d+\.\d+)(?:-dev)?`"),
    re.compile(r"#v(\d+\.\d+\.\d+)"),
    re.compile(r"Package mode: Git UPM release v(\d+\.\d+\.\d+)"),
    re.compile(r"current source line is `v(\d+\.\d+\.\d+)`"),
    re.compile(r"Latest source validation for `v(\d+\.\d+\.\d+)`"),
    re.compile(r"version=(\d+\.\d+\.\d+)"),
    re.compile(r"host Python tests for `v(\d+\.\d+\.\d+)`"),
    re.compile(r"Release tag `v(\d+\.\d+\.\d+)` is prepared"),
    re.compile(r"Source package is `v(\d+\.\d+\.\d+)`"),
    re.compile(r'"packageVersion": "(\d+\.\d+\.\d+)"'),
    re.compile(r'"softwareVersion": "v(\d+\.\d+\.\d+)"'),
    re.compile(r"git push origin v(\d+\.\d+\.\d+)"),
    re.compile(r"For package-level verification after upgrading to `v(\d+\.\d+\.\d+)`"),
)

DOC_ALLOWLIST = (
    "v0.3.11",
    "v0.3.12+",
    "v0.3.14",
    "v0.3.15+",
    "templates/unity-package#v0.3.11",
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def package_version(source_root: Path) -> str:
    return str(read_json(source_root / PACKAGE_JSON).get("version") or "").strip()


def server_info_version(source_root: Path, relative_path: Path) -> str:
    text = (source_root / relative_path).read_text(encoding="utf-8")
    match = re.search(
        r'SERVER_INFO\s*=\s*\{\s*"name":\s*"xuunity-mcp",\s*"version":\s*"([^"]+)"',
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def check_metadata_versions(source_root: Path, version: str) -> list[str]:
    errors: list[str] = []
    root_package_path = source_root / ROOT_PACKAGE_JSON
    if root_package_path.is_file():
        root_version = str(read_json(root_package_path).get("version") or "").strip()
        if root_version != version:
            errors.append(f"{ROOT_PACKAGE_JSON}: version is {root_version!r}, expected {version!r}")
    root_lock_path = source_root / ROOT_PACKAGE_LOCK
    if root_lock_path.is_file():
        lock_payload = read_json(root_lock_path)
        lock_version = str(lock_payload.get("version") or "").strip()
        if lock_version != version:
            errors.append(f"{ROOT_PACKAGE_LOCK}: version is {lock_version!r}, expected {version!r}")
        lock_root_version = str(((lock_payload.get("packages") or {}).get("") or {}).get("version") or "").strip()
        if lock_root_version != version:
            errors.append(f"{ROOT_PACKAGE_LOCK}: packages[''].version is {lock_root_version!r}, expected {version!r}")
    for relative_path in SERVER_INFO_TEMPLATES:
        if not (source_root / relative_path).is_file():
            continue
        server_version = server_info_version(source_root, relative_path)
        if server_version != version:
            errors.append(f"{relative_path}: SERVER_INFO version is {server_version!r}, expected {version!r}")
    for relative_path in PACKAGE_MANIFESTS:
        manifest_version = str(read_json(source_root / relative_path).get("version") or "").strip()
        if manifest_version != version:
            errors.append(f"{relative_path}: version is {manifest_version!r}, expected {version!r}")
    return errors


def changelog_top_section(text: str) -> str:
    match = re.search(r"(?ms)\n## (\d+\.\d+\.\d+)\n.*?(?=\n## \d+\.\d+\.\d+\n|\Z)", text)
    return match.group(0) if match else ""


def check_changelog(source_root: Path, version: str) -> list[str]:
    path = source_root / CHANGELOG
    if not path.is_file():
        return [f"{CHANGELOG}: missing changelog"]
    text = path.read_text(encoding="utf-8")
    top = changelog_top_section(text)
    errors: list[str] = []
    if not top.startswith(f"\n## {version}\n"):
        errors.append(f"{CHANGELOG}: top release section is not {version!r}")
    if f"Release tag: `v{version}`" not in top:
        errors.append(f"{CHANGELOG}: top release section is missing Release tag v{version}")
    if f"#v{version}" not in top:
        errors.append(f"{CHANGELOG}: top release section is missing Git UPM URL tag v{version}")
    errors.extend(release_doc_version_sweep(source_root))
    return errors


def line_is_allowlisted(relative_path: Path, line: str) -> bool:
    if relative_path.parts and relative_path.parts[0] == "docs" and "archive" in relative_path.parts:
        return True
    if relative_path == CHANGELOG:
        return True
    return any(token in line for token in DOC_ALLOWLIST)


def claimed_versions(line: str) -> list[str]:
    values: list[str] = []
    for pattern in CLAIM_PATTERNS:
        values.extend(match.group(1) for match in pattern.finditer(line))
    return values


def is_generated_artifact(relative_path: Path) -> bool:
    """Test output is not a release doc.

    `playwright-report/` and `test-results/` are gitignored build products that quote the page under test, so a
    stale version inside a failure snapshot was reported as a release-doc defect.
    """

    return bool(relative_path.parts) and relative_path.parts[0] in {
        "playwright-report",
        "test-results",
        "node_modules",
    }


def check_release_docs(source_root: Path, version: str) -> list[str]:
    errors: list[str] = []
    release_docs = sorted(source_root.rglob("*.md")) + sorted(source_root.rglob("*.html"))
    for path in release_docs:
        relative_path = path.relative_to(source_root)
        if is_generated_artifact(relative_path) or line_is_allowlisted(relative_path, ""):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line_is_allowlisted(relative_path, line):
                continue
            for claim in claimed_versions(line):
                if claim != version:
                    errors.append(
                        f"{relative_path}:{line_number}: release-facing version claim {claim!r} "
                        f"does not match package version {version!r}: {line.strip()}"
                    )
    return errors


def check_release_version_consistency(source_root: Path) -> list[str]:
    version = package_version(source_root)
    errors = check_metadata_versions(source_root, version)
    errors.extend(check_changelog(source_root, version))
    errors.extend(check_release_docs(source_root, version))
    return errors


def release_doc_version_sweep(source_root: Path) -> list[str]:
    """Fail on any current-release version claim in a release doc that did not follow the release.

    The pattern-whitelist above only recognises phrasings someone thought to list, and the sync tool only
    rewrote the *immediately previous* version. Anything worded differently, or already more than one release
    behind, was invisible to both: the public site told visitors to set up `v0.3.45` for ten releases.

    This sweep inverts that. Every `0.x.y` token in a release-facing doc must equal the current version, unless
    it uses the `vX.Y.Z+` "since this version" convention, carries the sync tool's explicit historical-evidence
    marker, or its legacy line is recorded in HISTORICAL_VERSION_CLAIMS. A version paired with a measured result
    must be marked historical, because bumping it without re-running the measurement replaces a stale truth with
    a fresh lie.
    """

    # Import the sweep's rules from this checkout, not from the tree under inspection: a minimal fixture tree
    # has no scripts/tools, and the rules belong to the gate.
    tools_dir = repo_root_from_script() / "scripts" / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import sync_release_version as sync

    version = package_version(source_root)
    errors: list[str] = []
    for relative_path in sync.RELEASE_DOCS:
        path = source_root / relative_path
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if sync.line_records_history(relative_path, line) or line_is_allowlisted(relative_path, line):
                continue
            for match in sync.RELEASE_DOC_VERSION_TOKEN.finditer(line):
                if (
                    match.group("plus")
                    or match.group("version") == version
                    or match.group("version") in sync.HISTORICAL_VERSION_TOKENS
                ):
                    continue
                errors.append(
                    f"{relative_path.as_posix()}:{number}: stale release-facing version {match.group(0)!r} "
                    f"does not match package version {version!r}: {line.strip()[:120]}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    source_root = repo_root_from_script() if not argv else Path(argv[0]).resolve()
    errors = check_release_version_consistency(source_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"release_version_consistency=ok version={package_version(source_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
