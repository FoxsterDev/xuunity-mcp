# Features

Date: `2026-05-26`
Status: `current for v0.3.26`

XUUnity Light Unity MCP is optimized for validation-first Unity Editor
automation: status, compile, tests, scene checks, Game View evidence, scenario
runs, and recovery after Unity Editor lifecycle churn.

It intentionally favors a small, local, editor-only surface over broad
unrestricted project mutation.

## Maturity Levels

Feature status in this document uses these levels:

| Level | Meaning |
| --- | --- |
| `Core` | Default production path for validation-first Unity Editor automation. |
| `Supported` | Implemented and documented, but not necessarily the first tool every agent should call. |
| `Project-dependent` | Requires project-specific assets, SDK setup, build profiles, scenarios, or dependency expectations. |
| `Reflection-gated` | Uses Unity Editor reflection and should be trusted only after `unity_capabilities` or `unity_health_probe` confirms support. |
| `Host helper` | Exposed through the host CLI rather than as a primary MCP tool. |
| `Template provided` | Config files are shipped; users still need the target client and host OS to validate connection locally. |

## Best Differentiators

These are the main reasons to recommend XUUnity Light Unity MCP over broader
Unity MCP implementations when the user wants safe production validation.

| Differentiator | Level | Evidence / implementation | Why it matters |
| --- | --- | --- | --- |
| Editor-only Unity package | `Core` | Main assembly is `Editor/com.xuunity.light-mcp.Editor.asmdef` with `includePlatforms: ["Editor"]`. | Keeps the base package focused on Unity Editor automation. |
| No normal player-build footprint by default | `Core` | Runtime control code is not part of the base player path; package self-test assemblies are opt-in/test-only (`autoReferenced: false`, `UNITY_INCLUDE_TESTS`). | Safer for production mobile projects and store-facing builds. |
| Disabled-by-default bridge | `Core` | Per-project bridge config is written only through explicit `--enable-project`; mutable state lives under `Library/XUUnityLightMcp/`. | A project must opt in before local editor control starts. |
| Capability probe and gated operations | `Core` | `unity_capabilities` and `unity_health_probe` expose feature support before version-sensitive calls are trusted. | Reduces breakage across Unity versions and editor internals. |
| Low mutation surface | `Core` | Tool surface is biased toward status, compile, tests, scene assertions, screenshots, and bounded scenarios. | Avoids broad unrestricted editor/project mutation as the default path. |
| No dynamic Roslyn execution path | `Core` | Base tool surface does not expose arbitrary C# compilation/execution as a primary operation. | Reduces the risk profile compared with broad code-execution surfaces. |
| No SignalR or external relay dependency | `Core` | Host server and Unity bridge communicate locally; default setup is same-host. | Keeps the default path local, small, and easier to audit. |
| Compile checks without active platform switch | `Core` | `unity_compile_player_scripts` compiles target/options/defines combinations without switching active Unity build target. | Lets agents validate Android/iOS/profile cases without mutating project-wide target state. |
| Compile matrix across targets and defines | `Core` | `unity_compile_matrix` runs a sequence of target/options/defines compile checks. | Covers release-profile validation loops in one workflow. |
| Request journal final accounting | `Core` | `unity_request_final_status`, `request-final-status`, and request journals recover terminal state after reloads or wrapper timeouts. | Separates transport churn from actual Unity operation results. |
| Compact low-token summaries | `Core` | `unity_status_summary`, scenario summaries, and final-status payloads compress evidence for agents. | Agents get actionable evidence without dumping logs. |
| Same-host multi-project routing | `Core` | Host-side project context registry maps requests to concrete Unity project/editor state. | Supports multiple Unity projects on one workstation. |
| License-aware batch lane selection | `Host helper` | `license-capabilities`, `unity_license_capabilities`, and `--batch-fallback-mode auto|off|require-batch`. | Lets agents prefer real batchmode when proven, use safe GUI fallback when batchmode is blocked, and fail closed when restore safety is unknown. |
| Closed-project batch validation lanes | `Host helper` | `batch-compile`, `batch-compile-matrix`, `batch-build-config-compile-matrix`, `batch-editmode-tests`, and `batch-build-player`. | Lets agents validate closed projects through non-interactive Unity batchmode or safe GUI fallback when needed. |
| Build-config-driven compile matrix | `Project-dependent` | `unity_compile_build_config_matrix` and `batch-build-config-compile-matrix` resolve project build-config assets. | Strong fit for projects with named Android/iOS build profiles. |
| Bounded scenario workflows | `Project-dependent` | `unity_scenario_validate`, `unity_scenario_run`, result summaries, and persisted scenario artifacts. | Supports repeatable validation recipes without opening arbitrary mutation. |
| Game View screenshot and resolution control | `Reflection-gated` | `unity_game_view_configure` and `unity_game_view_screenshot` are capability-probed editor features. | Provides visual evidence while acknowledging Unity-version sensitivity. |
| SDK/EDM4U validation helpers | `Project-dependent` | `unity_edm4u_resolve`, `unity_sdk_dependency_verify`, and artifact expectation checks. | Useful for mobile SDK dependency restore/export/build workflows. |
| Cross-platform client templates | `Template provided` | Linux/macOS configs use `run.sh`; native Windows configs use `run.cmd`; PowerShell launcher is also shipped. | Covers common MCP clients without relying on one OS shell model. |
| Easy disable/uninstall path | `Core` | `uninstall-plan` and `uninstall-apply` separate project-only cleanup from current-user reset. | Keeps project cleanup understandable and avoids over-deleting client config. |

