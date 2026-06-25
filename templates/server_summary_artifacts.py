from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from server_bridge_runtime import build_bridge_stabilization_summary


def truncate_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)] + "..."


def list_files_under(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def try_read_json_dict(path: Path, read_json: Callable[[Path], Any]) -> dict[str, Any] | None:
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def summarize_prune_group(
    *,
    name: str,
    paths: list[Path],
    keep_latest: int,
    max_age_hours: int,
    dry_run: bool,
    protected_paths: set[Path] | None = None,
) -> dict[str, Any]:
    protected_paths = protected_paths or set()
    now = time.time()
    cutoff = now - (max_age_hours * 3600.0)
    ranked_paths = sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)

    removed_files = 0
    removed_bytes = 0
    kept_files = 0

    for index, path in enumerate(ranked_paths):
        try:
            stat_result = path.stat()
        except OSError:
            continue

        resolved_path = path.resolve()
        if resolved_path in protected_paths:
            kept_files += 1
            continue

        if index < keep_latest or stat_result.st_mtime >= cutoff:
            kept_files += 1
            continue

        removed_files += 1
        removed_bytes += stat_result.st_size
        if dry_run:
            continue
        try:
            path.unlink()
        except OSError:
            kept_files += 1
            removed_files -= 1
            removed_bytes -= stat_result.st_size

    return {
        "name": name,
        "total_files": len(ranked_paths),
        "kept_files": kept_files,
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "keep_latest": keep_latest,
        "max_age_hours": max_age_hours,
        "dry_run": dry_run,
    }


def read_active_scenario_result_path(
    project_root: Path,
    *,
    active_scenario_run_path: Callable[[Path], Path],
    read_json: Callable[[Path], Any],
) -> Path | None:
    state_path = active_scenario_run_path(project_root)
    if not state_path.is_file():
        return None

    payload = try_read_json_dict(state_path, read_json) or {}
    result_path_value = str(payload.get("resultPath") or payload.get("result_path") or "")
    if not result_path_value:
        return None

    try:
        return Path(result_path_value).expanduser().resolve()
    except OSError:
        return None


def categorize_scenario_result(path: Path, read_json: Callable[[Path], Any]) -> str:
    payload = try_read_json_dict(path, read_json) or {}
    status = str(payload.get("status") or "")
    if status == "passed":
        return "success"
    if status == "failed":
        return "failure"
    return "running"


def prune_project_artifacts(
    project_root: Path,
    arguments: dict[str, Any],
    *,
    bridge_root: Callable[[Path], Path],
    request_journal_dir: Callable[[Path], Path],
    scenario_results_dir: Callable[[Path], Path],
    active_scenario_run_path: Callable[[Path], Path],
    captures_dir: Callable[[Path], Path],
    logs_dir: Callable[[Path], Path],
    default_editor_log_path: Callable[[Path], Path],
    read_json: Callable[[Path], Any],
) -> dict[str, Any]:
    dry_run = bool(arguments.get("dryRun", False))
    categories: list[dict[str, Any]] = []

    categories.append(
        summarize_prune_group(
            name="request_journal",
            paths=list_files_under(request_journal_dir(project_root)),
            keep_latest=max(0, int(arguments.get("requestJournalKeepLatest", 200))),
            max_age_hours=max(1, int(arguments.get("requestJournalMaxAgeHours", 72))),
            dry_run=dry_run,
        )
    )

    active_result_path = read_active_scenario_result_path(
        project_root,
        active_scenario_run_path=active_scenario_run_path,
        read_json=read_json,
    )
    protected_paths = {active_result_path} if active_result_path else set()
    scenario_groups = {
        "success": [],
        "failure": [],
        "running": [],
    }
    for path in list_files_under(scenario_results_dir(project_root)):
        category = categorize_scenario_result(path, read_json)
        scenario_groups.setdefault(category, []).append(path)

    categories.append(
        summarize_prune_group(
            name="scenario_results_success",
            paths=scenario_groups.get("success", []),
            keep_latest=max(0, int(arguments.get("scenarioKeepLatestSuccess", 20))),
            max_age_hours=max(1, int(arguments.get("scenarioSuccessMaxAgeHours", 168))),
            dry_run=dry_run,
            protected_paths=protected_paths,
        )
    )
    categories.append(
        summarize_prune_group(
            name="scenario_results_failure",
            paths=scenario_groups.get("failure", []),
            keep_latest=max(0, int(arguments.get("scenarioKeepLatestFailure", 50))),
            max_age_hours=max(1, int(arguments.get("scenarioFailureMaxAgeHours", 336))),
            dry_run=dry_run,
            protected_paths=protected_paths,
        )
    )
    categories.append(
        summarize_prune_group(
            name="scenario_results_running",
            paths=scenario_groups.get("running", []),
            keep_latest=max(0, int(arguments.get("scenarioKeepLatestRunning", 20))),
            max_age_hours=max(1, int(arguments.get("scenarioRunningMaxAgeHours", 168))),
            dry_run=dry_run,
            protected_paths=protected_paths,
        )
    )

    categories.append(
        summarize_prune_group(
            name="captures",
            paths=list_files_under(captures_dir(project_root)),
            keep_latest=max(0, int(arguments.get("capturesKeepLatest", 20))),
            max_age_hours=max(1, int(arguments.get("capturesMaxAgeHours", 168))),
            dry_run=dry_run,
        )
    )

    if bool(arguments.get("pruneLogs", False)):
        protected_log_paths = {default_editor_log_path(project_root).resolve()} if default_editor_log_path(project_root).exists() else set()
        categories.append(
            summarize_prune_group(
                name="logs",
                paths=list_files_under(logs_dir(project_root)),
                keep_latest=max(0, int(arguments.get("logsKeepLatest", 10))),
                max_age_hours=max(1, int(arguments.get("logsMaxAgeHours", 168))),
                dry_run=dry_run,
                protected_paths=protected_log_paths,
            )
        )

    removed_file_count = sum(int(category.get("removed_files") or 0) for category in categories)
    removed_bytes = sum(int(category.get("removed_bytes") or 0) for category in categories)
    kept_file_count = sum(int(category.get("kept_files") or 0) for category in categories)
    total_file_count = sum(int(category.get("total_files") or 0) for category in categories)

    return {
        "action": "unity_maintenance_prune",
        "project_root": str(project_root),
        "bridge_root": str(bridge_root(project_root)),
        "dry_run": dry_run,
        "active_scenario_result_protected": active_result_path is not None,
        "active_scenario_result_path": str(active_result_path) if active_result_path else "",
        "total_file_count": total_file_count,
        "kept_file_count": kept_file_count,
        "removed_file_count": removed_file_count,
        "removed_bytes": removed_bytes,
        "categories": categories,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
