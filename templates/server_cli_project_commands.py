# -*- coding: utf-8 -*-
from __future__ import annotations

from server_cli_shared import *

from server_ui_fixture import validate_ui_fixture
from server_ui_interaction import validate_ui_interactions
from server_ui_reference_compare import compare_ui_reference
from server_ui_reference_registry import register_ui_reference, validate_ui_reference
from server_ui_vision_packet import build_vision_packet, submit_vision_review

def cmd_project_action_list(args):
    project_root = ensure_project_root(args.project_root)
    catalog = load_project_action_catalog(project_root, args.catalog_file or "")
    print_json(project_action_catalog_payload(catalog))


def cmd_project_action_invoke(args):
    project_root = ensure_project_root(args.project_root)
    result, is_error = invoke_project_action_from_catalog(
        project_root=project_root,
        requested_action=args.action_id,
        action_payload=load_project_action_payload_args(args),
        catalog_path=args.catalog_file or "",
        scenario_name=args.scenario_name or "",
        timeout_ms=resolve_operation_default_timeout_ms(project_root, "unity.scenario.run", 600000) if args.timeout_ms is None else args.timeout_ms,
        poll_interval_ms=args.poll_interval_ms,
        wait_for_result=not bool(args.no_wait),
        allow_mutating=bool(args.allow_mutating),
        strict_payload=bool(getattr(args, "strict_payload", False)),
    )
    print_json(result)
    if is_error:
        raise SystemExit(1)


def cmd_project_hook_scaffold(args):
    result = scaffold_project_hook(
        hook_name=args.hook_name,
        action_id=args.action_id,
        class_name=args.class_name,
        namespace=args.namespace,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        mutating=bool(args.mutating),
        ui_fixture=bool(args.ui_fixture),
        write_files=bool(args.write),
    )
    print_json(result)


def cmd_artifact_register(args):
    project_root = ensure_project_root(args.project_root)
    payload = register_artifact(
        project_root=project_root,
        artifact_path=args.path,
        destination=args.destination,
        kind=args.kind,
        producer=args.producer,
        artifact_schema_version=args.artifact_schema_version,
        language=args.language,
        retention_policy=args.retention_policy,
        metadata=load_optional_json_object(args.metadata_json, "artifact_metadata_invalid"),
        workspace_root=args.workspace_root,
        allow_unity_assets=bool(args.allow_unity_assets),
    )
    print_json(payload)


def cmd_artifact_write_report(args):
    project_root = ensure_project_root(args.project_root)
    payload = write_artifact_report(
        project_root=project_root,
        content=load_report_content_args(args),
        destination=args.destination,
        category=args.category,
        relative_path=args.relative_path,
        kind=args.kind,
        producer=args.producer,
        artifact_schema_version=args.artifact_schema_version,
        language=args.language,
        retention_policy=args.retention_policy,
        metadata=load_optional_json_object(args.metadata_json, "artifact_metadata_invalid"),
        workspace_root=args.workspace_root,
        allow_unity_assets=bool(args.allow_unity_assets),
    )
    print_json(payload)


def cmd_artifact_probe(args):
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    if artifact_probe_config is None:
        raise ToolInvocationError(
            "artifact_probe_missing",
            "Pass --artifact-probe-file or --artifact-probe-json.",
        )

    summary = run_artifact_probe(
        artifact_probe_config,
        artifact_path_override=args.artifact_path or "",
        truncate_text=truncate_text,
    )
    print_json({"artifact_probe_summary": summary})
    if not bool(summary.get("succeeded")) and not bool(args.artifact_probe_warn_only):
        raise SystemExit(1)


