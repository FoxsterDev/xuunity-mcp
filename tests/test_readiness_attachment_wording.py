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
from server_bridge_paths import host_editor_session_state_path
from server_core import write_json
from server_setup_common import UNITY_EDITOR_ATTACHMENT_RESTART_CRITERION


class ReadinessAttachmentWordingTests(unittest.TestCase):
    def _error(self, project_root: Path) -> lifecycle.ToolInvocationError:
        with (
            mock.patch.object(lifecycle, "find_running_unity_editors_for_project", return_value=[{"pid": 222}]),
            mock.patch.object(lifecycle, "pid_is_alive", return_value=False),
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

    def test_readiness_and_setup_share_one_restart_criterion(self) -> None:
        exc = self._error(self._project(manifest_age_seconds=60, opened_age_seconds=None))

        self.assertEqual(UNITY_EDITOR_ATTACHMENT_RESTART_CRITERION, exc.details["restart_criterion"])


if __name__ == "__main__":
    unittest.main()
