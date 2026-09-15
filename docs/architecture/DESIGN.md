# XUUnity Light Unity MCP Design

Date: `2026-05-09`
Status: `active public design`

## Goal

Build a small Unity MCP service for `xuunity` with:
- editor-only footprint
- zero player-build impact by default
- no project settings mutation
- easy install and removal
- stable validation-focused operations
- support for more than one MCP client

## Service Shape

The service has two parts:

1. local stdio MCP server
2. embedded Unity editor-only bridge package

Transport between them:
- file IPC under `<Project>/Library/XUUnityLightMcp/`

No runtime/player package is part of the base service.

Current transport shape:
- per-project routing now goes through an in-memory registry layer keyed by normalized `projectRoot`
- transport selection is maintained per project instead of as a single global host assumption
- host wrapper now uses an internal transport adapter layer
- `tcp_loopback` on `127.0.0.1` is the default same-host transport for new project setup
- each TCP response is one compact newline-delimited JSON frame; the host
  accepts a complete JSON value immediately and does not require socket EOF as
  the response boundary
- `file_ipc` remains the fallback and explicit compatibility transport
- a TCP request may recover its matching file outbox response when the socket
  channel disappears after Unity processing
- lifecycle orchestration is no longer hard-wired directly to inbox/outbox paths
- this choice is intentionally cross-platform for macOS, Windows, and Linux; the design avoids Unix-domain-socket-only assumptions

## Current Architecture Baseline

The current public baseline is no longer a single flat wrapper around one
project.

The host side now has an explicit per-project routing layer with:

- `BridgeRegistry`
- `ProjectContext`
- normalized `projectRoot` instance keys
- per-project mutation locking
- per-project transport metadata and transport selection
- explicit stale-context pruning

Discovery is now a first-class routing phase instead of an ad hoc side effect of
reading one state file.

Current discovery inputs:

- bridge state
- host editor session state
- process-table verification for the target Unity project
- bridge-writer process class and editor-log identity
- bridge-enabled project config state

Current discovery outputs:

- `discovery_classification`
- `authoritative_state_source`
- `reconciliation_case`
- `reconciliation_status`
- `reconciliation_recommended_next_action`
- `bridge_process_class`
- `bridge_state_writer_trust_class`
- `runtime_execution_allowed`

Current health outputs:

- `host_health_classification`
- `host_health_reason`
- `host_health_recommended_next_action`
- `host_health_termination_policy`
- `anr_classification`
- compact editor-log diagnosis when health is stale or degraded

Current public structured state grouping now includes:

- `transport_state`
- `state_groups.bridge_identity`
- `state_groups.process_identity`
- `state_groups.transport`
- `state_groups.health`
- `state_groups.editor_state`
- `state_groups.lifecycle_flags`

Flat compatibility keys are still preserved for existing clients and scripts.

## Lifecycle Contract

The wrapper is responsible for the host-local lifecycle gaps that the Unity package alone cannot close.

Current design intent:
- use `bridge-state` and `unity.status` as readiness evidence, not only request transport
- classify stale bridge state with a dead `editor_pid` as offline
- prefer reusing a healthy editor session before forcing a new editor launch
- avoid launching a second Unity instance when the project is already open without a reusable bridge
- distinguish a real Unity editor process from launcher-only helper processes such as Unity Hub
- refuse bridge startup inside Unity Asset Import Workers before any session,
  transport, heartbeat, or journal file is created
- fail closed with `bridge_owned_by_non_main_process` when a legacy state file
  is attributed to a worker or another live non-main process; compiler booleans,
  counts, and diagnostics from that state are unknown rather than green
- fail fast when a launch command completes but no matching editor process appears for the target project
- surface editor busy reasons explicitly
- open or reuse Unity before interactive operations, but do not steal native OS
  focus as a default remediation
- wait for editor idle before and after lifecycle-sensitive synchronous operations
- distinguish request acceptance from settled editor completion
- carry bridge session identity and generation in state
- persist a lightweight request journal for reconnect and timeout evidence
- restore the original closed state when the host opened Unity only for validation

