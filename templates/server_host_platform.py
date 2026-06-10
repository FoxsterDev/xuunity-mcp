from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


WSL_PROC_ROOT = Path("/proc")


def _clear_thread_exception() -> None:
    try:
        import ctypes
        if hasattr(ctypes, "pythonapi") and hasattr(ctypes.pythonapi, "PyErr_Clear"):
            ctypes.pythonapi.PyErr_Clear()
    except Exception:
        pass


@dataclass(frozen=True)
class HostPlatformAdapter:
    platform_kind: str

    def pid_is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False

        _clear_thread_exception()

        is_windows_like = (os.name == "nt" or sys.platform in ("win32", "cygwin", "msys"))

        if is_windows_like:
            if os.name == "nt":
                try:
                    import ctypes
                    from ctypes import wintypes
                    kernel32 = ctypes.windll.kernel32

                    # Explicitly declare argument and return types to prevent 64-bit handle truncation
                    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel32.OpenProcess.restype = wintypes.HANDLE

                    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

                    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                    kernel32.CloseHandle.restype = wintypes.BOOL

                    kernel32.GetLastError.argtypes = []
                    kernel32.GetLastError.restype = wintypes.DWORD

                    handle = kernel32.OpenProcess(0x1000, False, pid)
                    if not handle:
                        is_alive = (kernel32.GetLastError() == 5)
                        _clear_thread_exception()
                        return is_alive

                    exit_code = wintypes.DWORD()
                    success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    kernel32.CloseHandle(handle)

                    _clear_thread_exception()
                    if success:
                        return exit_code.value == 259
                    return False
                except Exception:
                    _clear_thread_exception()

            # Fallback for native Windows, or primary route for Cygwin/MSYS
            for cmd in ["tasklist", "tasklist.exe"]:
                try:
                    completed = subprocess.run(
                        [cmd, "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    return windows_tasklist_contains_pid(completed.stdout, pid)
                except Exception:
                    pass
            return False

        if not is_wsl():
            try:
                os.kill(pid, 0)
                _clear_thread_exception()
                return True
            except (OSError, SystemError):
                _clear_thread_exception()
                pass
        else:
            interop_status = wsl_linux_unity_interop_pid_status(pid)
            if interop_status is not None:
                return interop_status

            for cmd in ["tasklist.exe", "tasklist"]:
                try:
                    completed = subprocess.run(
                        [cmd, "/FI", f"PID eq {pid}", "/NH"],
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
                stderr = "PowerShell was not found on PATH."
                if is_wsl():
                    stderr = (
                        "PowerShell was not found on PATH. In WSL, ensure Windows interop is enabled and "
                        "appendWindowsPath = true is set in /etc/wsl.conf, or expose powershell.exe/pwsh.exe on PATH."
                    )
                return {
                    "available": False,
                    "commands": [],
                    "error_code": "process_listing_tool_missing",
                    "stderr": stderr,
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
    target = int(pid)
    for line in str(output or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('"'):
            try:
                fields = next(csv.reader([stripped]))
            except Exception:
                fields = []
            if len(fields) >= 2:
                try:
                    if int(fields[1]) == target and "unity" in fields[0].lower():
                        return True
                except ValueError:
                    pass
        else:
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    if int(parts[1]) == target and "unity" in parts[0].lower():
                        return True
                except ValueError:
                    pass
    return False


def windows_tasklist_process_pid(line: str) -> int | None:
    stripped = str(line or "").strip()
    if not stripped:
        return None

    lowered = stripped.lower()
    if (
        lowered.startswith(("info:", "error:", "warning:", "success:"))
        or lowered.startswith("image name")
        or set(stripped) <= {"=", "-"}
    ):
        return None

    if stripped.startswith('"'):
        try:
            fields = next(csv.reader([stripped]))
        except (csv.Error, StopIteration):
            fields = []
        if len(fields) >= 2:
            try:
                return int(str(fields[1]).strip())
            except (TypeError, ValueError):
                return None

    parts = stripped.split()
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except (TypeError, ValueError):
            return None

    return None


def wsl_linux_unity_interop_pid_status(pid: int) -> bool | None:
    if pid <= 0 or not is_wsl():
        return None

    proc_pid_dir = WSL_PROC_ROOT / str(pid)
    cmdline_path = proc_pid_dir / "cmdline"
    if not cmdline_path.is_file():
        return None

    try:
        exe_link = os.readlink(str(proc_pid_dir / "exe"))
        if "init" not in os.path.basename(exe_link):
            return None
    except OSError:
        return None

    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return False

    text = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
    return "unity" in text


def wsl_host_diagnostics() -> dict[str, object]:
    if not is_wsl():
        return {
            "wsl": False,
            "wslpath_available": True,
            "warnings": [],
        }

    warnings: list[str] = []
    wslpath_available = shutil.which("wslpath") is not None
    if not wslpath_available:
        warnings.append(
            "wslpath_missing: WSL path conversion is limited to fallback drive mappings; install/restore wslpath for custom mount roots."
        )

    return {
        "wsl": True,
        "wslpath_available": wslpath_available,
        "warnings": warnings,
    }


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
