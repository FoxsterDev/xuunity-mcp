#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from server_core import BRIDGE_ENABLE_RECOVERY_COMMAND

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
    is_windows_like_host,
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
from server_hub_licensing import (
    cleanup_owned_licensing_children,
    discover_owned_licensing_children,
    licensing_client_pid_snapshot,
    prepare_hub_licensing_unity_args,
    resolve_hub_licensing_ipc,
    sanitize_launch_command,
    sanitize_unity_args,
)

from server_licensing_state import guard_editor_licensing_launch, editor_license_evidence

ACTIVATION_DELAY_SECONDS = 0.35
UNITY_EDITOR_ROOTS_ENV = "XUUNITY_UNITY_EDITOR_ROOTS"
HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS = 90.0
TASKKILL_TIMEOUT_SECONDS = 15.0
LAUNCH_HELPER_TIMEOUT_SECONDS = 30.0
TRANSIENT_LICENSING_BLOCKER_GRACE_SECONDS = 5.0
STARTUP_BLOCKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "licensing_connection_lost",
        re.compile(
            r"connection with (?:the )?Unity Licensing Client has been lost|re-connection attempt was UN-successful",
            re.IGNORECASE,
        ),
    ),
    (
        "licensing_channel_unavailable",
        re.compile(r"Channel\s+[^\r\n]+\s+doesn't exist", re.IGNORECASE),
    ),
    (
        "licensing_initialization_failed",
        re.compile(r"Licensing(?:\s+initialization)?\s+failed|waiting for Licensing to initialize", re.IGNORECASE),
    ),
    (
        "terms_or_activation_ui_required",
        re.compile(r"accept.*terms|terms.*accept|sign in to (?:the )?Unity Hub|activation.*required", re.IGNORECASE),
    ),
    (
        "invalid_editor_license",
        re.compile(
            r"No valid Unity Editor license found|Unity has not been activated with a valid License|"
            r"No valid Unity license|No ULF license found|Access token is unavailable|"
            r"packages were not registered because your license doesn't allow it",
            re.IGNORECASE,
        ),
    ),
    (
        "api_update_dialog",
        re.compile(r"API Update Required|UnityUpgradable", re.IGNORECASE),
    ),
    (
        "safe_mode_dialog",
        re.compile(r"Enter Safe Mode|Opening project in Safe Mode", re.IGNORECASE),
    ),
)
LICENSING_RECOVERY_PATTERN = re.compile(
    r"Successfully connected to LicensingClient|Successfully resolved entitlement details|"
    r"Successfully updated (?:the )?access token",
    re.IGNORECASE,
)


def _redact_licensing_channels(text: str) -> str:
    return re.sub(
        r"(?:Unity-)?LicenseClient-[A-Za-z0-9._-]+",
        "<redacted-licensing-channel>",
        str(text or ""),
    )


from server_editor_host_discovery import *
from server_editor_host_state import *
from server_editor_host_processes import *
from server_editor_host_paths import *