This keeps the lightweight lane closer to Rider-style behavior without depending on Rider runtime internals.

## Editor-Truth Evidence Boundary

Editor residency, player-loop progress, and Game View pixels are different
facts. A fresh bridge heartbeat proves that the editor process is responsive;
it does not prove that Play Mode advanced a frame. Likewise, `Screen.width` and
`Screen.height` describe Unity's current Screen surface, but the Editor Game
View can capture a render texture with different dimensions.

Operations that make a decision from a running frame therefore sample
liveness at the point of use. UI tree/query/click results, Game View
screenshots, and persisted scenario-step results carry the play-mode state,
frame sample, editor focus, `playmode_loop_liveness`, warning/remediation, and
`result_trust_class`. `throttled` maps to `playmode_throttled`; a playing state
without sufficient samples maps to `playmode_liveness_unproven`. Neither is
equivalent to runtime proof even when transport and editor health are green.
A playing state with no sample yet is not throttled: its remediation is to wait
for the next liveness sample, not to focus the editor. The complete value set
for every trust, warning, outcome and gap field is one table in
`docs/reference/GLOSSARY.md`.

Background execution is opt-in and reversible. In the editor
`Application.runInBackground` is backed by `PlayerSettings.runInBackground`, so
assigning it writes a project setting that can be serialized into the
consumer's `ProjectSettings.asset`. The bridge therefore applies it only when
`background_execution_enabled: true` is set in the project's bridge config, and
only once per domain rather than per tick. The pre-existing value is captured in
`SessionState` and restored when the bridge is disabled or the editor quits, and
`background_execution_mode` reports `managed` or `project_owned`. Enabling it
reduces focus dependence but is not a liveness verdict; native autofocus stays
disabled and point-of-use frame advancement remains authoritative.

Screenshot and UI-read evidence also separates:

- `render_width` / `render_height`: dimensions of the existing Game View render
  target (and therefore the captured screenshot when capture succeeds)
- `screen_width` / `screen_height`: the contemporaneous Unity `Screen.*`
  values used by runtime layout APIs
- `render_target_available`: whether an existing render texture could be
  inspected without opening or mutating a Game View
- `render_target_differs_from_screen`: an explicit mismatch verdict

An unavailable render target is reported as unavailable, not inferred from
`Screen.*`. A mismatch is valid evidence about two surfaces, not an invitation
to relabel one as the other. This boundary prevents a semantically correct UI
tree from being combined with pixels rendered at an unstated resolution.

## Portfolio Reporting Contract

Per-project request artifacts remain the source of truth. For test runs, the
persisted `state/test_results/<request_id>.json` file owns the final counts,
failure list, lifecycle churn flag, and request id for that Unity request.

Portfolio aggregate artifacts are operator-facing verdicts. They should make a
multi-project run cheap to read and quote, but they must point back to the
per-project request/result artifacts rather than replacing them. Aggregate
summaries are responsible for:

- separating MCP operation success from Unity test-suite pass/fail status
- grouping repeated first-failure classes across projects
- reporting editor restore or closeout status
- summarizing package manifest/package-lock alignment when package source is
  part of the validation claim
- summarizing workspace side effects without mutating or cleaning files

Compile eligibility must be normalized once from the authoritative matrix
evidence and then shared by the aggregate and any follow-up test selector.
Valid GUI fallback evidence is not a second-class pass. The public target
shape, legacy-result compatibility rules, selection fail-closed behavior,
license freshness policy, and launcher-diagnostics boundary are specified in
[`XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md`](designs/XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md).

Current public bridge-state baseline includes:

