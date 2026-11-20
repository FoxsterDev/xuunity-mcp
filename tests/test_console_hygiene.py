import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_console_hygiene
import server_health

SESSION_TOKEN = "a8Kd93jsl2Lq0Zx7"


class ConsoleSecretRedactionTests(unittest.TestCase):
    def test_token_like_values_are_replaced(self) -> None:
        cases = {
            'POST /login -> {"sessionToken":"%s","player":"p1"}' % SESSION_TOKEN:
                'POST /login -> {"sessionToken":"[REDACTED]","player":"p1"}',
            "Authorization: Bearer abcDEF123456.ghi-789_xyz": "Authorization: Bearer [REDACTED]",
            "GET https://api.example.test/v1/level?access_token=9f8e7d6c5b4a3210&x=1":
                "GET https://api.example.test/v1/level?access_token=[REDACTED]&x=1",
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c ok":
                "jwt [REDACTED] ok",
            "password=hunter2x; next": "password=[REDACTED]; next",
            "X-Api-Key: 0123456789abcdef0123": "X-Api-Key: [REDACTED]",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                redacted, count = server_console_hygiene.redact_console_secrets(text)
                self.assertEqual(expected, redacted)
                self.assertEqual(1, count)

    def test_ordinary_log_lines_are_untouched(self) -> None:
        for text in (
            "[Flow] result=win reward=50",
            "tokenCount=12 cancellationToken: System.Threading.CancellationToken",
            "Assets/Game/TokenView.cs(12,4): error CS0103: The name 'token' does not exist",
            "cookie: none",
        ):
            with self.subTest(text=text):
                self.assertEqual((text, 0), server_console_hygiene.redact_console_secrets(text))

    def test_redaction_stays_fast_on_long_runs(self) -> None:
        started = time.monotonic()
        for text in ("a" * 200000, "token" * 40000, "tokenA=" + "b" * 200000):
            server_console_hygiene.redact_console_secrets(text)
        self.assertLess(time.monotonic() - started, 5.0)


class ConsoleItemFinalizeTests(unittest.TestCase):
    def test_long_message_is_capped_and_flagged(self) -> None:
        payload = server_console_hygiene.finalize_console_items(
            {"items": [{"message": "bodyPreview=" + "x" * 11000, "line": 3}, {"message": "short", "line": 4}]}
        )
        capped = payload["items"][0]
        self.assertTrue(capped["message"].endswith(server_console_hygiene.CONSOLE_ITEM_TRUNCATION_MARKER))
        self.assertLessEqual(len(capped["message"].encode("utf-8")), 2048 + 32)
        self.assertEqual(11012, capped["message_bytes_before_cap"])
        self.assertNotIn("message_bytes_before_cap", payload["items"][1])
        self.assertEqual(2048, payload["max_item_bytes"])
        self.assertEqual(1, payload["items_truncated_for_item_cap"])
        self.assertIn("maxItemBytes=-1", payload["item_cap_recovery_hint"])

    def test_negative_cap_returns_full_lines_but_still_redacts(self) -> None:
        message = "x" * 5000 + " sessionToken=" + SESSION_TOKEN
        payload = server_console_hygiene.finalize_console_items({"items": [{"message": message}]}, -1)
        self.assertEqual(-1, payload["max_item_bytes"])
        self.assertEqual(0, payload["items_truncated_for_item_cap"])
        self.assertNotIn(SESSION_TOKEN, payload["items"][0]["message"])
        self.assertEqual(1, payload["redacted_secret_count"])
        self.assertIn("redaction_note", payload)

    def test_context_lines_and_stack_traces_are_redacted(self) -> None:
        payload = server_console_hygiene.finalize_console_items(
            {"items": [{
                "message": "login ok",
                "stack_trace": "Net.Client:Send (token=%s)" % SESSION_TOKEN,
                "context_before": ["Authorization: Bearer abcDEF123456789"],
                "context_after": ['Props {"sessionToken":"%s"}' % SESSION_TOKEN],
            }]}
        )
        self.assertNotIn(SESSION_TOKEN, json.dumps(payload))
        self.assertNotIn("abcDEF123456789", json.dumps(payload))
        self.assertEqual(3, payload["redacted_secret_count"])

    def test_finalize_is_idempotent(self) -> None:
        once = server_console_hygiene.finalize_console_items({"items": [{"message": "password=hunter2x"}]})
        self.assertEqual(once, server_console_hygiene.finalize_console_items(once, -1))


class ConsoleToolHygieneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"
        self.log.write_text(
            "[Net] login sessionToken=%s\n[Net] bodyPreview=%s\n" % (SESSION_TOKEN, "y" * 9000),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _call(self, tool, arguments: dict) -> dict:
        with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=self.root):
            result = tool({"projectRoot": str(self.root), "editorLogPath": str(self.log), **arguments})
        return json.loads(result["content"][0]["text"])

    def test_editor_log_grep_redacts_and_caps_by_default(self) -> None:
        payload = self._call(server_batch_orchestrator.call_unity_console_grep_tool, {"pattern": "Net"})
        text = json.dumps(payload)
        self.assertNotIn(SESSION_TOKEN, text)
        self.assertEqual(1, payload["redacted_secret_count"])
        self.assertEqual(1, payload["items_truncated_for_item_cap"])
        self.assertLess(len(text), 9000)

    def test_editor_log_grep_messages_only_is_redacted_too(self) -> None:
        payload = self._call(
            server_batch_orchestrator.call_unity_console_grep_tool, {"pattern": "login", "messagesOnly": True}
        )
        self.assertEqual("[Net] login sessionToken=[REDACTED]", payload["items"][0]["message"])

    def test_editor_log_tail_redacts_and_honours_max_item_bytes(self) -> None:
        payload = self._call(
            server_batch_orchestrator.call_unity_console_tail_tool, {"maxItemBytes": -1, "maxPayloadBytes": -1}
        )
        self.assertNotIn(SESSION_TOKEN, json.dumps(payload))
        self.assertEqual(0, payload["items_truncated_for_item_cap"])
        self.assertTrue(any(len(item["message"]) > 9000 for item in payload["items"]))

    def test_console_source_grep_is_redacted(self) -> None:
        bridge_payload = {"items": [{"type": "log", "message": "token=%s" % SESSION_TOKEN}], "match_count": 1}
        response = {"status": "ok", "payload_json": json.dumps(bridge_payload)}
        with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=self.root), \
                mock.patch.object(server_batch_orchestrator, "invoke_bridge", return_value=response):
            result = server_batch_orchestrator.call_unity_console_grep_tool(
                {"projectRoot": str(self.root), "pattern": "token", "source": "console"}
            )
        self.assertNotIn(SESSION_TOKEN, json.dumps(result))

    def test_max_item_bytes_must_be_an_integer(self) -> None:
        with self.assertRaises(server_batch_orchestrator.JsonRpcError):
            self._call(server_batch_orchestrator.call_unity_console_grep_tool, {"pattern": "Net", "maxItemBytes": "x"})


if __name__ == "__main__":
    unittest.main()
