# Features

Date: `2026-07-06`
Status: `current for v0.3.74`

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
| Project-action currency gate | `Core` | Every typed or scenario `project_action` becomes `project_action_currency -> project_defined_hook`; `requiresFreshAssets: true` prepends a settled forced refresh. | Prevents a green player compile or stale AssetDatabase from producing a confident result from old editor state. |
| Low mutation surface | `Core` | Tool surface is biased toward status, compile, tests, scene assertions, screenshots, and bounded scenarios. | Avoids broad unrestricted editor/project mutation as the default path. |
| No dynamic Roslyn execution path | `Core` | Base tool surface does not expose arbitrary C# compilation/execution as a primary operation. | Reduces the risk profile compared with broad code-execution surfaces. |
| No SignalR or external relay dependency | `Core` | Host server and Unity bridge communicate locally; default setup is same-host. | Keeps the default path local, small, and easier to audit. |
| Compile checks without active platform switch | `Core` | `unity_compile_player_scripts` compiles target/options/defines combinations without switching active Unity build target. | Lets agents validate Android/iOS/profile cases without mutating project-wide target state. |
| Compile matrix across targets and defines | `Core` | `unity_compile_matrix` runs a sequence of target/options/defines compile checks. | Covers release-profile validation loops in one workflow. |
| Request journal final accounting | `Core` | `unity_request_final_status`, `request-final-status`, and request journals recover terminal state after reloads or wrapper timeouts. | Separates transport churn from actual Unity operation results. |
| Compact low-token summaries | `Core` | `ensure-ready` defaults to `payload_mode=compact_ensure_ready`; `unity_status_summary` defaults to `payload_mode=compact_status_summary`; `unity_scenario_run_and_wait` defaults to `payload_mode=compact_decision`; refresh, compile, build-config compile, direct EditMode/PlayMode test MCP tools, and common timeout/transport failure envelopes default to compact decision fields. | Agents get actionable evidence without dumping logs; `--include-full-payload`, `includeFullPayload=true`, verbose scenario mode, or emitted full-payload recovery arguments remain available for deep debug. |
| Same-host multi-project routing | `Core` | Host-side project context registry maps requests to concrete Unity project/editor state. | Supports multiple Unity projects on one workstation. |
| License-aware batch lane selection | `Host helper` | `license-capabilities`, `unity_license_capabilities`, and `--batch-fallback-mode auto|off|require-batch`; per-user host locking and a shared executable/version probe cache serialize admission across projects and helper processes. | Prevents probe storms, keeps GUI launches from racing a probe, prefers real batchmode only when proven, and uses the licensed GUI fallback when batch entitlement is unavailable. |
| Exact Hub licensing handoff | `Host helper` | Hub pipe discovery forwards the editor-normalized channel and reports separate redacted discovery/forwarding fingerprints; Editor.log confirms the exact forwarded connection. | Detects mismatched or lost licensing connections before an editor is reported ready, without exposing the raw local channel. |
| Closed-project batch validation lanes | `Host helper` | `batch-compile`, `batch-compile-matrix`, `batch-build-config-compile-matrix`, `batch-editmode-tests`, and `batch-build-player`. | Lets agents validate closed projects through non-interactive Unity batchmode or safe GUI fallback when needed. |
| Build-config-driven compile matrix | `Project-dependent` | `unity_compile_build_config_matrix` and `batch-build-config-compile-matrix` resolve project build-config assets. | Strong fit for projects with named Android/iOS build profiles. |
| Bounded scenario workflows | `Project-dependent` | `unity_scenario_validate`, `unity_scenario_run`, `unity_scenario_run_and_wait`, poll-until hooks, project-action steps, result summaries, and persisted scenario artifacts. | Supports repeatable validation recipes and project-local hooks without opening arbitrary mutation; full payload mode omits duplicated `run_start.steps` unless `includeStepPayloads=true`. |
| Editor-log identity, grep, and tail | `Core` | `unity.status`, bridge state, `unity_status_summary`, `request-status-summary`, and `ensure-ready` surface active Editor.log identity; `unity_console_grep` / `request-console-grep` and `unity_console_tail` / `request-console-tail` support `source=editor_log`. | Lets agents distinguish console-buffer false negatives from path-backed Editor.log evidence. |
| Game View screenshot and resolution control | `Reflection-gated` | `unity_game_view_configure` and `unity_game_view_screenshot` are capability-probed editor features. | Provides visual evidence while acknowledging Unity-version sensitivity. |
| SDK/EDM4U validation helpers | `Project-dependent` | `unity_edm4u_resolve`, `unity_sdk_dependency_verify`, and artifact expectation checks. | Android resolve fails closed unless Android is the active build target. Menu execution remains request evidence; dependency and generated-diff checks are still required for a trustworthy rollout verdict. |
| Cross-platform client templates | `Template provided` | Linux/macOS configs use shell launchers; native Windows configs use `.cmd`; PowerShell `.ps1` launchers are also shipped for environments that allow them. | Covers common MCP clients without relying on one OS shell model. |
| Easy disable/uninstall path | `Core` | `uninstall-plan` and `uninstall-apply` separate project-only cleanup from current-user reset. | Keeps project cleanup understandable and avoids over-deleting client config. |

