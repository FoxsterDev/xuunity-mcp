from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from server_bridge_paths import default_editor_log_path
from server_core import parse_utc_timestamp

FRESH_HEARTBEAT_MAX_AGE_SECONDS = 5.0
STALE_HEARTBEAT_MAX_AGE_SECONDS = 15.0
ANR_SUSPECTED_HEARTBEAT_MAX_AGE_SECONDS = 30.0
STARTUP_MODAL_QUIESCENCE_SECONDS = 20.0
# Below this a quiet log is just an idle editor, not the wrong file.
STALE_LOG_LANE_MIN_AGE_SECONDS = 600.0
DEFAULT_LOG_TAIL_MAX_CHARS = 40000
EDITOR_LOG_GREP_MAX_CHARS = 500000
EDITOR_LOG_GREP_MIN_CHARS = 4096
EDITOR_LOG_GREP_ABS_MAX_CHARS = 10000000
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
EDITOR_LOG_STALE_MATCH_CAVEAT = (
    "Editor.log accumulates across editor sessions and play sessions, so an unanchored match may predate the "
    "current run; pass since=playmode_start or since=bridge_generation to bound the search to this session."
)
CONSOLE_TAIL_DEFAULT_MAX_PAYLOAD_BYTES = 16384
CONSOLE_ITEM_BYTE_OVERHEAD = 64
CONSOLE_TAIL_BYTE_TRUNCATION_MARKER = "\n[truncated_by_byte_budget]"
CONSOLE_TAIL_TRUNCATION_RECOVERY_TOOL = "unity_console_grep"
CONSOLE_TAIL_TRUNCATION_RECOVERY_HINT = (
    "Use unity_console_grep with a pattern (same source) to fetch the specific entries compactly."
)
CONSOLE_TAIL_FULL_PAYLOAD_RECOVERY_HINT = (
    "Re-run unity_console_tail with maxPayloadBytes=-1 for the unbounded raw tail; raise limit for more items."
)
EDITOR_LOG_PARTIAL_SCOPE_RECOVERY_ACTION = (
    "retry_with_since_request_id_near_the_expected_event_or_search_editor_log_from_since_anchor_start_offset_bytes"
)
SINCE_ANCHORS = ("playmode_start", "bridge_generation", "request_id")
SINCE_ANCHOR_STATE_KEYS = {
    "playmode_start": "editor_log_offset_at_playmode_start",
    "bridge_generation": "editor_log_offset_at_bridge_generation_start",
}
SINCE_ANCHOR_PID_STATE_KEYS = {
    "playmode_start": "editor_log_playmode_anchor_editor_pid",
    "bridge_generation": "editor_log_bridge_generation_anchor_editor_pid",
}
API_UPDATER_RECOMMENDED_ACTION = "relaunch_noninteractive_accept_apiupdate"
# Mirrors XUUnityLightMcpConsoleNoise.BuildPipelineProgressPattern in the editor package. Build-pipeline
# progress lines match whatever feature name the compile job carries, so a feature-keyword grep drowns in
# them; keep the two patterns in step.
BUILD_PIPELINE_PROGRESS_PATTERN = (
    r"(^\s*(CopyFiles|CopyDirs|CopyFile|MoveFiles|WriteFile|Compile|Link|Strip)\s)|(^\s*\[\s*\d+\s*/\s*\d+\s)"
)
BUILD_PIPELINE_PROGRESS = re.compile(BUILD_PIPELINE_PROGRESS_PATTERN)


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
    """Whether two paths name the same file, using the platform's own equality rules.

    `samefile` settles it when both exist. When one does not — a rotated or deleted log, which is exactly when the
    anchor guards compare paths — the fallback string comparison was case- and separator-sensitive, so on Windows
    `C:\\Users\\user\\Editor.log` and `c:/users/user/editor.log` read as different files and a valid anchor was refused as
    `anchor_log_mismatch`. `os.path.normcase` applies the platform rule: lowercase plus separator folding on
    Windows, identity on POSIX, so macOS and Linux behaviour is unchanged.
    """

    try:
        if left.samefile(right):
            return True
    except OSError:
        pass
    try:
        left_resolved = left.expanduser().resolve()
        right_resolved = right.expanduser().resolve()
    except OSError:
        left_resolved, right_resolved = left.expanduser(), right.expanduser()
    return os.path.normcase(str(left_resolved)) == os.path.normcase(str(right_resolved))


def rotated_editor_log_sibling(log_path: Path) -> Path:
    """The name Unity rotates a platform Editor.log to when another editor starts.

    The editor that owned the log keeps writing the renamed file through its open handle, while
    `Application.consoleLogPath` still returns the static path, so the sibling is where a first-started editor's
    output actually lands.
    """

    return log_path.with_name(f"{log_path.stem}-prev{log_path.suffix}")


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
    # A rotated sibling is a real candidate: on a multi-editor host it is the log the first editor writes.
    return candidates + [rotated_editor_log_sibling(candidate) for candidate in candidates]


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


