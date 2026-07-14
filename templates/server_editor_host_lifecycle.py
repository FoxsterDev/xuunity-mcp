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
from server_core import (
    ToolInvocationError,
    hidden_window_subprocess_kwargs,
    read_json,
    render_launcher_cli,
    write_json,
)
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
TASKKILL_TIMEOUT_SECONDS = 15.0
LAUNCH_HELPER_TIMEOUT_SECONDS = 30.0


from server_editor_host_discovery import *
from server_editor_host_state import *
from server_editor_host_processes import *
from server_editor_host_paths import *

def open_unity_editor(project_root: Path, log_path: Path, unity_app: Path, background_open: bool) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    live_state = try_read_live_editor_state(project_root)
    if live_state is not None:
        requested_version = resolve_unity_app_version(unity_app)
        running_version = str(live_state.get("unity_version") or "")
        if requested_version and running_version and requested_version != running_version:
            raise ToolInvocationError(
                "project_already_open_with_different_unity_version",
                (
                    "This project already appears open in Unity "
                    f"{running_version} (pid {live_state.get('editor_pid')}). "
                    f"Requested Unity version is {requested_version}. "
                    "Close the running editor instance for this project before opening a different version."
                ),
            )

        return {
            "unity_app": str(unity_app),
            "editor_log_path": str(log_path),
            "background_open": background_open,
            "reused_existing_editor": True,
            "editor_pid": live_state.get("editor_pid"),
            "unity_version": running_version,
        }

    process_report = list_process_commands_report()
    visibility = {
        "process_visibility_available": bool(process_report.get("available")),
        "process_visibility_error_code": str(process_report.get("error_code") or ""),
        "process_visibility_stderr": _truncate_host_process_text(process_report.get("stderr") or ""),
        "process_visibility_platform_kind": str(process_report.get("platform_kind") or host_platform_kind()),
    }
    if is_wsl():
        diagnostics = wsl_host_diagnostics()
        visibility["process_visibility_wslpath_available"] = bool(diagnostics.get("wslpath_available"))
        visibility["process_visibility_warnings"] = list(diagnostics.get("warnings") or [])

    process_visibility_available = bool(visibility.get("process_visibility_available"))
    if not process_visibility_available:
        error_code = str(visibility.get("process_visibility_error_code") or "process_visibility_restricted")
        details = {
            "project_root": str(project_root),
            "unity_app": str(unity_app),
            "editor_log_path": str(log_path),
            "background_open": background_open,
            "process_visibility_available": False,
            "process_visibility_error_code": error_code,
            "process_visibility_stderr": str(visibility.get("process_visibility_stderr") or ""),
            "process_visibility_platform_kind": str(visibility.get("process_visibility_platform_kind") or host_platform_kind()),
            "selected_action": "fail_closed",
            "reason": "process_visibility_restricted_before_open",
            "recommended_next_action": "restore_host_process_visibility",
        }
        raise ToolInvocationError(
            "process_visibility_restricted_before_open",
            (
                "Unity process visibility is unavailable, so the wrapper cannot prove this project is closed. "
                "Refusing to open a second Unity editor instance."
            ),
            details,
        )

    process_commands = list(process_report.get("commands") or [])
    detected_editors = find_running_unity_editors_for_project(project_root, process_commands)
    detected_workers = find_running_unity_worker_processes_for_project(project_root, process_commands)
    detected_worker_pids = [int(worker["pid"]) for worker in detected_workers]
    if detected_editors:
        requested_version = resolve_unity_app_version(unity_app)
        detected_versions = sorted(
            {
                str(editor.get("unity_version") or "").strip()
                for editor in detected_editors
                if str(editor.get("unity_version") or "").strip()
            }
        )
        if requested_version and detected_versions and requested_version not in detected_versions:
            raise ToolInvocationError(
                "project_already_open_with_different_unity_version",
                (
                    "This project already appears open in Unity "
                    f"{', '.join(detected_versions)} (pid {detected_editors[0]['pid']}). "
                    f"Requested Unity version is {requested_version}. "
                    "Close the running editor instance for this project before opening a different version."
                ),
            )

        detected_unity_app = str(detected_editors[0].get("unity_app") or unity_app)
        try:
            activate_unity_editor(project_root, Path(detected_unity_app))
        except Exception:
            pass

        return {
            "unity_app": detected_unity_app,
            "editor_log_path": str(log_path),
            "background_open": background_open,
            "reused_existing_editor": True,
            "reused_via": "project_process_detection",
            "bridge_available": False,
            "editor_pid": detected_editors[0]["pid"],
            "unity_version": str(detected_editors[0].get("unity_version") or requested_version or ""),
            "matching_editor_pids": [int(editor["pid"]) for editor in detected_editors],
            "launch_decision": {
                "bridge_ready": False,
                "process_visibility_available": True,
                "main_same_project_editor_pids": [int(editor["pid"]) for editor in detected_editors],
                "worker_pids": detected_worker_pids,
                "selected_action": "reuse",
                "reason": "same_project_editor_process_detected",
            },
        }

    launch_in_progress = try_read_recent_host_editor_launch_in_progress(project_root)
    if launch_in_progress is not None:
        return {
            "unity_app": str(launch_in_progress.get("unity_app") or unity_app),
            "editor_log_path": str(launch_in_progress.get("editor_log_path") or log_path),
            "background_open": bool(launch_in_progress.get("background_open")),
            "reused_existing_editor": True,
            "reused_via": "host_launch_in_progress",
            "opened_by_host": True,
            "launch_in_progress": True,
            "launch_in_progress_age_seconds": launch_in_progress.get("launch_in_progress_age_seconds"),
            "editor_pid": int(launch_in_progress.get("editor_pid") or 0),
            "launch_decision": {
                "bridge_ready": False,
                "process_visibility_available": True,
                "main_same_project_editor_pids": [],
                "worker_pids": detected_worker_pids,
                "selected_action": "wait",
                "reason": "host_launch_in_progress",
            },
        }

    lock_state = inspect_project_lock(project_root)
    if lock_state["present"]:
        live_owner_pids = lock_state["live_owner_pids"]
        if live_owner_pids:
            raise ToolInvocationError(
                "project_already_open_without_bridge",
                (
                    "This project already appears open in Unity, but no reusable MCP bridge session is currently "
                    f"available. Project lock: {lock_state['path']}. "
                    f"Live lock owner pid(s): {', '.join(str(pid) for pid in live_owner_pids)}. "
                    "Focus or recover the running editor instead of launching a second instance."
                ),
            )
        cleared_lock_state = clear_stale_project_lock(project_root)
        if cleared_lock_state.get("present"):
            raise ToolInvocationError(
                "project_lock_present_without_bridge",
                (
                    "This project has a Unity lock file, but no reusable MCP bridge session is currently available. "
                    f"Project lock: {lock_state['path']}. "
                    "Another Unity instance may already own the project, or the editor may have exited uncleanly. "
                "Resolve the running editor or clear the stale lock before retrying."
                ),
            )

    launch_session = build_host_editor_session_state(project_root, unity_app, log_path, background_open, 0)
    launch_session["launch_in_progress"] = True
    write_host_editor_session_state(project_root, launch_session)

    launched_pid = 0
    launch_command: list[str]
    try:
        if host_platform_kind() == "macos":
            launch_command = ["open"]
            if background_open:
                launch_command.append("-g")
            launch_command.extend(
                [
                    "-na",
                    str(unity_app),
                    "--args",
                    "-projectPath",
                    str(project_root),
                    "-logFile",
                    str(log_path),
                    "-accept-apiupdate",
                ]
            )
            try:
                subprocess.run(
                    launch_command,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=LAUNCH_HELPER_TIMEOUT_SECONDS,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                stderr = (getattr(exc, "stderr", "") or "").strip()
                stdout = (getattr(exc, "stdout", "") or "").strip()
                detail = stderr or stdout or str(exc)
                unity_executable_path = unity_app / "Contents" / "MacOS" / "Unity"
                launch_services_error_match = re.search(r"(?:Code=|error\s+)(-?\d+)", detail)
                raise ToolInvocationError(
                    "unity_editor_launch_failed",
                    (
                        f"Failed to launch Unity editor at {unity_app}. "
                        f"Command: {' '.join(launch_command)}. Detail: {detail}"
                    ),
                    {
                        "unity_app_bundle_present": unity_app.is_dir(),
                        "unity_executable_present": unity_executable_path.is_file(),
                        "unity_executable_path": str(unity_executable_path),
                        "launch_services_error_code": (
                            launch_services_error_match.group(1)
                            if launch_services_error_match
                            else ""
                        ),
                    },
                ) from exc

            launched_editor = wait_for_matching_editor_process(project_root, unity_app, 15.0)
            if launched_editor is None:
                hub_launchers = find_running_unity_hub_launchers_for_project(project_root)
                terminated_hub_pids = terminate_project_hub_launchers(project_root, 5000) if hub_launchers else []
                hub_pids = [int(launcher.get("pid") or 0) for launcher in hub_launchers]
                raise ToolInvocationError(
                    "editor_process_not_observed_after_launch",
                    (
                        f"Unity launch command completed but no matching editor process was observed for project {project_root}. "
                        f"Resolved unity_app: {unity_app}. "
                        f"Command: {' '.join(launch_command)}. "
                        f"Observed Unity Hub launcher pid(s): {hub_pids or []}. "
                        f"Terminated stale Hub launcher pid(s): {terminated_hub_pids or []}."
                    ),
                )
            launched_pid = int(launched_editor["pid"])
        else:
            unity_executable = resolve_unity_executable(unity_app)
            project_path_str = wsl_to_windows_path(project_root) if is_wsl() else str(project_root)
            log_path_str = wsl_to_windows_path(log_path) if is_wsl() else str(log_path)
            launch_command = [
                str(unity_executable),
                "-projectPath",
                project_path_str,
                "-logFile",
                log_path_str,
                "-accept-apiupdate",
            ]
            popen_kwargs: dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
                "close_fds": True,
            }
            if os.name == "nt":
                creation_flags = 0
                detached_process = getattr(subprocess, "DETACHED_PROCESS", 0)
                new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                if background_open:
                    creation_flags |= detached_process
                creation_flags |= new_process_group
                if creation_flags:
                    popen_kwargs["creationflags"] = creation_flags
            else:
                popen_kwargs["start_new_session"] = True

            process = subprocess.Popen(launch_command, **popen_kwargs)
            launched_pid = int(process.pid or 0)
    except Exception:
        clear_host_editor_session_state(project_root)
        raise

    write_host_editor_session_state(
        project_root,
        build_host_editor_session_state(project_root, unity_app, log_path, background_open, launched_pid),
    )
    return {
        "unity_app": str(unity_app),
        "editor_log_path": str(log_path),
        "background_open": background_open,
        "opened_by_host": True,
        "editor_pid": launched_pid,
        "launch_command": [str(part) for part in launch_command],
        "launch_decision": {
            "bridge_ready": False,
            "process_visibility_available": True,
            "main_same_project_editor_pids": [],
            "worker_pids": detected_worker_pids,
            "selected_action": "open",
            "reason": "same_project_editor_absence_proven",
        },
    }


