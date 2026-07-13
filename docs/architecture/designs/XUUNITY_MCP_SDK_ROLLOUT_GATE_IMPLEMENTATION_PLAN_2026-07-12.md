# XUUnity MCP SDK Rollout Gate — Implementation Plan

Date: `2026-07-12`
Status: `P0.1 Git-tracked generated-diff vertical slice implemented in unreleased source; broader plan remains open; hardened after adversarial review (§14)`
Baseline: released source line `v0.3.44`
Elaborates: `XUUNITY_MCP_SDK_ROLLOUT_VALIDATION_DESIGN_2026-05-14.md` (direction) —
this document turns that direction into a build-ready plan with exact
registration seams, contracts, reuse targets, phasing, and validation.
Scope: public-safe reusable MCP surface only. Project-specific resolve/build
wiring lives in host-local project hooks, not in this public plan.

## 1. Goal

Make a third-party SDK update (ad / attribution / analytics / consent packages
and their EDM4U-managed native dependencies) a **repeatable, evidence-backed,
suspicious-diff-aware gate** instead of a manual, per-project, trust-the-menu
operation. The gate must catch the two failure classes that today pass every
existing check:

- **stale resolution** — the resolver reported success but the generated Android
  outputs still carry the previous native dependency version;
- **generated-file damage** — the new dependency is present (so
  `unity.sdk.dependency.verify` passes) but the resolver silently removed a
  signing block, a Maven repository, a manifest placeholder, or an NDK pin.

Compile-green and dependency-present are both insufficient. The gate adds the
missing proofs while staying inside the current same-host editor lane for its P0
layer, and isolates device/native depth into opt-in layers.

## 2. Problem, grounded in the current surface

Verified against `v0.3.44` source:

- `unity.edm4u.resolve` (`XUUnityLightMcpEdm4uResolveOperation`) only calls
  `EditorApplication.ExecuteMenuItem(...)` over the Android Resolver menu
  candidates and returns `outcome="resolve_requested"`. It does **not** read
  `EditorUserBuildSettings.activeBuildTarget`, does **not** require
  `BuildTarget.Android`, and does **not** verify generated-output freshness. Its
  only "settle" is editor-idle (`XUUnityLightMcpRefreshSettleRuntime.PollLocked`
  → 2 stable idle ticks), which can report `settled` even if EDM4U wrote nothing.
- `unity.sdk.dependency.verify` (`XUUnityLightMcpSdkDependencyVerifyOperation`)
  is a **presence** checker: per-expectation `file_contains` / `file_regex` /
  `android_resolver_package` / `gradle_dependency` / `gradle_repository` /
  `podfile_lock_pod` substring/regex matching. It computes a per-file `sha256`
  and sandboxes paths with `TryResolveProjectFile`, but has no baseline diff, no
  removal detection, and no change classification.
- Compile proof exists (`unity.compile.matrix`,
  `unity_compile_build_config_matrix`) and now carries lane-agnostic
  `compile_evidence` (from `VALIDATION_VERDICT_COHERENCE`, `v0.3.44`).

So the smallest honest gate needs exactly three new capabilities on top of what
exists: **detect stale resolution**, **detect destructive generated-file
change**, and **run both safely at portfolio scale without an editor stampede**.

## 3. Architecture decision

Four layers, reuse-first, no new service / transport / runtime package:

1. **Reusable MCP-core operations (public, in `com.xuunity.light-mcp`)** — the
   generic, project-agnostic proofs:
   - `unity.sdk.android_resolve` — typed resolver with active-target enforcement
     and generated-output freshness waiting.
   - `unity.sdk.generated_diff_guard` — baseline-diff + change classification.
   - `unity.sdk.package_restore` — closed-editor package settle with recorded
     package-cache evidence.
2. **Project-owned hooks (host-local, not public)** — any project-specific
   resolve/build/config wiring is authored as a catalog-backed `project_action`
   / `project_defined_hook_poll_until` scenario hook implementing
   `IXUUnityLightMcpScenarioHook`, following the existing project build-hook
   pattern. No package edits for project specifics.