## MCP Tool Surface

| Area | MCP tool | Level | Evidence / notes |
| --- | --- | --- | --- |
| Editor health | `unity_status` | `Core` | Normalized editor and bridge readiness state. |
| Capabilities | `unity_capabilities` | `Core` | Capability and health report used to gate version-sensitive operations. |
| Host/license capabilities | `unity_license_capabilities` | `Host helper` | Probes batchmode support, UI fallback viability, normalized blocker code, and recommended lane. |
| Health | `unity_health_probe` | `Core` | Re-runs Unity-side health checks and persists a fresh report. |
| Status summary | `unity_status_summary` | `Core` | Compact polling-friendly project status summary by default; pass `includeFullPayload=true` for nested discovery, transport, state-group, timing, and artifact details. Surfaces editor-domain currency, runtime background execution, play-mode liveness evidence (`playmode_loop_liveness`, frame advance, editor focus, throttle warning), `compiler_diagnostics_trust_class` provenance, and the `editor_launch_lane` split-log-lane notice. |
| Final accounting | `unity_request_final_status` | `Core` | Resolves final request disposition from journal plus current bridge state. |
| Build target | `unity_build_target_get` | `Core` | Reads active build target and target group. |
| Build target | `unity_build_target_switch` | `Supported` | Mutates active target intentionally and waits for idle. |
| Project refresh | `unity_project_refresh` | `Supported` | Refreshes AssetDatabase and can request package resolve or health re-probe; compact default preserves settled refresh fields and full payload is opt-in. |
| EDM4U | `unity_edm4u_resolve` | `Project-dependent` | Requires External Dependency Manager for Unity, Android Build Support, a whitelisted resolver menu, and active BuildTarget.Android for the Android lane. The result explicitly leaves resolver-output freshness unproven. |
| SDK validation | `unity_sdk_dependency_verify` | `Project-dependent` | Requires explicit generated-artifact expectations. |
| Console | `unity_console_tail` | `Core` | Returns recent path-backed Editor.log lines by default; explicit `source=console` returns normalized in-memory Console-buffer items with stale-buffer caveats. Payloads are byte-bounded (`maxPayloadBytes`, default 16384; `-1` for the unbounded raw tail) with explicit drop/truncation accounting and `unity_console_grep` named as the compact recovery tool. |
| Console | `unity_console_grep` | `Core` | Returns compact console or Editor.log matches by string or regex without stack traces by default; use `source=editor_log` for path-backed log-presence checks. |
| Console | `unity_loading_timing` | `Core` | Returns compact loading/startup timing evidence through `unity.console.grep`. |
| Scene | `unity_scene_snapshot` | `Core` | Lightweight active-scene snapshot. Compact scene envelope by default (scene facts, root objects, `root_object_count`); `includeFullPayload=true` returns the full bridge payload with host lifecycle evidence. |
| Scene | `unity_scene_open` | `Core` | Opens a project-relative `Assets/...` scene in Edit Mode for deterministic boot-flow or scenario setup; dirty open scenes require explicit discard approval. Compact scene-transition envelope by default; `includeFullPayload=true` opts into the full bridge payload. |
| Scene | `unity_scene_assert` | `Core` | Asserts scene name, path, root objects, or dirty state. |
| Tests | `unity_tests_run_editmode` | `Core` | Runs EditMode tests with normalized result accounting. |
| Tests | `unity_tests_run_playmode` | `Supported` | Runs PlayMode tests with normalized result accounting; usefulness depends on project test coverage. |
| Play Mode | `unity_playmode_state` | `Core` | Reads normalized Play Mode state plus game-loop liveness evidence: `playmode_loop_liveness` (`advancing`/`throttled`/`paused`/`not_playing`/`unknown`) from frame advance between heartbeats, editor focus, and the `playmode_throttled_editor_unfocused` warning with remediation. |
| Play Mode | `unity_playmode_set` | `Supported` | Enters/exits Play Mode or controls pause state. Only `enter` is compile-gated; `exit`/`pause`/`resume` always pass the host compile gate because exiting Play Mode is the remediation that lets Unity run its deferred recompile. |
| Game View | `unity_game_view_configure` | `Reflection-gated` | Sets active Game View fixed resolution after capability checks. Compact resolved-view envelope by default; `includeFullPayload=true` opts into the full bridge payload. |
| Game View | `unity_game_view_screenshot` | `Reflection-gated` | Captures Unity Editor Game View screenshot evidence after capability checks. Compact capture envelope by default; base64 inlines only within `imageBudgetBytes` (default `48000`, ~66k base64 characters), otherwise the payload reports `image_omitted_reason=payload_budget` and the operator reads `file_path`. |
| Compile | `unity_compile_player_scripts` | `Core` | Compiles player scripts for one target/options/defines combination without active target switch; `v0.3.70` compact summaries preserve authoritative post-settle truth plus warning occurrence/unique counts and bounded diagnostic rows, while current source adds rebuilt-versus-cache-hit evidence. |
| Compile | `unity_compile_matrix` | `Core` | Runs multiple compile checks across targets/options/defines; `v0.3.70` compact summaries preserve per-lane verdicts, post-settle compiler truth, and aggregated warning evidence, while current source adds aggregate and per-configuration rebuild/cache evidence. |
| Compile | `unity_compile_build_config_matrix` | `Project-dependent` | Resolves build profiles from Unity build-config assets and runs matrix validation; compact default and full payload opt-in match other compile tools. |
| Build | `unity_build_player` | `Project-dependent` | Runs a plain BuildPipeline player build through the GUI bridge; used as the GUI fallback for `batch-build-player`. Configured BuildTool projects should expose a project action such as `build.dev_android` when raw BuildPipeline builds are non-representative. |
| Scenarios | `unity_scenario_validate` | `Project-dependent` | Validates scripted scenario JSON before execution. |
| Scenarios | `unity_scenario_run` | `Project-dependent` | Starts asynchronous scenario execution inside Unity. |
| Scenarios | `unity_scenario_result` | `Project-dependent` | Reads current or completed scenario result. |
| Scenarios | `unity_scenario_result_summary` | `Project-dependent` | Compact scenario result summary. |
| Scenarios | `unity_scenario_results_list` | `Project-dependent` | Lists persisted scenario result summaries. |
| Scenarios | `unity_scenario_result_latest` | `Project-dependent` | Returns latest persisted scenario result, optionally filtered by name. |
| Scenarios | `unity_scenario_run_and_wait` | `Project-dependent` | Starts a scenario and waits for a terminal compact decision verdict with trust class, failure class, recommended next action, compact steps, and lifecycle relaunch attribution (`editor_relaunched`, previous/current editor PID, bridge generations, and cold-start reason) when applicable. |
| Project actions | `unity_project_action_list` | `Project-dependent` | Lists catalog-backed project actions from `project_actions.yaml`. |
| Project actions | `unity_project_action_currency` | `Core` | Read-only preflight reporting whether the loaded editor domain is current with editor inputs under `Assets`; optionally resolves an action's `requiresFreshAssets` declaration without refreshing or invoking it. |
| Project actions | `unity_project_action_invoke` | `Project-dependent` | Invokes a typed project action through a persisted scenario with mutation approval and a mandatory editor-domain currency gate. `requiresFreshAssets: true` actions receive an automatic settled AssetDatabase refresh before the shared gate and hook. Compact envelope by default (currency, action id, outcome, evidence scalars, mutation trust verdict); `includeFullPayload=true` restores the scenario echo and nested scenario summary. |
| Artifacts | `unity_artifact_register` | `Supported` | Registers artifact metadata in the project MCP artifact registry without invoking Unity. |
| Artifacts | `unity_artifact_write_report` | `Supported` | Writes a text report to an approved project output root and registers it. |
| UI reference | `unity_ui_reference_register` | `Supported` | Registers a supplied design reference as a `ui-reference.v1` acceptance contract with viewport, regions, declared masks, tolerance profile, and acceptance lanes. |
| UI reference | `unity_ui_reference_validate` | `Supported` | Validates a registered reference (schema, expected-image hash, viewport agreement, region geometry, mask policy) and reports same-aspect capture resolutions. |
| UI reference | `unity_ui_reference_compare` | `Supported` | Compares a Game View capture against a reference on a resolution-independent similarity grid and publishes actual/overlay/diff/metrics artifacts with a `reference_acceptance` verdict. |
| UI reference | `unity_ui_fixture_validate` | `Supported` | Validates a `ui-fixture.v1` readiness report (fixture and state id, frozen clock, pinned locale, data source, viewport, ready predicate) and derives `visual_determinism`; live data without a recorded payload hash is downgraded to `unproven`. |
| UI reference | `unity_ui_vision_packet` | `Supported` | Renders a side-by-side reference/candidate review sheet with failed regions outlined and ships the rubric, so a multimodal judge can rule on style, placement, and size. Hash-bound to the exact image pair; numeric scores withheld by default so the judgement is not anchored. |
| UI reference | `unity_ui_vision_submit` | `Supported` | Records a rubric judgement against a packet, checks the arithmetic (observation per criterion, overall clamped to the worst required criterion plus one), records judge role, and returns the vision lane. |
| UI reference | `unity_ui_interaction_validate` | `Supported` | Validates `ui-interaction.v1` evidence from a scenario result; Play-mode delivery proves a user path, Edit-mode delivery blocks the lane instead of passing it. |
| Prefab read | `unity_prefab_snapshot` | `Supported` | Reads a prefab asset hierarchy as normalized `ui.read.v1` nodes without opening it for editing. |
| Prefab read | `unity_prefab_validate` | `Supported` | Reports typed pre-PlayMode defects (missing script GUID, missing or mistyped serialized reference, missing nested prefab) and lists lanes it could not evaluate. |
| UI read | `unity_ui_tree_snapshot` | `Supported` | Snapshots the live uGUI hierarchy with paths, active state, effective CanvasGroup alpha, canvas order, screen bounds, and text/font/material where a backend reader is present. |
| UI read | `unity_ui_query` | `Supported` | Returns nodes matching an AND-combined selector (name, type, path, text, visibility, interactability) and reports ambiguity. |
| UI read | `unity_ui_exists` | `Supported` | Existence check over the same selector model; reports match count and ambiguity, never answers from a screenshot. |
| UI read | `unity_ui_get_text` | `Supported` | Returns the semantic text of a single matched node; zero, ambiguous, and text-less matches are distinct typed failures. |
| UI read | `unity_ui_get_bounds` | `Supported` | Returns the screen-space rect of a single matched node so a failed comparison region maps to concrete geometry. |
| UI render | `unity_prefab_render` | `Supported` | Renders a prefab in an isolated preview scene at the declared viewport and safe area without booting the app, returning the PNG plus the snapshot it rendered. Requires com.unity.ugui. |
| UI mutation | `unity_prefab_mutate` | `Supported` | Typed atomic prefab transaction through the Editor API; previews by default, re-validates bindings, rolls the whole batch back on any failure, and emits a reversible inverse patch. |
| UI interaction | `unity_ui_click` | `Supported` | One guarded EventSystem click to a unique selector; refuses ambiguous, hidden, disabled, raycast-transparent, and handler-less targets. A node/depth-budget-limited search is `ui_selector_search_truncated` with scope/budget evidence because absence or uniqueness is unproven. Requires com.unity.ugui. |
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
| License capabilities | `license-capabilities` | `Host helper` | Reports batch/UI capability, blocker code, recommended lane, and redacted Hub IPC resolution with typed machine-recoverable versus user-action admission. |
| Diagnostic bundle | `diagnostic-retro-bundle` | `Host helper` | Emits a bounded, sanitized, read-only project-version/package/license/editor/request/test/restore bundle without raw process commands or licensing channels. |
| Discovery | `project-discovery-report` | `Host helper` | Explains bridge, editor, package, and stale-artifact state for one project. |
| Registry | `registry-context-report` | `Host helper` | Reports same-host project context cache state. |
| Registry | `registry-prune-contexts` | `Host helper` | Prunes stale same-host project context entries. |
| Readiness | `open-editor` | `Host helper` | Resolves the project-owned Unity version, auto-forwards exactly one verified Hub licensing channel, and returns redacted launch provenance; repeatable explicit `--unity-arg` values remain supported. |
| Readiness | `ensure-ready` | `Host helper` | Opens or recovers Unity until the bridge is ready; wrong versions, Hub-channel ambiguity, user-action licensing, and bridge startup blockers have distinct typed outcomes. |
| Recovery | `verify-editor-closed` | `Host helper` | Verifies `same_project_editor_closed=true` before closed-project batch lanes. |
| Recovery | `request-editor-quit --wait-for-exit` | `Host helper` | Separates quit acknowledgement from process-exit proof; optional `--force-after-ms` performs one identity-reverified same-project termination and remains off by default. |
| Recovery | `restore-editor-state` | `Host helper` | Restores host-opened editor session state. |
| Recovery | `recover-editor-session` | `Host helper` | Recovers common stale editor/session cases. |
| Request state | `request-status-summary` | `Host helper` | CLI status summary for polling and diagnostics when MCP tools are not yet visible in the client session. |
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
| Project actions | `project-action-list` | `Project-dependent` | Lists catalog-backed project actions from the host helper. |
| Project actions | `project-action-invoke` | `Project-dependent` | Invokes a catalog-backed action through scenario normalization from the host helper. |
| Project actions | `project-hook-scaffold` | `Template provided` | Generates a project hook class, project action fragment, activation scenario, and checklist for review. |
| Console | `request-console-grep` | `Host helper` | CLI route for compact console grep summaries. |
| Console | `request-loading-timing` | `Host helper` | CLI route for compact loading/startup timing summaries. |
| Artifacts | `artifact-register` | `Host helper` | Registers artifact metadata from the host helper. |
| Artifacts | `artifact-write-report` | `Host helper` | Writes and registers a report artifact from the host helper. |
| Artifacts | `artifact-probe` | `Host helper` | Checks build artifact files, ZIP entries, and manifest text expectations. |
| Maintenance | `maintenance-prune` | `Host helper` | Prunes stale local MCP artifacts. |

