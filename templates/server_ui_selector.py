from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from server_core import ToolInvocationError

UI_SELECTOR_SCHEMA_PROPERTIES: dict[str, dict[str, str]] = {
    "name": {"type": "string"},
    "type": {"type": "string"},
    "path": {"type": "string"},
    "pathContains": {"type": "string"},
    "textEquals": {"type": "string"},
    "textContains": {"type": "string"},
    "caseInsensitiveText": {"type": "boolean"},
    "requireVisible": {"type": "boolean"},
    "requireInteractable": {"type": "boolean"},
}
UI_SELECTOR_KEYS = tuple(UI_SELECTOR_SCHEMA_PROPERTIES)
UI_SELECTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "AND-combined node selector. Only these keys exist: " + ", ".join(UI_SELECTOR_KEYS) + ". "
        "An unknown key is refused as unknown_selector_key instead of being ignored."
    ),
    "properties": UI_SELECTOR_SCHEMA_PROPERTIES,
    "additionalProperties": False,
}
SCENARIO_STEP_GROUPS = ("steps", "cleanupSteps")


def unknown_ui_selector_keys(selector: Any) -> list[str]:
    if not isinstance(selector, dict):
        return []
    return [str(key) for key in selector if str(key) not in UI_SELECTOR_SCHEMA_PROPERTIES]


def closest_ui_selector_keys(key: str) -> list[str]:
    lowered = {candidate.lower(): candidate for candidate in UI_SELECTOR_KEYS}
    if key.lower() in lowered:
        return [lowered[key.lower()]]
    return get_close_matches(key, UI_SELECTOR_KEYS, n=3, cutoff=0.4)


def assert_ui_selector_keys(selector: Any, *, where: str) -> None:
    unknown = unknown_ui_selector_keys(selector)
    if not unknown:
        return
    suggestions = {key: closest_ui_selector_keys(key) for key in unknown}
    described = "; ".join(
        f"'{key}' (closest: {', '.join(matches) if matches else 'none'})" for key, matches in suggestions.items()
    )
    raise ToolInvocationError(
        "unknown_selector_key",
        f"{where} has unknown selector key(s): {described}. Valid keys: {', '.join(UI_SELECTOR_KEYS)}. "
        "Nothing was executed.",
        {
            "where": where,
            "unknown_selector_keys": unknown,
            "closest_valid_keys": suggestions,
            "valid_selector_keys": list(UI_SELECTOR_KEYS),
            "request_submitted": False,
        },
    )


def assert_scenario_ui_selector_keys(scenario: Any) -> None:
    if not isinstance(scenario, dict):
        return
    for group in SCENARIO_STEP_GROUPS:
        steps = scenario.get(group)
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or "selector" not in step:
                continue
            step_id = str(step.get("stepId") or step.get("step_id") or index)
            assert_ui_selector_keys(step.get("selector"), where=f"scenario {group}[{index}] '{step_id}'")
