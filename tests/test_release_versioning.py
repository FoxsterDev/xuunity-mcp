import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


sync_release_version = load_module(
    "sync_release_version",
    REPO_ROOT / "scripts" / "tools" / "sync_release_version.py",
)
release_consistency = load_module(
    "check_release_version_consistency",
    REPO_ROOT / "scripts" / "testing" / "check_release_version_consistency.py",
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReleaseVersioningTests(unittest.TestCase):
    def create_minimal_release_tree(self, root: Path) -> None:
        package_payload = {
            "name": "com.xuunity.light-mcp",
            "displayName": "XUUnity Light Unity MCP",
            "version": "0.3.16",
            "unity": "2021.3",
        }
        write_json(root / "packages" / "com.xuunity.light-mcp" / "package.json", package_payload)
        write_json(root / "templates" / "package-manifests" / "unity-package-2021_2022.json", package_payload)
        unity_6000_payload = dict(package_payload)
        unity_6000_payload["unity"] = "6000.0"
        write_json(root / "templates" / "package-manifests" / "unity-package-6000.json", unity_6000_payload)
        write_text(
            root / "templates" / "server.py",
            'SERVER_INFO = {\n    "name": "xuunity-mcp",\n    "version": "0.3.16",\n}\n',
        )
        write_text(
            root / "templates" / "server_batch_orchestrator.py",
            'SERVER_INFO = {\n    "name": "xuunity-mcp",\n    "version": "0.3.16",\n}\n',
        )
        write_text(
            root / "README.md",
            "\n".join(
                [
                    "Status: `current for v0.3.16`",
                    "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16",
                    "Historical migration uses `templates/unity-package#v0.3.11`.",
                    "",
                ]
            ),
        )
        write_text(
            root / "docs" / "index.html",
            "\n".join(
                [
                    '<script type="application/ld+json">',
                    '{"softwareVersion": "v0.3.16"}',
                    "</script>",
                    "",
                ]
            ),
        )
        write_text(
            root / "docs" / "install.html",
            "\n".join(
                [
                    "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16",
                    "",
                ]
            ),
        )
        write_text(
            root / "docs" / "reference" / "LISTING_KIT.md",
            "\n".join(
                [
                    "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16",
                    "",
                ]
            ),
        )
        write_text(
            root / "docs" / "reference" / "STATUS.md",
            "\n".join(
                [
                    "The current source line is `v0.3.16`.",
                    "- `v0.3.15+` adds license-aware batch fallback.",
                    "Latest source validation for `v0.3.16`:",
                    "| Package metadata | `packages/com.xuunity.light-mcp/package.json` | `name=com.xuunity.light-mcp`, `version=0.3.16`, `unity=2021.3` |",
                    "| Git tag visibility | Git refs | Release tag `v0.3.16` is prepared locally. |",
                    "",
                ]
            ),
        )
        write_text(
            root / "CHANGELOG.md",
            "\n".join(
                [
                    "# Changelog",
                    "",
                    "## Unreleased",
                    "",
                    "## 0.3.16",
                    "",
                    "Release tag: `v0.3.16`",
                    "",
                    "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16",
                    "",
                    "## 0.3.15",
                    "",
                    "Release tag: `v0.3.15`",
                    "",
                    "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.15",
                    "",
                ]
            ),
        )

    def test_sync_release_version_updates_current_refs_without_rewriting_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)

            changed = sync_release_version.sync_release_version(root, "0.3.17")

            self.assertIn(Path("packages/com.xuunity.light-mcp/package.json"), changed)
            self.assertIn(Path("templates/server.py"), changed)
            self.assertIn(Path("templates/server_batch_orchestrator.py"), changed)
            self.assertEqual(
                "0.3.17",
                json.loads((root / "packages" / "com.xuunity.light-mcp" / "package.json").read_text())["version"],
            )
            self.assertIn('"version": "0.3.17"', (root / "templates" / "server.py").read_text(encoding="utf-8"))
            self.assertIn(
                '"version": "0.3.17"',
                (root / "templates" / "server_batch_orchestrator.py").read_text(encoding="utf-8"),
            )

            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Status: `current for v0.3.17`", readme)
            self.assertIn("#v0.3.17", readme)
            self.assertIn("templates/unity-package#v0.3.11", readme)

            index = (root / "docs" / "index.html").read_text(encoding="utf-8")
            self.assertIn('"softwareVersion": "v0.3.17"', index)

            install = (root / "docs" / "install.html").read_text(encoding="utf-8")
            self.assertIn("#v0.3.17", install)

            listing_kit = (root / "docs" / "reference" / "LISTING_KIT.md").read_text(encoding="utf-8")
            self.assertIn("#v0.3.17", listing_kit)

            status = (root / "docs" / "reference" / "STATUS.md").read_text(encoding="utf-8")
            self.assertIn("current source line is `v0.3.17`", status)
            self.assertIn("Latest source validation for `v0.3.17`", status)
            self.assertIn("version=0.3.17", status)
            self.assertIn("Release tag `v0.3.17` is prepared", status)
            self.assertIn("`v0.3.15+` adds license-aware batch fallback", status)

            changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## 0.3.17", changelog)
            self.assertIn("Release tag: `v0.3.17`", changelog)
            self.assertIn("## 0.3.16", changelog)
            self.assertIn("Release tag: `v0.3.16`", changelog)
            self.assertIn("#v0.3.16", changelog)
            self.assertIn("## 0.3.15", changelog)
            self.assertIn("Release tag: `v0.3.15`", changelog)
            self.assertIn("#v0.3.15", changelog)

    def test_release_version_consistency_passes_for_repo(self) -> None:
        errors = release_consistency.check_release_version_consistency(REPO_ROOT)
        self.assertEqual([], errors)

    def test_release_version_consistency_detects_stale_current_doc_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            text = (root / "README.md").read_text(encoding="utf-8")
            (root / "README.md").write_text(text.replace("current for v0.3.16", "current for v0.3.15"), encoding="utf-8")

            errors = release_consistency.check_release_version_consistency(root)

            self.assertTrue(any("README.md:1" in error for error in errors), errors)

    def test_release_version_consistency_detects_stale_site_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            (root / "docs" / "index.html").write_text(
                '{"softwareVersion": "v0.3.15"}\n',
                encoding="utf-8",
            )

            errors = release_consistency.check_release_version_consistency(root)

            self.assertTrue(any("docs/index.html:1" in error.replace("\\", "/") for error in errors), errors)

    def test_release_version_consistency_detects_stale_orchestrator_server_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            text = (root / "templates" / "server_batch_orchestrator.py").read_text(encoding="utf-8")
            (root / "templates" / "server_batch_orchestrator.py").write_text(
                text.replace('"version": "0.3.16"', '"version": "0.3.15"'),
                encoding="utf-8",
            )

            errors = release_consistency.check_release_version_consistency(root)

            self.assertTrue(
                any("templates/server_batch_orchestrator.py" in error.replace("\\", "/") for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
