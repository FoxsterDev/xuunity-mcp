from __future__ import annotations

import hashlib
import json
import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from server_core import ToolInvocationError, hidden_window_subprocess_kwargs, read_json, write_json


SDK_GENERATED_DIFF_GUARD_SCHEMA_VERSION = "xuunity.sdk-generated-diff-guard.v2"
SDK_GENERATED_DIFF_BASELINE_SCHEMA_VERSION = "xuunity.sdk-generated-diff-baseline.v1"
DEFAULT_REPORT_RELATIVE_PATH = "Library/XUUnityLightMcp/sdk/generated_diff_guard.json"
DEFAULT_LIBRARY_BASELINE_DIR = "Library/XUUnityLightMcp/sdk/baseline/default"
LIBRARY_BASELINE_ROOT = "Library/XUUnityLightMcp/sdk/baseline"
LIBRARY_BASELINE_MANIFEST = "baseline_manifest.json"
_SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9._/@^~-]+$")
_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DIFF_MODES = {"xml_structural", "gradle_tokenized", "line_normalized"}
_DEFAULT_DIFF_MODES = {
    "*.xml": "xml_structural",
    "*.gradle": "gradle_tokenized",
    "*": "line_normalized",
}


def run_sdk_generated_diff_guard(
    *,
    project_root: Path,
    config: dict[str, Any],
    report_file: str = "",
) -> dict[str, Any]:
    """Compare generated SDK files to provenance-clean Git or fingerprint-bound baselines."""
    root = project_root.expanduser().resolve()
    git_prefix = _git_worktree_prefix(root)
    normalized = _normalize_config(config)
    baseline_ref = normalized["baseline_ref"]
    _git_assert_ref(root, baseline_ref)
    git_tracked_by_path = {
        relative_path: _git_blob_exists(root, baseline_ref, _git_path(git_prefix, relative_path))
        for relative_path in normalized["tracked_paths"]
    }
    library_paths = [path for path, git_tracked in git_tracked_by_path.items() if not git_tracked]
    library_baseline_dir = _resolve_library_baseline_dir(root, normalized["library_baseline_dir"])
    baseline_fingerprint = ""
    fingerprint_match: bool | None = None
    library_manifest: dict[str, Any] = {}
    if library_paths:
        fingerprint_inputs = _build_baseline_fingerprint_inputs(root, normalized)
        baseline_fingerprint = _baseline_fingerprint(fingerprint_inputs)
        if normalized["capture_baseline"]:
            _assert_baseline_capture_clean(root, library_paths)
            library_manifest = _capture_library_baseline(
                project_root=root,
                baseline_dir=library_baseline_dir,
                relative_paths=library_paths,
                fingerprint=baseline_fingerprint,
                fingerprint_inputs=fingerprint_inputs,
                diff_modes=normalized["diff_modes"],
                required_markers=normalized["required_markers_after"],
                marker_paths=normalized["tracked_paths"],
            )
            fingerprint_match = True
        else:
            library_manifest = _load_library_baseline_manifest(library_baseline_dir)
            recorded_fingerprint = str(library_manifest.get("baseline_fingerprint") or "")
            fingerprint_match = recorded_fingerprint == baseline_fingerprint
            if not fingerprint_match:
                raise ToolInvocationError(
                    "baseline_fingerprint_stale",
                    "The Library baseline fingerprint does not match the current project, Unity, package-lock, and SDK-version inputs.",
                    {
                        "recorded_fingerprint": recorded_fingerprint,
                        "current_fingerprint": baseline_fingerprint,
                    },
                )
    elif normalized["capture_baseline"]:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_capture_baseline_not_needed",
            "Every tracked path has a Git baseline; captureBaseline is only for Git-untracked generated outputs.",
        )
    rows: list[dict[str, Any]] = []
    changed_paths: list[str] = []
    unexpected_changed_files: list[str] = []
    missing_current_files: list[str] = []
    required_marker_missing: list[str] = []
    stale_versions: list[dict[str, str]] = []
    invalid_generated_files: list[dict[str, str]] = []
    current_text_by_path: dict[str, str] = {}
    comment_free_current_text_by_path: dict[str, str] = {}
    diff_mode_by_path: dict[str, str] = {}

    for relative_path in normalized["tracked_paths"]:
        if git_tracked_by_path[relative_path]:
            baseline_source = "git_head"
            baseline_text = _git_show(root, baseline_ref, _git_path(git_prefix, relative_path))
        else:
            baseline_source = "library_fingerprint"
            baseline_text = _read_library_baseline(
                baseline_dir=library_baseline_dir,
                manifest=library_manifest,
                relative_path=relative_path,
            )
        current_path = _safe_project_file(root, relative_path)
        current_exists = current_path.is_file()
        if not current_exists:
            missing_current_files.append(relative_path)
        current_text = _read_text(current_path) if current_exists else ""
        current_text_by_path[relative_path] = current_text
        diff_mode = _diff_mode_for_path(relative_path, normalized["diff_modes"])
        diff_mode_by_path[relative_path] = diff_mode
        try:
            comment_free_current_text_by_path[relative_path] = _comment_free_text(current_text, diff_mode)
        except ValueError:
            comment_free_current_text_by_path[relative_path] = ""
        changed = baseline_text != current_text
        if changed:
            changed_paths.append(relative_path)

        normalization_error = ""
        semantic_changed = changed
        try:
            baseline_normalized = _normalize_diff_text(baseline_text, diff_mode)
            current_normalized = _normalize_diff_text(current_text, diff_mode) if current_exists else ""
            semantic_changed = baseline_normalized != current_normalized
        except ValueError as exc:
            normalization_error = str(exc)
            invalid_generated_files.append(
                {
                    "path": relative_path,
                    "diff_mode": diff_mode,
                    "reason": normalization_error,
                }
            )

        version_change = _matching_expected_version_change(
            normalized["expected_version_changes"],
            relative_path,
            baseline_text,
            current_text,
        )
        expected_version_only = False
        if changed and version_change is not None and not normalization_error:
            expected_baseline = baseline_text.replace(version_change["from_value"], version_change["to_value"])
            expected_version_only = _normalize_diff_text(expected_baseline, diff_mode) == current_normalized

        if normalization_error:
            change_class = "invalid_generated_file"
        elif changed and not semantic_changed:
            change_class = "resolver_normalization_noise"
        elif changed and expected_version_only:
            change_class = "expected_dependency_update"
        elif changed and relative_path in normalized["expected_changed_allowlist"]:
            change_class = "expected_allowlisted_change"
        elif changed:
            change_class = "unexpected_mutation"
            unexpected_changed_files.append(relative_path)
        else:
            change_class = "unchanged"

        rows.append(
            {
                "path": relative_path,
                "baseline_source": baseline_source,
                "baseline_ref": baseline_ref if baseline_source == "git_head" else "",
                "change_class": change_class,
                "diff_mode": diff_mode,
                "semantic_changed": semantic_changed,
                "baseline_sha256": _sha256_text(baseline_text),
                "current_sha256": _sha256_text(current_text) if current_exists else "",
                "current_file_exists": current_exists,
                "on_allowlist": relative_path in normalized["expected_changed_allowlist"],
                "normalization_error": normalization_error,
            }
        )

    for marker in normalized["required_markers_after"]:
        if not any(
            _marker_present(marker, current_text_by_path[path], diff_mode_by_path[path])
            for path in normalized["tracked_paths"]
        ):
            required_marker_missing.append(marker)

    for row in rows:
        path = row["path"]
        markers_present = [
            marker
            for marker in normalized["required_markers_after"]
            if _marker_present(marker, current_text_by_path.get(path, ""), diff_mode_by_path[path])
        ]
        row["markers_present"] = markers_present
        row["markers_missing"] = [
            marker for marker in normalized["required_markers_after"] if marker not in markers_present
        ]

    if not normalized["capture_baseline"]:
        for expected in normalized["expected_version_changes"]:
            current_text = comment_free_current_text_by_path.get(expected["path"], "")
            if expected["from_value"] and expected["from_value"] in current_text:
                stale_versions.append(
                    {
                        "path": expected["path"],
                        "previous_value": expected["from_value"],
                        "expected_value": expected["to_value"],
                    }
                )

    failed = bool(required_marker_missing or stale_versions or missing_current_files or invalid_generated_files)
    if normalized["fail_on_unexpected_changed_file"] and unexpected_changed_files:
        failed = True
    verdict = "failed" if failed else "passed"
    result: dict[str, Any] = {
        "schema_version": SDK_GENERATED_DIFF_GUARD_SCHEMA_VERSION,
        "operation": "unity.sdk.generated_diff_guard",
        "scope": _baseline_scope(git_tracked_by_path),
        "verdict": verdict,
        "baseline_source": _baseline_source(git_tracked_by_path),
        "baseline_ref": baseline_ref,
        "baseline_captured": bool(normalized["capture_baseline"] and library_paths),
        "library_baseline_dir": str(library_baseline_dir) if library_paths else "",
        "baseline_fingerprint": baseline_fingerprint,
        "fingerprint_match": fingerprint_match,
        "tracked_path_count": len(rows),
        "changed_path_count": len(changed_paths),
        "changed_paths": changed_paths,
        "paths": rows,
        "required_marker_missing": required_marker_missing,
        "missing_current_files": missing_current_files,
        "invalid_generated_files": invalid_generated_files,
        "stale_versions": stale_versions,
        "unexpected_changed_files": unexpected_changed_files,
        "fail_on_unexpected_changed_file": normalized["fail_on_unexpected_changed_file"],
        "recommended_next_action": _recommended_next_action(
            required_marker_missing=required_marker_missing,
            missing_current_files=missing_current_files,
            invalid_generated_files=invalid_generated_files,
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
    capture_baseline = config.get("captureBaseline", False)
    if not isinstance(capture_baseline, bool):
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "captureBaseline must be a boolean.")
    baseline_source = str(config.get("baselineSource", "git_head") or "git_head").strip().lower()
    if baseline_source != "git_head":
        raise ToolInvocationError(
            "sdk_generated_diff_guard_baseline_source_unsupported",
            "baselineSource must be git_head; Git-untracked paths automatically use the fingerprint-bound Library fallback.",
            {"baselineSource": baseline_source},
        )
    baseline_ref = str(config.get("baselineRef", "HEAD") or "HEAD").strip()
    if not _SAFE_GIT_REF.fullmatch(baseline_ref):
        raise ToolInvocationError("sdk_generated_diff_guard_baseline_ref_invalid", "baselineRef contains unsupported characters.")

    tracked_paths = _string_list(config.get("trackedPaths"), "trackedPaths", required=True)
    allowlist = set(_string_list(config.get("expectedChangedAllowlist", []), "expectedChangedAllowlist"))
    markers = _string_list(config.get("requiredMarkersAfter", []), "requiredMarkersAfter")
    expected_versions = _normalize_expected_version_changes(config.get("expectedVersionChanges", []), tracked_paths)
    tracked_sdk_versions = _normalize_tracked_sdk_versions(config.get("trackedSdkVersions", {}))
    diff_modes = _normalize_diff_modes(config.get("diffMode", _DEFAULT_DIFF_MODES))
    fail_on_unexpected = config.get("failOnUnexpectedChangedFile", True)
    if not isinstance(fail_on_unexpected, bool):
        raise ToolInvocationError(
            "sdk_generated_diff_guard_config_invalid",
            "failOnUnexpectedChangedFile must be a boolean.",
        )
    return {
        "baseline_ref": baseline_ref,
        "baseline_source": baseline_source,
        "library_baseline_dir": str(config.get("libraryBaselineDir", DEFAULT_LIBRARY_BASELINE_DIR) or DEFAULT_LIBRARY_BASELINE_DIR),
        "capture_baseline": capture_baseline,
        "tracked_paths": tracked_paths,
        "expected_changed_allowlist": allowlist,
        "required_markers_after": markers,
        "expected_version_changes": expected_versions,
        "tracked_sdk_versions": tracked_sdk_versions,
        "diff_modes": diff_modes,
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


def _normalize_tracked_sdk_versions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "trackedSdkVersions must be an object.")
    result: dict[str, str] = {}
    for raw_name, raw_version in value.items():
        name = str(raw_name or "").strip()
        version = str(raw_version or "").strip()
        if not name or not version:
            raise ToolInvocationError(
                "sdk_generated_diff_guard_config_invalid",
                "trackedSdkVersions keys and values must be non-empty strings.",
            )
        result[name] = version
    return dict(sorted(result.items()))


def _normalize_diff_modes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ToolInvocationError("sdk_generated_diff_guard_config_invalid", "diffMode must be a non-empty object.")
    result: dict[str, str] = {}
    for raw_pattern, raw_mode in value.items():
        if not isinstance(raw_pattern, str) or not raw_pattern.strip():
            raise ToolInvocationError(
                "sdk_generated_diff_guard_config_invalid",
                "diffMode patterns must be non-empty strings.",
            )
        pattern = raw_pattern.strip().replace("\\", "/")
        mode = str(raw_mode or "").strip().lower()
        if mode not in _DIFF_MODES:
            raise ToolInvocationError(
                "sdk_generated_diff_guard_config_invalid",
                f"diffMode[{pattern}] must be one of: {', '.join(sorted(_DIFF_MODES))}.",
            )
        result[pattern] = mode
    if "*" not in result:
        result["*"] = "line_normalized"
    return result


def _git_worktree_prefix(project_root: Path) -> str:
    result = _run_git(project_root, ["rev-parse", "--is-inside-work-tree"], "sdk_generated_diff_guard_git_unavailable")
    if result.stdout.strip() != "true":
        raise ToolInvocationError("sdk_generated_diff_guard_git_unavailable", "projectRoot is not inside a Git worktree.")
    prefix_result = _run_git(project_root, ["rev-parse", "--show-prefix"], "sdk_generated_diff_guard_git_unavailable")
    return prefix_result.stdout.strip().strip("/")


def _git_path(prefix: str, relative_path: str) -> str:
    return f"{prefix}/{relative_path}" if prefix else relative_path


def _git_assert_ref(project_root: Path, baseline_ref: str) -> None:
    _run_git(
        project_root,
        ["rev-parse", "--verify", f"{baseline_ref}^{{commit}}"],
        "sdk_generated_diff_guard_baseline_unavailable",
    )


def _git_blob_exists(project_root: Path, baseline_ref: str, relative_path: str) -> bool:
    result = _run_git_unchecked(project_root, ["cat-file", "-e", f"{baseline_ref}:{relative_path}"])
    if result.returncode == 0:
        return True
    if result.returncode == 128:
        return False
    detail = (result.stderr or result.stdout or "Git could not inspect the baseline path.").strip()
    raise ToolInvocationError("sdk_generated_diff_guard_baseline_unavailable", detail[:300])


def _git_show(project_root: Path, baseline_ref: str, relative_path: str) -> str:
    result = _run_git(
        project_root,
        ["show", f"{baseline_ref}:{relative_path}"],
        "sdk_generated_diff_guard_baseline_unavailable",
    )
    return result.stdout


def _run_git(project_root: Path, args: list[str], error_code: str) -> subprocess.CompletedProcess[str]:
    result = _run_git_unchecked(project_root, args, error_code=error_code)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Git did not return baseline content.").strip()
        raise ToolInvocationError(error_code, detail[:300])
    return result


def _run_git_unchecked(
    project_root: Path,
    args: list[str],
    *,
    error_code: str = "sdk_generated_diff_guard_git_unavailable",
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            **hidden_window_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolInvocationError(error_code, f"Git baseline command could not run: {exc}") from exc
    return result


def _resolve_library_baseline_dir(project_root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()
    allowed_root = (project_root / LIBRARY_BASELINE_ROOT).resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_library_baseline_dir_invalid",
            f"libraryBaselineDir must stay under {LIBRARY_BASELINE_ROOT}.",
        ) from exc
    return candidate


def _build_baseline_fingerprint_inputs(project_root: Path, normalized: dict[str, Any]) -> dict[str, Any]:
    project_version_path = project_root / "ProjectSettings" / "ProjectVersion.txt"
    packages_lock_path = project_root / "Packages" / "packages-lock.json"
    project_version_text = _read_text(project_version_path)
    match = re.search(r"^m_EditorVersion:\s*(\S+)\s*$", project_version_text, re.MULTILINE)
    if match is None:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_fingerprint_input_unavailable",
            "ProjectSettings/ProjectVersion.txt does not contain m_EditorVersion.",
        )
    try:
        packages_lock_bytes = packages_lock_path.read_bytes()
    except OSError as exc:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_fingerprint_input_unavailable",
            "Packages/packages-lock.json is required for a fingerprint-bound Library baseline.",
        ) from exc
    expected_versions = [
        {
            "path": item["path"],
            "from_value": item["from_value"],
            "to_value": item["to_value"],
        }
        for item in normalized["expected_version_changes"]
    ]
    return {
        "project_root": str(project_root),
        "unity_version": match.group(1),
        "packages_lock_sha256": hashlib.sha256(packages_lock_bytes).hexdigest(),
        "tracked_sdk_versions": normalized["tracked_sdk_versions"],
        "expected_version_changes": expected_versions,
    }


