"""Full host↔bridge file-IPC path exercised against a simulated editor.

Before this file, the file-IPC transport was tested with in-process fixtures
only; no test ever ran the host stack against a *separate OS process* playing
the Unity side. These tests close that gap without Unity:

- a bridge-simulator subprocess (tests/bridge_ipc_simulator.py) publishes a
  live heartbeat and answers ``unity.status`` requests through the real
  inbox/outbox files, while the MCP server — spawned through the real per-OS
  launcher chain — drives the request. This validates request write, response
  poll/parse/unlink, state liveness (editor_pid), and transport resolution on
  the actual host filesystem (NTFS on the Windows CI leg).
- a writer subprocess rewrites one JSON file through the production
  ``write_json`` atomic publish while this process reads it concurrently,
  asserting a reader can never observe a torn payload (the W2-7 class:
  half-written JSON consumed by a poller).
"""

import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
TEMPLATES_DIR = TESTS_DIR.parent / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from bash_support import run_with_timeout, skip_if_prior_subprocess_timeout
from bridge_ipc_simulator import SIMULATOR_MARKER, STRESS_BLOB
from server_bridge_paths import bridge_config_path, bridge_state_path, request_journal_dir
from server_core import read_json, write_json
from test_mcp_stdio_e2e import (
    PROTOCOL_VERSION,
    encode_stdin,
    launcher_argv,
    make_launcher_env,
    mcp_notification,
    mcp_request,
    scaffold_unity_project,
)

SIMULATOR_PATH = TESTS_DIR / "bridge_ipc_simulator.py"


def start_simulator(
    project_root: Path,
    deadline_seconds: float,
    *,
    mode: str = "simulate",
) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(SIMULATOR_PATH), mode, str(project_root), str(deadline_seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def stop_process(process: subprocess.Popen) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=15)
    return stdout or "", stderr or ""


class UnityStatusThroughSimulatedBridgeTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def wait_for_simulator_state(self, project_root: Path, process: subprocess.Popen) -> None:
        state_path = bridge_state_path(project_root)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if state_path.is_file():
                return
            if process.poll() is not None:
                stdout, stderr = stop_process(process)
                self.fail(f"simulator exited before publishing state: {stdout} {stderr}")
            time.sleep(0.1)
        stdout, stderr = stop_process(process)
        self.fail(f"simulator never published bridge state: {stdout} {stderr}")

    def test_unity_status_round_trips_launcher_transport_and_simulated_editor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Симулятор Бриджа" / "Fake Project", declare_light_mcp=True
            )
            write_json(
                bridge_config_path(project_root),
                {"enabled": True, "transport": "file_ipc"},
            )
            env = make_launcher_env(temp_root / "neutral-install")

            simulator = start_simulator(project_root, deadline_seconds=240.0)
            try:
                self.wait_for_simulator_state(project_root, simulator)

                completed = run_with_timeout(
                    launcher_argv(),
                    cwd=str(TESTS_DIR.parent),
                    env=env,
                    timeout_seconds=240,
                    input_text=encode_stdin(
                        [
                            mcp_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}),
                            mcp_notification("notifications/initialized"),
                            mcp_request(
                                2,
                                "tools/call",
                                {
                                    "name": "unity_status",
                                    "arguments": {
                                        "projectRoot": str(project_root),
                                        "timeoutMs": 30000,
                                    },
                                },
                            ),
                        ]
                    ),
                )
            finally:
                sim_stdout, sim_stderr = stop_process(simulator)

            self.assertEqual(0, completed.returncode, completed.stderr + sim_stderr)
            responses = {}
            for line in completed.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    payload = json.loads(line)
                    responses[payload.get("id")] = payload

            call_result = responses[2]["result"]
            self.assertFalse(
                call_result.get("isError"),
                f"unity_status through the simulated bridge failed: {call_result}"
                f" simulator: {sim_stdout} {sim_stderr}",
            )
            payload = call_result["structuredContent"]
            self.assertEqual(SIMULATOR_MARKER, payload.get("simulator_marker"), payload)
            self.assertEqual("unity.status", payload.get("operation"), payload)
            self.assertEqual(
                project_root.resolve(),
                Path(str(payload.get("echo_project_root") or "")).resolve(),
                "project root must reach the editor side intact through the request file",
            )

    def test_generation_change_preserves_completed_outcome_without_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Lifecycle Delivery" / "Fake Project", declare_light_mcp=True
            )
            write_json(
                bridge_config_path(project_root),
                {"enabled": True, "transport": "file_ipc"},
            )
            env = make_launcher_env(temp_root / "neutral-install")

            simulator = start_simulator(
                project_root,
                deadline_seconds=30.0,
                mode="complete-without-delivery",
            )
            try:
                self.wait_for_simulator_state(project_root, simulator)
                completed = run_with_timeout(
                    launcher_argv(),
                    cwd=str(TESTS_DIR.parent),
                    env=env,
                    timeout_seconds=240,
                    input_text=encode_stdin(
                        [
                            mcp_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}),
                            mcp_notification("notifications/initialized"),
                            mcp_request(
                                2,
                                "tools/call",
                                {
                                    "name": "unity_status",
                                    "arguments": {
                                        "projectRoot": str(project_root),
                                        "timeoutMs": 1200,
                                    },
                                },
                            ),
                        ]
                    ),
                )

                request_match = re.search(r"request_id=([0-9a-fA-F-]{36})", completed.stderr)
                self.assertIsNotNone(request_match, completed.stderr)
                request_id = request_match.group(1)

                final_status = run_with_timeout(
                    launcher_argv(
                        [
                            "request-final-status",
                            "--project-root",
                            str(project_root),
                            "--request-id",
                            request_id,
                            "--timeout-ms",
                            "0",
                        ]
                    ),
                    cwd=str(TESTS_DIR.parent),
                    env=env,
                    timeout_seconds=240,
                )
            finally:
                sim_stdout, sim_stderr = stop_process(simulator)

            self.assertEqual(0, completed.returncode, completed.stderr + sim_stderr)
            responses = {}
            for line in completed.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    payload = json.loads(line)
                    responses[payload.get("id")] = payload
            call_result = responses[2]["result"]
            self.assertTrue(call_result.get("isError"), call_result)
            transport_error = call_result.get("structuredContent") or {}
            self.assertEqual(
                "unity_completed_host_delivery_unproven",
                transport_error.get("terminal_disposition"),
                transport_error,
            )
            self.assertEqual("continue_without_retry", transport_error.get("safe_next_action"))

            self.assertEqual(0, final_status.returncode, final_status.stderr)
            status = json.loads(final_status.stdout)
            self.assertEqual("completed_ok", status.get("operation_outcome"), status)
            self.assertEqual("unity_completed_confirmed", status.get("result_trust_class"), status)
            self.assertEqual(
                "unity_completed_host_delivery_unproven",
                status.get("terminal_disposition"),
                status,
            )
            self.assertEqual("unity_request_journal", status.get("completion_source"), status)
            self.assertEqual(1, status.get("submission_bridge_generation"), status)
            self.assertEqual(2, status.get("completion_bridge_generation"), status)
            self.assertEqual(1, status.get("bridge_generation_delta"), status)
            self.assertEqual("none", status.get("recommended_next_action"), status)
            self.assertEqual("continue_without_retry", status.get("safe_next_action"), status)
            self.assertFalse((status.get("operator_verdict") or {}).get("should_retry"), status)
            journal_events = [
                read_json(path)
                for path in request_journal_dir(project_root).glob("*.json")
            ]
            submitted_ids = {
                str(event.get("request_id") or "")
                for event in journal_events
                if event.get("event_type") == "request_submitted"
            }
            started_ids = {
                str(event.get("request_id") or "")
                for event in journal_events
                if event.get("event_type") == "request_started"
            }
            self.assertEqual({request_id}, submitted_ids, journal_events)
            self.assertEqual({request_id}, started_ids, journal_events)
            self.assertEqual("", sim_stdout)


