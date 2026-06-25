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


def try_read_host_editor_session_state(project_root: Path) -> dict[str, Any] | None:
    path = host_editor_session_state_path(project_root)
    if not path.is_file():
        return None

    try:
        data = read_json(path)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def write_host_editor_session_state(project_root: Path, data: dict[str, Any]) -> None:
    write_json(host_editor_session_state_path(project_root), data)


def clear_host_editor_session_state(project_root: Path) -> None:
    path = host_editor_session_state_path(project_root)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def try_read_recent_host_editor_launch_in_progress(project_root: Path) -> dict[str, Any] | None:
    session = try_read_host_editor_session_state(project_root)
    if not session or not bool(session.get("opened_by_host")) or not bool(session.get("launch_in_progress")):
        return None

    path = host_editor_session_state_path(project_root)
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        age_seconds = HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS + 1.0

    if age_seconds > HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS:
        return None

    session["launch_in_progress_age_seconds"] = round(max(0.0, age_seconds), 3)
    return session


def clear_stale_bridge_state(project_root: Path) -> bool:
    path = bridge_state_path(project_root)
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        return False
    return False


def clear_stale_active_test_run_state(project_root: Path) -> bool:
    path = project_root / "Library" / "XUUnityLightMcp" / "state" / "active_test_run.json"
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        return False
    return False


__all__ = [name for name in globals() if not name.startswith("__")]
