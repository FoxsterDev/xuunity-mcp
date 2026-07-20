# XUUnity Light Unity MCP Smoke Tests

Date: `2026-07-15`
Status: `current source after v0.3.45`

This file defines the public reusable smoke-test contract for the lightweight
Unity MCP lane.

Keep project-specific wrappers, project roots, build-config assets, and local
hook names out of this file. Those belong in host-local `AIOutput/Operations/`
or project-local guidance.

## Goal

Provide a small generic baseline that proves:

- the bridge can start and report healthy state
- basic editor-integrated operations work through MCP
- ordered scenario execution works
- play mode lifecycle control works
- refresh semantics settle instead of returning only request-time transport

Current release evidence:

- current-source host Python tests: `458` tests passed on macOS, with `13`
  expected native-Windows-only skips covered by the Windows CI leg
- source package self-tests for the current release line: EditMode and PlayMode
  self-test lanes passed on runnable installed Unity `2021.3`, `2022.3`, and
  `6000.x` editors after offline optional Test Framework setup
- multi-project batch compile matrix in a consumer repo: `9/9` projects, `38/38` lanes, `0` failures

## Generic Smoke Layers

### 1. Bridge Readiness Smoke

Run:

- `ensure-ready`
- `request-status`
- `request-health-probe`

Pass criteria:

- healthy bridge heartbeat
- `unity.status` reachable
- `unity.health.probe` reports supported operations without infrastructure failure
- compact status output should expose whether the bridge is already stabilized enough for retry

### 1a. Closeout Truth Smoke

Run a host-opened validation session and then `restore-editor-state`.

Pass criteria:

- a host-opened editor closes with verified process exit, not only a quit
  acknowledgement
- the result exposes `closeout_classification`
- `closeout_classification=quit_ack_without_exit` is treated as a failure signal
  for the smoke, not as a passing closeout
- when closeout proof is incomplete, the wrapper surfaces one obvious follow-up
  command through `recommended_recovery_command`

### 2. Compile Gate

Changed C# scripts require a fast compile gate before EditMode, PlayMode,
scenario, or GUI smoke validation unless the task is explicitly investigating a
compile failure.

Preferred routes:

- `request-build-config-compile-matrix` when a project defines the authoritative build-profile matrix
- otherwise the narrowest representative `unity.compile.player_scripts` route

Pass criteria:

- no infrastructure failure
- all required target/profile entries pass for the project contract
- when Unity-side settle evidence is available, compile payloads should report
  `completion_basis: unity_compile_settle_watcher`
- MCP compile tools return compact operation summaries by default. Smokes that
  assert raw lifecycle snapshots or artifact-manifest internals must pass
  `includeFullPayload=true`; ordinary pass/fail gates should stay on the compact
  default and read `status`, counts, `post_settle_compile`, `settle_phase`, and
  `completion_basis`.
- If new `.cs` files were created outside the Unity editor and direct compile
  reports missing namespaces or types, run `request-project-refresh` once and
  retry before treating the result as a code failure.
- if the compile gate is blocked because the same project editor is open, the
  batch summary reports `unity_outcome: not_started` and surfaces a concrete
  recovery command before any heavier validation is attempted

### 2a. SDK Generated-Diff Guard

For an SDK rollout, run `unity_sdk_generated_diff_guard` (or
`sdk-generated-diff-guard --config-file <guard.json>`) after resolver work and
before treating dependency presence or compile-green as rollout proof. The
guard uses `baselineRef` (default `HEAD`) for Git-tracked paths. For a generated
path absent from that ref, capture a fingerprint-bound baseline once from a
clean tree with `captureBaseline=true`; only the selected Git-untracked outputs
may be present outside Git. The default capture directory is
`Library/XUUnityLightMcp/sdk/baseline/default`, and `libraryBaselineDir` can
select a different label under the same baseline root. Re-run with
`captureBaseline=false` for the rollout comparison.

