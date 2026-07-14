from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json, render_launcher_cli, write_json
from server_project_context import inspect_light_mcp_import_state, project_not_found_error

LIGHT_MCP_PACKAGE_NAME = "com.xuunity.light-mcp"
TEST_FRAMEWORK_PACKAGE_NAME = "com.unity.test-framework"
TEST_FRAMEWORK_MINIMUM_VERSION = "1.1.33"
TEST_FRAMEWORK_CAPABILITY_DEFINE = "XUUNITY_LIGHT_MCP_TESTS_CAPABILITY"
DEFAULT_GIT_REPO_URL = "https://github.com/FoxsterDev/xuunity-mcp.git"
UNINSTALL_MODE_PROJECT_ONLY = "project-only-cleanup"
UNINSTALL_MODE_FULL_RESET = "full-reset-current-user"
UNINSTALL_MODE_FULL_RESET_ALIAS = "current-user-reset"
UNINSTALL_MODES = {UNINSTALL_MODE_PROJECT_ONLY, UNINSTALL_MODE_FULL_RESET}
UNINSTALL_MODE_ALIASES = {UNINSTALL_MODE_FULL_RESET_ALIAS: UNINSTALL_MODE_FULL_RESET}
UNINSTALL_MODE_INPUTS = UNINSTALL_MODES | set(UNINSTALL_MODE_ALIASES)
SUPPORTED_USER_CLIENTS = {"codex", "claude_code", "cursor", "windsurf", "claude_desktop", "neutral"}
MINIMUM_HELPER_SAFETY_EPOCH = 2


def normalize_uninstall_mode(mode: str) -> str:
    return UNINSTALL_MODE_ALIASES.get(mode, mode)


