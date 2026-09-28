"""Operator-verdict and evidence-surface contracts from the 2026-09-28 readiness/settle retro.

Each case reproduces a false verdict or a missing surface the retro recorded: an editor that had already left
Safe Mode was reported as blocked on the dialog, compact test payloads listed three failures of nine, an anchored
grep searched the oldest 500k characters of a 2 MB scope, a stale heartbeat during a long import was reported as a
frozen editor, and the post-PlayMode domain reload read as a warning. Unity and the OS process table are the only
mocked boundaries.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
RUNNER_DIR = REPO_ROOT / "scripts" / "testing"
for candidate in (TEMPLATES_DIR, RUNNER_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_multi_project
import server_batch_lanes
import server_batch_orchestrator
import server_batch_reporting
import server_bridge_payloads
import server_bridge_state
import server_editor_host
import server_editor_host_lifecycle
import server_editor_host_paths
import server_health
import server_launcher
import server_operation_evidence
from server_bridge_paths import test_result_path
from server_core import ToolInvocationError, read_json, write_json
from server_readiness_summary import build_ensure_ready_summary

SAFE_MODE_EXIT_LINE = "[ScriptCompilation] Requested script compilation because: Exiting safe mode"


class SafeModeClassifierTests(unittest.TestCase):
    def test_the_exit_line_is_not_a_dialog_marker(self) -> None:
        log = "Assets/Foo.cs(1,1): error CS1061: missing member\n" + SAFE_MODE_EXIT_LINE + "\n"

        self.assertEqual("safe_mode_exited", server_editor_host_paths.safe_mode_log_observation(log))
        code, message = server_editor_host_paths.classify_editor_log(log, "fail_fast_on_interactive_compile_block")

        self.assertEqual("compile_errors_after_safe_mode_exit", code)
        self.assertIn("no dialog is blocking", message)

    def test_a_dialog_marker_after_the_exit_line_still_reports_the_dialog(self) -> None:
        log = "error CS1002\n" + SAFE_MODE_EXIT_LINE + "\nOpening project in Safe Mode\n"

        self.assertEqual("safe_mode_marker_present", server_editor_host_paths.safe_mode_log_observation(log))
        code, _ = server_editor_host_paths.classify_editor_log(log, "fail_fast_on_interactive_compile_block")

        self.assertEqual("interactive_compile_block_with_safe_mode_dialog", code)

    def test_compile_errors_without_any_safe_mode_mention_keep_the_plain_block_code(self) -> None:
        self.assertEqual("none", server_editor_host_paths.safe_mode_log_observation("error CS1002\n"))
        code, _ = server_editor_host_paths.classify_editor_log("error CS1002\n", "fail_fast_on_interactive_compile_block")

        self.assertEqual("interactive_compile_block_detected", code)


class ReadinessAfterSafeModeTests(unittest.TestCase):
    def _patches(self, *, classification: tuple[str, str], idle_seconds: float, states: list[dict], ready: list[bool], times: list[float]):
        fake_time = types.SimpleNamespace(time=mock.Mock(side_effect=times), sleep=mock.Mock())
        return fake_time, (
            mock.patch.object(server_editor_host, "time", fake_time),
            mock.patch.object(server_editor_host, "bridge_enabled", return_value=True),
            mock.patch.object(server_editor_host, "try_read_bridge_state", side_effect=states),
            mock.patch.object(server_editor_host, "bridge_state_is_ready", side_effect=ready),
            mock.patch.object(server_editor_host, "read_recent_editor_log", return_value="error CS1061\n" + SAFE_MODE_EXIT_LINE),
            mock.patch.object(server_editor_host, "classify_editor_log", return_value=classification),
            mock.patch.object(server_editor_host, "find_running_unity_editors_for_project", return_value=[{"pid": 222}]),
            mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            mock.patch.object(server_editor_host_lifecycle, "_editor_log_idle_seconds", return_value=idle_seconds),
            mock.patch.object(server_editor_host, "heartbeat_age_seconds", return_value=1.0),
        )

    def test_a_moving_log_with_dialog_markers_keeps_polling_until_the_deadline(self) -> None:
        fake_time, patches = self._patches(
            classification=("interactive_compile_block_with_safe_mode_dialog", "Safe Mode dialog observed."),
            idle_seconds=2.0,
            states=[{}, {}],
            ready=[False, False],
            times=[0.0, 0.0, 2.0],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
            with self.assertRaises(ToolInvocationError) as ctx:
                server_editor_host.wait_for_ready(
                    Path("/tmp/FakeProject"),
                    timeout_ms=1000,
                    heartbeat_max_age_seconds=10,
                    startup_policy="fail_fast_on_interactive_compile_block",
                    editor_log_path=Path("/tmp/editor.log"),
                )

        self.assertEqual("startup_safe_mode_dialog_observed", ctx.exception.code)
        self.assertEqual("readiness_deadline_reached_with_safe_mode_markers", ctx.exception.details["dialog_block_basis"])
        self.assertEqual(2.0, ctx.exception.details["editor_log_idle_seconds"])
        fake_time.sleep.assert_called_once_with(1.0)

    def test_an_editor_that_left_safe_mode_becomes_ready_with_compile_errors(self) -> None:
        ready_state = {
            "editor_pid": 222,
            "bridge_bootstrap_attached": True,
            "health_status": "healthy",
            "script_compilation_failed": True,
            "compiler_error_count": 1,
        }
        fake_time, patches = self._patches(
            classification=("compile_errors_after_safe_mode_exit", "Editor left Safe Mode with compile errors."),
            idle_seconds=0.5,
            states=[{}, ready_state],
            ready=[False, True],
            times=[0.0, 0.0, 0.5],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
            state = server_editor_host.wait_for_ready(
                Path("/tmp/FakeProject"),
                timeout_ms=1000,
                heartbeat_max_age_seconds=10,
                startup_policy="fail_fast_on_interactive_compile_block",
                editor_log_path=Path("/tmp/editor.log"),
            )

        observation = state["startup_log_observation"]
        self.assertEqual("startup_compile_errors_after_safe_mode_exit", observation["readiness_condition"])
        self.assertTrue(observation["safe_mode_exit_observed"])
        self.assertEqual("bridge_attached", observation["resolved_by"])
        self.assertEqual("fix_compile_errors", observation["recommended_next_action"])
        fake_time.sleep.assert_called_once_with(1.0)

        summary = build_ensure_ready_summary(Path("/tmp/FakeProject"), {"bridge_state": state, "discovery": {}})
        self.assertEqual("ready_with_compile_errors", summary["verdict"])
        self.assertTrue(summary["succeeded"])
        self.assertEqual("fix_compile_errors", summary["recommended_next_action"])
        self.assertIn("request-project-refresh", summary["recovery_command"])
        self.assertEqual(observation, summary["startup_log_observation"])
        self.assertNotIn("Safe Mode manually", summary["verdict_note"])

    def test_a_healthy_bridge_without_compile_errors_stays_plain_ready(self) -> None:
        summary = build_ensure_ready_summary(
            Path("/tmp/FakeProject"),
            {"bridge_state": {"health_status": "healthy", "compiler_error_count": 0}, "discovery": {}},
        )

        self.assertEqual("ready", summary["verdict"])
        self.assertNotIn("verdict_note", summary)


def failures(count: int) -> list[dict[str, str]]:
    return [{"name": f"Suite.Test{index}", "message": f"Expected {index}"} for index in range(count)]


class CompleteFailureListTests(unittest.TestCase):
    def test_the_compact_test_payload_lists_every_failure_up_to_the_bound(self) -> None:
        payload = {
            "status": "failed",
            "total": 12,
            "failed": 9,
            "failures": failures(9),
            "test_result_path": "/project/Library/XUUnityLightMcp/state/test_results/req.json",
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.tests.run_editmode")

        self.assertEqual(3, len(compact["first_failures"]))
        self.assertEqual(9, len(compact["failures"]))
        self.assertEqual(9, compact["failure_count"])
        self.assertFalse(compact["failures_truncated"])
        self.assertEqual(payload["test_result_path"], compact["test_result_path"])
        self.assertEqual({"name", "message"}, set(compact["failures"][8]))

    def test_more_failures_than_the_bound_are_counted_and_flagged(self) -> None:
        compact = server_bridge_payloads.compact_operation_payload(
            {"status": "failed", "failures": failures(30)}, "unity.tests.run_playmode"
        )

        self.assertEqual(25, server_operation_evidence.COMPACT_TEST_FAILURE_LIMIT)
        self.assertEqual(25, len(compact["failures"]))
        self.assertEqual(30, compact["failure_count"])
        self.assertTrue(compact["failures_truncated"])

    def test_direct_test_evidence_names_the_persisted_result_file(self) -> None:
        enriched = {"status": "failed", "total": 9, "failed": 9, "failures": failures(9)}
        project_root = Path("/tmp/FakeProject")

        server_operation_evidence._attach_direct_test_verdict(
            enriched, operation="unity.tests.run_editmode", project_root=project_root, request_id="req-9"
        )

        self.assertEqual(9, enriched["failure_count"])
        self.assertFalse(enriched["failures_truncated"])
        self.assertEqual(str(test_result_path(project_root, "req-9")), enriched["test_result_path"])
        self.assertEqual(9, len(enriched["failures"]), "the full payload keeps the raw failure list")

    def test_the_terminal_envelope_carries_the_count_and_the_result_path(self) -> None:
        envelope = server_launcher.build_compact_terminal_envelope(
            {
                "outcome": "completed",
                "first_failures": failures(3),
                "failure_count": 9,
                "test_result_path": "/project/Library/XUUnityLightMcp/state/test_results/req.json",
            },
            exit_code=1,
        )

        self.assertEqual(failures(3)[0], envelope["first_failure"])
        self.assertEqual(9, envelope["failure_count"])
        self.assertTrue(envelope["test_result_path"].endswith("req.json"))


class ExpectedDomainReloadTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "status": "passed",
            "playmode_state_after_settle": "edit",
            "playmode_state_after_settle_trust_class": "stale_risk",
            "playmode_state_after_settle_note": "bridge identity changed during post-test settle",
            "playmode_state_after_settle_recommended_next_action": "confirm_via_unity_playmode_state",
            "lifecycle_churn_observed": True,
        }

    def test_reconciled_playmode_results_relabel_the_exit_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            request_id = "req-playmode"
            write_json(test_result_path(project_root, request_id), {"request_id": request_id, "response_handoff_state": "written"})
            payload = self._payload()

            outcome = server_batch_orchestrator.reconcile_persisted_test_result_after_lifecycle(
                project_root, request_id, "unity.tests.run_playmode", payload
            )
            persisted = read_json(test_result_path(project_root, request_id))

        self.assertEqual("reconciled", outcome)
        self.assertEqual("expected_domain_reload", payload["playmode_state_after_settle_trust_class"])
        self.assertEqual("none", payload["playmode_state_after_settle_recommended_next_action"])
        self.assertEqual("expected_playmode_exit_domain_reload", payload["lifecycle_churn_classification"])
        self.assertTrue(payload["lifecycle_churn_observed"])
        self.assertEqual("expected_domain_reload", persisted["playmode_state_after_settle_trust_class"])

    def test_editmode_churn_and_unreconciled_results_keep_stale_risk(self) -> None:
        editmode = self._payload()
        self.assertFalse(server_bridge_payloads.relabel_reconciled_playmode_reload(editmode, "unity.tests.run_editmode"))
        self.assertEqual("stale_risk", editmode["playmode_state_after_settle_trust_class"])

        with tempfile.TemporaryDirectory() as tmp:
            payload = self._payload()
            outcome = server_batch_orchestrator.reconcile_persisted_test_result_after_lifecycle(
                Path(tmp), "req-missing", "unity.tests.run_playmode", payload, wait_timeout_seconds=0.0
            )

        self.assertEqual("pending_or_unavailable", outcome)
        self.assertEqual("stale_risk", payload["playmode_state_after_settle_trust_class"])


class AnchoredGrepAutoExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"
        prefix = "previous session\n"
        filler = "noise line that is long enough to matter\n" * 15000
        self.log.write_bytes((prefix + filler + "LATE MARKER\n").encode("utf-8"))
        self.bridge_state = {"editor_log_offset_at_playmode_start": len(prefix), "editor_log_path": str(self.log)}
        self.assertGreater(self.log.stat().st_size, server_health.EDITOR_LOG_GREP_MAX_CHARS)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_an_anchored_scope_beyond_the_default_window_is_searched_completely(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root, self.log, pattern="LATE MARKER", since="playmode_start", bridge_state=self.bridge_state
        )

        self.assertTrue(payload["search_window_auto_extended"])
        self.assertEqual(server_health.EDITOR_LOG_GREP_MAX_CHARS, payload["requested_search_chars"])
        self.assertFalse(payload["scope_truncated"])
        self.assertEqual("matched", payload["search_verdict"])
        self.assertEqual("editor_log_absolute", payload["line_numbering_basis"])

        absent = server_health.grep_editor_log_payload(
            self.root, self.log, pattern="NEVER LOGGED", since="playmode_start", bridge_state=self.bridge_state
        )

        self.assertEqual("not_matched", absent["search_verdict"])
        self.assertEqual("complete_anchored_scope_searched", absent["search_verdict_reason"])

    def test_an_explicit_budget_still_bounds_the_search(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="LATE MARKER",
            since="playmode_start",
            max_chars=4096,
            bridge_state=self.bridge_state,
        )

        self.assertFalse(payload["search_window_auto_extended"])
        self.assertTrue(payload["scope_truncated"])
        self.assertEqual("inconclusive", payload["search_verdict"])
        self.assertEqual(4096, payload["searched_tail_chars"])


if __name__ == "__main__":
    unittest.main()
