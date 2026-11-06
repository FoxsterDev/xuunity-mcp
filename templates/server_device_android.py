from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from server_core import ToolInvocationError, hidden_window_subprocess_kwargs

ADB_ENV_OVERRIDE = "XUUNITY_ADB_PATH"
READY_STATE = "device"
INT64_MAX = 9223372036854775807

INSTALL_FAILURE_CLASSES = {
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "install_refused_signature_conflict",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "install_refused_downgrade",
    "INSTALL_FAILED_CONFLICTING_PROVIDER": "install_refused_conflicting_provider",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "install_refused_insufficient_storage",
    "INSTALL_FAILED_NO_MATCHING_ABIS": "install_refused_abi_mismatch",
    "INSTALL_FAILED_OLDER_SDK": "install_refused_device_sdk_too_old",
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": "install_refused_unsigned_apk",
}

STATE_REMEDIATION = {
    "unauthorized": "Unlock the device and accept the 'Allow USB debugging' prompt, then list devices again.",
    "offline": "Reconnect the cable or run 'adb reconnect'; the device stopped answering adb.",
    "no permissions": "Fix the host's USB permissions (udev rules on Linux), then reconnect the device.",
    "recovery": "The device is in recovery mode; boot it normally.",
    "bootloader": "The device is in the bootloader; boot it normally.",
}


@dataclass
class AdbResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _executable_name() -> str:
    return "adb.exe" if sys.platform.startswith("win") else "adb"


def _unity_android_sdk_candidates() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "darwin":
        hub = Path("/Applications/Unity/Hub/Editor")
        if hub.is_dir():
            roots.extend(sorted(hub.glob("*/PlaybackEngines/AndroidPlayer/SDK/platform-tools"), reverse=True))
    elif sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
            hub = Path(base) / "Unity" / "Hub" / "Editor"
            if hub.is_dir():
                roots.extend(sorted(hub.glob("*/Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools"), reverse=True))
    else:
        hub = Path.home() / "Unity" / "Hub" / "Editor"
        if hub.is_dir():
            roots.extend(sorted(hub.glob("*/Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools"), reverse=True))
    return roots


