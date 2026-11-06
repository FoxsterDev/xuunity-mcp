import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_device_android as android
import server_device_metrics as metrics
import server_device_tools as tools
from server_core import ToolInvocationError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "device"
PACKAGE = "com.example.game"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def latency_output(presents_ns: list[int], refresh_ns: int = 16666666) -> str:
    rows = [str(refresh_ns)]
    rows.extend(f"{value - 2_000_000}\t{value}\t{value - 4_000_000}" for value in presents_ns)
    rows.append("0\t0\t0")
    rows.append(f"{android.INT64_MAX}\t{android.INT64_MAX}\t{android.INT64_MAX}")
    return "\n".join(rows)


class LayerSelectionTests(unittest.TestCase):
    def test_each_android_generation_picks_the_app_surface_not_its_background(self) -> None:
        expected = {
            "sf_list_android10.txt": ("SurfaceView - com.example.game/com.unity3d.player.UnityPlayerActivity#0", "surfaceview"),
            "sf_list_android12.txt": ("SurfaceView[com.example.game/com.unity3d.player.UnityPlayerActivity]#0", "surfaceview"),
            "sf_list_android12_lowend_device.txt": (
                "SurfaceView[com.example.game/com.unity3d.player.UnityPlayerActivity](BLAST)#0",
                "surfaceview_blast",
            ),
            "sf_list_android14.txt": (
                "SurfaceView[com.example.game/com.unity3d.player.UnityPlayerActivity](BLAST)#411",
                "surfaceview_blast",
            ),
        }
        for name, (layer, basis) in expected.items():
            with self.subTest(name=name):
                self.assertEqual((layer, basis), metrics.select_app_layer(fixture(name), PACKAGE))

    def test_a_package_prefix_of_another_app_and_input_sinks_never_match(self) -> None:
        listing = "\n".join(
            [
                "d289ca3 ActivityRecordInputSink com.example.gamedev/com.unity3d.player.UnityPlayerActivity#0",
                "SurfaceView[com.example.gamedev/com.unity3d.player.UnityPlayerActivity](BLAST)#88",
                "ActivityRecordInputSink com.example.game/com.unity3d.player.UnityPlayerActivity#3",
            ]
        )
        self.assertEqual(("", "no_layer_for_package"), metrics.select_app_layer(listing, PACKAGE))
        listing += "\nSurfaceView[com.example.game/com.unity3d.player.UnityPlayerActivity](BLAST)#91"
        self.assertEqual(
            ("SurfaceView[com.example.game/com.unity3d.player.UnityPlayerActivity](BLAST)#91", "surfaceview_blast"),
            metrics.select_app_layer(listing, PACKAGE),
        )

    def test_an_unknown_package_yields_no_layer(self) -> None:
        self.assertEqual(("", "no_layer_for_package"), metrics.select_app_layer(fixture("sf_list_android14.txt"), "com.other"))


