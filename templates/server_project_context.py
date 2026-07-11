from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from server_bridge_runtime import bridge_state_path, parse_journal_utc_timestamp, request_journal_dir
from server_core import ToolInvocationError, read_json

LIGHTWEIGHT_PACKAGE_NAME = "com.xuunity.light-mcp"
LIGHTWEIGHT_PACKAGE_TEMPLATE_MARKERS = (
    Path("packages/com.xuunity.light-mcp/package.json"),
    Path("AIRoot/Operations/XUUnityLightUnityMcp/packages/com.xuunity.light-mcp/package.json"),
)


def is_windows_like_host() -> bool:
    return (
        os.name == "nt"
        or sys.platform.startswith("win")
        or os.environ.get("OS") == "Windows_NT"
        or bool(os.environ.get("APPDATA"))
        or str(os.environ.get("MSYSTEM") or "").upper().startswith(("MINGW", "MSYS", "CYGWIN"))
    )


def project_not_found_error(raw_project_root: str, resolved_root: Path) -> ToolInvocationError:
    details: dict[str, Any] = {
        "raw_project_root": raw_project_root,
        "resolved_project_root": str(resolved_root),
    }
    message = f"Not a Unity project root: {resolved_root}"
    if is_windows_like_host():
        hint = (
            "On Windows, quote --project-root/--workspace-root values that contain spaces "
            "and prefer the .cmd launcher for setup commands; Git Bash can change native "
            "argument boundaries before Python receives argv."
        )
        details["windows_launcher_hint"] = hint
        details["recommended_launcher_flavor"] = "cmd"
        message = f"{message}. {hint}"
    return ToolInvocationError("project_not_found", message, details)


def ensure_project_root(project_root: str) -> Path:
    raw_project_root = str(project_root)
    root = Path(raw_project_root).expanduser().resolve()
    if not (root / "Assets").is_dir() or not (root / "ProjectSettings" / "ProjectVersion.txt").is_file():
        raise project_not_found_error(raw_project_root, root)
    return root


