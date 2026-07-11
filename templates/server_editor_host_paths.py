#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from server_bridge_runtime import (
    bridge_state_path,
    bridge_enabled,
    default_editor_log_path,
    heartbeat_age_seconds,
    host_editor_session_state_path,
    logs_dir,
    pid_is_alive,
    try_read_bridge_state,
    try_read_live_editor_state,
)
from server_core import ToolInvocationError, read_json, write_json
from server_host_platform import (
    current_host_platform_adapter,
    host_path_to_local_path,
    is_wsl,
    wsl_host_diagnostics,
    wsl_linux_unity_interop_pid_status,
    wsl_to_windows_path,
)
from server_specs import STARTUP_POLICIES

ACTIVATION_DELAY_SECONDS = 0.35
UNITY_EDITOR_ROOTS_ENV = "XUUNITY_UNITY_EDITOR_ROOTS"
HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS = 90.0


from server_editor_host_discovery import *
from server_editor_host_state import *
from server_editor_host_processes import *

def build_host_editor_session_state(
    project_root: Path,
    unity_app: Path,
    log_path: Path,
    background_open: bool,
    editor_pid: int = 0,
) -> dict[str, Any]:
    log_session_start_offset_bytes = 0
    log_session_start_mtime = 0.0
    try:
        if log_path.is_file():
            stat_result = log_path.stat()
            log_session_start_offset_bytes = int(stat_result.st_size or 0)
            log_session_start_mtime = float(stat_result.st_mtime or 0.0)
    except OSError:
        log_session_start_offset_bytes = 0
        log_session_start_mtime = 0.0

    return {
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "editor_log_path": str(log_path),
        "background_open": background_open,
        "opened_by_host": True,
        "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "editor_pid": max(0, int(editor_pid or 0)),
        "log_session_started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "log_session_start_offset_bytes": log_session_start_offset_bytes,
        "log_session_start_mtime": round(log_session_start_mtime, 6),
        "log_scope_source": "host_opened_editor_session",
    }


def update_host_editor_session_pid(project_root: Path, editor_pid: int) -> None:
    state = try_read_host_editor_session_state(project_root)
    if not state or not bool(state.get("opened_by_host")):
        return

    normalized = dict(state)
    normalized["editor_pid"] = max(0, int(editor_pid or 0))
    write_host_editor_session_state(project_root, normalized)


def detect_unity_app_path(explicit_path: str | None) -> Path:
    if explicit_path:
        normalized = normalize_unity_installation_path(Path(explicit_path))
        if normalized is None:
            raise ToolInvocationError("unity_app_not_found", f"Unity installation not found: {explicit_path}")
        return normalized

    candidates = discover_unity_installations()
    if not candidates:
        raise ToolInvocationError(
            "unity_app_not_found",
            (
                "Could not auto-detect a Unity installation. "
                f"Check the default Unity Hub install locations for {host_platform_kind()} "
                f"or set {UNITY_EDITOR_ROOTS_ENV} to one or more custom roots."
            ),
        )
    return candidates[-1][1]


def read_project_unity_version(project_root: Path) -> str | None:
    version_path = project_root / "ProjectSettings" / "ProjectVersion.txt"
    if not version_path.is_file():
        return None

    try:
        for line in version_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("m_EditorVersion:"):
                version = line.split(":", 1)[1].strip()
                return version or None
    except OSError:
        return None

    return None


