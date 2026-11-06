# Agent Workflows

Date: `2026-07-01`
Status: `active public guidance`

## Purpose

This document gives MCP-capable coding agents production-grade Unity workflows
for XUUnity Light Unity MCP.

This closes Priority 15: add example agent workflows.

The workflows are public-safe patterns distilled from recurring production
Unity mobile project work: compile-first validation, Editor readiness gates,
scenario evidence, SDK dependency checks, batch validation, lifecycle recovery,
and closeout reporting. They intentionally avoid project-private names,
business logic, credentials, and game-specific implementation details.

Use this file after the MCP is installed and a target Unity project is known.
Use `AI_INTEGRATION.md` for install/integration rules and this file for the
day-to-day agent playbooks.

For portfolio or single-project `com.xuunity.light-mcp` version bumps, use the
lean package-bump playbook first: `PACKAGE_BUMP_FAST_PATH.md`.

## Workflow Contract

Every agent workflow should follow this contract:

1. Resolve exactly one Unity project root.
2. Confirm the bridge is enabled only for that project.
3. Prefer `ensure-ready` over blind sleeps.
4. Do not start multiple activation-heavy commands in parallel for one Unity
   project until the bridge is healthy; serialize `ensure-ready`, compile,
   tests, PlayMode, and scenario start.
5. Run capability and health probes before version-sensitive operations.
6. Prefer compile validation before tests when scripts changed.
7. Prefer read and validation tools before mutation.
8. Record structured evidence, not only a pass/fail sentence.
9. Resolve interrupted requests through `request-final-status`.
10. Restore host-opened editor state at closeout.
11. Report unsupported capabilities as explicit validation gaps.
12. For substantial MCP implementation plans, update the design-plan history and
    perform a code/docs self-review before final closeout.
13. Launch the editor through `ensure-ready --open-editor`; a self-launched
    editor splits the log lane for the session, so every console log query then
    needs an explicit `editorLogPath` (watch for
    `editor_launch_lane: not_opened_by_host` on `unity_status_summary`).
14. Treat a play-mode observation as evidence only while
    `playmode_loop_liveness` is `advancing`; an unfocused editor throttles the
    game loop while every editor health field stays green.
15. Treat `editor_domain_current=true` as a precondition for project actions;
    mark asset-reading actions `requiresFreshAssets: true` so refresh and settle
    happen automatically before the shared currency gate.

Stop immediately when:

- the referenced paths map to more than one Unity project
- `ensure-ready` reports a startup blocker
- `unity_capabilities` or `unity_health_probe` marks the required operation unsupported
- Unity is in Safe Mode and the selected startup policy is fail-fast
- a validation failure is already specific enough to act on

## Operator Discipline For An Edit And Evidence Cycle

Finish one coherent source-edit batch before validation; freeze that batch while
compile, tests, or scenarios consume it. After C# edits, choose the supported
compile-first route from the actual editor state: use closed-project batch
validation only after closure is proven, or reuse the live bridge compile lane
when the target editor is already open. Unknown editor ownership is a blocker
for lane selection. Follow Workflows 2 and 9 rather than opening the GUI before
the compile gate or launching a competing editor.

Wait for the selected operation's typed terminal result and the required editor
settle/readiness evidence before advancing. Request delivery, a healthy heartbeat,
or an idle sample alone does not prove completion. Recover interrupted requests
by their request id; keep pending, unmeasured, failed, and timed-out results
distinct. A later successful query does not change a failed scenario into a
pass; retain its run id and record a corrected rerun separately.

During startup, Safe Mode prompt, entered, ambiguous and exited log markers are
different observations. A moving log does not establish a blocked dialog.
Changed conditions emit bounded JSON with `provisional=true` and a typed `code`
on stderr while readiness continues; repeated identical conditions are
not emitted every poll. Compile state remains unmeasured until authoritative
bridge/compiler evidence arrives. An explicit quiet prompt may stop early;
the deadline preserves the last typed observation. Client stderr buffering can
delay its presentation and is outside the host readiness guarantee.

Set `XUUNITY_HOST_CALL_TIMING=1` to measure host work. MCP results include a
pre-emission snapshot in `_meta.xuunity_host_timing`; a bounded
`xuunity_host_call_timing` stderr receipt records the total after stdout flush.
CLI receipts use `cli_dispatch` scope. Exclusive measured stages plus the
explicit unattributed remainder reconcile to the monotonic total; missing
stages are null/unmeasured. Serialization measures JSON encoding; output writes
and flush are within the total and remainder. Launcher startup, client latency
and diagnostic receipt emission are excluded. `dispatch_unity_wait` includes
transport and host waiting; use the separate request/Unity timing evidence to
inspect execution and settle. Profile comparable calls before attributing gaps
or optimizing them.

For UI work, query the known selector and narrow scene/root scope with
`unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`, or
`unity_ui_get_bounds` before requesting a full tree. Widen scope or node budgets
only when the result requires it; a truncated search cannot prove absence or
uniqueness. Keep the fixed Game View and point-of-use PlayMode liveness checks
from the [smoke contract](../operations/SMOKE_TESTS.md).

