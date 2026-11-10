#!/usr/bin/env python3
"""Safe, resumable Git UPM consumer rollout orchestration.

The helper keeps release publication separate from consumer adoption. It plans
an authoritative inventory, proves a safe Unity batch lane, validates one
published-package canary, fans out only after that canary passes, and persists
an atomic per-project ledger that another bounded worker can resume.

The default output is a compact decision projection. Use ``--output full`` to
inspect the frozen inventory, preflight evidence, or worker task packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SCRIPT_DIR.parents[1]
TEMPLATES_DIR = SOURCE_ROOT / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_core import (  # noqa: E402
    hidden_window_subprocess_kwargs,
    reconfigure_stdio_utf8,
    write_json,
)
from server_editor_host import (  # noqa: E402
    resolve_unity_app_version,
    resolve_unity_executable,
    terminate_editor_pid,
)
from server_editor_host_discovery import list_process_commands_report  # noqa: E402
from server_editor_host_processes import (  # noqa: E402
    classify_unity_process_role,
    unity_command_executable,
    unity_command_targets_project,
)
from server_license import build_license_capabilities  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_PACKAGE_NAME = "com.xuunity.light-mcp"
DEFAULT_WORKER_TIMEOUT_SECONDS = 20 * 60
DEFAULT_OVERALL_DEADLINE_SECONDS = 4 * 60 * 60
DEFAULT_LICENSE_TIMEOUT_SECONDS = 45
GIT_TIMEOUT_SECONDS = 30
PROCESS_CLEANUP_TIMEOUT_MS = 15_000

DISCOVERY_PRUNE_DIRS = {
    ".agents",
    ".claude",
    ".codex",
    ".git",
    ".idea",
    ".vs",
    ".vscode",
    "Build",
    "Builds",
    "Library",
    "Logs",
    "Temp",
    "obj",
    "node_modules",
}

COMPILER_ERROR_PATTERNS = (
    re.compile(r"\berror\s+CS\d+\b", re.IGNORECASE),
    re.compile(r"Scripts have compiler errors", re.IGNORECASE),
    re.compile(r"Compilation failed", re.IGNORECASE),
    re.compile(r"Aborting batchmode due to failure", re.IGNORECASE),
    re.compile(r"executeMethod method .* threw exception", re.IGNORECASE),
)

SENSITIVE_COMMAND_OPTION = re.compile(
    r"(?i)^--?(?:access[-_]?token|auth[-_]?token|refresh[-_]?token|"
    r"api[-_]?key|password|secret)$"
)
SENSITIVE_COMMAND_ASSIGNMENT = re.compile(
    r"(?i)^(--?(?:access[-_]?token|auth[-_]?token|refresh[-_]?token|"
    r"api[-_]?key|password|secret))=.*$"
)
SENSITIVE_COMMAND_TEXT = re.compile(
    r"(?i)(--?(?:access[-_]?token|auth[-_]?token|refresh[-_]?token|"
    r"api[-_]?key|password|secret))(?:\s*=\s*|\s+)"
    r"(?:\"[^\"]*\"|'[^']*'|\S+)"
)


class RolloutError(RuntimeError):
    """Refusal or invalid state that must not be silently bypassed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalized_path(path: str | Path) -> str:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        resolved = Path(path).expanduser().absolute()
    return str(resolved)


def path_match_key(path: str | Path) -> str:
    return normalized_path(path).replace("\\", "/").rstrip("/").lower()


def redact_command_text(command: str) -> str:
    """Remove credential-shaped command arguments before evidence is persisted."""
    return SENSITIVE_COMMAND_TEXT.sub(r"\1 [REDACTED]", command)


def redact_command_args(command: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for argument in command:
        value = str(argument)
        if hide_next:
            redacted.append("[REDACTED]")
            hide_next = False
            continue
        if SENSITIVE_COMMAND_OPTION.fullmatch(value):
            redacted.append(value)
            hide_next = True
            continue
        assignment = SENSITIVE_COMMAND_ASSIGNMENT.fullmatch(value)
        if assignment:
            redacted.append(f"{assignment.group(1)}=[REDACTED]")
            continue
        redacted.append(redact_command_text(value))
    return redacted


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RolloutError(f"JSON root must be an object: {path}")
    return payload


def run_helper(command: list[str], *, cwd: Path | None = None, timeout: float = GIT_TIMEOUT_SECONDS) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **hidden_window_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": str(exc.stderr or ""),
            "error_code": "helper_timeout",
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "error_code": "helper_spawn_failed",
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "error_code": "" if completed.returncode == 0 else "helper_failed",
    }


