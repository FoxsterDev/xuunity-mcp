import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_core import ToolInvocationError
from server_project_actions import (
    build_project_action_scenario,
    normalize_project_action_record,
    normalize_project_action_step,
    validate_project_action_payload,
)


def _record(payload_schema, **extra):
    raw = {"hookName": "example.profile_summary", "payload": payload_schema, **extra}
    return normalize_project_action_record("perf.profile_summary", raw, "")


PROFILE_SCHEMA = {
    "raw_path": "required_string",
    "spike_ms": "float_default_50",
    "max_spikes": "int_default_30",
    "tree_frames": "int_array",
    "tree_min_ms": "float_default_20",
    "max_depth": "int_default_40",
    "deep": "bool_default_false",
    "mode": "enum[summary, tree]",
    "folders": "list[asset_folder]",
    "free_form": "project-specific build configuration resource path",
}


class ProjectActionPayloadContractTests(unittest.TestCase):
    def test_a_well_typed_payload_is_ok(self) -> None:
        result = validate_project_action_payload(
            _record(PROFILE_SCHEMA),
            {
                "raw_path": "cap.raw",
                "spike_ms": 33,
                "tree_frames": [1, 2, 36],
                "tree_min_ms": 2.5,
                "deep": True,
                "mode": "tree",
                "folders": ["Assets/UI"],
                "free_form": 7,
                "action": "perf.profile_summary",
            },
        )
        self.assertEqual("ok", result["status"])
        self.assertEqual([], result["undeclared_payload_keys"])
        self.assertEqual([], result["payload_type_mismatches"])

    def test_the_string_tree_frames_regression_is_reported(self) -> None:
        result = validate_project_action_payload(
            _record(PROFILE_SCHEMA),
            {"raw_path": "cap.raw", "tree_frames": "1,2,36", "max_depth": 12.5, "deep": "true", "mode": "leaf"},
        )
        self.assertEqual("warning", result["status"])
        mismatched = {item["key"]: item for item in result["payload_type_mismatches"]}
        self.assertEqual({"tree_frames", "max_depth", "deep", "mode"}, set(mismatched))
        self.assertEqual("string", mismatched["tree_frames"]["actual_type"])
        self.assertEqual("int_array", mismatched["tree_frames"]["declared"])

    def test_bool_is_not_accepted_as_a_number(self) -> None:
        result = validate_project_action_payload(_record(PROFILE_SCHEMA), {"raw_path": "x", "max_spikes": True})
        self.assertEqual(["max_spikes"], [item["key"] for item in result["payload_type_mismatches"]])

    def test_undeclared_and_missing_required_keys_are_reported(self) -> None:
        result = validate_project_action_payload(_record(PROFILE_SCHEMA), {"tree_frame": [1]})
        self.assertEqual(["tree_frame"], result["undeclared_payload_keys"])
        self.assertEqual(["raw_path"], result["missing_required_payload_keys"])

    def test_strict_mode_refuses_before_dispatch_with_every_problem(self) -> None:
        with self.assertRaises(ToolInvocationError) as raised:
            build_project_action_scenario(
                action_record=_record(PROFILE_SCHEMA),
                action_payload={"raw_path": "cap.raw", "tree_frames": "1,2", "unknown": 1},
                strict_payload=True,
            )
        error = raised.exception
        self.assertEqual("project_action_payload_contract_violation", error.code)
        self.assertIn("tree_frames", error.message)
        self.assertIn("unknown", error.message)
        self.assertEqual("refused", error.details["status"])

    def test_catalog_entry_can_opt_into_strict_mode(self) -> None:
        with self.assertRaises(ToolInvocationError):
            build_project_action_scenario(
                action_record=_record(PROFILE_SCHEMA, strictPayload=True),
                action_payload={"raw_path": "cap.raw", "unknown": 1},
            )

    def test_warning_mode_still_dispatches_the_payload_unchanged(self) -> None:
        scenario = build_project_action_scenario(
            action_record=_record(PROFILE_SCHEMA),
            action_payload={"raw_path": "cap.raw", "tree_frames": "1,2"},
        )
        hook_step = next(step for step in scenario["steps"] if step.get("kind") == "project_defined_hook")
        hook_payload = json.loads(hook_step["hookPayloadJson"])
        self.assertEqual("1,2", hook_payload["tree_frames"])

    def test_scenario_steps_honour_strict_payload_and_strip_the_flag(self) -> None:
        catalog = {
            "actions_by_id": {"perf.profile_summary": _record(PROFILE_SCHEMA)},
            "alias_map": {},
            "alias_conflicts": {},
            "actions": [],
            "catalog_path": "",
        }
        step = {
            "kind": "project_action",
            "actionId": "perf.profile_summary",
            "payload": {"raw_path": "cap.raw", "tree_frames": "1"},
            "strictPayload": True,
        }
        with self.assertRaises(ToolInvocationError):
            normalize_project_action_step(catalog=catalog, step=step, step_group="steps", step_index=0)

        step["strictPayload"] = False
        normalized = normalize_project_action_step(catalog=catalog, step=step, step_group="steps", step_index=0)
        self.assertNotIn("strictPayload", normalized[0])


if __name__ == "__main__":
    unittest.main()
