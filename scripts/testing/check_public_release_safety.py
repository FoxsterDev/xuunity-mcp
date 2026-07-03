#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import NamedTuple


PUBLIC_ROOTS = (
    Path("CHANGELOG.md"),
    Path("README.md"),
    Path("INSTALL.md"),
    Path("SECURITY.md"),
    Path("llms.txt"),
    Path("mcp-server.json"),
    Path("docs"),
    Path("packages") / "com.xuunity.light-mcp" / "Documentation~",
    Path("templates") / "package-manifests",
    Path("templates") / "project_actions",
    Path("templates") / "scenarios",
)

TEXT_SUFFIXES = {
    ".cmd",
    ".css",
    ".html",
    ".json",
    ".md",
    ".ps1",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    "playwright-report",
    "test-results",
}

LOCAL_DENYLIST_FILES = (
    Path(".xuunity-public-safety-denylist"),
    Path(".public-safety-denylist"),
)


class Rule(NamedTuple):
    code: str
    pattern: re.Pattern[str]
    reason: str


BUILTIN_RULES = (
    Rule(
        "host_home_path",
        re.compile(r"(?<![A-Za-z0-9_])/(?:Users|home)/(?!(?:<username>|username|user|dev|runneradmin|runner)(?:/|$))[A-Za-z0-9._-]+(?:/|$)"),
        "replace host-local home paths with placeholders or public-safe summaries",
    ),
    Rule(
        "windows_user_path",
        re.compile(r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/]+Users[\\/]+(?!(?:<username>|username|user|dev|runneradmin|runner)(?:[\\/]|$))[A-Za-z0-9._-]+(?:[\\/]|$)"),
        "replace host-local Windows user paths with placeholders or public-safe summaries",
    ),
    Rule(
        "work_tree_path",
        re.compile(r"(?i)(?:^|[\s`\"'])Projects[\\/]+Work(?:[\\/]|$)"),
        "replace private worktree paths with generic validation-project wording",
    ),
    Rule(
        "windows_work_tree_path",
        re.compile(r"(?i)(?:^|[\s`\"'])[A-Z]:[\\/]+(?:Development|Projects|Work)[\\/]+"),
        "replace private Windows worktree paths with placeholders or public-safe summaries",
    ),
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def iter_public_files(source_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_root in PUBLIC_ROOTS:
        root = source_root / relative_root
        if root.is_file() and root.suffix.lower() in TEXT_SUFFIXES:
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(source_root).parts):
                continue
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return sorted(set(files))


def denylist_paths(source_root: Path, extra_paths: list[Path] | None = None) -> list[Path]:
    paths = [source_root / relative_path for relative_path in LOCAL_DENYLIST_FILES]
    env_value = os.environ.get("XUUNITY_PUBLIC_SAFETY_DENYLIST", "")
    for raw_path in env_value.split(os.pathsep):
        raw_path = raw_path.strip()
        if raw_path:
            paths.append(Path(raw_path).expanduser())
    if extra_paths:
        paths.extend(extra_paths)
    return paths


def load_denylist_tokens(source_root: Path, extra_paths: list[Path] | None = None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for path in denylist_paths(source_root, extra_paths):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            token = line.strip()
            if not token or token.startswith("#"):
                continue
            if token not in seen:
                seen.add(token)
                tokens.append(token)
    return tokens


def line_errors(relative_path: Path, line_number: int, line: str, denylist_tokens: list[str]) -> list[str]:
    errors: list[str] = []
    for rule in BUILTIN_RULES:
        if rule.pattern.search(line):
            errors.append(
                f"{relative_path}:{line_number}: public-safety violation {rule.code}: {rule.reason}: {line.strip()}"
            )
    for token in denylist_tokens:
        if token in line:
            errors.append(
                f"{relative_path}:{line_number}: public-safety violation local_denylist_token: "
                f"replace local/private token from denylist with public-safe wording: {line.strip()}"
            )
    return errors


def check_public_release_safety(source_root: Path, extra_denylist_paths: list[Path] | None = None) -> list[str]:
    errors: list[str] = []
    denylist_tokens = load_denylist_tokens(source_root, extra_denylist_paths)
    for path in iter_public_files(source_root):
        relative_path = path.relative_to(source_root)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            errors.extend(line_errors(relative_path, line_number, line, denylist_tokens))
    return errors


def main(argv: list[str] | None = None) -> int:
    source_root = repo_root_from_script() if not argv else Path(argv[0]).resolve()
    errors = check_public_release_safety(source_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "public_release_safety=ok "
        f"files={len(iter_public_files(source_root))} "
        f"local_denylist_tokens={len(load_denylist_tokens(source_root))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
