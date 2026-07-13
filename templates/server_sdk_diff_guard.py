from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, write_json


SDK_GENERATED_DIFF_GUARD_SCHEMA_VERSION = "xuunity.sdk-generated-diff-guard.v1"
DEFAULT_REPORT_RELATIVE_PATH = "Library/XUUnityLightMcp/sdk/generated_diff_guard.json"
_SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9._/@^~-]+$")
_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*$|#.*$", re.MULTILINE)


def run_sdk_generated_diff_guard(
    *,
    project_root: Path,
    config: dict[str, Any],
    report_file: str = "",
) -> dict[str, Any]:
    """Compare generated SDK files to a provenance-clean Git baseline.

    This first vertical slice deliberately supports only Git-tracked baselines.
    An unavailable baseline is unproven rather than a passing empty diff.
    """
    root = project_root.expanduser().resolve()
    git_prefix = _git_worktree_prefix(root)
    normalized = _normalize_config(config)
    baseline_ref = normalized["baseline_ref"]
    rows: list[dict[str, Any]] = []
    changed_paths: list[str] = []
    unexpected_changed_files: list[str] = []
    missing_current_files: list[str] = []
    required_marker_missing: list[str] = []
    stale_versions: list[dict[str, str]] = []
    current_text_by_path: dict[str, str] = {}

    for relative_path in normalized["tracked_paths"]:
        baseline_text = _git_show(root, baseline_ref, _git_path(git_prefix, relative_path))
        current_path = _safe_project_file(root, relative_path)
        current_exists = current_path.is_file()
        if not current_exists:
            missing_current_files.append(relative_path)
        current_text = _read_text(current_path) if current_exists else ""
        current_text_by_path[relative_path] = current_text
        changed = baseline_text != current_text
        if changed:
            changed_paths.append(relative_path)

        version_change = _matching_expected_version_change(
            normalized["expected_version_changes"],
            relative_path,
            baseline_text,
            current_text,
        )
        if changed and version_change is not None:
            change_class = "expected_dependency_update"
        elif changed and relative_path in normalized["expected_changed_allowlist"]:
            change_class = "resolver_normalization_noise"
        elif changed:
            change_class = "unexpected_mutation"
            unexpected_changed_files.append(relative_path)
        else:
            change_class = "unchanged"

        rows.append(
            {
                "path": relative_path,
                "baseline_source": "git_head",
                "baseline_ref": baseline_ref,
                "change_class": change_class,
                "baseline_sha256": _sha256_text(baseline_text),
                "current_sha256": _sha256_text(current_text) if current_exists else "",
                "current_file_exists": current_exists,
                "on_allowlist": relative_path in normalized["expected_changed_allowlist"],
            }
        )

    normalized_current_text = "\n".join(_strip_comments(value) for value in current_text_by_path.values())
    for marker in normalized["required_markers_after"]:
        if marker not in normalized_current_text:
            required_marker_missing.append(marker)

    for expected in normalized["expected_version_changes"]:
        current_text = current_text_by_path.get(expected["path"], "")
        if expected["from_value"] and expected["from_value"] in current_text:
            stale_versions.append(
                {
                    "path": expected["path"],
                    "previous_value": expected["from_value"],
                    "expected_value": expected["to_value"],
                }
            )

    failed = bool(required_marker_missing or stale_versions or missing_current_files)
    if normalized["fail_on_unexpected_changed_file"] and unexpected_changed_files:
        failed = True
    verdict = "failed" if failed else "passed"
    result: dict[str, Any] = {
        "schema_version": SDK_GENERATED_DIFF_GUARD_SCHEMA_VERSION,
        "operation": "unity.sdk.generated_diff_guard",
        "scope": "git_tracked_baseline",
        "verdict": verdict,
        "baseline_source": "git_head",
        "baseline_ref": baseline_ref,
        "tracked_path_count": len(rows),
        "changed_path_count": len(changed_paths),
        "changed_paths": changed_paths,
        "paths": rows,
        "required_marker_missing": required_marker_missing,
        "missing_current_files": missing_current_files,
        "stale_versions": stale_versions,
        "unexpected_changed_files": unexpected_changed_files,
        "fail_on_unexpected_changed_file": normalized["fail_on_unexpected_changed_file"],
        "recommended_next_action": _recommended_next_action(
            required_marker_missing=required_marker_missing,
            missing_current_files=missing_current_files,
            stale_versions=stale_versions,
            unexpected_changed_files=unexpected_changed_files,
        ),
    }
    output_path = _resolve_report_path(root, report_file)
    write_json(output_path, result)
    result["report_path"] = str(output_path)
    return result


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "Diff guard configuration must be an object.")
    if bool(config.get("captureBaseline", False)):
        raise ToolInvocationError(
            "sdk_generated_diff_guard_capture_baseline_unsupported",
            "This Git-tracked slice compares against an existing Git ref and does not capture Library baselines.",
        )
    baseline_source = str(config.get("baselineSource", "git_head") or "git_head").strip().lower()
    if baseline_source != "git_head":
        raise ToolInvocationError(
            "sdk_generated_diff_guard_baseline_source_unsupported",
            "This slice supports baselineSource=git_head only.",
            {"baselineSource": baseline_source},
        )
    baseline_ref = str(config.get("baselineRef", "HEAD") or "HEAD").strip()
    if not _SAFE_GIT_REF.fullmatch(baseline_ref):
        raise ToolInvocationError("sdk_generated_diff_guard_baseline_ref_invalid", "baselineRef contains unsupported characters.")

    tracked_paths = _string_list(config.get("trackedPaths"), "trackedPaths", required=True)
    allowlist = set(_string_list(config.get("expectedChangedAllowlist", []), "expectedChangedAllowlist"))
    markers = _string_list(config.get("requiredMarkersAfter", []), "requiredMarkersAfter")
    expected_versions = _normalize_expected_version_changes(config.get("expectedVersionChanges", []), tracked_paths)
    fail_on_unexpected = config.get("failOnUnexpectedChangedFile", True)
    if not isinstance(fail_on_unexpected, bool):
        raise ToolInvocationError(
            "sdk_generated_diff_guard_config_invalid",
            "failOnUnexpectedChangedFile must be a boolean.",
        )
    return {
        "baseline_ref": baseline_ref,
        "tracked_paths": tracked_paths,
        "expected_changed_allowlist": allowlist,
        "required_markers_after": markers,
        "expected_version_changes": expected_versions,
        "fail_on_unexpected_changed_file": fail_on_unexpected,
    }