`unity_ui_click` synchronizes the existing Game View context before computing
bounds and running EventSystem raycasts. It does not resize the preset or change
zoom. Inspect `coordinate_context_status`, the before/after Screen dimensions,
and `pointer_x`/`pointer_y` in `pointer_coordinate_space`. If synchronization
cannot establish matching render dimensions, `ui_coordinate_context_unresolved`
refuses delivery; make the intended Game View visible before retrying. A real
raycast is still required to prove occlusion checks, even when dimensions agree.

For scenario `project_refresh`, a settled phase must belong to the pending
request ID. Idle alone cannot replace lost request evidence after a reload.
Inspect the explicit unresolved reason and mutation boundary before choosing
the next action; do not replay pending project actions blindly. Measured refresh
timing separates execution and settle waiting. Missing or inconsistent clock
evidence produces `timing_measured=false` and a null compact step duration.

Treat click delivery and the expected application transition as separate proof.
For an asynchronous close or navigation, a scenario `ui_click` can use
`expectStateChange: false` to record delivery without requiring an immediate
tree change. It must then use the project's existing registered bounded wait or
`project_defined_hook_poll_until` contract, with explicit timeout and terminal
predicates, followed by `ui_exists` with `expectedExists: false` for disappearance
or a `ui_exists`/`ui_get_text` assertion for the next state. These UI read steps
are immediate assertions, not automatic waits. Do not invent a hook, repeat the
click while waiting, or remove a next-state assertion to obtain a passing run.
Keep `expectStateChange: true` when immediate change is the intended contract.

An occlusion refusal remains a refusal: inspect the named occluder and follow the
authorized user path to dismiss it before retrying. Do not invoke the handler
directly or disable overlays merely to bypass reachability checks. A synthesized
raycast explicitly leaves occlusion unproven. Existing source examples are
`Step_FailsWhenAnExpectedStateChangeDoesNotHappen` in the
[EditMode interaction tests](../../packages/com.xuunity.light-mcp/Tests/EditModeUgui/XUUnityLightMcpUiInteractionStepTests.cs)
and `AnOccludingHandlerIsRefusedInsteadOfClickedThrough` in the
[PlayMode raycast tests](../../packages/com.xuunity.light-mcp/Tests/PlayMode/Ugui/XUUnityLightMcpUiClickRaycastIdentityPlayModeTests.cs).
They cover an inert delivered click and an occlusion refusal respectively; the
latter can skip when the runtime supplies no raycast hit. Source presence is
not a passing test receipt.

Inspect configuration through an explicit allowlist of required non-secret
fields. Report presence, environment, and ownership rather than raw values;
never persist raw login request/response bodies, tokens, or credential-bearing
URLs in scenario payloads, logs, or evidence bundles.

Record a small proof matrix, with source identity, run/request id, artifacts,
and pass/fail/blocked/not-run status for every required claim:

| Claim | Representative proof | Remaining limit |
| --- | --- | --- |
| Source rule or payload contract | Inspected source plus focused real-code tests | Does not prove the live editor loaded it |
| Script compilation | Terminal compile result for the required targets/profiles and affected assemblies | Does not prove UI or startup behavior |
| Editor/runtime UI transition | Advancing PlayMode, delivery receipt, bounded wait and next-state assertion | Does not prove device behavior |
| Device or native behavior | Identified player build and representative device run | Editor/build success alone leaves this row unproven |
| Server-dependent journey | Correlated request and expected business outcome in the intended environment, with secrets excluded | Local models and UI tests cannot prove a backend result |
| Shared-source consumers | Exact shared revision and per-consumer terminal compile evidence | One project's compile does not cover its consumers |

For `unity_prefab_render`, `capture_status=capture_produced` means PNG writing
completed; a failed render before writing reports `capture_status=not_produced`.
The existing `success` field remains compatible, and `proof_class` describes
the available snapshot evidence. Every isolated render reports
`visual_acceptance=visual_acceptance_unproven`, including intentionally blank
captures. Visual acceptance still requires the intended fixture/state, semantic
text/visibility checks, and relevant pixels or reference comparison. Apply
transient preview overrides for runtime-populated holders and text, and retain
evidence that the original prefab bytes are unchanged. The render tests
`Render_RevealsAHiddenHolderAndTextOnlyOnThePreviewInstance` and
`Render_AcceptsAnIntentionallyBlankPrefabAsAnArtifact` in
[the render/click suite](../../packages/com.xuunity.light-mcp/Tests/EditModeUgui/XUUnityLightMcpRenderAndClickTests.cs)
separate these contracts: a known revealed holder needs its expected pixels,
while an intentionally blank prefab may still produce a valid artifact. Do not
apply a universal nonblank-pixel threshold or promote an isolated preview to
live-runtime or device acceptance.

## Discover Commands Before Writing Editor Automation

Read wrapper `--help` once when choosing a Unity workflow; it lists all parser
commands with required flags. Map the requested evidence to supported operations:
scene wiring to `unity.scene.snapshot` / `unity.scene.assert`, rendered output
to `unity.game_view.screenshot`, ordered transitions to scenarios, and build
artifacts to `batch-build-player`. Check capabilities and record why any required
evidence is skipped. A command's existence is not proof that its check ran.

