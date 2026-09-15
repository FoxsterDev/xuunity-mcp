#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from server_bridge_constants import COMPILE_RED_FAIL_FAST_OPERATIONS
from server_core import ToolInvocationError, parse_utc_timestamp
from server_recovery_commands import recommended_recovery_command_for_project

COMPILE_GATED_PLAYMODE_ACTIONS = frozenset({"enter"})

COMPILER_DIAGNOSTICS_TRUST_STALE = "stale"
COMPILER_DIAGNOSTICS_TRUST_CONFIRMED = "confirmed"
COMPILER_DIAGNOSTICS_TRUST_DEFERRED_DURING_PLAYMODE = "deferred_during_playmode"
COMPILER_DIAGNOSTICS_TRUST_FLAG_ONLY = "flag_only_not_verdict"

PLAYMODE_STATES_WITH_DEFERRED_RELOAD = frozenset({"playing", "paused", "transitioning"})

FLAG_ONLY_DIAGNOSTICS_NOTE = (
    "script_compilation_failed is a flag, not a verdict; the authoritative verdict is "
    "unity_project_refresh post_settle_compile."
)
DEFERRED_DIAGNOSTICS_NOTE = (
    "diagnostics were captured before the script reload that Play Mode defers, so the disk may "
    "already differ; exit Play Mode and run unity_project_refresh for the authoritative "
    "post_settle_compile."
)


def compiler_diagnostics_trust_from_state(state: dict[str, Any] | None, project_root: Path | None = None) -> dict[str, Any]:
    effective = state or {}
    if not bool(effective.get("script_compilation_failed")) and int(effective.get("compiler_error_count") or 0) <= 0:
        return {}

    source = str(effective.get("compiler_diagnostics_source") or "")
    playmode_state = str(effective.get("playmode_state") or "")
    if source != "compilation_pipeline":
        return {
            "compiler_diagnostics_trust_class": COMPILER_DIAGNOSTICS_TRUST_FLAG_ONLY,
            "compiler_diagnostics_note": FLAG_ONLY_DIAGNOSTICS_NOTE,
        }
    if playmode_state in PLAYMODE_STATES_WITH_DEFERRED_RELOAD:
        return {
            "compiler_diagnostics_trust_class": COMPILER_DIAGNOSTICS_TRUST_DEFERRED_DURING_PLAYMODE,
            "compiler_diagnostics_note": DEFERRED_DIAGNOSTICS_NOTE,
        }
    captured = parse_utc_timestamp(str(effective.get("compiler_diagnostics_captured_utc") or ""))
    generation = int(effective.get("compiler_diagnostics_bridge_generation") or 0)
    stale_reason = ""
    if captured is None or generation <= 0:
        stale_reason = "diagnostics_capture_unknown"
    elif generation != int(effective.get("bridge_generation") or 0):
        stale_reason = "diagnostics_from_previous_generation"
    else:
        root = project_root or (Path(effective["project_root"]) if effective.get("project_root") else None)
        for diagnostic in effective.get("recent_compiler_diagnostics") or []:
            if not isinstance(diagnostic, dict) or not diagnostic.get("file"):
                continue
            path = Path(str(diagnostic["file"]).replace("\\", "/"))
            if not path.is_absolute():
                if root is None:
                    stale_reason = "diagnostic_file_unresolved"
                    break
                path = root / path
            try:
                if path.stat().st_mtime > captured:
                    stale_reason = "diagnostic_file_changed"
                    break
            except OSError:
                stale_reason = "diagnostic_file_unavailable"
                break
    if stale_reason:
        return {
            "compiler_diagnostics_trust_class": COMPILER_DIAGNOSTICS_TRUST_STALE,
            "compiler_diagnostics_note": "Cached diagnostics require one project refresh and a post-settle verdict.",
            "compiler_diagnostics_stale_reason": stale_reason,
        }
    return {"compiler_diagnostics_trust_class": COMPILER_DIAGNOSTICS_TRUST_CONFIRMED}


def compiler_diagnostics_from_state(state: dict[str, Any] | None, project_root: Path | None = None) -> dict[str, Any]:
    effective = state or {}
    diagnostics = effective.get("recent_compiler_diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
    result = {
        "script_compilation_failed": bool(effective.get("script_compilation_failed")),
        "compiler_error_count": max(0, int(effective.get("compiler_error_count") or 0)),
        "recent_compiler_diagnostics": diagnostics[:5],
        "compiler_diagnostics_source": str(effective.get("compiler_diagnostics_source") or ""),
    }
    result["compiler_diagnostics_captured_utc"] = str(effective.get("compiler_diagnostics_captured_utc") or "")
    result["compiler_diagnostics_bridge_generation"] = int(effective.get("compiler_diagnostics_bridge_generation") or 0)
    result.update(compiler_diagnostics_trust_from_state(effective, project_root))
    return result


def fail_if_compile_broken_for_operation(
    project_root: Path,
    operation: str,
    state: dict[str, Any] | None,
    arguments: dict[str, Any] | None = None,
) -> bool:
    """Return True when the caller must refresh stale evidence before dispatch."""
    if operation not in COMPILE_RED_FAIL_FAST_OPERATIONS:
        return False

    if operation == "unity.playmode.set":
        action = str((arguments or {}).get("action") or "").strip().lower()
        if action not in COMPILE_GATED_PLAYMODE_ACTIONS:
            return False

    diagnostics = compiler_diagnostics_from_state(state, project_root)
    if not diagnostics["script_compilation_failed"] and diagnostics["compiler_error_count"] <= 0:
        return False

    if diagnostics.get("compiler_diagnostics_trust_class") == COMPILER_DIAGNOSTICS_TRUST_STALE:
        return True

    raise ToolInvocationError(
        "compile_broken",
        f"Unity has compilation errors; refusing to start {operation} before they are fixed.",
        {
            "project_root": str(project_root),
            "operation": operation,
            **diagnostics,
            "recommended_next_action": "run_compile_gate_and_fix_errors",
            "recommended_recovery_command": recommended_recovery_command_for_project(project_root, "run_compile_gate_and_fix_errors"),
        },
    )