The Library fingerprint binds the project path, Unity version,
`Packages/packages-lock.json` hash, configured `trackedSdkVersions`, and
`expectedVersionChanges`. A mismatch reports `baseline_fingerprint_stale`
instead of comparing against an unrelated snapshot. Snapshot hash mismatches
also fail closed.

The guard returns a compact verdict.
Its default `diffMode` maps `*.xml` to order-insensitive structural comparison,
`*.gradle` to tokenized/comment-free comparison with adjacent generated-block
order normalization, and other files to conservative line normalization. A
caller can override those path patterns with `xml_structural`,
`gradle_tokenized`, or `line_normalized` when a generated format needs a more
conservative policy.

Pass criteria:

- every requested generated file has a readable Git or fingerprint-bound
  Library baseline;
- every `requiredMarkersAfter` value remains present outside comments (Gradle
  markers are token-aware, so harmless whitespace does not create a false
  negative and a marker surviving only in `/* ... */` cannot pass);
- every requested generated file still exists in the working tree;
- every XML/Gradle file selected for structured comparison parses into a valid
  normalized representation;
- no configured previous native version remains after the resolve; and
- no unallowlisted generated-file change is present when
  `failOnUnexpectedChangedFile=true`.

The guard writes its JSON evidence under
`Library/XUUnityLightMcp/sdk/generated_diff_guard.json` by default. A failed
guard is a validation failure, not a passing resolver request. It does not yet
prove EDM4U async freshness, perform a package restore, or replace the planned
portfolio SDK lane.

Log-presence checks:

- `unity.console.grep` / `request-console-grep` default to `source=editor_log`
  for path-backed `Editor.log` checks.
- `unity.console.tail` / `request-console-tail` also default to
  `source=editor_log`. Explicit `source=console` preserves the in-memory Console
  buffer tail, but payloads mark it as `console_buffer_may_be_stale`.
- Explicit `source=console` searches the Unity Console buffer, which can be
  cleared on Play Mode entry and can evict early or high-volume logs.
- An empty console grep is not definitive proof that a log did not happen.
- Use `unity_console_grep` with `source=editor_log` or
  `request-console-grep --source editor_log` for path-backed Editor.log grep
  when log presence is the validation claim.
- When health runs without a live bridge/editor confirmation, treat
  `editor_log_diagnosis.freshness_class=prior_session_or_unverified` as stale
  evidence. Verify current source or reopen through `ensure-ready --open-editor`
  before treating that diagnosis as current compile truth.

First open after a Unity version upgrade:

- Prefer a closed-editor batch pass using `-batchmode -quit -accept-apiupdate`
  before opening the GUI.
- If health output reports `possible_interactive_dialog_block`, keep the editor
  under `observe_only` policy and relaunch non-interactively with
  `-accept-apiupdate`; do not assume the transport or bridge crashed.
- If health output reports `possible_safe_mode_dialog_block`, keep the editor
  under `observe_only` policy. Do not auto-click Safe Mode. Run the batch compile
  gate (`batch-build-config-compile-matrix` when available) and fix compile
  errors, or open Unity Safe Mode manually.
- `ensure-ready --open-editor` enables the project bridge config when it is
  missing or disabled, but package declaration alone still does not prove a live
  bridge heartbeat.

Compile gate scope limit (green compile is not "editor clean"):

- A green compile gate proves scripts COMPILE. It does not prove the GUI editor
  is free of editor-startup runtime errors. A `-batchmode` run and
  `unity.compile.player_scripts` do not execute `[InitializeOnLoad]`,
  `RuntimeInitializeOnLoadMethod`, `EditorApplication.update`, or editor startup
  reconcilers, and player-scripts compile excludes editor and test assemblies.
- A project whose package/infra graph pulls in an `[InitializeOnLoad]` editor
  reconciler that hard-requires a `Resources`-loaded config (for example a
  settings sync or first-load validator that calls `Resources.LoadAll<T>(path)`
  and expects exactly one hit) can compile green in batchmode while the GUI editor
  throws that reconciler's exception on every editor-update frame.
