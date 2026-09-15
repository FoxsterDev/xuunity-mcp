# XUUnity Light Unity MCP Continuation

Date: `2026-09-03`
Status: `active continuation note`

## Current Baseline

This service is past the design-only stage.

It now has:
- a working stdio MCP server
- an editor-only Unity bridge
- capability probing and gating
- compile and test validation
- compact status summaries with bridge stabilization output
- play mode control
- Game View configure and screenshot support
- asynchronous scenario automation with persisted results
- host-side startup helpers with fail-fast policy for interactive editor startup
- lifecycle-reset recovery by `request_id`
- explicit operator-facing split between transport outcome and Unity operation outcome
- compile-first public post-change validation ordering, including a
  closed-project batch compile preflight before `ensure-ready --open-editor`
  when the reusable post-change runner would otherwise open Unity
- public retro guidance for operator-facing lifecycle and transport failures
- summary-first token discipline for high-churn request paths
- same-project editor launch-in-progress reuse to avoid spawning a second Unity
  instance while an editor open is already in flight
- batch progress heartbeat JSONL sidecars for long-running batch helpers
- generic artifact probe summaries for ZIP/APK and file/text checks
- tracked workspace side-effect accounting around batch helpers
- persisted test-result table reporting for portfolio-scale EditMode/PlayMode
  closeout
- project-defined hook summary promotion in compact scenario summaries
- operator verdicts for confirmed lifecycle reclassification recovery
- design-plan history for retro-derived implementation plans
- public package-bump fast-path guidance for lean `com.xuunity.light-mcp`
  version updates
- point-of-use player-loop liveness/trust evidence on UI reads, guarded clicks,
  Game View screenshots, and persisted scenario steps
- explicit Game View render-target dimensions alongside Unity `Screen.*`
  dimensions and a mismatch verdict
- scenario `ui_click`, `ui_exists`, and `ui_get_text` steps, a public scenario
  capability/schema tool, and file-backed validation input
- request-scoped console-error pressure on EditMode and PlayMode test verdicts
- package-owned mutation-delta construction plus a guarded MCP project-hook
  scaffold path and scalar `xuunity_setup_plan.projectRoot` parity
- one shared project-action currency preflight: editor-domain freshness is
  checked before every hook, while catalog `requiresFreshAssets: true` actions
  automatically run and settle a forced AssetDatabase refresh first
- opt-in background execution: `Application.runInBackground` is backed by
  `PlayerSettings.runInBackground` in the editor, so the bridge changes it only
  under `background_execution_enabled: true` and restores the original value on
  disable or editor quit; never native OS autofocus, and point-of-use
  player-loop liveness remains authoritative

The public `xuunity` protocol layer also now understands validation-lane
selection.

## What Is Already Implemented

External server:
- minimal stdio MCP layer
- `initialize`
- `tools/list`
- `tools/call`
- local diagnostics helpers
- `open-editor`
- `ensure-ready`
- `request-editor-quit`
- `restore-editor-state`
- `request-status-summary`
- `request-final-status`
- `request-scenario-results-list`
- `request-scenario-result-latest`
- `unity_scenario_capabilities`
- `xuunity_project_hook_scaffold`
- additive request-scoped `structured_timing` and `artifact_manifest` on
  successful same-host editor responses and `request-final-status`
- host-local package-source mode switching:
  - `devmode`
  - `prodmode`
- approved closed-project batch validation helpers:
  - `batch-compile`
  - `batch-compile-matrix`
  - `batch-build-config-compile-matrix`
  - `batch-editmode-tests`
  - `batch-build-player`
  - `artifact-probe`
- `test-results-table`, which reads completed Unity Test Framework result
  artifacts without contacting the editor

Unity bridge:
- heartbeat state
- request pump
- capability probe
- capability gating
- status and health operations
- compile validation
- edit-mode test execution
- console tail
- scene snapshot
- scene open for deterministic Edit Mode scene setup
- play mode control
- Game View configure and screenshot
- scenario validation
- asynchronous scenario runs
- persisted scenario results

