#!/usr/bin/env python3
"""Editor stand-in for file-IPC tests: no Unity, real filesystem semantics.

Three modes, all spawned as a separate OS process so tests exercise true
cross-process file IPC on the host filesystem (NTFS on the Windows CI leg):

- ``simulate <project_root> <seconds>``: play the Unity-side bridge role —
  publish a live ``bridge_state.json`` heartbeat and answer every inbox
  request with a well-formed ok response, exactly like the C# bridge pump.
- ``stress-write <target> <iterations>``: rewrite one JSON file as fast as
  possible through the production ``write_json`` atomic publish, so a
  concurrent reader can assert it never observes a torn payload.
- ``complete-without-delivery <project_root> <seconds>``: accept one request,
  record Unity-side start/completion across a bridge generation change, and
  intentionally omit the outbox response. This models a completed Unity
  operation whose original host delivery channel was lost.

Not a test module: the ``bridge_ipc_simulator`` name keeps unittest discovery
from collecting it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = TESTS_DIR.parent / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_bridge_paths import bridge_state_path, inbox_dir, outbox_dir  # noqa: E402
from server_bridge_journal import write_host_request_journal_event  # noqa: E402
from server_core import read_json, write_json  # noqa: E402

SIMULATOR_MARKER = "xuunity-file-ipc-simulator"
STRESS_BLOB = "x" * 8000


def utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_state(
    last_processed_request_id: str,
    *,
    generation: int = 1,
    session_id: str = "ipc-simulator-session",
) -> dict:
    return {
        "bridge_version": 1,
        "bridge_generation": generation,
        "bridge_session_id": session_id,
        "transport": "file_ipc",
        "editor_pid": os.getpid(),
        "heartbeat_utc": utc_stamp(),
        "last_pump_utc": utc_stamp(),
        "health_status": "healthy",
        "playmode_state": "edit",
        "pending_request_count": 0,
        "last_processed_request_id": last_processed_request_id,
        "editor_simulator": True,
    }


def answer_request(project_root: Path, request_path: Path) -> str:
    request = read_json(request_path)
    if not isinstance(request, dict):
        return ""
    request_id = str(request.get("request_id") or "")
    if not request_id:
        return ""
    operation = str(request.get("operation") or "")
    payload = {
        "simulator_marker": SIMULATOR_MARKER,
        "operation": operation,
        "echo_args_json": str(request.get("args_json") or "{}"),
        "echo_project_root": str(request.get("project_root") or ""),
    }
    response = {
        "status": "ok",
        "request_id": request_id,
        "payload_type": operation,
        "payload_json": json.dumps(payload, ensure_ascii=True),
    }
    write_json(outbox_dir(project_root) / f"{request_id}.json", response)
    try:
        request_path.unlink()
    except OSError:
        pass
    return request_id


def simulate(project_root: Path, deadline_seconds: float) -> int:
    inbox = inbox_dir(project_root)
    inbox.mkdir(parents=True, exist_ok=True)
    outbox_dir(project_root).mkdir(parents=True, exist_ok=True)
    state_path = bridge_state_path(project_root)
    deadline = time.monotonic() + deadline_seconds
    last_processed = ""

    while time.monotonic() < deadline:
        write_json(state_path, build_state(last_processed))
        for request_path in sorted(inbox.glob("*.json")):
            try:
                processed = answer_request(project_root, request_path)
            except (OSError, ValueError):
                # Request still mid-write by the host; retry next pump cycle.
                continue
            if processed:
                last_processed = processed
                write_json(state_path, build_state(last_processed))
        time.sleep(0.05)
    return 0


def complete_without_delivery(project_root: Path, deadline_seconds: float) -> int:
    inbox = inbox_dir(project_root)
    inbox.mkdir(parents=True, exist_ok=True)
    outbox_dir(project_root).mkdir(parents=True, exist_ok=True)
    state_path = bridge_state_path(project_root)
    deadline = time.monotonic() + deadline_seconds
    generation = 1
    session_id = "ipc-simulator-session-1"
    last_processed = ""

    while time.monotonic() < deadline:
        write_json(
            state_path,
            build_state(
                last_processed,
                generation=generation,
                session_id=session_id,
            ),
        )
        for request_path in sorted(inbox.glob("*.json")):
            try:
                request = read_json(request_path)
            except (OSError, ValueError):
                continue
            if not isinstance(request, dict):
                continue
            request_id = str(request.get("request_id") or "")
            operation = str(request.get("operation") or "")
            if not request_id or not operation:
                continue

            write_host_request_journal_event(
                project_root,
                "request_started",
                {
                    "request_id": request_id,
                    "operation": operation,
                    "operation_status": "running",
                    "bridge_generation": generation,
                    "bridge_session_id": session_id,
                    "event_source": "unity_editor_simulator",
                    "started_at_utc": utc_stamp(),
                },
            )

            generation = 2
            session_id = "ipc-simulator-session-2"
            last_processed = request_id
            write_json(
                state_path,
                build_state(
                    last_processed,
                    generation=generation,
                    session_id=session_id,
                ),
            )
            write_host_request_journal_event(
                project_root,
                "request_completed",
                {
                    "request_id": request_id,
                    "operation": operation,
                    "operation_status": "ok",
                    "bridge_generation": generation,
                    "bridge_session_id": session_id,
                    "event_source": "unity_editor_simulator",
                    "completed_at_utc": utc_stamp(),
                },
            )
            try:
                request_path.unlink()
            except OSError:
                pass
        time.sleep(0.05)
    return 0


def stress_write(target: Path, iterations: int) -> int:
    for index in range(iterations):
        write_json(
            target,
            {"seq": index, "head": "begin", "blob": STRESS_BLOB, "tail_seq": index},
        )
    write_json(
        target,
        {
            "seq": iterations,
            "head": "begin",
            "blob": STRESS_BLOB,
            "tail_seq": iterations,
            "final": True,
        },
    )
    return 0


def main(argv: list) -> int:
    mode = argv[0] if argv else ""
    if mode == "simulate" and len(argv) == 3:
        return simulate(Path(argv[1]), float(argv[2]))
    if mode == "complete-without-delivery" and len(argv) == 3:
        return complete_without_delivery(Path(argv[1]), float(argv[2]))
    if mode == "stress-write" and len(argv) == 3:
        return stress_write(Path(argv[1]), int(argv[2]))
    sys.stderr.write(
        "usage: bridge_ipc_simulator.py simulate <project_root> <seconds>"
        " | complete-without-delivery <project_root> <seconds>"
        " | stress-write <target> <iterations>\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