3. **Host lanes (Python)** — `batch-edm4u-resolve` (closed-editor batch),
   `sdk-generated-diff-guard`, `sdk-validate` (portfolio orchestrator), each
   compact-by-default with `includeFullPayload` opt-in, integrating with the
   existing batch runner + license-aware fallback + `compile_evidence`.
4. **GUI editor process pool (Python)** — admission control wrapping
   `open_unity_editor`, so broad SDK validation cannot open an unbounded number
   of GUI editors or double-open a project.

The whole gate is then composed as **one reusable scenario**:
`package_restore → switch Android → android_resolve (freshness) →
generated_diff_guard → compile matrix → dependency.verify`, runnable per project
and fanned out across the portfolio.

Capability gating is mandatory: every new op is added to
`XUUnityLightMcpCapabilityRegistry.OperationCapabilities` (not only
`UngatedOperations`) so it degrades to a typed `operation_unavailable` when
EDM4U / the Android module / `adb` are absent — never silently "passes".

## 4. Reuse map (do not reinvent)

| Need | Reuse | Location |
| --- | --- | --- |
| Project-root sandbox + per-file sha256 | `TryResolveProjectFile`, `ComputeSha256` | promote from `XUUnityLightMcpSdkDependencyVerifyOperation` into a shared `XUUnityLightMcpSdkPaths` / `XUUnityLightMcpSdkHash` static helper |
| Menu firing + attempt log | `ExecuteMenuItem` loop, `XUUnityLightMcpMenuItemAttempt`, `AndroidForceResolveMenuCandidates` | `XUUnityLightMcpEdm4uResolveOperation` |
| Package/resolve settle tracking | `BridgeRuntimeState.BeginRefreshSettleTracking`, `MarkPackageOperationStarted`, `RefreshSettleRuntime.PollLocked` | `Editor/Bridge/*` |
| Active-target assertion + Android export toggle + busy guard | `SwitchActiveBuildTarget` / `activeBuildTarget` assert, `exportAsGoogleAndroidProject`, `isCompiling`/`isPlaying`/`isUpdating` guard | `XUUnityLightMcpBuildPlayerOperation` |
| Two-phase async settle in a scenario step | `ProcessCompilePlayerScriptsStep` (deadline + 2 stable idle ticks) | `XUUnityLightMcpScenarioCompileTestStepHandlers` |
| Long-running resolve as engine-driven poll | `project_defined_hook_poll_until` | `XUUnityLightMcpScenarioProjectHookStepHandlers`, `XUUnityLightMcpPollUntilStepNormalizer` |
| Evidence store (single JSONL ledger) | `register_artifact`, `write_artifact_report`, `append_artifact_registry_record`, `sha256_file`, `redact_mapping` | `server_artifact_registry.py` |
| Expectation engine for artifact checks | `run_artifact_probe`, `_run_expectation` | `server_artifact_probe.py` |
| Artifact manifest / structured timing enrichment | `build_artifact_manifest`, `attach_operation_evidence_to_payload` | `server_operation_evidence.py`, `server_batch_orchestrator.py:1194` |
| Graceful quit-and-wait + confirmed-PID-only hard-kill | `restore_host_opened_editor_state`, `terminate_editor_pid`, `list_live_project_editor_pids` | `server_editor_host_lifecycle.py` / `_processes.py` |
| Per-project single-flight lock | `write_host_editor_session_state` / `try_read_host_editor_session_state` | `server_editor_host_state.py` |
| Lane-agnostic compile evidence + fail-closed selection | `normalize_compile_evidence`, `BatchSelectionPlan` | `scripts/testing/run_multi_project.py` |
| License-aware batch/GUI fallback | `server_license.py`, `batch-*` lane machinery | `server_batch_lanes.py` |
| Capability degrade DTO | `XUUnityLightMcpCapabilityRecord` (supported/status/reason/dependency/recommended_action) | `XUUnityLightMcpCapabilityAndEditorModels.cs` |

## 5. P0 components

### 5.0 Shared SDK helper module (prerequisite)