def build_plain_batch_build_command(
    project_root: Path,
    unity_app: Path,
    log_path: Path,
    result_path: Path,
    build_target: str,
    output_path: str,
    scene_paths: list[str],
    build_options: list[str],
) -> list[str]:
    unity_binary = resolve_unity_executable(unity_app)
    project_path_str = wsl_to_windows_path(project_root) if is_wsl() else str(project_root)
    log_path_str = wsl_to_windows_path(log_path) if is_wsl() else str(log_path)
    result_path_str = wsl_to_windows_path(result_path) if is_wsl() else str(result_path)

    command = [
        str(unity_binary),
        "-batchmode",
        "-quit",
        "-accept-apiupdate",
        "-projectPath",
        project_path_str,
        "-buildTarget",
        build_target,
        "-logFile",
        log_path_str,
        "-executeMethod",
        "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchBuildCli.ExecuteFromCommandLine",
        "--",
        "--xuunity-build-target",
        build_target,
        "--xuunity-result-file",
        result_path_str,
    ]

    if output_path:
        command.extend(["--xuunity-output-path", output_path])
    for scene_path in scene_paths:
        command.extend(["--xuunity-scene-path", scene_path])
    for build_option in build_options:
        command.extend(["--xuunity-build-option", build_option])

    return command


