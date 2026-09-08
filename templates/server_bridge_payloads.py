from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from server_bridge_constants import COMPILE_WARNING_SAMPLE_LIMIT
from server_health import read_editor_log_scope


POST_SETTLE_COMPILE_TRUST_CONFIRMED = "confirmed"
POST_SETTLE_COMPILE_TRUST_EDITOR_STILL_BUSY = "editor_still_busy"
POST_SETTLE_COMPILE_TRUST_DEFERRED_DURING_PLAYMODE = "deferred_during_playmode"
PLAYING_PLAYMODE_STATES = {"playing", "paused", "transitioning"}
STRUCTURAL_COMPILER_LOG_MAX_CHARS = 2_000_000
STRUCTURAL_COMPILER_DIAGNOSTIC_SOURCE = "editor_log_bridge_generation_scope"


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _editor_was_playing(idle_wait_after: dict[str, Any]) -> bool:
    if bool(idle_wait_after.get("is_playing")) or bool(idle_wait_after.get("is_playing_or_will_change_playmode")):
        return True
    return str(idle_wait_after.get("playmode_state") or "") in PLAYING_PLAYMODE_STATES


def _attach_post_settle_compile_truth(
    normalized: dict[str, Any],
    idle_wait_after: dict[str, Any],
    *,
    settle_phase: str,
    completion_basis: str,
    playmode_defers_asset_import: bool = False,
) -> None:
    diagnostics = idle_wait_after.get("recent_compiler_diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []

    script_compilation_failed = bool(idle_wait_after.get("script_compilation_failed"))
    structural_diagnostics: list[dict[str, Any]] = []
    structural_scope: dict[str, Any] = {}
    if script_compilation_failed:
        structural_diagnostics, structural_scope = _extract_structural_compiler_diagnostics(
            str(idle_wait_after.get("editor_log_path") or ""),
            bridge_generation_start_offset=_int_or_zero(
                idle_wait_after.get("editor_log_offset_at_bridge_generation_start")
            ),
            bridge_generation=_int_or_zero(idle_wait_after.get("editor_log_offset_bridge_generation")),
        )

    diagnostics = _merge_compiler_diagnostics(structural_diagnostics, diagnostics)
    compiler_diagnostics_source = str(idle_wait_after.get("compiler_diagnostics_source") or "")
    if structural_diagnostics:
        compiler_diagnostics_source = "+".join(
            source
            for source in (STRUCTURAL_COMPILER_DIAGNOSTIC_SOURCE, compiler_diagnostics_source)
            if source
        )
    elif script_compilation_failed and not diagnostics:
        diagnostics = [_compiler_diagnostics_unavailable_row()]
        compiler_diagnostics_source = compiler_diagnostics_source or "script_compilation_failed_flag"

    post_settle_error_count = max(
        _int_or_zero(idle_wait_after.get("compiler_error_count")),
        len(structural_diagnostics),
    )
    post_settle_failed = script_compilation_failed or post_settle_error_count > 0
    compiling_or_updating = bool(idle_wait_after.get("is_compiling")) or bool(idle_wait_after.get("is_updating"))
    if compiling_or_updating:
        post_settle_compile = "inconclusive"
    elif post_settle_failed:
        post_settle_compile = "failed"
    else:
        post_settle_compile = "passed"

    if compiling_or_updating:
        trust_class = POST_SETTLE_COMPILE_TRUST_EDITOR_STILL_BUSY
    elif playmode_defers_asset_import and _editor_was_playing(idle_wait_after):
        trust_class = POST_SETTLE_COMPILE_TRUST_DEFERRED_DURING_PLAYMODE
    else:
        trust_class = POST_SETTLE_COMPILE_TRUST_CONFIRMED

    normalized["post_settle_compile_trust_class"] = trust_class
    if trust_class == POST_SETTLE_COMPILE_TRUST_DEFERRED_DURING_PLAYMODE:
        normalized["post_settle_compile_note"] = (
            "the editor was in Play Mode at settle, so asset import and script compilation are deferred; "
            "this compile verdict is not authoritative"
        )
        normalized["post_settle_compile_recommended_next_action"] = "exit_play_mode_then_rerun_refresh"
    elif trust_class == POST_SETTLE_COMPILE_TRUST_EDITOR_STILL_BUSY:
        normalized["post_settle_compile_note"] = (
            "the editor was still compiling or importing at settle, so this compile verdict is not final"
        )
        normalized["post_settle_compile_recommended_next_action"] = "wait_for_editor_idle_then_recheck"

    normalized["authoritative_state_source"] = "idle_wait_after"
    normalized["post_settle_compile"] = post_settle_compile
    normalized["post_settle_error_count"] = post_settle_error_count
    normalized["post_settle_diagnostics"] = diagnostics[:5]
    normalized["post_settle_compiler_diagnostics_source"] = compiler_diagnostics_source
    normalized["post_settle_script_compilation_failed"] = script_compilation_failed
    normalized["post_settle_structural_diagnostic_count"] = len(structural_diagnostics)
    if structural_scope:
        normalized["post_settle_structural_diagnostics_scope"] = structural_scope
    if structural_diagnostics:
        normalized["post_settle_compile_failure_class"] = "assembly_definition_error"
        normalized["post_settle_compile_recommended_next_action"] = (
            "inspect_asmdef_references_and_editor_log_before_cache_cleanup"
        )
    elif (
        script_compilation_failed
        and diagnostics
        and isinstance(diagnostics[0], dict)
        and diagnostics[0].get("type") == "DiagnosticUnavailable"
    ):
        normalized["post_settle_compile_failure_class"] = "compiler_diagnostics_unavailable"
        normalized["post_settle_compile_recommended_next_action"] = (
            "inspect_session_scoped_editor_log_before_cache_cleanup"
        )
    normalized["script_compilation_failed"] = script_compilation_failed
    normalized["compiler_error_count"] = post_settle_error_count
    normalized["recent_compiler_diagnostics"] = diagnostics[:5]
    normalized["compiler_diagnostics_source"] = compiler_diagnostics_source
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


def _structural_compile_failure_class(line: str) -> str:
    lowered = line.lower()
    if "assembly has duplicate references" in lowered:
        return "asmdef_duplicate_reference"
    if "unable to resolve reference" in lowered:
        return "asmdef_unresolved_reference"
    if "error parsing json" in lowered and ".asmdef" in lowered:
        return "asmdef_json_parse_error"
    if "will not be compiled because" in lowered and "exists outside the assets folder" not in lowered:
        return "assembly_not_compiled"
    return ""


def _extract_structural_compiler_diagnostics(
    log_path: str,
    *,
    bridge_generation_start_offset: int,
    bridge_generation: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scope: dict[str, Any] = {
        "anchor": "bridge_generation",
        "bridge_generation": bridge_generation,
        "start_offset_bytes": bridge_generation_start_offset,
    }
    if not log_path:
        scope.update({"trust_class": "unavailable", "reason": "editor_log_path_unavailable"})
        return [], scope
    if bridge_generation_start_offset <= 0:
        scope.update({"trust_class": "unavailable", "reason": "bridge_generation_anchor_unavailable"})
        return [], scope

    text, read_scope = read_editor_log_scope(
        Path(log_path),
        session_start_offset_bytes=bridge_generation_start_offset,
        max_chars=STRUCTURAL_COMPILER_LOG_MAX_CHARS,
    )
    scope.update(
        {
            key: value
            for key, value in read_scope.items()
            if key
            in {
                "scoped_bytes_available",
                "truncated_to_max_chars",
                "scope_unusable",
                "missing",
                "stat_failed",
            }
        }
    )
    if read_scope.get("fallback_used"):
        scope.update({"trust_class": "unscoped_refused", "reason": "bridge_generation_anchor_unusable"})
        return [], scope

    scope["trust_class"] = "session_scoped"
    findings: list[dict[str, Any]] = []
    seen_messages: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        failure_class = _structural_compile_failure_class(line)
        message_key = line.casefold()
        if not failure_class or message_key in seen_messages:
            continue
        seen_messages.add(message_key)
        findings.append(
            {
                "message": line,
                "file": "Editor.log",
                "line": 0,
                "type": "StructuralCompilationError",
                "severity": "Error",
                "failure_class": failure_class,
                "evidence_source": STRUCTURAL_COMPILER_DIAGNOSTIC_SOURCE,
            }
        )
    return findings[-5:], scope


def _merge_compiler_diagnostics(
    structural_diagnostics: list[dict[str, Any]],
    compiler_diagnostics: list[Any],
) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for diagnostic in [*structural_diagnostics, *compiler_diagnostics]:
        if isinstance(diagnostic, dict):
            key = str(
                diagnostic.get("message") or json.dumps(diagnostic, sort_keys=True, default=str)
            ).strip().casefold()
        else:
            key = str(diagnostic).strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(diagnostic)
    return merged


def _compiler_diagnostics_unavailable_row() -> dict[str, Any]:
    return {
        "message": (
            "Unity reports script compilation failed, but no current-session compiler diagnostic was available. "
            "Inspect Editor.log from the bridge-generation anchor before considering cache cleanup."
        ),
        "file": "Editor.log",
        "line": 0,
        "type": "DiagnosticUnavailable",
        "severity": "Warning",
    }


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
        playmode_defers_asset_import=True,
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
    for key in (
        "playmode_frame_count",
        "playmode_frames_advanced_last_interval",
        "playmode_frame_sample_interval_seconds",
        "editor_application_focused",
        "playmode_loop_liveness",
        "playmode_liveness_warning",
        "playmode_liveness_remediation",
    ):
        if key in settled_state:
            normalized[key] = settled_state.get(key)
    liveness = str(normalized.get("playmode_loop_liveness") or "")
    normalized["result_trust_class"] = (
        "playmode_throttled"
        if liveness == "throttled"
        else "playmode_advancing_confirmed"
        if liveness == "advancing"
        else "playmode_liveness_unproven"
        if str(normalized.get("playmode_state") or "") == "playing"
        else "editor_truth_confirmed"
    )
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

    callback_state = str(
        normalized.get("playmode_state_after_test_callbacks")
        or normalized.get("playmode_state_after_settle")
        or ""
    )
    host_settle_state = str(idle_wait_after.get("playmode_state") or "")
    if callback_state:
        normalized["playmode_state_after_test_callbacks"] = callback_state
    if not normalized.get("playmode_state_after_settle_source") and callback_state:
        normalized["playmode_state_after_settle_source"] = "unity_test_callbacks"

    if host_settle_state:
        normalized["playmode_state_after_host_settle"] = host_settle_state
        normalized["playmode_state_after_settle"] = host_settle_state
        normalized["playmode_state_after_settle_source"] = "idle_wait_after"
        accounting_consistent = not callback_state or callback_state == host_settle_state
        normalized["playmode_state_accounting_consistent"] = accounting_consistent
        if accounting_consistent:
            normalized.pop("playmode_state_accounting_note", None)
        else:
            normalized["playmode_state_accounting_note"] = (
                "Unity Test Runner callbacks reported "
                f"{callback_state!r}; the host observed {host_settle_state!r} after editor idle. "
                "playmode_state_after_settle uses the host-settled value."
            )

        transition = lifecycle.get("bridge_identity_transition")
        if isinstance(transition, dict) and transition:
            normalized["lifecycle_churn_observed"] = True
            normalized["playmode_state_after_settle_trust_class"] = "stale_risk"
            normalized["playmode_state_after_settle_note"] = (
                "bridge identity changed during post-test settle; confirm current Play Mode via unity_playmode_state"
            )
            normalized["playmode_state_after_settle_recommended_next_action"] = "confirm_via_unity_playmode_state"
        else:
            normalized["playmode_state_after_settle_trust_class"] = "confirmed"

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


EDITOR_OPEN_ATTRIBUTION_FIELDS = (
    "editor_opened_by_this_call",
    "editor_open_started_utc",
    "editor_open_completed_utc",
    "editor_open_duration_seconds",
    "editor_open_note",
)


def hoist_editor_open_attribution(lifecycle: dict[str, Any]) -> dict[str, Any]:
    """Lift "this call opened a Unity editor" out of the activation block into the payload.

    A mutating operation may launch Unity as a side effect. That fact used to live only inside
    `_xuunity_lifecycle.activation`, so a caller reading the payload -- or a compact envelope -- saw no sign of it
    and went on reporting the editor as not running.
    """

    activation = lifecycle.get("activation")
    if not isinstance(activation, dict) or not activation.get("editor_opened_by_this_call"):
        return {}
    return {field: activation[field] for field in EDITOR_OPEN_ATTRIBUTION_FIELDS if field in activation}


COMPACT_OPERATION_PAYLOADS = {
    "unity.project.refresh",
    "unity.project_action.currency",
    "unity.compile.player_scripts",
    "unity.compile.matrix",
    "unity.tests.run_editmode",
    "unity.tests.run_playmode",
    "unity.playmode.state",
    "unity.playmode.set",
    "unity.game_view.screenshot",
    "unity.scene.open",
    "unity.scene.snapshot",
    "unity.game_view.configure",
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
            "post_settle_compile_trust_class",
            "post_settle_compile_note",
            "post_settle_compile_recommended_next_action",
            "post_settle_error_count",
            "post_settle_script_compilation_failed",
            "post_settle_compiler_diagnostics_source",
            "post_settle_structural_diagnostic_count",
            "post_settle_structural_diagnostics_scope",
            "post_settle_compile_failure_class",
            "settle_phase",
            "completion_basis",
            "settled_at_utc",
            "editor_is_compiling_after_settle",
            "editor_is_updating_after_settle",
            "playmode_state_after_settle",
            "playmode_state_after_test_callbacks",
            "playmode_state_after_host_settle",
            "playmode_state_after_settle_source",
            "playmode_state_accounting_consistent",
            "playmode_state_accounting_note",
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
    result = payload.get("result")
    decision_source = result if isinstance(result, dict) else payload
    _copy_if_present(
        compact,
        decision_source,
        (
            "name",
            "target",
            "status",
            "outcome",
            "error_count",
            "warning_count",
            "unique_warning_count",
            "warning_sample_limit",
            "warnings_truncated",
            "compiled_assembly_count",
            "rebuilt_assembly_count",
            "cached_assembly_count",
            "rebuild_evidence_status",
            "rebuild_evidence_basis",
            "duration_seconds",
            "total",
            "passed",
            "failed",
            "skipped",
            "stop_on_first_failure",
        ),
    )
    _copy_if_present(
        compact,
        payload,
        ("settle_request_id",),
    )
    warnings = decision_source.get("warnings")
    if isinstance(warnings, list) and warnings:
        compact["warnings"] = warnings[:COMPILE_WARNING_SAMPLE_LIMIT]
    errors = decision_source.get("errors")
    if isinstance(errors, list) and errors:
        compact["errors"] = errors[:3]
    configurations = (
        decision_source.get("results")
        or decision_source.get("configurations")
        or payload.get("results")
        or payload.get("configurations")
    )
    if isinstance(configurations, list):
        compact["configuration_count"] = len(configurations)
        rebuild_rows = [
            {
                key: item.get(key)
                for key in (
                    "name",
                    "target",
                    "rebuilt_assembly_count",
                    "cached_assembly_count",
                    "rebuild_evidence_status",
                )
                if key in item
            }
            for item in configurations
            if isinstance(item, dict) and "rebuild_evidence_status" in item
        ]
        if rebuild_rows:
            compact["configuration_rebuild_evidence"] = rebuild_rows[:20]
            compact["configuration_rebuild_evidence_truncated"] = len(rebuild_rows) > 20
        failed_rows = [
            item for item in configurations
            if isinstance(item, dict) and str(item.get("status") or "") not in {"", "passed", "ok"}
        ]
        if failed_rows:
            compact["first_failed_configurations"] = failed_rows[:3]
        warning_rows = [
            item for item in configurations
            if isinstance(item, dict) and _int_or_zero(item.get("warning_count")) > 0
        ]
        if warning_rows:
            compact["first_warning_configurations"] = [
                {
                    key: item.get(key)
                    for key in (
                        "name",
                        "target",
                        "status",
                        "warning_count",
                        "unique_warning_count",
                        "warnings_truncated",
                        "warnings",
                    )
                    if key in item
                }
                for item in warning_rows[:3]
            ]
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
            "filter_requested",
            "filter_summary",
            "recommended_next_action",
            "recommended_recovery_command",
            "duration_seconds",
            "result_path",
            "settle_request_id",
            "persisted_test_result_reconciliation",
            "console_error_count_since_request_start",
            "console_error_count_trust_class",
            "console_error_pressure_detected",
        ),
    )
    failures = payload.get("failures") or payload.get("first_failures")
    if isinstance(failures, list) and failures:
        compact["first_failures"] = failures[:3]
    compact.update(_compact_post_settle_fields(payload))
    compact.update(_artifact_ref(payload))
    return compact


def _compact_playmode_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
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
            "playmode_state",
            "is_playing",
            "is_paused",
            "is_playing_or_will_change_playmode",
            "playmode_frame_count",
            "playmode_frames_advanced_last_interval",
            "playmode_frame_sample_interval_seconds",
            "editor_application_focused",
            "playmode_loop_liveness",
            "playmode_liveness_warning",
            "playmode_liveness_remediation",
            "requested_action",
            "settle_target_state",
            "settle_phase",
            "settle_request_id",
            "completion_basis",
            "settled_at_utc",
            "refusal_code",
            "recommended_next_action",
            "result_trust_class",
        ),
    )
    compact.update(_artifact_ref(payload))
    return compact


