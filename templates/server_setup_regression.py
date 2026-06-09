# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json, write_json
from server_batch_orchestrator import (
    run_self_json_command,
    default_batch_operation_result_path,
)
from server_project_context import (
    inspect_package_dependency_alignment,
)
from server_setup_wizard import (
    TEST_FRAMEWORK_PACKAGE_NAME,
)
from server_summaries import truncate_text

# Regression constants
TEST_FRAMEWORK_PERFORMANCE_PACKAGE_NAME = "com.unity.test-framework.performance"
LIGHTWEIGHT_PACKAGE_NAME = "com.xuunity.light-mcp"

TEST_FRAMEWORK_REGRESSION_LOCK_PACKAGES = [
    TEST_FRAMEWORK_PACKAGE_NAME,
    TEST_FRAMEWORK_PERFORMANCE_PACKAGE_NAME,
    LIGHTWEIGHT_PACKAGE_NAME,
]

TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET = "active"
TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR = (
    "Assets/XUUnityLightMcpGenerated/TestFrameworkRegression/Editor"
)
TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_FILE_NAME = (
    "XUUnityLightMcpTestFrameworkRegressionSelfTest.cs"
)
TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME = (
    "XUUnity.LightMcp.GeneratedTests."
    "XUUnityLightMcpTestFrameworkRegressionSelfTest.FrameworkSmokePasses"
)
TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_SOURCE = """using NUnit.Framework;

namespace XUUnity.LightMcp.GeneratedTests
{
    public sealed class XUUnityLightMcpTestFrameworkRegressionSelfTest
    {
        [Test]
        public void FrameworkSmokePasses()
        {
            Assert.That(1 + 1, Is.EqualTo(2));
        }
    }
}
"""


def test_framework_regression_result_path(project_root: Path) -> Path:
    return default_batch_operation_result_path(project_root, "test_framework_version_regression")


def test_framework_regression_artifacts_dir(result_path: Path) -> Path:
    suffix = result_path.suffix or ".json"
    stem = result_path.stem if result_path.suffix else result_path.name
    return result_path.with_name(f"{stem}_artifacts")


def normalize_requested_versions(raw_versions: list[str], versions_file: str | None) -> list[str]:
    versions: list[str] = []

    for raw_version in raw_versions:
        version = str(raw_version or "").strip()
        if version:
            versions.append(version)

    if versions_file:
        path = Path(versions_file).expanduser().resolve()
        if not path.is_file():
            raise ToolInvocationError(
                "versions_file_not_found",
                f"Version file not found: {path}",
            )

        text = path.read_text(encoding="utf-8")
        parsed_versions: list[str] = []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, list):
            parsed_versions = [str(item).strip() for item in payload]
        else:
            parsed_versions = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        versions.extend(version for version in parsed_versions if version)

    deduped: list[str] = []
    seen: set[str] = set()
    for version in versions:
        if version in seen:
            continue
        seen.add(version)
        deduped.append(version)
    return deduped


def version_slug(version: str) -> str:
    result = []
    for character in str(version or "").strip():
        if character.isalnum():
            result.append(character)
        else:
            result.append("_")
    return "".join(result).strip("_") or "unknown"


def read_declared_dependency_version(path: Path, package_name: str) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError(
            "dependency_file_unreadable",
            f"Could not read dependency file: {path}. {exc}",
        ) from exc

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ToolInvocationError(
            "dependency_missing",
            f"Dependencies object not found in: {path}",
        )

    value = dependencies.get(package_name)
    if not isinstance(value, str) or not value.strip():
        raise ToolInvocationError(
            "dependency_missing",
            f"{package_name} is not declared in: {path}",
        )

    return value.strip()


