import contextlib
import io
import json
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout


OPS_ROOT = Path(__file__).resolve().parents[1]
RUNNER = OPS_ROOT / "scripts" / "testing" / "run_multi_project_batch_compile_matrix.sh"
BASH = resolve_bash_executable()
RUNNER_DIR = OPS_ROOT / "scripts" / "testing"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

import run_multi_project


class MultiProjectBatchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def test_recovery_closeout_facts_do_not_infer_a_negative_from_missing_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            malformed_path = Path(temp_dir) / "recover.log"
            malformed_path.write_text("not json\n", encoding="utf-8")
            incomplete_path = Path(temp_dir) / "incomplete-recover.log"
            incomplete_path.write_text('{"closeout_attempted":true}\n', encoding="utf-8")

            not_requested = run_multi_project.recovery_closeout_facts(None)
            unavailable = run_multi_project.recovery_closeout_facts(malformed_path)
            incomplete = run_multi_project.recovery_closeout_facts(incomplete_path)

        self.assertEqual("not_requested", not_requested["recovery_evidence_status"])
        self.assertIsNone(not_requested["editor_closed_before_batch"])
        self.assertEqual("unavailable", unavailable["recovery_evidence_status"])
        self.assertIsNone(unavailable["editor_closed_before_batch"])
        self.assertTrue(unavailable["recovery_parse_error"])
        self.assertEqual("incomplete", incomplete["recovery_evidence_status"])
        self.assertTrue(incomplete["recovery_closeout_attempted"])
        self.assertIsNone(incomplete["editor_closed_before_batch"])
        self.assertTrue(incomplete["recovery_parse_error"])

    def test_jsonl_progress_plus_final_json_stdout_counts_as_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "ConsumerProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": "file:package"}}),
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )

            wrapper_path = temp_root / "fake_xuunity_light_unity_mcp.sh"
            wrapper_path.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    command_name="${1:-}"
                    case "$command_name" in
                      batch-build-config-compile-matrix)
                        fallback_mode=""
                        while [[ $# -gt 0 ]]; do
                          case "$1" in
                            --batch-fallback-mode)
                              fallback_mode="${2:-}"
                              shift 2
                              ;;
                            *)
                              shift
                              ;;
                          esac
                        done
                        if [[ "$fallback_mode" != "auto" ]]; then
                          echo "expected fallback mode auto, got: $fallback_mode" >&2
                          exit 4
                        fi
                        printf '{"event":"batch_progress","phase":"preflight"}\\n'
                        cat <<'JSON'
                    {
                      "action": "batch_build_config_compile_matrix",
                      "succeeded": true,
                      "result_summary": {
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "batch",
                        "batch_fallback_mode": "auto",
                        "matrix": {
                          "status": "passed",
                          "total": 4,
                          "passed": 4,
                          "failed": 0,
                          "skipped": 0
                        }
                      },
                      "summary_file": "/tmp/summary.json",
                      "result_file": "/tmp/result.json",
                      "log_path": "/tmp/editor.log"
                    }
                    JSON
                        ;;
                      recover-editor-session)
                        printf '{"recovery_classification":"recovered","closeout_attempted":true,"closeout":{"restored":true,"same_project_editor_closed":true,"closed_editor_pid":4242,"closeout_classification":"closed_via_unity_editor_quit","close_path":"unity.editor.quit"}}\\n'
                        ;;
                      *)
                        echo "unexpected command: $command_name" >&2
                        exit 2
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            wrapper_path.chmod(0o755)

            results_dir = temp_root / "results"
            env = os.environ.copy()
            env["XUUNITY_LIGHT_UNITY_MCP_WRAPPER"] = wrapper_path.as_posix()
            env["XUUNITY_LIGHT_UNITY_MCP_PYTHON"] = Path(sys.executable).as_posix()
            completed = run_with_timeout(
                [
                    BASH,
                    RUNNER.as_posix(),
                    "--repo-root",
                    temp_root.as_posix(),
                    "--project-root",
                    project_root.as_posix(),
                    "--parallelism",
                    "1",
                    "--results-dir",
                    results_dir.as_posix(),
                ],
                cwd=OPS_ROOT.as_posix(),
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
            status = json.loads((results_dir / "ConsumerProject_status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["json_parse_ok"])
            self.assertTrue(status["succeeded"])
            self.assertEqual("batch", status["requested_execution_lane"])
            self.assertEqual("batch", status["effective_execution_lane"])
            self.assertEqual("auto", status["batch_fallback_mode"])
            self.assertEqual("passed_via_batch", status["operator_verdict"])
            self.assertEqual("parsed", status["recovery_evidence_status"])
            self.assertTrue(status["recovery_closeout_attempted"])
            self.assertTrue(status["editor_closed_before_batch"])
            self.assertEqual(4242, status["closed_editor_pid"])
            self.assertEqual("closed_via_unity_editor_quit", status["editor_closeout_classification"])
            self.assertEqual("unity.editor.quit", status["editor_close_path"])
            self.assertEqual("passed", status["matrix_status"])
            self.assertEqual(4, status["total"])
            self.assertEqual(4, status["passed"])
            self.assertEqual(0, status["failed"])
            self.assertIn('"projects_failed": 0', completed.stdout)
            self.assertIn("batch_fallback_mode=auto", completed.stdout)
            self.assertIn("verdict=passed_via_batch", completed.stdout)
            self.assertIn('BATCH_EDITOR_CLOSE_NOTICE {"project":"ConsumerProject"', completed.stdout)
            self.assertLess(
                completed.stdout.index("BATCH_EDITOR_CLOSE_NOTICE"),
                completed.stdout.index("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_BEGIN"),
            )
            aggregate_text = completed.stdout.split("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_END\n", 1)[1]
            aggregate = json.loads(aggregate_text)
            self.assertEqual(1, aggregate["editors_closed_before_batch"])
            self.assertEqual(4242, aggregate["editor_close_side_effects"][0]["closed_editor_pid"])
            self.assertIn("closed 1 host-opened Unity editor", aggregate["side_effect_notice"])

    def test_gui_fallback_success_counts_as_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "ConsumerProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": "file:package"}}),
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )

            wrapper_path = temp_root / "fake_xuunity_light_unity_mcp.sh"
            wrapper_path.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    command_name="${1:-}"
                    case "$command_name" in
                      batch-build-config-compile-matrix)
                        fallback_mode=""
                        while [[ $# -gt 0 ]]; do
                          case "$1" in
                            --batch-fallback-mode)
                              fallback_mode="${2:-}"
                              shift 2
                              ;;
                            *)
                              shift
                              ;;
                          esac
                        done
                        if [[ "$fallback_mode" != "auto" ]]; then
                          echo "expected fallback mode auto, got: $fallback_mode" >&2
                          exit 4
                        fi
                        printf '{"event":"batch_progress","phase":"prepare_completed","message":"Batch preflight selected GUI fallback."}\\n'
                        cat <<'JSON'
                    {
                      "action": "batch_build_config_compile_matrix",
                      "succeeded": true,
                      "result_summary": {
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "gui",
                        "batch_fallback_mode": "auto",
                        "lane_fallback_reason": "access_token_unavailable",
                        "license_blocker_code": "access_token_unavailable",
                        "transport_outcome": "gui_operation_completed",
                        "unity_outcome": "passed"
                      },
                      "license_capabilities": {
                        "from_cache": true,
                        "probed_at_utc": "2000-01-01T00:00:00Z"
                      },
                      "bridge_response": {
                        "payload_json": "{\\\"matrix\\\":{\\\"status\\\":\\\"passed\\\",\\\"total\\\":6,\\\"passed\\\":6,\\\"failed\\\":0,\\\"skipped\\\":0}}"
                      },
                      "summary_file": "/tmp/summary.json",
                      "result_file": "/tmp/result.json",
                      "log_path": "/tmp/editor.log"
                    }
                    JSON
                        ;;
                      recover-editor-session)
                        printf '{"recovery_classification":"not_needed"}\\n'
                        ;;
                      *)
                        echo "unexpected command: $command_name" >&2
                        exit 2
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            wrapper_path.chmod(0o755)

            results_dir = temp_root / "results"
            env = os.environ.copy()
            env["XUUNITY_LIGHT_UNITY_MCP_WRAPPER"] = wrapper_path.as_posix()
            env["XUUNITY_LIGHT_UNITY_MCP_PYTHON"] = Path(sys.executable).as_posix()
            completed = run_with_timeout(
                [
                    BASH,
                    RUNNER.as_posix(),
                    "--repo-root",
                    temp_root.as_posix(),
                    "--project-root",
                    project_root.as_posix(),
                    "--parallelism",
                    "1",
                    "--no-close-live-editors",
                    "--results-dir",
                    results_dir.as_posix(),
                ],
                cwd=OPS_ROOT.as_posix(),
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
            status = json.loads((results_dir / "ConsumerProject_status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["succeeded"])
            self.assertEqual("gui", status["effective_execution_lane"])
            self.assertEqual("auto", status["batch_fallback_mode"])
            self.assertEqual("access_token_unavailable", status["lane_fallback_reason"])
            self.assertEqual("access_token_unavailable", status["license_blocker_code"])
            self.assertEqual("passed_via_gui_fallback", status["operator_verdict"])
            self.assertEqual("gui_operation_completed", status["transport_outcome"])
            self.assertEqual("passed", status["unity_outcome"])
            self.assertEqual("passed", status["matrix_status"])
            self.assertEqual(6, status["total"])
            self.assertEqual(6, status["passed"])
            self.assertEqual(0, status["failed"])
            self.assertEqual("gui_fallback_matrix", status["compile_evidence"]["evidence_source"])
            self.assertEqual("passed", status["compile_evidence"]["outcome"])
            self.assertTrue(status["license_from_cache"])
            self.assertGreaterEqual(status["license_probe_age_seconds"], 0)
            self.assertIn('"projects_failed": 0', completed.stdout)
            self.assertIn("verdict=passed_via_gui_fallback", completed.stdout)
            self.assertIn("effective_lane=gui", completed.stdout)
            self.assertIn("fallback_reason=access_token_unavailable", completed.stdout)
            self.assertIn("license_from_cache=true", completed.stdout)
            self.assertIn("license_probe_age_seconds=", completed.stdout)

    def test_compact_gui_fallback_success_counts_as_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            stdout_file = temp_root / "batch_stdout.json"
            stderr_file = temp_root / "batch_stderr.log"
            status_file = temp_root / "status.json"
            stdout_file.write_text(
                json.dumps(
                    {
                        "payload_mode": "compact_batch_cli",
                        "succeeded": True,
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "gui",
                        "batch_fallback_mode": "auto",
                        "lane_fallback_reason": "licensing_client_ipc_failure",
                        "unity_outcome": "passed",
                        "transport_outcome": "gui_operation_completed",
                        "matrix": {
                            "status": "passed",
                            "total": 6,
                            "passed": 6,
                            "failed": 0,
                            "skipped": 0,
                            "rebuilt_assembly_count": 4,
                            "cached_assembly_count": 136,
                            "rebuild_evidence_status": "measured",
                            "warning_count": 3,
                            "unique_warning_count": 2,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stderr_file.write_text("", encoding="utf-8")

            run_multi_project.build_batch_status(
                "ConsumerProject",
                str(temp_root / "ConsumerProject"),
                stdout_file,
                stderr_file,
                status_file,
                0,
                0,
                "auto",
            )

            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual("passed_via_gui_fallback", status["operator_verdict"])
            self.assertEqual("passed", status["unity_outcome"])
            self.assertEqual("compact_payload", status["unity_outcome_source"])
            self.assertEqual("gui_operation_completed", status["transport_outcome"])
            self.assertEqual("compact_payload", status["transport_outcome_source"])
            self.assertEqual("measured", status["matrix_counters_status"])
            self.assertEqual(6, status["total"])
            self.assertEqual(6, status["passed"])
            self.assertEqual(0, status["failed"])
            self.assertEqual(3, status["warning_count"])
            self.assertEqual(2, status["unique_warning_count"])
            self.assertEqual(4, status["rebuilt_assembly_count"])
            self.assertEqual(136, status["cached_assembly_count"])
            self.assertEqual("measured", status["rebuild_evidence_status"])

    def test_compact_gui_fallback_recovers_summary_file_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            summary_file = temp_root / "batch_summary.json"
            stdout_file = temp_root / "batch_stdout.json"
            stderr_file = temp_root / "batch_stderr.log"
            status_file = temp_root / "status.json"
            summary_file.write_text(
                json.dumps(
                    {
                        "unity_outcome": "passed",
                        "transport_outcome": "gui_operation_completed",
                        "matrix": {
                            "status": "passed",
                            "total": 6,
                            "passed": 6,
                            "failed": 0,
                            "skipped": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout_file.write_text(
                json.dumps(
                    {
                        "payload_mode": "compact_batch_cli",
                        "succeeded": True,
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "gui",
                        "batch_fallback_mode": "auto",
                        "summary_file": str(summary_file),
                    }
                ),
                encoding="utf-8",
            )
            stderr_file.write_text("", encoding="utf-8")

            run_multi_project.build_batch_status(
                "ConsumerProject",
                str(temp_root / "ConsumerProject"),
                stdout_file,
                stderr_file,
                status_file,
                0,
                0,
                "auto",
            )

            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual("passed_via_gui_fallback", status["operator_verdict"])
            self.assertEqual("summary_file", status["unity_outcome_source"])
            self.assertEqual("summary_file", status["transport_outcome_source"])
            self.assertEqual("summary_file_matrix", status["compile_evidence"]["evidence_source"])
            self.assertTrue(status["summary_file_loaded"])
            self.assertEqual(6, status["total"])

    def test_compact_gui_fallback_recovers_confirmed_result_file_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result_file = temp_root / "batch_result.json"
            stdout_file = temp_root / "batch_stdout.json"
            stderr_file = temp_root / "batch_stderr.log"
            status_file = temp_root / "status.json"
            result_file.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "total": 6,
                        "passed": 6,
                        "failed": 0,
                        "skipped": 0,
                        "validation_evidence": "unity_mcp",
                        "post_settle_compile_trust_class": "confirmed",
                    }
                ),
                encoding="utf-8",
            )
            stdout_file.write_text(
                json.dumps(
                    {
                        "payload_mode": "compact_batch_cli",
                        "succeeded": True,
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "gui",
                        "batch_fallback_mode": "auto",
                        "transport_outcome": "gui_operation_completed",
                        "result_file": str(result_file),
                    }
                ),
                encoding="utf-8",
            )
            stderr_file.write_text("", encoding="utf-8")

            run_multi_project.build_batch_status(
                "ConsumerProject",
                str(temp_root / "ConsumerProject"),
                stdout_file,
                stderr_file,
                status_file,
                0,
                0,
                "auto",
            )

            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual("passed_via_gui_fallback", status["operator_verdict"])
            self.assertEqual("result_file", status["unity_outcome_source"])
            self.assertEqual("compact_payload", status["transport_outcome_source"])
            self.assertEqual("result_file_matrix", status["compile_evidence"]["evidence_source"])
            self.assertTrue(status["result_file_loaded"])
            self.assertEqual(6, status["total"])

    def test_unavailable_matrix_counters_are_not_reported_as_zero(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            stdout_file = temp_root / "batch_stdout.json"
            stderr_file = temp_root / "batch_stderr.log"
            status_file = temp_root / "ConsumerProject_status.json"
            stdout_file.write_text(
                json.dumps(
                    {
                        "payload_mode": "compact_batch_cli",
                        "succeeded": True,
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "gui",
                        "batch_fallback_mode": "auto",
                        "unity_outcome": "passed",
                        "transport_outcome": "gui_operation_completed",
                    }
                ),
                encoding="utf-8",
            )
            stderr_file.write_text("", encoding="utf-8")

            run_multi_project.build_batch_status(
                "ConsumerProject",
                str(temp_root / "ConsumerProject"),
                stdout_file,
                stderr_file,
                status_file,
                0,
                0,
                "auto",
            )

            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual("unavailable", status["matrix_counters_status"])
            self.assertIsNone(status["total"])
            self.assertIsNone(status["passed"])
            self.assertIsNone(status["failed"])
            self.assertIsNone(status["skipped"])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = run_multi_project.emit_batch_final_summary(str(temp_root))
            self.assertEqual(1, exit_code)
            self.assertIn("matrix_counters=unavailable", output.getvalue())
            self.assertIn("total=unavailable", output.getvalue())
            self.assertNotIn("total=0", output.getvalue())

    def test_require_batch_mode_forwards_and_fails_when_batchmode_unavailable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "ConsumerProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": "file:package"}}),
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )

            wrapper_path = temp_root / "fake_xuunity_light_unity_mcp.sh"
            wrapper_path.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    command_name="${1:-}"
                    case "$command_name" in
                      batch-build-config-compile-matrix)
                        fallback_mode=""
                        while [[ $# -gt 0 ]]; do
                          case "$1" in
                            --batch-fallback-mode)
                              fallback_mode="${2:-}"
                              shift 2
                              ;;
                            *)
                              shift
                              ;;
                          esac
                        done
                        if [[ "$fallback_mode" != "require-batch" ]]; then
                          echo "expected fallback mode require-batch, got: $fallback_mode" >&2
                          exit 4
                        fi
                        cat <<'JSON'
                    {
                      "action": "batch_build_config_compile_matrix",
                      "succeeded": false,
                      "result_summary": {
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "none",
                        "batch_fallback_mode": "require-batch",
                        "license_batchmode_supported": false,
                        "license_blocker_code": "access_token_unavailable",
                        "transport_outcome": "batch_prepare_blocked",
                        "unity_outcome": "not_started"
                      },
                      "summary_file": "/tmp/summary.json",
                      "result_file": "/tmp/result.json",
                      "log_path": "/tmp/editor.log"
                    }
                    JSON
                        exit 1
                        ;;
                      recover-editor-session)
                        printf '{"recovery_classification":"not_needed"}\\n'
                        ;;
                      *)
                        echo "unexpected command: $command_name" >&2
                        exit 2
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            wrapper_path.chmod(0o755)

            results_dir = temp_root / "results"
            env = os.environ.copy()
            env["XUUNITY_LIGHT_UNITY_MCP_WRAPPER"] = wrapper_path.as_posix()
            env["XUUNITY_LIGHT_UNITY_MCP_PYTHON"] = Path(sys.executable).as_posix()
            completed = run_with_timeout(
                [
                    BASH,
                    RUNNER.as_posix(),
                    "--repo-root",
                    temp_root.as_posix(),
                    "--project-root",
                    project_root.as_posix(),
                    "--parallelism",
                    "1",
                    "--no-close-live-editors",
                    "--batch-fallback-mode",
                    "require-batch",
                    "--results-dir",
                    results_dir.as_posix(),
                ],
                cwd=OPS_ROOT.as_posix(),
                env=env,
                timeout_seconds=120,
            )

            self.assertNotEqual(0, completed.returncode)
            status = json.loads((results_dir / "ConsumerProject_status.json").read_text(encoding="utf-8"))
            self.assertFalse(status["succeeded"])
            self.assertEqual(1, status["batch_rc"])
            self.assertEqual("batch", status["requested_execution_lane"])
            self.assertEqual("none", status["effective_execution_lane"])
            self.assertEqual("require-batch", status["batch_fallback_mode"])
            self.assertEqual("access_token_unavailable", status["license_blocker_code"])
            self.assertEqual("failed_before_unity", status["operator_verdict"])
            self.assertIn("batch_fallback_mode=require-batch", completed.stdout)
            self.assertIn('"projects_failed": 1', completed.stdout)
            self.assertIn("verdict=failed_before_unity", completed.stdout)


class MultiProjectBatchSelectionTests(unittest.TestCase):
    def write_status(self, directory: Path, name: str, payload: dict) -> None:
        (directory / (name + "_status.json")).write_text(json.dumps(payload), encoding="utf-8")

    def test_legacy_gui_fallback_status_is_selected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self.write_status(
                results_dir,
                "FallbackProject",
                {
                    "project_root": "/tmp/FallbackProject",
                    "recover_rc": 0,
                    "batch_rc": 0,
                    "succeeded": True,
                    "operator_verdict": "passed_via_gui_fallback",
                    "unity_outcome": "passed",
                    "transport_outcome": "gui_operation_completed",
                    "effective_execution_lane": "gui",
                    "matrix_status": "",
                    "failed": 0,
                },
            )

            plan = run_multi_project.build_batch_selection_plan(str(results_dir))

            self.assertEqual(["/tmp/FallbackProject"], plan["selected_projects"])
            self.assertEqual(1, plan["eligible_projects"])
            self.assertEqual(1, plan["legacy_projects"])
            self.assertEqual([], plan["errors"])

    def test_new_gui_fallback_evidence_is_selected_from_matrix(self) -> None:
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self.write_status(
                results_dir,
                "FallbackProject",
                {
                    "project_root": "/tmp/FallbackProject",
                    "compile_evidence": {
                        "schema_version": 1,
                        "outcome": "passed",
                        "evidence_source": "gui_fallback_matrix",
                        "execution_lane": "gui",
                        "matrix": {"status": "passed", "total": 6, "passed": 6, "failed": 0, "skipped": 0},
                    },
                },
            )

            plan = run_multi_project.build_batch_selection_plan(str(results_dir))

            self.assertEqual(["/tmp/FallbackProject"], plan["selected_projects"])
            self.assertEqual(0, plan["legacy_projects"])
            self.assertEqual([], plan["errors"])

    def test_gui_main_passes_fallback_selection_to_workers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results_dir = root / "batch-results"
            gui_results_dir = root / "gui-results"
            results_dir.mkdir()
            self.write_status(
                results_dir,
                "FallbackProject",
                {
                    "project_root": "/tmp/FallbackProject",
                    "compile_evidence": {
                        "schema_version": 1,
                        "outcome": "passed",
                        "evidence_source": "gui_fallback_matrix",
                        "execution_lane": "gui",
                        "matrix": {"status": "passed", "total": 6, "passed": 6, "failed": 0, "skipped": 0},
                    },
                },
            )
            with (
                mock.patch.object(run_multi_project, "require_wrapper"),
                mock.patch.object(run_multi_project, "run_workers") as run_workers,
                mock.patch.object(run_multi_project, "emit_gui_final_summary", return_value=0),
            ):
                result = run_multi_project.main_gui(
                    [
                        "--from-batch-results",
                        str(results_dir),
                        "--results-dir",
                        str(gui_results_dir),
                        "--side-effect-mode",
                        "off",
                    ]
                )

            self.assertEqual(0, result)
            self.assertEqual(["/tmp/FallbackProject"], run_workers.call_args.args[0])

    def test_incomplete_batch_selection_warns_and_never_auto_discovers_projects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self.write_status(
                results_dir,
                "MissingRoot",
                {
                    "compile_evidence": {
                        "schema_version": 1,
                        "outcome": "passed",
                        "evidence_source": "gui_fallback_matrix",
                        "execution_lane": "gui",
                        "matrix": {"status": "passed", "total": 6, "passed": 6, "failed": 0, "skipped": 0},
                    },
                },
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(run_multi_project, "require_wrapper"),
                mock.patch.object(run_multi_project, "discover_project_roots") as discover,
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as raised,
            ):
                run_multi_project.main_gui(["--from-batch-results", str(results_dir)])

            self.assertEqual(2, raised.exception.code)
            self.assertIn("selection_warning=eligible_status_missing_project_root", stdout.getvalue())
            self.assertIn("selection_warning=selection_coverage_mismatch", stdout.getvalue())
            self.assertIn("no workers were started", stderr.getvalue())
            discover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