def _baseline_fingerprint(inputs: dict[str, Any]) -> str:
    payload = json.dumps(inputs, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assert_baseline_capture_clean(project_root: Path, library_paths: list[str]) -> None:
    tracked_dirty = _run_git_unchecked(project_root, ["diff", "--quiet", "--", "."])
    staged_dirty = _run_git_unchecked(project_root, ["diff", "--cached", "--quiet", "--", "."])
    if tracked_dirty.returncode not in {0, 1} or staged_dirty.returncode not in {0, 1}:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_git_unavailable",
            "Git could not determine whether the project tree is clean enough for baseline capture.",
        )
    untracked_result = _run_git(
        project_root,
        ["ls-files", "--others", "--exclude-standard", "-z", "--", "."],
        "sdk_generated_diff_guard_git_unavailable",
    )
    allowed_untracked = {path.replace("\\", "/") for path in library_paths}
    other_untracked = {
        path.replace("\\", "/")
        for path in untracked_result.stdout.split("\0")
        if path and path.replace("\\", "/") not in allowed_untracked
    }
    if tracked_dirty.returncode == 1 or staged_dirty.returncode == 1 or other_untracked:
        raise ToolInvocationError(
            "baseline_capture_dirty_tree",
            "Library baseline capture requires a clean project tree apart from the selected Git-untracked generated outputs.",
            {
                "tracked_changes_present": tracked_dirty.returncode == 1,
                "staged_changes_present": staged_dirty.returncode == 1,
                "other_untracked_count": len(other_untracked),
            },
        )


