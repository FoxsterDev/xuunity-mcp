"""Recovery contracts from dated diagnostics through the real host lifecycle.

The editor transport and OS process enumeration are external boundaries. The
compile gate, lifecycle ordering, file snapshots, journal and command rendering
remain production code.
"""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "templates"))
import server
import server_batch_orchestrator as host
import server_bridge_compile_gate as gate
import server_bridge_state as state_owner
import server_core
import server_launcher
from server_bridge_paths import bridge_config_path, bridge_state_path, request_journal_dir
from server_bridge_transport import FileIpcBridgeTransport
from server_core import ToolInvocationError, write_json, read_json
from server_readiness_summary import build_ensure_ready_summary
from server_recovery_commands import recommended_recovery_command_for_project
from server_registry import BridgeRegistry
from server_project_actions import load_project_action_catalog
import server_setup_common
import server_setup_plan
import server_setup_apply
from server_cli_parser import build_parser


def red_state(root):
    source = root / "Assets" / "Foo.cs"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("broken", encoding="utf-8")
    os.utime(source, (1700000000, 1700000000))
    return {
        "project_root": str(root), "editor_pid": os.getpid(),
        "bridge_generation": 3, "bridge_session_id": "session", "bridge_version": 11,
        "bridge_process_class": "main_editor", "health_status": "healthy",
        "heartbeat_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": "file_ipc", "playmode_state": "edit",
        "script_compilation_failed": True, "compiler_error_count": 1,
        "compiler_diagnostics_source": "compilation_pipeline",
        "compiler_diagnostics_captured_utc": "2026-01-01T00:00:00Z",
        "compiler_diagnostics_bridge_generation": 3,
        "recent_compiler_diagnostics": [{"file": "Assets/Foo.cs", "message": "CS1002"}],
    }


