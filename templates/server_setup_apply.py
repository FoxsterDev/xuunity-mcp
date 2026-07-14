from __future__ import annotations

from server_setup_common import *

def remove_lock_entries(project_root: Path, package_names: list[str]) -> list[str]:
    lock_path = project_root / "Packages" / "packages-lock.json"
    if not lock_path.is_file():
        return []
    try:
        payload = read_json(lock_path)
    except Exception:
        return []
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        return []
    removed: list[str] = []
    for package_name in package_names:
        if package_name in dependencies:
            dependencies.pop(package_name, None)
            removed.append(package_name)
    if removed:
        write_json(lock_path, payload)
    return removed


def set_manifest_dependency(project_root: Path, package_name: str, value: str) -> None:
    manifest_path = project_root / "Packages" / "manifest.json"
    payload = load_manifest(project_root)
    payload["dependencies"][package_name] = value
    write_json(manifest_path, payload)


def write_bridge_config(project_root: Path) -> None:
    config_path = project_root / "Library" / "XUUnityLightMcp" / "config" / "bridge_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        config_path,
        {
            "enabled": True,
            "heartbeat_interval_ms": 2000,
            "pump_interval_ms": 500,
            "transport": "tcp_loopback",
            "loopback_host": "127.0.0.1",
            "loopback_port": 0,
        },
    )


def apply_setup_plan(
    plan: dict[str, Any],
    *,
    approve: bool,
    selected_project_roots: list[str] | None = None,
) -> dict[str, Any]:
    if not approve:
        raise ToolInvocationError("approval_required", "setup-apply requires --yes or approve=true.")
    if not isinstance(plan, dict):
        raise ToolInvocationError("invalid_setup_plan", "Setup plan must be a JSON object.")
    plan_projects = list(plan.get("projects") or [])
    if not plan_projects:
        raise ToolInvocationError("invalid_setup_plan", "Setup plan does not contain any projects to apply.")

    normalized_selected_roots = [normalize_project_root(value) for value in selected_project_roots or []]
    available_project_roots = [str(normalize_project_root(str(project.get("project_root") or ""))) for project in plan_projects]
    if len(plan_projects) > 1 and not normalized_selected_roots:
        raise ToolInvocationError(
            "explicit_project_selection_required",
            "setup-apply refuses to mutate a multi-project plan without an explicit project selection.",
            {
                "available_project_roots": available_project_roots,
                "recommended_next_step": "Re-run setup-apply with one or more --project-root values chosen from the plan.",
            },
        )

    allowed_roots = {str(root) for root in normalized_selected_roots}
    unknown_selected_roots = sorted(allowed_roots.difference(available_project_roots))
    if unknown_selected_roots:
        raise ToolInvocationError(
            "selected_project_not_in_plan",
            "One or more selected project roots are not present in the approved setup plan.",
            {
                "selected_project_roots": sorted(allowed_roots),
                "available_project_roots": available_project_roots,
                "unknown_selected_project_roots": unknown_selected_roots,
            },
        )

    applied_projects: list[dict[str, Any]] = []
    skipped_project_roots: list[str] = []
    for project in plan_projects:
        project_root = normalize_project_root(str(project.get("project_root") or ""))
        if allowed_roots and str(project_root) not in allowed_roots:
            skipped_project_roots.append(str(project_root))
            continue
        applied_actions: list[dict[str, Any]] = []
        for action in project.get("planned_actions") or []:
            kind = str(action.get("kind") or "")
            if kind == "set_manifest_dependency":
                package_name = str(action.get("package") or "")
                value = str(action.get("value") or "")
                if "expected_current_value" in action:
                    expected_current_value = str(action.get("expected_current_value") or "")
                    actual_current_value = manifest_dependency(project_root, package_name)
                    if actual_current_value != expected_current_value:
                        raise ToolInvocationError(
                            "setup_plan_stale_dependency_changed",
                            "The package dependency changed after setup-plan was reviewed; refusing to apply a stale plan.",
                            {
                                "project_root": str(project_root),
                                "package": package_name,
                                "expected_current_value": expected_current_value,
                                "actual_current_value": actual_current_value,
                                "requested_value": value,
                                "recommended_next_step": "Run setup-plan again and review the new dependency state.",
                            },
                        )
                set_manifest_dependency(project_root, package_name, value)
                removed = remove_lock_entries(project_root, [package_name])
                applied_actions.append({**action, "packages_lock_entries_removed": removed})
            elif kind == "write_bridge_config":
                write_bridge_config(project_root)
                applied_actions.append(action)
            elif kind in {"install_test_framework_dependency", "upgrade_test_framework_dependency"}:
                version = str(action.get("version") or recommended_test_framework_version(parse_unity_version(project_root)))
                unity_version = parse_unity_version(project_root)
                before = classify_test_framework_state(project_root, unity_version)
                installed_before = str(before.get("installed_dependency_version") or "")
                if installed_before and version_at_least(installed_before, version):
                    applied_actions.append(
                        {
                            **action,
                            "version": version,
                            "outcome": "already_suitable",
                            "state_before": before,
                            "packages_lock_entries_removed": [],
                        }
                    )
                    continue
                set_manifest_dependency(project_root, TEST_FRAMEWORK_PACKAGE_NAME, version)
                removed = remove_lock_entries(project_root, [TEST_FRAMEWORK_PACKAGE_NAME])
                after = classify_test_framework_state(project_root, unity_version)
                applied_actions.append(
                    {
                        **action,
                        "version": version,
                        "outcome": "installed" if not installed_before else "upgraded",
                        "state_before": before,
                        "state_after": after,
                        "packages_lock_entries_removed": removed,
                    }
                )
        applied_projects.append({"project_root": str(project_root), "applied_actions": applied_actions})

    return {
        "action": "setup_apply",
        "approved": True,
        "selected_project_roots": [item["project_root"] for item in applied_projects],
        "skipped_project_roots": skipped_project_roots,
        "projects": applied_projects,
    }


