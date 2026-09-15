from __future__ import annotations

from pathlib import Path
from server_core import BRIDGE_ENABLE_RECOVERY_COMMAND, launcher_command_name, quoted_shell_path

DISCOVERY_NEXT_ACTION_COMMANDS = {
    "scaffold_project_hook": "{launcher} project-hook-scaffold --hook-name ProjectHook --action-id project.validate --class-name ProjectHook --output-dir {hook_output_dir} --write",
    "run_compile_gate_and_fix_errors": "{launcher} request-project-refresh --project-root {project_root} --timeout-ms 180000",
    "fix_compile_errors": "{launcher} request-project-refresh --project-root {project_root} --timeout-ms 180000",
    "refresh_stale_compiler_diagnostics": "{launcher} request-project-refresh --project-root {project_root} --timeout-ms 180000",
    "exit_playmode_before_editing": "{launcher} request-playmode-set --project-root {project_root} --action exit",
    "request-status-summary": "{launcher} request-status-summary --project-root {project_root}",
    "wait_for_editor_idle_or_inspect_busy_state": "{launcher} request-status-summary --project-root {project_root} --include-full-payload",
    "enable_bridge_and_retry": BRIDGE_ENABLE_RECOVERY_COMMAND,
    "open_editor_or_ensure_ready": "{launcher} ensure-ready --project-root {project_root} --open-editor",
    "ensure_ready_or_recover_bridge": "{launcher} ensure-ready --project-root {project_root} --open-editor",
    "wait_for_bridge_or_recover_editor": "{launcher} recover-editor-session --project-root {project_root} --timeout-ms 180000",
    "recover_editor_session": "{launcher} recover-editor-session --project-root {project_root} --timeout-ms 180000",
    "close_same_project_editor_or_use_interactive_lane": "{launcher} request-editor-quit --project-root {project_root} --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
    "start_or_recover_editor": "{launcher} ensure-ready --project-root {project_root} --open-editor",
    "clear_stale_host_session_and_retry": "{launcher} restore-editor-state --project-root {project_root} --timeout-ms 15000",
    "refresh_host_session_if_needed": "{launcher} request-status-summary --project-root {project_root} --timeout-ms 5000",
    "inspect_editor_log": "{launcher} project-discovery-report --project-root {project_root}",
    "inspect_editor_log_and_observe": "{launcher} project-discovery-report --project-root {project_root}",
    "inspect_editor_log_and_consider_graceful_restart": "{launcher} ensure-ready --project-root {project_root} --open-editor",
    "poll_bridge_bootstrap_attached_then_retry": "{launcher} request-status-summary --project-root {project_root} --timeout-ms 5000",
    "wait_for_main_editor_bridge": "{launcher} request-status-summary --project-root {project_root} --timeout-ms 5000",
    "wait_for_editor_idle_then_retry": "{launcher} request-status-summary --project-root {project_root} --timeout-ms 5000",
    "run_batch_compile_gate_and_fix_errors": "{launcher} batch-build-config-compile-matrix --project-root {project_root}",
    "open_safe_mode_manually": "Open the Unity project manually and enter Safe Mode; do not use automated dialog clicking.",
    "relaunch_noninteractive_accept_apiupdate": "Unity -batchmode -quit -accept-apiupdate -projectPath {project_root} -logFile {unity_apiupdate_log}",
    "restore_host_process_visibility": "{launcher} project-discovery-report --project-root {project_root}",
}


def recommended_recovery_command_for_project(project_root: Path, next_action: str) -> str:
    template = DISCOVERY_NEXT_ACTION_COMMANDS.get(str(next_action or "").strip())
    if not template:
        return ""
    return template.format(
        launcher=launcher_command_name(),
        project_root=quoted_shell_path(project_root),
        hook_output_dir=quoted_shell_path(project_root / "Temp" / "XUUnityHookScaffold"),
        unity_apiupdate_log=quoted_shell_path(
            project_root / "Library" / "XUUnityLightMcp" / "logs" / "unity_apiupdate.log"
        ),
    )
