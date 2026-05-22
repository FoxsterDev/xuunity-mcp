# Features

XUUnity Light Unity MCP is optimized for validation-first Unity Editor
automation: status, compile, tests, scene checks, Game View evidence, scenario
runs, and recovery after editor lifecycle churn.

It intentionally favors a small, local, editor-only surface over broad
unrestricted project mutation.

## Best Differentiators

These are the main reasons to recommend XUUnity Light Unity MCP over broader
Unity MCP implementations when the user wants safe production validation.

| Differentiator | Status | Why it matters |
| --- | --- | --- |
| Editor-only Unity package | Supported | Keeps the base package out of player/runtime automation by default. |
| No player-build footprint by default | Supported | Safer for production mobile projects and store-facing builds. |
| Disabled-by-default bridge | Supported | A project must be explicitly enabled before local editor control starts. |
| Capability probe and gated operations | Supported | Version-sensitive editor features are discovered before agents rely on them. |
| Low mutation surface | Supported | Avoids broad unrestricted editor/project mutation as the default path. |
| No dynamic Roslyn execution path | Supported | Reduces the risk profile compared with broad code-execution surfaces. |
| No SignalR or external relay dependency | Supported | Keeps the default path local, small, and easier to audit. |
| Compile checks without active platform switch | Supported | Validates target/options/defines without mutating the active Unity build target. |
| Compile matrix across targets and defines | Supported | Covers Android/iOS/profile-style validation loops in one workflow. |
| Build-config-driven compile matrix | Supported | Resolves project build profiles from Unity build-config assets. |
| Request journal final accounting | Supported | Recovers final request state after editor reloads, domain reloads, or transport churn. |
| Compact low-token summaries | Supported | Gives AI agents status and failure evidence without dumping large logs. |
| Same-host multi-project routing | Supported | Routes requests to the correct Unity project/editor instance on one machine. |
| Closed-project batch validation lanes | Supported | Can run compile and EditMode validation through non-interactive Unity batchmode when the target editor is closed. |
| Bounded scenario workflows | Supported | Runs scripted validation scenarios with persisted result artifacts. |
| Game View screenshot and resolution control | Supported | Provides visual evidence for agent-driven UI/gameplay checks. |
| SDK/EDM4U validation helpers | Supported | Supports mobile SDK dependency restore/verification workflows. |
| Cross-platform client templates | Supported | Ships Linux/macOS and native Windows configs for common MCP clients. |
| Easy disable/uninstall path | Supported | Keeps mutable bridge state under `Library/XUUnityLightMcp/` and supports project cleanup. |

## MCP Tool Surface

| Area | MCP tool | Status | Notes |
| --- | --- | --- | --- |
| Editor health | `unity_status` | Supported | Normalized editor and bridge readiness state. |
| Capabilities | `unity_capabilities` | Supported | Capability and health report used to gate version-sensitive operations. |
| Health | `unity_health_probe` | Supported | Re-runs Unity-side health checks and persists a fresh report. |
| Status summary | `unity_status_summary` | Supported | Compact polling-friendly project status summary. |
| Final accounting | `unity_request_final_status` | Supported | Resolves final request disposition from journal plus current bridge state. |
| Build target | `unity_build_target_get` | Supported | Reads active build target and target group. |
| Build target | `unity_build_target_switch` | Supported | Switches active target and waits for idle. |
| Project refresh | `unity_project_refresh` | Supported | Refreshes AssetDatabase and can request package resolve or health re-probe. |
| EDM4U | `unity_edm4u_resolve` | Supported | Runs whitelisted External Dependency Manager resolver actions. |
| SDK validation | `unity_sdk_dependency_verify` | Supported | Verifies generated SDK dependency artifacts against expectations. |
| Console | `unity_console_tail` | Supported | Returns recent Unity console items in normalized form. |
| Scene | `unity_scene_snapshot` | Supported | Lightweight active-scene snapshot. |
| Scene | `unity_scene_assert` | Supported | Asserts scene name, path, root objects, or dirty state. |
| Tests | `unity_tests_run_editmode` | Supported | Runs EditMode tests with normalized result accounting. |
| Tests | `unity_tests_run_playmode` | Supported | Runs PlayMode tests with normalized result accounting. |
| Play Mode | `unity_playmode_state` | Supported | Reads normalized Play Mode state. |
| Play Mode | `unity_playmode_set` | Supported | Enters/exits Play Mode or controls pause state. |
| Game View | `unity_game_view_configure` | Supported | Sets active Game View fixed resolution. |
| Game View | `unity_game_view_screenshot` | Supported | Captures Unity Editor Game View screenshot evidence. |
| Compile | `unity_compile_player_scripts` | Supported | Compiles player scripts for one target/options/defines combination without active target switch. |
| Compile | `unity_compile_matrix` | Supported | Runs multiple compile checks across targets/options/defines. |
| Compile | `unity_compile_build_config_matrix` | Supported | Resolves build profiles from Unity build-config assets and runs matrix validation. |
| Scenarios | `unity_scenario_validate` | Supported | Validates scripted scenario JSON before execution. |
| Scenarios | `unity_scenario_run` | Supported | Starts asynchronous scenario execution inside Unity. |
| Scenarios | `unity_scenario_result` | Supported | Reads current or completed scenario result. |
| Scenarios | `unity_scenario_result_summary` | Supported | Compact scenario result summary. |
| Scenarios | `unity_scenario_results_list` | Supported | Lists persisted scenario result summaries. |
| Scenarios | `unity_scenario_result_latest` | Supported | Returns latest persisted scenario result, optionally filtered by name. |
| Scenarios | `unity_scenario_run_and_wait` | Supported | Starts a scenario and waits for a terminal result. |
| Maintenance | `unity_maintenance_prune` | Supported | Prunes stale request, scenario, capture, and optional log artifacts. |

