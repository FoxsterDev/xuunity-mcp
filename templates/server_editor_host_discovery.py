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


def host_platform_kind() -> str:
    return current_host_platform_adapter().platform_kind


def _truncate_host_process_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def parse_unity_version_from_text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    match = re.search(r"(\d{4}\.\d+\.\d+[A-Za-z]\d+)", text)
    if match:
        return match.group(1)
    return text


def version_sort_key(version: str) -> tuple[Any, ...]:
    text = (version or "").strip()
    match = re.match(r"(\d+)\.(\d+)\.(\d+)([A-Za-z])(\d+)$", text)
    if not match:
        return (0, 0, 0, 0, 0, text)

    stream_rank = {
        "a": 0,
        "b": 1,
        "f": 2,
        "p": 3,
        "x": 4,
    }
    major, minor, patch, stream, stream_number = match.groups()
    return (
        int(major),
        int(minor),
        int(patch),
        stream_rank.get(stream.lower(), 99),
        int(stream_number),
        text,
    )


def normalize_unity_installation_path(path: Path) -> Path | None:
    candidate = Path(host_path_to_local_path(path)).expanduser().resolve()
    platform_kind = host_platform_kind()
    in_wsl = is_wsl()

    if platform_kind == "macos":
        if candidate.is_file() and candidate.name == "Unity" and candidate.parent.name == "MacOS":
            app_path = candidate.parent.parent.parent
            if app_path.name == "Unity.app":
                return app_path
        if candidate.is_dir() and candidate.name == "Unity.app" and (candidate / "Contents" / "MacOS" / "Unity").is_file():
            return candidate
        return None

    if platform_kind == "windows" or in_wsl:
        if candidate.is_file() and candidate.name.lower() in ("unity.exe", "unity"):
            return candidate
        if candidate.is_dir():
            for name in ("Unity.exe", "Unity", "unity.exe", "unity"):
                direct = candidate / name
                nested = candidate / "Editor" / name
                if direct.is_file():
                    return direct
                if nested.is_file():
                    return nested
        return None

    if candidate.is_file() and candidate.name == "Unity":
        return candidate
    if candidate.is_dir():
        direct = candidate / "Unity"
        nested = candidate / "Editor" / "Unity"
        if direct.is_file():
            return direct
        if nested.is_file():
            return nested
    return None


def resolve_unity_executable(unity_app: Path) -> Path:
    normalized = normalize_unity_installation_path(unity_app)
    if normalized is None:
        raise ToolInvocationError("unity_app_not_found", f"Unity installation not found: {unity_app}")

    if host_platform_kind() == "macos":
        executable = normalized / "Contents" / "MacOS" / "Unity"
    else:
        executable = normalized

    if not executable.is_file():
        raise ToolInvocationError("unity_binary_not_found", f"Unity binary not found: {executable}")
    return executable


def resolve_unity_app_version(unity_app: Path) -> str:
    normalized = normalize_unity_installation_path(unity_app)
    if normalized is None:
        for part in unity_app.parts:
            match = re.search(r"(\d{4}\.\d+\.\d+[A-Za-z]\d+)", part)
            if match:
                return match.group(1)
        return ""

    platform_kind = host_platform_kind()
    if platform_kind == "macos":
        return normalized.parent.name

    if platform_kind == "windows":
        if normalized.parent.name == "Editor":
            return parse_unity_version_from_text(normalized.parent.parent.name)
        return parse_unity_version_from_text(normalized.parent.name)

    if normalized.parent.name == "Editor":
        return parse_unity_version_from_text(normalized.parent.parent.name)
    return parse_unity_version_from_text(normalized.parent.name)


def configured_unity_editor_roots() -> list[Path]:
    raw = (os.environ.get(UNITY_EDITOR_ROOTS_ENV) or "").strip()
    if not raw:
        return []

    if is_wsl() and ";" in raw:
        entries = raw.split(";")
    elif is_wsl() and re.match(r"^[A-Za-z]:[\\/]", raw):
        entries = [raw]
    else:
        entries = raw.split(os.pathsep)

    roots: list[Path] = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        roots.append(Path(host_path_to_local_path(entry)).expanduser())
    return roots


def unity_hub_secondary_install_root() -> Path | None:
    """Unity Hub 'Installs location' when moved off the default drive.

    Stored as a JSON string in %APPDATA%/UnityHub/secondaryInstallPath.json.
    """
    appdata = (os.environ.get("APPDATA") or "").strip()
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    config_path = base / "UnityHub" / "secondaryInstallPath.json"
    try:
        raw = config_path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw.strip('"')
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value.strip()).expanduser()


