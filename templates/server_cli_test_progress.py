from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from server_bridge_paths import bridge_root
from server_core import parse_utc_timestamp, read_json

CLI_TEST_PROGRESS_SCHEMA = "xuunity.cli_test_progress.v1"
CLI_TEST_PROGRESS_QUIET_SECONDS = 300.0


def cli_test_progress_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "state" / "cli_test_progress.json"


def read_cli_test_progress(project_root: Path, *, pid_is_alive: Callable[[int], bool]) -> dict[str, Any]:
    """Compact view of the sidecar a `-batchmode -runTests` process writes, so a CLI run is no longer invisible."""

    path = cli_test_progress_path(project_root)
    if not path.is_file():
        return {}
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
