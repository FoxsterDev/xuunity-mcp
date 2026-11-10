import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator as orchestrator
import server_batch_reporting as reporting
from server_core import ToolInvocationError


def _truncate(value, limit):
    return str(value)[:limit]


COMPILE_RESULT = {"status": "passed", "error_count": 0, "compiled_assembly_count": 30, "rebuilt_assembly_count": 4,
                  "cached_assembly_count": 26, "rebuild_evidence_status": "measured", "warning_count": 1}


class LaneIndependentShapeTests(unittest.TestCase):
    def test_gui_and_batch_compile_payloads_yield_the_same_compile_section(self) -> None:
        gui = reporting.summarize_batch_result_payload(
            {"operation": "unity.compile.player_scripts", "result": dict(COMPILE_RESULT)}, truncate_text=_truncate
        )
        batch = reporting.summarize_batch_result_payload(
            {"operation": "compile-player-scripts", "compile": {"result": dict(COMPILE_RESULT)}}, truncate_text=_truncate
        )
        self.assertEqual(batch["compile"], gui["compile"])
        self.assertEqual("passed", reporting.build_batch_terminal_record(gui)["compile_status"])

    def test_gui_matrix_payload_yields_the_matrix_section(self) -> None:
        gui = reporting.summarize_batch_result_payload(
            {"operation": "unity.compile.matrix", "status": "failed", "total": 3, "failed": 1}, truncate_text=_truncate
        )
        self.assertEqual("failed", gui["matrix"]["status"])
        self.assertEqual("failed", reporting.build_batch_terminal_record(gui)["compile_status"])


class FailurePathTerminalRecordTests(unittest.TestCase):
    def test_busy_timeout_record_carries_the_code_and_retry_hint(self) -> None:
        exc = ToolInvocationError(
            "editor_idle_timeout",
            "stale heartbeat during import",
            {"retry_recommended": True, "retry_reason": "heartbeat_stale_while_editor_busy_with_asset_import",
             "classification": "editor_busy_heartbeat_stale"},
        )
        summary = reporting.build_batch_prepare_failure_summary(
            action="batch_compile", result_path=Path("/r/x.json"), log_path=Path("/r/x.log"), exc=exc, truncate_text=_truncate
        )
        record = reporting.build_batch_terminal_record(summary)
        self.assertEqual("editor_idle_timeout", record["error_code"])
        self.assertTrue(record["retry_recommended"])
        self.assertEqual("heartbeat_stale_while_editor_busy_with_asset_import", record["retry_reason"])

    def test_a_failed_gui_fallback_run_ends_with_exactly_one_terminal_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"action": "batch_compile", "project_root": str(root), "build_target": "Android"}

            def select_gui(**kwargs):
                kwargs["payload"]["effective_execution_lane"] = "gui"
                return "gui", {}

            def fail_gui(**kwargs):
                kwargs["payload"]["effective_execution_lane"] = "gui"
                raise ToolInvocationError(
                    "editor_idle_timeout",
                    "stale",
                    {"retry_recommended": True, "retry_reason": "heartbeat_stale_while_editor_busy_with_updating"},
                )

            with (
                mock.patch.object(orchestrator, "batch_lane_preflight_blocker", side_effect=select_gui),
                mock.patch.object(orchestrator, "run_gui_fallback_operation", side_effect=fail_gui),
            ):
                with self.assertRaises(ToolInvocationError) as raised:
                    orchestrator.run_batch_operation(
                        project_root=root,
                        unity_app=root / "Unity.app",
                        command=["unity"],
                        payload=payload,
                        log_path=root / "logs" / "unity.log",
                        result_path=root / "logs" / "result.json",
                        dry_run=False,
                        progress_stdout=False,
                        gui_operation="unity.compile.player_scripts",
                    )
            records = [
                json.loads(line)
                for line in Path(payload["progress_file"]).read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("event") == "batch_terminal_record"
            ]
        self.assertEqual(1, len(records))
        self.assertEqual("gui", records[0]["lane"])
        self.assertEqual("editor_idle_timeout", records[0]["error_code"])
        self.assertTrue(records[0]["retry_recommended"])
        summary = raised.exception.details["batch_failure_summary"]
        self.assertEqual("gui_fallback", summary["phase"])
        self.assertEqual("gui_operation_failed", summary["transport_outcome"])


if __name__ == "__main__":
    unittest.main()
