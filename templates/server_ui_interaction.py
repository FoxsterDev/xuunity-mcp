from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json
from server_ui_fixture import (
    resolve_result_path,
    result_path_provenance_gaps,
    scenario_step_payload,
)

UI_INTERACTION_SCHEMA_VERSION = "xuunity.ui-interaction.v1"
INTERACTION_STEP_KIND = "ui_click"
RUNTIME_PLAYMODE_STATES = ("playing", "paused")

GAP_MESSAGES = {
    "evidence_absent": "No ui_interaction evidence was reported for this capture.",
    "evidence_not_receipt_backed": (
        "ui_interaction evidence was asserted by the caller instead of read from a scenario result "
        "written by the editor, so nothing verifies that a click was actually delivered."
    ),
    "unsupported_or_missing_schema_version": (
        f"ui_interaction must declare schema_version '{UI_INTERACTION_SCHEMA_VERSION}'."
    ),
    "missing_interaction_id": "ui_interaction must name the interaction it exercised.",
    "refused": "The click was refused before delivery, so the user path is unproven.",
    "not_delivered": "No handler consumed the click, so the user path is unproven.",
    "no_state_change": (
        "The click was delivered but the UI tree did not change, so nothing shows the interaction "
        "had an effect."
    ),
    "edit_mode_delivery": (
        "The click was delivered in Edit mode. Edit-mode delivery exercises the handler wiring, not "
        "the running user path; only a Play-mode scenario proves a real transition."
    ),
    "step_failed": "The scenario step that delivered the interaction did not pass.",
    "scenario_run_failed": (
        "The scenario that delivered the interaction did not pass, so the run did not complete and "
        "a passing step inside it does not prove the user path."
    ),
    "result_path_outside_editor_results_directory": (
        "The scenario result was read from outside the editor's own results directory, so nothing "
        "distinguishes it from a file the caller wrote; it is treated as an assertion, not a receipt."
    ),
    "result_path_unverifiable_without_project_root": (
        "The scenario result could not be checked against the editor's results directory because no "
        "project root was supplied, so its provenance is unverified."
    ),
    "result_path_unverifiable": (
        "The scenario result path could not be resolved against the editor's results directory, so "
        "its provenance is unverified."
    ),
}


def ui_interaction_contract() -> dict[str, Any]:
    return {
        "schema_version": UI_INTERACTION_SCHEMA_VERSION,
        "emitted_by": f"scenario step kind '{INTERACTION_STEP_KIND}'",
        "consumed_by": ["unity_ui_reference_compare", "unity_ui_interaction_validate"],
        "required_fields": ["schema_version", "interaction_id", "action", "delivered"],
        "fields": {
            "interaction_id": "stable id the reference can require, for example close_button",
            "action": "always 'click'; this contract does not cover coordinate input",
            "selector": "the selector that resolved to exactly one node",
            "delivered": "true only when a handler consumed the event",
            "delivery_mechanism": "how the event reached the handler",
            "target_path": "the matched node path",
            "handler_path": "the ancestor that actually handled the click",
            "state_changed": "whether the UI tree signature differed after delivery",
            "effective": "true only when the click was delivered and produced an observable UI-tree change",
            "no_observable_effect": "true when delivery occurred but the before/after UI signatures are identical",
            "expect_state_change": "the step's expectStateChange; false waives the no_state_change gap but never hides no_observable_effect",
            "click_status": "the direct-tool status the step recorded: effective, delivered_no_observable_effect, or not_delivered",
            "playmode_state": "edit, playing, or paused at delivery time",
            "refusal_code": "set when the operation refused before delivery",
        },
        "rules": [
            "Edit-mode delivery never proves a runtime user path; run the step inside a Play-mode scenario.",
            "A refused or undelivered click is evidence of a broken path, not a missing measurement.",
            "Caller-asserted evidence is never receipt-backed.",
            "Delivery without a state change is always reported as no_observable_effect; it is a gap only when the step expected a change.",
        ],
        "scenario_step_example": {
            "stepId": "close_popup",
            "kind": INTERACTION_STEP_KIND,
            "interactionId": "close_button",
            "approve": True,
            "selector": {"path": "Canvas/Popup/CloseButton"},
            "expectStateChange": True,
        },
    }