Scenario second-wave steps:
- `scene_open`
- `compile_player_scripts`
- `tests_run_editmode`
- `game_view_configure`
- `project_defined_hook`
- `ui_click`
- `ui_exists`
- `ui_get_text`

Public reusable smoke assets:
- `templates/scenarios/`
- `templates/smoke/run_package_self_tests.sh`
- `templates/smoke/run_post_change_validation.sh`
- `templates/smoke/run_smoke_suite.sh`
- `templates/smoke/run_playmode_verdict_recovery_proof_suite.sh`
- `DEVMODE_VALIDATION.md`

Package self-test assemblies:
- `com.xuunity.light-mcp.Editor.Tests`
- `com.xuunity.light-mcp.PlayMode.Tests`
- default category: `XUUnity.MCP.SelfTest`
- quick categories: `XUUnity.MCP.Fast`, `XUUnity.MCP.Scene`,
  `XUUnity.MCP.GameObject`, `XUUnity.MCP.Lifecycle`,
  `XUUnity.MCP.Coroutine`

MCP devmode validation closeout:
- after executable-code changes to this MCP host/server/package, follow
  `DEVMODE_VALIDATION.md`
- project-specific validation is additive and does not replace
  `templates/smoke/run_package_self_tests.sh --mode all`

Transport defaults:
- new project setup writes `transport: tcp_loopback` to
  `Library/XUUnityLightMcp/config/bridge_config.json`
- `file_ipc` remains an explicit fallback/compatibility transport

Latest applied retro:
- `../archive/retros/2026-09-03_greenfield_scene_authoring_operator_retro.md`

Latest applied design plan:
- `../architecture/designs/XUUNITY_MCP_DEVMODE_BATCH_LIFECYCLE_HARDENING_DESIGN_2026-05-23.md`

Day-to-day readiness:
- suitable for same-host status, refresh, compile, EditMode, PlayMode, package
  self-test, and scenario workflows
- use `request-playmode-set --action exit` for PlayMode cleanup
- use `restore-editor-state` only for host-opened editor closeout
- use `ensure-ready --open-editor` as the normal startup/reuse path
- do not manually retry `open-editor` while a Unity splash/open is already in
  progress for the same project

## Important Runtime Files

Inside the target Unity project:

- `Library/XUUnityLightMcp/config/bridge_config.json`
- `Library/XUUnityLightMcp/state/bridge_state.json`
- `Library/XUUnityLightMcp/state/capabilities_report.json`
- `Library/XUUnityLightMcp/inbox/`
- `Library/XUUnityLightMcp/outbox/`
- `Library/XUUnityLightMcp/compile/`
- `Library/XUUnityLightMcp/state/test_results/`
- `Library/XUUnityLightMcp/captures/`

Completed Unity Test Framework requests persist one JSON file per `request_id`
under `state/test_results/`. Treat these files as the immutable source of truth
for completed test outcomes. The result counts are top-level fields:
`total`, `passed`, `failed`, and `skipped`; do not assume a nested `counts`
object. The result also carries `test_mode`, `request_id`, `failures`, and
`lifecycle_churn_observed`, which are what `test-results-table` and portfolio
summaries read.
- `Library/XUUnityLightMcp/scenarios/active_run.json`
- `Library/XUUnityLightMcp/scenarios/results/`
- `Library/XUUnityLightMcp/logs/`

## Key Decisions

- editor-only package
- disabled by default
- removable with minimal project residue
- no `ProjectSettings` mutation
- no runtime asmdef
- no broad define mutation
- compile checks should use Unity APIs, not platform switching
- version-sensitive features should be probed and gated
- Game View persistence must be opt-in, not default
- interactive startup should fail fast on compile and package blockers instead of hanging on heartbeat waits

