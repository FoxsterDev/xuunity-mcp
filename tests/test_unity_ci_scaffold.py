from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_TESTING_DIR = REPO_ROOT / "scripts" / "testing"
if str(SCRIPTS_TESTING_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_TESTING_DIR))

import scaffold_unity_ci_project as scaffold


class BuildManifestPayloadTests(unittest.TestCase):
    def test_ugui_lane_on_2022_installs_ugui_and_textmeshpro(self) -> None:
        payload = scaffold.build_manifest_payload("2022.3.62f1", "ugui", "file:../../packages/com.xuunity.light-mcp")

        self.assertEqual(payload["dependencies"]["com.unity.ugui"], "1.0.0")
        self.assertEqual(payload["dependencies"]["com.unity.textmeshpro"], "3.0.6")
        self.assertEqual(payload["dependencies"]["com.unity.test-framework"], "1.1.33")

    def test_ugui_lane_on_6000_installs_ugui_2_without_separate_textmeshpro(self) -> None:
        payload = scaffold.build_manifest_payload("6000.0.58f2", "ugui", "file:pkg")

        self.assertEqual(payload["dependencies"]["com.unity.ugui"], "2.0.0")
        self.assertNotIn("com.unity.textmeshpro", payload["dependencies"])
        self.assertEqual(payload["dependencies"]["com.unity.test-framework"], "1.5.1")

    def test_no_ugui_lane_never_installs_ugui_or_textmeshpro(self) -> None:
        for unity_version in ("2022.3.62f1", "6000.0.58f2"):
            payload = scaffold.build_manifest_payload(unity_version, "no-ugui", "file:pkg")

            self.assertNotIn("com.unity.ugui", payload["dependencies"])
            self.assertNotIn("com.unity.textmeshpro", payload["dependencies"])
            self.assertIn("com.unity.test-framework", payload["dependencies"])

    def test_package_is_always_a_dependency_and_testable(self) -> None:
        payload = scaffold.build_manifest_payload("2022.3.62f1", "no-ugui", "file:../../packages/com.xuunity.light-mcp")

        self.assertEqual(payload["dependencies"]["com.xuunity.light-mcp"], "file:../../packages/com.xuunity.light-mcp")
        self.assertEqual(payload["testables"], ["com.xuunity.light-mcp"])

    def test_test_framework_pin_matches_the_canonical_setup_policy(self) -> None:
        templates_dir = REPO_ROOT / "templates"
        if str(templates_dir) not in sys.path:
            sys.path.insert(0, str(templates_dir))
        from server_setup_common import recommended_test_framework_version

        for unity_version in ("2021.3.45f1", "2022.3.62f1", "6000.0.58f2"):
            payload = scaffold.build_manifest_payload(unity_version, "no-ugui", "file:pkg")
            self.assertEqual(
                payload["dependencies"]["com.unity.test-framework"],
                recommended_test_framework_version(unity_version),
            )

    def test_unknown_lane_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scaffold.build_manifest_payload("2022.3.62f1", "webgl", "file:pkg")


class PackageDependencyValueTests(unittest.TestCase):
    def test_windows_paths_render_posix_separators_only(self) -> None:
        value = scaffold.package_dependency_value(
            PureWindowsPath("C:/repo/packages/com.xuunity.light-mcp"),
            PureWindowsPath("C:/repo/CiProject/Packages"),
        )

        self.assertNotIn("\\", value)
        self.assertTrue(value.startswith("file:"))
        self.assertIn("packages/com.xuunity.light-mcp", value)

    def test_cross_drive_windows_paths_fall_back_to_absolute_posix(self) -> None:
        value = scaffold.package_dependency_value(
            PureWindowsPath("D:/repo/packages/com.xuunity.light-mcp"),
            PureWindowsPath("C:/work/CiProject/Packages"),
        )

        self.assertNotIn("\\", value)
        self.assertEqual(value, "file:D:/repo/packages/com.xuunity.light-mcp")

    def test_relative_value_points_from_packages_dir_to_package(self) -> None:
        value = scaffold.package_dependency_value(
            Path("/repo/packages/com.xuunity.light-mcp"),
            Path("/repo/CiProject/Packages"),
        )

        self.assertEqual(value, "file:../../packages/com.xuunity.light-mcp")