- When infra adds editor-startup hooks, add an editor-startup-clean gate AFTER the
  compile gate: open the GUI editor (`ensure-ready --open-editor`), then
  `unity_console_grep source=editor_log` for `Exception` / `error` (the console
  buffer can be evicted — see Log-presence checks; on `editor_log` prefer
  error-anchored patterns over entity names). Do not treat a green batchmode
  compile as "editor clean."

### 3. Interactive Acceptance Scenario

Minimum generic scenario steps:

- `status`
- `health_probe`
- `project_refresh`
- optional `scene_open` for boot-flow or scene-normalization smokes that must
  start from a specific scene
- `playmode_set enter`
- `wait_for_playmode_state playing`
- `assert_playmode_state playing`
- `playmode_set exit`
- `wait_for_playmode_state edit`
- `assert_playmode_state edit`

Optional project-local additions:

- `game_view_configure`
- `game_view_screenshot`
- `project_defined_hook`
- `console_tail` (defaults to path-backed `editor_log`; use explicit
  `source=console` only for in-memory Console-buffer checks)

Pass criteria:

- scenario reaches terminal `passed`
- refresh step settles successfully
- if `scene_open` is used, the payload reports `status=passed` and the expected
  `active_scene.path` before Play Mode entry
- play mode transitions reach explicit target states

### 4. Refresh Contract Smoke

Use a short scenario or direct route to verify refresh semantics.

Pass criteria:

- top-level refresh returns:
  - `refresh_completed` or `refresh_and_resolve_completed`
  - `requested_outcome`
  - `settled_at_utc`
  - `completion_basis`
- `playmode_state_after_settle_trust_class=confirmed` when bridge identity stayed
  stable during settle
- after a bridge identity change, refresh keeps the observed
  `playmode_state_after_settle` for compatibility but reports
  `playmode_state_after_settle_trust_class=stale_risk` and
  `playmode_state_after_settle_recommended_next_action=confirm_via_unity_playmode_state`;
  use `unity_playmode_state` before gating a PlayMode-sensitive mutation
- if scenario-driven refresh is used, nested refresh payload should expose the
  same settled contract class rather than only raw `*_requested` transport timing
- if a passed `project_defined_hook` reports an `*_applied` mutation and the
  immediately following `project_refresh` times out, the compact scenario
  verdict remains `inconclusive`/`failed` at scenario level but reports
  `failure_class=applied_mutation_settle_timeout`,
  `trust_class=mutation_applied_unsettled`, and
  `applied_mutation_settle_summary`. Treat the mutation as applied and the
  settle as unproven; verify the editor is settled before the next mutation.

### 4a. Filtered Test Zero-Match Recovery

When a direct EditMode or PlayMode request supplies one or more test, group,
category, or assembly filters, `total=0` is not passing validation even if the
outer MCP request completed successfully. Inspect the persisted test-result
artifact for the counts and filter summary.

After C# test sources were added or changed outside the Unity editor, run one
`request-project-refresh`, wait for the editor to settle, and retry the exact
same filtered request once. If it still selects zero tests, stop and report a
filter mismatch; do not turn repeated refreshes or a transport `ok` result into
validation evidence. An unfiltered request for a project with no tests remains
the separate `no_tests` case.

The reproducible cold-discovery regression creates an EditMode test source,
refreshes once, then requires its fully qualified target to select exactly one
passing leaf:

```bash
bash templates/smoke/run_editmode_targeted_filter_cold_discovery_suite.sh \
  --project-root /path/to/UnityProject
```

### 4b. Passive Readiness Poll Contract

Use `project_defined_hook_poll_until` when a project hook exposes a passive
readiness snapshot. The hook may report `status: not_started` while the target
flow or asynchronous model has not initialized yet. That status keeps polling
by default; `passWhen` and `failWhen` are evaluated first, so a caller can still
make `not_started` terminal explicitly. Any other unmatched status fails closed,
and repeated `not_started` payloads still end at the configured timeout.

Pass criteria:

