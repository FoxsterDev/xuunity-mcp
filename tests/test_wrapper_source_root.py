import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WrapperSourceRootTests(unittest.TestCase):
    def make_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHON"] = sys.executable
        return env

    def create_fake_project(self, root: Path, unity_version: str = "2021.3.58f1") -> Path:
        (root / "Assets").mkdir(parents=True)
        (root / "Packages").mkdir(parents=True)
        (root / "ProjectSettings").mkdir(parents=True)
        (root / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {unity_version}\n",
            encoding="utf-8",
        )
        return root

    def run_git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_devmode_prefers_operations_package_source_under_airroot(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            airroot = temp_root / "AIRoot"
            root_package = airroot / "packages" / "com.xuunity.light-mcp"
            operation_root = airroot / "Operations" / "XUUnityLightUnityMcp"
            operation_package = operation_root / "packages" / "com.xuunity.light-mcp"

            for root in (airroot, operation_root):
                (root / "templates").mkdir(parents=True, exist_ok=True)
                (root / "templates" / "server.py").write_text("# fake server\n", encoding="utf-8")
            for package in (root_package, operation_package):
                package.mkdir(parents=True, exist_ok=True)
                (package / "package.json").write_text('{"name":"com.xuunity.light-mcp"}\n', encoding="utf-8")

            project_root = temp_root / "FakeProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir(parents=True)
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env["XUUNITY_LIGHT_UNITY_MCP_AIRROOT"] = str(airroot)

            completed = subprocess.run(
                [str(wrapper), "devmode", "--project-root", str(project_root)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            dependency = manifest["dependencies"]["com.xuunity.light-mcp"]
            resolved_dependency = (project_root / "Packages" / dependency.removeprefix("file:")).resolve()
            self.assertEqual(operation_package.resolve(), resolved_dependency)
            self.assertIn(f"package_source={operation_package}", completed.stdout)

    def test_setup_plan_default_version_uses_source_without_installed_helper_sync(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"
        package_json = repo_root / "packages" / "com.xuunity.light-mcp" / "package.json"
        package_version = json.loads(package_json.read_text(encoding="utf-8"))["version"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)

            completed = subprocess.run(
                [str(wrapper), "setup-plan", "--project-root", str(project_root)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            plan = json.loads(completed.stdout)
            actions = plan["projects"][0]["planned_actions"]
            dependency_actions = [action for action in actions if action["kind"] == "set_manifest_dependency"]
            self.assertEqual(1, len(dependency_actions))
            self.assertTrue(dependency_actions[0]["value"].endswith(f"#v{package_version}"))

            installed_package_json = (
                codex_tools
                / "xuunity-light-unity-mcp"
                / "packages"
                / "com.xuunity.light-mcp"
                / "package.json"
            )
            self.assertFalse(installed_package_json.exists())

    def test_auto_install_target_prefers_codex_home_in_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            stale_claude_install = claude_tools / "xuunity-light-unity-mcp"
            stale_claude_install.mkdir(parents=True)
            stale_server = stale_claude_install / "server.py"
            stale_server.write_text("# stale claude helper\n", encoding="utf-8")

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_SHELL"] = "1"

            completed = subprocess.run(
                [str(wrapper), "server-help"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((codex_tools / "xuunity-light-unity-mcp" / "server.py").is_file())
            self.assertEqual("# stale claude helper\n", stale_server.read_text(encoding="utf-8"))

    def test_explicit_install_target_can_force_claude_from_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "claude"
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_SHELL"] = "1"

            completed = subprocess.run(
                [str(wrapper), "server-help"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((claude_tools / "xuunity-light-unity-mcp" / "server.py").is_file())
            self.assertFalse((codex_tools / "xuunity-light-unity-mcp" / "server.py").exists())

    def test_auto_install_target_preserves_existing_claude_helper_outside_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            claude_install = claude_tools / "xuunity-light-unity-mcp"
            claude_install.mkdir(parents=True)
            claude_server = claude_install / "server.py"
            claude_server.write_text("# stale claude helper\n", encoding="utf-8")

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", None)
            for key in list(env):
                if key.startswith("CODEX"):
                    env.pop(key, None)
            env.pop("CLAUDE_CODE", None)
            env.pop("CLAUDECODE", None)
            env.pop("CLAUDE_CONFIG_PATH", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)

            completed = subprocess.run(
                [str(wrapper), "server-help"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(claude_server.is_file())
            self.assertNotEqual("# stale claude helper\n", claude_server.read_text(encoding="utf-8"))
            self.assertFalse((codex_tools / "xuunity-light-unity-mcp" / "server.py").exists())

    def test_prodmode_pins_package_version_release_tag_not_raw_commit(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
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
                    {
                        "name": "com.xuunity.light-mcp",
                        "version": package_version,
                        "unity": "2021.3",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            remote_root = temp_root / "remote.git"
            self.run_git(temp_root, "init", "--bare", str(remote_root))
            self.run_git(source_root, "init")
            self.run_git(source_root, "config", "user.email", "test@example.invalid")
            self.run_git(source_root, "config", "user.name", "Wrapper Test")
            self.run_git(source_root, "add", ".")
            self.run_git(source_root, "commit", "-m", "Release source")
            self.run_git(source_root, "tag", "-a", release_tag, "-m", "Release")
            self.run_git(source_root, "remote", "add", "origin", str(remote_root))
            self.run_git(source_root, "push", "origin", "HEAD:refs/heads/master", f"refs/tags/{release_tag}")

            project_root = self.create_fake_project(temp_root / "FakeProject", "6000.0.58f2")
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )

            env = self.make_env()
            env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")

            completed = subprocess.run(
                [str(wrapper), "prodmode", "--project-root", str(project_root)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            dependency = manifest["dependencies"]["com.xuunity.light-mcp"]
            self.assertTrue(dependency.endswith(f"#{release_tag}"))
            self.assertNotRegex(dependency, r"#[0-9a-f]{40}$")
            self.assertIn(f"source_release_tag={release_tag}", completed.stdout)
            self.assertIn("source_head_matches_release=true", completed.stdout)

            lock = json.loads((project_root / "Packages" / "packages-lock.json").read_text(encoding="utf-8"))
            self.assertNotIn("com.xuunity.light-mcp", lock["dependencies"])


if __name__ == "__main__":
    unittest.main()