def build_batch_validation_command(
    project_root: Path,
    unity_app: Path,
    log_path: Path,
    result_path: Path,
    action: str,
    extra_args: list[str] | None = None,
) -> list[str]:
    unity_binary = resolve_unity_executable(unity_app)
    execute_method = (
        "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchTestFrameworkCli.ExecuteFromCommandLine"
        if action == "editmode-tests"
        else "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchValidationCli.ExecuteFromCommandLine"
    )
    project_path_str = wsl_to_windows_path(project_root) if is_wsl() else str(project_root)
    log_path_str = wsl_to_windows_path(log_path) if is_wsl() else str(log_path)
    result_path_str = wsl_to_windows_path(result_path) if is_wsl() else str(result_path)
    command = [
        str(unity_binary),
        "-batchmode",
        "-accept-apiupdate",
        "-projectPath",
        project_path_str,
        "-logFile",
        log_path_str,
        "-executeMethod",
        execute_method,
        "--",
        "--xuunity-batch-action",
        action,
        "--xuunity-result-file",
        result_path_str,
    ]

    if extra_args:
        command.extend(extra_args)
    return command


def terminate_editor_pid(pid: int, timeout_ms: int) -> bool:
    if pid <= 0 or not pid_is_alive(pid):
        return True

    is_windows_like = (os.name == "nt" or sys.platform in ("win32", "cygwin", "msys"))

    if is_windows_like:
        taskkill_success = False
        for cmd in ["taskkill", "taskkill.exe"]:
            try:
                # Deliberately omit /T. Even a verified editor PID must not
                # grant permission to terminate an unbounded descendant tree.
                completed = subprocess.run(
                    [cmd, "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                    timeout=TASKKILL_TIMEOUT_SECONDS,
                    **hidden_window_subprocess_kwargs(),
                )
                if completed.returncode == 0:
                    taskkill_success = True
                    break
            except Exception:
                pass

        if not taskkill_success and os.name == "nt":
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    elif is_wsl():
        if wsl_linux_unity_interop_pid_status(pid) is True:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        else:
            for cmd in ["taskkill.exe", "taskkill"]:
                try:
                    # Same single-PID boundary for Windows processes reached
                    # through WSL interop.
                    subprocess.run(
                        [cmd, "/F", "/PID", str(pid)],
                        capture_output=True,
                        check=False,
                        timeout=TASKKILL_TIMEOUT_SECONDS,
                        **hidden_window_subprocess_kwargs(),
                    )
                    break
                except Exception:
                    pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return not pid_is_alive(pid)

    deadline = time.time() + (max(1000, timeout_ms) / 1000.0)
    while time.time() < deadline:
        if not pid_is_alive(pid):
            return True
        time.sleep(0.2)

    return not pid_is_alive(pid)


def wait_for_project_editor_exit(
    project_root: Path,
    *,
    tracked_pid: int,
    current_pid: int,
    timeout_ms: int,
) -> tuple[bool, list[int]]:
    deadline = time.time() + (max(1000, timeout_ms) / 1000.0)
    live_project_pids: list[int] = []
    while time.time() < deadline:
        visibility = process_visibility_summary()
        if not bool(visibility.get("process_visibility_available")):
            return False, list_live_project_editor_pids(project_root)
        live_project_pids = list_live_project_editor_pids(project_root)
        tracked_alive = tracked_pid > 0 and pid_is_alive(tracked_pid)
        current_alive = current_pid > 0 and pid_is_alive(current_pid)
        if (
            not tracked_alive
            and not current_alive
            and (tracked_pid <= 0 or tracked_pid not in live_project_pids)
            and (current_pid <= 0 or current_pid not in live_project_pids)
        ):
            return True, live_project_pids
        time.sleep(0.2)

    return False, list_live_project_editor_pids(project_root)


def verify_project_editor_closed(project_root: Path, timeout_ms: int) -> dict[str, Any]:
    bounded_timeout_ms = max(0, int(timeout_ms or 0))
    deadline = time.time() + (bounded_timeout_ms / 1000.0)
    live_project_pids: list[int] = []
    visibility = process_visibility_summary()

    while True:
        live_project_pids = list_live_project_editor_pids(project_root)
        visibility = process_visibility_summary()
        process_visibility_available = bool(visibility.get("process_visibility_available"))
        if not process_visibility_available:
            break
        if not live_project_pids:
            break
        if time.time() >= deadline:
            break
        time.sleep(0.2)

    process_visibility_available = bool(visibility.get("process_visibility_available"))
    process_visibility_error_code = str(visibility.get("process_visibility_error_code") or "")
    same_project_editor_closed = process_visibility_available and not live_project_pids
    if not process_visibility_available:
        closeout_classification = "process_visibility_restricted"
        next_distinct_action = "restore_host_process_visibility"
        recommended_next_action = "restore_host_process_visibility"
    elif same_project_editor_closed:
        closeout_classification = "same_project_editor_closed"
        next_distinct_action = "rerun_closed_editor_batch_lane"
        recommended_next_action = "none"
    else:
        closeout_classification = "editor_still_running"
        next_distinct_action = "manual_editor_close_or_request_quit_wait"
        recommended_next_action = "manual_editor_close"

    result = {
        "action": "verify_editor_closed",
        "project_root": str(project_root),
        "timeout_ms": bounded_timeout_ms,
        "same_project_editor_closed": same_project_editor_closed,
        "process_exit_verified": same_project_editor_closed,
        "live_project_editor_pids": live_project_pids,
        "closeout_classification": closeout_classification,
        "recommended_next_action": recommended_next_action,
        "next_distinct_action": next_distinct_action,
        "recommended_recovery_command": (
            render_launcher_cli(
                "request-editor-quit",
                project_root,
                "--timeout-ms", "30000",
                "--wait-for-exit",
                "--exit-timeout-ms", "30000",
            )
            if live_project_pids and process_visibility_available
            else ""
        ),
    }
    result.update(visibility)
    if not process_visibility_available and not process_visibility_error_code:
        result["process_visibility_error_code"] = "process_visibility_restricted"
    return result


def _attach_editor_closed_verification(
    payload: dict[str, Any],
    project_root: Path,
    timeout_ms: int = 0,
) -> dict[str, Any]:
    verification = verify_project_editor_closed(project_root, timeout_ms)
    for key in (
        "same_project_editor_closed",
        "process_exit_verified",
        "live_project_editor_pids",
        "process_visibility_available",
        "process_visibility_error_code",
        "process_visibility_stderr",
        "process_visibility_platform_kind",
        "next_distinct_action",
    ):
        payload[key] = verification.get(key)
    payload["editor_closed_verification"] = verification
    return payload


def restore_host_opened_editor_state(
    project_root: Path,
    timeout_ms: int,
    request_editor_quit: Callable[[str, int], dict[str, Any]],
) -> dict[str, Any]:
    session = try_read_host_editor_session_state(project_root)
    if not session or not bool(session.get("opened_by_host")):
        return _attach_editor_closed_verification({
            "project_root": str(project_root),
            "host_opened_session_found": False,
            "restored": False,
            "closeout_verified": True,
            "closeout_classification": "not_opened_by_host",
            "recommended_next_action": "none",
            "reason": "not_opened_by_host",
        }, project_root, 0)

    tracked_pid = int(session.get("editor_pid") or 0)
    live_state = try_read_live_editor_state(project_root)
    current_pid = int((live_state or {}).get("editor_pid") or 0)
    managed_pid = tracked_pid if tracked_pid > 0 else current_pid
    bounded_timeout_ms = max(1000, timeout_ms)
    quit_wait_timeout_ms = max(1000, bounded_timeout_ms // 2)
    sigterm_timeout_ms = max(1000, bounded_timeout_ms - quit_wait_timeout_ms)
    restoration = {
        "project_root": str(project_root),
        "host_opened_session_found": True,
        "tracked_editor_pid": tracked_pid,
        "live_state_editor_pid": current_pid,
        "restored": False,
        "closeout_verified": False,
        "closeout_classification": "",
        "recommended_next_action": "inspect_project_editor_processes",
        "reason": "",
        "close_path": "",
    }

    already_closed_probe = verify_project_editor_closed(project_root, 0)
    if bool(already_closed_probe.get("process_visibility_available")) and bool(
        already_closed_probe.get("same_project_editor_closed")
    ):
        clear_host_editor_session_state(project_root)
        restoration["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
        restoration["stale_active_test_run_cleared"] = clear_stale_active_test_run_state(project_root)
        restoration["stale_project_lock_state"] = clear_stale_project_lock(project_root)
        restoration["restored"] = False
        restoration["closeout_verified"] = True
        restoration["process_exit_verified"] = True
        restoration["same_project_editor_closed"] = True
        restoration["closeout_classification"] = "tracked_editor_already_closed"
        restoration["recommended_next_action"] = "none"
        restoration["next_distinct_action"] = "rerun_closed_editor_batch_lane"
        restoration["reason"] = "tracked_editor_already_closed"
        restoration["close_path"] = "zero_time_process_probe"
        restoration["editor_closed_verification"] = already_closed_probe
        for key in (
            "live_project_editor_pids",
            "process_visibility_available",
            "process_visibility_error_code",
            "process_visibility_stderr",
            "process_visibility_platform_kind",
        ):
            restoration[key] = already_closed_probe.get(key)
        return restoration

    if current_pid > 0 and (tracked_pid <= 0 or current_pid == tracked_pid):
        restoration["quit_request_attempted"] = True
        try:
            quit_response = request_editor_quit(str(project_root), bounded_timeout_ms)
            restoration["quit_request_accepted"] = quit_response.get("status") == "ok"
            restoration["quit_request_id"] = str(quit_response.get("request_id") or "")
            restoration["quit_request_status"] = str(quit_response.get("status") or "")
        except ToolInvocationError as exc:
            restoration["quit_request_error"] = {
                "code": exc.code,
                "message": exc.message,
            }
            if exc.details:
                restoration["quit_request_error"]["details"] = dict(exc.details)
            restoration["quit_request_id"] = str((exc.details or {}).get("request_id") or "")
            restoration["quit_request_status"] = "error"

        quit_request_id = str(restoration.get("quit_request_id") or "")
        if quit_request_id:
            restoration["recommended_recovery_command"] = (
                f"request-final-status --project-root {project_root} --request-id {quit_request_id}"
            )

        closed_after_quit, live_project_pids = wait_for_project_editor_exit(
            project_root,
            tracked_pid=tracked_pid,
            current_pid=current_pid,
            timeout_ms=quit_wait_timeout_ms,
        )
        if closed_after_quit:
            clear_host_editor_session_state(project_root)
            restoration["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
            restoration["stale_active_test_run_cleared"] = clear_stale_active_test_run_state(project_root)
            restoration["restored"] = True
            restoration["closeout_verified"] = True
            restoration["process_exit_verified"] = True
            restoration["same_project_editor_closed"] = True
            restoration["closeout_classification"] = "closed_via_unity_editor_quit"
            restoration["recommended_next_action"] = "none"
            restoration["next_distinct_action"] = "rerun_closed_editor_batch_lane"
            restoration["reason"] = "host_opened_editor_closed"
            restoration["close_path"] = "unity.editor.quit"
            restoration["closed_editor_pid"] = current_pid
            restoration["live_project_editor_pids"] = live_project_pids
            clear_stale_project_lock(project_root)
            _attach_editor_closed_verification(restoration, project_root, 0)
            return restoration

    # The session file may be stale: after a crash or reboot the recorded pid
    # can belong to an unrelated process. Only force-kill a pid that is still
    # provably a Unity editor of THIS project (bridge state or command line).
    managed_pid_confirmed_project_editor = (
        managed_pid > 0 and managed_pid in list_live_project_editor_pids(project_root)
    )
    if managed_pid > 0 and not managed_pid_confirmed_project_editor and pid_is_alive(managed_pid):
        restoration["restored"] = False
        restoration["closeout_verified"] = False
        restoration["closeout_classification"] = "tracked_pid_not_project_editor"
        restoration["reason"] = "tracked_pid_identity_unverified"
        restoration["recommended_next_action"] = "inspect_project_editor_processes"
        restoration["next_distinct_action"] = "manual_editor_close_or_request_quit_wait"
        restoration["termination_skipped_pid"] = managed_pid
        restoration["live_project_editor_pids"] = list_live_project_editor_pids(project_root)
        restoration["same_project_editor_closed"] = False
        restoration["process_exit_verified"] = False
        restoration.update(process_visibility_summary())
        return restoration

    if managed_pid_confirmed_project_editor and terminate_editor_pid(managed_pid, sigterm_timeout_ms):
        live_project_pids = list_live_project_editor_pids(project_root)
        if managed_pid not in live_project_pids:
            clear_host_editor_session_state(project_root)
            restoration["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
            restoration["stale_active_test_run_cleared"] = clear_stale_active_test_run_state(project_root)
            restoration["restored"] = True
            restoration["closeout_verified"] = True
            restoration["process_exit_verified"] = True
            restoration["same_project_editor_closed"] = True
            restoration["reason"] = "host_opened_editor_closed"
            restoration["recommended_next_action"] = "none"
            restoration["next_distinct_action"] = "rerun_closed_editor_batch_lane"
            if bool(restoration.get("quit_request_attempted")) and bool(restoration.get("quit_request_accepted")):
                restoration["closeout_classification"] = "quit_ack_without_exit_sigterm_recovered"
                restoration["close_path"] = "unity.editor.quit+host_sigterm"
            elif bool(restoration.get("quit_request_attempted")):
                restoration["closeout_classification"] = "quit_request_failed_host_sigterm_recovered"
                restoration["close_path"] = "failed_quit_request+host_sigterm"
            else:
                restoration["closeout_classification"] = "closed_via_host_sigterm"
                restoration["close_path"] = "host_sigterm"
            restoration["closed_editor_pid"] = managed_pid
            restoration["live_project_editor_pids"] = live_project_pids
            clear_stale_project_lock(project_root)
            _attach_editor_closed_verification(restoration, project_root, 0)
            return restoration

    if managed_pid > 0 and not pid_is_alive(managed_pid):
        live_project_pids = list_live_project_editor_pids(project_root)
        if not live_project_pids:
            terminated_hub_pids = terminate_project_hub_launchers(project_root, timeout_ms)
            clear_host_editor_session_state(project_root)
            restoration["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
            restoration["stale_active_test_run_cleared"] = clear_stale_active_test_run_state(project_root)
            restoration["restored"] = False
            restoration["closeout_verified"] = True
            restoration["process_exit_verified"] = True
            restoration["same_project_editor_closed"] = True
            restoration["closeout_classification"] = "tracked_editor_already_closed"
            restoration["recommended_next_action"] = "none"
            restoration["next_distinct_action"] = "rerun_closed_editor_batch_lane"
            restoration["reason"] = "tracked_editor_already_closed"
            restoration["terminated_hub_launcher_pids"] = terminated_hub_pids
            _attach_editor_closed_verification(restoration, project_root, 0)
            return restoration

        if bool(restoration.get("quit_request_attempted")) and bool(restoration.get("quit_request_accepted")):
            restoration["closeout_classification"] = "quit_ack_without_exit"
            restoration["reason"] = "quit_request_completed_without_process_exit"
            restoration["recommended_next_action"] = (
                "inspect_quit_request_final_status"
                if restoration.get("recommended_recovery_command")
                else "manual_editor_close"
            )
        else:
            restoration["closeout_classification"] = "project_editor_still_running_untracked"
            restoration["reason"] = "project_editor_still_running_untracked"
        restoration["live_project_editor_pids"] = live_project_pids
        restoration["same_project_editor_closed"] = False
        restoration["process_exit_verified"] = False
        restoration["next_distinct_action"] = "manual_editor_close_or_request_quit_wait"
        restoration.update(process_visibility_summary())
        return restoration

    if bool(restoration.get("quit_request_attempted")) and bool(restoration.get("quit_request_accepted")):
        restoration["closeout_classification"] = "quit_ack_without_exit"
        restoration["reason"] = "quit_request_completed_without_process_exit"
        restoration["recommended_next_action"] = (
            "inspect_quit_request_final_status"
            if restoration.get("recommended_recovery_command")
            else "manual_editor_close"
        )
    elif bool(restoration.get("quit_request_attempted")):
        restoration["closeout_classification"] = "quit_request_failed_editor_still_running"
        restoration["reason"] = "quit_request_failed_editor_still_running"
        restoration["recommended_next_action"] = (
            "inspect_quit_request_final_status"
            if restoration.get("recommended_recovery_command")
            else "manual_editor_close"
        )
    else:
        restoration["closeout_classification"] = "tracked_editor_still_running"
        restoration["reason"] = "tracked_editor_still_running"
    restoration["live_project_editor_pids"] = list_live_project_editor_pids(project_root)
    restoration["same_project_editor_closed"] = False
    restoration["process_exit_verified"] = False
    restoration["next_distinct_action"] = "manual_editor_close_or_request_quit_wait"
    restoration.update(process_visibility_summary())
    return restoration


def wait_for_ready(
    project_root: Path,
    timeout_ms: int,
    heartbeat_max_age_seconds: int,
    startup_policy: str,
    editor_log_path: Path,
) -> dict[str, Any]:
    if startup_policy not in STARTUP_POLICIES:
        raise ToolInvocationError("invalid_startup_policy", f"Unknown startup policy: {startup_policy}")

    if not bridge_enabled(project_root):
        raise ToolInvocationError(
            "bridge_disabled",
            (
                "Unity bridge is disabled for this project. "
                "Enable it with init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project "
                "and reopen Unity."
            ),
        )

    started_at = time.time()
    deadline = started_at + (timeout_ms / 1000.0)
    state: dict[str, Any] | None = None
    while time.time() < deadline:
        state = try_read_bridge_state(project_root)
        if bridge_state_is_ready(state, heartbeat_max_age_seconds):
            age_seconds = heartbeat_age_seconds(state)
            state["startup_policy"] = startup_policy
            state["editor_log_path"] = str(editor_log_path)
            state["heartbeat_age_seconds"] = round(age_seconds or 0.0, 3)
            return state

        classification = classify_editor_log(read_recent_editor_log(editor_log_path, started_at), startup_policy)
        if classification:
            code, message = classification
            raise ToolInvocationError(code, message)

        time.sleep(1.0)

    raise ToolInvocationError(
        "editor_ready_timeout",
        (
            "Timed out waiting for a healthy Unity bridge heartbeat. "
            f"Last inspected log: {editor_log_path}. "
            f"Bridge state present: {bool(state)}. "
            f"Running editor pid(s): {[int(editor.get('pid') or 0) for editor in find_running_unity_editors_for_project(project_root)]}. "
            f"Running Unity Hub launcher pid(s): {[int(launcher.get('pid') or 0) for launcher in find_running_unity_hub_launchers_for_project(project_root)]}. "
            f"Host session: {try_read_host_editor_session_state(project_root) or {}}"
        ),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
