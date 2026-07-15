from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

FRESH_HEARTBEAT_MAX_AGE_SECONDS = 5.0
STALE_HEARTBEAT_MAX_AGE_SECONDS = 15.0
ANR_SUSPECTED_HEARTBEAT_MAX_AGE_SECONDS = 30.0
STARTUP_MODAL_QUIESCENCE_SECONDS = 20.0
DEFAULT_LOG_TAIL_MAX_CHARS = 40000
EDITOR_LOG_GREP_MAX_CHARS = 500000
EDITOR_LOG_CONSOLE_CAVEAT = (
    "Unity Console grep can be a false negative after console clear-on-play or "
    "ring-buffer eviction; source=editor_log searches the path-backed Editor.log tail."
)
CONSOLE_FALSE_EMPTY_WARNING = "console_buffer_may_be_stale_use_source_editor_log"
CONSOLE_TAIL_CAVEAT = (
    "Unity Console tail reads the in-memory Console buffer, which may be stale after clear-on-play or "
    "ring-buffer eviction; use source=editor_log for compile-error validation."
)
EDITOR_LOG_TAIL_CAVEAT = (
    "Editor.log tail is path-backed but untyped; use error-anchored patterns with unity_console_grep "
    "source=editor_log for compile-error decisions."
)
API_UPDATER_RECOMMENDED_ACTION = "relaunch_noninteractive_accept_apiupdate"


def truncate_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)] + "..."


def read_editor_log_tail(log_path: Path, max_chars: int = DEFAULT_LOG_TAIL_MAX_CHARS) -> str:
    if not log_path.is_file():
        return ""

    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def _mtime_utc(value: float) -> str:
    if value <= 0.0:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _file_info(path: Path) -> dict[str, Any]:
    info = {
        "path": str(path),
        "exists": False,
        "size_bytes": 0,
        "mtime_utc": "",
        "mtime_unix": 0.0,
    }
    try:
        stat_result = path.stat()
    except OSError:
        return info
    info.update(
        {
            "exists": True,
            "size_bytes": int(stat_result.st_size or 0),
            "mtime_utc": _mtime_utc(float(stat_result.st_mtime or 0.0)),
            "mtime_unix": float(stat_result.st_mtime or 0.0),
        }
    )
    return info


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve() or left.samefile(right)
    except OSError:
        return left.expanduser().resolve() == right.expanduser().resolve()


def platform_editor_log_candidates() -> list[Path]:
    candidates: list[Path] = []
    home = Path.home()
    if sys.platform == "darwin":
        candidates.append(home / "Library" / "Logs" / "Unity" / "Editor.log")
    elif sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Unity" / "Editor" / "Editor.log")
    else:
        candidates.append(home / ".config" / "unity3d" / "Editor.log")
    return candidates


def _project_path_markers(project_root: Path) -> list[str]:
    markers = {
        str(project_root),
        project_root.as_posix(),
        str(project_root).replace("\\", "/"),
    }
    try:
        resolved = project_root.resolve()
        markers.add(str(resolved))
        markers.add(resolved.as_posix())
    except OSError:
        pass
    return [marker for marker in markers if marker]


def _log_mentions_project(log_text: str, project_root: Path) -> bool:
    normalized = log_text.replace("\\", "/")
    return any(marker.replace("\\", "/") in normalized for marker in _project_path_markers(project_root))