def detect_unity_app_path_for_project(project_root: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        return detect_unity_app_path(explicit_path)

    project_version = read_project_unity_version(project_root)
    if project_version:
        for version, candidate in discover_unity_installations():
            if version == project_version:
                return candidate

    return detect_unity_app_path(None)


def activate_unity_editor(project_root: Path, explicit_unity_app: Path | None = None) -> dict[str, Any]:
    unity_app = explicit_unity_app or detect_unity_app_path_for_project(project_root, None)
    if host_platform_kind() == "macos":
        try:
            subprocess.run(
                ["open", str(unity_app)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise ToolInvocationError(
                "unity_editor_activation_failed",
                (
                    f"Failed to activate Unity editor at {unity_app}. "
                    f"Command: open {unity_app}. Detail: {detail}"
                ),
            ) from exc
    time.sleep(ACTIVATION_DELAY_SECONDS)
    return {
        "unity_app": str(unity_app),
        "activation_delay_seconds": ACTIVATION_DELAY_SECONDS,
    }


def try_find_matching_editor_process(project_root: Path, unity_app: Path) -> dict[str, Any] | None:
    requested_version = resolve_unity_app_version(unity_app)
    matches = find_running_unity_editors_for_project(project_root)
    if not matches:
        return None

    if requested_version:
        for match in matches:
            if str(match.get("unity_version") or "") == requested_version:
                return match

    return matches[0]


def wait_for_matching_editor_process(
    project_root: Path,
    unity_app: Path,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.time() + max(1.0, timeout_seconds)
    while time.time() < deadline:
        match = try_find_matching_editor_process(project_root, unity_app)
        if match is not None:
            return match
        time.sleep(0.25)
    return None


def terminate_project_hub_launchers(project_root: Path, timeout_ms: int) -> list[int]:
    terminated: list[int] = []
    for launcher in find_running_unity_hub_launchers_for_project(project_root):
        pid = int(launcher.get("pid") or 0)
        if pid > 0 and terminate_editor_pid(pid, timeout_ms):
            terminated.append(pid)
    return terminated


def bridge_state_is_ready(state: dict[str, Any] | None, heartbeat_max_age_seconds: int) -> bool:
    if not isinstance(state, dict):
        return False

    pid = int(state.get("editor_pid") or 0)
    age_seconds = heartbeat_age_seconds(state)
    return (
        pid_is_alive(pid)
        and age_seconds is not None
        and age_seconds <= heartbeat_max_age_seconds
        and state.get("health_status") == "healthy"
        and not bool(state.get("is_compiling"))
    )


def classify_editor_log(log_text: str, startup_policy: str) -> tuple[str, str] | None:
    if not log_text:
        return None

    if "Project has invalid dependencies:" in log_text or "An error occurred while resolving packages:" in log_text:
        return (
            "package_resolution_failed",
            "Unity package resolution failed. Inspect Editor.log for invalid dependencies, git package errors, or registry failures.",
        )

    if "Could not clone [" in log_text:
        return (
            "package_resolution_failed",
            "Unity could not clone a git package dependency. Inspect Editor.log for the failing dependency URL or commit hash.",
        )

    safe_mode_marker_present = any(
        marker in log_text
        for marker in (
            "Safe Mode",
            "safe mode",
            "Enter Safe Mode",
            "Opening project in Safe Mode",
        )
    )
    compile_error_present = "error CS" in log_text
    if compile_error_present:
        if safe_mode_marker_present:
            return (
                "interactive_compile_block_with_safe_mode_dialog",
                "Compilation errors were detected during startup and Editor.log includes Safe Mode markers. "
                "This wrapper will not click Safe Mode dialogs; run the batch compile gate and fix compile "
                "errors or open Safe Mode manually.",
            )

        if startup_policy == "batch_compile_lane":
            return (
                "interactive_compile_block_detected",
                "Interactive Unity startup is blocked by compilation errors. Use the batch compile lane for "
                "compile-only validation or fix the compile errors first.",
            )

        if startup_policy == "auto_enter_safe_mode_preferred":
            return (
                "safe_mode_manual_required",
                "Compilation errors were detected during startup. This host-side wrapper cannot click the Safe "
                "Mode dialog. Prefer auto-enter Safe Mode in Unity preferences or reopen manually into Safe Mode.",
            )

        return (
            "interactive_compile_block_detected",
            "Compilation errors were detected during interactive startup. This wrapper is failing fast instead "
            "of waiting for a bridge heartbeat that cannot become healthy.",
        )

    return None


def resolve_editor_log_path(project_root: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    return default_editor_log_path(project_root)


def sanitize_filename_component(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "item"

    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return sanitized.strip("._-") or "item"


def default_batch_build_log_path(project_root: Path, build_target: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return logs_dir(project_root) / "batch" / f"{timestamp}_{sanitize_filename_component(build_target)}.log"


def default_batch_build_result_path(project_root: Path, build_target: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return logs_dir(project_root) / "batch" / f"{timestamp}_{sanitize_filename_component(build_target)}_result.json"


def default_batch_operation_log_path(project_root: Path, operation_name: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return logs_dir(project_root) / "batch" / f"{timestamp}_{sanitize_filename_component(operation_name)}.log"


def default_batch_operation_result_path(project_root: Path, operation_name: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return logs_dir(project_root) / "batch" / f"{timestamp}_{sanitize_filename_component(operation_name)}_result.json"


def resolve_batch_build_output_path(project_root: Path, explicit_path: str | None) -> str:
    if not explicit_path:
        return ""

    path = Path(explicit_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return str(path.resolve())


def read_recent_editor_log(log_path: Path, command_started_at: float) -> str:
    if not log_path.is_file():
        return ""

    try:
        stat = log_path.stat()
    except OSError:
        return ""

    if stat.st_mtime < command_started_at - 1.0:
        return ""

    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    if len(text) > 200000:
        return text[-200000:]
    return text


__all__ = [name for name in globals() if not name.startswith("__")]
