from __future__ import annotations

import sys
import calendar
import time
from pathlib import Path
from typing import Any, Callable

from server_core import render_launcher_cli


TRANSIENT_SCENARIO_POLL_ERROR_CODES = frozenset(
    {
        "transport_not_ready",
        "transport_response_missing",
        "request_lifecycle_reset",
        "response_missing_after_lifecycle_reset",
    }
)


def is_terminal_scenario_status(status: Any, scenario_terminal_statuses: set[str]) -> bool:
    return isinstance(status, str) and status in scenario_terminal_statuses


def parse_utc_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return None


def summarize_step_for_heartbeat(step: Any) -> str:
    if not isinstance(step, dict):
        return "-"
    step_id = str(step.get("stepId") or step.get("step_id") or "")
    kind = str(step.get("kind") or "")
    status = str(step.get("status") or "")
    label = step_id or kind or "-"
    return f"{label}:{status or '-'}"


def first_failed_step_label(steps: Any) -> str:
    if not isinstance(steps, list):
        return "-"
    for step in steps:
        if isinstance(step, dict) and str(step.get("status") or "") == "failed":
            return summarize_step_for_heartbeat(step)
    return "-"


def emit_scenario_wait_heartbeat(
    *,
    project_root: Path,
    payload: dict[str, Any],
    last_key: str,
    last_emit_unix: float,
    min_interval_seconds: float = 15.0,
) -> tuple[str, float]:
    steps = payload.get("steps")
    current_step_index = int(payload.get("current_step_index") or -1)
    active_step = None
    if isinstance(steps, list) and 0 <= current_step_index < len(steps):
        active_step = steps[current_step_index]
    waiting_until_utc = str(payload.get("waiting_until_utc") or "")
    wait_remaining_seconds = None
    wait_until_unix = parse_utc_seconds(waiting_until_utc)
    if wait_until_unix is not None:
        wait_remaining_seconds = round(max(0.0, wait_until_unix - time.time()), 1)
    key = "|".join(
        [
            str(payload.get("status") or ""),
            str(current_step_index),
            summarize_step_for_heartbeat(active_step),
            first_failed_step_label(steps),
            waiting_until_utc,
        ]
    )
    now = time.time()
    if key == last_key and now - last_emit_unix < min_interval_seconds:
        return last_key, last_emit_unix

    message = (
        "[xuunity-mcp] scenario_wait "
        f"scenario={payload.get('scenario_name') or ''} "
        f"run_id={payload.get('run_id') or ''} "
        f"status={payload.get('status') or ''} "
        f"active_step={summarize_step_for_heartbeat(active_step)} "
        f"first_failed_step={first_failed_step_label(steps)} "
        f"waiting_until_utc={waiting_until_utc or '-'} "
        f"remaining_seconds={wait_remaining_seconds if wait_remaining_seconds is not None else '-'} "
        f"project_root={project_root}"
    )
    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    return key, now


