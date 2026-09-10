import contextlib
import datetime
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_bridge_final_status
import server_cli_commands
import server_core
import server_editor_host
import server_host_platform
import server_hub_licensing
import server_launcher
import server_licensing_state
import server_cli_parser


def process_report(platform_kind: str, processes: list[dict]) -> dict:
    return {
        "available": True,
        "commands": [(entry["pid"], entry["command"]) for entry in processes],
        "processes": processes,
        "error_code": "",
        "stderr": "",
        "platform_kind": platform_kind,
    }


class HubLicensingResolutionTests(unittest.TestCase):
    def test_explicit_channel_forms_normalize_once_and_preserve_source(self):
        for channel in ("Unity-LicenseClient-abc", "LicenseClient-abc"):
            args, resolution = server_hub_licensing.prepare_hub_licensing_unity_args(["-licensingIpc", channel])
            self.assertEqual(["-licensingIpc", "LicenseClient-abc"], args)
            self.assertEqual("explicit_unity_argument", resolution["source"])
            self.assertNotIn(channel, json.dumps(resolution))
            self.assertEqual(args, server_hub_licensing.prepare_hub_licensing_unity_args(args)[0])

    def test_connection_mechanism_requires_exact_forwarded_channel_and_no_missing_line(self):
        fingerprint = server_hub_licensing._fingerprint("LicenseClient-abc")
        wrong = 'Successfully connected to: "LicenseClient-fallback"'
        exact = 'Successfully connected to: "LicenseClient-abc"'
        missing = "Channel LicenseClient-abc doesn't exist"
        for log, expected in [(wrong, False), (exact, True), (missing + "\n" + exact, False), (missing + "\n" + wrong, False)]:
            result = server_licensing_state.licensing_connection_evidence(log, fingerprint)
            self.assertEqual(expected, result["licensing_forwarded_channel_connected"])
            self.assertNotIn("LicenseClient-abc", json.dumps(result))

    def test_live_hub_process_requires_matching_editor_entitlement_before_probe_skip(self):
        import server_host_platform
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "Editor.log"
            report = process_report("linux", [
                {"pid": 10, "ppid": 1, "command": "/opt/unityhub/unityhub"},
                {"pid": 11, "ppid": 10, "command": "/opt/unityhub/Unity.Licensing.Client --namedPipe Unity-LicenseClient-abc"},
                {"pid": 20, "ppid": 1, "command": f'/opt/Unity -projectPath "{tmp}" -logFile "{log}"'},
            ])
            adapter = mock.Mock(platform_kind="linux")
            adapter.list_process_commands_report.return_value = report
            adapter.pid_is_alive.return_value = True
            with (mock.patch.object(server_host_platform, "current_host_platform_adapter", return_value=adapter),
                  mock.patch.object(server_hub_licensing, "current_host_platform_adapter", return_value=adapter)):
                for text, licensed in [
                    ("", False),
                    ('Successfully connected to: "LicenseClient-abc"', False),
                    ('Successfully connected to: "LicenseClient-fallback"\nSuccessfully resolved entitlement details', False),
                    ('Successfully connected to: "LicenseClient-abc"\nSuccessfully resolved entitlement details', True),
                    ("packages were not registered because your license doesn't allow it", False),
                ]:
                    log.write_text(text, encoding="utf-8")
                    evidence = server_licensing_state.live_editor_licensing_evidence()
                    self.assertTrue(evidence["editor_live"])
                    self.assertEqual(licensed, evidence["licensed_editor_live"])

    def test_shared_bridge_recovery_uses_only_accepted_helper_verbs(self):
        import argparse
        parser = server_cli_parser.build_parser()
        choices = next(action.choices for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        recipe = server_core.BRIDGE_ENABLE_RECOVERY_COMMAND.format(project_root="<path>")
        for command in recipe.split("; then "):
            self.assertIn(command.split()[0], choices)
        self.assertIn("--plan-file <plan>", recipe)
        for path in TEMPLATES_DIR.glob("server*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("--enable-project", source, path.name)
            self.assertNotRegex(source, r"(?:server\.py|run\.sh|xuunity-mcp) init ", path.name)


    def test_single_live_hub_candidate_resolves_on_each_platform_without_public_channel(self) -> None:
        shapes = {
            "macos": (
                "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub",
                "/Applications/Unity Hub.app/Contents/Frameworks/UnityLicensingClient_V1.app/Contents/MacOS/Unity.Licensing.Client",
            ),
            "windows": (r"C:\Program Files\Unity Hub\Unity Hub.exe", r"C:\Program Files\Unity Hub\Unity.Licensing.Client.exe"),
            "linux": ("/opt/unityhub/unityhub", "/opt/unityhub/Unity.Licensing.Client"),
        }
        for platform_kind, (hub_command, client_command) in shapes.items():
            with self.subTest(platform_kind=platform_kind):
                report = process_report(
                    platform_kind,
                    [
                        {"pid": 10, "ppid": 1, "command": hub_command},
                        {
                            "pid": 11,
                            "ppid": 10,
                            "command": f'{client_command} --namedPipe "Unity-LicenseClient-session-123"',
                        },
                    ],
                )
                public, channel = server_hub_licensing.resolve_hub_licensing_ipc(
                    report,
                    pid_is_alive_fn=lambda pid: pid in {10, 11},
                )

                self.assertEqual("Unity-LicenseClient-session-123", channel)
                self.assertEqual("resolved", public["status"])
                self.assertEqual(1, public["candidate_count"])
                self.assertEqual("machine_recoverable_with_hub_session", public["action_classification"])
                self.assertNotIn(channel, json.dumps(public))

    def test_zero_stale_or_multiple_candidates_fail_closed(self) -> None:
        hub = {"pid": 10, "ppid": 1, "command": "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub"}
        client_a = {
            "pid": 11,
            "ppid": 10,
            "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-a",
        }
        client_b = {
            "pid": 12,
            "ppid": 10,
            "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-b",
        }

        stale, channel = server_hub_licensing.resolve_hub_licensing_ipc(
            process_report("macos", [hub, client_a]),
            pid_is_alive_fn=lambda pid: pid == 10,
        )
        self.assertEqual("no_hub_session", stale["status"])
        self.assertEqual("", channel)

        ambiguous, channel = server_hub_licensing.resolve_hub_licensing_ipc(
            process_report("macos", [hub, client_a, client_b]),
            pid_is_alive_fn=lambda pid: True,
        )
        self.assertEqual("ambiguous", ambiguous["status"])
        self.assertEqual(2, ambiguous["candidate_count"])
        self.assertEqual("", channel)

        spoofed_parent = {
            "pid": 10,
            "ppid": 1,
            "command": "python helper.py --label '/Applications/Unity Hub.app/Contents/MacOS/Unity Hub'",
        }
        spoofed, channel = server_hub_licensing.resolve_hub_licensing_ipc(
            process_report("macos", [spoofed_parent, client_a]),
            pid_is_alive_fn=lambda pid: True,
        )
        self.assertEqual("no_hub_session", spoofed["status"])
        self.assertEqual("", channel)

    def test_prepare_forwards_one_candidate_and_refuses_ambiguity(self) -> None:
        hub = {"pid": 10, "ppid": 1, "command": "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub"}
        client = {
            "pid": 11,
            "ppid": 10,
            "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-one",
        }
        report = process_report("macos", [hub, client])
        with mock.patch.object(server_hub_licensing, "current_host_platform_adapter") as adapter_factory:
            adapter_factory.return_value.pid_is_alive.return_value = True
            adapter_factory.return_value.platform_kind = "macos"
            args, public = server_hub_licensing.prepare_hub_licensing_unity_args([], report)

        self.assertEqual(["-licensingIpc", "LicenseClient-one"], args)
        self.assertTrue(public["unity_argument_forwarded"])
        self.assertNotIn("Unity-LicenseClient-one", json.dumps(public))

        ambiguous_report = process_report(
            "macos",
            [hub, client, {**client, "pid": 12, "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-two"}],
        )
        with mock.patch.object(server_hub_licensing, "current_host_platform_adapter") as adapter_factory:
            adapter_factory.return_value.pid_is_alive.return_value = True
            adapter_factory.return_value.platform_kind = "macos"
            with self.assertRaises(server_core.ToolInvocationError) as raised:
                server_hub_licensing.prepare_hub_licensing_unity_args([], ambiguous_report)
        self.assertEqual("licensing_ipc_ambiguous", raised.exception.code)

    def test_owned_child_discovery_excludes_preexisting_hub_client(self) -> None:
        report = process_report(
            "macos",
            [
                {"pid": 10, "ppid": 1, "command": "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub"},
                {"pid": 11, "ppid": 10, "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-shared"},
                {"pid": 20, "ppid": 1, "command": "/Applications/Unity.app/Contents/MacOS/Unity -projectPath /tmp/P"},
                {"pid": 21, "ppid": 20, "command": "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-owned"},
            ],
        )
        with mock.patch.object(server_hub_licensing, "current_host_platform_adapter") as adapter_factory:
            adapter_factory.return_value.list_process_commands_report.return_value = report
            adapter_factory.return_value.pid_is_alive.return_value = True
            owned = server_hub_licensing.discover_owned_licensing_children(
                baseline_pids=[11],
                editor_pid=20,
                process_report=report,
            )

        self.assertEqual([21], [entry["pid"] for entry in owned])
        self.assertNotIn("Unity-LicenseClient-owned", json.dumps(owned))

    def test_cleanup_refuses_a_current_shared_hub_client(self) -> None:
        hub_command = "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub"
        client_command = "/tmp/Unity.Licensing.Client --namedPipe Unity-LicenseClient-shared"
        report = process_report(
            "macos",
            [
                {"pid": 10, "ppid": 1, "command": hub_command},
                {"pid": 11, "ppid": 10, "command": client_command},
            ],
        )
        session = {
            "owned_licensing_children": [
                {
                    "pid": 11,
                    "spawned_after_launch": True,
                    "command_fingerprint": server_hub_licensing._fingerprint(client_command),
                }
            ]
        }
        with (
            mock.patch.object(server_hub_licensing, "current_host_platform_adapter") as adapter_factory,
            mock.patch.object(server_hub_licensing, "_terminate_verified_pid") as terminate,
        ):
            adapter_factory.return_value.list_process_commands_report.return_value = report
            adapter_factory.return_value.pid_is_alive.return_value = True
            result = server_hub_licensing.cleanup_owned_licensing_children(session, 1000)

        self.assertEqual(1, result["refused_count"])
        terminate.assert_not_called()


class OperatorEnvelopeAndLifecycleTests(unittest.TestCase):
    def test_compact_json_extraction_prefers_outer_terminal_payload_over_nested_object(self) -> None:
        payload = {
            "action": "request-final-status",
            "request_id": "req-outer",
            "operator_verdict": {"status": "confirmed_success", "should_retry": False},
        }
        mixed_output = "progress before terminal payload\n" + json.dumps(payload)

        extracted = server_launcher._extract_last_json_object(mixed_output)

        self.assertEqual("request-final-status", extracted["action"])
        self.assertEqual("req-outer", extracted["request_id"])

    def test_diagnostic_log_excerpts_are_relevant_bounded_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "Private Project"
            project_root.mkdir()
            log_path = project_root / "Editor.log"
            request_id = "12345678-1234-4234-9234-123456789abc"
            log_path.write_text(
                "CopyFiles build/Unity.IL2CPP.CompilerServices.dll\n"
                "[Licensing::Module] Serial number assigned to: \"private-serial\"\n"
                "[Licensing::Module] Successfully updated access token: \"private-token\"\n"
                "Assets/Private/PlayMode/Foo.asmdef will not be compiled because it exists outside Assets\n"
                "Licensing failure while reading /Users/private/SecretProject/Library/license.dat\n"
                f"Licensing failure at {project_root} --namedPipe Unity-LicenseClient-secret request_id={request_id}\n",
                encoding="utf-8",
            )

            excerpts = server_cli_commands._diagnostic_log_excerpts(log_path, project_root)

        encoded = json.dumps(excerpts)
        self.assertEqual(2, len(excerpts))
        self.assertNotIn(str(project_root), encoded)
        self.assertNotIn("Unity-LicenseClient-secret", encoded)
        self.assertNotIn(request_id, encoded)
        self.assertNotIn("private-serial", encoded)
        self.assertNotIn("private-token", encoded)
        self.assertNotIn("Assets/Private", encoded)
        self.assertNotIn("SecretProject", encoded)
        self.assertIn("<project-root>", encoded)
        self.assertLessEqual(len(excerpts[0]), 240)

    def test_diagnostic_bundle_has_a_hard_byte_ceiling(self) -> None:
        payload = {
            "action": "diagnostic_retro_bundle",
            "schema_version": 1,
            "sanitized": True,
            "project_root": "<project-root>",
            "project_unity_version": "2022.3.62f3",
            "licensing_ipc_resolution": {"status": "resolved", "validation_result": "x" * 50000},
            "terminal_request": {"operation": "unity.tests.run_playmode", "detail": "y" * 50000},
            "bounded_log_excerpts": ["z" * 240 for _ in range(12)],
            "bounds": {"max_bundle_bytes": 32768},
        }

        bounded = server_cli_commands._bounded_diagnostic_payload(payload)

        self.assertLessEqual(len((json.dumps(bounded, ensure_ascii=False) + "\n").encode("utf-8")), 32768)
        self.assertTrue(bounded["bundle_truncated"])

    def test_compact_terminal_envelope_is_bounded_and_omits_nested_payload(self) -> None:
        payload = {
            "action": "request_playmode_tests",
            "request_id": "req-1",
            "test_verdict": "passed",
            "total": 20,
            "passed": 20,
            "failed": 0,
            "retryable": False,
            "recommended_next_action": "none",
            "nested": {"raw": "secret-marker-" * 10000},
            "test_result_path": "/tmp/result.json",
        }
        envelope = server_launcher.build_compact_terminal_envelope(payload, 0)
        encoded = server_launcher._bounded_compact_json(envelope)

        self.assertLessEqual(len(encoded.encode("utf-8")), server_launcher.COMPACT_OUTPUT_MAX_BYTES)
        self.assertNotIn("secret-marker", encoded)
        self.assertEqual(20, json.loads(encoded)["passed"])
        self.assertEqual("/tmp/result.json", json.loads(encoded)["artifacts"]["test_result_path"])

    def test_compact_terminal_envelope_keeps_lifecycle_terminalization_and_redacts_channel_errors(self) -> None:
        envelope = server_launcher.build_compact_terminal_envelope(
            {
                "action": "request-final-status",
                "terminal_lifecycle_disposition": "confirmed_success_after_lifecycle_churn",
                "retry_required": False,
                "post_lifecycle_status_confirmation": {"confirmed": True, "playmode_state": "edit"},
                "error": {
                    "code": "launch_failed",
                    "message": "Channel Unity-LicenseClient-private doesn't exist",
                },
            },
            1,
        )

        encoded = json.dumps(envelope)
        self.assertEqual("confirmed_success_after_lifecycle_churn", envelope["terminal_lifecycle_disposition"])
        self.assertFalse(envelope["retry_required"])
        self.assertNotIn("Unity-LicenseClient-private", encoded)

    def test_compact_launcher_suppresses_child_stdout_and_stderr(self) -> None:
        child_payload = {
            "request_id": "req-compact",
            "payload_type": "unity.tests.run_playmode",
            "payload_json": json.dumps(
                {"status": "passed", "total": 20, "passed": 20, "failed": 0, "skipped": 0}
            ),
            "nested": "stdout-secret-" * 10000,
        }
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(child_payload),
            stderr="stderr-secret-" * 10000,
        )
        stdout = io.StringIO()
        with (
            mock.patch.object(server_launcher.subprocess, "run", return_value=completed),
            contextlib.redirect_stdout(stdout),
        ):
            result = server_launcher.run_server_with_optional_compact_summary(
                "/tmp/server.py",
                ["request-playmode-tests"],
                True,
            )

        encoded = stdout.getvalue()
        self.assertEqual(0, result.code)
        self.assertLessEqual(len(encoded.encode("utf-8")), server_launcher.COMPACT_OUTPUT_MAX_BYTES)
        self.assertNotIn("stdout-secret", encoded)
        self.assertNotIn("stderr-secret", encoded)
        self.assertEqual(20, json.loads(encoded)["passed"])

    def test_playmode_pass_is_confirmed_from_fresh_post_reload_bridge_state(self) -> None:
        summary = server_bridge_final_status.build_test_verdict_summary(
            project_root=Path("/tmp/FakeProject"),
            request_id="req-play",
            operation="unity.tests.run_playmode",
            response_payload={
                "completed_at_utc": "2026-08-30T00:00:00Z",
                "run_phase": "completed",
                "status": "passed",
                "total": 20,
                "passed": 20,
                "failed": 0,
                "skipped": 0,
                "playmode_state_after_settle_trust_class": "stale_risk",
            },
            persisted_test_result=None,
            request_submitted=True,
            request_started=True,
            request_completed=True,
            completion_status="ok",
            operation_outcome="completed_ok",
            active_state={
                "health_status": "healthy",
                "heartbeat_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "playmode_state": "edit",
                "is_compiling": False,
                "is_updating": False,
                "compiler_error_count": 0,
                "pending_request_count": 0,
                "bridge_generation": 9,
            },
            bridge_changed_since_submission=True,
        )

        self.assertEqual("confirmed_success_after_lifecycle_churn", summary["terminal_lifecycle_disposition"])
        self.assertFalse(summary["retry_required"])
        self.assertEqual("confirmed_after_lifecycle_churn", summary["playmode_state_after_settle_trust_class"])
        self.assertEqual("edit", summary["playmode_state_after_host_settle"])

    def test_explicit_wrong_unity_version_is_refused_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "Project"
            (project_root / "ProjectSettings").mkdir(parents=True)
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2022.3.62f3\n",
                encoding="utf-8",
            )
            explicit = Path(tmp_dir) / "Unity.app"
            with (
                mock.patch.object(server_editor_host, "detect_unity_app_path", return_value=explicit),
                mock.patch.object(server_editor_host, "resolve_unity_app_version", return_value="6000.0.58f2"),
                self.assertRaises(server_core.ToolInvocationError) as raised,
            ):
                server_editor_host.detect_unity_app_path_for_project(project_root, str(explicit))

        self.assertEqual("unity_version_mismatch", raised.exception.code)
        self.assertTrue(raised.exception.details["explicit_unity_app_refused"])


