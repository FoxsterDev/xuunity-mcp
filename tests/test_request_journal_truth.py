import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_bridge_final_status as final_status
import server_bridge_journal as journal
import server_bridge_transport as transport
from server_bridge_paths import request_journal_dir, response_path
from server_core import read_json, write_json


def _event(root: Path, name: str, payload: dict) -> None:
    directory = request_journal_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / f"{name}.json", payload)


def _utc(offset_seconds: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_seconds))


class ProgressEventRequestIdTests(unittest.TestCase):
    def test_progress_events_and_transport_share_one_request_id(self) -> None:
        project_root = Path(tempfile.gettempdir()) / "journal-truth-progress"
        context = SimpleNamespace(project_root=project_root, discovery_details={})
        phases: list[tuple[str, str]] = []
        transport_kwargs: dict = {}

        def capture_phase(**kwargs):
            phases.append((kwargs["phase"], kwargs.get("request_id", "")))

        def fake_transport(*_args, **kwargs):
            transport_kwargs.update(kwargs)
            return {"status": "ok", "payload_json": ""}, kwargs["request_id"], time.time(), {"name": "file_ipc"}

        policy = {
            "activate_unity": False,
            "wait_for_idle_before": True,
            "wait_for_idle_after": False,
            "idle_stable_cycles_after": 1,
            "retry_on_lifecycle_reset": False,
            "retry_on_transport_response_missing": False,
            "retry_on_transport_connect_failed": False,
            "post_reset_recovery_cap_ms": 0,
        }
        with (
            mock.patch.object(server_batch_orchestrator, "get_project_context", return_value=context),
            mock.patch.object(server_batch_orchestrator, "run_in_project_request_lock", side_effect=lambda _c, _o, cb: cb()),
            mock.patch.object(server_batch_orchestrator, "resolve_operation_lifecycle_policy", return_value=policy),
            mock.patch.object(server_batch_orchestrator, "try_read_live_editor_state", return_value={}),
            mock.patch.object(server_batch_orchestrator, "current_project_context_bridge_state", return_value={}),
            mock.patch.object(server_batch_orchestrator, "fail_if_compile_broken_for_operation", return_value=False),
            mock.patch.object(server_batch_orchestrator, "wait_for_editor_idle", return_value={}),
            mock.patch.object(server_batch_orchestrator, "report_operation_progress_phase", side_effect=capture_phase),
            mock.patch.object(server_batch_orchestrator, "invoke_bridge_transport", side_effect=fake_transport),
            mock.patch.object(server_batch_orchestrator, "refresh_project_context"),
        ):
            server_batch_orchestrator.invoke_bridge(str(project_root), "unity.status", {}, 1000)

        self.assertEqual(["wait_for_idle_before", "dispatching", "waiting_for_response"], [p for p, _ in phases])
        request_ids = {request_id for _, request_id in phases}
        self.assertEqual({transport_kwargs["request_id"]}, request_ids)
        self.assertTrue(transport_kwargs["request_id"])


class JournalOrderingTests(unittest.TestCase):
    def test_same_millisecond_host_events_sort_by_sequence(self) -> None:
        events = [
            {"event_at_utc": "2026-10-05T14:55:01Z", "event_id": "20261005T145501123Z_ffff_b", "host_event_sequence": 7},
            {"event_at_utc": "2026-10-05T14:55:01Z", "event_id": "20261005T145501123Z_0000_a", "host_event_sequence": 8},
            {"event_at_utc": "2026-10-05T14:55:01Z", "event_id": "20261005T145501100Z_9999_c"},
        ]
        ordered = sorted(events, key=journal.journal_event_sort_key)
        self.assertEqual(["c", "b", "a"], [event["event_id"].rsplit("_", 1)[1] for event in ordered])

    def test_host_events_carry_a_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = read_json(journal.write_host_request_journal_event(root, "operation_progress", {"request_id": "r"}))
            second = read_json(journal.write_host_request_journal_event(root, "operation_progress", {"request_id": "r"}))
        self.assertGreater(second["host_event_sequence"], first["host_event_sequence"])


