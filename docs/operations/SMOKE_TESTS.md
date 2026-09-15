# XUUnity Light Unity MCP Smoke Tests

Date: `2026-07-15`
Status: `current source after v0.3.76`

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
- a readiness timeout/error derived from log markers reports
  `compile_state=unmeasured`; it must not claim that a compile failed
- transient bridge-attach/import/identity conditions keep polling, so stale
  log markers cannot preempt a bridge that becomes healthy inside the budget
- bridge-not-attached and import/compile-busy readiness conditions recommend a
  status poll, not editor restart/recovery
- a blocking readiness condition must set `host_prerequisites.ready=false`,
  include its code in `blocking_codes`, and expose the matching
  `checks.readiness_gate` row

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
- The `v0.3.70` compile summaries also expose `warning_count`,
  `unique_warning_count`, and a bounded `warnings` sample. A warning-cleanup
  smoke must assert those fields explicitly; `status: passed` alone proves only
  that no compile error occurred. `warnings_truncated: true` means the counts
  remain authoritative while the sample is incomplete.
- Current-source compile summaries expose `rebuilt_assembly_count`,
  `cached_assembly_count`, and `rebuild_evidence_status`. Assert a measured
  nonzero rebuild count when the smoke is meant to prove a recent source edit;
  a green error/warning verdict with only cache hits does not prove that edit
  was compiled.
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
`Library/XUUnityLightMcp/sdk/generated_diff_guard.json` by default, then
registers the published file as an `sdk_generated_diff_report` artifact. Both
passing and failed verdicts return `artifact_registered=true` plus a compact
`artifact_registry` pointer containing the report hash and registry location.
A failed guard is a validation failure, not a passing resolver request. It does
not prove EDM4U async freshness or replace the planned portfolio SDK lane.

Before resolver work, run `unity_sdk_package_restore` or:

```bash
./xuunity_light_unity_mcp.sh request-sdk-package-restore \
  --project-root "/path/to/UnityProject"
```

The project must be closed. A passing, run-bound
`xuunity.sdk-package-restore.v1` receipt records the registered package
ids/versions, direct dependencies,
`*Dependencies.xml` paths and hashes, and post-restore manifest/lock hashes.
Timeout, missing/invalid receipt, nonzero Unity exit, restricted process
visibility, a same-project editor conflict, or an editor that remains live all
leave `decision_ready=false`.

For a decision-grade Android resolver verdict, prefer
`unity_sdk_android_resolve` or
`request-sdk-android-resolve --config-file <resolver.json>`. The config must
declare at least one `trackedGeneratedPaths` entry and one expected coordinate.
The operation passes only after the EDM4U callback reports success, all tracked
outputs have identical size/SHA-256 evidence across `stableIdleTicks` idle
samples, and dependency verification passes. Callback loss/failure,
missing/unstable output, and missing expected coordinates fail closed.

Before either Android EDM4U request, switch the active build target through
`unity_build_target_switch` / `request-build-target-switch` and wait for settle.
`unity_edm4u_resolve` now fails with `edm4u_android_target_not_active` when the
active target is not Android and with `edm4u_android_support_missing` when the
Android module is unavailable. A successful request reports
`build_target_precondition=confirmed`, but deliberately keeps
`resolver_output_freshness=unproven` and `decision_ready=false`; dependency and
generated-diff proof remain mandatory.

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
- A zero warning count now proves no warnings were observed by the Unity
  compilation callback for the requested lanes. It still does not prove that
  every relevant assembly rebuilt rather than coming from cache; use a clean
  consumer or separate rebuild evidence when that distinction matters.

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
- `ui_click`, `ui_exists`, and `ui_get_text`
- `project_defined_hook`
- `console_tail` (defaults to path-backed `editor_log`; use explicit
  `source=console` only for in-memory Console-buffer checks)

Pass criteria:

- scenario reaches terminal `passed`
- refresh step settles successfully
- if `scene_open` is used, the payload reports `status=passed` and the expected
  `active_scene.path` before Play Mode entry
