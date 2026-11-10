from __future__ import annotations

from pathlib import Path
from typing import Any

from server_bridge_paths import bridge_root
from server_core import read_json


def capability_report_path(project_root: Path) -> Path:
    return bridge_root(project_root) / "state" / "capabilities_report.json"


def capability_report_generation_view(report: dict[str, Any] | None, state: dict[str, Any] | None) -> dict[str, Any]:
    """Say whether a capability report was produced by an older domain than the bridge that is live now."""

    if not isinstance(report, dict) or "probe_bridge_generation" not in report:
        return {}
    probe_generation = int(report.get("probe_bridge_generation") or 0)
    bridge_generation = int((state or {}).get("bridge_generation") or 0)
    return {
        "capability_report_probe_bridge_generation": probe_generation,
        "capability_report_current_bridge_generation": bridge_generation,
        "capability_report_generation_behind": bridge_generation > 0 and 0 < probe_generation < bridge_generation,
    }


def read_capability_report_generation_view(project_root: Path, state: dict[str, Any] | None) -> dict[str, Any]:
    path = capability_report_path(project_root)
    if not path.is_file():
        return {}
    try:
        report = read_json(path)
    except (OSError, ValueError):
        return {}
    return capability_report_generation_view(report if isinstance(report, dict) else None, state)