def build_editor_log_identity(
    project_root: Path,
    active_log_path: Path,
    *,
    bridge_state: dict[str, Any] | None = None,
    host_session_state: dict[str, Any] | None = None,
    max_probe_chars: int = DEFAULT_LOG_TAIL_MAX_CHARS,
) -> dict[str, Any]:
    bridge_state = dict(bridge_state or {})
    host_session_state = dict(host_session_state or {})
    active_log_path = active_log_path.expanduser().resolve()
    active_info = _file_info(active_log_path)

    reported_paths: list[Path] = []
    for key in ("editor_log_path", "console_log_path"):
        value = bridge_state.get(key)
        if isinstance(value, str) and value.strip():
            reported_paths.append(Path(value).expanduser())
    host_log = host_session_state.get("editor_log_path")
    if isinstance(host_log, str) and host_log.strip():
        reported_paths.append(Path(host_log).expanduser())

    candidate_paths: list[Path] = []
    for candidate in [*reported_paths, *platform_editor_log_candidates()]:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            resolved = candidate.expanduser()
        if _same_path(resolved, active_log_path):
            continue
        if any(_same_path(resolved, existing) for existing in candidate_paths):
            continue
        candidate_paths.append(resolved)

    active_mtime = float(active_info.get("mtime_unix") or 0.0)
    candidates: list[dict[str, Any]] = []
    newer_foreign_logs: list[dict[str, Any]] = []
    for candidate in candidate_paths:
        info = _file_info(candidate)
        exists = bool(info.get("exists"))
        text = read_editor_log_tail(candidate, max_chars=max_probe_chars) if exists else ""
        same_project_evidence = _log_mentions_project(text, project_root) if text else False
        candidate_mtime = float(info.get("mtime_unix") or 0.0)
        newer_than_active = exists and (active_mtime <= 0.0 or candidate_mtime > active_mtime + 1.0)
        candidate_info = {
            "path": str(candidate),
            "exists": exists,
            "mtime_utc": str(info.get("mtime_utc") or ""),
            "size_bytes": int(info.get("size_bytes") or 0),
            "newer_than_active_log": newer_than_active,
            "same_project_evidence": same_project_evidence,
            "evidence": "project_root_in_log_tail" if same_project_evidence else "",
        }
        candidates.append(candidate_info)
        if newer_than_active and same_project_evidence:
            newer_foreign_logs.append(candidate_info)

    return {
        "active_editor_log_path": str(active_log_path),
        "active_editor_log": {
            "path": str(active_log_path),
            "exists": bool(active_info.get("exists")),
            "mtime_utc": str(active_info.get("mtime_utc") or ""),
            "size_bytes": int(active_info.get("size_bytes") or 0),
            "source": "host_expected_editor_log",
        },
        "unity_reported_editor_log_path": str(bridge_state.get("editor_log_path") or ""),
        "host_session_editor_log_path": str(host_session_state.get("editor_log_path") or ""),
        "foreign_editor_log_candidates": candidates,
        "newer_foreign_editor_logs": newer_foreign_logs,
        "newer_foreign_editor_log_count": len(newer_foreign_logs),
        "newer_foreign_editor_log_detected": bool(newer_foreign_logs),
        "console_grep_caveat": EDITOR_LOG_CONSOLE_CAVEAT,
    }


def grep_editor_log_payload(
    project_root: Path,
    log_path: Path,
    *,
    pattern: str,
    regex: bool = False,
    ignore_case: bool = True,
    include_stack_traces: bool = False,
    limit: int = 20,
    max_chars: int = EDITOR_LOG_GREP_MAX_CHARS,
) -> dict[str, Any]:
    pattern = str(pattern or "").strip()
    if not pattern:
        raise ValueError("editor_log grep requires a non-empty pattern.")

    options = re.IGNORECASE if ignore_case else 0
    compiled = None
    if regex:
        try:
            compiled = re.compile(pattern, options)
        except re.error as exc:
            raise ValueError(f"editor_log regex pattern is invalid: {exc}") from exc

    text = read_editor_log_tail(log_path, max_chars=max_chars)
    matches: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if compiled is not None:
            matched = compiled.search(line) is not None
        elif ignore_case:
            matched = pattern.lower() in line.lower()
        else:
            matched = pattern in line
        if not matched:
            continue
        matches.append(
            {
                "type": "editor_log",
                "message": line,
                "timestamp": "",
                "stack_trace": "" if not include_stack_traces else "",
                "line": line_number,
            }
        )

    limit = max(1, int(limit or 20))
    truncated = len(matches) > limit
    visible_matches = matches[-limit:] if truncated else matches
    return {
        "backend_id": "xuunity.light_unity_mcp",
        "project_root": str(project_root),
        "source": "editor_log",
        "editor_log_path": str(log_path),
        "pattern": pattern,
        "regex": bool(regex),
        "ignore_case": bool(ignore_case),
        "include_stack_traces": bool(include_stack_traces),
        "match_count": len(matches),
        "items": visible_matches,
        "truncated": truncated,
        "searched_tail_chars": max_chars,
        "console_grep_caveat": EDITOR_LOG_CONSOLE_CAVEAT,
        "validation_evidence": "unity_editor_log",
    }


