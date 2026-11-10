import contextlib
import io
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


OPS_ROOT = Path(__file__).resolve().parents[1]
RUNNER_DIR = OPS_ROOT / "scripts" / "testing"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

import run_consumer_rollout as rollout


OLD_TAG = "v0.3.59"
OLD_COMMIT = "a" * 40
RELEASE_TAG = "v0.3.60"
RELEASE_COMMIT = "b" * 40
PACKAGE_NAME = "com.xuunity.light-mcp"
PACKAGE_URL = "https://github.com/example/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp"


def create_consumer(root: Path, name: str, *, tag: str = OLD_TAG, commit: str = OLD_COMMIT) -> Path:
    project = root / name
    (project / "Packages").mkdir(parents=True)
    (project / "ProjectSettings").mkdir()
    (project / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 6000.0.58f2\n",
        encoding="utf-8",
    )
    dependency = f"{PACKAGE_URL}#{tag}"
    rollout.write_json(
        project / "Packages" / "manifest.json",
        {
            "dependencies": {
                "com.example.keep": "1.0.0",
                PACKAGE_NAME: dependency,
            }
        },
    )
    rollout.write_json(
        project / "Packages" / "packages-lock.json",
        {
            "dependencies": {
                PACKAGE_NAME: {
                    "version": dependency,
                    "depth": 0,
                    "source": "git",
                    "dependencies": {},
                    "hash": commit,
                },
                "com.example.keep": {
                    "version": "1.0.0",
                    "depth": 0,
                    "source": "registry",
                    "dependencies": {},
                },
            }
        },
    )
    return project


def clean_git_snapshot(project_root: Path, scoped_paths: list[Path]) -> dict:
    del scoped_paths
    return {
        "available": True,
        "error_code": "",
        "stderr": "",
        "root": str(project_root.parent),
        "branch": "main",
        "head": "c" * 40,
        "dirty_paths": [],
    }


def clean_workspace_snapshot(git_root: Path) -> dict:
    return {
        "available": True,
        "root": str(git_root),
        "dirty_paths": [],
        "error_code": "",
        "stderr": "",
    }


def make_inventory(root: Path, projects: list[Path], canary: Path) -> dict:
    with mock.patch.object(rollout, "git_snapshot", side_effect=clean_git_snapshot):
        return rollout.build_inventory(
            expected_roots=projects,
            search_roots=[root],
            canary_root=canary,
            package_name=PACKAGE_NAME,
        )


def make_passed_preflight(inventory: dict, root: Path) -> dict:
    unity_app = root / "Unity.app"
    unity_binary = root / "Unity"
    unity_binary.write_text("fake", encoding="utf-8")
    with (
        mock.patch.object(rollout, "resolve_unity_executable", return_value=unity_binary),
        mock.patch.object(rollout, "resolve_unity_app_version", return_value="6000.0.58f2"),
    ):
        return rollout.build_preflight(
            inventory=inventory,
            unity_app=unity_app,
            run_dir=root / "run",
            process_report_fn=lambda: {"available": True, "commands": []},
            workspace_snapshot_fn=clean_workspace_snapshot,
            license_probe_fn=lambda **_kwargs: {
                "batchmode_supported": True,
                "editor_ui_supported": None,
                "batchmode_blocker_code": "",
                "recommended_execution_lane": "batch",
                "batchmode_probe_exit_code": 0,
                "batchmode_probe_timed_out": False,
            },
        )


def make_ledger(root: Path, projects: list[Path], canary: Path) -> dict:
    inventory = make_inventory(root, projects, canary)
    if inventory["status"] != "ready":
        raise AssertionError(inventory["errors"])
    preflight = make_passed_preflight(inventory, root)
    if preflight["status"] != "passed":
        raise AssertionError(preflight["blockers"])
    return rollout.build_ledger(
        run_dir=root / "run",
        release_tag=RELEASE_TAG,
        release_commit=RELEASE_COMMIT,
        inventory=inventory,
        preflight=preflight,
        worker_label="bounded-test-worker",
        worker_timeout_seconds=10,
        overall_deadline_seconds=600,
    )


