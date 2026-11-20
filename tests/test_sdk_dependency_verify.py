import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_core
import server_sdk_dependency_verify

RESOLVER_XML = """<dependencies>
  <packages>
    <package>com.example.ads:ads-sdk:13.0.1</package>
    <package>com.example.mediation:adapter:[8.2.0.1]</package>
  </packages>
</dependencies>
"""
GRADLE = """dependencies {
    implementation 'com.example.ads:ads-sdk:13.0.1' // Assets/Ads/Editor/Dependencies.xml:4
    implementation "com.example.net:http:4.12.0@aar"
}
repositories { maven { url "https://maven.example.test/releases" } }
"""
PODFILE_LOCK = """PODS:
  - ExampleAds (13.0.1)
  - ExampleCore (= 2.4.0)
"""


class SdkDependencyVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        (self.root / "ProjectSettings").mkdir()
        (self.root / "Assets/Plugins/Android").mkdir(parents=True)
        (self.root / "ProjectSettings/AndroidResolverDependencies.xml").write_text(RESOLVER_XML, encoding="utf-8")
        (self.root / "Assets/Plugins/Android/mainTemplate.gradle").write_text(GRADLE, encoding="utf-8")
        (self.root / "Podfile.lock").write_text(PODFILE_LOCK, encoding="utf-8")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _one(self, **expectation) -> dict:
        payload = server_sdk_dependency_verify.run_sdk_dependency_verify(
            project_root=self.root, config={"expectations": [expectation]}
        )
        return payload["results"][0]

    def test_coordinate_kinds_return_the_parsed_version(self) -> None:
        resolver = self._one(
            path="ProjectSettings/AndroidResolverDependencies.xml",
            kind="android_resolver_package",
            value="com.example.ads:ads-sdk:13.0.1",
        )
        self.assertEqual(("passed", "13.0.1"), (resolver["status"], resolver["actual_version"]))
        bracketed = self._one(
            path="ProjectSettings/AndroidResolverDependencies.xml",
            kind="android_resolver_package",
            value="com.example.mediation:adapter",
            version="8.2.0.1",
        )
        self.assertEqual(("passed", "8.2.0.1"), (bracketed["status"], bracketed["actual_version"]))
        gradle = self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle",
            kind="gradle_dependency",
            value="com.example.net:http",
        )
        self.assertEqual(("passed", "4.12.0"), (gradle["status"], gradle["actual_version"]))

    def test_a_longer_version_no_longer_passes_as_a_substring(self) -> None:
        for path, kind in (
            ("ProjectSettings/AndroidResolverDependencies.xml", "android_resolver_package"),
            ("Assets/Plugins/Android/mainTemplate.gradle", "gradle_dependency"),
        ):
            with self.subTest(kind=kind):
                result = self._one(path=path, kind=kind, value="com.example.ads:ads-sdk:13.0")
                self.assertEqual("failed", result["status"])
                self.assertEqual("13.0.1", result["actual_version"])
                self.assertIn("version mismatch", result["message"])

    def test_min_version_and_missing_coordinate(self) -> None:
        low = self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle",
            kind="gradle_dependency",
            value="com.example.ads:ads-sdk",
            minVersion="13.1.0",
        )
        self.assertEqual("failed", low["status"])
        self.assertIn("lower than minimum", low["message"])
        ok = self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle",
            kind="gradle_dependency",
            value="com.example.ads:ads-sdk",
            minVersion="12.9",
        )
        self.assertEqual("passed", ok["status"])
        missing = self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle",
            kind="gradle_dependency",
            value="com.example.absent:lib:1.0.0",
        )
        self.assertEqual(("failed", ""), (missing["status"], missing["actual_version"]))

    def test_non_coordinate_values_keep_the_contains_check(self) -> None:
        result = self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle",
            kind="gradle_dependency",
            value="implementation 'com.example.ads:ads-sdk:13.0.1'",
        )
        self.assertEqual("passed", result["status"])

    def test_text_kinds_pod_lock_and_optional_files(self) -> None:
        self.assertEqual("passed", self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle", kind="gradle_repository",
            value="https://maven.example.test/releases")["status"])
        self.assertEqual("passed", self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle", kind="file_regex",
            value=r"^\s+implementation 'com\.example\.ads")["status"])
        self.assertEqual("failed", self._one(
            path="Assets/Plugins/Android/mainTemplate.gradle", kind="file_regex", value="(")["status"])
        pod = self._one(path="Podfile.lock", kind="podfile_lock_pod", value="ExampleCore", version="2.4.0")
        self.assertEqual(("passed", "2.4.0"), (pod["status"], pod["actual_version"]))
        self.assertEqual("failed", self._one(
            path="Podfile.lock", kind="podfile_lock_pod", value="ExampleAds", version="13.0.2")["status"])
        self.assertEqual("skipped", self._one(
            path="Missing.lock", kind="file_contains", value="x", optional=True)["status"])
        self.assertEqual("failed", self._one(path="Missing.lock", kind="file_contains", value="x")["status"])
        self.assertEqual("failed", self._one(path="Podfile.lock", kind="nonsense", value="x")["status"])

    def test_paths_outside_the_project_are_refused(self) -> None:
        outside = self._one(path="../outside.txt", kind="file_contains", value="x")
        self.assertEqual("failed", outside["status"])
        self.assertIn("inside the Unity project root", outside["message"])

    def test_payload_counts_and_stop_on_first_failure(self) -> None:
        config = {
            "stopOnFirstFailure": True,
            "expectations": [
                {"path": "Podfile.lock", "kind": "file_contains", "value": "ExampleAds"},
                {"path": "Podfile.lock", "kind": "file_contains", "value": "absent"},
                {"path": "Podfile.lock", "kind": "file_contains", "value": "ExampleCore"},
            ],
        }
        payload = server_sdk_dependency_verify.run_sdk_dependency_verify(project_root=self.root, config=config)
        self.assertEqual(("failed", 2, 1, 1), (payload["status"], payload["total"], payload["passed"], payload["failed"]))
        self.assertEqual("host_file_read", payload["validation_evidence"])
        self.assertIs(False, payload["editor_required"])
        self.assertEqual(64, len(payload["results"][0]["sha256"]))
        with self.assertRaises(server_core.ToolInvocationError):
            server_sdk_dependency_verify.run_sdk_dependency_verify(project_root=self.root, config={})


class SdkDependencyVerifyToolTests(unittest.TestCase):
    def test_mcp_tool_never_touches_the_bridge_or_an_editor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "Podfile.lock").write_text(PODFILE_LOCK, encoding="utf-8")
            arguments = {
                "projectRoot": str(root),
                "expectations": [{"path": "Podfile.lock", "kind": "podfile_lock_pod", "value": "ExampleAds"}],
            }
            with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=root), \
                    mock.patch.object(server_batch_orchestrator, "invoke_bridge") as invoke_bridge:
                result = server_batch_orchestrator.call_tool("unity_sdk_dependency_verify", arguments)
            invoke_bridge.assert_not_called()
            payload = json.loads(result["content"][0]["text"])
            self.assertEqual("passed", payload["status"])
            self.assertEqual("13.0.1", payload["results"][0]["actual_version"])
            self.assertLess(len(result["content"][0]["text"]), 1500)
            self.assertFalse(result.get("isError", False))

            arguments["expectations"][0]["version"] = "14.0.0"
            with mock.patch.object(server_batch_orchestrator, "ensure_project_root", return_value=root):
                failed = server_batch_orchestrator.call_tool("unity_sdk_dependency_verify", arguments)
            self.assertTrue(failed.get("isError"))


if __name__ == "__main__":
    unittest.main()
