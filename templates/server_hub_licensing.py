from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import time
from typing import Any, Callable

from server_core import ToolInvocationError, hidden_window_subprocess_kwargs, is_windows_like_host
from server_host_platform import current_host_platform_adapter, is_wsl


LICENSING_CLIENT_PATTERN = re.compile(r"(?:Unity[./\\])?Licensing[./\\]Client", re.IGNORECASE)
NAMED_PIPE_PATTERN = re.compile(
    r"(?:--namedPipe|-namedPipe)\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))",
    re.IGNORECASE,
)
VALID_CHANNEL_PATTERN = re.compile(r"^(?:Unity-)?LicenseClient-[A-Za-z0-9._-]+$")
TASKKILL_TIMEOUT_SECONDS = 15.0


def _fingerprint(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def _named_pipe_from_command(command: str) -> str:
    if not LICENSING_CLIENT_PATTERN.search(str(command or "")):
        return ""
    match = NAMED_PIPE_PATTERN.search(str(command or ""))
    if not match:
        return ""
    channel = next((value for value in match.groups() if value), "")
    return channel if VALID_CHANNEL_PATTERN.fullmatch(channel) else ""


def _is_unity_hub_command(command: str) -> bool:
    normalized = str(command or "").replace("\\", "/").strip().lower()
    if normalized.startswith('"'):
        normalized = normalized[1:]
    return bool(
        re.match(r"^/(?:[^\"\r\n]*/)?unity hub\.app/contents/macos/unity hub(?:\"|\s|$)", normalized)
        or re.match(r"^(?:[a-z]:/|//)[^\"\r\n]*/unity hub\.exe(?:\"|\s|$)", normalized)
        or re.match(r"^/[^\"\s]*/unityhub(?:-bin|[^/\"\s]*\.appimage)?(?:\"|\s|$)", normalized)
    )


def _normalized_processes(report: dict[str, Any]) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    raw_processes = report.get("processes") if isinstance(report, dict) else []
    for entry in raw_processes or []:
        if not isinstance(entry, dict):
            continue
        try:
            pid = int(entry.get("pid") or 0)
            ppid = int(entry.get("ppid") or 0)
        except (TypeError, ValueError):
            continue
        command = str(entry.get("command") or "").strip()
        if pid > 0 and command:
            processes.append({"pid": pid, "ppid": max(0, ppid), "command": command})
    if processes:
        return processes

    for entry in (report.get("commands") if isinstance(report, dict) else []) or []:
        try:
            pid = int(entry[0])
            command = str(entry[1]).strip()
        except (IndexError, TypeError, ValueError):
            continue
        if pid > 0 and command:
            processes.append({"pid": pid, "ppid": 0, "command": command})
    return processes


def _live_licensing_candidates(
    report: dict[str, Any],
    pid_is_alive_fn: Callable[[int], bool],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    processes = _normalized_processes(report)
    by_pid = {int(entry["pid"]): entry for entry in processes}
    candidates: list[dict[str, Any]] = []
    for entry in processes:
        channel = _named_pipe_from_command(str(entry.get("command") or ""))
        if not channel:
            continue
        pid = int(entry.get("pid") or 0)
        try:
            live = bool(pid_is_alive_fn(pid))
        except Exception:
            live = False
        if not live:
            continue
        parent = by_pid.get(int(entry.get("ppid") or 0), {})
        try:
            parent_live = int(parent.get("pid") or 0) > 0 and bool(pid_is_alive_fn(int(parent["pid"])))
        except Exception:
            parent_live = False
        candidates.append(
            {
                **entry,
                "channel": channel,
                "channel_fingerprint": _fingerprint(channel),
                "command_fingerprint": _fingerprint(str(entry.get("command") or "")),
                "hub_owned": parent_live and _is_unity_hub_command(str(parent.get("command") or "")),
                "parent_pid": int(parent.get("pid") or 0),
            }
        )
    return candidates, by_pid


def resolve_hub_licensing_ipc(
    process_report: dict[str, Any] | None = None,
    *,
    pid_is_alive_fn: Callable[[int], bool] | None = None,
) -> tuple[dict[str, Any], str]:
    adapter = current_host_platform_adapter()
    report = process_report if process_report is not None else adapter.list_process_commands_report()
    public: dict[str, Any] = {
        "source": "host_process_table",
        "platform_kind": str(report.get("platform_kind") or adapter.platform_kind),
        "process_visibility_available": bool(report.get("available")),
        "candidate_count": 0,
        "other_licensing_candidate_count": 0,
        "confidence": "none",
        "validation_result": "not_attempted",
        "status": "unavailable",
        "action_classification": "manual_user_action_required",
        "raw_channel_exposed": False,
    }
    if not bool(report.get("available")):
        public["validation_result"] = str(report.get("error_code") or "process_visibility_restricted")
        public["required_human_action"] = "restore_host_process_visibility"
        return public, ""

    candidates, _ = _live_licensing_candidates(report, pid_is_alive_fn or adapter.pid_is_alive)
    hub_candidates = [candidate for candidate in candidates if bool(candidate.get("hub_owned"))]
    public["candidate_count"] = len(hub_candidates)
    public["other_licensing_candidate_count"] = len(candidates) - len(hub_candidates)
    public["candidate_fingerprints"] = [
        str(candidate.get("channel_fingerprint") or "") for candidate in hub_candidates
    ]
    if len(hub_candidates) == 1:
        candidate = hub_candidates[0]
        public.update(
            {
                "status": "resolved",
                "confidence": "high",
                "validation_result": "live_hub_parent_and_client_identity_verified",
                "action_classification": "machine_recoverable_with_hub_session",
                "selected_candidate_fingerprint": str(candidate.get("channel_fingerprint") or ""),
                "required_human_action": "none",
            }
        )
        return public, str(candidate.get("channel") or "")
    if not hub_candidates:
        public.update(
            {
                "status": "no_hub_session",
                "validation_result": "no_live_hub_owned_licensing_client",
                "required_human_action": "start_or_sign_in_to_unity_hub",
            }
        )
        return public, ""

    public.update(
        {
            "status": "ambiguous",
            "confidence": "low",
            "validation_result": "multiple_live_hub_owned_candidates_refused",
            "required_human_action": "close_extra_unity_hub_sessions_or_pass_explicit_licensing_ipc",
        }
    )
    return public, ""


def editor_licensing_channel(channel: str) -> str:
    """The editor omits Unity- from the OS named pipe; discovery retains it."""
    return channel[len("Unity-"):] if channel.startswith("Unity-LicenseClient-") else channel


def unity_argument_value(unity_args: list[str], option_name: str) -> str:
    for index, value in enumerate(unity_args[:-1]):
        if str(value).lower() == option_name.lower():
            return str(unity_args[index + 1])
    return ""


def sanitize_unity_args(unity_args: list[str]) -> list[str]:
    sanitized = [str(value) for value in unity_args]
    for index, value in enumerate(sanitized[:-1]):
        if value.lower() == "-licensingipc":
            sanitized[index + 1] = "<redacted>"
    return sanitized


def sanitize_launch_command(command: list[str]) -> list[str]:
    return sanitize_unity_args([str(value) for value in command])


def prepare_hub_licensing_unity_args(
    unity_args: list[str],
    process_report: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    normalized = [str(value) for value in unity_args]
    explicit_channel = unity_argument_value(normalized, "-licensingIpc")
    if explicit_channel:
        for index, value in enumerate(normalized[:-1]):
            if value.lower() == "-licensingipc":
                normalized[index + 1] = editor_licensing_channel(normalized[index + 1])
        return normalized, {
            "unity_argument_forwarded": True,
            "forwarded_channel_fingerprint": _fingerprint(editor_licensing_channel(explicit_channel)),
            "source": "explicit_unity_argument",
            "status": "resolved",
            "candidate_count": 1,
            "confidence": "operator_supplied",
            "validation_result": "not_host_validated",
            "action_classification": "operator_managed_explicit_channel",
            "selected_candidate_fingerprint": _fingerprint(explicit_channel),
            "raw_channel_exposed": False,
            "required_human_action": "none",
        }

    resolution, channel = resolve_hub_licensing_ipc(process_report)
    if str(resolution.get("status") or "") == "ambiguous":
        raise ToolInvocationError(
            "licensing_ipc_ambiguous",
            "Multiple live Unity Hub licensing channels were found; refusing to guess which session owns this launch.",
            {"licensing_ipc_resolution": resolution},
        )
    if channel:
        normalized.extend(["-licensingIpc", editor_licensing_channel(channel)])
        resolution["forwarded_channel_fingerprint"] = _fingerprint(editor_licensing_channel(channel))
        resolution["unity_argument_forwarded"] = True
    else:
        resolution["unity_argument_forwarded"] = False
    return normalized, resolution


def licensing_client_pid_snapshot(process_report: dict[str, Any] | None = None) -> list[int]:
    adapter = current_host_platform_adapter()
    report = process_report if process_report is not None else adapter.list_process_commands_report()
    candidates, _ = _live_licensing_candidates(report, adapter.pid_is_alive)
    return sorted({int(candidate.get("pid") or 0) for candidate in candidates if int(candidate.get("pid") or 0) > 0})


def discover_owned_licensing_children(
    *,
    baseline_pids: list[int],
    editor_pid: int,
    process_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if editor_pid <= 0:
        return []
    adapter = current_host_platform_adapter()
    report = process_report if process_report is not None else adapter.list_process_commands_report()
    candidates, by_pid = _live_licensing_candidates(report, adapter.pid_is_alive)
    baseline = {int(pid) for pid in baseline_pids if int(pid) > 0}
    owned: list[dict[str, Any]] = []
    for candidate in candidates:
        pid = int(candidate.get("pid") or 0)
        if pid in baseline or bool(candidate.get("hub_owned")):
            continue
        ancestor_pid = int(candidate.get("ppid") or 0)
        ancestry: list[int] = []
        for _ in range(8):
            if ancestor_pid <= 0 or ancestor_pid in ancestry:
                break
            ancestry.append(ancestor_pid)
            if ancestor_pid == editor_pid:
                owned.append(
                    {
                        "pid": pid,
                        "spawned_after_launch": True,
                        "editor_ancestor_pid": editor_pid,
                        "command_fingerprint": str(candidate.get("command_fingerprint") or ""),
                        "channel_fingerprint": str(candidate.get("channel_fingerprint") or ""),
                        "identity_class": "unity_licensing_client",
                    }
                )
                break
            ancestor_pid = int((by_pid.get(ancestor_pid) or {}).get("ppid") or 0)
    return owned


def _terminate_verified_pid(pid: int, timeout_ms: int) -> bool:
    adapter = current_host_platform_adapter()
    if pid <= 0 or not adapter.pid_is_alive(pid):
        return True
    wsl_host = is_wsl()
    if wsl_host or is_windows_like_host():
        # WSL candidates come from the Windows process table, so these are taskkill pids, never Linux pids.
        for command in (["taskkill.exe", "taskkill"] if wsl_host else ["taskkill", "taskkill.exe"]):
            try:
                completed = subprocess.run(
                    [command, "/F", "/PID", str(pid)],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=TASKKILL_TIMEOUT_SECONDS,
                    **hidden_window_subprocess_kwargs(),
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if completed.returncode == 0:
                break
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return not adapter.pid_is_alive(pid)

    deadline = time.time() + max(1.0, int(timeout_ms or 0) / 1000.0)
    while time.time() < deadline:
        if not adapter.pid_is_alive(pid):
            return True
        time.sleep(0.1)
    return not adapter.pid_is_alive(pid)


def cleanup_owned_licensing_children(session: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    records = [entry for entry in session.get("owned_licensing_children") or [] if isinstance(entry, dict)]
    result: dict[str, Any] = {
        "tracked_count": len(records),
        "terminated_count": 0,
        "already_exited_count": 0,
        "refused_count": 0,
        "terminated_pids": [],
        "refusals": [],
    }
    if not records:
        result["classification"] = "no_helper_owned_licensing_children"
        return result

    adapter = current_host_platform_adapter()
    report = adapter.list_process_commands_report()
    candidates, by_pid = _live_licensing_candidates(report, adapter.pid_is_alive)
    by_candidate_pid = {int(entry.get("pid") or 0): entry for entry in candidates}
    for record in records:
        pid = int(record.get("pid") or 0)
        if pid <= 0 or not adapter.pid_is_alive(pid):
            result["already_exited_count"] += 1
            continue
        current = by_candidate_pid.get(pid)
        parent = by_pid.get(int((current or {}).get("ppid") or 0), {})
        identity_matches = bool(
            current
            and str(current.get("command_fingerprint") or "") == str(record.get("command_fingerprint") or "")
            and not _is_unity_hub_command(str(parent.get("command") or ""))
            and bool(record.get("spawned_after_launch"))
        )
        if not identity_matches:
            result["refused_count"] += 1
            result["refusals"].append({"pid": pid, "reason": "current_identity_or_ownership_not_verified"})
            continue
        if _terminate_verified_pid(pid, timeout_ms):
            result["terminated_count"] += 1
            result["terminated_pids"].append(pid)
        else:
            result["refused_count"] += 1
            result["refusals"].append({"pid": pid, "reason": "verified_termination_did_not_complete"})
    result["classification"] = (
        "helper_owned_licensing_children_cleaned"
        if result["refused_count"] == 0
        else "helper_owned_licensing_cleanup_incomplete"
    )
    return result
