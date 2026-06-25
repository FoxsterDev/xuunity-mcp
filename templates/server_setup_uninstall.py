from __future__ import annotations

from server_setup_common import *

def build_uninstall_plan(
    *,
    mode: str,
    project_roots: list[str] | None,
    workspace_root: str | None = None,
    recursive: bool = False,
    client: str | None = None,
    include_other_client_helpers: bool = False,
) -> dict[str, Any]:
    requested_mode = str(mode or "")
    if requested_mode not in UNINSTALL_MODE_INPUTS:
        raise ToolInvocationError(
            "invalid_uninstall_mode",
            f"Unsupported uninstall mode: {requested_mode}",
            {"supported_modes": sorted(UNINSTALL_MODE_INPUTS)},
        )
    mode = normalize_uninstall_mode(requested_mode)
    if mode == UNINSTALL_MODE_PROJECT_ONLY and not project_roots:
        raise ToolInvocationError(
            "project_root_required",
            f"{UNINSTALL_MODE_PROJECT_ONLY} requires --project-root.",
            {"recommended_next_step": "Run uninstall-plan with --project-root /path/to/UnityProject."},
        )
    normalized_project_roots = [normalize_project_root(value) for value in project_roots or []]
    detected = detect_client_context()
    selected_client = selected_uninstall_client(client)
    primary_project_root = normalized_project_roots[0] if normalized_project_roots else None
    client_config_targets = uninstall_client_config_targets(
        mode=mode,
        selected_client=selected_client,
        project_root=primary_project_root,
    )
    helper_targets = uninstall_helper_targets(
        mode=mode,
        selected_client=selected_client,
        include_other_client_helpers=include_other_client_helpers,
    )

    projects: list[dict[str, Any]] = []
    aggregate_project_file_changes: list[str] = []
    for project_root in normalized_project_roots:
        actions = uninstall_project_actions(project_root)
        file_changes = uninstall_project_file_changes(project_root, actions)
        aggregate_project_file_changes.extend(file_changes)
        projects.append(
            {
                "project_root": str(project_root),
                "selection_state": "explicit_project_root",
                "unity_version": parse_unity_version(project_root),
                "package_dependency": manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME),
                "bridge_directory": str(project_bridge_root(project_root)),
                "planned_actions": actions,
                "planned_project_file_changes": file_changes,
                "cleanup_status": "ready_to_apply" if actions else "already_clean",
            }
        )

    user_config_changes = [
        str(target.get("path"))
        for target in client_config_targets
        if target.get("scope") == "user" and target.get("remove_server_block")
    ]
    helper_removals = [
        str(target.get("install_dir"))
        for target in helper_targets
        if target.get("remove_helper_install")
    ]
    helper_kept = [
        str(target.get("install_dir"))
        for target in helper_targets
        if not target.get("remove_helper_install")
    ]
    restart_or_refresh_required = sorted(
        {
            str(target.get("restart_or_refresh_required"))
            for target in client_config_targets
            if target.get("remove_server_block")
        }
    )
    additional_projects = additional_workspace_projects(
        workspace_root=workspace_root,
        selected_project_roots=normalized_project_roots,
        recursive=recursive,
    )
    plan: dict[str, Any] = {
        "action": "uninstall_plan",
        "mode": mode,
        "workspace_root": str(Path(workspace_root).expanduser().resolve()) if workspace_root else "",
        "recursive": recursive,
        "requested_project_roots": [str(root) for root in normalized_project_roots],
        "additional_discovered_project_roots": additional_projects,
        "detected_client": detected["detected_client"],
        "detection_basis": detected["detection_basis"],
        "client_context_confidence": detected["client_context_confidence"],
        "selected_client": selected_client,
        "include_other_client_helpers": include_other_client_helpers,
        "apply_requires_approval": True,
        "projects": projects,
        "preflight_review": {
            "review_required": True,
            "mode": mode,
            "selected_project_roots": [str(root) for root in normalized_project_roots],
            "additional_discovered_project_roots": additional_projects,
            "planned_project_file_changes": sorted(set(aggregate_project_file_changes)),
            "planned_user_level_config_changes": user_config_changes,
            "planned_client_config_targets": client_config_targets,
            "planned_helper_install_targets": helper_targets,
            "helper_installs_to_remove": helper_removals,
            "helper_installs_to_keep": helper_kept,
            "restart_or_refresh_required": restart_or_refresh_required,
            "mutating_actions_require_approval": True,
            "recommended_next_step": "Review the uninstall plan, approve mutations, then run uninstall-apply.",
        },
    }
    plan["preflight_review"]["preferred_review_summary"] = render_uninstall_review_summary(
        mode=mode,
        detected_client=str(detected["detected_client"]),
        detection_basis=list(detected["detection_basis"]),
        client_context_confidence=str(detected["client_context_confidence"]),
        selected_client=selected_client,
        selected_project_roots=[str(root) for root in normalized_project_roots],
        additional_discovered_project_roots=additional_projects,
        project_file_changes=sorted(set(aggregate_project_file_changes)),
        user_config_changes=user_config_changes,
        helper_removals=helper_removals,
        helper_kept=helper_kept,
        restart_or_refresh_required=restart_or_refresh_required,
    )
    return plan


__all__ = [name for name in globals() if not name.startswith("__")]
