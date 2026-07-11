import subprocess
import sys
from pathlib import Path

SCRIPTS_TESTING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "testing"
if str(SCRIPTS_TESTING_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_TESTING_DIR))

from process_support import kill_process_tree as _kill_process_tree
from process_support import resolve_bash_executable
from process_support import run_with_timeout as _run_with_timeout

_first_timeout_cmd: str | None = None


def skip_if_prior_subprocess_timeout(test_case) -> None:
    if _first_timeout_cmd is not None:
        test_case.skipTest(
            f"a prior subprocess already timed out on this host; first: {_first_timeout_cmd}"
        )


def run_with_timeout(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 300,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return _run_with_timeout(
            cmd, cwd=cwd, env=env, timeout_seconds=timeout_seconds, input_text=input_text
        )
    except subprocess.TimeoutExpired as exc:
        global _first_timeout_cmd
        if _first_timeout_cmd is None:
            _first_timeout_cmd = " ".join(str(part) for part in cmd)[:300]
        message = (
            f"command timed out after {timeout_seconds}s: {cmd}\n"
            f"partial stdout:\n{(exc.output or '')[-4000:]}\n"
            f"partial stderr:\n{(exc.stderr or '')[-4000:]}"
        )
        sys.stderr.write(f"\n[run_with_timeout] {message}\n")
        sys.stderr.flush()
        raise AssertionError(message)