Use `project-hook-scaffold` then the reviewed project-action catalog and
`project-action-invoke` for custom editor work. The scaffold recovery command
writes into `Temp/XUUnityHookScaffold`; follow its checklist to place and register
the hook. Generating a scaffold does not activate it. Never run a long build
inline in `[InitializeOnLoad]`: editor main-thread blocking stops heartbeat and
request processing. Inspect `application_run_in_background` and actual progress
before inferring that deferred editor work cannot run.

For a degraded, blocked or timed-out result, follow the literal
`recommended_recovery_command` (readiness also retains `recovery_command`), and
read its prerequisite or manual-action explanation. Do not repeatedly execute a
state token or blindly repeat `ensure-ready`. The typed `test_filter_no_match`
result with a concrete refresh command is the reference pattern. The command
starts with the quoted absolute launcher path when the host knows it, so it runs
from any working directory in bash or cmd; in PowerShell, prefix a `.cmd` or
`.sh` launcher path with `& `.

Before calling a build a deliverable, verify both its structured result summary
and the referenced non-empty artifact on disk at handoff time. Record its path,
size and identity. If it was deleted or replaced, preserve the historical build
result but report the deliverable as missing or changed.

## Placeholders

Command examples use:

```bash
PROJECT_ROOT=/absolute/path/to/UnityProject
WRAPPER=./xuunity_light_unity_mcp.sh
```

When running from an installed host helper, replace `WRAPPER` with the project
or user-level wrapper path.

## MCP Tool Names

Use these MCP tools from compatible clients:

- `unity_status`
- `unity_status_summary`
- `unity_capabilities`
- `unity_health_probe`
- `unity_console_tail`
- `unity_console_grep`
- `unity_loading_timing`
- `unity_scene_snapshot`
- `unity_scene_assert`
- `unity_compile_player_scripts`
- `unity_compile_matrix`
- `unity_compile_build_config_matrix`
- `unity_tests_run_editmode`
- `unity_tests_run_playmode`
- `unity_build_player`
- `unity_playmode_state`
- `unity_playmode_set`
- `unity_game_view_configure`
- `unity_game_view_screenshot`
- `unity_scenario_validate`
- `unity_scenario_run_and_wait`
- `unity_scenario_result_summary`
- `unity_request_final_status`
- `unity_project_refresh`
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
- `unity_edm4u_resolve`
- `unity_sdk_android_resolve`
- `unity_sdk_dependency_verify`
- `xuunity_uninstall_plan`
- `xuunity_uninstall_apply`

Use the CLI examples below when you need a deterministic local fallback or when
you are documenting exactly what an agent did.

## Client Tool Call Examples

These examples use exact MCP tool names and argument objects. Client UIs expose
MCP tools differently, but the tool name and JSON arguments stay the same.

Claude Code, Claude Desktop, Cursor, and Windsurf:

```json
{
  "tool": "unity_status_summary",
  "arguments": {
    "projectRoot": "$PROJECT_ROOT",
    "timeoutMs": 5000
  }
}
```

```json
{
  "tool": "unity_project_refresh",
  "arguments": {
    "projectRoot": "$PROJECT_ROOT",
    "forceAssetRefresh": true,
    "resolvePackages": true,
    "rerunHealthProbe": true,
    "timeoutMs": 60000
  }
}
```

```json
{
  "tool": "unity_compile_player_scripts",
  "arguments": {
    "projectRoot": "$PROJECT_ROOT",
    "target": "Android",
    "optionFlags": ["DevelopmentBuild"],
    "name": "post-change-android-compile",
    "timeoutMs": 180000
  }
}
```

```json
{
  "tool": "unity_tests_run_editmode",
  "arguments": {
    "projectRoot": "$PROJECT_ROOT",
    "testNames": ["Namespace.FullyQualifiedTestName"],
    "timeoutMs": 180000
  }
}
```

All test filter fields are arrays of strings. Never pass a scalar test name;
the server rejects the wrong shape before executing anything.