class ScaffoldProjectTests(unittest.TestCase):
    def test_scaffold_writes_manifest_and_project_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "CiProject"
            summary = scaffold.scaffold_project(
                project_root=project_root,
                unity_version="6000.0.58f2",
                lane="ugui",
                package_dir=REPO_ROOT / "packages" / "com.xuunity.light-mcp",
                force=False,
            )

            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["testables"], ["com.xuunity.light-mcp"])
            self.assertTrue(manifest["dependencies"]["com.xuunity.light-mcp"].startswith("file:"))
            self.assertNotIn("\\", manifest["dependencies"]["com.xuunity.light-mcp"])

            project_version = (project_root / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8")
            self.assertEqual(project_version, "m_EditorVersion: 6000.0.58f2\n")
            self.assertTrue((project_root / "Assets").is_dir())
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["lane"], "ugui")

    def test_scaffold_refuses_nonempty_project_root_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "CiProject"
            project_root.mkdir()
            (project_root / "keep.txt").write_text("existing", encoding="utf-8")

            with self.assertRaises(SystemExit):
                scaffold.scaffold_project(
                    project_root=project_root,
                    unity_version="2022.3.62f1",
                    lane="no-ugui",
                    package_dir=REPO_ROOT / "packages" / "com.xuunity.light-mcp",
                    force=False,
                )

            summary = scaffold.scaffold_project(
                project_root=project_root,
                unity_version="2022.3.62f1",
                lane="no-ugui",
                package_dir=REPO_ROOT / "packages" / "com.xuunity.light-mcp",
                force=True,
            )
            self.assertEqual(summary["status"], "ok")
            self.assertEqual((project_root / "keep.txt").read_text(encoding="utf-8"), "existing")

    def test_main_rejects_a_package_dir_without_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as raised:
                scaffold.main(
                    [
                        "--project-root",
                        str(Path(tmp) / "CiProject"),
                        "--unity-version",
                        "2022.3.62f1",
                        "--lane",
                        "no-ugui",
                        "--package-dir",
                        tmp,
                    ]
                )
            self.assertEqual(raised.exception.code, 2)



class AddUguiToExistingProjectTests(unittest.TestCase):
    def write_manifest(self, root: Path, dependencies: dict) -> Path:
        manifest_path = root / "Packages" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({"dependencies": dependencies, "scopedRegistries": []}), encoding="utf-8")
        return manifest_path

    def test_a_6000_created_project_gains_ugui_and_keeps_everything_else(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = self.write_manifest(Path(tmp), {"com.unity.modules.ui": "1.0.0"})

            added = scaffold.add_ugui_lane_dependencies(manifest_path, "6000.5.10f1")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(["com.unity.ugui"], added)
            self.assertEqual({"com.unity.modules.ui": "1.0.0", "com.unity.ugui": "2.0.0"}, manifest["dependencies"])
            self.assertEqual([], manifest["scopedRegistries"])

    def test_existing_ugui_and_textmeshpro_versions_are_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = self.write_manifest(
                Path(tmp), {"com.unity.ugui": "1.0.0", "com.unity.textmeshpro": "3.0.7"}
            )
            before = manifest_path.read_bytes()

            self.assertEqual([], scaffold.add_ugui_lane_dependencies(manifest_path, "2021.3.58f1"))
            self.assertEqual(before, manifest_path.read_bytes())

    def test_cli_needs_an_existing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            scaffold.main(["--project-root", tmp, "--unity-version", "6000.0.58f2", "--add-ugui-to-existing"])

    def test_cli_still_requires_a_lane_for_a_new_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            scaffold.main(["--project-root", tmp, "--unity-version", "6000.0.58f2"])

if __name__ == "__main__":
    unittest.main()
