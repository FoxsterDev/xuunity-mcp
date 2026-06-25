#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

def bridge_root(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp"


def bridge_state_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "state" / "bridge_state.json"


def host_editor_session_state_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "state" / "host_editor_session.json"


def bridge_config_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "config" / "bridge_config.json"


def inbox_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "inbox"


def outbox_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "outbox"


def response_path(project_root: Path, request_id: str) -> Path:
    return outbox_dir(project_root) / f"{request_id}.json"


def test_result_path(project_root: Path, request_id: str) -> Path:
    return bridge_root(project_root) / "state" / "test_results" / f"{request_id}.json"


def logs_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "logs"


def captures_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "captures"


def scenarios_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "scenarios"


def scenario_results_dir(project_root: Path) -> Path:
    return scenarios_dir(project_root) / "results"


def active_scenario_run_path(project_root: Path) -> Path:
    return scenarios_dir(project_root) / "active_run.json"


def default_editor_log_path(project_root: Path) -> Path:
    return logs_dir(project_root) / "unity_editor.log"


def request_journal_dir(project_root: Path) -> Path:
    return bridge_root(project_root) / "journal" / "requests"