class FramePacingTests(unittest.TestCase):
    def test_latency_parsing_skips_pending_and_sentinel_rows(self) -> None:
        refresh, presents = metrics.parse_latency(latency_output([1_000_000_000, 1_016_666_666]))
        self.assertEqual(16666666, refresh)
        self.assertEqual([1_000_000_000, 1_016_666_666], presents)

    def test_overlapping_samples_dedupe_and_the_freeze_is_measured(self) -> None:
        frame = 16_666_666
        first = [1_000_000_000 + index * frame for index in range(60)]
        freeze_end = first[-1] + 595_000_000
        second = first[-20:] + [freeze_end + index * frame for index in range(40)]
        accumulator = metrics.PresentAccumulator()
        accumulator.add_sample(metrics.parse_latency(latency_output(first))[1])
        accumulator.add_sample(metrics.parse_latency(latency_output(second))[1])

        stats = metrics.frame_gap_stats(accumulator.sorted_presents(), sample_gaps=accumulator.sample_gaps)

        self.assertEqual(100, stats["frames"])
        self.assertEqual(595.0, stats["gap_max_ms"])
        self.assertEqual(1, stats["gaps_over_ms"]["500"])
        self.assertEqual(1, stats["gaps_over_ms"]["250"])
        self.assertEqual(0, stats["gaps_over_ms"]["33"] - 1)
        self.assertEqual([], accumulator.sample_gaps)

    def test_a_non_overlapping_full_buffer_is_a_sampling_hole_not_a_freeze(self) -> None:
        frame = 16_666_666
        first = [1_000_000_000 + index * frame for index in range(128)]
        second = [first[-1] + 3_000_000_000 + index * frame for index in range(128)]
        accumulator = metrics.PresentAccumulator()
        accumulator.add_sample(first)
        accumulator.add_sample(second)

        stats = metrics.frame_gap_stats(accumulator.sorted_presents(), sample_gaps=accumulator.sample_gaps)

        self.assertEqual(1, len(accumulator.sample_gaps))
        self.assertEqual(1, stats["gaps_excluded_for_sample_holes"])
        self.assertLess(stats["gap_max_ms"], 20)

    def test_a_real_low_end_device_capture_reproduces_the_measured_splash_freeze(self) -> None:
        capture = json.loads(fixture("lowend_android12_coldstart_presents.json"))
        accumulator = metrics.PresentAccumulator()
        for sample in capture["samples"]:
            accumulator.add_sample(sample)

        stats = metrics.frame_gap_stats(
            accumulator.sorted_presents(),
            window_start_s=capture["launch_monotonic_s"],
            window_end_s=capture["marker_monotonic_s"],
            sample_gaps=accumulator.sample_gaps,
        )

        self.assertEqual([], accumulator.sample_gaps)
        self.assertEqual(capture["expected_frames_until_marker"], stats["frames"])
        self.assertEqual(capture["expected_longest_gap_before_marker_ms"], stats["gap_max_ms"])
        self.assertLess(len(accumulator.presents), sum(len(sample) for sample in capture["samples"]))

    def test_the_window_limits_gaps_to_launch_until_marker(self) -> None:
        presents = [int(seconds * 1e9) for seconds in (1519.0, 1520.2, 1520.3, 1521.3, 1530.2, 1531.5)]
        stats = metrics.frame_gap_stats(presents, window_start_s=1520.104, window_end_s=1530.311)
        self.assertEqual(4, stats["frames"])
        self.assertAlmostEqual(8900.0, stats["gap_max_ms"], places=0)


class LogcatTimingTests(unittest.TestCase):
    def test_ready_time_runs_from_activity_start_to_the_marker_on_the_monotonic_clock(self) -> None:
        lines = fixture("logcat_monotonic.txt").splitlines()
        start, _ = android.find_activity_start(lines, PACKAGE)
        marker, line = android.find_logcat_marker(lines, r"Unity\s*:\s*APP_READY$", after=start)
        self.assertEqual(1520.104, start)
        self.assertEqual(1530.311, marker)
        self.assertTrue(line.endswith("APP_READY"))
        fully_drawn, _ = android.find_logcat_marker(lines, r"Fully drawn " + PACKAGE)
        self.assertEqual(1531.0, fully_drawn)

    def test_am_start_wait_times_are_parsed(self) -> None:
        output = "Status: ok\nLaunchState: COLD\nActivity: x\nTotalTime: 912\nWaitTime: 915\nComplete\n"
        self.assertEqual({"TotalTime": 912, "WaitTime": 915}, android.parse_am_start_times(output))


class QuotingTests(unittest.TestCase):
    def test_unity_args_reach_the_device_shell_as_one_extra(self) -> None:
        command = android.build_launch_shell_command(
            PACKAGE,
            "com.unity3d.player.UnityPlayerActivity",
            ["-profiler-enable", "-profiler-log-file", "/sdcard/Download/cap.raw"],
        )
        self.assertEqual(
            "am start -W -n com.example.game/com.unity3d.player.UnityPlayerActivity -e unity "
            "'-profiler-enable -profiler-log-file /sdcard/Download/cap.raw'",
            command,
        )
        self.assertEqual(
            ["am", "start", "-W", "-n", "com.example.game/com.unity3d.player.UnityPlayerActivity", "-e", "unity",
             "-profiler-enable -profiler-log-file /sdcard/Download/cap.raw"],
            shlex.split(command),
        )

    def test_quotes_inside_args_survive_the_device_shell(self) -> None:
        command = android.build_launch_shell_command(PACKAGE, ".Main", ["-label", "it's a test"])
        self.assertEqual("-label it's a test", shlex.split(command)[-1])
        self.assertIn("com.example.game/.Main", command)

    def test_the_windows_host_command_line_keeps_the_device_command_intact(self) -> None:
        device_command = android.build_launch_shell_command(PACKAGE, ".Main", ["-a", "b c"])
        host_line = subprocess.list2cmdline(["adb.exe", "-s", "X", "shell", device_command])
        self.assertIn('"am start -W -n com.example.game/.Main -e unity \'-a b c\'"', host_line)

    def test_unity_args_without_an_activity_are_refused(self) -> None:
        with self.assertRaises(ToolInvocationError) as raised:
            android.build_launch_shell_command(PACKAGE, "", ["-x"])
        self.assertEqual("device_launch_activity_required", raised.exception.code)
        self.assertTrue(android.build_launch_shell_command(PACKAGE, "", []).startswith("monkey -p com.example.game"))


