#!/usr/bin/env python3
"""Refresh the installed XUUnity MCP helper before launching it.

The sibling `.sh` entrypoint is intentionally a thin Python launcher. Keep
platform-sensitive behavior here so Windows Git Bash does not carry business
logic.
"""

from __future__ import annotations

import ast
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def require_supported_python() -> None:
    if sys.version_info[:2] >= (3, 10):
        return
    current = ".".join(str(part) for part in sys.version_info[:3])
    fail(f"Python 3.10 or newer is required. Selected interpreter reports {current}.")


def reconfigure_stdio_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def resolve_source_root(script_dir: Path) -> Path:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    if (script_dir / "init_xuunity_light_unity_mcp.sh").is_file() and (
        script_dir / "packages" / "com.xuunity.light-mcp" / "package.json"
    ).is_file():
        return script_dir

    marker = script_dir / ".source_root"
    if marker.is_file():
        lines = marker.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip():
            return Path(lines[0].strip()).expanduser().resolve()

    return script_dir


def expected_package_version(package_json: Path) -> str:
    if not package_json.is_file():
        fail(f"xuunity MCP package metadata not found: {package_json}")
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"failed to read xuunity MCP package metadata: {package_json}: {exc}")
    return str(payload.get("version") or "").strip()


def neutral_install_dir() -> Path:
    explicit = os.environ.get("XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR")
    if explicit:
        return Path(explicit).expanduser()

    if os.environ.get("OS") == "Windows_NT" or os.environ.get("APPDATA"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata.replace("\\", "/")) / "xuunity-mcp"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "xuunity-mcp"

    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "xuunity-mcp"
    return Path.home() / ".local" / "share" / "xuunity-mcp"


def installed_server_version(server_path: Path) -> str | None:
    if not server_path.is_file():
        return None
    try:
        tree = ast.parse(server_path.read_text(encoding="utf-8"), filename=str(server_path))
    except Exception:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "SERVER_INFO":
                try:
                    value = ast.literal_eval(node.value)
                except Exception:
                    return None
                if isinstance(value, dict):
                    return str(value.get("version") or "").strip()
    return None


def find_bash() -> str:
    if os.name != "nt":
        bash = shutil.which("bash")
        if bash:
            return bash
        fail("bash was not found. Install bash or run the installer manually.")

    for env_name in ("PROGRAMFILES", "ProgramW6432", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        for relative in (("Git", "usr", "bin", "bash.exe"), ("Git", "bin", "bash.exe")):
            candidate = Path(base).joinpath(*relative)
            if candidate.is_file():
                return str(candidate)

    bash = shutil.which("bash")
    if bash and "system32" not in bash.lower():
        return bash

    fail("Git Bash was not found. Install Git for Windows or run the installer manually.")
    raise AssertionError("unreachable")


def refresh_helper_if_needed(installer: Path, server_path: Path, run_path: Path, expected_version: str) -> None:
    if not installer.is_file():
        fail(f"xuunity MCP installer not found: {installer}")

    current_version = installed_server_version(server_path)
    if current_version == expected_version and run_path.is_file():
        return

    completed = subprocess.run(
        [find_bash(), str(installer), "--target", "both", "--force"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        fail(
            "xuunity MCP helper refresh failed. "
            "Run: bash init_xuunity_light_unity_mcp.sh --target both --force",
            completed.returncode,
        )


def exec_run(run_path: Path, args: list[str]) -> None:
    if os.name == "nt":
        if not run_path.is_file():
            fail(f"xuunity MCP Windows run launcher not found after refresh: {run_path}")
        completed = subprocess.run([str(run_path), *args], check=False)
        raise SystemExit(completed.returncode)

    if not run_path.is_file():
        fail(f"xuunity MCP run launcher not found after refresh: {run_path}")
    os.execv(str(run_path), [str(run_path), *args])


def main(argv: list[str]) -> int:
    require_supported_python()
    reconfigure_stdio_utf8()
    os.environ.setdefault("PYTHONUTF8", "1")
    script_dir = Path(__file__).resolve().parent
    source_root = resolve_source_root(script_dir)
    installer = source_root / "init_xuunity_light_unity_mcp.sh"
    package_json = source_root / "packages" / "com.xuunity.light-mcp" / "package.json"
    expected_version = expected_package_version(package_json)

    neutral_dir = neutral_install_dir()
    neutral_server = neutral_dir / "server.py"
    neutral_run = neutral_dir / ("run.cmd" if os.name == "nt" else "run.sh")

    refresh_helper_if_needed(installer, neutral_server, neutral_run, expected_version)

    if argv[:1] == ["--print-server"]:
        print(neutral_server)
        return 0
    if argv[:1] == ["--print-run"]:
        print(neutral_run)
        return 0

    exec_run(neutral_run, argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
