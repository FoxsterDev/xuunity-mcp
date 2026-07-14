import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_context
import server_setup_common
import server_setup_wizard as wizard

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "com.xuunity.light-mcp"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def create_unity_project(
    root: Path,
    *,
    unity_version: str,
    dependencies: dict[str, str] | None = None,
) -> Path:
    (root / "Assets").mkdir(parents=True, exist_ok=True)
    (root / "ProjectSettings").mkdir(parents=True, exist_ok=True)
    (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        f"m_EditorVersion: {unity_version}\n",
        encoding="utf-8",
    )
    write_json(root / "Packages" / "manifest.json", {"dependencies": dependencies or {}})
    return root


def create_installed_helper(install_dir: Path, *, version: str, refresh_name: str) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (install_dir / "server.py").write_text("SERVER_INFO = {}\n", encoding="utf-8")
    (install_dir / refresh_name).write_text("launcher\n", encoding="utf-8")
    write_json(
        install_dir / "packages" / "com.xuunity.light-mcp" / "package.json",
        {"name": "com.xuunity.light-mcp", "version": version},
    )


class SetupWizardTests(unittest.TestCase):
    def test_package_manifest_declares_2021_3_and_no_hard_test_framework_dependency(self) -> None:
        payload = json.loads((PACKAGE_ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual("2021.3", payload["unity"])
        self.assertNotIn("com.unity.test-framework", payload.get("dependencies", {}))

        manifests_dir = PACKAGE_ROOT.parents[1] / "templates" / "package-manifests"
        for manifest_path in manifests_dir.glob("unity-package-*.json"):
            template = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("com.unity.test-framework", template.get("dependencies", {}))

    def test_core_asmdef_has_no_test_runner_refs_and_optional_asmdef_has_version_define(self) -> None:
        core = json.loads((PACKAGE_ROOT / "Editor" / "com.xuunity.light-mcp.Editor.asmdef").read_text(encoding="utf-8"))
        optional = json.loads(
            (
                PACKAGE_ROOT
                / "Editor"
                / "TestFramework"
                / "com.xuunity.light-mcp.Editor.TestFramework.asmdef"
            ).read_text(encoding="utf-8")
        )

        self.assertNotIn("UnityEngine.TestRunner", core.get("references", []))
        self.assertNotIn("UnityEditor.TestRunner", core.get("references", []))
        self.assertIn("UnityEngine.TestRunner", optional.get("references", []))
        self.assertIn("UnityEditor.TestRunner", optional.get("references", []))
        self.assertEqual(["XUUNITY_LIGHT_MCP_TESTS_CAPABILITY"], optional["defineConstraints"])
        self.assertEqual(
            {
                "name": "com.unity.test-framework",
                "expression": "1.1.33",
                "define": "XUUNITY_LIGHT_MCP_TESTS_CAPABILITY",
            },
            optional["versionDefines"][0],
        )

    def test_package_test_asmdefs_enable_unity_test_assemblies(self) -> None:
        for relative_path in (
            "Tests/EditMode/com.xuunity.light-mcp.Editor.Tests.asmdef",
            "Tests/PlayMode/com.xuunity.light-mcp.PlayMode.Tests.asmdef",
        ):
            payload = json.loads((PACKAGE_ROOT / relative_path).read_text(encoding="utf-8"))
            self.assertIn("TestAssemblies", payload.get("optionalUnityReferences", []))
            self.assertNotIn("UnityEngine.TestRunner", payload.get("references", []))
            self.assertNotIn("UnityEditor.TestRunner", payload.get("references", []))

    def test_core_editor_sources_do_not_reference_test_runner_api(self) -> None:
        forbidden = (
            "UnityEditor.TestTools.TestRunner",
            "UnityEngine.TestRunner",
            "UnityEditor.TestRunner",
        )
        for path in (PACKAGE_ROOT / "Editor").rglob("*.cs"):
            if "TestFramework" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, str(path))

    def test_build_player_operation_is_registered_in_core_and_health_probe(self) -> None:
        registry = (PACKAGE_ROOT / "Editor" / "Core" / "XUUnityLightMcpOperationRegistry.cs").read_text(encoding="utf-8")
        capability = (PACKAGE_ROOT / "Editor" / "Core" / "XUUnityLightMcpCapabilityRegistry.cs").read_text(encoding="utf-8")
        health_probe = (PACKAGE_ROOT / "Editor" / "Helpers" / "XUUnityLightMcpHealthProbe.cs").read_text(encoding="utf-8")

        self.assertIn('"unity.build_player"', registry)
        self.assertIn("new XUUnityLightMcpBuildPlayerOperation()", registry)
        self.assertIn('"unity.build_player"', capability)
        self.assertIn("BuildBuildPlayerCapability()", health_probe)

    def test_scene_open_operation_is_registered_in_core_and_health_probe(self) -> None:
        registry = (PACKAGE_ROOT / "Editor" / "Core" / "XUUnityLightMcpOperationRegistry.cs").read_text(encoding="utf-8")
        capability = (PACKAGE_ROOT / "Editor" / "Core" / "XUUnityLightMcpCapabilityRegistry.cs").read_text(encoding="utf-8")
        health_probe = (PACKAGE_ROOT / "Editor" / "Helpers" / "XUUnityLightMcpHealthProbe.cs").read_text(encoding="utf-8")

        self.assertIn('"unity.scene.open"', registry)
        self.assertIn("new XUUnityLightMcpSceneOpenOperation()", registry)
        self.assertIn('"unity.scene.open"', capability)
        self.assertIn('"unity.scene.open"', health_probe)

    def test_compatibility_policy_does_not_directly_call_newer_package_info_api(self) -> None:
        text = (PACKAGE_ROOT / "Editor" / "Core" / "XUUnityLightMcpCompatibilityPolicy.cs").read_text(encoding="utf-8")
        self.assertNotIn(".FindForPackageName(", text)

    def test_policy_recommends_test_framework_version_by_unity_major(self) -> None:
        self.assertEqual("1.1.33", wizard.recommended_test_framework_version("2021.3.45f1"))
        self.assertEqual("1.1.33", wizard.recommended_test_framework_version("2022.3.60f1"))
        self.assertEqual("1.5.1", wizard.recommended_test_framework_version("6000.0.45f1"))
        self.assertEqual("1.5.1", wizard.recommended_test_framework_version("6000.5.0a1"))

    def test_setup_plan_discovers_recursive_mixed_unity_projects_without_global_dependency_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project_2022 = create_unity_project(
                workspace / "Hub2022",
                unity_version="2022.3.60f1",
            )
            project_6000 = create_unity_project(
                workspace / "nested" / "Repo6000" / "Hub6000",
                unity_version="6000.0.45f1",
                dependencies={"com.unity.test-framework": "1.1.33"},
            )

            plan = wizard.build_setup_plan(
                workspace_root=str(workspace),
                project_roots=None,
                recursive=True,
                include_test_framework="yes",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

        projects = {Path(item["project_root"]).name: item for item in plan["projects"]}
        self.assertEqual({"Hub2022", "Hub6000"}, set(projects))
        actions_2022 = projects[project_2022.name]["planned_actions"]
        actions_6000 = projects[project_6000.name]["planned_actions"]
        self.assertIn(
            {
                "kind": "install_test_framework_dependency",
                "package": "com.unity.test-framework",
                "version": "1.1.33",
                "reason": "enable_optional_test_capability",
                "requires_approval": True,
                "apply_phase": "before_opening_unity",
            },
            actions_2022,
        )
        upgrade_actions_6000 = [action for action in actions_6000 if action["kind"] == "upgrade_test_framework_dependency"]
        self.assertEqual(1, len(upgrade_actions_6000))
        self.assertEqual("1.1.33", upgrade_actions_6000[0]["current_version"])
        self.assertEqual("1.5.1", upgrade_actions_6000[0]["version"])
        self.assertEqual("upgrade_recommended", upgrade_actions_6000[0]["reason"])
        self.assertEqual("before_opening_unity", upgrade_actions_6000[0]["apply_phase"])

    def test_setup_plan_prefers_explicit_project_roots_over_workspace_sibling_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target_project = create_unity_project(
                workspace / "TargetProject",
                unity_version="6000.0.45f1",
            )
            create_unity_project(
                workspace / "TargetProject" / "NestedSample",
                unity_version="6000.0.45f1",
            )

            plan = wizard.build_setup_plan(
                workspace_root=str(target_project),
                project_roots=[str(target_project)],
                recursive=True,
                include_test_framework="auto",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

        self.assertEqual(1, plan["discovered_project_count"])
        self.assertEqual([str(target_project.resolve())], plan["requested_project_roots"])
        self.assertFalse(plan["requires_explicit_project_selection_for_apply"])
        self.assertEqual([str(target_project.resolve())], plan["preflight_review"]["selected_project_roots"])
        self.assertEqual("explicit_project_root", plan["projects"][0]["selection_state"])

    def test_setup_plan_does_not_plan_user_level_client_config_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = create_unity_project(
                root / "Project",
                unity_version="6000.0.58f2",
                dependencies={"com.xuunity.light-mcp": "git-url"},
            )
            claude_config = root / ".claude.json"
            claude_config.write_text("{}", encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {
                    "CLAUDECODE": "1",
                    "CLAUDE_CONFIG_PATH": str(claude_config),
                },
                clear=True,
            ):
                plan = wizard.build_setup_plan(
                    workspace_root=None,
                    project_roots=[str(project_root)],
                    recursive=False,
                    include_test_framework="auto",
                    package_source="git",
                    package_version="0.3.39",
                    local_package_source="/tmp/light-mcp",
                )

        review = plan["preflight_review"]
        self.assertEqual([], review["planned_user_level_config_changes"])
        self.assertIn("Review planned project manifest and bridge changes", review["notes"][0])
        self.assertIn("separate client wiring review", review["client_wiring_review"]["reason"])
        self.assertIn("Planned client config review targets", review["preferred_review_summary"])
        self.assertNotIn("user-level client config changes before applying setup", review["preferred_review_summary"])

    def test_setup_home_fallback_survives_missing_host_home_directory(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            server_setup_common.Path,
            "home",
            side_effect=RuntimeError("Could not determine home directory."),
        ):
            targets = server_setup_common.helper_install_targets()

        self.assertIn("codex", {target["client_id"] for target in targets})

    def test_setup_plan_upgrades_stale_canonical_pin_instead_of_reporting_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = create_unity_project(
                root / "Project",
                unity_version="6000.3.2f1",
                dependencies={
                    "com.xuunity.light-mcp": wizard.default_git_dependency("0.3.23"),
                },
            )
            wizard.write_bridge_config(project_root)
            with mock.patch.dict(
                os.environ,
                {
                    "HOME": str(root / "home"),
                    "CODEX_SHELL": "1",
                    "CODEX_HOME": str(root / "codex-home"),
                    "CODEX_TOOLS_HOME": str(root / "codex-tools"),
                    "CLAUDE_TOOLS_HOME": str(root / "claude-tools"),
                    "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(root / "neutral"),
                },
                clear=True,
            ):
                plan = wizard.build_setup_plan(
                    workspace_root=None,
                    project_roots=[str(project_root)],
                    recursive=False,
                    include_test_framework="no",
                    package_source="git",
                    package_version="0.3.45",
                    local_package_source="/unused",
                )

        project = plan["projects"][0]
        dependency_actions = [
            action for action in project["planned_actions"]
            if action["kind"] == "set_manifest_dependency"
        ]
        self.assertEqual("stale_git_pin", project["package_dependency_state"])
        self.assertEqual("ready_to_apply", project["validation_status"])
        self.assertNotEqual("already_configured", plan["setup_status"])
        self.assertFalse(plan["installation_alignment"]["runtime_execution_allowed"])
        self.assertFalse(plan["installation_alignment"]["current_mcp_session_safe"])
        self.assertTrue(plan["installation_alignment"]["live_session_proof_required"])
        self.assertEqual("0.3.45", plan["installation_alignment"]["required_live_server_version"])
        self.assertEqual(1, len(dependency_actions))
        self.assertEqual("upgrade_stale_git_pin", dependency_actions[0]["reason"])
        self.assertEqual(wizard.default_git_dependency("0.3.23"), dependency_actions[0]["expected_current_value"])
        self.assertEqual(wizard.default_git_dependency("0.3.45"), dependency_actions[0]["value"])

    def test_setup_plan_keeps_exact_pin_and_refuses_automatic_downgrade_or_custom_rewrite(self) -> None:
        cases = (
            (wizard.default_git_dependency("0.3.45"), "aligned", False),
            (wizard.default_git_dependency("0.3.46"), "newer_than_requested", True),
            ("https://example.com/fork.git?path=/package#v9.0.0", "custom_source_mismatch", True),
            ("file:../local-package", "custom_source_mismatch", True),
        )
        for dependency, expected_status, expects_manual in cases:
            with self.subTest(dependency=dependency), tempfile.TemporaryDirectory() as tmp:
                project_root = create_unity_project(
                    Path(tmp) / "Project",
                    unity_version="2022.3.60f1",
                    dependencies={"com.xuunity.light-mcp": dependency},
                )
                wizard.write_bridge_config(project_root)
                plan = wizard.build_setup_plan(
                    workspace_root=None,
                    project_roots=[str(project_root)],
                    recursive=False,
                    include_test_framework="no",
                    package_source="git",
                    package_version="0.3.45",
                    local_package_source="/unused",
                )

                project = plan["projects"][0]
                dependency_actions = [
                    action for action in project["planned_actions"]
                    if action["kind"] == "set_manifest_dependency"
                ]
                mismatch_actions = [
                    action for action in project["manual_actions"]
                    if action["kind"] == "resolve_package_source_or_version_mismatch"
                ]
                self.assertEqual(expected_status, project["package_dependency_state"])
                self.assertEqual([], dependency_actions)
                self.assertEqual(expects_manual, bool(mismatch_actions))

    def test_setup_apply_rejects_dependency_changed_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="6000.3.2f1",
                dependencies={"com.xuunity.light-mcp": wizard.default_git_dependency("0.3.23")},
            )
            wizard.write_bridge_config(project_root)
            plan = wizard.build_setup_plan(
                workspace_root=None,
                project_roots=[str(project_root)],
                recursive=False,
                include_test_framework="no",
                package_source="git",
                package_version="0.3.45",
                local_package_source="/unused",
            )
            wizard.set_manifest_dependency(
                project_root,
                "com.xuunity.light-mcp",
                wizard.default_git_dependency("0.3.24"),
            )

            with self.assertRaises(wizard.ToolInvocationError) as cm:
                wizard.apply_setup_plan(plan, approve=True)

            current = wizard.manifest_dependency(project_root, "com.xuunity.light-mcp")

        self.assertEqual("setup_plan_stale_dependency_changed", cm.exception.code)
        self.assertEqual(wizard.default_git_dependency("0.3.24"), current)

    def test_helper_target_requires_refresh_for_old_or_unknown_install(self) -> None:
        for host_system, refresh_name in (
            ("Darwin", "run_installed_or_refresh_xuunity_mcp.sh"),
            ("Linux", "run_installed_or_refresh_xuunity_mcp.sh"),
            ("Windows", "run_installed_or_refresh_xuunity_mcp.cmd"),
        ):
            with self.subTest(host_system=host_system), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                install_dir = root / "codex-tools" / "xuunity-mcp"
                create_installed_helper(
                    install_dir,
                    version="0.3.23",
                    refresh_name=refresh_name,
                )
                with mock.patch.object(
                    server_setup_common.platform,
                    "system",
                    return_value=host_system,
                ), mock.patch.dict(
                    os.environ,
                    {
                        "HOME": str(root / "home"),
                        "CODEX_SHELL": "1",
                        "CODEX_TOOLS_HOME": str(root / "codex-tools"),
                        "CLAUDE_TOOLS_HOME": str(root / "claude-tools"),
                        "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(root / "neutral"),
                    },
                    clear=True,
                ):
                    targets = server_setup_common.helper_install_targets("0.3.45")
                    write_json(
                        install_dir / "packages" / "com.xuunity.light-mcp" / "package.json",
                        {"name": "com.xuunity.light-mcp", "version": "0.3.45"},
                    )
                    same_version_without_integrity = server_setup_common.helper_install_targets("0.3.45")
                    (
                        install_dir / "packages" / "com.xuunity.light-mcp" / "package.json"
                    ).unlink()
                    unknown_version = server_setup_common.helper_install_targets("0.3.45")

                codex = next(item for item in targets if item["client_id"] == "codex")
                self.assertEqual("0.3.23", codex["installed_version"])
                self.assertEqual("stale", codex["version_alignment"])
                self.assertEqual("refresh_existing_helper", codex["helper_action"])
                self.assertFalse(codex["runtime_execution_allowed"])
                unverified = next(
                    item for item in same_version_without_integrity if item["client_id"] == "codex"
                )
                self.assertEqual("integrity_missing", unverified["version_alignment"])
                self.assertEqual("refresh_existing_helper", unverified["helper_action"])
                self.assertFalse(unverified["runtime_execution_allowed"])
                unknown = next(item for item in unknown_version if item["client_id"] == "codex")
                self.assertEqual("unknown", unknown["version_alignment"])
                self.assertEqual("refresh_existing_helper", unknown["helper_action"])
                self.assertFalse(unknown["runtime_execution_allowed"])

    def test_helper_target_rejects_non_native_refresh_launcher(self) -> None:
        for host_system, wrong_refresh_name, expected_refresh_name in (
            (
                "Darwin",
                "run_installed_or_refresh_xuunity_mcp.cmd",
                "run_installed_or_refresh_xuunity_mcp.sh",
            ),
            (
                "Linux",
                "run_installed_or_refresh_xuunity_mcp.cmd",
                "run_installed_or_refresh_xuunity_mcp.sh",
            ),
            (
                "Windows",
                "run_installed_or_refresh_xuunity_mcp.sh",
                "run_installed_or_refresh_xuunity_mcp.cmd",
            ),
        ):
            with self.subTest(host_system=host_system), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                install_dir = root / "codex-tools" / "xuunity-mcp"
                create_installed_helper(
                    install_dir,
                    version="0.3.45",
                    refresh_name=wrong_refresh_name,
                )
                with mock.patch.object(
                    server_setup_common.platform,
                    "system",
                    return_value=host_system,
                ), mock.patch.dict(
                    os.environ,
                    {
                        "HOME": str(root / "home"),
                        "CODEX_SHELL": "1",
                        "CODEX_TOOLS_HOME": str(root / "codex-tools"),
                        "CLAUDE_TOOLS_HOME": str(root / "claude-tools"),
                        "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(root / "neutral"),
                    },
                    clear=True,
                ):
                    targets = server_setup_common.helper_install_targets("0.3.45")

                codex = next(item for item in targets if item["client_id"] == "codex")
                self.assertEqual("refresh_launcher_missing", codex["version_alignment"])
                self.assertFalse(codex["refresh_launcher_present"])
                self.assertTrue(codex["run_path"].endswith(expected_refresh_name))
                self.assertEqual("refresh_existing_helper", codex["helper_action"])
                self.assertFalse(codex["runtime_execution_allowed"])

    def test_windows_codex_bash_launcher_requires_native_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text(
                "[mcp_servers.xuunity_light_unity]\n"
                'command = "bash"\n'
                'args = ["-lc", "exec \\"/tmp/xuunity/run.sh\\""]\n'
                "required = false\n",
                encoding="utf-8",
            )
            with mock.patch.object(server_setup_common.platform, "system", return_value="Windows"), mock.patch.dict(
                os.environ,
                {
                    "HOME": str(root / "home"),
                    "USERPROFILE": str(root / "home"),
                    "CODEX_SHELL": "1",
                    "CODEX_HOME": str(codex_home),
                },
                clear=True,
            ):
                targets = server_setup_common.build_client_config_targets(None)

        codex = next(item for item in targets if item["client_id"] == "codex")
        self.assertEqual("windows_launcher_migration_required", codex["launcher_status"])
        self.assertEqual("replace_incompatible_server_block", codex["config_action"])
        self.assertIn("windows_launcher_flavor_mismatch", codex["launcher_issue_codes"])
        self.assertIn("unsafe_legacy_launcher_reference", codex["launcher_issue_codes"])
        self.assertFalse(codex["runtime_execution_allowed"])

    def test_windows_codex_native_refresh_launcher_is_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            codex_home.mkdir(parents=True)
            args = ["/d", "/c", "call", r"C:\\Users\\dev\\.codex-tools\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd"]
            (codex_home / "config.toml").write_text(
                "[mcp_servers.xuunity_light_unity]\n"
                'command = "cmd.exe"\n'
                f"args = {json.dumps(args)}\n"
                "required = false\n",
                encoding="utf-8",
            )
            with mock.patch.object(server_setup_common.platform, "system", return_value="Windows"), mock.patch.dict(
                os.environ,
                {
                    "HOME": str(root / "home"),
                    "USERPROFILE": str(root / "home"),
                    "CODEX_SHELL": "1",
                    "CODEX_HOME": str(codex_home),
                },
                clear=True,
            ):
                targets = server_setup_common.build_client_config_targets(None)

        codex = next(item for item in targets if item["client_id"] == "codex")
        self.assertEqual("compatible", codex["launcher_status"])
        self.assertEqual("verify_existing_server_block", codex["config_action"])
        self.assertTrue(codex["runtime_execution_allowed"])

    def test_validate_setup_blocks_stale_canonical_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="6000.3.2f1",
                dependencies={"com.xuunity.light-mcp": wizard.default_git_dependency("0.3.23")},
            )
            wizard.write_bridge_config(project_root)
            result = wizard.validate_setup(
                project_root,
                expected_package_version="0.3.45",
            )

        self.assertEqual("blocked", result["validation_status"])
        self.assertEqual("stale_git_pin", result["package_alignment"]["status"])
        self.assertIn("mcp_package_version_mismatch", result["blockers"])

    def test_default_package_version_finds_installed_helper_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "xuunity-mcp"
            write_json(
                install_dir / "packages" / "com.xuunity.light-mcp" / "package.json",
                {"version": "0.3.45"},
            )
            with mock.patch.object(
                server_batch_context,
                "__file__",
                str(install_dir / "server_batch_context.py"),
            ):
                package_source = server_batch_context.default_local_package_source()
                version = server_batch_context.default_light_mcp_package_version()

        self.assertEqual(
            (install_dir / "packages" / "com.xuunity.light-mcp").resolve(),
            package_source.resolve(),
        )
        self.assertEqual("0.3.45", version)

    def test_setup_apply_requires_approval_and_mutates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(Path(tmp) / "Project", unity_version="2021.3.45f1")
            plan = wizard.build_setup_plan(
                workspace_root=None,
                project_roots=[str(project_root)],
                recursive=False,
                include_test_framework="yes",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

            with self.assertRaises(wizard.ToolInvocationError) as cm:
                wizard.apply_setup_plan(plan, approve=False)
            self.assertEqual("approval_required", cm.exception.code)

            result = wizard.apply_setup_plan(plan, approve=True)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("setup_apply", result["action"])
        self.assertIn("com.xuunity.light-mcp", manifest["dependencies"])
        self.assertEqual("1.1.33", manifest["dependencies"]["com.unity.test-framework"])

    def test_setup_apply_requires_explicit_project_selection_for_multi_project_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project_a = create_unity_project(workspace / "ProjectA", unity_version="2021.3.45f1")
            project_b = create_unity_project(workspace / "ProjectB", unity_version="6000.0.45f1")
            plan = wizard.build_setup_plan(
                workspace_root=str(workspace),
                project_roots=None,
                recursive=False,
                include_test_framework="auto",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

            with self.assertRaises(wizard.ToolInvocationError) as cm:
                wizard.apply_setup_plan(plan, approve=True)

        self.assertEqual("explicit_project_selection_required", cm.exception.code)
        self.assertEqual(
            sorted([str(project_a.resolve()), str(project_b.resolve())]),
            sorted(cm.exception.details["available_project_roots"]),
        )

    def test_setup_apply_can_filter_a_reviewed_multi_project_plan_to_one_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project_a = create_unity_project(workspace / "ProjectA", unity_version="2021.3.45f1")
            project_b = create_unity_project(workspace / "ProjectB", unity_version="6000.0.45f1")
            plan = wizard.build_setup_plan(
                workspace_root=str(workspace),
                project_roots=None,
                recursive=False,
                include_test_framework="auto",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

            result = wizard.apply_setup_plan(
                plan,
                approve=True,
                selected_project_roots=[str(project_b)],
            )
            manifest_a = json.loads((project_a / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            manifest_b = json.loads((project_b / "Packages" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual([str(project_b.resolve())], result["selected_project_roots"])
        self.assertEqual([str(project_a.resolve())], result["skipped_project_roots"])
        self.assertNotIn("com.xuunity.light-mcp", manifest_a["dependencies"])
        self.assertIn("com.xuunity.light-mcp", manifest_b["dependencies"])

    def test_uninstall_project_only_plan_keeps_user_config_and_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = create_unity_project(
                root / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.xuunity.light-mcp": "git-url"},
            )
            wizard.write_bridge_config(project_root)
            codex_home = root / "codex-home"
            codex_tools = root / "codex-tools"

            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "CODEX_TOOLS_HOME": str(codex_tools),
                    "CODEX_SHELL": "1",
                },
                clear=False,
            ):
                plan = wizard.build_uninstall_plan(
                    mode="project-only-cleanup",
                    project_roots=[str(project_root)],
                )

        review = plan["preflight_review"]
        project_actions = plan["projects"][0]["planned_actions"]
        self.assertEqual("uninstall_plan", plan["action"])
        self.assertEqual("project-only-cleanup", plan["mode"])
        self.assertEqual([], review["planned_user_level_config_changes"])
        self.assertEqual([], review["helper_installs_to_remove"])
        self.assertTrue(any(action["kind"] == "remove_manifest_dependency" for action in project_actions))
        self.assertTrue(any(action["kind"] == "remove_project_bridge_directory" for action in project_actions))
        self.assertIn("keep_helper_install", {target["uninstall_action"] for target in review["planned_helper_install_targets"]})

    def test_uninstall_project_only_apply_cleans_only_selected_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = create_unity_project(
                root / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.xuunity.light-mcp": "git-url", "com.example.keep": "1.0.0"},
            )
            sibling_root = create_unity_project(
                root / "Sibling",
                unity_version="2022.3.60f1",
                dependencies={"com.xuunity.light-mcp": "git-url"},
            )
            write_json(
                project_root / "Packages" / "packages-lock.json",
                {"dependencies": {"com.xuunity.light-mcp": {"version": "git-url"}, "com.example.keep": {"version": "1.0.0"}}},
            )
            wizard.write_bridge_config(project_root)
            wizard.write_bridge_config(sibling_root)
            plan = wizard.build_uninstall_plan(
                mode="project-only-cleanup",
                project_roots=[str(project_root)],
                workspace_root=str(root),
            )

            result = wizard.apply_uninstall_plan(plan, approve=True)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            sibling_manifest = json.loads((sibling_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            lock = json.loads((project_root / "Packages" / "packages-lock.json").read_text(encoding="utf-8"))

            self.assertEqual("uninstall_apply", result["action"])
            self.assertNotIn("com.xuunity.light-mcp", manifest["dependencies"])
            self.assertEqual("1.0.0", manifest["dependencies"]["com.example.keep"])
            self.assertNotIn("com.xuunity.light-mcp", lock["dependencies"])
            self.assertFalse((project_root / "Library" / "XUUnityLightMcp").exists())
            self.assertIn("com.xuunity.light-mcp", sibling_manifest["dependencies"])
            self.assertTrue((sibling_root / "Library" / "XUUnityLightMcp").exists())

    def test_uninstall_full_reset_accepts_current_user_reset_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(root / "codex-home"),
                    "CODEX_TOOLS_HOME": str(root / "codex-tools"),
                    "CODEX_SHELL": "1",
                },
                clear=False,
            ):
                plan = wizard.build_uninstall_plan(
                    mode="current-user-reset",
                    project_roots=[],
                    client="codex",
                )

        self.assertEqual("uninstall_plan", plan["action"])
        self.assertEqual("full-reset-current-user", plan["mode"])

    def test_uninstall_full_reset_removes_only_codex_block_and_selected_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            codex_config = codex_home / "config.toml"
            codex_config.parent.mkdir(parents=True)
            codex_config.write_text(
                "\n".join(
                    [
                        "[mcp_servers.other]",
                        "command = \"other\"",
                        "",
                        "[mcp_servers.xuunity_light_unity]",
                        "command = \"bash\"",
                        "args = [\"-lc\", \"exec run.sh\"]",
                        "",
                        "[profiles.default]",
                        "model = \"gpt\"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            codex_helper = root / "codex-tools" / "xuunity-mcp"
            codex_helper.mkdir(parents=True)
            (codex_helper / "server.py").write_text("# helper\n", encoding="utf-8")
            (codex_helper / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            claude_helper = root / "claude-tools" / "xuunity-mcp"
            claude_helper.mkdir(parents=True)
            (claude_helper / "server.py").write_text("# helper\n", encoding="utf-8")
            (claude_helper / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "CODEX_TOOLS_HOME": str(root / "codex-tools"),
                    "CLAUDE_TOOLS_HOME": str(root / "claude-tools"),
                    "CODEX_SHELL": "1",
                },
                clear=False,
            ):
                plan = wizard.build_uninstall_plan(
                    mode="full-reset-current-user",
                    project_roots=[],
                    client="codex",
                )
                result = wizard.apply_uninstall_plan(plan, approve=True)

            config_text = codex_config.read_text(encoding="utf-8")
            self.assertEqual("uninstall_apply", result["action"])
            self.assertNotIn("[mcp_servers.xuunity_light_unity]", config_text)
            self.assertIn("[mcp_servers.other]", config_text)
            self.assertIn("[profiles.default]", config_text)
            self.assertFalse(codex_helper.exists())
            self.assertTrue(claude_helper.exists())
            self.assertEqual(1, len(result["client_config_changes"]))
            self.assertEqual(1, len(result["helper_install_changes"]))

    def test_uninstall_full_reset_neutral_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_tools = root / "codex-tools"
            claude_tools = root / "claude-tools"
            neutral_tools = root / "neutral-tools" / "xuunity-mcp"

            codex_helper = codex_tools / "xuunity-mcp"
            codex_helper.mkdir(parents=True)
            (codex_helper / "server.py").write_text("# helper\n", encoding="utf-8")
            (codex_helper / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            neutral_tools.mkdir(parents=True)
            (neutral_tools / "server.py").write_text("# helper\n", encoding="utf-8")
            (neutral_tools / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_TOOLS_HOME": str(codex_tools),
                    "CLAUDE_TOOLS_HOME": str(claude_tools),
                    "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(neutral_tools),
                },
                clear=False,
            ):
                # 1. Codex full reset without other helpers should KEEP neutral
                plan = wizard.build_uninstall_plan(
                    mode="full-reset-current-user",
                    project_roots=[],
                    client="codex",
                    include_other_client_helpers=False,
                )
                helper_removals = plan["preflight_review"]["helper_installs_to_remove"]
                self.assertIn(str(codex_helper), helper_removals)
                self.assertNotIn(str(neutral_tools), helper_removals)

                # 2. Codex full reset WITH other helpers should REMOVE neutral
                plan_all = wizard.build_uninstall_plan(
                    mode="full-reset-current-user",
                    project_roots=[],
                    client="codex",
                    include_other_client_helpers=True,
                )
                helper_removals_all = plan_all["preflight_review"]["helper_installs_to_remove"]
                self.assertIn(str(codex_helper), helper_removals_all)
                self.assertIn(str(neutral_tools), helper_removals_all)

                # 3. Explicit neutral full reset should REMOVE neutral and KEEP others
                plan_neutral = wizard.build_uninstall_plan(
                    mode="full-reset-current-user",
                    project_roots=[],
                    client="neutral",
                )
                helper_removals_neutral = plan_neutral["preflight_review"]["helper_installs_to_remove"]
                self.assertIn(str(neutral_tools), helper_removals_neutral)
                self.assertNotIn(str(codex_helper), helper_removals_neutral)

                # 4. Manual selection required full reset (client=None, unknown client context) should REMOVE neutral
                with mock.patch.object(
                    wizard,
                    "detect_client_context",
                    return_value={
                        "detected_client": "unknown",
                        "detection_basis": [],
                        "client_context_confidence": "low",
                    },
                ):
                    plan_manual = wizard.build_uninstall_plan(
                        mode="full-reset-current-user",
                        project_roots=[],
                        client=None,
                    )
                    helper_removals_manual = plan_manual["preflight_review"]["helper_installs_to_remove"]
                    self.assertIn(str(neutral_tools), helper_removals_manual)

    def test_uninstall_apply_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.xuunity.light-mcp": "git-url"},
            )
            plan = wizard.build_uninstall_plan(
                mode="project-only-cleanup",
                project_roots=[str(project_root)],
            )

            with self.assertRaises(wizard.ToolInvocationError) as cm:
                wizard.apply_uninstall_plan(plan, approve=False)

        self.assertEqual("approval_required", cm.exception.code)

    def test_install_test_framework_rejects_explicit_version_below_capability_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(Path(tmp) / "Project", unity_version="2021.3.45f1")
            with self.assertRaises(wizard.ToolInvocationError) as cm:
                wizard.install_test_framework(project_root, approve=True, version="1.0.0")

        self.assertEqual("dependency_version_too_old", cm.exception.code)
        self.assertEqual("1.1.33", cm.exception.details["minimum_dependency_version"])

    def test_existing_suitable_test_framework_does_not_plan_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.unity.test-framework": "1.1.33"},
            )
            plan = wizard.build_setup_plan(
                workspace_root=None,
                project_roots=[str(project_root)],
                recursive=False,
                include_test_framework="yes",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

        project = plan["projects"][0]
        self.assertEqual("supported", project["test_framework_state"]["status"])
        self.assertFalse(project["test_framework_state"]["upgrade_recommended"])
        self.assertFalse(
            any(action["kind"].endswith("test_framework_dependency") for action in project["planned_actions"])
        )

    def test_auto_plan_proposes_cautious_upgrade_for_old_existing_test_framework(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="2021.3.45f1",
                dependencies={"com.unity.test-framework": "1.0.0"},
            )
            plan = wizard.build_setup_plan(
                workspace_root=None,
                project_roots=[str(project_root)],
                recursive=False,
                include_test_framework="auto",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

        state = plan["projects"][0]["test_framework_state"]
        actions = [
            action
            for action in plan["projects"][0]["planned_actions"]
            if action["kind"] == "upgrade_test_framework_dependency"
        ]
        self.assertEqual("disabled_dependency_too_old", state["status"])
        self.assertEqual("upgrade_required", state["dependency_action"])
        self.assertEqual(1, len(actions))
        self.assertEqual("1.0.0", actions[0]["current_version"])
        self.assertEqual("1.1.33", actions[0]["version"])
        self.assertIn("already declares Test Framework", actions[0]["caution"])

    def test_auto_plan_keeps_supported_test_framework_and_suggests_optional_unity_6000_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="6000.0.45f1",
                dependencies={
                    "com.xuunity.light-mcp": "git-url",
                    "com.unity.test-framework": "1.1.33",
                },
            )
            wizard.write_bridge_config(project_root)
            plan = wizard.build_setup_plan(
                workspace_root=None,
                project_roots=[str(project_root)],
                recursive=False,
                include_test_framework="auto",
                package_source="git",
                package_version="0.3.14",
                local_package_source="/tmp/light-mcp",
            )

        project = plan["projects"][0]
        self.assertEqual("supported", project["test_framework_state"]["status"])
        self.assertTrue(project["test_framework_state"]["upgrade_recommended"])
        self.assertEqual("manual_action_recommended", project["validation_status"])
        self.assertFalse(
            any(action["kind"] == "upgrade_test_framework_dependency" for action in project["planned_actions"])
        )
        manual_upgrades = [action for action in project["manual_actions"] if action["kind"] == "optional_test_framework_upgrade"]
        self.assertEqual(1, len(manual_upgrades))
        self.assertEqual("1.1.33", manual_upgrades[0]["current_version"])
        self.assertEqual("1.5.1", manual_upgrades[0]["recommended_version"])

    def test_install_test_framework_reports_already_suitable_without_manifest_churn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.unity.test-framework": "1.1.33"},
            )
            result = wizard.install_test_framework(project_root, approve=True)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("already_suitable", result["outcome"])
        self.assertEqual("1.1.33", manifest["dependencies"]["com.unity.test-framework"])
        self.assertEqual("offline_manifest", result["mutation_mode"])
        self.assertIn("ensure-ready --open-editor", result["next_action"])

    def test_install_test_framework_preserves_newer_existing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="6000.0.45f1",
                dependencies={"com.unity.test-framework": "1.6.0"},
            )
            result = wizard.install_test_framework(project_root, approve=True)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("already_suitable", result["outcome"])
        self.assertFalse(result["upgrade_recommended"])
        self.assertEqual("1.6.0", manifest["dependencies"]["com.unity.test-framework"])

    def test_install_test_framework_upgrades_existing_old_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="6000.0.45f1",
                dependencies={"com.unity.test-framework": "1.1.33"},
            )
            result = wizard.install_test_framework(project_root, approve=True)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("upgraded", result["outcome"])
        self.assertTrue(result["upgrade_recommended_before"])
        self.assertEqual("1.5.1", manifest["dependencies"]["com.unity.test-framework"])
        self.assertEqual("offline_manifest", result["mutation_mode"])
        self.assertEqual("before_opening_unity", result["apply_phase"])

    def test_validate_include_tests_blocks_missing_optional_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(
                Path(tmp) / "Project",
                unity_version="2022.3.60f1",
                dependencies={"com.xuunity.light-mcp": "git-url"},
            )
            wizard.write_bridge_config(project_root)
            result = wizard.validate_setup(project_root, include_tests=True)

        self.assertEqual("blocked", result["validation_status"])
        self.assertEqual("blocked", result["offline_validation_status"])
        self.assertEqual("offline_manifest_and_bridge_config_only", result["readiness_scope"])
        self.assertEqual("declared_not_resolved", result["package_import_state"]["import_state"])
        self.assertIn("test_framework_unavailable", result["blockers"])
        self.assertEqual("disabled_missing_dependency", result["test_capabilities_state"])
        self.assertEqual("1.1.33", result["test_framework_state"]["recommended_dependency_version"])

    def test_batch_editmode_preflight_reports_actionable_optional_dependency_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = create_unity_project(Path(tmp) / "Project", unity_version="6000.0.45f1")

            with self.assertRaises(server.ToolInvocationError) as cm:
                server.require_test_framework_capability_for_batch(project_root)

        self.assertEqual("test_capability_unavailable", cm.exception.code)
        self.assertEqual("disabled_missing_dependency", cm.exception.details["capability_status"])
        self.assertEqual("1.5.1", cm.exception.details["recommended_dependency_version"])
        self.assertIn("install-test-framework", cm.exception.details["install_command"])


if __name__ == "__main__":
    unittest.main()
