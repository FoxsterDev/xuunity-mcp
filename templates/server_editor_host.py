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

import server_editor_host_discovery as _discovery
import server_editor_host_state as _state
import server_editor_host_processes as _processes
import server_editor_host_paths as _paths
import server_editor_host_lifecycle as _lifecycle

ACTIVATION_DELAY_SECONDS = _discovery.ACTIVATION_DELAY_SECONDS
UNITY_EDITOR_ROOTS_ENV = _discovery.UNITY_EDITOR_ROOTS_ENV
HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS = _discovery.HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS

_OWNER_BY_NAME = {
    'host_platform_kind': _discovery,
    '_truncate_host_process_text': _discovery,
    'parse_unity_version_from_text': _discovery,
    'version_sort_key': _discovery,
    'normalize_unity_installation_path': _discovery,
    'resolve_unity_executable': _discovery,
    'resolve_unity_app_version': _discovery,
    'configured_unity_editor_roots': _discovery,
    'unity_hub_secondary_install_root': _discovery,
    'candidate_unity_editor_roots': _discovery,
    'iter_candidate_installation_paths_from_root': _discovery,
    'discover_unity_installations': _discovery,
    'list_process_commands': _discovery,
    'list_process_commands_report': _discovery,
    'process_visibility_summary': _discovery,
    'try_read_host_editor_session_state': _state,
    'write_host_editor_session_state': _state,
    'clear_host_editor_session_state': _state,
    'try_read_recent_host_editor_launch_in_progress': _state,
    'clear_stale_bridge_state': _state,
    'clear_stale_active_test_run_state': _state,
    '_normalized_project_match_key': _processes,
    'extract_unity_project_path_from_command': _processes,
    'unity_command_targets_project': _processes,
    'classify_unity_process_role': _processes,
    'find_running_unity_editors_for_project': _processes,
    'find_running_unity_worker_processes_for_project': _processes,
    'find_running_unity_hub_launchers_for_project': _processes,
    'list_live_project_editor_pids': _processes,
    'project_lock_path': _processes,
    'try_list_path_owner_pids': _processes,
    'inspect_project_lock': _processes,
    'clear_stale_project_lock': _processes,
    'build_host_editor_session_state': _paths,
    'update_host_editor_session_pid': _paths,
    'detect_unity_app_path': _paths,
    'read_project_unity_version': _paths,
    'detect_unity_app_path_for_project': _paths,
    'activate_unity_editor': _paths,
    'try_find_matching_editor_process': _paths,
    'wait_for_matching_editor_process': _paths,
    'terminate_project_hub_launchers': _paths,
    'bridge_state_is_ready': _paths,
    'classify_editor_log': _paths,
    'resolve_editor_log_path': _paths,
    'sanitize_filename_component': _paths,
    'default_batch_build_log_path': _paths,
    'default_batch_build_result_path': _paths,
    'default_batch_operation_log_path': _paths,
    'default_batch_operation_result_path': _paths,
    'resolve_batch_build_output_path': _paths,
    'read_recent_editor_log': _paths,
    'open_unity_editor': _lifecycle,
    'build_plain_batch_build_command': _lifecycle,
    'build_batch_validation_command': _lifecycle,
    'terminate_editor_pid': _lifecycle,
    'wait_for_project_editor_exit': _lifecycle,
    'verify_project_editor_closed': _lifecycle,
    '_attach_editor_closed_verification': _lifecycle,
    'restore_host_opened_editor_state': _lifecycle,
    'wait_for_ready': _lifecycle,
}