- play mode transitions reach explicit target states

For any UI-evidence lane, configure the Game View before entering Play Mode.
Use a fixed portrait or landscape size appropriate to the UI under test (for
example `1080x1920`) and keep it constant across projects. A responsive panel
can report itself visible while its rendered bounds are `0x0` below a layout
breakpoint; an unpinned capture can therefore show the wrong screen while a
visibility-only assertion appears plausible. If a capture is surprising,
measure the target with `unity_ui_query` or `unity_ui_get_bounds` before rerunning.
When Play Mode is expected, immediately before every UI interaction or
screenshot assertion require the point-of-use payload (or its persisted
scenario step) to report `playmode_loop_liveness=advancing`. A prior
`unity_playmode_state` sample is useful context but does not prove the later
frame advanced. Treat
`result_trust_class=playmode_throttled` or `playmode_liveness_unproven` as a
non-decision-ready observation and follow `playmode_liveness_remediation`.

For screenshot/layout acceptance, assert `render_target_available=true` and
use `render_width`/`render_height` as the captured-frame dimensions. When
`render_target_differs_from_screen=true`, retain `screen_width`/`screen_height`
only as separate editor/runtime layout evidence; never label the Screen values
as the screenshot resolution. UI read payloads expose the same pair so bounds
and captured pixels can be compared without guessing.

For `project_defined_hook_poll_until`, `passWhen` and `failWhen` remain the
terminal predicates. When `continueWhen` is omitted, an unmatched successful
payload now keeps polling until a terminal predicate matches or the step times
out. Supply `continueWhen` only when unmatched payloads should be treated as a
contract error instead of normal waiting.

### 3a. Profile Apply Then Gate

A build-profile apply may change scripting defines and trigger a domain reload.
Do not place `project_refresh` immediately after that hook. Mark the apply step
with `mutationSettlePolicy: "apply_then_gate"`; scenario validation then
requires the next three steps to be `wait`, `status`, and
`compile_player_scripts`, in that order, and rejects an intervening refresh.

Run hook-dependent scenarios only while the assembly that owns the hook is
enabled by the active profile. If validation cannot resolve a hook, the
`scenario_invalid` message now includes the first validation issue. When a
matching source candidate belongs to an assembly definition (`.asmdef`) with
define constraints, the issue names the assembly, its constraints, and the
active player defines. Apply the enabling profile in a separate gated phase,
then validate and run the hook-dependent scenario.

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
- if a passed `project_defined_hook` reports an `*_applied` mutation and a
  later refresh or compile gate fails after only passed wait/status steps, the compact scenario
  verdict remains `inconclusive`/`failed` at scenario level but reports
  `failure_class=applied_mutation_settle_timeout`,
  `trust_class=mutation_applied_unsettled`, and
  `applied_mutation_settle_summary`. Treat the mutation as applied and the
  settle as unproven; `should_retry=false` and verify mutated state before any
  reapply.
  This remains a compatibility diagnosis for older scenarios; new profile
  lanes should use the apply-then-gate contract above and avoid this shape.
- any other scenario whose first failure is a `project_refresh` step with
  `project_refresh_timeout` carries a `refresh_timeout_recovery` block. It
  classifies the timeout from Unity-side settle evidence captured at the
  timeout instant (`package_settle_timeout`, `compile_import_churn_timeout`,
  `editor_busy_timeout`, `idle_confirmation_incomplete`,
  `lost_final_accounting`), from host health (`editor_failure` when the editor
  is unreachable), or reports `unclassified_legacy_payload` for results written
  by an older package. Unless the editor is unreachable, the verdict-level
  `recommended_next_action` becomes `request_status_summary_then_compile_gate`
  with a concrete `recovery_cli_args` command and a note that the Unity
  operation may have completed even though the waiter timed out; do not retry
  blind. When the editor is unreachable the action is
  `recover_editor_session` with an `ensure-ready` recovery command.