def write_declared_dependency_version(path: Path, package_name: str, version: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError(
            "dependency_file_unreadable",
            f"Could not update dependency file: {path}. {exc}",
        ) from exc

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ToolInvocationError(
            "dependency_missing",
            f"Dependencies object not found in: {path}",
        )

    dependencies[package_name] = version
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def remove_lock_dependencies(path: Path, package_names: list[str]) -> list[str]:
    if not path.is_file():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError(
            "packages_lock_unreadable",
            f"Could not update packages-lock.json: {path}. {exc}",
        ) from exc

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        return []

    removed: list[str] = []
    for package_name in package_names:
        if package_name in dependencies:
            del dependencies[package_name]
            removed.append(package_name)

    if removed:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return removed


def read_locked_dependency_state(path: Path, package_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "package_name": package_name,
        "present": False,
        "version": "",
        "source": "",
        "depth": None,
    }
    if not path.is_file():
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["error"] = f"Could not read: {path}"
        return result

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        return result

    package_payload = dependencies.get(package_name)
    if not isinstance(package_payload, dict):
        return result

    result["present"] = True
    result["version"] = str(package_payload.get("version") or "")
    result["source"] = str(package_payload.get("source") or "")
    result["depth"] = package_payload.get("depth")
    return result


def read_test_framework_state(
    project_root: Path,
    project_manifest_path: Path,
    package_manifest_path: Path,
    packages_lock_path: Path,
) -> dict[str, Any]:
    return {
        "project_manifest_dependency": read_declared_dependency_version(project_manifest_path, TEST_FRAMEWORK_PACKAGE_NAME),
        "package_manifest_dependency": read_declared_dependency_version(package_manifest_path, TEST_FRAMEWORK_PACKAGE_NAME),
        "locked_test_framework": read_locked_dependency_state(packages_lock_path, TEST_FRAMEWORK_PACKAGE_NAME),
        "locked_test_framework_performance": read_locked_dependency_state(
            packages_lock_path,
            TEST_FRAMEWORK_PERFORMANCE_PACKAGE_NAME,
        ),
        "locked_lightweight_package": read_locked_dependency_state(packages_lock_path, LIGHTWEIGHT_PACKAGE_NAME),
        "package_dependency_alignment": inspect_package_dependency_alignment(project_root),
    }


def write_test_framework_step_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)


def deploy_test_framework_regression_focus_fixture(
    project_root: Path,
    relative_dir: str,
) -> dict[str, Any]:
    relative_dir = str(relative_dir or TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR).strip()
    fixture_dir = (project_root / relative_dir).resolve()
    fixture_path = fixture_dir / TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_FILE_NAME
    project_root_resolved = project_root.resolve()
    assets_root = project_root_resolved / "Assets"

    if project_root_resolved not in fixture_path.parents:
        raise ToolInvocationError(
            "generated_focus_fixture_path_outside_project",
            f"Generated focus fixture path must stay inside the Unity project: {fixture_path}",
        )
    if assets_root not in fixture_path.parents:
        raise ToolInvocationError(
            "generated_focus_fixture_path_outside_assets",
            f"Generated focus fixture path must stay under Assets: {fixture_path}",
        )

    existing_file = fixture_path.is_file()
    if existing_file:
        try:
            existing_source = fixture_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolInvocationError(
                "generated_focus_fixture_unreadable",
                f"Could not read generated focus fixture: {fixture_path}. {exc}",
            ) from exc
        if existing_source != TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_SOURCE:
            raise ToolInvocationError(
                "generated_focus_fixture_conflict",
                (
                    "Refusing to overwrite an existing project file while deploying "
                    f"the generated focus fixture: {fixture_path}"
                ),
            )

    created_directories: list[str] = []
    current = fixture_dir
    while current != project_root_resolved and current != assets_root and not current.exists():
        created_directories.append(str(current))
        current = current.parent

    fixture_dir.mkdir(parents=True, exist_ok=True)
    if not existing_file:
        fixture_path.write_text(TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_SOURCE, encoding="utf-8")

    return {
        "deployed": True,
        "relative_dir": relative_dir,
        "fixture_path": str(fixture_path),
        "test_name": TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME,
        "created_file": not existing_file,
        "created_directories": created_directories,
    }


def cleanup_test_framework_regression_focus_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    if not fixture or not bool(fixture.get("deployed")):
        return {"attempted": False}

    result: dict[str, Any] = {
        "attempted": True,
        "removed_file": False,
        "removed_meta": False,
        "removed_directories": [],
        "failed_paths": [],
    }
    fixture_path = Path(str(fixture.get("fixture_path") or ""))
    if bool(fixture.get("created_file")):
        for path in [fixture_path, Path(str(fixture_path) + ".meta")]:
            try:
                if path.is_file():
                    path.unlink()
                    if path.suffix == ".meta":
                        result["removed_meta"] = True
                    else:
                        result["removed_file"] = True
            except OSError:
                result["failed_paths"].append(str(path))

    for directory_value in list(fixture.get("created_directories") or []):
        directory = Path(str(directory_value))
        try:
            meta_path = Path(str(directory) + ".meta")
            if meta_path.is_file():
                meta_path.unlink()
            directory.rmdir()
            result["removed_directories"].append(str(directory))
        except OSError:
            pass

    return result


