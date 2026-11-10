"""Compact offline status_summary keeps the error to its code, message and recovery (QPF-MCP-05, RG-51)."""

import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_project_reporting
from server_core import ToolInvocationError

DETAILS = {
    "recommended_next_action": "recover_editor_session",
    "recommended_recovery_command": "xuunity_light_unity_mcp.sh recover-editor-session --project-root P",
    "host_health_classification": "offline",
    "stale_request_artifacts": {
        "candidate_count": 655,
        "classifications": {"orphaned_outbox_response": 655},
        "candidates": [{"path": f"outbox/{index}.json", "age_seconds": index} for index in range(50)],
    },
    "editor_log_diagnosis": {"classification": "interactive_compile_block_detected", "evidence_lines": ["x" * 300]},
    "state_groups": {"transport": {"listener": "inactive"}},
    "host_prerequisites": {"checks": {"live_editor": {"ok": False}}},
}


def build(include_full_payload: bool) -> dict:
    return server_project_reporting.build_discovery_status_summary_for_error_data(
        Path("P"),
        exc=ToolInvocationError("editor_not_running", "No live editor.", DETAILS),
        discovery={},
        build_status_summary_from_context=lambda root, payload, include_full_payload: {"action": "unity_status_summary"},
        enrich_error_details_with_discovery=lambda root, details: dict(details),
        include_full_payload=include_full_payload,
    )


class CompactStatusErrorTests(unittest.TestCase):
    def test_compact_error_keeps_code_message_and_recovery_only(self) -> None:
        error = build(False)["error"]

        self.assertEqual("editor_not_running", error["code"])
        details = error["details"]
        self.assertEqual("recover_editor_session", details["recommended_next_action"])
        self.assertIn("recover-editor-session", details["recommended_recovery_command"])
        self.assertEqual(655, details["stale_request_artifact_count"])
        self.assertEqual("interactive_compile_block_detected", details["editor_log_classification"])
        for heavy in ("stale_request_artifacts", "state_groups", "host_prerequisites", "editor_log_diagnosis"):
            self.assertNotIn(heavy, details)
        self.assertLess(len(json.dumps(error)), 700)

    def test_full_payload_keeps_every_detail(self) -> None:
        details = build(True)["error"]["details"]

        self.assertEqual(50, len(details["stale_request_artifacts"]["candidates"]))
        self.assertIn("state_groups", details)


if __name__ == "__main__":
    unittest.main()
