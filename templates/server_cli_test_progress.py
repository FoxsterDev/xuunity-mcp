from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from server_bridge_paths import bridge_root
from server_core import parse_utc_timestamp, read_json

CLI_TEST_PROGRESS_SCHEMA = "xuunity.cli_test_progress.v1"
CLI_TEST_PROGRESS_QUIET_SECONDS = 300.0
TEST_FRAMEWORK_PACKAGE_NAME = "com.unity.test-framework"


def cli_test_progress_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "state" / "cli_test_progress.json"


def project_declares_test_framework(project_root: Path) -> bool:
    """True when the manifest or the resolved lock names the Test Framework; unreadable files count as present."""
    found_readable = False
    for name in ("manifest.json", "packages-lock.json"):
        try:
            data = read_json(project_root / "Packages" / name)
        except (OSError, ValueError):
            continue
        dependencies = data.get("dependencies") if isinstance(data, dict) else None
        if not isinstance(dependencies, dict):
            continue
        found_readable = True
        if dependencies.get(TEST_FRAMEWORK_PACKAGE_NAME):
            return True
    return not found_readable


def _default_process_commands() -> list[tuple[int, str]]:
    from server_editor_host_discovery import list_process_commands

    return list(list_process_commands())


def _run_tests_process_ids(project_root: Path, process_commands: Callable[[], list[tuple[int, str]]]) -> list[int]:
    from server_editor_host_processes import classify_unity_process_role, unity_command_targets_project

    pids: list[int] = []
    try:
        commands = process_commands()
    except Exception:
        return []
    for entry in commands:
        try:
            pid = int(entry[0])
            command = str(entry[1])
            is_run = "-runtests" in command.lower()
            matches = classify_unity_process_role(command) == "main_editor" and unity_command_targets_project(
                command, project_root
            )
        except (IndexError, TypeError, ValueError, SystemError):
            continue
        if pid > 0 and is_run and matches:
            pids.append(pid)
    return sorted(pids)


def _test_framework_missing_view(
    project_root: Path,
    *,
    pid_is_alive: Callable[[int], bool],
    process_commands: Callable[[], list[tuple[int, str]]] | None,
) -> dict[str, Any]:
    if project_declares_test_framework(project_root):
        return {}
    pids = [pid for pid in _run_tests_process_ids(project_root, process_commands or _default_process_commands) if pid_is_alive(pid)]
    if not pids:
        return {}
    return {
        "readable": False,
        "status": "test_framework_missing",
        "process_id": pids[0],
        "process_ids": pids,
        "process_alive": True,
        "summary": (
            f"A -runTests process is running, but {TEST_FRAMEWORK_PACKAGE_NAME} is in neither Packages/manifest.json "
            "nor packages-lock.json. Without the Test Framework the editor loads and waits; no test will start and "
            "no results file will be written."
        ),
        "recommended_next_action": "stop_the_run_then_install_test_framework",
        "recommended_recovery_tool": "unity_package_install_test_framework",
    }


def read_cli_test_progress(
    project_root: Path,
    *,
    pid_is_alive: Callable[[int], bool],
    process_commands: Callable[[], list[tuple[int, str]]] | None = None,
) -> dict[str, Any]:
    """Compact view of the sidecar a `-batchmode -runTests` process writes, so a CLI run is no longer invisible."""

    path = cli_test_progress_path(project_root)
    if not path.is_file():
        return _test_framework_missing_view(project_root, pid_is_alive=pid_is_alive, process_commands=process_commands)
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {"path": str(path), "readable": False}
    if not isinstance(data, dict) or str(data.get("schema") or "") != CLI_TEST_PROGRESS_SCHEMA:
        return {}

    process_id = int(data.get("process_id") or 0)
    process_alive = process_id > 0 and pid_is_alive(process_id)
    run_phase = str(data.get("run_phase") or "")
    progress_unix = parse_utc_timestamp(data.get("last_progress_at_utc"))
    progress_age = None if progress_unix is None else round(max(0.0, time.time() - progress_unix), 3)
    running = run_phase == "running"
    if running and not process_alive:
        status = "process_exited_before_completion"
    elif running and progress_age is not None and progress_age >= CLI_TEST_PROGRESS_QUIET_SECONDS:
        status = "running_without_progress"
    elif running:
        status = "running"
    else:
        status = run_phase or "unknown"
    return {
        "path": str(path),
        "readable": True,
        "status": status,
        "run_phase": run_phase,
        "test_platform": str(data.get("test_platform") or ""),
        "process_id": process_id,
        "process_alive": process_alive,
        "total": int(data.get("total") or 0),
        "finished": int(data.get("finished") or 0),
        "passed": int(data.get("passed") or 0),
        "failed": int(data.get("failed") or 0),
        "skipped": int(data.get("skipped") or 0),
        "last_started_test": str(data.get("last_started_test") or ""),
        "last_started_at_utc": str(data.get("last_started_at_utc") or ""),
        "last_finished_test": str(data.get("last_finished_test") or ""),
        "last_progress_at_utc": str(data.get("last_progress_at_utc") or ""),
        "last_progress_age_seconds": progress_age,
        "started_at_utc": str(data.get("started_at_utc") or ""),
        "completed_at_utc": str(data.get("completed_at_utc") or ""),
        "result_status": str(data.get("result_status") or ""),
        "domain_reload_count": int(data.get("domain_reload_count") or 0),
    }