LINUX_HUB_PARENT_COMMANDS = (
    "/usr/bin/unityhub",
    "/opt/unityhub/unityhub --no-sandbox",
    "/opt/unityhub/unityhub-bin --no-sandbox --disable-gpu-sandbox",
    "/tmp/.mount_UnityHub3l2Kq9/unityhub-bin --type=renderer",
    "/home/dev/Applications/UnityHub-3.13.1.AppImage --no-sandbox",
    "/snap/unityhub/current/opt/unityhub/unityhub-bin",
)

LINUX_HUB_LOOKALIKE_COMMANDS = (
    "/usr/bin/vim /opt/unityhub/unityhub-bin",
    "/usr/bin/tail -f /opt/unityhub/logs/info-log.json",
    "python3 /home/dev/tools/unityhub_watch.py",
    "/home/dev/scripts/unityhub-installer.sh --check",
    "/opt/unityhub-old/unityhub-bin.bak",
    "bash -c /opt/unityhub/unityhub-bin",
)

MAC_AND_WINDOWS_HUB_COMMANDS = (
    "/Applications/Unity Hub.app/Contents/MacOS/Unity Hub",
    '"C:/Program Files/Unity Hub/Unity Hub.exe"',
    "C:\\Program Files\\Unity Hub\\Unity Hub.exe",
)


