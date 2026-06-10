from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


LIGHT_MCP_PACKAGE_NAME = "com.xuunity.light-mcp"
TEST_RESULT_MODES = {"editmode", "playmode"}


def test_results_dir(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp" / "state" / "test_results"


def load_test_result(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    mode = _normalize_mode(payload.get("test_mode") or _mode_from_operation(payload.get("operation")))
    total = _to_int(payload.get("total"))
    passed = _to_int(payload.get("passed"))
    failed = _to_int(payload.get("failed"))
    skipped = _to_int(payload.get("skipped"))
    status = _test_status(payload, total=total, failed=failed)
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    first_failure = _first_failure(failures)
    failure_class = classify_test_failure(first_failure)
    project_root = str(payload.get("project_root") or "")
    return {
        "project": Path(project_root).name if project_root else "",
        "project_root": project_root,
        "mode": mode,
        "status": status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "request_id": str(payload.get("request_id") or path.stem),
        "result_path": str(path),
        "lifecycle_churn_observed": bool(payload.get("lifecycle_churn_observed")),
        "first_failure_class": failure_class.get("class", ""),
        "first_failure_group_key": failure_class.get("group_key", ""),
        "first_failure_test": str(first_failure.get("name") or first_failure.get("fullName") or ""),
        "first_failure_message": str(first_failure.get("message") or ""),
        "completed_at_utc": str(payload.get("completed_at_utc") or payload.get("last_progress_at_utc") or ""),
        "started_at_utc": str(payload.get("started_at_utc") or ""),
    }


def select_test_result_rows(
    *,
    project_roots: list[Path],
    modes: list[str] | None = None,
    request_ids: list[str] | None = None,
    result_files: list[Path] | None = None,
) -> list[dict[str, Any]]:
    selected_modes = {_normalize_mode(mode) for mode in (modes or []) if str(mode or "").strip()}
    if not selected_modes:
        selected_modes = set(TEST_RESULT_MODES)

    rows: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()

    for result_file in result_files or []:
        path = result_file.expanduser().resolve()
        if path in seen_paths:
            continue
        row = load_test_result(path)
        if row["mode"] in selected_modes:
            rows.append(row)
            seen_paths.add(path)

    request_id_set = {str(value).strip() for value in (request_ids or []) if str(value).strip()}
    for project_root in project_roots:
        root = project_root.expanduser().resolve()
        for request_id in sorted(request_id_set):
            path = test_results_dir(root) / f"{request_id}.json"
            if path in seen_paths or not path.is_file():
                continue
            row = load_test_result(path)
            row["project"] = row["project"] or root.name
            row["project_root"] = row["project_root"] or str(root)
            if row["mode"] in selected_modes:
                rows.append(row)
                seen_paths.add(path)

    if request_id_set or result_files:
        return sorted(rows, key=_row_sort_key)

    for project_root in project_roots:
        root = project_root.expanduser().resolve()
        for mode in sorted(selected_modes):
            row = latest_test_result_row(root, mode)
            if row:
                rows.append(row)

    return sorted(rows, key=_row_sort_key)


def latest_test_result_row(project_root: Path, mode: str) -> dict[str, Any] | None:
    wanted_mode = _normalize_mode(mode)
    candidates: list[dict[str, Any]] = []
    for path in sorted(test_results_dir(project_root).glob("*.json")):
        try:
            row = load_test_result(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if row["mode"] != wanted_mode:
            continue
        row["project"] = row["project"] or project_root.name
        row["project_root"] = row["project_root"] or str(project_root)
        candidates.append(row)
    if not candidates:
        return None
    return max(candidates, key=_latest_sort_key)


def classify_test_failure(failure: dict[str, Any]) -> dict[str, str]:
    message = _compact_line(failure.get("message") or "")
    test_name = _compact_line(failure.get("name") or failure.get("fullName") or "")
    lower_message = message.lower()

    if not message and not test_name:
        return {"class": "", "group_key": ""}

    if "onetimesetup" in lower_message or "setup" in lower_message:
        class_name = "setup_failure"
    elif "expected file.exists" in lower_message or "file not found" in lower_message or "missing" in lower_message:
        class_name = "content_precondition"
    elif "expected" in lower_message or "assert" in lower_message:
        class_name = "assertion_failure"
    else:
        class_name = "test_failure"

    namespace = _test_namespace(test_name)
    normalized_message = _normalize_failure_message(message)
    group_key = "|".join(part for part in (class_name, namespace, normalized_message) if part)
    return {"class": class_name, "group_key": group_key}


def build_failure_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("first_failure_group_key") or "")
        if not key:
            continue
        group = groups.setdefault(
            key,
            {
                "group_key": key,
                "class": str(row.get("first_failure_class") or ""),
                "first_failure_message": str(row.get("first_failure_message") or ""),
                "projects": [],
                "modes": [],
                "count": 0,
            },
        )
        group["count"] = int(group.get("count") or 0) + 1
        _append_unique(group["projects"], str(row.get("project") or ""))
        _append_unique(group["modes"], str(row.get("mode") or ""))
    return sorted(groups.values(), key=lambda item: (-int(item.get("count") or 0), str(item.get("group_key") or "")))


def format_test_results(rows: list[dict[str, Any]], *, output_format: str = "markdown") -> str:
    output_format = str(output_format or "markdown").strip().lower()
    if output_format == "json":
        return json.dumps(
            {
                "rows": rows,
                "failure_groups": build_failure_groups(rows),
                "summary": summarize_test_rows(rows),
            },
            indent=2,
            ensure_ascii=True,
        ) + "\n"
    if output_format == "tsv":
        headers = _table_headers()
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(_cell(row, header).replace("\t", " ") for header in headers))
        return "\n".join(lines) + "\n"
    if output_format != "markdown":
        raise ValueError(f"Unsupported test results format: {output_format}")

    headers = _table_headers()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_escape(_cell(row, header)) for header in headers) + " |")
    return "\n".join(lines) + "\n"


