from __future__ import annotations

from server_setup_common import *

def render_preferred_review_summary(
    *,
    detected_client: str,
    detection_basis: list[str],
    client_context_confidence: str,
    intended_wiring_target: str,
    selected_project_roots: list[str],
    additional_discovered_project_roots: list[str],
    helper_targets: list[dict[str, Any]],
    project_file_changes: list[str],
    client_config_targets: list[dict[str, Any]],
    restart_or_refresh_required: list[str],
    recommended_next_step: str,
) -> str:
    lines: list[str] = ["Preflight review"]
    lines.append(f"- Current client: {detected_client}")
    lines.append(f"- Detection basis: {', '.join(detection_basis) if detection_basis else 'none'}")
    lines.append(f"- Client detection confidence: {client_context_confidence}")
    lines.append(f"- Wiring target: {intended_wiring_target}")
    lines.append(
        f"- Unity project root: {selected_project_roots[0] if selected_project_roots else 'none'}"
    )
    lines.append(
        "- Additional discovered Unity projects: "
        + (", ".join(additional_discovered_project_roots) if additional_discovered_project_roots else "none")
    )

    selected_helpers = [item for item in helper_targets if item.get("selected_by_default")]
    if selected_helpers:
        helper = selected_helpers[0]
        lines.append(
            "- Existing helper install: "
            + f"{helper.get('helper_action')} ({helper.get('run_path')})"
        )
    else:
        lines.append("- Existing helper install: manual selection required")

    lines.append(
        "- Planned project file changes: "
        + (", ".join(project_file_changes) if project_file_changes else "none")
    )

    selected_client_targets = [item for item in client_config_targets if item.get("selected_by_default")]
    if selected_client_targets:
        config_parts = [
            f"{item.get('path')} [{item.get('config_action')}]"
            for item in selected_client_targets
        ]
        lines.append("- Planned client config review targets: " + ", ".join(config_parts))
    else:
        lines.append("- Planned client config review targets: none")

    lines.append(
        "- Restart or refresh required after separate client config mutation: "
        + (", ".join(restart_or_refresh_required) if restart_or_refresh_required else "none")
    )
    lines.append(f"- Recommended next step after approval: {recommended_next_step}")
    lines.append("")
    lines.append(
        "Do not run setup-apply, installer commands, helper sync, or client config edits until "
        "the user explicitly approves this review."
    )
    return "\n".join(lines)