def _string_list(value: Any, field: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        suffix = " and contain at least one path" if required else ""
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", f"{field} must be an array{suffix}.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", f"{field} entries must be non-empty strings.")
        normalized = item.strip().replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized or normalized == "..":
            raise ToolInvocationError("sdk_generated_diff_guard_path_invalid", f"{field} path must stay under the project root.")
        result.append(normalized)
    if len(set(result)) != len(result):
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", f"{field} must not contain duplicates.")
    return result


def _normalize_expected_version_changes(value: Any, tracked_paths: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "expectedVersionChanges must be an array.")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "expectedVersionChanges entries must be objects.")
        path = str(item.get("path") or "").strip().replace("\\", "/")
        from_value = str(item.get("fromValue") or "")
        to_value = str(item.get("toValue") or "")
        if path not in tracked_paths or not from_value or not to_value:
            raise ToolInvocationError(
                "sdk_generated_diff_guard_config_invalid",
                "Each expectedVersionChanges entry needs a tracked path plus fromValue and toValue.",
            )
        result.append({"path": path, "from_value": from_value, "to_value": to_value})
    return result


def _git_worktree_prefix(project_root: Path) -> str:
    result = _run_git(project_root, ["rev-parse", "--is-inside-work-tree"], "sdk_generated_diff_guard_git_unavailable")
    if result.stdout.strip() != "true":
        raise ToolInvocationError("sdk_generated_diff_guard_git_unavailable", "projectRoot is not inside a Git worktree.")
    prefix_result = _run_git(project_root, ["rev-parse", "--show-prefix"], "sdk_generated_diff_guard_git_unavailable")
    return prefix_result.stdout.strip().strip("/")


def _git_path(prefix: str, relative_path: str) -> str:
    return f"{prefix}/{relative_path}" if prefix else relative_path


def _git_show(project_root: Path, baseline_ref: str, relative_path: str) -> str:
    result = _run_git(
        project_root,
        ["show", f"{baseline_ref}:{relative_path}"],
        "sdk_generated_diff_guard_baseline_unavailable",
    )
    return result.stdout


def _run_git(project_root: Path, args: list[str], error_code: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolInvocationError(error_code, f"Git baseline command could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Git did not return baseline content.").strip()
        raise ToolInvocationError(error_code, detail[:300])
    return result


def _safe_project_file(project_root: Path, relative_path: str) -> Path:
    candidate = (project_root / relative_path).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ToolInvocationError("sdk_generated_diff_guard_path_invalid", "trackedPaths must stay under projectRoot.") from exc
    return candidate


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolInvocationError("sdk_generated_diff_guard_file_unreadable", f"Expected text file is not UTF-8: {path.name}") from exc
    except OSError as exc:
        raise ToolInvocationError("sdk_generated_diff_guard_file_unreadable", str(exc)) from exc


def _matching_expected_version_change(
    expected_changes: list[dict[str, str]],
    path: str,
    baseline_text: str,
    current_text: str,
) -> dict[str, str] | None:
    for change in expected_changes:
        if change["path"] != path:
            continue
        if change["from_value"] in baseline_text and change["to_value"] in current_text:
            return change
    return None


def _strip_comments(value: str) -> str:
    return _LINE_COMMENT.sub("", _XML_COMMENT.sub("", value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_report_path(project_root: Path, report_file: str) -> Path:
    candidate = Path(report_file).expanduser() if report_file else project_root / DEFAULT_REPORT_RELATIVE_PATH
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ToolInvocationError("sdk_generated_diff_guard_report_path_invalid", "reportFile must stay under projectRoot.") from exc
    return candidate


def _recommended_next_action(
    *,
    required_marker_missing: list[str],
    missing_current_files: list[str],
    stale_versions: list[dict[str, str]],
    unexpected_changed_files: list[str],
) -> str:
    if missing_current_files:
        return "restore_missing_generated_files_or_review_resolver_output"
    if required_marker_missing:
        return "restore_required_generated_markers_or_review_resolver_output"
    if stale_versions:
        return "rerun_resolver_and_verify_expected_native_versions"
    if unexpected_changed_files:
        return "review_or_revert_unexpected_generated_file_changes"
    return "none"