Codex-style or custom stdio MCP clients can call the same tools through the
standard MCP JSON-RPC envelope:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "unity_status_summary",
    "arguments": {
      "projectRoot": "$PROJECT_ROOT",
      "timeoutMs": 5000
    }
  }
}
```

For visual checks:

```json
{
  "tool": "unity_game_view_screenshot",
  "arguments": {
    "projectRoot": "$PROJECT_ROOT",
    "fileName": "agent-visual-check.png",
    "includeImage": false,
    "maxResolution": 1280,
    "timeoutMs": 10000
  }
}
```

## Evidence Checklist

Each completed workflow should report:

- project root
- Unity version when available
- package version when available
- package source mode when MCP package wiring changed
- bridge readiness result
- capability/adapter status for used operations
- compile/test/scenario/build target outcome
- relevant artifact paths
- request id when available
- validation gaps and skipped checks
- execution channel per proof (`native-mcp`, `helper-cli`, `direct-unity`) and
  the Unity lane (`batch`/`gui`) when it matters
- exact stage per proof: a build or export never stands in for player or
  device runtime, and helper readiness never stands in for a native client call
- warning counts and rebuild evidence whenever a warning or rebuild policy applies
- the full required denominator with pass/fail/blocked/not_run counts, never
  only the passing rows
- whether the host-opened editor was restored
- design-plan or retro artifact updated when the work came from a plan
- self-review notes for code/docs changes
- post-retro risks and follow-up when reusable lessons were found

## Evidence JSON Schema

When a workflow closes out, prefer a structured evidence object that validates
against `templates/workflows/evidence_summary.schema.json`.

Minimum evidence object:

```json
{
  "schemaVersion": "xuunity.light-mcp.evidence.v1",
  "workflowId": "post_change_validation",
  "projectRoot": "$PROJECT_ROOT",
  "unityVersion": "6000.0.58f2",
  "packageVersion": "0.3.87",
  "packageSourceMode": "git",
  "verdict": "pass",
  "checks": [
    {
      "name": "readiness",
      "status": "pass",
      "tool": "unity_status_summary"
    },
    {
      "name": "compile",
      "status": "pass",
      "tool": "unity_compile_player_scripts",
      "requestId": "REQUEST_ID"
    }
  ],
  "artifacts": [],
  "validationGaps": [],
  "hostEditorRestored": true
}
```

Use `verdict: "partial"` when the workflow found useful evidence but skipped a
representative check. Use `verdict: "blocked"` when readiness, package restore,
capability gates, or editor startup prevented validation.

## Workflow 1: First Project Readiness Gate

Use when a project is newly connected to this MCP or the agent does not trust
the current Unity Editor state.

Agent prompt:

```text
Use XUUnity Light Unity MCP to verify this Unity project is ready for safe
agent validation. Do not mutate project settings. Stop after readiness,
capability, health, console, and scene evidence.
```

CLI route:

```bash
"$WRAPPER" ensure-ready \
  --project-root "$PROJECT_ROOT" \
  --open-editor \
  --background-open \
  --timeout-ms 120000

"$WRAPPER" request-status-summary \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000

"$WRAPPER" request-capabilities \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000

"$WRAPPER" request-health-probe \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000
```

Then inspect:

```bash
"$WRAPPER" request-status \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000

"$WRAPPER" request-scene-assert \
  --project-root "$PROJECT_ROOT" \
  --allow-dirty \
  --timeout-ms 5000
```

From an MCP client, also call:

- `unity_console_tail`
- `unity_scene_snapshot`

Evidence to report:

- bridge state and transport
- capability adapter ids
- disabled or unsupported operations
- console errors or warnings relevant to startup
- active scene name/path and dirty state

## Workflow 2: Post-Code-Change Validation Gate

Use after code edits before claiming a task is done.

Agent prompt:

```text
Validate the code changes through Unity. Run readiness, compile first, then
EditMode tests. Use PlayMode tests only when relevant to the changed surface.
Report exact failures and do not hide Unity validation gaps.
```

CLI route:

```bash
"$WRAPPER" batch-build-config-compile-matrix \
  --project-root "$PROJECT_ROOT" \
  --batch-fallback-mode require-batch \
  --output compact \
  --timeout-ms 300000

"$WRAPPER" ensure-ready \
  --project-root "$PROJECT_ROOT" \
  --open-editor \
  --timeout-ms 120000

"$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --force-asset-refresh \
  --resolve-packages \
  --rerun-health-probe \
  --timeout-ms 60000

"$WRAPPER" request-compile \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --name post-change-android-compile \
  --option-flag DevelopmentBuild \
  --timeout-ms 180000

"$WRAPPER" request-editmode-tests \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 180000
```

If a healthy editor is already open and intentionally being reused, run the
bridge compile matrix before scenarios/tests instead of the closed-project batch
lane. Do not let `ensure-ready --open-editor` be the first validation command
after Unity C# edits.

Optional PlayMode lane:

```bash
"$WRAPPER" request-playmode-tests \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 240000
```

Stop criteria:

- compile failure with file/line diagnostics
- package restore failure
- test failure with test name and assertion
- capability gate rejects a required operation

Closeout:

```bash
"$WRAPPER" restore-editor-state \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000
```

## Workflow 3: Compile Failure Triage

Use when Unity scripts fail to compile, especially after changing assembly
boundaries, SDK code, platform defines, or generated files.

Agent prompt:

```text
Find the smallest actionable Unity compile failure. Do not switch the active
Unity build target just to validate. Check target-specific defines and return
the first concrete file/line cause.
```

CLI route:

```bash
"$WRAPPER" request-compile \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --name android-dev-compile \
  --option-flag DevelopmentBuild \
  --timeout-ms 180000
```

When platform or profile combinations matter, prefer a compile matrix config:

```bash
"$WRAPPER" request-compile-matrix \
  --project-root "$PROJECT_ROOT" \
  --config-file /path/to/compile-matrix.json \
  --timeout-ms 300000
