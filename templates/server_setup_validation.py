from __future__ import annotations

from server_setup_common import *
from server_setup_apply import remove_lock_entries, set_manifest_dependency

def install_test_framework(project_root: Path, *, approve: bool, version: str = "") -> dict[str, Any]:
    if not approve:
        raise ToolInvocationError("approval_required", "install-test-framework requires --yes.")
    unity_version = parse_unity_version(project_root)
    selected_version = version.strip() if version else recommended_test_framework_version(unity_version)
    if not version_at_least(selected_version, TEST_FRAMEWORK_MINIMUM_VERSION):
        raise ToolInvocationError(
            "dependency_version_too_old",
            f"{TEST_FRAMEWORK_PACKAGE_NAME} {selected_version} is older than the minimum supported version {TEST_FRAMEWORK_MINIMUM_VERSION}.",
            {
                "dependency": TEST_FRAMEWORK_PACKAGE_NAME,
                "requested_version": selected_version,
                "minimum_dependency_version": TEST_FRAMEWORK_MINIMUM_VERSION,
                "recommended_dependency_version": recommended_test_framework_version(unity_version),
                "recommendation_basis": "unity_version_policy",
            },
        )
    before = classify_test_framework_state(project_root, unity_version)
    installed_before = str(before.get("installed_dependency_version") or "")
    if installed_before and version_at_least(installed_before, selected_version):
        return {
            "action": "install_test_framework",
            "project_root": str(project_root),
            "unity_version": unity_version,
            "dependency": TEST_FRAMEWORK_PACKAGE_NAME,
            "requested_version": selected_version,
            "recommended_dependency_version": recommended_test_framework_version(unity_version),
            "recommendation_basis": "unity_version_policy",
            "state_before": before,
            "state_after": before,
            "outcome": "already_suitable",
            "upgrade_recommended": bool(before.get("upgrade_recommended")),
            "packages_lock_entries_removed": [],
            "mutation_mode": "offline_manifest",
            "next_action": "open Unity or run ensure-ready --open-editor, then request capabilities when test operations are expected",
        }
    set_manifest_dependency(project_root, TEST_FRAMEWORK_PACKAGE_NAME, selected_version)
    removed = remove_lock_entries(project_root, [TEST_FRAMEWORK_PACKAGE_NAME])
    after = classify_test_framework_state(project_root, unity_version)
    return {
        "action": "install_test_framework",
        "project_root": str(project_root),
        "unity_version": unity_version,
        "dependency": TEST_FRAMEWORK_PACKAGE_NAME,
        "requested_version": selected_version,
        "recommended_dependency_version": recommended_test_framework_version(unity_version),
        "recommendation_basis": "unity_version_policy",
        "state_before": before,
        "state_after": after,
        "outcome": "installed" if not installed_before else "upgraded",
        "upgrade_recommended_before": bool(before.get("upgrade_recommended")),
        "upgrade_caution": str(before.get("upgrade_caution") or ""),
        "packages_lock_entries_removed": removed,
        "mutation_mode": "offline_manifest",
        "apply_phase": "before_opening_unity",
        "next_action": "open Unity or run ensure-ready --open-editor so Unity resolves packages, then run request-health-probe or validate-setup",
    }


def validate_setup(
    project_root: Path,
    *,
    include_tests: bool = False,
    expected_package_version: str = "",
) -> dict[str, Any]:
    unity_version = parse_unity_version(project_root)
    package_dependency = manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME)
    bridge_state = bridge_config_state(project_root)
    import_state = inspect_light_mcp_import_state(project_root)
    tf_state = classify_test_framework_state(project_root, unity_version)
    normalized_expected_version = normalize_package_version(expected_package_version)
    package_alignment: dict[str, Any] = {
        "status": "not_checked",
        "current_dependency": package_dependency,
        "requested_version": normalized_expected_version,
    }
    if package_dependency and normalized_expected_version:
        package_alignment = classify_light_mcp_dependency(
            package_dependency,
            package_source="git",
            package_version=normalized_expected_version,
            local_package_source="",
        )
    blockers: list[str] = []
    if not package_dependency:
        blockers.append("mcp_package_missing")
    elif (
        normalized_expected_version
        and canonical_light_mcp_git_version(package_dependency)
        and package_alignment.get("status") != "aligned"
    ):
        blockers.append("mcp_package_version_mismatch")
    if not bridge_state["enabled"]:
        blockers.append("bridge_config_missing")
    if include_tests and not tf_state["supported"]:
        blockers.append("test_framework_unavailable")
    offline_status = "ready" if not blockers else "blocked"
    return {
        "action": "validate_setup",
        "project_root": str(project_root),
        "unity_version": unity_version,
        "package_dependency_state": "declared" if package_dependency else "missing",
        "package_dependency": package_dependency,
        "expected_package_version": normalized_expected_version,
        "package_alignment": package_alignment,
        "package_import_state": import_state,
        "bridge_config_state": bridge_state,
        "test_framework_state": tf_state,
        "test_capabilities_state": test_capabilities_state(tf_state),
        "validation_status": offline_status,
        "offline_validation_status": offline_status,
        "readiness_scope": "offline_manifest_and_bridge_config_only",
        "readiness_scope_note": (
            "validate-setup checks the canonical package pin when an expected release is supplied, "
            "but does not prove Unity package resolution, package import, or live bridge heartbeat; "
            "run ensure-ready --open-editor only after package/helper/client alignment is ready."
        ),
        "blockers": blockers,
    }


def require_test_framework_capability_for_batch(project_root: Path) -> dict[str, Any]:
    unity_version = parse_unity_version(project_root)
    state = classify_test_framework_state(project_root, unity_version)
    if bool(state.get("supported")):
        return state

    recommended_version = str(state.get("recommended_dependency_version") or "")
    install_command = render_launcher_cli(
        "install-test-framework",
        project_root,
        "--yes",
        *(("--version", recommended_version) if recommended_version else ()),
    )
    status = str(state.get("status") or "error")
    if status == "unsupported":
        recommended_next_action = "use_supported_unity_version"
        next_distinct_action = "open_project_with_unity_2021_3_or_newer"
    elif status == "disabled_dependency_too_old":
        recommended_next_action = "upgrade_optional_test_framework"
        next_distinct_action = "upgrade_test_framework_then_rerun_batch"
    else:
        recommended_next_action = "install_optional_test_framework"
        next_distinct_action = "install_test_framework_then_rerun_batch"

    raise ToolInvocationError(
        "test_capability_unavailable",
        "Batch EditMode tests require the optional Test Framework capability.",
        {
            "capability": "tests",
            "capability_status": status,
            "capability_define": TEST_FRAMEWORK_CAPABILITY_DEFINE,
            "dependency": TEST_FRAMEWORK_PACKAGE_NAME,
            "installed_dependency_version": str(state.get("installed_dependency_version") or ""),
            "minimum_dependency_version": str(state.get("minimum_dependency_version") or ""),
            "recommended_dependency_version": recommended_version,
            "recommendation_basis": str(state.get("recommendation_basis") or ""),
            "recommended_action": str(state.get("recommended_action") or ""),
            "dependency_action": str(state.get("dependency_action") or ""),
            "upgrade_caution": str(state.get("upgrade_caution") or ""),
            "recommended_next_action": recommended_next_action,
            "next_distinct_action": next_distinct_action,
            "install_command": install_command,
            "unity_version": unity_version,
        },
    )


__all__ = [name for name in globals() if not name.startswith("__")]