def fake_runner_factory(outcomes: dict[str, str], calls: list[str]):
    def runner(*, project, unity_executable, run_dir, timeout_seconds, on_started):
        del unity_executable, timeout_seconds
        calls.append(project["project"])
        unity_log = run_dir / f"{project['project_id']}.unity.log"
        process_log = run_dir / f"{project['project_id']}.process.log"
        command = [
            "/Applications/Unity/Unity.app/Contents/MacOS/Unity",
            "-batchmode",
            "-projectPath",
            project["project_root"],
            "-logFile",
            str(unity_log),
        ]
        on_started(4000 + len(calls), command, unity_log, process_log)
        outcome = outcomes.get(project["project"], "passed")
        unity_log.write_text(
            "Tundra build success\n" if outcome == "passed" else "Scripts have compiler errors\n",
            encoding="utf-8",
        )
        process_log.write_text("", encoding="utf-8")
        return {
            "outcome": outcome,
            "exit_code": 0 if outcome == "passed" else 1,
            "duration_seconds": 0.01,
            "unity_log_path": str(unity_log),
            "process_log_path": str(process_log),
            "compile_error": "" if outcome == "passed" else "Scripts have compiler errors",
            "owned_process": {"active": False, "pid": 4000 + len(calls), "command": command},
        }

    return runner