```

If a request times out or the Editor reloads, recover final accounting:

```bash
"$WRAPPER" request-latest-status \
  --project-root "$PROJECT_ROOT" \
  --operation unity.compile.player_scripts

"$WRAPPER" request-final-status \
  --project-root "$PROJECT_ROOT" \
  --request-id REQUEST_ID \
  --operation unity.compile.player_scripts
```

Evidence to report:

- target
- option flags
- extra defines
- whether active build target was unchanged
- first compiler error with file/line
- request id and final status when recovery was needed

## Workflow 4: Test Failure Triage

Use when tests fail or when a changed subsystem needs a focused regression pass.

Agent prompt:

```text
Run the narrowest useful Unity test lane first. Start with focused EditMode
tests when names or assemblies are known. Broaden only if the focused lane
passes or the failure is inconclusive.
```

Focused EditMode route:

```bash
"$WRAPPER" request-editmode-tests \
  --project-root "$PROJECT_ROOT" \
  --assembly-name AssemblyName.Editor.Tests \
  --timeout-ms 180000
```

Focused test route:

```bash
"$WRAPPER" request-editmode-tests \
  --project-root "$PROJECT_ROOT" \
  --test-name Namespace.TypeName.TestMethod \
  --timeout-ms 180000
```

PlayMode route:

```bash
"$WRAPPER" request-playmode-tests \
  --project-root "$PROJECT_ROOT" \
  --assembly-name AssemblyName.PlayMode.Tests \
  --timeout-ms 240000
```

Size `--timeout-ms` (MCP `timeoutMs`) above the expected suite duration; it
bounds the test run including the wait across the Play Mode entry domain reload.

Evidence to report:

- lane: EditMode or PlayMode
- filters used
- total/passed/failed/skipped counts
- `test_verdict` and `filter_summary`
- failing test names and assertions
- whether PlayMode returned to a settled Edit state

If a filtered direct request reports `test_verdict=test_filter_no_match`, its
transport delivery succeeded but validation did not: refresh once, wait for
settle, then retry the exact same request once.

```bash
"$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 180000
```

If the retry still selects zero tests, report a filter mismatch and stop. An
unfiltered empty suite remains the distinct `no_tests` result.

## Workflow 5: Game View Visual Verification

Use when a change affects UI, camera, scene composition, rendering, or visual
regression evidence.

Agent prompt:

```text
Capture Game View evidence only after capabilities confirm support. Configure a
fixed resolution, enter Play Mode only when needed, capture the screenshot, then
exit Play Mode and report the artifact path.
```

Capability gate:

```bash
"$WRAPPER" request-capabilities \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000
```

MCP route:

- call `unity_game_view_configure`
- call `unity_playmode_set` with `enter` if runtime state is required
- call `unity_game_view_screenshot`
- call `unity_playmode_set` with `exit`
- call `unity_request_final_status` if a request is interrupted

Cheaper default for prefab-only UI acceptance: `unity_prefab_render` renders
the prefab in isolation without Play Mode or the boot flow, in fractions of a
second, and is immune to editor throttling. Use the play-mode route only when
the running app itself is under test, and check `playmode_loop_liveness` is
`advancing` before trusting a screenshot taken in Play Mode.

CLI route for Play Mode state:

```bash
"$WRAPPER" request-playmode-state \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000

"$WRAPPER" request-playmode-set \
  --project-root "$PROJECT_ROOT" \
  --action enter \
  --timeout-ms 120000

"$WRAPPER" request-playmode-set \
  --project-root "$PROJECT_ROOT" \
  --action exit \
  --timeout-ms 120000
```

Evidence to report:

- capability support for Game View adapter
- requested resolution
- screenshot artifact path
- Play Mode state before and after
- validation gap if reflection-gated Game View operations are unsupported

## Workflow 6: Scenario Regression Replay

Use when a project has deterministic scenario JSON or project-defined scenario
hooks.

Agent prompt:

```text
Validate the scenario first, run it once, wait for a terminal result, and
summarize failed steps with artifact paths. Do not invent scenario hooks.
```

CLI route:

```bash
"$WRAPPER" request-scenario-validate \
  --project-root "$PROJECT_ROOT" \
  --scenario-file templates/scenarios/interactive_acceptance_smoke.json \
  --timeout-ms 5000

"$WRAPPER" request-scenario-run-and-wait \
  --project-root "$PROJECT_ROOT" \
  --scenario-file templates/scenarios/interactive_acceptance_smoke.json \
  --timeout-ms 240000 \
  --poll-interval-ms 1000

"$WRAPPER" request-scenario-result-latest \
  --project-root "$PROJECT_ROOT" \
  --scenario-name interactive_acceptance_smoke
```

Evidence to report:

- scenario file
- validation result
- run id
- terminal status
- failed step name/kind
- screenshot/log/artifact paths
- latest persisted result path

## Workflow 7: Mobile Build Profile Compile Matrix

Use before merging mobile SDK, define, package, or build-profile changes.

Agent prompt:

```text
Validate Android and iOS script compilation from project build profiles without
switching the active Unity build target. Stop on the first profile failure and
report exact target/profile evidence.
```

CLI route:

```bash
"$WRAPPER" request-build-config-compile-matrix \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --target iOS \
  --profile Development \
  --profile Release \
  --stop-on-first-failure \
  --timeout-ms 300000
