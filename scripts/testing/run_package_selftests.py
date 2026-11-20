#!/usr/bin/env python3
"""Run the package's own tests in a closed project through `-batchmode -runTests`.

A project made by `-createProject` on Unity 6000.x has no Test Framework, and a
bare `-runTests` there loads the editor and waits forever. This runner adds the
Test Framework and the package's `testables` entry first, always passes its own
`-logFile`, and stops the editor when no results file appears within the bound.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SCRIPT_DIR.parents[1]
TEMPLATES_DIR = SOURCE_ROOT / "templates"
for entry in (TEMPLATES_DIR, SCRIPT_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from server_core import ToolInvocationError, read_json, reconfigure_stdio_utf8, write_json  # noqa: E402
from server_editor_host import find_running_unity_editors_for_project  # noqa: E402
from server_setup_validation import install_test_framework  # noqa: E402
from unity_run_guard import UnitySlotBusy, acquire_slot, default_lock_path, release_slot  # noqa: E402

PACKAGE_NAME = "com.xuunity.light-mcp"
DEFAULT_BOUND_SECONDS = 900
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_SLOT_BUSY = 3
LOG_TAIL_LINES = 25


def ensure_testables(project_root: Path) -> bool:
    manifest_path = project_root / "Packages" / "manifest.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ToolInvocationError("manifest_invalid", f"{manifest_path} is not a JSON object.")
    dependencies = manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}
    if not dependencies.get(PACKAGE_NAME):
        raise ToolInvocationError(
            "package_not_declared",
            f"{PACKAGE_NAME} is not declared in {manifest_path}; install the package before running its self-tests.",
        )
    testables = manifest.get("testables") if isinstance(manifest.get("testables"), list) else []
    if PACKAGE_NAME in testables:
        return False
    manifest["testables"] = [*testables, PACKAGE_NAME]
    write_json(manifest_path, manifest)
    return True


def read_results(results_path: Path) -> dict[str, Any]:
    root = ElementTree.parse(results_path).getroot()

    def count(name: str) -> int:
        try:
            return int(root.get(name) or 0)
        except ValueError:
            return 0

    return {
        "result": str(root.get("result") or ""),
        "total": count("total"),
        "passed": count("passed"),
        "failed": count("failed"),
        "skipped": count("skipped"),
        "inconclusive": count("inconclusive"),
    }


def log_tail(log_path: Path) -> list[str]:
    try:
        return log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL_LINES:]
    except OSError:
        return []


def stop_child(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass


def run_selftests(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    unity = Path(args.unity).expanduser()
    project_root = Path(args.project).expanduser().resolve()
    payload: dict[str, Any] = {
        "action": "run_package_selftests",
        "project_root": str(project_root),
        "test_platform": args.test_platform,
        "test_filter": args.filter or "",
        "bound_seconds": args.bound_seconds,
    }
    if not unity.is_file():
        payload.update({"status": "refused", "error": "unity_executable_not_found", "unity": str(unity)})
        return payload, EXIT_USAGE
    if not (project_root / "Packages" / "manifest.json").is_file():
        payload.update({"status": "refused", "error": "unity_project_not_found"})
        return payload, EXIT_USAGE
    live = [int(item.get("pid") or 0) for item in find_running_unity_editors_for_project(project_root)]
    if live:
        payload.update({"status": "refused", "error": "editor_running_batch_conflict", "live_project_editor_pids": live})
        return payload, EXIT_USAGE

    artifacts = Path(args.artifacts_dir).expanduser().resolve() if args.artifacts_dir else (
        project_root / "Library" / "XUUnityLightMcp" / "selftests" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    )
    artifacts.mkdir(parents=True, exist_ok=True)
    results_path = artifacts / f"results_{args.test_platform.lower()}.xml"
    log_path = artifacts / f"unity_{args.test_platform.lower()}.log"
    payload.update({"results_path": str(results_path), "log_path": str(log_path)})

    slot_path = default_lock_path()
    if not args.no_slot:
        try:
            acquire_slot(
                slot_path, pid=os.getpid(), owner="run_package_selftests",
                command=f"run_package_selftests {project_root.name} {args.test_platform} {args.filter}".strip(),
            )
        except UnitySlotBusy as busy:
            payload.update({"status": "refused", "error": "unity_slot_busy", "lock_path": str(slot_path), "holder": busy.holder})
            return payload, EXIT_SLOT_BUSY
    process: subprocess.Popen | None = None
    started = time.monotonic()
    timed_out = False
    try:
        framework = install_test_framework(project_root, approve=True)
        payload["test_framework"] = {
            "outcome": str(framework.get("outcome") or ""),
            "requested_version": str(framework.get("requested_version") or ""),
        }
        payload["testables_entry_added"] = ensure_testables(project_root)

        command = [
            str(unity), "-batchmode", "-projectPath", str(project_root), "-runTests",
            "-testPlatform", args.test_platform, "-testResults", str(results_path), "-logFile", str(log_path),
        ]
        if args.filter:
            command.extend(["-testFilter", args.filter])
        payload["command"] = command

        started = time.monotonic()
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        deadline = started + max(1, int(args.bound_seconds))
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.5)
        timed_out = process.poll() is None
    finally:
        if process is not None:
            stop_child(process)
        if not args.no_slot:
            release_slot(slot_path, pid=os.getpid())

    payload["elapsed_seconds"] = round(time.monotonic() - started, 1)
    payload["unity_exit_code"] = process.returncode
    if not results_path.is_file():
        payload.update(
            {
                "status": "failed",
                "error": "results_not_written_within_bound" if timed_out else "results_not_written",
                "editor_stopped_by_runner": timed_out,
                "log_tail": log_tail(log_path),
            }
        )
        return payload, EXIT_FAILED
    try:
        results = read_results(results_path)
    except (OSError, ElementTree.ParseError) as exc:
        payload.update({"status": "failed", "error": "results_unreadable", "detail": str(exc)})
        return payload, EXIT_FAILED
    payload["results"] = results
    if results["total"] == 0:
        payload.update({"status": "failed", "error": "no_tests_matched"})
        return payload, EXIT_FAILED
    passed = results["failed"] == 0 and results["result"].lower().startswith("passed")
    payload["status"] = "passed" if passed else "failed"
    if not passed:
        payload["error"] = "tests_failed"
    return payload, 0 if passed else EXIT_FAILED


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("unity", help="Unity editor executable.")
    parser.add_argument("project", help="Closed Unity project that declares the package.")
    parser.add_argument("--filter", default="", help="Value for -testFilter.")
    parser.add_argument("--test-platform", choices=("EditMode", "PlayMode"), default="EditMode")
    parser.add_argument(
        "--bound-seconds", type=int, default=DEFAULT_BOUND_SECONDS,
        help="Stop the editor and fail when no results file exists after this long.",
    )
    parser.add_argument("--artifacts-dir", default="", help="Where the log and results go. Default: under the project's Library.")
    parser.add_argument("--no-slot", action="store_true", help="Skip the host Unity slot; only for a caller that already holds it.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    reconfigure_stdio_utf8()
    args = parse_args(argv)
    try:
        payload, code = run_selftests(args)
    except ToolInvocationError as exc:
        payload, code = {"action": "run_package_selftests", "status": "refused", "error": exc.code, "message": exc.message}, EXIT_USAGE
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