def tail_editor_log_payload(
    project_root: Path,
    log_path: Path,
    *,
    limit: int = 50,
    max_chars: int = EDITOR_LOG_GREP_MAX_CHARS,
) -> dict[str, Any]:
    limit = max(1, int(limit or 50))
    text = read_editor_log_tail(log_path, max_chars=max_chars)
    lines = [line.rstrip("\n") for line in text.splitlines() if line.strip()]
    truncated = len(lines) > limit
    visible_lines = lines[-limit:] if truncated else lines
    start_line = max(1, len(lines) - len(visible_lines) + 1)
    items = [
        {
            "type": "editor_log",
            "message": line,
            "timestamp": "",
            "stack_trace": "",
            "line": start_line + index,
        }
        for index, line in enumerate(visible_lines)
    ]
    return {
        "backend_id": "xuunity.light_unity_mcp",
        "project_root": str(project_root),
        "source": "editor_log",
        "editor_log_path": str(log_path),
        "items": items,
        "truncated": truncated,
        "tail_count": len(items),
        "searched_tail_chars": max_chars,
        "result_trust_class": "editor_log_path_backed_untyped",
        "console_tail_caveat": EDITOR_LOG_TAIL_CAVEAT,
        "recommended_next_action": "use_source_editor_log_grep_for_compile_errors",
        "validation_evidence": "unity_editor_log",
    }


def console_grep_false_empty_applies(payload: dict[str, Any], include_types: list[str] | None) -> bool:
    try:
        match_count = int(payload.get("match_count") or 0)
    except (TypeError, ValueError):
        match_count = 0
    if match_count != 0:
        return False
    normalized = {str(value or "").strip().lower() for value in include_types or [] if str(value or "").strip()}
    if not normalized:
        normalized = {"error", "warning", "log", "exception"}
    return bool(normalized.intersection({"error", "exception"}))


def annotate_console_grep_false_empty(payload: dict[str, Any], include_types: list[str] | None) -> dict[str, Any]:
    annotated = dict(payload or {})
    annotated.setdefault("source", "console")
    if not console_grep_false_empty_applies(annotated, include_types):
        return annotated
    warnings = list(annotated.get("warnings") or [])
    if CONSOLE_FALSE_EMPTY_WARNING not in warnings:
        warnings.append(CONSOLE_FALSE_EMPTY_WARNING)
    annotated["warnings"] = warnings
    annotated["console_grep_caveat"] = EDITOR_LOG_CONSOLE_CAVEAT
    annotated["result_trust_class"] = "console_buffer_may_be_stale"
    annotated["recommended_next_action"] = "retry_with_source_editor_log"
    return annotated


def annotate_console_tail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(payload or {})
    annotated.setdefault("source", "console")
    annotated["result_trust_class"] = "console_buffer_may_be_stale"
    annotated["console_tail_caveat"] = CONSOLE_TAIL_CAVEAT
    annotated["recommended_next_action"] = "use_source_editor_log_for_compile_errors"
    warnings = list(annotated.get("warnings") or [])
    if CONSOLE_FALSE_EMPTY_WARNING not in warnings:
        warnings.append(CONSOLE_FALSE_EMPTY_WARNING)
    annotated["warnings"] = warnings
    return annotated