def summarize_test_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed_rows = [row for row in rows if str(row.get("status") or "") == "failed"]
    return {
        "rows_total": len(rows),
        "rows_failed": len(failed_rows),
        "lifecycle_churn_observed": any(bool(row.get("lifecycle_churn_observed")) for row in rows),
        "total": sum(_to_int(row.get("total")) for row in rows),
        "passed": sum(_to_int(row.get("passed")) for row in rows),
        "failed": sum(_to_int(row.get("failed")) for row in rows),
        "skipped": sum(_to_int(row.get("skipped")) for row in rows),
    }


def inspect_light_mcp_package_source(project_root: Path) -> dict[str, Any]:
    manifest_path = project_root / "Packages" / "manifest.json"
    lock_path = project_root / "Packages" / "packages-lock.json"
    result: dict[str, Any] = {
        "package_name": LIGHT_MCP_PACKAGE_NAME,
        "manifest_path": str(manifest_path),
        "lock_path": str(lock_path),
        "manifest_dependency": "",
        "lock_dependency": "",
        "lock_version": "",
        "lock_hash": "",
        "dependency_mode": "missing",
        "alignment": "unknown",
        "mismatch_reason": "",
    }

    try:
        manifest = _read_json_object(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result["alignment"] = "manifest_unreadable"
        result["mismatch_reason"] = str(exc)
        return result

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        result["alignment"] = "manifest_dependencies_missing"
        result["mismatch_reason"] = "Packages/manifest.json does not contain a dependencies object."
        return result

    manifest_dependency = str(dependencies.get(LIGHT_MCP_PACKAGE_NAME) or "").strip()
    result["manifest_dependency"] = manifest_dependency
    result["dependency_mode"] = _dependency_mode(manifest_dependency)
    if not manifest_dependency:
        result["alignment"] = "manifest_dependency_missing"
        result["mismatch_reason"] = f"{LIGHT_MCP_PACKAGE_NAME} is missing from Packages/manifest.json."
        return result

    try:
        lock = _read_json_object(lock_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result["alignment"] = "lock_unreadable"
        result["mismatch_reason"] = str(exc)
        return result

    lock_entry = _lock_entry(lock)
    if not lock_entry:
        result["alignment"] = "lock_dependency_missing"
        result["mismatch_reason"] = f"{LIGHT_MCP_PACKAGE_NAME} is missing from Packages/packages-lock.json."
        return result

    result["lock_dependency"] = str(lock_entry.get("source") or lock_entry.get("url") or lock_entry.get("dependency") or "").strip()
    result["lock_version"] = str(lock_entry.get("version") or "").strip()
    result["lock_hash"] = str(lock_entry.get("hash") or "").strip()

    manifest_ref = _dependency_ref(manifest_dependency)
    lock_ref = _dependency_ref(result["lock_version"] or result["lock_dependency"])
    if manifest_ref and lock_ref and manifest_ref != lock_ref:
        result["alignment"] = "manifest_lock_mismatch"
        result["mismatch_reason"] = f"Manifest reference {manifest_ref} does not match lock reference {lock_ref}."
    elif result["dependency_mode"] == "git_or_remote" and not result["lock_hash"]:
        result["alignment"] = "lock_hash_missing"
        result["mismatch_reason"] = "Git or remote package lock entry does not expose a resolved hash."
    else:
        result["alignment"] = "aligned"
    return result


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _mode_from_operation(operation: Any) -> str:
    value = str(operation or "").lower()
    if "playmode" in value:
        return "playmode"
    if "editmode" in value:
        return "editmode"
    return ""


def _normalize_mode(mode: Any) -> str:
    value = str(mode or "").strip().lower()
    if value in TEST_RESULT_MODES:
        return value
    return value


def _test_status(payload: dict[str, Any], *, total: int, failed: int) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status
    if failed > 0:
        return "failed"
    if total <= 0:
        return "no_tests"
    return "passed"


def _first_failure(failures: list[Any]) -> dict[str, Any]:
    for failure in failures:
        if isinstance(failure, dict):
            return failure
    return {}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compact_line(value: Any, limit: int = 240) -> str:
    line = " ".join(str(value or "").split())
    return line[:limit]


def _normalize_failure_message(message: str) -> str:
    normalized = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<id>", message)
    normalized = re.sub(r"\d+", "<n>", normalized)
    normalized = re.sub(r"[/\\][^\s]+", "<path>", normalized)
    return _compact_line(normalized, 180)


def _test_namespace(test_name: str) -> str:
    parts = [part for part in test_name.split(".") if part]
    if len(parts) >= 2:
        return ".".join(parts[:-1])
    return test_name


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("project") or ""), str(row.get("mode") or ""), str(row.get("request_id") or ""))