def decode_bridge_payload(response_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response_payload, dict):
        return {}
    payload_json = response_payload.get("payload_json")
    if not isinstance(payload_json, str) or not payload_json.strip():
        return {}
    try:
        decoded = json.loads(payload_json)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def extract_test_failure_names(payload: dict[str, Any]) -> list[str]:
    failures = payload.get("failures")
    if not isinstance(failures, list):
        return []

    names: list[str] = []
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        for key in ("name", "test_name", "fullName", "full_name"):
            value = str(failure.get(key) or "").strip()
            if value:
                names.append(value)
                break
    return names


def summarize_bridge_step(output: dict[str, Any]) -> dict[str, Any]:
    response_payload = output.get("stdout_json")
    decoded = decode_bridge_payload(response_payload if isinstance(response_payload, dict) else None)
    summary: dict[str, Any] = {
        "exit_code": output.get("exit_code"),
        "succeeded": output.get("succeeded"),
    }
    if isinstance(response_payload, dict):
        summary["transport_status"] = response_payload.get("status")
        error_payload = response_payload.get("error")
        if isinstance(error_payload, dict) and (error_payload.get("code") or error_payload.get("message")):
            summary["error"] = {
                "code": error_payload.get("code"),
                "message": error_payload.get("message"),
            }
    if decoded:
        summary["payload"] = decoded
    stderr_text = str(output.get("stderr_text") or "").strip()
    if stderr_text:
        summary["stderr_tail"] = truncate_text(stderr_text[-600:], 600)
    parse_error = str(output.get("stdout_parse_error") or "").strip()
    if parse_error:
        summary["stdout_parse_error"] = parse_error
    return summary


