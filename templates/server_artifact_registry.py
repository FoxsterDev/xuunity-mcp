from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError


ARTIFACT_REGISTRY_SCHEMA_VERSION = "xuunity.artifact-registry.v1"
REPORT_DESTINATIONS = {"repo_report", "repo_artifact", "library", "unity_asset", "external"}
SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|credential|private[_-]?key)", re.IGNORECASE)


def register_artifact(
    *,
    project_root: Path,
    artifact_path: str,
    destination: str = "repo_artifact",
    kind: str = "artifact",
    producer: str = "",
    artifact_schema_version: str = "",
    language: str = "",
    retention_policy: str = "project",
    metadata: dict[str, Any] | None = None,
    workspace_root: str = "",
    allow_unity_assets: bool = False,
) -> dict[str, Any]:
    workspace = resolve_workspace_root(project_root, workspace_root)
    normalized_destination = normalize_destination(destination)
    require_assets_approval(normalized_destination, allow_unity_assets)
    path = resolve_artifact_path(
        project_root=project_root,
        workspace_root=workspace,
        artifact_path=artifact_path,
        destination=normalized_destination,
    )
    record = build_artifact_record(
        project_root=project_root,
        workspace_root=workspace,
        artifact_path=path,
        destination=normalized_destination,
        kind=kind,
        producer=producer,
        artifact_schema_version=artifact_schema_version,
        language=language,
        retention_policy=retention_policy,
        metadata=metadata or {},
    )
    registry_path = append_artifact_registry_record(project_root, workspace, record)
    payload = dict(record)
    payload["registry_path"] = str(registry_path)
    payload["registry_repo_relative_path"] = repo_relative_path(registry_path, workspace)
    return payload