def user_home_fallback() -> Path:
    for key in ("HOME", "USERPROFILE"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    drive = os.environ.get("HOMEDRIVE")
    path = os.environ.get("HOMEPATH")
    if drive and path:
        return Path(drive + path)
    try:
        return Path.home()
    except RuntimeError:
        return Path(tempfile.gettempdir()) / "xuunity-home-unavailable"


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
    raw_path = str(path)
    root = Path(raw_path).expanduser().resolve()
    if not is_unity_project_root(root):
        raise project_not_found_error(raw_path, root)
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


_CANONICAL_LIGHT_MCP_GIT_DEPENDENCY_RE = re.compile(
    r"^https://github\.com/FoxsterDev/xuunity-mcp(?:\.git)?"
    r"\?path=/packages/com\.xuunity\.light-mcp#v(?P<version>[^#\s]+)$",
    flags=re.IGNORECASE,
)


def normalize_package_version(version: str) -> str:
    return str(version or "").strip().removeprefix("v")


def canonical_light_mcp_git_version(dependency: str) -> str:
    match = _CANONICAL_LIGHT_MCP_GIT_DEPENDENCY_RE.fullmatch(str(dependency or "").strip())
    return normalize_package_version(match.group("version")) if match else ""


def classify_light_mcp_dependency(
    dependency: str,
    *,
    package_source: str,
    package_version: str,
    local_package_source: str,
) -> dict[str, Any]:
    """Compare the declared package with the exact source requested by setup.

    Only a missing dependency, a stale pin from the canonical repository, or an
    explicitly requested local-file source is safe to rewrite automatically
    after approval. Forks and other custom sources remain manual decisions.
    """

    current = str(dependency or "").strip()
    requested_version = normalize_package_version(package_version)
    requested_dependency = (
        f"file:{Path(local_package_source).expanduser().resolve()}"
        if package_source == "file"
        else default_git_dependency(requested_version)
    )
    declared_version = canonical_light_mcp_git_version(current)
    status = "missing"
    automatic_update_allowed = True
    runtime_execution_allowed = False
    reason = "install_missing_dependency"

    if not current:
        pass
    elif current == requested_dependency:
        status = "aligned"
        automatic_update_allowed = False
        runtime_execution_allowed = True
        reason = "requested_dependency_already_declared"
    elif package_source == "git" and declared_version:
        if declared_version == requested_version:
            # Accept the canonical URL with or without the optional .git suffix.
            status = "aligned"
            automatic_update_allowed = False
            runtime_execution_allowed = True
            reason = "requested_canonical_version_already_declared"
        elif version_tuple(declared_version) < version_tuple(requested_version):
            status = "stale_git_pin"
            automatic_update_allowed = True
            reason = "upgrade_stale_git_pin"
        elif version_tuple(declared_version) > version_tuple(requested_version):
            status = "newer_than_requested"
            automatic_update_allowed = False
            reason = "refuse_automatic_downgrade"
        else:
            status = "version_mismatch"
            automatic_update_allowed = False
            reason = "manual_version_review_required"
    elif package_source == "file":
        status = "explicit_source_change"
        automatic_update_allowed = True
        reason = "switch_to_explicit_local_source"
    else:
        status = "custom_source_mismatch"
        automatic_update_allowed = False
        reason = "preserve_custom_or_forked_source"

    return {
        "status": status,
        "current_dependency": current,
        "requested_dependency": requested_dependency,
        "declared_version": declared_version,
        "requested_version": requested_version,
        "automatic_update_allowed": automatic_update_allowed,
        "runtime_execution_allowed": runtime_execution_allowed,
        "reason": reason,
    }


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


def get_neutral_install_dir() -> Path:

    override = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR")
    if override:
        return Path(override)

    home = user_home_fallback()
    system = platform.system().lower()
    if system == "windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "xuunity-mcp"
        return home / "AppData" / "Roaming" / "xuunity-mcp"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "xuunity-mcp"

    if system == "darwin":
        return home / "Library" / "Application Support" / "xuunity-mcp"

    return home / ".local" / "share" / "xuunity-mcp"


def read_helper_package_version(install_dir: Path) -> str:
    package_path = install_dir / "packages" / LIGHT_MCP_PACKAGE_NAME / "package.json"
    try:
        payload = read_json(package_path)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return normalize_package_version(str(payload.get("version") or ""))


def read_helper_source_root(install_dir: Path) -> tuple[str, str]:
    marker_path = install_dir / ".source_root"
    try:
        source_root = marker_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "", ""
    if not source_root:
        return "", ""
    source_version = ""
    try:
        payload = read_json(Path(source_root) / "packages" / LIGHT_MCP_PACKAGE_NAME / "package.json")
        if isinstance(payload, dict):
            source_version = normalize_package_version(str(payload.get("version") or ""))
    except Exception:
        pass
    return source_root, source_version


def verify_helper_integrity_manifest(install_dir: Path, expected_version: str) -> dict[str, Any]:
    manifest_path = install_dir / ".install_manifest.json"
    try:
        payload = read_json(manifest_path)
    except Exception:
        return {"status": "missing", "verified": False, "safety_epoch": 0, "mismatched_files": []}
    if not isinstance(payload, dict):
        return {"status": "invalid", "verified": False, "safety_epoch": 0, "mismatched_files": []}

    try:
        safety_epoch = int(payload.get("safety_epoch") or 0)
    except (TypeError, ValueError):
        return {"status": "invalid", "verified": False, "safety_epoch": 0, "mismatched_files": []}
    manifest_version = normalize_package_version(str(payload.get("version") or ""))
    files = payload.get("files")
    if safety_epoch < MINIMUM_HELPER_SAFETY_EPOCH:
        return {
            "status": "unsafe_epoch",
            "verified": False,
            "safety_epoch": safety_epoch,
            "mismatched_files": [],
        }
    if manifest_version != normalize_package_version(expected_version):
        return {
            "status": "version_mismatch",
            "verified": False,
            "safety_epoch": safety_epoch,
            "mismatched_files": [],
        }
    if not isinstance(files, dict) or not files:
        return {
            "status": "invalid",
            "verified": False,
            "safety_epoch": safety_epoch,
            "mismatched_files": [],
        }

    mismatched_files: list[str] = []
    for relative_name, expected_hash in files.items():
        relative_path = Path(str(relative_name))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            mismatched_files.append(str(relative_name))
            continue
        file_path = install_dir / relative_path
        try:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError:
            actual_hash = ""
        if actual_hash != str(expected_hash or ""):
            mismatched_files.append(str(relative_name))
    return {
        "status": "verified" if not mismatched_files else "file_hash_mismatch",
        "verified": not mismatched_files,
        "safety_epoch": safety_epoch,
        "mismatched_files": sorted(mismatched_files),
    }


def build_helper_install_target(
    *,
    client_id: str,
    tools_home: Path,
    install_dir: Path,
    expected_version: str,
    selected_by_default: bool,
) -> dict[str, Any]:
    current_platform = platform_kind()
    legacy_run_path = install_dir / "run.sh"
    server_path = install_dir / "server.py"
    refresh_run_path = install_dir / (
        "run_installed_or_refresh_xuunity_mcp.cmd"
        if current_platform == "windows"
        else "run_installed_or_refresh_xuunity_mcp.sh"
    )
    installed = legacy_run_path.is_file() and server_path.is_file()
    installed_version = read_helper_package_version(install_dir) if installed else ""
    source_root, source_version = read_helper_source_root(install_dir) if installed else ("", "")
    normalized_expected = normalize_package_version(expected_version)
    refresh_launcher_present = refresh_run_path.is_file()
    integrity = (
        verify_helper_integrity_manifest(install_dir, normalized_expected)
        if installed
        else {"status": "missing", "verified": False, "safety_epoch": 0, "mismatched_files": []}
    )

    if not installed:
        version_alignment = "missing"
        helper_action = "neutral_install" if client_id == "neutral" else "install_helper"
    elif not installed_version:
        version_alignment = "unknown"
        helper_action = "refresh_existing_helper"
    elif installed_version != normalized_expected:
        version_alignment = "stale" if version_tuple(installed_version) < version_tuple(normalized_expected) else "mismatch"
        helper_action = "refresh_existing_helper"
    elif source_version and source_version != normalized_expected:
        version_alignment = "source_root_mismatch"
        helper_action = "refresh_existing_helper"
    elif not refresh_launcher_present:
        version_alignment = "refresh_launcher_missing"
        helper_action = "refresh_existing_helper"
    elif not integrity["verified"]:
        version_alignment = f"integrity_{integrity['status']}"
        helper_action = "refresh_existing_helper"
    else:
        version_alignment = "aligned"
        helper_action = "reuse_current_helper"

    return {
        "client_id": client_id,
        "tools_home": str(tools_home),
        "install_dir": str(install_dir),
        "run_path": str(refresh_run_path),
        "legacy_direct_run_path": str(legacy_run_path),
        "server_path": str(server_path),
        "installed": installed,
        "installed_version": installed_version,
        "expected_version": normalized_expected,
        "version_alignment": version_alignment,
        "source_root": source_root,
        "source_root_version": source_version,
        "refresh_launcher_present": refresh_launcher_present,
        "integrity_status": integrity["status"],
        "integrity_verified": integrity["verified"],
        "safety_epoch": integrity["safety_epoch"],
        "integrity_mismatched_files": integrity["mismatched_files"],
        "runtime_execution_allowed": version_alignment == "aligned",
        "helper_action": helper_action,
        "selected_by_default": selected_by_default,
    }


def helper_install_targets(expected_version: str = "") -> list[dict[str, Any]]:
    home = user_home_fallback()
    codex_tools_home = Path(os.environ.get("CODEX_TOOLS_HOME") or home / ".codex-tools")
    claude_tools_home = Path(os.environ.get("CLAUDE_TOOLS_HOME") or home / ".claude-tools")
    neutral_tools_home = get_neutral_install_dir()
    detected_client = detect_current_host_client()
    targets: list[dict[str, Any]] = []
    for client_id, tools_home in (
        ("codex", codex_tools_home),
        ("claude_code", claude_tools_home),
    ):
        install_dir = tools_home / "xuunity-mcp"
        targets.append(
            build_helper_install_target(
                client_id=client_id,
                tools_home=tools_home,
                install_dir=install_dir,
                expected_version=expected_version,
                selected_by_default=client_id == intended_wiring_target_for_detected_client(detected_client),
            )
        )

    targets.append(
        build_helper_install_target(
            client_id="neutral",
            tools_home=neutral_tools_home.parent,
            install_dir=neutral_tools_home,
            expected_version=expected_version,
            selected_by_default=True,
        )
    )
    return targets


def toml_server_block_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(
        r"^\[mcp_servers\.xuunity_light_unity\]\s*$"
        r"(?P<body>.*?)(?=^\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(0).strip() if match else ""


def json_server_entry(path: Path) -> dict[str, Any]:
    try:
        payload = read_json(path)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        return {}
    entry = servers.get("xuunity_light_unity")
    return entry if isinstance(entry, dict) else {}


def classify_client_launcher(path: Path, config_format: str, current_platform: str) -> dict[str, Any]:
    command = ""
    args: list[str] = []
    raw = ""
    if config_format == "toml":
        raw = toml_server_block_text(path)
        command_match = re.search(r'^\s*command\s*=\s*"([^"\n]+)"', raw, flags=re.MULTILINE)
        command = command_match.group(1) if command_match else ""
        args_match = re.search(r"^\s*args\s*=\s*(\[[^\n]*\])", raw, flags=re.MULTILINE)
        if args_match:
            try:
                parsed_args = json.loads(args_match.group(1))
                if isinstance(parsed_args, list):
                    args = [str(item) for item in parsed_args]
            except Exception:
                pass
    else:
        entry = json_server_entry(path)
        command = str(entry.get("command") or "")
        raw_args = entry.get("args")
        if isinstance(raw_args, list):
            args = [str(item) for item in raw_args]
        raw = json.dumps(entry, ensure_ascii=True)

    if not raw:
        return {"status": "missing", "issue_codes": [], "command": "", "args": []}

    issue_codes: list[str] = []
    combined = " ".join([command, *args]).lower()
    if current_platform == "windows":
        if command.lower() not in {"cmd", "cmd.exe"}:
            issue_codes.append("windows_launcher_flavor_mismatch")
        if args[:3] != ["/d", "/c", "call"]:
            issue_codes.append("windows_cmd_invocation_mismatch")
        if "run_installed_or_refresh_xuunity_mcp.cmd" not in combined:
            issue_codes.append("refresh_launcher_missing")
        if "bash" in combined or ".sh" in combined or re.search(r"(?:^|[\\/])run\.sh(?:$|\s)", combined):
            issue_codes.append("unsafe_legacy_launcher_reference")
        status = "compatible" if not issue_codes else "windows_launcher_migration_required"
    else:
        if not command.startswith("/"):
            issue_codes.append("posix_launcher_not_absolute")
        if not args or args[0] != "-c" or "-lc" in args:
            issue_codes.append("posix_login_shell_not_allowed")
        if "run_installed_or_refresh_xuunity_mcp.sh" not in combined:
            issue_codes.append("refresh_launcher_missing")
        if re.search(r"(?:^|/)run\.sh(?:$|[\s\"'])", combined):
            issue_codes.append("unsafe_legacy_launcher_reference")
        status = "compatible" if not issue_codes else "posix_launcher_migration_required"

    return {"status": status, "issue_codes": issue_codes, "command": command, "args": args}

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
    home = user_home_fallback()
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
        launcher = (
            classify_client_launcher(path, config_format, current_platform)
            if has_server_block
            else {"status": "missing", "issue_codes": [], "command": "", "args": []}
        )
        if has_server_block and launcher["status"] == "compatible":
            config_action = "verify_existing_server_block"
        elif has_server_block:
            config_action = "replace_incompatible_server_block"
        elif path.is_file():
            config_action = "merge_add_server_block"
        else:
            config_action = "create_config_with_server_block"
        targets.append(
            {
                "client_id": client_id,
                "scope": scope,
                "path": str(path),
                "config_format": config_format,
                "exists": path.is_file(),
                "server_block_present": has_server_block,
                "config_action": config_action,
                "launcher_status": launcher["status"],
                "launcher_issue_codes": launcher["issue_codes"],
                "configured_command": launcher["command"],
                "configured_args": launcher["args"],
                "runtime_execution_allowed": launcher["status"] == "compatible",
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


def project_bridge_root(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp"


def remove_manifest_dependency(project_root: Path, package_name: str) -> bool:
    manifest_path = project_root / "Packages" / "manifest.json"
    payload = load_manifest(project_root)
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict) or package_name not in dependencies:
        return False
    dependencies.pop(package_name, None)
    write_json(manifest_path, payload)
    return True


def selected_uninstall_client(requested_client: str | None) -> str:
    requested = (requested_client or "auto").strip()
    if requested and requested != "auto":
        if requested not in SUPPORTED_USER_CLIENTS:
            raise ToolInvocationError(
                "unsupported_client",
                f"Unsupported uninstall client: {requested}",
                {"supported_clients": sorted(SUPPORTED_USER_CLIENTS)},
            )
        return requested
    detected = intended_wiring_target_for_detected_client(detect_current_host_client())
    if detected in SUPPORTED_USER_CLIENTS:
        return detected
    return "manual_selection_required"


def uninstall_project_actions(project_root: Path) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    package_dependency = manifest_dependency(project_root, LIGHT_MCP_PACKAGE_NAME)
    if package_dependency:
        actions.append(
            {
                "kind": "remove_manifest_dependency",
                "package": LIGHT_MCP_PACKAGE_NAME,
                "path": str(project_root / "Packages" / "manifest.json"),
                "lock_path": str(project_root / "Packages" / "packages-lock.json"),
                "current_value": package_dependency,
            }
        )
    bridge_root = project_bridge_root(project_root)
    if bridge_root.exists():
        actions.append(
            {
                "kind": "remove_project_bridge_directory",
                "path": str(bridge_root),
                "reason": "remove_project_bridge_config_state_and_request_artifacts",
            }
        )
    return actions


def uninstall_project_file_changes(project_root: Path, planned_actions: list[dict[str, Any]]) -> list[str]:
    changed_paths: set[str] = set()
    for action in planned_actions:
        kind = str(action.get("kind") or "")
        if kind == "remove_manifest_dependency":
            changed_paths.add(str(project_root / "Packages" / "manifest.json"))
            changed_paths.add(str(project_root / "Packages" / "packages-lock.json"))
        elif kind == "remove_project_bridge_directory":
            changed_paths.add(str(project_bridge_root(project_root)))
    return sorted(changed_paths)


def additional_workspace_projects(
    *,
    workspace_root: str | None,
    selected_project_roots: list[Path],
    recursive: bool,
) -> list[str]:
    if not workspace_root:
        return []
    selected = {str(root) for root in selected_project_roots}
    discovered = discover_unity_projects(workspace_root=workspace_root, project_roots=None, recursive=recursive)
    return [str(root) for root in discovered if str(root) not in selected]


def uninstall_client_config_targets(
    *,
    mode: str,
    selected_client: str,
    project_root: Path | None,
) -> list[dict[str, Any]]:
    targets = build_client_config_targets(project_root)
    for target in targets:
        target["uninstall_action"] = "keep_client_config"
        target["remove_server_block"] = False
    if mode != UNINSTALL_MODE_FULL_RESET or selected_client == "manual_selection_required":
        return targets
    for target in targets:
        if (
            target.get("scope") == "user"
            and target.get("client_id") == selected_client
            and target.get("server_block_present")
        ):
            target["uninstall_action"] = "remove_xuunity_server_block"
            target["remove_server_block"] = True
        elif target.get("scope") == "user" and target.get("client_id") == selected_client:
            target["uninstall_action"] = "verify_absent"
    return targets


def uninstall_helper_targets(
    *,
    mode: str,
    selected_client: str,
    include_other_client_helpers: bool,
) -> list[dict[str, Any]]:
    targets = helper_install_targets()
    for target in targets:
        client_id = str(target.get("client_id") or "")
        remove = False
        if mode == UNINSTALL_MODE_FULL_RESET:
            is_selected = client_id == selected_client
            is_neutral_reset = (
                client_id == "neutral"
                and (
                    selected_client in ("neutral", "manual_selection_required")
                    or include_other_client_helpers
                )
            )
            remove = is_selected or is_neutral_reset or (
                include_other_client_helpers
                and bool(target.get("installed"))
            )
        target["uninstall_action"] = (
            "remove_helper_install" if remove and target.get("installed") else "keep_helper_install"
        )
        target["remove_helper_install"] = bool(remove and target.get("installed"))
        target["selected_by_default"] = client_id == selected_client or (
            client_id == "neutral"
            and (
                selected_client in ("neutral", "manual_selection_required")
                or include_other_client_helpers
            )
        )
    return targets


def render_uninstall_review_summary(
    *,
    mode: str,
    detected_client: str,
    detection_basis: list[str],
    client_context_confidence: str,
    selected_client: str,
    selected_project_roots: list[str],
    additional_discovered_project_roots: list[str],
    project_file_changes: list[str],
    user_config_changes: list[str],
    helper_removals: list[str],
    helper_kept: list[str],
    restart_or_refresh_required: list[str],
) -> str:
    lines: list[str] = ["Uninstall preflight review"]
    lines.append(f"- Mode: {mode}")
    lines.append(f"- Current client: {detected_client}")
    lines.append(f"- Detection basis: {', '.join(detection_basis) if detection_basis else 'none'}")
    lines.append(f"- Client detection confidence: {client_context_confidence}")
    lines.append(f"- Selected client cleanup target: {selected_client}")
    lines.append(
        "- Unity project root: "
        + (", ".join(selected_project_roots) if selected_project_roots else "none")
    )
    lines.append(
        "- Additional discovered Unity projects: "
        + (", ".join(additional_discovered_project_roots) if additional_discovered_project_roots else "none")
    )
    lines.append(
        "- Planned project cleanup: "
        + (", ".join(project_file_changes) if project_file_changes else "none")
    )
    lines.append(
        "- Planned user-level config cleanup: "
        + (", ".join(user_config_changes) if user_config_changes else "none")
    )
    lines.append(
        "- Helper installs to remove: "
        + (", ".join(helper_removals) if helper_removals else "none")
    )
    lines.append(
        "- Helper installs to keep: "
        + (", ".join(helper_kept) if helper_kept else "none")
    )
    lines.append(
        "- Restart or refresh required after mutation: "
        + (", ".join(restart_or_refresh_required) if restart_or_refresh_required else "none")
    )
    lines.append("")
    lines.append("Do not run uninstall-apply until the user explicitly approves this review.")
    return "\n".join(lines)


__all__ = [name for name in globals() if not name.startswith("__")]
