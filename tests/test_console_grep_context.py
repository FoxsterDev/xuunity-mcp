"""console_grep context lines (RG-50): bounded per-match blocks inside the byte budget."""

from __future__ import annotations

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
import server_health
from server_batch_orchestrator import JsonRpcError


LOG_LINES = [
    "Loading scene",
    "[LogAttributes] SpinResult reward=10",
    "Props: {\"wheel\": 3}",
    "Props: {\"multiplier\": 2}",
    "Unrelated line",
    "[LogAttributes] SpinResult reward=20",
    "Props: {\"wheel\": 5}",
]


class ConsoleGrepContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"
        self.log.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def grep(self, **kwargs) -> dict:
        return server_health.grep_editor_log_payload(self.root, self.log, pattern="SpinResult", **kwargs)

    def test_after_lines_return_the_structured_lines_that_follow_each_match(self) -> None:
        payload = self.grep(after_lines=2)

        self.assertEqual(2, payload["match_count"])
        first, second = payload["items"]
        self.assertEqual(['Props: {"wheel": 3}', 'Props: {"multiplier": 2}'], first["context_after"])
        self.assertEqual([], first["context_before"])
        self.assertEqual(['Props: {"wheel": 5}'], second["context_after"])
        self.assertEqual({"before": 0, "after": 2}, payload["context_lines"])
        self.assertFalse(payload["byte_budget_truncated"])

    def test_before_lines_and_first_line_numbering(self) -> None:
        payload = self.grep(before_lines=2, limit=1)

        item = payload["items"][0]
        self.assertEqual(6, item["line"])
        self.assertEqual(["Props: {\"multiplier\": 2}", "Unrelated line"], item["context_before"])
        self.assertEqual(4, item["context_first_line"])

    def test_without_context_the_payload_is_unchanged(self) -> None:
        payload = self.grep()

        self.assertNotIn("context_before", payload["items"][0])
        self.assertNotIn("max_payload_bytes", payload)

    def test_context_is_bounded(self) -> None:
        for kwargs in ({"after_lines": 21}, {"before_lines": -1}, {"after_lines": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.grep(**kwargs)

    def test_byte_budget_drops_oldest_blocks_then_newest_context(self) -> None:
        self.log.write_text(
            "\n".join(["MATCH one"] + ["x" * 200] * 20 + ["MATCH two"] + ["y" * 200] * 20) + "\n",
            encoding="utf-8",
        )
        payload = server_health.grep_editor_log_payload(
            self.root, self.log, pattern="MATCH", after_lines=20, max_payload_bytes=1500
        )

        self.assertTrue(payload["byte_budget_truncated"])
        self.assertEqual(1, len(payload["items"]))
        newest = payload["items"][0]
        self.assertEqual("MATCH two", newest["message"])
        self.assertTrue(newest["context_truncated_for_byte_budget"])
        self.assertLess(len(newest["context_after"]), 20)
        self.assertLessEqual(payload["payload_bytes_estimate"], 1500)

    def test_mcp_tool_passes_context_and_refuses_it_for_the_console_source(self) -> None:
        with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=self.root):
            result = server_batch_orchestrator.call_unity_console_grep_tool(
                {"projectRoot": str(self.root), "pattern": "SpinResult", "editorLogPath": str(self.log), "afterLines": 1}
            )
            payload = json.loads(result["content"][0]["text"])
            self.assertEqual(['Props: {"wheel": 3}'], payload["items"][0]["context_after"])
            with self.assertRaises(JsonRpcError):
                server_batch_orchestrator.call_unity_console_grep_tool(
                    {"projectRoot": str(self.root), "pattern": "x", "source": "console", "afterLines": 1}
                )


if __name__ == "__main__":
    unittest.main()