def _capture_library_baseline(
    *,
    project_root: Path,
    baseline_dir: Path,
    relative_paths: list[str],
    fingerprint: str,
    fingerprint_inputs: dict[str, Any],
    diff_modes: dict[str, str],
    required_markers: list[str],
    marker_paths: list[str],
) -> dict[str, Any]:
    entries: dict[str, dict[str, str]] = {}
    marker_text_by_path = {
        relative_path: _read_text(current_path)
        for relative_path in marker_paths
        if (current_path := _safe_project_file(project_root, relative_path)).is_file()
    }
    for relative_path in relative_paths:
        current_path = _safe_project_file(project_root, relative_path)
        if not current_path.is_file():
            raise ToolInvocationError(
                "sdk_generated_diff_guard_baseline_capture_file_missing",
                f"Cannot capture missing Git-untracked generated file: {relative_path}",
            )
        current_text = _read_text(current_path)
        diff_mode = _diff_mode_for_path(relative_path, diff_modes)
        try:
            _normalize_diff_text(current_text, diff_mode)
        except ValueError as exc:
            raise ToolInvocationError(
                "sdk_generated_diff_guard_baseline_capture_invalid_generated_file",
                f"Cannot capture an invalid {diff_mode} generated file: {relative_path} ({exc})",
            ) from exc
        snapshot_path = _safe_library_baseline_file(baseline_dir, relative_path)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(current_text, encoding="utf-8")
        entries[relative_path] = {
            "snapshot_relative_path": f"files/{relative_path}",
            "sha256": _sha256_text(current_text),
        }
    missing_markers = [
        marker
        for marker in required_markers
        if not any(
            _marker_present(marker, marker_text_by_path[path], _diff_mode_for_path(path, diff_modes))
            for path in marker_text_by_path
        )
    ]
    if missing_markers:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_baseline_capture_required_marker_missing",
            "Cannot capture a baseline that is already missing required generated markers.",
            {"required_marker_missing": missing_markers},
        )
    manifest = {
        "schema_version": SDK_GENERATED_DIFF_BASELINE_SCHEMA_VERSION,
        "baseline_fingerprint": fingerprint,
        "fingerprint_inputs": fingerprint_inputs,
        "paths": entries,
    }
    write_json(baseline_dir / LIBRARY_BASELINE_MANIFEST, manifest)
    return manifest


