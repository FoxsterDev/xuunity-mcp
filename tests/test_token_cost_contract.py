import json
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_context
import server_batch_orchestrator
from server_bridge_paths import request_journal_dir
from server_core import ToolInvocationError
from server_test_suite_timeout import is_unfiltered_test_run, suite_aware_default_timeout_ms


class ErrorEnvelopeDeduplicationTests(unittest.TestCase):
    def test_promoted_final_status_and_stabilization_are_not_repeated_in_error_details(self) -> None:
        final_status = {"payload_mode": "compact_final_status", "request_id": "r1", "journal_event_count": 9}
        error = ToolInvocationError(
            "transport_response_missing",
            "missing",
            {
                "request_id": "r1",
                "request_final_status": final_status,
                "bridge_stabilization": {"stabilized": True},
                "recommended_recovery_command": "x request-final-status --request-id r1",
            },
        )
        for builder in (server_batch_orchestrator.build_tool_error_payload, server_batch_context.build_tool_error_payload):
            payload = builder(error)
            self.assertEqual(final_status, payload["request_final_status"])
            self.assertEqual({"stabilized": True}, payload["bridge_stabilization"])
            self.assertNotIn("request_final_status", payload["error"]["details"])
            self.assertNotIn("bridge_stabilization", payload["error"]["details"])
            self.assertEqual("r1", payload["error"]["details"]["request_id"])
            self.assertEqual(1, json.dumps(payload).count('"journal_event_count"'))
            self.assertIn("request_final_status", error.details)


class SuiteAwareTestTimeoutTests(unittest.TestCase):
    def _write_completed(self, project_root: Path, name: str, operation: str, started: str, completed: str) -> None:
        journal = request_journal_dir(project_root)
        journal.mkdir(parents=True, exist_ok=True)
        (journal / f"{name}_request_completed.json").write_text(
            json.dumps({"operation": operation, "started_at_utc": started, "completed_at_utc": completed}),
            encoding="utf-8",
        )

    def test_only_unfiltered_test_runs_qualify(self) -> None:
        self.assertTrue(is_unfiltered_test_run("unity.tests.run_editmode", {}))
        self.assertTrue(is_unfiltered_test_run("unity.tests.run_playmode", {"testNames": [""]}))
        self.assertFalse(is_unfiltered_test_run("unity.tests.run_editmode", {"assemblyNames": ["A.Tests"]}))
        self.assertFalse(is_unfiltered_test_run("unity.status", {}))

    def test_default_grows_to_one_and_a_half_times_the_longest_recent_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_completed(root, "20261105T200000000Z_a", "unity.tests.run_editmode", "2026-11-05T19:55:00Z", "2026-11-05T20:05:00Z")
            self._write_completed(root, "20261105T201000000Z_b", "unity.tests.run_editmode", "2026-11-05T20:09:00Z", "2026-11-05T20:09:20Z")
            self._write_completed(root, "20261105T202000000Z_c", "unity.tests.run_playmode", "2026-11-05T20:10:00Z", "2026-11-05T21:10:00Z")

            timeout, basis = suite_aware_default_timeout_ms(root, "unity.tests.run_editmode", 300000)

        self.assertEqual(900000, timeout)
        self.assertEqual("recent_suite_duration", basis)

    def test_short_or_missing_history_keeps_the_declared_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual((300000, "declared_default"), suite_aware_default_timeout_ms(root, "unity.tests.run_editmode", 300000))
            self._write_completed(root, "20261105T200000000Z_a", "unity.tests.run_editmode", "2026-11-05T19:55:00Z", "2026-11-05T19:56:00Z")
            self.assertEqual((300000, "declared_default"), suite_aware_default_timeout_ms(root, "unity.tests.run_editmode", 300000))


if __name__ == "__main__":
    unittest.main()
