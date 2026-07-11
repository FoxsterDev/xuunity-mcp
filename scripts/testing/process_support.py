"""Shared subprocess helpers for orchestrators and tests.

Promoted from tests/bash_support.py so the multi-project orchestrator and the
test suite kill runaway process trees the same way on every OS.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path


def resolve_bash_executable() -> str:
    if os.name != "nt":
        return "bash"
    for env_name in ("PROGRAMFILES", "ProgramW6432", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        for relative in (("Git", "usr", "bin", "bash.exe"), ("Git", "bin", "bash.exe")):
            candidate = Path(base).joinpath(*relative)
            if candidate.is_file():
                return str(candidate)
    located = shutil.which("bash")
    if located and "system32" not in located.lower():
        return located
    return "bash"


def kill_process_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
        )
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def run_with_timeout(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 300,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run cmd capturing text output; kill the whole tree on timeout.

    Raises subprocess.TimeoutExpired (with partial output attached) after the
    tree has been killed, so callers never leak a hung child. input_text, when
    given, is written to the child's stdin (UTF-8) and stdin is closed after.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name != "nt"),
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        raise subprocess.TimeoutExpired(cmd, timeout_seconds, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def run_to_files(
    cmd: list[str],
    stdout_path: str,
    stderr_path: str,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    merge_stderr: bool = False,
) -> int:
    """Run cmd streaming output to files, mirroring shell `>out 2>err` redirects.

    Files are truncated on every call, matching the shell behavior. With a
    timeout, the process tree is killed and 124 is returned.
    """
    with open(stdout_path, "w", encoding="utf-8") as stdout_file:
        stderr_file = stdout_file if merge_stderr else open(stderr_path, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=(os.name != "nt"),
            )
            try:
                proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                kill_process_tree(proc)
                proc.wait(timeout=30)
                stderr_file.write(
                    "\n[run_to_files] command timed out after %ss and its process tree was killed: %s\n"
                    % (timeout_seconds, " ".join(str(part) for part in cmd))
                )
                return 124
            return proc.returncode
        finally:
            if not merge_stderr:
                stderr_file.close()
