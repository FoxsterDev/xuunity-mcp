import json
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_test_reporting


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_project(root: Path, name: str = "Project") -> Path:
    project_root = root / name
    (project_root / "Packages").mkdir(parents=True)
    (project_root / "ProjectSettings").mkdir(parents=True)
    (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 6000.0.58f2\n",
        encoding="utf-8",
    )
    return project_root


class TestReportingTests(unittest.TestCase):
    def test_latest_result_selection_uses_top_level_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = make_project(Path(temp_dir), "ConsumerProject")
            result_dir = server_test_reporting.test_results_dir(project_root)
            write_json(
                result_dir / "older.json",
                {
                    "project_root": str(project_root),
                    "request_id": "older",
                    "operation": "unity.tests.run_editmode",
                    "test_mode": "editmode",
                    "completed_at_utc": "2026-06-10T10:00:00Z",
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "counts": {"total": 999, "passed": 999},
                },
            )
            write_json(
                result_dir / "newer.json",
                {
                    "project_root": str(project_root),
                    "request_id": "newer",
                    "operation": "unity.tests.run_editmode",
                    "test_mode": "editmode",
                    "completed_at_utc": "2026-06-10T11:00:00Z",
                    "total": 3,
                    "passed": 2,
                    "failed": 1,
                    "skipped": 0,
                    "failures": [{"name": "Example.Tests.Fixture.TestA", "message": "Expected value to be True"}],
                },
            )

            rows = server_test_reporting.select_test_result_rows(
                project_roots=[project_root],
                modes=["editmode"],
            )

        self.assertEqual(1, len(rows))
        self.assertEqual("newer", rows[0]["request_id"])
        self.assertEqual(3, rows[0]["total"])
        self.assertEqual(2, rows[0]["passed"])
        self.assertEqual(1, rows[0]["failed"])
        self.assertEqual("failed", rows[0]["status"])
        self.assertEqual("assertion_failure", rows[0]["first_failure_class"])

    def test_explicit_request_id_and_result_file_output_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = make_project(Path(temp_dir), "ConsumerProject")
            result_dir = server_test_reporting.test_results_dir(project_root)
            write_json(
                result_dir / "edit-request.json",
                {
                    "project_root": str(project_root),
                    "request_id": "edit-request",
                    "operation": "unity.tests.run_editmode",
                    "test_mode": "editmode",
                    "completed_at_utc": "2026-06-10T10:00:00Z",
                    "total": 2,
                    "passed": 2,
                    "failed": 0,
                    "skipped": 0,
                    "lifecycle_churn_observed": False,
                },
            )
            external_result = Path(temp_dir) / "play.json"
            write_json(
                external_result,
                {
                    "project_root": str(project_root),
                    "request_id": "play-request",
                    "operation": "unity.tests.run_playmode",
                    "test_mode": "playmode",
                    "completed_at_utc": "2026-06-10T10:01:00Z",
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                },
            )

            rows = server_test_reporting.select_test_result_rows(
                project_roots=[project_root],
                request_ids=["edit-request"],
                result_files=[external_result],
            )
            markdown = server_test_reporting.format_test_results(rows, output_format="markdown")
            tsv = server_test_reporting.format_test_results(rows, output_format="tsv")
            json_payload = json.loads(server_test_reporting.format_test_results(rows, output_format="json"))

        self.assertEqual(["edit-request", "play-request"], sorted(row["request_id"] for row in rows))
        self.assertIn("| project | mode | status |", markdown)
        self.assertIn("request_id", tsv.splitlines()[0])
        self.assertEqual(2, json_payload["summary"]["rows_total"])
        self.assertEqual(3, json_payload["summary"]["total"])

    def test_failure_classifier_groups_repeated_setup_failures(self) -> None:
        rows = []
        for project, test_name in (("A", "Example.Tests.Fixture.TestA"), ("B", "Example.Tests.Fixture.TestB")):
            classification = server_test_reporting.classify_test_failure(
                {
                    "name": test_name,
                    "message": "OneTimeSetUp: Expected File.Exists(fixturePath) to be True but found False.",
                }
            )
            rows.append(
                {
                    "project": project,
                    "mode": "editmode",
                    "first_failure_class": classification["class"],
                    "first_failure_group_key": classification["group_key"],
                    "first_failure_message": "OneTimeSetUp: Expected File.Exists(fixturePath) to be True but found False.",
                }
            )

        groups = server_test_reporting.build_failure_groups(rows)

        self.assertEqual(1, len(groups))
        self.assertEqual(2, groups[0]["count"])
        self.assertEqual("setup_failure", groups[0]["class"])
        self.assertEqual(["A", "B"], groups[0]["projects"])

    def test_package_manifest_lock_alignment_and_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = make_project(Path(temp_dir), "ConsumerProject")
            manifest_dependency = (
                "https://github.com/FoxsterDev/xuunity-mcp.git"
                "?path=/packages/com.xuunity.light-mcp#v0.3.24"
            )
            write_json(
                project_root / "Packages" / "manifest.json",
                {"dependencies": {"com.xuunity.light-mcp": manifest_dependency}},
            )
            write_json(
                project_root / "Packages" / "packages-lock.json",
                {
                    "dependencies": {
                        "com.xuunity.light-mcp": {
                            "version": manifest_dependency,
                            "hash": "abcdef",
                        }
                    }
                },
            )

            aligned = server_test_reporting.inspect_light_mcp_package_source(project_root)
            write_json(
                project_root / "Packages" / "packages-lock.json",
                {
                    "dependencies": {
                        "com.xuunity.light-mcp": {
                            "version": manifest_dependency.replace("v0.3.24", "v0.3.23"),
                            "hash": "abcdef",
                        }
                    }
                },
            )
            mismatched = server_test_reporting.inspect_light_mcp_package_source(project_root)

        self.assertEqual("aligned", aligned["alignment"])
        self.assertEqual("abcdef", aligned["lock_hash"])
        self.assertEqual("manifest_lock_mismatch", mismatched["alignment"])


if __name__ == "__main__":
    unittest.main()