class ConsumerInventoryTests(unittest.TestCase):
    def test_inventory_reconciles_expected_and_ignore_independent_discovery(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = create_consumer(root, "Expected")
            newly_discovered = create_consumer(root / "nested", "NewConsumer")
            with mock.patch.object(rollout, "git_snapshot", side_effect=clean_git_snapshot):
                blocked = rollout.build_inventory(
                    expected_roots=[expected],
                    search_roots=[root],
                    canary_root=expected,
                )
                accepted = rollout.build_inventory(
                    expected_roots=[expected],
                    search_roots=[root],
                    canary_root=expected,
                    accept_discovered=True,
                )

            self.assertEqual("needs_smart_escalation", blocked["status"])
            self.assertEqual(1, blocked["denominator"]["unexpected_discovered"])
            self.assertIn(
                "unexpected_consumer_requires_root_triage",
                {item["code"] for item in blocked["errors"]},
            )
            self.assertEqual("ready", accepted["status"])
            self.assertEqual(2, accepted["denominator"]["total"])
            self.assertEqual(
                {expected.resolve(), newly_discovered.resolve()},
                {Path(row["project_root"]) for row in accepted["projects"] if row["included"]},
            )

            with mock.patch.object(rollout, "git_snapshot", side_effect=clean_git_snapshot):
                excluded = rollout.build_inventory(
                    expected_roots=[expected],
                    search_roots=[root],
                    canary_root=expected,
                    excluded_roots=[root / "nested"],
                )
            self.assertEqual("ready", excluded["status"])
            self.assertEqual(1, excluded["denominator"]["discovered"])

    def test_dirty_canary_is_a_hard_inventory_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")

            def dirty_snapshot(project_root, scoped_paths):
                result = clean_git_snapshot(project_root, scoped_paths)
                result["dirty_paths"] = ["Canary/Packages/manifest.json"]
                return result

            with mock.patch.object(rollout, "git_snapshot", side_effect=dirty_snapshot):
                inventory = rollout.build_inventory(
                    expected_roots=[canary],
                    search_roots=[root],
                    canary_root=canary,
                )

            self.assertEqual("needs_smart_escalation", inventory["status"])
            self.assertIn("canary_package_files_dirty", {item["code"] for item in inventory["errors"]})


class ConsumerPreflightTests(unittest.TestCase):
    def test_preflight_blocks_unrelated_global_unity_before_license_probe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            inventory = make_inventory(root, [canary], canary)
            unity_binary = root / "Unity"
            unity_binary.write_text("fake", encoding="utf-8")
            license_probe = mock.Mock()
            with (
                mock.patch.object(rollout, "resolve_unity_executable", return_value=unity_binary),
                mock.patch.object(rollout, "resolve_unity_app_version", return_value="6000.0.58f2"),
            ):
                preflight = rollout.build_preflight(
                    inventory=inventory,
                    unity_app=root / "Unity.app",
                    run_dir=root / "run",
                    process_report_fn=lambda: {
                        "available": True,
                        "commands": [
                            (
                                8123,
                                "/Applications/Unity/Unity.app/Contents/MacOS/Unity "
                                "-projectPath /private/other-project",
                            )
                        ],
                    },
                    license_probe_fn=license_probe,
                )

            self.assertEqual("blocked", preflight["status"])
            self.assertIn("global_unity_process_conflict", {row["code"] for row in preflight["blockers"]})
            license_probe.assert_not_called()

    def test_preflight_ignores_unity_paths_in_arguments_of_other_processes(self) -> None:
        unity = "/Applications/Unity/Unity.app/Contents/MacOS/Unity"
        report = {
            "available": True,
            "commands": [
                (8201, f"/bin/zsh -c {unity} -batchmode -projectPath /private/other-project"),
                (8202, f"/usr/bin/python3 run_consumer_rollout.py plan --unity-app {unity}"),
                (8203, "/usr/bin/python3 helper.py --label '/opt/Unity Licensing Client/UnityLicensingClient'"),
                (8204, f"{unity} -projectPath /private/other-project"),
                (8205, "/Applications/Unity Hub.app/Contents/Frameworks/UnityLicensingClient_V1.app/Contents/MacOS/Unity.Licensing.Client"),
            ],
        }
        rows = rollout.relevant_unity_processes(report)
        self.assertEqual({8204: "main_editor"}, {row["pid"]: row["role"] for row in rows if row["role"] != "launcher"})
        report["commands"] = report["commands"][:3]
        self.assertEqual([], rollout.relevant_unity_processes(report))

    def test_preflight_proves_writes_visibility_and_batch_license(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            inventory = make_inventory(root, [canary], canary)
            preflight = make_passed_preflight(inventory, root)

            self.assertEqual("passed", preflight["status"])
            self.assertEqual("6000.0.58f2", preflight["unity_version"])
            self.assertTrue(preflight["license_capabilities"]["batchmode_supported"])
            self.assertTrue(all(row["writable"] for row in preflight["write_probes"]))
            self.assertEqual("root_agent", preflight["cleanup_owner"])


class ConsumerExecutionTests(unittest.TestCase):
    def test_canary_failure_prevents_fanout_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            calls: list[str] = []
            result = rollout.execute_rollout(
                ledger,
                runner=fake_runner_factory({"Canary": "needs_smart_escalation"}, calls),
                workspace_snapshot_fn=clean_workspace_snapshot,
            )

            self.assertEqual(["Canary"], calls)
            self.assertEqual("needs_smart_escalation", result["status"])
            self.assertEqual(RELEASE_TAG, rollout.inspect_consumer(canary, PACKAGE_NAME)["manifest_ref"])
            self.assertEqual(OLD_TAG, rollout.inspect_consumer(follower, PACKAGE_NAME)["manifest_ref"])

    def test_successful_canary_fans_out_and_completes_serially(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            calls: list[str] = []
            result = rollout.execute_rollout(
                ledger,
                runner=fake_runner_factory({}, calls),
                workspace_snapshot_fn=clean_workspace_snapshot,
            )

            self.assertEqual(["Canary", "Follower"], calls)
            self.assertEqual("completed", result["status"])
            for project in (canary, follower):
                inspected = rollout.inspect_consumer(project, PACKAGE_NAME)
                self.assertEqual(RELEASE_TAG, inspected["manifest_ref"])
                self.assertEqual(RELEASE_TAG, inspected["lock_ref"])
                self.assertEqual(RELEASE_COMMIT, inspected["lock_hash"])
            persisted = rollout.load_ledger(Path(result["ledger_path"]))
            self.assertTrue(all(row["state"] == "passed" for row in persisted["projects"]))

    def test_root_authorized_resume_skips_prior_pass_and_retries_first_unproven(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            first_calls: list[str] = []
            result = rollout.execute_rollout(
                ledger,
                runner=fake_runner_factory({"Follower": "needs_smart_escalation"}, first_calls),
                workspace_snapshot_fn=clean_workspace_snapshot,
            )
            follower_row = next(row for row in result["projects"] if row["project"] == "Follower")

            rollout.authorize_resume(
                result,
                project_id=follower_row["project_id"],
                confirm_release_tag=RELEASE_TAG,
            )
            second_calls: list[str] = []
            completed = rollout.execute_rollout(
                result,
                runner=fake_runner_factory({}, second_calls),
                workspace_snapshot_fn=clean_workspace_snapshot,
            )

            self.assertEqual(["Canary", "Follower"], first_calls)
            self.assertEqual(["Follower"], second_calls)
            self.assertEqual("completed", completed["status"])
            resumed = next(row for row in completed["projects"] if row["project"] == "Follower")
            self.assertEqual(1, len(resumed["attempts"]))

    def test_overall_deadline_stops_before_fanout(self) -> None:
        class ControlledDateTime(datetime):
            current = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)

            @classmethod
            def now(cls, tz=None):
                value = cls.current
                return value if tz is None else value.astimezone(tz)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            ledger["overall_deadline_seconds"] = 5
            calls: list[str] = []
            base_runner = fake_runner_factory({}, calls)

            def advancing_runner(**kwargs):
                result = base_runner(**kwargs)
                ControlledDateTime.current += timedelta(seconds=10)
                return result

            with mock.patch.object(rollout, "datetime", ControlledDateTime):
                result = rollout.execute_rollout(
                    ledger,
                    runner=advancing_runner,
                    workspace_snapshot_fn=clean_workspace_snapshot,
                )

            self.assertEqual(["Canary"], calls)
            self.assertEqual("needs_smart_escalation", result["status"])
            self.assertEqual(
                "root_review_overall_deadline_before_fanout",
                result["recommended_next_action"],
            )
            self.assertEqual(OLD_TAG, rollout.inspect_consumer(follower, PACKAGE_NAME)["manifest_ref"])


class ConsumerWatchdogTests(unittest.TestCase):
    def test_worker_timeout_records_owned_pid_without_killing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = create_consumer(root, "Canary")
            row = {"project_id": "canary-1", "project_root": str(project)}
            started: list[tuple] = []
            proc = mock.Mock(pid=4321)
            proc.wait.side_effect = subprocess.TimeoutExpired(cmd=["Unity"], timeout=1)
            with mock.patch.object(rollout.subprocess, "Popen", return_value=proc):
                result = rollout.run_project_validation(
                    project=row,
                    unity_executable="/Applications/Unity/Unity.app/Contents/MacOS/Unity",
                    run_dir=root,
                    timeout_seconds=1,
                    on_started=lambda *args: started.append(args),
                )

            self.assertEqual("needs_smart_escalation", result["outcome"])
            self.assertTrue(result["owned_process"]["active"])
            self.assertEqual(4321, result["owned_process"]["pid"])
            self.assertEqual(1, len(started))
            proc.kill.assert_not_called()
            proc.terminate.assert_not_called()

    def test_cleanup_kills_only_freshly_reverified_owned_unity_pid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = create_consumer(root, "Canary")
            ledger = make_ledger(root, [project], project)
            row = ledger["projects"][0]
            unity_log = root / "run" / "owned.unity.log"
            command = (
                "/Applications/Unity/Unity.app/Contents/MacOS/Unity -batchmode "
                f'-projectPath "{project}" -logFile "{unity_log}"'
            )
            row["state"] = "needs_smart_escalation"
            row["owned_process"] = {
                "active": True,
                "pid": 7654,
                "project_root": str(project),
                "unity_log_path": str(unity_log),
                "command": command.split(),
            }
            terminated: list[tuple[int, int]] = []
            _, cleaned = rollout.cleanup_owned_process(
                ledger,
                project_id=row["project_id"],
                process_report_fn=lambda: {"available": True, "commands": [(7654, command)]},
                terminate_fn=lambda pid, timeout: terminated.append((pid, timeout)) or True,
            )

            self.assertTrue(cleaned)
            self.assertEqual([(7654, rollout.PROCESS_CLEANUP_TIMEOUT_MS)], terminated)
            self.assertEqual("terminated", row["cleanup"]["status"])
            self.assertFalse(row["owned_process"]["active"])

    def test_cleanup_refuses_foreign_or_reused_pid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = create_consumer(root, "Canary")
            ledger = make_ledger(root, [project], project)
            row = ledger["projects"][0]
            row["owned_process"] = {
                "active": True,
                "pid": 7654,
                "project_root": str(project),
                "unity_log_path": str(root / "run" / "owned.unity.log"),
            }
            terminate = mock.Mock(return_value=True)
            _, cleaned = rollout.cleanup_owned_process(
                ledger,
                project_id=row["project_id"],
                process_report_fn=lambda: {"available": True, "commands": [(7654, "/usr/bin/python unrelated.py")]},
                terminate_fn=terminate,
            )

            self.assertFalse(cleaned)
            self.assertEqual("refused_identity_unproven", row["cleanup"]["status"])
            terminate.assert_not_called()


class ConsumerEvidenceTests(unittest.TestCase):
    def test_process_evidence_redacts_sensitive_arguments_before_persisting(self) -> None:
        secret_values = ("access-value", "api-value", "password value")
        command = (
            "/Applications/Unity/Unity.app/Contents/MacOS/Unity "
            "-projectPath /tmp/Project -accessToken access-value "
            "--api-key=api-value -password 'password value'"
        )

        rows = rollout.relevant_unity_processes(
            {"available": True, "commands": [(7654, command)]}
        )
        persisted = json.dumps(rows)

        self.assertEqual(1, len(rows))
        self.assertGreaterEqual(persisted.count("[REDACTED]"), 3)
        for secret in secret_values:
            self.assertNotIn(secret, persisted)

        args = rollout.redact_command_args(
            ["Unity", "-accessToken", "access-value", "--api-key=api-value"]
        )
        self.assertEqual(
            ["Unity", "-accessToken", "[REDACTED]", "--api-key=[REDACTED]"],
            args,
        )

    def test_workspace_side_effects_allow_owned_pins_but_report_new_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            ledger = make_ledger(root, [canary], canary)
            git_root = Path(ledger["preflight"]["workspace_baselines"][0]["root"])
            relative_manifest = str(
                (canary / "Packages" / "manifest.json").resolve().relative_to(git_root.resolve())
            )
            result = rollout.workspace_side_effects(
                ledger,
                workspace_snapshot_fn=lambda _root: {
                    "available": True,
                    "root": str(git_root),
                    "dirty_paths": [relative_manifest, "Unexpected.asset"],
                    "error_code": "",
                },
            )

            self.assertEqual("needs_smart_escalation", result["status"])
            self.assertIn(f"{git_root}:Unexpected.asset", result["new_unowned_dirty_paths"])
            self.assertNotIn(f"{git_root}:{relative_manifest}", result["new_unowned_dirty_paths"])

    def test_workspace_side_effects_exclude_the_helpers_own_run_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            ledger = make_ledger(root, [canary], canary)
            git_root = Path(ledger["preflight"]["workspace_baselines"][0]["root"])
            run_dir = Path(ledger["run_dir"]).resolve().relative_to(git_root.resolve()).as_posix()
            result = rollout.workspace_side_effects(
                ledger,
                workspace_snapshot_fn=lambda _root: {
                    "available": True,
                    "root": str(git_root),
                    "dirty_paths": [
                        f"{run_dir}/consumer_rollout_ledger.json",
                        f"{run_dir}/canary.unity.log",
                        f"{run_dir}-sibling/notes.txt",
                    ],
                    "error_code": "",
                },
            )

            self.assertEqual([f"{git_root}:{run_dir}-sibling/notes.txt"], result["new_unowned_dirty_paths"])
            self.assertEqual(f"{run_dir}/", result["workspaces"][0]["own_run_dir"])
            self.assertEqual(2, result["workspaces"][0]["own_run_dir_path_count"])

    def test_compiler_servers_left_by_batch_compiles_are_recorded_and_closed_at_completion(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            install = root.resolve() / "Unity.app"
            vbcs = (
                f"{install}/Contents/NetCoreRuntime/dotnet exec "
                f"{install}/Contents/DotNetSdkRoslyn/VBCSCompiler.dll -pipename:abc"
            )
            foreign = "/opt/dotnet/dotnet exec /opt/sdk/VBCSCompiler.dll -pipename:other"
            ledger["preflight"]["compiler_servers_at_preflight"] = [700]
            report = {
                "available": True,
                "commands": [(700, vbcs), (701, vbcs), (702, foreign), (703, "/usr/bin/python3 grep VBCSCompiler")],
            }
            terminated: list[int] = []
            result = rollout.execute_rollout(
                ledger,
                runner=fake_runner_factory({}, []),
                workspace_snapshot_fn=clean_workspace_snapshot,
                process_report_fn=lambda: report,
                terminate_fn=lambda pid, _timeout: terminated.append(pid) or True,
            )

            self.assertEqual("completed", result["status"])
            statuses = {row["pid"]: row["status"] for row in result["compiler_servers"]}
            self.assertEqual({701: "closed", 702: "left_open_identity_unproven"}, statuses)
            self.assertEqual([701], terminated)
            self.assertEqual("Canary", next(
                row for row in result["projects"] if row["project_id"] == result["compiler_servers"][0]["first_seen_after_project_id"]
            )["project"])
            self.assertEqual(1, rollout.compact_projection(result)["compiler_servers_open"])

    def test_compiler_servers_stay_open_while_a_unity_editor_is_live(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            ledger = make_ledger(root, [canary], canary)
            install = root.resolve() / "Unity.app"
            vbcs = f"{install}/Contents/NetCoreRuntime/dotnet exec {install}/Contents/DotNetSdkRoslyn/VBCSCompiler.dll"
            ledger["compiler_servers"] = [
                {"pid": 801, "command": vbcs, "unity_install_match": True, "status": "open"}
            ]
            report = {
                "available": True,
                "commands": [(801, vbcs), (802, f"{install}/Contents/MacOS/Unity -projectPath /tmp/Other")],
            }
            terminate = mock.Mock(return_value=True)
            summary = rollout.close_compiler_servers(ledger, process_report_fn=lambda: report, terminate_fn=terminate)

            terminate.assert_not_called()
            self.assertEqual("live_unity_editor_may_share_the_server", summary["reason"])
            self.assertEqual(1, summary["left_open"])
            report["commands"] = []
            summary = rollout.close_compiler_servers(ledger, process_report_fn=lambda: report, terminate_fn=terminate)
            self.assertEqual(1, summary["exited"])
            self.assertEqual("exited", ledger["compiler_servers"][0]["status"])

    def test_worker_packet_is_exact_and_denies_diagnosis_release_and_kill(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            follower = create_consumer(root, "Follower")
            ledger = make_ledger(root, [canary, follower], canary)
            packet = rollout.read_json_object(Path(ledger["task_packet_path"]))

            self.assertEqual("bounded-test-worker", packet["worker_label"])
            self.assertEqual(2, len(packet["project_order"]))
            self.assertTrue(packet["project_order"][0]["canary"])
            self.assertFalse(packet["permissions"]["process_termination"])
            self.assertIn("do_not_diagnose_or_fix_unexpected_results", packet["non_authorities"])
            self.assertIn("do_not_kill_processes", packet["non_authorities"])
            self.assertEqual("needs_smart_escalation", packet["unexpected_result_contract"]["status"])

    def test_compact_summary_is_default_decision_shape_with_full_opt_in(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canary = create_consumer(root, "Canary")
            ledger = make_ledger(root, [canary], canary)
            compact = rollout.compact_projection(ledger)
            encoded = json.dumps(compact, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

            self.assertEqual("compact_consumer_rollout", compact["payload_mode"])
            self.assertNotIn("projects", compact)
            self.assertNotIn("inventory", compact)
            self.assertEqual("--output full", compact["full_payload_cli_argument"])
            self.assertLessEqual(len(encoded), 2000)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rollout.main(["summary", "--ledger", ledger["ledger_path"]])
            emitted = json.loads(stdout.getvalue())
            self.assertEqual("compact_consumer_rollout", emitted["payload_mode"])


if __name__ == "__main__":
    unittest.main()
