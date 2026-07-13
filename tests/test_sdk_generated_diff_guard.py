import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
from server_sdk_diff_guard import run_sdk_generated_diff_guard


class SdkGeneratedDiffGuardTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        project = root / "UnityProject"
        source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
        source.parent.mkdir(parents=True)
        (project / "ProjectSettings").mkdir(parents=True)
        (project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.0f1\n",
            encoding="utf-8",
        )
        source.write_text(
            "repositories { mavenCentral() }\nandroid { signingConfig signingConfigs.release }\nimplementation 'com.vendor:sdk:1.2.3'\n",
            encoding="utf-8",
        )
        self._git(project, "init")
        self._git(project, "config", "user.email", "tests@example.invalid")
        self._git(project, "config", "user.name", "Test User")
        self._git(project, "add", ".")
        self._git(project, "commit", "-m", "baseline")
        return project

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    def _config(self, **overrides: object) -> dict:
        config = {
            "trackedPaths": ["Assets/Plugins/Android/mainTemplate.gradle"],
            "requiredMarkersAfter": ["mavenCentral()", "signingConfig"],
            "expectedVersionChanges": [
                {
                    "path": "Assets/Plugins/Android/mainTemplate.gradle",
                    "fromValue": "com.vendor:sdk:1.2.3",
                    "toValue": "com.vendor:sdk:1.3.0",
                }
            ],
        }
        config.update(overrides)
        return config

    def test_expected_version_update_passes_and_persists_compact_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(source.read_text(encoding="utf-8").replace("1.2.3", "1.3.0"), encoding="utf-8")

            result = run_sdk_generated_diff_guard(project_root=project, config=self._config())
            report_payload = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("expected_dependency_update", result["paths"][0]["change_class"])
        self.assertEqual("none", result["recommended_next_action"])
        self.assertEqual("passed", report_payload["verdict"])

    def test_missing_required_marker_fails_even_when_change_is_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text("repositories { mavenCentral() }\nimplementation 'com.vendor:sdk:1.3.0'\n", encoding="utf-8")

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(expectedChangedAllowlist=["Assets/Plugins/Android/mainTemplate.gradle"]),
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual(["signingConfig"], result["required_marker_missing"])
        self.assertEqual("restore_required_generated_markers_or_review_resolver_output", result["recommended_next_action"])

    def test_stale_previous_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(source.read_text(encoding="utf-8") + "// resolver rewrote whitespace\n", encoding="utf-8")

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(expectedChangedAllowlist=["Assets/Plugins/Android/mainTemplate.gradle"]),
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual("com.vendor:sdk:1.2.3", result["stale_versions"][0]["previous_value"])
        self.assertEqual("rerun_resolver_and_verify_expected_native_versions", result["recommended_next_action"])

    def test_unexpected_generated_change_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(source.read_text(encoding="utf-8") + "packagingOptions { }\n", encoding="utf-8")

            result = run_sdk_generated_diff_guard(project_root=project, config=self._config(expectedVersionChanges=[]))

        self.assertEqual("failed", result["verdict"])
        self.assertEqual(["Assets/Plugins/Android/mainTemplate.gradle"], result["unexpected_changed_files"])

    def test_deleted_generated_file_fails_even_if_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            (project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle").unlink()

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(
                    expectedVersionChanges=[],
                    expectedChangedAllowlist=["Assets/Plugins/Android/mainTemplate.gradle"],
                    requiredMarkersAfter=[],
                ),
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual(["Assets/Plugins/Android/mainTemplate.gradle"], result["missing_current_files"])
        self.assertEqual("restore_missing_generated_files_or_review_resolver_output", result["recommended_next_action"])

    def test_project_inside_monorepo_uses_git_relative_baseline_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            host_root = Path(tmp) / "HostRepo"
            project = host_root / "UnityProject"
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.parent.mkdir(parents=True)
            source.write_text(
                "repositories { mavenCentral() }\nandroid { signingConfig signingConfigs.release }\n",
                encoding="utf-8",
            )
            (project / "ProjectSettings").mkdir()
            (project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.0f1\n", encoding="utf-8")
            self._git(host_root, "init")
            self._git(host_root, "config", "user.email", "tests@example.invalid")
            self._git(host_root, "config", "user.name", "Test User")
            self._git(host_root, "add", ".")
            self._git(host_root, "commit", "-m", "nested baseline")

            result = run_sdk_generated_diff_guard(project_root=project, config=self._config(expectedVersionChanges=[]))

        self.assertEqual("passed", result["verdict"])

    def test_mcp_tool_returns_validation_failure_without_bridge_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text("implementation 'com.vendor:sdk:1.3.0'\n", encoding="utf-8")
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_sdk_generated_diff_guard",
                        "arguments": {"projectRoot": str(project), **self._config()},
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        self.assertTrue(response["result"]["isError"])
        self.assertEqual("failed", response["result"]["structuredContent"]["verdict"])
        self.assertIn("signingConfig", response["result"]["structuredContent"]["required_marker_missing"])

    def test_parser_registers_sdk_guard_command(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(
            ["sdk-generated-diff-guard", "--project-root", "/tmp/FakeProject", "--config-file", "/tmp/guard.json"]
        )
        self.assertEqual("cmd_sdk_generated_diff_guard", args.func_name)