def _load_library_baseline_manifest(baseline_dir: Path) -> dict[str, Any]:
    manifest_path = baseline_dir / LIBRARY_BASELINE_MANIFEST
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_library_baseline_unavailable",
            "No readable fingerprint-bound Library baseline exists; run once with captureBaseline=true from a clean tree.",
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SDK_GENERATED_DIFF_BASELINE_SCHEMA_VERSION:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_library_baseline_unavailable",
            "The Library baseline manifest schema is missing or unsupported.",
        )
    return manifest


def _read_library_baseline(*, baseline_dir: Path, manifest: dict[str, Any], relative_path: str) -> str:
    entries = manifest.get("paths")
    entry = entries.get(relative_path) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        raise ToolInvocationError(
            "sdk_generated_diff_guard_library_baseline_unavailable",
            f"The Library baseline does not contain: {relative_path}",
        )
    snapshot_path = _safe_library_baseline_file(baseline_dir, relative_path)
    baseline_text = _read_text(snapshot_path)
    recorded_sha256 = str(entry.get("sha256") or "")
    if not recorded_sha256 or _sha256_text(baseline_text) != recorded_sha256:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_library_baseline_integrity_mismatch",
            f"The Library baseline snapshot hash does not match its manifest: {relative_path}",
        )
    return baseline_text