## MCP Tool Surface

| Area | MCP tool | Level | Evidence / notes |
| --- | --- | --- | --- |
| Editor health | `unity_status` | `Core` | Normalized editor and bridge readiness state. |
| Capabilities | `unity_capabilities` | `Core` | Capability and health report used to gate version-sensitive operations. |
| Host/license capabilities | `unity_license_capabilities` | `Host helper` | Probes batchmode support, UI fallback viability, normalized blocker code, and recommended lane. |
| Health | `unity_health_probe` | `Core` | Re-runs Unity-side health checks and persists a fresh report. |
| Status summary | `unity_status_summary` | `Core` | Compact polling-friendly project status summary. |
| Final accounting | `unity_request_final_status` | `Core` | Resolves final request disposition from journal plus current bridge state. |
| Build target | `unity_build_target_get` | `Core` | Reads active build target and target group. |
| Build target | `unity_build_target_switch` | `Supported` | Mutates active target intentionally and waits for idle. |
| Project refresh | `unity_project_refresh` | `Supported` | Refreshes AssetDatabase and can request package resolve or health re-probe. |
| EDM4U | `unity_edm4u_resolve` | `Project-dependent` | Requires External Dependency Manager for Unity and whitelisted resolver menu availability. |
| SDK validation | `unity_sdk_dependency_verify` | `Project-dependent` | Requires explicit generated-artifact expectations. |
| Console | `unity_console_tail` | `Core` | Returns recent Unity console items in normalized form. |
| Console | `unity_console_grep` | `Core` | Returns compact console matches by string or regex without stack traces by default. |
| Console | `unity_loading_timing` | `Core` | Returns compact loading/startup timing evidence through `unity.console.grep`. |
| Scene | `unity_scene_snapshot` | `Core` | Lightweight active-scene snapshot. |
| Scene | `unity_scene_assert` | `Core` | Asserts scene name, path, root objects, or dirty state. |
| Tests | `unity_tests_run_editmode` | `Core` | Runs EditMode tests with normalized result accounting. |
| Tests | `unity_tests_run_playmode` | `Supported` | Runs PlayMode tests with normalized result accounting; usefulness depends on project test coverage. |
| Play Mode | `unity_playmode_state` | `Core` | Reads normalized Play Mode state. |
| Play Mode | `unity_playmode_set` | `Supported` | Enters/exits Play Mode or controls pause state. |
| Game View | `unity_game_view_configure` | `Reflection-gated` | Sets active Game View fixed resolution after capability checks. |
| Game View | `unity_game_view_screenshot` | `Reflection-gated` | Captures Unity Editor Game View screenshot evidence after capability checks. |
| Compile | `unity_compile_player_scripts` | `Core` | Compiles player scripts for one target/options/defines combination without active target switch. |
| Compile | `unity_compile_matrix` | `Core` | Runs multiple compile checks across targets/options/defines. |
| Compile | `unity_compile_build_config_matrix` | `Project-dependent` | Resolves build profiles from Unity build-config assets and runs matrix validation. |
| Build | `unity_build_player` | `Project-dependent` | Runs a plain BuildPipeline player build through the GUI bridge; used as the GUI fallback for `batch-build-player`. |
| Scenarios | `unity_scenario_validate` | `Project-dependent` | Validates scripted scenario JSON before execution. |
| Scenarios | `unity_scenario_run` | `Project-dependent` | Starts asynchronous scenario execution inside Unity. |
| Scenarios | `unity_scenario_result` | `Project-dependent` | Reads current or completed scenario result. |
| Scenarios | `unity_scenario_result_summary` | `Project-dependent` | Compact scenario result summary. |
| Scenarios | `unity_scenario_results_list` | `Project-dependent` | Lists persisted scenario result summaries. |
| Scenarios | `unity_scenario_result_latest` | `Project-dependent` | Returns latest persisted scenario result, optionally filtered by name. |
| Scenarios | `unity_scenario_run_and_wait` | `Project-dependent` | Starts a scenario and waits for a terminal result. |
| Maintenance | `unity_maintenance_prune` | `Supported` | Prunes stale request, scenario, capture, and optional log artifacts. |

