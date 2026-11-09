import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_summaries

TERMINAL = {"passed", "failed"}
COMPACT_PASSING_BYTE_BUDGET = 3000


def _click(index: int, status: str = "passed") -> dict:
    step = {
        "stepId": f"step_{index:02d}",
        "kind": "ui_click",
        "status": status,
        "outcome": "interaction_delivered" if status == "passed" else "",
        "duration_seconds": 0.123,
        "playmode_state": "playing",
        "playmode_loop_liveness": "advancing",
        "playmode_liveness_warning": "",
        "playmode_liveness_remediation": "",
        "result_trust_class": "playmode_advancing_confirmed",
        "editor_application_focused": False,
        "payload_json": json.dumps(
            {
                "expect_state_change": True,
                "click_status": "effective",
                "ui_interaction": {
                    "interaction_id": f"button_{index}",
                    "delivered": True,
                    "state_changed": status == "passed",
                    "refusal_code": "",
                    "target_path": f"Canvas/Root/Popup/Buttons/Button_{index}",
                },
            }
        ),
    }
    if status == "failed":
        step["error_code"] = "ui_interaction_no_state_change"
        step["error_message"] = "Interaction was delivered but the UI tree did not change."
    return step


def _payload(steps: list, status: str, **extra) -> dict:
    return {
        "status": status,
        "terminal": status in TERMINAL,
        "run_id": "run-compact",
        "scenario_name": "DevFlow",
        "project_root": "/projects/Example",
        "result_path": "/projects/Example/Library/XUUnityLightMcp/scenarios/results/run-compact.json",
        "total_steps": len(steps),
        "steps": steps,
        **extra,
    }


class ScenarioCompactEnvelopeTests(unittest.TestCase):
    def test_twenty_step_passing_run_stays_under_the_byte_budget(self) -> None:
        verdict = server_summaries.build_scenario_decision_verdict(
            _payload([_click(index) for index in range(20)], "passed"), TERMINAL
        )

        size = len(json.dumps(verdict, ensure_ascii=True))
        self.assertLess(size, COMPACT_PASSING_BYTE_BUDGET, size)
        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual([], verdict["steps"])
        self.assertEqual("decision_steps", verdict["steps_payload_mode"])
        self.assertEqual(20, verdict["raw_step_count"])
        self.assertEqual(20, verdict["omitted_step_count"])
        self.assertEqual(20, verdict["required_steps"]["passed"])
        self.assertIn("passed_step_list", verdict["full_payload_required_for"])
        self.assertEqual("unity_scenario_result", verdict["full_payload_tool"])

    def test_failed_run_lists_only_failed_and_skipped_optional_steps(self) -> None:
        steps = [_click(index) for index in range(20)]
        steps[5] = {
            **steps[5],
            "status": "skipped_optional_absent",
            "outcome": "skipped_optional_absent",
            "optional": True,
            "optional_absent_reason": "ui_node_not_found",
        }
        steps[12] = _click(12, "failed")

        verdict = server_summaries.build_scenario_decision_verdict(_payload(steps, "failed"), TERMINAL)

        self.assertEqual(["step_05", "step_12"], [step["step_id"] for step in verdict["steps"]])
        self.assertEqual(2, verdict["compact_step_count"])
        self.assertEqual(18, verdict["omitted_step_count"])
        self.assertEqual("step_12", verdict["first_failure"]["step_id"])
        self.assertEqual(["step_05"], [step["step_id"] for step in verdict["skipped_optional_steps"]])

    def test_unfinished_run_keeps_its_active_step(self) -> None:
        steps = [_click(0), {"stepId": "wait_spin", "kind": "project_defined_hook_poll_until", "status": "running"}]
        verdict = server_summaries.build_scenario_decision_verdict(
            _payload(steps, "running", current_step_index=1), TERMINAL
        )
        self.assertEqual(["wait_spin"], [step["step_id"] for step in verdict["steps"]])

    def test_cleanup_steps_are_trimmed_to_decision_steps(self) -> None:
        steps = [
            _click(0, "failed"),
            {"stepId": "exit_playmode", "kind": "playmode_set", "status": "passed"},
            {"stepId": "restore_profile", "kind": "project_defined_hook", "status": "failed", "error_code": "hook_failed"},
        ]
        verdict = server_summaries.build_scenario_decision_verdict(
            _payload(steps, "failed", cleanup_start_index=1), TERMINAL
        )
        cleanup = verdict["cleanup_summary"]
        self.assertEqual(2, cleanup["cleanup_step_count"])
        self.assertEqual(1, cleanup["cleanup_passed_count"])
        self.assertEqual(["restore_profile"], [step["step_id"] for step in cleanup["cleanup_steps"]])

    def test_result_summary_keeps_the_full_compact_step_list(self) -> None:
        summary = server_summaries.build_scenario_result_summary(
            _payload([_click(index) for index in range(3)], "passed"), TERMINAL
        )
        self.assertEqual(3, len(summary["steps"]))


if __name__ == "__main__":
    unittest.main()