def _normalize_unity_launch_args(unity_args: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw_value in unity_args or []:
        value = str(raw_value)
        if not value or "\x00" in value:
            raise ToolInvocationError(
                "invalid_unity_launch_argument",
                "Unity launch arguments must be non-empty strings without NUL characters.",
            )
        normalized.append(value)
    return normalized


def _unity_launch_argument_value(unity_args: list[str], option_name: str) -> str:
    for index, value in enumerate(unity_args[:-1]):
        if value.lower() == option_name.lower():
            return unity_args[index + 1]
    return ""


def _command_contains_unity_launch_args(command: str, unity_args: list[str]) -> bool:
    if not unity_args:
        return True
    try:
        command_parts = shlex.split(str(command or ""), posix=os.name != "nt")
    except ValueError:
        return False

    expected_index = 0
    for part in command_parts:
        if part == unity_args[expected_index]:
            expected_index += 1
            if expected_index == len(unity_args):
                return True
    return False


@guard_editor_licensing_launch
def open_unity_editor(
    project_root: Path,
    log_path: Path,
    unity_app: Path,
    background_open: bool,
    unity_args: list[str] | None = None,
) -> dict[str, Any]:
    extra_unity_args = _normalize_unity_launch_args(unity_args)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    live_state = try_read_live_editor_state(project_root)
    if live_state is not None and not extra_unity_args:
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
            "unity_args": sanitize_unity_args(extra_unity_args),
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
            "unity_args": sanitize_unity_args(extra_unity_args),
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
        detected_command = str(detected_editors[0].get("command") or "")
        if extra_unity_args and not _command_contains_unity_launch_args(detected_command, extra_unity_args):
            raise ToolInvocationError(
                "existing_editor_launch_arguments_not_applied",
                (
                    "A Unity editor for this project is already running, so requested launch arguments cannot "
                    "be applied to that process. Close only the identified same-project editor, then retry the "
                    "open command with the requested arguments."
                ),
                {
                    "project_root": str(project_root),
                    "editor_pid": int(detected_editors[0].get("pid") or 0),
                    "matching_editor_pids": [int(editor["pid"]) for editor in detected_editors],
                    "requested_unity_args": sanitize_unity_args(extra_unity_args),
                    "requested_unity_args_applied": False,
                    "recommended_next_action": "close_same_project_editor_then_retry_open",
                },
            )
        try:
            activate_unity_editor(project_root, Path(detected_unity_app))
        except Exception:
            pass

        return {
            "unity_app": detected_unity_app,
            "editor_log_path": str(log_path),
            "background_open": background_open,
            "unity_args": sanitize_unity_args(extra_unity_args),
            "requested_unity_args_applied": bool(extra_unity_args),
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

    if live_state is not None:
        raise ToolInvocationError(
            "existing_editor_launch_arguments_unverifiable",
            (
                "A live bridge reports an existing editor for this project, but its process command could not be "
                "verified. Refusing to claim that requested Unity launch arguments were applied."
            ),
            {
                "project_root": str(project_root),
                "editor_pid": int(live_state.get("editor_pid") or 0),
                "requested_unity_args": sanitize_unity_args(extra_unity_args),
                "requested_unity_args_applied": False,
                "recommended_next_action": "restore_process_visibility_or_close_same_project_editor",
            },
        )

    launch_in_progress = try_read_recent_host_editor_launch_in_progress(project_root)
    if launch_in_progress is not None:
        return {
            "unity_app": str(launch_in_progress.get("unity_app") or unity_app),
            "editor_log_path": str(launch_in_progress.get("editor_log_path") or log_path),
            "background_open": bool(launch_in_progress.get("background_open")),
            "unity_args": list(launch_in_progress.get("unity_args") or []),
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

    licensing_client_pids_before_launch = licensing_client_pid_snapshot(process_report)
    extra_unity_args, licensing_ipc_resolution = prepare_hub_licensing_unity_args(
        extra_unity_args,
        process_report,
    )
    launch_session = build_host_editor_session_state(
        project_root,
        unity_app,
        log_path,
        background_open,
        0,
        extra_unity_args,
    )
    launch_session["licensing_ipc_resolution"] = licensing_ipc_resolution
    launch_session["licensing_client_pids_before_launch"] = licensing_client_pids_before_launch
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
                    *extra_unity_args,
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
                        f"Command: {' '.join(sanitize_launch_command(launch_command))}. Detail: {detail}"
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
                        f"Command: {' '.join(sanitize_launch_command(launch_command))}. "
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
                *extra_unity_args,
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

    completed_session = build_host_editor_session_state(
        project_root,
        unity_app,
        log_path,
        background_open,
        launched_pid,
        extra_unity_args,
    )
    completed_session["licensing_ipc_resolution"] = licensing_ipc_resolution
    completed_session["licensing_client_pids_before_launch"] = licensing_client_pids_before_launch
    post_launch_process_report = list_process_commands_report()
    completed_session["owned_licensing_children"] = discover_owned_licensing_children(
        baseline_pids=licensing_client_pids_before_launch,
        editor_pid=launched_pid,
        process_report=post_launch_process_report,
    )
    write_host_editor_session_state(project_root, completed_session)
    return {
        "unity_app": str(unity_app),
        "editor_log_path": str(log_path),
        "background_open": background_open,
        "unity_args": sanitize_unity_args(extra_unity_args),
        "licensing_ipc_channel": "<redacted>" if _unity_launch_argument_value(extra_unity_args, "-licensingIpc") else "",
        "licensing_ipc_channel_redacted": bool(_unity_launch_argument_value(extra_unity_args, "-licensingIpc")),
        "licensing_ipc_resolution": licensing_ipc_resolution,
        "owned_licensing_child_count": len(completed_session.get("owned_licensing_children") or []),
        "license_state": "unknown",
        "license_probe_active": False,
        "licensing_channel_fingerprint": licensing_ipc_resolution.get("selected_candidate_fingerprint", ""),
        "opened_by_host": True,
        "editor_pid": launched_pid,
        "launch_command": sanitize_launch_command([str(part) for part in launch_command]),
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
    if action == "editmode-tests":
        execute_method = "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchTestFrameworkCli.ExecuteFromCommandLine"
    elif action == "package-restore":
        execute_method = "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchPackageRestoreCli.ExecuteFromCommandLine"
    else:
        execute_method = "XUUnity.LightMcp.Editor.Batch.XUUnityLightMcpBatchValidationCli.ExecuteFromCommandLine"
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

    is_windows_like = is_windows_like_host() and not is_wsl()

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


def force_terminate_verified_project_editor(
    project_root: Path,
    expected_live_pids: list[int],
    timeout_ms: int,
) -> dict[str, Any]:
    visibility = process_visibility_summary()
    if not bool(visibility.get("process_visibility_available")):
        raise ToolInvocationError(
            "process_visibility_restricted",
            "Refusing forced editor termination because host process visibility is unavailable.",
            visibility,
        )

    expected = sorted({int(pid) for pid in expected_live_pids if int(pid) > 0})
    current = sorted({int(pid) for pid in list_live_project_editor_pids(project_root) if int(pid) > 0})
    if len(current) != 1 or current[0] not in expected:
        raise ToolInvocationError(
            "force_termination_identity_not_unique",
            (
                "Refusing forced editor termination because exactly one current same-project editor identity "
                "was not re-verified."
            ),
            {
                "expected_live_project_editor_pids": expected,
                "current_live_project_editor_pids": current,
                "termination_attempted": False,
            },
        )

    editor_pid = current[0]
    terminated = terminate_editor_pid(editor_pid, max(1000, int(timeout_ms or 0)))
    verification = verify_project_editor_closed(project_root, max(1000, int(timeout_ms or 0)))
    result = {
        "termination_attempted": True,
        "termination_identity_reverified": True,
        "force_terminated_editor_pid": editor_pid,
        "force_termination_signal_completed": bool(terminated),
    }
    result.update(verification)
    if not bool(verification.get("same_project_editor_closed")):
        raise ToolInvocationError(
            "editor_force_termination_failed",
            f"Forced termination was requested for editor pid {editor_pid}, but process exit was not verified.",
            result,
        )
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


def _attach_owned_licensing_cleanup(
    payload: dict[str, Any],
    session: dict[str, Any],
    timeout_ms: int,
) -> None:
    payload["licensing_child_cleanup"] = cleanup_owned_licensing_children(
        session,
        max(1000, min(15000, int(timeout_ms or 0))),
    )


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
        _attach_owned_licensing_cleanup(restoration, session, bounded_timeout_ms)
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
            _attach_owned_licensing_cleanup(restoration, session, bounded_timeout_ms)
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
            _attach_owned_licensing_cleanup(restoration, session, bounded_timeout_ms)
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
            _attach_owned_licensing_cleanup(restoration, session, bounded_timeout_ms)
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


def _readiness_error_from_log_observation(
    project_root: Path,
    state: dict[str, Any] | None,
    classification: tuple[str, str],
) -> ToolInvocationError:
    """Turn a startup-log observation into a condition-shaped readiness error.

    Editor.log is not an authoritative compile result. A file whose mtime moved
    during this wait can still retain older compiler diagnostics in its tail.
    Preserve the observation for a condition-specific timeout (while an
    explicit Safe Mode dialog remains immediately actionable), and mark compile
    truth as unmeasured.
    """

    observed_state = dict(state or {})
    log_code, log_summary = classification
    live_editor_pids = sorted(
        {
            int(editor.get("pid") or 0)
            for editor in find_running_unity_editors_for_project(project_root)
            if int(editor.get("pid") or 0) > 0
        }
    )
    bridge_pid = int(observed_state.get("editor_pid") or 0)
    bridge_pid_alive = bridge_pid > 0 and pid_is_alive(bridge_pid)

    details: dict[str, Any] = {
        "compile_state": "unmeasured",
        "compile_measurement_source": "none",
        "editor_log_observation_code": log_code,
        "editor_log_observation_summary": log_summary,
        "observed_bridge_pid": bridge_pid,
        "observed_bridge_pid_alive": bridge_pid_alive,
        "observed_live_editor_pids": live_editor_pids,
        "bridge_bootstrap_attached": observed_state.get("bridge_bootstrap_attached"),
        "is_compiling": bool(observed_state.get("is_compiling")),
        "is_updating": bool(observed_state.get("is_updating")),
        "asset_import_in_progress": bool(observed_state.get("asset_import_in_progress")),
        "domain_reload_in_progress": bool(observed_state.get("domain_reload_in_progress")),
        "package_operation_in_progress": bool(observed_state.get("package_operation_in_progress")),
    }

    if log_code == "interactive_compile_block_with_safe_mode_dialog":
        code = "startup_safe_mode_dialog_observed"
        summary = (
            "Editor.log contains Safe Mode dialog and compiler-diagnostic markers written during the readiness "
            "wait. Handle the dialog explicitly; this is a log observation, not an authoritative compile verdict."
        )
        next_action = "open_safe_mode_manually"
    elif bridge_pid > 0 and live_editor_pids and bridge_pid not in live_editor_pids:
        code = "editor_identity_changed"
        summary = (
            "The persisted bridge state belongs to a different editor pid than the live editor for this project. "
            "Refresh host/session state before retrying; no compile result was measured."
        )
        next_action = "refresh_host_session_if_needed"
    elif bridge_pid_alive and bool(observed_state.get("is_compiling")):
        code = "editor_busy_compiling"
        summary = (
            "The live editor is compiling and has not reached readiness yet. Wait for editor idle, then retry; "
            "no compile verdict was measured by this readiness wait."
        )
        next_action = "wait_for_editor_idle_then_retry"
    elif bridge_pid_alive and any(
        bool(observed_state.get(key))
        for key in (
            "is_updating",
            "asset_import_in_progress",
            "domain_reload_in_progress",
            "package_operation_in_progress",
            "script_reload_pending",
        )
    ):
        code = "editor_busy_importing"
        summary = (
            "The live editor is still importing or reloading and has not reached readiness yet. Wait for editor "
            "idle, then retry; no compile result was measured."
        )
        next_action = "wait_for_editor_idle_then_retry"
    elif live_editor_pids and (
        not observed_state
        or bridge_pid <= 0
        or not bridge_pid_alive
        or observed_state.get("bridge_bootstrap_attached") is False
    ):
        code = "editor_not_ready_bridge_not_attached"
        summary = (
            "A matching Unity editor is live, but a current bridge has not attached yet. Poll bridge readiness, "
            "then retry; do not restart the editor based on this observation. No compile result was measured."
        )
        next_action = "poll_bridge_bootstrap_attached_then_retry"
    else:
        code = "startup_log_compile_markers_observed"
        summary = (
            "Editor.log contains compiler-diagnostic markers written during the readiness wait. Use the batch "
            "compile gate to establish current compile truth; this readiness check did not run a compile."
        )
        next_action = (
            "open_safe_mode_manually"
            if log_code == "safe_mode_manual_required"
            else "run_batch_compile_gate_and_fix_errors"
        )

    details["readiness_condition"] = code
    details["readiness_summary"] = summary
    details["recommended_next_action"] = next_action
    return ToolInvocationError(code, summary, details)


def _editor_log_idle_seconds(editor_log_path: Path) -> float | None:
    try:
        return max(0.0, time.time() - float(editor_log_path.stat().st_mtime))
    except OSError:
        return None


def _startup_blocker_observation(
    project_root: Path,
    editor_log_path: Path,
    started_at: float,
) -> dict[str, Any]:
    live_editor_pids = sorted(
        {
            int(editor.get("pid") or 0)
            for editor in find_running_unity_editors_for_project(project_root)
            if int(editor.get("pid") or 0) > 0
        }
    )
    log_text = read_recent_editor_log(editor_log_path, started_at)
    log_observation_during_wait = bool(log_text)
    if not log_text and live_editor_pids and editor_log_path.is_file():
        try:
            log_text = editor_log_path.read_text(encoding="utf-8", errors="ignore")[-200000:]
        except OSError:
            log_text = ""
    last_match_kind = ""
    last_match_line = ""
    last_licensing_recovery_line = ""
    for line in log_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if LICENSING_RECOVERY_PATTERN.search(stripped):
            last_licensing_recovery_line = _redact_licensing_channels(stripped[-500:])
            if last_match_kind.startswith("licensing_") or last_match_kind == "invalid_editor_license":
                last_match_kind = ""
                last_match_line = ""
        for kind, pattern in STARTUP_BLOCKER_PATTERNS:
            if pattern.search(stripped):
                last_match_kind = kind
                last_match_line = _redact_licensing_channels(stripped[-500:])

    idle_seconds = _editor_log_idle_seconds(editor_log_path)
    observation: dict[str, Any] = {
        "editor_pid": live_editor_pids[0] if len(live_editor_pids) == 1 else 0,
        "live_project_editor_pids": live_editor_pids,
        "editor_log_path": str(editor_log_path),
        "editor_log_idle_seconds": None if idle_seconds is None else round(idle_seconds, 3),
        "bridge_bootstrap_attached": False,
        "editor_log_observation_during_wait": log_observation_during_wait,
        "editor_log_observation_scope": (
            "current_wait" if log_observation_during_wait else "stale_tail_for_live_project_editor"
        ),
    }
    session = try_read_host_editor_session_state(project_root) or {}
    observation["opened_by_host"] = bool(session.get("opened_by_host")) and int(session.get("editor_pid") or 0) in live_editor_pids
    observation.update(editor_license_evidence(editor_log_path, session))
    if last_match_line:
        observation["startup_blocker_kind"] = last_match_kind
        observation["last_matched_startup_blocker_line"] = last_match_line
        licensing_channel_match = re.search(
            r"Channel\s+['\"]?([^'\"\s]+)['\"]?\s+doesn't exist",
            last_match_line,
            re.IGNORECASE,
        )
        if licensing_channel_match:
            observation["licensing_channel"] = "<redacted>"
            observation["licensing_channel_redacted"] = True
    if last_licensing_recovery_line:
        observation["last_licensing_recovery_line"] = last_licensing_recovery_line
    return observation


def _launch_blocked_error(observation: dict[str, Any]) -> ToolInvocationError:
    blocker_kind = str(observation.get("startup_blocker_kind") or "unknown_startup_blocker")
    blocker_line = str(observation.get("last_matched_startup_blocker_line") or "")
    details = dict(observation)
    details["launch_classification"] = "launch_blocked_probable_modal"
    if blocker_kind.startswith("licensing_"):
        resolution, _ = resolve_hub_licensing_ipc()
        details["licensing_ipc_resolution"] = resolution
        if str(resolution.get("status") or "") == "resolved":
            details["licensing_handoff_classification"] = "hub_ipc_available_but_not_forwarded"
            details["recommended_next_action"] = "retry_hub_aware_ensure_ready"
        else:
            details["licensing_handoff_classification"] = "manual_user_action_required"
            details["recommended_next_action"] = str(
                resolution.get("required_human_action") or "start_or_sign_in_to_unity_hub"
            )
    elif blocker_kind in {"terms_or_activation_ui_required", "invalid_editor_license"}:
        details["licensing_handoff_classification"] = "terms_or_activation_ui_required"
        details["recommended_next_action"] = "complete_terms_sign_in_or_activation_in_unity_hub"
    else:
        details["recommended_next_action"] = "dismiss_startup_dialog_or_relaunch_with_noninteractive_arguments"
    if (blocker_kind.startswith("licensing_") or blocker_kind in {"invalid_editor_license", "terms_or_activation_ui_required"}) and observation.get("opened_by_host") is False:
        details["licensing_handoff_classification"] = "licensing_ipc_not_forwarded_external_launch"
        details["recommended_next_action"] = "Reopen using open-editor --unity-arg=<argument> so the wrapper forwards the Hub licensing channel."
    return ToolInvocationError(
        "launch_blocked_probable_modal",
        (
            "A Unity editor process is alive, but the MCP bridge never attached and Editor.log identifies "
            f"a probable startup blocker ({blocker_kind}). Last matched line: {blocker_line}"
        ),
        details,
    )


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
                f"Enable it with {BRIDGE_ENABLE_RECOVERY_COMMAND.format(project_root='<path>')} "
                "and reopen Unity."
            ),
        )

    started_at = time.time()
    deadline = started_at + (timeout_ms / 1000.0)
    state: dict[str, Any] | None = None
    last_readiness_error: ToolInvocationError | None = None
    while time.time() < deadline:
        state = try_read_bridge_state(project_root)
        if bridge_state_is_ready(state, heartbeat_max_age_seconds):
            session = try_read_host_editor_session_state(project_root) or {}
            license_evidence = editor_license_evidence(editor_log_path, session)
            if license_evidence["license_state"] == "unlicensed":
                observation = _startup_blocker_observation(project_root, editor_log_path, started_at)
                observation.setdefault("startup_blocker_kind", "invalid_editor_license")
                raise _launch_blocked_error(observation)
            state.update(license_evidence)
            age_seconds = heartbeat_age_seconds(state)
            state["startup_policy"] = startup_policy
            state["editor_log_path"] = str(editor_log_path)
            state["heartbeat_age_seconds"] = round(age_seconds or 0.0, 3)
            return state

        classification = classify_editor_log(read_recent_editor_log(editor_log_path, started_at), startup_policy)
        if classification:
            code, message = classification
            if code in {
                "interactive_compile_block_detected",
                "interactive_compile_block_with_safe_mode_dialog",
                "safe_mode_manual_required",
            }:
                readiness_error = _readiness_error_from_log_observation(project_root, state, classification)
                if readiness_error.code == "startup_safe_mode_dialog_observed":
                    raise readiness_error
                # A bridge can attach or finish import immediately after the log
                # moves. Do not turn that normal startup race into a blocking
                # verdict; retain the typed condition for the timeout path and
                # keep polling for authoritative bridge readiness.
                last_readiness_error = readiness_error
                time.sleep(1.0)
                continue
            raise ToolInvocationError(code, message)

        blocker_observation = _startup_blocker_observation(project_root, editor_log_path, started_at)
        if blocker_observation.get("live_project_editor_pids") and blocker_observation.get(
            "last_matched_startup_blocker_line"
        ):
            blocker_kind = str(blocker_observation.get("startup_blocker_kind") or "")
            blocker_is_fresh_licensing_signal = (
                blocker_kind.startswith("licensing_") or blocker_kind == "invalid_editor_license"
            ) and bool(blocker_observation.get("editor_log_observation_during_wait"))
            if (
                blocker_is_fresh_licensing_signal
                and (time.time() - started_at) < TRANSIENT_LICENSING_BLOCKER_GRACE_SECONDS
            ):
                # Unity 2022 can briefly report that both the supplied Hub
                # channel and its version-local fallback channel are absent,
                # then launch/connect the fallback client and resolve the
                # entitlement. Give only fresh licensing evidence a short
                # recovery window; stale invalid-license dialogs still fail
                # immediately and the timeout path retains the typed blocker.
                time.sleep(1.0)
                continue
            raise _launch_blocked_error(blocker_observation)

        time.sleep(1.0)

    if last_readiness_error is not None:
        raise last_readiness_error

    blocker_observation = _startup_blocker_observation(project_root, editor_log_path, started_at)
    if blocker_observation.get("live_project_editor_pids"):
        if blocker_observation.get("last_matched_startup_blocker_line"):
            raise _launch_blocked_error(blocker_observation)
        details = dict(blocker_observation)
        details["launch_classification"] = "editor_process_alive_bridge_never_attached"
        details["recommended_next_action"] = "read_editor_log_before_extending_wait"
        raise ToolInvocationError(
            "editor_process_alive_bridge_never_attached",
            (
                "A Unity editor process remained alive until the readiness deadline, but the MCP bridge never "
                f"attached. Read {editor_log_path} before extending the wait."
            ),
            details,
        )

    raise ToolInvocationError(
        "editor_ready_timeout",
        (
            "Timed out waiting for a healthy Unity bridge heartbeat. "
            f"Last inspected log: {editor_log_path}. "
            f"Bridge state present: {bool(state)}. "
            f"Running Unity Hub launcher pid(s): {[int(launcher.get('pid') or 0) for launcher in find_running_unity_hub_launchers_for_project(project_root)]}. "
            f"Host session: {try_read_host_editor_session_state(project_root) or {}}"
        ),
        blocker_observation,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
