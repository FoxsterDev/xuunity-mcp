from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from server_artifact_registry import register_artifact
from server_core import ToolInvocationError, hidden_window_subprocess_kwargs
from server_device_android import (
    ADB_DAEMON_RESTARTS,
    build_launch_shell_command,
    classify_install_output,
    device_shell_command,
    find_activity_start,
    find_logcat_marker,
    locate_adb,
    parse_am_start_times,
    parse_devices,
    parse_dexopt_status,
    parse_package_versions,
    require_adb,
    resolve_serial,
    run_adb,
)
from server_device_metrics import (
    SURFACE_LAYER_BASES,
    PresentAccumulator,
    frame_gap_stats,
    parse_latency,
    parse_meminfo,
    parse_thermal,
    parse_top_for_package,
    select_app_layer,
    summarize_build_runs,
)
from server_runtime_config import load_runtime_config

DEVICE_SCHEMA_VERSION = "xuunity.device-lane.v1"
FRAME_SAMPLE_INTERVAL_SECONDS = 1.0
PULL_ALLOWED_PREFIXES = ("/sdcard/Android/data/", "/storage/emulated/0/Android/data/", "/sdcard/Download/", "/storage/emulated/0/Download/", "/data/local/tmp/")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def device_root(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp" / "device"


def new_session_dir(project_root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_") or "session"
    path = device_root(project_root) / "sessions" / f"{stamp}_{safe}_{uuid.uuid4().hex[:6]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def device_config(project_root: Path) -> dict[str, Any]:
    config, _ = load_runtime_config(project_root)
    block = config.get("device") if isinstance(config, dict) else None
    return block if isinstance(block, dict) else {}


def allowed_packages(project_root: Path) -> list[str]:
    config = device_config(project_root)
    packages = config.get("packages")
    result: list[str] = []
    if isinstance(packages, list):
        result.extend(str(item) for item in packages if str(item).strip())
    elif isinstance(packages, dict):
        result.extend(str(key) for key in packages)
    return result


def package_profile(project_root: Path, package: str) -> dict[str, Any]:
    packages = device_config(project_root).get("packages")
    if isinstance(packages, dict) and isinstance(packages.get(package), dict):
        return dict(packages[package])
    return {}


def require_mutation(arguments: dict[str, Any], operation: str) -> None:
    if not bool(arguments.get("allowMutating")):
        raise ToolInvocationError(
            "device_mutation_approval_required",
            f"{operation} changes device state. Pass allowMutating=true. Nothing was run.",
            {"operation": operation},
        )


def require_destructive(project_root: Path, arguments: dict[str, Any], operation: str, package: str) -> None:
    require_mutation(arguments, operation)
    if not bool(arguments.get("approve")):
        raise ToolInvocationError(
            "device_destructive_approval_required",
            f"{operation} deletes app data on the device (local saves and login are lost). Pass approve=true. Nothing was run.",
            {"operation": operation, "package": package},
        )
    allowed = allowed_packages(project_root)
    if package not in allowed:
        raise ToolInvocationError(
            "device_package_not_allowlisted",
            (
                f"{operation} is limited to packages listed under device.packages in the project's MCP runtime "
                f"config; {package} is not listed. Nothing was run."
            ),
            {"operation": operation, "package": package, "allowed_packages": allowed},
        )


def list_devices(adb: str = "") -> list[dict[str, Any]]:
    result = run_adb(["devices", "-l"], adb=adb, timeout_seconds=15)
    if not result.ok:
        raise ToolInvocationError(
            "device_adb_failed",
            f"adb devices failed: {result.stderr.strip() or result.stdout.strip()}",
            {"returncode": result.returncode, "timed_out": result.timed_out},
        )
    return parse_devices(result.stdout)


def resolve_device(arguments: dict[str, Any]) -> str:
    return resolve_serial(list_devices(), str(arguments.get("serial") or ""))


def shell(serial: str, command: str, timeout_seconds: float = 30.0) -> str:
    result = run_adb(["shell", command], serial=serial, timeout_seconds=timeout_seconds)
    if result.timed_out:
        raise ToolInvocationError(
            "device_command_timeout",
            f"adb shell timed out after {timeout_seconds:.0f} s: {command[:120]}",
            {"serial": serial},
        )
    return result.stdout


def device_descriptor(serial: str) -> dict[str, Any]:
    props = shell(serial, "getprop ro.product.model; getprop ro.build.version.release; getprop ro.build.version.sdk; wm size; dumpsys input | grep -m1 SurfaceOrientation")
    lines = [line.strip() for line in props.splitlines()]
    resolution = ""
    orientation = ""
    for line in lines:
        size = re.search(r"(?:Override|Physical) size:\s*(\d+x\d+)", line)
        if size:
            resolution = size.group(1)
        rotation = re.search(r"SurfaceOrientation:\s*(\d)", line)
        if rotation:
            orientation = "portrait" if rotation.group(1) in {"0", "2"} else "landscape"
    return {
        "serial": serial,
        "model": lines[0] if lines else "",
        "os": "Android",
        "os_version": lines[1] if len(lines) > 1 else "",
        "sdk": lines[2] if len(lines) > 2 else "",
        "resolution": resolution,
        "orientation": orientation,
    }


def installed_versions(serial: str, package: str) -> dict[str, str]:
    return parse_package_versions(shell(serial, f"dumpsys package {package}"))


def install_apk(
    project_root: Path,
    serial: str,
    arguments: dict[str, Any],
    apk_path: Path,
    package: str,
) -> dict[str, Any]:
    require_mutation(arguments, "device.install")
    if not apk_path.is_file():
        raise ToolInvocationError("device_apk_not_found", f"APK not found: {apk_path}", {"apk_path": str(apk_path)})
    if bool(arguments.get("uninstallFirst")):
        require_destructive(project_root, arguments, "device.install uninstallFirst", package)
        run_adb(["uninstall", package], serial=serial, timeout_seconds=120)

    command = ["install", "-r"]
    if bool(arguments.get("allowDowngrade")):
        command.append("-d")
    command.append(str(apk_path))
    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        result = run_adb(command, serial=serial, timeout_seconds=float(arguments.get("installTimeoutSeconds") or 600))
        text = f"{result.stdout}\n{result.stderr}"
        trust_class, failure_code = classify_install_output(text)
        if result.ok or failure_code or attempts >= 2:
            break
        time.sleep(3)
    payload: dict[str, Any] = {
        "operation": "device.install",
        "serial": serial,
        "apk_path": str(apk_path),
        "package": package,
        "install_seconds": round(time.monotonic() - started, 2),
        "install_attempts": attempts,
    }
    if result.ok and "Success" in text and not failure_code:
        payload["result_trust_class"] = "device_truth_confirmed"
        if package:
            payload.update(installed_versions(serial, package))
        return payload

    payload["result_trust_class"] = trust_class or "install_failed"
    payload["failure_code"] = failure_code
    payload["adb_output"] = text.strip()[-800:]
    if trust_class == "install_refused_signature_conflict":
        payload["recommended_next_action"] = "reinstall_with_uninstallFirst_and_approve_after_accepting_data_loss"
        payload["data_loss_warning"] = (
            "The installed app is signed with a different key (for example a store-signed build). Replacing it "
            "uninstalls it first, which deletes its local data and login."
        )
    elif trust_class == "install_refused_downgrade":
        payload["recommended_next_action"] = "retry_with_allowDowngrade"
    elif not failure_code:
        payload["result_trust_class"] = "install_transport_failed"
        payload["recommended_next_action"] = "check_adb_devices_then_retry_install"
    raise ToolInvocationError("device_install_refused", f"Install refused: {failure_code or 'unknown'}.", payload)


def compile_verify(serial: str, package: str) -> dict[str, Any]:
    shell(serial, f"cmd package compile -m verify -f {package}", timeout_seconds=300)
    status = parse_dexopt_status(shell(serial, "dumpsys package dexopt", timeout_seconds=60), package)
    return {"dexopt_status": status, "dexopt_verified": status in {"verify", "speed-profile", "speed", "everything"}}


class LogcatStream:
    def __init__(self, serial: str, path: Path, *, clear: bool = True, buffer_size: str = "") -> None:
        self.serial = serial
        self.path = path
        if buffer_size:
            run_adb(["logcat", "-G", buffer_size], serial=serial, timeout_seconds=15)
        if clear:
            run_adb(["logcat", "-c"], serial=serial, timeout_seconds=15)
        self._handle = path.open("wb")
        self._process = subprocess.Popen(
            [require_adb(), "-s", serial, "logcat", "-v", "monotonic"],
            stdin=subprocess.DEVNULL,
            stdout=self._handle,
            stderr=subprocess.DEVNULL,
            **hidden_window_subprocess_kwargs(),
        )

    def lines(self) -> list[str]:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def stop(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._handle.close()


class FrameSampler:
    def __init__(self, serial: str, package: str, raw_path: Path, interval: float = FRAME_SAMPLE_INTERVAL_SECONDS) -> None:
        self.serial = serial
        self.package = package
        self.raw_path = raw_path
        self.interval = interval
        self.accumulator = PresentAccumulator()
        self.layer = ""
        self.layer_basis = ""
        self.layers_seen: list[str] = []
        self.refresh_ns = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        with self.raw_path.open("a", encoding="utf-8") as raw:
            while not self._stop.is_set():
                if self.layer_basis not in SURFACE_LAYER_BASES:
                    listing = run_adb(["shell", "dumpsys SurfaceFlinger --list"], serial=self.serial, timeout_seconds=10)
                    layer, basis = select_app_layer(listing.stdout, self.package)
                    if layer and layer != self.layer:
                        self.layer, self.layer_basis = layer, basis
                        self.layers_seen.append(layer)
                if self.layer:
                    sample = run_adb(
                        ["shell", device_shell_command(["dumpsys", "SurfaceFlinger", "--latency", self.layer])],
                        serial=self.serial,
                        timeout_seconds=10,
                    )
                    refresh_ns, presents = parse_latency(sample.stdout)
                    self.refresh_ns = refresh_ns or self.refresh_ns
                    self.accumulator.add_sample(presents)
                    raw.write(json.dumps({"t": time.time(), "layer": self.layer, "presents": presents}) + "\n")
                self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=15)


def wait_for(predicate: Callable[[], bool], timeout_seconds: float, poll: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll)
    return predicate()


def launch_and_measure(
    *,
    serial: str,
    package: str,
    activity: str,
    unity_args: list[str],
    marker: str,
    marker_timeout_seconds: float,
    tail_seconds: float,
    session_dir: Path,
    run_label: str,
    measure_frames: bool,
    mode: str = "cold",
) -> dict[str, Any]:
    if mode == "cold":
        shell(serial, f"am force-stop {package}")
    elif mode == "warm":
        shell(serial, "input keyevent KEYCODE_HOME")
    logcat_path = session_dir / f"{run_label}_logcat.txt"
    stream = LogcatStream(serial, logcat_path)
    sampler = FrameSampler(serial, package, session_dir / f"{run_label}_frames.jsonl") if measure_frames else None
    try:
        time.sleep(0.3)
        if sampler:
            sampler.start()
        launch_output = shell(serial, build_launch_shell_command(package, activity, unity_args), timeout_seconds=60)
        found = False
        if marker:
            found = wait_for(lambda: find_logcat_marker(stream.lines(), marker)[0] is not None, marker_timeout_seconds)
        if tail_seconds > 0:
            time.sleep(tail_seconds)
    finally:
        if sampler:
            sampler.stop()
        stream.stop()

    lines = stream.lines()
    start_s, start_line = find_activity_start(lines, package)
    marker_s, marker_line = find_logcat_marker(lines, marker, after=start_s) if marker else (None, "")
    result: dict[str, Any] = {
        "run": run_label,
        "mode": mode,
        "launch_monotonic_s": start_s,
        "marker_monotonic_s": marker_s,
        "marker_found": marker_s is not None,
        "ready_seconds": round(marker_s - start_s, 3) if marker_s is not None and start_s is not None else None,
        "marker_line": marker_line[:240],
        "launch_line": start_line[:240],
        "logcat_path": str(logcat_path),
        "result_trust_class": "device_truth_confirmed" if marker_s is not None else ("device_marker_timeout" if marker else "device_launched"),
    }
    am_times = parse_am_start_times(launch_output)
    if "TotalTime" in am_times:
        result["am_total_time_ms"] = am_times["TotalTime"]
    if marker and not found and marker_s is None:
        result["marker_timeout_seconds"] = marker_timeout_seconds
    if sampler:
        window_end = marker_s if marker_s is not None else None
        result["frame_layer"] = sampler.layer
        result["frame_layer_basis"] = sampler.layer_basis
        result["frame_layers_seen"] = sampler.layers_seen
        result["frame_samples"] = sampler.accumulator.sample_count
        result["frame_sample_holes"] = sampler.accumulator.sample_gaps
        before_marker = frame_gap_stats(
            sampler.accumulator.sorted_presents(),
            window_start_s=start_s,
            window_end_s=window_end,
            sample_gaps=sampler.accumulator.sample_gaps,
        )
        result["frames_until_marker"] = before_marker
        result["longest_gap_before_marker_ms"] = before_marker["gap_max_ms"] if before_marker["frames"] > 1 else None
        if not sampler.layer:
            result["frame_pacing_trust_class"] = "frame_layer_not_found"
        elif before_marker["frames"] < 2:
            result["frame_pacing_trust_class"] = "frame_layer_no_presents"
        else:
            result["frame_pacing_trust_class"] = "device_truth_confirmed"
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return value.split()
    return []


def _package_and_activity(project_root: Path, arguments: dict[str, Any]) -> tuple[str, str, str]:
    package = str(arguments.get("package") or "").strip()
    if not package:
        raise ToolInvocationError("device_package_required", "package is required.", {})
    profile = package_profile(project_root, package)
    activity = str(arguments.get("activity") or profile.get("activity") or "").strip()
    marker = str(arguments.get("marker") or profile.get("readyMarker") or "").strip()
    return package, activity, marker


def tool_device_list(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    adb, source = locate_adb()
    if not adb:
        require_adb()
    devices = list_devices(adb)
    if bool(arguments.get("describe")):
        for device in devices:
            if device["ready"]:
                device["descriptor"] = device_descriptor(device["serial"])
    return {
        "operation": "device.list",
        "schema_version": DEVICE_SCHEMA_VERSION,
        "adb_path": adb,
        "adb_source": source,
        "devices": devices,
        "ready_count": sum(1 for device in devices if device["ready"]),
        "allowed_packages": allowed_packages(project_root),
    }


def tool_device_install(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    serial = resolve_device(arguments)
    package = str(arguments.get("package") or "").strip()
    apk = Path(str(arguments.get("apkPath") or "")).expanduser()
    if not apk.is_absolute():
        apk = (project_root / apk).resolve()
    payload = install_apk(project_root, serial, arguments, apk, package)
    if package and bool(arguments.get("compileVerify", True)):
        payload.update(compile_verify(serial, package))
    return payload


def tool_device_app(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "").strip()
    serial = resolve_device(arguments)
    package, activity, marker = _package_and_activity(project_root, arguments)
    if operation == "info":
        info = installed_versions(serial, package)
        pid = shell(serial, f"pidof {package}").strip()
        dexopt = parse_dexopt_status(shell(serial, "dumpsys package dexopt", timeout_seconds=60), package)
        return {"operation": "device.app.info", "serial": serial, "package": package, **info,
                "installed": bool(info.get("version_code")), "running_pid": pid, "dexopt_status": dexopt}
    if operation == "stop":
        require_mutation(arguments, "device.app.stop")
        shell(serial, f"am force-stop {package}")
        return {"operation": "device.app.stop", "serial": serial, "package": package, "result_trust_class": "device_truth_confirmed"}
    if operation in {"clear_data", "uninstall"}:
        require_destructive(project_root, arguments, f"device.app.{operation}", package)
        if operation == "clear_data":
            output = shell(serial, f"pm clear {package}")
        else:
            output = run_adb(["uninstall", package], serial=serial, timeout_seconds=120).stdout
        return {"operation": f"device.app.{operation}", "serial": serial, "package": package,
                "adb_output": output.strip()[-200:], "result_trust_class": "device_truth_confirmed" if "Success" in output else "device_command_failed"}
    if operation == "launch":
        require_mutation(arguments, "device.app.launch")
        session = new_session_dir(project_root, f"launch_{package}")
        result = launch_and_measure(
            serial=serial,
            package=package,
            activity=activity,
            unity_args=_string_list(arguments.get("unityArgs")),
            marker=marker,
            marker_timeout_seconds=float(arguments.get("timeoutSeconds") or 60),
            tail_seconds=float(arguments.get("tailSeconds") or 0),
            session_dir=session,
            run_label="launch",
            measure_frames=bool(arguments.get("measureFrames")),
            mode=str(arguments.get("mode") or "cold"),
        )
        return {"operation": "device.app.launch", "serial": serial, "package": package, "session_dir": str(session), **result}
    raise ToolInvocationError("device_operation_invalid", "operation must be launch, stop, info, clear_data or uninstall.", {"operation": operation})


def tool_device_logcat(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "").strip()
    if operation in {"grep", "tail"}:
        path = Path(str(arguments.get("path") or ""))
        if not path.is_file():
            raise ToolInvocationError("device_logcat_file_missing", "path must point to a captured logcat file.", {"path": str(path)})
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        limit = int(arguments.get("maxLines") or 50)
        if operation == "tail":
            selected = lines[-limit:]
        else:
            regex = re.compile(str(arguments.get("pattern") or "."))
            selected = [line for line in lines if regex.search(line)][:limit]
        return {"operation": f"device.logcat.{operation}", "path": str(path), "line_count": len(lines), "lines": selected}
    if operation == "capture":
        serial = resolve_device(arguments)
        session = new_session_dir(project_root, "logcat")
        path = session / "logcat.txt"
        stream = LogcatStream(serial, path, clear=bool(arguments.get("clear", False)), buffer_size=str(arguments.get("bufferSize") or ""))
        stop_when = str(arguments.get("stopWhen") or "")
        duration = float(arguments.get("durationSeconds") or 10)
        try:
            if stop_when:
                matched = wait_for(lambda: find_logcat_marker(stream.lines(), stop_when)[0] is not None, duration)
            else:
                time.sleep(duration)
                matched = False
        finally:
            stream.stop()
        return {"operation": "device.logcat.capture", "serial": serial, "path": str(path),
                "line_count": len(stream.lines()), "stop_when_matched": matched}
    raise ToolInvocationError("device_operation_invalid", "operation must be capture, grep or tail.", {"operation": operation})


def tool_device_files(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "").strip()
    serial = resolve_device(arguments)
    remote = str(arguments.get("remotePath") or "").strip()
    if not remote.startswith(PULL_ALLOWED_PREFIXES):
        raise ToolInvocationError(
            "device_path_not_allowed",
            "remotePath must be under the app's external files dir, Download or /data/local/tmp.",
            {"remotePath": remote, "allowed_prefixes": list(PULL_ALLOWED_PREFIXES)},
        )
    if operation == "list":
        output = shell(serial, device_shell_command(["ls", "-la", remote]))
        return {"operation": "device.files.list", "serial": serial, "remote_path": remote, "entries": output.splitlines()[:200]}
    if operation == "pull":
        session = new_session_dir(project_root, "pull")
        result = run_adb(["pull", remote, str(session)], serial=serial, timeout_seconds=float(arguments.get("timeoutSeconds") or 300))
        pulled = sorted(str(path) for path in session.rglob("*") if path.is_file())
        if not result.ok or not pulled:
            raise ToolInvocationError("device_pull_failed", (result.stderr or result.stdout).strip()[-400:] or "nothing pulled", {"remotePath": remote})
        return {"operation": "device.files.pull", "serial": serial, "remote_path": remote, "local_files": pulled[:100], "session_dir": str(session)}
    raise ToolInvocationError("device_operation_invalid", "operation must be pull or list.", {"operation": operation})


def tool_device_screen(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    serial = resolve_device(arguments)
    session = new_session_dir(project_root, "screenshot")
    path = session / "screenshot.png"
    result = run_adb(["exec-out", "screencap", "-p"], serial=serial, timeout_seconds=30, binary=True)
    data = result.stdout if isinstance(result.stdout, (bytes, bytearray)) else b""
    if not result.ok or not data.startswith(b"\x89PNG"):
        raise ToolInvocationError("device_screenshot_failed", result.stderr.strip() or "screencap returned no PNG", {"serial": serial})
    path.write_bytes(data)
    descriptor = device_descriptor(serial)
    if arguments.get("buildRevision"):
        descriptor["build_revision"] = str(arguments.get("buildRevision"))
    return {"operation": "device.screen.screenshot", "serial": serial, "path": str(path), "bytes": len(data),
            "capture_lane": "device", "device": descriptor}


def tool_device_frame_pacing(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    serial = resolve_device(arguments)
    package = str(arguments.get("package") or "").strip()
    if not package:
        raise ToolInvocationError("device_package_required", "package is required.", {})
    session = new_session_dir(project_root, f"frames_{package}")
    sampler = FrameSampler(serial, package, session / "frames.jsonl", float(arguments.get("intervalSeconds") or FRAME_SAMPLE_INTERVAL_SECONDS))
    sampler.start()
    time.sleep(float(arguments.get("durationSeconds") or 10))
    sampler.stop()
    stats = frame_gap_stats(sampler.accumulator.sorted_presents(), sample_gaps=sampler.accumulator.sample_gaps)
    trust = "device_truth_confirmed" if stats["frames"] > 1 else ("frame_layer_not_found" if not sampler.layer else "frame_layer_no_presents")
    return {"operation": "device.frame_pacing.capture", "serial": serial, "package": package, "layer": sampler.layer,
            "layer_basis": sampler.layer_basis, "refresh_period_ns": sampler.refresh_ns, "samples": sampler.accumulator.sample_count,
            "sample_holes": sampler.accumulator.sample_gaps, "result_trust_class": trust, "raw_path": str(session / "frames.jsonl"), **stats}


def tool_device_metrics(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    serial = resolve_device(arguments)
    package = str(arguments.get("package") or "").strip()
    kinds = _string_list(arguments.get("kinds")) or ["meminfo", "thermal", "cpu"]
    payload: dict[str, Any] = {"operation": "device.metrics", "serial": serial, "package": package, "captured_at_utc": utc_now()}
    if "meminfo" in kinds and package:
        payload["meminfo"] = parse_meminfo(shell(serial, f"dumpsys meminfo {package}", timeout_seconds=60))
    if "thermal" in kinds:
        payload["thermal"] = parse_thermal(shell(serial, "dumpsys thermalservice", timeout_seconds=30))
    if "cpu" in kinds and package:
        payload["cpu"] = parse_top_for_package(shell(serial, "top -b -n 1", timeout_seconds=30), package)
    return payload


def tool_device_coldstart_ab(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    require_mutation(arguments, "device.coldstart_ab")
    serial = resolve_device(arguments)
    package, activity, marker = _package_and_activity(project_root, arguments)
    if not marker:
        raise ToolInvocationError("device_marker_required", "marker (a logcat regex for app-ready) is required.", {})
    builds = arguments.get("builds")
    if not isinstance(builds, list) or not builds:
        raise ToolInvocationError("device_builds_required", "builds must list at least one {label, apkPath}.", {})
    runs = int(arguments.get("runs") or 3)
    session = new_session_dir(project_root, f"coldstart_ab_{package}")
    daemon_restarts_before = len(ADB_DAEMON_RESTARTS)
    descriptor = device_descriptor(serial)
    per_build: list[dict[str, Any]] = []
    for index, build in enumerate(builds):
        label = str((build or {}).get("label") or f"build{index + 1}")
        apk = str((build or {}).get("apkPath") or "").strip()
        build_record: dict[str, Any] = {"label": label, "apk_path": apk}
        if apk:
            apk_path = Path(apk).expanduser()
            if not apk_path.is_absolute():
                apk_path = (project_root / apk_path).resolve()
            build_record["install"] = install_apk(project_root, serial, arguments, apk_path, package)
        if bool(arguments.get("compileVerify", True)):
            build_record.update(compile_verify(serial, package))
        run_results = []
        for run in range(1, runs + 1):
            run_results.append(
                launch_and_measure(
                    serial=serial,
                    package=package,
                    activity=activity,
                    unity_args=_string_list((build or {}).get("unityArgs") or arguments.get("unityArgs")),
                    marker=marker,
                    marker_timeout_seconds=float(arguments.get("timeoutSeconds") or 60),
                    tail_seconds=float(arguments.get("tailSeconds") or 3),
                    session_dir=session,
                    run_label=f"{label}_run{run}",
                    measure_frames=bool(arguments.get("measureFrames", True)),
                )
            )
            time.sleep(float(arguments.get("sleepBetweenSeconds") or 2))
        build_record["runs"] = run_results
        build_record["summary"] = summarize_build_runs(run_results)
        per_build.append(build_record)
        (session / "coldstart_ab.partial.json").write_text(json.dumps(per_build, indent=2), encoding="utf-8")

    table = [
        {
            "build": record["label"],
            "ready_seconds": record["summary"]["ready_seconds"],
            "ready_seconds_median": record["summary"]["ready_seconds_median"],
            "longest_gap_before_marker_ms": record["summary"]["longest_gap_before_marker_ms"],
            "longest_gap_before_marker_ms_median": record["summary"]["longest_gap_before_marker_ms_median"],
            "dexopt_status": record.get("dexopt_status", ""),
        }
        for record in per_build
    ]
    report = {
        "operation": "device.coldstart_ab",
        "schema_version": DEVICE_SCHEMA_VERSION,
        "serial": serial,
        "device": descriptor,
        "package": package,
        "marker": marker,
        "runs_per_build": runs,
        "table": table,
        "builds": per_build,
        "session_dir": str(session),
        "result_trust_class": "device_truth_confirmed"
        if all(record["summary"]["runs_with_marker"] == runs for record in per_build)
        else "device_marker_timeout",
    }
    report["adb_daemon_restarts_observed"] = len(ADB_DAEMON_RESTARTS) - daemon_restarts_before
    if report["adb_daemon_restarts_observed"]:
        report["adb_daemon_warning"] = (
            "The adb server restarted during the run (another adb client, often an editor's bundled Android SDK, "
            "can restart it). Install, dexopt and timing results of the affected runs need a re-check."
        )
    report_path = session / "coldstart_ab.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if bool(arguments.get("registerArtifact", True)):
        try:
            report["artifact"] = register_artifact(
                project_root=project_root,
                artifact_path=str(report_path),
                destination="library",
                kind="device_coldstart_ab",
                producer="unity_device_coldstart_ab",
                artifact_schema_version=DEVICE_SCHEMA_VERSION,
                metadata={"package": package, "serial": serial, "builds": [record["label"] for record in per_build]},
            ).get("registry_path", "")
        except Exception as exc:
            report["artifact_error"] = type(exc).__name__
    report["report_path"] = str(report_path)
    compact = dict(report)
    if not bool(arguments.get("includeFullPayload")):
        compact["builds"] = [
            {key: value for key, value in record.items() if key != "runs"} for record in per_build
        ]
    return compact


DEVICE_TOOL_HANDLERS: dict[str, Callable[[Path, dict[str, Any]], dict[str, Any]]] = {
    "unity_device_list": tool_device_list,
    "unity_device_install": tool_device_install,
    "unity_device_app": tool_device_app,
    "unity_device_logcat": tool_device_logcat,
    "unity_device_files": tool_device_files,
    "unity_device_screen": tool_device_screen,
    "unity_device_frame_pacing": tool_device_frame_pacing,
    "unity_device_metrics": tool_device_metrics,
    "unity_device_coldstart_ab": tool_device_coldstart_ab,
}
