#!/usr/bin/env python3
"""Read-only mechanism check after a source-runtime open-editor launch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "templates"))
from server_core import read_json, reconfigure_stdio_utf8
from server_bridge_runtime import host_editor_session_state_path, try_read_bridge_state, pid_is_alive
from server_licensing_state import editor_license_evidence


def main() -> int:
    reconfigure_stdio_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    session = read_json(host_editor_session_state_path(args.project_root))
    state = try_read_bridge_state(args.project_root) or {}
    evidence = editor_license_evidence(session.get("editor_log_path") or "", session)
    pid = int(session.get("editor_pid") or 0)
    owned_live_editor = bool(session.get("opened_by_host")) and pid > 0 and pid_is_alive(pid) and pid == int(state.get("editor_pid") or 0)
    passed = owned_live_editor and evidence["licensing_forwarded_channel_connected"] and evidence["license_state"] == "licensed"
    print(json.dumps({"passed": passed, "owned_live_editor": owned_live_editor, **evidence}, ensure_ascii=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
