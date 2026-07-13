from __future__ import annotations

from server_cli_shared import *
from server_sdk_diff_guard import run_sdk_generated_diff_guard


def cmd_sdk_generated_diff_guard(args):
    project_root = ensure_project_root(args.project_root)
    config = load_json_file(args.config_file, "sdk_generated_diff_guard_config_invalid")
    result = run_sdk_generated_diff_guard(
        project_root=project_root,
        config=config,
        report_file=getattr(args, "report_file", "") or "",
    )
    print_json(result)
    if result.get("verdict") != "passed":
        raise SystemExit(1)