def _safe_library_baseline_file(baseline_dir: Path, relative_path: str) -> Path:
    files_root = (baseline_dir / "files").resolve()
    candidate = (files_root / relative_path).resolve()
    try:
        candidate.relative_to(files_root)
    except ValueError as exc:
        raise ToolInvocationError(
            "sdk_generated_diff_guard_path_invalid",
            "Library baseline paths must stay under the selected baseline directory.",
        ) from exc
    return candidate


def _baseline_source(git_tracked_by_path: dict[str, bool]) -> str:
    sources = set(git_tracked_by_path.values())
    if sources == {True}:
        return "git_head"
    if sources == {False}:
        return "library_fingerprint"
    return "mixed"


def _baseline_scope(git_tracked_by_path: dict[str, bool]) -> str:
    source = _baseline_source(git_tracked_by_path)
    if source == "git_head":
        return "git_tracked_baseline"
    if source == "library_fingerprint":
        return "git_untracked_fingerprint_baseline"
    return "mixed_git_and_library_baseline"


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


def _diff_mode_for_path(path: str, diff_modes: dict[str, str]) -> str:
    matches = [
        (pattern, mode)
        for pattern, mode in diff_modes.items()
        if pattern != "*" and fnmatchcase(path, pattern)
    ]
    if matches:
        pattern, mode = max(matches, key=lambda item: (len(item[0].replace("*", "")), len(item[0])))
        return mode
    return diff_modes["*"]