def read_editor_log_scope(
    log_path: Path,
    *,
    session_start_offset_bytes: int | None = None,
    session_start_mtime: float | None = None,
    max_chars: int = DEFAULT_LOG_TAIL_MAX_CHARS,
) -> tuple[str, dict[str, Any]]:
    scope = {
        "source": "tail_fallback",
        "start_offset_bytes": 0,
        "fallback_used": True,
        "scoped_bytes_available": 0,
    }

    if not log_path.is_file():
        scope["missing"] = True
        return "", scope

    try:
        stat_result = log_path.stat()
    except OSError:
        scope["stat_failed"] = True
        return "", scope

    try:
        file_size = int(stat_result.st_size or 0)
        file_mtime = float(stat_result.st_mtime or 0.0)
    except (TypeError, ValueError):
        file_size = 0
        file_mtime = 0.0

    start_offset = max(0, int(session_start_offset_bytes or 0))
    start_mtime = float(session_start_mtime or 0.0)
    can_use_scope = (
        start_offset > 0
        and file_size >= start_offset
        and (start_mtime <= 0.0 or file_mtime >= max(0.0, start_mtime - 1.0))
    )

    if can_use_scope:
        try:
            with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(start_offset)
                scoped_text = handle.read()
        except OSError:
            scoped_text = ""
        if scoped_text:
            scope.update(
                {
                    "source": "host_opened_editor_session",
                    "start_offset_bytes": start_offset,
                    "fallback_used": False,
                    "scoped_bytes_available": max(0, file_size - start_offset),
                }
            )
            if len(scoped_text) > max_chars:
                scoped_text = scoped_text[-max_chars:]
            return scoped_text, scope
        scope["scoped_bytes_available"] = max(0, file_size - start_offset)
        scope["scoped_text_empty"] = True
        scope["source"] = "host_opened_editor_session"
        scope["start_offset_bytes"] = start_offset
        scope["fallback_used"] = False
        return "", scope

    tail_text = read_editor_log_tail(log_path, max_chars=max_chars)
    if not can_use_scope and start_offset > 0:
        scope["scope_unusable"] = True
        scope["requested_start_offset_bytes"] = start_offset
    return tail_text, scope


def _matching_log_lines(log_text: str, patterns: list[str], limit: int = 3) -> list[str]:
    matches: list[str] = []
    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern in line for pattern in patterns):
            matches.append(truncate_text(line, 220))
        if len(matches) >= limit:
            break
    return matches


def _editor_log_idle_seconds(log_path: Path) -> float | None:
    try:
        mtime = float(log_path.stat().st_mtime or 0.0)
    except OSError:
        return None
    if mtime <= 0.0:
        return None
    return max(0.0, time.time() - mtime)


def build_editor_log_diagnosis(
    log_path: Path,
    *,
    startup_policy: str,
    classify_editor_log: Callable[[str, str], tuple[str, str] | None],
    max_chars: int = DEFAULT_LOG_TAIL_MAX_CHARS,
    session_start_offset_bytes: int | None = None,
    session_start_mtime: float | None = None,
) -> dict[str, Any]:
    diagnosis = _build_editor_log_diagnosis_core(
        log_path,
        startup_policy=startup_policy,
        classify_editor_log=classify_editor_log,
        max_chars=max_chars,
        session_start_offset_bytes=session_start_offset_bytes,
        session_start_mtime=session_start_mtime,
    )
    if diagnosis:
        idle_seconds = _editor_log_idle_seconds(log_path)
        if idle_seconds is not None:
            diagnosis["log_idle_seconds"] = round(idle_seconds, 3)
    return diagnosis