- at least one `not_started` poll is observed before the passing payload;
- the scenario does not terminate with `project_hook_poll_until_unmatched_status`;
- a matching `failWhen` for `not_started` fails on the first poll;
- a never-ready hook ends with `project_hook_poll_until_timeout` and preserves
  the latest payload.

### 5. PlayMode Result Parity Smoke

Use a representative direct `unity.tests.run_playmode` request and a scenario
`tests_run_playmode` step that target the same PlayMode test.

Pass criteria:

- both paths finish successfully
- both payloads expose `playmode_state_after_settle`
- both payloads report the same final value
- for the common single-test happy path, the final value should normally be
  `edit`

### 5a. Portfolio Test Closeout Smoke

For multi-project EditMode/PlayMode validation, the closeout artifact must
distinguish:

- MCP transport or wrapper operation success
- Unity test request completion
- test-suite pass/fail status
- editor restoration or closeout status

Pass criteria:

- the aggregate summary contains one row per project/mode that ran
- each row includes request id, result artifact path, top-level test counts,
  lifecycle churn flag, and restore/closeout status
- repeated test failures are grouped by a stable first-failure class/key
- package-source and package-lock alignment are summarized when package
  validation is part of the run
- workspace side effects separate preexisting dirty files, allowed new dirty
  files, and unexpected new dirty files
- a completed MCP request with failing tests is reported as a test-suite
  failure, not as an infrastructure failure

### 5b. Batch-Result GUI Subset Selection

`run_multi_project_gui_test_subset.sh --from-batch-results DIR` consumes the
persisted compile evidence from a previous multi-project compile run. A passed
compile matrix is eligible regardless of whether it ran in batch mode or the
valid GUI fallback lane.

Pass criteria:

- the selection summary reports status-file, eligible, selected, excluded, and
  legacy-result counts before GUI workers start;
- a GUI fallback matrix retains its real total/passed/failed counters in the
  persisted status and is selected once;
- a malformed status, missing project root, duplicate eligible root, or
  eligible-versus-selected mismatch reports `selection_warning` and stops
  before any editor is opened;
- an explicit `--from-batch-results` request with no eligible projects does
  not fall back to broad project auto-discovery;
- compact batch rows state whether license evidence came from cache and, when
  available, its age in seconds.

### 6. PlayMode Lifecycle Retry Smoke

Use a representative direct `unity.tests.run_playmode` request while the editor
is already in Play Mode so the host must:

- observe `playmode_state_invalid`
- issue `unity.playmode.set exit`
- retry the PlayMode test request

Pass criteria:

- the terminal operator verdict exposes `result_trust_class`
- accepted terminal trust classes are:
  - `unity_completed_confirmed`
  - `unity_completed_after_lifecycle_reset`
  - `wrapper_failed_unity_unproven`
- a terminal `request_lifecycle_reset` without `result_trust_class` is a smoke
  failure
- a reclassified PlayMode request must not leave stale test ownership behind:
  a follow-up PlayMode request may fail for other reasons, but it must not fail
  with `tests_busy`
- final status returns to healthy `edit`

### 7. Lifecycle Reclassification Fault Smoke

Use a temporary editor script change that forces a real compile or bridge
rebootstrap while a top-level refresh request is in flight.

Pass criteria:

- the refresh request still resolves successfully
- lifecycle metadata reports a `bridge_identity_transition`
- the transition includes a host-written `request_reclassified` journal event
- a cleanup refresh returns the editor to healthy `edit` idle state

### 8. Request-Abandoned Fault Smoke

Use an in-flight async request plus an injected editor reload to prove Unity-side
`request_abandoned` journaling.

Pass criteria:

- the async request reaches `request_started`
- a forced reload occurs before completion
- Unity writes `request_abandoned` journal evidence for the same `request_id`
- cleanup restores healthy `edit` idle state

### 9. Transport Matrix Smoke

Switch the bridge transport across the supported transport set and rerun the
compact post-change validation route on each transport.

Pass criteria:

- each configured transport reaches healthy status
- status reports the requested and active transport coherently
- the compact post-change validation route passes on each transport
- cleanup restores the original bridge config