### 4a. Filtered Test Zero-Match Recovery

When a direct EditMode or PlayMode request supplies one or more test, group,
category, or assembly filters, `total=0` is not passing validation even if the
outer MCP request completed successfully. Inspect the persisted test-result
artifact for the counts and filter summary.

MCP `testNames`, `groupNames`, `categories`, `assemblies`, and
`assemblyNames` filters are arrays of strings. A scalar such as
`"testNames": "Namespace.Test"` is rejected with `-32602` before Unity runs;
it is never widened to an unfiltered suite.

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

### 4b.1. Project-Action Currency Contract

Exercise both catalog modes through `unity_project_action_invoke` or a raw
scenario `project_action` step.

For an ordinary action, normalization must produce
`project_action_currency -> project_defined_hook`. The hook keeps the caller's
step id and depends on the generated `__currency` step. If the newest `.cs`,
`.asmdef`, `.asmref`, or `.rsp` under `Assets` is newer than
`editor_domain_loaded_utc`, the currency step fails with
`editor_domain_stale`; the hook is not invoked and the result recommends
`run_unity_project_refresh_before_invoking`. An unavailable timestamp or failed
scan is `unknown` and also fails closed.

For an asset-reading catalog action marked `requiresFreshAssets: true`, the
sequence must be
`project_refresh -> project_action_currency -> project_defined_hook`. The
generated refresh uses `forceAssetRefresh=true`, `resolvePackages=false`, and
`rerunHealthProbe=false`, waits for the existing refresh/domain settle
contract, and records `asset_refresh_performed=true` before the hook can run.
Original dependencies stay on the refresh; each generated step depends on its
predecessor.

Also assert that `unity_status_summary` and
`unity_project_action_currency` expose the same domain timestamp, currency
classification, newest input, reason, and recovery. While the bridge is active,
`application_run_in_background=true` and `native_autofocus_enabled=false` must
be explicit. Neither field replaces the point-of-use
`playmode_loop_liveness=advancing` requirement for Play Mode evidence.

### 4c. Mutating Project-Action Delta Contract

For a mutating action invoked through `unity_project_action_invoke`, distinguish
Unity execution from acceptance. A passed hook should return:

```json
{
  "mutation_delta": {
    "schema_version": "xuunity.mutation-delta.v1",
    "unit": "rows",
    "target": "generated_catalog",
    "before_count": 22,
    "after_count": 22,
    "added_count": 2,
    "removed_count": 2,
    "changed_count": 4
  }
}
```

The counts must be non-negative integers and satisfy
`after_count == before_count + added_count - removed_count`. The wrapper keeps
`succeeded` as Unity execution truth and adds the acceptance verdict:

- valid, no removals/count shrink: `mutation_decision_ready=true` and
  `mutation_trust_class=mutation_delta_confirmed`;
- missing or invalid delta: non-decision-ready `unverified_mutation` plus an
  inspect-diff/update-hook action;
- removals or count shrink: non-decision-ready `destructive_drop_risk` plus a
  review-removed-entities-and-diff action.

Do not interpret `succeeded=true` alone as permission to accept generated
assets or catalogs. Raw `project_action` scenario envelopes promote a reported
delta through the hook summary, but catalog-aware missing-proof verdicts remain
a follow-up outside the typed invoke tool.

Project hooks should construct this payload with the package-owned
`XUUnityLightMcpMutationDelta.Create(...)` helper. The helper owns the schema
version, rejects empty unit/target values, rejects negative counts, and enforces
the count invariant before the hook can serialize misleading proof.

### 4d. Synchronous Rule-Assertion Hooks As A Validation Lane

