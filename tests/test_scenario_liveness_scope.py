import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_summaries

TERMINAL = {"passed", "failed"}
FOCUS_REMEDY = "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling"


def _throttled_playmode_step(step_id: str, status: str = "passed", **extra) -> dict:
    return {
        "stepId": step_id,
        "kind": "ui_click",
        "status": status,
        "playmode_state": "playing",
        "playmode_loop_liveness": "throttled",
        "editor_application_focused": False,
        "playmode_liveness_warning": "playmode_throttled_editor_unfocused",
        "playmode_liveness_remediation": FOCUS_REMEDY,
        "result_trust_class": "playmode_throttled",
        **extra,
    }


def _edit_mode(step: dict) -> dict:
    return {
        **step,
        "playmode_state": "edit",
        "playmode_loop_liveness": "not_playing",
        "editor_application_focused": False,
        "result_trust_class": "editor_truth_confirmed",
    }


class ScenarioLivenessScopeTests(unittest.TestCase):
    def test_throttled_playmode_step_before_an_edit_mode_refresh_keeps_the_unsettled_label(self) -> None:
        payload = {
            "status": "failed",
            "terminal": True,
            "steps": [
                _throttled_playmode_step("open_reward"),
                _edit_mode({"stepId": "exit_play", "kind": "playmode_set", "status": "passed"}),
                _edit_mode(
                    {
                        "stepId": "apply_config",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "payload_json": json.dumps({"outcome": "config_applied"}),
                    }
                ),
                _edit_mode(
                    {
                        "stepId": "refresh",
                        "kind": "project_refresh",
                        "status": "failed",
                        "error_code": "project_refresh_timeout",
                    }
                ),
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("applied_mutation_settle_timeout", verdict["failure_class"])
        self.assertEqual("mutation_applied_unsettled", verdict["trust_class"])
        self.assertNotEqual(FOCUS_REMEDY, verdict["recommended_next_action"])
        liveness = verdict["playmode_liveness_summary"]
        self.assertEqual(["open_reward"], liveness["throttled_step_ids"])
        self.assertEqual("refresh", liveness["deciding_step_id"])
        self.assertFalse(liveness["applies_to_verdict"])

    def test_failed_step_that_itself_ran_throttled_still_gets_the_focus_remedy(self) -> None:
        payload = {
            "status": "failed",
            "terminal": True,
            "steps": [
                _throttled_playmode_step(
                    "open_banner",
                    status="failed",
                    error_code="ui_interaction_no_state_change",
                ),
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("playmode_throttled", verdict["trust_class"])
        self.assertEqual(FOCUS_REMEDY, verdict["recommended_next_action"])
        self.assertEqual("open_banner", verdict["playmode_liveness_summary"]["deciding_step_id"])
        self.assertTrue(verdict["playmode_liveness_summary"]["applies_to_verdict"])

    def test_passed_run_keeps_the_run_level_downgrade(self) -> None:
        payload = {
            "status": "passed",
            "terminal": True,
            "steps": [
                _throttled_playmode_step("capture"),
                _edit_mode({"stepId": "status", "kind": "status", "status": "passed"}),
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual("playmode_throttled", verdict["trust_class"])
        self.assertTrue(verdict["playmode_liveness_summary"]["applies_to_verdict"])
        self.assertEqual("", verdict["playmode_liveness_summary"]["deciding_step_id"])

    def test_failed_edit_mode_step_after_throttled_playmode_keeps_authoritative_trust(self) -> None:
        payload = {
            "status": "failed",
            "terminal": True,
            "steps": [
                _throttled_playmode_step("open_reward"),
                _edit_mode(
                    {
                        "stepId": "assert_scene",
                        "kind": "scene_assert",
                        "status": "failed",
                        "error_code": "missing_root",
                        "error_message": "assertion failed: root missing",
                    }
                ),
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, TERMINAL)

        self.assertEqual("product_assertion", verdict["failure_class"])
        self.assertEqual("authoritative", verdict["trust_class"])


if __name__ == "__main__":
    unittest.main()