### 10. Lifecycle Stress Smoke

Run a short resilience route while another desktop app is frontmost, then verify
the bridge still handles refresh, scenario, and playmode lifecycle operations.

Pass criteria:

- status, refresh, contract scenario, and playmode enter/exit all succeed
- repeated `ensure-ready` works against the same editor session
- final status returns to healthy `edit`

### 11. Multi-Project Acceptance Smoke

Run the same compact readiness and refresh route against more than one Unity
project on the same host, with different project roots and transport bindings
where feasible.

Pass criteria:

- each project resolves to its own editor instance or offline state correctly
- status and refresh requests do not leak across project roots
- same-host transport selection stays per project, not global
- one project's degraded or offline state does not make the second healthy
  project look degraded

### 12. Discovery Divergence Smoke

Exercise cases where bridge state, host session state, and process-table
evidence disagree.

Minimum cases:

- `same_project_editor_running_bridge_not_ready`
- `stale_bridge_state`
- `stale_host_session`
- `bridge_disabled`

Pass criteria:

- `project-discovery-report` returns the expected
  `discovery_classification`
- summary surfaces return the expected `reconciliation_case`
- the surfaced `recommended_next_action` is coherent with the detected case
- `bridge_disabled` guidance distinguishes package declaration from project
  bridge enablement: manual manifest edits and manual Unity opens may import the
  package but are not treated as bridge opt-in

### 13. Health Policy Smoke

Exercise stale and ANR-suspected health classifications without accepting false
positive termination during normal lifecycle churn.

Pass criteria:

- healthy baseline reports fresh host health
- stale and ANR-suspected synthetic or live evidence classify correctly
- the surfaced termination policy is coherent with the health evidence
- normal compile/import/playmode churn does not escalate to destructive
  termination policy by default

### 14. Artifact Probe Smoke

Use a small ZIP/APK fixture and run `artifact-probe`.

Pass criteria:

- an existing ZIP entry passes
- a missing required entry fails
- `zip_entry_glob_exists` reports a match without dumping archive contents
- `--artifact-probe-warn-only` keeps the wrapper path non-fatal while the
  probe verdict is still surfaced clearly

### 15. Android APK Smoke

Use a clean Unity project and prove the default Git UPM package route can:

- import the package
- enable the bridge without rewriting package mode
- pass `ensure-ready`
- report healthy `unity.status`
- close the host-opened editor session cleanly
- produce an Android APK from a regular Unity batch build command

Pass criteria:

- `--enable-project` leaves `Packages/manifest.json` on the Git dependency
- `request-status-summary` reports `dependency_mode=git_or_remote`
- `request-status-summary` reports `alignment=git_pinned`
- the smoke emits a summary artifact with APK path, SHA-256, and build log path
- when Android Build Support is missing and the caller does not pass
  `--allow-no-android`, the runner fails in `preflight` and still writes a
  summary artifact with the recommended fix
- when Android Build Support is missing and the caller passes
  `--allow-no-android`, the runner still proves MCP readiness and marks the APK
  lane as `skipped_missing_android_build_support`

Reusable runner:

```bash
templates/smoke/run_clean_project_android_apk_smoke.sh
templates/smoke/run_clean_project_android_apk_smoke.sh --allow-no-android
```

### 15. Batch Side-Effect Smoke

Use a temporary Git workspace around a short batch helper or synthetic command.

Pass criteria:

- a file dirty before the command is listed under `preexisting_dirty_paths`
- a file dirtied during the command is listed as new
- allow-file paths are separated under `allowed_new_dirty_paths`
- unexpected paths are separated under `unexpected_new_dirty_paths`
- no cleanup is executed automatically

### 16. Project Hook Summary Smoke

Run a scenario with at least one `project_defined_hook` step.

Pass criteria:

- compact scenario summary includes `project_defined_hook_summary`
- hook step id, hook name, status, and outcome are visible
- boolean payload fields are promoted under `payload_flags`
- small scalar payload fields are promoted under `payload_scalars`
- secret-shaped payload keys are not surfaced