def _normalize_diff_text(value: str, diff_mode: str) -> str:
    if diff_mode == "xml_structural":
        return _normalize_xml(value)
    if diff_mode == "gradle_tokenized":
        return _normalize_gradle(value)
    if diff_mode == "line_normalized":
        return _normalize_lines(value)
    raise ValueError(f"unsupported diff mode: {diff_mode}")


def _normalize_xml(value: str) -> str:
    try:
        root = ElementTree.fromstring(value)
    except ElementTree.ParseError as exc:
        raise ValueError(f"xml_parse_error:{exc.code}") from exc

    def canonical(element: ElementTree.Element) -> dict[str, Any]:
        children = [canonical(child) for child in list(element)]
        children.sort(key=lambda child: json.dumps(child, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return {
            "tag": str(element.tag),
            "attributes": sorted((str(key), _collapse_whitespace(val)) for key, val in element.attrib.items()),
            "text": _collapse_whitespace(element.text or ""),
            "children": children,
        }

    return json.dumps(canonical(root), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _normalize_gradle(value: str) -> str:
    tokens = _gradle_tokens(value, keep_newlines=True)
    units, next_index = _parse_gradle_units(tokens, 0, nested=False)
    if next_index != len(tokens):
        raise ValueError("gradle_unbalanced_closing_brace")
    return json.dumps(units, ensure_ascii=True, separators=(",", ":"))


def _parse_gradle_units(tokens: list[str], start: int, *, nested: bool) -> tuple[list[Any], int]:
    units: list[Any] = []
    pending: list[str] = []
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token == "}":
            if not nested:
                raise ValueError("gradle_unbalanced_closing_brace")
            _flush_gradle_statement(units, pending)
            return _sort_adjacent_gradle_blocks(units), index + 1
        if token != "{":
            pending.append(token)
            index += 1
            continue

        while pending and pending[-1] == "\n":
            pending.pop()
        boundary = max(
            (position for position, value in enumerate(pending) if value in {"\n", ";"}),
            default=-1,
        )
        prefix = pending[: boundary + 1]
        header = [value for value in pending[boundary + 1 :] if value != "\n"]
        if not header:
            raise ValueError("gradle_block_header_missing")
        _flush_gradle_statement(units, prefix)
        pending = []
        body, index = _parse_gradle_units(tokens, index + 1, nested=True)
        units.append(["block", header, body])

    if nested:
        raise ValueError("gradle_unclosed_block")
    _flush_gradle_statement(units, pending)
    return _sort_adjacent_gradle_blocks(units), index


def _flush_gradle_statement(units: list[Any], pending: list[str]) -> None:
    statement = [token for token in pending if token != "\n"]
    if statement:
        units.append(["statement", statement])


def _sort_adjacent_gradle_blocks(units: list[Any]) -> list[Any]:
    result: list[Any] = []
    index = 0
    while index < len(units):
        if units[index][0] != "block":
            result.append(units[index])
            index += 1
            continue
        end = index
        while end < len(units) and units[end][0] == "block":
            end += 1
        result.extend(sorted(units[index:end], key=lambda unit: json.dumps(unit, ensure_ascii=True, separators=(",", ":"))))
        index = end
    return result


def _normalize_lines(value: str) -> str:
    uncommented = _strip_code_comments(_XML_COMMENT.sub("", value))
    return "\n".join(
        normalized
        for line in uncommented.splitlines()
        if (normalized := _collapse_whitespace(line))
    )


def _comment_free_text(value: str, diff_mode: str) -> str:
    if diff_mode == "xml_structural":
        return _XML_COMMENT.sub("", value)
    return _strip_code_comments(value)


def _marker_present(marker: str, value: str, diff_mode: str) -> bool:
    try:
        comment_free = _comment_free_text(value, diff_mode)
    except ValueError:
        return False
    if marker in comment_free:
        return True
    if diff_mode == "gradle_tokenized":
        try:
            marker_tokens = _gradle_tokens(marker, keep_newlines=False)
            value_tokens = _gradle_tokens(value, keep_newlines=False)
        except ValueError:
            return False
        return bool(marker_tokens) and _contains_token_sequence(value_tokens, marker_tokens)
    return _collapse_whitespace(marker) in _collapse_whitespace(comment_free)


def _contains_token_sequence(values: list[str], expected: list[str]) -> bool:
    limit = len(values) - len(expected) + 1
    return any(values[index : index + len(expected)] == expected for index in range(max(0, limit)))


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _strip_code_comments(value: str) -> str:
    tokens = _gradle_tokens(value, keep_newlines=True, preserve_whitespace=True)
    return "".join("\n" if token == "\n" else token for token in tokens)


def _gradle_tokens(
    value: str,
    *,
    keep_newlines: bool,
    preserve_whitespace: bool = False,
) -> list[str]:
    tokens: list[str] = []
    index = 0
    line_start = True
    while index < len(value):
        char = value[index]
        if char == "\r" or char == "\n":
            if char == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
                index += 1
            if keep_newlines:
                tokens.append("\n")
            line_start = True
            index += 1
            continue
        if char.isspace():
            start = index
            while index < len(value) and value[index].isspace() and value[index] not in "\r\n":
                index += 1
            if preserve_whitespace:
                tokens.append(value[start:index])
            continue
        if value.startswith("//", index):
            index = _skip_to_line_end(value, index + 2)
            continue
        if value.startswith("/*", index):
            end = value.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated_block_comment")
            index = end + 2
            continue
        if char == "#" and line_start:
            index = _skip_to_line_end(value, index + 1)
            continue
        line_start = False
        if char in {"'", '"'}:
            token, index = _read_quoted_token(value, index)
            tokens.append(token)
            continue
        if char.isalnum() or char in {"_", "$", "."}:
            start = index
            while index < len(value) and (value[index].isalnum() or value[index] in {"_", "$", ".", "-"}):
                index += 1
            tokens.append(value[start:index])
            continue
        two_char = value[index : index + 2]
        if two_char in {"->", "==", "!=", ">=", "<=", "&&", "||", "?:", "++", "--", "+=", "-="}:
            tokens.append(two_char)
            index += 2
            continue
        tokens.append(char)
        index += 1
    return tokens


def _skip_to_line_end(value: str, index: int) -> int:
    while index < len(value) and value[index] not in "\r\n":
        index += 1
    return index


def _read_quoted_token(value: str, start: int) -> tuple[str, int]:
    quote = value[start]
    triple = value.startswith(quote * 3, start)
    delimiter = quote * (3 if triple else 1)
    index = start + len(delimiter)
    while index < len(value):
        if value.startswith(delimiter, index):
            end = index + len(delimiter)
            return value[start:end], end
        if value[index] == "\\" and not triple:
            index += 2
            continue
        index += 1
    raise ValueError("unterminated_string_literal")


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
    invalid_generated_files: list[dict[str, str]],
    stale_versions: list[dict[str, str]],
    unexpected_changed_files: list[str],
) -> str:
    if missing_current_files:
        return "restore_missing_generated_files_or_review_resolver_output"
    if invalid_generated_files:
        return "repair_invalid_generated_files_or_select_conservative_diff_mode"
    if required_marker_missing:
        return "restore_required_generated_markers_or_review_resolver_output"
    if stale_versions:
        return "rerun_resolver_and_verify_expected_native_versions"
    if unexpected_changed_files:
        return "review_or_revert_unexpected_generated_file_changes"
    return "none"