def remove_toml_server_block(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.splitlines(keepends=True)
    start_index = -1
    for index, line in enumerate(lines):
        if line.strip() == "[mcp_servers.xuunity_light_unity]":
            start_index = index
            break
    if start_index < 0:
        return False
    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        if lines[index].lstrip().startswith("["):
            end_index = index
            break
    new_text = "".join(lines[:start_index] + lines[end_index:])
    path.write_text(new_text, encoding="utf-8")
    return True


def remove_json_server_block(path: Path) -> bool:
    try:
        payload = read_json(path)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict) or "xuunity_light_unity" not in servers:
        return False
    servers.pop("xuunity_light_unity", None)
    write_json(path, payload)
    return True


def remove_client_server_block(target: dict[str, Any]) -> bool:
    path = Path(str(target.get("path") or "")).expanduser()
    if not path.is_file():
        return False
    config_action = str(target.get("config_action") or "")
    if not bool(target.get("remove_server_block")) and config_action != "remove_xuunity_server_block":
        return False
    config_format = str(target.get("config_format") or "")
    if not config_format:
        if path.suffix.lower() == ".toml":
            config_format = "toml"
        else:
            config_format = "json"
    if config_format == "toml":
        return remove_toml_server_block(path)
    return remove_json_server_block(path)


def safe_remove_project_bridge_directory(project_root: Path, path_text: str) -> bool:
    bridge_root = project_bridge_root(project_root).resolve()
    target = Path(path_text).expanduser().resolve()
    if target != bridge_root:
        raise ToolInvocationError(
            "unsafe_bridge_removal_path",
            "Refusing to remove a project bridge directory that does not match the selected project root.",
            {"project_root": str(project_root), "requested_path": str(target), "expected_path": str(bridge_root)},
        )
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True


