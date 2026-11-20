import json
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_bridge_payloads
import server_specs


def _response(project_root: Path, platform: str = "android") -> dict:
    payload = {
        "project_root": str(project_root),
        "platform": platform,
        "outcome": "menu_item_executed",
        "resolver_output_freshness": "unproven",
        "recommended_next_action": "verify_resolver_output_freshness_and_generated_diff",
    }
    return {"status": "ok", "payload_type": "unity.edm4u.resolve", "payload_json": json.dumps(payload)}


class Edm4uResolveNextToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _result(self, **kwargs) -> dict:
        result = server_batch_orchestrator.bridge_response_to_tool_result(_response(self.root, **kwargs))
        return json.loads(result["content"][0]["text"])

    def test_android_result_names_the_typed_lanes_with_present_files(self) -> None:
        present = [
            "Assets/Plugins/Android/mainTemplate.gradle",
            "ProjectSettings/AndroidResolverDependencies.xml",
            "Assets/Plugins/Android/gradleTemplate.properties",
        ]
        for relative in present:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n", encoding="utf-8")

        payload = self._result()

        self.assertEqual("unity_sdk_generated_diff_guard", payload["recommended_next_tool"])
        self.assertEqual("present_on_disk", payload["next_tools_tracked_paths_basis"])
        guard, resolve = payload["next_tools"]
        self.assertEqual("unity_sdk_generated_diff_guard", guard["tool"])
        self.assertEqual({"projectRoot": str(self.root), "trackedPaths": present}, guard["arguments"])
        self.assertEqual("unity_sdk_android_resolve", resolve["tool"])
        self.assertEqual(present, resolve["arguments"]["trackedGeneratedPaths"])
        for entry in payload["next_tools"]:
            self.assertIn(entry["tool"], server_specs.TOOLS)
            self.assertTrue(set(entry["arguments"]) <= set(server_specs.TOOLS[entry["tool"]]["inputSchema"]["properties"]))

    def test_missing_files_fall_back_to_the_conventional_paths(self) -> None:
        payload = self._result()

        self.assertEqual("conventional_defaults", payload["next_tools_tracked_paths_basis"])
        self.assertEqual(
            list(server_bridge_payloads.EDM4U_TRACKED_OUTPUT_CANDIDATES[:2]),
            payload["next_tools"][0]["arguments"]["trackedPaths"],
        )

    def test_version_handler_and_other_operations_get_no_next_tools(self) -> None:
        self.assertNotIn("next_tools", self._result(platform="version_handler"))
        other = server_batch_orchestrator.bridge_response_to_tool_result(
            {"status": "ok", "payload_type": "unity.scene.snapshot", "payload_json": json.dumps({"platform": "android"})}
        )
        self.assertNotIn("next_tools", json.loads(other["content"][0]["text"]))

    def test_tool_description_points_at_the_typed_lane(self) -> None:
        description = server_specs.TOOLS["unity_edm4u_resolve"]["description"]
        self.assertIn("unity_sdk_android_resolve", description)
        self.assertIn("unity_sdk_generated_diff_guard", description)
        self.assertIn("next_tools", description)


if __name__ == "__main__":
    unittest.main()
