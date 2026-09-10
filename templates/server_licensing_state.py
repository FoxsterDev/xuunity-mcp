"""Host licensing coordination and evidence; contains no Unity package dependencies."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
import threading
from collections import OrderedDict
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from server_core import ToolInvocationError


def licensing_host_state_dir() -> Path:
    try:
        home = str(Path.home())
    except (OSError, RuntimeError):
        home = ""
    identity = (
        home
        or os.environ.get("USERPROFILE")
        or os.environ.get("HOME")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or (f"uid:{os.getuid()}" if hasattr(os, "getuid") else "unknown-user")
    )
    user = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    # Do not use process-specific TMPDIR/TEMP: different helper environments
    # must still contend on the same per-user lock. Native Windows uses its
    # user cache; POSIX uses the shared temporary filesystem.
    if os.name == "nt":
        cache_root = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.environ.get("TMP")
        base = Path(cache_root) if cache_root else Path(tempfile.gettempdir())
    else:
        base = Path("/tmp")
    return base / ("xuunity-licensing-" + user)


@contextmanager
def licensing_host_lock(timeout_seconds: float = 35.0):
    """OS lock shared by threads and processes, automatically released on exit/crash."""
    directory = licensing_host_state_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "probe.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + timeout_seconds
        waited = False
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ToolInvocationError(
                        "licensing_busy", "A host licensing probe or editor launch is active; retry after it completes."
                    ) from exc
                waited = True
                time.sleep(0.05)
        try:
            yield waited
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def license_probe_active() -> bool:
    # A non-blocking lock check also avoids stale PID marker files after a crash.
    try:
        with licensing_host_lock(0):
            return False
    except ToolInvocationError:
        return True


def guard_editor_licensing_launch(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with licensing_host_lock(0):
            result = function(*args, **kwargs)
        if result.get("reused_existing_editor"):
            from server_editor_host import try_read_host_editor_session_state
            project_root = args[0] if args else kwargs["project_root"]
            session = try_read_host_editor_session_state(project_root) or {}
            if int(session.get("editor_pid") or 0) != int(result.get("editor_pid") or 0):
                session = {}
            result.update(editor_license_evidence(result.get("editor_log_path") or "", session))
            result["opened_by_host"] = bool(session.get("opened_by_host"))
        return result
    return guarded


ENTITLEMENT_SUCCESS = re.compile(
    r"Successfully resolved entitlement details|Successfully updated license|\[Licensing::Module\] License group:",
    re.IGNORECASE,
)
PACKAGE_REFUSAL = re.compile(r"packages were not registered because your license doesn't allow it", re.IGNORECASE)
LICENSE_FAILURE = re.compile(
    r"Channel\s+[^\r\n]+\s+doesn't exist|Licensing(?:\s+initialization)?\s+failed|"
    r"waiting for Licensing to initialize|No valid Unity (?:Editor )?license|"
    r"connection with (?:the )?Unity Licensing Client has been lost|"
    r"re-connection attempt was UN-successful|"
    r"Unity has not been activated with a valid License|No ULF license found|Access token is unavailable|"
    r"accept.*terms|terms.*accept|sign in to (?:the )?Unity Hub|activation.*required",
    re.IGNORECASE,
)


def license_state_from_log(text: str) -> str:
    state = "unknown"
    for line in text.splitlines():
        # Refused packages remain missing even if licensing later recovers.
        if PACKAGE_REFUSAL.search(line):
            return "unlicensed"
        if ENTITLEMENT_SUCCESS.search(line):
            state = "licensed"
        elif LICENSE_FAILURE.search(line):
            state = "unlicensed"
    return state


_LOG_CACHE: OrderedDict = OrderedDict()
_LOG_CACHE_LOCK = threading.Lock()
_LOG_EVIDENCE = re.compile(
    r"Licens|entitlement|Access token|packages were not registered|accept.*terms|terms.*accept|activation.*required|sign in to (?:the )?Unity Hub",
    re.IGNORECASE,
)


def read_license_log(path: Path | str) -> str:
    """Retain licensing evidence and scan only appended bytes on repeated status calls."""
    if not path:
        return ""
    try:
        with _LOG_CACHE_LOCK, Path(path).open("rb") as stream:
            stat = os.fstat(stream.fileno())
            header = stream.read(256)
            key = str(path)
            cached = _LOG_CACHE.get(key, {})
            unchanged_prefix = cached.get("inode") == stat.st_ino and cached.get("header") == header
            if unchanged_prefix and cached.get("size") == stat.st_size and cached.get("mtime") == stat.st_mtime_ns:
                return cached["observed_text"]
            appended = unchanged_prefix and stat.st_size > cached.get("size", 0)
            stream.seek(cached["offset"] if appended else 0)
            lines = [cached["text"]] if appended else []
            offset = stream.tell()
            partial_evidence = False
            for raw in stream:
                # Re-read a partial final line after the next append.
                complete = raw.endswith(b"\n")
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("Unity Editor version:"):
                    lines = []
                if _LOG_EVIDENCE.search(line):
                    lines.append(line.rstrip("\r\n"))
                    partial_evidence = not complete
                if complete:
                    offset = stream.tell()
            text = "\n".join(lines)
            # Partial evidence is returned now but not retained, avoiding double counts.
            retained = "\n".join(lines[:-1]) if partial_evidence else text
            _LOG_CACHE[key] = {"inode": stat.st_ino, "header": header, "size": stat.st_size,
                               "mtime": stat.st_mtime_ns, "offset": offset, "text": retained,
                               "observed_text": text}
            _LOG_CACHE.move_to_end(key)
            while len(_LOG_CACHE) > 32:
                _LOG_CACHE.popitem(last=False)
            return text
    except OSError:
        return ""


def licensing_connection_evidence(text: str, forwarded_fingerprint: str) -> dict:
    connected = False
    missing = False
    for line in text.splitlines():
        success = re.search(r'Successfully connected to:\s*"([^"]+)"', line)
        failure = re.search(r"Channel\s+['\"]?([^'\"\s]+)['\"]?\s+doesn't exist", line)
        for match, kind in ((success, "success"), (failure, "failure")):
            if match and hashlib.sha256(match.group(1).encode("utf-8")).hexdigest()[:16] == forwarded_fingerprint:
                connected |= kind == "success"
                missing |= kind == "failure"
    return {
        "licensing_forwarded_channel_connected": connected and not missing,
        "licensing_forwarded_channel_missing": missing,
    }


def editor_license_evidence(log_path: Path | str, session: dict | None = None) -> dict:
    resolution = (session or {}).get("licensing_ipc_resolution") or {}
    fingerprint = str(resolution.get("forwarded_channel_fingerprint") or "")
    forwarded_fingerprint = fingerprint
    text = read_license_log(log_path)
    if not fingerprint:
        connections = re.findall(r'Successfully connected to:\s*"([^"]+)"', text)
        if connections:
            fingerprint = hashlib.sha256(connections[-1].encode("utf-8")).hexdigest()[:16]
    return {
        "license_state": license_state_from_log(text),
        "licensing_channel_fingerprint": str(resolution.get("selected_candidate_fingerprint") or fingerprint),
        "license_probe_active": license_probe_active(),
        **licensing_connection_evidence(text, forwarded_fingerprint),
    }


def live_editor_licensing_evidence() -> dict:
    # Lazy imports avoid the editor facade's import cycle.
    from server_editor_host_processes import classify_unity_process_role, extract_unity_project_path_from_command
    from server_host_platform import current_host_platform_adapter, host_path_to_local_path
    from server_hub_licensing import resolve_hub_licensing_ipc, _normalized_processes, _fingerprint, editor_licensing_channel, _live_licensing_candidates
    adapter = current_host_platform_adapter()
    report = adapter.list_process_commands_report()
    resolution, channel = resolve_hub_licensing_ipc(report)
    result = {"editor_live": False, "licensed_editor_live": False, "resolution": resolution}
    if not report.get("available"):
        result["visibility_unknown"] = True
        return result
    candidates, _ = _live_licensing_candidates(report, adapter.pid_is_alive)
    for entry in _normalized_processes(report):
        command = entry["command"]
        if classify_unity_process_role(command) != "main_editor" or not adapter.pid_is_alive(entry["pid"]):
            continue
        result["editor_live"] = True
        project = extract_unity_project_path_from_command(command)
        match = re.search(r'-logFile\s+(?:"([^"]+)"|([^\s]+))', command, re.IGNORECASE)
        if not match or not project or not channel:
            continue
        text = read_license_log(host_path_to_local_path(next(value for value in match.groups() if value)))
        connected_live_client = any(
            licensing_connection_evidence(text, _fingerprint(editor_licensing_channel(candidate["channel"])))["licensing_forwarded_channel_connected"]
            for candidate in candidates
        )
        if license_state_from_log(text) == "licensed" and connected_live_client:
            result["licensed_editor_live"] = True
    return result