class ReclassificationGenerationTests(unittest.TestCase):
    def _write(self, root: Path, state: dict) -> dict:
        with mock.patch.object(transport, "read_best_effort_bridge_state", return_value=state):
            path = transport.write_lifecycle_reclassification_event(
                root,
                request_id="r1",
                operation="unity.tests.run_playmode",
                retryable=False,
                initial_generation=5,
                initial_session_id="s5",
                state={},
                trigger="transport_restarting",
                recovery_fields={},
            )
        return read_json(path)

    def test_unchanged_generation_is_not_reported_as_a_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = self._write(Path(tmp), {"bridge_generation": 5, "bridge_session_id": "s5"})
        self.assertFalse(event["bridge_generation_changed"])
        self.assertEqual("transport_restarting_before_response", event["reason"])
        self.assertEqual(5, event["bridge_generation"])

    def test_new_generation_read_at_write_time_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = self._write(Path(tmp), {"bridge_generation": 6, "bridge_session_id": "s6"})
        self.assertTrue(event["bridge_generation_changed"])
        self.assertEqual("bridge_generation_changed_before_response", event["reason"])
        self.assertEqual(6, event["bridge_generation"])
        self.assertEqual(5, event["previous_bridge_generation"])


class FinalStatusJournalTruthTests(unittest.TestCase):
    def _status(self, root: Path, request_id: str, **kwargs) -> dict:
        with mock.patch.object(final_status, "read_best_effort_bridge_state", return_value={}):
            return final_status.build_request_final_status(root, request_id, **kwargs)

    def test_playmode_run_abandoned_by_play_entry_reload_is_not_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _event(root, "a_submitted", {"event_type": "request_submitted", "request_id": "pm", "operation": "unity.tests.run_playmode",
                                         "event_at_utc": _utc(-10), "event_source": "host_wrapper", "request_timeout_ms": 900000,
                                         "request_submitted_unix": time.time() - 10, "host_delivery_tracking": True})
            _event(root, "b_started", {"event_type": "request_started", "request_id": "pm", "operation": "unity.tests.run_playmode",
                                       "event_at_utc": _utc(-9), "event_source": "unity_bridge"})
            _event(root, "c_abandoned", {"event_type": "request_abandoned", "request_id": "pm", "operation": "unity.tests.run_playmode",
                                         "event_at_utc": _utc(-4), "event_source": "unity_bridge", "retryable": True,
                                         "reason": "domain_reload_before_request_completion",
                                         "reclassified_status": "retryable_after_lifecycle_reset"})
            status = self._status(root, "pm")
        self.assertTrue(status["resumes_after_domain_reload"])
        self.assertFalse(status["retryable"])
        self.assertEqual("resumes_after_domain_reload", status["operation_outcome"])
        self.assertEqual("wait_for_final_status", status["recommended_next_action"])
        self.assertEqual("unity_unproven", status["result_trust_class"])
        self.assertEqual(0, status["safe_retry_budget_total"])

    def test_editmode_abandon_stays_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _event(root, "a_abandoned", {"event_type": "request_abandoned", "request_id": "em", "operation": "unity.project.refresh",
                                         "event_at_utc": _utc(-4), "retryable": True,
                                         "reason": "domain_reload_before_request_completion",
                                         "reclassified_status": "retryable_after_lifecycle_reset"})
            status = self._status(root, "em")
        self.assertFalse(status["resumes_after_domain_reload"])
        self.assertTrue(status["retryable"])

    def test_refusal_closes_the_planned_request_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _event(root, "a_progress", {"event_type": "operation_progress", "request_id": "rf", "phase": "wait_for_idle_before",
                                        "event_at_utc": _utc(-3), "event_source": "host_wrapper"})
            _event(root, "b_refused", {"event_type": "request_refused", "request_id": "rf", "code": "editor_idle_timeout",
                                       "request_submitted": False, "recommended_next_action": "wait_for_editor_idle_then_retry",
                                       "event_at_utc": _utc(-2), "event_source": "host_wrapper"})
            status = self._status(root, "rf")
        self.assertEqual("refused_before_submission", status["operation_outcome"])
        self.assertEqual("editor_idle_timeout", status["refusal_code"])
        self.assertEqual("wait_for_editor_idle_then_retry", status["recommended_next_action"])
        self.assertEqual("request_not_observed", status["result_trust_class"])

    def _orphan_fixture(self, root: Path) -> Path:
        _event(root, "a_submitted", {"event_type": "request_submitted", "request_id": "or", "operation": "unity.tests.run_playmode",
                                     "event_at_utc": _utc(-400), "event_source": "host_wrapper", "request_timeout_ms": 300000,
                                     "request_submitted_unix": time.time() - 400, "host_delivery_tracking": True})
        _event(root, "b_started", {"event_type": "request_started", "request_id": "or", "event_at_utc": _utc(-399)})
        _event(root, "c_reclassified", {"event_type": "request_reclassified", "request_id": "or", "event_at_utc": _utc(-100),
                                        "event_source": "host_wrapper", "retryable": False,
                                        "reclassified_status": "response_missing_after_lifecycle_reset"})
        _event(root, "d_completed", {"event_type": "request_completed", "request_id": "or", "operation_status": "ok",
                                     "event_at_utc": _utc(-50)})
        outbox = response_path(root, "or")
        outbox.parent.mkdir(parents=True, exist_ok=True)
        write_json(outbox, {"request_id": "or", "status": "ok", "payload_json": json.dumps({"status": "passed"})})
        return outbox

    def test_user_final_status_consumes_an_orphaned_outbox_response_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outbox = self._orphan_fixture(root)
            status = self._status(root, "or", reconcile_orphaned_outbox=True)
            self.assertFalse(outbox.exists())
            self.assertTrue(status["orphaned_outbox_response"]["consumed"])
            self.assertEqual("host_waiter_reclassified", status["orphaned_outbox_response"]["basis"])
            reconciled = list(request_journal_dir(root).glob("*request_outbox_reconciled.json"))
            self.assertEqual(1, len(reconciled))
            again = self._status(root, "or", reconcile_orphaned_outbox=True)
            self.assertNotIn("orphaned_outbox_response", again)

    def test_internal_final_status_never_consumes_the_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outbox = self._orphan_fixture(root)
            status = self._status(root, "or")
            self.assertTrue(outbox.exists())
            self.assertNotIn("orphaned_outbox_response", status)

    def test_outbox_of_a_live_waiter_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _event(root, "a_submitted", {"event_type": "request_submitted", "request_id": "lw", "event_at_utc": _utc(-5),
                                         "event_source": "host_wrapper", "request_timeout_ms": 600000,
                                         "request_submitted_unix": time.time() - 5, "host_delivery_tracking": True})
            _event(root, "b_completed", {"event_type": "request_completed", "request_id": "lw", "operation_status": "ok",
                                         "event_at_utc": _utc(-1)})
            outbox = response_path(root, "lw")
            outbox.parent.mkdir(parents=True, exist_ok=True)
            write_json(outbox, {"request_id": "lw", "status": "ok", "payload_json": "{}"})
            self._status(root, "lw", reconcile_orphaned_outbox=True)
            self.assertTrue(outbox.exists())


class RuntimeBudgetTests(unittest.TestCase):
    def test_completed_run_past_its_budget_is_classified_not_failed(self) -> None:
        overrun = final_status.completed_runtime_budget_overrun_seconds(
            {"runtime_timeout_ms": 900000, "started_at_utc": "2026-10-05T14:44:00Z", "completed_at_utc": "2026-10-05T15:00:44Z"}
        )
        self.assertEqual(104.0, overrun)

    def test_completed_run_inside_its_budget_has_no_overrun(self) -> None:
        self.assertIsNone(
            final_status.completed_runtime_budget_overrun_seconds(
                {"runtime_timeout_ms": 900000, "started_at_utc": "2026-10-05T14:44:00Z", "completed_at_utc": "2026-10-05T14:50:00Z"}
            )
        )


if __name__ == "__main__":
    unittest.main()