def write_artifact_report(
    *,
    project_root: Path,
    content: str,
    destination: str = "repo_report",
    category: str = "XUUnityLightUnityMcp",
    relative_path: str = "",
    kind: str = "report",
    producer: str = "",
    artifact_schema_version: str = "",
    language: str = "",
    retention_policy: str = "project",
    metadata: dict[str, Any] | None = None,
    workspace_root: str = "",
    allow_unity_assets: bool = False,
) -> dict[str, Any]:
    workspace = resolve_workspace_root(project_root, workspace_root)
    normalized_destination = normalize_destination(destination)
    if normalized_destination not in {"repo_report", "repo_artifact", "library", "unity_asset"}:
        raise ToolInvocationError(
            "artifact_report_destination_invalid",
            "Report writes must use repo_report, repo_artifact, library, or unity_asset.",
            {"destination": normalized_destination},
        )
    require_assets_approval(normalized_destination, allow_unity_assets)

    output_root = resolve_destination_root(
        project_root=project_root,
        workspace_root=workspace,
        destination=normalized_destination,
        category=category,
    )
    output_relative_path = relative_path.strip() or generated_report_name(kind)
    if not Path(output_relative_path).suffix:
        output_relative_path = f"{output_relative_path}.md"
    output_path = safe_join(output_root, output_relative_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    record = build_artifact_record(
        project_root=project_root,
        workspace_root=workspace,
        artifact_path=output_path,
        destination=normalized_destination,
        kind=kind,
        producer=producer,
        artifact_schema_version=artifact_schema_version,
        language=language,
        retention_policy=retention_policy,
        metadata=metadata or {},
    )
    registry_path = append_artifact_registry_record(project_root, workspace, record)
    payload = dict(record)
    payload["registry_path"] = str(registry_path)
    payload["registry_repo_relative_path"] = repo_relative_path(registry_path, workspace)
    payload["content_bytes"] = len(content.encode("utf-8"))
    return payload


def resolve_workspace_root(project_root: Path, workspace_root: str = "") -> Path:
    if workspace_root:
        return Path(workspace_root).expanduser().resolve()

    for parent in (project_root.parent, *project_root.parents):
        if (parent / "AIOutput").exists() or (parent / ".git").exists():
            return parent.resolve()
    return project_root.resolve()


def normalize_destination(destination: str) -> str:
    normalized = str(destination or "repo_artifact").strip()
    if normalized not in REPORT_DESTINATIONS:
        raise ToolInvocationError(
            "artifact_destination_invalid",
            "Artifact destination must be one of: external, library, repo_artifact, repo_report, unity_asset.",
            {"destination": normalized},
        )
    return normalized


def require_assets_approval(destination: str, allow_unity_assets: bool) -> None:
    if destination == "unity_asset" and not allow_unity_assets:
        raise ToolInvocationError(
            "artifact_unity_asset_approval_required",
            "Writing or registering Unity-imported Assets output requires allowUnityAssets=true.",
            {"destination": destination},
        )


def resolve_destination_root(
    *,
    project_root: Path,
    workspace_root: Path,
    destination: str,
    category: str,
) -> Path:
    normalized_category = sanitize_relative_path(category or "XUUnityLightUnityMcp")
    project_name = project_root.name
    if destination == "repo_report":
        return workspace_root / "AIOutput" / "Projects" / project_name / "Reports" / normalized_category
    if destination == "repo_artifact":
        return workspace_root / "AIOutput" / "Projects" / project_name / "Artifacts" / normalized_category
    if destination == "library":
        return project_root / "Library" / "XUUnityLightMcp" / "artifacts" / normalized_category
    if destination == "unity_asset":
        return project_root / "Assets" / "AIOutput" / normalized_category
    raise ToolInvocationError(
        "artifact_destination_not_writable",
        "External artifacts can be registered but not written by artifact-write-report.",
        {"destination": destination},
    )


def resolve_artifact_path(
    *,
    project_root: Path,
    workspace_root: Path,
    artifact_path: str,
    destination: str,
) -> Path:
    if not str(artifact_path or "").strip():
        raise ToolInvocationError("artifact_path_required", "artifact path is required.")

    candidate = Path(artifact_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if destination == "unity_asset":
        return (project_root / candidate).resolve()
    if destination == "library":
        return (project_root / candidate).resolve()
    return (workspace_root / candidate).resolve()


def build_artifact_record(
    *,
    project_root: Path,
    workspace_root: Path,
    artifact_path: Path,
    destination: str,
    kind: str,
    producer: str,
    artifact_schema_version: str,
    language: str,
    retention_policy: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    exists = artifact_path.exists()
    size_bytes = artifact_path.stat().st_size if exists and artifact_path.is_file() else 0
    return {
        "schema_version": ARTIFACT_REGISTRY_SCHEMA_VERSION,
        "registered_at_utc": utc_now(),
        "project": project_root.name,
        "project_root": str(project_root.resolve()),
        "workspace_root": str(workspace_root.resolve()),
        "destination": destination,
        "unity_imported": destination == "unity_asset",
        "path": str(artifact_path),
        "repo_relative_path": repo_relative_path(artifact_path, workspace_root),
        "project_relative_path": project_relative_path(artifact_path, project_root),
        "kind": str(kind or "artifact"),
        "producer": str(producer or ""),
        "artifact_schema_version": str(artifact_schema_version or ""),
        "language": str(language or ""),
        "hash_sha256": sha256_file(artifact_path) if exists and artifact_path.is_file() else "",
        "size_bytes": size_bytes,
        "exists": exists,
        "retention_policy": str(retention_policy or "project"),
        "metadata": redact_mapping(metadata),
    }


def append_artifact_registry_record(project_root: Path, workspace_root: Path, record: dict[str, Any]) -> Path:
    registry_path = (
        workspace_root
        / "AIOutput"
        / "Projects"
        / project_root.name
        / "Operations"
        / "XUUnityLightUnityMcp"
        / "artifact_registry.jsonl"
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return registry_path


def safe_join(root: Path, relative_path: str) -> Path:
    clean_relative = sanitize_relative_path(relative_path)
    candidate = (root / clean_relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ToolInvocationError(
            "artifact_relative_path_invalid",
            "Artifact relative path must stay under the selected output root.",
            {"relative_path": relative_path},
        ) from exc
    return candidate


def sanitize_relative_path(value: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ToolInvocationError("artifact_relative_path_invalid", "Artifact relative path cannot be empty.")
    path = Path(raw)
    if path.is_absolute():
        raise ToolInvocationError(
            "artifact_relative_path_invalid",
            "Artifact relative path must not be absolute.",
            {"relative_path": raw},
        )
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ToolInvocationError(
            "artifact_relative_path_invalid",
            "Artifact relative path must not contain empty, current, or parent segments.",
            {"relative_path": raw},
        )
    return path


def generated_report_name(kind: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(kind or "report")).strip("._-") or "report"
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{base}.md"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative_path(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return ""


def project_relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return ""


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if SECRET_KEY_PATTERN.search(key_text):
            result[key_text] = "[REDACTED]"
            continue
        if isinstance(item, dict):
            result[key_text] = redact_mapping(item)
        elif isinstance(item, list):
            result[key_text] = [redact_value(entry) for entry in item]
        else:
            result[key_text] = item
    return result


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(entry) for entry in value]
    return value