def candidate_unity_editor_roots() -> list[Path]:
    configured = configured_unity_editor_roots()
    if configured:
        return configured

    platform_kind = host_platform_kind()
    roots: list[Path] = []
    in_wsl = is_wsl()

    if platform_kind == "macos":
        roots.append(Path("/Applications/Unity/Hub/Editor"))
        return roots

    if platform_kind == "windows" or in_wsl:
        seen: set[str] = set()
        if platform_kind == "windows":
            for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
                value = (os.environ.get(env_name) or "").strip()
                if not value:
                    continue
                expanded = str(Path(value).expanduser())
                if expanded.lower() in seen:
                    continue
                seen.add(expanded.lower())
                roots.append(Path(expanded))
            secondary_root = unity_hub_secondary_install_root()
            if secondary_root is not None and str(secondary_root).lower() not in seen:
                seen.add(str(secondary_root).lower())
                roots.append(secondary_root)
        else:
            for drive in ("c", "d", "e"):
                drive_root = Path(f"/mnt/{drive}")
                if drive_root.is_dir():
                    roots.append(drive_root)
                for pf in ("Program Files", "Program Files (x86)", "ProgramFiles", "ProgramFiles (x86)", "ProgramW6432"):
                    path = Path(f"/mnt/{drive}/{pf}")
                    if path.is_dir():
                        roots.append(path)
            roots.append(Path.home() / "Unity" / "Hub" / "Editor")
            roots.append(Path("/opt/Unity/Hub/Editor"))
            roots.append(Path("/opt/unity/Hub/Editor"))
        return roots

    roots.append(Path.home() / "Unity" / "Hub" / "Editor")
    roots.append(Path("/opt/Unity/Hub/Editor"))
    roots.append(Path("/opt/unity/Hub/Editor"))
    return roots


def iter_candidate_installation_paths_from_root(root: Path) -> list[Path]:
    platform_kind = host_platform_kind()
    in_wsl = is_wsl()
    candidates: list[Path] = []

    normalized_root = normalize_unity_installation_path(root)
    if normalized_root is not None:
        candidates.append(normalized_root)
        return candidates

    if not root.exists():
        return candidates

    if platform_kind == "macos":
        candidates.extend(sorted(root.glob("*/Unity.app")))
        return candidates

    if platform_kind == "windows" or in_wsl:
        candidates.extend(sorted(root.glob("*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Unity/Hub/Editor/*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("UnityHub/Editor/*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Unity*/Editor/*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Unity*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Unity/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("Program*/Unity*/Editor/*/Editor/Unity.exe")))
        candidates.extend(sorted(root.glob("*/Editor/Unity")))
        candidates.extend(sorted(root.glob("Editor/Unity")))
        candidates.extend(sorted(root.glob("Unity/Hub/Editor/*/Editor/Unity")))
        candidates.extend(sorted(root.glob("UnityHub/Editor/*/Editor/Unity")))
        candidates.extend(sorted(root.glob("Unity*/Editor/*/Editor/Unity")))
        candidates.extend(sorted(root.glob("Unity*/Editor/Unity")))
        candidates.extend(sorted(root.glob("Unity/Editor/Unity")))
        candidates.extend(sorted(root.glob("Program*/Unity*/Editor/*/Editor/Unity")))
        return candidates

    candidates.extend(sorted(root.glob("*/Editor/Unity")))
    candidates.extend(sorted(root.glob("*/Unity")))
    return candidates


def discover_unity_installations() -> list[tuple[str, Path]]:
    discovered: list[tuple[str, Path]] = []
    seen: set[str] = set()

    for root in candidate_unity_editor_roots():
        for candidate in iter_candidate_installation_paths_from_root(root):
            normalized = normalize_unity_installation_path(candidate)
            if normalized is None:
                continue
            key = str(normalized).lower() if (os.name == "nt" or is_wsl()) else str(normalized)
            if key in seen:
                continue
            seen.add(key)
            version = resolve_unity_app_version(normalized)
            discovered.append((version, normalized))

    discovered.sort(key=lambda item: version_sort_key(item[0]))
    return discovered


def list_process_commands() -> list[tuple[int, str]]:
    return current_host_platform_adapter().list_process_commands()


def list_process_commands_report() -> dict[str, Any]:
    report = current_host_platform_adapter().list_process_commands_report()
    commands = report.get("commands") if isinstance(report, dict) else []
    normalized_commands: list[tuple[int, str]] = []
    for entry in commands or []:
        try:
            pid = int(entry[0])
            command = str(entry[1])
        except (IndexError, TypeError, ValueError):
            continue
        if pid > 0 and command:
            normalized_commands.append((pid, command))
    return {
        "available": bool(report.get("available")) if isinstance(report, dict) else False,
        "commands": normalized_commands,
        "error_code": str(report.get("error_code") or "") if isinstance(report, dict) else "process_listing_failed",
        "stderr": _truncate_host_process_text(report.get("stderr") if isinstance(report, dict) else ""),
        "platform_kind": str(report.get("platform_kind") or host_platform_kind()) if isinstance(report, dict) else host_platform_kind(),
    }


def process_visibility_summary() -> dict[str, Any]:
    report = list_process_commands_report()
    summary = {
        "process_visibility_available": bool(report.get("available")),
        "process_visibility_error_code": str(report.get("error_code") or ""),
        "process_visibility_stderr": _truncate_host_process_text(report.get("stderr") or ""),
        "process_visibility_platform_kind": str(report.get("platform_kind") or host_platform_kind()),
    }
    if is_wsl():
        diagnostics = wsl_host_diagnostics()
        summary["process_visibility_wslpath_available"] = bool(diagnostics.get("wslpath_available"))
        summary["process_visibility_warnings"] = list(diagnostics.get("warnings") or [])
    return summary


__all__ = [name for name in globals() if not name.startswith("__")]
