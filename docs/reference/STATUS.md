# Status

Date: `2026-10-27`
Status: `active public status snapshot`

XUUnity Light Unity MCP is a working same-host Unity Editor automation service
for MCP-capable AI agents. The current released source line is `v0.3.87`.

The offline validation-acceptance evaluator now treats saved helper measurements
as authoritative. Receipt metadata cannot hide warnings, missing rebuild evidence,
test counts or post-settle errors. This is an offline acceptance correction;
Unity execution and transport behavior are unchanged.

## Current-Source Evidence Boundaries

Compact responses no longer interpret null, empty, or whitespace-only error
containers as failures. Explicit failed verdicts and meaningful error content
still fail. Scenario summaries expose `mutation_boundary` so an applied hook is
not mistaken for an action safe to replay; pending/skipped hooks remain separate
and `automatic_replay_safe` is always false.

Scenario refresh completion must match the pending request identity. It reports
execution and settle-wait durations separately; missing or inconsistent timing
is unmeasured. Safe Mode entry, prompt, generic marker, and exit observations
are distinct log evidence. Startup emits bounded, provisional stderr updates
while waiting for bridge readiness; these do not establish a current compile
verdict or authorize clicking a dialog.

`XUUNITY_HOST_CALL_TIMING=1` enables host-side monotonic timing for MCP calls and
CLI dispatch. The stderr receipt follows stdout flush, with exclusive measured
stages and an explicit unattributed remainder; launcher startup and client
latency are excluded. Stale-artifact inspection reads the journal once per call
for all candidate requests, without a persistent journal cache. See
[Smoke Tests](../operations/SMOKE_TESTS.md#host-call-timing-diagnostic-smoke).

Prefab rendering distinguishes a produced PNG from visual acceptance: inspect
the requested state, text, visibility and pixels or run reference comparison.
Runtime uGUI clicks synchronize the existing Game View context before building
the UI tree, verify actual Screen dimensions, and refuse unresolved context as
`ui_coordinate_context_unresolved`. This does not resize the view or change zoom.

The latest focused live evidence for these changes is on macOS, Unity
`6000.0.58f2`, on the primary display: fixed-portrait click tests passed `4/4`
without skips across three canvas modes and a real occluder, at `1440x3200` and
zoom `0.35`; prefab tests passed `23/23`, refresh tests `29/29`, and asynchronous
interaction tests `4/4`. This is not proof for other Unity versions, operating
systems, or display configurations. A no-reload refresh control completed with
matching request identity; a controlled domain reload lost runtime identity and
returned explicit unresolved accounting without replaying the request. Separate
runtime and test-assembly compile-negative fixtures stopped in batchmode before
GUI acceptance, and restored positive controls passed. Remote Unity Package CI
remains waived for lack of a runner license; local evidence does not replace it.

## Current Package

Unity package:

```text
com.xuunity.light-mcp
```

Current Git UPM URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.87
```

Current package path:

```text
packages/com.xuunity.light-mcp
```

Current source coordinates Unity licensing probes and GUI editor admission with
a host-wide lock, forwards the normalized Hub licensing channel, verifies the
exact channel connection, and blocks readiness when licensing is lost.

Current source gates `unity_ui_click` on uGUI pointer reachability instead of
render alpha: a transparent `raycastTarget` hit area (for example an alpha-0
button Image framing a visible icon) is clicked and reported as
`transparent_hit_area`, while `pointer_target_status` and
`pointer_target_blocked_by` name the raycast filter that makes a target
unreachable (`canvas_group_blocks_raycasts`, `alpha_hit_test_rejected`,
`raycast_filter_rejected`, `no_raycaster`, and others). UI tree nodes report
`pointer_targetable` beside the unchanged render-visibility `visible` field, and
the scenario `ui_click` step carries the same evidence.

Current source applies the 2026-09-28 readiness/settle retro: `ensure-ready`
keeps polling after a Safe Mode observation while Editor.log still moves and
returns `ready_with_compile_errors` once the bridge attaches with compile errors
(the `Exiting safe mode` line is no longer read as the dialog); compact test
payloads carry `failures[]` up to 25 entries plus `failure_count` and
`test_result_path`; the scenario `compile_player_scripts` step waits for editor
idle before it dispatches and retries one `editor_busy` refusal, so an
`apply_then_gate` profile hook needs only `status` and `compile_player_scripts`
after it; anchored `unity_console_grep` searches the whole anchored scope up to
the hard cap unless `maxSearchChars` is passed, and `source=console` accepts
`since=playmode_start`; a stale heartbeat under 600 s during import or compile
reports `editor_busy_heartbeat_stale` with `retry_recommended=true`, a GUI
fallback that quit its own editor no longer recommends `recover-editor-session`,
and every batch summary carries a lane-independent `terminal_record`; a
reconciled PlayMode result labels the exit reload `expected_domain_reload`;
`unity_asset_snapshot` reads serialized asset fields without Play Mode.

Current source closes the separate rebuilt-versus-cache-hit evidence gap.
Direct, matrix, batch, and multi-project compile summaries report how many
assemblies Unity rebuilt and how many it accepted from cache, plus a status and
basis that make unsupported evidence explicit.

Migration note:

- `v0.3.11` and earlier used `templates/unity-package`.
- `v0.3.12+` uses `packages/com.xuunity.light-mcp`.
- `v0.3.14+` keeps the default package metadata on Unity `2021.3` and makes
  Test Framework-backed operations optional.
- `v0.3.15+` adds license-aware batch fallback and Codex helper install-target
  selection.
- `v0.3.29+` adds project-defined hook poll-until scenarios and richer compact
  scenario summaries.
- `v0.3.32+` makes `unity_scenario_run_and_wait` a compact decision-verdict
  surface by default, with lifecycle relaunch attribution and full-payload
  opt-in.
- `v0.3.34+` makes refresh, compile, build-config compile, and direct test MCP
  responses compact by default while preserving authoritative post-settle
  verdict fields and `includeFullPayload=true` recovery.
- Current source preserves both callback-time and host-idle Play Mode states on
  direct test responses and their matching persisted test result. The
  compatibility field names its source; a disagreement is explicit and never
  changes the callback-derived test verdict or totals. Full and compact
  final-status recovery preserve the same fields, including explicit legacy
  source labeling and lifecycle-churn accounting.
- Current source qualifies refresh `playmode_state_after_settle` with explicit
  source/trust metadata; bridge identity churn yields `stale_risk` and directs
  PlayMode-sensitive callers to confirm via `unity_playmode_state`.
- Current source also keeps a terminal scenario inconclusive when a confirmed
  project-hook `*_applied` mutation is followed by passive wait/status steps
  and a refresh or compile-settle failure, while explicitly separating the
  applied mutation from the unproven settle and disabling replay.
- Current source classifies every other scenario refresh-settle timeout from
  Unity-side evidence captured at the timeout instant (package settle,
  compile/import churn, busy editor, incomplete idle confirmation, or lost
  final accounting; host health adds `editor_failure`, and older-package
  results classify as `unclassified_legacy_payload`). The scenario summary and
  decision verdict promote a `refresh_timeout_recovery` block with a concrete
  recovery command and the explicit note that the Unity operation may have
  completed; the recommended next action becomes
  `request_status_summary_then_compile_gate` while the editor is reachable.
- Current source returns compact envelopes by default from `unity_scene_open`,
  `unity_scene_snapshot`, and `unity_game_view_configure`: the duplicated host
  lifecycle block is dropped, scene/view facts are preserved (including
  `root_object_count`), and `includeFullPayload=true` opts back into the full
  bridge payload — completing the compact-by-default contract across the
  interactive scene/playmode/view loop.
- Current source byte-bounds console tail payloads: `unity_console_tail` and
  the `console_tail` scenario step enforce a deterministic `maxPayloadBytes`
  ceiling (default `16384`, `-1` for the unbounded raw tail) in the Unity
  bridge, with a host-side fallback for older packages, oldest-first drops, an
  explicit newest-item truncation marker, full accounting fields, and
  `unity_console_grep` named as the compact recovery tool on truncation.
  In-memory Console tail also suppresses stack traces by default and exposes
  `includeStackTraces=true` as an explicit signal-expansion control.
- Current source makes anchored Editor.log grep absence trustworthy: a bounded
  `unity_console_grep source=editor_log` window stays adjacent to its resolved
  anchor so boot/init evidence is searched first, and any truncated zero-match
  is promoted to `search_verdict=inconclusive` with the window direction,
  partial-scope trust class, and a concrete recovery action. A complete
  anchored zero-match is explicitly `not_matched`; `unity_console_tail` keeps
  its separate recent-tail semantics.
  Operators can raise `maxSearchChars` without leaving the tool, and anchors
  from another editor PID resolve to `anchor_process_mismatch` rather than a
  false complete negative.
- Current source adds automated Unity package CI and a release tag gate: the
  `Unity Package CI` workflow compiles the package and runs EditMode/PlayMode
  self-tests on Unity `2022.3` and `6000.0` in `ugui` and `no-ugui` consumer
  lanes, a missing license secret fails loudly instead of skipping, and
  `scripts/testing/check_release_ci_gates.py` blocks tag preparation until
  `Integration Tests`, `Unity Package CI`, and `Discovery Checks` are green for
  the release SHA (re-verified in CI by the `Release Tag Gate` workflow).
- Current source adds a capability-gated uGUI PlayMode package test assembly.
  It drives the real guarded-click scenario-step path and proves exactly-once
  delivery, a decision-bearing receipt, semantic state change, the runtime
  Play Mode claim, and refusal without a receipt. The dependency-free core
  PlayMode lane remains available to projects without uGUI.
- Current source keeps passive `project_defined_hook_poll_until` readiness
  snapshots running through `status: not_started`; explicit pass/fail
  predicates still win, unmatched statuses still fail closed, and timeout stays
  authoritative.
- Current source promotes the standardized `xuunity.mutation-delta.v1` payload
  from project-defined hooks. `unity_project_action_invoke` keeps Unity
  execution success separate from acceptance: a completed mutating action is
  decision-ready only with a valid, non-destructive delta; missing/invalid
  proof or removals/count shrink produce an explicit mutation trust class,
  operator verdict, warning, and review action. Non-decision-ready verdicts
  name the schema and carry `mutation_delta_contract_doc` pointing at the
  worked contract example.
- Current source gives every catalog-backed project action a shared
  `project_action_currency` preflight. It compares the loaded editor-domain
  timestamp with the newest editor input under `Assets` and blocks stale or
  unknown domains before hook execution. Catalog actions marked
  `requiresFreshAssets: true` automatically run a forced AssetDatabase refresh,
  wait for settle/domain reload, re-check currency, and then invoke the hook.
  The standalone `unity_project_action_currency` tool and
  `unity_status_summary` expose the same evidence.
- Background execution is opt-in: the editor's `Application.runInBackground` is
  backed by `PlayerSettings.runInBackground`, so the bridge changes it only when
  the project's bridge config sets `background_execution_enabled: true`, and
  restores the original value on disable or editor quit.
  `background_execution_mode` reports `managed` or `project_owned`. Native
  autofocus remains disabled and explicit in payloads; player-loop liveness is
  still the trust boundary.
- Current source closes the 2026-08-17 play-mode liveness retro P0/P1 set:
  the bridge heartbeat samples frame advance and editor focus, and
  `unity_playmode_state` / `unity.status` / `unity_status_summary` report
  `playmode_loop_liveness` with an explicit
  `playmode_throttled_editor_unfocused` warning when a playing loop stops
  advancing frames; the host compile gate covers `playmode_set` `enter` only
  (exit is remediation and is never gated; `unity.scenario.run` dispatch is
  deliberately ungated with step-level gates owning correctness);
  compiler-evidence payloads stamp `compiler_diagnostics_trust_class`;
  `unity_project_action_invoke` is compact by default; a catalog
  `payload.action` conflict is listed and refused instead of silently
  overridden; and `unity_status_summary` warns up front on a split log lane
  (`editor_launch_lane: not_opened_by_host`).
- Current source separates readiness observations from compile verdicts.
  Compiler-diagnostic text seen while waiting for the bridge is retained as an
  observation while transient bridge attach, editor identity, and
  compile/import busy states keep polling. If readiness never settles, the
  top-level result names the live condition or log-only observation and reports
  `compile_state=unmeasured`. Recovery stays non-destructive, and the embedded
  readiness prerequisite becomes blocking with the same code instead of
  simultaneously claiming `ready=true`.
- Current source labels Editor.log health diagnoses as heuristic pattern
  matches. The non-interactive `-accept-apiupdate` launch flag is excluded from
  API Updater activity evidence, so the recovery flag cannot by itself imply an
  interactive updater dialog.
- Current source prevents Unity Asset Import Workers from attaching the MCP
  bridge before any session, transport, heartbeat, or journal file is created.
  Host discovery also rejects older worker-owned state as
  `bridge_owned_by_non_main_process`, sets `runtime_execution_allowed=false`,
  and reports compile failure, error count, and diagnostics as unknown rather
  than accepting a worker's green state as main-editor truth. Bootstrap journal
  events now record writer pid, process class, and editor-log path.
- Current source adds a fail-closed published-package consumer rollout helper.
  It reconciles explicit and ignore-independent discovery sets before edits,
  proves the global Unity/license/write lane, requires a passing canary before
  fan-out, persists an atomic resumable ledger, gives bounded workers no
  diagnosis/release/process-kill authority, re-verifies owned PID identity
  before root cleanup, and returns compact decision evidence by default.
- Current source closes the licensing/dialog GUI-launch retro cluster:
  repeatable `--unity-arg` pass-through, typed live-process/bridge-never-attached
  diagnostics with Editor.log evidence, first-cause `scenario_invalid` output,
  constrained-hook define hints, catalog-declared host-scope refusals,
  enforced apply-then-gate sequencing, poll-until default continuation,
  `--json-only`, fixed Game View guidance, and identity-verified
  `request-editor-quit --force-after-ms` escalation.
- Current source serializes licensing probes and GUI admission across projects
  and helper processes with a per-user host lock. It normalizes discovered Hub
  pipe names before forwarding them to Unity, verifies the exact channel in
  Editor.log, caches one probe per executable/version, and makes an unrecovered
  licensing-client disconnect block readiness.
- Current source closes the reusable 2026-09-03 greenfield-authoring retro
  backlog. UI reads/clicks, screenshots, and persisted scenario steps now carry
  point-of-use player-loop liveness and trust; UI/screenshot payloads separate
  effective Game View render dimensions from Unity `Screen.*`. Scenarios add
  `ui_exists` and `ui_get_text` alongside the existing guarded `ui_click`, with
  schema discovery and file-backed validation. Test verdicts expose
  request-scoped console-error pressure. The host accepts scalar setup
  `projectRoot`, exposes an approval-gated project-hook scaffold, and the
  package ships `XUUnityLightMcpMutationDelta.Create(...)` for measured hook
  proof.
- Current source makes `unity_ui_click` selector verdicts budget-aware. If
  `maxNodes` or `maxDepth` stops the UI walk, the direct tool and scenario step
  return `ui_selector_search_truncated` whether the scanned prefix found zero
  or one candidate, because neither absence nor uniqueness is proven. Their
  payloads preserve the searched scene scope, scenes not reached, node/depth
  budgets, node count, match count, and truncation reason; callers can narrow
  `targetKind` / `targetValue` / `sceneName` or raise the scenario's new
  `maxNodes` / `maxDepth` controls and retry.
  Delivered clicks now also require an observable semantic change before
  `success=true`; inert delivery reports `delivered_no_observable_effect` with
  raycast/log/hook remediation.
- Current source validates declared MCP argument types before any project
  resolution or Unity request. In particular, scalar test filters are rejected
  instead of widening to a full suite. Plain project-hook payload aliases are
  normalized or rejected rather than dropped, and status attributes request
  submissions by a domain-reload-stable `client_session_id` plus a
  `client_kind` of `mcp_server` or `cli`.
  `foreign_request_activity_detected` means a different long-lived client
  session submitted requests to this editor, so mutating work should pause
  until that session is identified. It does not mean the operator ran the
  wrapper CLI or a smoke suite against their own editor: that traffic is
  counted in `cli_requests_since_client_start` and is informational.
- `v0.3.38+` makes `unity_status_summary` compact by default for MCP callers,
  with `payload_mode` markers and full nested diagnostics available through
  `includeFullPayload=true`.
- `v0.3.39+` adds compact output for batch helper CLI commands; current source
  makes it the default while preserving `--output full` for diagnosis.
- `v0.3.67+` makes the multi-project compile runner consume that compact shape
  without losing Unity or transport outcomes. It falls back to named summary
  and Unity-confirmed result artifacts, records the chosen evidence source, and
  reports absent matrix counters as unavailable rather than zero.
- Current source makes the default multi-project recovery side effect explicit:
  if the runner proves that it closed a host-opened editor, it emits
  `BATCH_EDITOR_CLOSE_NOTICE` before compile and retains the editor process id,
  closeout classification, and close path in each result and the aggregate.
  Missing recovery evidence is reported as unavailable, not as a negative.
- `v0.3.36+` makes `ensure-ready` compact by default,
  adds active editor-log identity and path-backed `editor_log` grep, removes
  duplicated scenario `run_start.steps` unless `includeStepPayloads=true`,
  adds post-change validation phase/churn dashboard output, and ships a
  public-safe config-applying project-action build template.
- The old path is kept only as a migration pointer for users pinned to
  `v0.3.11`.

OpenUPM status:

- the package layout is OpenUPM-ready
- the package is not documented as published on OpenUPM yet
- use Git UPM until the OpenUPM package page exists

## Current Surface

SDK rollout safety (`v0.3.45` plus current-source hardening):

- Android `unity.edm4u.resolve` now refuses to fire unless
  `BuildTarget.Android` is active and Android Build Support is loaded. Passing
  request payloads expose the target precondition while keeping
  `resolver_output_freshness=unproven` and `decision_ready=false`.
- Current source adds capability-gated `unity.sdk.android_resolve` /
  `unity_sdk_android_resolve` / `request-sdk-android-resolve`. It uses EDM4U's
  callback as completion proof, requires stable SHA-256 generated outputs across
  idle ticks, and verifies explicit expected coordinates before returning
  `trust_class=decision_grade` and `decision_ready=true`.
- Current source adds closed-project `unity.sdk.package_restore` /
  `unity_sdk_package_restore` / `request-sdk-package-restore`. Unity batchmode
  waits for an idle-stable registered package graph, publishes an atomic
  run-bound `xuunity.sdk-package-restore.v1` receipt with package ids/versions,
  dependency-XML hashes, and manifest/lock hashes, then exits. Missing receipts,
  nonzero exits, timeouts, an open project, or unproven exit all fail closed.
- `unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard` provides the
  generated-file vertical slice of the SDK rollout gate. Git-tracked paths use
  a named Git ref; Git-untracked paths can use an explicit `Library/` capture
  bound to project path, Unity version, package-lock hash, and configured SDK
  versions. Capture rejects dirty trees, and comparison rejects stale
  fingerprints or tampered snapshots. The host-side compact proof also detects
  missing required markers, stale expected versions, unallowlisted changes,
  invalid structured files, and normalization-only XML/Gradle rewrites without
  opening Unity. Current source registers every published pass/fail JSON report
  as an `sdk_generated_diff_report` artifact and returns its hash plus registry
  pointer. GUI admission control, batch resolve, and portfolio orchestration
  remain separate open slices.

Implemented Unity-side operations:

- `unity.status`
- `unity.capabilities.get`
- `unity.health.probe`
- `unity.build_target.get`
- `unity.build_target.switch`
- `unity.editor.quit`
- `unity.project.refresh`
- `unity.project_action.currency`
- `unity.package.install_test_framework`
- `unity.edm4u.resolve`
- `unity.sdk.android_resolve`
- `unity.sdk.dependency.verify`
- `unity.console.tail`
- `unity.console.grep`
- `unity.scene.snapshot`
- `unity.scene.open`
- `unity.scene.assert`
- `unity.tests.run_editmode`
- `unity.tests.run_playmode`
- `unity.playmode.state`
- `unity.playmode.set`
- `unity.game_view.configure`
- `unity.game_view.screenshot`
- `unity.compile.player_scripts`
- `unity.compile.matrix`
- `unity.build_player`
- `unity.scenario.validate`
- `unity.scenario.run`
- `unity.scenario.result`

Implemented Unity-side scenario step families include status, health probe,
project refresh, scene open/snapshot/assert, console grep, compile, tests, Play
Mode, Game View, waits, project-defined hooks, poll-until hooks, and
catalog-backed `project_action` steps with generated currency/asset-refresh
preflights.

Implemented host-side MCP tools and helpers:

- `unity_status`
- `unity_license_capabilities`
- `unity_tests_cancel`
- `unity_device_list`
- `unity_device_install`
- `unity_device_app`
- `unity_device_logcat`
- `unity_device_files`
- `unity_device_screen`
- `unity_device_frame_pacing`
- `unity_device_metrics`
- `unity_device_coldstart_ab`
- `unity_status_summary`
- `unity_capabilities`
- `unity_health_probe`
- `unity_console_tail`
- `unity_console_grep`
- `unity_loading_timing`
- `unity_scene_snapshot`
- `unity_scene_open`
- `unity_scene_assert`
- `unity_compile_player_scripts`
- `unity_compile_matrix`
- `unity_tests_run_editmode`
- `unity_tests_run_playmode`
- `unity_playmode_state`
- `unity_playmode_set`
- `unity_build_player`
- `unity_game_view_configure`
- `unity_game_view_screenshot`
- `unity_project_refresh`
- `unity_build_target_get`
- `unity_build_target_switch`
- `unity_edm4u_resolve`
- `unity_sdk_android_resolve`
- `unity_sdk_dependency_verify`
- `unity_sdk_generated_diff_guard`
- `xuunity_setup_plan`
- `xuunity_setup_apply`
- `xuunity_setup_validate`
- `xuunity_uninstall_plan`
- `xuunity_uninstall_apply`
- `unity_package_install_test_framework`
- `unity_request_final_status`
- `unity_scenario_result_summary`
- `unity_scenario_results_list`
- `unity_scenario_result_latest`
- `unity_scenario_run_and_wait`
- `unity_compile_build_config_matrix`
- `unity_project_action_list`
- `unity_project_action_currency`
- `unity_project_action_invoke`
- `unity_artifact_register`
- `unity_artifact_write_report`
- `unity_ui_reference_register`
- `unity_ui_reference_validate`
- `unity_ui_reference_compare`
- `unity_ui_fixture_validate`
- `unity_ui_vision_packet`
- `unity_ui_vision_submit`
- `unity_ui_interaction_validate`
- `unity_prefab_snapshot`
- `unity_prefab_validate`
- `unity_asset_snapshot`
- `unity_ui_tree_snapshot`
- `unity_ui_query`
- `unity_ui_exists`
- `unity_ui_get_text`
- `unity_ui_get_bounds`
- `unity_prefab_render`
- `unity_prefab_mutate`
- `unity_ui_click`
- `unity_maintenance_prune`
- `unity_ensure_ready`
- `project-discovery-report`
- `registry-context-report`
- `registry-prune-contexts`
- `setup-plan`
- `setup-apply`
- `uninstall-plan`
- `uninstall-apply`
- `validate-setup`
- `install-test-framework`
- `license-capabilities`
- `open-editor`
- `ensure-ready`
- `recover-editor-session`
- `restore-editor-state`
- `request-status-summary`
- `request-final-status`
- `request-latest-status`
- `request-cancel`
- `request-stale-cleanup`
- `request-console-grep`
- `request-loading-timing`
- `request-build-player`
- `batch-compile`
- `batch-compile-matrix`
- `batch-build-config-compile-matrix`
- `batch-editmode-tests`
- `batch-test-framework-version-regression`
- `batch-build-player`
- `project-action-list`
- `project-action-invoke`
- `project-hook-scaffold`
- `artifact-register`
- `artifact-write-report`
- `artifact-probe`
- `sdk-generated-diff-guard`
- `request-sdk-package-restore`

## Current Validation Evidence

Current release evidence for `v0.3.87`:

| Area | Evidence | Result |
| --- | --- | --- |
| Package metadata | `packages/com.xuunity.light-mcp/package.json` | `name=com.xuunity.light-mcp`, `version=0.3.87`, `unity=2021.3`, no hard Test Framework dependency |
| Host Python tests | `scripts/testing/run_host_python_tests.sh` | `1196` tests run, `1182` passed, `14` skipped, zero failures/errors. Skips cover native Windows behavior and the manual-only Unity workflow contract. |
| Focused Unity checks | macOS Unity `6000.0.58f2`, primary display | Refresh `29/29`, RenderAndClick `23/23`, fixed-portrait interaction `4/4`, asynchronous interaction `4/4`, no skips. Separate targeted scopes; no current cross-version matrix claim. See [evidence boundaries](#current-source-evidence-boundaries). |
| Public site checks | `scripts/testing/run_site_ui_checks.sh` | Public site Playwright checks passed for `v0.3.87`: `42/42`. |
| Git tag visibility | Remote Git refs and GitHub Release | [`v0.3.87`](https://github.com/FoxsterDev/xuunity-mcp/releases/tag/v0.3.87) is published at `c84bb74fa61123e3a7917e7098ca34d7d6c7b79e`; the tag remains immutable. |

## Historical Validation Records

The following measurements were not rerun as a cross-version `v0.3.87` matrix.
Original counts and explicitly named release versions are retained. Record links
show where the observations were documented; they do not independently establish
the exact source loaded by every historical Editor session.

| Area | Evidence | Result |
| --- | --- | --- |
| Historical source uGUI pointer targeting | Package self-tests in scaffolded consumer projects | EditMode `178/178` on Unity `2022.3.67f2` and `6000.0.58f2` with uGUI, `128/128` on Unity `6000.0.58f2` without uGUI; the uGUI PlayMode assembly passes `17` with `2` environment skips on `6000.0.58f2`, including a live `EventSystem` raycast that reaches an alpha-0 `Image` stacked over an opaque button. PlayMode was not run on `2022.3`. |
| `v0.3.73` rebuilt/cache compile evidence | Consumer editors on Unity `2022.3.62f3` and `6000.0.58f2` using the release source | Both versions passed package EditMode `161/161`. Live player-script compile returned `9` rebuilt / `30` cached assemblies on Unity `2022.3.62f3` and `76` rebuilt / `181` cached assemblies on Unity `6000.0.58f2`, each `measured` with zero compiler errors or warnings; original package pins and editor ownership were restored. | <!-- release-version: historical -->
| Historical play-mode liveness measurement | Interactive MCP observation of an unfocused editor in Play Mode | With `playmode_state=playing` and `health_status=healthy`, the payload reports `playmode_loop_liveness=throttled`, `playmode_frames_advanced_last_interval=0`, `editor_application_focused=false`, `playmode_liveness_warning=playmode_throttled_editor_unfocused`, and the focus/no-throttling remediation; `unity_status_summary` carries the same fields. |
| Historical source structural compile diagnostics | Focused host contract plus a live duplicate-reference fault injection on Unity `2022.3.62f3` | Focused refresh/compile/test envelope coverage passes `129/129`. A real duplicate `.asmdef` reference produced `assembly_definition_error` with session-scoped `Editor.log` evidence and recovered to authoritative compile green after probe removal. Package tests passed EditMode `68/68` and PlayMode `18` passed with one expected skip; the editor was closed and consumer manifest/lock bytes were restored. |
| Compact MCP envelopes | Changelog and regression coverage for `0.3.32`-`0.3.53` | Scenario decision verdicts, compact operation/readiness/status summaries, authoritative post-settle compile/test/refresh fields, editor-log identity, scenario step-payload opt-ins, PlayMode already-playing stale-risk summaries, deterministic scene-open setup, opt-in compact batch helper output, safer `Editor.log` console grep/tail defaults, compact transport/idle timeout errors, compile-first post-change validation, lane-agnostic GUI-fallback compile evidence, and requested-filter zero-match verdicts are documented with full-payload recovery. |
| `v0.3.53` release package tests | Clean devmode projects on installed Unity editors | Unity `2022.3.62f3` and `6000.0.58f2` each pass EditMode `62/62` and dependency-free PlayMode `5/5`, with post-settle compile green and verified editor closeout. |
| Historical source guarded interaction proof | Development-system Unity `2022.3.62f3` and main-consumer Unity `6000.0.58f2`, both in devmode | Package PlayMode tests pass `7/7` on each consumer, including the uGUI-gated guarded-click delivery and refusal tests; each project was restored to its original Git UPM pin afterwards. |
| Historical source full package gate | Clean devmode projects on Unity `2022.3.62f3` and `6000.0.58f2` | Both versions pass EditMode `86/86` and dependency-free PlayMode `5/5`, plus acceptance, refresh, and compile contracts with authoritative post-settle compile green and verified editor closeout. |
| Reference-driven UI acceptance | Unity `2021.3` and `6000.0` EditMode over `XUUnity.MCP.SelfTest` | `77/78` pass on both editors with one graphics-device-dependent test correctly self-skipping; the graphics-enabled `XUUnity.MCP.UiRenderClick` category passes `11/11`; a project without `com.unity.ugui` compiles with zero errors and builds only the core editor assembly. |
| Typed resolver oracle | Historical source Unity `2022.3` + EDM4U callback adapter | Inactive Android and resolver callback failure fail closed; a project-local Maven coordinate passes with callback success, two stable SHA-256 samples, explicit dependency proof, `trust_class=decision_grade`, and a cleared package-operation busy flag. |
| Consumer regression route | Compile preflight + scenario/contract + PlayMode lifecycle + consistency | Unity `6000.0` passes compile preflight `6/6`, acceptance `10/10`, refresh/compile contract, settled-state and lifecycle recovery, healthy final Edit Mode with zero compiler errors/unrecovered abandons, and project-action consistency. |
| Historical source readiness/settle retro fixes (2026-09-28) | Host suite plus a live consumer hub project on Unity `6000.0.58f2` in devmode | Host suite `1156` OK with `14` expected platform skips. Package EditMode `128/128`, `6/6`, `39/39` including seven new tests. A define-changing profile hook followed by a 2 s wait let the scenario compile step gate `16.0` s on editor idle and compile `87` rebuilt / `189` cached assemblies with zero errors (scenario passed in `41` s); the restore profile compiled `82` rebuilt / `181` cached with an immediate dispatch. A play smoke `console_grep since=playmode_start` resolved its anchor with a complete scope (`64` matches; an absent marker `not_matched`), and `unity_asset_snapshot` read an enum override from the consumer's build configuration asset without Play Mode. Editor closeout and the consumer package pin were restored. |
| Historical Git UPM release smoke | Clean Unity project pinned to an earlier public tag | Bridge reached healthy `git_pinned` status, Android APK smoke passed, package self-tests passed, and closeout verified process exit. |
| Multi-project compile matrix | Public summary evidence from consumer validation | `9/9` projects, `38/38` compile lanes, `0` failures |

- Ugui pointer targeting: [recorded 2026-09-30](https://github.com/FoxsterDev/xuunity-mcp/blob/fa9190f1dcd4856032820e05d5a2830f455fe80f/docs/reference/STATUS.md).
- Structural compile diagnostics: [recorded 2026-08-08](https://github.com/FoxsterDev/xuunity-mcp/blob/487b07e873356e07f83ec0e1b4325c832d4da370/docs/reference/STATUS.md).
- Guarded interaction proof: [recorded 2026-08-02](https://github.com/FoxsterDev/xuunity-mcp/blob/01cb97e1606ab6db161a43a87de9a229d7d43a9c/docs/reference/STATUS.md).
- Full package gate: [recorded 2026-08-26](https://github.com/FoxsterDev/xuunity-mcp/blob/878807ba4574b845592025a736a3eea623f72b14/docs/reference/STATUS.md).
- Reference-driven ui acceptance: [recorded 2026-07-30](https://github.com/FoxsterDev/xuunity-mcp/blob/c7bdc74da302be76d09c4e8cba8bf11ee10d113e/docs/reference/STATUS.md).
- Typed resolver oracle and consumer regression route: [recorded 2026-07-29](https://github.com/FoxsterDev/xuunity-mcp/blob/9ad31c9acfb9a7b80cd28cd547adda05e8796567/docs/reference/STATUS.md).
- Readiness/settle observations: [recorded 2026-09-28](https://github.com/FoxsterDev/xuunity-mcp/blob/af1807d0d1c92ea3b7a283effcf84874cf934a37/docs/reference/STATUS.md).
- Multi-project compile matrix: [recorded 2026-07-02](https://github.com/FoxsterDev/xuunity-mcp/blob/669e9125a3f9e6eb93f002fdf06af2342295b33e/docs/reference/STATUS.md).

Cross-platform capabilities and historical observations (live observations in
this table are not new `v0.3.87` measurements):

| Target | Status | Notes |
| --- | --- | --- |
| macOS host tools | `validated on this host` | Shell wrapper, host tests, same-host Unity readiness/status/health probes, and post-change validation route passed. |
| `v0.3.70` compile-warning evidence (historical, not re-measured since) | `host + Unity 2022 + Unity 6000 validated` | Focused host `211/211`, full host `1011/1011` with 14 expected platform skips, site UI `42/42`, and clean Unity `2022.3.62f3` plus `6000.0.58f2` package lanes pass. Each Unity lane passed EditMode `104/104`, PlayMode `5/5`, acceptance `9/9`, compile contract `2/2`, and verified closeout. |
| Linux host tools | `portable by design` | Bash-compatible launchers/templates exist; run a Linux Unity smoke before claiming live proof. |
| Native Windows clients | `templates provided; CI-exercised` | `run.cmd`, `run.ps1`, and Windows client configs exist; the Windows CI leg drives the real `.cmd` launcher through MCP stdio `initialize`/`tools/list`/`tools/call` end to end (`tests/test_mcp_stdio_e2e.py`), incl. a Cyrillic+spaces project path, plus: a real install through the refresh launcher serving MCP from the installed copy and a spawn of the exact command written by `--install-claude-config` (`tests/test_installed_delegate_e2e.py`), the verbatim README PowerShell 5.1 quickstart with a UTF-16 plan file (`tests/test_readme_quickstart_windows_e2e.py`), the file-IPC transport against a live editor-simulator process incl. a two-process torn-read stress (`tests/test_file_ipc_bridge_simulator_e2e.py`), and cp866/cp1252 hostile-codepage legs (`tests/test_ru_console_codepage_e2e.py`); a live Windows host session with a real Unity editor still needs execution proof. |
| Unity 2021.3+ | `default package line` | Checked-in package metadata targets Unity `2021.3`; setup wizard chooses optional Test Framework recommendations per project. |
| Optional Test Framework | `capability-gated` | Core readiness stays healthy when missing; tests report `disabled_missing_dependency`, `disabled_dependency_too_old`, or supported with `upgrade_recommended` when an existing dependency should be reviewed. |
| License-aware batch fallback | `implemented; host + contention validated` | `license-capabilities` reports batchmode support, blocker code, probe log, recommended lane, cache provenance, and active-probe state. One 12-project live contention sweep launched one probe and served 11 waiters from cache; that probe timed out, so batch entitlement remains unproven on this host. |
| Hub-aware GUI admission | `implemented; macOS live validated` | Platform-native process parsing accepts exactly one live Hub-owned licensing client, normalizes the editor channel, reports only redacted fingerprints, and verifies the exact connection in Editor.log. Two Unity `6000.0.58f2` GUI editors were restored licensed after contention validation. |
| Bounded compact terminal envelope | `implemented; host-unit validated` | Wrapper `--compact-summary` suppresses nested stdout/stderr and emits one JSON envelope capped at 8192 bytes. |
| PlayMode lifecycle terminalization | `implemented; host-unit validated` | A passed suite plus a fresh healthy post-reload Edit Mode state returns `confirmed_success_after_lifecycle_churn` with retry disabled. |

## Package Source Modes

Use Git UPM for production consumers:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.87"
  }
}
```

Use local `file:` only while developing this MCP package:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp"
  }
}
```

Mode switch helpers:

```bash
bash xuunity_light_unity_mcp.sh devmode --project-root /path/to/UnityProject
bash xuunity_light_unity_mcp.sh prodmode --project-root /path/to/UnityProject
```

Rules:

- `devmode` points a Unity project at the local package working tree.
- `prodmode` pins the Unity project to the published release tag that matches
  the package version, for example `#v0.3.87`.
