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
release_docs_freshness = load_module(
    "check_release_docs_freshness",
    REPO_ROOT / "scripts" / "testing" / "check_release_docs_freshness.py",
)
public_release_safety = load_module(
    "check_public_release_safety",
    REPO_ROOT / "scripts" / "testing" / "check_public_release_safety.py",
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
        write_json(root / "package.json", {"name": "xuunity-mcp-site-checks", "version": "0.3.16"})
        write_json(
            root / "package-lock.json",
            {
                "name": "xuunity-mcp-site-checks",
                "version": "0.3.16",
                "lockfileVersion": 3,
                "packages": {"": {"name": "xuunity-mcp-site-checks", "version": "0.3.16"}},
            },
        )
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

    def create_minimal_fresh_docs_tree(self, root: Path, version: str = "0.3.16") -> None:
        write_json(root / "packages" / "com.xuunity.light-mcp" / "package.json", {"version": version})
        for relative_path in release_docs_freshness.PUBLIC_DOCS:
            markers = release_docs_freshness.REQUIRED_MARKERS.get(relative_path, ())
            lines = [marker.format(version=version) for marker in markers]
            write_text(root / relative_path, "\n".join(lines) + "\n")

    def test_sync_release_version_updates_current_refs_without_rewriting_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)

            changed = sync_release_version.sync_release_version(root, "0.3.17")

            self.assertIn(Path("package.json"), changed)
            self.assertIn(Path("package-lock.json"), changed)
            self.assertIn(Path("packages/com.xuunity.light-mcp/package.json"), changed)
            self.assertIn(Path("templates/server.py"), changed)
            self.assertIn(Path("templates/server_batch_orchestrator.py"), changed)
            self.assertEqual(
                "0.3.17",
                json.loads((root / "package.json").read_text())["version"],
            )
            package_lock = json.loads((root / "package-lock.json").read_text())
            self.assertEqual("0.3.17", package_lock["version"])
            self.assertEqual("0.3.17", package_lock["packages"][""]["version"])
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

    def test_release_docs_freshness_passes_for_repo(self) -> None:
        errors = release_docs_freshness.check_release_docs_freshness(REPO_ROOT)
        self.assertEqual([], errors)

    def test_public_release_safety_passes_for_repo(self) -> None:
        errors = public_release_safety.check_public_release_safety(REPO_ROOT)
        self.assertEqual([], errors)

    def test_public_release_safety_detects_host_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "CHANGELOG.md", "Validated from /Users/privateuser/Projects/SecretProject.\n")

            errors = public_release_safety.check_public_release_safety(root)

            self.assertTrue(any("host_home_path" in error for error in errors), errors)

    def test_public_release_safety_detects_windows_worktree_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "CHANGELOG.md", "Validated from D:\\Development\\Unity\\PrivateProject.\n")

            errors = public_release_safety.check_public_release_safety(root)

            self.assertTrue(any("windows_work_tree_path" in error for error in errors), errors)

    def test_public_release_safety_detects_local_denylist_token_without_committing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            denylist_path = root / "denylist.txt"
            write_text(denylist_path, "PrivateProjectName\n")
            write_text(root / "CHANGELOG.md", "Validation passed on PrivateProjectName.\n")

            errors = public_release_safety.check_public_release_safety(root, [denylist_path])

            self.assertTrue(any("local_denylist_token" in error for error in errors), errors)

    def test_release_docs_freshness_detects_stale_prepared_tag_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_fresh_docs_tree(root)
            status_path = root / "docs" / "reference" / "STATUS.md"
            with status_path.open("a", encoding="utf-8") as handle:
                handle.write("Release tag `v0.3.16` is prepared locally.\n")

            errors = release_docs_freshness.check_release_docs_freshness(root)

            self.assertTrue(any("prepared" in error for error in errors), errors)

    def test_release_docs_freshness_detects_missing_feature_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_fresh_docs_tree(root)
            features_path = root / "docs" / "reference" / "FEATURES.md"
            text = features_path.read_text(encoding="utf-8")
            features_path.write_text(text.replace("payload_mode=compact_decision\n", ""), encoding="utf-8")

            errors = release_docs_freshness.check_release_docs_freshness(root)

            self.assertTrue(any("payload_mode=compact_decision" in error for error in errors), errors)

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

    def test_release_version_consistency_detects_a_stale_claim_no_pattern_covers(self) -> None:
        """The public site said "set up release v0.3.45" for ten releases.

        Neither tool saw it: the checker matched a whitelist of phrasings, and the sync tool only rewrote the
        immediately previous version, so a claim worded differently — or already more than one release behind —
        was permanently invisible. The sweep must fail on any release-facing version that is not the current one,
        whatever the wording.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            index = root / "docs" / "index.html"
            index.write_text(
                "<p>Set up XUUnity Light Unity MCP release <code>v0.3.45</code> from the canonical repo.</p>\n",
                encoding="utf-8",
            )

            errors = release_consistency.check_release_version_consistency(root)

            self.assertTrue(
                any("v0.3.45" in error and "docs/index.html" in error.replace("\\", "/") for error in errors),
                errors,
            )

    def test_the_sweep_leaves_since_version_and_measured_claims_alone(self) -> None:
        """`vX.Y.Z+` means "since this version", and a version paired with a measured result is evidence.

        Bumping either would be wrong: the first is a lower bound, and the second would replace a stale truth with
        a fresh lie about a measurement nobody re-ran.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            status = root / "docs" / "reference" / "STATUS.md"
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text("- `v0.3.29+` adds hook scenarios\n", encoding="utf-8")

            errors = release_consistency.check_release_version_consistency(root)

            self.assertFalse([error for error in errors if "v0.3.29" in error], errors)

    def test_a_measured_evidence_row_keeps_the_release_that_measured_it(self) -> None:
        """A row naming a measurement must keep its own release label through later sweeps.

        This exact row was relabelled twice - v0.3.70 evidence published first as v0.3.71 and then as v0.3.72 -
        because it was not registered as history. The sweep must leave it, and the gate must accept it.
        """

        row = (
            "| `v0.3.70` compile-warning evidence (historical, not re-measured since) | "
            "`host validated` | Full host `1011/1011` with 14 expected platform skips. |\n"
        )

        import sys as _sys

        tools_dir = REPO_ROOT / "scripts" / "tools"
        if str(tools_dir) not in _sys.path:
            _sys.path.insert(0, str(tools_dir))
        import sync_release_version as sync

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_release_tree(root)
            status = root / "docs" / "reference" / "STATUS.md"
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text(row, encoding="utf-8")

            swept = sync.sweep_release_doc_versions(
                Path("docs") / "reference" / "STATUS.md", row, "0.3.72"
            )
            self.assertEqual(row, swept)

            errors = release_consistency.check_release_version_consistency(root)
            self.assertFalse([error for error in errors if "v0.3.70" in error], errors)

    def test_explicit_historical_evidence_marker_prevents_release_relabelling(self) -> None:
        """New measured claims can opt out without growing a path-and-phrase allowlist."""

        import sys as _sys

        tools_dir = REPO_ROOT / "scripts" / "tools"
        if str(tools_dir) not in _sys.path:
            _sys.path.insert(0, str(tools_dir))
        import sync_release_version as sync

        claims = (
            (
                Path("docs/reference/STATUS.md"),
                "| `v0.3.73` rebuilt/cache evidence | `161/161` passed. | "
                "<!-- release-version: historical -->\n",
            ),
            (
                Path("docs/architecture/ROADMAP.md"),
                "- `v0.3.67` fixed compact batch verdicts. "
                "<!-- release-version: historical -->\n",
            ),
        )

        for relative_path, line in claims:
            with self.subTest(relative_path=relative_path):
                swept = sync.sweep_release_doc_versions(relative_path, line, "0.3.75")
                self.assertEqual(line, swept)
                self.assertTrue(sync.line_records_history(relative_path, line))
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.create_minimal_release_tree(root)
                    target = root / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(line, encoding="utf-8")
                    errors = release_consistency.release_doc_version_sweep(root)
                    self.assertFalse(
                        [error for error in errors if relative_path.as_posix() in error.replace("\\", "/")],
                        errors,
                    )

    def test_unmarked_historical_looking_claim_still_follows_current_release(self) -> None:
        """The escape hatch is explicit; ordinary release-facing claims still advance."""

        import sys as _sys

        tools_dir = REPO_ROOT / "scripts" / "tools"
        if str(tools_dir) not in _sys.path:
            _sys.path.insert(0, str(tools_dir))
        import sync_release_version as sync

        line = "- Release `v0.3.74` adds a capability.\n"
        swept = sync.sweep_release_doc_versions(Path("docs/reference/STATUS.md"), line, "0.3.75")

        self.assertEqual("- Release `v0.3.75` adds a capability.\n", swept)

    def test_warning_release_claims_are_not_relabelled_by_future_sweeps(self) -> None:
        import sys as _sys

        tools_dir = REPO_ROOT / "scripts" / "tools"
        if str(tools_dir) not in _sys.path:
            _sys.path.insert(0, str(tools_dir))
        import sync_release_version as sync

        claims = (
            (Path("README.md"), "The `v0.3.70` compile summaries retain warning evidence end to end:\n"),
            (
                Path("docs/architecture/ROADMAP.md"),
                "- `v0.3.70` compiler-warning evidence across direct, matrix, batch, and\n",
            ),
            (
                Path("docs/operations/SMOKE_TESTS.md"),
                "- The `v0.3.70` compile summaries also expose `warning_count`,\n",
            ),
            (
                Path("docs/reference/FEATURES.md"),
                "| Compile | current source plus `v0.3.70` warning occurrence/unique counts |\n",
            ),
            (
                Path("docs/reference/FEATURES.md"),
                "| Compile | current source plus `v0.3.70` aggregated warning evidence |\n",
            ),
        )

        for relative_path, line in claims:
            with self.subTest(relative_path=relative_path, line=line):
                swept = sync.sweep_release_doc_versions(relative_path, line, "0.3.73")
                self.assertEqual(line, swept)

    def test_the_sweep_never_rewrites_a_unity_editor_version(self) -> None:
        """Unity's own `6000.0.58f2` contains `0.0.58`. An unanchored sweep rewrote it to `6000.3.55f2`."""

        import sys as _sys

        tools_dir = REPO_ROOT / "scripts" / "tools"
        if str(tools_dir) not in _sys.path:
            _sys.path.insert(0, str(tools_dir))
        import sync_release_version as sync

        line = "Unity `2022.3.62f3` and `6000.0.58f2` each pass EditMode `62/62`.\n"
        swept = sync.sweep_release_doc_versions(Path("docs/reference/STATUS.md"), line, "0.3.55")

        self.assertEqual(line, swept, "editor versions must survive the sweep untouched")

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
