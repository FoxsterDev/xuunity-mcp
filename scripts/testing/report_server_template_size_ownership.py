#!/usr/bin/env python3
"""Report server template Python file size and ownership hints.

The report is intentionally non-failing. It is a review guardrail for the
server-side monolith reduction waves, not a CI gate.
"""

from __future__ import annotations

import argparse
from pathlib import Path


WARN_LINES = 700
HARD_REVIEW_LINES = 1200
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "Library",
    "node_modules",
    "packages",
    "playwright-report",
    "test-results",
    "generated",
    "Generated",
}


def resolve_repo_root(requested: str) -> Path:
    if requested:
        return Path(requested).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def is_excluded(path: Path, repo_root: Path) -> bool:
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return True
    return any(part in EXCLUDED_DIRS for part in relative.parts)


def ownership_for(path: Path, templates_root: Path) -> str:
    name = path.name
    if name == "server_batch_orchestrator.py":
        return "batch orchestration facade"
    if name == "server_bridge_runtime.py":
        return "bridge runtime facade"
    if name == "server_cli_commands.py":
        return "CLI command adapters"
    if name == "server_editor_host.py":
        return "editor host lifecycle"
    if name == "server_setup_wizard.py":
        return "setup/uninstall wizard"
    if name == "server_summaries.py":
        return "summary projection"
    if name == "server_specs.py":
        return "MCP/static specs"
    if name == "server_mcp_tools.py":
        return "MCP tool adapter"
    if name == "server_mcp_protocol.py":
        return "JSON-RPC protocol"
    if name == "server_cli_parser.py":
        return "CLI parser contract"
    if name.startswith("server_batch_"):
        return "batch support"
    if name.startswith("server_bridge_"):
        return "bridge support"
    if name.startswith("server_project_"):
        return "project context/actions"
    if name.startswith("server_setup_"):
        return "setup support"
    if name.startswith("server_"):
        return "server support"
    return "uncategorized server template"


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def severity(lines: int) -> str:
    if lines > HARD_REVIEW_LINES:
        return "hard-review"
    if lines > WARN_LINES:
        return "warn"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report server template Python file sizes and ownership hints.")
    parser.add_argument("--repo-root", default="", help="Repository root. Defaults to this script's repo.")
    parser.add_argument("--format", choices=("table", "tsv"), default="table")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    templates_root = repo_root / "templates"
    rows = []
    for path in templates_root.rglob("*.py"):
        if is_excluded(path, repo_root):
            continue
        lines = line_count(path)
        rows.append(
            {
                "severity": severity(lines),
                "lines": lines,
                "ownership": ownership_for(path, templates_root),
                "path": path.relative_to(repo_root).as_posix(),
            }
        )

    rows.sort(key=lambda row: (-row["lines"], row["path"]))

    print("# XUUnity MCP server template size/ownership report")
    print(f"# repo_root={repo_root}")
    print(f"# warn_above_lines={WARN_LINES}")
    print(f"# hard_review_above_lines={HARD_REVIEW_LINES}")
    print("# report_only=true")

    if args.format == "tsv":
        print("severity\tlines\townership\tpath")
        for row in rows:
            print(f"{row['severity']}\t{row['lines']}\t{row['ownership']}\t{row['path']}")
        return 0

    width = max([len(row["path"]) for row in rows] + [4])
    print()
    print(f"{'severity':<12} {'lines':>6}  {'ownership':<28} path")
    print(f"{'-' * 12} {'-' * 6}  {'-' * 28} {'-' * width}")
    for row in rows:
        print(f"{row['severity']:<12} {row['lines']:>6}  {row['ownership']:<28} {row['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