```

When the Editor should remain closed, use the batch lane:

```bash
"$WRAPPER" batch-build-config-compile-matrix \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --target iOS \
  --profile Development \
  --profile Release \
  --stop-on-first-failure \
  --timeout-ms 600000
```

Evidence to report:

- build config asset if detected
- profiles selected
- targets selected
- first failing target/profile/define set
- batch artifact paths when batch lane is used

## Workflow 8: SDK / EDM4U Dependency Validation

Use after changing mobile SDK packages, External Dependency Manager for Unity,
Gradle dependency expectations, or generated dependency artifacts.

Agent prompt:

```text
Refresh the project, switch to Android, then run the typed EDM4U resolver with
tracked generated outputs and explicit expected coordinates. Do not print
credentials or secret-bearing URLs. Accept a rollout verdict only when callback
completion, stable output hashes, and coordinate verification all pass.
```

CLI route:

```bash
"$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --force-asset-refresh \
  --resolve-packages \
  --rerun-health-probe \
  --timeout-ms 60000

"$WRAPPER" request-build-target-switch \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --timeout-ms 180000

"$WRAPPER" request-sdk-android-resolve \
  --project-root "$PROJECT_ROOT" \
  --config-file /path/to/sdk-android-resolver.json \
  --timeout-ms 300000

"$WRAPPER" request-sdk-dependency-verify \
  --project-root "$PROJECT_ROOT" \
  --config-file /path/to/sdk-dependency-expectations.json \
  --timeout-ms 60000
```

Evidence to report:

- required and active build target
- EDM4U callback adapter or missing capability
- resolver callback status, stable output hashes, and
  `resolver_output_freshness`
- verified files
- missing dependencies
- redacted evidence for sensitive config fields

The typed operation returns `decision_ready: true` only with callback success,
stable generated outputs, and expected-coordinate proof. The older
`unity_edm4u_resolve` remains fire-and-report; its
`resolver_output_freshness: unproven` / `decision_ready: false` payload must not
be promoted to a rollout verdict. Run `unity_sdk_generated_diff_guard` after
either resolver lane to catch destructive unrelated generated-file changes.

## Workflow 9: Closed-Project Batch Validation

Use in CI-like local validation or when interactive Unity should not be opened.

Agent prompt:

```text
Use the non-interactive batch lane because the project should stay closed.
Fail if another live Unity Editor owns this project. Capture result files and
logs.
```

If the batch preflight reports a same-project editor conflict, close and verify
before retrying:

```bash
"$WRAPPER" request-editor-quit \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 30000 \
  --exit-timeout-ms 30000

"$WRAPPER" verify-editor-closed \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 30000
```

`request-editor-quit` waits for and verifies process exit by default; pass
`--no-wait-for-exit` only when an unverified acknowledgement is enough
(`closeout_classification=quit_ack_unverified`). If it fails with
`editor_quit_ack_without_exit`, read `quit_executing_observed`,
`quit_expired_observed`, `editor_application_focused` and `scene_dirty`, then follow
`recommended_recovery_command`: `restore-editor-state --require-closed` when
`host_opened_session_found=true`, otherwise close the editor manually and run
`verify-editor-closed` (`explicit_escalation_command` carries the
`--force-after-ms` form). The quit command never signals the editor itself. If
it fails with `editor_quit_request_rejected`, Unity never armed an exit; read
`quit_request_error_code` instead of waiting or restoring.

Only rerun the batch helper after `same_project_editor_closed=true` and
`process_exit_verified=true`. If `process_visibility_restricted` appears, move
the command to a host context that can list local processes; do not treat an
empty PID list as proof while visibility is restricted.

Before assuming a closed-project batch command can run as real Unity batchmode,
check the host capability report:

```bash
"$WRAPPER" license-capabilities \
  --project-root "$PROJECT_ROOT" \
  --refresh \
  --timeout-ms 30000
```

For local PlayMode, resolve the editor from
`ProjectSettings/ProjectVersion.txt`, then use `ensure-ready --open-editor` and
`request-playmode-tests`. Do not select an installed Unity executable directly,
and do not default local PlayMode to batchmode. The helper refuses an explicit
wrong-version editor before Unity can mutate `Library`, and automatically
forwards exactly one verified Unity Hub licensing channel when available.

Default batch helpers use `--batch-fallback-mode auto`. If the report proves
batchmode is blocked by a known license, Hub, account, Unity version, headless,
or session condition, the helper uses the equivalent GUI bridge lane when the
editor is idle enough to restore safely. Treat this as successful completion
when the command succeeds and Unity reports a passed outcome; do not classify
GUI fallback itself as failure. Use `--batch-fallback-mode require-batch` only
when the workflow must fail unless real batchmode is proven.
If GUI admission reports multiple Hub licensing candidates, stop rather than
choosing one. If it reports `manual_user_action_required`, let the user resolve
Hub sign-in/session state; do not reinterpret it as package import, Test
Framework, or compile failure. That refusal is an observability limit, not a
proof that the editor cannot license itself: it fires when no live process whose
parent is Unity Hub owns a licensing client, which is also what a standalone
Licensing Client, a floating/license-server host, or a host with the Hub closed
looks like. A host whose GUI editor does license itself can set
`XUUNITY_LIGHT_UNITY_MCP_GUI_ADMISSION_OVERRIDE=1` to admit the GUI lane; the
override is recorded in the lane payload as `gui_admission_override_active` with
the waived blocker, and it waives only that preflight, never the license.

Compile route:

```bash
"$WRAPPER" batch-compile \
  --project-root "$PROJECT_ROOT" \
  --target Android \
  --name closed-project-android-compile \
  --option-flag DevelopmentBuild \
  --timeout-ms 300000
