"""PID identity contract for host-side editor termination.

The host editor session file survives crashes and reboots, so the recorded pid
can be reused by an unrelated process. restore_host_opened_editor_state must
force-kill only a pid that is still provably a Unity editor of THIS project
(bridge state pid or -projectPath command-line match); an alive-but-unverified
pid is reported, never killed.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_editor_host
import server_editor_host_lifecycle
import server_editor_host_processes


def make_unity_project(root: Path) -> Path:
    (root / "Assets").mkdir(parents=True, exist_ok=True)
    project_settings = root / "ProjectSettings"
    project_settings.mkdir(parents=True, exist_ok=True)
    (project_settings / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 6000.0.58f2\n", encoding="utf-8"
    )
    return root


VISIBILITY_OK = {
    "process_visibility_available": True,
    "process_visibility_error_code": "",
    "process_visibility_platform_kind": "windows",
}
VISIBILITY_RESTRICTED = {
    "process_visibility_available": False,
    "process_visibility_error_code": "process_listing_failed",
    "process_visibility_platform_kind": "windows",
}


class RestoreHostOpenedEditorKillIdentityTest(unittest.TestCase):
    def write_session(self, project_root: Path, pid: int) -> Path:
        server_editor_host.write_host_editor_session_state(
            project_root,
            {"opened_by_host": True, "editor_pid": pid},
        )
        return server_editor_host.host_editor_session_state_path(project_root)

    def test_alive_pid_not_matching_project_editors_is_never_killed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_unity_project(Path(tmp_dir) / "MyProject")
            session_path = self.write_session(project_root, 4242)

            with (
                mock.patch.object(server_editor_host, "try_read_live_editor_state", return_value=None),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids", return_value=[555]
                ),
                mock.patch.object(
                    server_editor_host, "process_visibility_summary", return_value=dict(VISIBILITY_OK)
                ),
                mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
                mock.patch.object(server_editor_host, "terminate_editor_pid") as terminate_mock,
            ):
                request_quit = mock.Mock()
                result = server_editor_host.restore_host_opened_editor_state(
                    project_root, 30000, request_quit
                )

            terminate_mock.assert_not_called()
            request_quit.assert_not_called()
            self.assertEqual("tracked_pid_not_project_editor", result["closeout_classification"])
            self.assertEqual("tracked_pid_identity_unverified", result["reason"])
            self.assertEqual(4242, result["termination_skipped_pid"])
            self.assertEqual([555], result["live_project_editor_pids"])
            self.assertFalse(result["restored"])
            self.assertFalse(result["same_project_editor_closed"])
            self.assertTrue(
                session_path.is_file(),
                "session must survive so a later verified run can still close out",
            )

    def test_alive_pid_unverifiable_without_process_visibility_is_never_killed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_unity_project(Path(tmp_dir) / "MyProject")
            self.write_session(project_root, 4242)

            with (
                mock.patch.object(server_editor_host, "try_read_live_editor_state", return_value=None),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids", return_value=[]
                ),
                mock.patch.object(
                    server_editor_host,
                    "process_visibility_summary",
                    return_value=dict(VISIBILITY_RESTRICTED),
                ),
                mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
                mock.patch.object(server_editor_host, "terminate_editor_pid") as terminate_mock,
            ):
                result = server_editor_host.restore_host_opened_editor_state(
                    project_root, 30000, mock.Mock()
                )

            terminate_mock.assert_not_called()
            self.assertEqual("tracked_pid_not_project_editor", result["closeout_classification"])
            self.assertEqual("inspect_project_editor_processes", result["recommended_next_action"])

    def test_stale_bridge_foreign_pid_never_passes_restore_identity_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_unity_project(Path(tmp_dir) / "MyProject")
            self.write_session(project_root, 4242)
            stale_bridge_state = {"editor_pid": 4242, "heartbeat_utc": "2000-01-01T00:00:00Z"}

            with (
                mock.patch.object(
                    server_editor_host_lifecycle,
                    "try_read_live_editor_state",
                    return_value=stale_bridge_state,
                ),
                mock.patch.object(
                    server_editor_host_processes,
                    "try_read_live_editor_state",
                    return_value=stale_bridge_state,
                ),
                mock.patch.object(
                    server_editor_host_processes,
                    "find_running_unity_editors_for_project",
                    return_value=[],
                ),
                mock.patch.object(server_editor_host_processes, "pid_is_alive", return_value=True),
                mock.patch.object(
                    server_editor_host_lifecycle,
                    "list_live_project_editor_pids",
                    side_effect=server_editor_host_processes.list_live_project_editor_pids,
                ),
                mock.patch.object(
                    server_editor_host_lifecycle,
                    "process_visibility_summary",
                    return_value=dict(VISIBILITY_OK),
                ),
                mock.patch.object(server_editor_host_lifecycle, "pid_is_alive", return_value=True),
                mock.patch.object(
                    server_editor_host_lifecycle, "terminate_editor_pid"
                ) as terminate_mock,
            ):
                request_quit = mock.Mock()
                result = server_editor_host_lifecycle.restore_host_opened_editor_state(
                    project_root, 30000, request_quit
                )

            terminate_mock.assert_not_called()
            request_quit.assert_not_called()
            self.assertTrue(result["same_project_editor_closed"])
            self.assertEqual("tracked_editor_already_closed", result["closeout_classification"])

    def test_confirmed_project_editor_pid_is_killed_and_closed_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_unity_project(Path(tmp_dir) / "MyProject")
            session_path = self.write_session(project_root, 4242)

            with mock.patch.object(
                server_editor_host, "terminate_editor_pid", return_value=True
            ) as terminate_mock:

                def live_pids(_root):
                    return [] if terminate_mock.called else [4242]

                with (
                    mock.patch.object(
                        server_editor_host, "try_read_live_editor_state", return_value=None
                    ),
                    mock.patch.object(
                        server_editor_host, "list_live_project_editor_pids", side_effect=live_pids
                    ),
                    mock.patch.object(
                        server_editor_host,
                        "process_visibility_summary",
                        return_value=dict(VISIBILITY_OK),
                    ),
                    mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
                ):
                    result = server_editor_host.restore_host_opened_editor_state(
                        project_root, 30000, mock.Mock()
                    )

            terminate_mock.assert_called_once_with(4242, 15000)
            self.assertTrue(result["restored"])
            self.assertEqual("closed_via_host_sigterm", result["closeout_classification"])
            self.assertEqual(4242, result["closed_editor_pid"])
            self.assertFalse(session_path.is_file())


if __name__ == "__main__":
    unittest.main()
