from __future__ import annotations

import json
import os
import platform
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


def platform_kind() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return system or "unknown"


def codex_context_detected() -> bool:
    env = os.environ
    return bool(
        env.get("CODEX_SHELL")
        or env.get("CODEX_THREAD_ID")
        or env.get("CODEX_SANDBOX")
        or env.get("CODEX_HOME")
        or env.get("CODEX_CI")
        or ("Codex" in str(env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") or ""))
    )


def claude_code_context_detected() -> bool:
    env = os.environ
    return bool(
        env.get("CLAUDE_CODE")
        or env.get("CLAUDECODE")
        or env.get("CLAUDE_CONFIG_PATH")
    )


def codex_detection_basis() -> list[str]:
    env = os.environ
    basis: list[str] = []
    if env.get("CODEX_SHELL"):
        basis.append("env:CODEX_SHELL")
    if env.get("CODEX_THREAD_ID"):
        basis.append("env:CODEX_THREAD_ID")
    if env.get("CODEX_SANDBOX"):
        basis.append("env:CODEX_SANDBOX")
    if env.get("CODEX_HOME"):
        basis.append("env:CODEX_HOME")
    if env.get("CODEX_CI"):
        basis.append("env:CODEX_CI")
    if "Codex" in str(env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") or ""):
        basis.append("env:CODEX_INTERNAL_ORIGINATOR_OVERRIDE")
    return basis


def claude_code_detection_basis() -> list[str]:
    env = os.environ
    basis: list[str] = []
    if env.get("CLAUDE_CODE"):
        basis.append("env:CLAUDE_CODE")
    if env.get("CLAUDECODE"):
        basis.append("env:CLAUDECODE")
    if env.get("CLAUDE_CONFIG_PATH"):
        basis.append("env:CLAUDE_CONFIG_PATH")
    return basis


def detect_client_context() -> dict[str, Any]:
    codex_basis = codex_detection_basis()
    claude_basis = claude_code_detection_basis()
    if codex_basis and not claude_basis:
        return {
            "detected_client": "codex",
            "detection_basis": codex_basis,
            "client_context_confidence": "high",
        }
    if claude_basis and not codex_basis:
        return {
            "detected_client": "claude_code",
            "detection_basis": claude_basis,
            "client_context_confidence": "high",
        }
    if codex_basis and claude_basis:
        return {
            "detected_client": "codex",
            "detection_basis": codex_basis + claude_basis,
            "client_context_confidence": "medium",
        }
    return {
        "detected_client": "unknown",
        "detection_basis": [],
        "client_context_confidence": "low",
    }


def detect_current_host_client() -> str:
    return str(detect_client_context()["detected_client"])


def intended_wiring_target_for_detected_client(detected_client: str) -> str:
    if detected_client == "codex":
        return "codex"
    if detected_client == "claude_code":
        return "claude_code"
    return "manual_selection_required"


def helper_install_targets() -> list[dict[str, Any]]:
    home = Path.home()
    codex_tools_home = Path(os.environ.get("CODEX_TOOLS_HOME") or home / ".codex-tools")
    claude_tools_home = Path(os.environ.get("CLAUDE_TOOLS_HOME") or home / ".claude-tools")
    detected_client = detect_current_host_client()
    targets: list[dict[str, Any]] = []
    for client_id, tools_home in (
        ("codex", codex_tools_home),
        ("claude_code", claude_tools_home),
    ):
        install_dir = tools_home / "xuunity-light-unity-mcp"
        run_path = install_dir / "run.sh"
        server_path = install_dir / "server.py"
        installed = run_path.is_file() and server_path.is_file()
        targets.append(
            {
                "client_id": client_id,
                "tools_home": str(tools_home),
                "install_dir": str(install_dir),
                "run_path": str(run_path),
                "server_path": str(server_path),
                "installed": installed,
                "helper_action": "reuse_existing_helper" if installed else "install_helper",
                "selected_by_default": client_id == intended_wiring_target_for_detected_client(detected_client),
            }
        )
    return targets


def toml_contains_server_block(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"^\[mcp_servers\.xuunity_light_unity\]", text, flags=re.MULTILINE))


def json_contains_server_block(path: Path) -> bool:
    try:
        payload = read_json(path)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    servers = payload.get("mcpServers")
    return isinstance(servers, dict) and "xuunity_light_unity" in servers


def build_client_config_targets(primary_project_root: Path | None) -> list[dict[str, Any]]:
    home = Path.home()
    current_platform = platform_kind()
    detected_client = detect_current_host_client()
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    claude_config_path = Path(os.environ.get("CLAUDE_CONFIG_PATH") or home / ".claude.json")
    targets: list[dict[str, Any]] = []

    def append_target(
        *,
        client_id: str,
        scope: str,
        path: Path,
        config_format: str,
        restart_or_refresh_required: str,
    ) -> None:
        if config_format == "toml":
            has_server_block = toml_contains_server_block(path) if path.is_file() else False
        else:
            has_server_block = json_contains_server_block(path) if path.is_file() else False
        if has_server_block:
            config_action = "verify_existing_server_block"
        elif path.is_file():
            config_action = "merge_add_server_block"
        else:
            config_action = "create_config_with_server_block"
        targets.append(
            {
                "client_id": client_id,
                "scope": scope,
                "path": str(path),
                "exists": path.is_file(),
                "server_block_present": has_server_block,
                "config_action": config_action,
                "merge_only": True,
                "selected_by_default": client_id == intended_wiring_target_for_detected_client(detected_client),
                "restart_or_refresh_required": restart_or_refresh_required,
            }
        )

    append_target(
        client_id="codex",
        scope="user",
        path=codex_home / "config.toml",
        config_format="toml",
        restart_or_refresh_required="refresh_or_restart_codex_if_not_hot_reloaded",
    )
    append_target(
        client_id="claude_code",
        scope="user",
        path=claude_config_path,
        config_format="json",
        restart_or_refresh_required="restart_or_refresh_claude_code_if_not_hot_reloaded",
    )
    if primary_project_root is not None:
        append_target(
            client_id="claude_code",
            scope="project",
            path=primary_project_root / ".mcp.json",
            config_format="json",
            restart_or_refresh_required="restart_or_refresh_claude_code_if_not_hot_reloaded",
        )
        append_target(
            client_id="cursor",
            scope="project",
            path=primary_project_root / ".cursor" / "mcp.json",
            config_format="json",
            restart_or_refresh_required="refresh_cursor_mcp_server_list_if_not_hot_reloaded",
        )
    append_target(
        client_id="cursor",
        scope="user",
        path=home / ".cursor" / "mcp.json",
        config_format="json",
        restart_or_refresh_required="refresh_cursor_mcp_server_list_if_not_hot_reloaded",
    )
    append_target(
        client_id="windsurf",
        scope="user",
        path=home / ".codeium" / "windsurf" / "mcp_config.json",
        config_format="json",
        restart_or_refresh_required="refresh_windsurf_mcp_panel_if_not_hot_reloaded",
    )
    if current_platform == "macos":
        append_target(
            client_id="claude_desktop",
            scope="user",
            path=home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            config_format="json",
            restart_or_refresh_required="restart_claude_desktop_after_config_change",
        )
    elif current_platform == "windows":
        appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        append_target(
            client_id="claude_desktop",
            scope="user",
            path=appdata / "Claude" / "claude_desktop_config.json",
            config_format="json",
            restart_or_refresh_required="restart_claude_desktop_after_config_change",
        )
    return targets


def planned_project_file_changes(project_root: Path, planned_actions: list[dict[str, Any]]) -> list[str]:
    changed_paths: set[str] = set()
    for action in planned_actions:
        kind = str(action.get("kind") or "")
        if kind in {
            "set_manifest_dependency",
            "install_test_framework_dependency",
            "upgrade_test_framework_dependency",
        }:
            changed_paths.add(str(project_root / "Packages" / "manifest.json"))
            changed_paths.add(str(project_root / "Packages" / "packages-lock.json"))
        elif kind == "write_bridge_config":
            changed_paths.add(str(project_root / "Library" / "XUUnityLightMcp" / "config" / "bridge_config.json"))
    return sorted(changed_paths)


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
    lines.append("Do not run setup-apply until the user explicitly approves this review.")
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