def _build_editor_log_diagnosis_core(
    log_path: Path,
    *,
    startup_policy: str,
    classify_editor_log: Callable[[str, str], tuple[str, str] | None],
    max_chars: int = DEFAULT_LOG_TAIL_MAX_CHARS,
    session_start_offset_bytes: int | None = None,
    session_start_mtime: float | None = None,
) -> dict[str, Any]:
    log_text, log_scope = read_editor_log_scope(
        log_path,
        session_start_offset_bytes=session_start_offset_bytes,
        session_start_mtime=session_start_mtime,
        max_chars=max_chars,
    )
    if not log_text:
        return {}

    api_updater_lines = _matching_log_lines(
        log_text,
        [
            "API Update Required",
            "[ApiUpdater]",
            "[API Updater]",
            "UnityUpgradable",
            "-accept-apiupdate",
        ],
    )
    if api_updater_lines:
        return {
            "code": "api_updater_activity_observed",
            "severity": "warning",
            "summary": (
                "Editor.log contains API Updater markers; an interactive first-open may be blocked on the "
                "API Update Required dialog."
            ),
            "evidence_lines": api_updater_lines,
            "scope": log_scope,
        }

    version_upgrade_lines = _matching_log_lines(
        log_text,
        [
            "Upgrading project",
            "Project was created with",
            "This project was last opened with",
            "ProjectVersion.txt",
            "m_EditorVersion",
        ],
    )
    if version_upgrade_lines:
        return {
            "code": "unity_version_upgrade_activity_observed",
            "severity": "warning",
            "summary": (
                "Editor.log contains Unity version-upgrade markers; a first-open package/import stall may be "
                "blocked on an interactive upgrade dialog."
            ),
            "evidence_lines": version_upgrade_lines,
            "scope": log_scope,
        }

    classified = classify_editor_log(log_text, startup_policy)
    if classified is not None:
        code, summary = classified
        evidence_lines = _matching_log_lines(
            log_text,
            [
                "Project has invalid dependencies:",
                "An error occurred while resolving packages:",
                "Could not clone [",
                "error CS",
                "Safe Mode",
                "safe mode",
                "Enter Safe Mode",
            ],
        )
        return {
            "code": code,
            "severity": "error",
            "summary": summary,
            "evidence_lines": evidence_lines,
            "scope": log_scope,
        }

    runtime_exception_lines = _matching_log_lines(
        log_text,
        [
            "Exception:",
            "NullReferenceException",
            "MissingReferenceException",
            "StackOverflowException",
        ],
    )
    if runtime_exception_lines:
        return {
            "code": "runtime_exception_observed",
            "severity": "warning",
            "summary": "Editor.log contains recent runtime exception markers.",
            "evidence_lines": runtime_exception_lines,
            "scope": log_scope,
        }

    lifecycle_lines = _matching_log_lines(
        log_text,
        [
            "ReloadAssembly",
            "AssetDatabase: script compilation time:",
            "RefreshInfo:",
            "RefreshV2(",
            "Begin MonoManager ReloadAssembly",
            "Exiting Playmode",
            "Entering Playmode",
        ],
    )
    if lifecycle_lines:
        return {
            "code": "lifecycle_activity_observed",
            "severity": "info",
            "summary": "Editor.log shows recent lifecycle activity consistent with compile/import/playmode churn.",
            "evidence_lines": lifecycle_lines,
            "scope": log_scope,
        }

    timeout_lines = _matching_log_lines(
        log_text,
        [
            "Timeout",
            "timed out",
            "Transport connect failed",
        ],
    )
    if timeout_lines:
        return {
            "code": "timeout_markers_observed",
            "severity": "warning",
            "summary": "Editor.log contains recent timeout markers.",
            "evidence_lines": timeout_lines,
            "scope": log_scope,
        }

    last_non_empty_lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    evidence_lines = [truncate_text(line, 220) for line in last_non_empty_lines[-3:]]
    return {
        "code": "log_tail_present_no_known_blocker",
        "severity": "info",
        "summary": "Editor.log is present, but no known startup blocker marker was identified in the recent tail.",
        "evidence_lines": evidence_lines,
        "scope": log_scope,
    }


def _collect_progress_evidence(
    bridge_state: dict[str, Any],
    *,
    busy_reason: str,
    editor_log_diagnosis: dict[str, Any],
) -> list[str]:
    evidence: list[str] = []

    if str(bridge_state.get("active_operation") or ""):
        evidence.append("active_operation")
    if int(bridge_state.get("pending_request_count") or 0) > 0:
        evidence.append("pending_request_count")
    if str(bridge_state.get("last_processed_request_id") or ""):
        evidence.append("last_processed_request_id")
    if str(bridge_state.get("request_journal_head") or ""):
        evidence.append("request_journal_head")
    if bool(bridge_state.get("domain_reload_in_progress")):
        evidence.append("domain_reload_in_progress")
    if bool(bridge_state.get("package_operation_in_progress")):
        evidence.append("package_operation_in_progress")
    if bool(bridge_state.get("refresh_settle_pending")):
        evidence.append("refresh_settle_pending")
    if bool(bridge_state.get("compile_settle_pending")):
        evidence.append("compile_settle_pending")
    if bool(bridge_state.get("playmode_transition_pending")):
        evidence.append("playmode_transition_pending")
    if bool(bridge_state.get("is_compiling")):
        evidence.append("is_compiling")
    if bool(bridge_state.get("is_updating")):
        evidence.append("is_updating")
    if busy_reason not in {"", "idle", "bridge_state_missing"}:
        evidence.append(f"busy_reason:{busy_reason}")

    log_code = str(editor_log_diagnosis.get("code") or "")
    if log_code == "lifecycle_activity_observed":
        evidence.append("editor_log_lifecycle_activity")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def annotate_editor_log_diagnosis_freshness(
    editor_log_diagnosis: dict[str, Any],
    *,
    bridge_state_live: bool,
    live_editor_present: bool,
) -> dict[str, Any]:
    diagnosis = dict(editor_log_diagnosis or {})
    if not diagnosis or bridge_state_live:
        return diagnosis

    if live_editor_present:
        diagnosis["freshness_class"] = "unverified_live_editor_session"
        diagnosis["derived_from"] = "editor_log_without_live_bridge_confirmation"
        diagnosis["reflects_current_working_tree"] = False
        diagnosis["freshness_warning"] = (
            "Editor.log diagnosis was produced without a live bridge heartbeat; verify against current "
            "source and a fresh editor session before treating it as current compile truth."
        )
    else:
        diagnosis["freshness_class"] = "prior_session_or_unverified"
        diagnosis["derived_from"] = "prior_editor_session"
        diagnosis["reflects_current_working_tree"] = False
        diagnosis["freshness_warning"] = (
            "Editor.log diagnosis reflects a prior or unverified editor session because no live editor "
            "process/bridge heartbeat was proven."
        )
    return diagnosis