def build_setup_plan(
    *,
    workspace_root: str | None,
    project_roots: list[str] | None,
    recursive: bool,
    include_test_framework: str,
    package_source: str,
    package_version: str,
    local_package_source: str,
) -> dict[str, Any]:
    explicit_project_roots = [normalize_project_root(value) for value in project_roots or []]
    projects = discover_unity_projects(
        workspace_root=workspace_root,
        project_roots=project_roots,
        recursive=recursive,
    )
    if not projects:
        raise ToolInvocationError("unity_projects_not_found", "No Unity projects were discovered for setup planning.")

    client_context = detect_client_context()
    normalized_package_version = normalize_package_version(package_version)
    result: dict[str, Any] = {
        "action": "setup_plan",
        "workspace_root": str(Path(workspace_root).expanduser().resolve()) if workspace_root else "",
        "workspace_kind": "multi_project" if len(projects) > 1 else "single_project",
        "requested_project_roots": [str(root) for root in explicit_project_roots],
        "discovered_project_count": len(projects),
        "requires_explicit_project_selection_for_apply": len(projects) > 1,
        "apply_requires_approval": True,
        "recursive": recursive,
        "include_test_framework": include_test_framework,
        "package_source": package_source,
        "requested_package_version": normalized_package_version,
        "detected_client": client_context["detected_client"],
        "detection_basis": client_context["detection_basis"],
        "client_context_confidence": client_context["client_context_confidence"],
        "intended_wiring_target": intended_wiring_target_for_detected_client(str(client_context["detected_client"])),
        "helper_install_targets": helper_install_targets(normalized_package_version),
        "projects": [],
    }
    primary_project_root = explicit_project_roots[0] if explicit_project_roots else (projects[0] if projects else None)
    client_config_targets = build_client_config_targets(primary_project_root)

    for project_root in projects:
        unity_version = parse_unity_version(project_root)
        package_dependency = manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME)
        tf_state = classify_test_framework_state(project_root, unity_version)
        bridge_state = bridge_config_state(project_root)
        planned_actions: list[dict[str, Any]] = []
        manual_actions: list[dict[str, Any]] = []

        package_alignment = classify_light_mcp_dependency(
            package_dependency,
            package_source=package_source,
            package_version=normalized_package_version,
            local_package_source=local_package_source,
        )
        package_dependency_state = str(package_alignment["status"])
        if package_alignment["automatic_update_allowed"] and package_dependency_state != "aligned":
            planned_actions.append(
                {
                    "kind": "set_manifest_dependency",
                    "package": LIGHT_MCP_PACKAGE_NAME,
                    "value": package_alignment["requested_dependency"],
                    "current_value": package_dependency,
                    "expected_current_value": package_dependency,
                    "reason": package_alignment["reason"],
                    "requires_approval": True,
                    "apply_phase": "before_opening_unity",
                }
            )
        elif not package_alignment["runtime_execution_allowed"]:
            manual_actions.append(
                {
                    "kind": "resolve_package_source_or_version_mismatch",
                    "current_value": package_dependency,
                    "requested_value": package_alignment["requested_dependency"],
                    "declared_version": package_alignment["declared_version"],
                    "requested_version": package_alignment["requested_version"],
                    "reason": package_alignment["reason"],
                    "requires_explicit_source_or_version_selection": True,
                }
            )

        if not bridge_state["enabled"]:
            planned_actions.append({"kind": "write_bridge_config"})

        if include_test_framework == "yes":
            if tf_state["status"] == "disabled_missing_dependency":
                planned_actions.append(
                    {
                        "kind": "install_test_framework_dependency",
                        "package": TEST_FRAMEWORK_PACKAGE_NAME,
                        "version": tf_state["recommended_dependency_version"],
                        "reason": "enable_optional_test_capability",
                        "requires_approval": True,
                        "apply_phase": "before_opening_unity",
                    }
                )
            elif tf_state["status"] == "disabled_dependency_too_old" or tf_state["upgrade_recommended"]:
                planned_actions.append(
                    {
                        "kind": "upgrade_test_framework_dependency",
                        "package": TEST_FRAMEWORK_PACKAGE_NAME,
                        "current_version": tf_state["installed_dependency_version"],
                        "version": tf_state["recommended_dependency_version"],
                        "reason": tf_state["dependency_action"],
                        "requires_approval": True,
                        "caution": tf_state["upgrade_caution"],
                        "apply_phase": "before_opening_unity",
                    }
                )
        elif include_test_framework == "auto" and tf_state["status"] == "disabled_dependency_too_old":
            planned_actions.append(
                {
                    "kind": "upgrade_test_framework_dependency",
                    "package": TEST_FRAMEWORK_PACKAGE_NAME,
                    "current_version": tf_state["installed_dependency_version"],
                    "version": tf_state["recommended_dependency_version"],
                    "reason": "required_for_optional_test_capability",
                    "requires_approval": True,
                    "caution": tf_state["upgrade_caution"],
                    "apply_phase": "before_opening_unity",
                }
            )
        elif include_test_framework == "auto" and tf_state["upgrade_recommended"]:
            manual_actions.append(
                {
                    "kind": "optional_test_framework_upgrade",
                    "recommended_command": render_launcher_cli("install-test-framework", project_root, "--yes", "--version", str(tf_state["recommended_dependency_version"])),
                    "current_version": tf_state["installed_dependency_version"],
                    "recommended_version": tf_state["recommended_dependency_version"],
                    "reason": tf_state["dependency_action"],
                    "caution": tf_state["upgrade_caution"],
                }
            )
        elif include_test_framework == "auto" and tf_state["status"] == "disabled_missing_dependency":
            manual_actions.append(
                {
                    "kind": "optional_test_framework_install",
                    "recommended_command": render_launcher_cli("install-test-framework", project_root, "--yes"),
                    "recommended_version": tf_state["recommended_dependency_version"],
                    "reason": "enable_optional_test_capability",
                    "requires_approval": True,
                }
            )

        if planned_actions:
            validation_status = "ready_to_apply"
        elif manual_actions:
            validation_status = "manual_action_recommended"
        else:
            validation_status = "already_configured"
        project_file_changes = planned_project_file_changes(project_root, planned_actions)

        selection_state = "explicit_project_root" if explicit_project_roots else "workspace_discovered"
        result["projects"].append(
            {
                "project_root": str(project_root),
                "selection_state": selection_state,
                "unity_version": unity_version,
                "package_dependency_state": package_dependency_state,
                "package_dependency": package_dependency,
                "package_alignment": package_alignment,
                "runtime_execution_allowed": bool(package_alignment["runtime_execution_allowed"]),
                "bridge_config_state": bridge_state,
                "test_framework_state": tf_state,
                "test_capabilities_state": test_capabilities_state(tf_state),
                "planned_actions": planned_actions,
                "planned_project_file_changes": project_file_changes,
                "manual_actions": manual_actions,
                "validation_status": validation_status,
            }
        )

    aggregate_project_file_changes = sorted(
        {
            changed_path
            for project in result["projects"]
            for changed_path in project.get("planned_project_file_changes") or []
        }
    )
    selected_helpers = [
        item for item in result["helper_install_targets"] if item.get("selected_by_default")
    ]
    selected_client_targets = [
        item for item in client_config_targets if item.get("selected_by_default")
    ]
    alignment_blockers: list[str] = []
    if not all(bool(project.get("runtime_execution_allowed")) for project in result["projects"]):
        alignment_blockers.append("project_package_alignment_required")
    if not selected_helpers or not all(bool(item.get("runtime_execution_allowed")) for item in selected_helpers):
        alignment_blockers.append("helper_install_or_refresh_required")
    if not selected_client_targets:
        alignment_blockers.append("client_selection_required")
    elif not all(bool(item.get("runtime_execution_allowed")) for item in selected_client_targets):
        alignment_blockers.append("client_launcher_install_or_migration_required")

    on_disk_alignment_ready = not alignment_blockers
    host_mutation_required = any(
        str(item.get("helper_action")) != "reuse_current_helper" for item in selected_helpers
    ) or any(
        str(item.get("config_action")) != "verify_existing_server_block"
        for item in selected_client_targets
    )
    result["installation_alignment"] = {
        "status": (
            "on_disk_aligned_live_session_unverified"
            if on_disk_alignment_ready
            else "blocked_until_upgrade_or_wiring_fix"
        ),
        "on_disk_alignment_ready": on_disk_alignment_ready,
        "runtime_execution_allowed": False,
        "runtime_execution_allowed_after_live_session_proof": on_disk_alignment_ready,
        "current_mcp_session_safe": False,
        "live_mcp_session_status": "unverified",
        "live_session_proof_required": True,
        "required_live_server_version": normalized_package_version,
        "client_restart_required_after_host_changes": host_mutation_required,
        "blockers": alignment_blockers,
        "safety_rule": (
            "Do not run Unity operations, ensure-ready, or tests through an existing helper/session "
            "until package, helper, and native client launcher all match the requested release."
        ),
    }
    result["setup_status"] = (
        "on_disk_aligned_live_session_unverified"
        if on_disk_alignment_ready
        else "upgrade_or_wiring_required"
    )
    review_notes: list[str] = [
        "Review planned project manifest and bridge changes before applying setup."
    ]
    review_notes.append(
        "setup-plan covers project-level MCP package and bridge mutations only; review client wiring separately with the matching client guide."
    )
    review_notes.append(
        "setup-plan is pre-approval inspection only; it must not refresh installed helper files or mutate user-level client config."
    )
    review_notes.append(
        "A stale or unknown helper must not be executed to continue setup; refresh it from the requested source checkout first."
    )
    if explicit_project_roots:
        review_notes.append("The plan is scoped to the explicitly requested Unity project roots only.")
    elif len(projects) > 1:
        review_notes.append(
            "Multiple Unity projects were discovered. Choose the intended target project before running setup-apply."
        )

    result["preflight_review"] = {
        "review_required": True,
        "detected_project_count": len(projects),
        "selected_project_count": len(projects),
        "selected_project_roots": [item["project_root"] for item in result["projects"]],
        "mutating_actions_require_approval": True,
        "planned_project_file_changes": aggregate_project_file_changes,
        "planned_user_level_config_changes": [],
        "planned_client_config_targets": client_config_targets,
        "client_wiring_review": {
            "status": "required_separate_check",
            "reason": "setup-plan reports likely client config targets for a separate client wiring review; setup-apply does not mutate them.",
            "detected_client": result["detected_client"],
            "detection_basis": result["detection_basis"],
            "client_context_confidence": result["client_context_confidence"],
            "restart_or_refresh_required": sorted(
                {
                    item["restart_or_refresh_required"]
                    for item in client_config_targets
                    if item["selected_by_default"]
                }
            ),
        },
        "notes": review_notes,
        "recommended_next_step": (
            "Resolve the reported package/helper/client alignment blockers, restart the MCP client after host changes, then prove the live server version before Unity operations."
            if alignment_blockers
            else (
                (
                    "Run setup-apply with the approved project_root selection after user review."
                    if len(projects) > 1
                    else "Review the plan, approve mutations, then run setup-apply."
                )
                if aggregate_project_file_changes
                else (
                    "Restart or refresh the MCP client, verify the live server reports the requested version, "
                    "list XUUnity tools, and run unity_status_summary before Unity operations."
                )
            )
        ),
    }
    result["preflight_review"]["preferred_review_summary"] = render_preferred_review_summary(
        detected_client=str(result["detected_client"]),
        detection_basis=list(result["detection_basis"]),
        client_context_confidence=str(result["client_context_confidence"]),
        intended_wiring_target=str(result["intended_wiring_target"]),
        selected_project_roots=list(result["preflight_review"]["selected_project_roots"]),
        additional_discovered_project_roots=[
            item["project_root"]
            for item in result["projects"]
            if item["project_root"] not in result["preflight_review"]["selected_project_roots"]
        ],
        helper_targets=list(result["helper_install_targets"]),
        project_file_changes=list(result["preflight_review"]["planned_project_file_changes"]),
        client_config_targets=list(result["preflight_review"]["planned_client_config_targets"]),
        restart_or_refresh_required=list(result["preflight_review"]["client_wiring_review"]["restart_or_refresh_required"]),
        recommended_next_step=str(result["preflight_review"]["recommended_next_step"]),
    )
    return result


__all__ = [name for name in globals() if not name.startswith("__")]