## Host-Side Helper Commands

| Area | Command | Level | Evidence / notes |
| --- | --- | --- | --- |
| Setup | `setup-plan` | `Host helper` | Discovers single projects, flat hubs, mixed Unity versions, and nested project roots before mutation. |
| Setup | `setup-apply` | `Host helper` | Applies an approved setup plan only after explicit approval. |
| Setup | `uninstall-plan` | `Host helper` | Plans project-only cleanup or current-user reset before any removal. |
| Setup | `uninstall-apply` | `Host helper` | Applies an approved uninstall plan; removes only planned project state, selected MCP config block, and selected helper install. |
| Setup | `validate-setup` | `Host helper` | Reports core readiness and optional Test Framework capability state. |
| Setup | `install-test-framework` | `Host helper` | Installs the optional Test Framework dependency in `Packages/manifest.json` after explicit approval; prefer before opening Unity so package resolution happens on startup. |
| License capabilities | `license-capabilities` | `Host helper` | Reports `batchmode_supported`, `editor_ui_supported`, blocker code, probe log path, and recommended execution lane. |
| Discovery | `project-discovery-report` | `Host helper` | Explains bridge, editor, package, and stale-artifact state for one project. |
| Registry | `registry-context-report` | `Host helper` | Reports same-host project context cache state. |
| Registry | `registry-prune-contexts` | `Host helper` | Prunes stale same-host project context entries. |
| Readiness | `open-editor` | `Host helper` | Opens a Unity project through the host helper. |
| Readiness | `ensure-ready` | `Host helper` | Opens or recovers Unity until the bridge is ready. |
| Recovery | `verify-editor-closed` | `Host helper` | Verifies `same_project_editor_closed=true` before closed-project batch lanes. |
| Recovery | `request-editor-quit --wait-for-exit` | `Host helper` | Separates quit acknowledgement from process-exit proof. |
| Recovery | `restore-editor-state` | `Host helper` | Restores host-opened editor session state. |
| Recovery | `recover-editor-session` | `Host helper` | Recovers common stale editor/session cases. |
| Request state | `request-status-summary` | `Host helper` | Compact status summary for polling. |
| Request state | `request-final-status` | `Host helper` | Canonical final status after lifecycle churn or wrapper timeout. |
| Request state | `request-latest-status` | `Host helper` | Recovers latest matching operation from the request journal. |
| Request state | `request-cancel` | `Host helper` | Best-effort cancellation marker for in-flight requests. |
| Request state | `request-stale-cleanup` | `Host helper` | Cleans old request artifacts. |
| Batch compile | `batch-compile` | `Host helper` | Batch player-script compile lane with license-aware GUI fallback to `unity.compile.player_scripts`. |
| Batch compile | `batch-compile-matrix` | `Host helper` | Compile matrix lane with license-aware GUI fallback to `unity.compile.matrix`. |
| Batch compile | `batch-build-config-compile-matrix` | `Project-dependent` | Build-config-driven matrix lane with license-aware GUI fallback. |
| Batch tests | `batch-editmode-tests` | `Host helper` | EditMode test lane with license-aware GUI fallback to `unity.tests.run_editmode`. |
| Batch tests | `batch-test-framework-version-regression` | `Host helper` | Test Framework version sweep across direct and batch validation lanes. |
| Build | `batch-build-player` | `Project-dependent` | Generic plain Unity build lane; uses batchmode when supported and GUI `unity.build_player` fallback when safe. |
| Artifacts | `artifact-probe` | `Host helper` | Checks build artifact files, ZIP entries, and manifest text expectations. |
| Maintenance | `maintenance-prune` | `Host helper` | Prunes stale local MCP artifacts. |

