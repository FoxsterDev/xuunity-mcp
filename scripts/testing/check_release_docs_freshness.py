#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import json
from pathlib import Path


PACKAGE_JSON = Path("packages") / "com.xuunity.light-mcp" / "package.json"

PUBLIC_DOCS = (
    Path("README.md"),
    Path("docs") / "reference" / "FEATURES.md",
    Path("docs") / "reference" / "STATUS.md",
    Path("docs") / "architecture" / "ROADMAP.md",
    Path("docs") / "operations" / "SMOKE_TESTS.md",
    Path("docs") / "agents" / "AI_INTEGRATION.md",
    Path("docs") / "agents" / "AGENT_WORKFLOWS.md",
    Path("docs") / "reference" / "COMPARISON.md",
    Path("packages") / "com.xuunity.light-mcp" / "Documentation~" / "README.md",
    Path("packages") / "com.xuunity.light-mcp" / "Documentation~" / "AI_INTEGRATION.md",
)


REQUIRED_MARKERS: dict[Path, tuple[str, ...]] = {
    Path("docs") / "reference" / "FEATURES.md": (
        "payload_mode=compact_status_summary",
        "payload_mode=compact_decision",
        "includeFullPayload=true",
        "post-settle",
        "editor_relaunched",
        "unity_project_action_list",
        "unity_project_action_invoke",
        "batch-fallback-mode auto|off|require-batch",
        "run.ps1",
    ),
    Path("docs") / "reference" / "STATUS.md": (
        "unity_status_summary` compact",
        "unity_project_action_invoke",
        "unity_artifact_write_report",
        "Remote Git refs",
        "Public site checks",
    ),
    Path("docs") / "architecture" / "ROADMAP.md": (
        "current `v{version}` Git UPM",
        "includeFullPayload=true",
        "license-aware batch helper fallback",
        ".ps1",
    ),
    Path("docs") / "operations" / "SMOKE_TESTS.md": (
        "post_settle_compile",
        "payload_mode=compact_decision",
        "--include-full-payload",
        "editor_relaunched",
    ),
    Path("docs") / "agents" / "AI_INTEGRATION.md": (
        "includeFullPayload=true",
        "project_actions.yaml",
    ),
    Path("docs") / "agents" / "AGENT_WORKFLOWS.md": (
        "unity_project_action_invoke",
        "unity_artifact_write_report",
        "unity_build_player",
        "--batch-fallback-mode require-batch",
    ),
    Path("docs") / "reference" / "COMPARISON.md": (
        "XUUnity repo-local evidence refreshed",
        "Git UPM available",
        "Compact MCP envelopes",
        "310` tests",
    ),
    Path("packages") / "com.xuunity.light-mcp" / "Documentation~" / "README.md": (
        "catalog-backed `project_action`",
        "poll-until hook scenarios",
        "post-settle",
        "full-payload opt-in",
    ),
    Path("packages") / "com.xuunity.light-mcp" / "Documentation~" / "AI_INTEGRATION.md": (
        "project-action list/invoke",
        "verbose/full-payload",
    ),
}


STALE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"Release tag `v\d+\.\d+\.\d+` is prepared(?: locally)?"),
        "release tag visibility must not be documented as only prepared once the release is published",
    ),
    (
        re.compile(r"must be pushed to `?origin`? for Git UPM consumers"),
        "current release docs must not tell consumers the current tag is still unpushed",
    ),
    (
        re.compile(r"Current package source\s*\|\s*`Release tag prepared`"),
        "current package source should say whether Git UPM is available, not prepared",
    ),
    (
        re.compile(r"\b141 host Python tests\b"),
        "host-test count is stale for the current release line",
    ),
    (
        re.compile(r"v0\.3\.17` is prepared"),
        "old prepared-release validation wording leaked into current docs",
    ),
    (
        re.compile(r"production Git UPM consumption through `v0\.3\.12`"),
        "roadmap baseline must not describe v0.3.12 as the current production line",
    ),
    (
        re.compile(r"\bPrivate multi-project consumer validation\b"),
        "public docs should use public-safe summary wording, not private evidence labels",
    ),
    (
        re.compile(r"previous published `v0\.3\.14` Git UPM tag"),
        "current release validation should not lead with old package self-test evidence",
    ),
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def package_version(source_root: Path) -> str:
    payload = json.loads((source_root / PACKAGE_JSON).read_text(encoding="utf-8"))
    return str(payload.get("version") or "").strip()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def line_errors_for_stale_patterns(relative_path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in STALE_PATTERNS:
            if pattern.search(line):
                errors.append(f"{relative_path}:{line_number}: stale release-doc claim: {reason}: {line.strip()}")
    return errors


def marker_errors(relative_path: Path, text: str, version: str) -> list[str]:
    errors: list[str] = []
    for marker in REQUIRED_MARKERS.get(relative_path, ()):
        rendered_marker = marker.format(version=version)
        if rendered_marker not in text:
            errors.append(f"{relative_path}: missing release freshness marker {rendered_marker!r}")
    return errors


def check_release_docs_freshness(source_root: Path) -> list[str]:
    errors: list[str] = []
    version = package_version(source_root)
    for relative_path in PUBLIC_DOCS:
        path = source_root / relative_path
        if not path.is_file():
            errors.append(f"{relative_path}: missing public release doc")
            continue
        text = read_text(path)
        errors.extend(marker_errors(relative_path, text, version))
        errors.extend(line_errors_for_stale_patterns(relative_path, text))
    return errors


def main(argv: list[str] | None = None) -> int:
    source_root = repo_root_from_script() if not argv else Path(argv[0]).resolve()
    errors = check_release_docs_freshness(source_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("release_docs_freshness=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
