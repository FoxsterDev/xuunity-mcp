from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json, write_json

LIGHT_MCP_PACKAGE_NAME = "com.xuunity.light-mcp"
TEST_FRAMEWORK_PACKAGE_NAME = "com.unity.test-framework"
TEST_FRAMEWORK_MINIMUM_VERSION = "1.1.33"
TEST_FRAMEWORK_CAPABILITY_DEFINE = "XUUNITY_LIGHT_MCP_TESTS_CAPABILITY"
DEFAULT_GIT_REPO_URL = "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git"


def parse_unity_version(project_root: Path) -> str:
    version_path = project_root / "ProjectSettings" / "ProjectVersion.txt"
    try:
        text = version_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("m_EditorVersion:"):
            return line.split(":", 1)[1].strip()
    return ""


def unity_major(unity_version: str) -> int:
    match = re.match(r"^(\d+)", unity_version or "")
    return int(match.group(1)) if match else 0


def recommended_test_framework_version(unity_version: str) -> str:
    return "1.5.1" if unity_major(unity_version) >= 6000 else "1.1.33"


def version_tuple(version: str) -> tuple[int, int, int]:
    values = [int(item) for item in re.findall(r"\d+", version or "")[:3]]
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def version_at_least(installed: str, minimum: str) -> bool:
    return version_tuple(installed) >= version_tuple(minimum)


def is_supported_unity_version(unity_version: str) -> bool:
    major, minor, _patch = version_tuple(unity_version)
    if major == 0:
        return True
    if major > 2021:
        return True
    return major == 2021 and minor >= 3


def is_unity_project_root(path: Path) -> bool:
    return (
        (path / "Assets").is_dir()
        and (path / "Packages" / "manifest.json").is_file()
        and (path / "ProjectSettings" / "ProjectVersion.txt").is_file()
    )


def normalize_project_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if not is_unity_project_root(root):
        raise ToolInvocationError("project_not_found", f"Not a Unity project root: {root}")
    return root


def discover_unity_projects(
    *,
    workspace_root: str | Path | None = None,
    project_roots: list[str] | None = None,
    recursive: bool = False,
) -> list[Path]:
    discovered: dict[str, Path] = {}
    explicit_project_roots = [normalize_project_root(value) for value in project_roots or []]

    for root in explicit_project_roots:
        discovered[str(root)] = root

    # When the caller already knows the exact Unity project target, prefer that
    # explicit selection over scanning sibling projects under the same workspace.
    if explicit_project_roots:
        return [discovered[key] for key in sorted(discovered)]

    if workspace_root:
        workspace = Path(workspace_root).expanduser().resolve()
        if is_unity_project_root(workspace):
            discovered[str(workspace)] = workspace

        candidates: list[Path] = []
        if recursive:
            for version_path in workspace.rglob("ProjectSettings/ProjectVersion.txt"):
                candidates.append(version_path.parent.parent)
        elif workspace.is_dir():
            candidates.extend(path for path in workspace.iterdir() if path.is_dir())

        for candidate in candidates:
            if is_unity_project_root(candidate):
                root = candidate.resolve()
                discovered[str(root)] = root

    return [discovered[key] for key in sorted(discovered)]


def load_manifest(project_root: Path) -> dict[str, Any]:
    manifest_path = project_root / "Packages" / "manifest.json"
    try:
        data = read_json(manifest_path)
    except Exception as exc:
        raise ToolInvocationError("manifest_unreadable", f"Could not read Packages/manifest.json: {exc}") from exc
    if not isinstance(data, dict):
        raise ToolInvocationError("manifest_unreadable", "Packages/manifest.json must contain a JSON object.")
    data.setdefault("dependencies", {})
    if not isinstance(data["dependencies"], dict):
        raise ToolInvocationError("manifest_unreadable", "Packages/manifest.json dependencies must be an object.")
    return data


def manifest_dependency(project_root: Path, package_name: str) -> str:
    manifest = load_manifest(project_root)
    value = manifest.get("dependencies", {}).get(package_name)
    return value.strip() if isinstance(value, str) else ""


