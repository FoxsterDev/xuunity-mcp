"""The version matrix installs the checkout into a per-run sandbox, not the host's live MCP installs."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCRIPT = REPO_ROOT / "scripts" / "testing" / "run_unity_version_matrix.sh"
INIT_SCRIPT = REPO_ROOT / "init_xuunity_light_unity_mcp.sh"

SANDBOXED_VARIABLES = (
    "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR",
    "CLAUDE_TOOLS_HOME",
    "CODEX_TOOLS_HOME",
    "CODEX_HOME",
)


class UnityVersionMatrixHostSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = MATRIX_SCRIPT.read_text(encoding="utf-8")

    def sandbox_block(self) -> str:
        match = re.search(r'if \[\[ "\$USE_HOST_INSTALL" != "true" \]\]; then\n(.*?)\nfi\n', self.matrix, re.S)
        self.assertIsNotNone(match, "matrix script has no host-install sandbox block")
        return match.group(1)

    def test_every_install_destination_is_exported_into_the_run_root(self) -> None:
        block = self.sandbox_block()
        self.assertIn('HOST_INSTALL_SANDBOX="$RUN_ROOT/host-install"', block)
        for name in SANDBOXED_VARIABLES:
            with self.subTest(name=name):
                self.assertRegex(block, rf'export {name}="\$HOST_INSTALL_SANDBOX/[a-z-]+"')

    def test_sandbox_is_set_before_the_first_install(self) -> None:
        sandbox_at = self.matrix.index('if [[ "$USE_HOST_INSTALL" != "true" ]]')
        install_at = self.matrix.index('bash "$INIT_SCRIPT"')
        self.assertLess(sandbox_at, install_at)

    def test_sandbox_covers_every_install_root_the_installer_reads(self) -> None:
        init = INIT_SCRIPT.read_text(encoding="utf-8")
        read_roots = set(re.findall(r'\$\{((?:CODEX|CLAUDE)_[A-Z_]*HOME):-', init))
        if "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR" in init:
            read_roots.add("XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR")
        self.assertEqual(set(SANDBOXED_VARIABLES), read_roots)

    def test_host_install_is_an_explicit_opt_in(self) -> None:
        self.assertIn('USE_HOST_INSTALL="false"\n', self.matrix)
        self.assertIn("--use-host-install)", self.matrix)


if __name__ == "__main__":
    unittest.main()
