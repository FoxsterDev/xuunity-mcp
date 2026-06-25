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


UI_SMOKE_PAYLOAD_FIELDS = (
    "user_path",
    "selected_tab",
    "selected_screen",
    "before_model",
    "after_model",
    "before_ui",
    "after_ui",
    "blocking_popup",
    "failure_class",
    "screenshot_path",
)

SCENARIO_FAILURE_CLASSES = {
    "none",
    "product_assertion",
    "startup_lobby",
    "precondition",
    "blocking_popup",
    "infrastructure_timeout",
    "cleanup",
    "unity_unproven",
}

INFRASTRUCTURE_TIMEOUT_ERROR_CODES = {
    "project_refresh_timeout",
    "compile_player_scripts_timeout",
    "editor_idle_timeout",
    "unity_response_timeout",
    "bridge_timeout",
    "request_timeout",
    "scenario_wait_timeout",
}

EDITOR_RELAUNCH_ATTRIBUTION_FIELDS = (
    "editor_relaunched",
    "previous_editor_pid",
    "current_editor_pid",
    "bridge_generation_before",
    "bridge_generation_after",
    "cold_start_reason",
)


def normalize_scenario_payload(payload: dict[str, Any], scenario_terminal_statuses: set[str]) -> dict[str, Any]:
    normalized = dict(payload)
    status = str(normalized.get("status") or "")
    terminal = status in scenario_terminal_statuses
    normalized["terminal"] = terminal
    normalized["succeeded"] = status == "passed"
    normalized["terminal_status"] = status if terminal else ""
    normalized["terminal_statuses"] = sorted(scenario_terminal_statuses)
    return normalized


def utc_age_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - parsed.timestamp())
    except Exception:
        return None


def summarize_scenario_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(step, dict):
        return None

    summary = {
        "step_id": str(step.get("stepId") or ""),
        "kind": str(step.get("kind") or ""),
        "status": str(step.get("status") or ""),
        "outcome": str(step.get("outcome") or ""),
        "duration_seconds": round(float(step.get("duration_seconds") or 0.0), 3),
    }

    error_code = str(step.get("error_code") or "")
    error_message = str(step.get("error_message") or "")
    if error_code:
        summary["error_code"] = error_code
    if error_message:
        summary["error_message"] = truncate_text(error_message, 320)
    return summary


def build_project_defined_hook_summary(steps: list[Any]) -> dict[str, Any]:
    hooks: list[dict[str, Any]] = []
    for raw_step in steps:
        if not isinstance(raw_step, dict):
            continue
        if str(raw_step.get("kind") or "") not in {"project_defined_hook", "project_defined_hook_poll_until"}:
            continue

        payload = _parse_step_payload_json(raw_step)
        hook_summary: dict[str, Any] = {
            "step_id": str(raw_step.get("stepId") or raw_step.get("step_id") or ""),
            "hook_name": str(raw_step.get("hook_name") or raw_step.get("hookName") or ""),
            "kind": str(raw_step.get("kind") or ""),
            "status": str(raw_step.get("status") or ""),
            "outcome": truncate_text(payload.get("outcome") or raw_step.get("outcome") or "", 120),
        }
        payload_flags = _extract_payload_flags(payload)
        payload_scalars = _extract_payload_scalars(payload)
        if payload_flags:
            hook_summary["payload_flags"] = payload_flags
        if payload_scalars:
            hook_summary["payload_scalars"] = payload_scalars
        promoted_scalars = _extract_promoted_payload_scalars(payload, raw_step.get("promote_payload_fields"))
        if promoted_scalars:
            hook_summary["promoted_payload_scalars"] = promoted_scalars

        for key in ("terminal_status", "failure_class", "poll_count"):
            if key in raw_step and raw_step.get(key) not in ("", None):
                hook_summary[key] = raw_step.get(key)

        screenshot_payload = _parse_json_string(raw_step.get("terminal_screenshot_payload_json"))
        screenshot_path = str(screenshot_payload.get("file_path") or screenshot_payload.get("screenshot_path") or "")
        if screenshot_path:
            hook_summary["screenshot_path"] = screenshot_path

        ui_smoke_summary = _extract_ui_smoke_payload_summary(payload, raw_step, screenshot_path=screenshot_path)
        if ui_smoke_summary:
            hook_summary["ui_smoke_summary"] = ui_smoke_summary

        path_coverage_summary = _extract_path_coverage_summary(payload)
        if path_coverage_summary:
            hook_summary["path_coverage_summary"] = path_coverage_summary

        console_tail_payload = _parse_json_string(raw_step.get("terminal_console_tail_payload_json"))
        if console_tail_payload:
            entries = console_tail_payload.get("entries")
            if isinstance(entries, list):
                hook_summary["terminal_console_tail_count"] = len(entries)
            elif "lines" in console_tail_payload and isinstance(console_tail_payload.get("lines"), list):
                hook_summary["terminal_console_tail_count"] = len(console_tail_payload.get("lines") or [])

        error_code = str(raw_step.get("error_code") or "")
        error_message = str(raw_step.get("error_message") or "")
        if error_code:
            hook_summary["error_code"] = error_code
        if error_message:
            hook_summary["error_message"] = truncate_text(error_message, 240)
        hooks.append(hook_summary)

    return {
        "hook_count": len(hooks),
        "all_hooks_succeeded": bool(hooks) and all(str(item.get("status") or "") == "passed" for item in hooks),
        "hooks": hooks,
    }