- `prodmode` refuses to pin when that release tag is not visible on `origin`.
- both modes remove the package lock entry so Unity re-resolves honestly.

## Install And Smoke Commands

Install host helper:

```bash
bash init_xuunity_light_unity_mcp.sh
```

Enable one project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Readiness check:

```bash
bash xuunity_light_unity_mcp.sh ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor \
  --background-open
```

Package self-test lane:

```bash
templates/smoke/run_package_self_tests.sh \
  --project-root /path/to/UnityProject \
  --mode all
```

Multi-project compile matrix:

```bash
scripts/testing/run_multi_project_batch_compile_matrix.sh \
  --repo-root /path/to/repo-with-unity-projects \
  --parallelism 4
```

With its default `--close-live-editors` policy, the runner prints
`BATCH_EDITOR_CLOSE_NOTICE` before continuing whenever recovery proves that it
closed a host-opened Unity editor. The final JSON repeats every verified close
under `editor_close_side_effects`.

## Safety Status

Current safety guarantees:

- editor-only package assembly
- disabled-by-default bridge activation
- no normal player-build footprint by default
- no dynamic Roslyn execution path
- no SignalR or external relay dependency
- local same-host transport model
- capability-gated reflection-sensitive operations
- mutable bridge/request artifacts stay under `Library/XUUnityLightMcp/`

Current limitations:

- OpenUPM publication is still pending
- Linux and native Windows need live host smoke proof before strong support claims
- Game View operations remain reflection-gated and must be capability-probed
- native OS autofocus is intentionally not implemented; runtime background
  execution reduces focus dependence, while liveness evidence remains required
- License-aware batch fallback is host-capability based; unknown probe failures
  keep batch as a diagnostic path. A verified licensed editor proves only the
  GUI lane, while the host lock prevents concurrent projects from starting a
  probe storm or racing a GUI launch against an active probe
- device/runtime automation is outside the base package
- broad unrestricted editor mutation is intentionally out of scope

## Related Docs

- `../../INSTALL.md`
- `FEATURES.md`
- `../../SECURITY.md`
- `COMPARISON.md`
- `DISCOVERY.md`
- `../agents/AI_INTEGRATION.md`
- `../agents/AGENT_WORKFLOWS.md`
- `../operations/BUILD_AUTOMATION.md`
- `../operations/SMOKE_TESTS.md`
- `../architecture/ROADMAP.md`
