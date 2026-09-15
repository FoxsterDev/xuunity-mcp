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
result with a concrete refresh command is the reference pattern.

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
  "packageVersion": "0.3.75",
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
  --wait-for-exit \
  --exit-timeout-ms 30000

"$WRAPPER" verify-editor-closed \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 30000
```

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
# --version 0.3.75 when preparing the next patch release.
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