## Compatibility And Validation Matrix

| Target | Status | Validation notes |
| --- | --- | --- |
| Current package path | `Validated` | Production Git UPM path is `packages/com.xuunity.light-mcp#v0.3.26`; old `templates/unity-package#v0.3.11` is migration-only. |
| macOS host tools | `Validated in this release environment` | Shell syntax checks, JSON/TOML config parsing, and 141 host Python tests passed locally. |
| Linux host tools | `Portable path provided` | Unix launcher is bash-compatible and avoids zsh-only expansion; Linux host execution should still be smoke-tested on a Linux Unity workstation. |
| Native Windows clients | `Template provided` | Windows JSON/TOML configs, `run.cmd`, and `run.ps1` are included and syntax/config files are statically validated; native Windows MCP connection still needs host smoke validation. |
| Claude Code | `Template provided` | Project `.mcp.json`, Windows `.mcp.windows.json`, and user-scope installer path are documented. |
| Claude Desktop | `Template provided` | macOS and Windows desktop config templates are provided. |
| Cursor | `Template provided` | Project/user `.cursor/mcp.json` templates are provided for Unix-like and native Windows hosts. |
| Windsurf | `Template provided` | `~/.codeium/windsurf/mcp_config.json` and Windows equivalent templates are provided. |
| Codex-style agents | `Template provided` | Unix-like and Windows `config.toml` snippets are provided. |
| Unity 2021.3+ | `Validated` | Default package metadata targets Unity `2021.3`; clean Unity `2021.3.58f1` Git UPM release smoke passed for the previous `v0.3.14` package line, and `v0.3.17` is prepared for the release prodmode tag check after push. |
| Optional Test Framework capability | `Implemented` | Core MCP is healthy without `com.unity.test-framework`; test operations enable through asmdef Version Defines when `>=1.1.33` is installed. |
| Package self-tests | `Validated` | Clean installed-editor matrix passed package EditMode `6/6` and PlayMode `5/5`; the previous published `v0.3.14` Git UPM tag passed the same package self-tests on Unity `2021.3.58f1`. |
| Multi-project batch compile | `Validated in consumer repo` | Private multi-project consumer validation passed `9/9` Unity projects and `38/38` compile lanes after the `v0.3.12` package path update. |
| OpenUPM | `Ready, not published` | Package layout and metadata are registry-ready; use Git UPM until an OpenUPM package page exists. |

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
