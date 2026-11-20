import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_core
import server_project_actions
import server_specs
import server_ui_selector
from server_specs_scenario import SCENARIO_STEP_SCHEMA

UI_SELECTOR_TOOLS = ("unity_ui_click", "unity_ui_query", "unity_ui_exists", "unity_ui_get_text", "unity_ui_get_bounds")


class UiSelectorSchemaTests(unittest.TestCase):
    def test_every_selector_tool_declares_the_closed_key_set(self) -> None:
        declared = [
            name for name, tool in server_specs.TOOLS.items()
            if "selector" in tool.get("inputSchema", {}).get("properties", {})
        ]
        self.assertEqual(sorted(UI_SELECTOR_TOOLS), sorted(declared))
        for name in UI_SELECTOR_TOOLS:
            schema = server_specs.TOOLS[name]["inputSchema"]["properties"]["selector"]
            self.assertIs(False, schema["additionalProperties"])
            self.assertEqual(list(server_ui_selector.UI_SELECTOR_KEYS), list(schema["properties"]))
        step_selector = SCENARIO_STEP_SCHEMA["properties"]["selector"]
        self.assertIs(False, step_selector["additionalProperties"])
        self.assertEqual(list(server_ui_selector.UI_SELECTOR_KEYS), list(step_selector["properties"]))

    def test_closest_keys(self) -> None:
        self.assertEqual(["pathContains"], server_ui_selector.closest_ui_selector_keys("pathcontains"))
        self.assertIn("name", server_ui_selector.closest_ui_selector_keys("nameContains"))
        self.assertIn("textContains", server_ui_selector.closest_ui_selector_keys("text"))
        self.assertEqual([], server_ui_selector.closest_ui_selector_keys("zzz"))


class UiSelectorToolRefusalTests(unittest.TestCase):
    def _call(self, name: str, arguments: dict):
        with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=Path("/tmp/p")), \
                mock.patch.object(server_batch_orchestrator, "invoke_bridge") as invoke_bridge:
            invoke_bridge.return_value = {"status": "ok", "payload_type": "x", "payload_json": "{}"}
            result = server_batch_orchestrator.call_tool(name, arguments)
        return result, invoke_bridge

    def test_unknown_key_is_refused_before_the_bridge(self) -> None:
        for name in UI_SELECTOR_TOOLS:
            with self.subTest(tool=name):
                arguments = {"projectRoot": "/tmp/p", "selector": {"nameContains": "Shop"}}
                if name == "unity_ui_click":
                    arguments["approve"] = True
                result, invoke_bridge = self._call(name, arguments)
                invoke_bridge.assert_not_called()
                self.assertTrue(result["isError"])
                text = result["content"][0]["text"]
                self.assertIn("unknown_selector_key", text)
                self.assertIn("nameContains", text)
                self.assertIn("pathContains", text)

    def test_valid_selector_reaches_the_bridge(self) -> None:
        result, invoke_bridge = self._call(
            "unity_ui_query",
            {"projectRoot": "/tmp/p", "selector": {"pathContains": "Shop", "requireVisible": True}},
        )
        invoke_bridge.assert_called_once()
        self.assertFalse(result["isError"])


class ScenarioSelectorRefusalTests(unittest.TestCase):
    def test_scenario_steps_and_cleanup_steps_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for group in ("steps", "cleanupSteps"):
                with self.subTest(group=group):
                    scenario = {
                        "name": "s",
                        "steps": [{"stepId": "a", "kind": "ui_exists", "selector": {"name": "Ok"}}],
                        "cleanupSteps": [],
                    }
                    scenario[group] = list(scenario[group]) + [
                        {"stepId": "close", "kind": "ui_click", "selector": {"Name": "Close", "textContain": "x"}}
                    ]
                    with self.assertRaises(server_core.ToolInvocationError) as caught:
                        server_project_actions.normalize_project_action_scenario(project_root=root, scenario=scenario)
                    self.assertEqual("unknown_selector_key", caught.exception.code)
                    self.assertEqual(["Name", "textContain"], caught.exception.details["unknown_selector_keys"])
                    self.assertEqual(["name"], caught.exception.details["closest_valid_keys"]["Name"])
                    self.assertIn(group, caught.exception.message)
                    self.assertIn("'close'", caught.exception.message)
            valid = {"name": "s", "steps": [{"stepId": "a", "kind": "ui_exists", "selector": {"name": "Ok"}}]}
            self.assertEqual(
                valid, server_project_actions.normalize_project_action_scenario(project_root=root, scenario=valid)
            )

    def test_ui_click_step_without_interaction_id_takes_its_step_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scenario = {
                "name": "s",
                "steps": [
                    {"stepId": "open_shop", "kind": "ui_click", "selector": {"name": "Shop"}, "approve": True},
                    {"stepId": "named", "kind": "ui_click", "interactionId": "buy", "selector": {"name": "Buy"}},
                    {"stepId": "check", "kind": "ui_exists", "selector": {"name": "Shop"}},
                    {"kind": "ui_click", "selector": {"name": "NoId"}},
                ],
                "cleanupSteps": [{"stepId": "close", "kind": "ui_click", "interactionId": " ", "selector": {"name": "X"}}],
            }
            original = json.loads(json.dumps(scenario))
            normalized = server_project_actions.normalize_project_action_scenario(
                project_root=Path(temp), scenario=scenario
            )
        self.assertEqual(original, scenario)
        self.assertEqual("open_shop", normalized["steps"][0]["interactionId"])
        self.assertEqual("buy", normalized["steps"][1]["interactionId"])
        self.assertNotIn("interactionId", normalized["steps"][2])
        self.assertNotIn("interactionId", normalized["steps"][3])
        self.assertEqual("close", normalized["cleanupSteps"][0]["interactionId"])
        self.assertIn("Defaults to stepId", SCENARIO_STEP_SCHEMA["properties"]["interactionId"]["description"])

    def test_mcp_scenario_tool_returns_the_typed_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            scenario = {"name": "s", "steps": [{"stepId": "a", "kind": "ui_click", "selector": {"nameContains": "x"}}]}
            with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=root), \
                    mock.patch.object(server_batch_orchestrator, "invoke_bridge") as invoke_bridge:
                result = server_batch_orchestrator.call_tool(
                    "unity_scenario_run", {"projectRoot": str(root), "scenario": scenario}
                )
            invoke_bridge.assert_not_called()
            self.assertTrue(result["isError"])
            self.assertIn("unknown_selector_key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
