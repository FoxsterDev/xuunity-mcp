"""Windows client-config templates must stay spawnable through argv quoting.

MCP clients (Node libuv, Python list2cmdline) quote argv with the C-runtime
rules: an arg containing spaces or quotes gets wrapped, and embedded quotes
become ``\\"``. cmd.exe does not understand ``\\"``, so a config arg like
``if defined X (call "%X%\\run.cmd") else (...)`` can never spawn — the first
config-to-connection e2e run on the Windows CI leg caught exactly that. Every
Windows client template must therefore keep each arg free of quotes and
parentheses and carry the launcher path as its own argv entry.
"""

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENTS_DIR = REPO_ROOT / "templates" / "clients"

WINDOWS_JSON_TEMPLATES = (
    CLIENTS_DIR / "claude-code" / ".mcp.windows.json",
    CLIENTS_DIR / "claude-desktop" / "claude_desktop_config.windows.json",
    CLIENTS_DIR / "cursor" / "mcp.windows.json",
    CLIENTS_DIR / "windsurf" / "mcp_config.windows.json",
    CLIENTS_DIR / "generic" / "stdio-mcp.windows.json",
)
WINDOWS_TOML_TEMPLATE = CLIENTS_DIR / "codex" / "config.windows.toml.snippet"
LAUNCHER_BASENAME = "run_installed_or_refresh_xuunity_mcp.cmd"


class WindowsClientConfigContractTest(unittest.TestCase):
    def test_json_templates_use_quote_free_call_args(self) -> None:
        for template in WINDOWS_JSON_TEMPLATES:
            with self.subTest(template=template.name):
                payload = json.loads(template.read_text(encoding="utf-8"))
                server = payload["mcpServers"]["xuunity_light_unity"]
                self.assertEqual("cmd.exe", server["command"], template)
                args = server["args"]
                self.assertEqual(["/d", "/c", "call"], args[:3], template)
                self.assertEqual(4, len(args), template)
                for arg in args:
                    self.assertNotRegex(
                        arg,
                        r'["()]',
                        f"{template.name}: embedded quotes/parens do not survive "
                        "client argv quoting on Windows",
                    )
                self.assertTrue(args[3].endswith(LAUNCHER_BASENAME), args[3])

    def test_codex_toml_template_uses_quote_free_call_args(self) -> None:
        text = WINDOWS_TOML_TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("if defined", text, "conditional one-liners cannot spawn")
        args_match = re.search(r"(?m)^args = \[(?P<args>.+)\]$", text)
        self.assertIsNotNone(args_match, text)
        args = re.findall(r'"((?:[^"\\]|\\.)*)"', args_match.group("args"))
        self.assertEqual(["/d", "/c", "call"], args[:3], text)
        self.assertEqual(4, len(args), text)
        for arg in args:
            self.assertNotRegex(arg.replace("\\\\", "\\"), r'["()]', text)
        self.assertTrue(args[3].replace("\\\\", "\\").endswith(LAUNCHER_BASENAME), args[3])


if __name__ == "__main__":
    unittest.main()