Promote the currently-`private static` `TryResolveProjectFile` and
`ComputeSha256` out of `XUUnityLightMcpSdkDependencyVerifyOperation` into an
`internal static` helper (`XUUnityLightMcpSdkPaths` for path sandboxing,
`XUUnityLightMcpSdkHash` for streaming hex sha256). Both the existing verify op
and the new guard/resolve ops consume it. Pure refactor, covered by the existing
dependency-verify EditMode self-tests.

### 5.1 `unity.sdk.generated_diff_guard` — the do-first slice

Highest ROI, smallest surface, builds directly atop `dependency.verify`. Runs
**after** resolve and **before** compile. Baseline, diff mode, and
critical-marker handling are hardened per §14 (git-first baseline,
structure-aware diff, presence-after markers).

**Request (`args_json`, JsonUtility-flat DTO):**

```json
{
  "baselineSource": "git_head",
  "baselineRef": "HEAD",
  "libraryBaselineDir": "Library/XUUnityLightMcp/sdk/baseline/<label>",
  "captureBaseline": false,
  "trackedPaths": [
    "ProjectSettings/AndroidResolverDependencies.xml",
    "Assets/Plugins/Android/mainTemplate.gradle",
    "Assets/Plugins/Android/settingsTemplate.gradle",
    "Assets/Plugins/Android/gradleTemplate.properties",
    "Assets/Plugins/Android/AndroidManifest.xml"
  ],
  "diffMode": { "*.xml": "xml_structural", "*.gradle": "gradle_tokenized",
                "*": "line_normalized" },
  "expectedChangedAllowlist": ["Assets/Plugins/Android/mainTemplate.gradle"],
  "expectedVersionChanges": [
    { "path": "Assets/Plugins/Android/mainTemplate.gradle",
      "fromValue": "com.vendor:sdk:1.2.3", "toValue": "com.vendor:sdk:1.3.0" }
  ],
  "requiredMarkersAfter": [
    "namespace \"com.unity3d.player\"", "ndkPath", "ndkVersion",
    "mavenCentral()", "signingConfig", "manifestPlaceholders", "packagingOptions"
  ],
  "failOnUnexpectedChangedFile": true,
  "failOnStalePreviousVersion": true
}
```

**Baseline (fix §14.2 — provenance-clean, git-first):** for a `trackedPaths`
entry tracked in git, the baseline is the committed blob at `baselineRef`
(default `HEAD`) — the comparison is `git diff`-equivalent: provenance-clean,
reviewable, portable across machines/CI. The guard reads `git status --porcelain`
for the path and diffs HEAD→worktree only when dirty. Only a **git-untracked**
generated output falls back to a `Library/` snapshot, and that snapshot carries a
`baseline_fingerprint` = hash(projectRoot + Unity version +
`Packages/packages-lock.json` hash + tracked-SDK versions); the guard **refuses
to compare across a fingerprint mismatch** (`baseline_fingerprint_stale`) and
**refuses capture from a dirty tree** (`baseline_capture_dirty_tree`) so a garbage
baseline can never silently bless damage.

**Diff (fix §14.3 — structure-aware, not substring):** each path is compared with
a format-aware differ chosen by `diffMode`. `xml_structural` diffs
`AndroidResolverDependencies.xml` as an order-insensitive node set (a reordered
`<package>` is not a change). `gradle_tokenized` normalizes whitespace, comments,
and block order before diffing (a reformat is noise, not a false removal).
`line_normalized` is the conservative fallback. This is what lets the guard tell
**moved/reformatted** from **removed**.

**Critical markers (fix §14.3 — presence-after, not removal-detection):**
`requiredMarkersAfter` are asserted to still be **present in the new file**
(comments ignored) rather than diffed for a removal — a `signingConfig` that
merely moved still passes, while a genuinely deleted one fails
`required_marker_missing`.