def summarize_editmode_step(output: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_bridge_step(output)
    payload = summary.get("payload") or {}
    if isinstance(payload, dict):
        summary["tests"] = {
            "status": payload.get("status"),
            "total": payload.get("total"),
            "passed": payload.get("passed"),
            "failed": payload.get("failed"),
            "skipped": payload.get("skipped"),
            "completion_basis": payload.get("completion_basis"),
            "failure_names": extract_test_failure_names(payload),
        }
    return summary


def summarize_compile_step(output: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_bridge_step(output)
    payload = summary.get("payload") or {}
    if isinstance(payload, dict):
        compile_payload = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        summary["compile"] = {
            "status": compile_payload.get("status"),
            "compiled_assembly_count": compile_payload.get("compiled_assembly_count"),
            "error_count": compile_payload.get("error_count"),
            "warning_count": compile_payload.get("warning_count"),
        }
    return summary


def summarize_build_target_step(output: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_bridge_step(output)
    payload = summary.get("payload") or {}
    if isinstance(payload, dict):
        summary["build_target"] = {
            "active_build_target": payload.get("active_build_target"),
            "active_build_target_group": payload.get("active_build_target_group"),
            "target_support_loaded": payload.get("target_support_loaded"),
        }
    return summary


def summarize_health_probe_step(output: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_bridge_step(output)
    payload = summary.get("payload") or {}
    report = payload.get("report") if isinstance(payload, dict) else {}
    if isinstance(report, dict):
        summary["health_probe"] = {
            "status": report.get("status"),
            "supported_operation_count": len(report.get("supported_operations") or []),
            "disabled_operation_count": len(report.get("disabled_operations") or []),
        }
    return summary


def summarize_project_refresh_step(output: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_bridge_step(output)
    payload = summary.get("payload") or {}
    if isinstance(payload, dict):
        summary["project_refresh"] = {
            "outcome": payload.get("outcome"),
            "refresh_settle_phase": payload.get("refresh_settle_phase"),
            "package_resolve_requested": payload.get("package_resolve_requested"),
            "health_probe_status": payload.get("health_probe_status"),
        }
    return summary


def summarize_batch_editmode_step(output: dict[str, Any]) -> dict[str, Any]:
    response_payload = output.get("stdout_json")
    summary: dict[str, Any] = {
        "exit_code": output.get("exit_code"),
        "succeeded": output.get("succeeded"),
    }
    if isinstance(response_payload, dict):
        summary["result_summary"] = response_payload.get("result_summary")
        summary["result_file"] = response_payload.get("result_file")
        summary["summary_file"] = response_payload.get("summary_file")
        summary["top_actionable_error"] = response_payload.get("top_actionable_error")
        result_file = response_payload.get("result_file")
        if isinstance(result_file, str) and result_file.strip():
            result_path = Path(result_file).expanduser().resolve()
            if result_path.is_file():
                try:
                    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    result_payload = None
                if isinstance(result_payload, dict):
                    tests_payload = result_payload.get("tests") or {}
                    if isinstance(tests_payload, dict):
                        summary["tests"] = {
                            "status": tests_payload.get("status"),
                            "total": tests_payload.get("total"),
                            "passed": tests_payload.get("passed"),
                            "failed": tests_payload.get("failed"),
                            "skipped": tests_payload.get("skipped"),
                            "failure_names": extract_test_failure_names(tests_payload),
                        }
    stderr_text = str(output.get("stderr_text") or "").strip()
    if stderr_text:
        summary["stderr_tail"] = truncate_text(stderr_text[-600:], 600)
    parse_error = str(output.get("stdout_parse_error") or "").strip()
    if parse_error:
        summary["stdout_parse_error"] = parse_error
    return summary


def evaluate_candidate_contract(candidate_result: dict[str, Any]) -> dict[str, Any]:
    state_after_open = candidate_result.get("state_after_open") or {}
    locked_test_framework = state_after_open.get("locked_test_framework") if isinstance(state_after_open, dict) else {}

    direct_focus = (((candidate_result.get("interactive") or {}).get("focused_editmode")) or {}).get("tests") or {}
    batch_focus = (((candidate_result.get("batch") or {}).get("focused_editmode")) or {}).get("tests") or {}
    direct_broad = (((candidate_result.get("interactive") or {}).get("broad_editmode")) or {}).get("tests") or {}
    batch_broad = (((candidate_result.get("batch") or {}).get("broad_editmode")) or {}).get("tests") or {}
    compile_summary = (((candidate_result.get("interactive") or {}).get("compile")) or {}).get("compile") or {}
    health_probe = (((candidate_result.get("interactive") or {}).get("health_probe")) or {}).get("health_probe") or {}
    project_refresh = (((candidate_result.get("interactive") or {}).get("project_refresh")) or {}).get("project_refresh") or {}

    requested_version = str(candidate_result.get("requested_version") or "")
    resolved_version = str((locked_test_framework or {}).get("version") or "")

    failures: list[str] = []
    if not requested_version or requested_version != resolved_version:
        failures.append("resolved_version_mismatch")
    if str(health_probe.get("status") or "") != "healthy":
        failures.append("health_probe_not_healthy")
    if str(project_refresh.get("outcome") or "") not in {
        "refreshed",
        "ok",
        "completed",
        "refresh_and_resolve_completed",
    }:
        failures.append("project_refresh_not_completed")
    if str(compile_summary.get("status") or "") != "passed":
        failures.append("compile_regression_failed")
    if str(direct_focus.get("status") or "") != "passed":
        failures.append("focused_direct_editmode_failed")
    if str(batch_focus.get("status") or "") != "passed":
        failures.append("focused_batch_editmode_failed")
    if direct_broad.get("total") is None:
        failures.append("broad_direct_editmode_missing")
    if batch_broad.get("total") is None:
        failures.append("broad_batch_editmode_missing")

    return {
        "requested_version": requested_version,
        "resolved_version": resolved_version,
        "broad_direct_failed": direct_broad.get("failed"),
        "broad_batch_failed": batch_broad.get("failed"),
        "focused_direct_status": direct_focus.get("status"),
        "focused_batch_status": batch_focus.get("status"),
        "compile_status": compile_summary.get("status"),
        "health_status": health_probe.get("status"),
        "project_refresh_outcome": project_refresh.get("outcome"),
        "contract_passed": len(failures) == 0,
        "contract_failures": failures,
    }


def compare_candidate_to_baseline(
    baseline_result: dict[str, Any],
    candidate_result: dict[str, Any],
) -> dict[str, Any]:
    baseline_direct = (((baseline_result.get("interactive") or {}).get("broad_editmode")) or {}).get("tests") or {}
    baseline_batch = (((baseline_result.get("batch") or {}).get("broad_editmode")) or {}).get("tests") or {}
    candidate_direct = (((candidate_result.get("interactive") or {}).get("broad_editmode")) or {}).get("tests") or {}
    candidate_batch = (((candidate_result.get("batch") or {}).get("broad_editmode")) or {}).get("tests") or {}

    baseline_direct_failures = set(baseline_direct.get("failure_names") or [])
    baseline_batch_failures = set(baseline_batch.get("failure_names") or [])
    candidate_direct_failures = set(candidate_direct.get("failure_names") or [])
    candidate_batch_failures = set(candidate_batch.get("failure_names") or [])

    return {
        "baseline_version": baseline_result.get("requested_version"),
        "direct_failed_delta": (candidate_direct.get("failed") or 0) - (baseline_direct.get("failed") or 0),
        "batch_failed_delta": (candidate_batch.get("failed") or 0) - (baseline_batch.get("failed") or 0),
        "direct_new_failures": sorted(candidate_direct_failures - baseline_direct_failures),
        "batch_new_failures": sorted(candidate_batch_failures - baseline_batch_failures),
        "direct_missing_failures": sorted(baseline_direct_failures - candidate_direct_failures),
        "batch_missing_failures": sorted(baseline_batch_failures - candidate_batch_failures),
    }


def run_single_test_framework_candidate(
    *,
    project_root: Path,
    requested_version: str,
    project_manifest_path: Path,
    package_manifest_path: Path,
    packages_lock_path: Path,
    artifacts_dir: Path,
    compile_target: str,
    focus_assemblies: list[str],
    focus_tests: list[str],
    broad_assemblies: list[str],
) -> dict[str, Any]:
    candidate_slug = version_slug(requested_version)
    candidate_dir = artifacts_dir / candidate_slug
    candidate_dir.mkdir(parents=True, exist_ok=True)

    write_declared_dependency_version(project_manifest_path, TEST_FRAMEWORK_PACKAGE_NAME, requested_version)
    write_declared_dependency_version(package_manifest_path, TEST_FRAMEWORK_PACKAGE_NAME, requested_version)
    removed_lock_entries = remove_lock_dependencies(packages_lock_path, TEST_FRAMEWORK_REGRESSION_LOCK_PACKAGES)

    result: dict[str, Any] = {
        "requested_version": requested_version,
        "candidate_slug": candidate_slug,
        "candidate_dir": str(candidate_dir),
        "removed_lock_entries": removed_lock_entries,
        "state_after_patch": read_test_framework_state(
            project_root,
            project_manifest_path,
            package_manifest_path,
            packages_lock_path,
        ),
        "interactive": {},
        "batch": {},
    }

    ensure_ready_output = run_self_json_command(
        [
            "ensure-ready",
            "--project-root",
            str(project_root),
            "--open-editor",
            "--timeout-ms",
            "180000",
        ]
    )
    write_test_framework_step_artifact(candidate_dir / "interactive_ensure_ready.json", ensure_ready_output)
    result["interactive"]["ensure_ready"] = summarize_bridge_step(ensure_ready_output)

    if ensure_ready_output.get("succeeded"):
        result["state_after_open"] = read_test_framework_state(
            project_root,
            project_manifest_path,
            package_manifest_path,
            packages_lock_path,
        )

        health_probe_output = run_self_json_command(
            [
                "request-health-probe",
                "--project-root",
                str(project_root),
                "--timeout-ms",
                "30000",
            ]
        )
        write_test_framework_step_artifact(candidate_dir / "interactive_health_probe.json", health_probe_output)
        result["interactive"]["health_probe"] = summarize_health_probe_step(health_probe_output)

        project_refresh_output = run_self_json_command(
            [
                "request-project-refresh",
                "--project-root",
                str(project_root),
                "--timeout-ms",
                "120000",
            ]
        )
        write_test_framework_step_artifact(candidate_dir / "interactive_project_refresh.json", project_refresh_output)
        result["interactive"]["project_refresh"] = summarize_project_refresh_step(project_refresh_output)

        compile_target_for_candidate = compile_target
        if compile_target_for_candidate.lower() == "active":
            build_target_output = run_self_json_command(
                [
                    "request-build-target-get",
                    "--project-root",
                    str(project_root),
                    "--timeout-ms",
                    "30000",
                ]
            )
            write_test_framework_step_artifact(candidate_dir / "interactive_build_target_get.json", build_target_output)
            result["interactive"]["build_target"] = summarize_build_target_step(build_target_output)
            build_target_payload = ((result["interactive"]["build_target"] or {}).get("build_target") or {})
            compile_target_for_candidate = str(build_target_payload.get("active_build_target") or "").strip()
            if not compile_target_for_candidate:
                raise ToolInvocationError(
                    "active_compile_target_unresolved",
                    "Could not resolve the active Unity build target for test-framework regression compile validation.",
                )

        result["compile_target"] = compile_target_for_candidate
        compile_output = run_self_json_command(
            [
                "request-compile",
                "--project-root",
                str(project_root),
                "--target",
                compile_target_for_candidate,
                "--name",
                f"test_framework_regression_{candidate_slug}",
                "--timeout-ms",
                "180000",
            ]
        )
        write_test_framework_step_artifact(candidate_dir / "interactive_compile.json", compile_output)
        result["interactive"]["compile"] = summarize_compile_step(compile_output)

        focused_editmode_args = [
            "request-editmode-tests",
            "--project-root",
            str(project_root),
            "--timeout-ms",
            "600000",
        ]
        for assembly_name in focus_assemblies:
            focused_editmode_args.extend(["--assembly-name", assembly_name])
        for test_name in focus_tests:
            focused_editmode_args.extend(["--test-name", test_name])
        focused_editmode_output = run_self_json_command(focused_editmode_args)
        write_test_framework_step_artifact(candidate_dir / "interactive_focused_editmode.json", focused_editmode_output)
        result["interactive"]["focused_editmode"] = summarize_editmode_step(focused_editmode_output)

        broad_editmode_args = [
            "request-editmode-tests",
            "--project-root",
            str(project_root),
            "--timeout-ms",
            "600000",
        ]
        for assembly_name in broad_assemblies:
            broad_editmode_args.extend(["--assembly-name", assembly_name])
        broad_editmode_output = run_self_json_command(broad_editmode_args)
        write_test_framework_step_artifact(candidate_dir / "interactive_broad_editmode.json", broad_editmode_output)
        result["interactive"]["broad_editmode"] = summarize_editmode_step(broad_editmode_output)

    close_output = run_self_json_command(
        [
            "restore-editor-state",
            "--project-root",
            str(project_root),
            "--timeout-ms",
            "30000",
        ]
    )
    write_test_framework_step_artifact(candidate_dir / "restore_editor_state.json", close_output)
    result["restore_editor_state"] = summarize_bridge_step(close_output)

    focused_batch_args = [
        "batch-editmode-tests",
        "--project-root",
        str(project_root),
    ]
    for assembly_name in focus_assemblies:
        focused_batch_args.extend(["--assembly-name", assembly_name])
    for test_name in focus_tests:
        focused_batch_args.extend(["--test-name", test_name])
    focused_batch_output = run_self_json_command(focused_batch_args)
    write_test_framework_step_artifact(candidate_dir / "batch_focused_editmode.json", focused_batch_output)
    result["batch"]["focused_editmode"] = summarize_batch_editmode_step(focused_batch_output)

    broad_batch_args = [
        "batch-editmode-tests",
        "--project-root",
        str(project_root),
    ]
    for assembly_name in broad_assemblies:
        broad_batch_args.extend(["--assembly-name", assembly_name])
    broad_batch_output = run_self_json_command(broad_batch_args)
    write_test_framework_step_artifact(candidate_dir / "batch_broad_editmode.json", broad_batch_output)
    result["batch"]["broad_editmode"] = summarize_batch_editmode_step(broad_batch_output)

    result["contract"] = evaluate_candidate_contract(result)
    return result
