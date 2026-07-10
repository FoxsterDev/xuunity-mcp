from __future__ import annotations

import json
from typing import Any, Callable


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _attach_post_settle_compile_truth(
    normalized: dict[str, Any],
    idle_wait_after: dict[str, Any],
    *,
    settle_phase: str,
    completion_basis: str,
) -> None:
    diagnostics = idle_wait_after.get("recent_compiler_diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
    post_settle_error_count = _int_or_zero(idle_wait_after.get("compiler_error_count"))
    script_compilation_failed = bool(idle_wait_after.get("script_compilation_failed"))
    post_settle_failed = script_compilation_failed or post_settle_error_count > 0
    compiling_or_updating = bool(idle_wait_after.get("is_compiling")) or bool(idle_wait_after.get("is_updating"))
    if compiling_or_updating:
        post_settle_compile = "inconclusive"
    elif post_settle_failed:
        post_settle_compile = "failed"
    else:
        post_settle_compile = "passed"

    normalized["authoritative_state_source"] = "idle_wait_after"
    normalized["post_settle_compile"] = post_settle_compile
    normalized["post_settle_error_count"] = post_settle_error_count
    normalized["post_settle_diagnostics"] = diagnostics[:5]
    normalized["post_settle_compiler_diagnostics_source"] = str(idle_wait_after.get("compiler_diagnostics_source") or "")
    normalized["post_settle_script_compilation_failed"] = script_compilation_failed
    normalized["script_compilation_failed"] = script_compilation_failed
    normalized["compiler_error_count"] = post_settle_error_count
    normalized["recent_compiler_diagnostics"] = diagnostics[:5]
    normalized["compiler_diagnostics_source"] = str(idle_wait_after.get("compiler_diagnostics_source") or "")
    normalized["settle_phase"] = settle_phase or str(normalized.get("settle_phase") or "")
    normalized["completion_basis"] = completion_basis or str(normalized.get("completion_basis") or "")


def _editor_relaunch_attribution_from_recovery(recovery: Any) -> dict[str, Any]:
    if not isinstance(recovery, dict):
        return {}
    if bool(recovery.get("editor_relaunched")):
        return {
            "editor_relaunched": True,
            "previous_editor_pid": _int_or_zero(recovery.get("previous_editor_pid")),
            "current_editor_pid": _int_or_zero(recovery.get("current_editor_pid")),
            "bridge_generation_before": _int_or_zero(recovery.get("bridge_generation_before")),
            "bridge_generation_after": _int_or_zero(recovery.get("bridge_generation_after")),
            "cold_start_reason": str(recovery.get("cold_start_reason") or ""),
        }

    nested = recovery.get("host_health_recovery")
    if isinstance(nested, dict):
        return _editor_relaunch_attribution_from_recovery(nested)
    return {}


def _editor_relaunch_attribution_from_lifecycle(lifecycle: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "activation",
        "lifecycle_reset_recovery",
        "transport_response_missing_recovery",
        "transport_connect_failed_recovery",
    ):
        attribution = _editor_relaunch_attribution_from_recovery(lifecycle.get(key))
        if attribution:
            return attribution
    return {}


def _attach_editor_relaunch_attribution(normalized: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    attribution = _editor_relaunch_attribution_from_lifecycle(lifecycle)
    if attribution:
        normalized.update(attribution)


def _attach_post_settle_playmode_accounting(
    normalized: dict[str, Any],
    idle_wait_after: dict[str, Any],
    lifecycle: dict[str, Any],
) -> None:
    normalized["playmode_state_after_settle"] = str(idle_wait_after.get("playmode_state") or "")
    normalized["playmode_state_after_settle_source"] = "idle_wait_after"

    transition = lifecycle.get("bridge_identity_transition")
    if isinstance(transition, dict) and transition:
        normalized["playmode_state_after_settle_trust_class"] = "stale_risk"
        normalized["playmode_state_after_settle_note"] = (
            "bridge identity changed during post-request settle; confirm current Play Mode via unity_playmode_state"
        )
        normalized["playmode_state_after_settle_recommended_next_action"] = "confirm_via_unity_playmode_state"
        return

    normalized["playmode_state_after_settle_trust_class"] = "confirmed"


def normalize_refresh_payload_from_lifecycle(payload: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    requested_outcome = str(normalized.get("outcome") or "")
    idle_wait_after = lifecycle.get("idle_wait_after")
    if not isinstance(idle_wait_after, dict):
        return normalized

    settled_at_utc = str(idle_wait_after.get("heartbeat_utc") or "")
    normalized["requested_outcome"] = requested_outcome
    normalized["outcome"] = (
        "refresh_and_resolve_completed"
        if bool(normalized.get("package_resolve_requested"))
        else "refresh_completed"
    )
    normalized["settled_at_utc"] = settled_at_utc
    if (
        str(idle_wait_after.get("refresh_settle_phase") or "") == "settled"
        and str(idle_wait_after.get("refresh_settle_request_id") or "") == str(normalized.get("settle_request_id") or "")
    ):
        normalized["completion_basis"] = "unity_refresh_settle_watcher"
        normalized["settled_at_utc"] = str(idle_wait_after.get("refresh_settle_completed_utc") or settled_at_utc)
        normalized["settle_phase"] = "settled"
        normalized["settle_request_id"] = str(idle_wait_after.get("refresh_settle_request_id") or normalized.get("settle_request_id") or "")
    else:
        normalized["completion_basis"] = "host_waited_for_editor_idle"
        normalized["settle_phase"] = str(idle_wait_after.get("refresh_settle_phase") or "editor_idle_observed")
    normalized["editor_is_compiling_after_settle"] = bool(idle_wait_after.get("is_compiling"))
    normalized["editor_is_updating_after_settle"] = bool(idle_wait_after.get("is_updating"))
    _attach_post_settle_playmode_accounting(normalized, idle_wait_after, lifecycle)
    _attach_post_settle_compile_truth(
        normalized,
        idle_wait_after,
        settle_phase=str(normalized.get("settle_phase") or ""),
        completion_basis=str(normalized.get("completion_basis") or ""),
    )
    return normalized


def normalize_compile_payload_from_lifecycle(payload: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    idle_wait_after = lifecycle.get("idle_wait_after")
    if not isinstance(idle_wait_after, dict):
        return normalized

    settled_at_utc = str(idle_wait_after.get("heartbeat_utc") or "")
    request_id = str(normalized.get("settle_request_id") or "")
    if (
        str(idle_wait_after.get("compile_settle_phase") or "") == "settled"
        and str(idle_wait_after.get("compile_settle_request_id") or "") == request_id
    ):
        normalized["completion_basis"] = "unity_compile_settle_watcher"
        normalized["settled_at_utc"] = str(idle_wait_after.get("compile_settle_completed_utc") or settled_at_utc)
        normalized["settle_phase"] = "settled"
        normalized["settle_request_id"] = str(idle_wait_after.get("compile_settle_request_id") or request_id)
    else:
        normalized["completion_basis"] = "host_waited_for_editor_idle"
        normalized["settled_at_utc"] = settled_at_utc
        normalized["settle_phase"] = str(idle_wait_after.get("compile_settle_phase") or "editor_idle_observed")

    normalized["editor_is_compiling_after_settle"] = bool(idle_wait_after.get("is_compiling"))
    normalized["editor_is_updating_after_settle"] = bool(idle_wait_after.get("is_updating"))
    normalized["playmode_state_after_settle"] = str(idle_wait_after.get("playmode_state") or "")
    _attach_post_settle_compile_truth(
        normalized,
        idle_wait_after,
        settle_phase=str(normalized.get("settle_phase") or ""),
        completion_basis=str(normalized.get("completion_basis") or ""),
    )
    return normalized


def normalize_playmode_payload_from_lifecycle(payload: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    settled_state = lifecycle.get("playmode_wait_after")
    if not isinstance(settled_state, dict):
        return normalized

    settled_at_utc = str(settled_state.get("heartbeat_utc") or "")
    request_id = str(normalized.get("settle_request_id") or "")
    if (
        str(settled_state.get("playmode_transition_phase") or "") == "settled"
        and str(settled_state.get("playmode_transition_request_id") or "") == request_id
    ):
        normalized["completion_basis"] = "unity_playmode_transition_watcher"
        normalized["settled_at_utc"] = str(settled_state.get("playmode_transition_completed_utc") or settled_at_utc)
        normalized["settle_phase"] = "settled"
    else:
        normalized["completion_basis"] = "host_waited_for_playmode_state"
        normalized["settled_at_utc"] = settled_at_utc

    normalized["settle_target_state"] = str(
        settled_state.get("playmode_transition_target_state")
        or normalized.get("settle_target_state")
        or settled_state.get("playmode_state")
        or ""
    )
    normalized["settle_request_id"] = str(
        settled_state.get("playmode_transition_request_id")
        or request_id
    )
    normalized["is_playing"] = bool(settled_state.get("is_playing"))
    normalized["is_paused"] = bool(settled_state.get("is_paused"))
    normalized["is_playing_or_will_change_playmode"] = bool(settled_state.get("is_playing_or_will_change_playmode"))
    normalized["playmode_state"] = str(settled_state.get("playmode_state") or normalized.get("playmode_state") or "")
    return normalized


def normalize_build_target_payload_from_lifecycle(payload: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    idle_wait_after = lifecycle.get("idle_wait_after")
    if not isinstance(idle_wait_after, dict):
        return normalized

    normalized["completion_basis"] = "host_waited_for_editor_idle"
    normalized["settled_at_utc"] = str(idle_wait_after.get("heartbeat_utc") or normalized.get("settled_at_utc") or "")
    normalized["editor_is_compiling_after_settle"] = bool(idle_wait_after.get("is_compiling"))
    normalized["editor_is_updating_after_settle"] = bool(idle_wait_after.get("is_updating"))
    normalized["playmode_state_after_settle"] = str(idle_wait_after.get("playmode_state") or "")
    return normalized


def normalize_tests_payload_from_lifecycle(payload: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    idle_wait_after = lifecycle.get("idle_wait_after")
    if not isinstance(idle_wait_after, dict):
        return normalized

    normalized["playmode_state_after_settle"] = str(
        idle_wait_after.get("playmode_state")
        or normalized.get("playmode_state_after_settle")
        or ""
    )
    _attach_post_settle_compile_truth(
        normalized,
        idle_wait_after,
        settle_phase=str(idle_wait_after.get("compile_settle_phase") or "editor_idle_observed"),
        completion_basis=str(normalized.get("completion_basis") or "host_waited_for_editor_idle"),
    )
    return normalized


def normalize_response_payload_from_lifecycle(
    response: dict[str, Any],
    lifecycle: dict[str, Any],
    *,
    normalize_scenario_payload: Callable[[dict[str, Any], set[str]], dict[str, Any]],
    scenario_terminal_statuses: set[str],
) -> dict[str, Any]:
    if response.get("status") != "ok":
        return response

    settled_state = lifecycle.get("playmode_wait_after")
    payload_json = response.get("payload_json")
    if not isinstance(payload_json, str) or not payload_json:
        return response

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return response

    operation = str(lifecycle.get("operation") or "")
    payload_type = str(response.get("payload_type") or "")

    if operation == "unity.playmode.set" and isinstance(settled_state, dict):
        payload = normalize_playmode_payload_from_lifecycle(payload, lifecycle)
    elif operation == "unity.project.refresh":
        payload = normalize_refresh_payload_from_lifecycle(payload, lifecycle)
    elif operation in {"unity.compile.player_scripts", "unity.compile.matrix"}:
        payload = normalize_compile_payload_from_lifecycle(payload, lifecycle)
    elif operation == "unity.build_target.switch":
        payload = normalize_build_target_payload_from_lifecycle(payload, lifecycle)
    elif operation in {"unity.tests.run_playmode", "unity.tests.run_editmode"}:
        payload = normalize_tests_payload_from_lifecycle(payload, lifecycle)

    if payload_type in {"unity.scenario.run", "unity.scenario.result"}:
        payload = normalize_scenario_payload(payload, scenario_terminal_statuses)

    _attach_editor_relaunch_attribution(payload, lifecycle)

    normalized = dict(response)
    normalized["payload_json"] = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return normalized


COMPACT_OPERATION_PAYLOADS = {
    "unity.project.refresh",
    "unity.compile.player_scripts",
    "unity.compile.matrix",
    "unity.tests.run_editmode",
    "unity.tests.run_playmode",
}


def _copy_if_present(target: dict[str, Any], source: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in source:
            target[key] = source.get(key)


def _artifact_ref(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("artifact_manifest")
    if not isinstance(manifest, dict):
        return {}

    ref: dict[str, Any] = {}
    base_dir = manifest.get("base_dir") or manifest.get("artifact_dir")
    if base_dir:
        ref["artifact_dir"] = str(base_dir)

    groups = manifest.get("groups")
    if isinstance(groups, dict):
        total = 0
        for value in groups.values():
            if isinstance(value, list):
                total += len(value)
        ref["artifact_count"] = total
    return ref


def _compact_post_settle_fields(payload: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    _copy_if_present(
        compact,
        payload,
        (
            "authoritative_state_source",
            "post_settle_compile",
            "post_settle_error_count",
            "post_settle_script_compilation_failed",
            "post_settle_compiler_diagnostics_source",
            "settle_phase",
            "completion_basis",
            "settled_at_utc",
            "editor_is_compiling_after_settle",
            "editor_is_updating_after_settle",
            "playmode_state_after_settle",
            "playmode_state_after_settle_source",
            "playmode_state_after_settle_trust_class",
            "playmode_state_after_settle_note",
            "playmode_state_after_settle_recommended_next_action",
        ),
    )
    diagnostics = payload.get("post_settle_diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        compact["post_settle_diagnostics"] = diagnostics[:3]
    return compact


def _compact_compile_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "name",
            "target",
            "status",
            "outcome",
            "error_count",
            "warning_count",
            "compiled_assembly_count",
            "duration_seconds",
            "total",
            "passed",
            "failed",
            "skipped",
            "stop_on_first_failure",
            "settle_request_id",
        ),
    )
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        compact["errors"] = errors[:3]
    configurations = payload.get("configurations")
    if isinstance(configurations, list):
        compact["configuration_count"] = len(configurations)
        failed_rows = [
            item for item in configurations
            if isinstance(item, dict) and str(item.get("status") or "") not in {"", "passed", "ok"}
        ]
        if failed_rows:
            compact["first_failed_configurations"] = failed_rows[:3]
    compact.update(_compact_post_settle_fields(payload))
    compact.update(_artifact_ref(payload))
    return compact


def _compact_refresh_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "status",
            "outcome",
            "requested_outcome",
            "package_resolve_requested",
            "health_probe_requested",
            "asset_refresh_requested",
            "settle_request_id",
        ),
    )
    compact.update(_compact_post_settle_fields(payload))
    compact.update(_artifact_ref(payload))
    return compact


def _compact_tests_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "status",
            "outcome",
            "test_mode",
            "run_phase",
            "test_verdict",
            "total",
            "passed",
            "failed",
            "skipped",
            "duration_seconds",
            "result_path",
            "settle_request_id",
        ),
    )
    failures = payload.get("failures") or payload.get("first_failures")
    if isinstance(failures, list) and failures:
        compact["first_failures"] = failures[:3]
    compact.update(_compact_post_settle_fields(payload))
    compact.update(_artifact_ref(payload))
    return compact


def compact_operation_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    if operation in {"unity.compile.player_scripts", "unity.compile.matrix"}:
        return _compact_compile_payload(payload, operation)
    if operation == "unity.project.refresh":
        return _compact_refresh_payload(payload, operation)
    if operation in {"unity.tests.run_editmode", "unity.tests.run_playmode"}:
        return _compact_tests_payload(payload, operation)
    return payload


def bridge_response_to_tool_result(
    response: dict[str, Any],
    *,
    normalize_scenario_payload: Callable[[dict[str, Any], set[str]], dict[str, Any]],
    scenario_terminal_statuses: set[str],
    include_full_payload: bool = True,
) -> dict[str, Any]:
    if response.get("status") == "ok":
        payload = {}
        payload_json = response.get("payload_json") or "{}"
        payload_type = str(response.get("payload_type") or "")
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {"raw_payload_json": payload_json}

        lifecycle = response.get("_xuunity_lifecycle")
        operation = ""
        if isinstance(lifecycle, dict) and lifecycle:
            operation = str(lifecycle.get("operation") or "")
            payload["_xuunity_lifecycle"] = lifecycle
        elif payload_type in {"unity.scenario.run", "unity.scenario.result"} and isinstance(payload, dict):
            payload = normalize_scenario_payload(payload, scenario_terminal_statuses)

        if (
            not include_full_payload
            and isinstance(payload, dict)
            and operation in COMPACT_OPERATION_PAYLOADS
        ):
            payload = compact_operation_payload(payload, operation)
            payload["full_payload_available"] = True
            payload["full_payload_tool_arguments"] = {"includeFullPayload": True}

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=True)
                }
            ],
            "structuredContent": payload,
            "isError": False
        }

    error = response.get("error") or {}
    message = error.get("message") or "Unknown bridge error."
    code = error.get("code") or "unknown_bridge_error"
    structured = {
        "error": {
            "code": code,
            "message": message
        }
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(structured, ensure_ascii=True)
            }
        ],
        "structuredContent": structured,
        "isError": True
    }


def scenario_failure_tool_result(result_payload: dict[str, Any]) -> dict[str, Any]:
    scenario_name = str(result_payload.get("scenario_name") or "unknown_scenario")
    status = str(result_payload.get("status") or result_payload.get("terminal_status") or "failed")
    structured = {
        "error": {
            "code": "scenario_failed",
            "message": f"Scenario '{scenario_name}' finished with status '{status}'.",
        },
        "scenario": result_payload,
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(structured, ensure_ascii=True)
            }
        ],
        "structuredContent": structured,
        "isError": True,
    }


def _decode_bridge_payload_dict(response: dict[str, Any]) -> dict[str, Any] | None:
    payload_json = response.get("payload_json")
    if not isinstance(payload_json, str) or not payload_json:
        return None

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _bridge_error_code(response: dict[str, Any]) -> str:
    error = response.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "")
        if code:
            return code

    payload = _decode_bridge_payload_dict(response)
    if not isinstance(payload, dict):
        return ""

    payload_error = payload.get("error")
    if not isinstance(payload_error, dict):
        return ""
    return str(payload_error.get("code") or "")