def _compact_screenshot_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "capture_source",
            "file_path",
            "width",
            "height",
            "render_width",
            "render_height",
            "screen_width",
            "screen_height",
            "render_target_available",
            "render_target_differs_from_screen",
            "playmode_state",
            "playmode_frame_count",
            "playmode_frames_advanced_last_interval",
            "playmode_frame_sample_interval_seconds",
            "editor_application_focused",
            "playmode_loop_liveness",
            "playmode_liveness_warning",
            "playmode_liveness_remediation",
            "result_trust_class",
            "image_included",
            "image_requested",
            "image_omitted_reason",
            "image_bytes",
            "image_budget_bytes",
            "recommended_next_action",
        ),
    )
    image_base64 = payload.get("image_base64")
    if isinstance(image_base64, str) and image_base64:
        compact["image_base64"] = image_base64
    compact.update(_artifact_ref(payload))
    return compact


def _compact_scene_open_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "status",
            "opened",
            "outcome",
            "requested_scene_path",
            "allow_dirty_scene_discard",
            "previous_scene",
            "active_scene",
            "failure_reason",
            "recommended_next_action",
        ),
    )
    compact.update(_compact_post_settle_fields(payload))
    compact.update(_artifact_ref(payload))
    return compact


def _compact_scene_snapshot_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "active_scene",
            "root_objects",
            "result_trust_class",
            "recommended_next_action",
        ),
    )
    root_objects = payload.get("root_objects")
    if isinstance(root_objects, list):
        compact["root_object_count"] = len(root_objects)
    compact.update(_artifact_ref(payload))
    return compact