def _parse_json_string(value: Any) -> dict[str, Any]:
    text = str(value or "")
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_promoted_payload_scalars(payload: dict[str, Any], requested_fields: Any) -> dict[str, Any]:
    if not isinstance(requested_fields, list):
        return {}
    result: dict[str, Any] = {}
    for raw_key in requested_fields:
        key = str(raw_key or "").strip()
        if not key or _is_sensitive_payload_key(key) or key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, (int, float)):
            result[key] = value
        elif isinstance(value, str):
            result[key] = truncate_text(value, 120)
    return result


def _compact_summary_value(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return truncate_text(value, 160)
    if isinstance(value, dict):
        if depth >= 2:
            return truncate_text(json.dumps(value, ensure_ascii=True, sort_keys=True), 200)
        result: dict[str, Any] = {}
        skipped = 0
        for key, nested in value.items():
            if _is_sensitive_payload_key(key):
                continue
            if len(result) >= 12:
                skipped += 1
                continue
            result[str(key)] = _compact_summary_value(nested, depth=depth + 1)
        if skipped > 0:
            result["_truncated_key_count"] = skipped
        return result
    if isinstance(value, list):
        items = [_compact_summary_value(item, depth=depth + 1) for item in value[:8]]
        if len(value) > 8:
            items.append(f"... {len(value) - 8} more")
        return items
    return truncate_text(value, 160)


def _extract_ui_smoke_payload_summary(
    payload: dict[str, Any],
    raw_step: dict[str, Any],
    *,
    screenshot_path: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in UI_SMOKE_PAYLOAD_FIELDS:
        if key not in payload or _is_sensitive_payload_key(key):
            continue
        result[key] = _compact_summary_value(payload.get(key))

    failure_class = str(raw_step.get("failure_class") or "")
    if failure_class and "failure_class" not in result:
        result["failure_class"] = truncate_text(failure_class, 80)
    if screenshot_path and "screenshot_path" not in result:
        result["screenshot_path"] = screenshot_path
    return result


def _first_list_payload_value(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _path_row_identifier(row: Any) -> str:
    if isinstance(row, dict):
        for key in ("path_id", "path", "user_path", "row", "name", "id"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""
    return str(row or "").strip()


def _path_row_label(row: Any, fallback: str) -> str:
    if isinstance(row, dict):
        for key in ("label", "description", "title"):
            value = str(row.get(key) or "").strip()
            if value:
                return truncate_text(value, 120)
    return fallback


def _normalize_path_coverage_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"pass", "passed", "ok", "covered", "satisfied", "true"}:
        return "passed"
    if normalized in {"fail", "failed", "error", "blocked", "false"}:
        return "failed"
    if normalized in {"unavailable", "missing", "not_available", "not_reported", "unknown", "skipped"}:
        return "unavailable"
    return ""


def _payload_reported_path_status(payload: dict[str, Any]) -> str:
    for key in ("path_status", "path_result", "path_coverage_status", "user_path_status"):
        status = _normalize_path_coverage_status(payload.get(key))
        if status:
            return status
    return _normalize_path_coverage_status(payload.get("status"))


def _path_coverage_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = payload.get("path_coverage")
    if coverage is None:
        coverage = payload.get("pathCoverage")

    if isinstance(coverage, dict):
        rows = coverage.get("rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        result: list[dict[str, Any]] = []
        for key, value in coverage.items():
            if key == "rows":
                continue
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("path", key)
                result.append(row)
            else:
                result.append({"path": key, "status": value})
        return result

    if isinstance(coverage, list):
        return [row if isinstance(row, dict) else {"path": row} for row in coverage]

    return []


def _extract_path_coverage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    required_rows = _first_list_payload_value(
        payload,
        (
            "required_path_rows",
            "required_paths",
            "path_rows_required",
            "requiredPathRows",
            "requiredPaths",
        ),
    )
    reported_path = str(
        payload.get("user_path")
        or payload.get("reported_path")
        or payload.get("reported_path_row")
        or payload.get("path_row")
        or ""
    ).strip()

    coverage_rows = _path_coverage_rows_from_payload(payload)
    coverage_by_path: dict[str, dict[str, Any]] = {}
    for raw_row in coverage_rows:
        path = _path_row_identifier(raw_row)
        if path:
            coverage_by_path[path] = raw_row

    if not required_rows and not coverage_rows and not reported_path:
        return {}

    output_rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    reported_status = _payload_reported_path_status(payload)

    for raw_row in required_rows:
        path = _path_row_identifier(raw_row)
        if not path:
            continue
        coverage_row = coverage_by_path.get(path, {})
        status = (
            _normalize_path_coverage_status((raw_row if isinstance(raw_row, dict) else {}).get("status"))
            or _normalize_path_coverage_status(coverage_row.get("status"))
        )
        reported = bool(reported_path and path == reported_path)
        if not status:
            status = reported_status if reported and reported_status else "unavailable"
        output_rows.append(
            {
                "path": path,
                "label": _path_row_label(raw_row, path),
                "required": True,
                "reported": reported,
                "status": status,
            }
        )
        seen_paths.add(path)

    for raw_row in coverage_rows:
        path = _path_row_identifier(raw_row)
        if not path or path in seen_paths:
            continue
        status = _normalize_path_coverage_status(raw_row.get("status")) or "unavailable"
        output_rows.append(
            {
                "path": path,
                "label": _path_row_label(raw_row, path),
                "required": False,
                "reported": bool(reported_path and path == reported_path),
                "status": status,
            }
        )
        seen_paths.add(path)

    if reported_path and reported_path not in seen_paths:
        output_rows.append(
            {
                "path": reported_path,
                "label": reported_path,
                "required": False,
                "reported": True,
                "status": reported_status or "unavailable",
            }
        )

    required_output_rows = [row for row in output_rows if bool(row.get("required"))]
    failed_required_count = sum(1 for row in required_output_rows if row.get("status") == "failed")
    unavailable_required_count = sum(1 for row in required_output_rows if row.get("status") == "unavailable")
    passed_required_count = sum(1 for row in required_output_rows if row.get("status") == "passed")
    return {
        "required_path_count": len(required_output_rows),
        "reported_path": reported_path,
        "passed_required_path_count": passed_required_count,
        "failed_required_path_count": failed_required_count,
        "unavailable_required_path_count": unavailable_required_count,
        "all_required_paths_passed": bool(required_output_rows)
        and passed_required_count == len(required_output_rows),
        "rows": output_rows,
    }


def build_profile_mutation_summary(steps: list[Any]) -> dict[str, Any]:
    mutation_steps: list[dict[str, Any]] = []
    restore_steps: list[dict[str, Any]] = []
    final_assertion_steps: list[dict[str, Any]] = []

    for raw_step in steps:
        if not isinstance(raw_step, dict):
            continue
        action = _step_action_hint(raw_step)
        if not action:
            continue
        step_summary = {
            "step_id": str(raw_step.get("stepId") or raw_step.get("step_id") or ""),
            "kind": str(raw_step.get("kind") or ""),
            "status": str(raw_step.get("status") or ""),
            "action": truncate_text(action, 160),
        }
        if _looks_like_profile_mutation(action):
            mutation_steps.append(step_summary)
        if _looks_like_profile_restore(action):
            restore_steps.append(step_summary)
        if _looks_like_profile_assertion(action):
            final_assertion_steps.append(step_summary)

    profile_restore_required = bool(mutation_steps) and not bool(restore_steps or final_assertion_steps)
    if not mutation_steps and not restore_steps and not final_assertion_steps:
        return {
            "profile_mutation_detected": False,
            "profile_restore_required": False,
            "recommended_next_action": "",
            "mutation_steps": [],
            "restore_steps": [],
            "final_assertion_steps": [],
        }

    recommended = ""
    if profile_restore_required:
        recommended = "restore_or_assert_final_profile_then_run_compile_gate"

    return {
        "profile_mutation_detected": bool(mutation_steps),
        "profile_restore_required": profile_restore_required,
        "recommended_next_action": recommended,
        "mutation_steps": mutation_steps,
        "restore_steps": restore_steps,
        "final_assertion_steps": final_assertion_steps,
    }


def _step_action_hint(step: dict[str, Any]) -> str:
    payload = _parse_step_payload_json(step)
    for key in ("action", "projectAction", "actionId", "profileName", "config_name", "environment"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("action", "projectAction", "actionId", "profileName", "config_name", "environment"):
        value = step.get(key)
        if value:
            return str(value)
    raw_payload = str(step.get("hookPayloadJson") or step.get("payloadJson") or "")
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
            if isinstance(payload, dict):
                for key in ("action", "projectAction", "actionId", "profileName", "config_name", "environment"):
                    value = payload.get(key)
                    if value:
                        return str(value)
        except json.JSONDecodeError:
            return raw_payload
    return ""


def _looks_like_profile_mutation(action: str) -> bool:
    normalized = action.lower()
    return any(marker in normalized for marker in ("set_environment", "apply_profile", "set_profile", "profile.apply", "environment.apply"))


def _looks_like_profile_restore(action: str) -> bool:
    normalized = action.lower()
    return any(marker in normalized for marker in ("restore", "release", "store", "production", "final_profile"))


def _looks_like_profile_assertion(action: str) -> bool:
    normalized = action.lower()
    return any(marker in normalized for marker in ("assert_profile", "assert_environment", "verify_profile", "verify_environment"))


def _parse_step_payload_json(step: dict[str, Any]) -> dict[str, Any]:
    payload_json = str(step.get("payload_json") or "")
    if not payload_json:
        return {}
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_payload_flags(payload: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key, value in payload.items():
        if _is_sensitive_payload_key(key):
            continue
        if isinstance(value, bool):
            result[str(key)] = value
    return result


def _extract_payload_scalars(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "outcome" or _is_sensitive_payload_key(key) or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            result[str(key)] = value
        elif isinstance(value, str):
            result[str(key)] = truncate_text(value, 120)
    return result


def _is_sensitive_payload_key(key: Any) -> bool:
    normalized = str(key or "").lower()
    return any(
        marker in normalized
        for marker in (
            "secret",
            "token",
            "password",
            "credential",
            "private_key",
            "client_secret",
            "api_key",
            "auth",
        )
    )


def _normalize_scenario_failure_class(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return ""
    if normalized in SCENARIO_FAILURE_CLASSES:
        return normalized
    if normalized in {"product", "assertion", "ui_assertion", "semantic_assertion"}:
        return "product_assertion"
    if "product" in normalized or "assert" in normalized:
        return "product_assertion"
    if "startup" in normalized or "lobby" in normalized:
        return "startup_lobby"
    if "precondition" in normalized or "fixture" in normalized:
        return "precondition"
    if "popup" in normalized:
        return "blocking_popup"
    if "cleanup" in normalized or "restore" in normalized:
        return "cleanup"
    if "infrastructure" in normalized or (normalized.endswith("_timeout") and "hook_poll" not in normalized):
        return "infrastructure_timeout"
    if "unproven" in normalized or "unknown" in normalized:
        return "unity_unproven"
    return ""


def _first_failed_raw_step(step_items: list[Any]) -> tuple[int, dict[str, Any] | None]:
    for index, raw_step in enumerate(step_items):
        if isinstance(raw_step, dict) and str(raw_step.get("status") or "") == "failed":
            return index, raw_step
    return -1, None


def _step_error_text(step: dict[str, Any] | None) -> str:
    if not isinstance(step, dict):
        return ""
    parts = [
        str(step.get("kind") or ""),
        str(step.get("outcome") or ""),
        str(step.get("error_code") or ""),
        str(step.get("error_message") or ""),
    ]
    payload = _parse_step_payload_json(step)
    for key in ("failure_class", "error_code", "code", "message", "outcome"):
        if payload.get(key):
            parts.append(str(payload.get(key) or ""))
    return " ".join(part for part in parts if part).lower()


def classify_scenario_failure(
    normalized: dict[str, Any],
    step_items: list[Any],
) -> str:
    status = str(normalized.get("status") or "")
    if status == "passed":
        return "none"
    if not bool(normalized.get("terminal")):
        return "unity_unproven"

    first_failed_index, first_failed = _first_failed_raw_step(step_items)
    if first_failed is None:
        error = normalized.get("error")
        if isinstance(error, dict):
            return _normalize_scenario_failure_class(error.get("code")) or "unity_unproven"
        return "unity_unproven"

    try:
        cleanup_start_index = int(normalized.get("cleanup_start_index"))
    except (TypeError, ValueError):
        cleanup_start_index = -1
    if cleanup_start_index >= 0 and first_failed_index >= cleanup_start_index:
        return "cleanup"

    payload = _parse_step_payload_json(first_failed)
    for value in (
        first_failed.get("failure_class"),
        payload.get("failure_class"),
        payload.get("failureClass"),
        payload.get("failure_type"),
    ):
        failure_class = _normalize_scenario_failure_class(value)
        if failure_class:
            return failure_class

    if bool(payload.get("blocking_popup")) or bool(payload.get("blockingPopup")):
        return "blocking_popup"

    error_code = str(first_failed.get("error_code") or payload.get("error_code") or payload.get("code") or "")
    kind = str(first_failed.get("kind") or "")
    if error_code in INFRASTRUCTURE_TIMEOUT_ERROR_CODES:
        return "infrastructure_timeout"
    if kind in {"project_refresh", "compile_player_scripts"} and error_code.endswith("_timeout"):
        return "infrastructure_timeout"

    text = _step_error_text(first_failed)
    if "blocking_popup" in text or "popup" in text:
        return "blocking_popup"
    if "startup" in text or "lobby" in text:
        return "startup_lobby"
    if "precondition" in text:
        return "precondition"
    if error_code in INFRASTRUCTURE_TIMEOUT_ERROR_CODES or "editor_idle_timeout" in text:
        return "infrastructure_timeout"
    if kind in {"scene_assert", "scene_assertion", "project_defined_hook", "project_defined_hook_poll_until"}:
        return "product_assertion"
    if "assert" in text:
        return "product_assertion"
    return "unity_unproven"


def scenario_verdict_for_failure_class(status: str, failure_class: str) -> str:
    if status == "passed":
        return "passed"
    if failure_class in {"infrastructure_timeout", "unity_unproven"}:
        return "inconclusive"
    if status == "failed":
        return "failed"
    return "inconclusive"


def scenario_trust_class(
    normalized: dict[str, Any],
    *,
    failure_class: str,
) -> str:
    if not bool(normalized.get("terminal")):
        return "unity_unproven"
    if bool(normalized.get("scenario_result_reconciled_from_persisted")) and str(
        normalized.get("scenario_result_lookup_strategy") or ""
    ) != "run_id":
        return "stale_risk"
    if failure_class == "infrastructure_timeout":
        return "infrastructure_timeout"
    if failure_class == "unity_unproven":
        return "unity_unproven"
    return "authoritative"


def recommended_next_action_for_scenario(
    normalized: dict[str, Any],
    *,
    verdict: str,
    failure_class: str,
    trust_class: str,
) -> str:
    explicit = str(normalized.get("recommended_next_action") or "")
    if explicit:
        return explicit
    if verdict == "passed":
        return "none"
    if trust_class == "stale_risk":
        return "rerun_scenario_or_query_by_run_id"
    if failure_class == "infrastructure_timeout":
        return "verify_editor_settled_then_retry_or_increase_timeout"
    if failure_class == "cleanup":
        return "inspect_cleanup_failure_and_restore_state"
    if failure_class == "blocking_popup":
        return "dismiss_or_handle_blocking_popup_then_rerun"
    if failure_class == "startup_lobby":
        return "inspect_startup_or_lobby_readiness_then_rerun"
    if failure_class == "precondition":
        return "satisfy_precondition_then_rerun"
    if failure_class == "product_assertion":
        return "inspect_first_failure_and_product_evidence"
    return "inspect_scenario_result_artifacts_before_retry"


def _summary_int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_editor_relaunch_attribution(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [payload]
    run_start = payload.get("run_start")
    if isinstance(run_start, dict):
        candidates.append(run_start)

    for candidate in candidates:
        if not isinstance(candidate, dict) or not bool(candidate.get("editor_relaunched")):
            continue
        attribution: dict[str, Any] = {"editor_relaunched": True}
        for key in (
            "previous_editor_pid",
            "current_editor_pid",
            "bridge_generation_before",
            "bridge_generation_after",
        ):
            attribution[key] = _summary_int_or_zero(candidate.get(key))
        attribution["cold_start_reason"] = str(candidate.get("cold_start_reason") or "")
        return attribution
    return {}


def build_scenario_result_summary(payload: dict[str, Any], scenario_terminal_statuses: set[str]) -> dict[str, Any]:
    normalized = normalize_scenario_payload(payload, scenario_terminal_statuses)
    steps = normalized.get("steps")
    step_items = steps if isinstance(steps, list) else []

    first_failed_step = None
    last_completed_step = None
    active_step = None
    compact_steps: list[dict[str, Any]] = []
    current_step_index = int(normalized.get("current_step_index") or -1)

    for index, raw_step in enumerate(step_items):
        if not isinstance(raw_step, dict):
            continue

        summarized_step = summarize_scenario_step(raw_step)
        if summarized_step:
            compact_steps.append(summarized_step)
        status = str(raw_step.get("status") or "")
        if first_failed_step is None and status == "failed":
            first_failed_step = summarized_step
        if status not in {"pending", ""}:
            last_completed_step = summarized_step
        if index == current_step_index:
            active_step = summarized_step

    summary = {
        "action": "unity_scenario_result_summary",
        "project_root": str(normalized.get("project_root") or ""),
        "run_id": str(normalized.get("run_id") or ""),
        "scenario_name": str(normalized.get("scenario_name") or ""),
        "status": str(normalized.get("status") or ""),
        "terminal": bool(normalized.get("terminal")),
        "succeeded": bool(normalized.get("succeeded")),
        "terminal_status": str(normalized.get("terminal_status") or ""),
        "started_at_utc": str(normalized.get("started_at_utc") or ""),
        "updated_at_utc": str(normalized.get("updated_at_utc") or ""),
        "completed_at_utc": str(normalized.get("completed_at_utc") or ""),
        "duration_seconds": round(float(normalized.get("duration_seconds") or 0.0), 3),
        "total_steps": int(normalized.get("total_steps") or 0),
        "passed_steps": int(normalized.get("passed_steps") or 0),
        "failed_steps": int(normalized.get("failed_steps") or 0),
        "skipped_steps": int(normalized.get("skipped_steps") or 0),
        "current_step_index": current_step_index,
        "waiting_until_utc": str(normalized.get("waiting_until_utc") or ""),
        "result_path": str(normalized.get("result_path") or ""),
        "active_step": active_step,
        "last_completed_step": last_completed_step,
        "first_failed_step": first_failed_step,
        "steps": compact_steps,
    }
    wait_remaining = scenario_wait_remaining_seconds(summary["waiting_until_utc"])
    if wait_remaining is not None:
        summary["wait_remaining_seconds"] = wait_remaining
    for key in ("structured_timing", "artifact_manifest"):
        if key in normalized:
            summary[key] = normalized.get(key)

    if "recommended_next_action" in normalized:
        summary["recommended_next_action"] = str(normalized.get("recommended_next_action") or "")
    if "waited_for_terminal_state" in normalized:
        summary["waited_for_terminal_state"] = bool(normalized.get("waited_for_terminal_state"))
    if "wait_duration_seconds" in normalized:
        summary["wait_duration_seconds"] = round(float(normalized.get("wait_duration_seconds") or 0.0), 3)
    if "recovery_attempt_count" in normalized:
        summary["recovery_attempt_count"] = int(normalized.get("recovery_attempt_count") or 0)
    if "scenario_result_reconciled_from_persisted" in normalized:
        summary["scenario_result_reconciled_from_persisted"] = bool(normalized.get("scenario_result_reconciled_from_persisted"))
    for key in (
        "scenario_result_reconciliation_reason",
        "scenario_result_lookup_strategy",
    ):
        if key in normalized:
            summary[key] = str(normalized.get(key) or "")
    for key in (
        "scenario_result_matched_result_count",
        "scenario_result_terminal_result_count",
    ):
        if key in normalized:
            summary[key] = int(normalized.get(key) or 0)
    if "offline_error_code" in normalized:
        summary["offline_error_code"] = str(normalized.get("offline_error_code") or "")
    if "offline_error_message" in normalized:
        summary["offline_error_message"] = truncate_text(normalized.get("offline_error_message") or "", 320)

    project_defined_hook_summary = build_project_defined_hook_summary(step_items)
    if project_defined_hook_summary["hook_count"] > 0:
        summary["project_defined_hook_summary"] = project_defined_hook_summary
        ui_smoke_summaries = [
            hook.get("ui_smoke_summary")
            for hook in project_defined_hook_summary.get("hooks", [])
            if isinstance(hook, dict) and isinstance(hook.get("ui_smoke_summary"), dict)
        ]
        if ui_smoke_summaries:
            summary["ui_smoke_summary"] = (
                dict(ui_smoke_summaries[0])
                if len(ui_smoke_summaries) == 1
                else {"hook_count": len(ui_smoke_summaries), "hooks": ui_smoke_summaries}
            )
        path_coverage_summaries = [
            hook.get("path_coverage_summary")
            for hook in project_defined_hook_summary.get("hooks", [])
            if isinstance(hook, dict) and isinstance(hook.get("path_coverage_summary"), dict)
        ]
        if path_coverage_summaries:
            summary["path_coverage_summary"] = (
                dict(path_coverage_summaries[0])
                if len(path_coverage_summaries) == 1
                else {"hook_count": len(path_coverage_summaries), "hooks": path_coverage_summaries}
            )

    cleanup_summary = build_scenario_cleanup_summary(step_items, normalized.get("cleanup_start_index"))
    if cleanup_summary["cleanup_step_count"] > 0:
        summary["cleanup_summary"] = cleanup_summary

    profile_mutation_summary = build_profile_mutation_summary(step_items)
    if bool(profile_mutation_summary.get("profile_mutation_detected")) or bool(profile_mutation_summary.get("restore_steps")):
        summary["profile_mutation_summary"] = profile_mutation_summary
        if bool(profile_mutation_summary.get("profile_restore_required")) and "recommended_next_action" not in summary:
            summary["recommended_next_action"] = str(profile_mutation_summary.get("recommended_next_action") or "")

    for key in (
        "host_health_classification",
        "host_health_reason",
        "host_health_recommended_next_action",
        "host_health_termination_policy",
        "host_health_busy_reason",
        "anr_classification",
        "discovery_classification",
        "discovery_reason",
        "authoritative_state_source",
        "reconciliation_case",
        "reconciliation_status",
        "reconciliation_reason",
        "reconciliation_recommended_next_action",
    ):
        if key in normalized:
            summary[key] = str(normalized.get(key) or "")

    for key in ("detected_editor_count",):
        if key in normalized:
            summary[key] = int(normalized.get(key) or 0)

    for key in ("host_health_heartbeat_age_seconds",):
        if key in normalized:
            summary[key] = normalized.get(key)

    attribution = _extract_editor_relaunch_attribution(normalized)
    if attribution:
        summary.update(attribution)

    if "detected_editor_pids" in normalized:
        summary["detected_editor_pids"] = list(normalized.get("detected_editor_pids") or [])
    if "host_health_progress_evidence" in normalized:
        summary["host_health_progress_evidence"] = list(normalized.get("host_health_progress_evidence") or [])
    if "editor_log_diagnosis" in normalized:
        summary["editor_log_diagnosis"] = dict(normalized.get("editor_log_diagnosis") or {})
    if "editor_log_scope" in normalized:
        summary["editor_log_scope"] = dict(normalized.get("editor_log_scope") or {})
    if "stale_request_artifacts" in normalized:
        summary["stale_request_artifacts"] = dict(normalized.get("stale_request_artifacts") or {})
    if "host_prerequisites" in normalized:
        summary["host_prerequisites"] = dict(normalized.get("host_prerequisites") or {})
    if "transport_state" in normalized:
        summary["transport_state"] = dict(normalized.get("transport_state") or {})
    if "state_groups" in normalized:
        summary["state_groups"] = dict(normalized.get("state_groups") or {})

    error = normalized.get("error")
    if isinstance(error, dict):
        summary["error"] = {
            "code": str(error.get("code") or ""),
            "message": truncate_text(error.get("message") or "", 320),
        }

    return summary


def build_scenario_decision_verdict(payload: dict[str, Any], scenario_terminal_statuses: set[str]) -> dict[str, Any]:
    normalized = normalize_scenario_payload(payload, scenario_terminal_statuses)
    steps = normalized.get("steps")
    step_items = steps if isinstance(steps, list) else []
    summary = build_scenario_result_summary(normalized, scenario_terminal_statuses)
    failure_class = classify_scenario_failure(normalized, step_items)
    scenario_status = str(summary.get("status") or "")
    verdict = scenario_verdict_for_failure_class(scenario_status, failure_class)
    trust_class = scenario_trust_class(normalized, failure_class=failure_class)
    recommended_next_action = recommended_next_action_for_scenario(
        normalized,
        verdict=verdict,
        failure_class=failure_class,
        trust_class=trust_class,
    )
    first_failure = summary.get("first_failed_step")
    if first_failure is None and isinstance(summary.get("error"), dict):
        first_failure = dict(summary.get("error") or {})

    envelope: dict[str, Any] = {
        "action": "unity_scenario_run_and_wait",
        "verdict": verdict,
        "trust_class": trust_class,
        "failure_class": failure_class,
        "scenario_status": scenario_status,
        "status": scenario_status,
        "terminal": bool(summary.get("terminal")),
        "succeeded": verdict == "passed",
        "run_id": str(summary.get("run_id") or ""),
        "scenario_name": str(summary.get("scenario_name") or ""),
        "result_path": str(summary.get("result_path") or ""),
        "first_failure": first_failure,
        "steps": list(summary.get("steps") or []),
        "recommended_next_action": recommended_next_action,
        "full_payload_available": True,
    }

    for key in (
        "project_root",
        "started_at_utc",
        "updated_at_utc",
        "completed_at_utc",
        "duration_seconds",
        "total_steps",
        "passed_steps",
        "failed_steps",
        "skipped_steps",
        "waited_for_terminal_state",
        "wait_duration_seconds",
        "recovery_attempt_count",
        "scenario_result_reconciled_from_persisted",
        "scenario_result_reconciliation_reason",
        "scenario_result_lookup_strategy",
        "scenario_result_matched_result_count",
        "scenario_result_terminal_result_count",
    ):
        if key in summary:
            envelope[key] = summary.get(key)

    for key in EDITOR_RELAUNCH_ATTRIBUTION_FIELDS:
        if key in summary:
            envelope[key] = summary.get(key)

    for key in (
        "project_defined_hook_summary",
        "cleanup_summary",
        "ui_smoke_summary",
        "path_coverage_summary",
        "profile_mutation_summary",
        "structured_timing",
        "artifact_manifest",
    ):
        if key in summary:
            envelope[key] = summary.get(key)

    if isinstance(summary.get("error"), dict):
        envelope["error"] = summary.get("error")

    return envelope


def build_scenario_cleanup_summary(steps: list[Any], cleanup_start_index: Any) -> dict[str, Any]:
    try:
        start_index = int(cleanup_start_index)
    except (TypeError, ValueError):
        start_index = -1

    if start_index < 0 or start_index >= len(steps):
        return {
            "cleanup_step_count": 0,
            "cleanup_passed_count": 0,
            "cleanup_failed_count": 0,
            "cleanup_skipped_count": 0,
            "cleanup_result": "",
            "cleanup_steps": [],
        }

    cleanup_steps: list[dict[str, Any]] = []
    for raw_step in steps[start_index:]:
        summarized = summarize_scenario_step(raw_step if isinstance(raw_step, dict) else None)
        if summarized:
            cleanup_steps.append(summarized)

    passed = sum(1 for item in cleanup_steps if str(item.get("status") or "") == "passed")
    failed = sum(1 for item in cleanup_steps if str(item.get("status") or "") == "failed")
    skipped = sum(1 for item in cleanup_steps if str(item.get("status") or "") == "skipped")
    if failed > 0:
        cleanup_result = "failed"
    elif cleanup_steps and passed == len(cleanup_steps):
        cleanup_result = "passed"
    elif cleanup_steps:
        cleanup_result = "incomplete"
    else:
        cleanup_result = ""

    return {
        "cleanup_step_count": len(cleanup_steps),
        "cleanup_passed_count": passed,
        "cleanup_failed_count": failed,
        "cleanup_skipped_count": skipped,
        "cleanup_result": cleanup_result,
        "cleanup_steps": cleanup_steps,
    }


def scenario_wait_remaining_seconds(waiting_until_utc: Any) -> float | None:
    age = utc_age_seconds(waiting_until_utc)
    if age is None:
        return None
    text = str(waiting_until_utc or "").strip()
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return round(max(0.0, parsed.timestamp() - time.time()), 3)
    except Exception:
        return None


__all__ = [name for name in globals() if not name.startswith("__")]