def find_latest_request_event(
    project_root: Path,
    operations: list[str] | None = None,
) -> dict[str, Any] | None:
    journal_dir = request_journal_dir(project_root)
    if not journal_dir.is_dir():
        return None

    normalized_operations = {
        str(operation).strip()
        for operation in (operations or [])
        if str(operation).strip()
    }

    matched: list[dict[str, Any]] = []
    for path in journal_dir.glob("*.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            continue

        operation = str(payload.get("operation") or "").strip()
        if normalized_operations and operation not in normalized_operations:
            continue

        event = dict(payload)
        event["_path"] = str(path)
        matched.append(event)

    matched.sort(
        key=lambda item: (
            parse_journal_utc_timestamp(item.get("event_at_utc")),
            str(item.get("event_id") or ""),
        )
    )
    return matched[-1] if matched else None


def find_repo_local_package_source(project_root: Path) -> Path | None:
    for candidate_root in (project_root, *project_root.parents):
        for marker_relative_path in LIGHTWEIGHT_PACKAGE_TEMPLATE_MARKERS:
            marker = candidate_root / marker_relative_path
            if marker.is_file():
                return marker.parent.resolve()
    return None


def inspect_package_dependency_alignment(project_root: Path) -> dict[str, Any]:
    manifest_path = project_root / "Packages" / "manifest.json"
    package_source = find_repo_local_package_source(project_root)
    result: dict[str, Any] = {
        "package_name": LIGHTWEIGHT_PACKAGE_NAME,
        "manifest_path": str(manifest_path),
        "dependency": "",
        "dependency_mode": "missing",
        "repo_local_package_source": str(package_source) if package_source else "",
        "repo_local_package_source_present": package_source is not None,
        "alignment": "unknown",
        "warning": "",
    }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["alignment"] = "manifest_unreadable"
        result["warning"] = f"Could not inspect manifest dependency: {exc}"
        return result

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        result["alignment"] = "dependencies_missing"
        result["warning"] = "Packages/manifest.json does not contain a dependencies object."
        return result

    dependency_value = dependencies.get(LIGHTWEIGHT_PACKAGE_NAME)
    if not isinstance(dependency_value, str) or not dependency_value.strip():
        result["alignment"] = "dependency_missing"
        result["warning"] = f"{LIGHTWEIGHT_PACKAGE_NAME} is not declared in Packages/manifest.json."
        return result

    dependency_value = dependency_value.strip()
    result["dependency"] = dependency_value

    if dependency_value.startswith("file:"):
        result["dependency_mode"] = "file"
        dependency_path = (manifest_path.parent / dependency_value[len("file:"):]).resolve()
        result["resolved_dependency_path"] = str(dependency_path)
        if package_source is None:
            result["alignment"] = "file_no_repo_local_reference"
        elif dependency_path == package_source:
            result["alignment"] = "aligned"
        else:
            result["alignment"] = "file_mismatch"
            result["warning"] = (
                "The project uses a file dependency, but it does not point at the repo-local "
                "AIRoot XUUnityLightUnityMcp package source."
            )
        return result

    if dependency_value.startswith(("http://", "https://", "git@", "ssh://")):
        result["dependency_mode"] = "git_or_remote"
    else:
        result["dependency_mode"] = "other"

    if result["dependency_mode"] == "git_or_remote":
        result["alignment"] = "git_pinned"
    else:
        result["alignment"] = "external_only"

    return result


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _lock_entry(lock: dict[str, Any]) -> dict[str, Any]:
    dependencies = lock.get("dependencies")
    if isinstance(dependencies, dict) and isinstance(dependencies.get(LIGHTWEIGHT_PACKAGE_NAME), dict):
        return dependencies[LIGHTWEIGHT_PACKAGE_NAME]
    entry = lock.get(LIGHTWEIGHT_PACKAGE_NAME)
    return entry if isinstance(entry, dict) else {}


def _package_cache_paths(project_root: Path) -> list[Path]:
    cache_root = project_root / "Library" / "PackageCache"
    if not cache_root.is_dir():
        return []
    matches = [
        path
        for path in cache_root.glob(f"{LIGHTWEIGHT_PACKAGE_NAME}@*")
        if path.is_dir()
    ]
    direct = cache_root / LIGHTWEIGHT_PACKAGE_NAME
    if direct.is_dir():
        matches.append(direct)
    return sorted({path.resolve() for path in matches}, key=lambda path: str(path))


def inspect_light_mcp_import_state(project_root: Path) -> dict[str, Any]:
    manifest_path = project_root / "Packages" / "manifest.json"
    lock_path = project_root / "Packages" / "packages-lock.json"
    cache_root = project_root / "Library" / "PackageCache"
    state_path = bridge_state_path(project_root)
    result: dict[str, Any] = {
        "package_name": LIGHTWEIGHT_PACKAGE_NAME,
        "manifest_path": str(manifest_path),
        "lock_path": str(lock_path),
        "package_cache_root": str(cache_root),
        "bridge_state_path": str(state_path),
        "manifest_declared": False,
        "manifest_dependency": "",
        "lock_entry_present": False,
        "lock_version": "",
        "lock_hash": "",
        "lock_source": "",
        "lock_dependency": "",
        "package_cache_present": False,
        "package_cache_paths": [],
        "bridge_state_present": state_path.is_file(),
        "import_state": "unknown",
        "warning": "",
    }

    try:
        manifest = _read_json_object(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result["warning"] = f"Could not inspect manifest dependency: {exc}"
        return result

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        result["warning"] = "Packages/manifest.json does not contain a dependencies object."
        return result

    manifest_dependency = str(dependencies.get(LIGHTWEIGHT_PACKAGE_NAME) or "").strip()
    result["manifest_dependency"] = manifest_dependency
    result["manifest_declared"] = bool(manifest_dependency)
    if not manifest_dependency:
        result["import_state"] = "not_declared"
        return result

    try:
        lock = _read_json_object(lock_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result["warning"] = f"Could not inspect packages-lock.json: {exc}"
        if result["bridge_state_present"]:
            result["import_state"] = "imported_or_bridge_state_present"
        else:
            result["import_state"] = "declared_not_resolved"
        return result

    lock_entry = _lock_entry(lock)
    result["lock_entry_present"] = bool(lock_entry)
    if lock_entry:
        result["lock_version"] = str(lock_entry.get("version") or "").strip()
        result["lock_hash"] = str(lock_entry.get("hash") or "").strip()
        result["lock_source"] = str(lock_entry.get("source") or "").strip()
        result["lock_dependency"] = str(
            lock_entry.get("dependency")
            or lock_entry.get("url")
            or lock_entry.get("source")
            or ""
        ).strip()

    cache_paths = _package_cache_paths(project_root)
    result["package_cache_paths"] = [str(path) for path in cache_paths]
    result["package_cache_present"] = bool(cache_paths)

    if result["bridge_state_present"]:
        result["import_state"] = "imported_or_bridge_state_present"
    elif not result["lock_entry_present"]:
        result["import_state"] = "declared_not_resolved"
    elif not result["package_cache_present"]:
        result["import_state"] = "resolved_not_cached"
    else:
        result["import_state"] = "cached_without_bridge_state"

    return result


GIT_DEPENDENCY_PREFIXES = ("http://", "https://", "git@", "ssh://", "git+")


def maybe_fail_fast_ensure_ready_package_state(
    project_root: Path,
    package_import_state: dict[str, Any],
    open_editor: bool,
) -> None:
    """Fail before the heartbeat wait when readiness is impossible.

    A package that is absent from Packages/manifest.json can never start the
    bridge, and a git dependency cannot resolve on first open without a git
    executable — both used to burn the full ensure-ready timeout.
    """
    import_state = str(package_import_state.get("import_state") or "")

    if import_state == "not_declared":
        raise ToolInvocationError(
            "package_not_declared",
            (
                f"{LIGHTWEIGHT_PACKAGE_NAME} is not declared in Packages/manifest.json for "
                f"{project_root}, so the editor bridge can never become ready. "
                "Run setup-plan and setup-apply for this project first."
            ),
            {
                "fail_fast_reason": "ensure_ready_package_not_declared",
                "package_import_state": package_import_state,
                "recommended_next_action": "run_setup_plan_then_setup_apply",
            },
        )

    if not open_editor:
        return

    manifest_dependency = str(package_import_state.get("manifest_dependency") or "")
    if (
        import_state == "declared_not_resolved"
        and manifest_dependency.startswith(GIT_DEPENDENCY_PREFIXES)
        and shutil.which("git") is None
    ):
        raise ToolInvocationError(
            "git_executable_missing_for_package_resolve",
            (
                "The package is declared as a git dependency "
                f"({manifest_dependency}) but no git executable is on PATH, so Unity cannot "
                "resolve it on first open. Install Git (Git for Windows on Windows) and retry."
            ),
            {
                "fail_fast_reason": "ensure_ready_git_missing_for_git_dependency",
                "manifest_dependency": manifest_dependency,
                "package_import_state": package_import_state,
                "recommended_next_action": "install_git_then_retry_ensure_ready",
            },
        )