def safe_remove_helper_install(path_text: str) -> bool:
    install_dir = Path(path_text).expanduser().resolve()
    if install_dir.name != "xuunity-mcp":
        raise ToolInvocationError(
            "unsafe_helper_removal_path",
            "Refusing to remove a helper install path with an unexpected directory name.",
            {"requested_path": str(install_dir)},
        )
    if not install_dir.exists():
        return False
    if not install_dir.is_dir():
        raise ToolInvocationError(
            "unsafe_helper_removal_path",
            "Refusing to remove a helper install path that is not a directory.",
            {"requested_path": str(install_dir)},
        )
    shutil.rmtree(install_dir)
    return True


def apply_uninstall_plan(plan: dict[str, Any], *, approve: bool) -> dict[str, Any]:
    if not approve:
        raise ToolInvocationError("approval_required", "uninstall-apply requires --yes or approve=true.")
    if not isinstance(plan, dict) or plan.get("action") != "uninstall_plan":
        raise ToolInvocationError("invalid_uninstall_plan", "Uninstall plan must be a JSON object from uninstall-plan.")
    requested_mode = str(plan.get("mode") or "")
    if requested_mode not in UNINSTALL_MODE_INPUTS:
        raise ToolInvocationError(
            "invalid_uninstall_mode",
            f"Unsupported uninstall mode in plan: {requested_mode}",
            {"supported_modes": sorted(UNINSTALL_MODE_INPUTS)},
        )
    mode = normalize_uninstall_mode(requested_mode)

    applied_projects: list[dict[str, Any]] = []
    for project in list(plan.get("projects") or []):
        project_root = normalize_project_root(str(project.get("project_root") or ""))
        applied_actions: list[dict[str, Any]] = []
        for action in list(project.get("planned_actions") or []):
            kind = str(action.get("kind") or "")
            if kind == "remove_manifest_dependency":
                package_name = str(action.get("package") or LIGHT_MCP_PACKAGE_NAME)
                removed_manifest_dependency = remove_manifest_dependency(project_root, package_name)
                removed_lock_entries = remove_lock_entries(project_root, [package_name])
                applied_actions.append(
                    {
                        **action,
                        "removed_manifest_dependency": removed_manifest_dependency,
                        "packages_lock_entries_removed": removed_lock_entries,
                    }
                )
            elif kind == "remove_project_bridge_directory":
                removed = safe_remove_project_bridge_directory(project_root, str(action.get("path") or ""))
                applied_actions.append({**action, "removed": removed})
        applied_projects.append({"project_root": str(project_root), "applied_actions": applied_actions})

    applied_client_config_changes: list[dict[str, Any]] = []
    for target in list((plan.get("preflight_review") or {}).get("planned_client_config_targets") or []):
        if not target.get("remove_server_block"):
            continue
        removed = remove_client_server_block(target)
        applied_client_config_changes.append(
            {
                "client_id": target.get("client_id"),
                "path": target.get("path"),
                "scope": target.get("scope"),
                "removed_server_block": removed,
            }
        )

    applied_helper_changes: list[dict[str, Any]] = []
    for target in list((plan.get("preflight_review") or {}).get("planned_helper_install_targets") or []):
        if not target.get("remove_helper_install"):
            continue
        removed = safe_remove_helper_install(str(target.get("install_dir") or ""))
        applied_helper_changes.append(
            {
                "client_id": target.get("client_id"),
                "install_dir": target.get("install_dir"),
                "removed_helper_install": removed,
            }
        )

    return {
        "action": "uninstall_apply",
        "approved": True,
        "mode": mode,
        "selected_client": plan.get("selected_client"),
        "projects": applied_projects,
        "client_config_changes": applied_client_config_changes,
        "helper_install_changes": applied_helper_changes,
        "restart_or_refresh_required": list((plan.get("preflight_review") or {}).get("restart_or_refresh_required") or []),
        "remaining_risks": [
            "Unity may keep stale Library cache data until the editor re-resolves packages; stale cache alone is not active installation.",
            "Restart or refresh any client whose MCP config block was removed.",
        ],
    }


__all__ = [name for name in globals() if not name.startswith("__")]