- `bridge_session_id`
- `bridge_generation`
- `bridge_bootstrap_attached`
- `domain_reload_in_progress`
- `asset_import_in_progress`
- `package_operation_in_progress`
- `package_operation_name`
- `script_reload_pending`
- `request_journal_directory`
- `request_journal_head`
- `refresh_settle_pending`
- `refresh_settle_request_id`
- `refresh_settle_started_utc`
- `refresh_settle_completed_utc`
- `refresh_settle_phase`
- `refresh_settle_package_resolve_requested`
- `compile_settle_pending`
- `compile_settle_request_id`
- `compile_settle_started_utc`
- `compile_settle_completed_utc`
- `compile_settle_phase`
- `compile_settle_operation`
- `package_operation_phase`
- `playmode_transition_pending`
- `playmode_transition_request_id`
- `playmode_transition_action`
- `playmode_transition_target_state`
- `playmode_transition_started_utc`
- `playmode_transition_completed_utc`
- `playmode_transition_phase`

Current request journal baseline includes:

- `bridge_bootstrap_attached`
- `request_started`
- `request_completed`
- `request_abandoned`
- `request_reclassified`

Every host process stamps a stable `client_session_id` and a `client_kind`
(`mcp_server` or `cli`) into the requests it submits, and publishes its
`client_session_id` to child host processes so a delegated CLI request stays
own work. Unity preserves the id across domain reloads and writes it, plus the
real editor PID, on lifecycle journal events. Compact status counts own,
foreign, CLI, and unattributed submissions since the current client process
started.

`foreign_request_activity_detected` is the alarm. It means a client session
other than this one, and not a CLI process, submitted requests to this editor,
so mutating work should pause until that session is identified. It does not
mean the operator ran the wrapper CLI or a smoke suite against their own
editor: those submissions are counted in `cli_requests_since_client_start`
with `last_cli_request_at_utc`, and are informational. Two cases the alarm
cannot see: a request written straight into the file-IPC inbox, which produces
no host journal event at all, and a second client that drives the editor only
through the wrapper CLI, which is indistinguishable from the operator doing
the same; such a client re-arms the alarm by exporting
`XUUNITY_CLIENT_KIND=mcp_server`. A row written by a host older than the
`client_kind` field carries no kind and stays in the alarm bucket, so version
skew never silences it.

This is intentionally a first protocol layer, not the final reconnect model.

Licensing IPC provenance is host-owned and fail-closed. Candidate discovery is
read-only and platform-native, accepts only live Unity licensing clients whose
current parent is Unity Hub, and auto-selects only when the candidate count is
exactly one. Public payloads carry fingerprints and validation classes, never
raw named-pipe values. Helper cleanup records only licensing clients that were
absent before launch and whose original ancestry contains the helper-owned
editor; it revalidates exact process identity before single-PID termination and
never treats the shared Hub client as helper-owned.

Wrapper compact output is a terminal protocol, not a footer. It suppresses the
child payload and stderr, emits one JSON envelope with an 8192-byte ceiling,
and retains only decision fields plus artifact pointers. Full evidence remains
an explicit opt-in.

UI click delivery and click effectiveness are separate facts. `delivered=true`
means the event reached the target; `effective=true` requires an observable
semantic state change. A delivered no-op returns
`status=delivered_no_observable_effect`, `success=false`, and remediation for
raycast, log, or project-hook verification.
The scenario step adds an `expectStateChange` opt-out the direct tool does not
have; a waived inert click passes with outcome `delivered_no_observable_effect`
and is surfaced as `ui_interaction_summary` on the scenario step summary, so a
passing scenario never reads as a proven user path on its own.

Known current weakness:

- an already-open Unity session may not hot-pick up external file-package source edits reliably through `AssetDatabase.Refresh()` plus `Client.Resolve()` alone
- in current live evidence, pickup required a real recompilation/rebootstrap cycle before the new package code became active
- editor reopen is not always required, but plain refresh/resolve is still too weak as the only update path

Current reconnect policy:

- the host classifies a request as `request_lifecycle_reset` when bridge generation/session changes before a response is observed
- after lifecycle reset, the host resolves final disposition by `request_id` from the request journal before returning the final operator-facing error
- lifecycle-reset output now separates:
  - `transport_outcome`
  - `operation_outcome`
  - `terminal_disposition`
  - host delivery observed/unproven state
  - `recommended_next_action`