**Classification:** each changed path lands in exactly one bucket —
`expected_dependency_update` · `resolver_normalization_noise` ·
`unexpected_mutation` · `required_marker_missing` · `stale_previous_version`.
Fail closed on `required_marker_missing`, on a surviving `stale_previous_version`,
or (if `failOnUnexpectedChangedFile`) on a non-allowlisted `unexpected_mutation`.
Never infer state from a log or transport success — file evidence only.

**Return payload:** `status`, per-path `{path, baseline_source, change_class,
baseline_sha256, current_sha256, markers_present[], markers_missing[],
on_allowlist}`, `required_marker_missing[]`, `stale_versions[]`,
`unexpected_changed_files[]`, `baseline_fingerprint` + `fingerprint_match`, and a
compact `verdict`. Register the report via
`register_artifact(kind="sdk_generated_diff_report", …)`.

**Where it runs (git/editor boundary):** because the authoritative baseline is
git, the baseline resolution + structure-aware diff live **host-side** in the
`sdk-generated-diff-guard` lane (which already shells git in the multi-project
runner). The optional in-scenario `sdk.generated_diff_guard` step **delegates to
that host check** rather than reimplementing git inside the editor, so the C#
side stays filesystem-only.

**Registration (three-registry rule, Ordinal-exact):** host tool/CLI
`unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard`; capability
`sdk_generated_diff_guard`; if also exposed as a bridge op, its `OperationName` /
`XUUnityLightMcpOperationRegistry.Operations` key / `bridgeOperation` must match
and the scenario kind must be added to **both**
`XUUnityLightMcpScenarioStepDispatcher` and `XUUnityLightMcpScenarioValidator`.

### 5.2 `unity.sdk.android_resolve` (+ `unity.sdk.package_restore`)

Supersedes `unity.edm4u.resolve` for the gate. Reuses the menu-firing loop and
settle tracking but adds the two missing proofs.

- **Active-target precondition:** read `EditorUserBuildSettings.activeBuildTarget`;
  if not `BuildTarget.Android`, either fail with `android_target_not_active` or
  (when `switchTarget: true`) switch first, then assert. Mirror the assertion
  pattern in `XUUnityLightMcpBuildPlayerOperation`.
- **Optional Version Handler update** before Force Resolve
  (`runVersionHandler: true`) via the existing VersionHandler menu candidates.
