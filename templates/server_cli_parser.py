#!/usr/bin/env python3
from __future__ import annotations

import argparse
from server_batch_reporting import BATCH_OUTPUT_MODES, DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS
from server_specs import STARTUP_POLICIES

TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET = "active"
TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR = (
    "Assets/XUUnityLightMcpGenerated/TestFrameworkRegression/Editor"
)


def add_batch_operator_arguments(command_parser: argparse.ArgumentParser) -> None:
    command_parser.add_argument("--workspace-root")
    command_parser.add_argument("--side-effect-mode", choices=["git", "off"], default="git")
    command_parser.add_argument("--side-effect-allow-file")
    command_parser.add_argument("--batch-fallback-mode", choices=["auto", "off", "require-batch"], default="auto")
    command_parser.add_argument("--output", choices=BATCH_OUTPUT_MODES, default="full")
    command_parser.add_argument("--refresh-license", action="store_true")
    command_parser.add_argument(
        "--progress-interval-seconds",
        type=float,
        default=DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS,
    )
    command_parser.add_argument("--no-progress-stdout", action="store_true")


def add_artifact_probe_arguments(command_parser: argparse.ArgumentParser) -> None:
    command_parser.add_argument("--artifact-probe-file")
    command_parser.add_argument("--artifact-probe-json")
    command_parser.add_argument("--artifact-probe-warn-only", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "XUUnity Light Unity MCP server. "
            "Without arguments it serves MCP over stdio. "
            "Subcommands are local diagnostics helpers."
        )
    )
    sub = parser.add_subparsers(dest="command")

    setup_plan_cmd = sub.add_parser(
        "setup-plan",
        help="Discover Unity projects and print an explicit per-project XUUnity Light MCP setup plan.",
    )
    setup_plan_cmd.add_argument("--workspace-root")
    setup_plan_cmd.add_argument("--project-root", action="append", default=[])
    setup_plan_cmd.add_argument("--recursive", action="store_true")
    setup_plan_cmd.add_argument("--include-test-framework", choices=["auto", "yes", "no"], default="auto")
    setup_plan_cmd.add_argument("--package-source", choices=["git", "file"], default="git")
    setup_plan_cmd.add_argument("--package-version", default="")
    setup_plan_cmd.add_argument("--local-package-source", default="")
    setup_plan_cmd.set_defaults(func_name="cmd_setup_plan")

    setup_apply_cmd = sub.add_parser(
        "setup-apply",
        help="Apply an approved setup plan from setup-plan. Mutates manifests only with --yes.",
    )
    setup_apply_cmd.add_argument("--plan-file", required=True)
    setup_apply_cmd.add_argument("--project-root", action="append", default=[])
    setup_apply_cmd.add_argument("--yes", action="store_true")
    setup_apply_cmd.set_defaults(func_name="cmd_setup_apply")

    uninstall_plan_cmd = sub.add_parser(
        "uninstall-plan",
        help="Print a safe XUUnity Light MCP uninstall plan before removing project, client, or helper state.",
    )
    uninstall_plan_cmd.add_argument(
        "--mode",
        required=True,
        choices=["project-only-cleanup", "full-reset-current-user", "current-user-reset"],
    )
    uninstall_plan_cmd.add_argument("--workspace-root")
    uninstall_plan_cmd.add_argument("--project-root", action="append", default=[])
    uninstall_plan_cmd.add_argument("--recursive", action="store_true")
    uninstall_plan_cmd.add_argument(
        "--client",
        choices=["auto", "codex", "claude_code", "cursor", "windsurf", "claude_desktop", "neutral"],
        default="auto",
    )
    uninstall_plan_cmd.add_argument("--include-other-client-helpers", action="store_true")
    uninstall_plan_cmd.set_defaults(func_name="cmd_uninstall_plan")

    uninstall_apply_cmd = sub.add_parser(
        "uninstall-apply",
        help="Apply an approved uninstall plan from uninstall-plan. Requires --yes.",
    )
    uninstall_apply_cmd.add_argument("--plan-file", required=True)
    uninstall_apply_cmd.add_argument("--yes", action="store_true")
    uninstall_apply_cmd.set_defaults(func_name="cmd_uninstall_apply")

    validate_setup_cmd = sub.add_parser(
        "validate-setup",
        help="Validate one project's XUUnity Light MCP setup and optional Test Framework capability.",
    )
    validate_setup_cmd.add_argument("--project-root", required=True)
    validate_setup_cmd.add_argument("--include-tests", action="store_true")
    validate_setup_cmd.set_defaults(func_name="cmd_validate_setup")

    install_test_framework_cmd = sub.add_parser(
        "install-test-framework",
        help="Install the optional com.unity.test-framework dependency in a project manifest after explicit approval.",
    )
    install_test_framework_cmd.add_argument("--project-root", required=True)
    install_test_framework_cmd.add_argument("--yes", action="store_true")
    install_test_framework_cmd.add_argument("--version", default="")
    install_test_framework_cmd.set_defaults(func_name="cmd_install_test_framework")

    license_capabilities_cmd = sub.add_parser(
        "license-capabilities",
        help="Probe and report Unity batchmode/editor UI execution capability for one project/editor session.",
    )
    license_capabilities_cmd.add_argument("--project-root", required=True)
    license_capabilities_cmd.add_argument("--unity-app")
    license_capabilities_cmd.add_argument("--refresh", action="store_true")
    license_capabilities_cmd.add_argument("--timeout-ms", type=int, default=30000)
    license_capabilities_cmd.set_defaults(func_name="cmd_license_capabilities")

    state_cmd = sub.add_parser("bridge-state", help="Read the Unity bridge heartbeat state file.")
    state_cmd.add_argument("--project-root", required=True)
    state_cmd.set_defaults(func_name="cmd_bridge_state")

    status_cmd = sub.add_parser("request-status", help="Send a direct unity.status request through the active bridge transport.")
    status_cmd.add_argument("--project-root", required=True)
    status_cmd.add_argument("--timeout-ms", type=int, default=5000)
    status_cmd.set_defaults(func_name="cmd_request_status")

    status_summary_cmd = sub.add_parser("request-status-summary", help="Send unity.status and print a compact summary suitable for polling.")
    status_summary_cmd.add_argument("--project-root", required=True)
    status_summary_cmd.add_argument("--timeout-ms", type=int, default=5000)
    status_summary_cmd.add_argument("--include-full-payload", action="store_true")
    status_summary_cmd.set_defaults(func_name="cmd_request_status_summary")

    latest_status_cmd = sub.add_parser(
        "request-latest-status",
        help="Recover the latest compact request verdict from the journal; use --include-full-payload for full evidence.",
    )
    latest_status_cmd.add_argument("--project-root", required=True)
    latest_status_cmd.add_argument("--operation", action="append", default=[])
    latest_status_cmd.add_argument("--timeout-ms", type=int, default=2000)
    latest_status_cmd.add_argument("--include-full-payload", action="store_true")
    latest_status_cmd.set_defaults(func_name="cmd_request_latest_status")

    final_status_cmd = sub.add_parser("request-final-status", help="Summarize a compact final disposition from the request journal; use --include-full-payload for full evidence.")
    final_status_cmd.add_argument("--project-root", required=True)
    final_status_cmd.add_argument("--request-id", required=True)
    final_status_cmd.add_argument("--operation")
    final_status_cmd.add_argument("--timeout-ms", type=int, default=2000)
    final_status_cmd.add_argument("--include-full-payload", action="store_true")
    final_status_cmd.set_defaults(func_name="cmd_request_final_status")

    cancel_cmd = sub.add_parser("request-cancel", help="Best-effort host-side cancellation for a submitted request id in the current same-host editor lane.")
    cancel_cmd.add_argument("--project-root", required=True)
    cancel_cmd.add_argument("--request-id", required=True)
    cancel_cmd.add_argument("--operation")
    cancel_cmd.set_defaults(func_name="cmd_request_cancel")

    stale_cleanup_cmd = sub.add_parser("request-stale-cleanup", help="Clean up stale inbox/outbox request artifacts for the current same-host editor lane.")
    stale_cleanup_cmd.add_argument("--project-root", required=True)
    stale_cleanup_cmd.add_argument("--stale-age-seconds", type=int, default=600)
    stale_cleanup_cmd.add_argument("--dry-run", action="store_true")
    stale_cleanup_cmd.add_argument("--max-entries", type=int, default=50)
    stale_cleanup_cmd.set_defaults(func_name="cmd_request_stale_cleanup")

    playmode_state_cmd = sub.add_parser("request-playmode-state", help="Send a direct unity.playmode.state request through the active bridge transport.")
    playmode_state_cmd.add_argument("--project-root", required=True)
    playmode_state_cmd.add_argument("--timeout-ms", type=int, default=5000)
    playmode_state_cmd.set_defaults(func_name="cmd_request_playmode_state")

    playmode_set_cmd = sub.add_parser("request-playmode-set", help="Send a direct unity.playmode.set request through the active bridge transport.")
    playmode_set_cmd.add_argument("--project-root", required=True)
    playmode_set_cmd.add_argument("--action", required=True, choices=["enter", "exit", "pause", "resume"])
    playmode_set_cmd.add_argument("--timeout-ms", type=int, default=None)
    playmode_set_cmd.set_defaults(func_name="cmd_request_playmode_set")

    capabilities_cmd = sub.add_parser("request-capabilities", help="Send a direct unity.capabilities.get request through the active bridge transport.")
    capabilities_cmd.add_argument("--project-root", required=True)
    capabilities_cmd.add_argument("--timeout-ms", type=int, default=5000)
    capabilities_cmd.set_defaults(func_name="cmd_request_capabilities")

    probe_cmd = sub.add_parser("request-health-probe", help="Send a direct unity.health.probe request through the active bridge transport.")
    probe_cmd.add_argument("--project-root", required=True)
    probe_cmd.add_argument("--timeout-ms", type=int, default=15000)
    probe_cmd.set_defaults(func_name="cmd_request_health_probe")

    build_target_get_cmd = sub.add_parser("request-build-target-get", help="Send a direct unity.build_target.get request through the active bridge transport.")
    build_target_get_cmd.add_argument("--project-root", required=True)
    build_target_get_cmd.add_argument("--timeout-ms", type=int, default=5000)
    build_target_get_cmd.set_defaults(func_name="cmd_request_build_target_get")

    build_target_switch_cmd = sub.add_parser("request-build-target-switch", help="Send a direct unity.build_target.switch request through the active bridge transport.")
    build_target_switch_cmd.add_argument("--project-root", required=True)
    build_target_switch_cmd.add_argument("--target", required=True)
    build_target_switch_cmd.add_argument("--timeout-ms", type=int, default=120000)
    build_target_switch_cmd.set_defaults(func_name="cmd_request_build_target_switch")

    request_build_player_cmd = sub.add_parser("request-build-player", help="Run unity.build_player through the active GUI bridge transport.")
    request_build_player_cmd.add_argument("--project-root", required=True)
    request_build_player_cmd.add_argument("--build-target", required=True)
    request_build_player_cmd.add_argument("--output-path")
    request_build_player_cmd.add_argument("--scene-path", action="append", default=[])
    request_build_player_cmd.add_argument("--build-option", action="append", default=[])
    request_build_player_cmd.add_argument("--result-file")
    request_build_player_cmd.add_argument("--timeout-ms", type=int, default=None)
    add_artifact_probe_arguments(request_build_player_cmd)
    request_build_player_cmd.set_defaults(func_name="cmd_request_build_player")

    scene_assert_cmd = sub.add_parser("request-scene-assert", help="Assert active Unity scene name, path, root objects, or dirty state through the active bridge transport.")
    scene_assert_cmd.add_argument("--project-root", required=True)
    scene_assert_cmd.add_argument("--expected-name", default="")
    scene_assert_cmd.add_argument("--expected-path", default="")
    scene_assert_cmd.add_argument("--required-root-name", action="append", default=[])
    scene_assert_cmd.add_argument("--allow-dirty", dest="allow_dirty", action=argparse.BooleanOptionalAction, default=True)
    scene_assert_cmd.add_argument("--timeout-ms", type=int, default=5000)
    scene_assert_cmd.set_defaults(func_name="cmd_request_scene_assert")

    scene_open_cmd = sub.add_parser("request-scene-open", help="Open a project-relative Assets/... Unity scene through the active bridge transport.")
    scene_open_cmd.add_argument("--project-root", required=True)
    scene_open_cmd.add_argument("--scene-path", required=True)
    scene_open_cmd.add_argument("--allow-dirty-scene-discard", action="store_true")
    scene_open_cmd.add_argument("--timeout-ms", type=int, default=10000)
    scene_open_cmd.set_defaults(func_name="cmd_request_scene_open")

    console_grep_cmd = sub.add_parser("request-console-grep", help="Search recent Unity console messages or the path-backed Editor.log tail.")
    console_grep_cmd.add_argument("--project-root", required=True)
    console_grep_cmd.add_argument("--pattern", required=True)
    console_grep_cmd.add_argument("--source", choices=["console", "editor_log"], default="editor_log")
    console_grep_cmd.add_argument("--editor-log-path")
    console_grep_cmd.add_argument("--regex", action="store_true")
    console_grep_cmd.add_argument("--ignore-case", dest="ignore_case", action=argparse.BooleanOptionalAction, default=True)
    console_grep_cmd.add_argument("--include-stack-traces", action="store_true")
    console_grep_cmd.add_argument("--include-type", action="append", default=[])
    console_grep_cmd.add_argument("--limit", type=int, default=20)
    console_grep_cmd.add_argument("--timeout-ms", type=int, default=5000)
    console_grep_cmd.set_defaults(func_name="cmd_request_console_grep")

    console_tail_cmd = sub.add_parser("request-console-tail", help="Return recent Unity console messages or the path-backed Editor.log tail.")
    console_tail_cmd.add_argument("--project-root", required=True)
    console_tail_cmd.add_argument("--source", choices=["console", "editor_log"], default="editor_log")
    console_tail_cmd.add_argument("--editor-log-path")
    console_tail_cmd.add_argument("--include-type", action="append", default=[])
    console_tail_cmd.add_argument("--limit", type=int, default=50)
    console_tail_cmd.add_argument("--timeout-ms", type=int, default=5000)
    console_tail_cmd.set_defaults(func_name="cmd_request_console_tail")

    loading_timing_cmd = sub.add_parser("request-loading-timing", help="Return compact loading/startup timing console evidence using unity.console.grep.")
    loading_timing_cmd.add_argument("--project-root", required=True)
    loading_timing_cmd.add_argument("--marker", action="append", default=[], help="Loading marker, step name, or timing label to match. Repeat for multiple markers.")
    loading_timing_cmd.add_argument("--include-non-timing", action="store_true", help="Match markers without requiring timing words or duration units.")
    loading_timing_cmd.add_argument("--include-stack-traces", action="store_true")
    loading_timing_cmd.add_argument("--include-type", action="append", default=[])
    loading_timing_cmd.add_argument("--limit", type=int, default=20)
    loading_timing_cmd.add_argument("--timeout-ms", type=int, default=5000)
    loading_timing_cmd.set_defaults(func_name="cmd_request_loading_timing")

    editor_quit_cmd = sub.add_parser("request-editor-quit", help="Send a direct unity.editor.quit request through the active bridge transport.")
    editor_quit_cmd.add_argument("--project-root", required=True)
    editor_quit_cmd.add_argument("--timeout-ms", type=int, default=15000)
    editor_quit_cmd.add_argument("--wait-for-exit", action="store_true")
    editor_quit_cmd.add_argument("--exit-timeout-ms", type=int, default=30000)
    editor_quit_cmd.set_defaults(func_name="cmd_request_editor_quit")

    verify_editor_closed_cmd = sub.add_parser(
        "verify-editor-closed",
        help="Verify that no same-project Unity editor process is live.",
    )
    verify_editor_closed_cmd.add_argument("--project-root", required=True)
    verify_editor_closed_cmd.add_argument("--timeout-ms", type=int, default=30000)
    verify_editor_closed_cmd.set_defaults(func_name="cmd_verify_editor_closed")

    project_refresh_cmd = sub.add_parser("request-project-refresh", help="Send a direct unity.project.refresh request through the active bridge transport.")
    project_refresh_cmd.add_argument("--project-root", required=True)
    project_refresh_cmd.add_argument("--force-asset-refresh", dest="force_asset_refresh", action=argparse.BooleanOptionalAction, default=True)
    project_refresh_cmd.add_argument("--resolve-packages", dest="resolve_packages", action=argparse.BooleanOptionalAction, default=True)
    project_refresh_cmd.add_argument("--rerun-health-probe", dest="rerun_health_probe", action=argparse.BooleanOptionalAction, default=True)
    project_refresh_cmd.add_argument("--timeout-ms", type=int, default=None)
    project_refresh_cmd.set_defaults(func_name="cmd_request_project_refresh")

    project_action_list_cmd = sub.add_parser(
        "project-action-list",
        help="Read the typed project action catalog for a Unity project.",
    )
    project_action_list_cmd.add_argument("--project-root", required=True)
    project_action_list_cmd.add_argument("--catalog-file")
    project_action_list_cmd.set_defaults(func_name="cmd_project_action_list")

    project_action_invoke_cmd = sub.add_parser(
        "project-action-invoke",
        help="Invoke a typed project action by compiling it to a one-step Unity scenario.",
    )
    project_action_invoke_cmd.add_argument("--project-root", required=True)
    project_action_invoke_cmd.add_argument("--action-id", required=True)
    project_action_invoke_cmd.add_argument("--payload-json", default="")
    project_action_invoke_cmd.add_argument("--payload-file", default="")
    project_action_invoke_cmd.add_argument("--catalog-file")
    project_action_invoke_cmd.add_argument("--scenario-name", default="")
    project_action_invoke_cmd.add_argument("--allow-mutating", action="store_true")
    project_action_invoke_cmd.add_argument("--no-wait", action="store_true")
    project_action_invoke_cmd.add_argument("--timeout-ms", type=int, default=None)
    project_action_invoke_cmd.add_argument("--poll-interval-ms", type=int, default=1000)
    project_action_invoke_cmd.set_defaults(func_name="cmd_project_action_invoke")

    project_hook_scaffold_cmd = sub.add_parser(
        "project-hook-scaffold",
        help="Generate a project hook class, project_actions fragment, activation scenario, and checklist.",
    )
    project_hook_scaffold_cmd.add_argument("--hook-name", required=True)
    project_hook_scaffold_cmd.add_argument("--action-id", required=True)
    project_hook_scaffold_cmd.add_argument("--class-name", required=True)
    project_hook_scaffold_cmd.add_argument("--namespace", default="Example.Project.Editor")
    project_hook_scaffold_cmd.add_argument("--output-dir", required=True)
    project_hook_scaffold_cmd.add_argument("--mutating", action="store_true")
    project_hook_scaffold_cmd.add_argument("--write", action="store_true")
    project_hook_scaffold_cmd.set_defaults(func_name="cmd_project_hook_scaffold")

    artifact_register_cmd = sub.add_parser(
        "artifact-register",
        help="Register artifact metadata in the project MCP artifact registry.",
    )
    artifact_register_cmd.add_argument("--project-root", required=True)
    artifact_register_cmd.add_argument("--path", required=True)
    artifact_register_cmd.add_argument("--destination", default="repo_artifact")
    artifact_register_cmd.add_argument("--kind", default="artifact")
    artifact_register_cmd.add_argument("--producer", default="")
    artifact_register_cmd.add_argument("--artifact-schema-version", default="")
    artifact_register_cmd.add_argument("--language", default="")
    artifact_register_cmd.add_argument("--retention-policy", default="project")
    artifact_register_cmd.add_argument("--metadata-json", default="")
    artifact_register_cmd.add_argument("--workspace-root", default="")
    artifact_register_cmd.add_argument("--allow-unity-assets", action="store_true")
    artifact_register_cmd.set_defaults(func_name="cmd_artifact_register")

    artifact_write_report_cmd = sub.add_parser(
        "artifact-write-report",
        help="Write a report artifact to an approved output root and register it.",
    )
    artifact_write_report_cmd.add_argument("--project-root", required=True)
    artifact_write_report_cmd.add_argument("--content", default="")
    artifact_write_report_cmd.add_argument("--content-file", default="")
    artifact_write_report_cmd.add_argument("--destination", default="repo_report")
    artifact_write_report_cmd.add_argument("--category", default="XUUnityLightUnityMcp")
    artifact_write_report_cmd.add_argument("--relative-path", default="")
    artifact_write_report_cmd.add_argument("--kind", default="report")
    artifact_write_report_cmd.add_argument("--producer", default="")
    artifact_write_report_cmd.add_argument("--artifact-schema-version", default="")
    artifact_write_report_cmd.add_argument("--language", default="")
    artifact_write_report_cmd.add_argument("--retention-policy", default="project")
    artifact_write_report_cmd.add_argument("--metadata-json", default="")
    artifact_write_report_cmd.add_argument("--workspace-root", default="")
    artifact_write_report_cmd.add_argument("--allow-unity-assets", action="store_true")
    artifact_write_report_cmd.set_defaults(func_name="cmd_artifact_write_report")

    install_tf_bridge_cmd = sub.add_parser(
        "request-install-test-framework",
        help="Install optional com.unity.test-framework through Unity Package Manager on a healthy bridge after explicit approval.",
    )
    install_tf_bridge_cmd.add_argument("--project-root", required=True)
    install_tf_bridge_cmd.add_argument("--yes", action="store_true")
    install_tf_bridge_cmd.add_argument("--version", default="")
    install_tf_bridge_cmd.add_argument("--timeout-ms", type=int, default=None)
    install_tf_bridge_cmd.set_defaults(func_name="cmd_request_install_test_framework")

    edm4u_resolve_cmd = sub.add_parser("request-edm4u-resolve", help="Run a whitelisted External Dependency Manager for Unity resolver operation through the active bridge transport.")
    edm4u_resolve_cmd.add_argument("--project-root", required=True)
    edm4u_resolve_cmd.add_argument("--platform", default="android", choices=["android", "version_handler"])
    edm4u_resolve_cmd.add_argument("--force", action=argparse.BooleanOptionalAction, default=True)
    edm4u_resolve_cmd.add_argument("--refresh-before", dest="refresh_before", action=argparse.BooleanOptionalAction, default=True)
    edm4u_resolve_cmd.add_argument("--refresh-after", dest="refresh_after", action=argparse.BooleanOptionalAction, default=True)
    edm4u_resolve_cmd.add_argument("--menu-path-candidate", action="append", default=[])
    edm4u_resolve_cmd.add_argument("--timeout-ms", type=int, default=None)
    edm4u_resolve_cmd.set_defaults(func_name="cmd_request_edm4u_resolve")

    sdk_dependency_verify_cmd = sub.add_parser("request-sdk-dependency-verify", help="Verify generated SDK dependency artifacts from a JSON expectations file through the active bridge transport.")
    sdk_dependency_verify_cmd.add_argument("--project-root", required=True)
    sdk_dependency_verify_cmd.add_argument("--config-file", required=True)
    sdk_dependency_verify_cmd.add_argument("--timeout-ms", type=int, default=None)
    sdk_dependency_verify_cmd.set_defaults(func_name="cmd_request_sdk_dependency_verify")

    editmode_cmd = sub.add_parser("request-editmode-tests", help="Send a direct unity.tests.run_editmode request through the active bridge transport.")
    editmode_cmd.add_argument("--project-root", required=True)
    editmode_cmd.add_argument("--test-name", dest="test_names", action="append", default=[])
    editmode_cmd.add_argument("--group-name", dest="group_names", action="append", default=[])
    editmode_cmd.add_argument("--category-name", dest="category_names", action="append", default=[])
    editmode_cmd.add_argument("--assembly-name", dest="assembly_names", action="append", default=[])
    editmode_cmd.add_argument("--timeout-ms", type=int, default=None)
    editmode_cmd.set_defaults(func_name="cmd_request_editmode_tests")

    playmode_cmd = sub.add_parser("request-playmode-tests", help="Send a direct unity.tests.run_playmode request through the active bridge transport.")
    playmode_cmd.add_argument("--project-root", required=True)
    playmode_cmd.add_argument("--test-name", dest="test_names", action="append", default=[])
    playmode_cmd.add_argument("--group-name", dest="group_names", action="append", default=[])
    playmode_cmd.add_argument("--category-name", dest="category_names", action="append", default=[])
    playmode_cmd.add_argument("--assembly-name", dest="assembly_names", action="append", default=[])
    playmode_cmd.add_argument("--timeout-ms", type=int, default=None)
    playmode_cmd.set_defaults(func_name="cmd_request_playmode_tests")

    compile_cmd = sub.add_parser("request-compile", help="Send a direct unity.compile.player_scripts request through the active bridge transport.")
    compile_cmd.add_argument("--project-root", required=True)
    compile_cmd.add_argument("--target", required=True)
    compile_cmd.add_argument("--name", default="")
    compile_cmd.add_argument("--option-flag", dest="option_flags", action="append", default=[])
    compile_cmd.add_argument("--extra-define", dest="extra_defines", action="append", default=[])
    compile_cmd.add_argument("--timeout-ms", type=int, default=None)
    compile_cmd.set_defaults(func_name="cmd_request_compile")

    compile_matrix_cmd = sub.add_parser("request-compile-matrix", help="Send a direct unity.compile.matrix request using a JSON config file through the active bridge transport.")
    compile_matrix_cmd.add_argument("--project-root", required=True)
    compile_matrix_cmd.add_argument("--config-file", required=True)
    compile_matrix_cmd.add_argument("--timeout-ms", type=int, default=None)
    compile_matrix_cmd.set_defaults(func_name="cmd_request_compile_matrix")

    build_config_matrix_cmd = sub.add_parser(
        "request-build-config-compile-matrix",
        help="Send a direct unity.compile.matrix request using build matrix configurations resolved from the project's build-config asset through the active bridge transport.",
    )
    build_config_matrix_cmd.add_argument("--project-root", required=True)
    build_config_matrix_cmd.add_argument("--build-config-asset")
    build_config_matrix_cmd.add_argument("--profile", action="append", default=[])
    build_config_matrix_cmd.add_argument("--target", action="append", default=[])
    build_config_matrix_cmd.add_argument("--stop-on-first-failure", action="store_true")
    build_config_matrix_cmd.add_argument("--timeout-ms", type=int, default=None)
    build_config_matrix_cmd.set_defaults(func_name="cmd_request_build_config_compile_matrix")

    scenario_validate_cmd = sub.add_parser("request-scenario-validate", help="Validate a Unity scenario JSON file through unity.scenario.validate on the active bridge transport.")
    scenario_validate_cmd.add_argument("--project-root", required=True)
    scenario_validate_cmd.add_argument("--scenario-file", required=True)
    scenario_validate_cmd.add_argument("--timeout-ms", type=int, default=5000)
    scenario_validate_cmd.set_defaults(func_name="cmd_request_scenario_validate")

    scenario_run_cmd = sub.add_parser("request-scenario-run", help="Start a Unity scenario JSON file through unity.scenario.run on the active bridge transport.")
    scenario_run_cmd.add_argument("--project-root", required=True)
    scenario_run_cmd.add_argument("--scenario-file", required=True)
    scenario_run_cmd.add_argument("--timeout-ms", type=int, default=None)
    scenario_run_cmd.set_defaults(func_name="cmd_request_scenario_run")

    scenario_run_wait_cmd = sub.add_parser("request-scenario-run-and-wait", help="Start a Unity scenario JSON file and wait until it reaches a terminal state.")
    scenario_run_wait_cmd.add_argument("--project-root", required=True)
    scenario_run_wait_cmd.add_argument("--scenario-file", required=True)
    scenario_run_wait_cmd.add_argument("--timeout-ms", type=int, default=None)
    scenario_run_wait_cmd.add_argument("--poll-interval-ms", type=int, default=1000)
    scenario_run_wait_cmd.add_argument("--verbose", action="store_true")
    scenario_run_wait_cmd.add_argument("--include-full-payload", action="store_true")
    scenario_run_wait_cmd.add_argument("--include-step-payloads", action="store_true")
    scenario_run_wait_cmd.set_defaults(func_name="cmd_request_scenario_run_and_wait")

    scenario_result_cmd = sub.add_parser("request-scenario-result", help="Read the current or completed result of a Unity scenario run.")
    scenario_result_cmd.add_argument("--project-root", required=True)
    scenario_result_cmd.add_argument("--run-id")
    scenario_result_cmd.add_argument("--scenario-name")
    scenario_result_cmd.add_argument("--timeout-ms", type=int, default=5000)
    scenario_result_cmd.set_defaults(func_name="cmd_request_scenario_result")

    scenario_result_summary_cmd = sub.add_parser("request-scenario-result-summary", help="Read the current or completed result of a Unity scenario run and print a compact summary.")
    scenario_result_summary_cmd.add_argument("--project-root", required=True)
    scenario_result_summary_cmd.add_argument("--run-id")
    scenario_result_summary_cmd.add_argument("--scenario-name")
    scenario_result_summary_cmd.add_argument("--timeout-ms", type=int, default=5000)
    scenario_result_summary_cmd.set_defaults(func_name="cmd_request_scenario_result_summary")

    scenario_results_list_cmd = sub.add_parser("request-scenario-results-list", help="List persisted Unity scenario results with compact summaries.")
    scenario_results_list_cmd.add_argument("--project-root", required=True)
    scenario_results_list_cmd.add_argument("--scenario-name")
    scenario_results_list_cmd.add_argument("--limit", type=int, default=20)
    scenario_results_list_cmd.set_defaults(func_name="cmd_request_scenario_results_list")

    scenario_result_latest_cmd = sub.add_parser("request-scenario-result-latest", help="Read the latest persisted Unity scenario result summary, optionally filtered by scenario name.")
    scenario_result_latest_cmd.add_argument("--project-root", required=True)
    scenario_result_latest_cmd.add_argument("--scenario-name")
    scenario_result_latest_cmd.set_defaults(func_name="cmd_request_scenario_result_latest")

    open_editor_cmd = sub.add_parser(
        "open-editor",
        help="Open a Unity Editor instance for the target project and return the launch payload.",
    )
    open_editor_cmd.add_argument("--project-root", required=True)
    open_editor_cmd.add_argument("--unity-app")
    open_editor_cmd.add_argument("--editor-log-path")
    open_editor_cmd.add_argument("--background-open", action="store_true")
    open_editor_cmd.set_defaults(func_name="cmd_open_editor")

    ensure_ready_cmd = sub.add_parser(
        "ensure-ready",
        help="Wait until the target Unity editor session bridge heartbeat is ready, optionally launching the editor.",
    )
    ensure_ready_cmd.add_argument("--project-root", required=True)
    ensure_ready_cmd.add_argument("--open-editor", action="store_true")
    ensure_ready_cmd.add_argument("--unity-app")
    ensure_ready_cmd.add_argument("--editor-log-path")
    ensure_ready_cmd.add_argument("--background-open", action="store_true")
    ensure_ready_cmd.add_argument("--timeout-ms", type=int, default=120000)
    ensure_ready_cmd.add_argument("--heartbeat-max-age-seconds", type=int, default=10)
    ensure_ready_cmd.add_argument("--include-full-payload", action="store_true")
    ensure_ready_cmd.add_argument(
        "--startup-policy",
        default="fail_fast_on_interactive_compile_block",
        choices=sorted(STARTUP_POLICIES),
    )
    ensure_ready_cmd.set_defaults(func_name="cmd_ensure_ready")

    restore_editor_cmd = sub.add_parser(
        "restore-editor-state",
        help="Restore editor to its original state (e.g. quit it if it was opened by the host wrapper).",
    )
    restore_editor_cmd.add_argument("--project-root", required=True)
    restore_editor_cmd.add_argument("--timeout-ms", type=int, default=15000)
    restore_editor_cmd.add_argument("--require-closed", action="store_true")
    restore_editor_cmd.set_defaults(func_name="cmd_restore_editor_state")

    recover_editor_cmd = sub.add_parser(
        "recover-editor-session",
        help="Attempt host-side editor closeout recovery, optional batch compile probe, and optional GUI reopen for the target project.",
    )
    recover_editor_cmd.add_argument("--project-root", required=True)
    recover_editor_cmd.add_argument("--timeout-ms", type=int, default=180000)
    recover_editor_cmd.add_argument("--close-timeout-ms", type=int, default=45000)
    recover_editor_cmd.add_argument("--open-editor", action="store_true")
    recover_editor_cmd.add_argument("--force-compile-probe", action="store_true")
    recover_editor_cmd.add_argument("--heartbeat-max-age-seconds", type=int, default=10)
    recover_editor_cmd.add_argument(
        "--startup-policy",
        default="fail_fast_on_interactive_compile_block",
        choices=sorted(STARTUP_POLICIES),
    )
    recover_editor_cmd.set_defaults(func_name="cmd_recover_editor_session")

    runtime_config_cmd = sub.add_parser(
        "runtime-config-show",
        help="Print the merged runtime timeout configuration for this Unity project.",
    )
    runtime_config_cmd.add_argument("--project-root", required=True)
    runtime_config_cmd.set_defaults(func_name="cmd_runtime_config_show")

    discovery_report_cmd = sub.add_parser(
        "project-discovery-report",
        help="Print the current project discovery and reconciliation report from the host registry.",
    )
    discovery_report_cmd.add_argument("--project-root", required=True)
    discovery_report_cmd.set_defaults(func_name="cmd_project_discovery_report")

    registry_report_cmd = sub.add_parser(
        "registry-context-report",
        help="Print the current in-memory per-project registry context cache report.",
    )
    registry_report_cmd.set_defaults(func_name="cmd_registry_context_report")

    registry_prune_cmd = sub.add_parser(
        "registry-prune-contexts",
        help="Prune stale in-memory per-project registry contexts and print the remaining cache report.",
    )
    registry_prune_cmd.add_argument("--offline-context-max-idle-seconds", type=float)
    registry_prune_cmd.add_argument("--general-context-max-idle-seconds", type=float)
    registry_prune_cmd.set_defaults(func_name="cmd_registry_prune_contexts")

    batch_compile_cmd = sub.add_parser(
        "batch-compile",
        help="Run unity.compile.player_scripts through a non-interactive Unity batchmode lane when the target project is closed.",
    )
    batch_compile_cmd.add_argument("--project-root", required=True)
    batch_compile_cmd.add_argument("--target", required=True)
    batch_compile_cmd.add_argument("--name", default="")
    batch_compile_cmd.add_argument("--option-flag", action="append", default=[])
    batch_compile_cmd.add_argument("--extra-define", action="append", default=[])
    batch_compile_cmd.add_argument("--unity-app")
    batch_compile_cmd.add_argument("--batch-log-path")
    batch_compile_cmd.add_argument("--result-file")
    batch_compile_cmd.add_argument("--timeout-ms", type=int)
    batch_compile_cmd.add_argument("--dry-run", action="store_true")
    add_batch_operator_arguments(batch_compile_cmd)
    batch_compile_cmd.set_defaults(func_name="cmd_batch_compile")

    batch_compile_matrix_cmd = sub.add_parser(
        "batch-compile-matrix",
        help="Run unity.compile.matrix through a non-interactive Unity batchmode lane from a JSON config file when the target project is closed.",
    )
    batch_compile_matrix_cmd.add_argument("--project-root", required=True)
    batch_compile_matrix_cmd.add_argument("--config-file", required=True)
    batch_compile_matrix_cmd.add_argument("--unity-app")
    batch_compile_matrix_cmd.add_argument("--batch-log-path")
    batch_compile_matrix_cmd.add_argument("--result-file")
    batch_compile_matrix_cmd.add_argument("--timeout-ms", type=int)
    batch_compile_matrix_cmd.add_argument("--dry-run", action="store_true")
    add_batch_operator_arguments(batch_compile_matrix_cmd)
    batch_compile_matrix_cmd.set_defaults(func_name="cmd_batch_compile_matrix")

    batch_build_config_matrix_cmd = sub.add_parser(
        "batch-build-config-compile-matrix",
        help="Resolve build profiles from the project's build-config asset and run the Android/iOS compile matrix through a non-interactive Unity batchmode lane when the target project is closed.",
    )
    batch_build_config_matrix_cmd.add_argument("--project-root", required=True)
    batch_build_config_matrix_cmd.add_argument("--build-config-asset")
    batch_build_config_matrix_cmd.add_argument("--profile", action="append", default=[])
    batch_build_config_matrix_cmd.add_argument("--target", action="append", default=[])
    batch_build_config_matrix_cmd.add_argument("--stop-on-first-failure", action="store_true")
    batch_build_config_matrix_cmd.add_argument("--unity-app")
    batch_build_config_matrix_cmd.add_argument("--batch-log-path")
    batch_build_config_matrix_cmd.add_argument("--result-file")
    batch_build_config_matrix_cmd.add_argument("--timeout-ms", type=int)
    add_batch_operator_arguments(batch_build_config_matrix_cmd)
    batch_build_config_matrix_cmd.set_defaults(func_name="cmd_batch_build_config_compile_matrix")

    batch_editmode_cmd = sub.add_parser(
        "batch-editmode-tests",
        help="Run unity.tests.run_editmode through a non-interactive Unity batchmode lane when the target project is closed.",
    )
    batch_editmode_cmd.add_argument("--project-root", required=True)
    batch_editmode_cmd.add_argument("--test-name", dest="test_names", action="append", default=[])
    batch_editmode_cmd.add_argument("--group-name", dest="group_names", action="append", default=[])
    batch_editmode_cmd.add_argument("--category-name", dest="category_names", action="append", default=[])
    batch_editmode_cmd.add_argument("--assembly-name", dest="assembly_names", action="append", default=[])
    batch_editmode_cmd.add_argument("--unity-app")
    batch_editmode_cmd.add_argument("--batch-log-path")
    batch_editmode_cmd.add_argument("--result-file")
    batch_editmode_cmd.add_argument("--timeout-ms", type=int)
    batch_editmode_cmd.add_argument("--dry-run", action="store_true")
    add_batch_operator_arguments(batch_editmode_cmd)
    batch_editmode_cmd.set_defaults(func_name="cmd_batch_editmode_tests")

    test_results_table_cmd = sub.add_parser(
        "test-results-table",
        help="Read persisted Unity Test Framework result JSON files and print a compact table.",
    )
    test_results_table_cmd.add_argument("--project-root", action="append", default=[])
    test_results_table_cmd.add_argument("--workspace-root")
    test_results_table_cmd.add_argument("--mode", action="append", choices=["editmode", "playmode"], default=[])
    test_results_table_cmd.add_argument("--request-id", action="append", default=[])
    test_results_table_cmd.add_argument("--result-file", action="append", default=[])
    test_results_table_cmd.add_argument("--format", choices=["markdown", "json", "tsv"], default="markdown")
    test_results_table_cmd.set_defaults(func_name="cmd_test_results_table")

    regression_cmd = sub.add_parser(
        "batch-test-framework-version-regression",
        help="Run the Phase 0 com.unity.test-framework version sweep against the live MCP and batch EditMode validation lanes.",
    )
    regression_cmd.add_argument("--project-root", required=True)
    regression_cmd.add_argument("--version", action="append", default=[])
    regression_cmd.add_argument("--versions-file")
    regression_cmd.add_argument("--compile-target", default=TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET)
    regression_cmd.add_argument("--focus-assembly-name", action="append", default=[])
    regression_cmd.add_argument("--focus-test-name", action="append", default=[])
    regression_cmd.add_argument(
        "--generated-focus-relative-dir",
        default=TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR,
    )
    regression_cmd.add_argument("--no-generated-focus-test", action="store_true")
    regression_cmd.add_argument("--broad-assembly-name", action="append", default=[])
    regression_cmd.add_argument(
        "--restore-original-version",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    regression_cmd.add_argument("--result-file")
    regression_cmd.set_defaults(func_name="cmd_batch_test_framework_version_regression")

    batch_build_cmd = sub.add_parser(
        "batch-build-player",
        help="Run a generic plain Unity batch build for simple projects using the public lightweight MCP package entrypoint.",
    )
    batch_build_cmd.add_argument("--project-root", required=True)
    batch_build_cmd.add_argument("--build-target", required=True)
    batch_build_cmd.add_argument("--output-path")
    batch_build_cmd.add_argument("--scene-path", action="append", default=[])
    batch_build_cmd.add_argument("--build-option", action="append", default=[])
    batch_build_cmd.add_argument("--unity-app")
    batch_build_cmd.add_argument("--batch-log-path")
    batch_build_cmd.add_argument("--result-file")
    batch_build_cmd.add_argument("--timeout-ms", type=int)
    batch_build_cmd.add_argument("--dry-run", action="store_true")
    add_batch_operator_arguments(batch_build_cmd)
    add_artifact_probe_arguments(batch_build_cmd)
    batch_build_cmd.set_defaults(func_name="cmd_batch_build_player")

    artifact_probe_cmd = sub.add_parser(
        "artifact-probe",
        help="Inspect an existing build artifact against generic ZIP/file/text expectations.",
    )
    artifact_probe_cmd.add_argument("--artifact-path")
    add_artifact_probe_arguments(artifact_probe_cmd)
    artifact_probe_cmd.set_defaults(func_name="cmd_artifact_probe")

    sdk_generated_diff_guard_cmd = sub.add_parser(
        "sdk-generated-diff-guard",
        help="Fail closed when Git-tracked generated SDK files lose required markers, retain stale versions, or change unexpectedly.",
    )
    sdk_generated_diff_guard_cmd.add_argument("--project-root", required=True)
    sdk_generated_diff_guard_cmd.add_argument("--config-file", required=True)
    sdk_generated_diff_guard_cmd.add_argument(
        "--report-file",
        help="Optional JSON evidence path under projectRoot; defaults to Library/XUUnityLightMcp/sdk/generated_diff_guard.json.",
    )
    sdk_generated_diff_guard_cmd.set_defaults(func_name="cmd_sdk_generated_diff_guard")

    maintenance_prune_cmd = sub.add_parser(
        "maintenance-prune",
        help="Prune stale request-journal, scenario-result, capture, and optional log artifacts under Library/XUUnityLightMcp.",
    )
    maintenance_prune_cmd.add_argument("--project-root", required=True)
    maintenance_prune_cmd.add_argument("--dry-run", action="store_true")
    maintenance_prune_cmd.add_argument("--request-journal-max-age-hours", type=int, default=72)
    maintenance_prune_cmd.add_argument("--request-journal-keep-latest", type=int, default=200)
    maintenance_prune_cmd.add_argument("--scenario-success-max-age-hours", type=int, default=168)
    maintenance_prune_cmd.add_argument("--scenario-failure-max-age-hours", type=int, default=336)
    maintenance_prune_cmd.add_argument("--scenario-running-max-age-hours", type=int, default=168)
    maintenance_prune_cmd.add_argument("--scenario-keep-latest-success", type=int, default=20)
    maintenance_prune_cmd.add_argument("--scenario-keep-latest-failure", type=int, default=50)
    maintenance_prune_cmd.add_argument("--scenario-keep-latest-running", type=int, default=20)
    maintenance_prune_cmd.add_argument("--captures-max-age-hours", type=int, default=168)
    maintenance_prune_cmd.add_argument("--captures-keep-latest", type=int, default=20)
    maintenance_prune_cmd.add_argument("--prune-logs", action="store_true")
    maintenance_prune_cmd.add_argument("--logs-max-age-hours", type=int, default=168)
    maintenance_prune_cmd.add_argument("--logs-keep-latest", type=int, default=10)
    maintenance_prune_cmd.set_defaults(func_name="cmd_maintenance_prune")

    # Resolve callable commands dynamically to avoid cyclic import issues
    import server_cli_commands
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for cmd_name, cmd_parser in action.choices.items():
                func_name = cmd_parser.get_default("func_name")
                if func_name:
                    func_callable = getattr(server_cli_commands, func_name, None)
                    if func_callable is not None:
                        cmd_parser.set_defaults(func=func_callable)

    return parser