- lifecycle-reset recovery now also classifies `result_trust_class` so the
  operator can distinguish:
  - Unity completed and the host has proof
  - Unity completed across lifecycle churn
  - wrapper/session failed after Unity accepted the request, leaving the Unity
    result unproven
- a completed PlayMode request dominates an earlier `request_abandoned` event;
  when the fresh post-reload bridge is healthy, idle, in Edit Mode, and has zero
  compiler errors, the terminal owner is
  `confirmed_success_after_lifecycle_churn` and retry is false
- compact operator recovery is the default through
  `request-final-status <request_id>` and `request-latest-status`; CLI callers
  can request complete evidence with `--include-full-payload`
- tracked requests that have a Unity `request_completed` journal event but no
  host delivery receipt preserve their confirmed operation result and report
  `terminal_disposition=unity_completed_host_delivery_unproven`; their safe
  action is `continue_without_retry`, not replay
- the MCP `unity_request_final_status` tool returns the compact decision fields
  by default and accepts `includeFullPayload=true` for the complete journal and
  artifact evidence
- delivery remains `host_delivery_pending` while the original tracked request
  is still inside its timeout; it becomes unproven only after the deadline or
  an explicit response-channel loss event
- explicitly idempotent operations can be retried once automatically
- non-idempotent operations stay fail-fast and surface the lifecycle-reset evidence instead of retrying blindly
- deferred async operations now retain active-request ownership until their completion callback, which makes `request_abandoned` reachable during real in-flight reloads instead of only in theory
- host lifecycle output now records transport metadata for each request attempt
- mixed-mode response routing is allowed: when `tcp_loopback` is active, direct socket-backed requests use the live connection, while file-IPC requests can still be served as fallback through the same bridge

Current multi-project lifecycle baseline:

- same-project mutating operations are serialized through `ProjectContext.request_lock`
- different project roots can proceed independently
- process-table project ownership is matched by exact parsed `-projectPath`
- process-table matches are split between main editor processes and
  worker/helper processes; worker-only visibility does not count as a live
  editor
- `bridge_bootstrap_attached` journal events identify their writer by process
  id, process class, and editor-log path; the current package never emits this
  event from an Asset Import Worker
- host editor opening fails closed when process visibility is unavailable, so
  the wrapper does not call `open -na` without proving same-project absence
- the host can classify and recover:
  - `same_project_editor_running_bridge_not_ready`
  - `stale_bridge_state`
  - `stale_host_session`
  - `bridge_disabled`
  - `bridge_owned_by_non_main_process`
  - `editor_process_alive_bridge_never_attached`
  - `launch_blocked_probable_modal`, with the live editor PID, Editor.log path,
    log idle time, and the last matched licensing/API-updater/dialog line
- reconciliation is used not only for diagnostics but also for recovery decisions in:
  - `ensure-ready`
  - direct bridge invocation retry
  - scenario wait/result paths

Current native settle-watcher start:

- `unity.project.refresh` now starts a Unity-side settle tracker
- settle completion is based on package/import/script/update state observed inside Unity
- host still waits for idle as a guard, but successful refreshes can now report `completion_basis: unity_refresh_settle_watcher`
- `unity.compile.player_scripts` and `unity.compile.matrix` now start a Unity-side compile settle tracker
- successful compile payloads can now report `completion_basis: unity_compile_settle_watcher`
- nested scenario `compile_player_scripts` steps use the same compile settle watcher instead of treating synchronous API return as final completion
- `unity.playmode.set` now starts a Unity-side playmode transition watcher
- successful playmode payloads can now report `completion_basis: unity_playmode_transition_watcher`
- pending playmode transition state persists through bridge rebootstrap so `enter` can still complete on the native watcher path after Play Mode recreates the bridge session
- `unity.editor.quit` is now part of the core bridge surface so the host can close a host-opened editor session without GUI automation
- `open-editor` accepts ordered, repeatable extra Unity arguments and records
  them in the host launch session; this supports host-required licensing IPC,
  cache-server, and API-updater arguments without shell-string parsing. An
  existing editor is reused with requested arguments only when its process
  command proves them; later successful licensing evidence supersedes earlier
  transient channel errors in the same log
