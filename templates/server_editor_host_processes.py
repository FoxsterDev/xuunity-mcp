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

def _normalized_project_match_key(path_value: str | Path) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    if is_wsl() and len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        drive = text[0].lower()
        text = f"/mnt/{drive}{text[2:]}"
    try:
        resolved = str(Path(text).expanduser().resolve())
    except OSError:
        resolved = str(Path(text).expanduser())
    normalized = resolved.replace("\\", "/").rstrip("/")
    normalized = normalized.lower()
    return normalized


def extract_unity_project_path_from_command(command: str) -> str:
    normalized_command = str(command or "").replace("\\ ", " ").strip()
    if not normalized_command:
        return ""

    match = re.search(
        r'(?:^|\s)-projectPath\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s].*?))(?=\s+-\w|\s*$)',
        normalized_command,
        re.IGNORECASE,
    )
    if not match:
        return ""

    for group in match.groups():
        value = str(group or "").strip()
        if value:
            return value
    return ""


def unity_command_targets_project(command: str, project_root: Path) -> bool:
    project_path_argument = extract_unity_project_path_from_command(command)
    if not project_path_argument:
        return False
    return _normalized_project_match_key(project_path_argument) == _normalized_project_match_key(project_root)


def classify_unity_process_role(command: str) -> str:
    normalized_command = str(command or "").replace("\\ ", " ").strip()
    if not normalized_command:
        return ""

    lower_command = normalized_command.lower()
    command_for_match = normalized_command.replace("\\", "/")
    lower_command_for_match = command_for_match.lower()

    if "/unity hub.app/" in lower_command_for_match or "unity hub helper" in lower_command:
        return "launcher"

    worker_markers = (
        "assetimportworker",
        "asset import worker",
        "-assetimportworker",
        "unityshadercompiler",
        "unity shader compiler",
        "unitypackagemanager",
        "unity package manager",
        "/unity helper.app/",
    )
    if any(marker in lower_command_for_match for marker in worker_markers):
        return "worker"

    if (
        "Unity.app/Contents/MacOS/Unity" in normalized_command
        or "unity.exe" in lower_command
        or re.search(r'(^|\s)"?/[^"\s]*/Unity"?(?:\s|$)', command_for_match)
        or command_for_match.endswith("/Unity")
    ):
        return "main_editor"

    return ""