- **Force Resolve** via the existing candidate loop + attempt log.
- **Generated-output freshness wait (fix §14.1 — prove the NEW correct state, not
  the OLD marker's absence):** a successful `ExecuteMenuItem` return is explicitly
  **not** completion proof. Poll a settle predicate that holds only when ALL of:
  **(a)** the EDM4U/Android Resolver resolution log/summary reports completion
  *when such a log exists* (parsed, not assumed); **(b)** every tracked generated
  output is **sha-stable across N consecutive idle ticks** (reuse the
  `ProcessCompilePlayerScriptsStep` 2-stable-tick template — this also closes the
  partial-write race that an mtime check has); and **(c)** a post-resolve
  `dependency.verify` of the **new expected** coordinate/version passes. Proving
  freshness by the *new* state being correct removes the dependence on a
  `previousNativeVersion` string — which is unknown at portfolio scale and never
  clears for a same-coordinate transitive-only bump. Timeout with the predicate
  unmet fails `resolver_output_stale`, reporting which sub-condition (a/b/c) was
  not met.

Because EDM4U schedules async work after the menu returns, model the freshness
wait as **either** a scenario `sdk.android_resolve` step using the
`ProcessCompilePlayerScriptsStep` two-phase deadline template, **or** a
`project_defined_hook_poll_until` whose poll action evaluates the (a/b/c)
predicate and reports `{status: running|succeeded|failed, failure_class}` —
poll-until is preferred so the wait is engine-driven, not a blocking `Execute`.

`unity.sdk.package_restore` is the closed-editor sibling: open with package
resolve, settle, record package-cache ids/versions and dependency-XML sources,
exit. It feeds step 3 of the recommended update order.

### 5.3 GUI editor process pool

Admission-control wrapper around `open_unity_editor` — **not** a new store or
kill path. Enforce a global GUI cap (default `3`), an SDK-resolver-lane cap
(`1`), and a per-project lock; derive occupancy from
`list_live_project_editor_pids` across pooled projects (never cached counters);
inherit `open_unity_editor`'s fail-closed stance when
`process_visibility_available` is false. Eviction/quit uses
`restore_host_opened_editor_state` verbatim (graceful bridge quit → wait →
`terminate_editor_pid` **only** for a PID confirmed in
`list_live_project_editor_pids`). Extend `write_host_editor_session_state` with a
`lane`/`pool_slot` field rather than adding a second lock. Expose as
`request-editor-quit-and-wait` and a pool-aware admission check used by
`sdk-validate`; broad SDK validation prefers batch/closed-editor lanes and
reserves GUI slots for inspection.

**Cross-process cap lease (fix §14.4):** the global and per-lane caps are shared
state across independently-launched `sdk-validate` invocations, so a slot is a
**held lease**, not an in-memory counter. Admission acquires an atomic lease file
(reuse `XUUnityLightMcpAtomicFileWriter` + the PID/mtime-TTL freshness pattern
already used by the per-project session lock); a dead-PID or stale-TTL lease is
reclaimable. Without this, two concurrent operators each believe they own the cap
and open `global_cap × 2` editors.

### 5.4 `batch-edm4u-resolve` host lane

Closed-editor `-batchmode -executeMethod` wrapper that **owns async resolver
waiting** (the same freshness contract as 5.2, server-side). Integrates with the
existing batch runner: license-aware fallback (`server_license.py`), GUI
fallback only when batchmode is blocked and restore safety is known, and
`normalize_compile_evidence` so a resolve+compile lane produces lane-agnostic,
fail-closed portfolio evidence. Register via `server_cli_parser.add_parser`
(reuse `add_batch_operator_arguments`) + a `cmd_*` re-exported into
`server_cli_commands.py`. Batchmode feasibility for EDM4U must be proven with
versioned smoke coverage before it becomes the portfolio default.

### 5.5 `sdk-validate` portfolio orchestrator + reusable gate scenario

Ship a public reusable scenario template (`templates/scenarios/sdk_rollout_gate`)
composing package_restore → switch Android → android_resolve → generated_diff_guard
→ compile matrix → dependency.verify, with `cleanupSteps` restoring the previous
build target. `sdk-validate` fans this across selected projects through the GUI
pool + `BatchSelectionPlan` fail-closed selection, emitting a compact portfolio
SDK-validation summary: per-project `{resolve_status, freshness, diff_verdict,
suspicious_removals, compile_evidence, dependency_verify}` plus a manual
dashboard checklist for the out-of-scope backend/vendor-dashboard gates.

## 6. P1 components (editor-adjacent, still same-host)

### 6.1 Android native artifact validation (`unity.sdk.android_artifact` / `android-artifact-verify`)

After Android export/build: run the Gradle dependency report on the exported
project, verify expected resolved artifacts + transitive native SDKs, detect
duplicate classes / dependency conflicts, and inspect the merged
`AndroidManifest`, repositories, ProGuard/R8 rules, native libs, and manifest
placeholders. Implement checks as new `_run_expectation` kinds in
`server_artifact_probe.py` (`gradle_dependency_report_contains`,
`duplicate_class_absent`, …) and register logs/reports through the artifact
registry. Capability `sdk_android_artifact`.

### 6.2 iOS native artifact validation

Fresh iOS export → `pod install` → verify pods/versions in `Podfile.lock` →
`xcodebuild` compile/archive gate where feasible → inspect `Info.plist`,
privacy manifests, SKAdNetwork IDs, linked frameworks. New probe kinds
(`pod_lock_contains`, `xcodebuild_succeeded`). Capability `sdk_ios_artifact`.
Host-tooling dependent; gate conservatively on macOS + Xcode presence.

### 6.3 Connected-device validation layer (ROADMAP Wave 5 — opt-in module)

`device.android.list/install/launch/logs.tail/screenshot` (adb) and the iOS
equivalents ship as a **separate self-registering assembly** using the
`[InitializeOnLoad]` module pattern
(`XUUnityLightMcpTestFrameworkModule`): it calls
`OperationRegistry.Register(...)` + `CapabilityRegistry.RegisterProvider(...)`
only when its dependencies compile, so the base package stays device-free.
Capabilities `device_android` / `device_ios`, degrading to
`operation_unavailable` with a `recommended_action` when `adb`/Xcode is absent.

### 6.4 SDK smoke-hook contract

A debug-only, project-implemented `IXUUnityLightMcpScenarioHook` probe reporting
structured JSON (SDK init status, adapter/native versions, interstitial/rewarded/
banner load-show-fail callbacks, revenue continuity, consent/ATT/TCF state) —
never literal secret values. The MCP drives it and collects the JSON;
screen-tapping is a fallback, not the primary strategy.

## 7. P2 — vendor-specific evidence plugins

Optional validators atop the generic lane: parse vendor init/adapter-mismatch
logs, verify required native SDKs, check SKAdNetwork/privacy warnings, verify
config-field presence without exposing secrets. Kept out of the base package;
backend/dashboard checks remain a produced manual checklist unless a safe
host-local connector exists.

## 8. New MCP surface (summary)

| Layer | Operation | MCP tool | CLI | Capability |
| --- | --- | --- | --- | --- |
| P0 | `unity.sdk.generated_diff_guard` | `unity_sdk_generated_diff_guard` | `sdk-generated-diff-guard` | `sdk_generated_diff_guard` |
| P0 | `unity.sdk.android_resolve` | `unity_sdk_android_resolve` | `request-sdk-android-resolve` | `sdk_resolver` |
| P0 | `unity.sdk.package_restore` | `unity_sdk_package_restore` | `request-sdk-package-restore` | `sdk_resolver` |
| P0 | (host lane) | — | `batch-edm4u-resolve` | — |
| P0 | (host orchestrator) | — | `sdk-validate` | — |
| P0 | (host pool) | — | `request-editor-quit-and-wait` | — |
| P1 | `unity.sdk.android_artifact` | `unity_sdk_android_artifact` | `android-artifact-verify` | `sdk_android_artifact` |
| P1 | `unity.sdk.ios_artifact` | `unity_sdk_ios_artifact` | `ios-artifact-verify` | `sdk_ios_artifact` |
| P1 | `unity.device.android.*` (module) | `unity_device_android_*` | `device-android-*` | `device_android` |

## 9. Per-operation registration checklist (fail-closed contract)

For every new C# operation, all of the following must agree (Ordinal-exact) or
the request lands as `tool_unsupported`:

1. `OperationName` on the class.
2. Entry in `XUUnityLightMcpOperationRegistry.Operations`.
3. `bridgeOperation` in `server_specs_tools.py`.
4. Scenario kind added to **both** `XUUnityLightMcpScenarioStepDispatcher` and
   `XUUnityLightMcpScenarioValidator` (validator default fails closed).
5. Capability in `XUUnityLightMcpCapabilityRegistry.OperationCapabilities` +
   `Build*Capability()` in `XUUnityLightMcpHealthProbe` + `ProbeVersion` bump.
6. `cmd_*` handler re-exported into `server_cli_commands.py`'s import block
   (CLI binds by `getattr`; an un-re-exported command silently fails to bind).
7. Lifecycle policy in `server_specs_lifecycle.py` (activate/wait-for-idle/retry).
8. Compact-by-default response with `includeFullPayload` opt-in; non-passthrough
   tools get a handler in the `call_tool` `special_tool_handlers` dict.

## 10. Rejected alternatives

| Alternative | Rejection |
| --- | --- |
| Extend `unity.edm4u.resolve` in place | It returns `resolve_requested`; bolting target-enforcement + freshness onto it breaks its "fire and report" contract and its callers. A typed sibling keeps both. |
| Trust `ExecuteMenuItem` return as resolve completion | EDM4U schedules async work after the menu returns; the return only proves the menu existed. |
| Treat dependency presence as rollout proof | `dependency.verify` passing coexists with a wiped signing block / repo — the exact silent-damage case. |
| Copy `TryResolveProjectFile`/`ComputeSha256` into each op | Duplicated sandbox/hash logic drifts; promote to a shared helper once. |
| One giant `unity.sdk.validate` operation | Violates the narrow-composable-operations principle; the gate is a scenario over small ops so each proof is independently reusable and testable. |
| Ship device ops in the base package | Contaminates the editor-only base; device layer must be an opt-in self-registering module (ROADMAP Wave 5). |
| Let the GUI pool count slots from cached counters | Editors open/close out of band; occupancy must come from `list_live_project_editor_pids`, fail-closed when visibility is down. |

## 11. Phasing & exit criteria

- **P0.1 — shared helper + `generated_diff_guard`.** Exit: baseline capture +
  classification + suspicious-removal fail-closed, host regression + EditMode
  self-tests, one live Android project where a hand-removed signing block fails
  the guard while `dependency.verify` still passes.
- **P0.2 — `android_resolve` + `package_restore`.** Exit: active-target
  enforced, freshness wait fails on a stale output, poll-until integration,
  live proof that a no-op resolve (already fresh) passes and a forced-stale case
  fails.
- **P0.3 — GUI pool + `batch-edm4u-resolve`.** Exit: cap/lock honored under a
  simulated multi-project run, quit-and-wait eviction leaves no orphan editors,
  batchmode EDM4U proven on ≥1 real editor with versioned smoke.
- **P0.4 — `sdk-validate` + reusable scenario + portfolio summary.** Exit:
  fail-closed selection, compact portfolio summary, live fan-out over ≥2 real
  consumers.
- **P1 / P2** — native artifact validation, device module, smoke-hook contract,
  vendor plugins, sequenced after P0 is live-proven.

## 12. Validation plan

- **Host regression (`tests/`):**
  - *Baseline (§14.2):* git-tracked file diffs HEAD→worktree; clean tree reports
    `unchanged`; capture from a dirty tree is rejected
    (`baseline_capture_dirty_tree`); untracked-fallback refuses to compare across
    a `baseline_fingerprint` mismatch (`baseline_fingerprint_stale`).
  - *Diff (§14.3):* a reordered `<package>` / reformatted Gradle block classifies
    as `resolver_normalization_noise`, not a change; a moved-but-present
    `signingConfig` passes; a genuinely deleted marker fails
    `required_marker_missing`; a marker present only in a comment does not count.
  - *Freshness (§14.1):* the (a/b/c) predicate fails when the resolver log is
    absent-and-outputs-unstable, when outputs are not sha-stable across N ticks,
    and when post-resolve `dependency.verify` of the new coordinate fails; passes
    only when all three hold; a same-coordinate transitive-only bump still
    settles.
  - *Pool (§14.4):* admission caps + per-project lock; two concurrent
    `sdk-validate` runs cannot exceed the global cap (lease contention);
    dead-PID / stale-TTL lease is reclaimable.
  - *Selection & gating:* fail-closed selection for malformed/duplicate/zero
    eligible; capability degrade when EDM4U/adb/`git` absent.
- **Live Unity evidence:** on a real Android consumer, run the full gate scenario
  through a healthy editor; assert (a) a forced-stale resolver output is caught,
  (b) a hand-removed critical template marker is caught while `dependency.verify`
  still reports present, (c) a legitimate version bump passes with
  `expected_dependency_update` classification only. Record through the artifact
  registry.
- **Portfolio matrix:** `sdk-validate` across the consumer set with
  `compile_evidence` per project and a compact summary; document any lane not
  live-run.

## 13. Risks & non-goals

- Not a broadening of the Unity operation surface beyond SDK validation; product
  test semantics are unchanged.
- Batchmode EDM4U feasibility is asserted only after versioned smoke proof; until
  then GUI-lane resolve with the pool is the safe default.
- Device/native depth is opt-in and host-tooling dependent; absence degrades to
  a typed capability gap, never a false pass.
- Backend / vendor-dashboard / revenue verification stay outside the public core;
  the gate emits a manual checklist for them.
- Secrets: config-field presence is verified without exposing literal values;
  reports run through `redact_mapping`.

## 14. Known weaknesses & hardening decisions

An adversarial review scored the first draft **79/100**: the plumbing (grounding,
reuse, registration, phasing) was strong, but the two hardest correctness bets —
resolver-completion detection and baseline provenance — were under-specified. The
decisions below are folded into the component designs above and are load-bearing:
skipping them yields a gate that gives *false confidence*, which is worse than no
gate.

**14.1 Resolver-completion oracle (was the #1 risk).** EDM4U resolution is async
and exposes no clean bridge-friendly "done" signal; freshness-by-mtime +
old-version-marker is fragile — a same-coordinate transitive-only bump never
clears the marker, an identical rewrite bumps mtime, and a mid-write snapshot
races. **Decision:** prove freshness by the **new correct state**, not the old
marker's absence — settle predicate = resolver-log completion (when available)
AND sha-stable across N idle ticks AND post-resolve `dependency.verify` of the
new coordinate passes. See §5.2.

**14.2 Baseline provenance (was the #2 risk).** A `Library/` snapshot is
machine-local, gitignored, unreviewable, and can be captured from an
already-dirty tree (garbage baseline → every subsequent diff passes silently).
**Decision:** **git HEAD is the baseline** for tracked generated files
(provenance-clean, reviewable, portable); the `Library/` fallback is only for
git-untracked outputs and is fingerprint-bound (project + Unity + packages-lock +
SDK versions), refusing to compare across a mismatch and refusing capture from a
dirty tree. The guard's baseline/diff therefore runs host-side (it has git); the
scenario step delegates to it. See §5.1.

**14.3 Substring-classification treadmill (was the #3 risk).** `Contains(...)`
over Gradle/XML cannot tell moved from removed or reformatted from changed, so it
floods false positives until operators widen the allowlist into a rubber stamp.
**Decision:** **structure-aware diff** (XML node-set, Gradle tokenized) so
reformat/reorder is noise, and critical markers become a **presence-after**
assertion rather than removal-detection. See §5.1.

**14.4 GUI-cap coordination.** Caps are cross-process state; concurrent
`sdk-validate` runs would each assume they own the cap and open `cap × 2`
editors. **Decision:** a slot is a **host-side lease** (atomic file + PID/TTL),
not an in-memory counter. See §5.3.

**Residual risks accepted for now (explicit, not hidden):** batchmode-EDM4U
feasibility is still a bet — gated behind versioned smoke, with the GUI pool as
the fallback until proven; the guard is **detect-only** — no auto-remediation, so
a failed verdict surfaces a `recommended_next_action` (re-resolve / revert
generated files to HEAD) and the operator acts; and P1/P2 device/native depth is
opt-in and may slip without blocking the P0 value. These are named so a future
reader does not mistake them for oversights.

## 15. Do-first

The first release-ready vertical slice is now implemented in unreleased source:
`unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard` compares explicit
Git-tracked files against `HEAD` (or another named Git ref), returns a compact
verdict, writes ignored-library JSON evidence, and fails closed on missing
required post-resolve markers, stale configured previous versions, or
unallowlisted file changes. It intentionally rejects Library-baseline capture
and non-Git baseline sources rather than treating them as a pass. Host regression
coverage exercises an expected version update, missing marker, stale version,
unexpected change, MCP exposure, and CLI registration.

Remaining P0.1 work is the richer structure-aware XML/Gradle classification,
Git-untracked fingerprint-bound Library fallback, and artifact-registry
registration. P0.2+ remains unchanged.

Ship **P0.1 (`unity.sdk.generated_diff_guard` + the shared helper)** first. It is
the highest-ROI false-positive catch (destructive generated-file change while
compile-green and dependency-present both pass), the smallest new surface, builds
atop the already-shipped `dependency.verify`, and needs no new lifecycle or
device dependency. `android_resolve`, the GUI pool, and `batch-edm4u-resolve`
follow in that order.