def _latest_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("completed_at_utc") or row.get("started_at_utc") or ""), str(row.get("request_id") or ""))


def _table_headers() -> list[str]:
    return [
        "project",
        "mode",
        "status",
        "total",
        "passed",
        "failed",
        "skipped",
        "request_id",
        "lifecycle_churn_observed",
        "first_failure_class",
        "first_failure_message",
        "result_path",
    ]


def _cell(row: dict[str, Any], header: str) -> str:
    return str(row.get(header) if row.get(header) is not None else "")


def _markdown_escape(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _dependency_mode(dependency: str) -> str:
    if not dependency:
        return "missing"
    if dependency.startswith("file:"):
        return "file"
    if dependency.startswith(("http://", "https://", "git@", "ssh://")):
        return "git_or_remote"
    return "other"


def _dependency_ref(value: str) -> str:
    match = re.search(r"#([^#\s]+)$", value)
    if match:
        return match.group(1)
    return value.strip()


def _lock_entry(lock: dict[str, Any]) -> dict[str, Any]:
    dependencies = lock.get("dependencies")
    if isinstance(dependencies, dict) and isinstance(dependencies.get(LIGHT_MCP_PACKAGE_NAME), dict):
        return dependencies[LIGHT_MCP_PACKAGE_NAME]
    entry = lock.get(LIGHT_MCP_PACKAGE_NAME)
    if isinstance(entry, dict):
        return entry
    return {}
