#!/usr/bin/env python3
"""Host-wide Unity slot lock and owned-process cleanup for the test runners.

One Unity run per machine at a time is an operating rule, not something Unity
enforces. The slot is an advisory lock file under the neutral install's state
directory; the test runners take it and refuse while another live process holds
it. ``stop-run`` ends only what a stopped run started: the children it tracked
and the Unity processes whose command line names that run's projects directory.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SCRIPT_DIR.parents[1]
TEMPLATES_DIR = SOURCE_ROOT / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_core import is_windows_like_host, reconfigure_stdio_utf8  # noqa: E402
from server_editor_host import terminate_editor_pid  # noqa: E402
from server_editor_host_processes import classify_unity_process_role, unity_command_executable  # noqa: E402
from server_host_platform import current_host_platform_adapter  # noqa: E402
from server_python_gate import neutral_install_dir  # noqa: E402

LOCK_FILE_ENV = "XUUNITY_UNITY_SLOT_LOCK_FILE"
LOCK_FILE_NAME = "unity_slot.lock.json"
LOCK_SCHEMA_VERSION = 1
EXIT_SLOT_BUSY = 3
START_TIME_TOLERANCE_SECONDS = 5.0
STOP_TIMEOUT_MS = 10000
# Shared by every editor on the host; a stopped run must not take licensing away from the others.
SHARED_PROCESS_MARKERS = ("unity.licensing.client", "unitylicensingclient", "unity hub")
UNITY_ROLES = {"main_editor", "worker"}


class UnitySlotBusy(RuntimeError):
    def __init__(self, holder: dict[str, Any]):
        super().__init__("The Unity slot is held by another live run.")
        self.holder = holder


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_lock_path() -> Path:
    explicit = os.environ.get(LOCK_FILE_ENV)
    if explicit:
        return Path(explicit).expanduser()
    return neutral_install_dir() / "state" / LOCK_FILE_NAME


def read_lock(lock_path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def holder_state(
    holder: dict[str, Any] | None,
    *,
    pid_is_alive: Callable[[int], bool],
    process_start_time: Callable[[int], float | None],
) -> str:
    """live, or the reason the lock is stale."""
    if not holder:
        return "unreadable"
    try:
        pid = int(holder.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return "no_pid"
    if not pid_is_alive(pid):
        return "holder_exited"
    recorded = holder.get("process_started_epoch")
    current = process_start_time(pid)
    if isinstance(recorded, (int, float)) and current is not None:
        if abs(float(recorded) - current) > START_TIME_TOLERANCE_SECONDS:
            return "holder_pid_reused"
    return "live"


def _adapter_callbacks() -> tuple[Callable[[int], bool], Callable[[int], float | None]]:
    adapter = current_host_platform_adapter()
    return adapter.pid_is_alive, adapter.process_start_time


def acquire_slot(
    lock_path: Path,
    *,
    pid: int,
    owner: str,
    command: str,
    pid_is_alive: Callable[[int], bool] | None = None,
    process_start_time: Callable[[int], float | None] | None = None,
) -> dict[str, Any]:
    default_alive, default_start = _adapter_callbacks()
    pid_is_alive = pid_is_alive or default_alive
    process_start_time = process_start_time or default_start
    record = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "pid": int(pid),
        "owner": str(owner),
        "command": str(command),
        "started_utc": utc_now(),
        "process_started_epoch": process_start_time(int(pid)),
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stale_reason = ""
    for _attempt in range(3):
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            holder = read_lock(lock_path)
            state = holder_state(holder, pid_is_alive=pid_is_alive, process_start_time=process_start_time)
            if state == "live":
                if int((holder or {}).get("pid") or 0) == int(pid):
                    return {"acquired": True, "reentrant": True, "lock_path": str(lock_path), "holder": holder}
                raise UnitySlotBusy(dict(holder or {}))
            stale_reason = state
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=True)
        result = {"acquired": True, "lock_path": str(lock_path), "holder": record}
        if stale_reason:
            result["stale_lock_taken_over"] = stale_reason
        return result
    raise UnitySlotBusy(dict(read_lock(lock_path) or {}))


def release_slot(lock_path: Path, *, pid: int) -> dict[str, Any]:
    holder = read_lock(lock_path)
    if holder is None:
        return {"released": False, "reason": "no_lock"}
    if int(holder.get("pid") or 0) != int(pid):
        return {"released": False, "reason": "held_by_another_pid", "holder": holder}
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    return {"released": True, "lock_path": str(lock_path)}


def slot_status(lock_path: Path) -> dict[str, Any]:
    holder = read_lock(lock_path)
    if holder is None and not lock_path.exists():
        return {"lock_path": str(lock_path), "state": "free"}
    alive, started = _adapter_callbacks()
    return {
        "lock_path": str(lock_path),
        "state": holder_state(holder, pid_is_alive=alive, process_start_time=started),
        "holder": holder or {},
    }


def record_tracked_pid(tracked_file: Path, pid: int) -> dict[str, Any]:
    _alive, process_start_time = _adapter_callbacks()
    entry = {"pid": int(pid), "process_started_epoch": process_start_time(int(pid)), "recorded_utc": utc_now()}
    tracked_file.parent.mkdir(parents=True, exist_ok=True)
    with tracked_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def read_tracked_pids(tracked_file: Path | None) -> list[dict[str, Any]]:
    if tracked_file is None:
        return []
    entries: list[dict[str, Any]] = []
    try:
        lines = tracked_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _path_key(value: str) -> str:
    return str(value).replace("\\", "/").rstrip("/").lower()


def _is_shared_process(command: str) -> bool:
    try:
        lowered = command.lower()
    except (AttributeError, SystemError):
        return True
    return any(marker in lowered for marker in SHARED_PROCESS_MARKERS)


def owned_run_processes(
    processes: list[dict[str, Any]],
    *,
    projects_root: Path,
    tracked: list[dict[str, Any]],
    process_start_time: Callable[[int], float | None],
    exclude_pids: set[int],
) -> list[dict[str, Any]]:
    """Processes this run started: verified tracked children, this run's Unity editors, and their descendants."""
    by_pid: dict[int, dict[str, Any]] = {}
    children: dict[int, list[int]] = {}
    for entry in processes:
        try:
            pid = int(entry.get("pid") or 0)
            ppid = int(entry.get("ppid") or 0)
            command = str(entry.get("command") or "")
        except (TypeError, ValueError, AttributeError):
            continue
        if pid <= 0:
            continue
        by_pid[pid] = {"pid": pid, "ppid": ppid, "command": command}
        children.setdefault(ppid, []).append(pid)

    root_key = _path_key(str(projects_root)) + "/"
    reasons: dict[int, str] = {}
    for item in tracked:
        try:
            pid = int(item.get("pid") or 0)
        except (TypeError, ValueError):
            continue
        recorded = item.get("process_started_epoch")
        if pid not in by_pid or not isinstance(recorded, (int, float)):
            continue
        current = process_start_time(pid)
        if current is not None and abs(float(recorded) - current) <= START_TIME_TOLERANCE_SECONDS:
            reasons[pid] = "tracked_child"
    for pid, entry in by_pid.items():
        try:
            role = classify_unity_process_role(entry["command"])
            references_run = root_key in (_path_key(entry["command"]) + "/")
        except (TypeError, ValueError, SystemError):
            continue
        if role in UNITY_ROLES and references_run:
            reasons.setdefault(pid, f"unity_{role}_for_run_project")

    pending = list(reasons)
    while pending:
        parent = pending.pop()
        for child in children.get(parent, []):
            if child not in reasons:
                reasons[child] = "descendant_of_owned_process"
                pending.append(child)

    owned = []
    for pid, reason in reasons.items():
        entry = by_pid[pid]
        if pid in exclude_pids or _is_shared_process(entry["command"]):
            continue
        owned.append({"pid": pid, "reason": reason, "executable": unity_command_executable(entry["command"])[-120:]})
    return sorted(owned, key=lambda item: item["pid"], reverse=True)


