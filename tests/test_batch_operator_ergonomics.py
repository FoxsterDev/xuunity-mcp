import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_artifact_probe
import server_batch_reporting
import server_loading_timing
import server_project_actions
import server_specs
import server_summaries
import server_workspace_effects


def truncate_text(value, max_length=240):
    return str(value or "")[:max_length]


def get_subparser_choices(parser):
    for action in parser._actions:
        if isinstance(action, server.argparse._SubParsersAction):
            return set(action.choices.keys())
    return set()


class BatchOperatorErgonomicsTests(unittest.TestCase):
    def test_artifact_probe_checks_zip_entries_and_manifest_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = Path(tmp_dir) / "App.apk"
            with zipfile.ZipFile(artifact_path, "w") as archive:
                archive.writestr("res/drawable-mdpi-v4/ic_stat_example.png", "image")
                archive.writestr("AndroidManifest.xml", "android.permission.POST_NOTIFICATIONS")

            summary = server_artifact_probe.run_artifact_probe(
                {
                    "version": 1,
                    "artifactPath": str(artifact_path),
                    "expectations": [
                        {
                            "id": "icon",
                            "kind": "zip_entry_exists",
                            "path": "res/drawable-mdpi-v4/ic_stat_example.png",
                        },
                        {
                            "id": "glob",
                            "kind": "zip_entry_glob_exists",
                            "path": "res/drawable-*-v4/ic_stat_example.png",
                        },
                        {
                            "id": "permission",
                            "kind": "android_manifest_contains",
                            "value": "android.permission.POST_NOTIFICATIONS",
                        },
                    ],
                },
                artifact_path_override="",
                truncate_text=truncate_text,
            )

        self.assertTrue(summary["succeeded"])
        self.assertEqual(3, summary["passed_count"])
        self.assertEqual(0, summary["failed_count"])

    def test_artifact_probe_reports_required_failure_without_echoing_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = Path(tmp_dir) / "App.apk"
            with zipfile.ZipFile(artifact_path, "w") as archive:
                archive.writestr("res/present.txt", "safe")

            summary = server_artifact_probe.run_artifact_probe(
                {
                    "version": 1,
                    "artifactPath": str(artifact_path),
                    "expectations": [
                        {
                            "id": "missing",
                            "kind": "zip_entry_exists",
                            "path": "res/missing.txt",
                        }
                    ],
                },
                artifact_path_override="",
                truncate_text=truncate_text,
            )

        self.assertFalse(summary["succeeded"])
        self.assertEqual(1, summary["failed_count"])
        self.assertEqual("Entry is missing.", summary["failures"][0]["message"])

    def test_workspace_side_effects_separate_preexisting_allowed_and_unexpected_dirty_paths(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=workspace, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True)
            (workspace / "preexisting.txt").write_text("base\n", encoding="utf-8")
            (workspace / "allowed.txt").write_text("base\n", encoding="utf-8")
            (workspace / "unexpected.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=workspace, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            (workspace / "preexisting.txt").write_text("before\n", encoding="utf-8")
            before_mode, before_dirty = server_workspace_effects.capture_git_dirty_paths(workspace)
            (workspace / "allowed.txt").write_text("after\n", encoding="utf-8")
            (workspace / "unexpected.txt").write_text("after\n", encoding="utf-8")
            after_mode, after_dirty = server_workspace_effects.capture_git_dirty_paths(workspace)

            summary = server_workspace_effects.build_workspace_side_effects(
                workspace_root=workspace,
                before_dirty_paths=before_dirty,
                after_dirty_paths=after_dirty,
                mode="git" if before_mode == "git" and after_mode == "git" else "unavailable",
                allow_config={"allowedTrackedPaths": ["allowed.txt"]},
            )

        self.assertEqual(["preexisting.txt"], summary["preexisting_dirty_paths"])
        self.assertEqual(["allowed.txt"], summary["allowed_new_dirty_paths"])
        self.assertEqual(["unexpected.txt"], summary["unexpected_new_dirty_paths"])
        self.assertIn("git restore -- allowed.txt", summary["recommended_cleanup_commands"])

    def test_batch_progress_reporter_writes_running_heartbeat_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            progress_path = Path(tmp_dir) / "progress.jsonl"
            reporter = server_batch_reporting.BatchProgressReporter(
                run_id="run-1",
                operation="batch-build-player",
                log_path=Path(tmp_dir) / "build.log",
                progress_path=progress_path,
                interval_seconds=0.05,
                stdout=False,
            )

            exit_code, timed_out = server_batch_reporting.run_subprocess_with_progress(
                [sys.executable, "-c", "import time; time.sleep(0.15)"],
                reporter=reporter,
                timeout_ms=1000,
            )
            events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(0, exit_code)
        self.assertFalse(timed_out)
        self.assertIn("unity_batch_started", [event["phase"] for event in events])
        self.assertIn("unity_batch_running", [event["phase"] for event in events])
        self.assertEqual("unity_batch_completed", events[-1]["phase"])

    def test_project_defined_hook_summary_promotes_compact_flags_and_scalars(self) -> None:
        summary = server_summaries.build_scenario_result_summary(
            {
                "project_root": "/tmp/FakeProject",
                "run_id": "run-1",
                "scenario_name": "HookSmoke",
                "status": "passed",
                "steps": [
                    {
                        "stepId": "regenerate_assets",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "outcome": "hook_succeeded",
                        "hook_name": "example.hook",
                        "payload_json": json.dumps(
                            {
                                "outcome": "completed",
                                "contains_unexpected_test_assemblies": False,
                                "changed_file_count": 2,
                                "api_token": "do-not-surface",
                            }
                        ),
                    }
                ],
            },
            {"passed", "failed"},
        )

        hook_summary = summary["project_defined_hook_summary"]
        self.assertEqual(1, hook_summary["hook_count"])
        self.assertTrue(hook_summary["all_hooks_succeeded"])
        hook = hook_summary["hooks"][0]
        self.assertEqual("example.hook", hook["hook_name"])
        self.assertEqual("completed", hook["outcome"])
        self.assertFalse(hook["payload_flags"]["contains_unexpected_test_assemblies"])
        self.assertEqual(2, hook["payload_scalars"]["changed_file_count"])
        self.assertNotIn("api_token", hook.get("payload_scalars", {}))

    def test_profile_mutation_summary_warns_when_restore_is_missing(self) -> None:
        summary = server_summaries.build_scenario_result_summary(
            {
                "project_root": "/tmp/FakeProject",
                "run_id": "run-profile",
                "scenario_name": "ProfileProbe",
                "status": "failed",
                "steps": [
                    {
                        "stepId": "apply_dev",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "hook_name": "example.environment",
                        "payload_json": json.dumps({"action": "project.set_environment", "environment": "dev"}),
                    }
                ],
            },
            {"passed", "failed"},
        )

        profile = summary["profile_mutation_summary"]
        self.assertTrue(profile["profile_mutation_detected"])
        self.assertTrue(profile["profile_restore_required"])
        self.assertEqual("restore_or_assert_final_profile_then_run_compile_gate", summary["recommended_next_action"])

    def test_project_hook_scaffold_emits_activation_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "scaffold"
            result = server_project_actions.scaffold_project_hook(
                hook_name="example.hook",
                action_id="example.list_targets",
                class_name="ExampleHook",
                namespace="Example.Project.Editor",
                output_dir=output_dir,
                mutating=False,
                write_files=True,
            )

            self.assertEqual("project_hook_scaffold", result["action"])
            self.assertTrue((output_dir / "ExampleHook.cs").is_file())
            self.assertTrue((output_dir / "project_actions.fragment.yaml").is_file())
            self.assertTrue((output_dir / "ACTIVATION_CHECKLIST.md").is_file())
            scenario_files = list(output_dir.glob("*_activation_smoke.json"))
            self.assertEqual(1, len(scenario_files))
            scenario = json.loads(scenario_files[0].read_text(encoding="utf-8"))
            self.assertEqual("project_action", scenario["steps"][0]["kind"])
            self.assertIn("run_project_action_list", result["activation_order"])

    def test_config_applying_build_project_action_template_is_generic(self) -> None:
        template_dir = Path(__file__).resolve().parents[1] / "templates" / "project_actions"
        catalog = (template_dir / "config_applying_build.project_actions.yaml").read_text(encoding="utf-8")
        hook = (template_dir / "ConfigApplyingBuildActionHook.cs.template").read_text(encoding="utf-8")

        self.assertIn("build.dev_android", catalog)
        self.assertIn("buildStaticMethod", catalog)
        self.assertIn("ConfigApplyingBuildActionHook", hook)
        for private_marker in ("Apperfun", "JoyfulJam", "SlideBall", "Facebook"):
            self.assertNotIn(private_marker, catalog)
            self.assertNotIn(private_marker, hook)

    def test_parser_contains_artifact_probe_command(self) -> None:
        self.assertIn("artifact-probe", get_subparser_choices(server.build_parser()))

    def test_parser_contains_hook_scaffold_and_console_grep_commands(self) -> None:
        choices = get_subparser_choices(server.build_parser())
        self.assertIn("project-hook-scaffold", choices)
        self.assertIn("request-console-grep", choices)
        self.assertIn("request-loading-timing", choices)

    def test_loading_timing_helper_builds_marker_and_timing_regex(self) -> None:
        args = server_loading_timing.build_loading_timing_grep_args(
            markers=["Boot", "Init"],
            timing_only=True,
            include_stack_traces=False,
            include_types=[],
            limit=10,
        )

        self.assertTrue(args["regex"])
        self.assertEqual(10, args["limit"])
        self.assertIn("Boot", args["pattern"])
        self.assertIn("Init", args["pattern"])
        self.assertIn("duration", args["pattern"])
        self.assertFalse(args["includeStackTraces"])

    def test_loading_timing_summary_extracts_compact_timing_values(self) -> None:
        response = {
            "request_id": "request-1",
            "status": "ok",
            "payload_json": json.dumps(
                {
                    "match_count": 2,
                    "truncated": False,
                    "items": [
                        {
                            "type": "log",
                            "timestamp": "2026-06-09T18:00:00Z",
                            "message": "Boot finished in 123ms",
                        },
                        {
                            "type": "log",
                            "timestamp": "2026-06-09T18:00:01Z",
                            "message": "Init duration 1.5s",
                        },
                    ],
                }
            ),
        }

        summary = server_loading_timing.summarize_loading_timing_response(
            project_root="/tmp/FakeProject",
            response=response,
            markers=["Boot", "Init"],
            timing_only=True,
            include_stack_traces=False,
            include_types=[],
            limit=20,
        )

        self.assertTrue(summary["succeeded"])
        self.assertEqual("unity_loading_timing_summary", summary["action"])
        self.assertEqual(2, summary["returned_count"])
        self.assertEqual(2, summary["timing_value_count"])
        self.assertEqual(123.0, summary["timing_values"][0]["milliseconds"])
        self.assertEqual(1500.0, summary["timing_values"][1]["milliseconds"])

    def test_scenario_step_limit_zero_means_default(self) -> None:
        limit_schema = server_specs.SCENARIO_STEP_SCHEMA["properties"]["limit"]

        self.assertEqual(0, limit_schema["minimum"])
        self.assertIn("step default", limit_schema["description"])

    def test_console_grep_operation_reports_invalid_regex(self) -> None:
        operation_path = (
            Path(__file__).resolve().parents[1]
            / "packages"
            / "com.xuunity.light-mcp"
            / "Editor"
            / "Operations"
            / "XUUnityLightMcpConsoleGrepOperation.cs"
        )
        operation_source = operation_path.read_text(encoding="utf-8")

        self.assertIn('"invalid_regex"', operation_source)
        self.assertIn("new Regex(pattern, options)", operation_source)
        self.assertNotIn("return false;", operation_source)

    def test_batch_commands_accept_fallback_mode(self) -> None:
        parser = server.build_parser()
        commands = (
            ["batch-compile", "--project-root", "/tmp/FakeProject", "--target", "Android"],
            ["batch-compile-matrix", "--project-root", "/tmp/FakeProject", "--config-file", "/tmp/config.json"],
            ["batch-build-config-compile-matrix", "--project-root", "/tmp/FakeProject"],
            ["batch-editmode-tests", "--project-root", "/tmp/FakeProject"],
            ["batch-build-player", "--project-root", "/tmp/FakeProject", "--build-target", "Android"],
        )
        for command in commands:
            with self.subTest(command=command[0]):
                parsed = parser.parse_args([*command, "--batch-fallback-mode", "require-batch"])
                self.assertEqual("require-batch", parsed.batch_fallback_mode)

    def test_batch_commands_accept_compact_output_mode(self) -> None:
        parser = server.build_parser()
        commands = (
            ["batch-compile", "--project-root", "/tmp/FakeProject", "--target", "Android"],
            ["batch-compile-matrix", "--project-root", "/tmp/FakeProject", "--config-file", "/tmp/config.json"],
            ["batch-build-config-compile-matrix", "--project-root", "/tmp/FakeProject"],
            ["batch-editmode-tests", "--project-root", "/tmp/FakeProject"],
            ["batch-build-player", "--project-root", "/tmp/FakeProject", "--build-target", "Android"],
        )
        for command in commands:
            with self.subTest(command=command[0]):
                parsed = parser.parse_args([*command, "--output", "compact"])
                self.assertEqual("compact", parsed.output)


if __name__ == "__main__":
    unittest.main()