def find_running_unity_editors_for_project(
    project_root: Path,
    process_commands: list[tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen_pids: set[int] = set()
    for pid, command in (process_commands if process_commands is not None else list_process_commands()):
        normalized_command = command.replace("\\ ", " ").strip()
        command_for_match = normalized_command.replace("\\", "/")

        if pid <= 0 or pid in seen_pids or not pid_is_alive(pid):
            continue

        if classify_unity_process_role(normalized_command) != "main_editor":
            continue

        project_path_argument = extract_unity_project_path_from_command(normalized_command)
        if not project_path_argument or not unity_command_targets_project(normalized_command, project_root):
            continue

        unity_app = ""
        unity_version = ""
        app_match = re.search(r"(.+?/Unity\.app)/Contents/MacOS/Unity", normalized_command)
        if app_match:
            unity_app = app_match.group(1)
            unity_version = resolve_unity_app_version(Path(unity_app))
        else:
            windows_match = re.search(r'([A-Za-z]:\\[^"\r\n]*?Unity\.exe)', normalized_command)
            linux_match = re.search(r"((?:/[^\"\s]+)+/Unity)(?:\s|$)", command_for_match)
            if windows_match:
                unity_app = windows_match.group(1)
                unity_version = resolve_unity_app_version(Path(unity_app))
            elif linux_match:
                unity_app = linux_match.group(1)
                unity_version = resolve_unity_app_version(Path(unity_app))

        matches.append(
            {
                "pid": pid,
                "command": normalized_command,
                "project_path": project_path_argument,
                "unity_app": unity_app,
                "unity_version": unity_version,
                "process_role": "main_editor",
            }
        )
        seen_pids.add(pid)

    return matches


def find_running_unity_worker_processes_for_project(
    project_root: Path,
    process_commands: list[tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen_pids: set[int] = set()
    for pid, command in (process_commands if process_commands is not None else list_process_commands()):
        normalized_command = command.replace("\\ ", " ").strip()

        if pid <= 0 or pid in seen_pids or not pid_is_alive(pid):
            continue

        if classify_unity_process_role(normalized_command) != "worker":
            continue

        project_path_argument = extract_unity_project_path_from_command(normalized_command)
        if not project_path_argument or not unity_command_targets_project(normalized_command, project_root):
            continue

        matches.append(
            {
                "pid": pid,
                "command": normalized_command,
                "project_path": project_path_argument,
                "process_role": "worker",
            }
        )
        seen_pids.add(pid)

    return matches


def find_running_unity_hub_launchers_for_project(project_root: Path) -> list[dict[str, Any]]:
    if host_platform_kind() != "macos":
        return []

    matches: list[dict[str, Any]] = []
    seen_pids: set[int] = set()
    for pid, command in list_process_commands():
        normalized_command = command.replace("\\ ", " ").strip()

        if pid <= 0 or pid in seen_pids or not pid_is_alive(pid):
            continue

        if "Unity Hub.app/Contents/MacOS/Unity Hub" not in normalized_command:
            continue

        project_path_argument = extract_unity_project_path_from_command(normalized_command)
        if not project_path_argument or not unity_command_targets_project(normalized_command, project_root):
            continue

        matches.append(
            {
                "pid": pid,
                "command": normalized_command,
                "project_path": project_path_argument,
            }
        )
        seen_pids.add(pid)

    return matches


def list_live_project_editor_pids(project_root: Path) -> list[int]:
    pids: set[int] = set()

    # A persisted bridge-state PID is not process identity. The file can
    # survive an editor crash long enough for the operating system to reuse
    # the PID for an unrelated application. Only the current process table,
    # with both a Unity executable role and an exact -projectPath match, may
    # classify a PID as this project's editor.
    for editor in find_running_unity_editors_for_project(project_root):
        pid = int(editor.get("pid") or 0)
        if pid > 0 and pid_is_alive(pid):
            pids.add(pid)

    return sorted(pids)


def project_lock_path(project_root: Path) -> Path:
    return project_root / "Temp" / "UnityLockfile"


def try_list_path_owner_pids(path: Path) -> list[int]:
    if not path.is_file():
        return []

    lsof_path = shutil.which("lsof")
    if not lsof_path:
        return []

    try:
        completed = subprocess.run(
            [lsof_path, "-t", "--", str(path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    owner_pids: list[int] = []
    for line in completed.stdout.splitlines():
        raw_value = line.strip()
        if not raw_value:
            continue
        try:
            pid = int(raw_value)
        except ValueError:
            continue
        if pid > 0 and pid not in owner_pids:
            owner_pids.append(pid)
    return owner_pids


def windows_lock_open_denied(path: Path) -> bool | None:
    """Windows share-mode probe; None when not applicable (non-Windows/missing file).

    lsof does not exist on Windows, so per-pid lock attribution is unavailable
    there. Unity holds Temp/UnityLockfile with an exclusive share mode, so a
    denied read-write open proves some live process owns the lock even without
    attribution. A PermissionError from other causes (e.g. a read-only file)
    also reports True — the fail-safe direction, since callers only use this to
    refuse deleting the lock.
    """
    if os.name != "nt" or not path.is_file():
        return None
    try:
        handle = os.open(str(path), os.O_RDWR)
    except PermissionError:
        return True
    except OSError:
        return None
    os.close(handle)
    return False


def inspect_project_lock(project_root: Path) -> dict[str, Any]:
    lock_path = project_lock_path(project_root)
    present = lock_path.is_file()
    owner_pids = try_list_path_owner_pids(lock_path) if present else []
    owner_pid_source = "lsof" if owner_pids else ""
    lock_open_denied = windows_lock_open_denied(lock_path) if present else None
    if present and not owner_pids and lock_open_denied:
        owner_pids = list_live_project_editor_pids(project_root)
        if owner_pids:
            owner_pid_source = "windows_share_mode_editor_attribution"
    live_owner_pids = [pid for pid in owner_pids if pid_is_alive(pid)]

    return {
        "path": str(lock_path),
        "present": present,
        "owner_pids": owner_pids,
        "live_owner_pids": live_owner_pids,
        "lock_open_denied": bool(lock_open_denied),
        "owner_pid_source": owner_pid_source,
    }


def clear_stale_project_lock(project_root: Path) -> dict[str, Any]:
    lock_state = inspect_project_lock(project_root)
    if not lock_state["present"] or lock_state["live_owner_pids"] or lock_state.get("lock_open_denied"):
        lock_state["removed"] = False
        return lock_state

    try:
        Path(lock_state["path"]).unlink()
        lock_state["removed"] = True
        lock_state["present"] = False
    except OSError:
        lock_state["removed"] = False
    return lock_state


__all__ = [name for name in globals() if not name.startswith("__")]
