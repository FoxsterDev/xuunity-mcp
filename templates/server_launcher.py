"""Wrapper core for the operator-side launcher.

Behavior-preserving port of the historical xuunity_light_unity_mcp.sh wrapper
body. Shell entrypoints stay thin (find a Python >= 3.10 interpreter, exec this
module); every resolve, mode switch, sync, and dispatch decision lives here.

Contract mirrors the bash wrapper exactly: command names, env variables
(XUUNITY_LIGHT_UNITY_MCP_*), stdout/stderr line shapes, and exit codes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM_PYTHON_VERSION = "3.10"

if sys.version_info[:2] < (3, 10):
    current = ".".join(str(v) for v in sys.version_info[:3])
    sys.stderr.write(
        "Python %s or newer is required. Selected interpreter reports %s. "
        "Set PYTHON to a Python 3.10+ executable.\n" % (MINIMUM_PYTHON_VERSION, current)
    )
    raise SystemExit(1)

PACKAGE_NAME = "com.xuunity.light-mcp"
SERVER_TEMPLATE_RELATIVE_PATH = "templates/server.py"
RUN_TEMPLATE_RELATIVE_PATH = "templates/run.sh"
SERVER_MODULES_TEMPLATE_GLOB = "server_*.py"
RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH = "templates/xuunity_light_unity_mcp_runtime_defaults.json"
PACKAGE_TEMPLATE_RELATIVE_PATH = "packages/com.xuunity.light-mcp"
PACKAGE_METADATA_RELATIVE_PATH = PACKAGE_TEMPLATE_RELATIVE_PATH + "/package.json"

_LAUNCHER_DIR = Path(os.path.abspath(__file__)).parent
sys.path.insert(0, str(_LAUNCHER_DIR))

import server_setup_wizard


def fail(message: str, exit_code: int = 1) -> "SystemExit":
    sys.stderr.write(message + "\n")
    return SystemExit(exit_code)


def launcher_display_name() -> str:
    return os.environ.get("XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME") or "xuunity_light_unity_mcp.sh"


def directory_abspath_or_fail(value: str, env_name: str) -> str:
    if not os.path.isdir(value):
        raise fail("%s does not point to a directory: %s" % (env_name, value))
    return os.path.abspath(value)


def source_root_has_mcp_package(candidate: str) -> bool:
    return os.path.isfile(os.path.join(candidate, SERVER_TEMPLATE_RELATIVE_PATH)) and os.path.isfile(
        os.path.join(candidate, PACKAGE_TEMPLATE_RELATIVE_PATH, "package.json")
    )


def resolve_source_root() -> str:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT")
    if explicit:
        return directory_abspath_or_fail(explicit, "XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT")

    airroot = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_AIRROOT")
    if airroot:
        operations_candidate = os.path.join(airroot, "Operations", "XUUnityLightUnityMcp")
        if source_root_has_mcp_package(operations_candidate):
            return directory_abspath_or_fail(operations_candidate, "XUUNITY_LIGHT_UNITY_MCP_AIRROOT")
        if source_root_has_mcp_package(airroot):
            return directory_abspath_or_fail(airroot, "XUUNITY_LIGHT_UNITY_MCP_AIRROOT")

    return str(_LAUNCHER_DIR.parent)


def resolve_repo_root(source_root: str) -> str:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT")
    if explicit:
        return directory_abspath_or_fail(explicit, "XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT")

    for relative in ("../../..", ".."):
        candidate = os.path.abspath(os.path.join(source_root, relative))
        if not os.path.isdir(candidate):
            continue
        if os.path.isdir(os.path.join(candidate, "AIOutput")) or os.path.isdir(os.path.join(candidate, "AIModules")):
            return candidate

    candidate = os.getcwd()
    previous = ""
    while candidate and candidate != previous:
        if os.path.isdir(os.path.join(candidate, "AIRoot")) and (
            os.path.isdir(os.path.join(candidate, "AIOutput")) or os.path.isdir(os.path.join(candidate, "AIModules"))
        ):
            return candidate
        previous = candidate
        candidate = os.path.dirname(candidate)

    return os.getcwd()


def codex_install_dir() -> str:
    home = os.environ.get("CODEX_TOOLS_HOME") or os.path.join(str(Path.home()), ".codex-tools")
    return os.path.join(home, "xuunity-mcp")


def claude_install_dir() -> str:
    home = os.environ.get("CLAUDE_TOOLS_HOME") or os.path.join(str(Path.home()), ".claude-tools")
    return os.path.join(home, "xuunity-mcp")


def neutral_install_dir() -> str:
    return str(server_setup_wizard.get_neutral_install_dir())


def resolve_install_dir() -> str:
    install_target = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET") or "auto"
    if install_target == "neutral":
        return neutral_install_dir()
    if install_target == "codex":
        return codex_install_dir()
    if install_target == "claude":
        return claude_install_dir()
    if install_target != "auto":
        raise fail(
            "invalid XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=%s (expected codex, claude, neutral, or auto)"
            % install_target
        )

    if server_setup_wizard.codex_context_detected():
        return codex_install_dir()
    if server_setup_wizard.claude_code_context_detected():
        return claude_install_dir()
    for candidate in (neutral_install_dir(), claude_install_dir(), codex_install_dir()):
        if os.path.isfile(os.path.join(candidate, "server.py")):
            return candidate
    return neutral_install_dir()


class LauncherPaths:
    def __init__(self) -> None:
        self.source_root = resolve_source_root()
        self.repo_root = resolve_repo_root(self.source_root)
        server_override = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_SERVER")
        if server_override:
            self.server_path = server_override
            self.install_dir = directory_abspath_or_fail(
                os.path.dirname(server_override) or ".", "XUUNITY_LIGHT_UNITY_MCP_SERVER"
            )
        else:
            self.install_dir = resolve_install_dir()
            self.server_path = os.path.join(self.install_dir, "server.py")
        self.run_path = os.path.join(self.install_dir, "run.sh")
        self.source_server_path = os.path.join(self.source_root, SERVER_TEMPLATE_RELATIVE_PATH)


def require_command(command_name: str) -> None:
    if shutil.which(command_name) is None:
        raise fail("required command not found: %s" % command_name)


def require_package_source_root(source_root: str) -> None:
    expected_package_source = os.path.join(source_root, PACKAGE_TEMPLATE_RELATIVE_PATH)
    if os.path.isfile(os.path.join(source_root, SERVER_TEMPLATE_RELATIVE_PATH)) and os.path.isfile(
        os.path.join(expected_package_source, "package.json")
    ):
        return
    sys.stderr.write("xuunity-mcp source root preflight failed\n")
    sys.stderr.write("source_root=%s\n" % source_root)
    sys.stderr.write("expected_package_source=%s\n" % expected_package_source)
    sys.stderr.write("airroot=%s\n" % (os.environ.get("XUUNITY_LIGHT_UNITY_MCP_AIRROOT") or ""))
    sys.stderr.write("recommended_next_action=fix_source_root_or_set_XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT\n")
    raise SystemExit(1)


def emit_compact_summary_from_payload_text(payload_text: str, exit_code: int) -> None:
    try:
        payload = json.loads(payload_text)
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    def line(*parts) -> None:
        sys.stderr.write("[xuunity-mcp] compact " + " ".join(str(p) for p in parts if str(p)) + "\n")

    if str(payload.get("reason") or "") == "assistive_access_not_granted":
        line(
            "outcome=window_arrangement",
            "reason=assistive_access_not_granted",
            "remediation=grant_accessibility_permission_then_rerun",
        )
        return

    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    error_code = str(error.get("code") or "")
    if exit_code != 0 or error_code:
        parts = ["outcome=error", f"exit_code={exit_code}", f"code={error_code}"]
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        if payload.get("request_id"):
            parts.append(f"request_id={payload.get('request_id')}")
        next_action = payload.get("recommended_next_action") or error.get("recommended_next_action")
        if next_action:
            parts.append(f"next={next_action}")
        for key in (
            "process_visibility_error_code",
            "same_project_editor_closed",
            "process_exit_verified",
            "closeout_classification",
        ):
            value = payload.get(key)
            if value is None:
                value = details.get(key)
            if value is not None and value != "":
                if isinstance(value, bool):
                    value = str(value).lower()
                parts.append(f"{key}={value}")
        line(*parts)
        return

    if payload.get("action") == "unity_status_summary" or "health_status" in payload:
        line(
            "outcome=status",
            f"health={payload.get('health_status', '')}",
            f"editor_running={str(bool(payload.get('editor_running'))).lower()}",
            f"mcp_reachable={str(bool(payload.get('mcp_reachable'))).lower()}",
            f"pending={int(payload.get('pending_request_count') or 0)}",
            f"busy_reason={payload.get('busy_reason', '')}",
            f"playmode={payload.get('playmode_state', '')}",
        )
        return

    if payload.get("action") == "unity_scenario_result_summary":
        parts = [
            "outcome=scenario",
            f"scenario={payload.get('scenario_name', '')}",
            f"status={payload.get('status', '')}",
            f"terminal={str(bool(payload.get('terminal'))).lower()}",
            f"passed_steps={int(payload.get('passed_steps') or 0)}",
            f"failed_steps={int(payload.get('failed_steps') or 0)}",
            f"skipped_steps={int(payload.get('skipped_steps') or 0)}",
        ]
        failed = payload.get("first_failed_step") if isinstance(payload.get("first_failed_step"), dict) else {}
        if failed:
            parts.append(f"first_failed={failed.get('step_id', '')}:{failed.get('error_code', '')}")
        profile = (
            payload.get("profile_mutation_summary")
            if isinstance(payload.get("profile_mutation_summary"), dict)
            else {}
        )
        if profile:
            parts.append(
                f"profile_restore_required={str(bool(profile.get('profile_restore_required'))).lower()}"
            )
        line(*parts)
        return

    if payload.get("action") == "unity_project_action_invoke":
        parts = [
            "outcome=project_action",
            f"action_id={payload.get('action_id', '')}",
            f"hook={payload.get('hook_name', '')}",
            f"status={payload.get('status', '')}",
            f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
            f"mutating={str(bool(payload.get('mutation'))).lower()}",
        ]
        if payload.get("result_path"):
            parts.append(f"result_path={payload.get('result_path')}")
        line(*parts)
        return

    if payload.get("action") == "unity_loading_timing_summary":
        parts = [
            "outcome=loading_timing",
            f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
            f"matches={int(payload.get('match_count') or 0)}",
            f"returned={int(payload.get('returned_count') or 0)}",
            f"timing_values={int(payload.get('timing_value_count') or 0)}",
            f"truncated={str(bool(payload.get('truncated'))).lower()}",
        ]
        if payload.get("marker_count"):
            parts.append(f"markers={int(payload.get('marker_count') or 0)}")
        if payload.get("first_timestamp"):
            parts.append(f"first={payload.get('first_timestamp')}")
        if payload.get("last_timestamp"):
            parts.append(f"last={payload.get('last_timestamp')}")
        line(*parts)
        return

    if isinstance(payload.get("result_summary"), dict):
        summary = payload.get("result_summary") or {}
        matrix = summary.get("matrix") if isinstance(summary.get("matrix"), dict) else {}
        parts = [
            "outcome=batch",
            f"action={payload.get('action', '')}",
            f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
            f"requested_lane={summary.get('requested_execution_lane', '')}",
            f"effective_lane={summary.get('effective_execution_lane', '')}",
            f"unity={summary.get('unity_outcome', '')}",
            f"transport={summary.get('transport_outcome', '')}",
        ]
        if matrix:
            parts.extend(
                [
                    f"matrix_status={matrix.get('status', '')}",
                    f"total={int(matrix.get('total') or 0)}",
                    f"failed={int(matrix.get('failed') or 0)}",
                ]
            )
        if payload.get("summary_file"):
            parts.append(f"summary_file={payload.get('summary_file')}")
        line(*parts)
        return

    if payload.get("request_id") and payload.get("payload_type"):
        parts = [
            "outcome=ok",
            f"request_id={payload.get('request_id')}",
            f"payload_type={payload.get('payload_type')}",
            f"status={payload.get('status', '')}",
        ]
        decoded = {}
        raw = payload.get("payload_json")
        if isinstance(raw, str) and raw:
            try:
                decoded = json.loads(raw)
            except Exception:
                decoded = {}
        payload_type = str(payload.get("payload_type") or "")
        if payload_type == "unity.compile.matrix":
            parts.extend(
                [
                    f"matrix_status={decoded.get('status', '')}",
                    f"total={int(decoded.get('total') or 0)}",
                    f"passed={int(decoded.get('passed') or 0)}",
                    f"failed={int(decoded.get('failed') or 0)}",
                ]
            )
        elif payload_type.startswith("unity.tests."):
            parts.extend(
                [
                    f"test_status={decoded.get('status', '')}",
                    f"total={int(decoded.get('total') or 0)}",
                    f"passed={int(decoded.get('passed') or 0)}",
                    f"failed={int(decoded.get('failed') or 0)}",
                ]
            )
        elif payload_type == "unity.console.grep":
            items = decoded.get("items")
            parts.extend(
                [
                    f"matches={int(decoded.get('match_count') or 0)}",
                    f"returned={len(items) if isinstance(items, list) else 0}",
                    f"truncated={str(bool(decoded.get('truncated'))).lower()}",
                ]
            )
        line(*parts)


def exec_python_script(script_path: str, args: list) -> "SystemExit":
    argv = [sys.executable, script_path] + list(args)
    if os.name != "nt":
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, argv)
    completed = subprocess.run(argv)
    return SystemExit(completed.returncode)


def run_server_with_optional_compact_summary(server_path: str, args: list, compact_summary: bool) -> "SystemExit":
    if not compact_summary:
        raise exec_python_script(server_path, args)

    completed = subprocess.run(
        [sys.executable, server_path] + list(args),
        stdout=subprocess.PIPE,
        text=True,
    )
    sys.stdout.write(completed.stdout)
    sys.stdout.flush()
    emit_compact_summary_from_payload_text(completed.stdout, completed.returncode)
    return SystemExit(completed.returncode)


def sync_file_from_source(paths: LauncherPaths, destination_path: str, relative_source_path: str) -> None:
    source_path = os.path.join(paths.source_root, relative_source_path)
    payload = Path(source_path).read_bytes()
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() == payload:
        return
    destination.write_bytes(payload)


def sync_installed_helper_if_needed(paths: LauncherPaths) -> None:
    if not os.path.exists(os.path.join(paths.source_root, ".git")):
        return
    if not os.path.isfile(os.path.join(paths.source_root, SERVER_TEMPLATE_RELATIVE_PATH)):
        return

    os.makedirs(paths.install_dir, exist_ok=True)

    sync_file_from_source(paths, paths.server_path, SERVER_TEMPLATE_RELATIVE_PATH)
    sync_file_from_source(paths, paths.run_path, RUN_TEMPLATE_RELATIVE_PATH)
    sync_file_from_source(
        paths,
        os.path.join(paths.install_dir, os.path.basename(RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH)),
        RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH,
    )
    sync_file_from_source(
        paths,
        os.path.join(paths.install_dir, PACKAGE_METADATA_RELATIVE_PATH),
        PACKAGE_METADATA_RELATIVE_PATH,
    )

    templates_dir = Path(paths.source_root) / "templates"
    for module_source_path in sorted(templates_dir.glob(SERVER_MODULES_TEMPLATE_GLOB)):
        if not module_source_path.is_file():
            continue
        sync_file_from_source(
            paths,
            os.path.join(paths.install_dir, module_source_path.name),
            os.path.join("templates", module_source_path.name),
        )
    os.chmod(paths.run_path, 0o755)


def require_project_root_argument(args: list) -> str:
    project_root = ""
    index = 0
    while index < len(args):
        if args[index] == "--project-root":
            index += 1
            if index >= len(args):
                raise fail("--project-root requires a value")
            project_root = args[index]
        index += 1

    if not project_root:
        raise fail("missing required argument: --project-root /path/to/UnityProject")

    if not os.path.isdir(os.path.join(project_root, "Packages")):
        raise fail("Unity project Packages directory not found under: %s" % project_root)

    return os.path.realpath(project_root)


def normalize_git_url_for_unity_upm(git_url: str) -> str:
    if git_url.startswith("git@github.com:"):
        return "https://github.com/" + git_url[len("git@github.com:"):]
    if git_url.startswith("ssh://git@github.com/"):
        return "https://github.com/" + git_url[len("ssh://git@github.com/"):]
    return git_url


def run_git(source_root: str, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", source_root] + list(args),
        stdout=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.stdout.strip()


def remote_release_tag_commit(source_root: str, remote_name: str, release_tag: str):
    tag_ref = "refs/tags/%s" % release_tag
    peeled_ref = tag_ref + "^{}"
    completed = subprocess.run(
        ["git", "-C", source_root, "ls-remote", "--tags", remote_name, tag_ref, peeled_ref],
        stdout=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        return None
    direct_hash = ""
    for raw_line in completed.stdout.splitlines():
        if "\t" not in raw_line:
            continue
        commit_hash, ref = raw_line.split("\t", 1)
        if ref == peeled_ref:
            return commit_hash
        if ref == tag_ref:
            direct_hash = commit_hash
    return direct_hash or None


def read_package_version(source_root: str) -> str:
    package_json = Path(source_root) / PACKAGE_METADATA_RELATIVE_PATH
    version = json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
    if not version:
        raise SystemExit("Could not read package version from package.json")
    return version


def read_project_unity_version(project_root: str) -> str:
    project_version_path = Path(project_root) / "ProjectSettings" / "ProjectVersion.txt"
    for raw_line in project_version_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("m_EditorVersion:"):
            return raw_line.split(":", 1)[1].strip()
    raise SystemExit("Could not find m_EditorVersion in ProjectVersion.txt")


def update_manifest_dependency(manifest_path: str, dependency_value: str) -> None:
    manifest = Path(manifest_path)
    data = json.loads(manifest.read_text())
    dependencies = data.setdefault("dependencies", {})
    dependencies[PACKAGE_NAME] = dependency_value
    manifest.write_text(json.dumps(data, indent=2) + "\n")


def remove_lock_dependency(lock_path: str) -> None:
    lock = Path(lock_path)
    if not lock.is_file():
        return
    data = json.loads(lock.read_text())
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict) and PACKAGE_NAME in dependencies:
        del dependencies[PACKAGE_NAME]
        lock.write_text(json.dumps(data, indent=2) + "\n")


def switch_project_to_devmode(paths: LauncherPaths, args: list) -> None:
    project_root = require_project_root_argument(args)
    manifest_path = os.path.join(project_root, "Packages", "manifest.json")
    lock_path = os.path.join(project_root, "Packages", "packages-lock.json")
    package_source_path = os.path.join(paths.source_root, PACKAGE_TEMPLATE_RELATIVE_PATH)

    require_package_source_root(paths.source_root)

    dependency_value = "file:" + os.path.relpath(
        os.path.realpath(package_source_path),
        os.path.realpath(os.path.join(project_root, "Packages")),
    )

    update_manifest_dependency(manifest_path, dependency_value)
    remove_lock_dependency(lock_path)

    print("xuunity-mcp mode switched: devmode")
    print("project_root=%s" % project_root)
    print("dependency=%s" % dependency_value)
    print("package_source=%s" % package_source_path)
    print("packages_lock_entry_removed=true")
    print("next_step=let Unity re-resolve packages by reopen, focus, or explicit refresh")


def switch_project_to_prodmode(paths: LauncherPaths, args: list) -> None:
    require_command("git")

    project_root = require_project_root_argument(args)
    unity_version = read_project_unity_version(project_root)
    unity_major = unity_version.split(".", 1)[0]

    require_package_source_root(paths.source_root)

    if not os.path.exists(os.path.join(paths.source_root, ".git")):
        raise fail("source git metadata not found: %s/.git" % paths.source_root)

    if not (len(unity_major) == 4 and unity_major.isdigit() and unity_major.startswith("6")):
        raise fail(
            "prodmode is currently supported only for Unity 6000+ package variants; "
            "use devmode for direct local package iteration on %s" % unity_version
        )

    manifest_path = os.path.join(project_root, "Packages", "manifest.json")
    lock_path = os.path.join(project_root, "Packages", "packages-lock.json")
    remote_name = "origin"
    git_url = normalize_git_url_for_unity_upm(run_git(paths.source_root, "remote", "get-url", remote_name))
    git_commit = run_git(paths.source_root, "rev-parse", "HEAD")
    source_branch = run_git(paths.source_root, "branch", "--show-current")
    package_version = read_package_version(paths.source_root)
    release_tag = "v%s" % package_version

    release_commit = remote_release_tag_commit(paths.source_root, remote_name, release_tag)
    if not release_commit:
        sys.stderr.write(
            "prodmode requires the package release tag to be published on the remote before pinning it.\n"
        )
        sys.stderr.write(
            "release tag is not currently advertised by remote '%s': %s\n" % (remote_name, release_tag)
        )
        sys.stderr.write(
            'Push it first, for example: git -C "%s" push %s %s\n'
            % (paths.source_root, remote_name, release_tag)
        )
        raise SystemExit(1)

    dependency_value = "%s?path=/%s#%s" % (git_url, PACKAGE_TEMPLATE_RELATIVE_PATH, release_tag)

    update_manifest_dependency(manifest_path, dependency_value)
    remove_lock_dependency(lock_path)

    worktree_dirty = "true" if run_git(paths.source_root, "status", "--short") else "false"

    print("xuunity-mcp mode switched: prodmode")
    print("project_root=%s" % project_root)
    print("dependency=%s" % dependency_value)
    print("source_remote=%s" % remote_name)
    print("source_branch=%s" % source_branch)
    print("source_commit=%s" % git_commit)
    print("source_release_tag=%s" % release_tag)
    print("source_release_commit=%s" % release_commit)
    if git_commit == release_commit:
        print("source_head_matches_release=true")
    else:
        print("source_head_matches_release=false")
    print("source_worktree_dirty=%s" % worktree_dirty)
    print("packages_lock_entry_removed=true")
    if worktree_dirty == "true":
        print("warning=prodmode pins the published release tag; local working tree has unpublished changes")
    elif git_commit != release_commit:
        print("warning=prodmode pins the published release tag; local HEAD differs from the release commit")
    else:
        print("warning=prodmode pins the published release tag; Unity must re-resolve to apply it")


def dispatch_arrange_unity_windows(paths: LauncherPaths, args: list) -> None:
    arrange_script_path = os.path.join(paths.source_root, "scripts", "tools", "arrange_unity_windows.py")
    if not os.path.isfile(arrange_script_path):
        raise fail("arrange_unity_windows.py not found: %s" % arrange_script_path)
    raise exec_python_script(arrange_script_path, args)


WRAPPER_HELP_TEMPLATE = """Usage: {name} [--compact-summary] <command> [args]