def wait_for_scenario_result_data(
    project_root: Path,
    run_id: str,
    scenario_name: str,
    timeout_ms: int,
    poll_interval_ms: int,
    *,
    scenario_recovery_error_codes: set[str] | frozenset[str],
    scenario_terminal_statuses: set[str],
    default_heartbeat_max_age_seconds: int,
    try_read_live_editor_state: Callable[[Path], dict[str, Any] | None],
    activate_unity_editor: Callable[[Path], Any],
    invoke_bridge: Callable[[str, str, dict[str, Any], int], dict[str, Any]],
    recover_project_bridge_for_reconciliation: Callable[..., dict[str, Any]],
    current_project_context_bridge_state: Callable[[Path], dict[str, Any]],
    enrich_tool_invocation_error_with_discovery: Callable[[Path, Any], Exception],
    bridge_response_to_tool_result: Callable[[dict[str, Any]], dict[str, Any]],
    normalize_scenario_payload: Callable[[dict[str, Any], set[str]], dict[str, Any]],
    apply_discovery_to_scenario_payload: Callable[[dict[str, Any], Path], dict[str, Any]],
    reconcile_persisted_scenario_result: Callable[[Path, str, str], dict[str, Any]],
    tool_invocation_error_type: type,
) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + (timeout_ms / 1000.0)
    effective_poll_interval = max(0.1, poll_interval_ms / 1000.0)
    last_payload: dict[str, Any] | None = None
    recovery_attempt_count = 0
    last_heartbeat_key = ""
    last_heartbeat_unix = 0.0

    while time.time() < deadline:
        live_state = try_read_live_editor_state(project_root)
        if isinstance(live_state, dict) and bool(live_state.get("playmode_transition_pending")):
            target_state = str(live_state.get("playmode_transition_target_state") or "")
            current_state = str(live_state.get("playmode_state") or "")
            if target_state in {"playing", "paused"} and current_state != target_state:
                try:
                    activate_unity_editor(project_root)
                except Exception:
                    pass

        remaining_ms = max(1000, min(5000, int((deadline - time.time()) * 1000)))
        bridge_args: dict[str, Any] = {}
        if run_id:
            bridge_args["runId"] = run_id
        if scenario_name:
            bridge_args["scenarioName"] = scenario_name

        try:
            response = invoke_bridge(str(project_root), "unity.scenario.result", bridge_args, remaining_ms)
        except Exception as exc:
            exc_code = str(getattr(exc, "code", "") or "")
            if exc_code in scenario_recovery_error_codes and time.time() + effective_poll_interval < deadline:
                recovery_attempt_count += 1
                try:
                    recover_project_bridge_for_reconciliation(
                        project_root,
                        timeout_ms=min(remaining_ms, 10000),
                        heartbeat_max_age_seconds=default_heartbeat_max_age_seconds,
                        startup_policy=str(
                            (current_project_context_bridge_state(project_root) or {}).get("startup_policy")
                            or "fail_fast_on_interactive_compile_block"
                        ),
                        allow_open_editor=True,
                    )
                except Exception as recovery_exc:
                    raise enrich_tool_invocation_error_with_discovery(project_root, recovery_exc)
                time.sleep(effective_poll_interval)
                continue
            if exc_code in TRANSIENT_SCENARIO_POLL_ERROR_CODES and time.time() + effective_poll_interval < deadline:
                time.sleep(effective_poll_interval)
                continue
            raise enrich_tool_invocation_error_with_discovery(project_root, exc)

        tool_result = bridge_response_to_tool_result(response)
        if tool_result.get("isError"):
            structured = tool_result.get("structuredContent") or {}
            error = structured.get("error") or {}
            raise tool_invocation_error_type(
                str(error.get("code") or "scenario_result_failed"),
                str(error.get("message") or "Scenario result polling failed."),
            )

        payload = tool_result.get("structuredContent") or {}
        if isinstance(payload, dict):
            payload = normalize_scenario_payload(payload, scenario_terminal_statuses)
        last_payload = payload

        if is_terminal_scenario_status(payload.get("status"), scenario_terminal_statuses):
            payload["waited_for_terminal_state"] = True
            payload["wait_duration_seconds"] = round(time.time() - started_at, 3)
            payload["recovery_attempt_count"] = recovery_attempt_count
            return apply_discovery_to_scenario_payload(payload, project_root)

        last_heartbeat_key, last_heartbeat_unix = emit_scenario_wait_heartbeat(
            project_root=project_root,
            payload=payload,
            last_key=last_heartbeat_key,
            last_emit_unix=last_heartbeat_unix,
        )

        time.sleep(effective_poll_interval)

    reconciliation = reconcile_persisted_scenario_result(project_root, run_id, scenario_name)
    if bool(reconciliation.get("terminal_result_found")):
        payload = dict(reconciliation.get("payload") or {})
        payload = normalize_scenario_payload(payload, scenario_terminal_statuses)
        payload["waited_for_terminal_state"] = True
        payload["wait_duration_seconds"] = round(time.time() - started_at, 3)
        payload["recovery_attempt_count"] = recovery_attempt_count
        payload["scenario_result_reconciled_from_persisted"] = True
        payload["scenario_result_reconciliation_reason"] = "terminal_persisted_result_after_poll_timeout"
        payload["scenario_result_lookup_strategy"] = str(reconciliation.get("lookup_strategy") or "")
        payload["scenario_result_matched_result_count"] = int(reconciliation.get("matched_result_count") or 0)
        payload["scenario_result_terminal_result_count"] = int(reconciliation.get("terminal_result_count") or 0)
        if payload.get("status") == "passed":
            payload.setdefault("recommended_next_action", "none")
        elif payload.get("status") == "failed":
            payload.setdefault("recommended_next_action", "inspect_persisted_scenario_failure")
        return apply_discovery_to_scenario_payload(payload, project_root)

    scenario_label = scenario_name or run_id or "unknown"
    suffix = ""
    if last_payload:
        suffix = f" Last observed status: {last_payload.get('status') or 'unknown'}."
    recovery_command = (
        render_launcher_cli("request-scenario-result-summary", project_root, "--run-id", str(run_id))
        if run_id
        else render_launcher_cli("request-scenario-result-latest", project_root, "--scenario-name", str(scenario_name))
    )
    raise enrich_tool_invocation_error_with_discovery(
        project_root,
        tool_invocation_error_type(
            "scenario_wait_timeout",
            f"Timed out waiting for scenario '{scenario_label}' to reach a terminal state.{suffix}",
            {
                "run_id": run_id,
                "scenario_name": scenario_name,
                "last_observed_status": str((last_payload or {}).get("status") or ""),
                "recovery_attempt_count": recovery_attempt_count,
                "persisted_scenario_result_lookup_found": bool(reconciliation.get("lookup_found")),
                "persisted_scenario_result_lookup_strategy": str(reconciliation.get("lookup_strategy") or ""),
                "persisted_scenario_result_terminal_found": False,
                "latest_persisted_scenario_status": str(reconciliation.get("status") or ""),
                "latest_persisted_scenario_result_path": str(reconciliation.get("result_path") or ""),
                "scenario_recovery_command": recovery_command,
            },
        ),
    )