class DeviceParsingTests(unittest.TestCase):
    def test_devices_are_parsed_with_states_and_remediation(self) -> None:
        devices = android.parse_devices(
            "List of devices attached\n"
            "ZT322H9WK6             device usb:1-1 product:p model:moto_g22 device:d transport_id:1\n"
            "emulator-5554          unauthorized transport_id:2\n"
            "R58M                   no permissions (user in plugdev group); see [http://x]\n"
        )
        self.assertEqual(["ZT322H9WK6", "emulator-5554", "R58M"], [device["serial"] for device in devices])
        self.assertTrue(devices[0]["ready"])
        self.assertEqual("moto_g22", devices[0]["model"])
        self.assertIn("Allow USB debugging", devices[1]["remediation"])
        self.assertEqual("no permissions", devices[2]["state"])

    def test_serial_is_required_with_two_devices_and_never_guessed(self) -> None:
        devices = android.parse_devices("A device\nB device\n")
        with self.assertRaises(ToolInvocationError) as raised:
            android.resolve_serial(devices, "")
        self.assertEqual("device_serial_required", raised.exception.code)
        self.assertEqual("B", android.resolve_serial(devices, "B"))

    def test_unready_or_missing_devices_are_refused_with_their_state(self) -> None:
        with self.assertRaises(ToolInvocationError) as unauthorized:
            android.resolve_serial(android.parse_devices("X unauthorized\n"), "")
        self.assertEqual("device_unauthorized", unauthorized.exception.code)
        with self.assertRaises(ToolInvocationError) as missing:
            android.resolve_serial([], "")
        self.assertEqual("device_not_attached", missing.exception.code)

    def test_install_refusals_are_classified(self) -> None:
        self.assertEqual(
            ("install_refused_signature_conflict", "INSTALL_FAILED_UPDATE_INCOMPATIBLE"),
            android.classify_install_output("Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package signatures do not match]"),
        )
        self.assertEqual("install_refused_downgrade", android.classify_install_output("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")[0])
        self.assertEqual("install_refused_conflicting_provider", android.classify_install_output("INSTALL_FAILED_CONFLICTING_PROVIDER")[0])
        self.assertEqual(("", ""), android.classify_install_output("Performing Streamed Install\nSuccess"))

    def test_dexopt_status_is_read_for_the_package(self) -> None:
        self.assertEqual("verify", android.parse_dexopt_status(fixture("dexopt.txt"), PACKAGE))
        self.assertEqual("speed-profile", android.parse_dexopt_status(fixture("dexopt.txt"), "com.other.app"))
        self.assertEqual("", android.parse_dexopt_status(fixture("dexopt.txt"), "com.missing"))

    def test_package_versions_are_read(self) -> None:
        self.assertEqual(
            {"version_name": "1.64.4", "version_code": "1640401"},
            android.parse_package_versions("    versionCode=1640401 minSdk=24 targetSdk=35\n    versionName=1.64.4\n"),
        )

    def test_adb_lookup_prefers_the_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "adb"
            fake.write_text("", encoding="utf-8")
            self.assertEqual((str(fake), "env_override"), android.locate_adb({android.ADB_ENV_OVERRIDE: str(fake)}))


class SafetyRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "Game"
        (self.project / "Library" / "XUUnityLightMcp" / "config").mkdir(parents=True)
        (self.project / "Library" / "XUUnityLightMcp" / "config" / "runtime_config.json").write_text(
            json.dumps({"device": {"packages": {PACKAGE: {"activity": ".Main", "readyMarker": "APP_READY"}}}}),
            encoding="utf-8",
        )
        self.devices = mock.patch.object(tools, "list_devices", return_value=android.parse_devices("A device\n"))
        self.devices.start()

    def tearDown(self) -> None:
        self.devices.stop()
        self.temp.cleanup()

    def test_mutating_operations_need_allow_mutating(self) -> None:
        for handler, arguments in (
            (tools.tool_device_app, {"operation": "launch", "package": PACKAGE}),
            (tools.tool_device_app, {"operation": "stop", "package": PACKAGE}),
            (tools.tool_device_install, {"apkPath": "x.apk", "package": PACKAGE}),
            (tools.tool_device_coldstart_ab, {"package": PACKAGE, "builds": [{"label": "A"}]}),
        ):
            with self.subTest(handler=handler.__name__, operation=arguments.get("operation")):
                with self.assertRaises(ToolInvocationError) as raised:
                    handler(self.project, arguments)
                self.assertEqual("device_mutation_approval_required", raised.exception.code)

    def test_destructive_operations_need_approve_and_an_allowlisted_package(self) -> None:
        with self.assertRaises(ToolInvocationError) as no_approve:
            tools.tool_device_app(self.project, {"operation": "clear_data", "package": PACKAGE, "allowMutating": True})
        self.assertEqual("device_destructive_approval_required", no_approve.exception.code)
        with self.assertRaises(ToolInvocationError) as not_listed:
            tools.tool_device_app(
                self.project,
                {"operation": "uninstall", "package": "com.store.app", "allowMutating": True, "approve": True},
            )
        self.assertEqual("device_package_not_allowlisted", not_listed.exception.code)

    def test_package_profile_supplies_activity_and_marker(self) -> None:
        self.assertEqual((PACKAGE, ".Main", "APP_READY"), tools._package_and_activity(self.project, {"package": PACKAGE}))

    def test_pull_paths_are_limited(self) -> None:
        with self.assertRaises(ToolInvocationError) as raised:
            tools.tool_device_files(self.project, {"operation": "pull", "remotePath": "/data/data/com.example.game/shared_prefs"})
        self.assertEqual("device_path_not_allowed", raised.exception.code)

    def test_a_signature_conflict_names_the_data_loss(self) -> None:
        apk = self.project / "a.apk"
        apk.write_bytes(b"PK")
        refused = android.AdbResult(1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]", "")
        with mock.patch.object(tools, "run_adb", return_value=refused):
            with self.assertRaises(ToolInvocationError) as raised:
                tools.install_apk(self.project, "A", {"allowMutating": True}, apk, PACKAGE)
        details = raised.exception.details
        self.assertEqual("install_refused_signature_conflict", details["result_trust_class"])
        self.assertIn("deletes its local data", details["data_loss_warning"])

    def test_an_install_cut_off_without_an_install_code_is_a_transport_failure(self) -> None:
        apk = self.project / "a.apk"
        apk.write_bytes(b"PK")
        cut = android.AdbResult(1, "Performing Streamed Install\n\nadb: failed to install a.apk:", "")
        with mock.patch.object(tools, "run_adb", return_value=cut) as run, mock.patch.object(tools.time, "sleep"):
            with self.assertRaises(ToolInvocationError) as raised:
                tools.install_apk(self.project, "A", {"allowMutating": True}, apk, PACKAGE)
        self.assertEqual(2, run.call_count)
        self.assertEqual(2, raised.exception.details["install_attempts"])
        self.assertEqual("install_transport_failed", raised.exception.details["result_trust_class"])
        self.assertEqual("check_adb_devices_then_retry_install", raised.exception.details["recommended_next_action"])

    def test_a_downgrade_is_refused_until_allowed(self) -> None:
        apk = self.project / "a.apk"
        apk.write_bytes(b"PK")
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if "-d" in args:
                return android.AdbResult(0, "Success", "")
            return android.AdbResult(1, "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]", "")

        with mock.patch.object(tools, "run_adb", side_effect=fake_run), mock.patch.object(
            tools, "installed_versions", return_value={"version_name": "1", "version_code": "1"}
        ):
            with self.assertRaises(ToolInvocationError) as raised:
                tools.install_apk(self.project, "A", {"allowMutating": True}, apk, PACKAGE)
            self.assertEqual("retry_with_allowDowngrade", raised.exception.details["recommended_next_action"])
            accepted = tools.install_apk(self.project, "A", {"allowMutating": True, "allowDowngrade": True}, apk, PACKAGE)
        self.assertEqual("device_truth_confirmed", accepted["result_trust_class"])
        self.assertIn("-d", calls[-1])


class ColdStartSummaryTests(unittest.TestCase):
    def test_medians_ignore_runs_without_a_marker(self) -> None:
        summary = metrics.summarize_build_runs(
            [
                {"marker_found": True, "ready_seconds": 10.44, "longest_gap_before_marker_ms": 1179},
                {"marker_found": True, "ready_seconds": 10.48, "longest_gap_before_marker_ms": 1134},
                {"marker_found": True, "ready_seconds": 10.44, "longest_gap_before_marker_ms": 1134},
                {"marker_found": False, "ready_seconds": None, "longest_gap_before_marker_ms": None},
                {"marker_found": True, "ready_seconds": 12.0, "longest_gap_before_marker_ms": None},
            ]
        )
        self.assertEqual(4, summary["runs_with_marker"])
        self.assertEqual(10.46, summary["ready_seconds_median"])
        self.assertEqual(1134, summary["longest_gap_before_marker_ms_median"])


if __name__ == "__main__":
    unittest.main()
