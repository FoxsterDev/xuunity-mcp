import json
import os
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


OPS_ROOT = Path(__file__).resolve().parents[1]
RUNNER = OPS_ROOT / "scripts" / "testing" / "run_multi_project_gui_test_subset.sh"


class MultiProjectGuiRunnerTests(unittest.TestCase):
    def test_gui_runner_persists_test_package_restore_and_aggregate_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "ConsumerProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir()
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )
            dependency = (
                "https://github.com/FoxsterDev/xuunity-mcp.git"
                "?path=/packages/com.xuunity.light-mcp#v0.3.24"
            )
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": dependency}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps(
                    {
                        "dependencies": {
                            "com.xuunity.light-mcp": {
                                "version": dependency,
                                "hash": "abcdef",
                            }
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            wrapper_path = temp_root / "fake_xuunity_light_unity_mcp.sh"
            wrapper_path.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    command_name="${1:-}"
                    project_root=""
                    while [[ $# -gt 0 ]]; do
                      case "$1" in
                        --project-root)
                          project_root="${2:-}"
                          shift 2
                          ;;
                        *)
                          shift
                          ;;
                      esac
                    done

                    emit_payload() {
                      local mode="$1"
                      local request_id="$2"
                      local total="$3"
                      local passed="$4"
                      local failed="$5"
                      local message="${6:-}"
                      local result_dir="$project_root/Library/XUUnityLightMcp/state/test_results"
                      mkdir -p "$result_dir"
                      python3 - "$project_root" "$mode" "$request_id" "$total" "$passed" "$failed" "$message" <<'PY'
                    import json
                    import sys
                    from pathlib import Path

                    project_root, mode, request_id, total, passed, failed, message = sys.argv[1:]
                    payload = {
                        "project_root": project_root,
                        "operation": f"unity.tests.run_{mode}",
                        "test_mode": mode,
                        "completed_at_utc": "2026-06-10T12:00:00Z",
                        "total": int(total),
                        "passed": int(passed),
                        "failed": int(failed),
                        "skipped": 0,
                        "lifecycle_churn_observed": False,
                        "failures": [],
                    }
                    if message:
                        payload["failures"].append({"name": "Example.Tests.Fixture.TestA", "message": message})
                    result_path = Path(project_root) / "Library" / "XUUnityLightMcp" / "state" / "test_results" / f"{request_id}.json"
                    persisted = dict(payload)
                    persisted["request_id"] = request_id
                    result_path.write_text(json.dumps(persisted, indent=2) + "\\n", encoding="utf-8")
                    print(json.dumps({"status": "ok", "request_id": request_id, "payload_json": json.dumps(payload)}))
                    PY
                    }

                    case "$command_name" in
                      recover-editor-session)
                        printf '{"recovery_classification":"not_needed","recommended_next_action":"none"}\\n'
                        ;;
                      ensure-ready)
                        printf '{"bridge_state":{"health_status":"ready"},"launch":{"editor_pid":123}}\\n'
                        ;;
                      request-editmode-tests)
                        emit_payload "editmode" "edit-id" 3 2 1 "OneTimeSetUp: Expected file to exist."
                        ;;
                      request-playmode-tests)
                        emit_payload "playmode" "play-id" 2 2 0 ""
                        ;;
                      restore-editor-state)
                        printf '{"closeout_verified":true,"closeout_classification":"closed","live_project_editor_pids":[]}\\n'
                        ;;
                      *)
                        echo "unexpected command: $command_name" >&2
                        exit 2
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            wrapper_path.chmod(0o755)

            results_dir = temp_root / "results"
            env = os.environ.copy()
            env["XUUNITY_LIGHT_UNITY_MCP_WRAPPER"] = str(wrapper_path)
            completed = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "--repo-root",
                    str(temp_root),
                    "--project-root",
                    str(project_root),
                    "--parallelism",
                    "1",
                    "--window-arrangement",
                    "off",
                    "--side-effect-mode",
                    "off",
                    "--results-dir",
                    str(results_dir),
                ],
                cwd=OPS_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            status_path = results_dir / "ConsumerProject_status.json"
            self.assertTrue(
                status_path.is_file(),
                completed.stderr + completed.stdout + "\nfiles=" + "\n".join(str(path) for path in sorted(results_dir.glob("*"))),
            )
            status = json.loads(status_path.read_text(encoding="utf-8"))
            aggregate = json.loads((results_dir / "_aggregate_summary.json").read_text(encoding="utf-8"))

        self.assertEqual(1, completed.returncode, completed.stderr + completed.stdout)
        self.assertEqual("edit-id", status["edit_request_id"])
        self.assertEqual(1, status["edit_failed"])
        self.assertFalse(status["edit_lifecycle_churn_observed"])
        self.assertEqual("play-id", status["play_request_id"])
        self.assertTrue(status["closeout_verified"])
        self.assertEqual("aligned", status["package_source"]["alignment"])
        self.assertEqual("off", status["workspace_side_effects"]["mode"])
        self.assertEqual(1, aggregate["projects_failed"])
        self.assertEqual(1, len(aggregate["failure_groups"]))
        self.assertEqual("setup_failure", aggregate["failure_groups"][0]["class"])
        self.assertEqual(0, aggregate["package_mismatch_count"])


if __name__ == "__main__":
    unittest.main()
