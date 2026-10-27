"""Operator-verdict and evidence-surface contracts from the 2026-09-28 readiness/settle retro.

Each case reproduces a false verdict or a missing surface the retro recorded: an editor that had already left
Safe Mode was reported as blocked on the dialog, compact test payloads listed three failures of nine, an anchored
grep searched the oldest 500k characters of a 2 MB scope, a stale heartbeat during a long import was reported as a
frozen editor, and the post-PlayMode domain reload read as a warning. Time, filesystem inputs and the OS process
table are controlled while owned interpretation and orchestration remain real.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
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
    def test_the_exit_line_is_observed_history_not_current_compile_truth(self) -> None:
        log = "Assets/Foo.cs(1,1): error CS1061: missing member\n" + SAFE_MODE_EXIT_LINE + "\n"

        self.assertEqual("safe_mode_exited", server_editor_host_paths.safe_mode_log_observation(log))
        code, message = server_editor_host_paths.classify_editor_log(log, "fail_fast_on_interactive_compile_block")

        self.assertEqual("compile_errors_after_safe_mode_exit", code)
        self.assertIn("observed history", message)
        self.assertNotIn("no dialog is blocking", message)

    def test_the_newest_explicit_state_or_ambiguous_mention_wins(self) -> None:
        cases = (
            ("Entered Safe Mode", "safe_mode_entered"),
            ("Entering Safe Mode", "safe_mode_entered"),
            ("Safe Mode dialog", "safe_mode_prompt"),
            ("Safe Mode prompt", "safe_mode_prompt"),
            ("Would you like to enter Safe Mode?", "safe_mode_prompt"),
            ("Opening project in Safe Mode", "safe_mode_entered"),
            ("Safe Mode", "safe_mode_marker_present"),
            (SAFE_MODE_EXIT_LINE, "safe_mode_exited"),
        )
        for line, expected in cases:
            with self.subTest(line=line):
                log = "Safe Mode prompt\nEntered Safe Mode\n" + SAFE_MODE_EXIT_LINE + "\n" + line
                self.assertEqual(expected, server_editor_host_paths.safe_mode_log_observation(log))

    def test_entered_safe_mode_does_not_recommend_entering_again(self) -> None:
        code, message = server_editor_host_paths.classify_editor_log(
            "error CS1002\nEntered Safe Mode", "auto_enter_safe_mode_preferred"
        )
        self.assertEqual("interactive_compile_block_in_safe_mode", code)
        self.assertNotIn("open Safe Mode manually", message)
        self.assertIn("Fix the compile errors", message)

    def test_only_an_explicit_prompt_gets_the_dialog_code(self) -> None:
        for line, expected in (
            ("Safe Mode dialog", "interactive_compile_block_with_safe_mode_dialog"),
            ("Safe Mode", "interactive_compile_block_with_safe_mode_marker"),
        ):
            with self.subTest(line=line):
                code, message = server_editor_host_paths.classify_editor_log(
                    "error CS1002\n" + line, "fail_fast_on_interactive_compile_block"
                )
                self.assertEqual(expected, code)
                if expected.endswith("marker"):
                    self.assertIn("ambiguous", message)
                    self.assertNotIn("open Safe Mode manually", message)

    def test_compile_errors_without_any_safe_mode_mention_keep_the_plain_block_code(self) -> None:
        self.assertEqual("none", server_editor_host_paths.safe_mode_log_observation("error CS1002\n"))
        code, _ = server_editor_host_paths.classify_editor_log("error CS1002\n", "fail_fast_on_interactive_compile_block")
        self.assertEqual("interactive_compile_block_detected", code)


class ReadinessAfterSafeModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"
        self.stderr = io.StringIO()
        self.enterContext(redirect_stderr(self.stderr))

    def _wait(self, marker: str, *, becomes_ready: bool = False, quiet: bool = False, compile_diagnostics: bool = True, during_sleep=None, progress_marker: str = "import progress", session_id: str = "a" * 32) -> tuple[dict | ToolInvocationError, mock.Mock]:
        clock = [1000.0]
        self.log.write_text(("error CS1061\n" if compile_diagnostics else "") + marker + "\n", encoding="utf-8")
        os.utime(self.log, (clock[0], clock[0]))
        ready_state = {
            "editor_pid": 222, "bridge_bootstrap_attached": True, "health_status": "healthy",
            "script_compilation_failed": compile_diagnostics, "compiler_error_count": int(compile_diagnostics),
        }
        starting_state = {"editor_pid": 111, "bridge_generation": 7, "bridge_session_id": session_id,
                          "editor_log_path": "PRIVATE_PATH_SENTINEL", "authorization": "SECRET_SENTINEL"}

        def sleep(seconds: float) -> None:
            if during_sleep is not None:
                during_sleep()
            clock[0] += seconds
            if not quiet:
                with self.log.open("a", encoding="utf-8") as handle:
                    handle.write(progress_marker + "\n")
                os.utime(self.log, (clock[0], clock[0]))

        fake_time = types.SimpleNamespace(time=lambda: clock[0], sleep=mock.Mock(side_effect=sleep))
        # Keep the parser, readiness decision, idle calculation and observation paths real.
        # Only filesystem inputs, process visibility and the clock are controlled.
        with ExitStack() as stack:
            for name, value in (
                ("time", fake_time), ("bridge_enabled", mock.Mock(return_value=True)),
                ("try_read_bridge_state", mock.Mock(side_effect=[starting_state, ready_state] if becomes_ready else lambda _: starting_state)),
                ("find_running_unity_editors_for_project", mock.Mock(return_value=[{"pid": 222}])),
                ("pid_is_alive", mock.Mock(return_value=True)),
                ("heartbeat_age_seconds", mock.Mock(return_value=1.0)),
            ):
                stack.enter_context(mock.patch.object(server_editor_host, name, value))
            server_editor_host.bridge_state_is_ready(None, 10)  # Sync the facade's closed-boundary patches.
            if quiet:
                os.utime(self.log, (clock[0], clock[0] - 100.0))
                # Read freshness is a filesystem input; the real idle calculation stays active.
                stack.enter_context(mock.patch.object(server_editor_host, "read_recent_editor_log", return_value=self.log.read_text(encoding="utf-8")))
            try:
                result = server_editor_host.wait_for_ready(
                    self.root, timeout_ms=2000, heartbeat_max_age_seconds=10,
                    startup_policy="fail_fast_on_interactive_compile_block", editor_log_path=self.log,
                )
            except ToolInvocationError as exc:
                result = exc
        # Facade calls restore its copied boundary values after each scoped patch.
        server_editor_host.bridge_state_is_ready(None, 10)
        server_editor_host._sync_owner(server_editor_host_lifecycle)
        return result, fake_time.sleep

    def test_moving_logs_keep_polling_to_the_deadline_with_a_typed_condition(self) -> None:
        for marker, expected, action in (
            ("Safe Mode dialog", "startup_safe_mode_dialog_observed", "open_safe_mode_manually"),
            ("Entered Safe Mode", "startup_safe_mode_entered_observed", "fix_compile_errors"),
            ("Safe Mode", "startup_safe_mode_marker_observed", "inspect_editor_state_and_compile_evidence"),
            ("Opening project in Safe Mode", "startup_safe_mode_entered_observed", "fix_compile_errors"),
        ):
            with self.subTest(marker=marker):
                result, sleep = self._wait(marker)
                self.assertIsInstance(result, ToolInvocationError)
                self.assertEqual(expected, result.code)
                self.assertEqual("unmeasured", result.details["compile_state"])
                self.assertEqual("none", result.details["compile_measurement_source"])
                self.assertEqual(action, result.details["recommended_next_action"])
                self.assertEqual("readiness_deadline_reached", result.details["startup_stage"])
                self.assertEqual("observed_history", result.details["editor_log_evidence_kind"])
                self.assertEqual([222], result.details["observed_live_editor_pids"])
                self.assertEqual(111, result.details["observed_bridge_pid"])
                self.assertTrue(result.details["observed_bridge_pid_alive"])
                self.assertEqual(2, sleep.call_count)

    def test_provisional_stderr_event_precedes_ready_and_keeps_stdout_clean(self) -> None:
        seen_before_ready = []
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            state, sleep = self._wait(
                "Opening project in Safe Mode\nPRIVATE_LOG_SENTINEL", becomes_ready=True,
                during_sleep=lambda: seen_before_ready.extend(json.loads(line) for line in self.stderr.getvalue().splitlines()),
            )
        self.assertIsInstance(state, dict)
        self.assertEqual("bridge_ready", state["startup_log_observation"]["startup_stage"])
        self.assertEqual(1, len(seen_before_ready))
        event = seen_before_ready[0]
        self.assertEqual("startup_safe_mode_entered_observed", event["code"])
        self.assertTrue(event["provisional"])
        self.assertEqual("waiting_for_bridge_readiness", event["startup_stage"])
        self.assertEqual("unmeasured", event["compile_state"])
        self.assertEqual((111, [222], 7, "a" * 32), (event["observed_bridge_pid"], event["observed_live_editor_pids"], event["bridge_generation"], event["bridge_session_id"]))
        self.assertTrue(event["editor_log_observation_during_wait"])
        self.assertEqual("", stdout.getvalue())
        self.assertNotIn("PRIVATE", self.stderr.getvalue())
        self.assertNotIn("SECRET", self.stderr.getvalue())
        self.assertLess(len(self.stderr.getvalue().encode("utf-8")), 2048)
        self.assertEqual({"code", "startup_stage", "provisional", "compile_state", "observed_bridge_pid", "observed_bridge_pid_alive", "observed_live_editor_pids", "observed_live_editor_pid_count", "observed_live_editor_pids_truncated", "bridge_generation", "bridge_session_id", "bridge_bootstrap_attached", "is_compiling", "editor_log_observation_during_wait", "recommended_next_action"}, set(event))
        sleep.assert_called_once_with(1.0)

    def test_unchanged_conditions_emit_once_and_changed_conditions_emit_again(self) -> None:
        result, sleep = self._wait("Entered Safe Mode")
        self.assertEqual("startup_safe_mode_entered_observed", result.code)
        self.assertEqual(2, sleep.call_count)
        self.assertEqual(1, len(self.stderr.getvalue().splitlines()))
        self.stderr.seek(0)
        self.stderr.truncate(0)
        result, _ = self._wait("Safe Mode", progress_marker="Entered Safe Mode")
        self.assertEqual("startup_safe_mode_entered_observed", result.code)
        self.assertEqual(["startup_safe_mode_marker_observed", "startup_safe_mode_entered_observed"], [json.loads(line)["code"] for line in self.stderr.getvalue().splitlines()])

    def test_unrecognized_session_identity_is_not_emitted(self) -> None:
        self._wait("Entered Safe Mode", session_id="/PRIVATE/SECRET_TOKEN")
        event = json.loads(self.stderr.getvalue())
        self.assertEqual("", event["bridge_session_id"])
        self.assertNotIn("PRIVATE", self.stderr.getvalue())
        self.assertNotIn("SECRET", self.stderr.getvalue())

    def test_unavailable_stderr_does_not_turn_polling_into_a_failure(self) -> None:
        unavailable = io.StringIO()
        unavailable.close()
        with redirect_stderr(unavailable):
            state, sleep = self._wait("Entered Safe Mode", becomes_ready=True)
        self.assertIsInstance(state, dict)
        self.assertEqual("bridge_ready", state["startup_log_observation"]["startup_stage"])
        sleep.assert_called_once_with(1.0)

    def test_only_a_quiet_explicit_prompt_uses_the_early_block(self) -> None:
        for marker, count in (("Safe Mode prompt", 0), ("Entered Safe Mode", 2), ("Safe Mode", 2)):
            with self.subTest(marker=marker):
                result, sleep = self._wait(marker, quiet=True)
                self.assertIsInstance(result, ToolInvocationError)
                self.assertEqual(count, sleep.call_count)
                if count == 0:
                    self.assertEqual("startup_safe_mode_dialog_observed", result.code)
                    self.assertEqual("editor_log_quiescent_with_safe_mode_markers", result.details["dialog_block_basis"])

    def test_moving_logs_yield_to_authoritative_bridge_readiness(self) -> None:
        for marker, expected in (
            ("Entered Safe Mode", "startup_safe_mode_entered_observed"),
            ("Opening project in Safe Mode", "startup_safe_mode_entered_observed"),
            ("Safe Mode", "startup_safe_mode_marker_observed"),
            ("Safe Mode prompt", "startup_safe_mode_dialog_observed"),
            (SAFE_MODE_EXIT_LINE, "startup_compile_errors_after_safe_mode_exit"),
        ):
            with self.subTest(marker=marker):
                state, sleep = self._wait(marker, becomes_ready=True)
                self.assertIsInstance(state, dict)
                observation = state["startup_log_observation"]
                self.assertEqual(expected, observation["readiness_condition"])
                self.assertEqual(marker == SAFE_MODE_EXIT_LINE, observation["safe_mode_exit_observed"])
                self.assertEqual("bridge_attached", observation["resolved_by"])
                self.assertEqual("bridge_ready", observation["startup_stage"])
                self.assertEqual("fix_compile_errors", observation["recommended_next_action"])
                self.assertEqual([222], observation["observed_live_editor_pids"])
                self.assertEqual(111, observation["observed_bridge_pid"])
                self.assertEqual(222, state["editor_pid"])
                sleep.assert_called_once_with(1.0)
                summary = build_ensure_ready_summary(self.root, {"bridge_state": state, "discovery": {}})
                self.assertEqual("ready_with_compile_errors", summary["verdict"])
                self.assertTrue(summary["succeeded"])
                self.assertEqual("fix_compile_errors", summary["recommended_next_action"])
                self.assertEqual(observation, summary["startup_log_observation"])

    def test_opening_without_compile_diagnostics_keeps_polling_to_typed_deadline(self) -> None:
        result, sleep = self._wait("Opening project in Safe Mode", compile_diagnostics=False)
        self.assertIsInstance(result, ToolInvocationError)
        self.assertEqual("startup_safe_mode_entered_observed", result.code)
        self.assertEqual("unmeasured", result.details["compile_state"])
        self.assertEqual("poll_bridge_bootstrap_attached_then_retry", result.details["recommended_next_action"])
        self.assertNotIn("startup_blocker_kind", result.details)
        self.assertEqual(2, sleep.call_count)

    def test_opening_without_compile_diagnostics_can_become_ready_after_an_earlier_prompt(self) -> None:
        state, sleep = self._wait("Would you like to enter Safe Mode?\nOpening project in Safe Mode", becomes_ready=True, compile_diagnostics=False)
        self.assertIsInstance(state, dict)
        observation = state["startup_log_observation"]
        self.assertEqual("startup_safe_mode_entered_observed", observation["readiness_condition"])
        self.assertEqual("none", observation["recommended_next_action"])
        self.assertFalse(observation["compile_errors_reported_by_bridge"])
        sleep.assert_called_once_with(1.0)

    def test_explicit_prompt_without_compile_diagnostics_remains_a_modal_positive_control(self) -> None:
        result, sleep = self._wait("Safe Mode prompt is waiting for user input", compile_diagnostics=False)
        self.assertIsInstance(result, ToolInvocationError)
        self.assertEqual("launch_blocked_probable_modal", result.code)
        self.assertEqual("safe_mode_dialog", result.details["startup_blocker_kind"])
        self.assertEqual("dismiss_startup_dialog_or_relaunch_with_noninteractive_arguments", result.details["recommended_next_action"])
        sleep.assert_not_called()

    def test_stale_tail_does_not_resurrect_a_prompt_superseded_by_opening_or_exit(self) -> None:
        for latest, expected in (("Opening project in Safe Mode", "safe_mode_entered"), (SAFE_MODE_EXIT_LINE, "safe_mode_exited")):
            with self.subTest(latest=latest):
                self.log.write_text("Would you like to enter Safe Mode?\n" + latest, encoding="utf-8")
                os.utime(self.log, (0.0, 0.0))
                with mock.patch.object(server_editor_host, "find_running_unity_editors_for_project", return_value=[{"pid": 222}]):
                    server_editor_host._sync_owner(server_editor_host_lifecycle)
                    observation = server_editor_host_lifecycle._startup_blocker_observation(self.root, self.log, time.time())
                server_editor_host._sync_owner(server_editor_host_lifecycle)
                self.assertEqual(expected, observation["safe_mode_log_observation"])
                self.assertEqual("stale_tail_for_live_project_editor", observation["editor_log_observation_scope"])
                self.assertNotIn("startup_blocker_kind", observation)

    def test_log_freshness_still_requires_a_write_during_the_wait(self) -> None:
        text = "error CS1061\nEntered Safe Mode\n"
        self.log.write_text(text, encoding="utf-8")
        os.utime(self.log, (900.0, 900.0))
        self.assertEqual("", server_editor_host.read_recent_editor_log(self.log, 1000.0))
        os.utime(self.log, (1000.0, 1000.0))
        self.assertEqual(text, server_editor_host.read_recent_editor_log(self.log, 1000.0))

    def test_a_healthy_bridge_without_compile_errors_stays_plain_ready(self) -> None:
        summary = build_ensure_ready_summary(
            self.root, {"bridge_state": {"health_status": "healthy", "compiler_error_count": 0}, "discovery": {}},
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
                "retry_recommended": True,
            },
            exit_code=1,
        )

        self.assertEqual(failures(3)[0], envelope["first_failure"])
        self.assertEqual(9, envelope["failure_count"])
        self.assertTrue(envelope["test_result_path"].endswith("req.json"))
        self.assertTrue(envelope["retry_recommended"])


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


class StaleHeartbeatRetryHintTests(unittest.TestCase):
    def _details(self, *, age: float, busy_reason: str, alive: bool = True) -> dict:
        state = {"editor_pid": 123, "heartbeat_utc": "2026-09-28T14:32:00Z", "busy_reason": busy_reason}
        with (
            mock.patch.object(server_bridge_state, "pid_is_alive", return_value=alive),
            mock.patch.object(server_bridge_state, "heartbeat_age_seconds", return_value=age),
        ):
            return server_bridge_state.build_editor_idle_timeout_details(
                Path("/project"), last_state=state, reason="before unity.compile.player_scripts",
                timeout_ms=180000, heartbeat_max_age_seconds=10, require_healthy_bridge=False,
            )

    def test_a_stale_heartbeat_during_a_bounded_import_stall_recommends_a_retry(self) -> None:
        for busy_reason in ("asset_import", "updating"):
            with self.subTest(busy_reason=busy_reason):
                details = self._details(age=183.4, busy_reason=busy_reason)

                self.assertEqual("editor_busy_heartbeat_stale", details["classification"])
                self.assertFalse(details["state_frozen"])
                self.assertTrue(details["heartbeat_stale"])
                self.assertTrue(details["retry_recommended"])
                self.assertTrue(details["safe_to_retry"])
                self.assertEqual(f"heartbeat_stale_while_editor_busy_with_{busy_reason}", details["retry_reason"])
                self.assertEqual("wait_for_editor_idle_then_retry", details["recommended_next_action"])
                self.assertIn("request-status-summary", details["recommended_recovery_command"])

    def test_a_non_transient_reason_or_a_long_stale_heartbeat_stays_frozen(self) -> None:
        for age, busy_reason in ((183.4, "idle"), (1522.871, "asset_import")):
            with self.subTest(age=age, busy_reason=busy_reason):
                details = self._details(age=age, busy_reason=busy_reason)

                self.assertEqual("editor_state_frozen", details["classification"])
                self.assertFalse(details["retry_recommended"])
                self.assertEqual("recover_editor_session", details["recommended_next_action"])

    def test_a_dead_pid_is_never_retryable(self) -> None:
        details = self._details(age=183.4, busy_reason="asset_import", alive=False)

        self.assertEqual("editor_state_frozen", details["classification"])
        self.assertFalse(details["retry_recommended"])


class GuiFallbackQuitAnnotationTests(unittest.TestCase):
    def test_recovery_aimed_at_the_editor_the_wrapper_quit_becomes_a_rerun(self) -> None:
        exc = ToolInvocationError(
            "editor_idle_timeout",
            "Timed out waiting for Unity editor idle. recommended_next_action=recover_editor_session",
            {"recommended_next_action": "recover_editor_session", "recommended_recovery_command": "x recover-editor-session"},
        )

        server_batch_lanes.annotate_gui_fallback_error_after_wrapper_quit(exc)

        self.assertTrue(exc.details["editor_quit_by_wrapper"])
        self.assertEqual("retry_same_command", exc.details["recommended_next_action"])
        self.assertEqual("", exc.details["recommended_recovery_command"])
        self.assertTrue(exc.details["retry_recommended"])
        self.assertIn("recommended_next_action=retry_same_command", exc.message)
        self.assertEqual(exc.message, str(exc))

    def test_product_level_next_actions_are_left_alone(self) -> None:
        exc = ToolInvocationError("compile_failed", "compile failed", {"recommended_next_action": "inspect_compile_errors"})

        server_batch_lanes.annotate_gui_fallback_error_after_wrapper_quit(exc)

        self.assertTrue(exc.details["editor_quit_by_wrapper"])
        self.assertEqual("inspect_compile_errors", exc.details["recommended_next_action"])
        self.assertNotIn("retry_recommended", exc.details)


class BatchTerminalRecordTests(unittest.TestCase):
    def test_gui_and_batch_shaped_summaries_produce_the_same_record_shape(self) -> None:
        gui_summary = {
            "action": "batch_compile", "succeeded": True, "unity_outcome": "passed",
            "transport_outcome": "gui_operation_completed", "effective_execution_lane": "gui",
            "lane_fallback_reason": "licensing_client_ipc_failure", "result_file": "/r/gui.json",
            "compile": {"status": "passed", "error_count": 0, "rebuilt_assembly_count": 16, "cached_assembly_count": 140,
                        "rebuild_evidence_status": "measured"},
        }
        batch_summary = {
            "action": "batch_build_config_compile_matrix", "succeeded": False, "unity_outcome": "failed",
            "transport_outcome": "batch_process_exited_cleanly", "effective_execution_lane": "batch",
            "result_file": "/r/batch.json", "total_errors": 2,
            "matrix": {"status": "failed", "failed": 1, "warning_count": 4, "rebuilt_assembly_count": 3,
                       "cached_assembly_count": 9, "rebuild_evidence_status": "measured"},
            "top_actionable_error": "CS1061",
        }

        gui = server_batch_reporting.build_batch_terminal_record(gui_summary, summary_path=Path("/r/gui_summary.json"))
        batch = server_batch_reporting.build_batch_terminal_record(batch_summary, summary_path=Path("/r/batch_summary.json"))

        self.assertEqual(set(gui), set(batch))
        self.assertEqual(("gui", "passed", 0, 16), (gui["lane"], gui["compile_status"], gui["error_count"], gui["rebuilt_assembly_count"]))
        self.assertEqual(("batch", "failed", 2, 3), (batch["lane"], batch["compile_status"], batch["error_count"], batch["rebuilt_assembly_count"]))
        self.assertEqual("licensing_client_ipc_failure", gui["lane_fallback_reason"])
        self.assertEqual("CS1061", batch["top_actionable_error"])
        self.assertEqual("/r/batch_summary.json", batch["summary_file"].replace("\\", "/"))

    def test_the_record_reaches_the_compact_cli_output_and_the_last_ndjson_line(self) -> None:
        summary = {"action": "batch_compile", "succeeded": True, "unity_outcome": "passed", "effective_execution_lane": "batch",
                   "compile": {"status": "passed", "error_count": 0}}
        record = server_batch_reporting.attach_batch_terminal_record(summary)
        compact = server_batch_reporting.build_compact_batch_cli_output({"action": "batch_compile", "succeeded": True, "result_summary": summary})

        self.assertEqual("passed", compact["terminal_record"]["compile_status"])
        self.assertEqual("batch", compact["terminal_record"]["lane"])

        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "progress.jsonl"
            reporter = server_batch_reporting.BatchProgressReporter(
                run_id="run-1", operation="batch_compile", log_path=Path(tmp) / "unity.log", progress_path=progress_path
            )
            captured = io.StringIO()
            with redirect_stdout(captured):
                reporter.emit("summary_written")
                reporter.emit_terminal_record(record)
            lines = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual("batch_terminal_record", lines[-1]["event"])
        self.assertEqual("passed", lines[-1]["compile_status"])
        self.assertEqual("batch_terminal_record", json.loads(captured.getvalue().splitlines()[-1])["event"])

    def test_the_sweep_runner_reads_the_record_and_the_retry_hint(self) -> None:
        payload = {
            "error": {"code": "editor_idle_timeout", "details": {"retry_recommended": True, "retry_reason": "heartbeat_stale_while_editor_busy_with_asset_import"}},
            "editor_quit_by_wrapper": True,
            "result_summary": {"terminal_record": {"lane": "gui", "compile_status": ""}},
        }

        details = run_multi_project.batch_error_details(payload)
        record = run_multi_project.terminal_record_from_run(payload["result_summary"], {})

        self.assertTrue(details["retry_recommended"])
        self.assertTrue(details["editor_quit_by_wrapper"])
        self.assertEqual("gui", record["lane"])
        self.assertEqual({}, run_multi_project.terminal_record_from_run({}, {"summary": 1}))


if __name__ == "__main__":
    unittest.main()
