"""Console errors a passing test consumed with LogAssert.Expect must not read as console pressure.

A green PlayMode suite whose only exception was asserted by the test's own `LogAssert.Expect` reported
`console_error_pressure_detected: true` with no sample, so the operator had to grep the console and the
source to classify it. These pins hold the host half of the per-test classification: pressure follows the
not-expected count, expected errors are subtracted only within their own counter session, recorded
not-expected errors stay a floor across later domains, and samples stay bounded on every surface.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_bridge_final_status
import server_bridge_payloads
import server_launcher
import server_operation_evidence
from server_bridge_paths import test_result_path
from server_core import read_json, write_json

PLAYMODE = "unity.tests.run_playmode"
EDITMODE = "unity.tests.run_editmode"


def sample(classification: str, message: str = "InvalidOperationException: init failed", **overrides) -> dict:
    item = {
        "type": "exception",
        "message": message,
        "active_test": "Suite.Fixture.Case",
        "classification": classification,
        "logged_at_utc": "2026-11-03T16:00:30Z",
    }
    item.update(overrides)
    return item


def expected_only_response() -> dict:
    return {
        "status": "passed",
        "run_phase": "completed",
        "completed_at_utc": "2026-11-03T16:01:01Z",
        "total": 39,
        "passed": 39,
        "console_error_count_since_request_start": 1,
        "console_error_count_trust_class": "lower_bound_after_domain_reload",
        "console_error_pressure_detected": False,
        "console_error_expected_by_test_count": 1,
        "console_error_not_expected_count": 0,
        "console_error_classification_basis": "utf_log_scope",
        "console_error_samples": [sample("expected_by_test")],
    }


def verdict_summary(
    *,
    response_payload: dict | None = None,
    persisted_test_result: dict | None = None,
    active_state: dict | None = None,
    request_completed: bool = True,
    operation: str = PLAYMODE,
) -> dict:
    return server_bridge_final_status.build_test_verdict_summary(
        project_root=Path("/tmp/FakeProject"),
        request_id="req-console-classification",
        operation=operation,
        response_payload=response_payload,
        persisted_test_result=persisted_test_result,
        request_submitted=True,
        request_started=True,
        request_completed=request_completed,
        completion_status="ok" if request_completed else "",
        operation_outcome="completed_ok" if request_completed else "started_in_progress",
        active_state=active_state if active_state is not None else {"playmode_state": "edit"},
        bridge_changed_since_submission=False,
    )


def compact_projection(summary: dict, operation: str = PLAYMODE) -> dict:
    return server_bridge_final_status.build_compact_final_status_projection({"operation": operation, **summary})


class ConsoleErrorClassificationVerdictTests(unittest.TestCase):
    def test_passing_run_whose_only_error_was_expected_reports_no_pressure(self) -> None:
        summary = verdict_summary(response_payload=expected_only_response())

        self.assertEqual("passed", summary["test_verdict"])
        self.assertEqual(1, summary["console_error_count_since_request_start"])
        self.assertFalse(summary["console_error_pressure_detected"])
        self.assertEqual("", summary["console_error_pressure_warning"])
        self.assertEqual(1, summary["console_error_expected_by_test_count"])
        self.assertEqual(0, summary["console_error_not_expected_count"])
        self.assertEqual("utf_log_scope", summary["console_error_classification_basis"])
        self.assertEqual(["expected_by_test"], [item["classification"] for item in summary["console_error_samples"]])

        compact = compact_projection(summary)
        self.assertFalse(compact["console_error_pressure_detected"])
        self.assertEqual(1, compact["console_error_expected_by_test_count"])
        self.assertEqual(0, compact["console_error_not_expected_count"])
        self.assertEqual("utf_log_scope", compact["console_error_classification_basis"])
        self.assertEqual("Suite.Fixture.Case", compact["console_error_samples"][0]["active_test"])

    def test_old_editor_payload_without_classification_keeps_raw_pressure(self) -> None:
        summary = verdict_summary(
            response_payload={
                "status": "passed",
                "completed_at_utc": "2026-11-03T16:01:01Z",
                "total": 2,
                "passed": 2,
                "console_error_count_since_request_start": 2,
                "console_error_count_trust_class": "complete_since_request_start",
                "console_error_pressure_detected": True,
            }
        )

        self.assertTrue(summary["console_error_pressure_detected"])
        self.assertEqual(2, summary["console_error_not_expected_count"])
        self.assertEqual(0, summary["console_error_expected_by_test_count"])
        self.assertEqual([], summary["console_error_samples"])
        self.assertEqual("", summary["console_error_classification_basis"])
        self.assertNotIn("console_error_samples", compact_projection(summary))

    def test_persisted_fallback_subtracts_expected_only_in_the_same_counter_session(self) -> None:
        persisted = {
            "run_phase": "running",
            "total": 1,
            "passed": 1,
            "console_error_count_at_request_start": 0,
            "console_error_counter_session_id_at_request_start": "session-a",
            "console_error_expected_by_test_count": 1,
            "console_error_expected_by_test_count_in_session": 1,
            "console_error_expected_by_test_counter_session_id": "session-b",
            "console_error_not_expected_recorded_count": 0,
            "console_error_classification_basis": "utf_log_scope",
            "console_error_samples": [sample("expected_by_test")],
        }

        same = verdict_summary(
            persisted_test_result=persisted,
            active_state={"console_error_counter_session_id": "session-b", "console_error_count_total": 1},
            request_completed=False,
        )
        self.assertEqual("lower_bound_after_domain_reload", same["console_error_count_trust_class"])
        self.assertFalse(same["console_error_pressure_detected"])
        self.assertEqual(0, same["console_error_not_expected_count"])

        other = verdict_summary(
            persisted_test_result=persisted,
            active_state={"console_error_counter_session_id": "session-c", "console_error_count_total": 1},
            request_completed=False,
        )
        self.assertTrue(other["console_error_pressure_detected"])
        self.assertEqual(1, other["console_error_not_expected_count"])

    def test_not_expected_recorded_count_is_a_floor_after_a_later_domain(self) -> None:
        persisted = {
            "run_phase": "running",
            "total": 1,
            "passed": 1,
            "console_error_count_at_request_start": 4,
            "console_error_counter_session_id_at_request_start": "edit-domain",
            "console_error_expected_by_test_count": 0,
            "console_error_not_expected_recorded_count": 1,
            "console_error_classification_basis": "utf_log_scope_unavailable",
            "console_error_samples": [sample("unclassified")],
        }

        summary = verdict_summary(
            persisted_test_result=persisted,
            active_state={"console_error_counter_session_id": "post-exit-domain", "console_error_count_total": 0},
            request_completed=False,
        )

        self.assertEqual(0, summary["console_error_count_since_request_start"])
        self.assertTrue(summary["console_error_pressure_detected"])
        self.assertEqual(1, summary["console_error_not_expected_count"])
        self.assertEqual("utf_log_scope_unavailable", summary["console_error_classification_basis"])
        self.assertTrue(compact_projection(summary)["console_error_pressure_detected"])

        without_bridge = verdict_summary(persisted_test_result=persisted, active_state={}, request_completed=False)
        self.assertTrue(without_bridge["console_error_pressure_detected"])

        completed = verdict_summary(
            persisted_test_result={**persisted, "run_phase": "response_written", "completed_at_utc": "2026-11-03T16:01:01Z"},
            active_state={"console_error_counter_session_id": "post-exit-domain", "console_error_count_total": 0},
        )
        self.assertTrue(completed["console_error_pressure_detected"])
        self.assertEqual(1, completed["console_error_not_expected_count"])

    def test_runtime_timeout_with_only_expected_errors_does_not_promote_console_inspection(self) -> None:
        summary = verdict_summary(
            persisted_test_result={
                "run_phase": "timed_out",
                "timeout_classification": "runtime_timeout_after_test_start",
                "started_at_utc": "2020-01-01T00:00:00Z",
                "runtime_timeout_ms": 1000,
                "console_error_count_at_request_start": 10,
                "console_error_counter_session_id_at_request_start": "same-session",
                "console_error_expected_by_test_count": 2,
                "console_error_expected_by_test_count_in_session": 2,
                "console_error_expected_by_test_counter_session_id": "same-session",
            },
            active_state={"playmode_state": "edit", "console_error_count_total": 12, "console_error_counter_session_id": "same-session"},
            request_completed=False,
            operation=EDITMODE,
        )

        self.assertEqual("runtime_timeout", summary["test_verdict"])
        self.assertEqual(2, summary["console_error_count_since_request_start"])
        self.assertFalse(summary["console_error_pressure_detected"])
        self.assertEqual("inspect_test_timeout_or_raise_budget", summary["recommended_next_action"])

    def test_persisted_result_reconciliation_keeps_the_classification_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            request_id = "req-classified"
            persisted = {
                "request_id": request_id,
                "response_handoff_state": "written",
                "console_error_expected_by_test_count": 1,
                "console_error_not_expected_recorded_count": 1,
                "console_error_samples": [sample("unexpected"), sample("expected_by_test")],
            }
            write_json(test_result_path(project_root, request_id), persisted)

            outcome = server_batch_orchestrator.reconcile_persisted_test_result_after_lifecycle(
                project_root, request_id, PLAYMODE, {"status": "passed", "playmode_state_after_settle": "edit"}
            )
            reconciled = read_json(test_result_path(project_root, request_id))

        self.assertEqual("reconciled", outcome)
        for key in ("console_error_expected_by_test_count", "console_error_not_expected_recorded_count", "console_error_samples"):
            self.assertEqual(persisted[key], reconciled[key])


def completed_persisted_result_0_3_84(**overrides) -> dict:
    persisted = {
        "request_id": "69096501-1f22-47d2-a0d3-a5f116c2f63b",
        "operation": PLAYMODE,
        "run_phase": "response_written",
        "completed_at_utc": "2026-11-03T19:13:43Z",
        "status": "passed",
        "test_verdict": "passed",
        "response_handoff_state": "written",
        "total": 14,
        "passed": 14,
        "console_error_count_at_request_start": 0,
        "console_error_counter_session_id_at_request_start": "7784644c0c104ee09fe665fc12c53513",
        "console_error_samples": [],
        "console_error_expected_by_test_count": 0,
        "console_error_expected_by_test_count_in_session": 0,
        "console_error_expected_by_test_counter_session_id": "",
        "console_error_not_expected_recorded_count": 0,
        "console_error_classification_basis": "none",
    }
    persisted.update(overrides)
    return persisted


class CompletedRunFinalStatusTests(unittest.TestCase):
    later_run_state = {"console_error_counter_session_id": "later-run-session", "console_error_count_total": 1}

    def test_completed_run_reports_its_own_recorded_counts_not_the_live_counter(self) -> None:
        pressure = server_bridge_final_status._test_console_pressure_summary(
            completed_persisted_result_0_3_84(), self.later_run_state
        )

        self.assertFalse(pressure["console_error_pressure_detected"])
        self.assertEqual(0, pressure["console_error_not_expected_count"])
        self.assertEqual(0, pressure["console_error_count_since_request_start"])
        self.assertEqual("lower_bound_from_recorded_attribution", pressure["console_error_count_trust_class"])

        same_session_after_later_runs = server_bridge_final_status._test_console_pressure_summary(
            completed_persisted_result_0_3_84(),
            {"console_error_counter_session_id": "7784644c0c104ee09fe665fc12c53513", "console_error_count_total": 5},
        )
        self.assertFalse(same_session_after_later_runs["console_error_pressure_detected"])
        self.assertEqual(0, same_session_after_later_runs["console_error_count_since_request_start"])

        summary = verdict_summary(persisted_test_result=completed_persisted_result_0_3_84(), active_state=self.later_run_state)
        self.assertEqual("passed", summary["test_verdict"])
        self.assertFalse(summary["console_error_pressure_detected"])
        self.assertEqual("", summary["console_error_pressure_warning"])
        compact = compact_projection(summary)
        self.assertFalse(compact["console_error_pressure_detected"])
        self.assertEqual(0, compact["console_error_not_expected_count"])

    def test_completed_legacy_run_counts_its_recorded_attribution(self) -> None:
        pressure = server_bridge_final_status._test_console_pressure_summary(
            completed_persisted_result_0_3_84(
                console_error_expected_by_test_count=2,
                console_error_expected_by_test_count_in_session=2,
                console_error_expected_by_test_counter_session_id="later-run-session",
                console_error_not_expected_recorded_count=1,
                console_error_samples=[sample("unexpected"), sample("expected_by_test")],
            ),
            {"console_error_counter_session_id": "later-run-session", "console_error_count_total": 9},
        )

        self.assertTrue(pressure["console_error_pressure_detected"])
        self.assertEqual(1, pressure["console_error_not_expected_count"])
        self.assertEqual(2, pressure["console_error_expected_by_test_count"])
        self.assertEqual(3, pressure["console_error_count_since_request_start"])
        self.assertEqual(["unexpected", "expected_by_test"], [item["classification"] for item in pressure["console_error_samples"]])

    def test_completed_run_prefers_the_counts_frozen_at_completion(self) -> None:
        frozen = completed_persisted_result_0_3_84(
            console_error_expected_by_test_count=1,
            console_error_count_at_completion=1,
            console_error_count_trust_class_at_completion="lower_bound_after_domain_reload",
            console_error_not_expected_count_at_completion=0,
        )
        for active_state in (self.later_run_state, {}, {"console_error_counter_session_id": "x", "console_error_count_total": 40}):
            with self.subTest(active_state=active_state):
                pressure = server_bridge_final_status._test_console_pressure_summary(frozen, active_state)
                self.assertFalse(pressure["console_error_pressure_detected"])
                self.assertEqual(0, pressure["console_error_not_expected_count"])
                self.assertEqual(1, pressure["console_error_count_since_request_start"])
                self.assertEqual("lower_bound_after_domain_reload", pressure["console_error_count_trust_class"])

        with_floor = server_bridge_final_status._test_console_pressure_summary(
            {**frozen, "console_error_not_expected_count_at_completion": 2, "console_error_not_expected_recorded_count": 3},
            self.later_run_state,
        )
        self.assertTrue(with_floor["console_error_pressure_detected"])
        self.assertEqual(3, with_floor["console_error_not_expected_count"])

    def test_completed_result_without_attribution_never_reads_the_live_counter(self) -> None:
        pre_attribution = {
            key: value
            for key, value in completed_persisted_result_0_3_84().items()
            if not key.startswith("console_error_") or key.endswith("_at_request_start")
        }
        pressure = server_bridge_final_status._test_console_pressure_summary(pre_attribution, self.later_run_state)

        self.assertFalse(pressure["console_error_pressure_detected"])
        self.assertEqual(0, pressure["console_error_count_since_request_start"])
        self.assertEqual("unavailable", pressure["console_error_count_trust_class"])

    def test_abandoned_run_reports_its_recorded_attribution_not_later_runs(self) -> None:
        abandoned_fields = {
            "run_phase": "abandoned",
            "response_handoff_state": "released",
            "completed_at_utc": "",
            "status": "",
            "test_verdict": "",
            "timeout_classification": "timeout_before_test_start",
            "total": 0,
            "passed": 0,
            "console_error_counter_session_id_at_request_start": "S1",
            "console_error_count_at_request_start": 0,
        }
        cases = {
            "same_session": {"console_error_counter_session_id": "S1", "console_error_count_total": 5},
            "later_domain": {"console_error_counter_session_id": "S2", "console_error_count_total": 5},
        }
        for basis in ("none", "utf_log_scope"):
            for name, active_state in cases.items():
                with self.subTest(basis=basis, case=name):
                    abandoned = completed_persisted_result_0_3_84(console_error_classification_basis=basis, **abandoned_fields)
                    pressure = server_bridge_final_status._test_console_pressure_summary(abandoned, active_state)
                    self.assertFalse(pressure["console_error_pressure_detected"])
                    self.assertEqual(0, pressure["console_error_not_expected_count"])
                    self.assertEqual(0, pressure["console_error_count_since_request_start"])
                    self.assertEqual("lower_bound_from_recorded_attribution", pressure["console_error_count_trust_class"])

        legacy_abandoned = {
            key: value
            for key, value in completed_persisted_result_0_3_84(**abandoned_fields).items()
            if not key.startswith("console_error_") or key.endswith("_at_request_start")
        }
        pressure = server_bridge_final_status._test_console_pressure_summary(legacy_abandoned, cases["same_session"])
        self.assertFalse(pressure["console_error_pressure_detected"])
        self.assertEqual("unavailable", pressure["console_error_count_trust_class"])

        summary = verdict_summary(
            persisted_test_result=completed_persisted_result_0_3_84(**abandoned_fields),
            active_state=cases["same_session"],
            request_completed=False,
        )
        self.assertEqual("unity_unproven", summary["test_verdict"])
        self.assertFalse(summary["console_error_pressure_detected"])
        self.assertEqual(0, summary["console_error_not_expected_count"])

    def test_timed_out_run_keeps_the_live_counter_lower_bound(self) -> None:
        timed_out = completed_persisted_result_0_3_84(run_phase="timed_out", completed_at_utc="", response_handoff_state="pending")
        pressure = server_bridge_final_status._test_console_pressure_summary(timed_out, self.later_run_state)

        self.assertTrue(pressure["console_error_pressure_detected"])
        self.assertEqual("lower_bound_after_domain_reload", pressure["console_error_count_trust_class"])

    def test_running_result_keeps_the_live_counter_lower_bound(self) -> None:
        running = completed_persisted_result_0_3_84(run_phase="running", completed_at_utc="", response_handoff_state="pending")
        pressure = server_bridge_final_status._test_console_pressure_summary(running, self.later_run_state)

        self.assertTrue(pressure["console_error_pressure_detected"])
        self.assertEqual(1, pressure["console_error_not_expected_count"])
        self.assertEqual("lower_bound_after_domain_reload", pressure["console_error_count_trust_class"])


class HeartbeatConsoleCounterOwnershipTests(unittest.TestCase):
    def heartbeat(self, active_request_id: str) -> dict:
        return {
            "playmode_state": "edit",
            "active_test_request_id": active_request_id,
            "active_test_console_error_count_trust_class": "complete_since_request_start",
            "active_test_console_error_count_since_request_start": 3,
        }

    def test_completed_request_without_payload_ignores_another_runs_heartbeat_counts(self) -> None:
        summary = server_bridge_final_status.build_test_verdict_summary(
            project_root=Path("/tmp/FakeProject"),
            request_id="B",
            operation=PLAYMODE,
            response_payload=None,
            persisted_test_result=None,
            request_submitted=True,
            request_started=True,
            request_completed=True,
            completion_status="error",
            operation_outcome="completed_error",
            active_state=self.heartbeat("A"),
            bridge_changed_since_submission=False,
        )

        self.assertEqual(0, summary["console_error_count_since_request_start"])
        self.assertEqual("unavailable", summary["console_error_count_trust_class"])
        self.assertEqual(0, summary["console_error_not_expected_count"])
        self.assertFalse(summary["console_error_pressure_detected"])

    def test_heartbeat_counts_apply_only_to_their_own_running_request(self) -> None:
        own_running = server_bridge_final_status._test_console_pressure_summary(
            None, self.heartbeat("A"), request_id="A", request_completed=False
        )
        self.assertEqual(3, own_running["console_error_count_since_request_start"])
        self.assertEqual("complete_since_request_start", own_running["console_error_count_trust_class"])
        self.assertTrue(own_running["console_error_pressure_detected"])

        for request_id, request_completed in (("B", False), ("A", True), ("", False)):
            with self.subTest(request_id=request_id, request_completed=request_completed):
                pressure = server_bridge_final_status._test_console_pressure_summary(
                    None, self.heartbeat("A"), request_id=request_id, request_completed=request_completed
                )
                self.assertEqual(0, pressure["console_error_count_since_request_start"])
                self.assertEqual("unavailable", pressure["console_error_count_trust_class"])
                self.assertFalse(pressure["console_error_pressure_detected"])


class ConsoleErrorSampleSurfaceTests(unittest.TestCase):
    def test_compact_tests_payload_bounds_truncates_and_orders_samples(self) -> None:
        samples = [sample("expected_by_test", message=f"expected {index}") for index in range(4)]
        samples.append(sample("unexpected", message="x" * 1000, junk="drop me"))
        payload = {
            "status": "passed",
            "total": 5,
            "passed": 5,
            "console_error_count_since_request_start": 5,
            "console_error_pressure_detected": True,
            "console_error_expected_by_test_count": 4,
            "console_error_not_expected_count": 1,
            "console_error_classification_basis": "utf_log_scope",
            "console_error_samples": samples,
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, PLAYMODE)

        self.assertEqual(3, len(compact["console_error_samples"]))
        self.assertEqual("unexpected", compact["console_error_samples"][0]["classification"])
        for item in compact["console_error_samples"]:
            self.assertEqual(server_operation_evidence.CONSOLE_ERROR_SAMPLE_FIELDS, tuple(item))
            self.assertLessEqual(len(item["message"]), server_operation_evidence.CONSOLE_ERROR_SAMPLE_MESSAGE_LIMIT + 3)
        self.assertTrue(compact["console_error_samples"][0]["message"].endswith("..."))
        self.assertEqual(4, compact["console_error_expected_by_test_count"])
        self.assertEqual(1, compact["console_error_not_expected_count"])
        self.assertEqual("utf_log_scope", compact["console_error_classification_basis"])

        clean = server_bridge_payloads.compact_operation_payload(
            {"status": "passed", "total": 1, "passed": 1, "console_error_samples": []}, EDITMODE
        )
        self.assertNotIn("console_error_samples", clean)

    def test_sample_projection_is_idempotent_and_normalizes_unknown_values(self) -> None:
        once = server_operation_evidence.compact_console_error_samples(
            [sample("surprise", message="m" * 600, type="warning", active_test="t" * 400), "not a dict"]
        )
        twice = server_operation_evidence.compact_console_error_samples(once)

        self.assertEqual(once, twice)
        self.assertEqual("unclassified", once[0]["classification"])
        self.assertEqual("error", once[0]["type"])
        self.assertEqual(server_operation_evidence.CONSOLE_ERROR_SAMPLE_ACTIVE_TEST_LIMIT + 3, len(once[0]["active_test"]))
        self.assertEqual([], server_operation_evidence.compact_console_error_samples(None))

    def test_terminal_envelope_carries_the_classification_within_the_byte_ceiling(self) -> None:
        decoded = expected_only_response()
        decoded["console_error_samples"] = [
            sample("unexpected", message="\U0001F600" * 2000, active_test="ж" * 2000) for _ in range(5)
        ]
        decoded["failures"] = [{"name": "Layout.Test", "message": "m" * 2000}]
        envelope = server_launcher.build_compact_terminal_envelope(
            {
                "action": "request",
                "request_id": "req-console",
                "payload_type": PLAYMODE,
                "payload_json": json.dumps(decoded),
            },
            0,
        )

        self.assertFalse(envelope["console_error_pressure_detected"])
        self.assertEqual(1, envelope["console_error_expected_by_test_count"])
        self.assertEqual(0, envelope["console_error_not_expected_count"])
        self.assertEqual(3, len(envelope["console_error_samples"]))
        encoded = server_launcher._bounded_compact_json(envelope)
        self.assertLessEqual(len(encoded.encode("utf-8")), server_launcher.COMPACT_OUTPUT_MAX_BYTES)
        self.assertNotIn("compact_truncated", json.loads(encoded))

    def test_terminal_envelope_sheds_optional_evidence_before_the_verdict(self) -> None:
        environment = {"capture_status": "captured", "render_width": 1440, "render_height": 3200, "preset_label": "L" * 64}
        for failure_message, omitted in (
            ("m" * 6000, ["console_error_samples"]),
            ("ж" * 1200, ["console_error_samples"]),
            ("m" * 7900, ["console_error_samples", "test_environment", "first_failure"]),
        ):
            with self.subTest(length=len(failure_message), omitted=omitted):
                decoded = {
                    "status": "failed",
                    "total": 40,
                    "passed": 39,
                    "failed": 1,
                    "failures": [{"name": "Layout.Test", "message": failure_message}],
                    "console_error_pressure_detected": True,
                    "console_error_not_expected_count": 3,
                    "console_error_samples": [
                        sample("unexpected", message="x" * 240, active_test="t" * 160) for _ in range(3)
                    ],
                    "test_environment": environment,
                }
                envelope = server_launcher.build_compact_terminal_envelope(
                    {"action": "request", "request_id": "req-shed", "payload_type": PLAYMODE, "payload_json": json.dumps(decoded)},
                    0,
                )
                encoded = server_launcher._bounded_compact_json(envelope)
                compact = json.loads(encoded)

                self.assertLessEqual(len(encoded.encode("utf-8")), server_launcher.COMPACT_OUTPUT_MAX_BYTES)
                self.assertTrue(compact["compact_truncated"])
                self.assertEqual(omitted, compact["compact_omitted_fields"])
                self.assertEqual("failed", compact["test_verdict"])
                self.assertEqual((40, 39, 1), (compact["total"], compact["passed"], compact["failed"]))
                self.assertTrue(compact["console_error_pressure_detected"])
                self.assertEqual("Layout.Test", compact["first_failure"]["name"])
                self.assertNotIn("console_error_samples", compact)

    def test_reduced_envelope_keeps_the_test_verdict_and_counts(self) -> None:
        envelope = {
            "outcome": "error",
            "action": "request",
            "test_verdict": "failed",
            "total": 2,
            "passed": 1,
            "failed": 1,
            "console_error_pressure_detected": True,
            "padding": "x" * server_launcher.COMPACT_OUTPUT_MAX_BYTES,
        }
        compact = json.loads(server_launcher._bounded_compact_json(envelope))

        self.assertTrue(compact["compact_truncated"])
        self.assertNotIn("padding", compact)
        self.assertEqual("failed", compact["test_verdict"])
        self.assertEqual((2, 1, 1), (compact["total"], compact["passed"], compact["failed"]))
        self.assertTrue(compact["console_error_pressure_detected"])

    def test_final_status_envelope_falls_back_to_the_top_level_classification(self) -> None:
        summary = verdict_summary(response_payload=expected_only_response())
        envelope = server_launcher.build_compact_terminal_envelope(
            {"action": "request-final-status", **summary}, 0
        )

        self.assertFalse(envelope["console_error_pressure_detected"])
        self.assertEqual(1, envelope["console_error_expected_by_test_count"])
        self.assertEqual("expected_by_test", envelope["console_error_samples"][0]["classification"])

        legacy = server_launcher.build_compact_terminal_envelope({"action": "request-final-status", "test_verdict": "passed"}, 0)
        self.assertNotIn("console_error_pressure_detected", legacy)
        self.assertNotIn("console_error_samples", legacy)


if __name__ == "__main__":
    unittest.main()
