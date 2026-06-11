#!/usr/bin/env python3
"""Multi-project orchestration for batch compile matrices and GUI test subsets.

Behavior-preserving port of run_multi_project_batch_compile_matrix.sh and
run_multi_project_gui_test_subset.sh. Workers are I/O-bound subprocess waits,
so a ThreadPoolExecutor provides identical cross-platform parallelism without
fork or msys emulation; xargs is gone.

Subcommands: batch-compile-matrix, gui-test-subset. The CLI surface, stdout
line contract (header lines, MULTI_PROJECT_*_SUMMARY_BEGIN/END blocks,
aggregate JSON) and per-project status JSON files match the shell runners.

Optional per-worker watchdog: set XUUNITY_LIGHT_UNITY_MCP_WORKER_TIMEOUT_SECONDS
to a positive number to kill a stuck worker's process tree (exit code 124).
Unset keeps the historical unbounded behavior.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from process_support import resolve_bash_executable, run_to_files

SOURCE_ROOT = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT") or str(SCRIPT_DIR.parents[1])
WRAPPER_PATH = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_WRAPPER") or os.path.join(
    SOURCE_ROOT, "xuunity_light_unity_mcp.sh"
)
ARRANGE_SCRIPT_PATH = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_ARRANGE_SCRIPT") or os.path.join(
    SOURCE_ROOT, "scripts", "tools", "arrange_unity_windows.py"
)
PYTHON_CMD = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_PYTHON") or sys.executable


def worker_timeout_seconds() -> float | None:
    raw = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_WORKER_TIMEOUT_SECONDS") or ""
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def add_templates_to_path() -> None:
    templates_dir = os.path.join(SOURCE_ROOT, "templates")
    if templates_dir not in sys.path:
        sys.path.insert(0, templates_dir)


def fail(message: str, exit_code: int = 1) -> "SystemExit":
    sys.stderr.write(message + "\n")
    return SystemExit(exit_code)


def resolve_repo_root() -> str:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT")
    if explicit:
        if not os.path.isdir(explicit):
            raise fail("XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT does not point to a directory: %s" % explicit)
        return os.path.abspath(explicit)

    for relative in ("../../..", ".."):
        candidate = os.path.abspath(os.path.join(SOURCE_ROOT, relative))
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


def wrapper_command() -> list:
    if os.name == "nt":
        return [resolve_bash_executable(), Path(WRAPPER_PATH).as_posix()]
    return [WRAPPER_PATH]


def require_wrapper() -> None:
    if not os.path.isfile(WRAPPER_PATH):
        raise fail("Wrapper not found: %s" % WRAPPER_PATH)
    if os.name != "nt" and not os.access(WRAPPER_PATH, os.X_OK):
        raise fail("Wrapper is not executable: %s" % WRAPPER_PATH)


def manifest_declares_light_mcp(manifest_path: str) -> bool:
    try:
        text = Path(manifest_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return '"com.xuunity.light-mcp"' in text


def discover_project_roots(repo_root: str) -> list:
    discovered = []
    try:
        children = sorted(os.listdir(repo_root))
    except OSError:
        return discovered
    for child_name in children:
        child_dir = os.path.join(repo_root, child_name)
        if not os.path.isdir(child_dir):
            continue
        manifest_path = os.path.join(child_dir, "Packages", "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        if not os.path.isfile(os.path.join(child_dir, "ProjectSettings", "ProjectVersion.txt")):
            continue
        if manifest_declares_light_mcp(manifest_path):
            discovered.append(child_dir)
    return discovered


def resolve_project_root(candidate: str, repo_root: str) -> str:
    resolved = candidate
    if not os.path.isdir(resolved):
        resolved = os.path.join(repo_root, candidate)
    if not os.path.isdir(resolved):
        raise fail("Project root not found: %s" % candidate)
    return str(Path(resolved).resolve())


def resolve_results_dir(requested: str, mktemp_prefix: str) -> str:
    if requested:
        os.makedirs(requested, exist_ok=True)
        return str(Path(requested).resolve())
    temp_base = os.environ.get("TMPDIR") or "/tmp"
    if not os.path.isdir(temp_base):
        temp_base = None
    return tempfile.mkdtemp(prefix=mktemp_prefix + ".", dir=temp_base)


def parse_positive_int(value: str, message: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise fail(message)
    return int(value)


def run_workers(projects: list, parallelism: int, worker) -> None:
    with ThreadPoolExecutor(max_workers=max(1, parallelism)) as pool:
        futures = [pool.submit(worker, project_root) for project_root in projects]
        for future in futures:
            future.result()


BATCH_USAGE = """Usage:
  run_multi_project_batch_compile_matrix.sh [options]

Options:
  --parallelism N          Number of concurrent batch compile workers. Default: 4
  --repo-root PATH         Root containing Unity project directories. Defaults to env or current repo layout.
  --project-root PATH      Include one explicit Unity project root. Repeatable.
  --close-live-editors     Try to recover/close live editors before batch compile. Default.
  --no-close-live-editors  Skip the recovery preflight and fail fast on editor conflicts.
  --batch-fallback-mode M  Batch lane fallback policy: auto, off, or require-batch. Default: auto.
  --results-dir DIR        Write status artifacts to a persistent directory.
  --cleanup-results        Remove the results dir on exit instead of keeping it.
  --help                   Show this message.

Behavior:
  - auto-discovers direct child Unity projects under the selected repo root
  - filters to projects that already declare com.xuunity.light-mcp
  - runs batch-build-config-compile-matrix in parallel
  - prefers real Unity batchmode and uses GUI fallback when --batch-fallback-mode auto allows it
  - emits one compact per-project summary plus a final aggregate summary
  - keeps results_dir by default so it can feed later GUI-subset runs
