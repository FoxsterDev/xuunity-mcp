from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError

SDK_DEPENDENCY_VERIFY_KINDS = (
    "file_contains",
    "file_regex",
    "android_resolver_package",
    "gradle_dependency",
    "gradle_repository",
    "podfile_lock_pod",
)
_COORDINATE = re.compile(r"^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[^\s:'\"<>]+)?$")
_VERSION_PART = re.compile(r"\d+")


def run_sdk_dependency_verify(*, project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Check generated SDK dependency files against expectations by reading them on the host."""
    root = project_root.expanduser().resolve()
    expectations = config.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        raise ToolInvocationError(
            "missing_expectations",
            "unity_sdk_dependency_verify requires at least one expectation.",
        )
    stop_on_first_failure = bool(config.get("stopOnFirstFailure", False))
    results: list[dict[str, Any]] = []
    for raw in expectations:
        result = _verify_expectation(root, raw if isinstance(raw, dict) else {})
        results.append(result)
        if stop_on_first_failure and result["status"] == "failed":
            break
    passed = sum(1 for item in results if item["status"] == "passed")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    failed = len(results) - passed - skipped
    return {
        "backend_id": "xuunity.light_unity_mcp",
        "project_root": str(root),
        "status": "passed" if failed == 0 and results else "failed",
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "stop_on_first_failure": stop_on_first_failure,
        "results": results,
        "validation_evidence": "host_file_read",
        "executed_by": "host",
        "editor_required": False,
    }


def _verify_expectation(root: Path, expectation: dict[str, Any]) -> dict[str, Any]:
    kind = str(expectation.get("kind") or "").strip().lower() or "file_contains"
    result: dict[str, Any] = {
        "id": str(expectation.get("id") or ""),
        "platform": str(expectation.get("platform") or ""),
        "path": str(expectation.get("path") or ""),
        "full_path": "",
        "kind": kind,
        "value": str(expectation.get("value") or ""),
        "expected_version": str(expectation.get("version") or ""),
        "expected_min_version": str(expectation.get("minVersion") or ""),
        "actual_version": "",
        "status": "failed",
        "message": "",
        "file_exists": False,
        "file_size_bytes": 0,
        "sha256": "",
    }
    if not result["path"].strip():
        return _fail(result, "Expectation path is required.")
    full_path = _resolve_project_file(root, result["path"])
    if full_path is None:
        return _fail(result, "Path must resolve inside the Unity project root.")
    result["full_path"] = str(full_path)
    result["file_exists"] = full_path.is_file()
    if not result["file_exists"]:
        if bool(expectation.get("optional", False)):
            return _finish(result, "skipped", "Optional file is missing.")
        return _fail(result, "Expected file is missing.")
    try:
        data = full_path.read_bytes()
    except OSError as exc:
        return _fail(result, f"Expected file could not be read: {exc}")
    result["file_size_bytes"] = len(data)
    result["sha256"] = hashlib.sha256(data).hexdigest()
    content = data.decode("utf-8-sig", errors="replace")

    if kind in {"file_contains", "gradle_repository"}:
        return _check_contains(result, content)
    if kind == "file_regex":
        return _check_regex(result, content)
    if kind == "android_resolver_package":
        return _check_coordinate(result, content, r"<package>\s*{coordinate}:([^<\s]+)\s*</package>", "Android resolver package")
    if kind == "gradle_dependency":
        return _check_coordinate(result, content, r"['\"]{coordinate}:([^'\"@\s]+)(?:@[A-Za-z]+)?['\"]", "Gradle dependency")
    if kind == "podfile_lock_pod":
        return _check_podfile_lock_pod(result, content)
    return _fail(result, f"Unsupported dependency verification kind '{kind}'.")


def _resolve_project_file(root: Path, value: str) -> Path | None:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


def _check_contains(result: dict[str, Any], content: str) -> dict[str, Any]:
    if not result["value"].strip():
        return _fail(result, "Expected value is required.")
    if result["value"] in content:
        return _finish(result, "passed", "Expected value found.")
    return _fail(result, "Expected value was not found.")


def _check_regex(result: dict[str, Any], content: str) -> dict[str, Any]:
    if not result["value"].strip():
        return _fail(result, "Regex pattern is required.")
    try:
        matched = re.search(result["value"], content, re.MULTILINE) is not None
    except re.error as exc:
        return _fail(result, f"Regex pattern is invalid: {exc}")
    if matched:
        return _finish(result, "passed", "Expected regex matched.")
    return _fail(result, "Expected regex did not match.")


def _check_coordinate(result: dict[str, Any], content: str, template: str, label: str) -> dict[str, Any]:
    value = result["value"].strip()
    if not value:
        return _fail(result, f"Expected {label} spec is required.")
    if _COORDINATE.match(value) is None:
        return _check_contains(result, content)
    parts = value.split(":")
    coordinate = ":".join(parts[:2])
    expected = _normalize_version(result["expected_version"] or (parts[2] if len(parts) > 2 else ""))
    versions = [
        _normalize_version(match.group(1))
        for match in re.finditer(template.format(coordinate=re.escape(coordinate)), content)
    ]
    if not versions:
        return _fail(result, f"Expected {label} '{coordinate}' was not found.")
    result["actual_version"] = expected if expected in versions else versions[0]
    found = ", ".join(sorted(set(versions)))
    if expected and expected not in versions:
        return _fail(result, f"{label} version mismatch. Expected '{expected}', found '{found}'.")
    minimum = result["expected_min_version"]
    if minimum and _compare_versions(result["actual_version"], minimum) < 0:
        return _fail(
            result,
            f"{label} version '{result['actual_version']}' is lower than minimum '{_normalize_version(minimum)}'.",
        )
    return _finish(result, "passed", f"Expected {label} found at version '{result['actual_version']}'.")


def _check_podfile_lock_pod(result: dict[str, Any], content: str) -> dict[str, Any]:
    if not result["value"].strip():
        return _fail(result, "Expected pod name is required.")
    match = re.search(r"-\s+" + re.escape(result["value"]) + r"\s+\(([^)]+)\)", content)
    if match is None:
        return _fail(result, "Expected pod was not found.")
    result["actual_version"] = _normalize_version(match.group(1))
    expected = _normalize_version(result["expected_version"])
    if expected and result["actual_version"] != expected:
        return _fail(result, f"Pod version mismatch. Actual '{result['actual_version']}'.")
    minimum = result["expected_min_version"]
    if minimum and _compare_versions(result["actual_version"], minimum) < 0:
        return _fail(
            result,
            f"Pod version '{result['actual_version']}' is lower than minimum '{_normalize_version(minimum)}'.",
        )
    return _finish(result, "passed", "Expected pod version found.")


def _normalize_version(value: str) -> str:
    return str(value or "").strip().lstrip("=").strip().strip("[]").strip()


def _compare_versions(left: str, right: str) -> int:
    left_parts = _normalize_version(left).split(".")
    right_parts = _normalize_version(right).split(".")
    for index in range(max(len(left_parts), len(right_parts))):
        left_value = _version_part(left_parts, index)
        right_value = _version_part(right_parts, index)
        if left_value != right_value:
            return -1 if left_value < right_value else 1
    return 0


def _version_part(parts: list[str], index: int) -> int:
    if index >= len(parts):
        return 0
    match = _VERSION_PART.search(parts[index])
    return int(match.group(0)) if match else 0


def _finish(result: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    result["status"] = status
    result["message"] = message
    return result


def _fail(result: dict[str, Any], message: str) -> dict[str, Any]:
    return _finish(result, "failed", message)
