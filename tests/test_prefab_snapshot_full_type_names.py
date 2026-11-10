"""unity_prefab_snapshot forwards includeFullPayload so Unity adds full component type names (RG-48)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_mcp_tools
from server_specs import TOOLS as TOOL_SPECS


class PrefabSnapshotFullTypeNamesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.bridge_calls: list[tuple[str, dict]] = []

    def tearDown(self) -> None:
        self._temp.cleanup()

    def call(self, name: str, arguments: dict) -> dict:
        def invoke_bridge(project_root: str, operation: str, bridge_args: dict, timeout_ms: int) -> dict:
            self.bridge_calls.append((operation, bridge_args))
            return {"status": "ok", "payload_type": operation, "payload_json": "{}"}

        return server_mcp_tools.call_tool(
            name,
            {"projectRoot": str(self.root), **arguments},
            tools=TOOL_SPECS,
            special_tool_handlers={},
            tool_invocation_error_type=RuntimeError,
            ensure_project_root=lambda value: Path(value),
            resolve_operation_timeout_ms=lambda root, operation, requested, default: default,
            invoke_bridge=invoke_bridge,
            build_tool_error_payload=lambda exc: {"error": str(exc)},
            bridge_response_to_tool_result=lambda response, include_full_payload=False: {"isError": False},
        )

    def test_full_payload_reaches_the_bridge_for_the_prefab_snapshot(self) -> None:
        self.call("unity_prefab_snapshot", {"prefabPath": "Assets/UI/Popup.prefab", "includeFullPayload": True})

        operation, bridge_args = self.bridge_calls[-1]
        self.assertEqual("unity.prefab.snapshot", operation)
        self.assertIs(True, bridge_args["includeFullPayload"])

    def test_the_default_snapshot_request_is_unchanged(self) -> None:
        self.call("unity_prefab_snapshot", {"prefabPath": "Assets/UI/Popup.prefab"})
        self.call("unity_prefab_snapshot", {"prefabPath": "Assets/UI/Popup.prefab", "includeFullPayload": False})

        for _, bridge_args in self.bridge_calls:
            self.assertNotIn("includeFullPayload", bridge_args)

    def test_other_tools_keep_includefullpayload_host_side(self) -> None:
        forwarding = sorted(name for name, spec in TOOL_SPECS.items() if spec.get("forwardIncludeFullPayload"))
        self.assertEqual(["unity_prefab_snapshot"], forwarding)

        self.call("unity_ui_query", {"selector": {"name": "Button"}, "includeFullPayload": True})
        self.assertNotIn("includeFullPayload", self.bridge_calls[-1][1])

    def test_the_schema_declares_the_flag(self) -> None:
        properties = TOOL_SPECS["unity_prefab_snapshot"]["inputSchema"]["properties"]
        self.assertEqual("boolean", properties["includeFullPayload"]["type"])
        self.assertIn("component_type_full_names", properties["includeFullPayload"]["description"])


if __name__ == "__main__":
    unittest.main()