## Validation Lane Model

The shared public `xuunity` core now has a canonical lane model:

- `interactive_mcp`
- `batch_compile`
- `scenario`

Relevant public files:
- `../../../../Modules/XUUnity/knowledge/validation_lanes.md`
- `../../../../Modules/XUUnity/tasks/start_session.md`
- `../../../../Modules/XUUnity/tasks/validation_plan.md`
- `../../../../Modules/XUUnity/skills/tests/unity_test_runner_workflow.md`
- `../../../AI_PROTOCOL_HANDBOOK.md`

Meaning:
- do not re-open the old question of whether shell compile, MCP, and scenario
  automation are equivalent
- lane selection is now part of the protocol contract
- new work should extend that model rather than inventing another validation-path taxonomy
- compile and deterministic EditMode tests may now use an approved closed-project
  `batch_compile` lane, but Play Mode and scene-observation work still require
  `interactive_mcp`

### Batch-Versus-Interactive Routing When An Editor Is Open

The closed-project batch lane refuses any project that has a live editor, with
`editor_running_batch_conflict`. That refusal is protection, not a failure — it
prevents Library corruption — and the rollup now says so:

- the per-project verdict is `blocked_by_live_editor`, not `failed_before_unity`
- the aggregate reports `projects_blocked` separately from `projects_failed`,
  lists `blocked_projects` with their live editor pids, and emits one
  `aggregate_hint` naming the projects to re-run
- the process exit code still reflects "not everything was proven": a run with
  blocked projects exits non-zero, exactly as before

Route a blocked project one of two ways: verify it through `interactive_mcp`
against the editor that is already open, or close that editor with
`recover-editor-session` and rerun the batch lane. Never read `projects_failed`
alone as a portfolio compile verdict.

### Two-Step Editor Recovery

`recover-editor-session` clears stale bridge state; it does **not** open an
editor. Its response says so (`recommended_next_action:
open_editor_or_ensure_ready`), but the two steps are easy to conflate:

1. `recover-editor-session --project-root <path>` — clears a stale
   `bridge_state.json` whose `editor_pid` is dead
2. `ensure-ready --project-root <path> --open-editor` — brings the lane up

Both are needed after a stale-bridge classification. Only the second one gives
you a working interactive lane.

### Alive Editor Without an Attached Bridge

A running editor may predate package installation. Setup plan/apply report
`unity_editor_bridge_attachment_pending` and explain the boundary: until package import
and domain reload attach a bridge, `request-editor-quit` has no receiver.
`recover-editor-session` cannot restart an unbridged live process. Check
`same_project_editor_process_without_live_bridge_state` and project discovery.
Allow the editor to import/refresh; if the bridge still does not attach, save
work and close/reopen that editor out of band. An attachment warning is not authority
to force-kill a process or discard unsaved work.

### A Frozen Heartbeat Is Not a Current Busy Reason

An idle timeout reports PID liveness, `state_frozen`, `busy_reason_detail` and
`busy_reason_as_of_utc`. A dead PID or heartbeat beyond the waiter's freshness
limit yields `editor_state_frozen` and a `recover-editor-session` command.
Read `busy_reason` as the last observation at that timestamp. A live process
with a frozen heartbeat may be blocked, compiling, or otherwise unable to pump;
the snapshot does not prove a crash. Inspect current process/log evidence before
choosing a restart. Recovery refuses a live PID; do not bypass that safety gate.

### Lanes That Refuse During Play Mode

These refuse with `editor_in_play_mode` and name both valid next actions (exit
Play Mode, or use the closed-project batch lane):

- `unity.compile.player_scripts`
- `unity.compile.matrix`
- `unity.build_player`
- the closed-project `batch_compile` lane, which additionally requires no live
  editor at all

A `unity.project.refresh` issued during Play Mode is not refused, but its compile
verdict is not authoritative: asset import is deferred, so the payload carries
`post_settle_compile_trust_class: deferred_during_playmode`. Do not read that
green as proof.

