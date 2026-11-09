import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_specs
import server_summaries
from server_specs_scenario import SCENARIO_OPTIONAL_STEP_KINDS, SCENARIO_STEP_SCHEMA

TERMINAL = {"passed", "failed"}


def _click_payload(interaction_id: str, refusal_code: str = "", delivered: bool = False) -> str:
    return json.dumps(
        {
            "ui_interaction": {
                "interaction_id": interaction_id,
                "delivered": delivered,
                "refusal_code": refusal_code,
            }
        }
    )


def _optional_absent_click(step_id: str, reason: str) -> dict:
    return {
        "stepId": step_id,
        "kind": "ui_click",
        "status": "skipped_optional_absent",
        "outcome": "skipped_optional_absent",
        "optional": True,
        "optional_absent_reason": reason,
        "payload_json": _click_payload(step_id, refusal_code=reason),
    }


class ScenarioOptionalStepTests(unittest.TestCase):
    def test_schema_declares_optional_and_status_vocabulary(self) -> None:
        self.assertEqual("boolean", SCENARIO_STEP_SCHEMA["properties"]["optional"]["type"])
        self.assertIs(False, SCENARIO_STEP_SCHEMA["properties"]["optional"]["default"])
        self.assertEqual(("ui_click", "ui_exists", "ui_get_text"), SCENARIO_OPTIONAL_STEP_KINDS)
        self.assertIn("skipped_optional_absent", server_specs.SCENARIO_STEP_STATUSES)

    def test_optional_absent_click_with_passing_required_steps_is_passed(self) -> None:
        payload = {
            "status": "passed",
            "terminal": True,
            "total_steps": 4,
            "passed_steps": 2,
            "failed_steps": 0,
            "skipped_steps": 1,
            "steps": [
                {"stepId": "open", "kind": "ui_click", "status": "passed", "outcome": "interaction_delivered"},
                _optional_absent_click("close_offer", "ui_node_not_found"),
                {"stepId": "after_close", "kind": "ui_exists", "status": "skipped",
                 "outcome": "dependency_not_passed:close_offer"},
                {"stepId": "spin", "kind": "ui_click", "status": "passed", "outcome": "interaction_delivered"},
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("passed", verdict["verdict"])
        self.assertTrue(verdict["succeeded"])
        self.assertEqual("authoritative", verdict["trust_class"])
        self.assertEqual(
            {"total": 3, "passed": 2, "failed": 0, "skipped": 1, "pending": 0},
            verdict["required_steps"],
        )
        self.assertEqual(1, verdict["optional_steps"]["total"])
        self.assertEqual(1, verdict["optional_steps"]["skipped_optional_absent"])
        self.assertEqual(1, verdict["skipped_optional_step_count"])
        self.assertEqual(
            [{"step_id": "close_offer", "kind": "ui_click", "reason": "ui_node_not_found",
              "interaction_id": "close_offer"}],
            verdict["skipped_optional_steps"],
        )

    def test_optional_click_delivered_without_change_is_failed(self) -> None:
        payload = {
            "status": "failed",
            "terminal": True,
            "steps": [
                {
                    "stepId": "close_rating",
                    "kind": "ui_click",
                    "status": "failed",
                    "optional": True,
                    "error_code": "ui_interaction_no_state_change",
                    "error_message": "Interaction 'close_rating' was delivered but the UI tree did not change.",
                    "payload_json": _click_payload("close_rating", delivered=True),
                },
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("failed", verdict["scenario_status"])
        self.assertFalse(verdict["succeeded"])
        self.assertNotEqual("passed", verdict["verdict"])
        self.assertEqual("close_rating", verdict["first_failure"]["step_id"])
        self.assertEqual(1, verdict["optional_steps"]["failed"])
        self.assertEqual(0, verdict["skipped_optional_step_count"])
        self.assertEqual([], verdict["skipped_optional_steps"])

    def test_step_summary_carries_optional_flag_and_reason(self) -> None:
        summary = server_summaries.summarize_scenario_step(
            _optional_absent_click("accept_dialog", "ui_target_occluded")
        )
        self.assertTrue(summary["optional"])
        self.assertEqual("ui_target_occluded", summary["optional_absent_reason"])
        self.assertEqual("skipped_optional_absent", summary["status"])
        self.assertNotIn("error_code", summary)

    def test_cleanup_with_optional_absent_dismissal_still_passes(self) -> None:
        steps = [
            {"stepId": "body", "kind": "status", "status": "passed"},
            _optional_absent_click("close_popup", "ui_target_not_visible"),
            {"stepId": "exit", "kind": "playmode_set", "status": "passed"},
        ]
        summary = server_summaries.build_scenario_cleanup_summary(steps, 1)
        self.assertEqual("passed", summary["cleanup_result"])
        self.assertEqual(1, summary["cleanup_skipped_optional_count"])


if __name__ == "__main__":
    unittest.main()