When gameplay rules change, prefer a project hook that drives the game's own
API and asserts state synchronously over click-and-screenshot driving: it
needs no rendered frames, is immune to editor throttling and focus theft, runs
in fractions of a second, and returns decision-ready scalars through the
catalog `evidence` contract. In its source session such a hook caught a
same-frame duplicate-object defect (Unity's deferred `Destroy`) that the
visual lane had missed. The hook belongs in the project's own action catalog,
not in this package: the public surface only transports its typed evidence.

### 5. PlayMode Result Parity Smoke

Use a representative direct `unity.tests.run_playmode` request and a scenario
`tests_run_playmode` step that target the same PlayMode test.

Pass criteria:

- both paths finish successfully
- both payloads expose `playmode_state_after_settle`
- both payloads report the same final value
- for the common single-test happy path, the final value should normally be
  `edit`
- both completed and timed-out test envelopes report
  `console_error_count_since_request_start` plus its trust class; if a runtime
  timeout has positive console pressure, inspect the request-scoped console
  errors before increasing the timeout

Precondition: any observation made while Play Mode is running is evidence only
if `playmode_loop_liveness` is `advancing` (section 24); a play-mode
observation without proven frame advance is no evidence.

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
- a passing compact GUI-fallback row remains `passed_via_gui_fallback` whether
  its evidence is present at the payload top level or recovered from the named
  summary/result artifact;
- unavailable matrix counters print `unavailable`, never measured zeroes.

### 5c. Published-Package Consumer Rollout

Use `scripts/testing/run_consumer_rollout.py` for a release tag that must be
resolved and compiled across several Git package consumers managed by Unity
Package Manager (UPM). The detailed procedure is in
`docs/operations/CONSUMER_RELEASE_ROLLOUT.md`.

Pass criteria:

- explicit roots and the ignore-independent manifest discovery set reconcile
  before any package file changes;
- preflight proves exact Unity-version parity, global process visibility, no
  conflicting Unity main/worker process, batch-license capability, required
  write access, and a unique evidence directory;
- only the canary is pinned before its published tag/hash resolves and compiles;
- every later clean project uses that exact tag and full release commit;
- baseline-dirty package files remain unchanged and are reported separately;
- the atomic ledger records every project transition, command, unique log,
  package proof, compile verdict, workspace side-effect verdict, and cleanup;
- a timeout leaves an owned PID evidence record for root review instead of
  letting a bounded worker kill it;
- cleanup refuses any PID whose current process command no longer proves the
  exact Unity main process, project root, and unique log path;
- credential-shaped process arguments are redacted before ledger persistence,
  and the overall deadline can stop execution before fan-out;
- compact summary output is the default and names the canary, denominator,
  first unproven project, artifact paths, and next action; full evidence stays
  behind `--output full`.

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

Precondition: liveness first — any in-play observation counts only while
`playmode_loop_liveness` is `advancing` (section 24).

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
- if the same request later completes successfully, the terminal envelope is
  `confirmed_success_after_lifecycle_churn`, confirms Edit Mode and zero
  compiler errors, and reports `retry_required=false`

### 8a. Dynamic Hub Licensing Handoff Smoke

With a closed project and one signed-in Unity Hub session, run Hub-aware
`ensure-ready --open-editor` without explicit `-licensingIpc` arguments.

Pass criteria:

- exactly one live Hub-owned licensing candidate is discovered and forwarded
- the bridge reaches healthy readiness on the version from `ProjectVersion.txt`
- output includes redacted provenance and never the raw channel
- zero candidates returns typed user action; multiple candidates are refused
- a stale/dead candidate is ignored
- restore verifies editor exit and reports helper-owned licensing-child cleanup
- a pre-existing shared Hub licensing client is never terminated

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

### 19. Mutation Receipt Honesty Smoke

Every other guardrail on `unity_prefab_mutate` — `expectedSha256`, atomic
rollback, `post_validation`, `reversible_patch_json` — assumes the change table is
truthful. A receipt that reports `applied` for a write that changed nothing
defeats all of them at once, and an operator who does not re-measure the render
ships the wrong value believing the receipt.

Run four transactions against a throwaway prefab with a managed enum field
(`Image.m_Type` is a convenient one):

1. `set_serialized_field` writing the value the field already holds
2. `set_serialized_field` on the enum with `numberValue` out of range
3. `set_serialized_field` on the enum with `stringValue` naming a real member
4. `set_serialized_field` on the enum with `stringValue` naming no member

Pass criteria:

- case 1 reports `status: "no_op"` for that operation, never `applied`; the
  transaction still succeeds; `no_op_count` is `1` and `planned_change_count`
  excludes it; a `prefab_mutation_no_op_operations` warning is present
- case 2 fails as `prefab_mutation_enum_value_invalid`, the whole batch rolls
  back, and the message states that `numberValue` is the member index and lists
  the valid `name=index` pairs
- case 3 applies, and `before`/`after` name the enum members rather than
  indices, so `reversible_patch_json` carries a `restoreValue` that can be
  replayed through `stringValue`
- case 4 fails as `prefab_mutation_enum_value_invalid` and lists the valid
  members
- a transaction that supplies no `expectedSha256` reports
  `drift_guard: "unguarded"` plus a `prefab_mutation_unguarded_by_precondition`
  warning carrying the observed hash; one that supplies a stale hash fails as
  `prefab_mutation_asset_drifted` and names `unity_project_refresh` as the remedy

### 20. Render-To-Semantic-Lane Smoke

A snapshot returned inline only cannot close the semantic acceptance lane,
because `unity_ui_reference_compare` consumes a snapshot by path. Before this was
fixed, a reference declaring `acceptance.semantic: "required"` was unsatisfiable
outside Play mode and reported `not_evaluated / no_ui_snapshot_supplied` forever.

Register a reference with `acceptance.semantic: "required"` and at least one
`requiredUi` selector, then run `unity_prefab_render` on the prefab and feed the
result straight into `unity_ui_reference_compare`.

Pass criteria:

- the render returns a non-empty `snapshot_path`, the file exists beside the
  capture with a `.ui-snapshot.json` suffix, and it parses as a complete
  `xuunity.ui.read.v1` payload with the rendered nodes and `target.capture_width`
  / `target.capture_height`
- `includeSnapshot` defaults to `false`, so the response does not carry the node
  list
- passing that `snapshot_path` as `uiSnapshotPath` moves the semantic lane off
  `not_evaluated` with no Play-mode run
- rendering a second UI state through `overrides` needs zero mutations: the
  response reports `applied_overrides`, and the prefab's `sha256` is unchanged
  afterwards
- an override that cannot resolve fails the render as
  `prefab_render_override_failed` and returns no `screenshot_path`, because a
  capture of the un-overridden state is evidence for the wrong state
- a comparison that ran returns a successful envelope even when
  `reference_acceptance` is `failed` or `pending_lanes`; only a comparison that
  could not compute a visual verdict belongs on the error channel

### 21. Play-Mode-Blocked Compile Smoke

A compile refused during Play Mode used to report a generic
`Unity editor is busy. isCompiling=False, isPlayingOrWillChangePlaymode=True,
isUpdating=False`. Three flags is not guidance, and the operator had to know
that the second one is the only actionable bit.

Enter Play Mode with `unity_playmode_set action=enter`, then call
`unity_compile_player_scripts`.

Pass criteria:

- the refusal carries `error.code = editor_in_play_mode`, not
  `compile_player_scripts_failed` and not a bare busy string
- the message names both valid next actions: exit Play Mode, or run the
  closed-project batch lane
- `unity_build_player` refuses the same way and reports
  `outcome = gui_build_refused_editor_in_play_mode` with a `refusal_code`
- after `unity_playmode_set action=exit`, the same compile call succeeds

### 22. Stale-Marker Log Smoke

`source=editor_log` searches a fixed tail of a file that accumulates across
editor sessions and play sessions. A shell `until grep -q "<marker>"` wait loop
matched a line written by a *previous* play session and returned immediately —
a false positive that reads exactly like success.

Run a play session that logs a marker, stop, then start a second play session
that does not log it.

Pass criteria:

- an unanchored `unity_console_grep source=editor_log` still matches the stale
  line, and says so: `result_trust_class =
  editor_log_spans_multiple_sessions` with a non-empty `stale_match_caveat`
- the same grep with `since=playmode_start` returns zero matches,
  `result_trust_class = session_scoped_editor_log`, and an empty
  `stale_match_caveat`
- `since_anchor.resolved` is `playmode_start`, `since_anchor.start_offset_bytes`
  is non-zero, and `searched_from_line` points at the first line of the current
  play session
- reported `line` values stay absolute in the Editor.log while
  `line_numbering_basis` is `editor_log_absolute`
- against an editor that never recorded the anchor, the call still answers but
  reports `since_anchor.resolved = anchor_unavailable` and
  `since_anchor_degraded = true` rather than silently widening to the full tail
- an anchor recorded by a different editor PID resolves to
  `anchor_process_mismatch`; its zero-match result is inconclusive

For the truncation branch, generate more than the fixed grep window of log text
after the anchor, with one marker near the anchor and another after the window.

Pass criteria:

- the early marker is found with `search_window_direction =
  anchor_adjacent_head`, `scope_truncated = true`, and `search_verdict = matched`
- a zero-match for the marker outside that partial window reports
  `search_verdict = inconclusive`, `search_verdict_reason =
  anchored_scope_truncated_before_full_search`, and
  `result_trust_class = session_scoped_editor_log_partial_scope`
- the inconclusive payload names a `recommended_next_action`; it never presents
  `match_count = 0` as proof of absence
- raising `maxSearchChars` on the same tool call reaches the later marker and
  changes the verdict to `matched`
- a small complete anchored scope with no marker reports
  `search_verdict = not_matched`
- `unity_console_tail` still keeps the recent end of a truncated anchored scope
  and reports `search_window_direction = scope_tail`

Shell wait loops must use the same discipline. Capture the line count first, then
poll only the tail beyond it:

```bash
BASE=$(wc -l < "$EDITOR_LOG")
until tail -n +$((BASE + 1)) "$EDITOR_LOG" | grep -q "MY_MARKER"; do sleep 1; done
```

An unanchored `until grep -q "MY_MARKER" "$EDITOR_LOG"` is never a valid wait.

### 23. Out-Of-Scope UI Target Smoke

`unity_ui_*` resolved targets in the active scene only. In a project that keeps a
bootstrap scene active and loads screens additively, the operator could not reach
the UI in front of them, and `ui_target_not_found: No GameObject named 'X'` was
indistinguishable from "that object does not exist".

Enter Play Mode in a project with a bootstrap active scene, an additively loaded
screen, and a `DontDestroyOnLoad` overlay.

Pass criteria:

- `unity_ui_query targetKind=active_scene` with a selector matching the additive
  screen fails as `ui_target_out_of_scope`, and the detail names the owning
  scene, the searched scenes, and the loaded scenes
- a genuinely absent object still fails as `ui_target_not_found`
- `targetKind=all_loaded_scenes` finds the same node, and `target.searched_scenes`
  lists every loaded scene
- `target.dont_destroy_on_load_included` is `true` in Play Mode and the overlay's
  nodes are reachable; in Edit Mode the same call reports
  `dont_destroy_on_load_status = edit_mode_no_dont_destroy_on_load_scene`
- `sceneName=<additive scene>` narrows `target.searched_scenes` to that one scene
- `unity_ui_click` delivers to a node in the additive scene and to a node in
  `DontDestroyOnLoad`, and its `delivered_to_path` resolves in the owning scene
- with two same-named objects in different loaded scenes, the click refuses as
  `selector_ambiguous` rather than clicking whichever one a name lookup found first
- with a deliberately tiny `maxNodes`, a selector that exists beyond the
  scanned prefix refuses as `ui_selector_search_truncated`, reports
  `search_node_count`, `search_max_nodes`, `search_truncation_reason`, searched
  scenes, and scenes not reached, and does not deliver a click
- with a budget that finds one candidate but truncates before the remaining
  tree, the click still refuses as `ui_selector_search_truncated` because the
  candidate's uniqueness is not proven
- retrying the same direct or scenario click with a narrowed
  `targetKind`/`targetValue`/`sceneName` or a sufficient `maxNodes` reaches the
  target; only a complete zero-match search may return `ui_node_not_found`
- an inert click may report `delivered=true` but must report `effective=false`,
  `success=false`, `status=delivered_no_observable_effect`, and warning
  `ui_click_no_state_change`; only an observed semantic change sets
  `effective=true`

### 24. Play-Mode Liveness Assertion Smoke

An editor heartbeat is not a game-loop heartbeat: an unfocused editor throttles
its update loop while `is_playing`, `health_status`, and heartbeat freshness all
stay green. Every play-mode smoke above must assert liveness before treating any
in-play observation as evidence.

Enter Play Mode, then move OS focus away from the editor (any other frontmost
application) and poll `unity_playmode_state`.

Pass criteria:

- while the editor is frontmost and the app is running,
  `playmode_loop_liveness` is `advancing` and
  `playmode_frames_advanced_last_interval` is well above the throttle threshold
- after focus moves away long enough for editor throttling to engage,
  `playmode_loop_liveness` becomes `throttled` and the payload carries
  `playmode_liveness_warning: playmode_throttled_editor_unfocused` with the
  remediation `focus_the_unity_editor_or_set_interaction_mode_to_no_throttling`
- refocusing the editor returns `playmode_loop_liveness` to `advancing`
- `unity_status_summary` surfaces the same fields while playing
- `unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`, `unity_ui_click`,
  `unity_game_view_screenshot`, and persisted scenario-step results carry a
  fresh point-of-use liveness sample and `result_trust_class`
- a UI or screenshot call made while throttled reports
  `result_trust_class=playmode_throttled` and the focus/no-throttling remedy;
  it must not inherit a prior advancing verdict
- exiting Play Mode returns `playmode_loop_liveness` to `not_playing`
- immediately after a domain reload or a play-state change, a single sample may
  report `unknown`; `unknown` is not `advancing` and must not be read as
  liveness proof

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
- wrapper `--compact-summary` must emit one JSON document no larger than 8192
  bytes; regression fixtures must fail if nested payload or child stderr is
  printed before or after it
- use `diagnostic-retro-bundle` for a bounded licensing/readiness/lifecycle
  handoff instead of raw process commands or full Editor.log dumps

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


## Diagnostics Freshness and Recovery Regression

Host fixtures: `python3 -m unittest tests.test_retro_recovery`.
These exercise host behavior against an editor transport boundary; they are not
live Unity proof. Run the following separately on a disposable Unity project
using this package revision before claiming editor lifecycle validation:

1. Introduce a compile error, refresh, and capture a diagnostic timestamp and
   bridge generation. A test request must refuse the current error and journal
   exactly one `request_refused` for the original operation.
2. Fix the named source on disk without a manual refresh. The next test request
   must classify the old error as `stale`, refresh once, settle and then run.
   If the error remains after refresh, it must refuse; deferred or missing
   compile evidence must never dispatch the test.
3. With the editor closed, use an isolated copied state fixture with a dead PID
   and old heartbeat. The idle timeout must identify `editor_state_frozen`,
   preserve the timestamp/detail of the last busy reason, and name
   `recover-editor-session`. Do not replace a live editor's state file.
4. Run a well-formed filter matching zero tests and a failing test. Inspect the
   completion journal: `test_verdict` must distinguish no-match from pass;
   an error completion must have a non-empty `reason`.
5. In an isolated package fixture, declare uGUI but disable its optional MCP
   assembly. Probe must report declared-but-unregistered, not missing dependency.
   The optional failure must not degrade unrelated core bridge health. Restore
   the assembly and reload; verify the new probe generation and support.
6. Preserve the existing play-mode reload recovery and batch-to-GUI build
   fallback smoke cases. Verify the build output still exists before handoff.
