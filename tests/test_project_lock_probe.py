"""Project-lock ownership contract on hosts without lsof.

lsof is POSIX-only, so before the Windows share-mode probe the lock inspection
always reported zero owners on Windows: a genuinely held Temp/UnityLockfile
looked stale, clear_stale_project_lock deleted it, and the
project_already_open_without_bridge guard was unreachable. The contract now:

- a denied read-write open marks the lock as held even without pid attribution;
- held-without-attribution refuses deletion (fail-safe), so the lifecycle
  reports the lock instead of silently clearing a live editor's lock;
- attribution falls back to the live project-editor listing when denied;
- a free (stale) lock is still cleared.

The share-mode denial itself is also exercised natively on Windows with a real
exclusively-opened file.
"""

import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_editor_host


def make_locked_project(root: Path) -> Path:
    (root / "Temp").mkdir(parents=True, exist_ok=True)
    (root / "Temp" / "UnityLockfile").write_bytes(b"")
    return root


class ProjectLockInspectionContractTest(unittest.TestCase):
    def test_share_mode_denied_attributes_owners_to_live_project_editors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_locked_project(Path(tmp_dir) / "MyProject")

            with (
                mock.patch.object(server_editor_host, "try_list_path_owner_pids", return_value=[]),
                mock.patch.object(server_editor_host, "windows_lock_open_denied", return_value=True),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids", return_value=[4242]
                ),
                mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            ):
                lock_state = server_editor_host.inspect_project_lock(project_root)

            self.assertTrue(lock_state["present"])
            self.assertTrue(lock_state["lock_open_denied"])
            self.assertEqual([4242], lock_state["owner_pids"])
            self.assertEqual([4242], lock_state["live_owner_pids"])
            self.assertEqual(
                "windows_share_mode_editor_attribution", lock_state["owner_pid_source"]
            )

    def test_share_mode_denied_without_attribution_refuses_lock_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_locked_project(Path(tmp_dir) / "MyProject")
            lock_path = project_root / "Temp" / "UnityLockfile"

            with (
                mock.patch.object(server_editor_host, "try_list_path_owner_pids", return_value=[]),
                mock.patch.object(server_editor_host, "windows_lock_open_denied", return_value=True),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids", return_value=[]
                ),
            ):
                cleared = server_editor_host.clear_stale_project_lock(project_root)

            self.assertFalse(cleared["removed"], "a held lock must never be deleted")
            self.assertTrue(cleared["present"])
            self.assertTrue(
                lock_path.is_file(),
                "share-mode-held lock must survive even with zero attributable pids",
            )

    def test_free_lock_is_still_cleared_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_locked_project(Path(tmp_dir) / "MyProject")
            lock_path = project_root / "Temp" / "UnityLockfile"

            with (
                mock.patch.object(server_editor_host, "try_list_path_owner_pids", return_value=[]),
                mock.patch.object(
                    server_editor_host, "windows_lock_open_denied", return_value=False
                ),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids", return_value=[]
                ),
            ):
                cleared = server_editor_host.clear_stale_project_lock(project_root)

            self.assertTrue(cleared["removed"])
            self.assertFalse(lock_path.is_file())

    def test_lsof_attribution_still_wins_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_locked_project(Path(tmp_dir) / "MyProject")

            with (
                mock.patch.object(
                    server_editor_host, "try_list_path_owner_pids", return_value=[777]
                ),
                mock.patch.object(
                    server_editor_host, "list_live_project_editor_pids"
                ) as editor_listing_mock,
                mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            ):
                lock_state = server_editor_host.inspect_project_lock(project_root)

            editor_listing_mock.assert_not_called()
            self.assertEqual([777], lock_state["owner_pids"])
            self.assertEqual("lsof", lock_state["owner_pid_source"])

    @unittest.skipUnless(os.name != "nt", "POSIX applicability contract")
    def test_probe_is_not_applicable_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "UnityLockfile"
            path.write_bytes(b"")
            self.assertIsNone(server_editor_host.windows_lock_open_denied(path))


@unittest.skipUnless(os.name == "nt", "native Windows share-mode behavior")
class WindowsShareModeProbeNativeTest(unittest.TestCase):
    GENERIC_READ_WRITE = 0xC0000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def hold_exclusive(self, path: Path):
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            str(path), self.GENERIC_READ_WRITE, 0, None, self.OPEN_EXISTING, 0, None
        )
        self.assertNotEqual(self.INVALID_HANDLE_VALUE, handle, "fixture open failed")
        return handle

    def test_exclusively_held_file_reports_denied_then_free_after_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "UnityLockfile"
            path.write_bytes(b"")

            handle = self.hold_exclusive(path)
            try:
                self.assertTrue(server_editor_host.windows_lock_open_denied(path))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

            self.assertFalse(server_editor_host.windows_lock_open_denied(path))

    def test_missing_file_is_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "UnityLockfile"
            self.assertIsNone(server_editor_host.windows_lock_open_denied(path))


if __name__ == "__main__":
    unittest.main()
