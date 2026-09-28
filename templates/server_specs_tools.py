from __future__ import annotations

from typing import Any

from server_specs_scenario import SCENARIO_DEFINITION_SCHEMA

TOOLS: dict[str, dict[str, Any]] = {
    "xuunity_setup_plan": {
        "description": "Discover Unity projects under a workspace and produce an explicit per-project XUUnity Light MCP setup plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspaceRoot": {
                    "type": "string",
                    "description": "Workspace or repository root to scan for Unity projects."
                },
                "projectRoot": {
                    "type": "string",
                    "description": "One explicit Unity project root; scalar parity with setup-plan --project-root. Combined with projectRoots when both are supplied."
                },
                "projectRoots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit Unity project roots to include."
                },
                "recursive": {"type": "boolean", "default": False},
                "includeTestFramework": {
                    "type": "string",
                    "enum": ["auto", "yes", "no"],
                    "default": "auto",
                    "description": "Whether optional Unity Test Framework install or cautious upgrade actions should be planned."
                },
                "packageSource": {
                    "type": "string",
                    "enum": ["git", "file"],
                    "default": "git"
                },
                "packageVersion": {"type": "string"},
                "localPackageSource": {"type": "string"}
            }
        }
    },
    "xuunity_setup_apply": {
        "description": "Apply an approved XUUnity Light MCP setup plan. This mutates project manifests only when approve is true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object"},
                "approve": {"type": "boolean", "default": False},
                "projectRoots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit project roots to mutate from a reviewed multi-project plan."
                }
            },
            "required": ["plan", "approve"]
        }
    },
    "xuunity_uninstall_plan": {
        "description": "Produce a safe XUUnity Light MCP uninstall plan before removing project setup, user client wiring, or helper installs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["project-only-cleanup", "full-reset-current-user", "current-user-reset"],
                    "description": "project-only-cleanup removes only project-level setup; full-reset-current-user also plans current-user client/helper cleanup. current-user-reset is accepted as an alias for full-reset-current-user."
                },
                "workspaceRoot": {
                    "type": "string",
                    "description": "Optional workspace root used only to report additional discovered Unity projects."
                },
                "projectRoots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit Unity project roots to clean. Project-only mode requires at least one."
                },
                "recursive": {"type": "boolean", "default": False},
                "client": {
                    "type": "string",
                    "enum": ["auto", "codex", "claude_code", "cursor", "windsurf", "claude_desktop"],
                    "default": "auto",
                    "description": "Current-user client wiring/helper target for full reset."
                },
                "includeOtherClientHelpers": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, full reset may remove other known current-user helper installs; client config cleanup remains selected-client scoped."
                }
            },
            "required": ["mode"]
        }
    },
    "xuunity_uninstall_apply": {
        "description": "Apply an approved XUUnity Light MCP uninstall plan. Requires approve=true and removes only planned MCP project/client/helper state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object"},
                "approve": {"type": "boolean", "default": False}
            },
            "required": ["plan", "approve"]
        }
    },
    "xuunity_setup_validate": {
        "description": "Validate one Unity project's XUUnity Light MCP setup, optionally requiring the Test Framework capability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "includeTests": {"type": "boolean", "default": False}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_license_capabilities": {
        "description": "Probe and report Unity batchmode/editor UI execution capability for one project/editor session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "unityApp": {"type": "string"},
                "refresh": {"type": "boolean", "default": False},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_status": {
        "bridgeOperation": "unity.status",
        "description": "Return normalized Unity editor and bridge readiness state for one project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {
                    "type": "string",
                    "description": "Absolute or user-home-relative path to the Unity project root."
                },
                "timeoutMs": {
                    "type": "integer",
                    "description": "How long to wait for a bridge response.",
                    "default": 5000,
                    "minimum": 1000
                }
            },
            "required": ["projectRoot"]
        }
    },
    "unity_capabilities": {
        "bridgeOperation": "unity.capabilities.get",
        "description": "Return the persisted Unity capability and health report used to gate version-sensitive operations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_health_probe": {
        "bridgeOperation": "unity.health.probe",
        "description": "Re-run Unity-side health checks and persist a fresh capability report for this project and editor version.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 15000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_build_target_get": {
        "bridgeOperation": "unity.build_target.get",
        "description": "Return the current active Unity build target and target-group state for one project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_build_target_switch": {
        "bridgeOperation": "unity.build_target.switch",
        "description": "Switch the active Unity build target and wait until the editor returns to an idle state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "target": {
                    "type": "string",
                    "description": "Unity BuildTarget enum name, for example Android, iOS, StandaloneOSX, or StandaloneWindows64."
                },
                "timeoutMs": {"type": "integer", "default": 120000, "minimum": 1000}
            },
            "required": ["projectRoot", "target"]
        }
    },
    "unity_status_summary": {
        "description": "Return a compact Unity status summary suitable for polling and low-token diagnostics. Set includeFullPayload=true to include nested discovery, transport, state-group, timing, and artifact details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, include the full nested discovery/status payload instead of the compact polling summary."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_request_final_status": {
        "description": "Resolve a compact final delivery disposition for one request id from the request journal and current bridge state. Set includeFullPayload=true for journal paths, discovery, timing, and artifact evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "requestId": {"type": "string"},
                "operation": {"type": "string"},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, include full journal, discovery, timing, and artifact evidence instead of the compact delivery verdict."
                },
                "timeoutMs": {"type": "integer", "default": 2000, "minimum": 0}
            },
            "required": ["projectRoot", "requestId"]
        }
    },
    "unity_project_refresh": {
        "bridgeOperation": "unity.project.refresh",
        "description": "Refresh AssetDatabase, optionally request package resolve, and optionally persist a fresh capability report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "forceAssetRefresh": {"type": "boolean", "default": True},
                "resolvePackages": {"type": "boolean", "default": True},
                "rerunHealthProbe": {"type": "boolean", "default": True},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 180000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_project_action_list": {
        "description": "Read and normalize the typed project action catalog for a Unity project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "catalogPath": {
                    "type": "string",
                    "description": "Optional explicit project_actions.yaml path. Defaults to the host output location for the project."
                }
            },
            "required": ["projectRoot"]
        }
    },
    "unity_project_action_currency": {
        "bridgeOperation": "unity.project_action.currency",
        "description": "Report whether the loaded Unity editor domain is current with editor inputs under Assets. With actionId, also resolve the catalog requiresFreshAssets contract without performing a refresh or invoking the action.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "actionId": {"type": "string", "description": "Optional catalog action id or alias."},
                "catalogPath": {
                    "type": "string",
                    "description": "Optional explicit project_actions.yaml path. Defaults to the host output location for the project."
                },
                "timeoutMs": {"type": "integer", "default": 15000, "minimum": 1000},
                "includeFullPayload": {"type": "boolean", "default": False}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_project_action_invoke": {
        "description": "Invoke a typed project action through a persisted Unity scenario. Every action is gated by editor-domain currency; actions declaring requiresFreshAssets run and settle an automatic AssetDatabase refresh before the currency gate and hook. Completed mutating actions are decision-ready only when their hook payload reports a valid xuunity.mutation-delta.v1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "actionId": {
                    "type": "string",
                    "description": "Catalog action id or alias."
                },
                "payload": {
                    "type": "object",
                    "description": "Action-specific JSON payload. The reserved action field is supplied from the catalog action id."
                },
                "catalogPath": {
                    "type": "string",
                    "description": "Optional explicit project_actions.yaml path. Defaults to the host output location for the project."
                },
                "scenarioName": {"type": "string"},
                "allowMutating": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true for actions whose catalog entry declares mutates."
                },
                "waitForResult": {"type": "boolean", "default": True},
                "timeoutMs": {"type": "integer", "default": 600000, "minimum": 1000},
                "pollIntervalMs": {"type": "integer", "default": 1000, "minimum": 100},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full invocation envelope (scenario echo and nested scenario summary) instead of the compact action-id/outcome/evidence envelope."
                }
            },
            "required": ["projectRoot", "actionId"]
        }
    },
    "xuunity_project_hook_scaffold": {
        "description": (
            "Preview or write a project-local IXUUnityLightMcpScenarioHook activation bundle: C# hook, "
            "project_actions.yaml fragment, validation scenario, and checklist. Writes stay under projectRoot "
            "and occur only when approve=true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "hookName": {"type": "string"},
                "actionId": {"type": "string"},
                "className": {"type": "string"},
                "namespace": {"type": "string", "default": "Example.Project.Editor"},
                "outputDir": {
                    "type": "string",
                    "description": "Project-relative output directory. Defaults to Assets/Editor/XUUnityLightMcpHooks/<className>."
                },
                "mutating": {"type": "boolean", "default": False},
                "uiFixture": {"type": "boolean", "default": False},
                "approve": {
                    "type": "boolean",
                    "default": False,
                    "description": "When false, return the complete preview without writing files."
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true with approve=true before replacing any existing scaffold file."
                }
            },
            "required": ["projectRoot", "hookName", "actionId", "className"]
        }
    },
    "unity_artifact_register": {
        "description": "Register artifact metadata in the project MCP artifact registry without invoking Unity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "path": {"type": "string"},
                "destination": {
                    "type": "string",
                    "enum": ["repo_report", "repo_artifact", "library", "unity_asset", "external"],
                    "default": "repo_artifact"
                },
                "kind": {"type": "string", "default": "artifact"},
                "producer": {"type": "string"},
                "artifactSchemaVersion": {"type": "string"},
                "language": {"type": "string"},
                "retentionPolicy": {"type": "string", "default": "project"},
                "metadata": {"type": "object"},
                "workspaceRoot": {"type": "string"},
                "allowUnityAssets": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true before registering Unity-imported Assets output."
                }
            },
            "required": ["projectRoot", "path"]
        }
    },
    "unity_artifact_write_report": {
        "description": "Write a text report to an approved project output root and register it in the artifact registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "content": {"type": "string"},
                "destination": {
                    "type": "string",
                    "enum": ["repo_report", "repo_artifact", "library", "unity_asset"],
                    "default": "repo_report"
                },
                "category": {"type": "string", "default": "XUUnityLightUnityMcp"},
                "relativePath": {"type": "string"},
                "kind": {"type": "string", "default": "report"},
                "producer": {"type": "string"},
                "artifactSchemaVersion": {"type": "string"},
                "language": {"type": "string"},
                "retentionPolicy": {"type": "string", "default": "project"},
                "metadata": {"type": "object"},
                "workspaceRoot": {"type": "string"},
                "allowUnityAssets": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true before writing Unity-imported Assets output."
                }
            },
            "required": ["projectRoot", "content"]
        }
    },
    "unity_ui_reference_register": {
        "description": (
            "Register a supplied UI design reference image as a ui-reference.v1 acceptance contract "
            "(immutable expected image, declared viewport, comparison regions, declared masks, thresholds, "
            "and acceptance lanes). Host-side only; never touches Unity assets."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "referenceId": {
                    "type": "string",
                    "description": "Stable id such as flying-gift-available-v1."
                },
                "sourceImage": {
                    "type": "string",
                    "description": "Path to the supplied PNG reference. Copied verbatim; never resized or recompressed."
                },
                "viewport": {
                    "type": "object",
                    "description": "Declared capture viewport. Defaults to the reference image dimensions.",
                    "properties": {
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "orientation": {"type": "string", "enum": ["portrait", "landscape", "square"]},
                        "dpiPolicy": {"type": "string"}
                    }
                },
                "safeArea": {"type": "string", "default": "full_screen"},
                "fixture": {
                    "type": "string",
                    "description": "Canonical UI fixture id that must establish this state before capture."
                },
                "regions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Comparison regions [{id, rect:{x,y,width,height}, required, weight}]. Defaults to one full-screen region."
                },
                "dynamicMasks": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Declared masks [{id, rect, reason}]. Undeclared dynamic content is a failure, not a mask."
                },
                "requiredUi": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Semantic expectations [{selector, text, interactable}] for the later semantic lane."
                },
                "requiredInteractions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Interaction expectations [{id, selector, expect:{delivered, state_changed}}] proven by ui_click steps in a Play-mode scenario."
                },
                "visionPolicy": {
                    "type": "object",
                    "description": "Overrides the profile-derived vision bar: {minCriterion, minOverall, requiredCriteria, judgesRequired, allowSelfReview}. Pixel equality is never the bar; this is how close counts as recognisably the same screen."
                },
                "toleranceProfile": {
                    "type": "string",
                    "enum": ["strict", "balanced", "lenient"],
                    "default": "balanced",
                    "description": "How close counts as accepted. Acceptance is human-similarity on a resolution-independent grid, not pixel equality."
                },
                "scalePolicy": {
                    "type": "string",
                    "enum": ["aspect_scale", "strict", "stretch"],
                    "default": "aspect_scale",
                    "description": "aspect_scale accepts any Game View resolution with the reference aspect; strict demands identical pixel dimensions; stretch also allows a different aspect."
                },
                "thresholds": {
                    "type": "object",
                    "description": "Per-reference numeric overrides on top of the profile (cell_color_tolerance, cell_structure_tolerance, region_min_similarity, global_min_similarity, layout_offset_tolerance, layout_size_tolerance, comparison_grid_width, ...)."
                },
                "owner": {"type": "string", "enum": ["agent", "human"], "default": "agent"},
                "acceptance": {
                    "type": "object",
                    "description": "Per-lane requirement: {visual, semantic, interaction, vision} each required|optional|not_required. vision defaults to optional because the host cannot summon a judge, but a review that was submitted and failed still fails the comparison."
                },
                "notes": {"type": "string"},
                "category": {"type": "string", "default": "UIReference"},
                "workspaceRoot": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False}
            },
            "required": ["projectRoot", "referenceId", "sourceImage"]
        }
    },
    "unity_ui_reference_validate": {
        "description": (
            "Validate a registered ui-reference.v1 contract: schema, expected-image hash, viewport agreement, "
            "region geometry, and mask policy. Reports why a reference is not usable before any capture is compared."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "referenceId": {"type": "string"},
                "manifestPath": {"type": "string"},
                "category": {"type": "string", "default": "UIReference"},
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_ui_reference_compare": {
        "description": (
            "Compare a Game View capture against a registered UI reference and publish actual/overlay/diff/metrics "
            "artifacts with per-region colour, structure, and layout scores plus an explicit reference_acceptance "
            "verdict. Acceptance is tolerance-based human similarity on a resolution-independent grid, so a capture "
            "at a different resolution than the reference is valid input; only an orientation or aspect mismatch "
            "is refused as not comparable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "referenceId": {"type": "string"},
                "manifestPath": {"type": "string"},
                "actualImage": {"type": "string", "description": "Path to the captured PNG under review."},
                "stabilityImage": {
                    "type": "string",
                    "description": "Second capture of the same frozen fixture. Required before a passing verdict."
                },
                "requireCaptureStability": {"type": "boolean", "default": True},
                "toleranceProfile": {
                    "type": "string",
                    "enum": ["strict", "balanced", "lenient"],
                    "description": "Overrides the reference's tolerance profile for this comparison only."
                },
                "emitArtifacts": {"type": "boolean", "default": True},
                "includeExpectedCopy": {"type": "boolean", "default": False},
                "comparisonId": {"type": "string"},
                "fixtureResultPath": {
                    "type": "string",
                    "description": "Scenario result JSON whose project hook reported a ui-fixture.v1 block. Preferred over fixtureEvidence: it is a receipt the editor wrote, not a caller assertion."
                },
                "fixtureEvidence": {
                    "type": "object",
                    "description": "Caller-asserted ui-fixture.v1 block. Accepted, but never proves visual determinism; use fixtureResultPath for decision-ready evidence."
                },
                "uiSnapshotPath": {
                    "type": "string",
                    "description": "A ui.read.v1 snapshot (from unity_ui_tree_snapshot or unity_prefab_render). Failed regions are mapped to the nodes whose bounds cover them, and declared requiredUi selectors are checked as the semantic lane."
                },
                "interactionResultPath": {
                    "type": "string",
                    "description": "Scenario result JSON containing ui_click steps. Defaults to fixtureResultPath, so one Play-mode run can establish the fixture and prove the interactions. Edit-mode delivery blocks the interaction lane instead of passing it."
                },
                "interactionEvidence": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Caller-asserted ui-interaction.v1 blocks. Accepted, but never receipt-backed."
                },
                "visionReviewPaths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Vision review JSON files. Omit to pick up reviews already stored under this comparison id. A review bound to a different image pair is rejected as stale."
                },
                "captureLane": {
                    "type": "string",
                    "enum": ["game_view", "device"],
                    "default": "game_view",
                    "description": "Which acceptance lane this capture belongs to. Game View parity is never reported as device parity."
                },
                "device": {
                    "type": "object",
                    "description": "Required for captureLane=device: {model, os, osVersion, resolution:{width,height}, orientation, safeArea:{top,bottom,left,right}, buildRevision}."
                },
                "category": {"type": "string", "default": "UIReference"},
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot", "actualImage"]
        }
    },
    "unity_ui_fixture_validate": {
        "description": (
            "Validate a ui-fixture.v1 readiness report from a scenario result or an inline block: fixture and "
            "state id, frozen clock, pinned locale, data source, resolved viewport/safe-area, and ready-predicate "
            "evidence. Live or mixed data without a recorded payload hash is downgraded to "
            "visual_determinism=unproven. Returns the contract itself when no evidence is supplied."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "fixtureResultPath": {
                    "type": "string",
                    "description": "Scenario result JSON whose project hook reported a ui_fixture block."
                },
                "fixtureEvidence": {
                    "type": "object",
                    "description": "Inline ui-fixture.v1 block, for authoring a project hook before wiring a scenario."
                },
                "declaredFixture": {
                    "type": "string",
                    "description": "Fixture id the reference declares, to detect a capture taken under a different fixture."
                },
                "declaredViewport": {
                    "type": "object",
                    "description": "Reference viewport {width, height} to detect a fixture resolved at another size."
                },
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_ui_vision_packet": {
        "description": (
            "Build a ui-vision-review.v1 packet for a reference/candidate pair: one side-by-side PNG sheet "
            "with the reference on the left and the candidate on the right at a shared height, failed regions "
            "outlined on both panels, and the rubric a multimodal judge must fill in. Answers the question a "
            "cell-similarity score cannot: is this recognisably the same screen in style, placement, and size. "
            "Numeric scores are withheld from the packet by default so the judgement is not anchored to them. "
            "The packet is hash-bound to the exact image pair, so a review expires when either image changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "referenceId": {"type": "string"},
                "manifestPath": {"type": "string"},
                "actualImage": {"type": "string", "description": "Path to the captured PNG under review."},
                "comparisonPath": {
                    "type": "string",
                    "description": "verdict.json from unity_ui_reference_compare. Its failed regions become the outlined attention markers."
                },
                "comparisonId": {
                    "type": "string",
                    "description": "Stores the packet under this comparison so a later compare picks the review up automatically."
                },
                "includeNumericEvidence": {
                    "type": "boolean",
                    "default": False,
                    "description": "Disclose the similarity scores to the judge. Off by default: an anchored judgement is weaker evidence than an independent one."
                },
                "maxPanelHeight": {"type": "integer", "default": 1024},
                "category": {"type": "string", "default": "UIReference"},
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot", "actualImage"]
        }
    },
    "unity_ui_vision_submit": {
        "description": (
            "Record a multimodal judgement against a vision packet and return the resulting vision lane. "
            "Validates the rubric arithmetic: every required criterion needs a score and a one-line observation, "
            "and the overall score is clamped to the worst required criterion plus one so a strong overall claim "
            "cannot outrun a weak part. Records who judged and in what role; a review by the agent that authored "
            "the UI is stored but flagged as self-review, never as independent proof."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "packetPath": {
                    "type": "string",
                    "description": "vision_packet.json emitted by unity_ui_vision_packet."
                },
                "review": {
                    "type": "object",
                    "description": "The judgement: {schemaVersion, packetHash, judge:{id, role, model}, overall, criteria:{layout, sizing, color, typography, imagery, content}, defects}. Each criterion is {score: 0-4, observation}."
                },
                "reviewPath": {
                    "type": "string",
                    "description": "Read the judgement from a JSON file instead of passing it inline."
                },
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot", "packetPath"]
        }
    },
    "unity_ui_interaction_validate": {
        "description": (
            "Validate ui-interaction.v1 evidence from a scenario result: which guarded clicks were delivered, "
            "whether the UI state changed, and whether delivery happened in Play mode. Edit-mode delivery "
            "exercises handler wiring, not a running user path, so it blocks the interaction lane instead of "
            "passing it. Returns the contract itself when no evidence is supplied."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "interactionResultPath": {
                    "type": "string",
                    "description": "Scenario result JSON containing ui_click steps."
                },
                "interactionEvidence": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Inline ui-interaction.v1 blocks, for authoring before a scenario exists."
                },
                "requiredInteractions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Expectations [{id, selector, expect:{delivered, state_changed}}] to check the evidence against."
                },
                "workspaceRoot": {"type": "string"}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_prefab_snapshot": {
        "bridgeOperation": "unity.prefab.snapshot",
        "description": (
            "Read a prefab asset's hierarchy as normalized ui.read.v1 nodes (path, active state, components, "
            "canvas context, and component detail where a uGUI/TMP reader is available). Read-only; the prefab "
            "asset is never opened for editing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "prefabPath": {
                    "type": "string",
                    "description": "Project-relative prefab path such as Assets/UI/Popup.prefab."
                },
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "includeInactive": {"type": "boolean", "default": True},
                "includeBounds": {
                    "type": "boolean",
                    "default": False,
                    "description": "Prefab assets are not in a Canvas, so bounds are layout-local, not screen pixels."
                },
                "includeText": {"type": "boolean", "default": True},
                "writeSnapshot": {
                    "type": "boolean",
                    "default": True,
                    "description": "Persist the ui.read.v1 snapshot and return snapshot_path, so it can be passed to unity_ui_reference_compare as uiSnapshotPath."
                },
                "snapshotOutputPath": {
                    "type": "string",
                    "description": "Defaults to the project's MCP captures directory."
                },
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "prefabPath"]
        }
    },
    "unity_asset_snapshot": {
        "bridgeOperation": "unity.asset.snapshot",
        "description": (
            "Read the serialized fields of a project asset (a ScriptableObject, material, or any main asset) as a "
            "flat, depth-limited list of path/type/value rows without entering Play Mode or parsing asset YAML. "
            "Read-only; the asset is never modified. Nested structs recurse up to maxDepth, arrays report their size "
            "and the first maxArrayElements items, and object references render as type:name@path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "assetPath": {
                    "type": "string",
                    "description": "Project-relative asset path such as Assets/Configs/BuildConfiguration.asset."
                },
                "maxDepth": {"type": "integer", "default": 2, "minimum": 0},
                "maxFields": {"type": "integer", "default": 200, "minimum": 1},
                "maxArrayElements": {"type": "integer", "default": 8, "minimum": 0},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "assetPath"]
        }
    },
    "unity_prefab_validate": {
        "bridgeOperation": "unity.prefab.validate",
        "description": (
            "Validate a prefab before PlayMode and report typed defects: missing_script_guid, "
            "serialized_reference_missing_component, serialized_reference_type_mismatch, missing_prefab_instance, "
            "and optionally serialized_reference_unassigned. Lanes that need an absent backend are reported as "
            "not evaluated rather than silently passing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "prefabPath": {"type": "string"},
                "reportUnassignedReferences": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also report empty serialized references as info-level findings, scoped by unassignedReferenceScope."
                },
                "unassignedReferenceScope": {
                    "type": "string",
                    "enum": ["project_scripts", "required", "all"],
                    "default": "project_scripts",
                    "description": "project_scripts reports unfilled [SerializeField] members of components whose script lives under Assets/, which is the wiring bug operators care about; required narrows that to fields carrying a Required* attribute (empty when the project uses no such convention); all also reports uGUI/TMP fields that are empty by default. unassigned_reference_suppressed_count always reports what the scope hid."
                },
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "prefabPath"]
        }
    },
    "unity_prefab_render": {
        "bridgeOperation": "unity.prefab.render",
        "description": (
            "Render a prefab in an isolated preview scene under a controlled Canvas at the declared viewport and "
            "safe area, without booting the application. Writes the PNG and the ui.read.v1 snapshot beside it, and "
            "returns screenshot_path plus snapshot_path, so the capture closes both the visual and the semantic "
            "acceptance lane through unity_ui_reference_compare with no Play-mode run. Pass overrides to capture a "
            "second runtime-driven UI state without touching the asset. Non-persistent: the preview scene is closed "
            "and no open scene is modified. Requires com.unity.ugui."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "prefabPath": {"type": "string"},
                "width": {"type": "integer", "minimum": 1, "description": "Reference viewport width in pixels."},
                "height": {"type": "integer", "minimum": 1, "description": "Reference viewport height in pixels."},
                "safeAreaTop": {"type": "integer", "default": 0},
                "safeAreaBottom": {"type": "integer", "default": 0},
                "safeAreaLeft": {"type": "integer", "default": 0},
                "safeAreaRight": {"type": "integer", "default": 0},
                "outputPath": {"type": "string", "description": "Defaults to the project's MCP captures directory."},
                "backgroundColor": {"type": "string", "default": "#00000000"},
                "referenceWidth": {"type": "integer", "description": "Adds a CanvasScaler with this reference resolution."},
                "referenceHeight": {"type": "integer"},
                "scalerMatch": {"type": "number", "default": 0.5},
                "antiAliasing": {"type": "integer", "enum": [1, 2, 4, 8], "default": 1},
                "overrides": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Transient unity_prefab_mutate operations applied to the preview-scene instance only and never written to the asset, for rendering a UI state that runtime code normally applies. Reported back as applied_overrides; a failing override fails the render instead of capturing the un-overridden state."
                },
                "allowedComponentTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra component types the transient overrides may add or remove, on top of the built-in layout allowlist."
                },
                "writeSnapshot": {
                    "type": "boolean",
                    "default": True,
                    "description": "Persist the ui.read.v1 snapshot next to the capture and return snapshot_path."
                },
                "snapshotOutputPath": {
                    "type": "string",
                    "description": "Defaults to the capture path with a .ui-snapshot.json suffix."
                },
                "includeSnapshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also inline the whole snapshot in the response. Off by default: snapshot_path is what the comparison surface consumes, and the inline copy is large."
                },
                "includeInactive": {"type": "boolean", "default": False},
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "timeoutMs": {"type": "integer", "default": 60000, "minimum": 1000}
            },
            "required": ["projectRoot", "prefabPath", "width", "height"]
        }
    },
    "unity_prefab_mutate": {
        "bridgeOperation": "unity.prefab.mutate",
        "description": (
            "Apply a typed, atomic prefab transaction through the Editor API - never raw YAML. Supported ops: "
            "set_serialized_field, set_rect_transform, set_canvas_group, set_active, delete_child, "
            "create_child_from_template, add_component, remove_component. Previews by default; approve plus "
            "previewOnly=false is required to write. Any failing operation or failed post-validation discards the "
            "whole batch. A write that leaves the serialized value unchanged is reported as status no_op, never as "
            "applied, and counted in no_op_count. Enum properties are index-addressed: numberValue is the member "
            "index and out-of-range input is rejected, so pass stringValue to set an enum by member name. "
            "Asset-typed object references (Sprite, Material, TMP_FontAsset, ...) are writable by asset path or "
            "GUID; component and GameObject references stay refused so a component can never be swapped for "
            "another type. If the prefab file changed on disk since this session wrote it, the transaction is "
            "refused as prefab_mutation_asset_drifted instead of overwriting the out-of-band edit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "prefabPath": {"type": "string"},
                "operations": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Typed operations [{op, path, componentType, propertyPath, stringValue|numberValue|boolValue|x,y,z,w, templatePath, childName, assetSubAssetName, valueKind}]. On an enum property, numberValue is the member index and stringValue is the member name. On an asset-typed object reference, stringValue is a project-relative asset path or a 32-character GUID, optionally with assetSubAssetName (or a path#SubAsset suffix) for a sub-asset such as a sliced sprite; valueKind=\"null\" clears the reference."
                },
                "previewOnly": {"type": "boolean", "default": True},
                "approve": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true, together with previewOnly=false, before the prefab asset is written."
                },
                "expectedSha256": {
                    "type": "string",
                    "description": "Optional precondition: refuse if the prefab file changed since it was inspected."
                },
                "allowedComponentTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra component types this transaction may add or remove, on top of the built-in layout allowlist."
                },
                "timeoutMs": {"type": "integer", "default": 60000, "minimum": 1000}
            },
            "required": ["projectRoot", "prefabPath", "operations"]
        }
    },
    "unity_ui_click": {
        "bridgeOperation": "unity.ui.click",
        "description": (
            "Deliver one guarded semantic click to a unique selector through the EventSystem - never a coordinate "
            "click or OS automation. Refuses ambiguous, hidden, non-interactable, raycast-transparent, and "
            "handler-less targets. A node/depth-budget-limited search is ui_selector_search_truncated because "
            "absence or uniqueness is unproven; it reports the searched scope plus retry budget. Records the matched node, "
            "delivery mechanism, and before/after snapshot signatures. Requires explicit approve=true and "
            "action='click'. Requires com.unity.ugui."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "selector": {"type": "object"},
                "action": {"type": "string", "enum": ["click"], "default": "click"},
                "approve": {"type": "boolean", "default": False},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "selector", "approve"]
        }
    },
    "unity_ui_tree_snapshot": {
        "bridgeOperation": "unity.ui.tree_snapshot",
        "description": (
            "Snapshot the live uGUI hierarchy of the active scene or a named subtree as ui.read.v1 nodes: "
            "stable-within-snapshot path, active state, components, effective CanvasGroup alpha, raycast blocking, "
            "canvas sort order, screen-space bounds, and text/font/material where a reader is available. "
            "Read-only and never OCR-derived; reports proof_class, truncation, player-loop liveness, Screen size, "
            "and the existing Game View render-target size explicitly."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "includeInactive": {"type": "boolean", "default": False},
                "includeBounds": {"type": "boolean", "default": True},
                "includeText": {"type": "boolean", "default": True},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_ui_query": {
        "bridgeOperation": "unity.ui.query",
        "description": (
            "Return the uGUI nodes matching a selector. Selector fields combine with AND: name, type, path, "
            "pathContains, textEquals, textContains, requireVisible, requireInteractable. Ambiguity is reported, "
            "never hidden. The payload includes player-loop liveness and Screen-versus-render-target evidence so "
            "a throttled or mismatched editor frame cannot be mistaken for runtime truth."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "selector": {"type": "object"},
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "maxMatches": {"type": "integer", "default": 20, "minimum": 1},
                "includeInactive": {"type": "boolean", "default": False},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "selector"]
        }
    },
    "unity_ui_exists": {
        "bridgeOperation": "unity.ui.exists",
        "description": (
            "Existence check over the same selector model as unity_ui_query. Reports match_count and ambiguity "
            "even when the answer is true. Never answers from a screenshot."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "selector": {"type": "object"},
                "includeInactive": {"type": "boolean", "default": False},
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "selector"]
        }
    },
    "unity_ui_get_text": {
        "bridgeOperation": "unity.ui.get_text",
        "description": (
            "Return the semantic text of the single node a selector matches. Zero matches fail as ui_node_not_found, "
            "several fail as selector_ambiguous unless allowMany is set, and a node without text fails as "
            "ui_text_unavailable. An empty string is valid text and is distinguished from missing text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "selector": {"type": "object"},
                "allowMany": {"type": "boolean", "default": False},
                "includeInactive": {"type": "boolean", "default": False},
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "selector"]
        }
    },
    "unity_ui_get_bounds": {
        "bridgeOperation": "unity.ui.get_bounds",
        "description": (
            "Return the screen-space bounds of the single node a selector matches, so a failed reference-comparison "
            "region can be tied to a concrete rect. A node without a RectTransform fails as ui_bounds_unavailable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "targetKind": {
                    "type": "string",
                    "enum": ["active_scene", "all_loaded_scenes", "game_object_path", "game_object_name"],
                    "default": "active_scene",
                    "description": (
                        "Which roots to build the UI tree from. active_scene uses the active scene only, which is "
                        "the wrong scope in a bootstrap-plus-additive project; all_loaded_scenes walks every loaded "
                        "scene plus the DontDestroyOnLoad scene."
                    )
                },
                "targetValue": {"type": "string"},
                "sceneName": {
                    "type": "string",
                    "description": (
                        "Restrict the searched scope to one loaded scene, by scene name or scene path. Applies to "
                        "every targetKind and overrides the active_scene default."
                    )
                },
                "includeDontDestroyOnLoad": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include the DontDestroyOnLoad scene in the searched scope and in out-of-scope diagnostics. "
                        "Resolving it creates and immediately destroys one hidden probe GameObject, and only works "
                        "in Play Mode."
                    )
                },
                "selector": {"type": "object"},
                "allowMany": {"type": "boolean", "default": False},
                "includeInactive": {"type": "boolean", "default": False},
                "maxDepth": {"type": "integer", "default": 12, "minimum": 1},
                "maxNodes": {"type": "integer", "default": 500, "minimum": 1},
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "selector"]
        }
    },
    "unity_package_install_test_framework": {
        "bridgeOperation": "unity.package.install_test_framework",
        "description": "Install or cautiously upgrade the optional Unity Test Framework package through Unity Package Manager after explicit approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "approve": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true before mutating Package Manager state."
                },
                "version": {
                    "type": "string",
                    "description": "Optional explicit com.unity.test-framework version. Defaults to the Unity-version policy."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot", "approve"]
        }
    },
    "unity_edm4u_resolve": {
        "bridgeOperation": "unity.edm4u.resolve",
        "description": "Request a whitelisted External Dependency Manager for Unity resolver menu item. Android resolve fails closed unless BuildTarget.Android is already active; menu execution and editor-idle settle do not prove resolver-output freshness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "platform": {
                    "type": "string",
                    "default": "android",
                    "enum": ["android", "version_handler"],
                    "description": "Resolver lane to run. iOS CocoaPods resolution is validated after iOS export rather than through this editor menu operation."
                },
                "force": {"type": "boolean", "default": True},
                "refreshBefore": {"type": "boolean", "default": True},
                "refreshAfter": {"type": "boolean", "default": True},
                "menuPathCandidates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional override for version-specific EDM4U menu paths. Use only for known safe resolver menu items."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_sdk_android_resolve": {
        "bridgeOperation": "unity.sdk.android_resolve",
        "description": "Run Android resolution through EDM4U's completion callback, then pass only after every tracked generated output is hash-stable across idle ticks and the expected new dependency coordinates verify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "force": {"type": "boolean", "default": True},
                "refreshBefore": {"type": "boolean", "default": True},
                "stableIdleTicks": {
                    "type": "integer",
                    "default": 2,
                    "minimum": 2,
                    "maximum": 10,
                    "description": "Consecutive idle samples with identical hashes required after EDM4U reports completion."
                },
                "trackedGeneratedPaths": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 32,
                    "items": {"type": "string"},
                    "description": "Project-relative generated outputs that must exist and remain hash-stable."
                },
                "expectations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "platform": {"type": "string", "default": "android"},
                            "path": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "file_contains",
                                    "file_regex",
                                    "android_resolver_package",
                                    "gradle_dependency",
                                    "gradle_repository"
                                ],
                                "default": "file_contains"
                            },
                            "value": {"type": "string"},
                            "version": {"type": "string"},
                            "minVersion": {"type": "string"},
                            "optional": {"type": "boolean", "default": False}
                        },
                        "required": ["path", "kind", "value"]
                    },
                    "description": "Expected post-resolve dependency coordinates or generated content. At least one is required."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 5000}
            },
            "required": ["projectRoot", "trackedGeneratedPaths", "expectations"]
        }
    },
    "unity_sdk_package_restore": {
        "bridgeOperation": "host.sdk.package_restore",
        "description": "Open a closed Unity project in batchmode, wait for a stable registered Package Manager graph, record package ids/versions and dependency XML sources, then exit with an authoritative restore receipt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "unityApp": {"type": "string", "description": "Optional explicit Unity application or executable path."},
                "stableIdleTicks": {"type": "integer", "default": 2, "minimum": 2, "maximum": 10},
                "timeoutMs": {"type": "integer", "default": 600000, "minimum": 5000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_sdk_dependency_verify": {
        "bridgeOperation": "unity.sdk.dependency.verify",
        "description": "Verify generated SDK dependency artifacts against explicit expectations after package restore, EDM4U resolve, export, or build.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "stopOnFirstFailure": {"type": "boolean", "default": False},
                "expectations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "platform": {"type": "string"},
                            "path": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "file_contains",
                                    "file_regex",
                                    "android_resolver_package",
                                    "gradle_dependency",
                                    "gradle_repository",
                                    "podfile_lock_pod"
                                ],
                                "default": "file_contains"
                            },
                            "value": {"type": "string"},
                            "version": {"type": "string"},
                            "minVersion": {"type": "string"},
                            "optional": {"type": "boolean", "default": False}
                        },
                        "required": ["path", "kind", "value"]
                    },
                    "minItems": 1
                },
                "timeoutMs": {"type": "integer", "default": 30000, "minimum": 1000}
            },
            "required": ["projectRoot", "expectations"]
        }
    },
    "unity_sdk_generated_diff_guard": {
        "bridgeOperation": "host.sdk.generated_diff_guard",
        "description": "Compare generated SDK files to a Git baseline or a fingerprint-bound Library baseline for Git-untracked outputs, fail closed on provenance or structural damage, and register the published pass/fail report as durable artifact evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "baselineSource": {"type": "string", "enum": ["git_head"], "default": "git_head"},
                "baselineRef": {"type": "string", "default": "HEAD"},
                "libraryBaselineDir": {
                    "type": "string",
                    "default": "Library/XUUnityLightMcp/sdk/baseline/default"
                },
                "captureBaseline": {"type": "boolean", "default": False},
                "trackedPaths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "diffMode": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "string",
                        "enum": ["xml_structural", "gradle_tokenized", "line_normalized"]
                    },
                    "default": {
                        "*.xml": "xml_structural",
                        "*.gradle": "gradle_tokenized",
                        "*": "line_normalized"
                    }
                },
                "expectedChangedAllowlist": {"type": "array", "items": {"type": "string"}, "default": []},
                "requiredMarkersAfter": {"type": "array", "items": {"type": "string"}, "default": []},
                "expectedVersionChanges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "fromValue": {"type": "string"},
                            "toValue": {"type": "string"}
                        },
                        "required": ["path", "fromValue", "toValue"]
                    },
                    "default": []
                },
                "trackedSdkVersions": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {}
                },
                "failOnUnexpectedChangedFile": {"type": "boolean", "default": True},
                "reportFile": {"type": "string"}
            },
            "required": ["projectRoot", "trackedPaths"]
        }
    },
    "unity_console_tail": {
        "bridgeOperation": "unity.console.tail",
        "description": (
            "Return recent path-backed Editor.log lines by default, or explicit Unity in-memory "
            "Console buffer items with stale-buffer caveats."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["console", "editor_log"],
                    "default": "editor_log",
                    "description": (
                        "console tails Unity's in-memory Console buffer and may be stale; "
                        "editor_log tails the path-backed Editor.log."
                    ),
                },
                "editorLogPath": {
                    "type": "string",
                    "description": "Optional Editor.log path when source=editor_log. Defaults to the host-managed project log path.",
                },
                "limit": {"type": "integer", "default": 50, "minimum": 1},
                "includeStackTraces": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include Console stack traces. They are suppressed by default so recent messages stay signal-first."
                },
                "maxPayloadBytes": {
                    "type": "integer",
                    "default": 16384,
                    "minimum": -1,
                    "description": (
                        "Deterministic byte ceiling for returned items (message, stack trace, timestamp, type, "
                        "plus a fixed per-item overhead). Oldest items are dropped first and the drop is reported "
                        "in items_dropped_for_byte_budget/byte_budget_truncated; an oversized single newest item "
                        "is content-truncated and flagged as newest_item_truncated. Omit or 0 for the 16384 "
                        "default; -1 for the unbounded raw tail. On truncation the payload names "
                        "unity_console_grep as the compact recovery tool."
                    )
                },
                "includeTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of log, warning, error, exception for source=console. Editor.log tail is untyped."
                },
                "since": {
                    "type": "string",
                    "enum": ["playmode_start", "bridge_generation", "request_id"],
                    "description": (
                        "Bound an editor_log search to the current session. Editor.log accumulates across editor "
                        "and play sessions, so an unanchored match can be a line from a previous run - the exact "
                        "false positive a shell wait loop hits. playmode_start and bridge_generation resolve to "
                        "byte offsets the editor package records in bridge_state.json; request_id uses the "
                        "offset the editor recorded in that request's journal entry and also needs "
                        "sinceRequestId. The resolved anchor and searched_from_line are echoed back in "
                        "since_anchor, and an anchor that cannot be trusted is refused by name rather than "
                        "silently widened."
                    )
                },
                "sinceRequestId": {
                    "type": "string",
                    "description": "Request id to anchor on when since=request_id. Ignored for other anchors."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_console_grep": {
        "bridgeOperation": "unity.console.grep",
        "description": (
            "Return compact Unity console items or path-backed Editor.log lines whose message, and optionally "
            "stack trace, matches a string or regex pattern. Build-pipeline progress chatter (CopyFiles, "
            "[n/m ...]) is suppressed by default because it matches whatever feature name the compile job "
            "carries; the suppressed count is always reported. Anchored Editor.log searches keep the fixed "
            "window adjacent to the anchor; a zero-match from a truncated scope is explicitly inconclusive."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "pattern": {"type": "string"},
                "excludePattern": {
                    "type": "string",
                    "description": "Drop matches that also match this pattern. Uses the same regex/ignoreCase settings as pattern."
                },
                "includeBuildPipelineNoise": {
                    "type": "boolean",
                    "default": False,
                    "description": "Keep build-pipeline progress lines (CopyFiles, [n/m ...]) in the result instead of suppressing them."
                },
                "source": {
                    "type": "string",
                    "enum": ["console", "editor_log"],
                    "default": "editor_log",
                    "description": "console searches Unity's in-memory console buffer; editor_log searches the path-backed Editor.log tail and avoids console clear/ring-buffer false negatives.",
                },
                "editorLogPath": {
                    "type": "string",
                    "description": "Optional Editor.log path when source=editor_log. Defaults to the host-managed project log path.",
                },
                "regex": {"type": "boolean", "default": False},
                "ignoreCase": {"type": "boolean", "default": True},
                "includeStackTraces": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "minimum": 1},
                "maxSearchChars": {
                    "type": "integer",
                    "default": 500000,
                    "minimum": 4096,
                    "maximum": 10000000,
                    "description": (
                        "Maximum Editor.log characters searched from a resolved anchor. When omitted, an anchored "
                        "search extends to the whole anchored scope up to the 10,000,000-character hard cap and "
                        "reports search_window_auto_extended=true; pass a value to bound the search explicitly, "
                        "and raise it after an inconclusive scope_truncated result."
                    )
                },
                "includeTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of log, warning, error, exception."
                },
                "since": {
                    "type": "string",
                    "enum": ["playmode_start", "bridge_generation", "request_id"],
                    "description": (
                        "Bound an editor_log search to the current session. Editor.log accumulates across editor "
                        "and play sessions, so an unanchored match can be a line from a previous run - the exact "
                        "false positive a shell wait loop hits. playmode_start and bridge_generation resolve to "
                        "byte offsets the editor package records in bridge_state.json; request_id uses the "
                        "offset the editor recorded in that request's journal entry and also needs "
                        "sinceRequestId. The resolved anchor and searched_from_line are echoed back in "
                        "since_anchor, and an anchor that cannot be trusted is refused by name rather than "
                        "silently widened. An anchored scope larger than the default window is searched "
                        "completely up to the hard cap unless maxSearchChars is passed; beyond the cap grep keeps "
                        "the anchor-adjacent head, reports search_window_direction/scope_truncated, and ranks "
                        "a zero-match search_verdict as inconclusive rather than proof of absence. With "
                        "source=console only since=playmode_start is supported: it bounds the in-memory console "
                        "buffer to items logged after the latest Play Mode entry and reports "
                        "since_scope_complete."
                    )
                },
                "sinceRequestId": {
                    "type": "string",
                    "description": "Request id to anchor on when since=request_id. Ignored for other anchors."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot", "pattern"]
        }
    },
    "unity_loading_timing": {
        "description": "Return compact loading/startup timing evidence by querying Unity console messages through unity.console.grep.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "markers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Loading markers, step names, timing labels, or startup phases to match."
                },
                "timingOnly": {
                    "type": "boolean",
                    "default": True,
                    "description": "When true, require timing words or duration units in addition to markers."
                },
                "includeStackTraces": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "minimum": 1},
                "includeTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of log, warning, error, exception."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_scene_snapshot": {
        "bridgeOperation": "unity.scene.snapshot",
        "description": "Return a lightweight normalized snapshot of the currently active scene.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload (including host lifecycle evidence) instead of the compact scene envelope."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_scene_open": {
        "bridgeOperation": "unity.scene.open",
        "description": "Open a project-relative Assets/... scene in Edit Mode so scenario and boot-flow validation starts from a deterministic scene.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenePath": {
                    "type": "string",
                    "description": "Project-relative Assets/... path to a Unity scene asset."
                },
                "allowDirtySceneDiscard": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, allow the operation to discard unsaved changes in currently open scenes."
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload (including host lifecycle evidence) instead of the compact scene-open envelope."
                },
                "timeoutMs": {"type": "integer", "default": 10000, "minimum": 1000}
            },
            "required": ["projectRoot", "scenePath"]
        }
    },
    "unity_scene_assert": {
        "bridgeOperation": "unity.scene.assert",
        "description": "Assert the active Unity scene name, path, root objects, or dirty state and return a pass/fail payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "expectedName": {"type": "string"},
                "expectedPath": {"type": "string"},
                "requiredRootNames": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "allowDirty": {"type": "boolean", "default": True},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_tests_run_editmode": {
        "bridgeOperation": "unity.tests.run_editmode",
        "description": "Run Unity EditMode tests and return normalized result accounting plus console-error pressure observed since request start.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "testNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "groupNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "categoryNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "assemblyNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_tests_run_playmode": {
        "bridgeOperation": "unity.tests.run_playmode",
        "description": "Run Unity PlayMode tests and return normalized result accounting plus console-error pressure observed since request start.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "testNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "groupNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "categoryNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "assemblyNames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_playmode_state": {
        "bridgeOperation": "unity.playmode.state",
        "description": "Return normalized Unity play mode state for one project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload instead of the compact play-mode summary."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_playmode_set": {
        "bridgeOperation": "unity.playmode.set",
        "description": "Request a Unity play mode state transition or pause control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["enter", "exit", "pause", "resume"]
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload instead of the compact transition summary."
                },
                "timeoutMs": {"type": "integer", "default": 180000, "minimum": 1000}
            },
            "required": ["projectRoot", "action"]
        }
    },
    "unity_game_view_configure": {
        "bridgeOperation": "unity.game_view.configure",
        "description": "Set the active Unity Game View to a specific fixed resolution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "group": {"type": "string", "description": "Optional active group override; must match the current build group."},
                "label": {"type": "string", "description": "Optional custom label for a newly created resolution entry."},
                "allowCreateCustomSize": {
                    "type": "boolean",
                    "default": False,
                    "description": "When false, fail if the requested size is not already available in Unity Game View."
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload (including host lifecycle evidence) instead of the compact game-view envelope."
                },
                "timeoutMs": {"type": "integer", "default": 10000, "minimum": 1000}
            },
            "required": ["projectRoot", "width", "height"]
        }
    },
    "unity_game_view_screenshot": {
        "bridgeOperation": "unity.game_view.screenshot",
        "description": (
            "Capture a screenshot from the Unity Editor Game View. The intended operator path is to read the "
            "returned file_path with an image reader; includeImage inlines base64 only while the encoded PNG "
            "stays inside imageBudgetBytes, and otherwise reports image_omitted_reason=payload_budget rather "
            "than overflowing the tool result. The result distinguishes render_width/render_height from "
            "screen_width/screen_height, flags any mismatch, and reports player-loop liveness/trust."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "fileName": {"type": "string"},
                "includeImage": {"type": "boolean", "default": False},
                "maxResolution": {"type": "integer", "default": 640, "minimum": 1},
                "imageBudgetBytes": {
                    "type": "integer",
                    "default": 48000,
                    "minimum": 1024,
                    "description": (
                        "Maximum encoded PNG size that may be inlined as base64. Base64 costs about 1.37 bytes "
                        "per byte, so the default caps the inline image near 66k characters."
                    )
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload instead of the compact capture summary."
                },
                "timeoutMs": {"type": "integer", "default": 10000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_compile_player_scripts": {
        "bridgeOperation": "unity.compile.player_scripts",
        "description": "Compile Unity player scripts for one target/options/defines combination without switching the active build target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "target": {"type": "string", "description": "Unity BuildTarget enum name, for example StandaloneOSX, StandaloneWindows64, Android, or iOS."},
                "optionFlags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional ScriptCompilationOptions flag names, for example DevelopmentBuild."
                },
                "extraDefines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra scripting defines for this compile only."
                },
                "name": {"type": "string", "description": "Optional display name for this compile configuration."},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 180000, "minimum": 1000}
            },
            "required": ["projectRoot", "target"]
        }
    },
    "unity_compile_matrix": {
        "bridgeOperation": "unity.compile.matrix",
        "description": "Run a sequence of compile checks across multiple targets/options/defines combinations without switching active build target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "stopOnFirstFailure": {"type": "boolean", "default": False},
                "configurations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "target": {"type": "string"},
                            "optionFlags": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "extraDefines": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["target"]
                    },
                    "minItems": 1
                },
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot", "configurations"]
        }
    },
    "unity_build_player": {
        "bridgeOperation": "unity.build_player",
        "description": "Run a Unity BuildPipeline player build through the active editor bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "buildTarget": {"type": "string"},
                "outputPath": {"type": "string"},
                "scenePaths": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "buildOptions": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "timeoutMs": {"type": "integer", "default": 600000, "minimum": 1000}
            },
            "required": ["projectRoot", "buildTarget"]
        }
    },
    "unity_compile_build_config_matrix": {
        "description": "Resolve build profiles from the project's Unity build-config asset and run the Android/iOS compile matrix through unity.compile.matrix.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "buildConfigAsset": {
                    "type": "string",
                    "description": "Optional project-relative or absolute path to the Unity *BuildConfiguration.asset. When omitted, the tool auto-detects a single matching asset in the project."
                },
                "profiles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subset of build profile names from the asset Configurations list."
                },
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["Android", "iOS"]
                    },
                    "description": "Optional subset of compile targets. Defaults to Android and iOS."
                },
                "stopOnFirstFailure": {"type": "boolean", "default": False},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, return the full bridge payload including lifecycle snapshots instead of the compact decision summary."
                },
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_scenario_capabilities": {
        "description": (
            "Return the complete public scenario definition/step schema, valid step kinds, and validate input modes. "
            "Use this before authoring flows with status, scene, console, playmode, waits, screenshots, compile/tests, "
            "project actions/hooks, ui_click, ui_exists, or ui_get_text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_scenario_validate": {
        "bridgeOperation": "unity.scenario.validate",
        "description": (
            "Validate a scripted Unity automation scenario before execution. Supply exactly one of scenario "
            "(inline object) or scenarioFile (absolute or project-relative JSON path). Call "
            "unity_scenario_capabilities for the complete step-kind and field schema."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenario": SCENARIO_DEFINITION_SCHEMA,
                "scenarioFile": {
                    "type": "string",
                    "description": "Absolute or project-relative JSON path under projectRoot."
                },
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000},
            },
            "required": ["projectRoot"],
            "oneOf": [{"required": ["scenario"]}, {"required": ["scenarioFile"]}],
        },
    },
    "unity_scenario_run": {
        "bridgeOperation": "unity.scenario.run",
        "description": "Start a scripted Unity automation scenario. Valid kinds and fields are returned by unity_scenario_capabilities. Execution continues asynchronously inside the Unity editor update loop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenario": SCENARIO_DEFINITION_SCHEMA,
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000},
            },
            "required": ["projectRoot", "scenario"],
        },
    },
    "unity_scenario_result": {
        "bridgeOperation": "unity.scenario.result",
        "description": "Read the current or completed result of a previously started Unity automation scenario.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "runId": {"type": "string"},
                "scenarioName": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_scenario_result_summary": {
        "description": "Return a compact summary of the current or completed Unity automation scenario result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "runId": {"type": "string"},
                "scenarioName": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_scenario_results_list": {
        "description": "List persisted Unity automation scenario results with compact summaries from Library/XUUnityLightMcp/scenarios/results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenarioName": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_scenario_result_latest": {
        "description": "Return the latest persisted Unity automation scenario result summary, optionally filtered by scenario name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenarioName": {"type": "string"},
            },
            "required": ["projectRoot"],
        },
    },
    "unity_scenario_run_and_wait": {
        "description": "Start a Unity automation scenario and wait until it reaches a terminal state. Valid kinds and fields are returned by unity_scenario_capabilities, including ui_click, ui_exists, and ui_get_text. By default returns a compact decision envelope; set includeFullPayload=true when asserting raw per-step payload_json, hook_name, or parity fixture fields. Full payload mode omits duplicated run_start.steps unless includeStepPayloads=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenario": SCENARIO_DEFINITION_SCHEMA,
                "timeoutMs": {"type": "integer", "default": 600000, "minimum": 1000},
                "pollIntervalMs": {"type": "integer", "default": 1000, "minimum": 100},
                "verbose": {"type": "boolean", "default": False},
                "includeFullPayload": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return the raw scenario result including full steps and payload_json. Required for smoke helpers that assert per-step payload_json, hook_name, or exact raw step fields.",
                },
                "includeStepPayloads": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true with verbose/includeFullPayload, preserve the run_start.steps launch-time copy. By default it is omitted because the terminal result already carries step payloads.",
                },
            },
            "required": ["projectRoot", "scenario"],
        },
    },
    "unity_maintenance_prune": {
        "description": "Prune stale request-journal, scenario-result, capture, and optional log artifacts under Library/XUUnityLightMcp.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "dryRun": {"type": "boolean", "default": False},
                "requestJournalMaxAgeHours": {"type": "integer", "default": 72, "minimum": 1},
                "requestJournalKeepLatest": {"type": "integer", "default": 200, "minimum": 0},
                "scenarioSuccessMaxAgeHours": {"type": "integer", "default": 168, "minimum": 1},
                "scenarioFailureMaxAgeHours": {"type": "integer", "default": 336, "minimum": 1},
                "scenarioRunningMaxAgeHours": {"type": "integer", "default": 168, "minimum": 1},
                "scenarioKeepLatestSuccess": {"type": "integer", "default": 20, "minimum": 0},
                "scenarioKeepLatestFailure": {"type": "integer", "default": 50, "minimum": 0},
                "scenarioKeepLatestRunning": {"type": "integer", "default": 20, "minimum": 0},
                "capturesMaxAgeHours": {"type": "integer", "default": 168, "minimum": 1},
                "capturesKeepLatest": {"type": "integer", "default": 20, "minimum": 0},
                "pruneLogs": {"type": "boolean", "default": False},
                "logsMaxAgeHours": {"type": "integer", "default": 168, "minimum": 1},
                "logsKeepLatest": {"type": "integer", "default": 10, "minimum": 0}
            },
            "required": ["projectRoot"]
        }
    },
}