"""


def parse_last_json_document(text: str) -> tuple:
    payload = {}
    parse_error = ""
    try:
        decoder = json.JSONDecoder()
        idx = 0
        last_obj = None
        while idx < len(text):
            tail = text[idx:]
            stripped = tail.lstrip()
            if not stripped:
                break
            skipped = len(tail) - len(stripped)
            obj, end = decoder.raw_decode(stripped)
            last_obj = obj
            idx += skipped + end
        if isinstance(last_obj, dict):
            payload = last_obj
        elif last_obj is None:
            parse_error = "no JSON document found on stdout"
        else:
            parse_error = f"unexpected JSON root type: {type(last_obj).__name__}"
    except Exception as exc:
        parse_error = str(exc)
    return payload, parse_error


def build_batch_status(
    project_name: str,
    project_root: str,
    stdout_file: Path,
    stderr_file: Path,
    status_file: Path,
    recover_rc: int,
    batch_rc: int,
    invoked_batch_fallback_mode: str,
) -> None:
    payload = {}
    parse_error = ""
    if stdout_file.is_file():
        payload, parse_error = parse_last_json_document(stdout_file.read_text(encoding="utf-8"))

    result_summary = payload.get("result_summary") if isinstance(payload, dict) else {}
    matrix = result_summary.get("matrix") if isinstance(result_summary, dict) else {}
    stderr_tail = ""
    if stderr_file.is_file():
        stderr_lines = stderr_file.read_text(encoding="utf-8", errors="replace").splitlines()
        stderr_tail = "\n".join(stderr_lines[-20:])

    def first_string(*values):
        for value in values:
            if value is None:
                continue
            text = str(value)
            if text:
                return text
        return ""

    requested_execution_lane = first_string(
        result_summary.get("requested_execution_lane") if isinstance(result_summary, dict) else "",
        payload.get("requested_execution_lane") if isinstance(payload, dict) else "",
        "batch",
    )
    effective_execution_lane = first_string(
        result_summary.get("effective_execution_lane") if isinstance(result_summary, dict) else "",
        payload.get("effective_execution_lane") if isinstance(payload, dict) else "",
    )
    batch_fallback_mode = first_string(
        result_summary.get("batch_fallback_mode") if isinstance(result_summary, dict) else "",
        payload.get("batch_fallback_mode") if isinstance(payload, dict) else "",
        invoked_batch_fallback_mode,
    )
    lane_fallback_reason = first_string(
        result_summary.get("lane_fallback_reason") if isinstance(result_summary, dict) else "",
        payload.get("lane_fallback_reason") if isinstance(payload, dict) else "",
    )
    license_blocker_code = first_string(
        result_summary.get("license_blocker_code") if isinstance(result_summary, dict) else "",
        payload.get("license_blocker_code") if isinstance(payload, dict) else "",
    )
    unity_outcome = first_string(result_summary.get("unity_outcome") if isinstance(result_summary, dict) else "")
    transport_outcome = first_string(
        result_summary.get("transport_outcome") if isinstance(result_summary, dict) else ""
    )
    matrix_status = first_string(matrix.get("status") if isinstance(matrix, dict) else "")
    gui_fallback_pass = (
        bool(payload.get("succeeded")) if isinstance(payload, dict) else False
    ) and unity_outcome == "passed" and transport_outcome == "gui_operation_completed" and effective_execution_lane == "gui"
    batch_matrix_pass = matrix_status == "passed" and effective_execution_lane in {"", "batch"}

    if recover_rc == 0 and batch_rc == 0 and bool(payload.get("succeeded")) and batch_matrix_pass and int(matrix.get("failed", 0)) == 0:
        operator_verdict = "passed_via_batch"
    elif recover_rc == 0 and batch_rc == 0 and gui_fallback_pass:
        operator_verdict = "passed_via_gui_fallback"
    elif unity_outcome in {"not_started", ""} and (
        batch_rc != 0 or transport_outcome.endswith("_blocked") or effective_execution_lane == "none"
    ):
        operator_verdict = "failed_before_unity"
    elif unity_outcome and unity_outcome != "passed":
        operator_verdict = "failed_in_unity"
    else:
        operator_verdict = "failed_wrapper_unity_unproven"

    status = {
        "project": project_name,
        "project_root": project_root,
        "recover_rc": recover_rc,
        "batch_rc": batch_rc,
        "json_parse_ok": bool(payload),
        "parse_error": parse_error,
        "succeeded": bool(payload.get("succeeded")) if isinstance(payload, dict) else False,
        "requested_execution_lane": requested_execution_lane,
        "effective_execution_lane": effective_execution_lane,
        "batch_fallback_mode": batch_fallback_mode,
        "lane_fallback_reason": lane_fallback_reason,
        "license_blocker_code": license_blocker_code,
        "operator_verdict": operator_verdict,
        "unity_outcome": unity_outcome,
        "transport_outcome": transport_outcome,
        "matrix_status": matrix_status,
        "total": int(matrix.get("total", 0)) if isinstance(matrix, dict) else 0,
        "passed": int(matrix.get("passed", 0)) if isinstance(matrix, dict) else 0,
        "failed": int(matrix.get("failed", 0)) if isinstance(matrix, dict) else 0,
        "skipped": int(matrix.get("skipped", 0)) if isinstance(matrix, dict) else 0,
        "summary_file": str(payload.get("summary_file", "")) if isinstance(payload, dict) else "",
        "result_file": str(payload.get("result_file", "")) if isinstance(payload, dict) else "",
        "log_path": str(payload.get("log_path", "")) if isinstance(payload, dict) else "",
        "stderr_tail": stderr_tail,
    }

    status_file.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def run_batch_worker(
    results_dir: str,
    close_live_editors: bool,
    batch_fallback_mode: str,
    project_root: str,
) -> None:
    project_name = os.path.basename(project_root.rstrip("/\\"))
    worker_prefix = os.path.join(results_dir, project_name)
    recover_output_file = worker_prefix + "_recover.log"
    stdout_file = worker_prefix + "_batch_stdout.json"
    stderr_file = worker_prefix + "_batch_stderr.log"
    status_file = worker_prefix + "_status.json"
    recover_rc = 0
    batch_rc = 0
    timeout = worker_timeout_seconds()

    if close_live_editors:
        recover_rc = run_to_files(
            wrapper_command() + ["recover-editor-session", "--project-root", project_root],
            recover_output_file,
            recover_output_file,
            merge_stderr=True,
            timeout_seconds=timeout,
        )

    batch_rc = run_to_files(
        wrapper_command()
        + [
            "batch-build-config-compile-matrix",
            "--project-root",
            project_root,
            "--batch-fallback-mode",
            batch_fallback_mode,
        ],
        stdout_file,
        stderr_file,
        timeout_seconds=timeout,
    )

    build_batch_status(
        project_name,
        project_root,
        Path(stdout_file),
        Path(stderr_file),
        Path(status_file),
        recover_rc,
        batch_rc,
        batch_fallback_mode,
    )


def emit_batch_final_summary(results_dir: str) -> int:
    results_path = Path(results_dir)
    status_files = sorted(results_path.glob("*_status.json"))
    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in status_files]

    print("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_BEGIN")
    overall_failed = 0
    verdict_counts = {}
    for item in statuses:
        gui_fallback_pass = (
            item.get("succeeded") is True
            and item.get("unity_outcome") == "passed"
            and item.get("transport_outcome") == "gui_operation_completed"
            and item.get("effective_execution_lane") == "gui"
        )
        operator_verdict = str(item.get("operator_verdict") or "")
        if not operator_verdict:
            if item.get("matrix_status") == "passed" and item.get("failed", 0) == 0:
                operator_verdict = "passed_via_batch"
            elif gui_fallback_pass:
                operator_verdict = "passed_via_gui_fallback"
            elif item.get("unity_outcome") in {"not_started", ""}:
                operator_verdict = "failed_before_unity"
            elif item.get("unity_outcome") and item.get("unity_outcome") != "passed":
                operator_verdict = "failed_in_unity"
            else:
                operator_verdict = "failed_wrapper_unity_unproven"
        verdict_counts[operator_verdict] = verdict_counts.get(operator_verdict, 0) + 1
        ok = (
            item.get("recover_rc", 0) == 0
            and item.get("batch_rc", 0) == 0
            and item.get("succeeded") is True
            and (item.get("matrix_status") == "passed" or gui_fallback_pass)
            and item.get("failed", 0) == 0
        )
        if not ok:
            overall_failed += 1
        fields = [
            item.get("project", ""),
            f"recover_rc={item.get('recover_rc', 0)}",
            f"batch_rc={item.get('batch_rc', 0)}",
            f"succeeded={str(bool(item.get('succeeded'))).lower()}",
            f"verdict={operator_verdict}",
            f"requested_lane={item.get('requested_execution_lane', '')}",
            f"effective_lane={item.get('effective_execution_lane', '')}",
            f"fallback_mode={item.get('batch_fallback_mode', '')}",
            f"fallback_reason={item.get('lane_fallback_reason', '')}",
            f"license_blocker={item.get('license_blocker_code', '')}",
            f"transport={item.get('transport_outcome', '')}",
            f"unity={item.get('unity_outcome', '')}",
            f"matrix_status={item.get('matrix_status', '')}",
            f"total={item.get('total', 0)}",
            f"passed={item.get('passed', 0)}",
            f"failed={item.get('failed', 0)}",
            f"skipped={item.get('skipped', 0)}",
            f"result_file={item.get('result_file', '')}",
        ]
        print("|".join(fields))
    print("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_END")

    aggregate = {
        "projects_total": len(statuses),
        "projects_failed": overall_failed,
        "operator_verdict_counts": verdict_counts,
        "results_dir": str(results_path),
    }
    print(json.dumps(aggregate, indent=2))
    return 1 if overall_failed else 0


def main_batch(argv: list) -> int:
    repo_root = resolve_repo_root()
    parallelism_value = "4"
    close_live_editors = True
    keep_results = True
    batch_fallback_mode = "auto"
    requested_results_dir = ""
    project_roots = []

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--parallelism":
            parallelism_value = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--repo-root":
            value = argv[index + 1] if index + 1 < len(argv) else ""
            if not os.path.isdir(value):
                raise fail("Repo root not found: %s" % value)
            repo_root = os.path.abspath(value)
            index += 2
        elif arg == "--project-root":
            value = argv[index + 1] if index + 1 < len(argv) else ""
            project_roots.append(resolve_project_root(value, repo_root))
            index += 2
        elif arg == "--close-live-editors":
            close_live_editors = True
            index += 1
        elif arg == "--no-close-live-editors":
            close_live_editors = False
            index += 1
        elif arg == "--batch-fallback-mode":
            batch_fallback_mode = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--results-dir":
            requested_results_dir = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--cleanup-results":
            keep_results = False
            index += 1
        elif arg == "--help":
            sys.stdout.write(BATCH_USAGE)
            return 0
        else:
            sys.stderr.write("Unknown argument: %s\n" % arg)
            sys.stderr.write(BATCH_USAGE)
            return 1

    parallelism = parse_positive_int(parallelism_value, "parallelism must be a positive integer")

    if batch_fallback_mode not in {"auto", "off", "require-batch"}:
        raise fail("batch fallback mode must be one of: auto, off, require-batch")

    require_wrapper()

    if not project_roots:
        project_roots = discover_project_roots(repo_root)

    if not project_roots:
        raise fail("No Unity projects with com.xuunity.light-mcp were discovered.")

    results_dir = resolve_results_dir(requested_results_dir, "xuunity_multi_project_batch_compile")

    try:
        print("discovered_projects=%d" % len(project_roots))
        print("parallelism=%d" % parallelism)
        print("close_live_editors=%s" % ("true" if close_live_editors else "false"))
        print("batch_fallback_mode=%s" % batch_fallback_mode)
        print("results_dir=%s" % results_dir)
        sys.stdout.flush()

        run_workers(
            project_roots,
            parallelism,
            lambda project_root: run_batch_worker(
                results_dir, close_live_editors, batch_fallback_mode, project_root
            ),
        )

        return emit_batch_final_summary(results_dir)
    finally:
        if not keep_results:
            import shutil

            shutil.rmtree(results_dir, ignore_errors=True)


GUI_USAGE = """Usage:
  run_multi_project_gui_test_subset.sh [options]

