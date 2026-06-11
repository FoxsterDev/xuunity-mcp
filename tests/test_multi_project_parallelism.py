"""Real worker-overlap proof for the multi-project orchestrator.

Three fake projects with --parallelism 3 must actually overlap: every worker
records its own start/end wall-clock stamps, and the test asserts the latest
start happens before the earliest end. This must hold identically on macOS,
Linux, and Windows (the leg that lost parallelism in the xargs era).

Phase 3 of XUUNITY_MCP_THIN_LAUNCHER_PYTHON_CORE_DESIGN_2026-06-11.
"""

import json
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

OPS_ROOT = Path(__file__).resolve().parents[1]
RUNNER = OPS_ROOT / "scripts" / "testing" / "run_multi_project_batch_compile_matrix.sh"
BASH = resolve_bash_executable()

FAKE_WRAPPER = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail
    PYTHON_CMD="${XUUNITY_LIGHT_UNITY_MCP_PYTHON:-python3}"
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
    project_name="$(basename "$project_root")"
    case "$command_name" in
      batch-build-config-compile-matrix)
        "$PYTHON_CMD" -c 'import sys,time; open(sys.argv[1],"w").write(repr(time.time()))' \
          "$XUUNITY_PARALLELISM_STAMP_DIR/${project_name}_start"
        sleep 3
        "$PYTHON_CMD" -c 'import sys,time; open(sys.argv[1],"w").write(repr(time.time()))' \
          "$XUUNITY_PARALLELISM_STAMP_DIR/${project_name}_end"
        cat <<'JSON'
    {
      "action": "batch_build_config_compile_matrix",
      "succeeded": true,
      "result_summary": {
        "requested_execution_lane": "batch",
        "effective_execution_lane": "batch",
        "batch_fallback_mode": "auto",
        "matrix": {"status": "passed", "total": 1, "passed": 1, "failed": 0, "skipped": 0}
      }
    }
    JSON
        ;;
      *)
        echo "unexpected command: $command_name" >&2
        exit 2
        ;;
    esac
    """
)


class MultiProjectParallelismTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def create_fake_project(self, root: Path) -> Path:
        (root / "Packages").mkdir(parents=True)
        (root / "ProjectSettings").mkdir(parents=True)
        (root / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": {"com.xuunity.light-mcp": "file:package"}}) + "\n",
            encoding="utf-8",
        )
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.0.58f2\n", encoding="utf-8"
        )
        return root

    def test_three_workers_overlap_with_parallelism_three(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_names = ["ProjectAlpha", "ProjectBeta", "ProjectGamma"]
            project_roots = [self.create_fake_project(temp_root / name) for name in project_names]

            wrapper_path = temp_root / "fake_xuunity_light_unity_mcp.sh"
            wrapper_path.write_text(FAKE_WRAPPER, encoding="utf-8")
            wrapper_path.chmod(0o755)

            stamp_dir = temp_root / "stamps"
            stamp_dir.mkdir()
            results_dir = temp_root / "results"

            env = os.environ.copy()
            env["XUUNITY_LIGHT_UNITY_MCP_WRAPPER"] = wrapper_path.as_posix()
            env["XUUNITY_LIGHT_UNITY_MCP_PYTHON"] = Path(sys.executable).as_posix()
            env["XUUNITY_PARALLELISM_STAMP_DIR"] = stamp_dir.as_posix()

            cmd = [BASH, RUNNER.as_posix(), "--repo-root", temp_root.as_posix()]
            for project_root in project_roots:
                cmd.extend(["--project-root", project_root.as_posix()])
            cmd.extend(
                [
                    "--parallelism",
                    "3",
                    "--no-close-live-editors",
                    "--results-dir",
                    results_dir.as_posix(),
                ]
            )

            completed = run_with_timeout(cmd, cwd=OPS_ROOT.as_posix(), env=env, timeout_seconds=180)

            self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
            self.assertIn('"projects_failed": 0', completed.stdout)

            starts = []
            ends = []
            for name in project_names:
                start_path = stamp_dir / f"{name}_start"
                end_path = stamp_dir / f"{name}_end"
                self.assertTrue(start_path.is_file(), f"missing start stamp for {name}")
                self.assertTrue(end_path.is_file(), f"missing end stamp for {name}")
                starts.append(float(start_path.read_text(encoding="utf-8")))
                ends.append(float(end_path.read_text(encoding="utf-8")))

            latest_start = max(starts)
            earliest_end = min(ends)
            self.assertLess(
                latest_start,
                earliest_end,
                "workers did not overlap: latest start %.3f >= earliest end %.3f (starts=%s ends=%s)"
                % (latest_start, earliest_end, starts, ends),
            )


if __name__ == "__main__":
    unittest.main()