```

EditMode route:

```bash
"$WRAPPER" batch-editmode-tests \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 300000
```

Matrix route:

```bash
"$WRAPPER" batch-compile-matrix \
  --project-root "$PROJECT_ROOT" \
  --config-file /path/to/compile-matrix.json \
  --timeout-ms 600000
```

Evidence to report:

- batch log path
- result file path
- exit code/operator verdict
- `requested_execution_lane` and `effective_execution_lane`
- `license_blocker_code` and `batchmode_probe_log_path` when present
- `restore_editor_state` when GUI fallback opened the editor
- workspace side-effect summary when available
- reason if batch lane refused to run because an Editor was open

## Workflow 10: Same-Host Multi-Project Safety Check

Use when one workstation has several Unity projects open or recently opened.

Agent prompt:

```text
Before sending Unity operations, confirm the target project context maps to
exactly one live bridge. Do not send validation to a stale or wrong project.
```

CLI route:

```bash
"$WRAPPER" project-discovery-report \
  --project-root "$PROJECT_ROOT"

"$WRAPPER" registry-context-report

"$WRAPPER" registry-prune-contexts
```

Then:

```bash
"$WRAPPER" request-status-summary \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000
```

Evidence to report:

- resolved project root
- editor process ownership by parsed `-projectPath`
- stale contexts pruned
- active bridge path
- whether any conflicting live editor was detected

## Workflow 11: Lifecycle Churn Recovery

Use when Unity reloads assemblies, the Editor restarts, a request times out, or
the MCP transport fails before a terminal operation result is returned.

Agent prompt:

```text
Recover the true Unity-side final status instead of rerunning blindly. Use the
request journal, latest status by operation, and host recovery helpers. Only
rerun after proving the previous request is terminal or abandoned.
```

CLI route:

```bash
"$WRAPPER" request-latest-status \
  --project-root "$PROJECT_ROOT" \
  --operation unity.compile.player_scripts

"$WRAPPER" request-final-status \
  --project-root "$PROJECT_ROOT" \
  --request-id REQUEST_ID \
  --operation unity.compile.player_scripts
```

If the Editor session is unhealthy:

```bash
"$WRAPPER" recover-editor-session \
  --project-root "$PROJECT_ROOT" \
  --force-compile-probe \
  --open-editor \
  --timeout-ms 180000
```

Cleanup stale artifacts only after recording evidence:

```bash
"$WRAPPER" request-stale-cleanup \
  --project-root "$PROJECT_ROOT" \
  --dry-run \
  --max-entries 50
```

Evidence to report:

- interrupted operation
- request id
- journal final status
- whether persisted scenario or request evidence was reconciled
- recovery action taken
- whether a rerun is still needed

## Workflow 12: Release Closeout Evidence Summary

Use before a human pushes, tags, publishes, or closes a task.

Agent prompt:

```text
Produce a release closeout summary from Unity validation evidence. Include
exact checks run, artifact paths, skipped checks, and remaining risks. Do not
claim unsupported OS/client validation.
```

Minimum route:

```bash
"$WRAPPER" request-status-summary \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 5000

"$WRAPPER" request-health-probe \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000

"$WRAPPER" request-latest-status \
  --project-root "$PROJECT_ROOT" \
  --operation unity.compile.player_scripts \
  --operation unity.tests.run_editmode \
  --operation unity.tests.run_playmode \
  --operation unity.scenario.run
```

Optional cleanup:

```bash
"$WRAPPER" maintenance-prune \
  --project-root "$PROJECT_ROOT" \
  --dry-run
```

Closeout format:

```text
Unity validation:
- readiness:
- compile:
- EditMode tests:
- PlayMode tests:
- scenario / screenshot:
- SDK / build profile checks:
- artifacts:
- skipped checks:
- residual risk:
```

### Machine-checked acceptance

When the release owner has written an explicit validation plan, evaluate the
saved evidence offline instead of summarizing it by hand:

```bash
python3 scripts/testing/evaluate_validation_evidence.py \
  --plan release/validation-plan.json \
  --receipts release/validation-receipts.json \
  --report release/acceptance/report.json