def cmd_request_scenario_validate(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    response = invoke_bridge(
        str(project_root),
        "unity.scenario.validate",
        {"scenario": scenario},
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_run(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    response = invoke_bridge(
        str(project_root),
        "unity.scenario.run",
        {"scenario": scenario},
        resolve_operation_default_timeout_ms(project_root, "unity.scenario.run", 600000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_run_and_wait(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    result = call_unity_scenario_run_and_wait_tool(
        {
            "projectRoot": str(project_root),
            "scenario": scenario,
            "timeoutMs": args.timeout_ms,
            "pollIntervalMs": args.poll_interval_ms,
            "verbose": bool(args.verbose),
            "includeFullPayload": bool(args.include_full_payload),
            "includeStepPayloads": bool(args.include_step_payloads),
        }
    )
    print_json(result.get("structuredContent") or {})
    if result.get("isError"):
        raise SystemExit(1)


def cmd_request_scenario_result(args):
    bridge_args: dict[str, Any] = {}
    if args.run_id:
        bridge_args["runId"] = args.run_id
    if args.scenario_name:
        bridge_args["scenarioName"] = args.scenario_name

    response = invoke_bridge(
        args.project_root,
        "unity.scenario.result",
        bridge_args,
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_result_summary(args):
    project_root = ensure_project_root(args.project_root)
    bridge_args: dict[str, Any] = {}
    if args.run_id:
        bridge_args["runId"] = args.run_id
    if args.scenario_name:
        bridge_args["scenarioName"] = args.scenario_name

    try:
        response = invoke_bridge(
            str(project_root),
            "unity.scenario.result",
            bridge_args,
            args.timeout_ms,
        )
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES.union(SCENARIO_RECOVERY_ERROR_CODES):
            print_json(
                build_discovery_scenario_result_summary_for_error(
                    project_root,
                    bridge_args.get("runId", ""),
                    bridge_args.get("scenarioName", ""),
                    exc,
                )
            )
            return
        raise

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        print_json(tool_result.get("structuredContent") or {})
        raise SystemExit(1)
    payload = tool_result.get("structuredContent") or {}
    print_json(build_scenario_result_summary_from_context(project_root, payload if isinstance(payload, dict) else {}))


def cmd_request_scenario_results_list(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        list_persisted_scenario_result_summaries(
            project_root,
            scenario_results_dir=scenario_results_dir,
            read_json=read_json,
            parse_utc_timestamp=parse_utc_timestamp,
            attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
            build_scenario_result_summary=build_scenario_result_summary,
            scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
            scenario_name=str(args.scenario_name or ""),
            limit=int(args.limit or 20),
        )
    )


def cmd_request_scenario_result_latest(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        latest_persisted_scenario_result_summary(
            project_root,
            scenario_results_dir=scenario_results_dir,
            read_json=read_json,
            parse_utc_timestamp=parse_utc_timestamp,
            attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
            build_scenario_result_summary=build_scenario_result_summary,
            scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
            scenario_name=str(args.scenario_name or ""),
        )
    )


def cmd_maintenance_prune(args):
    project_root = ensure_project_root(args.project_root)
    result = prune_project_artifacts(
        project_root,
        {
            "dryRun": args.dry_run,
            "requestJournalMaxAgeHours": args.request_journal_max_age_hours,
            "requestJournalKeepLatest": args.request_journal_keep_latest,
            "scenarioSuccessMaxAgeHours": args.scenario_success_max_age_hours,
            "scenarioFailureMaxAgeHours": args.scenario_failure_max_age_hours,
            "scenarioRunningMaxAgeHours": args.scenario_running_max_age_hours,
            "scenarioKeepLatestSuccess": args.scenario_keep_latest_success,
            "scenarioKeepLatestFailure": args.scenario_keep_latest_failure,
            "scenarioKeepLatestRunning": args.scenario_keep_latest_running,
            "capturesMaxAgeHours": args.captures_max_age_hours,
            "capturesKeepLatest": args.captures_keep_latest,
            "pruneLogs": args.prune_logs,
            "logsMaxAgeHours": args.logs_max_age_hours,
            "logsKeepLatest": args.logs_keep_latest,
        },
        bridge_root=bridge_root,
        request_journal_dir=request_journal_dir,
        scenario_results_dir=scenario_results_dir,
        active_scenario_run_path=active_scenario_run_path,
        captures_dir=captures_dir,
        logs_dir=logs_dir,
        default_editor_log_path=default_editor_log_path,
        read_json=read_json,
    )
    print_json(result)


def load_optional_json_object_list(value: str, error_code: str) -> list[dict[str, Any]] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolInvocationError(error_code, str(exc)) from exc
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ToolInvocationError(error_code, "Expected a JSON array of objects.")
    return payload


def cmd_ui_reference_register(args):
    project_root = ensure_project_root(args.project_root)
    payload = register_ui_reference(
        project_root=project_root,
        reference_id=args.reference_id,
        source_image=args.source_image,
        viewport=load_optional_json_object(args.viewport_json, "ui_reference_viewport_invalid") or None,
        safe_area=args.safe_area,
        fixture=args.fixture,
        regions=load_optional_json_object_list(args.regions_json, "ui_reference_region_invalid"),
        dynamic_masks=load_optional_json_object_list(args.dynamic_masks_json, "ui_reference_mask_invalid"),
        required_ui=load_optional_json_object_list(args.required_ui_json, "ui_reference_required_ui_invalid"),
        required_interactions=load_optional_json_object_list(
            args.required_interactions_json, "ui_reference_required_interaction_invalid"
        ),
        vision_policy=load_optional_json_object(args.vision_policy_json, "ui_reference_vision_policy_invalid")
        or None,
        thresholds=load_optional_json_object(args.thresholds_json, "ui_reference_threshold_invalid") or None,
        tolerance_profile=args.tolerance_profile,
        scale_policy=args.scale_policy,
        owner=args.owner,
        acceptance=load_optional_json_object(args.acceptance_json, "ui_reference_acceptance_invalid") or None,
        notes=args.notes,
        category=args.category,
        workspace_root=args.workspace_root,
        overwrite=bool(args.overwrite),
    )
    print_json(payload)


def cmd_ui_reference_validate(args):
    project_root = ensure_project_root(args.project_root)
    payload = validate_ui_reference(
        project_root=project_root,
        reference_id=args.reference_id,
        manifest_path=args.manifest_path,
        category=args.category,
        workspace_root=args.workspace_root,
    )
    print_json(payload)
    if not bool((payload.get("validation") or {}).get("valid")):
        raise SystemExit(1)


def cmd_ui_reference_compare(args):
    project_root = ensure_project_root(args.project_root)
    payload = compare_ui_reference(
        project_root=project_root,
        actual_image=args.actual_image,
        reference_id=args.reference_id,
        manifest_path=args.manifest_path,
        stability_image=args.stability_image,
        require_capture_stability=not bool(args.no_require_capture_stability),
        emit_artifacts=not bool(args.no_artifacts),
        include_expected_copy=bool(args.include_expected_copy),
        comparison_id=args.comparison_id,
        tolerance_profile=args.tolerance_profile,
        fixture_evidence=load_optional_json_object(
            args.fixture_evidence_json, "ui_reference_fixture_evidence_invalid"
        ),
        fixture_result_path=args.fixture_result_path,
        ui_snapshot_path=args.ui_snapshot_path,
        interaction_result_path=args.interaction_result_path,
        interaction_evidence=load_optional_json_object_list(
            args.interaction_evidence_json, "ui_reference_interaction_evidence_invalid"
        ),
        vision_review_paths=list(args.vision_review_path or []),
        capture_lane=args.capture_lane,
        device=load_optional_json_object(args.device_json, "ui_reference_device_invalid") or None,
        category=args.category,
        workspace_root=args.workspace_root,
    )
    print_json(payload)
    if payload.get("reference_acceptance") != "passed":
        raise SystemExit(1)


def cmd_ui_fixture_validate(args):
    project_root = ensure_project_root(args.project_root)
    payload = validate_ui_fixture(
        project_root=project_root,
        workspace=resolve_workspace_root(project_root, args.workspace_root),
        fixture_evidence=load_optional_json_object(
            args.fixture_evidence_json, "ui_fixture_evidence_invalid"
        ),
        fixture_result_path=args.fixture_result_path,
        declared_fixture=args.declared_fixture,
        declared_viewport=load_optional_json_object(
            args.declared_viewport_json, "ui_fixture_viewport_invalid"
        ),
    )
    print_json(payload)
    if not bool(payload.get("succeeded")):
        raise SystemExit(1)


def cmd_ui_vision_packet(args):
    project_root = ensure_project_root(args.project_root)
    payload = build_vision_packet(
        project_root=project_root,
        actual_image=args.actual_image,
        reference_id=args.reference_id,
        manifest_path=args.manifest_path,
        comparison_path=args.comparison_path,
        comparison_id=args.comparison_id,
        include_numeric_evidence=bool(args.include_numeric_evidence),
        max_panel_height=int(args.max_panel_height),
        category=args.category,
        workspace_root=args.workspace_root,
    )
    print_json(payload)


def cmd_ui_vision_submit(args):
    project_root = ensure_project_root(args.project_root)
    payload = submit_vision_review(
        project_root=project_root,
        packet_path=args.packet_path,
        review=load_optional_json_object(args.review_json, "ui_vision_review_invalid"),
        review_path=args.review_path,
        workspace_root=args.workspace_root,
    )
    print_json(payload)
    if not bool(payload.get("succeeded")):
        raise SystemExit(1)


def cmd_ui_interaction_validate(args):
    project_root = ensure_project_root(args.project_root)
    payload = validate_ui_interactions(
        project_root=project_root,
        workspace=resolve_workspace_root(project_root, args.workspace_root),
        interaction_result_path=args.interaction_result_path,
        interaction_evidence=load_optional_json_object_list(
            args.interaction_evidence_json, "ui_interaction_evidence_invalid"
        ),
        required_interactions=load_optional_json_object_list(
            args.required_interactions_json, "ui_reference_required_interaction_invalid"
        ),
    )
    print_json(payload)
    if not bool(payload.get("succeeded")):
        raise SystemExit(1)