def _compact_game_view_configure_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "outcome",
            "game_view",
            "recommended_next_action",
        ),
    )
    compact.update(_artifact_ref(payload))
    return compact


def _compact_project_action_currency_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    compact = {
        "payload_mode": "compact_operation",
        "operation": operation,
    }
    _copy_if_present(
        compact,
        payload,
        (
            "project_root",
            "action_id",
            "catalog_path",
            "requires_fresh_assets",
            "asset_refresh_performed",
            "asset_refresh_step_id",
            "editor_domain_loaded_utc",
            "editor_domain_current",
            "editor_domain_currency_known",
            "editor_domain_currency",
            "newest_editor_input_path",
            "newest_editor_input_write_utc",
            "editor_input_count",
            "settled_forced_asset_refresh_requested_utc",
            "script_compilation_failed",
            "currency_basis",
            "safe_to_invoke",
            "reason",
            "recommended_next_action",
            "application_run_in_background",
            "native_autofocus_enabled",
            "background_execution_mode",
            "validation_evidence",
        ),
    )
    return compact


def compact_operation_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    if operation in {"unity.compile.player_scripts", "unity.compile.matrix"}:
        return _compact_compile_payload(payload, operation)
    if operation == "unity.project.refresh":
        return _compact_refresh_payload(payload, operation)
    if operation in {"unity.tests.run_editmode", "unity.tests.run_playmode"}:
        return _compact_tests_payload(payload, operation)
    if operation in {"unity.playmode.state", "unity.playmode.set"}:
        return _compact_playmode_payload(payload, operation)
    if operation == "unity.game_view.screenshot":
        return _compact_screenshot_payload(payload, operation)
    if operation == "unity.scene.open":
        return _compact_scene_open_payload(payload, operation)
    if operation == "unity.scene.snapshot":
        return _compact_scene_snapshot_payload(payload, operation)
    if operation == "unity.game_view.configure":
        return _compact_game_view_configure_payload(payload, operation)
    if operation == "unity.project_action.currency":
        return _compact_project_action_currency_payload(payload, operation)
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
        editor_open_attribution: dict[str, Any] = {}
        if isinstance(lifecycle, dict) and lifecycle:
            operation = str(lifecycle.get("operation") or "")
            payload["_xuunity_lifecycle"] = lifecycle
            editor_open_attribution = hoist_editor_open_attribution(lifecycle)
            if isinstance(payload, dict):
                payload.update(editor_open_attribution)
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
            # Compaction whitelists fields, so re-apply: "this call opened Unity" is decision-shaped, and it is
            # exactly the fact a caller missed while reporting the editor as not running.
            payload.update(editor_open_attribution)

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
