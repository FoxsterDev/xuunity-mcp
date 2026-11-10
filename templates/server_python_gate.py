"""Interpreter gate shared by every Python entrypoint.

Shell launchers stay thin and exec the first Python they find. When that interpreter is
older than 3.10, this gate looks for a supported one (the script's own venv, the neutral
install venv, then versioned names on PATH) and re-runs the entrypoint with it. Keep this
module importable by old interpreters: standard library only, no 3.10 syntax.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM_PYTHON = (3, 10)
REEXEC_MARKER_ENV = "XUUNITY_LIGHT_UNITY_MCP_REEXEC"
PATH_CANDIDATES = (
    "python3.15",
    "python3.14",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3.10",
    "python3",
    "python",
)
PROBE_SOURCE = "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 2)"
PROBE_TIMEOUT_SECONDS = 20


def _version_text() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])


def _windows_like() -> bool:
    return (
        os.name == "nt"
        or sys.platform.startswith("win")
        or os.environ.get("OS") == "Windows_NT"
        or str(os.environ.get("MSYSTEM") or "").upper().startswith(("MINGW", "MSYS", "CYGWIN"))
    )


def neutral_install_dir() -> Path:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if _windows_like():
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata.replace("\\", "/")) / "xuunity-mcp"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "xuunity-mcp"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "xuunity-mcp"
    return Path.home() / ".local" / "share" / "xuunity-mcp"


def _venv_interpreters(root: Path) -> list:
    return [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / ".venv" / "bin" / "python3",
    ]


def interpreter_candidates(script_dirs: list) -> list:
    candidates = []
    for root in [*script_dirs, neutral_install_dir()]:
        for path in _venv_interpreters(Path(root)):
            if path.is_file() and os.access(str(path), os.X_OK):
                candidates.append(str(path))
    for name in PATH_CANDIDATES:
        found = shutil.which(name)
        if found:
            candidates.append(found)
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def interpreter_is_supported(candidate: str) -> bool:
    try:
        completed = subprocess.run(
            [candidate, "-c", PROBE_SOURCE],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def ensure_supported_python(script_path: str, argv: list, script_dirs: list = ()) -> None:
    if sys.version_info[:2] >= MINIMUM_PYTHON:
        os.environ.pop(REEXEC_MARKER_ENV, None)
        return
    current = _version_text()
    explicit = os.environ.get("PYTHON")
    if explicit or os.environ.get(REEXEC_MARKER_ENV):
        source = f"PYTHON={explicit}" if explicit else "the re-executed interpreter"
        sys.stderr.write(
            f"Python 3.10 or newer is required. {source} reports {current}. "
            "Set PYTHON to the absolute path of a Python 3.10+ interpreter.\n"
        )
        raise SystemExit(1)

    tried = []
    for candidate in interpreter_candidates(list(script_dirs)):
        if interpreter_is_supported(candidate):
            sys.stderr.write(
                f"xuunity launcher: python {current} at {sys.executable} is too old; re-running with {candidate}\n"
            )
            sys.stderr.flush()
            os.environ[REEXEC_MARKER_ENV] = "1"
            command = [candidate, str(script_path), *argv]
            if os.name == "nt":
                raise SystemExit(subprocess.run(command, check=False).returncode)
            os.execv(candidate, command)
        tried.append(candidate)

    sys.stderr.write(
        f"Python 3.10 or newer is required. Selected interpreter {sys.executable} reports {current}; "
        f"no supported interpreter was found (tried: {', '.join(tried) or 'none'}). "
        "Set PYTHON to the absolute path of a Python 3.10+ interpreter.\n"
    )
    raise SystemExit(1)