class ConcurrentAtomicPublishStressTest(unittest.TestCase):
    """Two real processes hammer one JSON path; a reader must never see a torn payload."""

    STRESS_ITERATIONS = 400

    def test_reader_never_observes_torn_payload_under_concurrent_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "state" / "stress_state.json"

            writer = subprocess.Popen(
                [
                    sys.executable,
                    str(SIMULATOR_PATH),
                    "stress-write",
                    str(target),
                    str(self.STRESS_ITERATIONS),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            successful_reads = 0
            tolerated_read_errors = 0
            saw_final = False
            deadline = time.monotonic() + 120.0
            writer_done_at: float | None = None
            try:
                while time.monotonic() < deadline:
                    if writer_done_at is None and writer.poll() is not None:
                        writer_done_at = time.monotonic()
                    if writer_done_at is not None and time.monotonic() - writer_done_at > 5.0:
                        break
                    try:
                        payload = read_json(target)
                    except FileNotFoundError:
                        continue
                    except (OSError, ValueError):
                        # The retrying transport reader tolerates a briefly
                        # locked destination; what it must never get is a
                        # *successfully parsed* torn payload.
                        tolerated_read_errors += 1
                        continue

                    successful_reads += 1
                    self.assertEqual("begin", payload.get("head"), payload)
                    self.assertEqual(payload.get("seq"), payload.get("tail_seq"), payload)
                    self.assertEqual(len(STRESS_BLOB), len(payload.get("blob") or ""), "torn blob")
                    if payload.get("final"):
                        saw_final = True
                        break
            finally:
                try:
                    writer.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                writer_stdout, writer_stderr = stop_process(writer)

            self.assertEqual(0, writer.returncode, writer_stdout + writer_stderr)
            self.assertTrue(saw_final, "reader never observed the final frame")
            self.assertGreaterEqual(
                successful_reads,
                50,
                f"stress run too shallow to be meaningful: reads={successful_reads} "
                f"tolerated_errors={tolerated_read_errors}",
            )


if __name__ == "__main__":
    unittest.main()
