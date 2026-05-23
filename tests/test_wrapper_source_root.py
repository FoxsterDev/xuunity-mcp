import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class WrapperSourceRootTests(unittest.TestCase):
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

            env = dict(os.environ)
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


if __name__ == "__main__":
    unittest.main()
