import json
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
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
