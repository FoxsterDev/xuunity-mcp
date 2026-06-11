"""Golden parity between the legacy bash wrapper body and the Python launcher core.

Each scenario runs the same wrapper entrypoint twice — once with
XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER=1 (bash body) and once on the default
path (templates/server_launcher.py) — in isolated sandboxes, then asserts the
stdout/stderr/exit-code contract and filesystem effects are identical.

This is the porting-safety baseline required by
XUUNITY_MCP_THIN_LAUNCHER_PYTHON_CORE_DESIGN_2026-06-11.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "xuunity_light_unity_mcp.sh"
LEGACY_NAME = "xuunity_light_unity_mcp_legacy.sh"
WRAPPER_NAME = "xuunity_light_unity_mcp.sh"


class LauncherParityTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def make_env(self) -> dict:
        env = dict(os.environ)
        env["PYTHON"] = sys.executable
        env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = "/tmp/nonexistent-xuunity-neutral-dir"
        for key in (
            "XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT",
            "XUUNITY_LIGHT_UNITY_MCP_SERVER",
            "XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET",
            "XUUNITY_LIGHT_UNITY_MCP_AIRROOT",
            "XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER",
        ):
            env.pop(key, None)
        return env

    def run_wrapper(self, args: list, env: dict, *, legacy: bool, cwd: str | None = None):
        env = dict(env)
        if legacy:
            env["XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER"] = "1"
        completed = run_with_timeout(
            [resolve_bash_executable(), WRAPPER.as_posix(), *args],
            env=env,
            cwd=cwd,
            timeout_seconds=120,
        )
        stdout = completed.stdout.replace(LEGACY_NAME, WRAPPER_NAME)
        stderr = completed.stderr.replace(LEGACY_NAME, WRAPPER_NAME)
        return completed.returncode, stdout, stderr

    @staticmethod
    def temp_prefix_candidates() -> list:
        candidates = []
        for value in (
            tempfile.gettempdir(),
            os.environ.get("TMP") or "",
            os.environ.get("TEMP") or "",
        ):
            if not value:
                continue
            for variant in (value, os.path.realpath(value)):
                normalized = variant.replace("\\", "/").rstrip("/")
                if normalized and normalized != "/tmp" and normalized not in candidates:
                    candidates.append(normalized)
        return sorted(candidates, key=len, reverse=True)

    def normalize(self, text: str, roots: list) -> str:
        # The legacy bash body emits MSYS paths on Windows while the python
        # core emits native ones; compare path-shape-insensitively by keying
        # on the unique sandbox basename and collapsing separators and the
        # host temp prefix (incl. 8.3 short forms and JSON-escaped text).
        text = text.replace("\r\n", "\n")
        for root in roots:
            name = Path(root).name
            if name:
                text = text.replace(name, "<ROOT>")
        if os.name == "nt":
            text = text.replace("\\\\", "/").replace("\\", "/")
            for prefix in self.temp_prefix_candidates():
                text = text.replace(prefix, "/tmp")
        return re.sub(r"\b[0-9a-f]{40}\b", "<commit>", text)

    def assert_parity(self, legacy_result, python_result, roots: list = ()) -> None:
        legacy_code, legacy_out, legacy_err = legacy_result
        python_code, python_out, python_err = python_result
        roots = list(roots)
        self.assertEqual(legacy_code, python_code, f"exit codes differ\nlegacy stderr:\n{legacy_err}\npython stderr:\n{python_err}")
        self.assertEqual(self.normalize(legacy_out, roots), self.normalize(python_out, roots))
        self.assertEqual(self.normalize(legacy_err, roots), self.normalize(python_err, roots))

    def create_fake_project(self, root: Path, unity_version: str = "2021.3.58f1") -> Path:
        (root / "Assets").mkdir(parents=True)
        (root / "Packages").mkdir(parents=True)
        (root / "ProjectSettings").mkdir(parents=True)
        (root / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": {}}, indent=2) + "\n", encoding="utf-8"
        )
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {unity_version}\n", encoding="utf-8"
        )
        return root

    def test_help_parity(self) -> None:
        env = self.make_env()
        legacy = self.run_wrapper(["--help"], env, legacy=True)
        python = self.run_wrapper(["--help"], env, legacy=False)
        self.assert_parity(legacy, python)
        self.assertIn("Usage:", python[1])

    def test_mode_help_parity(self) -> None:
        env = self.make_env()
        for mode in ("devmode", "prodmode"):
            with self.subTest(mode=mode):
                legacy = self.run_wrapper([mode, "--help"], env, legacy=True)
                python = self.run_wrapper([mode, "--help"], env, legacy=False)
                self.assert_parity(legacy, python)
                self.assertEqual(0, python[0])

    def test_invalid_install_target_parity(self) -> None:
        env = self.make_env()
        env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "bogus"
        legacy = self.run_wrapper(["--help"], env, legacy=True)
        python = self.run_wrapper(["--help"], env, legacy=False)
        self.assert_parity(legacy, python)
        self.assertEqual(1, python[0])
        self.assertIn("invalid XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=bogus", python[2])

    def test_setup_plan_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                project_root = self.create_fake_project(Path(tmp_dir) / "FakeProject")
                env = self.make_env()
                env["CODEX_TOOLS_HOME"] = str(Path(tmp_dir) / "codex-tools")
                env["CLAUDE_TOOLS_HOME"] = str(Path(tmp_dir) / "claude-tools")
                results.append(
                    self.run_wrapper(["setup-plan", "--project-root", str(project_root)], env, legacy=legacy)
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(0, results[1][0])
            plan = json.loads(results[1][1])
            self.assertEqual("setup_plan", plan["action"])

    def test_devmode_parity_with_airroot_layout(self) -> None:
        def build(tmp_dir: str) -> tuple:
            temp_root = Path(tmp_dir)
            airroot = temp_root / "AIRoot"
            operation_root = airroot / "Operations" / "XUUnityLightUnityMcp"
            for root in (airroot, operation_root):
                (root / "templates").mkdir(parents=True, exist_ok=True)
                (root / "templates" / "server.py").write_text("# fake server\n", encoding="utf-8")
            for package in (
                airroot / "packages" / "com.xuunity.light-mcp",
                operation_root / "packages" / "com.xuunity.light-mcp",
            ):
                package.mkdir(parents=True, exist_ok=True)
                (package / "package.json").write_text('{"name":"com.xuunity.light-mcp"}\n', encoding="utf-8")

            project_root = temp_root / "FakeProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir(parents=True)
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {}}, indent=2) + "\n", encoding="utf-8"
            )
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n", encoding="utf-8"
            )
            return airroot, project_root

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            artifacts = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                airroot, project_root = build(tmp_dir)
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_AIRROOT"] = str(airroot)
                results.append(
                    self.run_wrapper(["devmode", "--project-root", str(project_root)], env, legacy=legacy)
                )
                artifacts.append(
                    (
                        (project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"),
                        (project_root / "Packages" / "packages-lock.json").read_text(encoding="utf-8"),
                    )
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(0, results[1][0])
            self.assertEqual(artifacts[0], artifacts[1])
            self.assertIn("xuunity-mcp mode switched: devmode", results[1][1])

    def test_prodmode_parity(self) -> None:
        def run_git(cwd: Path, *args: str) -> None:
            subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

        def build(tmp_dir: str) -> tuple:
            temp_root = Path(tmp_dir)
            source_root = temp_root / "Source"
            package_root = source_root / "packages" / "com.xuunity.light-mcp"
            templates_root = source_root / "templates"
            package_version = "0.3.14"
            release_tag = f"v{package_version}"

            templates_root.mkdir(parents=True)
            package_root.mkdir(parents=True)
            (templates_root / "server.py").write_text("# fake server\n", encoding="utf-8")
            (templates_root / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (templates_root / "xuunity_light_unity_mcp_runtime_defaults.json").write_text("{}\n", encoding="utf-8")
            (package_root / "package.json").write_text(
                json.dumps(
                    {"name": "com.xuunity.light-mcp", "version": package_version, "unity": "2021.3"},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            remote_root = temp_root / "remote.git"
            run_git(temp_root, "init", "--bare", str(remote_root))
            run_git(source_root, "init")
            run_git(source_root, "config", "user.email", "test@example.invalid")
            run_git(source_root, "config", "user.name", "Parity Test")
            run_git(source_root, "add", ".")
            run_git(source_root, "commit", "-m", "Release source")
            run_git(source_root, "tag", "-a", release_tag, "-m", "Release")
            run_git(source_root, "remote", "add", "origin", str(remote_root))
            run_git(source_root, "push", "origin", "HEAD:refs/heads/master", f"refs/tags/{release_tag}")

            project_root = self.create_fake_project(temp_root / "FakeProject", "6000.0.58f2")
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )
            return source_root, project_root

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            manifests = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root, project_root = build(tmp_dir)
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                results.append(
                    self.run_wrapper(["prodmode", "--project-root", str(project_root)], env, legacy=legacy)
                )
                manifest = json.loads(
                    (project_root / "Packages" / "manifest.json").read_text(encoding="utf-8")
                )
                manifests.append(self.normalize(manifest["dependencies"]["com.xuunity.light-mcp"], [tmp_dir]))
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(0, results[1][0])
            self.assertEqual(manifests[0], manifests[1])
            self.assertIn("source_head_matches_release=true", results[1][1])

    def test_prodmode_missing_release_tag_parity(self) -> None:
        def run_git(cwd: Path, *args: str) -> None:
            subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

        def build(tmp_dir: str) -> tuple:
            temp_root = Path(tmp_dir)
            source_root = temp_root / "Source"
            package_root = source_root / "packages" / "com.xuunity.light-mcp"
            (source_root / "templates").mkdir(parents=True)
            package_root.mkdir(parents=True)
            (source_root / "templates" / "server.py").write_text("# fake server\n", encoding="utf-8")
            (package_root / "package.json").write_text(
                json.dumps({"name": "com.xuunity.light-mcp", "version": "0.9.99"}, indent=2) + "\n",
                encoding="utf-8",
            )
            remote_root = temp_root / "remote.git"
            run_git(temp_root, "init", "--bare", str(remote_root))
            run_git(source_root, "init")
            run_git(source_root, "config", "user.email", "test@example.invalid")
            run_git(source_root, "config", "user.name", "Parity Test")
            run_git(source_root, "add", ".")
            run_git(source_root, "commit", "-m", "Unreleased source")
            run_git(source_root, "remote", "add", "origin", str(remote_root))
            run_git(source_root, "push", "origin", "HEAD:refs/heads/master")
            project_root = self.create_fake_project(temp_root / "FakeProject", "6000.0.58f2")
            return source_root, project_root

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root, project_root = build(tmp_dir)
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                results.append(
                    self.run_wrapper(["prodmode", "--project-root", str(project_root)], env, legacy=legacy)
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(1, results[1][0])
            self.assertIn("release tag is not currently advertised", results[1][2])

    def build_fake_synced_source(self, tmp_dir: str, server_body: str) -> Path:
        source_root = Path(tmp_dir) / "Source"
        (source_root / ".git").mkdir(parents=True)
        templates = source_root / "templates"
        templates.mkdir(parents=True)
        (templates / "server.py").write_text(server_body, encoding="utf-8")
        (templates / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (templates / "xuunity_light_unity_mcp_runtime_defaults.json").write_text("{}\n", encoding="utf-8")
        package_root = source_root / "packages" / "com.xuunity.light-mcp"
        package_root.mkdir(parents=True)
        (package_root / "package.json").write_text('{"name":"com.xuunity.light-mcp"}\n', encoding="utf-8")
        return source_root

    def test_compact_summary_and_helper_sync_parity(self) -> None:
        payload = {
            "action": "unity_status_summary",
            "health_status": "green",
            "editor_running": True,
            "mcp_reachable": True,
            "pending_request_count": 0,
            "busy_reason": "",
            "playmode_state": "edit",
        }
        server_body = "import json\nprint(json.dumps(" + repr(payload) + "))\n"

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            installed_listings = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root = self.build_fake_synced_source(tmp_dir, server_body)
                install_dir = Path(tmp_dir) / "install"
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "neutral"
                env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(install_dir)
                results.append(
                    self.run_wrapper(["--compact-summary", "request-status-summary"], env, legacy=legacy)
                )
                installed_listings.append(
                    sorted(
                        str(path.relative_to(install_dir))
                        for path in install_dir.rglob("*")
                        if path.is_file()
                    )
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(0, results[1][0])
            self.assertIn("[xuunity-mcp] compact outcome=status health=green", results[1][2])
            self.assertEqual(installed_listings[0], installed_listings[1])

    def test_compact_summary_error_exit_parity(self) -> None:
        payload = {
            "error": {"code": "bridge_unreachable", "recommended_next_action": "ensure-ready"},
            "request_id": "req-123",
        }
        server_body = (
            "import json, sys\nprint(json.dumps(" + repr(payload) + "))\nsys.exit(3)\n"
        )

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root = self.build_fake_synced_source(tmp_dir, server_body)
                install_dir = Path(tmp_dir) / "install"
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "neutral"
                env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(install_dir)
                results.append(
                    self.run_wrapper(["--compact-summary", "request-status"], env, legacy=legacy)
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(3, results[1][0])
            self.assertIn("outcome=error exit_code=3 code=bridge_unreachable", results[1][2])

    def test_missing_server_error_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root = Path(tmp_dir) / "Source"
                (source_root / "templates").mkdir(parents=True)
                install_dir = Path(tmp_dir) / "install"
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "neutral"
                env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(install_dir)
                results.append(self.run_wrapper(["request-status"], env, legacy=legacy))
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(1, results[1][0])
            self.assertIn("xuunity-mcp server not found:", results[1][2])

    def test_arrange_unity_windows_missing_script_error_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root = self.build_fake_synced_source(tmp_dir, "# fake\n")
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                results.append(self.run_wrapper(["arrange-unity-windows"], env, legacy=legacy))
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(1, results[1][0])
            self.assertIn("arrange_unity_windows.py not found:", results[1][2])

    def test_server_help_sync_parity(self) -> None:
        server_body = "import sys\nprint('usage: fake-server [--help]')\n"
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            results = []
            installed_listings = []
            for tmp_dir, legacy in ((tmp_a, True), (tmp_b, False)):
                source_root = self.build_fake_synced_source(tmp_dir, server_body)
                install_dir = Path(tmp_dir) / "install"
                env = self.make_env()
                env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
                env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "neutral"
                env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(install_dir)
                results.append(self.run_wrapper(["server-help"], env, legacy=legacy))
                installed_listings.append(
                    sorted(
                        str(path.relative_to(install_dir))
                        for path in install_dir.rglob("*")
                        if path.is_file()
                    )
                )
            self.assert_parity(results[0], results[1], roots=[tmp_a, tmp_b])
            self.assertEqual(0, results[1][0])
            self.assertEqual(installed_listings[0], installed_listings[1])
            self.assertIn("usage: fake-server", results[1][1])


if __name__ == "__main__":
    unittest.main()
