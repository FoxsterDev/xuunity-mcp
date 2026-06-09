from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HostPlatformAdapter:
    platform_kind: str

    def pid_is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False

        if os.name == "nt":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    return kernel32.GetLastError() == 5

                exit_code = ctypes.c_ulong()
                success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                kernel32.CloseHandle(handle)

                if success:
                    return exit_code.value == 259
                return False
            except Exception:
                try:
                    completed = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    return windows_tasklist_contains_pid(completed.stdout, pid)
                except Exception:
                    return False

        try:
            os.kill(pid, 0)
            return True
        except (OSError, SystemError):
            pass

        if is_wsl():
            try:
                completed = subprocess.run(
                    ["tasklist.exe", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return windows_tasklist_contains_pid(completed.stdout, pid)
            except Exception:
                pass

        return False

    def list_process_commands_report(self) -> dict[str, object]:
        if os.name == "nt" or is_wsl():
            shell_name = "powershell.exe" if is_wsl() else "powershell"
            shell_path = (
                shutil.which(shell_name) or
                shutil.which("powershell") or
                shutil.which("powershell.exe") or
                shutil.which("pwsh") or
                shutil.which("pwsh.exe")
            )
            if not shell_path:
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_tool_missing",
                    "stderr": "PowerShell was not found on PATH.",
                    "platform_kind": self.platform_kind,
                }

            script = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine } | "
                "Select-Object ProcessId,CommandLine | "
                "ConvertTo-Json -Compress"
            )
            try:
                completed = subprocess.run(
                    [shell_path, "-NoProfile", "-Command", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except OSError as exc:
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_failed",
                    "stderr": str(exc),
                    "platform_kind": self.platform_kind,
                }

            stderr = (completed.stderr or "").strip()
            if completed.returncode != 0:
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_failed",
                    "stderr": stderr,
                    "platform_kind": self.platform_kind,
                }

            raw = completed.stdout.strip()
            if not raw:
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_empty",
                    "stderr": stderr,
                    "platform_kind": self.platform_kind,
                }

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_parse_failed",
                    "stderr": f"{exc}: {stderr}".strip(),
                    "platform_kind": self.platform_kind,
                }

            if isinstance(payload, dict):
                payload = [payload]

            commands: list[tuple[int, str]] = []
            for entry in payload if isinstance(payload, list) else []:
                if not isinstance(entry, dict):
                    continue
                try:
                    pid = int(entry.get("ProcessId") or 0)
                except (TypeError, ValueError):
                    continue
                command = str(entry.get("CommandLine") or "").strip()
                if pid > 0 and command:
                    commands.append((pid, command))
            return {
                "available": True,
                "commands": commands,
                "error_code": "",
                "stderr": stderr,
                "platform_kind": self.platform_kind,
            }

        try:
            completed = subprocess.run(
                ["ps", "-axo", "pid=,command="],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return {
                "available": False,
                "commands": [],
                "error_code": "process_listing_failed",
                "stderr": str(exc),
                "platform_kind": self.platform_kind,
            }

        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            return {
                "available": False,
                "commands": [],
                "error_code": "process_listing_failed",
                "stderr": stderr,
                "platform_kind": self.platform_kind,
            }

        if not (completed.stdout or "").strip():
            return {
                "available": False,
                "commands": [],
                "error_code": "process_listing_empty",
                "stderr": stderr,
                "platform_kind": self.platform_kind,
            }

        commands: list[tuple[int, str]] = []
        for line in completed.stdout.splitlines():
            line = line.rstrip()
            if not line:
                continue
            parts = line.lstrip().split(None, 1)
            if len(parts) != 2:
                continue
            raw_pid, command = parts
            try:
                pid = int(raw_pid)
            except ValueError:
                continue
            command = command.strip()
            if pid > 0 and command:
                commands.append((pid, command))
        return {
            "available": True,
            "commands": commands,
            "error_code": "",
            "stderr": stderr,
            "platform_kind": self.platform_kind,
        }

    def list_process_commands(self) -> list[tuple[int, str]]:
        report = self.list_process_commands_report()
        commands = report.get("commands") if isinstance(report, dict) else []
        return list(commands or [])


def is_wsl() -> bool:
    if sys.platform == "linux":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return True
        except Exception:
            pass
    return False


def windows_tasklist_contains_pid(output: str, pid: int) -> bool:
    target = str(pid)
    for line in str(output or "").splitlines():
        if re.search(rf"(^|\s){re.escape(target)}(\s|$)", line):
            return True
    return False


def windows_to_wsl_path(path: str | Path) -> str:
    path_str = str(path).strip()
    if not path_str or not is_wsl():
        return path_str

    try:
        completed = subprocess.run(
            ["wslpath", "-u", path_str],
            capture_output=True,
            text=True,
            check=True,
        )
        converted = completed.stdout.strip()
        if converted:
            return converted
    except Exception:
        pass

    match = re.match(r"^([A-Za-z]):[\\/]*(.*)$", path_str)
    if match:
        drive, rest = match.groups()
        normalized_rest = rest.replace("\\", "/").strip("/")
        return f"/mnt/{drive.lower()}/{normalized_rest}" if normalized_rest else f"/mnt/{drive.lower()}"
    return path_str


def host_path_to_local_path(path: str | Path) -> str:
    return windows_to_wsl_path(path) if is_wsl() else str(path)


def wsl_to_windows_path(path: str | Path) -> str:
    path_str = str(path)
    if is_wsl():
        try:
            completed = subprocess.run(
                ["wslpath", "-w", path_str],
                capture_output=True,
                text=True,
                check=True,
            )
            return completed.stdout.strip()
        except Exception:
            if path_str.startswith("/mnt/"):
                parts = path_str.split("/", 3)
                if len(parts) >= 3:
                    drive = parts[2].upper()
                    rest = parts[3].replace("/", "\\") if len(parts) > 3 else ""
                    return f"{drive}:\\{rest}"
    return path_str


def host_platform_kind() -> str:
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return "linux"


def current_host_platform_adapter() -> HostPlatformAdapter:
    return HostPlatformAdapter(platform_kind=host_platform_kind())