class DiagnosticFreshnessTests(unittest.TestCase):
    def test_unity_roundtrip_timestamp_preserves_subsecond_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            state["compiler_diagnostics_captured_utc"] = "2026-01-01T00:00:00.0350890Z"
            captured = server_core.parse_utc_timestamp(state["compiler_diagnostics_captured_utc"])
            self.assertAlmostEqual(1767225600.035089, captured, places=5)
            os.utime(root / "Assets/Foo.cs", (captured - 0.01, captured - 0.01))
            self.assertEqual("confirmed", gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_trust_class"])
            os.utime(root / "Assets/Foo.cs", (captured + 0.01, captured + 0.01))
            self.assertEqual("stale", gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_trust_class"])

    def test_changed_file_requires_refresh_but_fresh_error_still_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            with self.assertRaises(ToolInvocationError) as raised:
                gate.fail_if_compile_broken_for_operation(root, "unity.tests.run_editmode", state)
            self.assertEqual("compile_broken", raised.exception.code)
            self.assertIn("request-project-refresh", raised.exception.details["recommended_recovery_command"])
            os.utime(root / "Assets/Foo.cs", (1800000000, 1800000000))
            self.assertEqual("stale", gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_trust_class"])
            self.assertTrue(gate.fail_if_compile_broken_for_operation(root, "unity.tests.run_editmode", state))

    def test_a_fix_in_any_compile_input_makes_the_diagnostics_stale(self):
        cases = (
            ("Assets/Component.cs", "source_tree_changed"),
            ("Assets/New/Added.cs", "source_tree_changed"),
            ("Assets/Game.asmdef", "source_tree_changed"),
            ("Packages/com.example.core/Runtime/Core.cs", "source_tree_changed"),
        )
        for relative, reason in cases:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = red_state(root)
                package = root / "Packages" / "com.example.core"
                package.mkdir(parents=True)
                (package / "package.json").write_text("{}", encoding="utf-8")
                os.utime(package / "package.json", (1700000000, 1700000000))
                self.assertEqual("confirmed", gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_trust_class"])
                changed = root / relative
                changed.parent.mkdir(parents=True, exist_ok=True)
                changed.write_text("fixed", encoding="utf-8")
                os.utime(changed, (1800000000, 1800000000))
                trust = gate.compiler_diagnostics_trust_from_state(state, root)
                self.assertEqual("stale", trust["compiler_diagnostics_trust_class"])
                self.assertEqual(reason, trust["compiler_diagnostics_stale_reason"])
                self.assertEqual(relative, trust["compiler_diagnostics_newer_input"])
                self.assertTrue(gate.fail_if_compile_broken_for_operation(root, "unity.tests.run_editmode", state))

    def test_non_input_and_ignored_files_keep_a_fresh_error_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            for relative in ("Assets/Art/icon.png", "Assets/Samples~/Old.cs", "Assets/.hidden/Tmp.cs"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
                os.utime(path, (1800000000, 1800000000))
            self.assertEqual("confirmed", gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_trust_class"])
            with self.assertRaises(ToolInvocationError):
                gate.fail_if_compile_broken_for_operation(root, "unity.tests.run_editmode", state)

    def test_prior_generation_and_undated_legacy_diagnostics_require_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for changes, reason in [({"compiler_diagnostics_bridge_generation": 2}, "diagnostics_from_previous_generation"),
                                    ({"compiler_diagnostics_captured_utc": ""}, "diagnostics_capture_unknown")]:
                with self.subTest(reason=reason):
                    state = {**red_state(root), **changes}
                    self.assertEqual(reason, gate.compiler_diagnostics_trust_from_state(state, root)["compiler_diagnostics_stale_reason"])

    def test_status_and_playmode_exit_do_not_refresh_or_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            self.assertFalse(gate.fail_if_compile_broken_for_operation(root, "unity.status", state))
            self.assertFalse(gate.fail_if_compile_broken_for_operation(root, "unity.playmode.set", state, {"action": "exit"}))


class RecoveryLifecycleTests(unittest.TestCase):
    def run_request(self, root, state, *, after_refresh="passed", timeout_ms=2000):
        write_json(bridge_state_path(root), state)
        write_json(bridge_config_path(root), {"enabled": True, "transport": "file_ipc"})
        registry = BridgeRegistry(ensure_project_root=lambda value: Path(value), refresh_context_state=lambda path: {})
        calls = []
        # A non-reentrant production lock is deliberately retained. If recovery
        # re-enters the public API, fail immediately instead of hanging the suite.
        class BoundedLock:
            def __init__(self):
                self.lock = threading.Lock()
            def __enter__(self):
                if not self.lock.acquire(timeout=0.1):
                    raise AssertionError("recovery reacquired the project request lock")
            def __exit__(self, *args):
                self.lock.release()
        registry.get_or_discover(str(root)).request_lock = BoundedLock()

        def editor_response(transport, project, operation, args, timeout, **kwargs):
            calls.append(operation)
            current = read_json(bridge_state_path(root))
            if operation == "unity.project.refresh":
                current.update({"compiler_error_count": int(after_refresh == "failed"),
                                "script_compilation_failed": after_refresh == "failed",
                                "recent_compiler_diagnostics": [], "compiler_diagnostics_source": ""})
                if after_refresh == "deferred":
                    current.update({"playmode_state": "playing", "is_playing": True})
            request_id = f"request-{len(calls)}"
            current.update({"heartbeat_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "last_processed_request_id": request_id})
            write_json(bridge_state_path(root), current)
            return {"status": "ok", "payload_json": "{}"}, request_id, time.time()

        with (mock.patch.object(server, "_BRIDGE_REGISTRY", registry),
              mock.patch.object(FileIpcBridgeTransport, "invoke", editor_response),
              mock.patch.object(state_owner.time, "sleep", return_value=None)):
            try:
                response = host.invoke_bridge(str(root), "unity.tests.run_editmode", {}, timeout_ms)
            except ToolInvocationError as error:
                response = error
        return calls, response

    def test_stale_error_refreshes_once_then_submits_original_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            state["compiler_diagnostics_bridge_generation"] = 2
            calls, response = self.run_request(root, state)
            self.assertEqual(["unity.project.refresh", "unity.tests.run_editmode"], calls)
            self.assertEqual("ok", response["status"])
            self.assertEqual([], list(request_journal_dir(root).glob("*request_refused.json")))

    def test_recovery_failure_or_deferred_verdict_never_dispatches_test(self):
        for verdict, code in [("failed", "compile_broken"), ("deferred", "compile_verdict_unavailable")]:
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = red_state(root)
                state["compiler_diagnostics_bridge_generation"] = 2
                calls, response = self.run_request(root, state, after_refresh=verdict)
                self.assertEqual(["unity.project.refresh"], calls)
                self.assertEqual(code, response.code)
                events = [read_json(p) for p in request_journal_dir(root).glob("*request_refused.json")]
                self.assertEqual(1, len(events))
                self.assertEqual(code, events[0]["code"])
                self.assertFalse(events[0]["request_submitted"])
                self.assertTrue(events[0]["recommended_recovery_command"])

    def test_fresh_compile_refusal_is_journaled_without_transport_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls, error = self.run_request(root, red_state(root))
            self.assertEqual([], calls)
            self.assertEqual("compile_broken", error.code)
            events = [read_json(p) for p in request_journal_dir(root).glob("*request_refused.json")]
            self.assertEqual(1, len(events))
            self.assertEqual(3, events[0]["state_fingerprint"]["bridge_generation"])

    def test_idle_refusal_is_journaled_without_transport_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = red_state(root)
            state.update({"compiler_error_count": 0, "script_compilation_failed": False,
                          "compile_settle_pending": True, "busy_reason": "compile_settle"})
            calls, error = self.run_request(root, state, timeout_ms=1)
            self.assertEqual([], calls)
            self.assertEqual("editor_idle_timeout", error.code)
            events = [read_json(p) for p in request_journal_dir(root).glob("*request_refused.json")]
            self.assertEqual(1, len(events))
            self.assertEqual("editor_idle_timeout", events[0]["code"])


class RecoveryGuidanceTests(unittest.TestCase):
    def test_dead_and_frozen_snapshots_are_distinct_from_a_live_busy_editor(self):
        for alive, age, frozen in [(False, 1500, True), (True, 1500, True), (True, 5, False)]:
            with self.subTest(alive=alive, age=age), mock.patch.object(state_owner, "pid_is_alive", return_value=alive), mock.patch.object(state_owner, "heartbeat_age_seconds", return_value=age):
                result = state_owner.build_editor_idle_timeout_details(Path("/project"), last_state={
                    "editor_pid": 123, "heartbeat_utc": "2026-01-01T00:00:00Z", "busy_reason": "domain_reload",
                    "busy_reason_detail": "beforeAssemblyReload", "domain_reload_in_progress": True,
                }, reason="tests", timeout_ms=1000, heartbeat_max_age_seconds=10, require_healthy_bridge=False)
                self.assertEqual(frozen, result["state_frozen"])
                self.assertEqual(alive, result["editor_pid_alive"])
                self.assertEqual("beforeAssemblyReload", result["busy_reason_detail"])
                self.assertEqual("2026-01-01T00:00:00Z", result["busy_reason_as_of_utc"])
                expected = "request-status-summary"
                if frozen:
                    expected = "project-discovery-report" if alive else "recover-editor-session"
                self.assertIn(expected, result["recommended_recovery_command"])
                if alive:
                    self.assertNotIn("recover-editor-session", result["recommended_recovery_command"])

    def test_timeout_retains_a_dead_pid_snapshot_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(bridge_state_path(root), {"editor_pid": 123, "heartbeat_utc": "2020-01-01T00:00:00Z", "busy_reason": "domain_reload"})
            with mock.patch.object(state_owner, "pid_is_alive", return_value=False), self.assertRaises(ToolInvocationError) as raised:
                state_owner.wait_for_editor_idle(root, 0, 10, "tests")
            self.assertEqual("editor_state_frozen", raised.exception.details["classification"])
            self.assertEqual("domain_reload", raised.exception.details["busy_reason"])

    def test_readiness_renders_recovery_action_instead_of_recommending_itself(self):
        root = Path("/project with spaces")
        for action in ("recover_editor_session", "close_same_project_editor_or_use_interactive_lane", "wait_for_editor_idle_or_inspect_busy_state"):
            with self.subTest(action=action):
                result = build_ensure_ready_summary(root, {"bridge_state": {"health_status": "degraded"}, "discovery": {"host_health_recommended_next_action": action}})
                self.assertEqual(recommended_recovery_command_for_project(root, action), result["recovery_command"])
                self.assertNotIn("ensure-ready", result["recovery_command"])

    @mock.patch.object(server_core, "is_windows_like_host", lambda: False)
    @mock.patch.dict(os.environ, {"XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME": "", "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_PATH": ""})
    def test_incident_recovery_actions_resolve_to_parseable_commands(self):
        import shlex
        for action in ("run_compile_gate_and_fix_errors", "fix_compile_errors",
                       "refresh_stale_compiler_diagnostics", "recover_editor_session",
                       "wait_for_editor_idle_or_inspect_busy_state", "exit_playmode_before_editing"):
            command = recommended_recovery_command_for_project(Path("/project with spaces"), action)
            self.assertTrue(command, action)
            parsed = build_parser().parse_args(shlex.split(command)[1:])
            self.assertEqual("/project with spaces", parsed.project_root)

    def test_wrapper_help_lists_every_parser_command_and_required_flags(self):
        parser = build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        output = io.StringIO()
        with redirect_stdout(output):
            server_launcher.print_wrapper_help()
        lines = output.getvalue().splitlines()
        self.assertLessEqual(len(lines), 90)
        for name, command in sub.choices.items():
            matching = [line for line in lines if line.startswith("  " + name + " ")]
            self.assertEqual(1, len(matching), name)
            for action in command._actions:
                if action.required:
                    self.assertIn(action.option_strings[0] if action.option_strings else action.dest, matching[0])



class ArchivedBoundaryReplayTests(unittest.TestCase):
    def test_archived_undated_confirmed_error_is_now_stale(self):
        fixture = read_json(ROOT / "tests/fixtures/retro_recovery_cases.json")
        state = fixture["legacy_compile_refusal"]
        self.assertEqual("confirmed", state["compiler_diagnostics_trust_class"])
        self.assertEqual("stale", gate.compiler_diagnostics_trust_from_state(state)["compiler_diagnostics_trust_class"])
        self.assertTrue(gate.fail_if_compile_broken_for_operation(Path("/example"), "unity.tests.run_playmode", state))

    def test_archived_alive_healthy_snapshot_is_frozen_by_heartbeat_age(self):
        fixture = read_json(ROOT / "tests/fixtures/retro_recovery_cases.json")["frozen_live_editor"]
        now = 1800000000.0
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - fixture["observed_heartbeat_age_seconds"]))
        state = {**fixture["state"], "heartbeat_utc": stamp, "editor_pid": 123}
        with mock.patch.object(state_owner, "pid_is_alive", return_value=fixture["pid_alive"]), mock.patch.object(state_owner.time, "time", return_value=now):
            result = state_owner.build_editor_idle_timeout_details(Path("/example"), last_state=state,
                reason="before unity.tests.run_editmode", timeout_ms=1000, heartbeat_max_age_seconds=10, require_healthy_bridge=False)
        self.assertEqual("editor_alive_but_unresponsive", result["classification"])
        self.assertTrue(result["state_frozen"])
        self.assertTrue(result["editor_pid_alive"])
        self.assertEqual("AssetPostprocessor activity", result["busy_reason_detail"])
        self.assertEqual(stamp, result["busy_reason_as_of_utc"])
        self.assertEqual("inspect_editor_log_and_observe", result["recommended_next_action"])
        self.assertNotIn("recover-editor-session", result["recommended_recovery_command"])


class LiveEditorRecoveryAuthorityTests(unittest.TestCase):
    """RG-01: recover-editor-session never quits or kills a live editor without --force-terminate."""

    def run_recover(self, *, opened_by_host, force_terminate, observe_returncode=1, observe_payload=None):
        import server_cli_bridge_commands as commands

        args = argparse.Namespace(
            project_root="/tmp/FakeProject", timeout_ms=180000, close_timeout_ms=1000, open_editor=True,
            force_compile_probe=False, compile_preflight="off", heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block", force_terminate=force_terminate,
            observe_timeout_ms=30000,
        )
        restore = mock.Mock(return_value={"closeout_verified": True})
        terminate = mock.Mock(return_value=True)
        observe = mock.Mock(return_value=(observe_payload or {"error": {"code": "editor_process_alive_bridge_never_attached", "details": {}}}, mock.Mock(returncode=observe_returncode, stderr="")))
        stdout = io.StringIO()
        code = 0
        patches = {
            "ensure_project_root": mock.Mock(return_value=Path("/tmp/FakeProject")),
            "refresh_project_context": mock.Mock(),
            "build_project_discovery_report": mock.Mock(return_value={"detected_editor_pids": [os.getpid()]}),
            "current_project_context_host_session_state": mock.Mock(return_value={"opened_by_host": opened_by_host, "editor_pid": os.getpid()}),
            "restore_host_opened_editor_state": restore,
            "run_self_json_command_with_completed": observe,
            "run_editor_open_compile_preflight": mock.Mock(return_value={"verdict": "skipped"}),
        }
        with mock.patch.multiple(commands, **patches), mock.patch.object(state_owner, "pid_is_alive", return_value=True), redirect_stdout(stdout):
            with mock.patch("server_editor_host_lifecycle.terminate_editor_pid", terminate):
                try:
                    commands.cmd_recover_editor_session(args)
                except SystemExit as exc:
                    code = int(exc.code or 0)
        return json.loads(stdout.getvalue()), code, restore, terminate, observe

    def test_a_live_host_opened_editor_is_observed_not_closed(self):
        payload, code, restore, terminate, observe = self.run_recover(opened_by_host=True, force_terminate=False)
        self.assertEqual(1, code)
        self.assertEqual("live_editor_refused", payload["recovery_classification"])
        self.assertEqual("observe_only_without_force_terminate", payload["live_editor_policy"])
        self.assertIn("--force-terminate", payload["force_terminate_command"])
        restore.assert_not_called()
        terminate.assert_not_called()
        observe_args = observe.call_args.args[0]
        self.assertNotIn("--open-editor", observe_args)
        self.assertEqual("30000", observe_args[observe_args.index("--timeout-ms") + 1])

    def test_a_live_editor_the_host_did_not_open_is_never_reported_recovered(self):
        payload, code, restore, terminate, _ = self.run_recover(opened_by_host=False, force_terminate=False)
        self.assertEqual(1, code)
        self.assertEqual("live_editor_not_host_owned", payload["recovery_classification"])
        self.assertEqual("", payload["force_terminate_command"])
        restore.assert_not_called()
        terminate.assert_not_called()

    def test_a_live_editor_whose_bridge_attaches_is_reported_as_such(self):
        payload, code, restore, _, _ = self.run_recover(opened_by_host=True, force_terminate=False, observe_returncode=0, observe_payload={"verdict": "ready"})
        self.assertEqual(0, code)
        self.assertEqual("live_editor_bridge_attached", payload["recovery_classification"])
        restore.assert_not_called()

    def test_a_modal_recommendation_for_a_host_opened_editor_carries_the_explicit_authority(self):
        modal = {"error": {"code": "editor_startup_modal_blocked", "details": {
            "recommended_next_action": "quit_editor_batch_compile_then_reopen",
            "recommended_recovery_command": "launcher recover-editor-session --project-root /tmp/FakeProject --force-compile-probe --open-editor",
        }}}
        payload, code, restore, _, _ = self.run_recover(opened_by_host=True, force_terminate=False, observe_payload=modal)
        self.assertEqual(1, code)
        self.assertEqual("quit_editor_batch_compile_then_reopen", payload["recovery_recommended_next_action"])
        self.assertIn("--force-terminate", payload["recommended_recovery_command"])
        restore.assert_not_called()

    def test_force_terminate_is_the_only_path_to_the_closeout(self):
        payload, code, restore, _, observe = self.run_recover(opened_by_host=True, force_terminate=True, observe_returncode=0, observe_payload={"verdict": "ready"})
        restore.assert_called_once()
        self.assertTrue(payload["closeout_attempted"])

    def test_enrichment_never_pairs_a_kill_recommendation_with_an_observe_only_policy(self):
        from server_project_reporting import enrich_error_details_with_discovery_data

        enriched = enrich_error_details_with_discovery_data(
            Path("/project"),
            details={"recommended_next_action": "recover_editor_session", "editor_pid_alive": True},
            discovery={"host_health_termination_policy": "observe_only", "host_health_recommended_next_action": "inspect_editor_log_and_observe"},
            recommended_recovery_command_for_project=recommended_recovery_command_for_project,
        )
        self.assertEqual("inspect_editor_log_and_observe", enriched["recommended_next_action"])
        self.assertNotIn("recover-editor-session", enriched["recommended_recovery_command"])


class SetupAndCatalogGuidanceTests(unittest.TestCase):
    @mock.patch.object(server_core, "is_windows_like_host", lambda: False)
    def test_missing_and_empty_catalog_offer_a_parseable_scaffold(self):
        import shlex
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for contents in (None, "", "schemaVersion: xuunity.project-actions.v1\nactions: {}\n"):
                with self.subTest(contents=contents):
                    catalog = root / "project_actions.yaml"
                    if contents is not None:
                        catalog.write_text(contents, encoding="utf-8")
                    with self.assertRaises(ToolInvocationError) as raised:
                        load_project_action_catalog(root, str(catalog) if contents is not None else "")
                    parsed = build_parser().parse_args(shlex.split(raised.exception.details["recommended_recovery_command"])[1:])
                    self.assertEqual("project-hook-scaffold", parsed.command)
                    self.assertTrue(parsed.write)

    def test_setup_warns_about_attachment_only_for_live_first_install(self):
        for live, installed in [(True, False), (False, False), (True, True)]:
            with self.subTest(live=live, installed=installed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "Assets").mkdir()
                (root / "ProjectSettings").mkdir()
                (root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.58f2", encoding="utf-8")
                write_json(root / "Packages/manifest.json", {"dependencies": {"com.xuunity.light-mcp": "file:existing"} if installed else {}})
                with mock.patch.object(server_setup_common, "find_running_unity_editors_for_project", return_value=[{"pid": 123}] if live else []):
                    plan = server_setup_plan.build_setup_plan(workspace_root=None, project_roots=[str(root)], recursive=False, include_test_framework="no", package_source="file", package_version="", local_package_source=str(ROOT / "packages/com.xuunity.light-mcp"))
                    expected = [str(root.resolve())] if live and not installed else []
                    self.assertEqual(expected, plan["unity_editor_bridge_attachment_pending"])
                    applied = server_setup_apply.apply_setup_plan(plan, approve=True)
                    self.assertEqual(expected, applied["unity_editor_bridge_attachment_pending"])
                    if expected:
                        self.assertIn("If refresh does not attach", applied["unity_editor_bridge_attachment_message"])
                    self.assertNotIn("unity_editor_restart_required", applied)


if __name__ == "__main__":
    unittest.main()