### Play-Mode Evidence Requires Frame Advance

An editor heartbeat is not a game-loop heartbeat. When the editor is not the
frontmost application it throttles its update loop: `is_playing` stays `true`,
`health_status` stays `healthy`, and the heartbeat stays fresh while the game
advances almost no frames — a booting app reads as frozen and the operator
starts debugging application code that is fine.

Before trusting any play-mode observation (screenshot, UI snapshot, click
outcome, boot timing), check the liveness evidence on `unity_playmode_state`
or `unity_status_summary`: `playmode_loop_liveness` must be `advancing`. A
`throttled` value with `playmode_liveness_warning:
playmode_throttled_editor_unfocused` means focus the editor (or set its
Interaction Mode to No Throttling) and re-observe; a play-mode observation
taken without frame advance is not evidence.

## What A New Chat Should Check First

1. Unity version for the consumer project
2. whether the package is installed through Git or local embedding
3. whether the bridge is enabled
4. `bridge_state.json`
5. `capabilities_report.json`
6. `unity.status` or `request-status-summary`
7. `unity.capabilities.get`
8. `unity.health.probe`
9. if a request crossed lifecycle churn and the `request_id` is known,
   `request-final-status <request_id>`
10. if the wrapper stalled before surfacing a usable `request_id`,
    `request-latest-status --operation <operation>`
11. prefer compact scenario or batch summaries before raw result polling or raw
    log inspection
12. if a same-project Unity open is in progress, wait for `ensure-ready` or run
    `project-discovery-report`; do not start a second editor instance

Mini-playbook after wrapper churn:

1. do not retry the original operation yet
2. check whether the wrapper already emitted a `request_submitted` acknowledgement
   - if it emitted `request_not_submitted`, do not search for request recovery
     yet; recover bridge/editor health first
3. run `request-status-summary --project-root <project>`
4. if the `request_id` is known, run:
   `request-final-status --project-root <project> --request-id <id>`
5. if the `request_id` is not known, run:
   `request-latest-status --project-root <project> --operation <operation>`
6. if the recovered request completed, use that disposition and continue
7. for `unity.tests.run_playmode`, read `test_verdict`,
   `result_payload_source`, counts, first failures, progress, timeout
   classification, and cleanup guidance; wrapper `completion_status=ok` alone
   is not a PlayMode pass
8. only retry after the compact recovery step says the original operation did
   not complete
9. if the original failure was `tests_busy`, prefer
   `request-latest-status --operation unity.tests.run_editmode` or
   `request-latest-status --operation unity.tests.run_playmode` before starting
   a second test run
10. for lifecycle-reset recovery, base retry decisions on structured JSON truth
   such as `recommended_next_action`, `result_trust_class`, and
   `bridge_stabilization.safe_to_retry`, not only shell exit behavior
11. if `operator_verdict.status=confirmed_success_after_lifecycle_churn`, do
    not retry; Unity completed the operation and the lifecycle churn is
    informational
12. if `operator_verdict.status=unity_completion_unproven`, inspect the
    surfaced recovery evidence before deciding whether a bounded retry is safe
13. inspect `foreign_requests_since_client_start`; when non-zero, another
    client session is driving this editor, so pause mutating work until it is
    identified; `cli_requests_since_client_start` is wrapper-CLI or smoke
    traffic and is informational, not a reason to stop
14. if a project action reports `mutation_status=applied` with settle/delivery
    unproven, verify project state and do not replay the mutation

Mini-playbook after `devmode` with an already-open editor:

1. do not assume the package source switch is active yet just because
   `ensure-ready` reused the live editor
2. run `request-project-refresh --project-root <project>`
3. run `request-status-summary --project-root <project>`
4. if the refresh request crossed lifecycle churn and the wrapper already
   surfaced a `request_id`, run:
   `request-final-status --project-root <project> --request-id <id>`
