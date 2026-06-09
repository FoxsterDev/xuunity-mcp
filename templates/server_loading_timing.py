from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable


TIMING_TOKEN_PATTERN = (
    r"\b\d+(?:\.\d+)?\s*(?:ms|msec|millisecond|milliseconds|s|sec|second|seconds)\b"
    r"|\b(?:elapsed|duration|timing|startup|start(?:ed)?|load(?:ing|ed)?|ready|init(?:ialized|ializing)?)\b"
)

TIMING_VALUE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|msec|millisecond|milliseconds|s|sec|second|seconds)\b",
    re.IGNORECASE,
)


def normalize_markers(markers: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for marker in markers or []:
        text = str(marker or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def build_loading_timing_regex(markers: list[str], *, timing_only: bool) -> str:
    marker_expr = "|".join(re.escape(marker) for marker in normalize_markers(markers))
    if marker_expr and timing_only:
        return rf"(?=.*(?:{marker_expr}))(?=.*(?:{TIMING_TOKEN_PATTERN})).*"
    if marker_expr:
        return rf"(?:{marker_expr})"
    return rf"(?:{TIMING_TOKEN_PATTERN})"


def build_loading_timing_grep_args(
    *,
    markers: list[Any] | None,
    timing_only: bool = True,
    include_stack_traces: bool = False,
    include_types: list[Any] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    normalized_markers = normalize_markers(markers)
    normalized_types = [str(value).strip() for value in include_types or [] if str(value or "").strip()]
    return {
        "pattern": build_loading_timing_regex(normalized_markers, timing_only=timing_only),
        "regex": True,
        "ignoreCase": True,
        "includeStackTraces": bool(include_stack_traces),
        "limit": max(1, int(limit or 20)),
        "includeTypes": normalized_types or None,
    }


def extract_timing_values(message: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for match in TIMING_VALUE_RE.finditer(message or ""):
        raw_value = float(match.group("value"))
        unit = match.group("unit").lower()
        milliseconds = raw_value
        if unit in {"s", "sec", "second", "seconds"}:
            milliseconds = raw_value * 1000.0
        values.append(
            {
                "value": raw_value,
                "unit": unit,
                "milliseconds": round(milliseconds, 3),
                "text": match.group(0),
            }
        )
    return values


def summarize_loading_timing_response(
    *,
    project_root: str | Path,
    response: dict[str, Any],
    markers: list[Any] | None,
    timing_only: bool,
    include_stack_traces: bool,
    include_types: list[Any] | None,
    limit: int,
) -> dict[str, Any]:
    normalized_markers = normalize_markers(markers)
    summary: dict[str, Any] = {
        "action": "unity_loading_timing_summary",
        "project_root": str(project_root),
        "succeeded": response.get("status") == "ok",
        "source_operation": "unity.console.grep",
        "source_request_id": str(response.get("request_id") or ""),
        "source_status": str(response.get("status") or ""),
        "markers": normalized_markers,
        "marker_count": len(normalized_markers),
        "timing_only": bool(timing_only),
        "include_stack_traces": bool(include_stack_traces),
        "include_types": [str(value).strip() for value in include_types or [] if str(value or "").strip()],
        "limit": max(1, int(limit or 20)),
        "pattern": build_loading_timing_regex(normalized_markers, timing_only=timing_only),
        "match_count": 0,
        "returned_count": 0,
        "truncated": False,
        "matches": [],
        "timing_value_count": 0,
        "timing_values": [],
    }

    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    if error and str(error.get("code") or ""):
        summary["error"] = {
            "code": str(error.get("code") or ""),
            "message": str(error.get("message") or ""),
        }
        return summary

    payload_json = response.get("payload_json")
    payload: dict[str, Any] = {}
    if isinstance(payload_json, str) and payload_json:
        try:
            decoded = json.loads(payload_json)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            summary["succeeded"] = False
            summary["error"] = {
                "code": "invalid_console_grep_payload",
                "message": "unity.console.grep returned non-JSON payload.",
            }
            return summary

    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    compact_items: list[dict[str, Any]] = []
    all_values: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "")
        timing_values = extract_timing_values(message)
        all_values.extend(timing_values)
        compact_items.append(
            {
                "index": index,
                "type": str(item.get("type") or ""),
                "timestamp": str(item.get("timestamp") or ""),
                "message": message,
                "timing_values": timing_values,
            }
        )

    timestamps = [item["timestamp"] for item in compact_items if item.get("timestamp")]
    summary.update(
        {
            "match_count": int(payload.get("match_count") or 0),
            "returned_count": len(compact_items),
            "truncated": bool(payload.get("truncated")),
            "matches": compact_items,
            "timing_value_count": len(all_values),
            "timing_values": all_values,
            "first_timestamp": timestamps[0] if timestamps else "",
            "last_timestamp": timestamps[-1] if timestamps else "",
        }
    )
    for key in ("structured_timing", "artifact_manifest"):
        if key in payload:
            summary[key] = payload.get(key)
    return summary


def request_loading_timing_summary(
    *,
    project_root: str | Path,
    markers: list[Any] | None,
    timing_only: bool,
    include_stack_traces: bool,
    include_types: list[Any] | None,
    limit: int,
    timeout_ms: int,
    invoke_bridge: Callable[[str, str, dict[str, Any], int], dict[str, Any]],
) -> dict[str, Any]:
    grep_args = build_loading_timing_grep_args(
        markers=markers,
        timing_only=timing_only,
        include_stack_traces=include_stack_traces,
        include_types=include_types,
        limit=limit,
    )
    response = invoke_bridge(str(project_root), "unity.console.grep", grep_args, timeout_ms)
    return summarize_loading_timing_response(
        project_root=project_root,
        response=response,
        markers=markers,
        timing_only=timing_only,
        include_stack_traces=include_stack_traces,
        include_types=include_types,
        limit=limit,
    )