- `request-editor-quit --force-after-ms` is an explicit escalation only: after
  the graceful wait it requires one current same-project editor PID, rechecks
  identity, terminates that PID, and verifies exit
- direct PlayMode test requests still have a stricter trust boundary than
  compile or refresh under lifecycle churn: bridge generation can change after
  request acceptance and before response commit, so a PlayMode retry may end
  with `wrapper_failed_unity_unproven` instead of a clean pass/fail result

## Stable Surface

Core validation operations:
- `unity.status`
- `unity.capabilities.get`
- `unity.health.probe`
- `unity.console.tail`
- `unity.scene.snapshot`
- `unity.tests.run_editmode`
- `unity.compile.player_scripts`
- `unity.compile.matrix`
- `unity.editor.quit`

Validated editor-control additions:
- `unity.playmode.state`
- `unity.playmode.set`
- `unity.game_view.configure`
- `unity.game_view.screenshot`

Compact operator and diagnostic surfaces:

- `request-status-summary`
- `request-final-status`
- `request-latest-status`
- `request-scenario-result-summary`
- `project-discovery-report`
- `registry-context-report`
- `registry-prune-contexts`

## Prefab Mutation Contract

`unity.prefab.mutate` is a typed transaction over the Editor API. Three properties
of that contract are not inferable from the schema and have each cost a real
session, so they are recorded here.

**Enum properties are index-addressed.** `SerializedProperty` exposes an enum
through `enumValueIndex`, the ordinal position in `enumNames`, while a caller
naturally supplies the enum's underlying value — for a TMP font weight, `700` for
Bold rather than the index. Unity clamps or discards out-of-range input silently,
so the natural call produced a `status: "applied"` receipt for a write that changed
nothing. The contract is therefore: `numberValue` on an enum is the member index
and out-of-range input is refused as `prefab_mutation_enum_value_invalid` naming
the valid `name=index` pairs; `stringValue` sets the member by name; and the
receipt's `before`/`after` name the member, so the emitted inverse patch is
replayable through `stringValue`.

**A write that changed nothing is `no_op`, not `applied`.** Every other guardrail
on this surface — `expectedSha256`, atomic rollback, `post_validation`,
`reversible_patch_json` — presumes the change report is truthful, so a
false-positive receipt defeats all of them at once. Value-setting operations
compare the serialized value after the write and report `no_op` when it is
unchanged; the transaction still succeeds, and `no_op_count` carries the total.

**The object-reference policy is split by what the reference points at.** Asset
references (`Sprite`, `Material`, `TMP_FontAsset`, meshes, ScriptableObjects) are
writable, addressed by project path or GUID, with an optional sub-asset name for a
sliced sprite. Component and `GameObject` references stay refused, because that is
the case where a write could swap a component for another type. The earlier blanket
refusal of all object references was the only remaining reason to hand-edit prefab
YAML, and the ordering hazard that came with it — an Editor-API write silently
overwriting an out-of-band edit from the editor's stale in-memory copy.

That hazard is guarded by the caller's `expectedSha256`, deliberately rather than
by inference: from inside the editor, a file rewritten by an external tool and a
file Unity itself reimported are indistinguishable, so an inferred drift check
refuses legitimate writes. A mismatched precondition fails as
`prefab_mutation_asset_drifted` naming `unity_project_refresh`; a transaction
without a precondition reports `drift_guard: "unguarded"` instead of implying the
check ran.

## Isolated Render Contract

