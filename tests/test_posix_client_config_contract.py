"""POSIX client templates must start without PATH or login-profile discovery."""

import json
import unittest
from pathlib import Path, PurePosixPath


CLIENTS_DIR = Path(__file__).resolve().parents[1] / "templates" / "clients"
JSON_CONFIGS = (
    CLIENTS_DIR / "claude-code" / ".mcp.json",
    CLIENTS_DIR / "claude-desktop" / "claude_desktop_config.json",
    CLIENTS_DIR / "cursor" / "mcp.json",
    CLIENTS_DIR / "generic" / "stdio-mcp.json",
    CLIENTS_DIR / "windsurf" / "mcp_config.json",
)


class PosixClientConfigContractTests(unittest.TestCase):
    def assert_posix_launcher(self, command: str, args: list[str], source: Path) -> None:
        self.assertTrue(PurePosixPath(command).is_absolute(), f"{source}: {command!r}")
        self.assertEqual("-c", args[0], f"{source}: {args!r}")
        self.assertNotIn("-lc", args, f"{source}: login profiles must not affect MCP startup")
        self.assertIn(command, args[1], f"{source}: launcher must reuse the resolved shell")
        self.assertIn("run_installed_or_refresh_xuunity_mcp.sh", args[1], source)

    def test_json_templates_use_absolute_non_login_bash(self) -> None:
        for config_path in JSON_CONFIGS:
            with self.subTest(config=config_path):
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                server = payload["mcpServers"]["xuunity_light_unity"]
                self.assert_posix_launcher(server["command"], server["args"], config_path)

    def test_codex_template_uses_absolute_non_login_bash(self) -> None:
        config_path = CLIENTS_DIR / "codex" / "config.toml.snippet"
        text = config_path.read_text(encoding="utf-8")

        self.assertIn('command = "/bin/bash"', text)
        self.assertIn('args = ["-c", "exec \\"/bin/bash\\"', text)
        self.assertNotIn('command = "bash"', text)
        self.assertNotIn('"-lc"', text)


if __name__ == "__main__":
    unittest.main()