### 17. Reclassification Verdict Smoke

Use the lifecycle fault/reclassification suite and inspect
`request-final-status`.

Pass criteria:

- completed requests reclassified after lifecycle churn report
  `operator_verdict.status=confirmed_success_after_lifecycle_churn`
- when Unity completion is confirmed but the original host response was not
  observed, tracked requests instead report
  `terminal_disposition=unity_completed_host_delivery_unproven`,
  `operation_outcome=completed_ok`, and
  `result_trust_class=unity_completed_confirmed`
- that delivery-unproven completed disposition reports
  `operator_verdict.should_retry=false`,
  `safe_next_action=continue_without_retry`, while keeping the operation-level
  `recommended_next_action=none`
- `operator_verdict.should_retry=false` when
  `recommended_next_action=none`
- unproven lifecycle failures keep warning-first wording and do not claim Unity
  completion

### 18. Scenario Decision Verdict Smoke

Use `unity_scenario_run_and_wait` on a small passing scenario and one failing
scenario.

Pass criteria:

- the default response is a compact decision envelope, not the raw scenario
  payload
- passing responses expose `verdict=passed`, `trust_class=authoritative`,
  `scenario_status=passed`, short `steps`, and `recommended_next_action=none`
- failing responses expose `verdict=failed`, a stable `failure_class`, and a
  compact `error.code` without dumping large hook payloads
- UI-smoke hook payloads promote `user_path`, `selected_tab`, model/UI before
  and after values, screenshot path, and path coverage summary when present
- full scenario payloads remain available only through the documented
  verbose/full-payload opt-in
- lifecycle recovery that opens or reopens Unity includes
  `editor_relaunched`, `previous_editor_pid`, `current_editor_pid`,
  `bridge_generation_before`, `bridge_generation_after`, and
  `cold_start_reason`

## Public Template Assets

Generic example scenario JSON templates live under:

- `templates/scenarios/interactive_acceptance_smoke.json`
- `templates/scenarios/refresh_contract_smoke.json`
- `templates/scenarios/compile_contract_smoke.json`
- `templates/smoke/run_playmode_settled_state_regression.sh`
- `templates/smoke/run_playmode_lifecycle_retry_smoke.sh`
- `templates/smoke/run_editmode_targeted_filter_cold_discovery_suite.sh`
- `templates/smoke/run_request_abandoned_fault_suite.sh`
- `templates/smoke/run_transport_matrix_suite.sh`
- `templates/smoke/run_lifecycle_stress_suite.sh`
- `templates/smoke/run_lifecycle_fault_injection_suite.sh`
- `templates/smoke/run_multi_project_acceptance_suite.sh`
- `templates/smoke/run_phase2_divergence_suite.sh`
- `templates/smoke/run_phase3_health_policy_suite.sh`
- `templates/smoke/run_post_change_validation.sh`
- `templates/smoke/run_smoke_suite.sh`

Projects may copy and extend them in host-local operational layers.

## Public Runner Contract

The public shell runners are baseline templates, not project routers.

Required caller-supplied inputs:

- `--project-root`
- `--acceptance-scenario`
- `--contract-scenario`

Current generic compile modes:

- `build-config-matrix`
- `none`

Required durable phase lines:

- compile preflight
- readiness
- compile matrix
- acceptance scenario
- contract scenario
- PlayMode/lifecycle checks
- auxiliary consistency checks
- cleanup/restore

Long auxiliary or cleanup phases should emit quiet heartbeat lines naming the
phase and next terminal condition. Bridge generation churn should be
`non_blocking_churn` when the terminal verdict passed, final health is healthy,
compiler errors are zero, and unrecovered abandoned requests are zero;
otherwise classify it as `actionable_churn`.

