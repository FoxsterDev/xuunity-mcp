#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from server_bridge_constants import COMPILE_RED_FAIL_FAST_OPERATIONS
from server_core import ToolInvocationError

def compiler_diagnostics_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    effective = state or {}
    diagnostics = effective.get("recent_compiler_diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
    return {
        "script_compilation_failed": bool(effective.get("script_compilation_failed")),
        "compiler_error_count": max(0, int(effective.get("compiler_error_count") or 0)),
        "recent_compiler_diagnostics": diagnostics[:5],
        "compiler_diagnostics_source": str(effective.get("compiler_diagnostics_source") or ""),
    }


def fail_if_compile_broken_for_operation(
    project_root: Path,
    operation: str,
    state: dict[str, Any] | None,
) -> None:
    if operation not in COMPILE_RED_FAIL_FAST_OPERATIONS:
        return

    diagnostics = compiler_diagnostics_from_state(state)
    if not diagnostics["script_compilation_failed"] and diagnostics["compiler_error_count"] <= 0:
        return

    raise ToolInvocationError(
        "compile_broken",
        f"Unity has compilation errors; refusing to start {operation} before they are fixed.",
        {
            "project_root": str(project_root),
            "operation": operation,
            **diagnostics,
            "recommended_next_action": "run_compile_gate_and_fix_errors",
        },
    )
