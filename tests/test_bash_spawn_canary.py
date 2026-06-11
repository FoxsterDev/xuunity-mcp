import os
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout

BASH = resolve_bash_executable()


class BashSpawnCanaryTests(unittest.TestCase):
    """Runs before the heavier multi-project runner tests. Guards the layers
    that historically hung on Windows hosts with no output: Git Bash spawn from
    Python and wrapper top-level init (dirname-walk fixed point, CRLF, msys
    path forms). A hang here fails fast with partial output instead of eating
    the CI job time limit."""

    def test_wrapper_help_runs_on_this_host(self) -> None:
        wrapper = Path(__file__).resolve().parents[1] / "xuunity_light_unity_mcp.sh"
        env = dict(os.environ, PYTHON=sys.executable)
        env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = "/tmp/nonexistent-xuunity-neutral-dir"
        completed = run_with_timeout(
            [BASH, wrapper.as_posix(), "--help"],
            env=env,
            timeout_seconds=60,
        )
        self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
        self.assertIn("Usage:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
