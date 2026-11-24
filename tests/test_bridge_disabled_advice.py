import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_bridge_transport import invoke_bridge_transport
from server_core import ToolInvocationError
from server_editor_host_lifecycle import wait_for_ready


def _write_manifest(project_root: Path, dependencies: dict[str, str]) -> None:
    (project_root / "Packages").mkdir()
    (project_root / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": dependencies}), encoding="utf-8"
    )


class BridgeDisabledAdviceTests(unittest.TestCase):
    def _raise_from_transport(self, project_root: Path) -> ToolInvocationError:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(ToolInvocationError) as ctx:
                invoke_bridge_transport(project_root, "unity.status", {}, 1000)
        return ctx.exception

    def _raise_from_readiness_wait(self, project_root: Path) -> ToolInvocationError:
        with self.assertRaises(ToolInvocationError) as ctx:
            wait_for_ready(
                project_root, 1000, 10, "fail_fast_on_interactive_compile_block", project_root / "editor.log"
            )
        return ctx.exception

    def test_declared_package_points_at_ensure_ready_not_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            _write_manifest(project_root, {"com.xuunity.light-mcp": "https://example.invalid/pkg.git#v1.0.0"})
            for error in (self._raise_from_transport(project_root), self._raise_from_readiness_wait(project_root)):
                self.assertEqual("bridge_disabled", error.code)
                self.assertEqual("open_editor_or_ensure_ready", error.details["recommended_next_action"])
                self.assertIn("ensure-ready", error.message)
                self.assertIn("--open-editor", error.message)
                self.assertNotIn("setup-plan", error.message)

    def test_missing_package_keeps_the_setup_advice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            _write_manifest(project_root, {"com.unity.ugui": "2.0.0"})
            for error in (self._raise_from_transport(project_root), self._raise_from_readiness_wait(project_root)):
                self.assertEqual("bridge_disabled", error.code)
                self.assertEqual("enable_bridge_and_retry", error.details["recommended_next_action"])
                self.assertIn("setup-plan", error.message)


if __name__ == "__main__":
    unittest.main()