Wrapper commands:
  help | --help
      Show this wrapper command list.
  server-help
      Show the installed server CLI help.
  devmode --project-root PATH
      Point com.xuunity.light-mcp at the local packages/com.xuunity.light-mcp source
      and remove its package-lock entry so Unity can re-resolve it.
  prodmode --project-root PATH
      Pin com.xuunity.light-mcp to the published release tag matching the
      package version and remove its package-lock entry. Refuses missing
      release tags.
  arrange-unity-windows [args]
      Arrange Unity and agent windows on macOS.

Server commands:
  setup-plan, uninstall-plan, and uninstall-apply run from the source checkout
  and do not refresh or write the installed helper. Other server commands
  refresh the installed helper from this source checkout and delegate to
  server.py. Common commands include:
    setup-plan
    setup-apply
    uninstall-plan
    uninstall-apply
    validate-setup
    install-test-framework
    ensure-ready
    request-status-summary
    request-capabilities
    request-health-probe
    request-project-refresh
    request-console-grep
    request-loading-timing
    request-install-test-framework
    request-compile
    request-editmode-tests
    request-playmode-tests
    request-final-status
    restore-editor-state
    batch-compile
    batch-editmode-tests

Mode notes:
  devmode is for local MCP package iteration only.
  prodmode is for published release state only; push the package release tag
  before switching a project back to prodmode.
  After devmode or prodmode, let Unity re-resolve packages by reopen, focus, or
  explicit project refresh.
