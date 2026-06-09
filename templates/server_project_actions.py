from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError


PROJECT_ACTION_SCHEMA_VERSION = "xuunity.project-actions.v1"
PROJECT_HOOK_SCAFFOLD_VERSION = "xuunity.project-hook-scaffold.v1"


def parse_project_actions_yaml(text: str) -> dict[str, Any]:
    lines: list[tuple[int, str, int]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip(), line_number))

    if not lines:
        return {}

    payload, index = _parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        _, content, line_number = lines[index]
        raise ToolInvocationError(
            "project_actions_yaml_invalid",
            f"Unexpected YAML content at line {line_number}: {content}",
        )
    if not isinstance(payload, dict):
        raise ToolInvocationError("project_actions_yaml_invalid", "Project action catalog must be a YAML object.")
    return payload


def _parse_yaml_block(lines: list[tuple[int, str, int]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index

    current_indent, content, _ = lines[index]
    if current_indent < indent:
        return {}, index
    if current_indent != indent:
        raise ToolInvocationError("project_actions_yaml_invalid", f"Unexpected indentation before: {content}")

    if content.startswith("- "):
        return _parse_yaml_list(lines, index, indent)
    return _parse_yaml_map(lines, index, indent)


def _parse_yaml_map(lines: list[tuple[int, str, int]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content, line_number = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ToolInvocationError(
                "project_actions_yaml_invalid",
                f"Unexpected indentation at line {line_number}: {content}",
            )
        if content.startswith("- "):
            break

        key, value = _split_yaml_key_value(content, line_number)
        if value:
            result[key] = _parse_yaml_scalar(value)
            index += 1
            continue

        next_index = index + 1
        if next_index >= len(lines) or lines[next_index][0] <= indent:
            result[key] = {}
            index += 1
            continue

        child, index = _parse_yaml_block(lines, next_index, lines[next_index][0])
        result[key] = child
    return result, index


def _parse_yaml_list(lines: list[tuple[int, str, int]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content, line_number = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ToolInvocationError(
                "project_actions_yaml_invalid",
                f"Unexpected indentation at line {line_number}: {content}",
            )
        if not content.startswith("- "):
            break

        value = content[2:].strip()
        if value:
            result.append(_parse_yaml_scalar(value))
            index += 1
            continue

        next_index = index + 1
        if next_index >= len(lines) or lines[next_index][0] <= indent:
            result.append("")
            index += 1
            continue

        child, index = _parse_yaml_block(lines, next_index, lines[next_index][0])
        result.append(child)
    return result, index


def _split_yaml_key_value(content: str, line_number: int) -> tuple[str, str]:
    if ":" not in content:
        raise ToolInvocationError(
            "project_actions_yaml_invalid",
            f"Expected key/value YAML entry at line {line_number}: {content}",
        )

    key, value = content.split(":", 1)
    key = key.strip()
    if not key:
        raise ToolInvocationError("project_actions_yaml_invalid", f"Empty YAML key at line {line_number}.")
    return key, value.strip()


def _parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(item.strip()) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def resolve_project_action_catalog_path(project_root: Path, catalog_path: str = "") -> Path:
    if catalog_path:
        candidate = Path(catalog_path).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if not candidate.is_file():
            raise ToolInvocationError(
                "project_action_catalog_not_found",
                f"Project action catalog file not found: {candidate}",
                {"catalog_path": str(candidate)},
            )
        return candidate

    project_name = project_root.name
    candidates: list[Path] = []
    for parent in (project_root, *project_root.parents):
        candidates.append(
            parent
            / "AIOutput"
            / "Projects"
            / project_name
            / "Operations"
            / "XUUnityLightUnityMcp"
            / "project_actions.yaml"
        )

    candidates.extend(
        [
            project_root / "AIOutput" / "Operations" / "XUUnityLightUnityMcp" / "project_actions.yaml",
            project_root / "Assets" / "AIOutput" / "Operations" / "XUUnityLightUnityMcp" / "project_actions.yaml",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise ToolInvocationError(
        "project_action_catalog_not_found",
        f"Project action catalog not found for project root: {project_root}",
        {"candidate_paths": [str(candidate) for candidate in candidates[:8]]},
    )


def load_project_action_catalog(project_root: Path, catalog_path: str = "") -> dict[str, Any]:
    resolved_path = resolve_project_action_catalog_path(project_root, catalog_path)
    try:
        raw = parse_project_actions_yaml(resolved_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ToolInvocationError("project_action_catalog_unreadable", str(exc)) from exc

    return normalize_project_action_catalog(raw, project_root=project_root, catalog_path=resolved_path)


def normalize_project_action_catalog(
    raw: dict[str, Any],
    *,
    project_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    schema_version = str(raw.get("schemaVersion") or "")
    if schema_version != PROJECT_ACTION_SCHEMA_VERSION:
        raise ToolInvocationError(
            "unsupported_project_action_schema",
            f"Unsupported project action schema '{schema_version}'. Expected '{PROJECT_ACTION_SCHEMA_VERSION}'.",
            {"catalog_path": str(catalog_path), "schema_version": schema_version},
        )

    actions_raw = raw.get("actions")
    if not isinstance(actions_raw, dict) or not actions_raw:
        raise ToolInvocationError(
            "project_action_catalog_empty",
            "Project action catalog must declare at least one action.",
            {"catalog_path": str(catalog_path)},
        )

    default_hook_name = str(raw.get("hookName") or "").strip()
    records: list[dict[str, Any]] = []
    actions_by_id: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, str] = {}
    alias_conflicts: dict[str, list[str]] = {}
    validation_errors: list[dict[str, str]] = []

    for action_id, action_raw in actions_raw.items():
        if not isinstance(action_raw, dict):
            validation_errors.append(
                {
                    "action_id": str(action_id),
                    "code": "invalid_action_entry",
                    "message": "Action entry must be a YAML object.",
                }
            )
            continue

        record = normalize_project_action_record(str(action_id), action_raw, default_hook_name)
        records.append(record)
        actions_by_id[record["action_id"]] = record
        for alias in record["aliases"]:
            existing = alias_map.get(alias)
            if existing and existing != record["action_id"]:
                alias_conflicts.setdefault(alias, [existing]).append(record["action_id"])
                continue
            alias_map[alias] = record["action_id"]

        if not record["hook_name"]:
            validation_errors.append(
                {
                    "action_id": record["action_id"],
                    "code": "missing_hook_name",
                    "message": "Action must declare hookName or inherit a catalog hookName.",
                }
            )

    records.sort(key=lambda item: item["action_id"])
    for values in alias_conflicts.values():
        values.sort()

    return {
        "schema_version": schema_version,
        "project": str(raw.get("project") or project_root.name),
        "project_root": str(project_root),
        "catalog_path": str(catalog_path),
        "default_hook_name": default_hook_name,
        "actions": records,
        "actions_by_id": actions_by_id,
        "alias_map": alias_map,
        "alias_conflicts": alias_conflicts,
        "validation_errors": validation_errors,
    }


def normalize_project_action_record(
    action_id: str,
    action_raw: dict[str, Any],
    default_hook_name: str,
) -> dict[str, Any]:
    aliases = _as_string_list(action_raw.get("aliases"))
    mutates = _as_string_list(action_raw.get("mutates"))
    return {
        "action_id": action_id,
        "aliases": aliases,
        "hook_name": str(action_raw.get("hookName") or default_hook_name or "").strip(),
        "payload_schema": _as_dict(action_raw.get("payload")),
        "mutates": mutates,
        "mutation": len(mutates) > 0,
        "preconditions": _as_string_list(action_raw.get("preconditions")),
        "postconditions": _as_string_list(action_raw.get("postconditions")),
        "cleanup": action_raw.get("cleanup", ""),
        "evidence": _as_string_list(action_raw.get("evidence")),
        "validation_modes": _as_string_list(action_raw.get("validationModes")),
    }


def project_action_catalog_payload(catalog: dict[str, Any]) -> dict[str, Any]:
    actions = list(catalog.get("actions") or [])
    return {
        "action": "unity_project_action_list",
        "project_root": str(catalog.get("project_root") or ""),
        "catalog_path": str(catalog.get("catalog_path") or ""),
        "schema_version": str(catalog.get("schema_version") or ""),
        "project": str(catalog.get("project") or ""),
        "default_hook_name": str(catalog.get("default_hook_name") or ""),
        "action_count": len(actions),
        "available_actions": [str(action.get("action_id") or "") for action in actions],
        "alias_count": len(dict(catalog.get("alias_map") or {})),
        "alias_conflicts": dict(catalog.get("alias_conflicts") or {}),
        "validation_errors": list(catalog.get("validation_errors") or []),
        "actions": actions,
    }


def resolve_project_action(catalog: dict[str, Any], requested_action: str) -> dict[str, Any]:
    requested = str(requested_action or "").strip()
    if not requested:
        raise ToolInvocationError("missing_project_action", "Project action id is required.")

    actions_by_id = dict(catalog.get("actions_by_id") or {})
    if requested in actions_by_id:
        return dict(actions_by_id[requested])

    alias_conflicts = dict(catalog.get("alias_conflicts") or {})
    if requested in alias_conflicts:
        raise ToolInvocationError(
            "ambiguous_project_action",
            f"Project action alias '{requested}' maps to multiple actions.",
            {"alias": requested, "action_ids": list(alias_conflicts.get(requested) or [])},
        )

    alias_map = dict(catalog.get("alias_map") or {})
    canonical = alias_map.get(requested)
    if canonical and canonical in actions_by_id:
        record = dict(actions_by_id[canonical])
        record["resolved_by_alias"] = requested
        return record

    raise ToolInvocationError(
        "unknown_project_action",
        f"Unknown project action '{requested}'.",
        {
            "requested_action": requested,
            "available_actions": [str(action.get("action_id") or "") for action in catalog.get("actions") or []],
        },
    )


def build_project_action_scenario(
    *,
    action_record: dict[str, Any],
    action_payload: dict[str, Any],
    scenario_name: str = "",
) -> dict[str, Any]:
    hook_name = str(action_record.get("hook_name") or "").strip()
    action_id = str(action_record.get("action_id") or "").strip()
    if not hook_name:
        raise ToolInvocationError(
            "project_action_hook_missing",
            f"Project action '{action_id}' does not declare a hookName.",
            {"action_id": action_id},
        )
    if "action" in action_payload and str(action_payload.get("action") or "").strip() not in {"", action_id}:
        raise ToolInvocationError(
            "project_action_payload_reserved_key",
            "Project action payload must not override the catalog action id.",
            {"action_id": action_id, "payload_action": str(action_payload.get("action") or "")},
        )

    hook_payload = dict(action_payload)
    hook_payload["action"] = action_id
    effective_scenario_name = scenario_name.strip() if scenario_name else ""
    if not effective_scenario_name:
        effective_scenario_name = f"project_action_{sanitize_action_name(action_id)}_{int(time.time())}"

    return {
        "name": effective_scenario_name,
        "description": f"Invoke typed project action {action_id}.",
        "stopOnFirstFailure": True,
        "steps": [
            {
                "stepId": "invoke_project_action",
                "kind": "project_defined_hook",
                "hookName": hook_name,
                "hookPayloadJson": json.dumps(hook_payload, ensure_ascii=True, separators=(",", ":")),
            }
        ],
    }


def scenario_has_project_action_steps(scenario: dict[str, Any]) -> bool:
    return any(
        isinstance(step, dict) and str(step.get("kind") or "") == "project_action"
        for step in list(scenario.get("steps") or []) + list(scenario.get("cleanupSteps") or [])
    )


def normalize_project_action_scenario(
    *,
    project_root: Path,
    scenario: dict[str, Any],
    catalog_path: str = "",
) -> dict[str, Any]:
    if not scenario_has_project_action_steps(scenario):
        return scenario

    catalog = load_project_action_catalog(project_root, catalog_path)
    normalized = dict(scenario)
    normalized["steps"] = normalize_project_action_steps(
        catalog=catalog,
        steps=list(scenario.get("steps") or []),
        step_group="steps",
    )
    if "cleanupSteps" in scenario:
        normalized["cleanupSteps"] = normalize_project_action_steps(
            catalog=catalog,
            steps=list(scenario.get("cleanupSteps") or []),
            step_group="cleanupSteps",
        )
    return normalized


def normalize_project_action_steps(
    *,
    catalog: dict[str, Any],
    steps: list[Any],
    step_group: str,
) -> list[Any]:
    normalized_steps: list[Any] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or str(step.get("kind") or "") != "project_action":
            normalized_steps.append(step)
            continue
        normalized_steps.append(
            normalize_project_action_step(
                catalog=catalog,
                step=step,
                step_group=step_group,
                step_index=index,
            )
        )
    return normalized_steps


def normalize_project_action_step(
    *,
    catalog: dict[str, Any],
    step: dict[str, Any],
    step_group: str,
    step_index: int,
) -> dict[str, Any]:
    step_id = str(step.get("stepId") or f"{step_group}_{step_index}").strip()
    action_id = str(step.get("actionId") or step.get("projectAction") or "").strip()
    action_record = resolve_project_action(catalog, action_id)
    canonical_action_id = str(action_record.get("action_id") or "")
    if bool(action_record.get("mutation")) and not bool(step.get("allowMutating")):
        raise ToolInvocationError(
            "project_action_mutation_approval_required",
            (
                f"Scenario step '{step_id}' invokes mutating project action '{canonical_action_id}'. "
                "Set allowMutating=true only after reviewing the project action catalog contract."
            ),
            {
                "step_id": step_id,
                "action_id": canonical_action_id,
                "mutates": list(action_record.get("mutates") or []),
                "catalog_path": str(catalog.get("catalog_path") or ""),
            },
        )

    if "hookName" in step or "hookPayloadJson" in step:
        raise ToolInvocationError(
            "project_action_step_reserved_key",
            "project_action scenario steps must not set hookName or hookPayloadJson directly.",
            {"step_id": step_id, "action_id": canonical_action_id},
        )

    if "payload" in step and "payloadJson" in step:
        raise ToolInvocationError(
            "project_action_payload_ambiguous",
            "project_action scenario step must not set both payload and payloadJson.",
            {"step_id": step_id, "action_id": canonical_action_id},
        )

    if "payloadJson" in step:
        try:
            payload = json.loads(str(step.get("payloadJson") or "{}"))
        except json.JSONDecodeError as exc:
            raise ToolInvocationError(
                "project_action_payload_invalid",
                f"project_action payloadJson must be a JSON object: {exc}",
                {"step_id": step_id, "action_id": canonical_action_id},
            ) from exc
    else:
        payload = step.get("payload", {})

    if not isinstance(payload, dict):
        raise ToolInvocationError(
            "project_action_payload_invalid",
            "project_action scenario step payload must be a JSON object.",
            {"step_id": step_id, "action_id": canonical_action_id},
        )
    if "action" in payload and str(payload.get("action") or "").strip() not in {"", canonical_action_id}:
        raise ToolInvocationError(
            "project_action_payload_reserved_key",
            "project_action scenario step payload must not override the catalog action id.",
            {
                "step_id": step_id,
                "action_id": canonical_action_id,
                "payload_action": str(payload.get("action") or ""),
            },
        )

    hook_name = str(action_record.get("hook_name") or "").strip()
    if not hook_name:
        raise ToolInvocationError(
            "project_action_hook_missing",
            f"Project action '{canonical_action_id}' does not declare a hookName.",
            {"step_id": step_id, "action_id": canonical_action_id},
        )

    hook_payload = dict(payload)
    hook_payload["action"] = canonical_action_id
    normalized = {
        key: value
        for key, value in step.items()
        if key not in {"kind", "actionId", "projectAction", "payload", "payloadJson", "allowMutating"}
    }
    normalized["kind"] = "project_defined_hook"
    normalized["hookName"] = hook_name
    normalized["hookPayloadJson"] = json.dumps(hook_payload, ensure_ascii=True, separators=(",", ":"))
    return normalized


def build_project_action_invocation_payload(
    *,
    project_root: Path,
    catalog: dict[str, Any],
    action_record: dict[str, Any],
    requested_action: str,
    action_payload: dict[str, Any],
    scenario: dict[str, Any],
    run_payload: dict[str, Any],
    scenario_summary: dict[str, Any] | None,
    wait_for_result: bool,
) -> dict[str, Any]:
    payload = {
        "action": "unity_project_action_invoke",
        "project_root": str(project_root),
        "catalog_path": str(catalog.get("catalog_path") or ""),
        "requested_action": requested_action,
        "action_id": str(action_record.get("action_id") or ""),
        "resolved_by_alias": str(action_record.get("resolved_by_alias") or ""),
        "hook_name": str(action_record.get("hook_name") or ""),
        "mutation": bool(action_record.get("mutation")),
        "mutates": list(action_record.get("mutates") or []),
        "evidence": list(action_record.get("evidence") or []),
        "validation_modes": list(action_record.get("validation_modes") or []),
        "payload_keys": sorted(str(key) for key in action_payload.keys()),
        "scenario_name": str(scenario.get("name") or ""),
        "scenario": scenario,
        "wait_for_result": wait_for_result,
        "run_id": str(run_payload.get("run_id") or ""),
        "run_start_status": str(run_payload.get("status") or ""),
    }
    if not wait_for_result:
        payload["status"] = str(run_payload.get("status") or "")
        payload["succeeded"] = False
        payload["terminal"] = False
        payload["run_start"] = run_payload
        return payload

    summary = dict(scenario_summary or {})
    payload["scenario_summary"] = summary
    payload["status"] = str(summary.get("status") or "")
    payload["succeeded"] = bool(summary.get("succeeded"))
    payload["terminal"] = bool(summary.get("terminal"))
    payload["result_path"] = str(summary.get("result_path") or "")
    if "project_defined_hook_summary" in summary:
        payload["project_defined_hook_summary"] = summary["project_defined_hook_summary"]
    return payload


def sanitize_action_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    sanitized = sanitized.strip("_").lower()
    return sanitized or "project_action"


def scaffold_project_hook(
    *,
    hook_name: str,
    action_id: str,
    class_name: str,
    namespace: str,
    output_dir: Path,
    mutating: bool = False,
    write_files: bool = False,
) -> dict[str, Any]:
    hook_name = hook_name.strip()
    action_id = action_id.strip()
    class_name = class_name.strip()
    namespace = namespace.strip() or "Example.Project.Editor"
    if not hook_name:
        raise ToolInvocationError("project_hook_scaffold_invalid", "hook_name is required.")
    if not action_id:
        raise ToolInvocationError("project_hook_scaffold_invalid", "action_id is required.")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", class_name):
        raise ToolInvocationError(
            "project_hook_scaffold_invalid",
            "class_name must be a valid C# identifier.",
            {"class_name": class_name},
        )
    if not output_dir:
        raise ToolInvocationError("project_hook_scaffold_invalid", "output_dir is required.")

    slug = sanitize_action_name(hook_name.replace(".", "_"))
    scenario_name = f"{slug}_activation_smoke"
    files = {
        f"{class_name}.cs": render_project_hook_class(
            hook_name=hook_name,
            action_id=action_id,
            class_name=class_name,
            namespace=namespace,
        ),
        "project_actions.fragment.yaml": render_project_actions_fragment(
            hook_name=hook_name,
            action_id=action_id,
            mutating=mutating,
        ),
        f"{scenario_name}.json": render_project_hook_activation_scenario(
            scenario_name=scenario_name,
            action_id=action_id,
            mutating=mutating,
        ),
        "ACTIVATION_CHECKLIST.md": render_project_hook_activation_checklist(
            hook_name=hook_name,
            action_id=action_id,
            class_name=class_name,
            scenario_name=scenario_name,
            mutating=mutating,
        ),
    }

    written_paths: list[str] = []
    if write_files:
        output_dir.mkdir(parents=True, exist_ok=True)
        for relative_path, content in files.items():
            target = output_dir / relative_path
            target.write_text(content, encoding="utf-8")
            written_paths.append(str(target))

    return {
        "action": "project_hook_scaffold",
        "schema_version": PROJECT_HOOK_SCAFFOLD_VERSION,
        "hook_name": hook_name,
        "action_id": action_id,
        "class_name": class_name,
        "namespace": namespace,
        "mutating": mutating,
        "output_dir": str(output_dir),
        "write_files": write_files,
        "written_paths": written_paths,
        "files": [
            {
                "path": relative_path,
                "content": content,
            }
            for relative_path, content in files.items()
        ],
        "activation_order": [
            "add_hook_class_under_project_editor_assembly",
            "merge_project_actions_fragment",
            "refresh_project_and_wait_for_compile",
            "run_project_action_list",
            "validate_activation_scenario",
            "run_non_mutating_activation_scenario",
            "only_then_run_mutating_action_with_explicit_approval" if mutating else "ready_for_non_mutating_action",
        ],
    }


def render_project_hook_class(*, hook_name: str, action_id: str, class_name: str, namespace: str) -> str:
    return f"""using System;
using UnityEngine;
using XUUnity.LightMcp.Editor.ScenarioHooks;

namespace {namespace}
{{
    public sealed class {class_name} : IXUUnityLightMcpScenarioHook
    {{
        [Serializable]
        private sealed class HookPayload
        {{
            public string action = "";
        }}

        [Serializable]
        private sealed class HookResponse
        {{
            public string action = "";
            public string outcome = "";
            public string executed_at_utc = "";
            public string[] available_actions = Array.Empty<string>();
        }}

        public string HookName => "{hook_name}";

        public XUUnityLightMcpScenarioHookResult Execute(string payloadJson)
        {{
            var payload = string.IsNullOrWhiteSpace(payloadJson)
                ? new HookPayload()
                : JsonUtility.FromJson<HookPayload>(payloadJson) ?? new HookPayload();

            var action = string.IsNullOrWhiteSpace(payload.action)
                ? "{action_id}"
                : payload.action.Trim();

            if (!string.Equals(action, "{action_id}", StringComparison.Ordinal))
            {{
                return Failure(action, "unsupported_action", $"Unsupported action '{{action}}'.");
            }}

            return Success(action, "activation_checked");
        }}

        private static XUUnityLightMcpScenarioHookResult Success(string action, string outcome)
        {{
            return new XUUnityLightMcpScenarioHookResult
            {{
                success = true,
                outcome = outcome,
                payload_json = JsonUtility.ToJson(CreateResponse(action, outcome)),
            }};
        }}

        private static XUUnityLightMcpScenarioHookResult Failure(string action, string errorCode, string errorMessage)
        {{
            return new XUUnityLightMcpScenarioHookResult
            {{
                success = false,
                outcome = errorCode,
                error_code = errorCode,
                error_message = errorMessage,
                payload_json = JsonUtility.ToJson(CreateResponse(action, errorCode)),
            }};
        }}

        private static HookResponse CreateResponse(string action, string outcome)
        {{
            return new HookResponse
            {{
                action = action ?? "",
                outcome = outcome ?? "",
                executed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                available_actions = new[] {{ "{action_id}" }},
            }};
        }}
    }}
}}
"""


def render_project_actions_fragment(*, hook_name: str, action_id: str, mutating: bool) -> str:
    mutates = "[project_specific_state]" if mutating else "[]"
    return f"""# Merge this action into <HostOutput>/Projects/<Project>/Operations/XUUnityLightUnityMcp/project_actions.yaml.
{action_id}:
  hookName: {hook_name}
  payload: {{}}
  mutates: {mutates}
  evidence:
    - outcome
    - available_actions
  validationModes:
    - project_action_contract
"""


def render_project_hook_activation_scenario(*, scenario_name: str, action_id: str, mutating: bool) -> str:
    step: dict[str, Any] = {
        "stepId": "invoke_project_action",
        "kind": "project_action",
        "actionId": action_id,
    }
    if mutating:
        step["allowMutating"] = True
    scenario = {
        "name": scenario_name,
        "description": "Activation smoke for a catalog-backed project hook.",
        "stopOnFirstFailure": True,
        "steps": [step],
    }
    return json.dumps(scenario, indent=2, ensure_ascii=True) + "\n"


def render_project_hook_activation_checklist(
    *,
    hook_name: str,
    action_id: str,
    class_name: str,
    scenario_name: str,
    mutating: bool,
) -> str:
    mutating_note = (
        "- This action declares mutations. Keep a non-mutating list/preflight action nearby and require explicit approval before real mutation.\n"
        if mutating
        else "- This activation action is non-mutating; keep it as the first validation path for the hook.\n"
    )
    return f"""# Project Hook Activation Checklist

Hook: `{hook_name}`
Class: `{class_name}`
Action: `{action_id}`
Scenario: `{scenario_name}`

## Checklist

- Place `{class_name}.cs` under a project Editor assembly that references `XUUnity.LightMcp.Editor.ScenarioHooks`.
- Merge `project_actions.fragment.yaml` into the project's `project_actions.yaml`.
- Refresh Unity and wait for compile/domain reload to settle.
- Run `project-action-list --project-root <ProjectRoot>` and confirm `{action_id}` resolves to `{hook_name}`.
- Validate `{scenario_name}.json` with `request-scenario-validate`.
- Run the activation scenario and inspect `request-scenario-result-summary`.
{mutating_note}- If the hook fans out across projects, preflight all targets before mutating the first one.
- Keep project-specific paths, product names, and private evidence out of public MCP docs.
"""


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
