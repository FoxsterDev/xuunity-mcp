# -*- coding: utf-8 -*-
from __future__ import annotations

from server_cli_shared import *

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