"""

DEVMODE_HELP_TEMPLATE = """Usage: {name} devmode --project-root PATH

Switch a Unity project to local XUUnity Light Unity MCP package development.

Effects:
  - sets com.xuunity.light-mcp to file:<relative path to packages/com.xuunity.light-mcp>
  - removes the com.xuunity.light-mcp package-lock entry

After switching, let Unity re-resolve packages by reopen, focus, or explicit
project refresh before running validation.
"""

PRODMODE_HELP_TEMPLATE = """Usage: {name} prodmode --project-root PATH

Switch a Unity project to a published Git release-tagged XUUnity Light Unity MCP package.

Effects:
  - verifies the package release tag is advertised by the remote
  - sets com.xuunity.light-mcp to the remote Git package URL pinned to that tag
  - removes the com.xuunity.light-mcp package-lock entry

Push the package release tag before prodmode. After switching, let Unity
re-resolve packages by reopen, focus, or explicit project refresh before running
validation.
"""


def print_wrapper_help() -> None:
    sys.stdout.write(WRAPPER_HELP_TEMPLATE.format(name=launcher_display_name()))


def print_mode_help(mode: str) -> None:
    if mode == "devmode":
        sys.stdout.write(DEVMODE_HELP_TEMPLATE.format(name=launcher_display_name()))
    elif mode == "prodmode":
        sys.stdout.write(PRODMODE_HELP_TEMPLATE.format(name=launcher_display_name()))


def main(argv: list) -> int:
    compact_summary = False
    args = []
    for arg in argv:
        if arg == "--compact-summary":
            compact_summary = True
            continue
        args.append(arg)

    command = args[0] if args else ""

    paths = LauncherPaths()

    if command in ("-h", "--help", "help"):
        print_wrapper_help()
        return 0

    if command in ("setup-plan", "uninstall-plan", "uninstall-apply"):
        if not os.path.isfile(paths.source_server_path):
            raise fail("xuunity-mcp source server not found: %s" % paths.source_server_path)
        raise run_server_with_optional_compact_summary(paths.source_server_path, args, compact_summary)

    if command == "server-help":
        sync_installed_helper_if_needed(paths)
        raise run_server_with_optional_compact_summary(
            paths.server_path, ["--help"] + args[1:], compact_summary
        )

    if command == "arrange-unity-windows":
        dispatch_arrange_unity_windows(paths, args[1:])
        return 0

    if command in ("devmode", "prodmode"):
        mode_args = args[1:]
        if mode_args and mode_args[0] in ("-h", "--help", "help"):
            print_mode_help(command)
            return 0
        if command == "devmode":
            switch_project_to_devmode(paths, mode_args)
        else:
            switch_project_to_prodmode(paths, mode_args)
        return 0

    sync_installed_helper_if_needed(paths)

    if not os.path.isfile(paths.server_path):
        sys.stderr.write("xuunity-mcp server not found: %s\n" % paths.server_path)
        sys.stderr.write("Install it with: bash init_xuunity_light_unity_mcp.sh\n")
        return 1

    raise run_server_with_optional_compact_summary(paths.server_path, args, compact_summary)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