def stop_run(
    projects_root: Path,
    *,
    tracked_file: Path | None = None,
    timeout_ms: int = STOP_TIMEOUT_MS,
    process_report_fn: Callable[[], dict[str, Any]] | None = None,
    terminate_fn: Callable[[int, int], bool] = terminate_editor_pid,
    pid_is_alive: Callable[[int], bool] | None = None,
    process_start_time: Callable[[int], float | None] | None = None,
) -> dict[str, Any]:
    adapter = current_host_platform_adapter()
    process_report_fn = process_report_fn or adapter.list_process_commands_report
    pid_is_alive = pid_is_alive or adapter.pid_is_alive
    process_start_time = process_start_time or adapter.process_start_time
    exclude = {os.getpid(), os.getppid()}
    result: dict[str, Any] = {"projects_root": str(projects_root), "terminated": [], "survivors": []}
    for sweep in range(2):
        report = process_report_fn()
        if not bool(report.get("available")):
            result["status"] = "process_visibility_unavailable"
            return result
        owned = owned_run_processes(
            list(report.get("processes") or []),
            projects_root=projects_root,
            tracked=read_tracked_pids(tracked_file),
            process_start_time=process_start_time,
            exclude_pids=exclude,
        )
        if not owned:
            break
        for item in owned:
            stopped = bool(terminate_fn(item["pid"], timeout_ms if sweep == 0 else 2000))
            if not stopped and not is_windows_like_host():
                try:
                    os.kill(item["pid"], signal.SIGKILL)
                except OSError:
                    pass
                time.sleep(0.2)
                stopped = not pid_is_alive(item["pid"])
            (result["terminated"] if stopped else result["survivors"]).append(item)
    survivors = {item["pid"] for item in result["survivors"] if pid_is_alive(item["pid"])}
    result["survivors"] = [item for item in result["survivors"] if item["pid"] in survivors]
    result["status"] = "survivors_remain" if result["survivors"] else "stopped"
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lock-path", help="Print the slot lock file path.")
    acquire = sub.add_parser("lock-acquire", help="Take the Unity slot or refuse with the holder's details.")
    acquire.add_argument("--owner", required=True)
    acquire.add_argument("--command-text", default="")
    acquire.add_argument("--pid", type=int, default=0, help="Holder pid; defaults to the caller's parent process.")
    release = sub.add_parser("lock-release", help="Release the Unity slot when this pid holds it.")
    release.add_argument("--pid", type=int, default=0)
    sub.add_parser("lock-status", help="Report the holder and whether the lock is live or stale.")
    track = sub.add_parser("track-pid", help="Record a child the run started, with its start time.")
    track.add_argument("--tracked-file", required=True)
    track.add_argument("--pid", type=int, required=True)
    stop = sub.add_parser("stop-run", help="End the processes a stopped run started.")
    stop.add_argument("--projects-root", required=True)
    stop.add_argument("--tracked-file", default="")
    stop.add_argument("--timeout-ms", type=int, default=STOP_TIMEOUT_MS)
    for command in (acquire, release, sub.choices["lock-status"], sub.choices["lock-path"]):
        command.add_argument("--lock-file", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    reconfigure_stdio_utf8()
    args = parse_args(argv)
    lock_path = Path(args.lock_file).expanduser() if getattr(args, "lock_file", "") else default_lock_path()
    if args.command == "lock-path":
        print(lock_path.as_posix())
        return 0
    if args.command == "lock-acquire":
        try:
            payload = acquire_slot(
                lock_path, pid=args.pid or os.getppid(), owner=args.owner, command=args.command_text
            )
        except UnitySlotBusy as busy:
            print(
                json.dumps(
                    {
                        "acquired": False,
                        "error": "unity_slot_busy",
                        "message": "Another Unity run holds the host slot. Wait for it, or do host-only work.",
                        "lock_path": str(lock_path),
                        "holder": busy.holder,
                    },
                    ensure_ascii=True,
                )
            )
            return EXIT_SLOT_BUSY
        print(json.dumps(payload, ensure_ascii=True))
        return 0
    if args.command == "lock-release":
        print(json.dumps(release_slot(lock_path, pid=args.pid or os.getppid()), ensure_ascii=True))
        return 0
    if args.command == "lock-status":
        print(json.dumps(slot_status(lock_path), ensure_ascii=True))
        return 0
    if args.command == "track-pid":
        print(json.dumps(record_tracked_pid(Path(args.tracked_file), args.pid), ensure_ascii=True))
        return 0
    payload = stop_run(
        Path(args.projects_root),
        tracked_file=Path(args.tracked_file) if args.tracked_file else None,
        timeout_ms=args.timeout_ms,
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("status") == "stopped" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