def classify_test_framework_state(project_root: Path, unity_version: str) -> dict[str, Any]:
    dependency = manifest_dependency(project_root, TEST_FRAMEWORK_PACKAGE_NAME)
    recommended = recommended_test_framework_version(unity_version)
    status = "disabled_missing_dependency"
    manifest_state = "missing"
    supported = False
    upgrade_recommended = False
    dependency_action = "install_optional_dependency"
    action = f"Install {TEST_FRAMEWORK_PACKAGE_NAME} {recommended} or newer."
    installed_version = ""
    upgrade_caution = ""

    if not is_supported_unity_version(unity_version):
        status = "unsupported"
        manifest_state = "unsupported_unity_version"
        dependency_action = "use_supported_unity_version"
        action = "Use Unity 2021.3 or newer for XUUnity Light MCP."
    elif dependency:
        manifest_state = "declared"
        installed_version = dependency.split("@", 1)[-1] if "@" in dependency else dependency
        if version_at_least(installed_version, TEST_FRAMEWORK_MINIMUM_VERSION):
            supported = True
            status = "supported"
            upgrade_recommended = version_tuple(installed_version) < version_tuple(recommended)
            dependency_action = "upgrade_recommended" if upgrade_recommended else "none"
            action = (
                f"Optionally upgrade {TEST_FRAMEWORK_PACKAGE_NAME} from {installed_version} to {recommended} for this Unity version."
                if upgrade_recommended
                else ""
            )
            if upgrade_recommended:
                upgrade_caution = (
                    "The installed Test Framework already satisfies the MCP capability gate. "
                    "Upgrade only after approval and normal Unity package review."
                )
        else:
            status = "disabled_dependency_too_old"
            dependency_action = "upgrade_required"
            action = (
                f"Upgrade {TEST_FRAMEWORK_PACKAGE_NAME} from {installed_version} to {recommended} "
                f"or newer; {installed_version} is below the MCP capability minimum "
                f"{TEST_FRAMEWORK_MINIMUM_VERSION}."
            )
            upgrade_caution = (
                "This project already declares Test Framework. Treat this as a package upgrade: "
                "ask for approval, preserve unrelated manifest entries, and let Unity re-resolve packages."
            )

    return {
        "dependency": TEST_FRAMEWORK_PACKAGE_NAME,
        "dependency_value": dependency,
        "installed_dependency_version": installed_version,
        "minimum_dependency_version": TEST_FRAMEWORK_MINIMUM_VERSION,
        "recommended_dependency_version": recommended,
        "recommendation_basis": "unity_version_policy",
        "capability_define": TEST_FRAMEWORK_CAPABILITY_DEFINE,
        "supported": supported,
        "status": status,
        "manifest_state": manifest_state,
        "upgrade_recommended": upgrade_recommended,
        "dependency_action": dependency_action,
        "upgrade_caution": upgrade_caution,
        "recommended_action": action,
    }


def test_capabilities_state(tf_state: dict[str, Any]) -> str:
    return str(tf_state.get("status") or "error")


def bridge_config_state(project_root: Path) -> dict[str, Any]:
    path = project_root / "Library" / "XUUnityLightMcp" / "config" / "bridge_config.json"
    if not path.is_file():
        return {"path": str(path), "state": "missing", "enabled": False}
    try:
        payload = read_json(path)
    except Exception:
        return {"path": str(path), "state": "unreadable", "enabled": False}
    enabled = bool(payload.get("enabled")) if isinstance(payload, dict) else False
    return {"path": str(path), "state": "enabled" if enabled else "disabled", "enabled": enabled}


def default_git_dependency(package_version: str) -> str:
    return f"{DEFAULT_GIT_REPO_URL}?path=/packages/com.xuunity.light-mcp#v{package_version}"


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
        "projects": [],
    }

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
                "manual_actions": manual_actions,
                "validation_status": validation_status,
            }
        )

    review_notes: list[str] = [
        "Review planned manifest, bridge, and user-level client config changes before applying setup."
    ]
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
        "notes": review_notes,
        "recommended_next_step": (
            "Run setup-apply with the approved project_root selection after user review."
            if len(projects) > 1
            else "Review the plan, approve mutations, then run setup-apply."
        ),
    }
    return result


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


def validate_setup(project_root: Path, *, include_tests: bool = False) -> dict[str, Any]:
    unity_version = parse_unity_version(project_root)
    package_dependency = manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME)
    bridge_state = bridge_config_state(project_root)
    tf_state = classify_test_framework_state(project_root, unity_version)
    blockers: list[str] = []
    if not package_dependency:
        blockers.append("mcp_package_missing")
    if not bridge_state["enabled"]:
        blockers.append("bridge_config_missing")
    if include_tests and not tf_state["supported"]:
        blockers.append("test_framework_unavailable")
    return {
        "action": "validate_setup",
        "project_root": str(project_root),
        "unity_version": unity_version,
        "package_dependency_state": "declared" if package_dependency else "missing",
        "package_dependency": package_dependency,
        "bridge_config_state": bridge_state,
        "test_framework_state": tf_state,
        "test_capabilities_state": test_capabilities_state(tf_state),
        "validation_status": "ready" if not blockers else "blocked",
        "blockers": blockers,
    }