5. if that compact recovery summary reports:
   - `request_submitted=true`
   - `request_observed_in_unity_journal=false`
   - `bridge_changed_since_submission=true`
   - `operation_outcome=submitted_lost_after_lifecycle_churn`
   treat it as transport submission with incomplete lifecycle proof, then verify
   the effect directly before blind retry
6. only after that move on to compile, tests, or scenario work

PlayMode churn note:

- `request_abandoned` is intermediate lifecycle evidence, not the terminal
  owner when the same request later has `request_completed`
- a passed PlayMode result followed by a fresh, healthy post-reload bridge in
  Edit Mode with zero compiler errors is returned as
  `confirmed_success_after_lifecycle_churn` with `retry_required=false`
- use `request-final-status` only when that bounded confirmation is absent;
  never retry solely because an earlier raw journal event says abandoned

Mini-playbook for closeout mismatch:

1. run
   `request-editor-quit --project-root <project> --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000`
2. if it returns `editor_quit_ack_without_exit`, treat that as "quit was
   acknowledged but process exit was not proven"
3. run `verify-editor-closed --project-root <project> --timeout-ms 30000`
4. if live project editor PIDs remain, close or terminate the editor explicitly,
   then run `verify-editor-closed` again
5. only after `same_project_editor_closed=true` and
   `process_exit_verified=true` treat the validation session as fully closed

When a known startup or store-profile modal systematically acknowledges quit
without exiting, the explicit escalation is:

```bash
request-editor-quit --project-root <project> --timeout-ms 30000 \
  --force-after-ms 30000
```

This is not a project-wide kill. The helper waits for graceful exit,
re-verifies exactly one current same-project Unity editor PID, terminates only
that PID, and verifies closure. It refuses restricted visibility, changed
identity, and multiple matching editors.

Compile-first closeout recipe for changed C# scripts:

1. inspect editor state with `request-status-summary --project-root <project>`
2. if the same project editor blocks the batch lane, run the surfaced recovery
   command, usually
   `request-editor-quit --project-root <project> --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000`
3. verify process exit with `verify-editor-closed --project-root <project>`
4. run the fast batch compile gate
5. only after compile passes, run batch EditMode tests, PlayMode, scenario, or
   GUI smoke validation

Host process visibility is a lifecycle-truth prerequisite. If a sandboxed or
restricted client reports `process_visibility_restricted`, do not infer that the
editor is closed. Move the command to a host context that can list local
processes, then rerun the closeout or batch preflight.

Only after that:
- compile
- tests
- play mode
- Game View operations
- scenario runs

## Design Plan And Retro Closeout

When a chat provides a concrete MCP design or implementation plan:

1. save a public-safe plan under `../architecture/designs/` when it is a feature,
   tool-surface, lifecycle, operator, or runtime design
2. save retro-derived action plans or lesson records under `../archive/retros/`
   when the source is an incident or weak operator session and the result is
   public-safe
3. update `../architecture/designs/DESIGN_PLAN_HISTORY.md` with status,
   implementation evidence, and remaining gaps
4. after implementation, self-review the code/docs diff before final closeout
5. record post-retro notes: what went well, where risks remain, what validation
   proved, and what follow-up should remain visible

When the retro contains host-private or consumer-project evidence, keep the raw
retro in the host's single MCP-specific retro area instead of a broad report
bucket or a per-project retro folder:

- private, project-specific, or raw evidence:
  `<host-output-root>/Operations/XUUnityLightUnityMcp/Retros/`

Only sanitized reusable lessons should be copied into `../archive/retros/`.
Whenever a durable retro is added, moved, renamed, or deleted, update the
`RETRO_REGISTRY.md` in the same destination.

Self-review should check:

