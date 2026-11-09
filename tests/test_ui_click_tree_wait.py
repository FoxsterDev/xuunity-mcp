import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_specs
import server_summaries

EDITOR = ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"


class UiClickTreeWaitTests(unittest.TestCase):
    def test_tool_and_step_schemas_bound_the_window(self) -> None:
        for schema in (
            server_specs.TOOLS["unity_ui_click"]["inputSchema"]["properties"]["waitForTreeChangeMs"],
            server_specs.SCENARIO_STEP_SCHEMA["properties"]["waitForTreeChangeMs"],
        ):
            self.assertEqual("integer", schema["type"])
            self.assertEqual(0, schema["minimum"])
            self.assertEqual(10000, schema["maximum"])
            self.assertEqual(0, schema["default"])
        self.assertGreater(
            server_specs.TOOLS["unity_ui_click"]["inputSchema"]["properties"]["timeoutMs"]["default"],
            10000,
        )

    def test_step_summary_reports_the_wait_outcome(self) -> None:
        step = {
            "stepId": "open_banner",
            "kind": "ui_click",
            "status": "passed",
            "outcome": "interaction_delivered",
            "payload_json": json.dumps(
                {
                    "expect_state_change": True,
                    "click_status": "effective",
                    "ui_interaction": {
                        "interaction_id": "open_banner",
                        "delivered": True,
                        "state_changed": True,
                        "wait_for_tree_change_ms": 1500,
                        "tree_change_wait_status": "changed_after_wait",
                        "tree_change_observed_after_ms": 212.5,
                        "tree_change_observed_after_frames": 6,
                    },
                }
            ),
        }

        summary = server_summaries.summarize_scenario_step(step)["ui_interaction_summary"]

        self.assertEqual(1500, summary["wait_for_tree_change_ms"])
        self.assertEqual("changed_after_wait", summary["tree_change_wait_status"])
        self.assertEqual(212.5, summary["tree_change_observed_after_ms"])
        self.assertEqual(6, summary["tree_change_observed_after_frames"])

    def test_step_summary_without_a_window_stays_unchanged(self) -> None:
        step = {
            "stepId": "close",
            "kind": "ui_click",
            "status": "passed",
            "payload_json": json.dumps({"ui_interaction": {"delivered": True, "state_changed": True}}),
        }
        summary = server_summaries.summarize_scenario_step(step)["ui_interaction_summary"]
        self.assertNotIn("tree_change_wait_status", summary)

    def test_the_watch_runs_from_the_update_loop_without_sleeping(self) -> None:
        bootstrap = (EDITOR / "Bridge" / "XUUnityLightMcpBridgeBootstrap.cs").read_text(encoding="utf-8")
        watch = (EDITOR / "Helpers" / "XUUnityLightMcpUiClickTreeWatch.cs").read_text(encoding="utf-8")
        operation = (EDITOR / "Ugui" / "XUUnityLightMcpUiClickOperation.cs").read_text(encoding="utf-8")

        self.assertIn("XUUnityLightMcpUiClickTreeWatch.Tick();", bootstrap)
        self.assertNotIn("Thread.Sleep", watch)
        self.assertNotIn("delayCall", watch)
        self.assertIn("SessionState", watch)
        self.assertIn("XUUnityLightMcpUiClickTreeWatch.Arm(request, args, payload);\n                    return null;", operation)
        self.assertIn('"ui_click_wait_in_progress"', operation)


if __name__ == "__main__":
    unittest.main()