def normalize_ui_interaction(
    raw: Any,
    *,
    evidence_source: str = "caller_asserted",
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "contract_version": UI_INTERACTION_SCHEMA_VERSION,
        "evidence_source": evidence_source,
        "receipt": dict(receipt or {}),
        "reported": raw is not None,
    }

    if not isinstance(raw, dict):
        record.update(
            {
                "valid": False,
                "interaction_id": "",
                "action": "",
                "selector": {},
                "delivered": False,
                "state_changed": False,
                "playmode_state": "",
                "runtime_proven": False,
                "gaps": ["evidence_absent"],
                "messages": [GAP_MESSAGES["evidence_absent"]],
            }
        )
        return record

    gaps: list[str] = []
    if _text(raw, "schema_version", "schemaVersion") != UI_INTERACTION_SCHEMA_VERSION:
        gaps.append("unsupported_or_missing_schema_version")

    interaction_id = _text(raw, "interaction_id", "interactionId")
    if not interaction_id:
        gaps.append("missing_interaction_id")

    refusal_code = _text(raw, "refusal_code", "refusalCode")
    delivered = bool(raw.get("delivered", False))
    state_changed = bool(raw.get("state_changed", raw.get("stateChanged", False)))
    effective = bool(raw.get("effective", delivered and state_changed))
    no_observable_effect = bool(raw.get("no_observable_effect", delivered and not state_changed))
    expect_state_change = bool(raw.get("expect_state_change", raw.get("expectStateChange", True)))
    playmode_state = _text(raw, "playmode_state", "playmodeState").lower()

    if refusal_code:
        gaps.append("refused")
    elif not delivered:
        gaps.append("not_delivered")
    elif not state_changed and expect_state_change:
        gaps.append("no_state_change")

    if delivered and playmode_state not in RUNTIME_PLAYMODE_STATES:
        gaps.append("edit_mode_delivery")

    if evidence_source != "scenario_result":
        gaps.append("evidence_not_receipt_backed")

    step_status = str((receipt or {}).get("step_status") or "")
    if step_status and step_status != "passed":
        gaps.append("step_failed")

    scenario_status = str((receipt or {}).get("scenario_status") or "")
    if scenario_status and scenario_status != "passed":
        gaps.append("scenario_run_failed")

    receipt_gaps = [str(code) for code in list((receipt or {}).get("provenance_gaps") or [])]
    gaps.extend(receipt_gaps)

    record.update(
        {
            "valid": "unsupported_or_missing_schema_version" not in gaps
            and "missing_interaction_id" not in gaps,
            "interaction_id": interaction_id,
            "action": _text(raw, "action").lower() or "click",
            "selector": raw.get("selector") if isinstance(raw.get("selector"), dict) else {},
            "delivered": delivered,
            "delivery_mechanism": _text(raw, "delivery_mechanism", "deliveryMechanism"),
            "target_path": _text(raw, "target_path", "targetPath"),
            "target_component": _text(raw, "target_component", "targetComponent"),
            "handler_path": _text(raw, "handler_path", "handlerPath"),
            "pointer_target_status": _text(raw, "pointer_target_status", "pointerTargetStatus"),
            "pointer_target_blocked_by": _text(raw, "pointer_target_blocked_by", "pointerTargetBlockedBy"),
            "transparent_hit_area": bool(raw.get("transparent_hit_area", raw.get("transparentHitArea", False))),
            "transparent_hit_area_evidence": _text(raw, "transparent_hit_area_evidence", "transparentHitAreaEvidence"),
            "state_changed": state_changed,
            "effective": effective,
            "no_observable_effect": no_observable_effect,
            "expect_state_change": expect_state_change,
            "click_status": _text(raw, "click_status", "clickStatus"),
            "before_signature": _text(raw, "before_signature", "beforeSignature"),
            "after_signature": _text(raw, "after_signature", "afterSignature"),
            "playmode_state": playmode_state,
            "refusal_code": refusal_code,
            "runtime_proven": delivered
            and playmode_state in RUNTIME_PLAYMODE_STATES
            and step_status in ("", "passed")
            and scenario_status in ("", "passed")
            and evidence_source == "scenario_result"
            and not refusal_code,
            "gaps": _dedupe(gaps),
        }
    )
    record["messages"] = [GAP_MESSAGES[code] for code in record["gaps"] if code in GAP_MESSAGES]
    return record


