import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_bridge_final_status import build_bridge_stabilization_summary
from server_bridge_state import effective_bridge_health_status
from server_discovery import discover_project_context_state
from server_summary_status import build_status_summary


def _batch_state(pid: int) -> dict:
    return {
        "editor_pid": pid,
        "bridge_process_class": "batch",
        "health_status": "healthy",
        "transport": "file_ipc",
    }


class DeadBatchStateTruthTests(unittest.TestCase):
    def test_hard_killed_batch_state_is_stale_not_non_main_owner(self) -> None:
        result = discover_project_context_state(
            Path("/tmp/ProjectA"),
            try_read_bridge_state=lambda _: _batch_state(5150),
            try_read_host_editor_session_state=lambda _: {},
            find_running_unity_editors_for_project=lambda _: [],
            pid_is_alive=lambda pid: False,
            bridge_enabled=lambda _: True,
        )

        self.assertFalse(result["bridge_owned_by_non_main_process"])
        self.assertTrue(result["bridge_state_writer_exited"])
        self.assertEqual("process_exited", result["bridge_health_status_effective"])
        self.assertEqual("stale_state", result["discovery_classification"])
        self.assertEqual("stale_bridge_state", result["reconciliation_case"])
        self.assertNotIn("bridge_owned_by_non_main_process", result["host_prerequisites"]["blocking_codes"])

    def test_hard_killed_batch_state_does_not_hide_a_live_main_editor(self) -> None:
        result = discover_project_context_state(
            Path("/tmp/ProjectA"),
            try_read_bridge_state=lambda _: _batch_state(5150),
            try_read_host_editor_session_state=lambda _: {"editor_pid": 101},
            find_running_unity_editors_for_project=lambda _: [{"pid": 101}],
            pid_is_alive=lambda pid: pid == 101,
            bridge_enabled=lambda _: True,
        )

        self.assertFalse(result["bridge_owned_by_non_main_process"])
        self.assertEqual("host_session_live", result["discovery_classification"])
        self.assertEqual(101, result["last_seen_pid"])

    def test_live_batch_writer_still_owns_the_bridge(self) -> None:
        result = discover_project_context_state(
            Path("/tmp/ProjectA"),
            try_read_bridge_state=lambda _: _batch_state(5150),
            try_read_host_editor_session_state=lambda _: {},
            find_running_unity_editors_for_project=lambda _: [{"pid": 5150}],
            pid_is_alive=lambda pid: pid == 5150,
            bridge_enabled=lambda _: True,
        )

        self.assertTrue(result["bridge_owned_by_non_main_process"])
        self.assertFalse(result["bridge_state_writer_exited"])
        self.assertEqual("healthy", result["bridge_health_status_effective"])

    def test_reused_pid_of_a_dead_batch_writer_reads_as_exited(self) -> None:
        result = discover_project_context_state(
            Path("/tmp/ProjectA"),
            try_read_bridge_state=lambda _: _batch_state(5150),
            try_read_host_editor_session_state=lambda _: {},
            find_running_unity_editors_for_project=lambda _: [],
            find_running_unity_worker_processes_for_project=lambda _: [],
            pid_is_alive=lambda pid: pid == 5150,
            bridge_enabled=lambda _: True,
            process_visibility_report={"process_visibility_available": True},
        )

        self.assertTrue(result["bridge_pid_alive"])
        self.assertTrue(result["bridge_state_writer_pid_reused"])
        self.assertTrue(result["bridge_state_writer_exited"])
        self.assertFalse(result["bridge_owned_by_non_main_process"])
        self.assertEqual("process_exited", result["bridge_health_status_effective"])
        self.assertEqual("stale_state", result["discovery_classification"])

    def test_reused_pid_is_not_claimed_without_process_visibility(self) -> None:
        result = discover_project_context_state(
            Path("/tmp/ProjectA"),
            try_read_bridge_state=lambda _: _batch_state(5150),
            try_read_host_editor_session_state=lambda _: {},
            find_running_unity_editors_for_project=lambda _: [],
            pid_is_alive=lambda pid: pid == 5150,
            bridge_enabled=lambda _: True,
            process_visibility_report={"process_visibility_available": False},
        )

        self.assertFalse(result["bridge_state_writer_pid_reused"])
        self.assertTrue(result["bridge_owned_by_non_main_process"])

    def test_status_summary_reads_process_exited_for_a_reused_batch_pid(self) -> None:
        summary = build_status_summary(
            Path("/tmp/ProjectA"),
            {},
            read_best_effort_bridge_state=lambda _: None,
            try_read_bridge_state=lambda _: _batch_state(5150),
            pid_is_alive=lambda pid: pid == 5150,
            heartbeat_age_seconds=lambda _: 3.0,
            derive_busy_reason=lambda _: "",
            summarize_state_for_error=lambda _: "",
            discovery_details={"bridge_state_writer_pid_reused": True, "bridge_state_writer_exited": True},
        )

        self.assertFalse(summary["editor_running"])
        self.assertEqual("process_exited", summary["health_status"])
        self.assertEqual("healthy", summary["recorded_health_status"])

    def test_stabilization_reports_process_exited_for_a_dead_batch_writer(self) -> None:
        summary = build_bridge_stabilization_summary(_batch_state(5150), editor_running=False)

        self.assertEqual("process_exited", summary["health_status"])
        self.assertEqual("healthy", summary["recorded_health_status"])
        self.assertIn("editor_not_running", summary["blocking_reasons"])
        self.assertNotIn("bridge_owned_by_non_main_process", summary["blocking_reasons"])
        self.assertFalse(summary["safe_to_retry"])

    def test_effective_health_keeps_recorded_status_for_live_or_unknown_pid(self) -> None:
        self.assertEqual("healthy", effective_bridge_health_status(_batch_state(5150), pid_alive=True))
        self.assertEqual("healthy", effective_bridge_health_status(_batch_state(0), pid_alive=False))
        self.assertEqual(
            "editor_not_running",
            effective_bridge_health_status({"editor_pid": 7, "health_status": "healthy"}, pid_alive=False),
        )
        self.assertEqual(
            "process_exited",
            effective_bridge_health_status(
                {"editor_pid": 7, "bridge_process_class": "batch", "health_status": "process_exited"},
                pid_alive=False,
            ),
        )


if __name__ == "__main__":
    unittest.main()