Before batch preflight, `run_post_change_validation.sh` emits an explicit
`lane_decision`. A healthy or otherwise live same-project editor selects
`interactive_mcp`; if `request-status-summary` fails, the runner checks direct
`bridge-state` liveness before deciding. Only a positive closed-editor result
selects `closed_batch_preflight` and lets `--compile-mode build-config-matrix` run
`batch-build-config-compile-matrix --batch-fallback-mode require-batch` before
`ensure-ready --open-editor`. This keeps script compile failures out of GUI Safe
Mode startup without sending a healthy open editor into a conflicting batch
lane. If both probes leave editor liveness unknown, the runner emits
`lane_decision=blocked` and stops before batch execution. Callers using
`--no-open-editor` keep the existing bridge compile matrix after readiness.

Optional post-change parity inputs:

- `--playmode-regression-assembly-name`
- `--playmode-regression-test-name`

PlayMode troubleshooting branch:

- if the first direct PlayMode request returns `playmode_state_invalid`, allow
  the host to exit Play Mode and retry once
- if the retry returns `request_lifecycle_reset`, recover by
  `request-final-status --request-id <id>` and inspect `result_trust_class`
  before concluding the test failed
- if the follow-up request returns `tests_busy`, treat that as stale test
  ownership and fail the smoke

Lifecycle contract:

- if the host opens Unity for the run, the runner should restore the original
  closed state on exit
- a closeout run is only considered successful when `restore-editor-state`
  reaches verified process exit; a plain quit acknowledgement is insufficient
- project-specific wrappers may opt out only when they intentionally want to
  preserve the interactive editor session for follow-up inspection
- after lifecycle churn or wrapper-side response loss, the preferred recovery
  path is `request-final-status --request-id <id>` before blind retry
- if the wrapper stalled before surfacing a usable `request_id`, the preferred
  recovery path is:
  - `request-status-summary`
  - then `request-latest-status --operation <operation>`
- when discovery and reconciliation surfaces exist, the preferred first
  diagnostic route is:
  - `project-discovery-report`
  - then compact status or final-status follow-up
- after a live-editor `devmode` package-source switch, the smoke contract should
  require:
  - `request-project-refresh`
  - then `request-status-summary`
  - before compile/test/scenario work claims success on the new package source
- when a compact summary surface exists, the smoke route should use it before
  raw result polling or large log inspection
- a lifecycle-reset smoke result is not accepted unless the wrapper exposes one
  obvious follow-up command using that exact `request_id`
- if the wrapper had already emitted `request_submitted`, a compact recovery
  result that reports:
  - `request_observed_in_unity_journal=false`
  - `bridge_changed_since_submission=true`
  - `operation_outcome=submitted_lost_after_lifecycle_churn`
  should be treated as a first-class regression signal for recovery clarity

Token-discipline contract:

- prefer `request-status-summary` over repeated raw status checks
- prefer `project-discovery-report` over manual state-file and process-table
  inspection when routing or recovery is unclear
- prefer `request-latest-status --operation ...` over manual request-journal
  digging when the request id is not already known
- prefer persisted scenario-result summaries over tight `unity.scenario.result`
  polling loops

Scenario payload contract:

- `request-scenario-run-and-wait` defaults to a compact decision envelope. Its
  `steps` field is a compact summary, not the raw persisted scenario `steps`.
- compact run-and-wait responses expose `payload_mode=compact_decision`,
  `steps_payload_mode=compact_summary`, `raw_steps_included=false`,
  `raw_steps_available`, `raw_step_count`, `compact_step_count`,
  `full_payload_cli_args`, `full_payload_tool`, and
  `full_payload_tool_arguments`.
- smoke helpers that assert `payload_json`, `hook_name`, exact raw step fields,
  or scenario parity fixtures must pass `--include-full-payload`.
- operators can recover full evidence from a compact verdict by using the
  structured `full_payload_cli_args` or by calling `unity_scenario_result` with
  the emitted `run_id`.
- compact scenario output remains the default for low-token operator decisions;
  raw full payload output is the explicit evidence/parity mode.
- prefer compact batch failure summaries over direct `prepare.log` or
  `build.log` tailing
- treat a smoke workflow as failed if it repeatedly dumps raw scenario results
  or raw build logs before exhausting the compact summary surfaces
