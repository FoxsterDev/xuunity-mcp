"""Closed-editor compile preflight: the persisted RG-42 input snapshot decides whether a batch compile runs first."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_recovery
import server_cli_bridge_commands
import server_editor_input_snapshot as snapshot_module
from server_core import ToolInvocationError

COMPILED_EPOCH = 1_800_000_000.0


def write(path: Path, text: str, mtime: float = COMPILED_EPOCH - 60) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


class SnapshotFixture(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        self.root = Path(temp.name) / "Project"
        self.outside = Path(outside.name)
        write(self.root / "Assets/Scripts/Board.cs", "class Board {}")
        write(self.root / "Packages/com.example.core/package.json", "{}")
        write(self.root / "Packages/com.example.core/Runtime/JsonUtils.cs", "class JsonUtils {}")
        write(self.root / "Packages/com.example.core/Samples~/Ignored.cs", "class Ignored {}")
        write(self.outside / "package.json", "{}")
        write(self.outside / "Shared.cs", "class Shared {}")
        write(
            self.root / "Packages/manifest.json",
            json.dumps({"dependencies": {"com.example.shared": "file:" + str(self.outside), "com.example.tarball": "file:Tarballs/x-1.0.0.tgz"}}),
        )

    def persist(self, *, outcome: str = "succeeded", dirty: list[str] | None = None, drop: str = "") -> None:
        keys = sorted(
            snapshot_module.editor_input_key(self.root, path)
            for path in snapshot_module.iter_editor_inputs(snapshot_module.resolve_editor_input_roots(self.root))
        )
        hashes = []
        for key in keys:
            path = Path(key) if os.path.isabs(key) else self.root / key
            hashes.append(snapshot_module.hash_editor_input(path))
        if drop:
            index = keys.index(drop)
            del keys[index], hashes[index]
        target = snapshot_module.editor_input_snapshot_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "trigger": "compilation_finished",
                    "basis_utc": "2027-01-15T08:00:00.0000000Z",
                    "captured_utc": "2027-01-15T08:00:01.0000000Z",
                    "editor_pid": 4242,
                    "compile_outcome": outcome,
                    "compile_error_count": 1 if outcome == "failed" else 0,
                    "input_count": len(keys),
                    "paths": keys,
                    "hashes": hashes,
                    "dirty_at_capture": dirty or [],
                }
            ),
            encoding="utf-8",
        )


class HashAndScanParityTests(SnapshotFixture):
    def test_the_hash_is_fnv1a64_with_the_length_prefix_the_editor_writes(self) -> None:
        for text, expected in ((b"", "0:cbf29ce484222325"), (b"a", "1:af63dc4c8601ec8c"), (b"foobar", "6:85944171f73967e8")):
            path = self.root / "h.bin"
            path.write_bytes(text)
            self.assertEqual(expected, snapshot_module.hash_editor_input(path))

    def test_the_scan_covers_assets_embedded_and_local_packages_but_not_ignored_or_tarball_entries(self) -> None:
        keys = [
            snapshot_module.editor_input_key(self.root, path)
            for path in snapshot_module.iter_editor_inputs(snapshot_module.resolve_editor_input_roots(self.root))
        ]
        self.assertIn("Assets/Scripts/Board.cs", keys)
        self.assertIn("Packages/com.example.core/Runtime/JsonUtils.cs", keys)
        self.assertTrue(any(key.endswith("Shared.cs") for key in keys))
        self.assertFalse(any("Samples~" in key for key in keys))
        self.assertEqual(3, len(keys))


class ComparisonTests(SnapshotFixture):
    def compare(self) -> dict:
        return snapshot_module.compare_editor_inputs_with_snapshot(self.root)

    def test_no_snapshot_is_unavailable_and_never_runs_a_probe(self) -> None:
        decision = snapshot_module.editor_open_compile_preflight_decision(self.root)
        self.assertEqual("unavailable", decision["input_comparison"]["state"])
        self.assertFalse(decision["run_compile_probe"])
        self.assertEqual("input_snapshot_unavailable", decision["reason"])

    def test_a_touch_without_a_content_change_stays_unchanged(self) -> None:
        self.persist()
        os.utime(self.root / "Assets/Scripts/Board.cs", (COMPILED_EPOCH + 600, COMPILED_EPOCH + 600))
        comparison = self.compare()
        self.assertEqual("ready", comparison["state"])
        self.assertEqual(0, comparison["changed_count"])
        decision = snapshot_module.editor_open_compile_preflight_decision(self.root)
        self.assertFalse(decision["run_compile_probe"])
        self.assertEqual("editor_inputs_unchanged_since_last_compile", decision["reason"])

    def test_content_edits_new_deleted_and_dirty_files_are_changes(self) -> None:
        self.persist()
        write(self.root / "Assets/Scripts/Board.cs", "class Board { Missing m; }", COMPILED_EPOCH + 600)
        self.assertEqual(["Assets/Scripts/Board.cs"], self.compare()["changed_paths"])

        self.persist(drop="Assets/Scripts/Board.cs")
        self.assertEqual(["Assets/Scripts/Board.cs"], self.compare()["changed_paths"])

        self.persist()
        (self.root / "Packages/com.example.core/Runtime/JsonUtils.cs").unlink()
        self.assertEqual(["Packages/com.example.core/Runtime/JsonUtils.cs"], self.compare()["changed_paths"])

        self.persist(dirty=["Assets/Scripts/Board.cs"])
        self.assertEqual(["Assets/Scripts/Board.cs"], self.compare()["changed_paths"])

    def test_a_recorded_red_compile_runs_the_probe_without_any_change(self) -> None:
        self.persist(outcome="failed")
        decision = snapshot_module.editor_open_compile_preflight_decision(self.root)
        self.assertTrue(decision["run_compile_probe"])
        self.assertEqual("last_recorded_compile_failed", decision["reason"])

    def test_a_torn_snapshot_is_unavailable(self) -> None:
        target = snapshot_module.editor_input_snapshot_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"paths": ["a"', encoding="utf-8")
        self.assertEqual("snapshot_missing_or_unreadable", self.compare()["reason"])


class PreflightVerdictTests(SnapshotFixture):
    def probe(self, *, succeeded: bool, log_text: str = "", conflict: bool = False) -> dict:
        log = self.root / "batch.log"
        log.write_text(log_text, encoding="utf-8")
        result = {"succeeded": succeeded, "batch_exit_code": 0 if succeeded else 1, "log_path": str(log)}
        if conflict:
            result["batch_probe"] = {"error": {"code": "editor_running_batch_conflict"}}
        return result

    def run_preflight(self, probe: dict, mode: str = "auto") -> tuple[dict, mock.Mock]:
        probe_mock = mock.Mock(return_value=probe)
        with mock.patch.object(server_batch_recovery, "run_batch_build_config_compile_matrix_probe", probe_mock):
            return server_batch_recovery.run_editor_open_compile_preflight(self.root, timeout_ms=1000, mode=mode), probe_mock

    def test_red_needs_compile_errors_in_the_batch_log(self) -> None:
        self.persist()
        write(self.root / "Assets/Scripts/Board.cs", "class Board { Missing m; }", COMPILED_EPOCH + 600)
        red, _ = self.run_preflight(self.probe(succeeded=False, log_text="Assets/Scripts/Board.cs(1,15): error CS0246: The type 'Missing' could not be found\n"))
        self.assertEqual("red", red["verdict"])
        self.assertEqual(1, red["compile_errors_observed"])
        self.assertIn("error CS0246", red["compile_error_lines"][0])
        inconclusive, _ = self.run_preflight(self.probe(succeeded=False, log_text="License error\n"))
        self.assertEqual("inconclusive", inconclusive["verdict"])
        blocked, _ = self.run_preflight(self.probe(succeeded=False, conflict=True))
        self.assertEqual("blocked_by_live_editor", blocked["verdict"])
        green, _ = self.run_preflight(self.probe(succeeded=True))
        self.assertEqual("green", green["verdict"])

    def test_a_project_without_a_build_config_falls_back_to_a_host_standalone_batch_compile(self) -> None:
        self.persist()
        write(self.root / "Assets/Scripts/Board.cs", "class Board { Missing m; }", COMPILED_EPOCH + 600)
        missing = {"succeeded": False, "batch_probe": {"error": {"code": "build_config_asset_not_found"}}}
        red = self.probe(succeeded=False, log_text="Assets/Scripts/Board.cs(1,15): error CS0246: missing\n")
        probe = mock.Mock(side_effect=[missing, red])
        with mock.patch.object(server_batch_recovery, "run_batch_build_config_compile_matrix_probe", probe), \
                mock.patch.object(server_batch_recovery, "host_standalone_build_target", return_value="StandaloneOSX"):
            preflight = server_batch_recovery.run_editor_open_compile_preflight(self.root, timeout_ms=1000)
        self.assertEqual("red", preflight["verdict"])
        self.assertEqual("build_config_asset_not_found", preflight["compile_probe_fallback_reason"])
        self.assertEqual("batch_compile_host_standalone", preflight["compile_probe_lane"])
        self.assertEqual("StandaloneOSX", probe.call_args_list[1].kwargs["fallback_target"])

    def test_off_and_unchanged_inputs_never_spawn_the_probe(self) -> None:
        self.persist()
        off, probe = self.run_preflight(self.probe(succeeded=False), mode="off")
        self.assertEqual("skipped", off["verdict"])
        probe.assert_not_called()
        unchanged, probe = self.run_preflight(self.probe(succeeded=False))
        self.assertEqual("not_needed", unchanged["verdict"])
        probe.assert_not_called()


class EnsureReadyPreflightTests(unittest.TestCase):
    def args(self, **overrides) -> argparse.Namespace:
        values = dict(
            project_root="/tmp/FakeProject", open_editor=True, unity_app=None, editor_log_path=None,
            background_open=False, timeout_ms=120000, heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block", compile_preflight="auto",
        )
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_ensure_ready(self, preflight: dict, *, detected_editor_count: int = 0, **arg_overrides):
        preflight_mock = mock.Mock(return_value=preflight)
        open_mock = mock.Mock(return_value={"reused_existing_editor": False, "editor_pid": 2468})
        with ExitStack() as stack:
            for name, value in (
                ("ensure_project_root", mock.Mock(return_value=Path("/tmp/FakeProject"))),
                ("resolve_editor_log_path", mock.Mock(return_value=Path("/tmp/editor.log"))),
                ("build_project_discovery_report", mock.Mock(return_value={"detected_editor_count": detected_editor_count})),
                ("current_project_context_bridge_state", mock.Mock(return_value={})),
                ("inspect_light_mcp_import_state", mock.Mock(return_value={"import_state": "resolved", "bridge_state_present": True})),
                ("bridge_config_state", mock.Mock(return_value={"enabled": True})),
                ("detect_unity_app_path_for_project", mock.Mock(return_value=Path("/Applications/Unity.app"))),
                ("open_unity_editor", open_mock),
                ("run_editor_open_compile_preflight", preflight_mock),
                ("wait_for_ready", mock.Mock(return_value={"editor_pid": 2468, "health_status": "healthy"})),
                ("update_host_editor_session_pid", mock.Mock()),
                ("refresh_project_context", mock.Mock()),
                ("inspect_package_dependency_alignment", mock.Mock(return_value={})),
                ("enrich_tool_invocation_error_with_discovery", mock.Mock(side_effect=lambda _, exc: exc)),
            ):
                stack.enter_context(mock.patch.object(server, name, value))
            stdout = io.StringIO()
            stack.enter_context(redirect_stdout(stdout))
            try:
                server.cmd_ensure_ready(self.args(**arg_overrides))
                outcome = json.loads(stdout.getvalue())
            except ToolInvocationError as exc:
                outcome = exc
        return outcome, preflight_mock, open_mock

    def test_a_red_preflight_refuses_the_gui_open(self) -> None:
        outcome, preflight, open_editor = self.run_ensure_ready(
            {"verdict": "red", "reason": "editor_inputs_changed_since_last_compile", "compile_errors_observed": 1, "compile_error_lines": ["error CS0246"]}
        )
        self.assertIsInstance(outcome, ToolInvocationError)
        self.assertEqual("editor_open_refused_compile_red", outcome.code)
        self.assertTrue(outcome.details["reopen_blocked"])
        self.assertEqual(["error CS0246"], outcome.details["compile_error_lines"])
        open_editor.assert_not_called()

    def test_green_or_not_needed_preflights_open_and_are_reported(self) -> None:
        for verdict in ("green", "not_needed", "inconclusive"):
            with self.subTest(verdict=verdict):
                outcome, preflight, open_editor = self.run_ensure_ready({"verdict": verdict, "reason": "x"})
                self.assertIsInstance(outcome, dict)
                self.assertEqual(verdict, outcome["compile_preflight"]["verdict"])
                open_editor.assert_called_once()

    def test_the_preflight_mode_is_forwarded_and_a_live_editor_skips_it(self) -> None:
        _, preflight, _ = self.run_ensure_ready({"verdict": "skipped"}, compile_preflight="off")
        self.assertEqual("off", preflight.call_args.kwargs["mode"])
        _, preflight, _ = self.run_ensure_ready({"verdict": "red"}, detected_editor_count=1)
        preflight.assert_not_called()


class RecoverEditorSessionPreflightTests(unittest.TestCase):
    def run_recover(self, preflight: dict) -> tuple[dict, int]:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject", timeout_ms=1000, close_timeout_ms=1000, open_editor=True,
            force_compile_probe=False, compile_preflight="auto", heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block",
        )
        stdout = io.StringIO()
        code = 0
        ensure = mock.Mock(return_value=({"ok": True}, mock.Mock(returncode=0)))
        with ExitStack() as stack:
            for name, value in (
                ("ensure_project_root", mock.Mock(return_value=Path("/tmp/FakeProject"))),
                ("refresh_project_context", mock.Mock()),
                ("build_project_discovery_report", mock.Mock(return_value={"detected_editor_pids": []})),
                ("current_project_context_host_session_state", mock.Mock(return_value={})),
                ("run_editor_open_compile_preflight", mock.Mock(return_value=preflight)),
                ("run_self_json_command_with_completed", ensure),
            ):
                stack.enter_context(mock.patch.object(server_cli_bridge_commands, name, value))
            stack.enter_context(redirect_stdout(stdout))
            try:
                server_cli_bridge_commands.cmd_recover_editor_session(args)
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(stdout.getvalue())
        payload["_reopen_attempted"] = ensure.called
        return payload, code

    def test_a_red_preflight_blocks_the_reopen(self) -> None:
        payload, code = self.run_recover({"verdict": "red", "run_compile_probe": True})
        self.assertEqual(1, code)
        self.assertTrue(payload["reopen_blocked"])
        self.assertEqual("compile_red_confirmed", payload["recovery_classification"])
        self.assertFalse(payload["_reopen_attempted"])

    def test_an_unchanged_project_reopens_without_a_probe(self) -> None:
        payload, code = self.run_recover({"verdict": "not_needed", "run_compile_probe": False})
        self.assertEqual(0, code)
        self.assertFalse(payload["compile_probe_attempted"])
        self.assertTrue(payload["_reopen_attempted"])



class EnsureReadyMcpToolTests(unittest.TestCase):
    def call(self, arguments: dict, *, returncode: int, payload: dict | None):
        import server_batch_orchestrator as orchestrator

        runner = mock.Mock(return_value=(payload, mock.Mock(returncode=returncode, stderr="", stdout="")))
        with mock.patch.object(orchestrator, "run_self_json_command_with_completed", runner), \
                mock.patch.object(orchestrator, "ensure_project_root", return_value=Path("/tmp/FakeProject")):
            result = orchestrator.call_tool("unity_ensure_ready", arguments)
        return result, runner.call_args.args[0] if runner.called else None

    def test_the_tool_forwards_the_cli_flags(self) -> None:
        result, command = self.call(
            {"projectRoot": "/tmp/FakeProject", "openEditor": True, "compilePreflight": "off", "timeoutMs": 60000},
            returncode=0, payload={"verdict": "ready", "succeeded": True},
        )
        self.assertFalse(result["isError"])
        self.assertEqual("ready", result["structuredContent"]["verdict"])
        self.assertEqual("ensure-ready", command[0])
        self.assertIn("--open-editor", command)
        self.assertEqual("off", command[command.index("--compile-preflight") + 1])
        self.assertEqual("60000", command[command.index("--timeout-ms") + 1])
        self.assertNotIn("--include-full-payload", command)

    def test_typed_exits_keep_their_code_and_recovery(self) -> None:
        for code in ("editor_startup_modal_blocked", "editor_open_refused_compile_red", "launch_blocked_probable_modal"):
            with self.subTest(code=code):
                error = {"error": {"code": code, "message": "m", "details": {"recommended_next_action": "x", "recommended_recovery_command": "launcher recover"}}}
                result, _ = self.call({"projectRoot": "/tmp/FakeProject", "openEditor": True}, returncode=1, payload=error)
                self.assertTrue(result["isError"])
                self.assertEqual(code, result["structuredContent"]["error"]["code"])
                self.assertEqual("launcher recover", result["structuredContent"]["error"]["details"]["recommended_recovery_command"])

    def test_a_crash_without_json_still_returns_a_typed_error(self) -> None:
        result, _ = self.call({"projectRoot": "/tmp/FakeProject"}, returncode=2, payload=None)
        self.assertTrue(result["isError"])
        self.assertEqual("ensure_ready_failed", result["structuredContent"]["error"]["code"])

    def test_bad_arguments_are_refused_before_anything_runs(self) -> None:
        from server_mcp_protocol import JsonRpcError

        for arguments in ({"projectRoot": "/tmp/FakeProject", "compilePreflight": "sometimes"}, {"projectRoot": "/tmp/FakeProject", "openEditor": "yes"}):
            with self.subTest(arguments=arguments), self.assertRaises(JsonRpcError):
                self.call(arguments, returncode=0, payload={})


if __name__ == "__main__":
    unittest.main()