`unity.prefab.render` persists the `ui.read.v1` snapshot it rendered beside the
capture and returns `snapshot_path`, because `unity_ui_reference_compare` consumes
a snapshot by path. While the snapshot was returned inline only, a reference
declaring `acceptance.semantic: "required"` was structurally unsatisfiable outside
Play mode and reported `not_evaluated / no_ui_snapshot_supplied` forever. The
inline copy is retained behind `includeSnapshot`, defaulting to off.

`overrides` takes the same typed operation list as the mutation surface and applies
it to the preview-scene instance only. A UI state that runtime code applies — a
second popup state, an active nav button — is therefore capturable without touching
an asset that other projects share. A failing override fails the render rather than
returning a capture of the un-overridden state, since that capture would be
evidence for the wrong state.

## Compile Validation

Compile validation uses Unity:
- `PlayerBuildInterface.CompilePlayerScripts`
- explicit `ScriptCompilationSettings`
- per-request `BuildTarget`
- per-request `ScriptCompilationOptions`
- per-request `extraScriptingDefines`

This enables:
- target-specific compile checks
- define-specific compile checks
- development-build compile checks

Without:
- switching active build target
- mutating project-wide scripting define symbols

Constraint:
- the corresponding Unity platform support module must be installed on the host editor

Gating boundary (compile-red fail-fast):
- the host-side compile gate covers direct one-shot operations only:
  `unity.tests.run_editmode`, `unity.tests.run_playmode`, and
  `unity.playmode.set` with `action=enter`
- the gate must never cover `unity.playmode.set` with `action=exit` (or
  `pause`/`resume`): when the editor is in Play Mode, Unity defers the script
  reload, so exiting Play Mode is exactly the remediation that clears a broken
  compile state — gating it creates an out-of-band deadlock
- `unity.scenario.run` is deliberately ungated at dispatch: scenarios are
  ordered remediation flows (playmode exit, refresh, compile), and step-level
  gates own correctness inside the editor — scenario test steps refuse with
  `compile_broken` editor-side, and Unity natively refuses Play Mode entry
  while compilation is broken
- the direct tool and the scenario step for the same operation must agree on
  gating, or the divergence must be recorded here as deliberate

### Diagnostics Have an Age

Compiler diagnostics describe the compilation inputs captured at
`compiler_diagnostics_captured_utc`, with
`compiler_diagnostics_bridge_generation` identifying their bridge domain.
The timestamp belongs to the compilation cycle, not each heartbeat. Diagnostics
from another generation, with unknown capture metadata, or naming a file changed
since capture are `stale`; they are not a current compile verdict.

Before a compile-gated operation, stale pipeline diagnostics trigger one
`unity.project.refresh` through the existing lifecycle path, inside the same
project request lock. Only a confirmed, passed post-settle verdict admits the
original request. A confirmed failed verdict yields `compile_broken`; a missing
or deferred verdict yields `compile_verdict_unavailable`. Recovery does not
re-enter the public lock or repeat a refresh loop. Play Mode exit remains ungated.

Host compile/idle refusals write `request_refused` with their error, recovery
command and state fingerprint. They are not submitted requests. Unity completion
events retain `operation_status` and also carry the error `reason` and, for test
runs, `test_verdict`; transport success alone is not a passing test verdict.

## Capability Probe Model

Version-sensitive operations are not trusted by default.

On the first enabled editor session for a given:
- project
- Unity version

the bridge runs a lightweight capability probe and persists:

- `Library/XUUnityLightMcp/state/capabilities_report.json`

The report stores:
- `probe_version`
- `unity_version`
- `adapter_id` per capability
- `supported_operations`
- `disabled_operations`
- structured capability records

Risky operations are gated by this report before execution.

## Versioned Adapter Strategy

Some capabilities must be treated as adapters, not permanent assumptions.

Current example:
- `game_view_reflection_v1`

Design rule:
- every version-sensitive capability should expose an `adapter_id`
- health probe decides whether that adapter is supported
- unsupported adapters disable their operations cleanly
- Unity Editor API differences should be guarded with Unity built-in version
  symbols such as `UNITY_2022_3_OR_NEWER` when the boundary is known; otherwise
  use narrow reflection/fallback helpers that compile on Unity 2021.3+