_SYNC_NAMES = {
    'ACTIVATION_DELAY_SECONDS',
    'Any',
    'Callable',
    'HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS',
    'Path',
    'STARTUP_POLICIES',
    'ToolInvocationError',
    'UNITY_EDITOR_ROOTS_ENV',
    '_attach_editor_closed_verification',
    '_normalized_project_match_key',
    '_truncate_host_process_text',
    'activate_unity_editor',
    'bridge_enabled',
    'bridge_state_is_ready',
    'bridge_state_path',
    'build_batch_validation_command',
    'build_host_editor_session_state',
    'build_plain_batch_build_command',
    'candidate_unity_editor_roots',
    'classify_editor_log',
    'classify_unity_process_role',
    'clear_host_editor_session_state',
    'clear_stale_active_test_run_state',
    'clear_stale_bridge_state',
    'clear_stale_project_lock',
    'configured_unity_editor_roots',
    'current_host_platform_adapter',
    'default_batch_build_log_path',
    'default_batch_build_result_path',
    'default_batch_operation_log_path',
    'default_batch_operation_result_path',
    'default_editor_log_path',
    'detect_unity_app_path',
    'detect_unity_app_path_for_project',
    'discover_unity_installations',
    'extract_unity_project_path_from_command',
    'find_running_unity_editors_for_project',
    'find_running_unity_hub_launchers_for_project',
    'find_running_unity_worker_processes_for_project',
    'heartbeat_age_seconds',
    'host_editor_session_state_path',
    'host_path_to_local_path',
    'host_platform_kind',
    'inspect_project_lock',
    'is_wsl',
    'iter_candidate_installation_paths_from_root',
    'json',
    'list_live_project_editor_pids',
    'list_process_commands',
    'list_process_commands_report',
    'logs_dir',
    'normalize_unity_installation_path',
    'open_unity_editor',
    'os',
    'parse_unity_version_from_text',
    'pid_is_alive',
    'process_visibility_summary',
    'project_lock_path',
    're',
    'read_json',
    'read_project_unity_version',
    'read_recent_editor_log',
    'resolve_batch_build_output_path',
    'resolve_editor_log_path',
    'resolve_unity_app_version',
    'resolve_unity_executable',
    'restore_host_opened_editor_state',
    'sanitize_filename_component',
    'shutil',
    'signal',
    'subprocess',
    'sys',
    'terminate_editor_pid',
    'terminate_project_hub_launchers',
    'time',
    'try_find_matching_editor_process',
    'try_list_path_owner_pids',
    'try_read_bridge_state',
    'try_read_host_editor_session_state',
    'try_read_live_editor_state',
    'try_read_recent_host_editor_launch_in_progress',
    'unity_command_targets_project',
    'unity_hub_secondary_install_root',
    'update_host_editor_session_pid',
    'verify_project_editor_closed',
    'version_sort_key',
    'wait_for_matching_editor_process',
    'wait_for_project_editor_exit',
    'wait_for_ready',
    'write_host_editor_session_state',
    'write_json',
    'wsl_host_diagnostics',
    'wsl_linux_unity_interop_pid_status',
    'wsl_to_windows_path',
}

_OWNER_MODULES = {_discovery, _state, _processes, _paths, _lifecycle}
_ORIGINALS: dict[tuple[Any, str], Any] = {
    (module, name): getattr(module, name)
    for module in _OWNER_MODULES
    for name in _SYNC_NAMES
    if hasattr(module, name)
}


def _sync_owner(module: Any) -> None:
    for name in _SYNC_NAMES:
        if name in globals():
            value = globals()[name]
            if getattr(value, "_xuunity_editor_host_facade_wrapper", False) is True:
                if (module, name) in _ORIGINALS:
                    setattr(module, name, _ORIGINALS[(module, name)])
                continue
            setattr(module, name, value)
        elif (module, name) in _ORIGINALS:
            setattr(module, name, _ORIGINALS[(module, name)])


def _call_owner(name: str, *args: Any, **kwargs: Any) -> Any:
    module = _OWNER_BY_NAME[name]
    _sync_owner(module)
    return getattr(module, name)(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name not in _OWNER_BY_NAME:
        raise AttributeError(name)

    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return _call_owner(name, *args, **kwargs)

    _wrapper.__name__ = name
    _wrapper.__qualname__ = name
    _wrapper.__doc__ = getattr(_OWNER_BY_NAME[name], name).__doc__
    _wrapper._xuunity_editor_host_facade_wrapper = True
    return _wrapper


__all__ = sorted(set(_OWNER_BY_NAME) | {
    'ACTIVATION_DELAY_SECONDS',
    'UNITY_EDITOR_ROOTS_ENV',
    'HOST_EDITOR_LAUNCH_IN_PROGRESS_MAX_AGE_SECONDS',
})
