#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_PACKAGE_PATH = Path("packages/com.xuunity.light-mcp")
EXCLUDED_PARTS = {
    "Library",
    "node_modules",
    "obj",
    "bin",
    "Generated",
}


def classify_owner(path: Path) -> str:
    text = path.as_posix()
    name = path.name
    if "Editor/Core/" in text:
        if name == "XUUnityLightMcpModels.cs":
            return "DTO contract facade"
        return "core contract/runtime"
    if "Editor/Bridge/" in text:
        if name == "XUUnityLightMcpBridgeRuntimeState.cs":
            return "bridge runtime state facade"
        return "bridge runtime support"
    if "Editor/Helpers/" in text:
        if name == "XUUnityLightMcpScenarioRunner.cs":
            return "scenario runner facade"
        if name == "XUUnityLightMcpScenarioProjectActionNormalizer.cs":
            return "project action normalization facade"
        return "editor helper support"
    if "Editor/Operations/" in text:
        return "MCP operation adapter"
    if "Editor/Batch/" in text or "/Batch/" in text:
        return "batch CLI support"
    if "Tests/" in text:
        return "package self-test"
    return "package support"


def should_include(path: Path) -> bool:
    if path.suffix != ".cs":
        return False
    return not any(part in EXCLUDED_PARTS for part in path.parts)


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except UnicodeDecodeError:
        return len(path.read_text(errors="replace").splitlines())


def severity(lines: int, warn_above: int, hard_review_above: int) -> str:
    if lines > hard_review_above:
        return "hard-review"
    if lines > warn_above:
        return "warn"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Unity package C# size and ownership hotspots.")
    parser.add_argument("--repo-root", default=".", help="Repository root containing packages/com.xuunity.light-mcp.")
    parser.add_argument("--package-path", default=str(DEFAULT_PACKAGE_PATH), help="Package path relative to repo root.")
    parser.add_argument("--warn-above-lines", type=int, default=500)
    parser.add_argument("--hard-review-above-lines", type=int, default=1000)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    package_root = (repo_root / args.package_path).resolve()
    records = []
    for path in sorted(package_root.rglob("*.cs")):
        relative = path.relative_to(repo_root)
        if not should_include(relative):
            continue
        lines = line_count(path)
        records.append((severity(lines, args.warn_above_lines, args.hard_review_above_lines), lines, classify_owner(relative), relative))

    order = {"hard-review": 0, "warn": 1, "ok": 2}
    records.sort(key=lambda item: (order[item[0]], -item[1], item[3].as_posix()))

    print("# XUUnity Light MCP Unity package size/ownership report")
    print(f"# repo_root={repo_root}")
    print(f"# package_root={package_root}")
    print(f"# warn_above_lines={args.warn_above_lines}")
    print(f"# hard_review_above_lines={args.hard_review_above_lines}")
    print("# report_only=true")
    print()
    print(f"{'severity':<12} {'lines':>6}  {'ownership':<38} path")
    print(f"{'-' * 12} {'-' * 6}  {'-' * 38} {'-' * 60}")
    for item_severity, lines, owner, relative in records:
        print(f"{item_severity:<12} {lines:>6}  {owner:<38} {relative.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
