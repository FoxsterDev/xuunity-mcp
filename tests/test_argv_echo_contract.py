"""Raw-argv echo on argparse failure.

Historical Windows failure class 7 (2026-06-17 retro): Git-Bash argv quoting
truncated `D:\\Unity Projects\\Foo` to `D:\\Unity`, and the argparse error gave
no way to see what the interpreter actually received. On parse failure the
server must echo the received argv (repr) to stderr; help exits must stay
clean.
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server

ECHO_MARKER = "argv as received"


class ArgvEchoOnParseFailureTest(unittest.TestCase):
    def run_main(self, argv: list) -> tuple:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["server.py", *argv]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                server.main()
        return ctx.exception.code, stdout.getvalue(), stderr.getvalue()

    def test_truncated_spaced_path_argv_is_echoed_verbatim(self) -> None:
        exit_code, _, stderr = self.run_main(
            ["ensure-ready", "--project-root", "D:\\Unity", "Projects\\Foo"]
        )
        self.assertNotEqual(0, exit_code)
        self.assertIn(ECHO_MARKER, stderr)
        self.assertIn(repr(["ensure-ready", "--project-root", "D:\\Unity", "Projects\\Foo"]), stderr)

    def test_unknown_command_is_echoed(self) -> None:
        exit_code, _, stderr = self.run_main(["definitely-not-a-command"])
        self.assertNotEqual(0, exit_code)
        self.assertIn(ECHO_MARKER, stderr)
        self.assertIn("definitely-not-a-command", stderr)

    def test_help_exit_stays_clean(self) -> None:
        exit_code, stdout, stderr = self.run_main(["--help"])
        self.assertEqual(0, exit_code)
        self.assertIn("usage:", stdout.lower())
        self.assertNotIn(ECHO_MARKER, stderr)


if __name__ == "__main__":
    unittest.main()
