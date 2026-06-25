# -*- coding: utf-8 -*-
from __future__ import annotations

from server_cli_shared import *


def cmd_batch_build_player(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    build_target = str(args.build_target or "").strip()
    if not build_target:
        raise ToolInvocationError("missing_build_target", "--build-target is required.")

    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_build_log_path(project_root, build_target)
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_build_result_path(project_root, build_target)
    )
    output_path = resolve_batch_build_output_path(project_root, args.output_path)
    from server_host_platform import is_wsl, wsl_to_windows_path

    output_path_windows = wsl_to_windows_path(output_path) if is_wsl() else output_path
    result_path_host = wsl_to_windows_path(result_path) if is_wsl() else str(result_path)
    scene_paths = list(args.scene_path or [])
    build_options = list(args.build_option or [])
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    artifact_probe_warn_only = bool(getattr(args, "artifact_probe_warn_only", False))

    command = build_plain_batch_build_command(
        project_root=project_root,
        unity_app=unity_app,
        log_path=log_path,
        result_path=result_path,
        build_target=build_target,
        output_path=output_path_windows,
        scene_paths=scene_paths,
        build_options=build_options,
    )

    payload: dict[str, Any] = {
        "action": "plain_batch_build",
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "build_target": build_target,
        "output_path": output_path,
        "scene_paths": scene_paths,
        "build_options": build_options,
        "log_path": str(log_path),
        "result_file": str(result_path),
        "command": command,
        "dry_run": args.dry_run,
        "artifact_probe_enabled": artifact_probe_config is not None,
        "artifact_probe_warn_only": artifact_probe_warn_only,
    }
    run_batch_operation(
        project_root=project_root,
        unity_app=unity_app,
        command=command,
        payload=payload,
        log_path=log_path,
        result_path=result_path,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
        workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
        side_effect_mode=getattr(args, "side_effect_mode", "git"),
        side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
        progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
        progress_stdout=progress_stdout_enabled(args),
        batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
        refresh_license=bool(getattr(args, "refresh_license", False)),
        gui_operation="unity.build_player",
        gui_operation_args={
            "buildTarget": build_target,
            "outputPath": output_path_windows,
            "resultFile": result_path_host,
            "scenePaths": scene_paths,
            "buildOptions": build_options,
        },
        artifact_probe_config=artifact_probe_config,
        artifact_probe_path_override=output_path,
        artifact_probe_warn_only=artifact_probe_warn_only,
        last_known_output_path=output_path,
    )
