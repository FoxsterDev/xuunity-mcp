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
        "description": "Return a compact Unity status summary suitable for polling and low-token diagnostics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_request_final_status": {
        "description": "Resolve final disposition for one request id from the request journal and current bridge state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "requestId": {"type": "string"},
                "operation": {"type": "string"},
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
    "unity_project_action_invoke": {
        "description": "Invoke a typed project action from project_actions.yaml through a one-step Unity scenario.",
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
                "pollIntervalMs": {"type": "integer", "default": 1000, "minimum": 100}
            },
            "required": ["projectRoot", "actionId"]
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
        "description": "Run a whitelisted External Dependency Manager for Unity resolver menu item, with Android Force Resolve as the default.",
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
    "unity_console_tail": {
        "bridgeOperation": "unity.console.tail",
        "description": "Return recent Unity console items in normalized form.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "limit": {"type": "integer", "default": 50, "minimum": 1},
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
    "unity_console_grep": {
        "bridgeOperation": "unity.console.grep",
        "description": "Return compact Unity console items whose message, and optionally stack trace, matches a string or regex pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "pattern": {"type": "string"},
                "regex": {"type": "boolean", "default": False},
                "ignoreCase": {"type": "boolean", "default": True},
                "includeStackTraces": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "minimum": 1},
                "includeTypes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of log, warning, error, exception."
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
                "timeoutMs": {"type": "integer", "default": 5000, "minimum": 1000}
            },
            "required": ["projectRoot"]
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
        "description": "Run Unity EditMode tests and return normalized result accounting.",
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
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_tests_run_playmode": {
        "bridgeOperation": "unity.tests.run_playmode",
        "description": "Run Unity PlayMode tests and return normalized result accounting.",
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
                "timeoutMs": {"type": "integer", "default": 10000, "minimum": 1000}
            },
            "required": ["projectRoot", "width", "height"]
        }
    },
    "unity_game_view_screenshot": {
        "bridgeOperation": "unity.game_view.screenshot",
        "description": "Capture a screenshot from the Unity Editor Game View.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "fileName": {"type": "string"},
                "includeImage": {"type": "boolean", "default": False},
                "maxResolution": {"type": "integer", "default": 640, "minimum": 1},
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
                "timeoutMs": {"type": "integer", "default": 300000, "minimum": 1000}
            },
            "required": ["projectRoot"]
        }
    },
    "unity_scenario_validate": {
        "bridgeOperation": "unity.scenario.validate",
        "description": "Validate a scripted Unity automation scenario before execution.",
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
    "unity_scenario_run": {
        "bridgeOperation": "unity.scenario.run",
        "description": "Start a scripted Unity automation scenario. Execution continues asynchronously inside the Unity editor update loop.",
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
        "description": "Start a Unity automation scenario and wait until it reaches a terminal state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": {"type": "string"},
                "scenario": SCENARIO_DEFINITION_SCHEMA,
                "timeoutMs": {"type": "integer", "default": 600000, "minimum": 1000},
                "pollIntervalMs": {"type": "integer", "default": 1000, "minimum": 100},
                "verbose": {"type": "boolean", "default": False},
                "includeFullPayload": {"type": "boolean", "default": False},
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
