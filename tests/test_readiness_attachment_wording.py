import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_editor_host_lifecycle as lifecycle
import server_host_platform
from server_bridge_paths import host_editor_session_state_path
from server_core import write_json
from server_setup_common import UNITY_EDITOR_ATTACHMENT_RESTART_CRITERION


class ReadinessAttachmentWordingTests(unittest.TestCase):
    def _error(self, project_root: Path, process_started_age_seconds: float | None = None) -> lifecycle.ToolInvocationError:
        started = None if process_started_age_seconds is None else time.time() - process_started_age_seconds
        with (
            mock.patch.object(lifecycle, "find_running_unity_editors_for_project", return_value=[{"pid": 222}]),
            mock.patch.object(lifecycle, "pid_is_alive", return_value=False),
            mock.patch.object(
                server_host_platform.HostPlatformAdapter, "process_start_time", return_value=started
            ) as self.process_start_time,
        ):
            return lifecycle._readiness_error_from_log_observation(
                project_root, {}, ("startup_log_compile_markers_observed", "markers")
            )

    def _project(self, *, manifest_age_seconds: float, opened_age_seconds: float | None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        manifest = root / "Packages" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}", encoding="utf-8")
        mtime = time.time() - manifest_age_seconds
        os.utime(manifest, (mtime, mtime))
        if opened_age_seconds is not None:
            session_path = host_editor_session_state_path(root)
            session_path.parent.mkdir(parents=True, exist_ok=True)
            opened = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - opened_age_seconds))
            write_json(session_path, {"editor_pid": 222, "opened_at_utc": opened})
        return root

    def test_editor_opened_before_the_install_names_refresh_and_the_restart_criterion(self) -> None:
        exc = self._error(self._project(manifest_age_seconds=60, opened_age_seconds=600))

        self.assertEqual("editor_not_ready_bridge_not_attached", exc.code)
        self.assertTrue(exc.details["attachment_pending_predates_install"])
        self.assertEqual("host_session_opened_before_manifest_change", exc.details["attachment_pending_basis"])
        self.assertIn("Assets > Refresh", exc.message)
        self.assertIn("once import has settled", exc.message)
        self.assertNotIn("do not restart", exc.message)
        self.assertEqual("poll_bridge_bootstrap_attached_then_retry", exc.details["recommended_next_action"])

    def test_editor_opened_after_the_install_only_polls_first(self) -> None:
        exc = self._error(self._project(manifest_age_seconds=600, opened_age_seconds=60))

        self.assertFalse(exc.details["attachment_pending_predates_install"])
        self.assertEqual("host_session_opened_after_manifest_change", exc.details["attachment_pending_basis"])
        self.assertNotIn("Assets > Refresh", exc.message)
        self.assertIn("Poll bridge readiness first", exc.message)

    def test_unknown_editor_start_is_not_claimed_to_predate_the_install(self) -> None:
        exc = self._error(self._project(manifest_age_seconds=60, opened_age_seconds=None))

        self.assertFalse(exc.details["attachment_pending_predates_install"])
        self.assertEqual("editor_start_time_unknown", exc.details["attachment_pending_basis"])

    def test_host_session_start_wins_and_the_process_is_not_probed(self) -> None:
        self._error(self._project(manifest_age_seconds=60, opened_age_seconds=600), process_started_age_seconds=5)
        self.process_start_time.assert_not_called()

    def test_external_editor_started_before_the_install_uses_the_process_start_time(self) -> None:
        exc = self._error(
            self._project(manifest_age_seconds=60, opened_age_seconds=None), process_started_age_seconds=600
        )

        self.process_start_time.assert_called_once_with(222)
        self.assertTrue(exc.details["attachment_pending_predates_install"])
        self.assertEqual("process_start_time", exc.details["attachment_pending_basis"])
        self.assertRegex(exc.details["editor_process_started_at_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIn("Assets > Refresh", exc.message)

    def test_external_editor_started_after_the_install_only_polls_first(self) -> None:
        exc = self._error(
            self._project(manifest_age_seconds=600, opened_age_seconds=None), process_started_age_seconds=60
        )

        self.assertFalse(exc.details["attachment_pending_predates_install"])
        self.assertEqual("process_start_time", exc.details["attachment_pending_basis"])
        self.assertNotIn("Assets > Refresh", exc.message)

    def test_readiness_and_setup_share_one_restart_criterion(self) -> None:
        exc = self._error(self._project(manifest_age_seconds=60, opened_age_seconds=None))

        self.assertEqual(UNITY_EDITOR_ATTACHMENT_RESTART_CRITERION, exc.details["restart_criterion"])


def _completed(stdout: str, returncode: int = 0) -> mock.Mock:
    return mock.Mock(stdout=stdout, stderr="", returncode=returncode)


class ProcessStartTimeReaderTests(unittest.TestCase):
    def _adapter(self) -> server_host_platform.HostPlatformAdapter:
        return server_host_platform.HostPlatformAdapter(platform_kind="test")

    def test_posix_branch_parses_ps_lstart_in_the_c_locale(self) -> None:
        with (
            mock.patch.object(server_host_platform.os, "name", "posix"),
            mock.patch.object(server_host_platform, "is_wsl", return_value=False),
            mock.patch.object(
                server_host_platform.subprocess, "run", return_value=_completed("Fri Nov 20 08:12:33 2026\n")
            ) as run,
        ):
            started = self._adapter().process_start_time(4242)

        self.assertEqual(time.mktime(time.strptime("2026-11-20 08:12:33", "%Y-%m-%d %H:%M:%S")), started)
        command = run.call_args.args[0]
        self.assertEqual(["ps", "-o", "lstart=", "-p", "4242"], command)
        self.assertEqual("C", run.call_args.kwargs["env"]["LC_ALL"])
        self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_windows_and_wsl_branches_parse_the_powershell_round_trip_time(self) -> None:
        for os_name, wsl in (("nt", False), ("posix", True)):
            with self.subTest(os_name=os_name, wsl=wsl):
                with (
                    mock.patch.object(server_host_platform.os, "name", os_name),
                    mock.patch.object(server_host_platform, "is_wsl", return_value=wsl),
                    mock.patch.object(server_host_platform.shutil, "which", return_value="powershell"),
                    mock.patch.object(
                        server_host_platform.subprocess,
                        "run",
                        return_value=_completed("2026-11-20T08:12:33.5000000Z\r\n"),
                    ) as run,
                ):
                    started = self._adapter().process_start_time(4242)

                self.assertEqual(1795162353.5, started)
                script = run.call_args.args[0][-1]
                self.assertIn("Get-Process -Id 4242", script)
                self.assertIn("StartTime", script)
                self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_every_failure_reads_as_unknown(self) -> None:
        import subprocess

        adapter = self._adapter()
        self.assertIsNone(adapter.process_start_time(0))
        self.assertIsNone(adapter.process_start_time("x"))
        for os_name in ("posix", "nt"):
            for failure in (
                {"side_effect": subprocess.TimeoutExpired("ps", 1)},
                {"side_effect": OSError("missing")},
                {"return_value": _completed("", returncode=1)},
                {"return_value": _completed("not a date")},
            ):
                with self.subTest(os_name=os_name, failure=sorted(failure)):
                    with (
                        mock.patch.object(server_host_platform.os, "name", os_name),
                        mock.patch.object(server_host_platform, "is_wsl", return_value=False),
                        mock.patch.object(server_host_platform.shutil, "which", return_value="powershell"),
                        mock.patch.object(server_host_platform.subprocess, "run", **failure),
                    ):
                        self.assertIsNone(adapter.process_start_time(4242))
        with (
            mock.patch.object(server_host_platform.os, "name", "nt"),
            mock.patch.object(server_host_platform.shutil, "which", return_value=None),
        ):
            self.assertIsNone(adapter.process_start_time(4242))


if __name__ == "__main__":
    unittest.main()
