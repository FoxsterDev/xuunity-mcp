from __future__ import annotations

from server_cli_shared import *
from server_sdk_dependency_verify import run_sdk_dependency_verify
from server_sdk_diff_guard import run_sdk_generated_diff_guard
from server_sdk_package_restore import run_sdk_package_restore


def cmd_request_sdk_package_restore(args):
    project_root = ensure_project_root(args.project_root)
    payload = run_sdk_package_restore(
        project_root=project_root,
        unity_app=args.unity_app,
        timeout_ms=args.timeout_ms,
        stable_idle_ticks=args.stable_idle_ticks,
        log_path=args.batch_log_path,
        result_path=args.result_file,
        dry_run=bool(args.dry_run),
    )
    print_json(payload)
    if not bool(payload.get("decision_ready")) and not bool(args.dry_run):
        raise SystemExit(1)


def cmd_request_sdk_dependency_verify(args):
    project_root = ensure_project_root(args.project_root)
    config = load_json_file(args.config_file, "invalid_dependency_verify_config")
    if not isinstance(config, dict):
        raise ToolInvocationError("invalid_dependency_verify_config", "Dependency verification config must be a JSON object.")
    payload = run_sdk_dependency_verify(project_root=project_root, config=config)
    print_json(
        {
            "status": "ok",
            "payload_type": "unity.sdk.dependency.verify",
            "payload_json": json.dumps(payload, ensure_ascii=True),
        }
    )
    if payload.get("status") != "passed":
        raise SystemExit(1)


def cmd_sdk_generated_diff_guard(args):
    project_root = ensure_project_root(args.project_root)
    config = load_json_file(args.config_file, "sdk_generated_diff_guard_config_invalid")
    result = run_sdk_generated_diff_guard(
        project_root=project_root,
        config=config,
        report_file=getattr(args, "report_file", "") or "",
    )
    print_json(result)
    if result.get("verdict") != "passed":
        raise SystemExit(1)