class HubParentCommandRecognitionTests(unittest.TestCase):
    maxDiff = None

    def parsed_commands(self, ps_stdout: str) -> list[str]:
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")
        completed = mock.Mock(returncode=0, stdout=ps_stdout, stderr="")
        with (
            mock.patch.object(server_host_platform.os, "name", "posix"),
            mock.patch.object(server_host_platform, "is_wsl", return_value=False),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed),
        ):
            report = adapter.list_process_commands_report()
        self.assertTrue(report["available"], report)
        return [str(entry.get("command") or "") for entry in report["processes"]]

    def test_real_ps_output_classifies_every_linux_hub_process_form(self) -> None:
        lines = [
            f"{4000 + index:>6} {1:>6} {command}"
            for index, command in enumerate(LINUX_HUB_PARENT_COMMANDS)
        ]
        commands = self.parsed_commands("\n".join(lines) + "\n")

        self.assertEqual(len(LINUX_HUB_PARENT_COMMANDS), len(commands))
        for command in commands:
            self.assertTrue(
                server_hub_licensing._is_unity_hub_command(command),
                f"a running Unity Hub was not recognized: {command}",
            )

    def test_real_ps_output_refuses_hub_lookalikes(self) -> None:
        lines = [
            f"{5000 + index:>6} {1:>6} {command}"
            for index, command in enumerate(LINUX_HUB_LOOKALIKE_COMMANDS)
        ]
        commands = self.parsed_commands("\n".join(lines) + "\n")

        self.assertEqual(len(LINUX_HUB_LOOKALIKE_COMMANDS), len(commands))
        for command in commands:
            self.assertFalse(
                server_hub_licensing._is_unity_hub_command(command),
                f"a process that only mentions the Hub was classified as the Hub: {command}",
            )

    def test_mac_and_windows_hub_forms_stay_recognized(self) -> None:
        for command in MAC_AND_WINDOWS_HUB_COMMANDS:
            self.assertTrue(
                server_hub_licensing._is_unity_hub_command(command),
                f"a running Unity Hub was not recognized: {command}",
            )


if __name__ == "__main__":
    unittest.main()