```

The evaluator matches every plan row on requirement id, exact dimensions,
scene, stage and execution channel, applies the warning, rebuild, test-count
and semantic-assertion policy separately from the operation outcome, and
prints one compact envelope (`payload_mode=compact_validation_acceptance`,
at most 8192 bytes). Exit `0` means accepted, `1` means a valid evaluation
with failed, blocked or not-run required rows, `2` means invalid input; never
record exit `2` as a blocked row. Receipts with
`evidenceKind: helper_response` point at saved helper responses, and the
evaluator decodes `payload_json` itself. A consumer release verdict can be
evaluated directly with `--consumer-verdict`.

Example: an Android APK build row passes while its device-runtime row is
blocked by a missing device. The envelope reports
`required: {total: 2, pass: 1, fail: 0, blocked: 1, not_run: 0}` and
`verdict: blocked`; the APK stays a valid artifact and publication stays
blocked. A native-client row passes only with a `clientReceiptRef` that
points at the `unity_status_summary` result captured inside the client
session; helper health or `client_kind=cli` yields `channel_unverified`.

## Workflow 13: MCP Package Source Mode Switching

Use when the agent is changing this MCP package or validating unpublished MCP
package changes inside a real Unity project.

Agent prompt:

```text
Switch the Unity project into the correct XUUnity Light Unity MCP package source
mode. Use devmode only for local package iteration. Use prodmode only after the
package release tag is published. Do not hand-edit the manifest to bypass the
wrapper checks.
```

Development route:

```bash
"$WRAPPER" devmode \
  --project-root "$PROJECT_ROOT"

"$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --force-asset-refresh \
  --resolve-packages \
  --rerun-health-probe \
  --timeout-ms 60000
```

Use `devmode` only while actively editing the MCP source package. It writes a
local `file:` dependency to `packages/com.xuunity.light-mcp` and removes the package
lock entry so Unity can re-resolve the package.

Production route:

```bash
# First synchronize release-facing version references, for example with
# --version 0.3.87 when preparing the next patch release.
python3 scripts/tools/sync_release_version.py --version <next-version>
python3 scripts/testing/check_release_version_consistency.py
scripts/testing/run_host_python_tests.sh

git push origin v<next-version>

"$WRAPPER" prodmode \
  --project-root "$PROJECT_ROOT"

"$WRAPPER" request-project-refresh \
  --project-root "$PROJECT_ROOT" \
  --force-asset-refresh \
  --resolve-packages \
  --rerun-health-probe \
  --timeout-ms 60000
```

Use `prodmode` for publishable project state. It pins the Unity dependency to
the published release tag matching the package version and removes the package
lock entry so Unity can re-resolve it.

Stop criteria:

- `prodmode` says the package release tag is not advertised by the remote
- Unity package re-resolution fails
- the project remains in devmode when the task is a release or publish closeout
- package refresh succeeds but health probe or compile validation fails

Evidence to report:

- mode selected: `devmode` or `prodmode`
- previous and new `com.xuunity.light-mcp` dependency value
- whether the package-lock entry was removed
- published release tag for prodmode
- project refresh and health-probe result after switching
- validation gap if Unity could not re-resolve packages

## Machine-readable Workflow Templates

Reusable templates live under `templates/workflows/`:

- `workflow.schema.json`
  - schema for workflow definitions
- `evidence_summary.schema.json`
  - schema for closeout evidence
- `readiness_gate.workflow.json`
  - first-contact readiness, capabilities, health, console, and scene checks
- `post_change_validation.workflow.json`
  - readiness, package refresh, compile, and EditMode validation
- `package_mode_switch.workflow.json`
  - wrapper-only `devmode` and `prodmode` source switching
- `validation_plan.schema.json`, `validation_receipts.schema.json`,
  `validation_acceptance.schema.json`
  - owner plan, evidence receipts and the acceptance report consumed and
    emitted by `scripts/testing/evaluate_validation_evidence.py`

These files are machine-readable planning artifacts for agents and wrappers.
They are not Unity scenario JSON and are not executed directly by the MCP server.

## Anti-Patterns

Avoid these agent behaviors:

- claiming Unity validation from shell-only C# or grep checks
- switching active build target when compile validation can run target-specific checks
- using broad editor mutation when a read/validate operation is enough
- rerunning timed-out operations before checking `request-final-status`
- treating Game View reflection support as universal
- leaving a release-bound project in `devmode`
- hand-editing `Packages/manifest.json` to fake `prodmode` around a missing release tag
- hiding skipped Windows/Linux/client smoke validation
- relabeling helper or CLI evidence as native MCP-client verification
- promoting a build or export result to a player-runtime or device-runtime claim
- shrinking a release denominator by dropping blocked or not-run rows
- storing credentials in scenario files, expectation files, logs, or generated reports
- using project-private details in public docs or examples

## Related Docs

- `../../README.md`
- `AI_INTEGRATION.md`
- `../reference/FEATURES.md`
- `../operations/BUILD_AUTOMATION.md`
- `../operations/SMOKE_TESTS.md`
- `../../SECURITY.md`
- `../reference/COMPARISON.md`
