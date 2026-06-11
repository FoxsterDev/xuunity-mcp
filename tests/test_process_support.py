"""Unit coverage for the promoted shared subprocess util."""

import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

SCRIPTS_TESTING_DIR = TESTS_DIR.parent / "scripts" / "testing"
if str(SCRIPTS_TESTING_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_TESTING_DIR))

from process_support import run_to_files


class RunToFilesTests(unittest.TestCase):
    def test_streams_stdout_and_stderr_to_separate_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            stdout_path = str(Path(temp_dir) / "out.txt")
            stderr_path = str(Path(temp_dir) / "err.txt")
            rc = run_to_files(
                [sys.executable, "-c", "import sys; print('to-out'); print('to-err', file=sys.stderr)"],
                stdout_path,
                stderr_path,
            )
            self.assertEqual(0, rc)
            self.assertEqual("to-out\n", Path(stdout_path).read_text(encoding="utf-8"))
            self.assertEqual("to-err\n", Path(stderr_path).read_text(encoding="utf-8"))

    def test_merge_stderr_writes_both_streams_to_one_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            merged_path = str(Path(temp_dir) / "merged.txt")
            rc = run_to_files(
                [sys.executable, "-c", "import sys; print('to-out'); print('to-err', file=sys.stderr)"],
                merged_path,
                merged_path,
                merge_stderr=True,
            )
            self.assertEqual(0, rc)
            merged = Path(merged_path).read_text(encoding="utf-8")
            self.assertIn("to-out", merged)
            self.assertIn("to-err", merged)

    def test_timeout_kills_process_tree_and_returns_124(self) -> None:
        with TemporaryDirectory() as temp_dir:
            stdout_path = str(Path(temp_dir) / "out.txt")
            stderr_path = str(Path(temp_dir) / "err.txt")
            started = time.monotonic()
            rc = run_to_files(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout_path,
                stderr_path,
                timeout_seconds=1,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(124, rc)
            self.assertLess(elapsed, 25, "timeout did not interrupt the sleeping child promptly")
            self.assertIn("timed out after", Path(stderr_path).read_text(encoding="utf-8"))

    def test_nonzero_exit_code_passthrough(self) -> None:
        with TemporaryDirectory() as temp_dir:
            stdout_path = str(Path(temp_dir) / "out.txt")
            stderr_path = str(Path(temp_dir) / "err.txt")
            rc = run_to_files(
                [sys.executable, "-c", "raise SystemExit(7)"],
                stdout_path,
                stderr_path,
            )
            self.assertEqual(7, rc)


if __name__ == "__main__":
    unittest.main()
