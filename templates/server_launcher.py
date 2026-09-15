"""Wrapper core for the operator-side launcher.

Behavior-preserving port of the historical xuunity_light_unity_mcp.sh wrapper
body. Shell entrypoints stay thin (find a Python >= 3.10 interpreter, exec this
module); every resolve, mode switch, sync, and dispatch decision lives here.

Contract mirrors the bash wrapper exactly: command names, env variables
(XUUNITY_LIGHT_UNITY_MCP_*), stdout/stderr line shapes, and exit codes.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
RUN_CMD_TEMPLATE_RELATIVE_PATH = "templates/run.cmd"
RUN_PS1_TEMPLATE_RELATIVE_PATH = "templates/run.ps1"
REFRESH_LAUNCHER_RELATIVE_PATH = "run_installed_or_refresh_xuunity_mcp.sh"
REFRESH_PYTHON_RELATIVE_PATH = "run_installed_or_refresh_xuunity_mcp.py"
REFRESH_CMD_RELATIVE_PATH = "run_installed_or_refresh_xuunity_mcp.cmd"
SERVER_MODULES_TEMPLATE_GLOB = "server_*.py"
RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH = "templates/xuunity_light_unity_mcp_runtime_defaults.json"
PACKAGE_TEMPLATE_RELATIVE_PATH = "packages/com.xuunity.light-mcp"
PACKAGE_METADATA_RELATIVE_PATH = PACKAGE_TEMPLATE_RELATIVE_PATH + "/package.json"

_LAUNCHER_DIR = Path(os.path.abspath(__file__)).parent
sys.path.insert(0, str(_LAUNCHER_DIR))

import server_setup_wizard
from server_core import hidden_window_subprocess_kwargs, reconfigure_stdio_utf8

COMPACT_OUTPUT_MAX_BYTES = 8192


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
        self.run_cmd_path = os.path.join(self.install_dir, "run.cmd")
        self.run_ps1_path = os.path.join(self.install_dir, "run.ps1")
        self.refresh_run_path = os.path.join(self.install_dir, "run_installed_or_refresh_xuunity_mcp.sh")
        self.refresh_python_path = os.path.join(self.install_dir, "run_installed_or_refresh_xuunity_mcp.py")
        self.refresh_cmd_path = os.path.join(self.install_dir, "run_installed_or_refresh_xuunity_mcp.cmd")
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


PAYLOAD_SHAPE_KEYS = ("action", "status", "error", "payload_mode", "payload_type", "request_id")


def _extract_last_json_object(payload_text: str) -> dict:
    decoder = json.JSONDecoder()
    last: dict = {}
    last_end = -1
    last_start = -1
    payload_shaped: dict = {}
    payload_shaped_end = -1
    text = str(payload_text or "")
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        absolute_end = index + consumed
        if any(key in value for key in PAYLOAD_SHAPE_KEYS) and absolute_end >= payload_shaped_end:
            payload_shaped = value
            payload_shaped_end = absolute_end
        if absolute_end > last_end or (absolute_end == last_end and (last_start < 0 or index < last_start)):
            last = value
            last_end = absolute_end
            last_start = index
    return payload_shaped or last


def _artifact_pointers(payload: dict) -> dict:
    pointers: dict[str, str] = {}
    allowed = {
        "result_path",
        "result_file",
        "summary_file",
        "editor_log_path",
        "batchmode_probe_log_path",
        "journal_event_path",
        "test_result_path",
        "cache_path",
    }

    def visit(value, depth: int = 0) -> None:
        if depth > 3 or len(pointers) >= 8:
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in allowed and isinstance(nested, str) and nested:
                    pointers.setdefault(key, nested)
                elif isinstance(nested, (dict, list)):
                    visit(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value[:8]:
                visit(nested, depth + 1)

    visit(payload)
    return pointers


def build_compact_terminal_envelope(payload: dict, exit_code: int, stderr_text: str = "") -> dict:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    envelope: dict = {
        "payload_mode": "compact_terminal_envelope",
        "exit_code": int(exit_code),
        "outcome": "error" if exit_code != 0 or error else "ok",
        "action": str(payload.get("action") or ""),
        "request_id": str(payload.get("request_id") or ""),
    }
    for key in (
        "status",
        "verdict",
        "succeeded",
        "health_status",
        "operation_outcome",
        "result_trust_class",
        "terminal_disposition",
        "terminal_lifecycle_disposition",
        "test_verdict",
        "total",
        "passed",
        "failed",
        "skipped",
        "retryable",
        "retry_required",
        "recommended_next_action",
        "closeout_classification",
        "closeout_verified",
        "process_exit_verified",
        "same_project_editor_closed",
        "recommended_execution_lane",
        "batchmode_supported",
        "editor_ui_supported",
        "batchmode_blocker_code",
        "licensing_handoff_classification",
        "manual_user_action_required",
        "post_lifecycle_status_confirmation",
    ):
        value = payload.get(key)
        if value is not None and value != "":
            envelope[key] = value

    for key in (
        "closeout_classification",
        "closeout_verified",
        "process_exit_verified",
        "same_project_editor_closed",
        "recommended_next_action",
        "result_trust_class",
        "operation_outcome",
        "retryable",
    ):
        if key not in envelope and details.get(key) is not None and details.get(key) != "":
            envelope[key] = details.get(key)

    payload_type = str(payload.get("payload_type") or "")
    decoded_payload: dict = {}
    if isinstance(payload.get("payload_json"), str):
        try:
            decoded = json.loads(payload.get("payload_json") or "{}")
            if isinstance(decoded, dict):
                decoded_payload = decoded
        except json.JSONDecodeError:
            decoded_payload = {}
    if payload_type:
        envelope["payload_type"] = payload_type
    if payload_type.startswith("unity.tests."):
        envelope["test_verdict"] = str(decoded_payload.get("status") or "")
        for key in ("total", "passed", "failed", "skipped"):
            envelope[key] = int(decoded_payload.get(key) or 0)
        failures = decoded_payload.get("failures")
        if isinstance(failures, list) and failures:
            envelope["first_failure"] = failures[0]
    elif payload_type == "unity.compile.matrix":
        envelope["matrix_status"] = str(decoded_payload.get("status") or "")
        for key in ("total", "passed", "failed"):
            envelope[key] = int(decoded_payload.get(key) or 0)

    result_summary = payload.get("result_summary") if isinstance(payload.get("result_summary"), dict) else {}
    if result_summary:
        for key in ("unity_outcome", "transport_outcome", "requested_execution_lane", "effective_execution_lane"):
            if result_summary.get(key) is not None and result_summary.get(key) != "":
                envelope[key] = result_summary.get(key)
        matrix = result_summary.get("matrix") if isinstance(result_summary.get("matrix"), dict) else {}
        if matrix:
            envelope["matrix"] = {
                key: matrix.get(key) for key in ("status", "total", "passed", "failed") if key in matrix
            }

    health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
    if health:
        envelope["health"] = {
            key: health.get(key)
            for key in ("status", "compiler_error_count", "playmode_state", "pending_request_count", "busy_reason")
            if key in health
        }
    operator_verdict = payload.get("operator_verdict") if isinstance(payload.get("operator_verdict"), dict) else {}
    if operator_verdict:
        envelope["operator_verdict"] = {
            key: operator_verdict.get(key)
            for key in ("status", "should_retry", "next_action")
            if key in operator_verdict
        }
    licensing_resolution = payload.get("licensing_ipc_resolution")
    if not isinstance(licensing_resolution, dict):
        licensing_resolution = details.get("licensing_ipc_resolution") if isinstance(details, dict) else {}
    if isinstance(licensing_resolution, dict) and licensing_resolution:
        envelope["licensing_ipc_resolution"] = {
            key: licensing_resolution.get(key)
            for key in (
                "status",
                "candidate_count",
                "confidence",
                "validation_result",
                "action_classification",
                "required_human_action",
                "unity_argument_forwarded",
                "raw_channel_exposed",
            )
            if key in licensing_resolution
        }
    if error:
        envelope["error"] = {
            "code": str(error.get("code") or ""),
            "message": re.sub(
                r"(?:Unity-)?LicenseClient-[A-Za-z0-9._-]+",
                "<redacted-licensing-channel>",
                str(error.get("message") or ""),
            )[:600],
            "recommended_next_action": str(
                error.get("recommended_next_action") or details.get("recommended_next_action") or ""
            ),
        }
    elif exit_code != 0 and stderr_text:
        envelope["error"] = {
            "code": "child_process_failed",
            "message": re.sub(
                r"(?:Unity-)?LicenseClient-[A-Za-z0-9._-]+",
                "<redacted-licensing-channel>",
                str(stderr_text),
            )[-600:],
        }
    if stderr_text and (exit_code != 0 or error) and "child_stderr_tail" not in envelope:
        envelope["child_stderr_tail"] = re.sub(
            r"(?:Unity-)?LicenseClient-[A-Za-z0-9._-]+",
            "<redacted-licensing-channel>",
            str(stderr_text),
        )[-600:]

    first_failures = payload.get("first_failures")
    if "first_failure" not in envelope and isinstance(first_failures, list) and first_failures:
        envelope["first_failure"] = first_failures[0]
    pointers = _artifact_pointers(payload)
    if pointers:
        envelope["artifacts"] = pointers
    envelope["full_payload_available"] = True
    if isinstance(payload.get("full_payload_command"), str) and payload.get("full_payload_command"):
        envelope["full_payload_command"] = payload.get("full_payload_command")
    return envelope


def _bounded_compact_json(envelope: dict) -> str:
    encoded = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= COMPACT_OUTPUT_MAX_BYTES:
        return encoded + "\n"
    reduced = {
        "payload_mode": "compact_terminal_envelope",
        "outcome": envelope.get("outcome"),
        "exit_code": envelope.get("exit_code"),
        "action": envelope.get("action"),
        "request_id": envelope.get("request_id"),
        "error": envelope.get("error"),
        "artifacts": envelope.get("artifacts"),
        "recommended_next_action": envelope.get("recommended_next_action"),
        "full_payload_available": True,
        "compact_truncated": True,
    }
    encoded = json.dumps(reduced, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= COMPACT_OUTPUT_MAX_BYTES:
        return encoded + "\n"
    minimal = {
        "payload_mode": "compact_terminal_envelope",
        "outcome": envelope.get("outcome"),
        "exit_code": envelope.get("exit_code"),
        "action": str(envelope.get("action") or "")[:256],
        "request_id": str(envelope.get("request_id") or "")[:256],
        "recommended_next_action": str(envelope.get("recommended_next_action") or "")[:512],
        "full_payload_available": True,
        "compact_truncated": True,
    }
    return json.dumps(minimal, ensure_ascii=True, separators=(",", ":")) + "\n"


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
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_window_subprocess_kwargs(),
    )
    payload = _extract_last_json_object(completed.stdout)
    if not payload:
        payload = {
            "action": str(args[0] if args else ""),
            "error": {
                "code": "compact_payload_parse_failed",
                "message": "The child command did not emit a parseable JSON object.",
            },
        }
    envelope = build_compact_terminal_envelope(payload, completed.returncode, completed.stderr)
    sys.stdout.write(_bounded_compact_json(envelope))
    sys.stdout.flush()
    return SystemExit(completed.returncode)


def sync_file_from_source(paths: LauncherPaths, destination_path: str, relative_source_path: str) -> None:
    source_path = os.path.join(paths.source_root, relative_source_path)
    payload = Path(source_path).read_bytes()
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() == payload:
        return
    destination.write_bytes(payload)


def write_helper_integrity_manifest(install_dir: str) -> None:
    target = Path(install_dir)
    package_path = target / PACKAGE_METADATA_RELATIVE_PATH
    package = json.loads(package_path.read_text(encoding="utf-8"))
    names = {
        "server.py",
        "run.sh",
        "run.cmd",
        "run.ps1",
        "run_installed_or_refresh_xuunity_mcp.sh",
        "run_installed_or_refresh_xuunity_mcp.py",
        "run_installed_or_refresh_xuunity_mcp.cmd",
        os.path.basename(RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH),
        PACKAGE_METADATA_RELATIVE_PATH,
        ".source_root",
    }
    names.update(path.name for path in target.glob(SERVER_MODULES_TEMPLATE_GLOB) if path.is_file())
    files = {
        relative_name: hashlib.sha256((target / relative_name).read_bytes()).hexdigest()
        for relative_name in sorted(names)
        if (target / relative_name).is_file()
    }
    payload = {
        "schema_version": 1,
        "version": str(package.get("version") or ""),
        "safety_epoch": 2,
        "files": files,
    }
    fd, temp_name = tempfile.mkstemp(prefix=".install_manifest.", suffix=".tmp", dir=target)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target / ".install_manifest.json")
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def sync_installed_helper_if_needed(paths: LauncherPaths) -> None:
    if not os.path.isfile(os.path.join(paths.source_root, SERVER_TEMPLATE_RELATIVE_PATH)):
        return

    os.makedirs(paths.install_dir, exist_ok=True)

    sync_file_from_source(paths, paths.run_path, RUN_TEMPLATE_RELATIVE_PATH)
    if os.path.isfile(os.path.join(paths.source_root, RUN_CMD_TEMPLATE_RELATIVE_PATH)):
        sync_file_from_source(paths, paths.run_cmd_path, RUN_CMD_TEMPLATE_RELATIVE_PATH)
    if os.path.isfile(os.path.join(paths.source_root, RUN_PS1_TEMPLATE_RELATIVE_PATH)):
        sync_file_from_source(paths, paths.run_ps1_path, RUN_PS1_TEMPLATE_RELATIVE_PATH)
    if os.path.isfile(os.path.join(paths.source_root, REFRESH_LAUNCHER_RELATIVE_PATH)):
        sync_file_from_source(paths, paths.refresh_run_path, REFRESH_LAUNCHER_RELATIVE_PATH)
    if os.path.isfile(os.path.join(paths.source_root, REFRESH_PYTHON_RELATIVE_PATH)):
        sync_file_from_source(paths, paths.refresh_python_path, REFRESH_PYTHON_RELATIVE_PATH)
    if os.path.isfile(os.path.join(paths.source_root, REFRESH_CMD_RELATIVE_PATH)):
        sync_file_from_source(paths, paths.refresh_cmd_path, REFRESH_CMD_RELATIVE_PATH)
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
    Path(paths.install_dir, ".source_root").write_text(paths.source_root + "\n", encoding="utf-8")
    # Keep the legacy version marker stale until every supporting module and
    # launcher has been published. This makes interrupted refreshes retryable.
    sync_file_from_source(paths, paths.server_path, SERVER_TEMPLATE_RELATIVE_PATH)
    os.chmod(paths.run_path, 0o755)
    if os.path.isfile(paths.refresh_run_path):
        os.chmod(paths.refresh_run_path, 0o755)
    write_helper_integrity_manifest(paths.install_dir)


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


GIT_LOCAL_TIMEOUT_SECONDS = 30.0
GIT_REMOTE_TIMEOUT_SECONDS = 60.0


def run_git(source_root: str, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", source_root] + list(args),
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_LOCAL_TIMEOUT_SECONDS,
            **hidden_window_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "git %s timed out after %.0fs in %s\n" % (" ".join(args), GIT_LOCAL_TIMEOUT_SECONDS, source_root)
        )
        raise SystemExit(124)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.stdout.strip()


def remote_release_tag_commit(source_root: str, remote_name: str, release_tag: str):
    tag_ref = "refs/tags/%s" % release_tag
    peeled_ref = tag_ref + "^{}"
    try:
        completed = subprocess.run(
            ["git", "-C", source_root, "ls-remote", "--tags", remote_name, tag_ref, peeled_ref],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_REMOTE_TIMEOUT_SECONDS,
            **hidden_window_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return None
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


def format_package_file_dependency(package_source_path: str, packages_dir: str) -> str:
    """UPM `file:` value: forward slashes on every host, absolute on cross-drive."""
    try:
        relative_source = os.path.relpath(
            os.path.realpath(package_source_path),
            os.path.realpath(packages_dir),
        )
        return "file:" + relative_source.replace(os.sep, "/").replace("\\", "/")
    except ValueError:
        return "file:" + Path(package_source_path).resolve().as_posix()


def update_manifest_dependency(manifest_path: str, dependency_value: str) -> None:
    manifest = Path(manifest_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    dependencies = data.setdefault("dependencies", {})
    dependencies[PACKAGE_NAME] = dependency_value
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def remove_lock_dependency(lock_path: str) -> None:
    lock = Path(lock_path)
    if not lock.is_file():
        return
    data = json.loads(lock.read_text(encoding="utf-8"))
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict) and PACKAGE_NAME in dependencies:
        del dependencies[PACKAGE_NAME]
        lock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def switch_project_to_devmode(paths: LauncherPaths, args: list) -> None:
    project_root = require_project_root_argument(args)
    manifest_path = os.path.join(project_root, "Packages", "manifest.json")
    lock_path = os.path.join(project_root, "Packages", "packages-lock.json")
    package_source_path = os.path.join(paths.source_root, PACKAGE_TEMPLATE_RELATIVE_PATH)

    require_package_source_root(paths.source_root)

    dependency_value = format_package_file_dependency(
        package_source_path, os.path.join(project_root, "Packages")
    )

    update_manifest_dependency(manifest_path, dependency_value)
    remove_lock_dependency(lock_path)

    print("xuunity-mcp mode switched: devmode")
    print("project_root=%s" % project_root)
    print("dependency=%s" % dependency_value)
    print("package_source=%s" % package_source_path)
    print("packages_lock_entry_removed=true")
    print("next_step=let Unity re-resolve packages by reopen, focus, or explicit refresh")
    print(
        'recommended_refresh_command=%s request-project-refresh '
        '--project-root "%s" --resolve-packages --timeout-ms 180000'
        % (launcher_display_name(), project_root)
    )
    print(
        "recommended_refresh_args_json=%s"
        % json.dumps(
            [
                "request-project-refresh",
                "--project-root",
                project_root,
                "--resolve-packages",
                "--timeout-ms",
                "180000",
            ],
            ensure_ascii=True,
        )
    )


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
Wrapper commands: help | --help; server-help; devmode --project-root PATH; prodmode --project-root PATH; arrange-unity-windows [args]
Setup/uninstall plans run from source; other server commands refresh the installed helper.
Modes: devmode uses local source; prodmode requires a published release tag. See <mode> --help.
--compact-summary prints one bounded terminal JSON envelope; omit it for full output.
{server_commands}
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


def server_command_help() -> str:
    import argparse
    from server_cli_parser import build_parser

    parser = build_parser()
    sub = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    descriptions = {action.dest: action.help for action in sub._choices_actions}
    groups = {name: [] for name in ("setup", "status", "request", "lifecycle", "batch", "project-action", "other")}
    for name, command in sub.choices.items():
        if name.startswith(("setup-", "uninstall-", "validate-setup", "install-")):
            group = "setup"
        elif name.startswith("batch-"):
            group = "batch"
        elif name.startswith(("project-action-", "project-hook-")):
            group = "project-action"
        elif name in {"open-editor", "recover-editor-session", "restore-editor-state", "ensure-ready", "request-editor-quit"}:
            group = "lifecycle"
        elif name.startswith(("request-status", "request-capabilities", "request-health", "project-discovery")):
            group = "status"
        elif name.startswith("request-"):
            group = "request"
        else:
            group = "other"
        required = " ".join(
            (action.option_strings[0] if action.option_strings else action.dest) +
            (" " + str(action.metavar or action.dest.upper()) if action.nargs != 0 else "")
            for action in command._actions if action.required
        )
        groups[group].append(f"  {name}{' ' + required if required else ''} — {descriptions.get(name, '')}")
    return "\n".join(group + ":\n" + "\n".join(lines) for group, lines in groups.items() if lines)


def print_wrapper_help() -> None:
    sys.stdout.write(WRAPPER_HELP_TEMPLATE.format(name=launcher_display_name(), server_commands=server_command_help()))


def print_mode_help(mode: str) -> None:
    if mode == "devmode":
        sys.stdout.write(DEVMODE_HELP_TEMPLATE.format(name=launcher_display_name()))
    elif mode == "prodmode":
        sys.stdout.write(PRODMODE_HELP_TEMPLATE.format(name=launcher_display_name()))


def main(argv: list) -> int:
    reconfigure_stdio_utf8()
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