def classify_project_health(
    *,
    bridge_state: dict[str, Any],
    discovery: dict[str, Any],
    editor_log_diagnosis: dict[str, Any],
    heartbeat_age_seconds: Callable[[dict[str, Any]], float | None],
    derive_busy_reason: Callable[[dict[str, Any] | None], str],
) -> dict[str, Any]:
    bridge_state_live = bool(discovery.get("bridge_state_live"))
    host_session_live = bool(discovery.get("host_session_live"))
    bridge_enabled = bool(discovery.get("bridge_enabled"))
    detected_editor_count = int(discovery.get("detected_editor_count") or 0)
    bridge_pid_alive = bool(discovery.get("bridge_pid_alive"))
    host_session_pid_alive = bool(discovery.get("host_session_pid_alive"))
    live_editor_present = bool(
        bridge_state_live
        or host_session_live
        or detected_editor_count > 0
        or bridge_pid_alive
        or host_session_pid_alive
    )

    heartbeat_age = heartbeat_age_seconds(bridge_state) if bridge_state else None
    busy_reason = derive_busy_reason(bridge_state if bridge_state else None)
    progress_evidence = _collect_progress_evidence(
        bridge_state if isinstance(bridge_state, dict) else {},
        busy_reason=busy_reason,
        editor_log_diagnosis=editor_log_diagnosis,
    )
    has_progress_evidence = bool(progress_evidence)

    classification = "offline"
    reason = "no_live_editor_process"
    recommended_next_action = str(discovery.get("reconciliation_recommended_next_action") or "open_editor_or_ensure_ready")
    termination_policy = "observe_only"
    anr_classification = "none"

    if not bridge_enabled and not live_editor_present:
        classification = "bridge_disabled"
        reason = "bridge_disabled_in_project_config"
        recommended_next_action = "enable_bridge_and_retry"
    elif not live_editor_present:
        classification = "offline"
        if str(discovery.get("discovery_classification") or "") == "stale_state":
            reason = "stale_state_without_live_editor"
        else:
            reason = "no_live_editor_process"
    elif not bridge_state_live:
        classification = "stale"
        if host_session_live or detected_editor_count > 0:
            reason = "live_editor_without_live_bridge_state"
        else:
            reason = "bridge_state_not_live"
    else:
        if heartbeat_age is None:
            classification = "stale"
            reason = "live_bridge_state_without_heartbeat_timestamp"
        elif heartbeat_age < FRESH_HEARTBEAT_MAX_AGE_SECONDS:
            classification = "fresh"
            reason = "heartbeat_fresh"
            recommended_next_action = "none"
        elif heartbeat_age < STALE_HEARTBEAT_MAX_AGE_SECONDS:
            classification = "stale"
            reason = "heartbeat_stale_but_not_anr_threshold"
        elif heartbeat_age < ANR_SUSPECTED_HEARTBEAT_MAX_AGE_SECONDS:
            if has_progress_evidence:
                classification = "stale"
                reason = "lifecycle_churn_with_progress_evidence"
            else:
                classification = "anr_suspected"
                reason = "heartbeat_stale_without_progress_evidence"
                recommended_next_action = "inspect_editor_log_and_observe"
                anr_classification = "anr_suspected"
        else:
            if has_progress_evidence:
                classification = "stale"
                reason = "prolonged_lifecycle_churn_with_progress_evidence"
            else:
                classification = "anr"
                reason = "live_editor_without_progress_evidence"
                recommended_next_action = "inspect_editor_log_and_consider_graceful_restart"
                termination_policy = "graceful_terminate"
                anr_classification = "anr"

    startup_modal_block = False
    if editor_log_diagnosis and classification in {"stale", "anr_suspected", "anr"}:
        diagnosis_code = str(editor_log_diagnosis.get("code") or "")
        if diagnosis_code in {
            "api_updater_activity_observed",
            "unity_version_upgrade_activity_observed",
        } and busy_reason in {"package_operation", "refresh_settle", "asset_import", "compiling", "updating"}:
            reason = "possible_interactive_dialog_block"
            recommended_next_action = API_UPDATER_RECOMMENDED_ACTION
            termination_policy = "observe_only"
            if classification == "anr":
                classification = "stale"
                anr_classification = "none"
        if diagnosis_code in {
            "package_resolution_failed",
        }:
            reason = f"{reason}_with_log_blocker"
            recommended_next_action = "inspect_editor_log"
            termination_policy = "observe_only"
            if classification == "anr":
                classification = "stale"
                anr_classification = "none"
        if diagnosis_code in {
            "interactive_compile_block_detected",
            "interactive_compile_block_with_safe_mode_dialog",
            "safe_mode_manual_required",
        }:
            # Unity does not log a "Safe Mode" marker while the "Enter Safe Mode?" prompt is
            # displayed, so string matching alone misses a blocking prompt. A live editor with
            # compile errors, no live bridge state, and an idle Editor.log is the reliable
            # fingerprint of a modal blocking startup.
            log_idle_seconds = editor_log_diagnosis.get("log_idle_seconds")
            startup_modal_block = (
                not bridge_state_live
                and isinstance(log_idle_seconds, (int, float))
                and float(log_idle_seconds) >= STARTUP_MODAL_QUIESCENCE_SECONDS
            )
            if startup_modal_block:
                reason = "startup_modal_dialog_block"
                recommended_next_action = "dismiss_editor_startup_dialog_or_quit_editor_then_retry"
            else:
                reason = "possible_safe_mode_dialog_block"
                recommended_next_action = "run_batch_compile_gate_and_fix_errors"
            termination_policy = "observe_only"
            if classification == "anr":
                classification = "stale"
                anr_classification = "none"

    annotated_editor_log_diagnosis = annotate_editor_log_diagnosis_freshness(
        editor_log_diagnosis,
        bridge_state_live=bridge_state_live,
        live_editor_present=live_editor_present,
    )

    if startup_modal_block:
        idle_seconds = editor_log_diagnosis.get("log_idle_seconds")
        annotated_editor_log_diagnosis["startup_modal_block_suspected"] = True
        annotated_editor_log_diagnosis["summary"] = (
            "Editor process is alive but Editor.log has been idle"
            + (f" for ~{round(float(idle_seconds))}s" if isinstance(idle_seconds, (int, float)) else "")
            + " after compile errors with no live bridge heartbeat — most likely blocked on the "
            "'Enter Safe Mode?' startup dialog. This wrapper does not click editor dialogs; dismiss it "
            "in the editor or quit the editor, then retry."
        )

    return {
        "host_health_classification": classification,
        "host_health_reason": reason,
        "host_health_recommended_next_action": recommended_next_action,
        "host_health_termination_policy": termination_policy,
        "host_health_heartbeat_age_seconds": None if heartbeat_age is None else round(float(heartbeat_age), 3),
        "host_health_busy_reason": busy_reason,
        "host_health_progress_evidence": progress_evidence,
        "anr_classification": anr_classification,
        "editor_log_diagnosis": annotated_editor_log_diagnosis,
        "editor_log_scope": dict(annotated_editor_log_diagnosis.get("scope") or {}),
    }