- public interface compatibility
- lifecycle and closeout truth fields
- process or project-selection ambiguity
- docs/operator guidance for the changed behavior
- tests for parser, failure, and recovery paths
- accidental project-private evidence in public docs

## What A New Chat Should Read First

For reusable MCP work:

1. `../../README.md`
2. `../architecture/DESIGN.md`
3. `../archive/retros/CHAT_RETRO_PROMPT.md` when the source is a real failure or weak operator session
4. `../architecture/ROADMAP.md`
5. `../agents/AI_INTEGRATION.md`
6. `../reference/COMPARISON.md`
7. `../architecture/designs/` for MCP-specific feature and tool-surface designs
8. `../archive/retros/` for public-safe feature retros and reusable lessons without project specificity
9. `../archive/reports/2026-05-05_progress_status.md`
10. `../archive/reports/2026-05-05_xuunity_protocol_integration_status.md`
11. this continuation note

For shared protocol integration work:

1. `../../../../Modules/XUUnity/knowledge/validation_lanes.md`
2. `../../../../Modules/XUUnity/tasks/start_session.md`
3. `../../../../Modules/XUUnity/tasks/validation_plan.md`
4. `../../../../Modules/XUUnity/skills/tests/unity_test_runner_workflow.md`
5. `../../../AI_PROTOCOL_HANDBOOK.md`

## What Is Already Proven

- the service can connect to a real Unity project
- compile can run for explicit targets without switching active platform
- edit-mode tests can run through the bridge
- play mode can be entered and exited
- Game View can be configured and captured
- scenario runs can persist results
- second-wave scenario steps can run and report structured results
- startup helpers can fail fast on interactive compile blockers and package-resolution failures
- host-opened editor sessions can be restored to the original closed state after validation
- baseline smoke orchestration can be reused from this public repo's templates while keeping consumer-specific fixtures host-local
- lifecycle-reset ambiguity can now be resolved from the request journal without manual raw journal digging
- the reusable post-change validation route now runs a compile preflight before
  opening Unity, then skips the duplicate bridge compile matrix when that
  preflight already proved the build-config matrix
- the public operator contract now prefers summary-first recovery over repeated
  raw result polling when compact surfaces exist
- host-opened editor closeout is now expected to distinguish quit acknowledgement
  from verified process exit instead of treating `unity.editor.quit` success as
  sufficient shutdown proof
- a prefab can be brought to artifact-backed visual parity through the isolated
  render lane alone, and the surface refuses to call that acceptance while fixture
  and interaction evidence are absent

## Compile Warning Evidence

The `v0.3.70` direct and matrix compile results preserve warnings without
changing the error-only compile verdict:

- `warning_count` counts every callback occurrence.
- `unique_warning_count` deduplicates file, line, code, and message identity.
- `warnings` retains a deterministic sample of at most 20 rows with
  file/line/code/severity/message fields.
- `warnings_truncated: true` means the aggregate counts are complete but the
  diagnostic sample is not; inspect the full artifact or Unity log for the
  omitted rows.

Compact bridge, batch, and multi-project summaries carry these fields forward.
Do not read `status: passed` as warning-free, and do not read a zero warning
count as proof that assemblies rebuilt rather than hitting cache. Current
source carries `rebuilt_assembly_count`, `cached_assembly_count`,
`rebuild_evidence_status`, and `rebuild_evidence_basis` through direct, matrix,
batch, and multi-project summaries; require `measured` evidence when the result
must prove a recent source edit was compiled.

## Structural Compile Errors

Unity can stop before `csc.exe` runs when an assembly definition has duplicate
or unresolved references, invalid JSON, or another structural refusal. These
errors do not use the `error CS...` form, and the in-memory compilation callback
can still contain older C# rows.

Refresh, compile, and direct-test post-settle envelopes scan only the current
bridge-generation scope of the editor-reported `Editor.log`. A matching error is
promoted ahead of secondary compiler rows with:

