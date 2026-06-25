# -*- coding: utf-8 -*-
from __future__ import annotations

from server_cli_shared import *

def cmd_setup_plan(args):
    payload = build_setup_plan(
        workspace_root=args.workspace_root,
        project_roots=list(args.project_root or []),
        recursive=bool(args.recursive),
        include_test_framework=args.include_test_framework,
        package_source=args.package_source,
        package_version=args.package_version or default_light_mcp_package_version(),
        local_package_source=args.local_package_source or str(default_local_package_source()),
    )
    print_json(payload)


def cmd_setup_apply(args):
    plan_path = Path(args.plan_file).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path).resolve()
    plan = read_json(plan_path)
    payload = apply_setup_plan(
        plan,
        approve=bool(args.yes),
        selected_project_roots=list(args.project_root or []),
    )
    print_json(payload)


def cmd_uninstall_plan(args):
    payload = build_uninstall_plan(
        mode=args.mode,
        project_roots=list(args.project_root or []),
        workspace_root=args.workspace_root,
        recursive=bool(args.recursive),
        client=args.client,
        include_other_client_helpers=bool(args.include_other_client_helpers),
    )
    print_json(payload)


def cmd_uninstall_apply(args):
    plan_path = Path(args.plan_file).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path).resolve()
    plan = read_json(plan_path)
    payload = apply_uninstall_plan(plan, approve=bool(args.yes))
    print_json(payload)


def cmd_validate_setup(args):
    project_root = normalize_setup_project_root(args.project_root)
    payload = validate_setup(project_root, include_tests=bool(args.include_tests))
    print_json(payload)
    if payload.get("validation_status") != "ready":
        raise SystemExit(1)


def cmd_install_test_framework(args):
    project_root = normalize_setup_project_root(args.project_root)
    payload = install_test_framework(project_root, approve=bool(args.yes), version=args.version or "")
    print_json(payload)


def cmd_license_capabilities(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    payload = build_license_capabilities(
        project_root=project_root,
        unity_app=unity_app,
        refresh=bool(args.refresh),
        timeout_ms=int(args.timeout_ms or 30000),
    )
    print_json(payload)


def cmd_request_install_test_framework(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.package.install_test_framework",
        {
            "approve": bool(args.yes),
            "version": args.version or "",
        },
        resolve_operation_default_timeout_ms(project_root, "unity.package.install_test_framework", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)