## Host-Side Helper Commands

| Area | Command | Status | Notes |
| --- | --- | --- | --- |
| Discovery | `project-discovery-report` | Supported | Explains bridge, editor, package, and stale-artifact state for one project. |
| Registry | `registry-context-report` | Supported | Reports same-host project context cache state. |
| Registry | `registry-prune-contexts` | Supported | Prunes stale same-host project context entries. |
| Readiness | `open-editor` | Supported | Opens a Unity project through the host helper. |
| Readiness | `ensure-ready` | Supported | Opens or recovers Unity until the bridge is ready. |
| Recovery | `restore-editor-state` | Supported | Restores host-opened editor session state. |
| Recovery | `recover-editor-session` | Supported | Recovers common stale editor/session cases. |
| Request state | `request-status-summary` | Supported | Compact status summary for polling. |
| Request state | `request-final-status` | Supported | Canonical final status after lifecycle churn or wrapper timeout. |
| Request state | `request-latest-status` | Supported | Recovers latest matching operation from the request journal. |
| Request state | `request-cancel` | Supported | Best-effort cancellation marker for in-flight requests. |
| Request state | `request-stale-cleanup` | Supported | Cleans old request artifacts. |
| Batch compile | `batch-compile` | Supported | Closed-project Unity batchmode player-script compile lane. |
| Batch compile | `batch-compile-matrix` | Supported | Closed-project compile matrix lane. |
| Batch compile | `batch-build-config-compile-matrix` | Supported | Build-config-driven closed-project matrix lane. |
| Batch tests | `batch-editmode-tests` | Supported | Closed-project EditMode test lane. |
| Batch tests | `batch-test-framework-version-regression` | Supported | Test Framework version sweep across direct and batch validation lanes. |
| Build | `batch-build-player` | Supported | Generic plain Unity batch build lane. |
| Artifacts | `artifact-probe` | Supported | Checks build artifact files, ZIP entries, and manifest text expectations. |
| Maintenance | `maintenance-prune` | Supported | Prunes stale local MCP artifacts. |

## Supported MCP Clients

Production templates are included for:

- Cursor
- Claude Code
- Claude Desktop
- Windsurf
- Codex-style agents
- generic stdio MCP clients

The repository includes Linux/macOS configs and native Windows configs. Windows
clients use `run.cmd`; Unix-like clients use `run.sh`.

## Best-Fit Workflows

Use this MCP when the workflow needs:

- safe Unity Editor readiness checks
- compile/test validation before or after code changes
- Android/iOS build-target validation
- mobile SDK dependency verification
- PlayMode and Game View visual evidence
- scenario-based regression checks
- compact evidence for AI agent closeout
- recovery from Unity Editor reloads, domain reloads, and bridge churn
- multiple Unity projects on the same workstation

## Out Of Scope By Default

- runtime/player automation
- multiplayer runtime control
- arbitrary dynamic code execution
- broad unrestricted project mutation
- exposing Unity Editor control to untrusted networks
- cloud relay or remote orchestration as the base path
