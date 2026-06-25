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
        "- Restart or refresh required after mutation: "
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
        "detected_client": detect_client_context()["detected_client"],
        "detection_basis": detect_client_context()["detection_basis"],
        "client_context_confidence": detect_client_context()["client_context_confidence"],
        "intended_wiring_target": intended_wiring_target_for_detected_client(str(detect_client_context()["detected_client"])),
        "helper_install_targets": helper_install_targets(),
        "projects": [],
    }
    primary_project_root = explicit_project_roots[0] if explicit_project_roots else (projects[0] if projects else None)
    client_config_targets = build_client_config_targets(primary_project_root)

    git_dependency = default_git_dependency(package_version)
    for project_root in projects:
        unity_version = parse_unity_version(project_root)
        package_dependency = manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME)
        tf_state = classify_test_framework_state(project_root, unity_version)
        bridge_state = bridge_config_state(project_root)
        planned_actions: list[dict[str, Any]] = []
        manual_actions: list[dict[str, Any]] = []

        if package_dependency:
            package_dependency_state = "declared"
        else:
            package_dependency_state = "missing"
            dependency_value = (
                f"file:{Path(local_package_source).expanduser().resolve()}"
                if package_source == "file"
                else git_dependency
            )
            planned_actions.append(
                {
                    "kind": "set_manifest_dependency",
                    "package": LIGHT_MCP_PACKAGE_NAME,
                    "value": dependency_value,
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
                    "recommended_command": f"xuunity_light_unity_mcp.sh install-test-framework --project-root {project_root} --yes --version {tf_state['recommended_dependency_version']}",
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
                    "recommended_command": f"xuunity_light_unity_mcp.sh install-test-framework --project-root {project_root} --yes",
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
    review_notes: list[str] = [
        "Review planned manifest, bridge, and user-level client config changes before applying setup."
    ]
    review_notes.append(
        "setup-plan covers project-level MCP package and bridge mutations only; review client wiring separately with the matching client guide."
    )
    review_notes.append(
        "setup-plan is pre-approval inspection only; it must not refresh installed helper files or mutate user-level client config."
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
        "planned_user_level_config_changes": [
            item["path"]
            for item in client_config_targets
            if item["scope"] == "user"
            and item["selected_by_default"]
            and item["config_action"] != "verify_existing_server_block"
        ],
        "planned_client_config_targets": client_config_targets,
        "client_wiring_review": {
            "status": "required_separate_check",
            "reason": "setup-plan reports likely client config targets, but client wiring still requires an explicit merge-safe review.",
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
            "Run setup-apply with the approved project_root selection after user review."
            if len(projects) > 1
            else "Review the plan, approve mutations, then run setup-apply."
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