def read_scenario_ui_interactions(
    result_path: Path,
    *,
    provenance_gaps: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        payload = read_json(result_path)
    except Exception as exc:
        raise ToolInvocationError(
            "ui_interaction_result_unreadable",
            f"Scenario result '{result_path}' could not be read as JSON: {exc}",
            {"result_path": str(result_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise ToolInvocationError(
            "ui_interaction_result_unreadable",
            f"Scenario result '{result_path}' is not a JSON object.",
            {"result_path": str(result_path)},
        )

    base_receipt = {
        "result_path": str(result_path),
        "sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "run_id": str(payload.get("run_id") or ""),
        "scenario_name": str(payload.get("scenario_name") or ""),
        "scenario_status": str(payload.get("status") or ""),
        "provenance_gaps": list(provenance_gaps or []),
    }
    source = "scenario_result" if not provenance_gaps else "unverified_result_path"

    records: list[dict[str, Any]] = []
    for step in _interaction_steps(payload):
        block = _extract_block(scenario_step_payload(step))
        if block is None:
            continue
        receipt = {
            **base_receipt,
            "step_id": str(step.get("stepId") or step.get("step_id") or ""),
            "step_kind": str(step.get("kind") or ""),
            "step_status": str(step.get("status") or ""),
        }
        records.append(normalize_ui_interaction(block, evidence_source=source, receipt=receipt))
    return records, base_receipt


def resolve_ui_interaction_evidence(
    *,
    workspace: Path,
    interaction_result_path: str = "",
    interaction_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    requested = str(interaction_result_path or "").strip()
    if requested:
        resolved = resolve_result_path(requested, workspace)
        records, _ = read_scenario_ui_interactions(
            resolved,
            provenance_gaps=result_path_provenance_gaps(resolved, project_root),
        )
        return records

    if not interaction_evidence:
        return []

    entries = interaction_evidence if isinstance(interaction_evidence, list) else [interaction_evidence]
    return [
        normalize_ui_interaction(_extract_block(entry) or entry, evidence_source="caller_asserted")
        for entry in entries
        if isinstance(entry, dict)
    ]


def evaluate_interaction_lane(
    *,
    interactions: list[dict[str, Any]],
    required_interactions: list[dict[str, Any]],
    requirement: str,
) -> dict[str, Any]:
    if not required_interactions and not interactions:
        return {
            "requirement": requirement,
            "status": "not_evaluated",
            "evidence": "no_required_interactions_declared_and_none_reported",
            "checked": 0,
            "reported": 0,
            "failures": [],
            "interactions": [],
        }

    by_id = {record["interaction_id"]: record for record in interactions if record.get("interaction_id")}
    failures: list[dict[str, Any]] = []
    blocked = False
    checked = 0

    for entry in required_interactions:
        checked += 1
        interaction_id = str(entry.get("id") or entry.get("interaction_id") or "").strip()
        expect = dict(entry.get("expect") or {})
        expect_delivered = bool(expect.get("delivered", True))
        expect_state_change = bool(expect.get("state_changed", True))
        record = by_id.get(interaction_id) or _match_by_selector(interactions, entry.get("selector"))

        if record is None:
            failures.append(
                {
                    "id": interaction_id,
                    "code": "interaction_not_reported",
                    "message": (
                        f"Required interaction '{interaction_id}' was never exercised; add a "
                        f"'{INTERACTION_STEP_KIND}' step to the Play-mode scenario."
                    ),
                }
            )
            continue
        if record.get("refusal_code"):
            failures.append(
                {
                    "id": interaction_id,
                    "code": str(record["refusal_code"]),
                    "message": f"The click on '{interaction_id}' was refused before delivery.",
                }
            )
            continue
        if expect_delivered and not record.get("delivered"):
            failures.append(
                {"id": interaction_id, "code": "not_delivered", "message": GAP_MESSAGES["not_delivered"]}
            )
            continue
        if expect_state_change and not record.get("state_changed"):
            failures.append(
                {"id": interaction_id, "code": "no_state_change", "message": GAP_MESSAGES["no_state_change"]}
            )
            continue
        if not record.get("runtime_proven"):
            blocked = True

    unproven = [
        record["interaction_id"]
        for record in interactions
        if record.get("delivered") and not record.get("runtime_proven")
    ]

    if failures:
        status = "failed"
    elif blocked or (not required_interactions and unproven):
        status = "blocked"
    elif not required_interactions:
        status = "not_evaluated"
    else:
        status = "passed"

    lane = {
        "requirement": requirement,
        "status": status,
        "evidence": (
            "guarded_event_system_delivery_recorded_by_a_scenario_receipt"
            if interactions
            else "no_interaction_evidence_supplied"
        ),
        "checked": checked,
        "reported": len(interactions),
        "failures": failures,
        "edit_mode_only": sorted(set(unproven)),
        "interactions": [_summary(record) for record in interactions],
    }
    if status == "blocked":
        lane["blocked_reason"] = "edit_mode_delivery_does_not_prove_a_runtime_user_path"
    return lane


def interaction_next_actions(lane: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    status = str(lane.get("status") or "")
    if status == "not_evaluated" and not lane.get("reported"):
        actions.append(
            "Declare required_interactions on the reference and exercise them with a "
            f"'{INTERACTION_STEP_KIND}' step inside a Play-mode scenario, then pass the scenario "
            "result as interactionResultPath."
        )
    if lane.get("blocked_reason"):
        actions.append(
            "Move the click into a Play-mode scenario (playmode_set enter, then "
            f"'{INTERACTION_STEP_KIND}'); Edit-mode delivery proves the wiring, not the user path."
        )
    for failure in list(lane.get("failures") or [])[:3]:
        actions.append(str(failure.get("message") or ""))
    return [action for action in actions if action]


def validate_ui_interactions(
    *,
    project_root: Path,
    workspace: Path,
    interaction_result_path: str = "",
    interaction_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    required_interactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records = resolve_ui_interaction_evidence(
        workspace=workspace,
        interaction_result_path=interaction_result_path,
        interaction_evidence=interaction_evidence,
        project_root=project_root,
    )
    lane = evaluate_interaction_lane(
        interactions=records,
        required_interactions=list(required_interactions or []),
        requirement="required",
    )
    return {
        "action": "unity_ui_interaction_validate",
        "project_root": str(project_root),
        "schema_version": UI_INTERACTION_SCHEMA_VERSION,
        "interaction_lane": lane,
        "interactions": records,
        "succeeded": lane["status"] == "passed",
        "next_actions": interaction_next_actions(lane),
        "contract": ui_interaction_contract(),
    }


def _interaction_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for group in ("steps", "cleanupSteps", "cleanup_steps"):
        for step in list(payload.get(group) or []):
            if isinstance(step, dict) and str(step.get("kind") or "") == INTERACTION_STEP_KIND:
                steps.append(step)
    return steps


def _extract_block(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for key in ("ui_interaction", "uiInteraction"):
        raw = payload.get(key)
        if isinstance(raw, dict):
            block = dict(raw)
            for parent_key in ("expect_state_change", "expectStateChange", "click_status", "clickStatus"):
                if parent_key in payload and parent_key not in block:
                    block[parent_key] = payload.get(parent_key)
            return block
    return None


def _match_by_selector(interactions: list[dict[str, Any]], selector: Any) -> dict[str, Any] | None:
    if not isinstance(selector, dict):
        return None
    path = str(selector.get("path") or "").strip()
    if not path:
        return None
    for record in interactions:
        if str(record.get("target_path") or "") == path:
            return record
    return None


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "interaction_id": record.get("interaction_id", ""),
        "delivered": record.get("delivered", False),
        "state_changed": record.get("state_changed", False),
        "no_observable_effect": record.get("no_observable_effect", False),
        "expect_state_change": record.get("expect_state_change", True),
        "playmode_state": record.get("playmode_state", ""),
        "runtime_proven": record.get("runtime_proven", False),
        "target_path": record.get("target_path", ""),
        "handler_path": record.get("handler_path", ""),
        "refusal_code": record.get("refusal_code", ""),
        "gaps": record.get("gaps", []),
    }


def _text(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