Future path:
- add Unity-version-specific adapters only where probe evidence shows real divergence
- prefer public Unity APIs when Unity exposes them

## UI Target Resolution Scope

`unity.ui.*` resolves a set of *roots* from a scene scope, then applies the selector inside those roots. The scope
is derived, never implicit:

| `targetKind` | `sceneName` | Searched scope |
| --- | --- | --- |
| `active_scene` (default) | empty | the active scene only |
| `all_loaded_scenes` | empty | every loaded scene, plus the `DontDestroyOnLoad` scene |
| any | set | the one loaded scene matching that name or path |

`active_scene` is the wrong scope in the common shipping shape: a bootstrap scene stays active, screens load
additively, and shared overlays live under `DontDestroyOnLoad`. Use `all_loaded_scenes` with a selector to reach
them — `targetKind` chooses the roots, the selector does the matching.

The `DontDestroyOnLoad` scene has no enumeration API. It is resolved by creating one hidden GameObject, calling
`Object.DontDestroyOnLoad` on it, reading `probe.scene`, and destroying it immediately. That only works in Play
Mode, so a UI read is never strictly side-effect-free once `includeDontDestroyOnLoad` is on (default `true`). Every
read reports which way it went:

- `target.scene_scope` — `active_scene` | `all_loaded_scenes` | `named_scene`
- `target.searched_scenes` / `target.loaded_scenes`
- `target.dont_destroy_on_load_included` and `target.dont_destroy_on_load_status`
  (`included` | `not_requested` | `out_of_scope_for_target_kind` |
  `edit_mode_no_dont_destroy_on_load_scene` | `probe_failed`).
  `out_of_scope_for_target_kind` is the case that reads oddly at first: the scene was discovered and appears in
  `loaded_scenes`, but the chosen `targetKind` did not search it, so `dont_destroy_on_load_included` is false
- per node, `scene_name`

### The `ui_target_out_of_scope` contract

"Not found" and "not reachable" are different answers and must never share a code:

- `ui_target_not_found` — the object exists in no loaded scene.
- `ui_target_out_of_scope` — the object exists, in a loaded scene the current scope did not search. The detail
  names the owning scene, the searched scenes, the loaded scenes, and the exact retry
  (`targetKind=all_loaded_scenes`, or `sceneName=<owner>`).

`unity.ui.click` refuses on `ui_target_out_of_scope` rather than reporting a missing node, and re-resolves its
target from the `Transform` the tree walk matched. It must not re-resolve by path: `GameObject.Find` cannot address
every object the widened scope reaches, and it silently picks the first same-named object across scenes.

## Game View Policy

`unity.game_view.configure` is intentionally conservative:

- by default it does not create a new custom size
- if the requested size is missing, it fails explicitly
- persistent editor user-state change requires:
  - `allowCreateCustomSize=true`

This keeps reflective editor-state mutation opt-in.

## Extension Model

Two extension axes are intended:

1. Unity operation adapters
2. MCP client config adapters

Unity adapters should stay narrow and explicit.
Client adapters live under:

- `templates/clients/codex/`
- `templates/clients/claude-code/`
- `templates/clients/cursor/`
- `templates/clients/generic/`

## Current Proof Baseline

The public reusable proof layer now includes:

- transport matrix smoke
- lifecycle fault-injection smoke
- request-abandoned smoke
- playmode settled-state regression smoke
- playmode verdict recovery proof smoke
- multi-project acceptance smoke
- divergence/reconciliation smoke
- health-policy smoke

These runners live under:

- `templates/smoke/`

The current public design position is:

- Phase 1 registry/context extraction is implemented
- Phase 2 discovery and reconciliation formalization is implemented
- Phase 3 host health and ANR classification scaffold is implemented
- Phase 4 schema and transport hardening is implemented
- flat compatibility remains intentionally preserved while the structured state
  contract matures
