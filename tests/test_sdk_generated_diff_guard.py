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
import server_core
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
        (project / "Packages").mkdir()
        (project / "Packages" / "packages-lock.json").write_text(
            '{"dependencies":{"com.vendor.sdk":{"version":"1.2.3"}}}\n',
            encoding="utf-8",
        )
        source.write_text(
            "repositories { mavenCentral() }\nandroid { signingConfig signingConfigs.release }\nimplementation 'com.vendor:sdk:1.2.3'\n",
            encoding="utf-8",
        )
        (source.parent / "AndroidResolverDependencies.xml").write_text(
            "<dependencies><androidPackages>"
            '<androidPackage spec="com.vendor:a:1.0"><repositories><repository>https://repo.example/a</repository></repositories></androidPackage>'
            '<androidPackage spec="com.vendor:b:2.0"><repositories><repository>https://repo.example/b</repository></repositories></androidPackage>'
            "</androidPackages></dependencies>\n",
            encoding="utf-8",
        )
        self._git(project, "init")
        self._git(project, "config", "user.email", "tests@example.invalid")
        self._git(project, "config", "user.name", "Test User")
        self._git(project, "add", ".")
        self._git(project, "commit", "-m", "baseline")
        return project

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            **server_core.hidden_window_subprocess_kwargs(),
        )

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
            registry_path = Path(result["artifact_registry"]["registry_path"])
            registry_records = [
                json.loads(line)
                for line in registry_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("xuunity.sdk-generated-diff-guard.v2", result["schema_version"])
        self.assertEqual("expected_dependency_update", result["paths"][0]["change_class"])
        self.assertEqual("gradle_tokenized", result["paths"][0]["diff_mode"])
        self.assertTrue(result["paths"][0]["semantic_changed"])
        self.assertEqual("none", result["recommended_next_action"])
        self.assertEqual("passed", report_payload["verdict"])
        self.assertTrue(result["artifact_registered"])
        self.assertEqual("sdk_generated_diff_report", result["artifact_registry"]["kind"])
        self.assertEqual(1, len(registry_records))
        self.assertEqual(result["report_path"], registry_records[0]["path"])
        self.assertEqual("library", registry_records[0]["destination"])
        self.assertEqual("unity_sdk_generated_diff_guard", registry_records[0]["producer"])
        self.assertEqual("xuunity.sdk-generated-diff-guard.v2", registry_records[0]["artifact_schema_version"])
        self.assertEqual("passed", registry_records[0]["metadata"]["verdict"])
        self.assertEqual(result["artifact_registry"]["hash_sha256"], registry_records[0]["hash_sha256"])

    def test_gradle_reformat_and_block_reorder_is_normalization_noise_without_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(
                "android {\n    signingConfig   signingConfigs.release\n}\n"
                "// resolver reordered generated blocks\n"
                "repositories {\n    mavenCentral ( )\n}\n"
                "implementation    'com.vendor:sdk:1.2.3'\n",
                encoding="utf-8",
            )

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(expectedVersionChanges=[]),
            )

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("resolver_normalization_noise", result["paths"][0]["change_class"])
        self.assertFalse(result["paths"][0]["semantic_changed"])
        self.assertEqual([], result["unexpected_changed_files"])

    def test_xml_node_and_attribute_reorder_is_structural_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/AndroidResolverDependencies.xml"
            source = project / relative_path
            source.write_text(
                "<dependencies><androidPackages>"
                "<!-- resolver output order is not semantic -->"
                '<androidPackage spec="com.vendor:b:2.0"><repositories><repository>https://repo.example/b</repository></repositories></androidPackage>'
                '<androidPackage spec="com.vendor:a:1.0"><repositories><repository>https://repo.example/a</repository></repositories></androidPackage>'
                "</androidPackages></dependencies>\n",
                encoding="utf-8",
            )

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config={
                    "trackedPaths": [relative_path],
                    "requiredMarkersAfter": ["com.vendor:a:1.0", "https://repo.example/b"],
                },
            )

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("xml_structural", result["paths"][0]["diff_mode"])
        self.assertEqual("resolver_normalization_noise", result["paths"][0]["change_class"])
        self.assertFalse(result["paths"][0]["semantic_changed"])

    def test_required_marker_present_only_in_block_comment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(
                "repositories { mavenCentral() }\n"
                "/* signingConfig signingConfigs.release */\n"
                "implementation 'com.vendor:sdk:1.3.0'\n",
                encoding="utf-8",
            )

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(expectedChangedAllowlist=["Assets/Plugins/Android/mainTemplate.gradle"]),
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual(["signingConfig"], result["required_marker_missing"])
        self.assertNotIn("signingConfig", result["paths"][0]["markers_present"])

    def test_comment_delimiter_inside_quoted_url_remains_visible_to_marker_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
            source.write_text(
                source.read_text(encoding="utf-8") + 'maven { url "https://repo.example/sdk" }\n',
                encoding="utf-8",
            )

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(
                    expectedVersionChanges=[],
                    expectedChangedAllowlist=["Assets/Plugins/Android/mainTemplate.gradle"],
                    requiredMarkersAfter=["https://repo.example/sdk"],
                ),
            )

        self.assertEqual("passed", result["verdict"])
        self.assertEqual(["https://repo.example/sdk"], result["paths"][0]["markers_present"])

    def test_invalid_xml_fails_closed_with_typed_normalization_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/AndroidResolverDependencies.xml"
            (project / relative_path).write_text("<dependencies><broken></dependencies>\n", encoding="utf-8")

            result = run_sdk_generated_diff_guard(
                project_root=project,
                config={"trackedPaths": [relative_path], "requiredMarkersAfter": []},
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual("invalid_generated_file", result["paths"][0]["change_class"])
        self.assertEqual("xml_structural", result["invalid_generated_files"][0]["diff_mode"])
        self.assertTrue(result["invalid_generated_files"][0]["reason"].startswith("xml_parse_error:"))
        self.assertEqual(
            "repair_invalid_generated_files_or_select_conservative_diff_mode",
            result["recommended_next_action"],
        )

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

    UNITY_TEMPLATE = (
        "dependencies {\n    implementation 'com.vendor:sdk:1.2.3'\n}\n"
        "android {\n    namespace \"com.unity3d.player\"\n    ndkPath \"**NDKPATH**\"\n"
        "    ndkVersion \"**NDKVERSION**\"\n    compileSdk **APIVERSION**\n}\n"
    )

    def _template_project(self, root: Path) -> tuple[Path, Path]:
        project = self._project(root)
        source = project / "Assets" / "Plugins" / "Android" / "mainTemplate.gradle"
        source.write_text(self.UNITY_TEMPLATE, encoding="utf-8")
        self._git(project, "add", ".")
        self._git(project, "commit", "-m", "unity template")
        return project, source

    def test_allowlisted_template_change_that_drops_unity_lines_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, source = self._template_project(Path(tmp))
            damaged = self.UNITY_TEMPLATE.replace("1.2.3", "1.3.0")
            for line in ('    namespace "com.unity3d.player"\n', '    ndkPath "**NDKPATH**"\n',
                         '    ndkVersion "**NDKVERSION**"\n'):
                damaged = damaged.replace(line, "")
            source.write_text(damaged, encoding="utf-8")
            config = {
                "trackedPaths": ["Assets/Plugins/Android/mainTemplate.gradle"],
                "expectedChangedAllowlist": ["Assets/Plugins/Android/mainTemplate.gradle"],
            }

            result = run_sdk_generated_diff_guard(project_root=project, config=config)
            waived = run_sdk_generated_diff_guard(
                project_root=project, config={**config, "templateMarkerGuard": False}
            )

        self.assertEqual("failed", result["verdict"])
        self.assertEqual("expected_allowlisted_change", result["paths"][0]["change_class"])
        self.assertEqual(
            ["**NDKPATH**", "**NDKVERSION**", "namespace", "ndkPath", "ndkVersion"],
            result["paths"][0]["dropped_template_markers"],
        )
        self.assertEqual("Assets/Plugins/Android/mainTemplate.gradle", result["template_markers_dropped"][0]["path"])
        self.assertEqual("restore_dropped_unity_template_lines_then_rerun_guard", result["recommended_next_action"])
        self.assertEqual("passed", waived["verdict"])
        self.assertIs(False, waived["template_marker_guard"])

    def test_allowlisted_template_change_that_keeps_unity_lines_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, source = self._template_project(Path(tmp))
            source.write_text(
                self.UNITY_TEMPLATE.replace(
                    "implementation 'com.vendor:sdk:1.2.3'",
                    "implementation 'com.vendor:sdk:1.3.0'\n    implementation 'com.vendor:extra:2.0.0'",
                ).replace('ndkPath "**NDKPATH**"', 'ndkPath  "**NDKPATH**" // moved'),
                encoding="utf-8",
            )
            result = run_sdk_generated_diff_guard(
                project_root=project,
                config={
                    "trackedPaths": ["Assets/Plugins/Android/mainTemplate.gradle"],
                    "expectedChangedAllowlist": ["Assets/Plugins/Android/mainTemplate.gradle"],
                },
            )

        self.assertEqual("passed", result["verdict"])
        self.assertEqual([], result["template_markers_dropped"])

    def test_template_marker_guard_ignores_non_template_files_and_validates_its_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            generated = project / "Assets" / "Plugins" / "Android" / "generated.gradle"
            generated.write_text('android {\n    namespace "x"\n    token **DEPS**\n}\n', encoding="utf-8")
            self._git(project, "add", ".")
            self._git(project, "commit", "-m", "generated")
            generated.write_text("android {\n}\n", encoding="utf-8")
            config = {
                "trackedPaths": ["Assets/Plugins/Android/generated.gradle"],
                "expectedChangedAllowlist": ["Assets/Plugins/Android/generated.gradle"],
            }
            result = run_sdk_generated_diff_guard(project_root=project, config=config)
            with self.assertRaises(server_core.ToolInvocationError):
                run_sdk_generated_diff_guard(project_root=project, config={**config, "templateMarkerGuard": "no"})

        self.assertEqual("passed", result["verdict"])
        self.assertEqual([], result["paths"][0]["dropped_template_markers"])

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
            (project / "Packages").mkdir()
            (project / "Packages" / "packages-lock.json").write_text("{}\n", encoding="utf-8")
            self._git(host_root, "init")
            self._git(host_root, "config", "user.email", "tests@example.invalid")
            self._git(host_root, "config", "user.name", "Test User")
            self._git(host_root, "add", ".")
            self._git(host_root, "commit", "-m", "nested baseline")

            result = run_sdk_generated_diff_guard(project_root=project, config=self._config(expectedVersionChanges=[]))

        self.assertEqual("passed", result["verdict"])

    def test_git_untracked_file_captures_and_reuses_fingerprint_bound_library_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/settingsTemplate.gradle"
            generated = project / relative_path
            generated.write_text(
                "repositories { mavenCentral() }\nimplementation 'com.vendor:sdk:1.2.3'\n",
                encoding="utf-8",
            )
            config = {
                "trackedPaths": [relative_path],
                "requiredMarkersAfter": ["mavenCentral()"],
                "trackedSdkVersions": {"com.vendor.sdk": "1.2.3"},
                "expectedVersionChanges": [
                    {"path": relative_path, "fromValue": "1.2.3", "toValue": "1.3.0"}
                ],
                "captureBaseline": True,
            }

            captured = run_sdk_generated_diff_guard(project_root=project, config=config)
            generated.write_text(generated.read_text(encoding="utf-8").replace("1.2.3", "1.3.0"), encoding="utf-8")
            compared = run_sdk_generated_diff_guard(
                project_root=project,
                config={**config, "captureBaseline": False},
            )

        self.assertEqual("passed", captured["verdict"])
        self.assertTrue(captured["baseline_captured"])
        self.assertEqual("library_fingerprint", captured["baseline_source"])
        self.assertEqual("git_untracked_fingerprint_baseline", captured["scope"])
        self.assertTrue(captured["fingerprint_match"])
        self.assertEqual("passed", compared["verdict"])
        self.assertFalse(compared["baseline_captured"])
        self.assertEqual(captured["baseline_fingerprint"], compared["baseline_fingerprint"])
        self.assertEqual("expected_dependency_update", compared["paths"][0]["change_class"])

    def test_git_untracked_baseline_refuses_fingerprint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/settingsTemplate.gradle"
            (project / relative_path).write_text("repositories { mavenCentral() }\n", encoding="utf-8")
            config = {"trackedPaths": [relative_path], "captureBaseline": True}
            run_sdk_generated_diff_guard(project_root=project, config=config)
            (project / "Packages" / "packages-lock.json").write_text(
                '{"dependencies":{"com.vendor.sdk":{"version":"1.3.0"}}}\n',
                encoding="utf-8",
            )

            with self.assertRaises(server_core.ToolInvocationError) as raised:
                run_sdk_generated_diff_guard(
                    project_root=project,
                    config={**config, "captureBaseline": False},
                )

        self.assertEqual("baseline_fingerprint_stale", raised.exception.code)
        self.assertNotEqual(
            raised.exception.details["recorded_fingerprint"],
            raised.exception.details["current_fingerprint"],
        )

    def test_git_untracked_baseline_capture_refuses_dirty_tracked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/settingsTemplate.gradle"
            (project / relative_path).write_text("repositories { mavenCentral() }\n", encoding="utf-8")
            (project / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2022.3.1f1\n",
                encoding="utf-8",
            )

            with self.assertRaises(server_core.ToolInvocationError) as raised:
                run_sdk_generated_diff_guard(
                    project_root=project,
                    config={"trackedPaths": [relative_path], "captureBaseline": True},
                )

        self.assertEqual("baseline_capture_dirty_tree", raised.exception.code)
        self.assertTrue(raised.exception.details["tracked_changes_present"])

    def test_git_untracked_baseline_refuses_tampered_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            relative_path = "Assets/Plugins/Android/settingsTemplate.gradle"
            (project / relative_path).write_text("repositories { mavenCentral() }\n", encoding="utf-8")
            config = {"trackedPaths": [relative_path], "captureBaseline": True}
            captured = run_sdk_generated_diff_guard(project_root=project, config=config)
            snapshot = Path(captured["library_baseline_dir"]) / "files" / relative_path
            snapshot.write_text("repositories { mavenLocal() }\n", encoding="utf-8")

            with self.assertRaises(server_core.ToolInvocationError) as raised:
                run_sdk_generated_diff_guard(
                    project_root=project,
                    config={**config, "captureBaseline": False},
                )

        self.assertEqual("sdk_generated_diff_guard_library_baseline_integrity_mismatch", raised.exception.code)

    def test_mixed_capture_preserves_per_path_provenance_and_global_marker_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            tracked_path = "Assets/Plugins/Android/mainTemplate.gradle"
            untracked_path = "Assets/Plugins/Android/settingsTemplate.gradle"
            (project / untracked_path).write_text("pluginManagement { }\n", encoding="utf-8")
            config = {
                "trackedPaths": [tracked_path, untracked_path],
                "requiredMarkersAfter": ["signingConfig"],
                "captureBaseline": True,
            }

            result = run_sdk_generated_diff_guard(project_root=project, config=config)

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("mixed", result["baseline_source"])
        self.assertEqual("mixed_git_and_library_baseline", result["scope"])
        self.assertEqual("HEAD", result["paths"][0]["baseline_ref"])
        self.assertEqual("", result["paths"][1]["baseline_ref"])
        self.assertEqual("git_head", result["paths"][0]["baseline_source"])
        self.assertEqual("library_fingerprint", result["paths"][1]["baseline_source"])

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
            structured = response["result"]["structuredContent"]
            registry_records = [
                json.loads(line)
                for line in Path(structured["artifact_registry"]["registry_path"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(response["result"]["isError"])
        self.assertEqual("failed", structured["verdict"])
        self.assertIn("signingConfig", structured["required_marker_missing"])
        self.assertTrue(structured["artifact_registered"])
        self.assertEqual("failed", registry_records[0]["metadata"]["verdict"])

    def test_custom_project_report_path_is_registered_without_claiming_library_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            result = run_sdk_generated_diff_guard(
                project_root=project,
                config=self._config(expectedVersionChanges=[]),
                report_file="Artifacts/sdk_guard.json",
            )
            registry_record = json.loads(
                Path(result["artifact_registry"]["registry_path"]).read_text(encoding="utf-8").splitlines()[0]
            )

        self.assertEqual("passed", result["verdict"])
        self.assertEqual("external", registry_record["destination"])
        self.assertEqual("Artifacts/sdk_guard.json", registry_record["project_relative_path"].replace("\\", "/"))

    def test_parser_registers_sdk_guard_command(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(
            ["sdk-generated-diff-guard", "--project-root", "/tmp/FakeProject", "--config-file", "/tmp/guard.json"]
        )
        self.assertEqual("cmd_sdk_generated_diff_guard", args.func_name)