- `post_settle_compile_failure_class: assembly_definition_error`
- a typed row such as `asmdef_duplicate_reference`
- `post_settle_structural_diagnostics_scope.trust_class: session_scoped`
- `post_settle_compile_recommended_next_action:
  inspect_asmdef_references_and_editor_log_before_cache_cleanup`

If the bridge-generation anchor is unavailable or unusable, the wrapper refuses
to promote the unscoped tail. If Unity reports compilation failure but neither
the current log scope nor the compilation callback supplies a diagnostic, the
envelope reports `compiler_diagnostics_unavailable`; it does not invent a root
cause.

Never delete `Library/ScriptAssemblies` or `Library/Bee` as a first response to
a compile error. Inspect the typed diagnostic and session-scoped `Editor.log`,
then fix the `.asmdef` or source error. Cache deletion is a heavyweight rebuild,
not a diagnosis.

## UI Acceptance Handoff Rule

A `visual`-only pass is a handoff state, not reference acceptance. Read the
verdict fields, not the similarity scalar:

- `decision_ready: false` with `decision_readiness_gaps` means the comparison ran
  and its conclusion is not yet decision-grade. A high similarity score plus a
  passing vision review does not buy acceptance while
  `fixture_evidence_absent` or a blocked lane is listed.
- `self_reviewed_only: true` on the vision lane means the agent that authored the
  UI also judged it. That review is stored, never counted as independent proof;
  closeout needs a different judge or a human.
- `pending_lanes: ["interaction"]` on an isolated-render capture is structural: a
  guarded click needs Play mode, so it needs a project scenario emitting a
  `ui_fixture` block. Report it as an open lane rather than lowering the
  reference's acceptance policy to make the verdict green.
- A comparison that ran returns a successful envelope even when
  `reference_acceptance` is `failed`. Do not read the transport envelope as the
  verdict; read `reference_acceptance`, `failed_lanes`, `blocked_lanes`,
  `pending_lanes`, and `decision_ready`.

When handing off mid-parity work, state which lanes carry evidence, which are
structurally open, and what each open lane needs — not an overall percentage.

Editing package sources under a `file:` dependency needs one explicit
`unity_project_refresh` before the next test run picks them up; a test run alone
can execute the previously compiled assemblies and report a stale verdict.
Typed project actions now enforce this boundary themselves: stale editor-domain
currency blocks the hook, and asset-reading actions marked
`requiresFreshAssets: true` receive an automatic refresh before the shared
currency gate.

## What Is Not Yet Proven

- broad multi-client production use
- stable behavior across a wider Unity version matrix
- device automation
- profiler export and analysis
- runtime bottleneck evidence
- resumable long-running automation
- richer scenario assertions beyond the current core

## Current Risk Areas

- stdio layer still needs hardening
- Game View support still depends on reflection
- deeper project inspection surface is still thin
- no runtime evidence pipeline yet
- no device-side artifact capture yet

## Recommended Next Work

1. harden lifecycle and transport proof:
   - lifecycle fault injection
   - bridge churn recovery proof
   - clearer cancellation and stale-request hygiene
   - explicit closeout truth for host-opened editor sessions
2. add scenario-result utilities:
   - last-result fetch
   - result listing
   - artifact path surfacing
3. harden the scenario lane:
   - richer assertions
   - better result summaries
   - clearer failure taxonomy
4. add first runtime evidence adapters:
   - runtime markers
   - frame or state checkpoints
   - controlled project hook outputs
5. design the device layer on top of scenario control:
   - launch
   - screenshot
   - profiler capture
6. broaden proof across more client and host combinations
7. only then move toward autonomous performance and bottleneck workflows

## Important Non-Goals For The Next Chat

Do not spend time re-evaluating:
- heavy third-party Unity MCP backends as the primary solution
- runtime-in-player MCP packaging
- broad reflection-driven dynamic code execution as the default extension model

Those questions are already settled enough for the current phase.
