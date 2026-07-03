# -*- coding: utf-8 -*-
from __future__ import annotations

from server_cli_shared import *

def cmd_recover_editor_session(args):
    project_root = ensure_project_root(args.project_root)
    refresh_project_context(project_root)
    initial_discovery = build_project_discovery_report(project_root)

    payload: dict[str, Any] = {
        "action": "recover_editor_session",
        "project_root": str(project_root),
        "dialog_policy": "observe_only",
        "recovery_classification": "inspection_only",
        "initial_discovery": initial_discovery,
        "closeout_attempted": False,
        "compile_probe_attempted": False,
    }

    host_session_state = current_project_context_host_session_state(project_root)
    if bool(host_session_state.get("opened_by_host")):
        payload["closeout_attempted"] = True
        closeout = restore_host_opened_editor_state(project_root, args.close_timeout_ms, request_editor_quit)
        payload["closeout"] = closeout
        refresh_project_context(project_root)
        if not bool(closeout.get("closeout_verified")):
            payload["recovery_classification"] = "closeout_incomplete"
            payload["recovery_recommended_next_action"] = str(
                closeout.get("recommended_next_action")
                or "manual_editor_close"
            )
            payload["recommended_recovery_command"] = str(closeout.get("recommended_recovery_command") or "")
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    refresh_project_context(project_root)
    discovery_after_closeout = build_project_discovery_report(project_root)
    payload["discovery_after_closeout"] = discovery_after_closeout

    detected_editor_pids = list(discovery_after_closeout.get("detected_editor_pids") or [])
    if (
        not detected_editor_pids
        and str(discovery_after_closeout.get("reconciliation_case") or "") in {"stale_bridge_state", "stale_bridge_and_host_session"}
    ):
        payload["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
        refresh_project_context(project_root)
        discovery_after_closeout = build_project_discovery_report(project_root)
        payload["discovery_after_closeout"] = discovery_after_closeout

    diagnosis = dict(discovery_after_closeout.get("editor_log_diagnosis") or {})
    diagnosis_code = str(diagnosis.get("code") or "")
    compile_block_detected = diagnosis_code in {
        "interactive_compile_block_detected",
        "safe_mode_manual_required",
        "package_resolution_failed",
    }

    if compile_block_detected or bool(args.force_compile_probe):
        payload["compile_probe_attempted"] = True
        compile_probe = run_batch_build_config_compile_matrix_probe(
            project_root,
            timeout_ms=args.timeout_ms,
        )
        payload["compile_probe"] = compile_probe
        if not bool(compile_probe.get("succeeded")):
            recovery_classification, next_action, recovery_command_template = classify_compile_probe_failure(compile_probe)
            payload["recovery_classification"] = recovery_classification
            payload["recovery_recommended_next_action"] = next_action
            payload["recommended_recovery_command"] = recovery_command_template.format(project_root=str(project_root))
            if recovery_classification == "compile_red_confirmed":
                payload["reopen_blocked"] = True
                payload["reopen_block_reason"] = "compile_red_after_batch_restore"
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    if args.open_editor:
        ensure_payload, ensure_completed = run_self_json_command_with_completed(
            [
                "ensure-ready",
                "--project-root",
                str(project_root),
                "--open-editor",
                "--timeout-ms",
                str(args.timeout_ms),
                "--heartbeat-max-age-seconds",
                str(args.heartbeat_max_age_seconds),
                "--startup-policy",
                str(args.startup_policy),
            ]
        )
        payload["ensure_ready"] = ensure_payload or {}
        if ensure_completed.returncode != 0:
            payload["recovery_classification"] = "reopen_failed"
            error_payload = dict((ensure_payload or {}).get("error") or {})
            details = dict(error_payload.get("details") or {})
            payload["recovery_recommended_next_action"] = str(
                details.get("recommended_next_action")
                or "inspect_editor_log"
            )
            payload["recommended_recovery_command"] = str(
                details.get("recommended_recovery_command")
                or recommended_recovery_command_for_project(project_root, payload["recovery_recommended_next_action"])
            )
            payload["reopen_error"] = {
                "code": str(error_payload.get("code") or "ensure_ready_failed"),
                "message": str(error_payload.get("message") or truncate_text(ensure_completed.stderr or "", 400)),
                "details": details,
            }
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    payload["recovery_classification"] = "recovered"
    payload["recovery_recommended_next_action"] = "none"
    payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
    print_json(payload)


def cmd_bridge_state(args):
    project_root = ensure_project_root(args.project_root)
    if not bridge_enabled(project_root):
        raise SystemExit(
            "Bridge is disabled for this project. Enable it with "
            "init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project and reopen Unity."
        )
    state_path = bridge_state_path(project_root)
    if not state_path.is_file():
        raise SystemExit(f"Bridge state file not found: {state_path}")
    print_json(annotate_bridge_state_with_liveness(read_json(state_path)))


def cmd_request_status(args):
    response = invoke_bridge(args.project_root, "unity.status", {}, args.timeout_ms)
    print_json(response)


def cmd_request_status_summary(args):
    project_root = ensure_project_root(args.project_root)
    try:
        response = invoke_bridge(str(project_root), "unity.status", {}, args.timeout_ms)
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES:
            print_json(build_discovery_status_summary_for_error(project_root, exc))
            return
        raise

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        print_json(tool_result.get("structuredContent") or {})
        raise SystemExit(1)
    payload = tool_result.get("structuredContent") or {}
    print_json(build_status_summary_from_context(project_root, payload if isinstance(payload, dict) else {}))


def cmd_request_latest_status(args):
    project_root = ensure_project_root(args.project_root)
    operations = [str(operation).strip() for operation in list(args.operation or []) if str(operation).strip()]
    current_state = current_project_context_bridge_state(project_root)
    latest_event = find_latest_request_event(project_root, operations)

    if latest_event is None:
        stabilization = build_bridge_stabilization_summary(current_state)
        print_json(apply_discovery_to_final_status_summary({
            "lookup_mode": "latest_request_by_operation",
            "lookup_found": False,
            "matched_operations": operations,
            "request_id": "",
            "operation": operations[-1] if operations else "",
            "request_started": False,
            "request_completed": False,
            "completion_status": "",
            "operation_outcome": "unknown",
            "reclassified": False,
            "reclassified_status": "",
            "reclassified_reason": "",
            "retryable": False,
            "recommended_next_action": (
                "retry_request" if stabilization["safe_to_retry"] else "wait_for_bridge_stabilization"
            ),
            "request_started_at_utc": "",
            "request_completed_at_utc": "",
            "last_event_type": "",
            "last_event_at_utc": "",
            "last_bridge_generation_seen": int((current_state or {}).get("bridge_generation") or 0),
            "last_bridge_session_id_seen": str((current_state or {}).get("bridge_session_id") or ""),
            "journal_event_count": 0,
            "journal_event_paths": [],
            "bridge_stabilization": stabilization,
        }, project_root))
        return

    request_id = str(latest_event.get("request_id") or "").strip()
    operation = str(latest_event.get("operation") or "").strip()
    summary = build_request_final_status_from_context(project_root, request_id, operation, args.timeout_ms)
    summary["lookup_mode"] = "latest_request_by_operation"
    summary["lookup_found"] = True
    summary["matched_operations"] = operations
    summary["lookup_event_type"] = str(latest_event.get("event_type") or "")
    summary["lookup_event_at_utc"] = str(latest_event.get("event_at_utc") or "")
    summary["lookup_event_path"] = str(latest_event.get("_path") or "")
    print_json(summary)


def cmd_request_final_status(args):
    project_root = ensure_project_root(args.project_root)
    summary = build_request_final_status_from_context(project_root, args.request_id, args.operation or "", args.timeout_ms)
    print_json(summary)


def cmd_request_cancel(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        cancel_request_best_effort(
            project_root,
            str(args.request_id or ""),
            operation=str(args.operation or ""),
        )
    )


def cmd_request_stale_cleanup(args):
    project_root = ensure_project_root(args.project_root)
    current_state = current_project_context_bridge_state(project_root)
    print_json(
        cleanup_stale_request_artifacts(
            project_root,
            current_state=current_state,
            stale_age_seconds=max(1, int(args.stale_age_seconds or 600)),
            dry_run=bool(args.dry_run),
            max_entries=max(1, int(args.max_entries or 50)),
        )
    )


def cmd_request_playmode_state(args):
    response = invoke_bridge(args.project_root, "unity.playmode.state", {}, args.timeout_ms)
    print_json(response)


def cmd_request_playmode_set(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.playmode.set",
        {"action": args.action},
        resolve_operation_default_timeout_ms(project_root, "unity.playmode.set", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_capabilities(args):
    response = invoke_bridge(args.project_root, "unity.capabilities.get", {}, args.timeout_ms)
    print_json(response)


def cmd_request_health_probe(args):
    response = invoke_bridge(args.project_root, "unity.health.probe", {}, args.timeout_ms)
    print_json(response)


def cmd_request_build_target_get(args):
    response = invoke_bridge(args.project_root, "unity.build_target.get", {}, args.timeout_ms)
    print_json(response)


def cmd_request_build_target_switch(args):
    response = invoke_bridge(
        args.project_root,
        "unity.build_target.switch",
        {"target": args.target},
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_build_player(args):
    project_root = ensure_project_root(args.project_root)
    build_target = str(args.build_target or "").strip()
    if not build_target:
        raise ToolInvocationError("missing_build_target", "--build-target is required.")
    output_path = resolve_batch_build_output_path(project_root, args.output_path)
    scene_paths = list(args.scene_path or [])
    build_options = list(args.build_option or [])
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if getattr(args, "result_file", "")
        else default_batch_build_result_path(project_root, build_target)
    )
    bridge_args = {
        "buildTarget": build_target,
        "outputPath": output_path,
        "resultFile": str(result_path),
        "scenePaths": scene_paths,
        "buildOptions": build_options,
    }
    response = invoke_bridge(
        str(project_root),
        "unity.build_player",
        bridge_args,
        resolve_operation_default_timeout_ms(project_root, "unity.build_player", 600000) if args.timeout_ms is None else args.timeout_ms,
    )
    payload = {
        "action": "request_build_player",
        "project_root": str(project_root),
        "bridge_response": response,
        "build_target": build_target,
        "output_path": output_path,
        "scene_paths": scene_paths,
        "build_options": build_options,
        "result_file": str(result_path),
    }
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    if artifact_probe_config is not None:
        summary = run_artifact_probe(
            artifact_probe_config,
            artifact_path_override=output_path,
            truncate_text=truncate_text,
        )
        payload["artifact_probe_summary"] = summary
        payload["artifact_probe_succeeded"] = bool(summary.get("succeeded"))
        if not bool(summary.get("succeeded")) and not bool(getattr(args, "artifact_probe_warn_only", False)):
            print_json(payload)
            raise SystemExit(1)
    print_json(payload)


def cmd_request_scene_assert(args):
    response = invoke_bridge(
        args.project_root,
        "unity.scene.assert",
        {
            "expectedName": args.expected_name or "",
            "expectedPath": args.expected_path or "",
            "requiredRootNames": args.required_root_name or None,
            "allowDirty": args.allow_dirty,
        },
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_scene_open(args):
    response = invoke_bridge(
        args.project_root,
        "unity.scene.open",
        {
            "scenePath": args.scene_path or "",
            "allowDirtySceneDiscard": args.allow_dirty_scene_discard,
        },
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_console_grep(args):
    project_root = ensure_project_root(args.project_root)
    source = str(getattr(args, "source", "console") or "console")
    if source == "editor_log":
        log_path = resolve_editor_log_path(project_root, getattr(args, "editor_log_path", None))
        try:
            payload = grep_editor_log_payload(
                project_root,
                log_path,
                pattern=args.pattern,
                regex=bool(args.regex),
                ignore_case=bool(args.ignore_case),
                include_stack_traces=bool(args.include_stack_traces),
                limit=max(1, int(args.limit or 20)),
            )
        except ValueError as exc:
            raise ToolInvocationError("invalid_editor_log_grep", str(exc)) from exc
        print_json(
            {
                "status": "ok",
                "payload_type": "unity.console.grep",
                "payload_json": json.dumps(payload, ensure_ascii=True),
            }
        )
        return

    response = invoke_bridge(
        str(project_root),
        "unity.console.grep",
        {
            "pattern": args.pattern,
            "regex": bool(args.regex),
            "ignoreCase": bool(args.ignore_case),
            "includeStackTraces": bool(args.include_stack_traces),
            "limit": max(1, int(args.limit or 20)),
            "includeTypes": args.include_type or None,
        },
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_loading_timing(args):
    project_root = ensure_project_root(args.project_root)
    summary = request_loading_timing_summary(
        project_root=project_root,
        markers=args.marker or [],
        timing_only=not bool(args.include_non_timing),
        include_stack_traces=bool(args.include_stack_traces),
        include_types=args.include_type or [],
        limit=int(args.limit or 20),
        timeout_ms=int(args.timeout_ms or 5000),
        invoke_bridge=invoke_bridge,
    )
    print_json(summary)
    if not bool(summary.get("succeeded")):
        raise SystemExit(1)


def cmd_request_editor_quit(args):
    project_root = ensure_project_root(args.project_root)
    response = request_editor_quit(str(project_root), args.timeout_ms)
    response["quit_request_accepted"] = response.get("status") == "ok"
    response["process_exit_verified"] = False
    if not bool(getattr(args, "wait_for_exit", False)):
        print_json(response)
        return

    verification = verify_project_editor_closed(project_root, args.exit_timeout_ms)
    payload = {
        "action": "request_editor_quit",
        "project_root": str(project_root),
        "quit_request": response,
        "quit_request_accepted": response.get("status") == "ok",
        "quit_request_id": str(response.get("request_id") or ""),
        "quit_request_status": str(response.get("status") or ""),
    }
    payload.update(verification)
    if bool(payload.get("same_project_editor_closed")):
        payload["closeout_classification"] = "quit_ack_and_process_exit_verified"
        payload["recommended_next_action"] = "none"
        payload["next_distinct_action"] = "rerun_closed_editor_batch_lane"
        print_json(payload)
        return

    if not bool(payload.get("process_visibility_available")):
        payload["closeout_classification"] = "process_visibility_restricted"
        payload["recommended_next_action"] = "restore_host_process_visibility"
        payload["next_distinct_action"] = "restore_host_process_visibility"
        raise ToolInvocationError(
            "process_visibility_restricted",
            (
                "Unity quit request was acknowledged, but host process visibility is unavailable, "
                "so process exit cannot be verified."
            ),
            payload,
        )

    payload["closeout_classification"] = "editor_quit_ack_without_exit"
    payload["recommended_next_action"] = "manual_editor_close"
    payload["next_distinct_action"] = "manual_editor_close_or_terminate_then_verify_closed"
    raise ToolInvocationError(
        "editor_quit_ack_without_exit",
        (
            "Unity quit request was acknowledged, but the same-project editor process is still live. "
            f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
        ),
        payload,
    )


def cmd_verify_editor_closed(args):
    project_root = ensure_project_root(args.project_root)
    payload = verify_project_editor_closed(project_root, args.timeout_ms)
    if bool(payload.get("same_project_editor_closed")):
        print_json(payload)
        return

    if not bool(payload.get("process_visibility_available")):
        raise ToolInvocationError(
            "process_visibility_restricted",
            "Host process visibility is unavailable, so same-project editor closure cannot be verified.",
            payload,
        )

    raise ToolInvocationError(
        "editor_still_running",
        (
            "The same-project Unity editor is still running. "
            f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
        ),
        payload,
    )


def cmd_request_project_refresh(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.project.refresh",
        {
            "forceAssetRefresh": args.force_asset_refresh,
            "resolvePackages": args.resolve_packages,
            "rerunHealthProbe": args.rerun_health_probe,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.project.refresh", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_edm4u_resolve(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.edm4u.resolve",
        {
            "platform": args.platform,
            "force": args.force,
            "refreshBefore": args.refresh_before,
            "refreshAfter": args.refresh_after,
            "menuPathCandidates": args.menu_path_candidate or None,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.edm4u.resolve", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_sdk_dependency_verify(args):
    project_root = ensure_project_root(args.project_root)
    config_path = Path(args.config_file).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise ToolInvocationError("invalid_dependency_verify_config", "Dependency verification config must be a JSON object.")

    response = invoke_bridge(
        str(project_root),
        "unity.sdk.dependency.verify",
        config,
        resolve_operation_default_timeout_ms(project_root, "unity.sdk.dependency.verify", 30000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_editmode_tests(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.tests.run_editmode",
        {
            "testNames": args.test_names or None,
            "groupNames": args.group_names or None,
            "categoryNames": args.category_names or None,
            "assemblyNames": args.assembly_names or None,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.tests.run_editmode", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_playmode_tests(args):
    project_root = ensure_project_root(args.project_root)
    request_args = {
        "testNames": args.test_names or None,
        "groupNames": args.group_names or None,
        "categoryNames": args.category_names or None,
        "assemblyNames": args.assembly_names or None,
    }
    timeout_ms = resolve_operation_default_timeout_ms(project_root, "unity.tests.run_playmode", 300000) if args.timeout_ms is None else args.timeout_ms
    response = invoke_bridge(
        str(project_root),
        "unity.tests.run_playmode",
        request_args,
        timeout_ms,
    )

    error_code = _bridge_error_code(response)
    if error_code == "playmode_state_invalid":
        invoke_bridge(
            str(project_root),
            "unity.playmode.set",
            {"action": "exit"},
            resolve_operation_default_timeout_ms(project_root, "unity.playmode.set", 180000),
        )
        response = invoke_bridge(
            str(project_root),
            "unity.tests.run_playmode",
            request_args,
            timeout_ms,
        )

    print_json(response)


def cmd_request_compile(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.compile.player_scripts",
        {
            "name": args.name,
            "target": args.target,
            "optionFlags": args.option_flags,
            "extraDefines": args.extra_defines,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.compile.player_scripts", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    config_file = Path(args.config_file).expanduser().resolve()
    if not config_file.is_file():
        raise ToolInvocationError("compile_matrix_config_not_found", f"Compile matrix config file not found: {config_file}")

    try:
        matrix_args = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError("compile_matrix_config_invalid", str(exc)) from exc

    response = invoke_bridge(
        str(project_root),
        "unity.compile.matrix",
        matrix_args,
        resolve_operation_default_timeout_ms(project_root, "unity.compile.matrix", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_build_config_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    compile_plan = build_compile_matrix_args_from_build_config(
        project_root=project_root,
        build_config_asset=args.build_config_asset,
        requested_profiles=args.profile,
        requested_targets=args.target,
        stop_on_first_failure=args.stop_on_first_failure,
        tool_error_type=ToolInvocationError,
    )
    response = invoke_bridge(
        str(project_root),
        "unity.compile.matrix",
        compile_plan["matrixArgs"],
        resolve_operation_default_timeout_ms(project_root, "unity.compile.matrix", 300000) if args.timeout_ms is None else args.timeout_ms,
    )

    payload = {
        "build_config_asset": compile_plan["assetPath"],
        "profiles": compile_plan["profiles"],
        "bridge_response": response,
    }
    print_json(payload)


def cmd_open_editor(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    log_path = resolve_editor_log_path(project_root, args.editor_log_path)
    payload = open_unity_editor(project_root, log_path, unity_app, args.background_open)
    payload["project_root"] = str(project_root)
    refresh_project_context(project_root)
    print_json(payload)


def cmd_ensure_ready(args):
    project_root = ensure_project_root(args.project_root)
    log_path = resolve_editor_log_path(project_root, args.editor_log_path)
    package_import_state_before_ready = inspect_light_mcp_import_state(project_root)

    payload: dict[str, Any] = {
        "project_root": str(project_root),
        "editor_log_path": str(log_path),
        "startup_policy": args.startup_policy,
        "package_import_state": package_import_state_before_ready,
        "package_import_state_before_ready": package_import_state_before_ready,
    }
    payload["discovery"] = build_project_discovery_report(project_root)

    try:
        if not args.open_editor:
            maybe_fail_fast_offline_ensure_ready_without_open(
                project_root,
                payload["discovery"],
            )
        current_state = current_project_context_bridge_state(project_root)

        if args.open_editor and bridge_state_is_ready(current_state, args.heartbeat_max_age_seconds):
            payload["launch"] = {
                "reused_existing_editor": True,
                "reused_via": "healthy_bridge_state",
                "editor_pid": int(current_state.get("editor_pid") or 0),
                "unity_version": str(current_state.get("unity_version") or ""),
            }
        elif args.open_editor:
            unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
            payload["launch"] = open_unity_editor(project_root, log_path, unity_app, args.background_open)

        state = wait_for_ready(
            project_root=project_root,
            timeout_ms=args.timeout_ms,
            heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
            startup_policy=args.startup_policy,
            editor_log_path=log_path,
        )
    except ToolInvocationError as exc:
        if str(exc.details.get("fail_fast_reason") or "") == "ensure_ready_without_open_editor_offline":
            raise
        details = dict(exc.details or {})
        package_import_state = inspect_light_mcp_import_state(project_root)
        details["package_import_state"] = package_import_state
        import_state = str(package_import_state.get("import_state") or "")
        discovery = build_project_discovery_report(project_root)
        live_editor_pids: list[int] = []
        for pid_value in discovery.get("detected_editor_pids") or discovery.get("live_project_editor_pids") or []:
            try:
                pid = int(pid_value or 0)
            except (TypeError, ValueError):
                continue
            if pid > 0:
                live_editor_pids.append(pid)
        bridge_state_present = bool(package_import_state.get("bridge_state_present")) or bool(
            current_project_context_bridge_state(project_root)
        )
        if (
            args.open_editor
            and import_state in {"declared_not_resolved", "resolved_not_cached"}
            and live_editor_pids
            and not bridge_state_present
        ):
            details["package_import_diagnosis"] = "package_declared_not_imported"
            details["recommended_next_action"] = "reopen_project_for_clean_resolve"
            details["next_distinct_action"] = "close_and_reopen_unity_to_resolve_package"
            details["recommended_recovery_command"] = (
                f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root.as_posix()} --open-editor"
            )
            details["live_project_editor_pids"] = live_editor_pids
        raise enrich_tool_invocation_error_with_discovery(
            project_root,
            ToolInvocationError(exc.code, exc.message, details),
        )

    payload["bridge_state"] = state
    if payload.get("launch") and not bool(payload["launch"].get("reused_existing_editor")):
        update_host_editor_session_pid(project_root, int(state.get("editor_pid") or 0))
    refresh_project_context(project_root)
    payload["discovery_after_ready"] = build_project_discovery_report(project_root)
    payload["package_dependency"] = inspect_package_dependency_alignment(project_root)
    payload["package_import_state"] = inspect_light_mcp_import_state(project_root)
    payload["package_import_state_after_ready"] = payload["package_import_state"]
    print_json(
        build_ensure_ready_summary(
            project_root,
            payload,
            include_full_payload=bool(getattr(args, "include_full_payload", False)),
        )
    )


def cmd_restore_editor_state(args):
    project_root = ensure_project_root(args.project_root)
    payload = restore_host_opened_editor_state(project_root, args.timeout_ms, request_editor_quit)
    refresh_project_context(project_root)
    payload["post_close_discovery"] = build_project_discovery_report(project_root)
    if bool(payload.get("host_opened_session_found")) and not bool(payload.get("closeout_verified")):
        closeout_classification = str(payload.get("closeout_classification") or "restore_editor_state_incomplete")
        recommended_next_action = str(payload.get("recommended_next_action") or "inspect_project_editor_processes")
        recommended_recovery_command = str(payload.get("recommended_recovery_command") or "")
        message = (
            "Host-opened editor closeout did not reach verified process exit. "
            f"closeout_classification: {closeout_classification} "
            f"recommended_next_action: {recommended_next_action}"
        )
        if recommended_recovery_command:
            message += f" next_step: {recommended_recovery_command}"
        raise ToolInvocationError("restore_editor_state_incomplete", message, payload)
    if bool(getattr(args, "require_closed", False)) and not bool(payload.get("same_project_editor_closed")):
        if not bool(payload.get("process_visibility_available")):
            raise ToolInvocationError(
                "process_visibility_restricted",
                "Host process visibility is unavailable, so restore-editor-state --require-closed cannot verify closure.",
                payload,
            )
        raise ToolInvocationError(
            "restore_editor_state_incomplete",
            (
                "restore-editor-state --require-closed did not reach verified same-project editor closure. "
                f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
            ),
            payload,
        )
    print_json(payload)


def cmd_runtime_config_show(args):
    project_root = ensure_project_root(args.project_root)
    print_json(build_runtime_config_report(project_root))


def cmd_project_discovery_report(args):
    project_root = ensure_project_root(args.project_root)
    print_json(build_project_discovery_report(project_root))


def cmd_registry_context_report(args):
    print_json(build_registry_context_report())


def cmd_registry_prune_contexts(args):
    pruned = prune_stale_project_contexts(
        offline_context_max_idle_seconds=args.offline_context_max_idle_seconds,
        general_context_max_idle_seconds=args.general_context_max_idle_seconds,
    )
    print_json(
        {
            "pruned_count": len(pruned),
            "pruned": pruned,
            "remaining": build_registry_context_report(),
        }
    )
