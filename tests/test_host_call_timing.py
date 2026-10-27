import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_host_call_timing as timing
import server_mcp_protocol as protocol


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += int(seconds * 1_000_000_000)


class HostCallTimingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.environment = mock.patch.dict(os.environ, {"XUUNITY_HOST_CALL_TIMING": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        patcher = mock.patch.object(timing.time, "monotonic_ns", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nested_stages_are_exclusive_and_remainder_is_retained(self):
        with timing.host_call_timing_scope("direct_handler") as call:
            self.clock.advance(2)
            with timing.measure_host_stage("activation"):
                self.clock.advance(3)
                with timing.measure_host_stage("context_discovery"):
                    self.clock.advance(4)
                self.clock.advance(2)
            self.clock.advance(1)
            report = call.snapshot("before_response_serialization")
        self.assertEqual(12, report["total_seconds"])
        self.assertEqual(5, report["stages"]["activation"]["duration_seconds"])
        self.assertEqual(4, report["stages"]["context_discovery"]["duration_seconds"])
        self.assertEqual(3, report["unattributed_seconds"])
        self.assertIsNone(report["stages"]["serialization"]["duration_seconds"])
        self.assertEqual("unmeasured", report["stages"]["serialization"]["status"])
        self.assertEqual(report["total_seconds"], report["measured_stage_total_seconds"] + report["unattributed_seconds"])

    def test_failed_attempt_and_retry_both_contribute(self):
        with timing.host_call_timing_scope("direct_handler") as call:
            with self.assertRaisesRegex(RuntimeError, "transport"):
                with timing.measure_host_stage("dispatch_unity_wait"):
                    self.clock.advance(3)
                    raise RuntimeError("transport")
            with timing.measure_host_stage("activation"):
                self.clock.advance(2)
            with timing.measure_host_stage("dispatch_unity_wait"):
                self.clock.advance(4)
            report = call.snapshot("completed")
        dispatch = report["stages"]["dispatch_unity_wait"]
        self.assertEqual(7, dispatch["duration_seconds"])
        self.assertEqual(2, dispatch["invocation_count"])
        self.assertEqual(1, dispatch["failure_count"])
        self.assertEqual(9, report["total_seconds"])

    def test_same_stage_reentry_does_not_double_count(self):
        with timing.host_call_timing_scope("direct_handler") as call:
            with timing.measure_host_stage("context_discovery"):
                self.clock.advance(1)
                with timing.measure_host_stage("context_discovery"):
                    self.clock.advance(2)
                self.clock.advance(3)
            report = call.snapshot("completed")
        self.assertEqual(6, report["measured_stage_total_seconds"])
        self.assertEqual(0, report["unattributed_seconds"])

    def test_scope_reset_and_negative_accounting_are_observable(self):
        with self.assertRaises(RuntimeError):
            with timing.host_call_timing_scope("first"):
                raise RuntimeError()
        with timing.host_call_timing_scope("second") as call:
            with timing.measure_host_stage("serialization"):
                self.clock.advance(2)
            self.clock.advance(-1)
            report = call.snapshot("completed")
        self.assertEqual("second", report["scope"])
        self.assertFalse(report["accounting_valid"])
        self.assertEqual(-1, report["unattributed_seconds"])

    def test_disabled_scope_is_noop(self):
        with mock.patch.dict(os.environ, {"XUUNITY_HOST_CALL_TIMING": "0"}):
            with timing.host_call_timing_scope("disabled") as call:
                self.assertIsNone(call)
                with timing.measure_host_stage("serialization"):
                    self.clock.advance(1)

    def test_timed_call_preserves_return_and_exception(self):
        def callback(fail=False):
            self.clock.advance(2)
            if fail:
                raise ValueError("original")
            return "returned"

        with timing.host_call_timing_scope("direct_handler") as call:
            self.assertEqual("returned", timing.timed_host_call("dispatch_unity_wait", callback))
            with self.assertRaisesRegex(ValueError, "original"):
                timing.timed_host_call("dispatch_unity_wait", callback, fail=True)
            report = call.snapshot("completed")
        self.assertEqual(4, report["stages"]["dispatch_unity_wait"]["duration_seconds"])
        self.assertEqual(1, report["stages"]["dispatch_unity_wait"]["failure_count"])

    def test_disabled_protocol_keeps_existing_envelope(self):
        expected = {"content": [], "structuredContent": {"status": "passed"}, "isError": False}
        with mock.patch.dict(os.environ, {"XUUNITY_HOST_CALL_TIMING": "0"}):
            response = protocol.handle_json_rpc_message(
                {"id": 9, "method": "tools/call", "params": {"name": "example"}}, {},
                protocol_version="test", server_info={}, tools={}, call_tool=lambda name, args: expected,
            )
        self.assertEqual({"jsonrpc": "2.0", "id": 9, "result": expected}, response)

    def test_stdout_failure_receipt_is_partial_and_preserves_io_error(self):
        class BrokenOutput(io.StringIO):
            def write(self, value):
                raise OSError("pipe closed")

        stderr = io.StringIO()
        with timing.host_call_timing_scope("stdio_received_line") as call:
            call.tool_name = "example"
            with contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(stderr):
                with self.assertRaisesRegex(OSError, "pipe closed"):
                    protocol.emit_message({"result": {}})
        receipt = json.loads(stderr.getvalue())
        self.assertEqual("stdout_emission_failed", receipt["boundary"])
        self.assertEqual("failed", receipt["outcome"])

    def test_stdio_receipt_measures_encoding_and_flush_without_changing_payload(self):
        clock = self.clock

        class Output(io.StringIO):
            def write(self, value):
                clock.advance(3)
                return super().write(value)

            def flush(self):
                clock.advance(4)
                return super().flush()

        original_dumps = json.dumps

        def encode(*args, **kwargs):
            encoded = original_dumps(*args, **kwargs)
            clock.advance(2)
            return encoded

        expected = {"content": [{"type": "text", "text": "unchanged"}], "structuredContent": {"status": "passed"}, "isError": False}

        def tool(name, arguments):
            with timing.measure_host_stage("dispatch_unity_wait"):
                clock.advance(5)
            return expected

        def handle(message, session):
            return protocol.handle_json_rpc_message(message, session, protocol_version="test", server_info={}, tools={}, call_tool=tool)

        request = original_dumps({"id": 17, "method": "tools/call", "params": {"name": "example", "arguments": {}}}) + "\n"
        stdout, stderr = Output(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(request)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), mock.patch.object(protocol.json, "dumps", side_effect=encode):
            self.assertEqual(0, protocol.serve_stdio(protocol_version="test", handle_message=handle))
        frames = stdout.getvalue().splitlines()
        self.assertEqual(1, len(frames))
        result = json.loads(frames[0])["result"]
        self.assertEqual(expected, {key: value for key, value in result.items() if key != "_meta"})
        snapshot = result["_meta"]["xuunity_host_timing"]
        self.assertEqual("before_response_serialization", snapshot["boundary"])
        self.assertIsNone(snapshot["stages"]["serialization"]["duration_seconds"])
        receipt = json.loads(stderr.getvalue())
        self.assertEqual(17, receipt["request_id"])
        self.assertEqual("stdout_flush_returned", receipt["boundary"])
        self.assertEqual(14, receipt["total_seconds"])
        self.assertEqual(2, receipt["stages"]["serialization"]["duration_seconds"])
        self.assertEqual(7, receipt["unattributed_seconds"])

    def test_direct_handler_reports_narrower_scope_and_invalid_calls_reset(self):
        kwargs = dict(protocol_version="test", server_info={}, tools={}, call_tool=lambda name, args: {"content": []})
        with self.assertRaises(protocol.JsonRpcError):
            protocol.handle_json_rpc_message({"method": "tools/call", "params": {"name": 7}}, {}, **kwargs)
        response = protocol.handle_json_rpc_message({"method": "tools/call", "params": {"name": "example"}}, {}, **kwargs)
        snapshot = response["result"]["_meta"]["xuunity_host_timing"]
        self.assertEqual("direct_handler", snapshot["scope"])
        self.assertIsNone(snapshot["stages"]["serialization"]["duration_seconds"])

    def test_registry_wrappers_measure_real_discovery_without_unity(self):
        import server_registry
        registry = server_registry.BridgeRegistry(ensure_project_root=lambda value: Path(value), refresh_context_state=lambda root: self.clock.advance(2) or {})
        with mock.patch.object(server_registry, "get_registry", return_value=registry):
            with timing.host_call_timing_scope("registry") as call:
                server_registry.get_project_context("example")
                server_registry.refresh_project_context("example")
                report = call.snapshot("completed")
        self.assertEqual(4, report["stages"]["context_discovery"]["duration_seconds"])
        self.assertEqual(2, report["stages"]["context_discovery"]["invocation_count"])

    def test_cli_real_registry_report_keeps_stdout_json_and_emits_dispatch_receipt(self):
        import server
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["server.py", "registry-context-report"]), mock.patch.object(server, "reconfigure_stdio_utf8"), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            server.main()
        self.assertIsInstance(json.loads(stdout.getvalue()), dict)
        receipts = [json.loads(line) for line in stderr.getvalue().splitlines() if line.startswith('{"schema_version"')]
        self.assertEqual(1, len(receipts))
        self.assertEqual("cli_dispatch", receipts[0]["scope"])
        self.assertEqual("measured", receipts[0]["stages"]["serialization"]["status"])
        self.assertIn("launcher_startup", receipts[0]["excludes"])


if __name__ == "__main__":
    unittest.main()
