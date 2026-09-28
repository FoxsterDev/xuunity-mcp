from __future__ import annotations

from typing import Any

SCENARIO_TERMINAL_STATUSES = {"passed", "failed"}

SCENARIO_STEP_KINDS = (
    "status",
    "health_probe",
    "scene_snapshot",
    "scene_open",
    "assert_scene",
    "project_refresh",
    "project_action_currency",
    "console_tail",
    "console_grep",
    "playmode_set",
    "wait",
    "wait_for_playmode_state",
    "assert_playmode_state",
    "game_view_screenshot",
    "compile_player_scripts",
    "tests_run_editmode",
    "tests_run_playmode",
    "game_view_configure",
    "project_action",
    "ui_click",
    "ui_exists",
    "ui_get_text",
    "project_defined_hook",
    "project_defined_hook_poll_until",
)

SCENARIO_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stepId": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": list(SCENARIO_STEP_KINDS),
        },
        "operation": {
            "type": "string",
            "description": "Alias for kind. Supported so scenario JSON can use operation-style step records.",
            "enum": list(SCENARIO_STEP_KINDS),
        },
        "action": {
            "type": "string",
            "enum": ["enter", "exit", "pause", "resume"],
        },
        "dependsOn": {
            "type": "array",
            "items": {"type": "string"},
        },
        "runIfStepPassed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "durationSeconds": {
            "type": "number",
            "minimum": 0.0,
        },
        "timeoutSeconds": {
            "type": "number",
            "minimum": 0.1,
        },
        "expectedPlaymodeState": {
            "type": "string",
            "enum": ["edit", "playing", "paused", "transitioning"],
        },
        "scenePath": {
            "type": "string",
            "description": "Project-relative Assets/... scene path to open before subsequent validation steps.",
        },
        "allowDirtySceneDiscard": {
            "type": "boolean",
            "default": False,
            "description": "When true, allow unity.scene.open to discard unsaved open-scene changes.",
        },
        "expectedName": {"type": "string"},
        "expectedPath": {"type": "string"},
        "requiredRootNames": {
            "type": "array",
            "items": {"type": "string"},
        },
        "allowDirty": {"type": "boolean", "default": True},
        "limit": {
            "type": "integer",
            "minimum": 0,
            "description": "Per-step item limit. Omit or use 0 to apply the step default.",
        },
        "pattern": {"type": "string"},
        "regex": {"type": "boolean"},
        "ignoreCase": {"type": "boolean"},
        "includeStackTraces": {"type": "boolean"},
        "includeTypes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "since": {
            "type": "string",
            "enum": ["playmode_start"],
            "description": (
                "console_grep only. Bound the in-memory console search to items logged after the most recent "
                "Play Mode entry; a zero-match is not_matched only when since_scope_complete is true."
            ),
        },
        "fileName": {"type": "string"},
        "includeImage": {"type": "boolean"},
        "maxResolution": {"type": "integer", "minimum": 1},
        "target": {"type": "string"},
        "optionFlags": {"type": "array", "items": {"type": "string"}},
        "extraDefines": {"type": "array", "items": {"type": "string"}},
        "name": {"type": "string"},
        "width": {"type": "integer", "minimum": 1},
        "height": {"type": "integer", "minimum": 1},
        "group": {"type": "string"},
        "label": {"type": "string"},
        "allowCreateCustomSize": {"type": "boolean"},
        "forceAssetRefresh": {"type": "boolean"},
        "resolvePackages": {"type": "boolean"},
        "rerunHealthProbe": {"type": "boolean"},
        "hookName": {"type": "string"},
        "hookPayloadJson": {"type": "string"},
        "startPayload": {"type": "object"},
        "startPayloadJson": {"type": "string"},
        "pollPayload": {"type": "object"},
        "pollPayloadJson": {"type": "string"},
        "passWhen": {
            "type": "string",
            "description": "Poll-until predicate using payload.<field> == 'value'.",
        },
        "failWhen": {
            "type": "string",
            "description": "Poll-until predicate using payload.<field> == 'value'.",
        },
        "continueWhen": {
            "type": "string",
            "description": "Optional poll-until predicate using payload.<field> == 'value'. A payload status of not_started also keeps waiting unless passWhen or failWhen explicitly matches it.",
        },
        "intervalSeconds": {"type": "number", "minimum": 0.0, "default": 2.0},
        "promotePayloadFields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "terminalScreenshot": {"type": "boolean", "default": False},
        "terminalConsoleTail": {"type": "boolean", "default": False},
        "continueToCleanupOnFail": {"type": "boolean", "default": True},
        "actionId": {"type": "string"},
        "projectAction": {"type": "string"},
        "payload": {"type": "object"},
        "payloadJson": {"type": "string"},
        "allowMutating": {"type": "boolean", "default": False},
        "requiresFreshAssets": {"type": "boolean", "default": False},
        "assetRefreshStepId": {"type": "string"},
        "interactionId": {
            "type": "string",
            "description": "ui_click only. Stable id a reference can require via required_interactions.",
        },
        "targetKind": {
            "type": "string",
            "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
            "description": (
                "UI steps only. Where to build the UI tree from before matching the selector. "
                "all_loaded_scenes walks every loaded scene plus DontDestroyOnLoad."
            ),
        },
        "targetValue": {"type": "string"},
        "sceneName": {
            "type": "string",
            "description": "UI steps only. Restrict the searched scope to this loaded scene, by scene name or scene path.",
        },
        "includeDontDestroyOnLoad": {
            "type": "boolean",
            "default": True,
            "description": (
                "UI steps only. Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope "
                "diagnostics. Resolving it creates and immediately destroys one hidden probe GameObject in Play Mode."
            ),
        },
        "maxDepth": {
            "type": "integer",
            "minimum": 1,
            "default": 12,
            "description": "UI steps only. Maximum hierarchy depth to inspect while searching for selector matches.",
        },
        "maxNodes": {
            "type": "integer",
            "minimum": 1,
            "default": 500,
            "description": (
                "UI steps only. Maximum nodes to inspect. If this budget is exhausted before the search is "
                "complete, the step fails as ui_selector_search_truncated instead of claiming absence or uniqueness."
            ),
        },
        "selector": {
            "type": "object",
            "description": "UI steps only. ui_click and ui_get_text require one unambiguous node.",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string"},
                "path": {"type": "string"},
                "pathContains": {"type": "string"},
                "textEquals": {"type": "string"},
                "textContains": {"type": "string"},
                "caseInsensitiveText": {"type": "boolean"},
                "requireVisible": {"type": "boolean"},
                "requireInteractable": {"type": "boolean"},
            },
        },
        "expectStateChange": {
            "type": "boolean",
            "default": True,
            "description": "ui_click only. Fail the step when the UI tree signature is unchanged after delivery.",
        },
        "expectedExists": {
            "type": "boolean",
            "default": True,
            "description": "ui_exists only. Assert that the selector's existence equals this value; absence passes only with a complete search.",
        },
        "expectedText": {
            "type": "string",
            "description": "ui_get_text only. When non-empty, require an exact match; otherwise capture any available semantic text.",
        },
        "approve": {
            "type": "boolean",
            "default": False,
            "description": "ui_click only. Required; delivering a pointer click mutates runtime UI state.",
        },
    },
    "anyOf": [{"required": ["kind"]}, {"required": ["operation"]}],
}

SCENARIO_DEFINITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "stopOnFirstFailure": {"type": "boolean", "default": True},
        "steps": {
            "type": "array",
            "items": SCENARIO_STEP_SCHEMA,
            "minItems": 1,
        },
        "cleanupSteps": {
            "type": "array",
            "items": SCENARIO_STEP_SCHEMA,
            "description": "Optional finally-style steps appended to the scenario and still run after a body failure when stopOnFirstFailure is true.",
        },
    },
    "required": ["name", "steps"],
}