def git_snapshot(project_root: Path, scoped_paths: list[Path]) -> dict[str, Any]:
    root_result = run_helper(["git", "-C", str(project_root), "rev-parse", "--show-toplevel"])
    if not root_result["ok"]:
        return {
            "available": False,
            "error_code": "git_root_unavailable",
            "stderr": root_result["stderr"][:500],
            "root": "",
            "branch": "",
            "head": "",
            "dirty_paths": [],
        }

    git_root = Path(root_result["stdout"].strip()).resolve()
    relative_paths: list[str] = []
    try:
        for path in scoped_paths:
            relative_paths.append(str(path.resolve().relative_to(git_root)))
    except (OSError, ValueError) as exc:
        return {
            "available": False,
            "error_code": "git_scope_outside_root",
            "stderr": str(exc)[:500],
            "root": str(git_root),
            "branch": "",
            "head": "",
            "dirty_paths": [],
        }

    branch_result = run_helper(["git", "-C", str(git_root), "branch", "--show-current"])
    head_result = run_helper(["git", "-C", str(git_root), "rev-parse", "HEAD"])
    status_result = run_helper(
        [
            "git",
            "-C",
            str(git_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *relative_paths,
        ]
    )
    if not (branch_result["ok"] and head_result["ok"] and status_result["ok"]):
        return {
            "available": False,
            "error_code": "git_snapshot_failed",
            "stderr": "\n".join(
                str(item.get("stderr") or "")[:300]
                for item in (branch_result, head_result, status_result)
                if not item["ok"]
            ),
            "root": str(git_root),
            "branch": "",
            "head": "",
            "dirty_paths": [],
        }

    dirty_paths = []
    for line in status_result["stdout"].splitlines():
        if not line.strip():
            continue
        path_text = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        dirty_paths.append(path_text)

    return {
        "available": True,
        "error_code": "",
        "stderr": "",
        "root": str(git_root),
        "branch": branch_result["stdout"].strip(),
        "head": head_result["stdout"].strip(),
        "dirty_paths": sorted(set(dirty_paths)),
    }


def git_workspace_snapshot(git_root: Path) -> dict[str, Any]:
    status_result = run_helper(
        ["git", "-C", str(git_root), "status", "--porcelain=v1", "--untracked-files=all"]
    )
    if not status_result["ok"]:
        return {
            "available": False,
            "root": str(git_root),
            "dirty_paths": [],
            "error_code": "git_workspace_status_failed",
            "stderr": str(status_result.get("stderr") or "")[:500],
        }
    dirty_paths = []
    for line in status_result["stdout"].splitlines():
        if not line.strip():
            continue
        path_text = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        dirty_paths.append(path_text)
    return {
        "available": True,
        "root": str(git_root),
        "dirty_paths": sorted(set(dirty_paths)),
        "error_code": "",
        "stderr": "",
    }


def dependency_ref(value: str) -> str:
    text = str(value or "").strip()
    return text.rsplit("#", 1)[1] if "#" in text else ""


def dependency_with_ref(value: str, release_tag: str) -> str:
    text = str(value or "").strip()
    if not text or not any(text.startswith(prefix) for prefix in ("http://", "https://", "git@", "ssh://", "git+")):
        raise RolloutError("The consumer dependency is not a Git/remote package URL.")
    base = text.rsplit("#", 1)[0]
    return f"{base}#{release_tag}"


def package_files(project_root: Path) -> tuple[Path, Path]:
    return (
        project_root / "Packages" / "manifest.json",
        project_root / "Packages" / "packages-lock.json",
    )


def project_unity_version(project_root: Path) -> str:
    version_path = project_root / "ProjectSettings" / "ProjectVersion.txt"
    try:
        text = version_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = re.search(r"^m_EditorVersion:\s*(\S+)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def inspect_consumer(project_root: Path, package_name: str) -> dict[str, Any]:
    manifest_path, lock_path = package_files(project_root)
    row: dict[str, Any] = {
        "project": project_root.name,
        "project_root": str(project_root),
        "manifest_path": str(manifest_path),
        "lock_path": str(lock_path),
        "package_name": package_name,
        "project_unity_version": project_unity_version(project_root),
        "manifest_dependency": "",
        "manifest_ref": "",
        "lock_version": "",
        "lock_ref": "",
        "lock_hash": "",
        "alignment": "unknown",
        "error": "",
        "fingerprints": {},
    }
    try:
        manifest = read_json_object(manifest_path)
        lock_payload = read_json_object(lock_path)
    except (OSError, ValueError, json.JSONDecodeError, RolloutError) as exc:
        row["alignment"] = "json_unreadable"
        row["error"] = str(exc)
        return row

    dependencies = manifest.get("dependencies")
    lock_dependencies = lock_payload.get("dependencies")
    if not isinstance(dependencies, dict) or not isinstance(lock_dependencies, dict):
        row["alignment"] = "dependencies_missing"
        row["error"] = "Manifest and lock must contain dependency objects."
        return row

    manifest_dependency = str(dependencies.get(package_name) or "").strip()
    lock_entry = lock_dependencies.get(package_name)
    if not manifest_dependency or not isinstance(lock_entry, dict):
        row["alignment"] = "package_missing"
        row["error"] = f"{package_name} must exist in both manifest and lock."
        return row

    lock_version = str(lock_entry.get("version") or "").strip()
    lock_hash = str(lock_entry.get("hash") or "").strip()
    manifest_ref = dependency_ref(manifest_dependency)
    lock_ref = dependency_ref(lock_version)
    row.update(
        {
            "manifest_dependency": manifest_dependency,
            "manifest_ref": manifest_ref,
            "lock_version": lock_version,
            "lock_ref": lock_ref,
            "lock_hash": lock_hash,
            "fingerprints": {
                "manifest_sha256": file_sha256(manifest_path),
                "lock_sha256": file_sha256(lock_path),
            },
        }
    )
    if not manifest_ref or not lock_ref:
        row["alignment"] = "git_ref_missing"
        row["error"] = "Manifest and lock Git dependencies must include a #ref."
    elif manifest_ref != lock_ref:
        row["alignment"] = "manifest_lock_ref_mismatch"
        row["error"] = f"Manifest ref {manifest_ref!r} differs from lock ref {lock_ref!r}."
    elif not lock_hash:
        row["alignment"] = "lock_hash_missing"
        row["error"] = "The Git package lock entry must include a resolved hash."
    else:
        row["alignment"] = "aligned"
    return row


def manifest_declares_package(manifest_path: Path, package_name: str) -> bool:
    try:
        payload = read_json_object(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError, RolloutError):
        return False
    dependencies = payload.get("dependencies")
    return isinstance(dependencies, dict) and bool(dependencies.get(package_name))


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def discover_consumers(
    search_roots: list[Path], package_name: str, excluded_roots: list[Path] | None = None
) -> list[Path]:
    discovered: dict[str, Path] = {}
    exclusions = [path.expanduser().resolve() for path in (excluded_roots or [])]
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for current_root, dir_names, file_names in os.walk(search_root):
            current_path = Path(current_root).resolve()
            if any(path_is_within(current_path, excluded) for excluded in exclusions):
                dir_names[:] = []
                continue
            dir_names[:] = [name for name in dir_names if name not in DISCOVERY_PRUNE_DIRS]
            dir_names[:] = [
                name
                for name in dir_names
                if not any(path_is_within(current_path / name, excluded) for excluded in exclusions)
            ]
            current = current_path
            if current.name != "Packages" or "manifest.json" not in file_names:
                continue
            project_root = current.parent
            if not (project_root / "ProjectSettings" / "ProjectVersion.txt").is_file():
                continue
            manifest_path = current / "manifest.json"
            if manifest_declares_package(manifest_path, package_name):
                discovered[path_match_key(project_root)] = project_root.resolve()
            dir_names[:] = []
    return [discovered[key] for key in sorted(discovered)]


def stable_project_id(project_root: Path) -> str:
    digest = hashlib.sha256(path_match_key(project_root).encode("utf-8")).hexdigest()[:12]
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", project_root.name).strip("-") or "project"
    return f"{safe_name}-{digest}"


def build_inventory(
    *,
    expected_roots: list[Path],
    search_roots: list[Path],
    canary_root: Path,
    package_name: str = DEFAULT_PACKAGE_NAME,
    accept_discovered: bool = False,
    excluded_roots: list[Path] | None = None,
) -> dict[str, Any]:
    expected = {path_match_key(path): Path(normalized_path(path)) for path in expected_roots}
    discovered_roots = discover_consumers(search_roots, package_name, excluded_roots)
    discovered = {path_match_key(path): path for path in discovered_roots}
    union_keys = sorted(set(expected) | set(discovered))
    errors: list[dict[str, Any]] = []

    missing_expected = sorted(set(expected) - set(discovered))
    unexpected_discovered = sorted(set(discovered) - set(expected))
    for key in missing_expected:
        errors.append(
            {
                "code": "expected_consumer_not_discovered",
                "project_root": str(expected[key]),
            }
        )
    if unexpected_discovered and not accept_discovered:
        for key in unexpected_discovered:
            errors.append(
                {
                    "code": "unexpected_consumer_requires_root_triage",
                    "project_root": str(discovered[key]),
                }
            )

    rows: list[dict[str, Any]] = []
    canary_key = path_match_key(canary_root)
    for key in union_keys:
        project_root = discovered.get(key) or expected[key]
        row = inspect_consumer(project_root, package_name)
        row["project_id"] = stable_project_id(project_root)
        row["expected"] = key in expected
        row["discovered"] = key in discovered
        row["canary"] = key == canary_key
        manifest_path, lock_path = package_files(project_root)
        git = git_snapshot(project_root, [manifest_path, lock_path]) if project_root.is_dir() else {
            "available": False,
            "error_code": "project_root_missing",
            "stderr": "",
            "root": "",
            "branch": "",
            "head": "",
            "dirty_paths": [],
        }
        row["git"] = git
        row["dirty"] = (not git.get("available")) or bool(git.get("dirty_paths"))
        row["included"] = row["discovered"] and (row["expected"] or accept_discovered)
        if row["alignment"] != "aligned":
            errors.append(
                {
                    "code": "consumer_package_alignment_invalid",
                    "project_id": row["project_id"],
                    "project_root": row["project_root"],
                    "alignment": row["alignment"],
                    "detail": row["error"],
                }
            )
        if not git.get("available"):
            errors.append(
                {
                    "code": "consumer_git_snapshot_unavailable",
                    "project_id": row["project_id"],
                    "project_root": row["project_root"],
                    "detail": git.get("error_code") or "git_unavailable",
                }
            )
        if row["canary"] and row["dirty"]:
            errors.append(
                {
                    "code": "canary_package_files_dirty",
                    "project_id": row["project_id"],
                    "dirty_paths": git.get("dirty_paths") or [],
                }
            )
        row["state"] = "skipped_dirty" if row["dirty"] else "pending"
        rows.append(row)

    canary_rows = [row for row in rows if row["canary"] and row["included"]]
    if len(canary_rows) != 1:
        errors.append(
            {
                "code": "canary_not_in_authoritative_inventory",
                "project_root": str(Path(normalized_path(canary_root))),
                "matches": len(canary_rows),
            }
        )

    included_rows = [row for row in rows if row["included"]]
    clean_rows = [row for row in included_rows if not row["dirty"]]
    dirty_rows = [row for row in included_rows if row["dirty"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if not errors else "needs_smart_escalation",
        "package_name": package_name,
        "created_at_utc": utc_now(),
        "search_roots": [str(path.resolve()) for path in search_roots],
        "excluded_roots": [str(path.expanduser().resolve()) for path in (excluded_roots or [])],
        "canary_project_root": normalized_path(canary_root),
        "accept_discovered": bool(accept_discovered),
        "denominator": {
            "expected": len(expected),
            "discovered": len(discovered),
            "total": len(included_rows),
            "clean": len(clean_rows),
            "dirty": len(dirty_rows),
            "missing_expected": len(missing_expected),
            "unexpected_discovered": len(unexpected_discovered),
        },
        "errors": errors,
        "projects": rows,
    }


def write_probe(directory: Path) -> dict[str, Any]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temp_path = tempfile.mkstemp(prefix=".xuunity-rollout-write-probe-", dir=str(directory))
        os.close(descriptor)
        Path(temp_path).unlink()
        return {"path": str(directory), "writable": True, "error": ""}
    except OSError as exc:
        return {"path": str(directory), "writable": False, "error": str(exc)[:500]}


def relevant_unity_processes(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in report.get("commands") or []:
        try:
            pid = int(entry[0])
            command = str(entry[1])
            role = classify_unity_process_role(command)
        except (IndexError, TypeError, ValueError, SystemError):
            continue
        executable = unity_command_executable(command).lower()
        if role or "unity licensing client" in executable or "unitylicensingclient" in executable:
            rows.append(
                {
                    "pid": pid,
                    "role": role or "licensing_client",
                    "command": redact_command_text(command)[:1000],
                }
            )
    return rows


def build_preflight(
    *,
    inventory: dict[str, Any],
    unity_app: Path,
    run_dir: Path,
    license_timeout_seconds: int = DEFAULT_LICENSE_TIMEOUT_SECONDS,
    process_report_fn: Callable[[], dict[str, Any]] = list_process_commands_report,
    license_probe_fn: Callable[..., dict[str, Any]] = build_license_capabilities,
    workspace_snapshot_fn: Callable[[Path], dict[str, Any]] = git_workspace_snapshot,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    if inventory.get("status") != "ready":
        blockers.append(
            {
                "code": "authoritative_inventory_not_ready",
                "inventory_error_codes": [
                    str(item.get("code") or "") for item in inventory.get("errors") or []
                ],
            }
        )
    write_probes = [write_probe(run_dir)]
    included_clean = [
        row for row in inventory.get("projects") or [] if row.get("included") and not row.get("dirty")
    ]
    for row in included_clean:
        project_root = Path(row["project_root"])
        manifest_path = Path(row["manifest_path"])
        lock_path = Path(row["lock_path"])
        for path in (manifest_path, lock_path):
            if not path.is_file() or not os.access(path, os.R_OK | os.W_OK):
                blockers.append(
                    {
                        "code": "package_file_not_read_write",
                        "project_id": row["project_id"],
                        "path": str(path),
                    }
                )
        write_probes.append(write_probe(manifest_path.parent))
        write_probes.append(write_probe(project_root / "Library"))

    for probe in write_probes:
        if not probe["writable"]:
            blockers.append({"code": "write_probe_failed", **probe})

    unity_app = Path(normalized_path(unity_app))
    unity_executable = Path("")
    unity_version = ""
    try:
        unity_executable = Path(resolve_unity_executable(unity_app))
        unity_version = str(resolve_unity_app_version(unity_app) or "")
        if not unity_executable.is_file():
            raise OSError(f"Unity executable not found: {unity_executable}")
    except (OSError, ValueError) as exc:
        blockers.append({"code": "unity_binary_unavailable", "detail": str(exc)[:500]})

    for row in included_clean:
        project_version = str(row.get("project_unity_version") or "")
        if not project_version:
            blockers.append(
                {
                    "code": "project_unity_version_unreadable",
                    "project_id": row["project_id"],
                }
            )
        elif unity_version and project_version != unity_version:
            blockers.append(
                {
                    "code": "project_unity_version_mismatch",
                    "project_id": row["project_id"],
                    "project_unity_version": project_version,
                    "selected_unity_version": unity_version,
                }
            )

    workspace_baselines = []
    seen_git_roots = set()
    for row in included_clean:
        git_root = str((row.get("git") or {}).get("root") or "")
        key = path_match_key(git_root) if git_root else ""
        if not key or key in seen_git_roots:
            continue
        seen_git_roots.add(key)
        baseline = workspace_snapshot_fn(Path(git_root))
        workspace_baselines.append(baseline)
        if not baseline.get("available"):
            blockers.append(
                {
                    "code": "workspace_baseline_unavailable",
                    "git_root": git_root,
                    "detail": str(baseline.get("error_code") or "git_workspace_status_failed"),
                }
            )

    process_report = process_report_fn()
    visibility_available = bool(process_report.get("available"))
    processes = relevant_unity_processes(process_report)
    conflicts = [row for row in processes if row["role"] in {"main_editor", "worker"}]
    if not visibility_available:
        blockers.append(
            {
                "code": "global_process_visibility_unavailable",
                "detail": str(process_report.get("error_code") or "process_listing_failed"),
            }
        )
    if conflicts:
        blockers.append(
            {
                "code": "global_unity_process_conflict",
                "pids": [row["pid"] for row in conflicts],
                "roles": sorted({row["role"] for row in conflicts}),
            }
        )

    license_payload: dict[str, Any] = {}
    canary_rows = [row for row in inventory.get("projects") or [] if row.get("canary") and row.get("included")]
    if not blockers and len(canary_rows) == 1:
        try:
            license_payload = license_probe_fn(
                project_root=Path(canary_rows[0]["project_root"]),
                unity_app=unity_app,
                refresh=True,
                timeout_ms=max(1, int(license_timeout_seconds)) * 1000,
            )
        except Exception as exc:
            blockers.append({"code": "license_probe_failed", "detail": str(exc)[:500]})
        else:
            if license_payload.get("batchmode_supported") is not True:
                blockers.append(
                    {
                        "code": "batch_license_not_proven",
                        "blocker_code": str(license_payload.get("batchmode_blocker_code") or ""),
                        "recommended_execution_lane": str(
                            license_payload.get("recommended_execution_lane") or ""
                        ),
                    }
                )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed" if not blockers and inventory.get("status") == "ready" else "blocked",
        "created_at_utc": utc_now(),
        "blockers": blockers,
        "unity_app": str(unity_app),
        "unity_executable": str(unity_executable) if str(unity_executable) != "." else "",
        "unity_version": unity_version,
        "process_visibility_available": visibility_available,
        "global_unity_processes": processes,
        "write_probes": write_probes,
        "workspace_baselines": workspace_baselines,
        "license_capabilities": {
            key: license_payload.get(key)
            for key in (
                "batchmode_supported",
                "editor_ui_supported",
                "batchmode_blocker_code",
                "recommended_execution_lane",
                "batchmode_probe_log_path",
                "batchmode_probe_exit_code",
                "batchmode_probe_timed_out",
                "probed_at_utc",
            )
            if key in license_payload
        },
        "cleanup_owner": "root_agent",
        "known_good_command_lane": "direct_unity_batchmode_resolve_compile_quit",
    }


def ordered_project_rows(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    included = [row for row in inventory.get("projects") or [] if row.get("included")]
    return sorted(included, key=lambda row: (not bool(row.get("canary")), str(row.get("project"))))


def default_validation_command(unity_executable: str, project_root: str, log_path: str) -> list[str]:
    return [
        unity_executable,
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath",
        project_root,
        "-logFile",
        log_path,
    ]


def build_worker_task_packet(
    *,
    inventory: dict[str, Any],
    preflight: dict[str, Any],
    ledger_path: Path,
    worker_label: str,
    worker_timeout_seconds: int,
    overall_deadline_seconds: int,
    release_tag: str,
    release_commit: str,
) -> dict[str, Any]:
    rows = [row for row in ordered_project_rows(inventory) if not row.get("dirty")]
    return {
        "schema_version": SCHEMA_VERSION,
        "worker_label": worker_label,
        "objective": "Validate the frozen Git UPM consumer rollout serially and persist exact evidence.",
        "release": {"tag": release_tag, "commit": release_commit},
        "frozen_denominator": inventory.get("denominator") or {},
        "project_order": [
            {
                "project_id": row["project_id"],
                "project": row["project"],
                "project_root": row["project_root"],
                "canary": bool(row.get("canary")),
            }
            for row in rows
        ],
        "unity": {
            "version": preflight.get("unity_version") or "",
            "executable": preflight.get("unity_executable") or "",
            "command_template": [
                "{unity_executable}",
                "-batchmode",
                "-nographics",
                "-quit",
                "-projectPath",
                "{project_root}",
                "-logFile",
                "{unique_unity_log_path}",
            ],
        },
        "permissions": {
            "project_write_required": True,
            "run_directory_write_required": True,
            "commit_push_tag_publish": False,
            "process_termination": False,
        },
        "timeouts": {
            "per_project_seconds": int(worker_timeout_seconds),
            "overall_deadline_seconds": int(overall_deadline_seconds),
        },
        "ledger_path": str(ledger_path),
        "stop_conditions": [
            "first_unexpected_exit_or_compile_error",
            "package_tag_or_hash_mismatch",
            "timeout_or_owned_process_outlives_worker",
            "new_or_changed_dirty_path",
            "unity_or_license_infrastructure_change",
        ],
        "non_authorities": [
            "do_not_rank_or_redesign",
            "do_not_diagnose_or_fix_unexpected_results",
            "do_not_modify_dirty_targets",
            "do_not_weaken_or_waive_gates",
            "do_not_commit_push_tag_or_publish",
            "do_not_kill_processes",
        ],
        "unexpected_result_contract": {
            "status": "needs_smart_escalation",
            "required_evidence": [
                "project_id",
                "exact_command",
                "pid_if_alive",
                "unity_log_path",
                "process_log_path",
                "first_relevant_error",
                "ledger_path",
            ],
        },
    }


def build_ledger(
    *,
    run_dir: Path,
    release_tag: str,
    release_commit: str,
    inventory: dict[str, Any],
    preflight: dict[str, Any],
    worker_label: str,
    worker_timeout_seconds: int,
    overall_deadline_seconds: int,
) -> dict[str, Any]:
    ledger_path = run_dir / "consumer_rollout_ledger.json"
    task_packet_path = run_dir / "worker_task_packet.json"
    projects = []
    for row in ordered_project_rows(inventory):
        projects.append(
            {
                **row,
                "baseline_fingerprints": dict(row.get("fingerprints") or {}),
                "state": "skipped_dirty" if row.get("dirty") else "pending",
                "pin_applied": False,
                "post_pin_fingerprints": {},
                "command": [],
                "unity_log_path": "",
                "process_log_path": "",
                "started_at_utc": "",
                "ended_at_utc": "",
                "duration_seconds": None,
                "exit_code": None,
                "compile_error": "",
                "cleanup": {"status": "not_needed"},
                "owned_process": {},
            }
        )
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "action": "consumer_rollout",
        "status": "planned" if preflight.get("status") == "passed" else "needs_smart_escalation",
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "ledger_path": str(ledger_path),
        "task_packet_path": str(task_packet_path),
        "release": {"tag": release_tag, "commit": release_commit},
        "inventory": inventory,
        "preflight": preflight,
        "projects": projects,
        "worker_timeout_seconds": int(worker_timeout_seconds),
        "overall_deadline_seconds": int(overall_deadline_seconds),
        "execution_started_at_utc": "",
        "execution_deadline_utc": "",
        "first_unproven_project_id": "",
        "recommended_next_action": "execute_rollout" if preflight.get("status") == "passed" else "resolve_preflight_blockers",
    }
    task_packet = build_worker_task_packet(
        inventory=inventory,
        preflight=preflight,
        ledger_path=ledger_path,
        worker_label=worker_label,
        worker_timeout_seconds=worker_timeout_seconds,
        overall_deadline_seconds=overall_deadline_seconds,
        release_tag=release_tag,
        release_commit=release_commit,
    )
    write_json(task_packet_path, task_packet)
    write_ledger(ledger)
    return ledger


def write_ledger(ledger: dict[str, Any]) -> None:
    ledger["updated_at_utc"] = utc_now()
    write_json(Path(ledger["ledger_path"]), ledger)


def compact_projection(ledger: dict[str, Any]) -> dict[str, Any]:
    projects = ledger.get("projects") or []
    state_counts = Counter(str(row.get("state") or "unknown") for row in projects)
    canary = next((row for row in projects if row.get("canary")), {})
    first_unproven = next(
        (
            row
            for row in projects
            if not row.get("dirty") and str(row.get("state") or "") not in {"passed"}
        ),
        {},
    )
    preflight = ledger.get("preflight") or {}
    inventory = ledger.get("inventory") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "payload_mode": "compact_consumer_rollout",
        "action": ledger.get("action") or "consumer_rollout",
        "status": ledger.get("status") or "unknown",
        "release": ledger.get("release") or {},
        "denominator": inventory.get("denominator") or {},
        "preflight_status": preflight.get("status") or "unknown",
        "preflight_blocker_codes": [str(item.get("code") or "") for item in preflight.get("blockers") or []],
        "canary": {
            "project": canary.get("project") or "",
            "state": canary.get("state") or "missing",
        },
        "state_counts": dict(sorted(state_counts.items())),
        "first_unproven_project": first_unproven.get("project") or "",
        "first_unproven_project_id": first_unproven.get("project_id") or "",
        "ledger_path": ledger.get("ledger_path") or "",
        "task_packet_path": ledger.get("task_packet_path") or "",
        "recommended_next_action": ledger.get("recommended_next_action") or "",
        "full_payload_available": True,
        "full_payload_cli_argument": "--output full",
    }


def emit_ledger(ledger: dict[str, Any], output_mode: str) -> None:
    payload = ledger if output_mode == "full" else compact_projection(ledger)
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def pin_matches(project: dict[str, Any], release_tag: str, release_commit: str) -> tuple[bool, dict[str, Any]]:
    inspected = inspect_consumer(Path(project["project_root"]), str(project["package_name"]))
    matches = (
        inspected.get("alignment") == "aligned"
        and inspected.get("manifest_ref") == release_tag
        and inspected.get("lock_ref") == release_tag
        and inspected.get("lock_hash") == release_commit
    )
    return matches, inspected


def baseline_fingerprints_match(project: dict[str, Any]) -> bool:
    manifest_path = Path(project["manifest_path"])
    lock_path = Path(project["lock_path"])
    expected = project.get("baseline_fingerprints") or {}
    try:
        return (
            file_sha256(manifest_path) == expected.get("manifest_sha256")
            and file_sha256(lock_path) == expected.get("lock_sha256")
        )
    except OSError:
        return False


def apply_package_pin(project: dict[str, Any], release_tag: str, release_commit: str) -> None:
    if project.get("dirty"):
        raise RolloutError(f"Refusing dirty consumer: {project.get('project')}")
    if not baseline_fingerprints_match(project):
        raise RolloutError(f"Consumer package files changed after planning: {project.get('project')}")

    project_root = Path(project["project_root"])
    package_name = str(project["package_name"])
    manifest_path, lock_path = package_files(project_root)
    manifest = read_json_object(manifest_path)
    lock_payload = read_json_object(lock_path)
    dependencies = manifest.get("dependencies")
    lock_dependencies = lock_payload.get("dependencies")
    if not isinstance(dependencies, dict) or not isinstance(lock_dependencies, dict):
        raise RolloutError("Manifest and lock dependencies must be objects.")
    current_manifest = str(dependencies.get(package_name) or "")
    lock_entry = lock_dependencies.get(package_name)
    if not isinstance(lock_entry, dict):
        raise RolloutError(f"{package_name} lock entry is missing.")

    target_dependency = dependency_with_ref(current_manifest, release_tag)
    previous_manifest_ref = dependency_ref(current_manifest)
    previous_lock_hash = str(lock_entry.get("hash") or "")
    old_manifest = json.loads(json.dumps(manifest))
    old_lock = json.loads(json.dumps(lock_payload))
    dependencies[package_name] = target_dependency
    lock_entry["version"] = target_dependency
    lock_entry["hash"] = release_commit
    try:
        write_json(manifest_path, manifest)
        write_json(lock_path, lock_payload)
    except Exception:
        write_json(manifest_path, old_manifest)
        write_json(lock_path, old_lock)
        raise

    matches, inspected = pin_matches(project, release_tag, release_commit)
    combined_text = "\n".join(
        (
            manifest_path.read_text(encoding="utf-8", errors="replace"),
            lock_path.read_text(encoding="utf-8", errors="replace"),
        )
    )
    previous_ref_absent = previous_manifest_ref == release_tag or previous_manifest_ref not in combined_text
    previous_hash_absent = previous_lock_hash == release_commit or previous_lock_hash not in combined_text
    if not matches or not previous_ref_absent or not previous_hash_absent:
        write_json(manifest_path, old_manifest)
        write_json(lock_path, old_lock)
        raise RolloutError(
            f"Post-write package pin verification failed for {project.get('project')}: "
            f"alignment={inspected.get('alignment')} previous_ref_absent={previous_ref_absent} "
            f"previous_hash_absent={previous_hash_absent}"
        )
    project["pin_applied"] = True
    project["manifest_dependency"] = inspected["manifest_dependency"]
    project["manifest_ref"] = inspected["manifest_ref"]
    project["lock_version"] = inspected["lock_version"]
    project["lock_ref"] = inspected["lock_ref"]
    project["lock_hash"] = inspected["lock_hash"]
    project["post_pin_fingerprints"] = dict(inspected.get("fingerprints") or {})
    project["previous_ref_absent"] = previous_ref_absent
    project["previous_hash_absent"] = previous_hash_absent
    project["state"] = "pinned"


def allowed_owned_package_paths(ledger: dict[str, Any], git_root: Path) -> set[str]:
    allowed = set()
    for project in ledger.get("projects") or []:
        if project.get("dirty"):
            continue
        for field in ("manifest_path", "lock_path"):
            try:
                allowed.add(str(Path(project[field]).resolve().relative_to(git_root.resolve())))
            except (KeyError, OSError, ValueError):
                continue
    return allowed


def workspace_side_effects(
    ledger: dict[str, Any],
    *,
    workspace_snapshot_fn: Callable[[Path], dict[str, Any]] = git_workspace_snapshot,
) -> dict[str, Any]:
    rows = []
    all_new_paths = []
    for baseline in (ledger.get("preflight") or {}).get("workspace_baselines") or []:
        git_root = Path(str(baseline.get("root") or ""))
        current = workspace_snapshot_fn(git_root)
        baseline_paths = set(str(path) for path in baseline.get("dirty_paths") or [])
        current_paths = set(str(path) for path in current.get("dirty_paths") or [])
        allowed_paths = allowed_owned_package_paths(ledger, git_root)
        new_paths = sorted(current_paths - baseline_paths - allowed_paths) if current.get("available") else []
        if new_paths:
            all_new_paths.extend(f"{git_root}:{path}" for path in new_paths)
        rows.append(
            {
                "git_root": str(git_root),
                "available": bool(current.get("available")),
                "baseline_dirty_count": len(baseline_paths),
                "current_dirty_count": len(current_paths),
                "allowed_owned_package_paths": sorted(allowed_paths),
                "new_unowned_dirty_paths": new_paths,
                "error_code": str(current.get("error_code") or ""),
            }
        )
    return {
        "status": "passed" if not all_new_paths and all(row["available"] for row in rows) else "needs_smart_escalation",
        "new_unowned_dirty_paths": sorted(all_new_paths),
        "workspaces": rows,
    }


def first_compile_error(log_text: str) -> str:
    for pattern in COMPILER_ERROR_PATTERNS:
        match = pattern.search(log_text)
        if not match:
            continue
        line_start = log_text.rfind("\n", 0, match.start()) + 1
        line_end = log_text.find("\n", match.end())
        if line_end < 0:
            line_end = len(log_text)
        return log_text[line_start:line_end].strip()[:1000]
    return ""


def run_project_validation(
    *,
    project: dict[str, Any],
    unity_executable: str,
    run_dir: Path,
    timeout_seconds: int,
    on_started: Callable[[int, list[str], Path, Path], None],
) -> dict[str, Any]:
    project_id = str(project["project_id"])
    unity_log = run_dir / f"{project_id}.unity.log"
    process_log = run_dir / f"{project_id}.process.log"
    command = default_validation_command(unity_executable, str(project["project_root"]), str(unity_log))
    started = time.monotonic()
    with process_log.open("w", encoding="utf-8") as process_stream:
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=process_stream,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
                **hidden_window_subprocess_kwargs(),
            )
        except OSError as exc:
            return {
                "outcome": "needs_smart_escalation",
                "exit_code": 127,
                "duration_seconds": round(time.monotonic() - started, 3),
                "unity_log_path": str(unity_log),
                "process_log_path": str(process_log),
                "compile_error": str(exc)[:1000],
                "owned_process": {},
            }
        on_started(proc.pid, command, unity_log, process_log)
        try:
            exit_code = proc.wait(timeout=max(1, int(timeout_seconds)))
        except subprocess.TimeoutExpired:
            return {
                "outcome": "needs_smart_escalation",
                "exit_code": None,
                "duration_seconds": round(time.monotonic() - started, 3),
                "unity_log_path": str(unity_log),
                "process_log_path": str(process_log),
                "compile_error": f"validation_timeout_after_{int(timeout_seconds)}s",
                "owned_process": {
                    "active": True,
                    "pid": proc.pid,
                    "command": redact_command_args(command),
                    "project_root": str(project["project_root"]),
                    "unity_log_path": str(unity_log),
                    "process_log_path": str(process_log),
                    "ownership_recorded_at_utc": utc_now(),
                },
            }

    unity_text = ""
    process_text = ""
    try:
        unity_text = unity_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    try:
        process_text = process_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    compile_error = first_compile_error("\n".join((unity_text, process_text)))
    return {
        "outcome": "passed" if exit_code == 0 and not compile_error else "needs_smart_escalation",
        "exit_code": int(exit_code),
        "duration_seconds": round(time.monotonic() - started, 3),
        "unity_log_path": str(unity_log),
        "process_log_path": str(process_log),
        "compile_error": compile_error or ("" if exit_code == 0 else f"unity_exit_code_{exit_code}"),
        "owned_process": {
            "active": False,
            "pid": proc.pid,
            "command": redact_command_args(command),
        },
    }


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def execute_rollout(
    ledger: dict[str, Any],
    *,
    runner: Callable[..., dict[str, Any]] = run_project_validation,
    workspace_snapshot_fn: Callable[[Path], dict[str, Any]] = git_workspace_snapshot,
) -> dict[str, Any]:
    if (ledger.get("preflight") or {}).get("status") != "passed":
        raise RolloutError("Preflight did not pass; consumer mutation is forbidden.")
    release = ledger.get("release") or {}
    release_tag = str(release.get("tag") or "")
    release_commit = str(release.get("commit") or "")
    if not release_tag or not release_commit:
        raise RolloutError("Ledger release tag/commit is incomplete.")

    active_owned = [
        row for row in ledger.get("projects") or [] if (row.get("owned_process") or {}).get("active")
    ]
    if active_owned:
        raise RolloutError("An owned validation process is still unaccounted for; run cleanup-owned first.")

    now = datetime.now(timezone.utc)
    if not ledger.get("execution_started_at_utc"):
        ledger["execution_started_at_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        deadline = now.timestamp() + int(ledger.get("overall_deadline_seconds") or DEFAULT_OVERALL_DEADLINE_SECONDS)
        ledger["execution_deadline_utc"] = datetime.fromtimestamp(deadline, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    execution_deadline = parse_utc(str(ledger["execution_deadline_utc"]))
    if datetime.now(timezone.utc) >= execution_deadline:
        ledger["status"] = "needs_smart_escalation"
        ledger["recommended_next_action"] = "root_review_overall_deadline"
        write_ledger(ledger)
        return ledger

    run_dir = Path(ledger["run_dir"])
    unity_executable = str((ledger.get("preflight") or {}).get("unity_executable") or "")
    worker_timeout = int(ledger.get("worker_timeout_seconds") or DEFAULT_WORKER_TIMEOUT_SECONDS)
    projects = ledger.get("projects") or []
    canary = next((row for row in projects if row.get("canary")), None)
    if not canary or canary.get("dirty"):
        raise RolloutError("The frozen canary is missing or dirty.")

    def validate_row(row: dict[str, Any]) -> bool:
        if row.get("state") == "passed":
            matches, inspected = pin_matches(row, release_tag, release_commit)
            log_exists = bool(row.get("unity_log_path")) and Path(str(row["unity_log_path"])).is_file()
            expected_fingerprints = row.get("post_pin_fingerprints") or {}
            fingerprints_match = bool(expected_fingerprints) and inspected.get("fingerprints") == expected_fingerprints
            if matches and log_exists and fingerprints_match:
                return True
            row["state"] = "needs_smart_escalation"
            row["compile_error"] = "previous_pass_artifact_or_pin_changed"
            ledger["status"] = "needs_smart_escalation"
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_changed_resume_baseline"
            write_ledger(ledger)
            return False

        if row.get("state") == "needs_smart_escalation":
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_previous_unexpected_result"
            write_ledger(ledger)
            return False

        remaining_seconds = int(
            (execution_deadline - datetime.now(timezone.utc)).total_seconds()
        )
        if remaining_seconds <= 0:
            row["state"] = "needs_smart_escalation"
            row["compile_error"] = "overall_deadline_elapsed_before_project"
            ledger["status"] = "needs_smart_escalation"
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_overall_deadline"
            write_ledger(ledger)
            return False

        if row.get("pin_applied"):
            matches, inspected = pin_matches(row, release_tag, release_commit)
            expected_fingerprints = row.get("post_pin_fingerprints") or {}
            if not matches or inspected.get("fingerprints") != expected_fingerprints:
                row["state"] = "needs_smart_escalation"
                row["compile_error"] = "pinned_package_files_changed_before_validation"
                ledger["status"] = "needs_smart_escalation"
                ledger["first_unproven_project_id"] = row["project_id"]
                ledger["recommended_next_action"] = "root_review_changed_pinned_files"
                write_ledger(ledger)
                return False

        if not row.get("pin_applied"):
            try:
                apply_package_pin(row, release_tag, release_commit)
            except Exception as exc:
                row["state"] = "needs_smart_escalation"
                row["compile_error"] = str(exc)[:1000]
                ledger["status"] = "needs_smart_escalation"
                ledger["first_unproven_project_id"] = row["project_id"]
                ledger["recommended_next_action"] = "root_review_pin_failure"
                write_ledger(ledger)
                return False
            write_ledger(ledger)

        row["state"] = "running"
        row["started_at_utc"] = utc_now()
        write_ledger(ledger)

        def on_started(pid: int, command: list[str], unity_log: Path, process_log: Path) -> None:
            safe_command = redact_command_args(command)
            row["command"] = safe_command
            row["unity_log_path"] = str(unity_log)
            row["process_log_path"] = str(process_log)
            row["owned_process"] = {
                "active": True,
                "pid": int(pid),
                "command": safe_command,
                "project_root": row["project_root"],
                "unity_log_path": str(unity_log),
                "process_log_path": str(process_log),
                "ownership_recorded_at_utc": utc_now(),
            }
            write_ledger(ledger)

        result = runner(
            project=row,
            unity_executable=unity_executable,
            run_dir=run_dir,
            timeout_seconds=min(worker_timeout, max(1, remaining_seconds)),
            on_started=on_started,
        )
        row.update(
            {
                "state": str(result.get("outcome") or "needs_smart_escalation"),
                "exit_code": result.get("exit_code"),
                "duration_seconds": result.get("duration_seconds"),
                "unity_log_path": str(result.get("unity_log_path") or row.get("unity_log_path") or ""),
                "process_log_path": str(result.get("process_log_path") or row.get("process_log_path") or ""),
                "compile_error": str(result.get("compile_error") or ""),
                "owned_process": result.get("owned_process") or {"active": False},
                "ended_at_utc": utc_now(),
            }
        )
        matches, inspected = pin_matches(row, release_tag, release_commit)
        package_files_unchanged = inspected.get("fingerprints") == (row.get("post_pin_fingerprints") or {})
        if row["state"] == "passed" and (not matches or not package_files_unchanged):
            row["state"] = "needs_smart_escalation"
            row["compile_error"] = (
                "post_validation_package_pin_mismatch"
                if not matches
                else "package_files_changed_during_validation"
            )
        if row["state"] == "passed":
            row["cleanup"] = {"status": "not_needed"}
        else:
            ledger["status"] = "needs_smart_escalation"
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_unexpected_validation_result"
        side_effects = workspace_side_effects(ledger, workspace_snapshot_fn=workspace_snapshot_fn)
        row["workspace_side_effects"] = side_effects
        if row["state"] == "passed" and side_effects["status"] != "passed":
            row["state"] = "needs_smart_escalation"
            row["compile_error"] = "new_unowned_workspace_side_effects"
            ledger["status"] = "needs_smart_escalation"
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_workspace_side_effects"
        write_ledger(ledger)
        return row["state"] == "passed"

    # Canary mutation and validation are the only operations allowed before fan-out.
    if not validate_row(canary):
        return ledger

    if datetime.now(timezone.utc) >= execution_deadline:
        next_row = next(
            (
                row
                for row in projects
                if row is not canary and not row.get("dirty") and row.get("state") != "passed"
            ),
            None,
        )
        ledger["status"] = "needs_smart_escalation"
        ledger["first_unproven_project_id"] = (
            str(next_row.get("project_id") or "") if next_row else ""
        )
        ledger["recommended_next_action"] = "root_review_overall_deadline_before_fanout"
        write_ledger(ledger)
        return ledger

    # The canary proved the published tag/hash. Fan out exact pins before the
    # remaining serial validation so a stopped run can resume at row N.
    for row in projects:
        if row is canary or row.get("dirty") or row.get("pin_applied"):
            continue
        try:
            apply_package_pin(row, release_tag, release_commit)
        except Exception as exc:
            row["state"] = "needs_smart_escalation"
            row["compile_error"] = str(exc)[:1000]
            ledger["status"] = "needs_smart_escalation"
            ledger["first_unproven_project_id"] = row["project_id"]
            ledger["recommended_next_action"] = "root_review_fanout_pin_failure"
            write_ledger(ledger)
            return ledger
        write_ledger(ledger)

    for row in projects:
        if row is canary or row.get("dirty"):
            continue
        if not validate_row(row):
            return ledger

    clean_rows = [row for row in projects if not row.get("dirty")]
    if clean_rows and all(row.get("state") == "passed" for row in clean_rows):
        ledger["status"] = "completed"
        ledger["first_unproven_project_id"] = ""
        ledger["recommended_next_action"] = "consumer_rollout_complete"
        write_ledger(ledger)
    return ledger


def cleanup_owned_process(
    ledger: dict[str, Any],
    *,
    project_id: str,
    process_report_fn: Callable[[], dict[str, Any]] = list_process_commands_report,
    terminate_fn: Callable[[int, int], bool] = terminate_editor_pid,
) -> tuple[dict[str, Any], bool]:
    project = next((row for row in ledger.get("projects") or [] if row.get("project_id") == project_id), None)
    if not project:
        raise RolloutError(f"Unknown project id: {project_id}")
    owned = project.get("owned_process") or {}
    if not owned.get("active"):
        project["cleanup"] = {"status": "not_needed", "checked_at_utc": utc_now()}
        write_ledger(ledger)
        return ledger, True

    try:
        pid = int(owned.get("pid"))
    except (TypeError, ValueError):
        pid = 0
    report = process_report_fn()
    command = ""
    for entry in report.get("commands") or []:
        try:
            entry_pid = int(entry[0])
            entry_command = str(entry[1])
        except (IndexError, TypeError, ValueError, SystemError):
            continue
        if entry_pid == pid:
            command = entry_command
            break

    unity_log = str(owned.get("unity_log_path") or "")
    normalized_command = command.replace("\\", "/").lower()
    log_in_command = bool(unity_log) and unity_log.replace("\\", "/").lower() in normalized_command
    identity_matches = (
        pid > 0
        and bool(report.get("available"))
        and classify_unity_process_role(command) == "main_editor"
        and unity_command_targets_project(command, Path(project["project_root"]))
        and log_in_command
    )
    if not identity_matches:
        project["cleanup"] = {
            "status": "refused_identity_unproven",
            "checked_at_utc": utc_now(),
            "pid": pid,
            "process_visibility_available": bool(report.get("available")),
        }
        ledger["status"] = "needs_smart_escalation"
        ledger["recommended_next_action"] = "inspect_owned_process_identity_without_killing"
        write_ledger(ledger)
        return ledger, False

    terminated = bool(terminate_fn(pid, PROCESS_CLEANUP_TIMEOUT_MS))
    project["cleanup"] = {
        "status": "terminated" if terminated else "termination_unproven",
        "checked_at_utc": utc_now(),
        "pid": pid,
        "identity_reverified": True,
    }
    if terminated:
        project["owned_process"]["active"] = False
        project["owned_process"]["terminated_at_utc"] = utc_now()
        ledger["recommended_next_action"] = "root_diagnose_then_resume_from_first_unproven"
    else:
        ledger["recommended_next_action"] = "inspect_owned_process_still_running"
    write_ledger(ledger)
    return ledger, terminated


def authorize_resume(ledger: dict[str, Any], *, project_id: str, confirm_release_tag: str) -> dict[str, Any]:
    release = ledger.get("release") or {}
    release_tag = str(release.get("tag") or "")
    release_commit = str(release.get("commit") or "")
    if confirm_release_tag != release_tag:
        raise RolloutError("--confirm-release-tag does not match the frozen ledger release.")
    project = next((row for row in ledger.get("projects") or [] if row.get("project_id") == project_id), None)
    if not project:
        raise RolloutError(f"Unknown project id: {project_id}")
    if project.get("dirty"):
        raise RolloutError("A baseline-dirty project cannot be authorized for resume.")
    if (project.get("owned_process") or {}).get("active"):
        raise RolloutError("The owned validation process is still active; cleanup-owned must close it first.")
    if project.get("state") != "needs_smart_escalation":
        raise RolloutError("Only a needs_smart_escalation row can be explicitly resumed.")
    matches, inspected = pin_matches(project, release_tag, release_commit)
    if not matches:
        raise RolloutError("The project tag/hash changed; create a new plan instead of resuming.")

    attempts = project.setdefault("attempts", [])
    attempts.append(
        {
            "state": project.get("state"),
            "command": project.get("command") or [],
            "unity_log_path": project.get("unity_log_path") or "",
            "process_log_path": project.get("process_log_path") or "",
            "started_at_utc": project.get("started_at_utc") or "",
            "ended_at_utc": project.get("ended_at_utc") or "",
            "duration_seconds": project.get("duration_seconds"),
            "exit_code": project.get("exit_code"),
            "compile_error": project.get("compile_error") or "",
            "cleanup": project.get("cleanup") or {},
            "archived_at_utc": utc_now(),
        }
    )
    project.update(
        {
            "state": "pinned",
            "post_pin_fingerprints": dict(inspected.get("fingerprints") or {}),
            "command": [],
            "unity_log_path": "",
            "process_log_path": "",
            "started_at_utc": "",
            "ended_at_utc": "",
            "duration_seconds": None,
            "exit_code": None,
            "compile_error": "",
            "cleanup": {"status": "not_needed"},
            "owned_process": {},
            "resume_authorized_at_utc": utc_now(),
        }
    )
    now = datetime.now(timezone.utc)
    deadline = now.timestamp() + int(ledger.get("overall_deadline_seconds") or DEFAULT_OVERALL_DEADLINE_SECONDS)
    ledger["execution_started_at_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger["execution_deadline_utc"] = datetime.fromtimestamp(deadline, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    ledger["status"] = "planned"
    ledger["first_unproven_project_id"] = project_id
    ledger["recommended_next_action"] = "execute_rollout_from_authorized_resume"
    write_ledger(ledger)
    return ledger


def validate_release_identity(release_tag: str, release_commit: str) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", release_tag):
        raise RolloutError("release tag must be a semantic version with a leading v")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
        raise RolloutError("release commit must be a full 40-character Git SHA")


def load_ledger(path: Path) -> dict[str, Any]:
    ledger = read_json_object(path)
    if int(ledger.get("schema_version") or 0) != SCHEMA_VERSION:
        raise RolloutError("Unsupported consumer rollout ledger schema.")
    ledger["ledger_path"] = str(path.resolve())
    return ledger


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Freeze inventory, preflight, ledger, and worker packet.")
    plan_parser.add_argument("--search-root", action="append", required=True)
    plan_parser.add_argument("--expected-project-root", action="append", required=True)
    plan_parser.add_argument(
        "--exclude-root",
        action="append",
        default=[],
        help="Exclude a reviewed clone, experiment, archive, or other non-consumer subtree. Repeatable.",
    )
    plan_parser.add_argument("--canary-project-root", required=True)
    plan_parser.add_argument("--release-tag", required=True)
    plan_parser.add_argument("--release-commit", required=True)
    plan_parser.add_argument("--unity-app", required=True)
    plan_parser.add_argument("--run-dir", required=True)
    plan_parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    plan_parser.add_argument("--accept-discovered", action="store_true")
    plan_parser.add_argument("--worker-label", default="bounded_executor")
    plan_parser.add_argument("--worker-timeout-seconds", type=int, default=DEFAULT_WORKER_TIMEOUT_SECONDS)
    plan_parser.add_argument("--overall-deadline-seconds", type=int, default=DEFAULT_OVERALL_DEADLINE_SECONDS)
    plan_parser.add_argument("--license-timeout-seconds", type=int, default=DEFAULT_LICENSE_TIMEOUT_SECONDS)
    plan_parser.add_argument("--output", choices=("compact", "full"), default="compact")

    execute_parser = subparsers.add_parser("execute", help="Run canary, fan-out, and serial validation.")
    execute_parser.add_argument("--ledger", required=True)
    execute_parser.add_argument("--confirm-release-tag", required=True)
    execute_parser.add_argument("--output", choices=("compact", "full"), default="compact")

    cleanup_parser = subparsers.add_parser("cleanup-owned", help="Root-only cleanup after PID identity proof.")
    cleanup_parser.add_argument("--ledger", required=True)
    cleanup_parser.add_argument("--project-id", required=True)
    cleanup_parser.add_argument("--output", choices=("compact", "full"), default="compact")

    resume_parser = subparsers.add_parser(
        "resume-project", help="Root-only re-arm of one diagnosed and cleaned escalation row."
    )
    resume_parser.add_argument("--ledger", required=True)
    resume_parser.add_argument("--project-id", required=True)
    resume_parser.add_argument("--confirm-release-tag", required=True)
    resume_parser.add_argument("--output", choices=("compact", "full"), default="compact")

    summary_parser = subparsers.add_parser("summary", help="Render a ledger decision projection.")
    summary_parser.add_argument("--ledger", required=True)
    summary_parser.add_argument("--output", choices=("compact", "full"), default="compact")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    reconfigure_stdio_utf8()
    args = parse_args(argv)
    try:
        if args.command == "plan":
            validate_release_identity(args.release_tag, args.release_commit)
            run_dir = Path(args.run_dir).expanduser().resolve()
            inventory = build_inventory(
                expected_roots=[Path(value) for value in args.expected_project_root],
                search_roots=[Path(value).expanduser().resolve() for value in args.search_root],
                canary_root=Path(args.canary_project_root),
                package_name=args.package_name,
                accept_discovered=args.accept_discovered,
                excluded_roots=[Path(value) for value in args.exclude_root],
            )
            preflight = build_preflight(
                inventory=inventory,
                unity_app=Path(args.unity_app),
                run_dir=run_dir,
                license_timeout_seconds=args.license_timeout_seconds,
            )
            ledger = build_ledger(
                run_dir=run_dir,
                release_tag=args.release_tag,
                release_commit=args.release_commit.lower(),
                inventory=inventory,
                preflight=preflight,
                worker_label=args.worker_label,
                worker_timeout_seconds=max(1, args.worker_timeout_seconds),
                overall_deadline_seconds=max(1, args.overall_deadline_seconds),
            )
            emit_ledger(ledger, args.output)
            return 0 if ledger["status"] == "planned" else 2

        ledger = load_ledger(Path(args.ledger).expanduser().resolve())
        if args.command == "execute":
            release_tag = str((ledger.get("release") or {}).get("tag") or "")
            if args.confirm_release_tag != release_tag:
                raise RolloutError("--confirm-release-tag does not match the frozen ledger release.")
            ledger = execute_rollout(ledger)
            emit_ledger(ledger, args.output)
            return 0 if ledger.get("status") == "completed" else 2
        if args.command == "cleanup-owned":
            ledger, cleaned = cleanup_owned_process(ledger, project_id=args.project_id)
            emit_ledger(ledger, args.output)
            return 0 if cleaned else 2
        if args.command == "resume-project":
            ledger = authorize_resume(
                ledger,
                project_id=args.project_id,
                confirm_release_tag=args.confirm_release_tag,
            )
            emit_ledger(ledger, args.output)
            return 0
        emit_ledger(ledger, args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RolloutError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "needs_smart_escalation",
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