Options:
  --from-batch-results DIR  Read *_status.json files from a previous batch runner results dir and select only green projects.
  --repo-root PATH          Root containing Unity project directories. Defaults to env or current repo layout.
  --project-root PATH       Include one explicit Unity project root. Repeatable.
  --parallelism N           Number of concurrent GUI workers. Default: 3
  --startup-policy VALUE    ensure-ready startup policy. Default: fail_fast_on_interactive_compile_block
  --window-arrangement MODE Unity window arrangement policy: auto, off, required. Default: auto
  --side-effect-mode MODE   Workspace side-effect accounting: git, off. Default: git
  --side-effect-allow-file FILE
                            JSON allow file with allowedTrackedPaths / allowedPathGlobs.
  --results-dir DIR         Write status artifacts to a persistent directory.
  --cleanup-results         Remove the results dir on exit instead of keeping it.
  --help                    Show this message.

Behavior:
  - selects a GUI-test subset from explicit project roots, a prior batch results dir, or auto-discovery
  - runs recover -> ensure-ready -> editmode -> playmode -> restore for each project
  - keeps editmode and playmode strictly sequential inside each project
  - emits one compact per-project summary plus a final aggregate summary
  - keeps results_dir by default for follow-up inspection
"""


def load_json_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def capture_dirty_paths(workspace_root: str, side_effect_mode: str, output_file: str) -> None:
    if side_effect_mode == "off":
        payload = {"mode": "off", "dirty_paths": []}
    else:
        add_templates_to_path()
        from server_workspace_effects import capture_git_dirty_paths

        mode, dirty_paths = capture_git_dirty_paths(Path(workspace_root))
        payload = {"mode": mode, "dirty_paths": dirty_paths}
    Path(output_file).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def collect_green_projects_from_batch_results(results_dir: str) -> list:
    results_path = Path(results_dir)
    if not results_path.is_dir():
        sys.stderr.write("Batch results dir not found: %s\n" % results_path)
        return []
    selected = []
    for status_path in sorted(results_path.glob("*_status.json")):
        try:
            item = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ok = (
            item.get("recover_rc", 0) == 0
            and item.get("batch_rc", 0) == 0
            and item.get("succeeded") is True
            and item.get("matrix_status") == "passed"
            and int(item.get("failed", 0)) == 0
        )
        if ok and item.get("project_root"):
            selected.append(item["project_root"])
    return selected


def run_json_command(cmd: list, stdout_file: str, stderr_file: str) -> int:
    cmd_rc = run_to_files(cmd, stdout_file, stderr_file, timeout_seconds=worker_timeout_seconds())
    if cmd_rc != 0:
        return cmd_rc
    path = Path(stdout_file)
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    error = payload.get("error") or {}
    status = str(payload.get("status") or "")
    code = str(error.get("code") or "")
    return 70 if code or status == "error" else 0


def should_retry_after_lifecycle_reset(stdout_file: str) -> bool:
    payload = load_json_file(Path(stdout_file))
    if not payload:
        return False
    error = payload.get("error") or {}
    details = error.get("details") or {}
    if str(error.get("code") or "") != "request_lifecycle_reset":
        return False
    final_status = details.get("request_final_status") or {}
    bridge_stabilization = details.get("bridge_stabilization") or final_status.get("bridge_stabilization") or {}
    retryable = bool(details.get("retryable"))
    recommended_next_action = str(
        final_status.get("recommended_next_action") or details.get("recommended_next_action") or ""
    )
    safe_to_retry = bool(bridge_stabilization.get("safe_to_retry"))
    return retryable and safe_to_retry and recommended_next_action == "retry_request"


def should_retry_after_tests_busy(stdout_file: str) -> bool:
    payload = load_json_file(Path(stdout_file))
    if not payload:
        return False
    error = payload.get("error") or {}
    return str(error.get("code") or "") == "tests_busy"


def extract_error_code(stdout_file: str) -> str:
    payload = load_json_file(Path(stdout_file))
    error = payload.get("error") or {}
    return str(error.get("code") or "")


def extract_result_trust_class(stdout_file: str) -> str:
    payload = load_json_file(Path(stdout_file))
    error = payload.get("error") or {}
    details = error.get("details") or {}
    final_status = details.get("request_final_status") or {}
    if payload.get("result_trust_class"):
        return str(payload.get("result_trust_class") or "")
    if details.get("result_trust_class"):
        return str(details.get("result_trust_class") or "")
    if final_status.get("result_trust_class"):
        return str(final_status.get("result_trust_class") or "")
    return ""


def append_to_file(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def run_json_command_with_lifecycle_retry(cmd: list, stdout_file: str, stderr_file: str) -> int:
    cmd_rc = run_json_command(cmd, stdout_file, stderr_file)
    if should_retry_after_lifecycle_reset(stdout_file):
        append_to_file(
            stderr_file,
            "\n[xuunity-multi-project-gui] retrying after lifecycle reset attempt=1/1 trust_class=%s\n"
            % extract_result_trust_class(stdout_file),
        )
        time.sleep(2)
        cmd_rc = run_json_command(cmd, stdout_file, stderr_file)
        if cmd_rc != 0:
            append_to_file(
                stderr_file,
                "[xuunity-multi-project-gui] retry budget exhausted retry_kind=lifecycle_reset final_code=%s trust_class=%s\n"
                % (extract_error_code(stdout_file), extract_result_trust_class(stdout_file)),
            )
    elif should_retry_after_tests_busy(stdout_file):
        append_to_file(stderr_file, "\n[xuunity-multi-project-gui] retrying after tests_busy attempt=1/1\n")
        time.sleep(3)
        cmd_rc = run_json_command(cmd, stdout_file, stderr_file)
        if cmd_rc != 0:
            append_to_file(
                stderr_file,
                "[xuunity-multi-project-gui] retry budget exhausted retry_kind=tests_busy final_code=%s trust_class=%s\n"
                % (extract_error_code(stdout_file), extract_result_trust_class(stdout_file)),
            )
    return cmd_rc


def arrange_windows_best_effort(stdout_file: str, stderr_file: str, editor_pid: int, mode: str) -> int:
    if mode == "off":
        Path(stdout_file).write_text(
            '{\n  "applied": false,\n  "reason": "window_arrangement_off"\n}\n', encoding="utf-8"
        )
        Path(stderr_file).write_text("", encoding="utf-8")
        return 0

    cmd = [PYTHON_CMD, ARRANGE_SCRIPT_PATH, "--include-all-running", "--focus-pid", str(editor_pid)]
    if mode == "required":
        cmd.append("--required")
    return run_to_files(cmd, stdout_file, stderr_file, timeout_seconds=worker_timeout_seconds())


def file_contains(path: str, needle: str) -> bool:
    try:
        return needle in Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def build_gui_status(
    project_name: str,
    project_root_value: str,
    status_file: Path,
    files: dict,
    rcs: dict,
    edit_retry_attempted: bool,
    play_retry_attempted: bool,
    side_effect_mode: str,
    side_effect_allow_file: str,
    side_effect_before_file: Path,
) -> None:
    add_templates_to_path()
    from server_test_reporting import inspect_light_mcp_package_source, load_test_result
    from server_workspace_effects import (
        build_workspace_side_effects,
        capture_git_dirty_paths,
        unavailable_workspace_side_effects,
    )

    project_root = Path(project_root_value)

    def load_json_with_error(path: Path) -> tuple:
        if not path.is_file():
            return {}, ""
        try:
            return json.loads(path.read_text(encoding="utf-8")), ""
        except Exception as exc:
            return {}, str(exc)

    def stderr_tail(path: Path) -> str:
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-20:])

    recover_payload, recover_parse_error = load_json_with_error(files["recover_stdout"])
    ensure_payload, ensure_parse_error = load_json_with_error(files["ensure_stdout"])
    edit_payload, edit_parse_error = load_json_with_error(files["edit_stdout"])
    play_payload, play_parse_error = load_json_with_error(files["play_stdout"])
    restore_payload, restore_parse_error = load_json_with_error(files["restore_stdout"])
    arrange_payload, arrange_parse_error = load_json_with_error(files["arrange_stdout"])

    def decode_embedded_json(payload: dict) -> dict:
        raw = payload.get("payload_json")
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except Exception:
            return {}
        if isinstance(decoded, dict) and not decoded.get("request_id") and payload.get("request_id"):
            decoded["request_id"] = str(payload.get("request_id") or "")
        return decoded if isinstance(decoded, dict) else {}

    edit_decoded = decode_embedded_json(edit_payload)
    play_decoded = decode_embedded_json(play_payload)

    def test_result_path(decoded: dict) -> str:
        request_id = str(decoded.get("request_id") or "")
        if not request_id:
            return ""
        path = project_root / "Library" / "XUUnityLightMcp" / "state" / "test_results" / f"{request_id}.json"
        return str(path)

    def load_persisted_test_summary(decoded: dict, mode: str) -> dict:
        path_value = test_result_path(decoded)
        if path_value:
            path = Path(path_value)
            if path.is_file():
                try:
                    return load_test_result(path)
                except Exception:
                    pass
        failures = decoded.get("failures") if isinstance(decoded.get("failures"), list) else []
        first_failure = failures[0] if failures and isinstance(failures[0], dict) else {}
        return {
            "project": project_name,
            "project_root": str(project_root),
            "mode": mode,
            "status": str(decoded.get("status") or ""),
            "total": int(decoded.get("total", 0) or 0),
            "passed": int(decoded.get("passed", 0) or 0),
            "failed": int(decoded.get("failed", 0) or 0),
            "skipped": int(decoded.get("skipped", 0) or 0),
            "request_id": str(decoded.get("request_id") or ""),
            "result_path": path_value,
            "lifecycle_churn_observed": bool(decoded.get("lifecycle_churn_observed")),
            "first_failure_class": "",
            "first_failure_group_key": "",
            "first_failure_message": str(first_failure.get("message") or ""),
        }

    edit_summary = load_persisted_test_summary(edit_decoded, "editmode")
    play_summary = load_persisted_test_summary(play_decoded, "playmode")

    def load_allow_config(path_value: str) -> dict:
        if not path_value:
            return {}
        return load_json_file(Path(path_value))

    def workspace_side_effects() -> dict:
        if side_effect_mode == "off":
            return unavailable_workspace_side_effects(project_root, mode="off")
        before_payload = load_json_file(side_effect_before_file)
        before_mode = str(before_payload.get("mode") or "unavailable")
        before_dirty_paths = list(before_payload.get("dirty_paths") or [])
        after_mode, after_dirty_paths = capture_git_dirty_paths(project_root)
        effective_mode = "git" if before_mode == "git" and after_mode == "git" else "unavailable"
        if effective_mode != "git":
            return unavailable_workspace_side_effects(project_root)
        return build_workspace_side_effects(
            workspace_root=project_root,
            before_dirty_paths=before_dirty_paths,
            after_dirty_paths=after_dirty_paths,
            mode=effective_mode,
            allow_config=load_allow_config(side_effect_allow_file),
        )

    recover_rc = rcs["recover"]
    ensure_rc = rcs["ensure"]
    edit_rc = rcs["edit"]
    play_rc = rcs["play"]
    arrange_rc = rcs["arrange"]
    restore_rc = rcs["restore"]

    acceptable_test_statuses = {"passed", "no_tests"}
    edit_status = str(edit_summary.get("status") or edit_decoded.get("status", ""))
    play_status = str(play_summary.get("status") or play_decoded.get("status", ""))

    ok = (
        recover_rc == 0
        and ensure_rc == 0
        and edit_rc == 0
        and play_rc == 0
        and restore_rc == 0
        and arrange_rc == 0
        and edit_status in acceptable_test_statuses
        and play_status in acceptable_test_statuses
        and bool(restore_payload.get("closeout_verified")) is True
    )

    status = {
        "project": project_name,
        "project_root": str(project_root),
        "recover_rc": recover_rc,
        "recover_parse_error": recover_parse_error,
        "recover_recommended_next_action": recover_payload.get("recommended_next_action", ""),
        "ensure_rc": ensure_rc,
        "ensure_parse_error": ensure_parse_error,
        "ensure_health": ensure_payload.get("bridge_state", {}).get("health_status", ""),
        "ensure_editor_pid": int(ensure_payload.get("launch", {}).get("editor_pid", 0) or 0),
        "edit_rc": edit_rc,
        "edit_parse_error": edit_parse_error,
        "edit_status": edit_status,
        "edit_total": int(edit_summary.get("total", 0) or 0),
        "edit_passed": int(edit_summary.get("passed", 0) or 0),
        "edit_failed": int(edit_summary.get("failed", 0) or 0),
        "edit_skipped": int(edit_summary.get("skipped", 0) or 0),
        "edit_request_id": str(edit_summary.get("request_id") or ""),
        "edit_result_path": str(edit_summary.get("result_path") or ""),
        "edit_lifecycle_churn_observed": bool(edit_summary.get("lifecycle_churn_observed")),
        "edit_first_failure_class": str(edit_summary.get("first_failure_class") or ""),
        "edit_first_failure_group_key": str(edit_summary.get("first_failure_group_key") or ""),
        "edit_first_failure_message": str(edit_summary.get("first_failure_message") or ""),
        "edit_retry_attempted": edit_retry_attempted,
        "edit_error_code": str((edit_payload.get("error") or {}).get("code") or ""),
        "edit_result_trust_class": (
            str((edit_payload.get("error") or {}).get("details", {}).get("request_final_status", {}).get("result_trust_class") or "")
            or str((edit_payload.get("error") or {}).get("details", {}).get("result_trust_class") or "")
            or ("unity_completed_confirmed" if edit_status in acceptable_test_statuses else "")
        ),
        "edit_retry_budget_total": 1,
        "edit_retry_budget_consumed": 1 if edit_retry_attempted else 0,
        "edit_retry_budget_exhausted": bool(edit_retry_attempted and edit_rc != 0),
        "play_rc": play_rc,
        "play_parse_error": play_parse_error,
        "play_status": play_status,
        "play_total": int(play_summary.get("total", 0) or 0),
        "play_passed": int(play_summary.get("passed", 0) or 0),
        "play_failed": int(play_summary.get("failed", 0) or 0),
        "play_skipped": int(play_summary.get("skipped", 0) or 0),
        "play_request_id": str(play_summary.get("request_id") or ""),
        "play_result_path": str(play_summary.get("result_path") or ""),
        "play_lifecycle_churn_observed": bool(play_summary.get("lifecycle_churn_observed")),
        "play_first_failure_class": str(play_summary.get("first_failure_class") or ""),
        "play_first_failure_group_key": str(play_summary.get("first_failure_group_key") or ""),
        "play_first_failure_message": str(play_summary.get("first_failure_message") or ""),
        "play_retry_attempted": play_retry_attempted,
        "play_error_code": str((play_payload.get("error") or {}).get("code") or ""),
        "play_result_trust_class": (
            str((play_payload.get("error") or {}).get("details", {}).get("request_final_status", {}).get("result_trust_class") or "")
            or str((play_payload.get("error") or {}).get("details", {}).get("result_trust_class") or "")
            or ("unity_completed_confirmed" if play_status in acceptable_test_statuses else "")
        ),
        "play_retry_budget_total": 1,
        "play_retry_budget_consumed": 1 if play_retry_attempted else 0,
        "play_retry_budget_exhausted": bool(play_retry_attempted and play_rc != 0),
        "arrange_rc": arrange_rc,
        "arrange_parse_error": arrange_parse_error,
        "arrange_applied": bool(arrange_payload.get("applied")),
        "arrange_reason": arrange_payload.get("reason", ""),
        "restore_rc": restore_rc,
        "restore_parse_error": restore_parse_error,
        "closeout_verified": bool(restore_payload.get("closeout_verified")),
        "closeout_classification": restore_payload.get("closeout_classification", ""),
        "live_project_editor_pids": restore_payload.get("live_project_editor_pids", []),
        "package_source": inspect_light_mcp_package_source(project_root),
        "workspace_side_effects": workspace_side_effects(),
        "succeeded": ok,
        "stderr_tails": {
            "recover": stderr_tail(files["recover_stderr"]),
            "ensure": stderr_tail(files["ensure_stderr"]),
            "edit": stderr_tail(files["edit_stderr"]),
            "play": stderr_tail(files["play_stderr"]),
            "arrange": stderr_tail(files["arrange_stderr"]),
            "restore": stderr_tail(files["restore_stderr"]),
        },
    }

    status_file.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def run_gui_worker(
    results_dir: str,
    startup_policy: str,
    window_arrangement: str,
    side_effect_mode: str,
    side_effect_allow_file: str,
    project_root: str,
) -> None:
    project_name = os.path.basename(project_root.rstrip("/\\"))
    worker_prefix = os.path.join(results_dir, project_name)

    recover_stdout = worker_prefix + "_recover_stdout.json"
    recover_stderr = worker_prefix + "_recover_stderr.log"
    ensure_stdout = worker_prefix + "_ensure_stdout.json"
    ensure_stderr = worker_prefix + "_ensure_stderr.log"
    edit_stdout = worker_prefix + "_edit_stdout.json"
    edit_stderr = worker_prefix + "_edit_stderr.log"
    play_stdout = worker_prefix + "_play_stdout.json"
    play_stderr = worker_prefix + "_play_stderr.log"
    arrange_stdout = worker_prefix + "_arrange_stdout.json"
    arrange_stderr = worker_prefix + "_arrange_stderr.log"
    restore_stdout = worker_prefix + "_restore_stdout.json"
    restore_stderr = worker_prefix + "_restore_stderr.log"
    side_effect_before_file = worker_prefix + "_side_effects_before.json"
    status_file = worker_prefix + "_status.json"

    rcs = {"recover": 0, "ensure": 0, "edit": 0, "play": 0, "arrange": 0, "restore": 0}
    edit_retry_attempted = False
    play_retry_attempted = False

    capture_dirty_paths(project_root, side_effect_mode, side_effect_before_file)

    rcs["recover"] = run_json_command(
        wrapper_command() + ["recover-editor-session", "--project-root", project_root],
        recover_stdout,
        recover_stderr,
    )

    rcs["ensure"] = run_json_command(
        wrapper_command()
        + [
            "ensure-ready",
            "--project-root",
            project_root,
            "--open-editor",
            "--background-open",
            "--startup-policy",
            startup_policy,
        ],
        ensure_stdout,
        ensure_stderr,
    )

    if rcs["ensure"] == 0:
        ensure_payload = load_json_file(Path(ensure_stdout))
        ensure_editor_pid = int((ensure_payload.get("launch") or {}).get("editor_pid") or 0)
        rcs["arrange"] = arrange_windows_best_effort(
            arrange_stdout, arrange_stderr, ensure_editor_pid, window_arrangement
        )

    if rcs["ensure"] == 0:
        rcs["edit"] = run_json_command_with_lifecycle_retry(
            wrapper_command() + ["request-editmode-tests", "--project-root", project_root],
            edit_stdout,
            edit_stderr,
        )
        edit_retry_attempted = file_contains(edit_stderr, "retrying after lifecycle reset")

    if rcs["ensure"] == 0 and rcs["edit"] == 0:
        rcs["play"] = run_json_command_with_lifecycle_retry(
            wrapper_command() + ["request-playmode-tests", "--project-root", project_root],
            play_stdout,
            play_stderr,
        )
        play_retry_attempted = file_contains(play_stderr, "retrying after lifecycle reset")

    rcs["restore"] = run_json_command(
        wrapper_command() + ["restore-editor-state", "--project-root", project_root],
        restore_stdout,
        restore_stderr,
    )

    build_gui_status(
        project_name,
        project_root,
        Path(status_file),
        {
            "recover_stdout": Path(recover_stdout),
            "recover_stderr": Path(recover_stderr),
            "ensure_stdout": Path(ensure_stdout),
            "ensure_stderr": Path(ensure_stderr),
            "edit_stdout": Path(edit_stdout),
            "edit_stderr": Path(edit_stderr),
            "play_stdout": Path(play_stdout),
            "play_stderr": Path(play_stderr),
            "arrange_stdout": Path(arrange_stdout),
            "arrange_stderr": Path(arrange_stderr),
            "restore_stdout": Path(restore_stdout),
            "restore_stderr": Path(restore_stderr),
        },
        rcs,
        edit_retry_attempted,
        play_retry_attempted,
        side_effect_mode,
        side_effect_allow_file,
        Path(side_effect_before_file),
    )


def emit_gui_final_summary(
    results_dir: str,
    workspace_root: str,
    side_effect_mode: str,
    side_effect_allow_file: str,
    side_effect_before_file: str,
) -> int:
    add_templates_to_path()
    from server_test_reporting import build_failure_groups
    from server_workspace_effects import (
        build_workspace_side_effects,
        capture_git_dirty_paths,
        unavailable_workspace_side_effects,
    )

    results_path = Path(results_dir)
    workspace_path = Path(workspace_root)
    before_path = Path(side_effect_before_file)
    status_files = sorted(results_path.glob("*_status.json"))
    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in status_files]

    def workspace_side_effects() -> dict:
        if side_effect_mode == "off":
            return unavailable_workspace_side_effects(workspace_path, mode="off")
        before_payload = load_json_file(before_path)
        before_mode = str(before_payload.get("mode") or "unavailable")
        before_dirty_paths = list(before_payload.get("dirty_paths") or [])
        after_mode, after_dirty_paths = capture_git_dirty_paths(workspace_path)
        effective_mode = "git" if before_mode == "git" and after_mode == "git" else "unavailable"
        if effective_mode != "git":
            return unavailable_workspace_side_effects(workspace_path)
        allow_config = load_json_file(Path(side_effect_allow_file)) if side_effect_allow_file else {}
        return build_workspace_side_effects(
            workspace_root=workspace_path,
            before_dirty_paths=before_dirty_paths,
            after_dirty_paths=after_dirty_paths,
            mode=effective_mode,
            allow_config=allow_config,
        )

    failure_rows = []
    for item in statuses:
        for mode in ("edit", "play"):
            failure_rows.append(
                {
                    "project": item.get("project", ""),
                    "mode": "editmode" if mode == "edit" else "playmode",
                    "first_failure_class": item.get(f"{mode}_first_failure_class", ""),
                    "first_failure_group_key": item.get(f"{mode}_first_failure_group_key", ""),
                    "first_failure_message": item.get(f"{mode}_first_failure_message", ""),
                }
            )

    package_mismatch_count = sum(
        1
        for item in statuses
        if str((item.get("package_source") or {}).get("alignment") or "") not in {"", "aligned"}
    )
    side_effects = workspace_side_effects()

    print("MULTI_PROJECT_GUI_TEST_SUBSET_SUMMARY_BEGIN")
    overall_failed = 0
    for item in statuses:
        ok = bool(item.get("succeeded"))
        if not ok:
            overall_failed += 1
        fields = [
            item.get("project", ""),
            f"recover_rc={item.get('recover_rc', 0)}",
            f"ensure_rc={item.get('ensure_rc', 0)}",
            f"ensure_health={item.get('ensure_health', '')}",
            f"edit_rc={item.get('edit_rc', 0)}",
            f"edit_status={item.get('edit_status', '')}",
            f"edit_trust={item.get('edit_result_trust_class', '')}",
            f"edit_retry_exhausted={str(bool(item.get('edit_retry_budget_exhausted'))).lower()}",
            f"edit_total={item.get('edit_total', 0)}",
            f"edit_failed={item.get('edit_failed', 0)}",
            f"edit_request_id={item.get('edit_request_id', '')}",
            f"edit_lifecycle_churn={str(bool(item.get('edit_lifecycle_churn_observed'))).lower()}",
            f"play_rc={item.get('play_rc', 0)}",
            f"play_status={item.get('play_status', '')}",
            f"play_trust={item.get('play_result_trust_class', '')}",
            f"play_retry_exhausted={str(bool(item.get('play_retry_budget_exhausted'))).lower()}",
            f"play_total={item.get('play_total', 0)}",
            f"play_failed={item.get('play_failed', 0)}",
            f"play_request_id={item.get('play_request_id', '')}",
            f"play_lifecycle_churn={str(bool(item.get('play_lifecycle_churn_observed'))).lower()}",
            f"arrange_rc={item.get('arrange_rc', 0)}",
            f"arrange_applied={str(bool(item.get('arrange_applied'))).lower()}",
            f"restore_rc={item.get('restore_rc', 0)}",
            f"closeout_verified={str(bool(item.get('closeout_verified'))).lower()}",
            f"package_alignment={(item.get('package_source') or {}).get('alignment', '')}",
            f"succeeded={str(ok).lower()}",
        ]
        print("|".join(fields))
    print("MULTI_PROJECT_GUI_TEST_SUBSET_SUMMARY_END")

    aggregate = {
        "projects_total": len(statuses),
        "projects_failed": overall_failed,
        "results_dir": str(results_path),
        "failure_groups": build_failure_groups(failure_rows),
        "package_mismatch_count": package_mismatch_count,
        "workspace_side_effects": side_effects,
    }
    (results_path / "_aggregate_summary.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(aggregate, indent=2))
    return 1 if overall_failed else 0


def main_gui(argv: list) -> int:
    repo_root = resolve_repo_root()
    parallelism_value = "3"
    startup_policy = "fail_fast_on_interactive_compile_block"
    batch_results_dir = ""
    keep_results = True
    requested_results_dir = ""
    project_roots = []
    window_arrangement = "auto"
    side_effect_mode = "git"
    side_effect_allow_file = ""

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--from-batch-results":
            batch_results_dir = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--repo-root":
            value = argv[index + 1] if index + 1 < len(argv) else ""
            if not os.path.isdir(value):
                raise fail("Repo root not found: %s" % value)
            repo_root = os.path.abspath(value)
            index += 2
        elif arg == "--project-root":
            value = argv[index + 1] if index + 1 < len(argv) else ""
            project_roots.append(resolve_project_root(value, repo_root))
            index += 2
        elif arg == "--parallelism":
            parallelism_value = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--startup-policy":
            startup_policy = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--window-arrangement":
            window_arrangement = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--side-effect-mode":
            side_effect_mode = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--side-effect-allow-file":
            side_effect_allow_file = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--results-dir":
            requested_results_dir = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
        elif arg == "--cleanup-results":
            keep_results = False
            index += 1
        elif arg == "--help":
            sys.stdout.write(GUI_USAGE)
            return 0
        else:
            sys.stderr.write("Unknown argument: %s\n" % arg)
            sys.stderr.write(GUI_USAGE)
            return 1

    parallelism = parse_positive_int(parallelism_value, "parallelism must be a positive integer")

    if window_arrangement not in {"auto", "off", "required"}:
        raise fail("window arrangement must be one of: auto, off, required")

    if side_effect_mode not in {"git", "off"}:
        raise fail("side-effect mode must be one of: git, off")

    require_wrapper()

    if batch_results_dir and not project_roots:
        project_roots = collect_green_projects_from_batch_results(batch_results_dir)

    if not project_roots:
        project_roots = discover_project_roots(repo_root)

    if not project_roots:
        raise fail("No Unity projects selected for GUI test subset run.")

    results_dir = resolve_results_dir(requested_results_dir, "xuunity_multi_project_gui_subset")

    try:
        print("selected_projects=%d" % len(project_roots))
        print("parallelism=%d" % parallelism)
        print("startup_policy=%s" % startup_policy)
        print("window_arrangement=%s" % window_arrangement)
        print("side_effect_mode=%s" % side_effect_mode)
        print("results_dir=%s" % results_dir)
        sys.stdout.flush()

        workspace_side_effect_before_file = os.path.join(results_dir, "_workspace_side_effects_before.json")
        capture_dirty_paths(repo_root, side_effect_mode, workspace_side_effect_before_file)

        run_workers(
            project_roots,
            parallelism,
            lambda project_root: run_gui_worker(
                results_dir,
                startup_policy,
                window_arrangement,
                side_effect_mode,
                side_effect_allow_file,
                project_root,
            ),
        )

        return emit_gui_final_summary(
            results_dir,
            repo_root,
            side_effect_mode,
            side_effect_allow_file,
            workspace_side_effect_before_file,
        )
    finally:
        if not keep_results:
            import shutil

            shutil.rmtree(results_dir, ignore_errors=True)


def main(argv: list) -> int:
    if not argv or argv[0] not in {"batch-compile-matrix", "gui-test-subset"}:
        sys.stderr.write("Usage: run_multi_project.py {batch-compile-matrix|gui-test-subset} [options]\n")
        return 1
    if argv[0] == "batch-compile-matrix":
        return main_batch(argv[1:])
    return main_gui(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