## Compatibility And Validation Matrix

| Target | Status | Validation notes |
| --- | --- | --- |
| Current package path | `Validated` | Production Git UPM path is `packages/com.xuunity.light-mcp#v0.3.74`; old `templates/unity-package#v0.3.11` is migration-only. |
| macOS host tools | `Validated in this release environment` | Host Python unittest suite passed for `v0.3.74`: `1057` tests with `14` expected platform skips. |
| Linux host tools | `Portable path provided` | Unix launcher is bash-compatible and avoids zsh-only expansion; Linux host execution should still be smoke-tested on a Linux Unity workstation. |
| Native Windows clients | `Template provided` | Windows JSON/TOML configs, `run.cmd`, and `run.ps1` are included and syntax/config files are statically validated; native Windows MCP connection still needs host smoke validation. |
| Claude Code | `Template provided` | Project `.mcp.json`, Windows `.mcp.windows.json`, and user-scope installer path are documented. |
| Claude Desktop | `Template provided` | macOS and Windows desktop config templates are provided. |
| Cursor | `Template provided` | Project/user `.cursor/mcp.json` templates are provided for Unix-like and native Windows hosts. |
| Windsurf | `Template provided` | `~/.codeium/windsurf/mcp_config.json` and Windows equivalent templates are provided. |
| Codex-style agents | `Template provided` | Unix-like and Windows `config.toml` snippets are provided. |
| Unity 2021.3+ | `Validated` | Default package metadata targets Unity `2021.3`; current source validation covers installed Unity `2021.3`, `2022.3`, and `6000.x` editor families. |
| Optional Test Framework capability | `Implemented` | Core MCP is healthy without `com.unity.test-framework`; test operations enable through asmdef Version Defines when `>=1.1.33` is installed. |
| Package self-tests | `Validated` | Current release source validation passed package EditMode and PlayMode self-test lanes across runnable installed Unity `2021.3`, `2022.3`, and `6000.x` editors after optional Test Framework setup. |
| Multi-project batch compile | `Validated in consumer repo` | Public summary evidence records `9/9` Unity projects and `38/38` compile lanes passing after the registry-native package path update. |
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