def locate_adb(environ: dict[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if environ is None else environ
    override = str(env.get(ADB_ENV_OVERRIDE) or "").strip()
    if override and Path(override).is_file():
        return override, "env_override"

    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = str(env.get(variable) or "").strip()
        if root:
            candidate = Path(root) / "platform-tools" / _executable_name()
            if candidate.is_file():
                return str(candidate), variable.lower()

    found = shutil.which("adb")
    if found:
        return found, "path"

    for directory in _unity_android_sdk_candidates():
        candidate = directory / _executable_name()
        if candidate.is_file():
            return str(candidate), "unity_android_sdk"
    return "", ""


def require_adb() -> str:
    adb, _ = locate_adb()
    if not adb:
        raise ToolInvocationError(
            "device_tool_unavailable",
            (
                "adb was not found. Install Android platform-tools or the Unity Android Build Support module, or set "
                f"ANDROID_HOME / {ADB_ENV_OVERRIDE}. No device operation was attempted."
            ),
            {"recommended_next_action": "install_android_platform_tools_or_set_android_home"},
        )
    return adb


def run_adb(
    args: list[str],
    *,
    serial: str = "",
    timeout_seconds: float = 30.0,
    adb: str = "",
    binary: bool = False,
) -> AdbResult:
    executable = adb or require_adb()
    command = [executable]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            **hidden_window_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        err = exc.stderr or b""
        return AdbResult(-1, out if binary else _decode(out), _decode(err), timed_out=True)
    except OSError as exc:
        return AdbResult(-1, b"" if binary else "", str(exc))
    stdout: Any = completed.stdout if binary else _decode(completed.stdout)
    return AdbResult(completed.returncode, stdout, _decode(completed.stderr))


def _decode(data: Any) -> str:
    if isinstance(data, str):
        return data
    return bytes(data or b"").decode("utf-8", errors="replace")


def device_shell_command(argv: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in argv)


def unity_launch_extra(unity_args: list[str]) -> list[str]:
    joined = " ".join(str(item) for item in unity_args if str(item).strip())
    return ["-e", "unity", joined] if joined else []


def build_launch_shell_command(package: str, activity: str, unity_args: list[str]) -> str:
    if activity:
        component = activity if "/" in activity else f"{package}/{activity}"
        return device_shell_command(["am", "start", "-W", "-n", component, *unity_launch_extra(unity_args)])
    if unity_args:
        raise ToolInvocationError(
            "device_launch_activity_required",
            "unityArgs need an explicit activity (am start -e unity ...); monkey launches cannot pass extras.",
            {"package": package},
        )
    return device_shell_command(["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])


def parse_devices(output: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        match = re.match(r"^(\S+)\s+(no permissions|\S+)(.*)$", line)
        if not match:
            continue
        serial, state, rest = match.group(1), match.group(2), match.group(3)
        entry: dict[str, Any] = {"serial": serial, "state": state, "ready": state == READY_STATE}
        for key, value in re.findall(r"(\w+):(\S+)", rest):
            entry[key] = value
        if state in STATE_REMEDIATION:
            entry["remediation"] = STATE_REMEDIATION[state]
        devices.append(entry)
    return devices


def resolve_serial(devices: list[dict[str, Any]], requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        match = next((device for device in devices if device["serial"] == requested), None)
        if match is None:
            raise ToolInvocationError(
                "device_not_found",
                f"No attached device has serial {requested}.",
                {"serial": requested, "attached": [device["serial"] for device in devices]},
            )
        if not match["ready"]:
            raise ToolInvocationError(
                f"device_{match['state'].replace(' ', '_')}",
                match.get("remediation") or f"Device {requested} is {match['state']}.",
                {"serial": requested, "state": match["state"]},
            )
        return requested

    if len(devices) > 1:
        raise ToolInvocationError(
            "device_serial_required",
            "More than one device is attached; pass serial explicitly. Nothing was run.",
            {"attached": [{"serial": device["serial"], "state": device["state"]} for device in devices]},
        )
    if not devices:
        raise ToolInvocationError(
            "device_not_attached",
            "No Android device is attached (adb devices is empty). Connect a device with USB debugging on.",
            {"recommended_next_action": "connect_device_and_enable_usb_debugging"},
        )
    only = devices[0]
    if not only["ready"]:
        raise ToolInvocationError(
            f"device_{only['state'].replace(' ', '_')}",
            only.get("remediation") or f"Device {only['serial']} is {only['state']}.",
            {"serial": only["serial"], "state": only["state"]},
        )
    return only["serial"]


def classify_install_output(text: str) -> tuple[str, str]:
    for code, trust_class in INSTALL_FAILURE_CLASSES.items():
        if code in text:
            return trust_class, code
    match = re.search(r"\b(INSTALL_[A-Z_]+)\b", text)
    if match:
        return "install_failed", match.group(1)
    return "", ""


def parse_am_start_times(output: str) -> dict[str, int]:
    times: dict[str, int] = {}
    for key in ("TotalTime", "WaitTime", "ThisTime"):
        match = re.search(rf"^{key}:\s*(\d+)", output, re.MULTILINE)
        if match:
            times[key] = int(match.group(1))
    return times


def parse_package_versions(dumpsys_package: str) -> dict[str, str]:
    name = re.search(r"versionName=(\S+)", dumpsys_package)
    code = re.search(r"versionCode=(\d+)", dumpsys_package)
    return {
        "version_name": name.group(1) if name else "",
        "version_code": code.group(1) if code else "",
    }


def parse_dexopt_status(dumpsys_dexopt: str, package: str) -> str:
    block_start = dumpsys_dexopt.find(f"[{package}]")
    if block_start < 0:
        return ""
    block = dumpsys_dexopt[block_start:]
    next_block = re.search(r"\n\s*\[[\w.]+\]", block[len(package) + 2 :])
    if next_block:
        block = block[: len(package) + 2 + next_block.start()]
    statuses = re.findall(r"status=([\w-]+)", block)
    if not statuses:
        statuses = re.findall(r"\[status=([\w-]+)\]", block)
    return statuses[0] if statuses else ""


MONOTONIC_LINE = re.compile(r"^\s*(\d+\.\d+)\s+\d+\s+\d+\s+[VDIWEF]\s")


def logcat_line_seconds(line: str) -> float | None:
    match = MONOTONIC_LINE.match(line)
    return float(match.group(1)) if match else None


def find_logcat_marker(lines: Iterable[str], pattern: str, *, after: float | None = None) -> tuple[float | None, str]:
    regex = re.compile(pattern)
    for line in lines:
        seconds = logcat_line_seconds(line)
        if seconds is None or (after is not None and seconds < after):
            continue
        if regex.search(line):
            return seconds, line.rstrip("\n")
    return None, ""


def find_activity_start(lines: Iterable[str], package: str) -> tuple[float | None, str]:
    return find_logcat_marker(lines, rf"(ActivityTaskManager|ActivityManager).*START u\d+ .*{re.escape(package)}")