def _count_lines_before_offset(log_path: Path, offset: int) -> int:
    """1-based line number of the first line at or after offset, or 0 when it cannot be derived."""

    if offset <= 0:
        return 1
    newlines = 0
    remaining = offset
    try:
        with log_path.open("rb") as handle:
            while remaining > 0:
                chunk = handle.read(min(1 << 20, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                newlines += chunk.count(b"\n")
    except OSError:
        return 0
    return newlines + 1


def _request_started_log_anchor(journal_events: list[dict[str, Any]] | None) -> tuple[int, str, int]:
    """The Editor.log length and path the editor recorded when it began handling the request.

    The editor writes both into the `request_started` journal event, so the anchor costs one stat per request
    the operator actually issued — never a stat inside the 0.5 s request pump. The path travels with the offset
    because the journal outlives bridge_state.json: `recover-editor-session` unlinks the state file and leaves
    the journal, so an offset that carried no identity of its own could be applied to a different log.
    """

    for event in journal_events or []:
        if str(event.get("event_type") or "") != "request_started":
            continue
        offset = _int_or_zero(event.get("editor_log_offset_bytes"))
        if offset > 0:
            return offset, str(event.get("editor_log_path") or ""), _int_or_zero(event.get("editor_pid"))
    return 0, "", 0


def _request_started_stamp_utc(journal_events: list[dict[str, Any]] | None) -> str:
    for event in journal_events or []:
        if str(event.get("event_type") or "") != "request_started":
            continue
        if _int_or_zero(event.get("editor_log_offset_bytes")) > 0:
            return str(event.get("event_at_utc") or "")
    return ""


def _offset_is_line_boundary(log_path: Path, offset: int) -> bool:
    """True when the recorded offset sits at the start of a line.

    The editor records FileInfo.Length at a moment in time, so it can land inside a partially written line.
    """

    if offset <= 0:
        return True
    try:
        with log_path.open("rb") as handle:
            handle.seek(offset - 1)
            return handle.read(1) == b"\n"
    except OSError:
        return True


def _parse_stamp_utc(value: Any) -> float:
    """Epoch seconds for a `...Z` stamp, independent of the host's timezone and DST rules.

    `time.mktime` reads a struct as *local* time, so converting a UTC stamp with it and subtracting
    `time.timezone` is only correct where standard time is in force year-round. Measured on the same stamp: exact
    on a no-DST host, and off by 3600 s on Europe/Berlin, America/New_York, and Australia/Sydney — where the error
    lands in the opposite half of the year. That hour propagates into the log-lane staleness threshold and the
    rotation guard, so the shared UTC parser is the only correct conversion here.
    """

    return parse_utc_timestamp(value) or 0.0


def detect_rotated_editor_log(log_path: Path, stamped_utc: Any) -> Path | None:
    """The sibling that actually holds this editor's output, when the searched path was rotated out.

    Staleness alone is not rotation. A live editor can leave its log untouched for minutes and still be the
    writer: measured on a real project, a `request_started` stamped at `22:28:53Z` against a log last written at
    `22:21:38Z` — quiet, not replaced. Treating that as rotation refused every `since=` anchor on an idle editor.

    Rotation is only claimed when a replacement candidate exists and looks like the newer file: Unity renames
    `Editor.log` to `Editor-prev.log` when a second editor starts, and the first editor keeps writing the renamed
    file, so the sibling is newer than both the searched log and the stamp.
    """

    predates, _, _ = _log_predates_its_own_stamp(log_path, stamped_utc)
    if not predates:
        return None

    sibling = rotated_editor_log_sibling(log_path)
    if not sibling.is_file():
        return None

    try:
        sibling_mtime = float(sibling.stat().st_mtime or 0.0)
        searched_mtime = float(log_path.stat().st_mtime or 0.0)
    except OSError:
        return None

    if sibling_mtime <= searched_mtime:
        return None

    sibling_predates, _, _ = _log_predates_its_own_stamp(sibling, stamped_utc)
    return None if sibling_predates else sibling


def _log_predates_its_own_stamp(log_path: Path, stamped_utc: Any) -> tuple[bool, str, str]:
    """True when the searched log was last written before the editor stamped an offset into it.

    An editor cannot stamp an offset against a log it is writing and leave that log older than the stamp. When it
    looks that way the path has been reused by a different file: Unity rotates `Editor.log` to `Editor-prev.log`
    when a second editor starts, and the first editor keeps writing the renamed file while
    `Application.consoleLogPath` still returns the static path. Verified on a two-editor host where the stamping
    editor held `Editor-prev.log` and the path named another editor's log.
    """

    stamp_epoch = _parse_stamp_utc(stamped_utc)
    if stamp_epoch <= 0.0:
        return False, "", ""
    try:
        mtime = float(log_path.stat().st_mtime or 0.0)
    except OSError:
        return False, "", ""
    if mtime <= 0.0 or mtime >= stamp_epoch - 2.0:
        return False, "", ""
    return True, _mtime_utc(mtime), str(stamped_utc or "")


def resolve_editor_log_since_anchor(
    log_path: Path,
    *,
    since: str = "",
    bridge_state: dict[str, Any] | None = None,
    host_session_state: dict[str, Any] | None = None,
    journal_events: list[dict[str, Any]] | None = None,
    since_request_id: str = "",
    bridge_state_is_live: bool = True,
    explicit_path_requested: bool = False,
) -> dict[str, Any]:
    """Resolve a `since` anchor to a byte offset in the Editor.log.

    Editor.log accumulates across editor sessions and play sessions, so an unanchored grep can match a line
    written by a previous run. The offsets come from the editor package: it records the log length at play-mode
    entry and at bridge-generation start into bridge_state.json.

    `bridge_state_is_live` must be false when the state file exists but its editor is gone. Those offsets were
    measured against a log Unity has since truncated, which is the failure that removed the `session_start`
    anchor: stale at first, then silently wrong once the new log grows past the recorded byte.
    """

    requested = str(since or "").strip().lower()
    anchor: dict[str, Any] = {
        "requested": requested,
        "resolved": "unanchored",
        "start_offset_bytes": 0,
        "anchored": False,
    }
    if not requested:
        return anchor

    if requested not in SINCE_ANCHORS:
        anchor["resolved"] = "unsupported_anchor"
        anchor["supported_anchors"] = list(SINCE_ANCHORS)
        return anchor

    if not bridge_state_is_live:
        anchor["resolved"] = "anchor_stale_dead_session"
        anchor["anchor_stale_reason"] = (
            "bridge_state.json belongs to an editor that is no longer running, so every offset in it was "
            "measured against that session's Editor.log; Unity truncates the log on start, so applying one to "
            "the current log would scope the search to an arbitrary byte while still reporting a session anchor"
        )
        anchor["recommended_next_action"] = (
            "treat this result as spanning previous sessions; clear the stale state with recover-editor-session "
            "and bring the lane up with ensure-ready --open-editor, then re-anchor against the live editor"
        )
        return anchor

    journal_log_path = ""
    anchor_editor_pid = 0
    if requested == "request_id":
        if not str(since_request_id or "").strip():
            anchor["resolved"] = "anchor_argument_missing"
            anchor["anchor_argument_missing_reason"] = "since=request_id also needs sinceRequestId"
            return anchor
        anchor["since_request_id"] = str(since_request_id).strip()
        offset, journal_log_path, anchor_editor_pid = _request_started_log_anchor(journal_events)
        source = "request_journal.request_started.editor_log_offset_bytes"
    else:
        state_key = SINCE_ANCHOR_STATE_KEYS[requested]
        offset = _int_or_zero((bridge_state or {}).get(state_key))
        anchor_editor_pid = _int_or_zero(
            (bridge_state or {}).get(SINCE_ANCHOR_PID_STATE_KEYS[requested])
        )
        source = f"bridge_state.{state_key}"

    current_editor_pid = _int_or_zero((bridge_state or {}).get("editor_pid"))
    if offset > 0 and anchor_editor_pid > 0 and current_editor_pid > 0 and anchor_editor_pid != current_editor_pid:
        anchor.update(
            {
                "resolved": "anchor_process_mismatch",
                "anchor_source": source,
                "anchor_editor_pid": anchor_editor_pid,
                "current_editor_pid": current_editor_pid,
                "anchor_process_mismatch_reason": (
                    "the anchor was recorded by a different Unity editor process; applying its byte offset to "
                    "the current process log could turn an incomplete search into a false negative"
                ),
                "recommended_next_action": (
                    "capture a new request_id, playmode_start, or bridge_generation anchor from the current "
                    "editor process, then retry the grep"
                ),
            }
        )
        return anchor

    stamped_log = journal_log_path or str((bridge_state or {}).get("editor_log_path") or "")
    if requested == "request_id" and offset > 0 and not stamped_log:
        anchor["resolved"] = "anchor_identity_unverified"
        anchor["anchor_source"] = source
        anchor["anchor_identity_unverified_reason"] = (
            "the journal entry carries an offset but no editor_log_path, and no live bridge_state names the log "
            "either, so there is nothing to prove the offset was measured against the log being searched"
        )
        anchor["recommended_next_action"] = (
            "use since=playmode_start or since=bridge_generation against the live editor, or rerun the operation "
            "so its journal entry is written by a package version that stamps the log path"
        )
        return anchor

    stamped_matches = bool(stamped_log) and (
        _same_path(Path(stamped_log).expanduser(), log_path.expanduser())
        # An operator following the rotation remediation searches the sibling of the stamped path. That is the
        # same editor's log, so calling it a mismatch would deadlock the two guards against each other.
        or _same_path(rotated_editor_log_sibling(Path(stamped_log).expanduser()), log_path.expanduser())
    )
    if stamped_log and not stamped_matches:
        anchor["resolved"] = "anchor_log_mismatch"
        anchor["anchor_source"] = source
        anchor["stamped_editor_log_path"] = stamped_log
        anchor["searched_editor_log_path"] = str(log_path)
        anchor["anchor_log_mismatch_reason"] = (
            "the editor measured this offset against its own Editor.log, which is not the log being searched; "
            "an editor opened outside the host writes to the platform Editor.log while the host defaults to the "
            "project-local one, and applying an offset across the two would scope the search to an arbitrary byte"
        )
        anchor["recommended_next_action"] = (
            "pass editorLogPath=<the path in bridge_state.editor_log_path>, or reopen the editor through "
            "ensure-ready --open-editor so both sides agree on one log"
        )
        return anchor

    stamped_utc = ""
    if requested == "playmode_start":
        stamped_utc = str((bridge_state or {}).get("editor_log_playmode_started_utc") or "")
    elif requested == "request_id":
        stamped_utc = _request_started_stamp_utc(journal_events)

    # Rotation is only claimed when a replacement candidate actually exists; a quiet log is not a replaced one.
    rotated_sibling = detect_rotated_editor_log(log_path, stamped_utc)
    if rotated_sibling is not None:
        anchor["forward_resolved_from_editor_log_path"] = str(log_path)
        anchor["forward_resolved_editor_log_path"] = str(rotated_sibling)
        anchor["forward_resolved_reason"] = (
            "the stamped path holds a file older than the stamp while its rotated sibling holds a newer one, so "
            "the stamping editor is writing the sibling; Unity renames Editor.log to Editor-prev.log when a "
            "second editor starts and the first editor keeps writing the renamed file"
        )
        try:
            sibling_size = int(rotated_sibling.stat().st_size or 0)
        except OSError:
            sibling_size = 0
        if sibling_size < offset:
            anchor["resolved"] = "anchor_log_rotated"
            anchor["anchor_source"] = source
            anchor["searched_editor_log_mtime_utc"] = _file_mtime_utc(log_path)
            anchor["anchor_log_rotated_reason"] = (
                "the path was rotated and the sibling this editor writes is smaller than the recorded offset, so "
                "no file on disk can serve this anchor"
            )
            anchor["recommended_next_action"] = (
                "use since=playmode_start or since=bridge_generation against the current editor, or reopen the "
                "project through ensure-ready --open-editor so the host owns the log with -logFile"
            )
            return anchor
        log_path = rotated_sibling

    anchor["anchor_source"] = source
    if offset <= 0:
        anchor["resolved"] = "anchor_unavailable"
        if requested == "request_id":
            anchor["anchor_unavailable_reason"] = (
                "no request_started journal event for this request id carries an Editor.log offset; the request "
                "may predate this package version, or its journal entry may have been pruned"
            )
            anchor["recommended_next_action"] = (
                "treat this result as spanning previous sessions; use since=playmode_start or "
                "since=bridge_generation instead, or rerun the operation and anchor on the new request id"
            )
        else:
            anchor["anchor_unavailable_reason"] = (
                "the editor has not recorded this anchor yet; it is written when Play Mode is entered and when "
                "the bridge generation starts, and it needs an editor running the current package version"
            )
            anchor["recommended_next_action"] = (
                "treat this result as spanning previous sessions; enter Play Mode through unity_playmode_set, or "
                "restart the editor so the bridge records an anchor, then retry"
            )
        return anchor

    try:
        file_size = int(log_path.stat().st_size or 0)
    except OSError:
        file_size = 0

    if file_size < offset:
        anchor["resolved"] = "anchor_stale"
        anchor["anchor_stale_reason"] = "the Editor.log is smaller than the recorded offset, so it was rotated"
        anchor["recorded_offset_bytes"] = offset
        return anchor

    anchor.update(
        {
            "resolved": requested,
            "anchored": True,
            "start_offset_bytes": offset,
            "searched_from_line": _count_lines_before_offset(log_path, offset),
            "scoped_bytes_available": max(0, file_size - offset),
            "starts_mid_line": not _offset_is_line_boundary(log_path, offset),
        }
    )
    if requested == "playmode_start":
        anchor["playmode_started_utc"] = str((bridge_state or {}).get("editor_log_playmode_started_utc") or "")
    if requested == "bridge_generation":
        anchor["bridge_generation"] = _int_or_zero((bridge_state or {}).get("editor_log_offset_bridge_generation"))
    return anchor


def effective_editor_log_path(log_path: Path, anchor: dict[str, Any]) -> Path:
    """The log actually read, which is the rotated sibling when the anchor forward-resolved onto it."""

    forwarded = str(anchor.get("forward_resolved_editor_log_path") or "")
    return Path(forwarded) if forwarded else log_path


def _read_editor_log_since_anchor(
    log_path: Path,
    anchor: dict[str, Any],
    max_chars: int,
    *,
    prefer_anchor_adjacent_window: bool = False,
) -> tuple[str, int]:
    """Return (text, first_line_number) for the anchored scope, falling back to the plain tail."""

    log_path = effective_editor_log_path(log_path, anchor)
    if not anchor.get("anchored"):
        return read_editor_log_tail(log_path, max_chars=max_chars), 1

    text, scope = read_editor_log_scope(
        log_path,
        session_start_offset_bytes=int(anchor.get("start_offset_bytes") or 0),
        max_chars=max_chars,
        prefer_anchor_adjacent_window=prefer_anchor_adjacent_window,
    )
    if scope.get("fallback_used"):
        anchor["resolved"] = "anchor_unusable"
        anchor["anchored"] = False
        return text, 1

    truncated = bool(scope.get("truncated_to_max_chars"))
    anchor["scope_truncated"] = truncated
    first_line = max(1, int(anchor.get("searched_from_line") or 1))
    window_direction = str(scope.get("search_window_direction") or "full_anchored_scope")
    anchor["search_window_direction"] = window_direction
    anchor["searched_window_chars"] = int(scope.get("searched_window_chars") or len(text))
    anchor["unsearched_scope_chars"] = int(scope.get("unsearched_scope_chars") or 0)

    # A window boundary inside a line lets a pattern match text the real line does not contain. A leading cut
    # that splits "xxNOMARKER" leaves "MARKER"; a trailing cut after "ERROR" in "ERRORDETAIL" fabricates an
    # `ERROR$` regex match. The recorded offset can split the leading line, and max_chars can split either the
    # leading edge of a tail window or the trailing edge of an anchor-adjacent head window.
    starts_mid_line = bool(anchor.get("starts_mid_line"))
    if truncated and window_direction == "scope_tail":
        starts_mid_line = bool(scope.get("truncated_window_starts_mid_line"))
    if starts_mid_line:
        newline_at = text.find("\n")
        text = "" if newline_at < 0 else text[newline_at + 1 :]
        anchor["partial_leading_line_dropped"] = True
        if not truncated or window_direction == "anchor_adjacent_head":
            first_line += 1

    if truncated and window_direction == "anchor_adjacent_head" and scope.get("truncated_window_ends_mid_line"):
        newline_at = text.rfind("\n")
        text = "" if newline_at < 0 else text[: newline_at + 1]
        anchor["partial_trailing_line_dropped"] = True

    if truncated and window_direction == "scope_tail":
        # The window no longer starts at the anchor, so absolute numbering is unrecoverable without a second
        # full read. Numbering goes relative to the window; keep the anchor's own line under a separate key so
        # the two are not confused.
        anchor["anchor_line"] = first_line
        anchor["searched_from_line"] = 1
        return text, 1

    anchor["searched_from_line"] = first_line
    return text, first_line


STALE_LOG_LANE_CAVEAT = (
    "This Editor.log has not been written since well before the live editor's last heartbeat, so it is not the "
    "log this editor is writing; matches describe an earlier session and absence proves nothing."
)


def build_editor_log_lane(
    project_root: Path,
    log_path: Path,
    *,
    bridge_state: dict[str, Any] | None = None,
    anchor: dict[str, Any] | None = None,
    explicit_path_requested: bool = False,
    editor_is_live: bool | None = None,
) -> dict[str, Any]:
    """Classify *which log lane* a `source=editor_log` read is on, not just which path it opened.

    The host default (`Library/XUUnityLightMcp/logs/unity_editor.log`) is correct only for editors the host
    launched with `-logFile`. An editor opened from the Hub writes the platform log instead, so the default can
    point at a file that has not been touched for hours while a healthy editor logs elsewhere. Reporting a path
    without saying whether the editor writes it is what let that read look authoritative.
    """

    state = bridge_state or {}
    searched = effective_editor_log_path(log_path, anchor or {})
    reported = str(state.get("editor_log_path") or "")
    host_default = default_editor_log_path(project_root)

    lane: dict[str, Any] = {
        "searched_editor_log_path": str(searched),
        "editor_reported_editor_log_path": reported,
        "host_default_editor_log_path": str(host_default),
        "explicit_path_requested": bool(explicit_path_requested),
        "editor_pid": _int_or_zero(state.get("editor_pid")),
    }

    log_age = _file_age_seconds(searched)
    lane["editor_log_mtime_utc"] = _file_mtime_utc(searched)
    lane["editor_log_age_seconds"] = log_age
    heartbeat_age = _heartbeat_age_seconds(state.get("heartbeat_utc"))
    lane["heartbeat_age_seconds"] = heartbeat_age
    if editor_is_live is None:
        # Fall back to heartbeat freshness so the lane still classifies when the caller has no liveness verdict.
        editor_is_live = heartbeat_age is not None and heartbeat_age <= ANR_SUSPECTED_HEARTBEAT_MAX_AGE_SECONDS
    lane["editor_is_live"] = bool(editor_is_live)

    if anchor and anchor.get("forward_resolved_editor_log_path"):
        lane["lane"] = "rotated_sibling"
        lane["lane_reason"] = str(anchor.get("forward_resolved_reason") or "")
        return lane

    # A live editor whose log has been idle for far longer than its own heartbeat is not writing this file.
    if (
        lane["editor_is_live"]
        and log_age is not None
        and heartbeat_age is not None
        and log_age > max(STALE_LOG_LANE_MIN_AGE_SECONDS, heartbeat_age * 4 + 60)
    ):
        lane["lane"] = "stale_not_written_by_live_editor"
        lane["lane_reason"] = (
            f"the editor heartbeat is {heartbeat_age:.0f}s old but this log has not been written for "
            f"{log_age:.0f}s, so a different file is receiving this editor's output"
        )
        lane["recommended_next_action"] = (
            "pass editorLogPath=<the path in bridge_state.editor_log_path>, or reopen the project through "
            "ensure-ready --open-editor so the host owns the log with -logFile"
        )
        return lane

    if reported and _same_path(Path(reported).expanduser(), searched.expanduser()):
        lane["lane"] = (
            "host_owned_logfile"
            if _same_path(host_default, searched)
            else "editor_reported_platform_log"
        )
        return lane

    if _same_path(host_default, searched):
        lane["lane"] = "host_owned_logfile" if not reported else "host_default_not_editor_reported"
        if reported:
            lane["lane_reason"] = (
                "the editor reports a different log than the host default this read opened"
            )
            lane["recommended_next_action"] = (
                "pass editorLogPath=<the path in bridge_state.editor_log_path>"
            )
        return lane

    lane["lane"] = "unverified_editor_log"
    lane["lane_reason"] = "no live bridge names a log, so nothing confirms this file receives editor output"
    return lane


def _file_mtime_utc(path: Path) -> str:
    try:
        return _mtime_utc(float(path.stat().st_mtime or 0.0))
    except OSError:
        return ""


def _file_age_seconds(path: Path) -> float | None:
    try:
        mtime = float(path.stat().st_mtime or 0.0)
    except OSError:
        return None
    if mtime <= 0.0:
        return None
    return max(0.0, time.time() - mtime)


def _heartbeat_age_seconds(heartbeat_utc: Any) -> float | None:
    stamp = _parse_stamp_utc(heartbeat_utc)
    if stamp <= 0.0:
        return None
    return max(0.0, time.time() - stamp)


def grep_editor_log_payload(
    project_root: Path,
    log_path: Path,
    *,
    pattern: str,
    exclude_pattern: str = "",
    regex: bool = False,
    ignore_case: bool = True,
    include_stack_traces: bool = False,
    include_build_pipeline_noise: bool = False,
    limit: int = 20,
    max_chars: int = EDITOR_LOG_GREP_MAX_CHARS,
    since: str = "",
    bridge_state: dict[str, Any] | None = None,
    host_session_state: dict[str, Any] | None = None,
    journal_events: list[dict[str, Any]] | None = None,
    since_request_id: str = "",
    bridge_state_is_live: bool = True,
    explicit_path_requested: bool = False,
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

    exclude_pattern = str(exclude_pattern or "").strip()
    compiled_exclude = None
    if regex and exclude_pattern:
        try:
            compiled_exclude = re.compile(exclude_pattern, options)
        except re.error as exc:
            raise ValueError(f"editor_log regex excludePattern is invalid: {exc}") from exc

    def line_matches(line: str, needle: str, compiled_needle: "re.Pattern[str] | None") -> bool:
        if compiled_needle is not None:
            return compiled_needle.search(line) is not None
        if ignore_case:
            return needle.lower() in line.lower()
        return needle in line

    anchor = resolve_editor_log_since_anchor(
        log_path,
        since=since,
        bridge_state=bridge_state,
        host_session_state=host_session_state,
        journal_events=journal_events,
        since_request_id=since_request_id,
        bridge_state_is_live=bridge_state_is_live,
    )
    lane = build_editor_log_lane(
        project_root,
        log_path,
        bridge_state=bridge_state,
        anchor=anchor,
        explicit_path_requested=explicit_path_requested,
        editor_is_live=bridge_state_is_live,
    )
    text, first_line_number = _read_editor_log_since_anchor(
        log_path,
        anchor,
        max_chars,
        prefer_anchor_adjacent_window=True,
    )
    matches: list[dict[str, Any]] = []
    excluded_count = 0
    build_pipeline_suppressed_count = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=first_line_number):
        line = raw_line.rstrip("\n")
        if not line_matches(line, pattern, compiled):
            continue
        if exclude_pattern and line_matches(line, exclude_pattern, compiled_exclude):
            excluded_count += 1
            continue
        if not include_build_pipeline_noise and BUILD_PIPELINE_PROGRESS.search(line) is not None:
            build_pipeline_suppressed_count += 1
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
    scope_truncated = bool(anchor.get("scope_truncated"))
    lane_is_stale = lane.get("lane") == "stale_not_written_by_live_editor"
    if matches:
        search_verdict = "matched"
        search_verdict_reason = "pattern_found_in_searched_window"
    elif anchor.get("anchored") and not scope_truncated and not lane_is_stale:
        search_verdict = "not_matched"
        search_verdict_reason = "complete_anchored_scope_searched"
    else:
        search_verdict = "inconclusive"
        if scope_truncated:
            search_verdict_reason = "anchored_scope_truncated_before_full_search"
        elif lane_is_stale:
            search_verdict_reason = "searched_log_not_written_by_live_editor"
        elif since and not anchor.get("anchored"):
            search_verdict_reason = "requested_anchor_not_available"
        else:
            search_verdict_reason = "unanchored_editor_log_window_does_not_prove_absence"

    payload = {
        "backend_id": "xuunity.light_unity_mcp",
        "project_root": str(project_root),
        "source": "editor_log",
        "editor_log_path": str(effective_editor_log_path(log_path, anchor)),
        "pattern": pattern,
        "exclude_pattern": exclude_pattern,
        "regex": bool(regex),
        "ignore_case": bool(ignore_case),
        "include_stack_traces": bool(include_stack_traces),
        "match_count": len(matches),
        "excluded_count": excluded_count,
        "build_pipeline_suppressed_count": build_pipeline_suppressed_count,
        "items": visible_matches,
        "truncated": truncated,
        "searched_tail_chars": max_chars,
        "searched_window_chars": int(anchor.get("searched_window_chars") or len(text)),
        "search_window_direction": str(anchor.get("search_window_direction") or "scope_tail"),
        "scope_truncated": scope_truncated,
        "search_verdict": search_verdict,
        "search_verdict_reason": search_verdict_reason,
        "since_anchor": anchor,
        "searched_from_line": first_line_number,
        "line_numbering_basis": (
            "anchored_scope_relative"
            if scope_truncated and anchor.get("search_window_direction") == "scope_tail"
            else "editor_log_absolute"
        ),
        "result_trust_class": (
            "session_scoped_editor_log_partial_scope"
            if anchor.get("anchored") and scope_truncated
            else "session_scoped_editor_log"
            if anchor.get("anchored")
            else "editor_log_spans_multiple_sessions"
        ),
        "log_lane": lane,
        "log_lane_caveat": ("" if lane.get("lane") != "stale_not_written_by_live_editor" else STALE_LOG_LANE_CAVEAT),
        "console_grep_caveat": EDITOR_LOG_CONSOLE_CAVEAT,
        "stale_match_caveat": "" if anchor.get("anchored") else EDITOR_LOG_STALE_MATCH_CAVEAT,
        "since_anchor_degraded": bool(since) and not anchor.get("anchored"),
        "validation_evidence": "unity_editor_log",
    }
    if search_verdict == "inconclusive" and scope_truncated:
        payload["recommended_next_action"] = EDITOR_LOG_PARTIAL_SCOPE_RECOVERY_ACTION
    return payload


def tail_editor_log_payload(
    project_root: Path,
    log_path: Path,
    *,
    limit: int = 50,
    max_chars: int = EDITOR_LOG_GREP_MAX_CHARS,
    since: str = "",
    bridge_state: dict[str, Any] | None = None,
    host_session_state: dict[str, Any] | None = None,
    journal_events: list[dict[str, Any]] | None = None,
    since_request_id: str = "",
    bridge_state_is_live: bool = True,
    explicit_path_requested: bool = False,
    max_payload_bytes: Any = None,
) -> dict[str, Any]:
    limit = max(1, int(limit or 50))
    anchor = resolve_editor_log_since_anchor(
        log_path,
        since=since,
        bridge_state=bridge_state,
        host_session_state=host_session_state,
        journal_events=journal_events,
        since_request_id=since_request_id,
        bridge_state_is_live=bridge_state_is_live,
    )
    lane = build_editor_log_lane(
        project_root,
        log_path,
        bridge_state=bridge_state,
        anchor=anchor,
        explicit_path_requested=explicit_path_requested,
        editor_is_live=bridge_state_is_live,
    )
    text, first_line_number = _read_editor_log_since_anchor(log_path, anchor, max_chars)
    # Number before filtering: blank lines occupy real line numbers in the log, so counting only the kept lines
    # would report every item several lines early while line_numbering_basis claims editor_log_absolute.
    lines = [
        (first_line_number + index, raw_line.rstrip("\n"))
        for index, raw_line in enumerate(text.splitlines())
        if raw_line.strip()
    ]
    truncated = len(lines) > limit
    visible_lines = lines[-limit:] if truncated else lines
    items = [
        {
            "type": "editor_log",
            "message": line,
            "timestamp": "",
            "stack_trace": "",
            "line": line_number,
        }
        for line_number, line in visible_lines
    ]
    payload = {
        "backend_id": "xuunity.light_unity_mcp",
        "project_root": str(project_root),
        "source": "editor_log",
        "editor_log_path": str(effective_editor_log_path(log_path, anchor)),
        "items": items,
        "truncated": truncated,
        "tail_count": len(items),
        "searched_tail_chars": max_chars,
        "since_anchor": anchor,
        "searched_from_line": first_line_number,
        "line_numbering_basis": (
            "anchored_scope_relative" if anchor.get("scope_truncated") else "editor_log_absolute"
        ),
        "result_trust_class": (
            "session_scoped_editor_log" if anchor.get("anchored") else "editor_log_path_backed_untyped"
        ),
        "log_lane": lane,
        "log_lane_caveat": ("" if lane.get("lane") != "stale_not_written_by_live_editor" else STALE_LOG_LANE_CAVEAT),
        "stale_match_caveat": "" if anchor.get("anchored") else EDITOR_LOG_STALE_MATCH_CAVEAT,
        "since_anchor_degraded": bool(since) and not anchor.get("anchored"),
        "console_tail_caveat": EDITOR_LOG_TAIL_CAVEAT,
        "recommended_next_action": "use_source_editor_log_grep_for_compile_errors",
        "validation_evidence": "unity_editor_log",
    }
    return apply_console_tail_byte_budget(payload, max_payload_bytes)


def resolve_console_tail_byte_budget(requested: Any) -> int:
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return CONSOLE_TAIL_DEFAULT_MAX_PAYLOAD_BYTES
    if value < 0:
        return -1
    return CONSOLE_TAIL_DEFAULT_MAX_PAYLOAD_BYTES if value == 0 else value


def estimate_console_item_bytes(item: dict[str, Any]) -> int:
    if not isinstance(item, dict):
        return CONSOLE_ITEM_BYTE_OVERHEAD
    total = CONSOLE_ITEM_BYTE_OVERHEAD
    for field in ("type", "message", "timestamp", "stack_trace"):
        value = item.get(field)
        if value:
            total += len(str(value).encode("utf-8"))
    return total


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if not value or max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _truncate_console_item_to_budget(item: dict[str, Any], budget: int) -> dict[str, Any]:
    clone = dict(item or {})
    clone["stack_trace"] = ""
    fixed_bytes = CONSOLE_ITEM_BYTE_OVERHEAD + len(CONSOLE_TAIL_BYTE_TRUNCATION_MARKER.encode("utf-8"))
    for field in ("type", "timestamp"):
        value = clone.get(field)
        if value:
            fixed_bytes += len(str(value).encode("utf-8"))
    available_for_message = max(0, budget - fixed_bytes)
    message = str(clone.get("message") or "")
    if len(message.encode("utf-8")) > available_for_message:
        message = _truncate_utf8(message, available_for_message)
    clone["message"] = message + CONSOLE_TAIL_BYTE_TRUNCATION_MARKER
    return clone


def apply_console_tail_byte_budget(payload: dict[str, Any], requested: Any, *, enforced_by: str = "host") -> dict[str, Any]:
    annotated = dict(payload or {})
    if "max_payload_bytes" in annotated:
        return annotated

    budget = resolve_console_tail_byte_budget(requested)
    items = [item for item in (annotated.get("items") or []) if isinstance(item, dict)]
    annotated["max_payload_bytes"] = budget
    annotated["byte_budget_enforced_by"] = enforced_by

    if budget < 0:
        annotated["payload_bytes_estimate"] = sum(estimate_console_item_bytes(item) for item in items)
        annotated["byte_budget_truncated"] = False
        annotated["items_dropped_for_byte_budget"] = 0
        annotated["newest_item_truncated"] = False
    else:
        kept_from_index = len(items)
        running_bytes = 0
        for index in range(len(items) - 1, -1, -1):
            item_bytes = estimate_console_item_bytes(items[index])
            if running_bytes + item_bytes > budget:
                break
            running_bytes += item_bytes
            kept_from_index = index

        if kept_from_index >= len(items) and items:
            truncated_newest = _truncate_console_item_to_budget(items[-1], budget)
            annotated["items"] = [truncated_newest]
            annotated["items_dropped_for_byte_budget"] = len(items) - 1
            annotated["newest_item_truncated"] = True
            annotated["payload_bytes_estimate"] = estimate_console_item_bytes(truncated_newest)
        else:
            annotated["items"] = items[kept_from_index:]
            annotated["items_dropped_for_byte_budget"] = kept_from_index
            annotated["newest_item_truncated"] = False
            annotated["payload_bytes_estimate"] = running_bytes
        annotated["byte_budget_truncated"] = (
            annotated["items_dropped_for_byte_budget"] > 0 or annotated["newest_item_truncated"]
        )

    if annotated["byte_budget_truncated"] or bool(annotated.get("truncated")):
        annotated["truncation_recovery_tool"] = CONSOLE_TAIL_TRUNCATION_RECOVERY_TOOL
        annotated["truncation_recovery_hint"] = CONSOLE_TAIL_TRUNCATION_RECOVERY_HINT
        annotated["full_payload_recovery_hint"] = CONSOLE_TAIL_FULL_PAYLOAD_RECOVERY_HINT
    return annotated


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
    prefer_anchor_adjacent_window: bool = False,
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
            scoped_chars_available = len(scoped_text)
            scope.update(
                {
                    "source": "host_opened_editor_session",
                    "start_offset_bytes": start_offset,
                    "fallback_used": False,
                    "scoped_bytes_available": max(0, file_size - start_offset),
                    "scoped_chars_available": scoped_chars_available,
                    "truncated_to_max_chars": False,
                    "truncated_window_starts_mid_line": False,
                    "truncated_window_ends_mid_line": False,
                    "search_window_direction": "full_anchored_scope",
                    "searched_window_chars": scoped_chars_available,
                    "unsearched_scope_chars": 0,
                }
            )
            if len(scoped_text) > max_chars:
                scope["truncated_to_max_chars"] = True
                scope["searched_window_chars"] = max_chars
                scope["unsearched_scope_chars"] = max(0, scoped_chars_available - max_chars)
                if prefer_anchor_adjacent_window:
                    scope["search_window_direction"] = "anchor_adjacent_head"
                    scope["truncated_window_ends_mid_line"] = scoped_text[max_chars - 1] != "\n"
                    scoped_text = scoped_text[:max_chars]
                else:
                    cut = len(scoped_text) - max_chars
                    scope["search_window_direction"] = "scope_tail"
                    scope["truncated_window_starts_mid_line"] = scoped_text[cut - 1] != "\n"
                    scoped_text = scoped_text[cut:]
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
        diagnosis.setdefault("diagnosis_confidence", "heuristic")
        diagnosis.setdefault("diagnosis_basis", "editor_log_pattern_match")
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
                "Assembly has duplicate references",
                "will not be compiled",
                "Unable to resolve reference",
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
    bridge_owned_by_non_main_process = bool(discovery.get("bridge_owned_by_non_main_process"))

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

    if bridge_owned_by_non_main_process:
        classification = "bridge_owned_by_non_main_process"
        reason = "bridge_state_writer_is_not_the_main_editor"
        recommended_next_action = "wait_for_main_editor_bridge"
        termination_policy = "observe_only"
    elif not bridge_enabled and not live_editor_present:
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
