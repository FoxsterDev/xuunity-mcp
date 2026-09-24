import argparse
import contextlib
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

OPS_ROOT = Path(__file__).resolve().parents[1]
RUNNER_DIR = OPS_ROOT / "scripts" / "testing"
TEMPLATES_DIR = OPS_ROOT / "templates"
for entry in (RUNNER_DIR, TEMPLATES_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import evaluate_validation_evidence as cli  # noqa: E402
import validation_acceptance as acceptance  # noqa: E402
from server_launcher import COMPACT_OUTPUT_MAX_BYTES, _bounded_compact_json  # noqa: E402

SOURCE = {"algorithm": "sha256", "digest": "a" * 64}
OTHER_SOURCE = {"algorithm": "sha256", "digest": "b" * 64}
DIMS = {"unityVersion": "6000.0.58f2", "target": "Android", "scriptingBackend": "IL2CPP", "inputMode": None}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def evidence(root: Path, name: str, payload) -> dict:
    path = root / name
    write_json(path, payload)
    return {"path": name, "sha256": acceptance.sha256_file(path)}


def requirement(identifier: str, *, stage: str = "compile", channel: str = "any", required: bool = True, **extra) -> dict:
    row = {
        "id": identifier,
        "required": required,
        "stage": stage,
        "executionChannel": channel,
        "dimensions": dict(DIMS),
        "scene": None,
        "artifactRequired": False,
    }
    row.update(extra)
    return row


def receipt(identifier: str, requirement_id: str, ref: dict, *, stage: str = "compile", channel: str = "direct-unity", outcome: str = "passed", **extra) -> dict:
    row = {
        "receiptId": identifier,
        "requirementId": requirement_id,
        "sourceIdentity": dict(SOURCE),
        "dimensions": dict(DIMS),
        "stage": stage,
        "executionChannel": channel,
        "evidenceRef": ref,
        "producer": {"name": "test-producer", "version": "1", "route": "fixture"},
        "startedAt": "2026-09-21T00:00:00Z",
        "completedAt": "2026-09-21T00:00:01Z",
        "operationOutcome": outcome,
    }
    row.update(extra)
    return row


def plan(*requirements: dict, **extra) -> dict:
    document = {
        "schemaVersion": acceptance.PLAN_SCHEMA_VERSION,
        "planId": "plan-1",
        "projectId": "project-1",
        "sourceIdentity": dict(SOURCE),
        "requirements": list(requirements),
    }
    document.update(extra)
    return document


def receipts(*rows: dict) -> dict:
    return {"schemaVersion": acceptance.RECEIPTS_SCHEMA_VERSION, "receipts": list(rows)}


def compile_response(*, status: str = "passed", warning_count=0, rebuild_status: str = "measured", rebuilt: int = 45) -> dict:
    result = {
        "status": status,
        "target": "Android",
        "error_count": 0,
        "warning_count": warning_count,
        "unique_warning_count": warning_count,
        "warnings": [],
        "warnings_truncated": False,
        "rebuilt_assembly_count": rebuilt,
        "cached_assembly_count": 99,
        "rebuild_evidence_status": rebuild_status,
    }
    return {
        "request_id": "req-compile",
        "status": "ok",
        "completed_at_utc": "2026-09-21T09:53:35Z",
        "payload_type": "unity.compile.player_scripts",
        "payload_json": json.dumps(
            {
                "completion_basis": "unity_compile_settle_watcher",
                "authoritative_state_source": "bridge_response",
                "post_settle_error_count": 0,
                "result": result,
            }
        ),
        "error": {"code": "", "message": ""},
        "_xuunity_lifecycle": {"operation": "unity.compile.player_scripts", "transport": {"transport": "tcp_loopback"}},
    }


def tests_response(*, verdict: str = "passed", total: int = 1, passed: int = 1, failed: int = 0, payload_type: str = "unity.tests.run_playmode") -> dict:
    return {
        "request_id": "req-tests",
        "status": "ok",
        "completed_at_utc": "2026-09-21T02:07:37Z",
        "payload_type": payload_type,
        "payload_json": json.dumps(
            {
                "test_verdict": verdict,
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": 0,
                "completion_basis": "unity_test_runner_callbacks",
                "post_settle_error_count": 0,
            }
        ),
        "error": {"code": "", "message": ""},
        "_xuunity_lifecycle": {"operation": payload_type, "transport": {"transport": "tcp_loopback"}},
    }


def run_eval(plan_document: dict, receipts_document: dict, manifest_dir: Path) -> dict:
    acceptance.validate_plan(plan_document)
    acceptance.validate_receipts(receipts_document)
    report = acceptance.evaluate(
        plan_document,
        receipts_document,
        manifest_dir=manifest_dir,
        plan_sha256="c" * 64,
        report_ref="report.json",
    )
    acceptance.validate_acceptance_report(report)
    return report


def synthetic_consumer_verdict() -> dict:
    lines = ["2022.3 LTS", "6000.0", "6000.3", "6000.5", "6000.6"]
    targets = ["Android", "iOS", "StandaloneOSX", "StandaloneWindows64", "StandaloneLinux64", "WebGL", "tvOS", "VisionOS"]
    backends = {target: ("IL2CPP" if target in ("Android", "iOS", "WebGL", "tvOS", "VisionOS") else "Mono2x") for target in targets}
    statuses = ["PASS"] * 8 + ["REUSED"] * 15 + ["BLOCKED"] * 17
    lanes = []
    rows = []
    for index, (line, target) in enumerate([(line, target) for line in lines for target in targets]):
        status = statuses[index]
        version = line.replace(" LTS", "") + ".1f1"
        lane = {"line": line, "target": target, "unity_version": version, "backend": backends[target], "status": status, "stage": "player-build"}
        if status == "BLOCKED":
            lane["reason"] = "platform_module_not_installed"
        else:
            lane["compiler_cleanliness"] = {"count": 0, "diagnostics": [], "schema_version": 1, "status": "PASS"}
            lane["stages"] = {"compile": "PASS", "player_build": "PASS", "player_run": "NOT_RUN", "tests": "NOT_RUN"}
        lanes.append(lane)
        rows.append(
            {
                "line": line,
                "target": target,
                "backend": backends[target],
                "unity_version": version,
                "required_stages": ["compile", "player_build"],
                "status": "PASS" if status != "BLOCKED" else "BLOCKED",
            }
        )
    return {
        "schema_version": acceptance.CONSUMER_VERDICT_SCHEMA_VERSION,
        "status": "BLOCKED",
        "version": "9.9.9",
        "completed_at_utc": "2026-09-21T14:35:18Z",
        "impact": {"digests": {"executable_content_sha256": "d" * 64, "package_content_sha256": "e" * 64}},
        "required_checks": [
            "android",
            "artifact",
            "asset_store_validator",
            "compatibility",
            "host_unit_tests",
            "lifecycle_tests",
            "package_static_contracts",
            "publisher_account",
            "router_check",
            "sample_e2e",
            "toolchain_preflight",
            "unity_matrix",
        ],
        "checks": {
            "unity_matrix": {"status": "BLOCKED", "lanes": lanes},
            "compatibility": {"status": "BLOCKED", "rows": rows, "claim": "exact rows only"},
            "sample_e2e": {
                "status": "PASS",
                "lanes": [
                    {
                        "line": "2022.3 LTS",
                        "input_mode": mode,
                        "unity_version": "2022.3.1f1",
                        "target": "StandaloneOSX",
                        "backend": "Mono2x",
                        "status": "PASS",
                        "compiler_cleanliness": {"count": 0, "status": "PASS"},
                        "editor_playmode": {"total": 1, "passed": 1, "status": "PASS"},
                        "result": {"scene": "Sample.Scene"},
                    }
                    for mode in ("legacy", "input-system")
                ],
            },
            "lifecycle_tests": {
                "status": "PASS",
                "required_editors": ["2022.3.1f1", "6000.6.1f1"],
                "rows": [
                    {"status": "PASS", "unity_version": "2022.3.1f1", "target": "StandaloneOSX"},
                    {"status": "PASS", "unity_version": "6000.6.1f1", "target": "StandaloneOSX"},
                ],
            },
            "android": {
                "status": "BLOCKED",
                "reason": "device and apk are required",
                "profiles": {name: {"status": "NOT_RUN"} for name in ("runtime-smoke", "performance", "network-transitions")},
            },
            "artifact": {"status": "PASS", "artifact": {"sha256": "f" * 64, "source_identity": {"dirty_paths": [], "revision": "0" * 40}}},
            "asset_store_validator": {"status": "PASS"},
            "host_unit_tests": {"status": "PASS"},
            "package_static_contracts": {"status": "PASS"},
            "publisher_account": {"status": "BLOCKED", "reason": "confirm the publisher account"},
            "router_check": {"status": "PASS"},
            "toolchain_preflight": {"status": "PASS"},
        },
    }


class SchemaContractTests(unittest.TestCase):
    def test_schema_files_match_generated_specs(self) -> None:
        for name in acceptance.SCHEMA_DOCUMENTS:
            with self.subTest(schema=name):
                on_disk = json.loads((TEMPLATES_DIR / "workflows" / name).read_text(encoding="utf-8"))
                self.assertEqual(acceptance.schema_document(name), on_disk)

    def test_existing_evidence_summary_schema_is_untouched(self) -> None:
        document = json.loads((TEMPLATES_DIR / "workflows" / "evidence_summary.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("xuunity.light-mcp.evidence.v1", document["properties"]["schemaVersion"]["const"])
        self.assertFalse(document["additionalProperties"])
        self.assertEqual(
            ["schemaVersion", "workflowId", "projectRoot", "verdict", "checks", "validationGaps"],
            document["required"],
        )
        self.assertEqual(
            {"schemaVersion", "workflowId", "projectRoot", "unityVersion", "packageVersion", "packageSourceMode", "verdict", "checks", "artifacts", "validationGaps", "hostEditorRestored", "residualRisk"},
            set(document["properties"]),
        )
        for template in ("readiness_gate", "post_change_validation", "package_mode_switch"):
            workflow = json.loads((TEMPLATES_DIR / "workflows" / f"{template}.workflow.json").read_text(encoding="utf-8"))
            self.assertEqual("templates/workflows/evidence_summary.schema.json", workflow["closeoutSchema"])

    def test_unknown_schema_version_duplicate_ids_and_unknown_keys_are_invalid(self) -> None:
        with self.assertRaises(acceptance.ValidationInputError) as raised:
            acceptance.validate_plan({**plan(requirement("r1")), "schemaVersion": "xuunity.light-mcp.validation-plan.v2"})
        self.assertEqual("unknown_schema_version", raised.exception.code)
        with self.assertRaises(acceptance.ValidationInputError) as raised:
            acceptance.validate_plan(plan(requirement("r1"), requirement("r1")))
        self.assertEqual("duplicate_id", raised.exception.code)
        with self.assertRaises(acceptance.ValidationInputError) as raised:
            acceptance.validate_plan(plan(requirement("r1", surprise=True)))
        self.assertEqual("schema_violation", raised.exception.code)
        with self.assertRaises(acceptance.ValidationInputError):
            acceptance.validate_plan(plan(requirement("r1", stage="apk")))
        with self.assertRaises(acceptance.ValidationInputError) as raised:
            acceptance.validate_receipts(receipts({k: v for k, v in receipt("x", "r1", {"path": "e", "sha256": "0"}).items() if k != "operationOutcome"}))
        self.assertIn("raw receipts must carry", raised.exception.message)

    def test_reason_codes_are_closed_set(self) -> None:
        source = (RUNNER_DIR / "validation_acceptance.py").read_text(encoding="utf-8")
        for code in acceptance.REASON_CODES:
            self.assertIn(f'"{code}"', source)


class EvaluationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_at01_compile_warning_fails_zero_warning_policy(self) -> None:
        ref = evidence(self.root, "compile.json", compile_response(warning_count=1))
        report = run_eval(
            plan(requirement("compile", policy={"warningBudget": 0})),
            receipts(receipt("c", "compile", ref, evidenceKind="helper_response")),
            self.root,
        )
        row = report["rows"][0]
        self.assertEqual("passed", row["operationOutcome"])
        self.assertEqual("fail", row["outcome"])
        self.assertIn("warning_budget_exceeded", row["reasons"])
        self.assertEqual(["payload_json.result", "payload_json.completion_basis", "payload_json.post_settle_error_count"], row["provenance"]["fieldPaths"])
        self.assertEqual("fail", report["verdict"])

    def test_helper_measurements_cannot_be_overridden_by_receipt_metadata(self) -> None:
        post_settle = compile_response()
        payload = json.loads(post_settle["payload_json"])
        payload["post_settle_error_count"] = 1
        post_settle["payload_json"] = json.dumps(payload)
        cases = [
            ("warnings", compile_response(warning_count=1), "compile",
             {"warningBudget": 0}, "fail", "warning_budget_exceeded"),
            ("warnings_missing", compile_response(warning_count=None), "compile",
             {"warningBudget": 0}, "blocked", "diagnostics_unmeasured"),
            ("cached", compile_response(rebuilt=0), "compile",
             {"requireMeasuredRebuild": True}, "blocked", "rebuild_cached_only"),
            ("unmeasured", compile_response(rebuild_status="unavailable"), "compile",
             {"requireMeasuredRebuild": True}, "blocked", "rebuild_unmeasured"),
            ("settle", post_settle, "compile", {}, "fail", "post_settle_errors"),
            ("minimum", tests_response(), "playmode",
             {"minTests": 2}, "fail", "test_count_insufficient"),
            ("failed_count", tests_response(failed=1), "playmode",
             {}, "fail", "test_verdict_not_passed"),
            ("timeout", tests_response(verdict="runtime_timeout"), "playmode",
             {}, "blocked", "runtime_timeout"),
        ]
        for name, response, stage, policy, outcome, reason in cases:
            with self.subTest(name=name):
                ref = evidence(self.root, name + ".json", response)
                report = run_eval(
                    plan(requirement("r", stage=stage, policy=policy)),
                    receipts(receipt(
                        "c", "r", ref, stage=stage, evidenceKind="helper_response",
                        diagnostics={"scope": "package", "complete": True, "warningCount": 0},
                        rebuild={"status": "measured", "rebuiltAssemblyCount": 99},
                        tests={"verdict": "passed", "total": 99, "failed": 0, "postSettleErrorCount": 0},
                        executionBlocker={"code": "receipt_override"},
                    )),
                    self.root,
                )
                self.assertEqual(outcome, report["rows"][0]["outcome"])
                self.assertIn(reason, report["rows"][0]["reasons"])
                self.assertEqual(1, report["required"]["total"])
                self.assertEqual(1, acceptance.exit_code_for(report))

    def test_helper_success_ignores_stale_receipt_measurements(self) -> None:
        ref = evidence(self.root, "clean.json", compile_response())
        report = run_eval(
            plan(requirement("r", policy={"warningBudget": 0, "requireMeasuredRebuild": True})),
            receipts(receipt(
                "c", "r", ref, evidenceKind="helper_response", outcome="failed",
                diagnostics={"scope": "all", "complete": True, "warningCount": 9},
                rebuild={"status": "unavailable"},
                tests={"verdict": "failed", "postSettleErrorCount": 9},
            )),
            self.root,
        )
        self.assertEqual("pass", report["verdict"])

    def test_at02_missing_or_incomplete_warning_counts_block_cleanliness(self) -> None:
        ref = evidence(self.root, "raw.json", {"ok": True})
        for diagnostics in (None, {"scope": "all", "complete": False, "warningCount": None}, {"scope": "all", "complete": True, "warningCount": None}):
            with self.subTest(diagnostics=diagnostics):
                report = run_eval(
                    plan(requirement("compile", policy={"warningBudget": 0})),
                    receipts(receipt("c", "compile", ref, diagnostics=diagnostics)),
                    self.root,
                )
                self.assertEqual("blocked", report["rows"][0]["outcome"])
                self.assertEqual(["diagnostics_unmeasured"], report["rows"][0]["reasons"])

    def test_at02b_package_cleanliness_needs_ownership_when_global_warnings_exist(self) -> None:
        ref = evidence(self.root, "raw.json", {"ok": True})
        base = plan(requirement("compile", policy={"warningBudget": 0, "diagnosticsScope": "package"}))
        zero = run_eval(base, receipts(receipt("c", "compile", ref, diagnostics={"scope": "all", "complete": True, "warningCount": 0})), self.root)
        self.assertEqual("pass", zero["rows"][0]["outcome"])
        noisy = run_eval(base, receipts(receipt("c", "compile", ref, diagnostics={"scope": "all", "complete": True, "warningCount": 3})), self.root)
        self.assertEqual("blocked", noisy["rows"][0]["outcome"])
        self.assertEqual(["diagnostics_unmeasured"], noisy["rows"][0]["reasons"])

    def test_at03_unmeasured_or_cached_only_rebuild_blocks_when_required(self) -> None:
        cases = {
            "rebuilt_only_cache_status_unavailable": ("rebuild_unmeasured", 3),
            "measured": ("rebuild_cached_only", 0),
        }
        for status, (code, rebuilt) in cases.items():
            with self.subTest(status=status):
                ref = evidence(self.root, f"{status}.json", compile_response(rebuild_status=status, rebuilt=rebuilt))
                report = run_eval(
                    plan(requirement("compile", policy={"requireMeasuredRebuild": True})),
                    receipts(receipt("c", "compile", ref, evidenceKind="helper_response")),
                    self.root,
                )
                self.assertEqual("blocked", report["rows"][0]["outcome"])
                self.assertEqual([code], report["rows"][0]["reasons"])

    def test_at04_outer_ok_with_failed_or_zero_tests_never_passes(self) -> None:
        for verdict in ("failed", "test_filter_no_match", "no_tests"):
            with self.subTest(verdict=verdict):
                ref = evidence(self.root, f"{verdict}.json", tests_response(verdict=verdict, total=0 if verdict != "failed" else 1, passed=0, failed=1 if verdict == "failed" else 0))
                report = run_eval(
                    plan(requirement("play", stage="playmode")),
                    receipts(receipt("p", "play", ref, stage="playmode", evidenceKind="helper_response")),
                    self.root,
                )
                self.assertEqual("fail", report["rows"][0]["outcome"])
                self.assertIn("test_verdict_not_passed", report["rows"][0]["reasons"])

    def test_at21_runtime_timeout_blocks_and_never_passes(self) -> None:
        ref = evidence(self.root, "timeout.json", tests_response(verdict="runtime_timeout", total=0, passed=0))
        report = run_eval(plan(requirement("play", stage="playmode")), receipts(receipt("p", "play", ref, stage="playmode", evidenceKind="helper_response")), self.root)
        self.assertEqual("blocked", report["rows"][0]["outcome"])
        self.assertEqual(["runtime_timeout"], report["rows"][0]["reasons"])

    def test_passed_tests_below_minimum_are_insufficient(self) -> None:
        ref = evidence(self.root, "one.json", tests_response())
        report = run_eval(
            plan(requirement("play", stage="playmode", policy={"minTests": 2})),
            receipts(receipt("p", "play", ref, stage="playmode", evidenceKind="helper_response")),
            self.root,
        )
        self.assertEqual("fail", report["rows"][0]["outcome"])
        self.assertEqual(["test_count_insufficient"], report["rows"][0]["reasons"])

    def test_at05_build_receipt_cannot_satisfy_device_runtime_row(self) -> None:
        ref = evidence(self.root, "build.json", {"apk": "built"})
        report = run_eval(
            plan(requirement("device", stage="device-runtime")),
            receipts(receipt("b", "device", ref, stage="build")),
            self.root,
        )
        self.assertEqual("blocked", report["rows"][0]["outcome"])
        self.assertEqual(["stage_mismatch"], report["rows"][0]["reasons"])
        helper = evidence(self.root, "compile.json", compile_response())
        report = run_eval(
            plan(requirement("play", stage="playmode")),
            receipts(receipt("h", "play", helper, stage="playmode", evidenceKind="helper_response")),
            self.root,
        )
        self.assertEqual(["stage_mismatch"], report["rows"][0]["reasons"])

    def test_at06_at20_native_row_requires_client_receipt_file(self) -> None:
        ref = evidence(self.root, "helper.json", {"status": "ok"})
        native_plan = plan(requirement("native", stage="client-integration", channel="native-mcp"))
        cli_labelled = run_eval(native_plan, receipts(receipt("n", "native", ref, stage="client-integration", channel="helper-cli")), self.root)
        self.assertEqual(["channel_unverified"], cli_labelled["rows"][0]["reasons"])
        relabelled = run_eval(native_plan, receipts(receipt("n", "native", ref, stage="client-integration", channel="native-mcp")), self.root)
        self.assertEqual(["channel_unverified"], relabelled["rows"][0]["reasons"])
        good_client = evidence(self.root, "client.json", {"capture": {"client_name": "test client"}, "tool_result": {"mcp_server_info": {"version": "0.3.78"}, "client_kind": "mcp_server"}})
        verified = run_eval(native_plan, receipts(receipt("n", "native", ref, stage="client-integration", channel="native-mcp", clientReceiptRef=good_client)), self.root)
        self.assertEqual("pass", verified["rows"][0]["outcome"])
        cli_client = evidence(self.root, "cli-client.json", {"mcp_server_info": {"version": "0.3.78"}, "client_kind": "cli"})
        rejected = run_eval(native_plan, receipts(receipt("n", "native", ref, stage="client-integration", channel="native-mcp", clientReceiptRef=cli_client)), self.root)
        self.assertEqual(["channel_unverified"], rejected["rows"][0]["reasons"])
        healthy_helper = evidence(self.root, "readiness.json", {"health_status": "healthy", "client_kind": "cli"})
        unproven = run_eval(native_plan, receipts(receipt("n", "native", ref, stage="client-integration", channel="native-mcp", clientReceiptRef=healthy_helper)), self.root)
        self.assertEqual(["channel_unverified"], unproven["rows"][0]["reasons"])

    def test_channel_mismatch_blocks_non_native_rows_unless_any(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        strict = run_eval(plan(requirement("c", channel="direct-unity")), receipts(receipt("r", "c", ref, channel="helper-cli")), self.root)
        self.assertEqual(["channel_unverified"], strict["rows"][0]["reasons"])
        loose = run_eval(plan(requirement("c", channel="any")), receipts(receipt("r", "c", ref, channel="helper-cli")), self.root)
        self.assertEqual("pass", loose["rows"][0]["outcome"])

    def test_at08_dimension_scene_and_lane_mismatch_block(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        other = dict(DIMS, unityVersion="2022.3.62f3")
        report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", ref, dimensions=other)), self.root)
        self.assertEqual(["dimension_mismatch"], report["rows"][0]["reasons"])
        report = run_eval(plan(requirement("c", stage="playmode", scene="Assets/Sample.unity")), receipts(receipt("r", "c", ref, stage="playmode", scene="Assets/Other.unity", tests={"verdict": "passed"})), self.root)
        self.assertEqual(["scene_mismatch"], report["rows"][0]["reasons"])
        report = run_eval(plan(requirement("c", executionLane="batch")), receipts(receipt("r", "c", ref, executionLane="gui")), self.root)
        self.assertEqual(["dimension_mismatch"], report["rows"][0]["reasons"])

    def test_at09_deleted_or_changed_artifact_blocks_deliverability_only(self) -> None:
        ref = evidence(self.root, "build.json", {"built": True})
        artifact_path = self.root / "out" / "app.apk"
        artifact_path.parent.mkdir()
        artifact_path.write_bytes(b"apk-bytes")
        artifact = {"path": "out/app.apk", "sha256": acceptance.sha256_file(artifact_path)}
        build_plan = plan(requirement("build", stage="build", artifactRequired=True))
        good = run_eval(build_plan, receipts(receipt("b", "build", ref, stage="build", artifact=artifact)), self.root)
        self.assertEqual("pass", good["rows"][0]["outcome"])
        artifact_path.write_bytes(b"replaced")
        changed = run_eval(build_plan, receipts(receipt("b", "build", ref, stage="build", artifact=artifact)), self.root)
        self.assertEqual("blocked", changed["rows"][0]["outcome"])
        self.assertEqual(["artifact_changed"], changed["rows"][0]["reasons"])
        self.assertEqual("passed", changed["rows"][0]["operationOutcome"])
        artifact_path.unlink()
        missing = run_eval(build_plan, receipts(receipt("b", "build", ref, stage="build", artifact=artifact)), self.root)
        self.assertEqual(["artifact_missing"], missing["rows"][0]["reasons"])
        absent = run_eval(build_plan, receipts(receipt("b", "build", ref, stage="build")), self.root)
        self.assertEqual(["artifact_missing"], absent["rows"][0]["reasons"])

    def test_at10_source_identity_mismatch_blocks_old_receipts(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", ref, sourceIdentity=OTHER_SOURCE)), self.root)
        self.assertEqual(["source_identity_mismatch"], report["rows"][0]["reasons"])
        self.assertEqual("blocked", report["verdict"])

    def test_at11_conflicting_receipts_need_pin_or_supersedes(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        first = receipt("r1", "c", ref, outcome="failed")
        second = receipt("r2", "c", ref)
        conflict = run_eval(plan(requirement("c")), receipts(first, second), self.root)
        self.assertEqual("blocked", conflict["rows"][0]["outcome"])
        self.assertEqual(["receipt_conflict"], conflict["rows"][0]["reasons"])
        self.assertEqual(["r1", "r2"], conflict["rows"][0]["matchedReceiptIds"])
        superseding = run_eval(plan(requirement("c")), receipts(first, {**second, "supersedes": ["r1"]}), self.root)
        self.assertEqual("pass", superseding["rows"][0]["outcome"])
        self.assertEqual(["r2"], superseding["rows"][0]["matchedReceiptIds"])
        pinned = run_eval(plan(requirement("c", receiptId="r1")), receipts(first, second), self.root)
        self.assertEqual("fail", pinned["rows"][0]["outcome"])

    def test_at12_required_semantic_assertion_must_pass(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        base = plan(requirement("click", stage="playmode", policy={"semanticAssertions": ["popup_state_changed"]}))
        delivered_only = run_eval(base, receipts(receipt("r", "click", ref, stage="playmode", tests={"verdict": "passed"}, semanticAssertions=[{"name": "popup_state_changed", "passed": False}])), self.root)
        self.assertEqual("fail", delivered_only["rows"][0]["outcome"])
        self.assertEqual(["semantic_assertion_failed"], delivered_only["rows"][0]["reasons"])
        absent = run_eval(base, receipts(receipt("r", "click", ref, stage="playmode", tests={"verdict": "passed"})), self.root)
        self.assertEqual(["semantic_assertion_failed"], absent["rows"][0]["reasons"])
        proven = run_eval(base, receipts(receipt("r", "click", ref, stage="playmode", tests={"verdict": "passed"}, semanticAssertions=[{"name": "popup_state_changed", "passed": True}])), self.root)
        self.assertEqual("pass", proven["rows"][0]["outcome"])

    def test_at13_portable_paths_and_escaping_paths(self) -> None:
        ref = evidence(self.root, os.path.join("evidence dir", "ünïcode file.json"), {"ok": 1})
        report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", ref)), self.root)
        self.assertEqual("pass", report["rows"][0]["outcome"])
        outside_root = self.root.parent / f"{self.root.name}-outside"
        outside_root.mkdir()
        try:
            outside_file = outside_root / "outside.json"
            write_json(outside_file, {"ok": 1})
            traversal = {"path": os.path.join("..", outside_root.name, "outside.json"), "sha256": acceptance.sha256_file(outside_file)}
            report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", traversal)), self.root)
            self.assertEqual(["evidence_outside_roots"], report["rows"][0]["reasons"])
            link = self.root / "link.json"
            try:
                link.symlink_to(outside_file)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this host")
            report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", {"path": "link.json", "sha256": traversal["sha256"]})), self.root)
            self.assertEqual(["evidence_outside_roots"], report["rows"][0]["reasons"])
        finally:
            for child in outside_root.iterdir():
                child.unlink()
            outside_root.rmdir()
        missing = run_eval(plan(requirement("c")), receipts(receipt("r", "c", {"path": "nope.json", "sha256": "0" * 64})), self.root)
        self.assertEqual(["evidence_missing"], missing["rows"][0]["reasons"])
        tampered = run_eval(plan(requirement("c")), receipts(receipt("r", "c", {**ref, "sha256": "0" * 64})), self.root)
        self.assertEqual(["evidence_changed"], tampered["rows"][0]["reasons"])

    def test_at14_compact_envelope_holds_the_byte_budget_and_full_report_keeps_rows(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        count = 3000
        rows = [requirement(f"row-{index}", stage="build") for index in range(count)]
        blocked = [receipt(f"r-{index}", f"row-{index}", ref, stage="build", outcome="blocked", executionBlocker={"code": "platform_module_not_installed", "message": "x" * 500}) for index in range(count)]
        report = run_eval(plan(*rows), receipts(*blocked), self.root)
        self.assertEqual(count, report["required"]["total"])
        self.assertEqual(count, report["required"]["blocked"])
        envelope = acceptance.compact_envelope(report, exit_code=1, report_path="report.json")
        encoded = _bounded_compact_json(envelope)
        self.assertLessEqual(len(encoded.encode("utf-8")), COMPACT_OUTPUT_MAX_BYTES)
        decoded = json.loads(encoded)
        self.assertEqual("compact_validation_acceptance", decoded["payload_mode"])
        self.assertEqual(count, decoded["required"]["total"])
        self.assertTrue(decoded["reasons_truncated"])
        self.assertEqual(acceptance.COMPACT_REASON_ROWS, len(decoded["first_reasons"]))

    def test_reused_receipts_stay_visible_and_counted(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        report = run_eval(plan(requirement("c")), receipts(receipt("r", "c", ref, reused=True, originalRunAt="2026-09-20T10:00:00Z")), self.root)
        self.assertEqual("pass", report["rows"][0]["outcome"])
        self.assertTrue(report["rows"][0]["reused"])
        self.assertEqual("2026-09-20T10:00:00Z", report["rows"][0]["originalRunAt"])
        self.assertEqual(1, report["reusedCount"])

    def test_aggregation_precedence_and_optional_rows(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        document = plan(requirement("a"), requirement("b"), requirement("c"), requirement("opt", required=False))
        report = run_eval(document, receipts(receipt("ra", "a", ref), receipt("rb", "b", ref, outcome="blocked", executionBlocker={"code": "no_device"})), self.root)
        self.assertEqual("blocked", report["verdict"])
        self.assertEqual({"total": 3, "pass": 1, "fail": 0, "blocked": 1, "not_run": 1}, report["required"])
        self.assertEqual({"total": 1, "pass": 0, "fail": 0, "blocked": 0, "not_run": 1}, report["optional"])
        report = run_eval(document, receipts(receipt("ra", "a", ref), receipt("rb", "b", ref), receipt("rc", "c", ref)), self.root)
        self.assertEqual("pass", report["verdict"])
        report = run_eval(document, receipts(receipt("ra", "a", ref), receipt("rb", "b", ref, outcome="failed"), receipt("rc", "c", ref, outcome="blocked")), self.root)
        self.assertEqual("fail", report["verdict"])
        report = run_eval(document, receipts(receipt("ra", "a", ref), receipt("rb", "b", ref)), self.root)
        self.assertEqual("partial", report["verdict"])

    def test_evaluation_is_deterministic(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        document = plan(requirement("a"), requirement("b"))
        rows = receipts(receipt("ra", "a", ref), receipt("rb", "b", ref, outcome="failed"))
        first = run_eval(document, rows, self.root)
        second = run_eval(copy.deepcopy(document), copy.deepcopy(rows), self.root)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


class HelperResponseAdapterTests(unittest.TestCase):
    def test_compile_response_fields_come_from_decoded_payload_result(self) -> None:
        normalized = acceptance.normalize_helper_response(compile_response(warning_count=2, rebuild_status="measured", rebuilt=45))
        self.assertEqual("compile", normalized["stage"])
        self.assertEqual("passed", normalized["operationOutcome"])
        self.assertEqual(2, normalized["diagnostics"]["warningCount"])
        self.assertTrue(normalized["diagnostics"]["complete"])
        self.assertEqual("measured", normalized["rebuild"]["status"])
        self.assertEqual(45, normalized["rebuild"]["rebuiltAssemblyCount"])
        self.assertEqual("unity_compile_settle_watcher|bridge_response|tcp_loopback", normalized["producer"]["route"])

    def test_outer_ok_does_not_override_failed_payload(self) -> None:
        normalized = acceptance.normalize_helper_response(compile_response(status="failed"))
        self.assertEqual("failed", normalized["operationOutcome"])
        normalized = acceptance.normalize_helper_response(tests_response(verdict="failed", failed=1))
        self.assertEqual("failed", normalized["operationOutcome"])
        self.assertEqual("failed", normalized["tests"]["verdict"])

    def test_missing_payload_is_blocked_with_error_code(self) -> None:
        normalized = acceptance.normalize_helper_response({"status": "error", "payload_type": "unity.tests.run_editmode", "payload_json": "", "error": {"code": "bridge_unavailable", "message": "no editor"}})
        self.assertEqual("blocked", normalized["operationOutcome"])
        self.assertEqual("bridge_unavailable", normalized["executionBlocker"]["code"])
        self.assertIsNone(normalized["tests"])

    def test_unknown_counts_stay_null_never_zero(self) -> None:
        response = compile_response()
        payload = json.loads(response["payload_json"])
        del payload["result"]["warning_count"]
        response["payload_json"] = json.dumps(payload)
        normalized = acceptance.normalize_helper_response(response)
        self.assertIsNone(normalized["diagnostics"]["warningCount"])
        self.assertFalse(normalized["diagnostics"]["complete"])


class ConsumerVerdictAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.verdict = synthetic_consumer_verdict()
        self.verdict_path = self.root / "release-verdict.json"
        write_json(self.verdict_path, self.verdict)
        self.ref = {"path": "release-verdict.json", "sha256": acceptance.sha256_file(self.verdict_path)}

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def derive(self):
        return acceptance.derive_from_consumer_verdict(self.verdict, project_id="consumer", plan_id="derived", verdict_ref=self.ref)

    def test_at07_forty_matrix_rows_keep_their_denominator_and_reuse(self) -> None:
        plan_document, receipts_document = self.derive()
        report = run_eval(plan_document, receipts_document, self.root)
        matrix = [row for row in report["rows"] if row["requirementId"].startswith("matrix:")]
        self.assertEqual(40, len(matrix))
        self.assertEqual(23, sum(row["outcome"] == "pass" for row in matrix))
        self.assertEqual(15, sum(row["outcome"] == "pass" and row["reused"] for row in matrix))
        self.assertEqual(17, sum(row["outcome"] == "blocked" for row in matrix))
        self.assertTrue(all(row["reasons"] == ["capability_unavailable"] for row in matrix if row["outcome"] == "blocked"))
        self.assertEqual(15, report["reusedCount"])
        self.assertEqual("blocked", report["verdict"])
        self.assertEqual(report["required"]["total"], sum(report["required"][key] for key in ("pass", "fail", "blocked", "not_run")))
        by_id = {row["requirementId"]: row for row in report["rows"]}
        self.assertEqual("pass", by_id["sample:2022.3 LTS:legacy"]["outcome"])
        self.assertEqual("Sample.Scene", by_id["sample:2022.3 LTS:legacy"]["scene"])
        self.assertEqual("pass", by_id["lifecycle:2022.3.1f1"]["outcome"])
        self.assertEqual("helper-cli", by_id["lifecycle:2022.3.1f1"]["executionChannel"])
        self.assertEqual("blocked", by_id["android:runtime-smoke"]["outcome"])
        self.assertEqual("device-runtime", by_id["android:runtime-smoke"]["stage"])
        self.assertEqual("blocked", by_id["check:publisher_account"]["outcome"])
        self.assertEqual("resolve", by_id["check:toolchain_preflight"]["stage"])
        self.assertEqual("export", by_id["matrix:6000.0:iOS"]["stage"])
        self.assertEqual("build", by_id["matrix:6000.0:Android"]["stage"])

    def test_missing_required_lifecycle_editor_is_not_run(self) -> None:
        self.verdict["checks"]["lifecycle_tests"]["rows"].pop()
        plan_document, receipts_document = self.derive()
        report = run_eval(plan_document, receipts_document, self.root)
        row = next(row for row in report["rows"] if row["requirementId"] == "lifecycle:6000.6.1f1")
        self.assertEqual("not_run", row["outcome"])
        self.assertEqual(["receipt_missing"], row["reasons"])

    def test_native_client_check_maps_to_native_row(self) -> None:
        client = evidence(self.root, "native-receipt.json", {"capture": {"client_name": "client"}, "tool_result": {"mcp_server_info": {"version": "0.3.78"}, "client_kind": "mcp_server"}})
        self.verdict["checks"]["native_client_receipt"] = {"status": "PASS", "client_kind": "mcp_server", "receipt": client}
        plan_document, receipts_document = self.derive()
        report = run_eval(plan_document, receipts_document, self.root)
        row = next(row for row in report["rows"] if row["requirementId"] == "check:native_client_receipt")
        self.assertEqual("pass", row["outcome"])
        self.assertFalse(row["required"])
        self.assertEqual("native-mcp", row["executionChannel"])
        self.verdict["checks"]["native_client_receipt"] = {"status": "BLOCKED", "reason": "no receipt supplied"}
        plan_document, receipts_document = self.derive()
        report = run_eval(plan_document, receipts_document, self.root)
        row = next(row for row in report["rows"] if row["requirementId"] == "check:native_client_receipt")
        self.assertEqual("blocked", row["outcome"])

    def test_unknown_consumer_schema_is_invalid_input(self) -> None:
        self.verdict["schema_version"] = "foxsterlabs.ccp.release-verdict.v3"
        with self.assertRaises(acceptance.ValidationInputError) as raised:
            self.derive()
        self.assertEqual("unknown_schema_version", raised.exception.code)


class CliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def invoke(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.run(cli.build_parser().parse_args(list(argv)))
        return code, output.getvalue()

    def test_plan_and_receipts_produce_report_and_compact_envelope(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        write_json(self.root / "plan.json", plan(requirement("a"), requirement("b", stage="device-runtime")))
        write_json(self.root / "receipts.json", receipts(receipt("ra", "a", ref)))
        report_path = self.root / "out" / "report.json"
        code, output = self.invoke("--plan", str(self.root / "plan.json"), "--receipts", str(self.root / "receipts.json"), "--report", str(report_path))
        self.assertEqual(1, code)
        envelope = json.loads(output)
        self.assertEqual("compact_validation_acceptance", envelope["payload_mode"])
        self.assertEqual("partial", envelope["verdict"])
        self.assertEqual({"total": 2, "pass": 1, "fail": 0, "blocked": 0, "not_run": 1}, envelope["required"])
        self.assertEqual("--output full", envelope["full_payload_cli_argument"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        acceptance.validate_acceptance_report(report)
        self.assertEqual(acceptance.sha256_file(self.root / "plan.json"), report["planSha256"])
        code, output = self.invoke("--plan", str(self.root / "plan.json"), "--receipts", str(self.root / "receipts.json"), "--report", str(report_path), "--output", "full")
        self.assertEqual(1, code)
        self.assertEqual(2, len(json.loads(output)["rows"]))

    def test_accepted_plan_exits_zero(self) -> None:
        ref = evidence(self.root, "e.json", {"ok": 1})
        write_json(self.root / "plan.json", plan(requirement("a")))
        write_json(self.root / "receipts.json", receipts(receipt("ra", "a", ref)))
        code, output = self.invoke("--plan", str(self.root / "plan.json"), "--receipts", str(self.root / "receipts.json"), "--report", str(self.root / "report.json"))
        self.assertEqual(0, code)
        self.assertEqual("accepted", json.loads(output)["recommended_next_action"])

    def test_at19_at22_invalid_inputs_exit_two_with_bounded_envelope(self) -> None:
        report_path = self.root / "report.json"
        cases = {
            "missing": (self.root / "absent.json", None),
            "malformed": (self.root / "broken.json", "{not json"),
            "unknown_schema": (self.root / "unknown.json", json.dumps({**plan(requirement("a")), "schemaVersion": "nope"})),
            "duplicate": (self.root / "dup.json", json.dumps(plan(requirement("a"), requirement("a")))),
        }
        write_json(self.root / "receipts.json", receipts())
        for name, (path, content) in cases.items():
            with self.subTest(case=name):
                if content is not None:
                    path.write_text(content, encoding="utf-8")
                code, output = self.invoke("--plan", str(path), "--receipts", str(self.root / "receipts.json"), "--report", str(report_path))
                self.assertEqual(2, code)
                envelope = json.loads(output)
                self.assertEqual("evaluation_invalid", envelope["reason"])
                self.assertEqual(2, envelope["exit_code"])
                self.assertNotIn("required", envelope)
                self.assertLessEqual(len(output.encode("utf-8")), COMPACT_OUTPUT_MAX_BYTES)
                self.assertFalse(report_path.exists())
        write_json(self.root / "plan.json", plan(requirement("a")))
        with mock.patch.object(acceptance, "MAX_INPUT_BYTES", 16):
            code, output = self.invoke("--plan", str(self.root / "plan.json"), "--receipts", str(self.root / "receipts.json"), "--report", str(report_path))
        self.assertEqual(2, code)
        self.assertEqual("input_too_large", json.loads(output)["error"]["code"])
        code, output = self.invoke("--plan", str(self.root / "plan.json"), "--report", str(report_path))
        self.assertEqual(2, code)
        self.assertEqual("missing_input", json.loads(output)["error"]["code"])

    def test_consumer_verdict_route_writes_derived_inputs_beside_report(self) -> None:
        verdict_path = self.root / "release-verdict.json"
        write_json(verdict_path, synthetic_consumer_verdict())
        report_path = self.root / "acceptance" / "report.json"
        code, output = self.invoke("--consumer-verdict", str(verdict_path), "--report", str(report_path))
        self.assertEqual(1, code)
        envelope = json.loads(output)
        self.assertEqual("blocked", envelope["verdict"])
        self.assertEqual(15, envelope["reused_count"])
        self.assertTrue((report_path.parent / "report.derived-plan.json").is_file())
        self.assertTrue((report_path.parent / "report.derived-receipts.json").is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(acceptance.sha256_file(report_path.parent / "report.derived-plan.json"), report["planSha256"])
        code, output = self.invoke("--consumer-verdict", str(verdict_path), "--plan", str(verdict_path), "--report", str(report_path))
        self.assertEqual(2, code)
        self.assertEqual("conflicting_inputs", json.loads(output)["error"]["code"])


if __name__ == "__main__":
    unittest.main()
