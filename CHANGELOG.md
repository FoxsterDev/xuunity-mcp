# Changelog

## Unreleased

## 0.3.73

Release tag: `v0.3.73`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.73
```

### Changed

- Released `v0.3.73` package metadata, server metadata, package manifests, and Git UPM examples.

### Why

- A passing compile matrix could not say whether Unity rebuilt the assemblies under test or reused cached
  results. That made a green error/warning report easy to overread as proof that a recent source edit had
  actually been compiled.

### Added

- Direct and matrix compile results now report `rebuilt_assembly_count`, `cached_assembly_count`,
  `rebuild_evidence_status`, and `rebuild_evidence_basis`. Unity `2022.1+` uses its native
  `assemblyCompilationStarted` and `assemblyCompilationNotRequired` events, so the evidence follows Unity's
  own rebuild decision instead of guessing from output files or log text.
- Compact MCP, batch, and multi-project summaries preserve the same rebuild/cache counts. Matrix compact
  output also keeps a bounded per-configuration evidence list, while the full result retains every row.

### Validation

- The full host suite passed `1058/1058` tests with `14` expected platform skips, and the public-site
  Playwright suite passed `42/42` checks.
- Current-source package EditMode tests passed `161/161` on Unity `2022.3.62f3` and `161/161` on Unity
  `6000.0.58f2`. Live player-script compile responses reported `9` rebuilt / `30` cached assemblies on
  Unity `2022.3.62f3` and `76` rebuilt / `181` cached assemblies on Unity `6000.0.58f2`, each with zero
  compiler errors or warnings and `rebuild_evidence_status: measured`.
- Work-commit Integration Tests, Discovery Checks, Site UI Checks, and GitHub Pages deployment passed for
  `1f836abfaae0cd2d07b29fe1ace69f97e14171a1` before the release sweep.

### Known limitations

- Unity `2021.3` exposes the rebuild-start event but not the cache-not-required event used by this evidence
  lane. It reports `rebuild_evidence_status: rebuilt_only_cache_status_unavailable`; cache-hit counts become
  decision-grade on Unity `2022.1+`.
- Hosted Unity Package CI remains waived because no Unity license secrets are configured for the runners.
  This release has live Unity `2022.3` and Unity `6000.0` consumer evidence, but not CI-recorded package
  EditMode/PlayMode proof for the release SHA.

## 0.3.72

Release tag: `v0.3.72`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.72
```

### Changed

- Released `v0.3.72` package metadata, server metadata, package manifests, and Git UPM examples.

### Why

- Two capabilities were broken in a way that reported success. `unity.game_view.configure`
  could not set a resolution on any iOS-targeted project, while the capability probe kept
  advertising Game View support because it only ever tested the one build group that always
  resolves. `unity.ui.click` reported `delivered: true` for clicks that the target's own
  handler then discarded, because the pointer event carried no raycast for the handler to
  recognise. In both cases the honest answer was available and the tool did not give it.
- A release landed as one commit carrying the product change, its tests, the whole
  documentation sweep and the version bump. That left the changelog as the only
  description of the change, made a revert of the release also revert the product, and let
  a version bump ride inside a feature commit unnoticed.

### Fixed

- `unity.game_view.configure` failed on every iOS-targeted project with
  `Requested value 'iPhone' was not found`. The resolver mapped `BuildTarget.iOS` to the
  string `"iPhone"` and parsed it against `GameViewSizeGroupType`, whose member is `iOS`;
  `BuildTargetGroup` still reports the obsolete `iPhone` alias, which is where the wrong
  name came from. The active group now comes from Unity's own
  `GameViewSizes.currentGroupType`, falling back to
  `BuildTargetGroupToGameViewSizeGroup`, and the enum value goes straight to `GetGroup`
  with no name round-trip. A caller-supplied `group` still has to match the active one,
  with `iOS` and `iPhone` accepted as aliases of each other. The reflection probe resolves
  the active group too, so the capability report no longer claims
  `game_view_reflection` works on a project where `configure` cannot.
- `unity.ui.click` left `pointerCurrentRaycast` unset, so any handler that validates
  raycast identity — the common `eventData.pointerCurrentRaycast.gameObject == gameObject`
  guard in hand-written button components — silently dropped the click while the operation
  reported `delivered: true` with no state change. The click now runs a live
  `EventSystem.RaycastAll` at the target's centre and carries the observed result, so such
  handlers run their production path. Where the raycast produces no hit the event carries a
  synthesized result naming the resolved handler and the payload says so, and where it
  resolves to a *different* handler the click is refused as `ui_target_occluded` instead of
  faking reachability. New `pointer_raycast_evidence`, `pointer_raycast_target_path`,
  `pointer_raycast_hit_count` and `occluded_by_path` fields carry the evidence.
- Follow-up to the Game View repair, found by re-auditing it: the
  `BuildTargetGroupToGameViewSizeGroup` fallback was inoperative on every Unity 6.x, where
  that method takes a `BuildTarget` and not the `BuildTargetGroup` the resolver passed, and
  its failure message claimed the method was absent when it was merely a different
  signature. The resolver now passes whichever type the method declares and says which of
  the two resolution paths failed. `GetActiveGroupName` no longer guesses a group name from
  the build target when resolution fails — it guessed `Standalone` for every target outside
  Android and iOS — and reports an empty group instead of a fabricated one.
- The capability report is cached on a key that did not include the active build target,
  while the Game View probe verdict now depends on it. A build-target switch therefore left
  a stale supported/unsupported verdict for `game_view_reflection`, refusing Game View
  operations on a target where they work, or admitting them on one where they do not. The
  cache key now carries the active build target.
- Package self-tests left an empty `Assets/XUUnityLightMcpGenerated/` and its `.meta`
  behind in the consumer project. `templates/smoke/run_package_self_tests.sh` removes that
  root on exit, using `rmdir` so a non-empty directory is never touched.

### Added

- `scripts/tools/sync_release_version.py` now records the compile-warning evidence row in
  `HISTORICAL_VERSION_CLAIMS`. That row holds a measurement taken for `v0.3.70` and the
  sweep had relabelled it twice, publishing the same untouched numbers first as `v0.3.71`
  evidence and then as `v0.3.72` evidence. A version printed beside a measured result is
  evidence, not a version reference, and the sweep now leaves it alone.
- `scripts/testing/check_release_commit_shape.py` enforces the two-commit release shape,
  so a release can be reverted without reverting the product change it published. A
  `release:` commit may carry only what the version sweep writes, the changelog section it
  opens, and the release bookkeeping docs. Every other commit must bump no version and must
  describe itself under `## Unreleased`; a commit that changes shipped package or host
  source and adds no line there is refused as `undescribed_work_commit`, so the release
  that promotes that section cannot silently omit a shipped change. Test-, docs-, script-
  and skill-only commits are exempt. The check names the exact files to move, runs over a
  single commit or a range, and derives its allowlist from
  `scripts/tools/sync_release_version.py` so a newly swept document does not need a second
  edit to stay releasable. The release checklist and publishing checklist now require it.

### Validation

- Host Python suite via `scripts/testing/run_host_python_tests.sh`: 1057 tests, 0 failures,
  14 skipped.
- Unity package self-tests on Unity 6000.0.58f2 in a consumer project whose active build
  target is iOS — the configuration the Game View defect needed: EditMode 159/159 passed;
  PlayMode 23 total, 21 passed, 2 conditional skips, 0 failed.
- Game View repair proven live, not only by unit test: a six-resolution sweep scenario ran
  19/19 steps on that iOS-targeted project, each capture's PNG header matching the
  requested size exactly (1080x1920, 1170x2532, 1284x2778, 1440x3200, 1536x2048,
  1080x2400), with the group reported as `iOS`. A caller-supplied `group` of `iPhone` was
  accepted and a `group` of `Android` was still refused against the active iOS group.
- Click repair proven live against a real identity-guarding button component in Play Mode:
  `pointer_raycast_evidence: event_system_raycast_resolves_to_handler`, `status: effective`,
  and the editor log shows the component's own click handler running its production path
  through to the network call it triggers. Before this change the same click reported
  `delivered: true` with no state change.
- Release gates green for this SHA: version consistency, release-docs freshness,
  public-release safety, and release-commit shape.

### Known limitations

- `Unity Package CI` remains waived: the runners have no Unity license, so the shipped
  package carries no CI-recorded EditMode/PlayMode proof for this release SHA. Every Unity
  result above was produced on a maintainer workstation, not by CI.
- The `ui_target_occluded` refusal engages only when the event-system raycast actually
  returns a hit. Where it returns none — Edit Mode, or a canvas the raycaster cannot reach —
  the click is still delivered with a synthesized raycast and occlusion is left unproven;
  the payload reports which case applied and warns on the synthesized one.
- That occlusion refusal has no automated coverage: the isolated self-test scene produces no
  event-system raycast hit, so the occlusion test skips itself rather than asserting a pass.
  It is proven only by the live run described above.

## 0.3.71

Release tag: `v0.3.71`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.71
```

### Why

- A project action could be blocked forever. The editor-domain currency gate compared
  file timestamps against the last domain reload, but it also counted scripts in folders
  Unity never imports, and a file touched without a content change is imported without a
  recompile. Both states reported `editor_domain_stale` with a remediation
  (`unity_project_refresh`) that could not change either number.
- The bridge set `Application.runInBackground = true` on every heartbeat. In the editor
  that property is backed by the project setting `PlayerSettings.runInBackground`, so the
  bridge was writing a value into consumers' `ProjectSettings.asset`, with no opt-out and
  no restore. The `v0.3.69` notes claimed the opposite.
- Point-of-use liveness evidence defaulted to `editor_truth_confirmed`. A scenario step
  that had not run yet, a step the run never reached, and a payload that could not be read
  all claimed confirmed editor truth with no sample behind them.
- The package self-test runner carried a hand-maintained `--assembly-name` filter and only
  failed when a whole run reported zero tests, so a capability-gated test assembly could be
  skipped for weeks while the lane printed a pass.
- Every wrapper CLI or smoke invocation is a fresh host process with a fresh
  `client_session_id`, so running them against one's own editor raised the foreign-client
  alarm on the operator's own server.

### Fixed

- The editor-domain currency scan now skips the entries Unity itself ignores (a name
  starting with `.`, ending with `~`, or named `cvs`) and prunes those directories instead
  of walking them, so a script under a folder such as `Samples~` can no longer pin the gate.
- The gate converges. A forced `unity_project_refresh` that settled at or after the newest
  editor-input timestamp is now evidence that Unity saw the file and owed no reload:
  `currency_basis` reports
  `settled_forced_asset_refresh_covers_newest_assets_editor_input`. A genuinely stale domain
  still blocks, and a failing script compilation blocks with
  `fix_script_compilation_errors_before_invoking` instead of a refresh that cannot help.
- The editor-domain load time is stamped once per domain by the bridge bootstrap before the
  bridge-enabled gate, so a project without the bridge enabled, a batch-mode editor, and a
  consumer running the shipped package tests all report it. Enabling the bridge inside one
  domain can no longer advance that timestamp and mask a stale domain.
- Background execution is opt-in (`background_execution_enabled` in the project's bridge
  config, default off). When enabled, the previous value is captured and restored on bridge
  disable or editor quit, the assignment happens once per domain instead of on every
  heartbeat/status/currency call, and `background_execution_mode` reports `managed` or
  `project_owned`. `setup-apply` now preserves operator-set keys in `bridge_config.json`.
- `result_trust_class` defaults to empty instead of `editor_truth_confirmed`. Every sampled
  payload keeps the value it reported before.
- A playing loop with no liveness sample yet reports
  `wait_for_playmode_liveness_sample_and_retry` instead of the throttle remediation, which
  told the operator to focus an editor when the correct action was to wait.
- Compiler diagnostic codes are read from the diagnostic, not from the file path. A message
  for a file under a folder such as `Physics2020` reported `CS2020` as the warning code.
- The compact compile response reads each field from the layer that owns it: the verdict
  from the nested result, the settle id from the envelope. A matrix nested under `result`
  now keeps its configuration evidence.
- Unity Hub is detected on Linux. The matcher only accepted a process whose final path
  segment was exactly `unityhub`, so the `unityhub-bin` and AppImage forms every real Linux
  install runs were invisible, which reported `no_hub_session` and, with the admission gate
  below, blocked those hosts.
- Request attribution separates the operator's own tooling from another agent. Host journal
  events carry a `client_kind` of `mcp_server` or `cli`, a host publishes its
  `client_session_id` to its child host processes, and `foreign_request_activity_detected`
  is scoped to a different non-CLI client session. CLI traffic is reported separately in
  `cli_requests_since_client_start`. A journal row from a host older than `client_kind`
  still counts as foreign, so version skew cannot silence the alarm.
- The compact wrapper envelope keeps a bounded `child_stderr_tail` when the child failed or
  returned a typed error, so a traceback beside a typed error is no longer dropped. A
  successful run still suppresses child output.
- The wrapper's compact payload extraction prefers the child's actual payload over a
  trailing log line that merely contains a JSON object.
- The `unity.project_action.currency` probe no longer activates or raises the editor window;
  it is a read, and the release that added it stated that XUUnity does not mutate OS focus.

### Changed

- The package self-test runner derives its per-mode assembly plan from the package source:
  every shipped test assembly whose tests carry the selected mode's category and whose
  `versionDefines` capability dependencies are installed in the consumer. The plan is
  reported as `editmode_plan=` / `playmode_plan=`, each planned assembly runs as its own
  filtered request and must contribute at least one test
  (`package_self_tests_assembly_contributed_no_tests`), and the discovery counter attributes
  tests to the owning assembly instead of guessing from a path segment.
- A host whose GUI editor licenses itself without a running Unity Hub can admit the GUI lane
  with `XUUNITY_LIGHT_UNITY_MCP_GUI_ADMISSION_OVERRIDE=1`. The refusal is unchanged by
  default and now names the override; when used, the override is recorded in the lane payload
  with the blocker it waived, so it is never silent.
- Released `v0.3.71` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- `docs/reference/GLOSSARY.md` now carries one table of every trust, outcome, warning and
  gap value this system publishes, with its producer and reader, so the next drift is visible.
- Regressions that would have caught these defects: the editor-log search bounds are one
  shared constant across the tool schema, the protocol refusal and the CLI clamp; a
  cross-language pin holds the `project_action` step expansion in Python and C# to the same
  step-id suffixes, refresh flags and `dependsOn` wiring; source sweeps hold
  `Application.runInBackground` to a single opt-in call site applied once per domain; and the
  Hub matcher is fed real `ps` output through the actual parser, including lookalikes that
  must not match.

### Benefits

- A project action that is genuinely invokable stops being refused, and a refusal now names
  an action that can change the outcome.
- A validation tool no longer edits the project it is validating.
- An empty trust class is never read as a confirmation, so a scenario result cannot look
  proven because a step never ran.
- The uGUI EditMode, uGUI PlayMode and TextMeshPro EditMode suites are under execution
  proof, and a project without `com.unity.ugui` or `com.unity.textmeshpro` still passes
  because those assemblies drop out of the plan instead of failing it.
- The foreign-client alarm keeps its meaning: another client session is driving this editor.

### Validation

- Host Python suite passes `1035` tests with `14` expected platform skips.
- Public site UI and accessibility checks pass `42/42` across desktop, mobile and
  narrow Chromium viewports.
- Release version consistency, documentation freshness and public-release safety pass;
  `git diff --check` is clean and every Python source parses.
- A clean uGUI consumer scaffolded from this source passes package EditMode `154/154`
  across all three shipped EditMode assemblies on both Unity `2022.3.67f2` and
  `6000.0.58f2`, and the consumer's `ProjectSettings.asset` is unchanged by the run.
- The full bridge lane (`run_package_self_tests.sh --mode all`) on Unity `2022.3.67f2`
  executed every assembly in the derived plan and reported each separately: EditMode core
  `110`, TextMeshPro `6`, uGUI `39`; PlayMode uGUI `13` passed with `1` expected skip, and
  PlayMode core `5/5`. That run also carried one EditMode probe that is deliberately not
  shipped, which is why the shipped EditMode total is `154`.
- The bridge reported `background_execution_mode=project_owned` throughout, which is the
  opt-in default.

### Known limitations

- Hosted `Unity Package CI` remains explicitly waived because its runners have no Unity
  license credentials. The local licensed Unity lanes above are the package evidence for
  this release.
- Live Unity validation was performed on macOS. Windows and Linux host behavior is covered
  by the portable host contracts and by fixtures, not by a live run. In particular the new
  Linux Unity Hub process forms are asserted through the real process-listing parser rather
  than observed on a Linux host.
- The helper-owned licensing-child termination path still has no live exercise: in this
  release's runs the child had already exited, so the guard was again not reached. It is now
  covered per platform shape (POSIX signal, native Windows `taskkill`, WSL `taskkill.exe`,
  and the refusal path) by tests instead of by a live kill.
- Restoring an opted-in `background_execution_enabled` value depends on a graceful bridge
  disable or editor quit. A force-killed editor cannot restore it, so an opted-in project
  can retain the enabled value.
- The GUI admission override waives the preflight, not the license. A host that genuinely
  cannot license an editor will still fail at launch, with the same evidence as before.
- `playmode_throttled` still serves as both a warning code and a trust-class value, and the
  request-status and liveness `result_trust_class` namespaces are still distinct sets under
  one field name. Both renames are breaking and are deliberately not done in a patch
  release; the full published vocabulary is now one table in `docs/reference/GLOSSARY.md`.
- The full bridge self-test lane needs a warm project on Unity `6000`: a cold first import
  can exceed the lane's `ensure-ready` timeout, which is why the `6000.0.58f2` evidence here
  comes from the batch lane.

### Errata for earlier releases

- The `v0.3.69` statement that background execution "does not change `PlayerSettings`" was
  wrong. An editor-time `Application.runInBackground` assignment reaches
  `PlayerSettings.runInBackground` and can be serialized into a consumer's
  `ProjectSettings.asset`. Consumers that ran `v0.3.69` or `v0.3.70` should check
  `ProjectSettings/ProjectSettings.asset` for an unintended `runInBackground` change.
- The package self-test runner's EditMode filter omitted the optional uGUI EditMode assembly
  from its introduction on `2026-07-30` until `v0.3.68`, and the TextMeshPro EditMode
  assembly from its introduction on `2026-07-31` until this release. EditMode counts in
  release notes whose evidence came from that runner therefore covered fewer assemblies than
  the package ships. The `v0.3.66` line "EditMode `95/95` in both uGUI and no-uGUI lanes" is
  the clearest instance: identical counts in both lanes prove the uGUI assembly contributed
  nothing.
- The `v0.3.63` statement that a host-opened editor was restored "without terminating the
  shared Hub licensing client" was not exercised. That run had no helper-owned licensing
  child, so the guard was never reached and the claim was unproven rather than proven.
- `v0.3.70` also repaired the default compact response of `unity_compile_player_scripts`
  without listing it. A direct compile nests its outcome under `result`, and the compact
  envelope had been reading `status`, `error_count`, `errors`, `compiled_assembly_count` and
  `duration_seconds` from the outer envelope, where those keys do not exist. From `v0.3.34`
  through `v0.3.69` that default response therefore carried no field from the compile itself.

## 0.3.70

Release tag: `v0.3.70`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.70
```

### Changed

- Released `v0.3.70` package metadata, server metadata, package manifests, and Git UPM examples.

### Why

- A passing compile matrix proved the absence of compiler errors but could not
  answer whether a warning-cleanup change actually removed warnings. Operators
  had to grep large raw Unity logs, and a newly introduced warning could hide
  behind an otherwise green compile verdict.

### Added

- Direct and matrix player-script compile results now report every warning
  occurrence through `warning_count`, deduplicate warning identities through
  `unique_warning_count`, and retain a deterministic bounded `warnings` sample
  with file, line, code, severity, and message evidence.
- Compact bridge, batch, and multi-project summaries preserve the warning
  counts and bounded evidence instead of discarding them.

### Benefits

- Warning-cleanup work can distinguish “compiled without errors” from
  “compiled without warnings” without scraping raw logs.
- The existing error-only compile verdict remains backward compatible: warnings
  are evidence and do not convert a successful compile into a failure.

### Validation

- Focused host regression coverage passes `211` tests; full host discovery
  passes `1011` tests with `14` expected platform skips, including live
  localhost TCP framing coverage.
- A clean Unity `2022.3.62f3` current-source consumer passes package EditMode
  `104/104`, PlayMode `5/5`, interactive acceptance `9/9`, compile contract
  `2/2`, and verified editor closeout.
- A clean Unity `6000.0.58f2` current-source consumer passes package EditMode
  `104/104`, PlayMode `5/5`, interactive acceptance `9/9`, compile contract
  `2/2`, and verified editor closeout.
- Public site UI/accessibility coverage passes `42/42`; Python syntax and
  `git diff --check` pass.

### Known limitations

- Warning evidence does not yet distinguish rebuilt assemblies from cache hits;
  that separate P1 finding remains open.
- Hosted `Unity Package CI` remains waived because the repository does not
  provide Unity license secrets; local licensed Unity `2022.3.62f3` and
  `6000.0.58f2` package lanes provide the release evidence instead.
- Live Unity validation for this release was performed on macOS; Linux and
  Windows host behavior remains covered by the existing portable and CI-backed
  host contracts rather than a live editor run.

## 0.3.69

Release tag: `v0.3.69`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.69
```

### Why

- A green player-script compile did not prove that Unity had reloaded the
  editor assembly used by a project action. An action could therefore execute
  older editor code and make a correct change look ineffective.
- A catalog action that read assets edited outside Unity could run before the
  AssetDatabase imported those edits and return a confident result for stale
  data.
- Forcing operating-system focus is disruptive and does not itself prove that
  the player loop advances. The bridge needed a background-execution aid that
  kept measured liveness as the source of truth.

### Changed

- Released `v0.3.69` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Every catalog-backed `project_action` now runs a persisted
  `project_action_currency` preflight before its project hook. The gate compares
  the loaded editor-domain timestamp with the newest `.cs`, `.asmdef`,
  `.asmref`, or `.rsp` input under `Assets` and blocks stale or unknown state.
- Catalog entries can declare `requiresFreshAssets: true`. Their invocation
  automatically performs and settles a forced AssetDatabase refresh, then
  rechecks editor-domain currency before calling the hook.
- `unity_project_action_currency`, `unity_project_action_invoke`, and
  `unity_status_summary` expose the same currency evidence and recovery action.
- While the bridge is active it keeps runtime
  `Application.runInBackground=true`. It does not change `PlayerSettings` or
  operating-system focus, reports `native_autofocus_enabled=false`, and keeps
  measured player-loop liveness authoritative.

### Benefits

- Project actions no longer silently use editor code or asset state older than
  the files on disk. A stale invocation stops before the hook and names the
  refresh needed to continue.
- Asset-reading hooks declare freshness once in `project_actions.yaml` instead
  of relying on every caller to remember a manual refresh.
- Unfocused Unity automation can continue when Unity supports background
  execution without stealing the developer's active window.

### Validation

- Full host discovery passed `1009` tests with `14` expected platform skips,
  including live localhost TCP framing coverage.
- Clean current-source package compilation and probe v4 passed on Unity
  `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`, `6000.1.13f1`,
  `6000.2.14f1`, `6000.3.23f1`, `6000.4.4f1`, `6000.5.10f1`, and
  `6000.6.0b3`. Every probe reported `game_view_reflection_v1` supported and
  exposed both Game View operations plus `unity.project_action.currency`.
- Package EditMode tests passed `102/102` with post-settle compilation green on
  Unity `2022.3.67f2` and `6000.6.0b3`.
- An unfocused Unity `6000.6.0b3` editor completed the full interactive
  enter-Play-Mode/exit-Play-Mode scenario with
  `application_run_in_background=true` and
  `native_autofocus_enabled=false`.

### Known limitations

- A first cold-project interactive run on Unity `6000.3`, `6000.5`, or
  `6000.6` can still encounter the existing transient Import Worker ownership
  guard during refresh. The warmed Unity `6000.6` rerun and its package tests
  passed; the guard fails closed and does not indicate a C# or Game View API
  incompatibility.
- `Application.runInBackground` is an execution preference, not proof that the
  player loop advanced. Callers must continue to use the reported liveness
  fields for Play Mode conclusions.
- Live Unity validation was performed on macOS. Native Windows and Linux host
  sessions were not rerun for this release.
- The hosted `Unity Package CI` workflow remains explicitly waived because its
  runners do not have Unity license credentials. Local clean-project Unity
  validation is the package evidence for this release.

## 0.3.68

Release tag: `v0.3.68`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.68
```

### Why

- Play Mode-dependent operations could report a missing UI control or capture a
  screenshot while an unfocused Unity Editor was not advancing frames. The
  dedicated state tool knew the loop was throttled, but that truth did not
  travel with the action where a developer needed it.
- Unity's editor `Screen.*` dimensions can differ from the Game View render
  target. Without both measurements, a captured layout could appear to prove
  behavior that actually ran against a different frame size.
- Greenfield authoring also required operators to hand-compose UI actions,
  project-hook boilerplate, and console diagnosis outside the persisted
  scenario/test evidence path.

### Changed

- Released `v0.3.68` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- UI read/click payloads, Game View screenshots, and persisted scenario steps
  now report point-of-use player-loop liveness, editor focus, remediation, and
  a result trust class. Throttled Play Mode evidence is explicitly downgraded.
- UI and screenshot evidence separates the effective Game View render target
  from Unity `Screen.*` dimensions and flags mismatches.
- Scenarios support `ui_exists` and `ui_get_text` alongside guarded `ui_click`.
  `unity_scenario_capabilities` exposes the complete schema, and scenario
  validation accepts a project-scoped JSON file path.
- EditMode and PlayMode test envelopes report console-error pressure since the
  request baseline, including a lower-bound trust class across domain reloads.
- The package exposes `XUUnityLightMcpMutationDelta.Create(...)`; the host adds
  approval-gated `xuunity_project_hook_scaffold` and scalar
  `xuunity_setup_plan.projectRoot` support.
- The package self-test runner includes the optional uGUI EditMode assembly
  whenever that dependency is present, closing a silent coverage gap.

### Documentation

- Added the greenfield project-hook authoring contract and the liveness/render
  evidence boundaries to the integration, smoke, architecture, status,
  roadmap, and continuation guides.

### Benefits

- UI interactions and captures now explain when the player loop is not live,
  so an unfocused Editor is not misdiagnosed as broken game logic.
- Scenario authors can keep boot, UI assertions, interaction, and capture in one
  ordered evidence record, while project-specific scene creation stays behind
  an explicit approval-gated hook.
- Test stalls expose concurrent console-error pressure, and package consumers
  no longer silently omit the optional uGUI EditMode assembly from self-tests.

### Validation

- Full host discovery passes `1007` tests with `14` expected platform skips,
  including live localhost TCP framing coverage.
- Clean Unity `2022.3.67f2` and `6000.0.58f2` core consumers pass
  compile/interactive acceptance, EditMode `99/99`, and PlayMode `5/5`, with
  verified editor closeout. A separate uGUI-enabled Unity 2022 consumer passes
  the corrected package-runner EditMode lane `138/138`.
- Release-document freshness and public-safety checks pass; public site UI and
  accessibility checks pass `42/42` across desktop, mobile, and narrow
  Chromium viewports.

### Known limitations

- XUUnity reports editor-focus and player-loop remediation but does not
  automatically focus Unity or mutate operating-system focus state.
- The hosted `Unity Package CI` workflow remains explicitly waived because its
  runners do not have Unity license credentials. Local clean-project Unity
  validation is the package evidence for this release.

## 0.3.67

Release tag: `v0.3.67`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.67
```

### Why

- A successful GUI-fallback compile matrix could return Unity's authoritative
  `passed` result with all six configurations green, while the multi-project
  runner reported `failed_wrapper_unity_unproven`, printed `total=0`, and
  exited with code 1. The runner understood the older full response but not the
  compact response that batch commands now emit by default.

### Fixed

- The multi-project compile runner resolves outcome evidence in a stable order:
  nested `result_summary`, compact top-level fields, the named summary artifact,
  then a Unity-confirmed result artifact. Reusing an already-open editor no
  longer changes a passing GUI-fallback matrix into a wrapper failure merely
  because that lane returned the compact response shape.
- Per-project status records identify which source supplied the Unity outcome,
  transport outcome, and matrix. Missing matrix counters are now reported as
  `unavailable` instead of measured zeroes.
- Regression coverage exercises compact top-level success, summary-artifact
  recovery, confirmed result-artifact recovery, and unavailable-counter output.

### Benefits

- A successful Unity compile matrix remains successful at the portfolio layer,
  so release and maintenance workflows no longer stop on a false wrapper
  failure or require manual inspection of the result JSON.

### Validation

- Release consistency, documentation freshness, and public-safety checks pass.
- The focused multi-project runner suites pass `12/12` tests, including compact
  top-level, summary-artifact, and confirmed result-artifact recovery.
- Full host discovery passes `996` tests with `14` expected platform skips,
  including live TCP loopback transport coverage.
- Public documentation UI checks pass `42/42` in desktop and narrow Chromium
  viewports.
- A fresh local Unity package-matrix attempt was blocked before package tests by
  the host Unity Licensing Client channel. The package C# source is unchanged
  from `v0.3.66`; this release relies on that release's green Unity 2022.3 and
  Unity 6000 package evidence for the unchanged package lane.

### Known limitations

- Compile-matrix warning totals and rebuilt-versus-cache-hit assembly counts
  remain separate open evidence gaps; this patch fixes verdict aggregation only.
- The `Unity Package CI` workflow remains explicitly waived because hosted
  runners do not have Unity license credentials.

## 0.3.66

Release tag: `v0.3.66`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.66
```

### Changed

- Released `v0.3.66` package metadata, server metadata, package manifests, and Git UPM examples.
- Batch helper CLIs now emit compact decision summaries by default; full nested
  evidence remains available with `--output full`.

### Why

- Two consumer retros found several trustworthy-looking but incomplete
  outcomes: delivered UI clicks with no visible effect, malformed scalar test
  filters that widened to a full suite, log anchors reused across editor
  processes, unattributed requests from another client, and applied mutations
  reported as not completed after lifecycle churn.

### Fixed

- UI click receipts separate event delivery from observable semantic effect.
  Delivered no-ops return `success=false`,
  `status=delivered_no_observable_effect`, and `ui_click_no_state_change`
  remediation.
- Declared MCP argument types are validated before execution, so scalar test
  filters cannot silently become an unfiltered test run.
- Editor-log anchors carry their writer PID and refuse cross-process offsets;
  `maxSearchChars` provides an in-tool continuation for truncated anchored
  grep, while Console tail suppresses stack traces unless requested.
- Requests carry a stable host `client_session_id` through transport, Unity
  journal events, and domain reloads. Status reports own, foreign, and
  unattributed request counts, and completed journal rows now carry the real
  editor PID.
- Applied project-hook mutations remain applied through passive wait/status
  steps and a later refresh or compile-settle failure. Mutation replay is
  disabled until state is verified, including lifecycle-recovered delivery
  ambiguity.
- Plain `project_defined_hook` object payloads are promoted to
  `hookPayloadJson`; conflicting or invalid aliases fail explicitly instead of
  validating and then disappearing at runtime.

### Benefits

- Operators can distinguish transport success from product effect, current
  client work from foreign editor activity, and a real negative log search
  from an inconclusive process/window mismatch.
- Test selection and mutating project actions now fail closed, preventing broad
  accidental suites and duplicate state changes.

### Validation

- Release-version consistency, documentation freshness, and public-release
  safety pass. The full host suite passes `992` tests with `14` expected
  platform skips, including live loopback transport coverage.
- The public site suite passes `42/42` browser checks.
- Clean Unity `2022.3.67f2` and `6000.0.58f2` projects pass EditMode `95/95` in
  both uGUI and no-uGUI lanes. uGUI PlayMode passes `18` tests with one expected
  skip; dependency-free PlayMode passes `5/5`, with authoritative post-settle
  compilation green in every lane.

### Known limitations

- Click effectiveness is based on the existing semantic snapshot comparison;
  custom UI effects without a modeled state change need log or project-hook
  evidence.
- `maxSearchChars` remains bounded at 10,000,000 characters; a larger log needs
  a nearer request/session anchor or direct artifact inspection.
- The `Unity Package CI` workflow remains explicitly waived because hosted
  runners do not have Unity license credentials. Local Unity validation is the
  release evidence for package changes.

## 0.3.65

Release tag: `v0.3.65`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.65
```

### Changed

- Released `v0.3.65` package metadata, server metadata, package manifests, and Git UPM examples.

### Why

- Unity 6000.5 marks `SerializedProperty.objectReferenceInstanceIDValue` as an
  error-level obsolete API (`CS0619`). The prefab validator used that API to
  distinguish an unassigned object reference from a serialized reference whose
  target was deleted, preventing the Editor assembly from compiling.

### Fixed

- Restored Unity 6000.5+ package compilation by using the supported
  `SerializedProperty.objectReferenceEntityIdValue` API for missing serialized
  object-reference detection while retaining the legacy instance-ID path on
  Unity 2021.3 through 6000.4.
- Added EditMode and source-contract regressions that preserve the distinction
  between unassigned and missing/deleted serialized object references and reject
  an unconditional legacy API use.

### Benefits

- The core Editor assembly and conditional uGUI assembly compile on Unity
  6000.5 and 6000.6 without losing prefab missing-reference diagnostics.
- Unity 2021.3, Unity 2022.3 LTS, and Unity 6000.0 through 6000.4 retain the
  established instance-ID implementation behind a version guard.

### Validation

- Focused/static contracts pass `52/52`. The full host suite collected `982`
  tests with `14` expected platform skips; six loopback-socket cases were
  sandbox-denied in that run, and the affected TCP module passed `11/11` when
  rerun with loopback access.
- Clean local-package projects compile both the core Editor and conditional
  uGUI assemblies with zero errors on Unity `2022.3.62f3`, `6000.0.58f2`,
  `6000.4.4f1`, `6000.5.10f1`, and `6000.6.0b3`.
- Unity `2022.3.62f3`, `6000.5.10f1`, and `6000.6.0b3` each pass EditMode
  `92/92` and PlayMode `18/19` with one expected skip. No `CS0619` occurs on
  Unity 6000.5 or 6000.6.

### Known limitations

- Unity `2021.3.45f2` was installed but could not begin package import because
  the local machine had no available license token. Its compatibility remains
  protected by the legacy compile branch and static regression coverage.
- Unity 6000.1 through 6000.3 were not run individually; Unity `6000.0.58f2`
  and `6000.4.4f1` exercise the same pre-6000.5 conditional branch.
- Live Editor compilation in this cycle covered macOS only. Windows and Linux
  retain host/static coverage.
- The `Unity Package CI` workflow remains explicitly waived because hosted
  runners do not have Unity license credentials; the local Unity matrix above
  is the release evidence for this package change.

## 0.3.64

Release tag: `v0.3.64`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.64
```

### Changed

- Released `v0.3.64` package metadata, server metadata, package manifests, and Git UPM examples.

### Why

- Two independent consumer retros showed that a capped UI tree search could
  report `ui_node_not_found` even though the requested control was simply
  beyond the scanned prefix. The same incomplete search could also find one
  candidate without proving that it was unique.

### Fixed

- `unity_ui_click` now refuses an incomplete selector search as
  `ui_selector_search_truncated`, whether the scanned prefix found zero or one
  candidate. It never delivers a click when absence or uniqueness is
  unproven.
- Direct and scenario click receipts now preserve the searched target and
  scenes, scanned node count, match count, depth/node limits, truncation flag,
  and truncation reason.

### Added

- Scenario `ui_click` steps now accept `maxDepth` and `maxNodes`, with the same
  `12` / `500` defaults as the direct tool. Recovery tells callers to narrow
  the target or scene, or deliberately raise the budget and retry.

### Benefits

- Automation can distinguish a real complete-search negative from an
  inconclusive partial search instead of silently skipping an existing button.
- A single match from a partial tree can no longer be mistaken for a safe
  unique target, preventing the wrong UI element from receiving the click.

### Validation

- Focused host contracts pass `153/153`; the full host suite completes `981`
  tests with `14` expected platform skips, and the public site UI suite passes
  `42/42` browser checks.
- Clean local-package projects on Unity `2022.3.67f2` and `6000.0.58f2` each
  pass EditMode `91/91` and PlayMode `18/19` with one expected skip and no
  failures.
- The development-system Unity `2022.3.62f3` consumer passes the same
  EditMode `91/91` and PlayMode `18/19` package gates, then returns to its
  original `v0.3.63` package pin.
- The primary Unity `6000.0.58f2` consumer passes its build-configuration
  compile matrix `6/6`, acceptance scenario `10/10`, contract scenario, both
  PlayMode lifecycle regressions, final health/settle checks, and corrected
  project-action catalog consistency lane. Its package pin is restored to
  `v0.3.63` before release.
- Release-version consistency, documentation freshness, public-release safety,
  and diff hygiene pass on the release tree.

### Known limitations

- A truncated selector search is not widened automatically. The caller must
  narrow the target or scene, or raise `maxDepth` / `maxNodes`, then retry.
- Guarded click delivery remains a uGUI capability and requires
  `com.unity.ugui`; UI Toolkit interaction is not added by this release.
- Live package validation covered macOS Unity `2022` and Unity `6000`. Windows
  and Linux keep fixture/host coverage rather than a live UI-click run in this
  cycle.
- The `Unity Package CI` workflow remains explicitly waived because the hosted
  runners do not have Unity license credentials. Local Unity validation is the
  release evidence for this package change.

## 0.3.63

Release tag: `v0.3.63`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.63
```

### Changed

- Released `v0.3.63` package metadata, server metadata, package manifests, and Git UPM examples.

### Fixed

- Added fail-closed, cross-platform Unity Hub licensing IPC discovery for GUI
  admission. One live Hub-owned candidate is forwarded automatically; zero or
  multiple candidates produce typed outcomes, and raw channels are redacted.
- Explicit Unity applications must now match `ProjectVersion.txt`, preventing a
  wrong-version launch from mutating `Library` outside an explicit matrix.
- Wrapper `--compact-summary` now emits one bounded JSON envelope instead of a
  full nested payload followed by a footer.
- Successful PlayMode requests that complete after domain reload now use the
  fresh bridge state to confirm Edit Mode and clean compilation, producing one
  `confirmed_success_after_lifecycle_churn` verdict with retry disabled.
- Host session cleanup tracks and revalidates only licensing clients spawned by
  the helper-owned editor and never claims the shared Hub client.

### Added

- Added `diagnostic-retro-bundle`, a bounded, sanitized, read-only licensing,
  readiness, request-lifecycle, test, and restore diagnostic.

### Validation

- A live macOS launch smoke on Unity `2022.3.62f3` passed automatic Unity Hub
  licensing IPC discovery without an explicit licensing argument. The editor
  reached a healthy bridge in Edit Mode with clean compilation, and the
  restore flow verified exact editor exit without terminating the shared Hub
  licensing client.
- The full host suite passes `979/979` tests with `14` expected platform skips,
  and the public documentation UI suite passes `42/42` browser checks.
- Release-version consistency, documentation freshness, and public-release
  safety checks pass on the release tree.

### Known limitations

- Live automatic Hub licensing handoff was exercised on macOS. Windows and
  Linux Hub process and endpoint shapes are covered by host fixtures, not by a
  live editor launch in this release cycle.
- The `Unity Package CI` continuous integration workflow remains explicitly
  waived because the hosted runners do not have Unity license credentials.
  Local validation covers the release, but the release commit has no
  CI-recorded EditMode or PlayMode proof.

## 0.3.62

Release tag: `v0.3.62`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.62
```

### Changed

- Released `v0.3.62` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Added `scripts/testing/run_consumer_rollout.py` for safely moving several
  Unity projects to one published Git package tag used by Unity Package Manager
  (UPM). Before any package file changes, it compares the expected project list
  with an ignore-independent scan, refuses a dirty canary project, and checks
  the Unity version, batch-mode license, write access, running Unity processes,
  and cleanup ownership. It updates and compiles one canary first, then updates
  the remaining clean projects only after that canary passes. An atomic
  per-project ledger supports reviewed resume; the generated worker packet
  cannot diagnose, release, or terminate processes; and root cleanup rechecks
  the current process identifier, project, and log before termination. Compact
  output is the default, overall deadlines can stop before wider updates, and
  credential-shaped process arguments are redacted before evidence is saved.

### Validation

- Focused rollout and timeout-contract tests pass `23/23`. The full host suite
  passes `966/966` tests with `14` expected platform skips, and the public
  documentation UI suite passes `42/42` browser checks.
- Clean projects on Unity `2022.3.67f2` and `6000.0.58f2` each pass package
  EditMode `91/91`, PlayMode `5/5`, interactive acceptance `9/9`, refresh
  contract `2/2`, compile contract `2/2`, and batch compilation. Both editors
  closed with no owned Unity process left for cleanup.
- Release-version consistency, documentation freshness, and public-release
  safety checks pass on the release tree.

### Known limitations

- The rollout helper proves Git package resolution and script compilation. It
  does not replace each game's Edit Mode, Play Mode, UI, or product tests.
- Projects with a dirty package manifest or lock at the frozen baseline are
  skipped. One ledger covers one selected Unity version, and a licensing or
  global-process blocker stops the run before package mutation.
- The `Unity Package CI` continuous integration workflow remains explicitly
  waived because the hosted runners do not have Unity license credentials.
  Local Unity validation above covers the release, but the release commit has
  no CI-recorded EditMode or PlayMode proof.

## 0.3.61

Release tag: `v0.3.61`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.61
```

### Changed

- Released `v0.3.61` package metadata, server metadata, package manifests, and Git UPM examples.
- `open-editor` and `ensure-ready --open-editor` accept ordered, repeatable
  `--unity-arg` values and report the effective launch arguments. This lets a
  developer supply a Unity licensing IPC channel, cache-server option, or other
  required editor flag without bypassing XUUnity's duplicate-editor guard.
  Existing editors are reused with requested arguments only when the process
  command proves them, and the package self-test runner forwards the same
  repeated arguments.
- Every host helper subcommand accepts `--json-only`, which suppresses progress
  chatter while keeping stdout as the final JSON result for scripts.
- `project_defined_hook_poll_until` keeps polling unmatched successful payloads
  until timeout when `continueWhen` is omitted. Scenario authors can still use
  an explicit `continueWhen` as a stricter payload contract.
- UI-evidence guidance now requires a fixed Game View size before Play Mode and
  a bounds query after a surprising capture, because responsive UI can collapse
  to zero size while a visibility flag remains true.

### Fixed

- `ensure-ready` no longer ends a live-editor/no-bridge launch as a generic
  timeout. It reports the editor PID, Editor.log path and idle time, and the
  last matched licensing or startup-dialog line; known blockers use
  `launch_blocked_probable_modal`. A later successful licensing handshake or
  entitlement resolution supersedes earlier transient channel errors. Fresh
  licensing errors receive a five-second recovery window because Unity 2022
  can briefly report a missing channel before its local licensing client is
  ready; stale invalid-license evidence still fails immediately.
- `scenario_invalid` includes its first validation cause. A missing hook can
  name the source candidate's assembly definition constraints and active player
  defines, so the developer can apply the profile that enables the hook before
  rerunning the scenario.
- Catalog authors can mark actions `hostScoped` and name
  `requiredPayloadFields`; invocation refuses with `hook_is_host_scoped` when a
  project-specific value is missing. Profile mutations can declare
  `mutationSettlePolicy: apply_then_gate`, which rejects refresh-after-apply and
  requires `wait`, `status`, then `compile_player_scripts`.
- `request-editor-quit --force-after-ms` adds an opt-in escape from modal-blocked
  quit. It terminates only one current, identity-verified editor for the target
  project and verifies process exit; ambiguous or invisible processes are
  refused.

### Validation

- The host suite passes `966/966` tests with `14` expected platform skips, and
  the public documentation UI suite passes `42/42` browser checks.
- Clean projects on Unity `2022.3.67f2` and `6000.0.58f2` each pass package
  EditMode `91/91` and PlayMode `5/5` from the current source.
- A Unity `2022.3.62f3` consumer passes package EditMode `91/91`; its broader
  PlayMode environment passes `18` tests with one expected environment skip.
  A Unity `6000.0.58f2` consumer passes an Android compile, the profile
  apply-then-gate scenario `7/7`, a fixed-Game-View GUI scenario `18/18`, and
  the profile-restore compile scenario `8/8`.

### Known limitations

- `Unity Package CI` remains explicitly waived because the hosted runners do
  not have Unity license credentials. Local Unity validation above covers the
  release, but the release commit has no CI-recorded EditMode or PlayMode proof.
- Live editor-launch and forced-quit validation was performed on macOS. Windows
  and Linux host paths are covered by the host suite, not by a live editor run
  in this release cycle.

## 0.3.60

Release tag: `v0.3.60`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.60
```

### Changed

- Released `v0.3.60` package metadata, server metadata, package manifests, and Git UPM examples.

### Changed

- The release closeout now requires a published GitHub Release after the tag
  gate, not only a Git tag. Release notes follow a fact-locked, junior-friendly
  structure that explains the developer pain, the concrete behavior change,
  the practical benefit, exact validation, and every known gap. Host automation
  may then update private consumer pins and the external product site without
  putting private paths or project names in this public repository.

### Fixed

- Unity Asset Import Workers no longer attach the Model Context Protocol (MCP)
  bridge. These headless
  child processes load editor code while importing assets, but they do not own
  the main Unity Editor's compile state. The bridge now exits before creating a
  session, transport, heartbeat, or journal file in an import worker. The host
  also refuses older worker-owned state with
  `bridge_owned_by_non_main_process`, reports compile health as unknown instead
  of `false` / `0`, and blocks runtime requests until the main editor writes a
  trusted state. Bootstrap journal entries now include the writer process id,
  process class, and editor-log path for later diagnosis.

### Validation

- The host suite passes `938/938` tests with `14` expected platform skips.
  Focused bridge-ownership regression passes `220/220` tests, and the
  separate-process file inter-process communication (IPC) simulator passes
  `3/3` ownership and delivery tests.
- Clean projects on Unity `2022.3.62f3` and `6000.0.58f2` each pass package
  EditMode `86/86`, PlayMode `5/5`, acceptance, refresh, and compile contracts.
- A Unity `2022.3.62f3` consumer passes package EditMode `86/86` and PlayMode
  with `18` passed and one expected environment skip. A Unity `6000.0.58f2`
  consumer passes compile preflight `6/6`, acceptance `10/10`, refresh/compile
  contract, PlayMode lifecycle recovery, and project-action consistency.
- Public documentation checks pass `42/42` desktop, mobile, and narrow-layout
  browser tests.

### Known limitations

- An older bridge state with no process class and no worker-shaped editor-log
  path stays compatible until host process discovery can attribute its process
  id. This avoids breaking older package/host combinations while still
  refusing a proven non-main writer.
- The `Unity Package CI` continuous integration workflow remains explicitly
  waived because the runners have no Unity license secrets. The release
  therefore has no CI-recorded EditMode or PlayMode result for its exact
  commit; the local Unity validation above is the available package proof.
  Restore the gate after configuring the documented Unity license secrets.

## 0.3.59

Release tag: `v0.3.59`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.59
```

### Changed

- Released `v0.3.59` package metadata, server metadata, package manifests, and Git UPM examples.

### Changed

- `Unity Package CI` is suspended in the release gate through an explicit waiver instead of being required.
  Runner Unity license secrets do not exist yet, so the workflow cannot produce a run for any SHA and the
  `Release Tag Gate` failed on the `v0.3.58` tag with `Unity Package CI: missing`. The gate now keeps the
  workflow in `RELEASE_GATE_WORKFLOWS`, reports a `waived_gates` record carrying the reason, the concrete
  evidence gap (`no CI-recorded EditMode/PlayMode proof for the release SHA`), and the restore condition, and
  reports `status=ok_with_waived_gates` — never plain `ok` — so a waived gate cannot be read as a passed one.
  `--require "Unity Package CI"` re-arms it for a single run. `v0.3.58` was validated locally on both Unity
  lines instead (EditMode `121/121` ugui on `2022.3` and `6000.0`, `84/84` no-ugui, PlayMode `18` with one
  environment skip); that evidence is not CI-recorded.
- `Discovery Checks` no longer path-filters its master push trigger. The release gate requires a run per
  release SHA, so the filter made the gate unsatisfiable for any commit outside it: the tag gate for a
  test-only commit polled its full 30-minute budget waiting for a run that could never be created, and
  earlier releases passed only because they happened to touch `docs/` or `templates/`. The contract test now
  enforces the no-filter rule for every workflow in the gate's set, not just `Unity Package CI`.
- The post-reset recovery budget is covered by the deadline handed to the recovery poll and by direct unit
  tests of `resolve_post_reset_recovery_timeout_ms`, instead of a wall-clock bound that failed on a slow
  Windows runner (`0.735s` against `0.65s`) while the logical behavior was correct — and that a fresh-budget
  mutation passed unnoticed.

### Fixed

- Anchored `unity_console_grep source=editor_log` searches keep the fixed-size window beside the anchor instead
  of keeping the end of a long anchored scope, so early boot/init evidence is no longer displaced by later log
  volume. The payload now promotes `search_verdict`, `search_verdict_reason`, `scope_truncated`, and
  `search_window_direction`; a zero-match from any partial scope is `inconclusive`, carries a recovery action,
  and uses `session_scoped_editor_log_partial_scope` instead of looking like proof of absence. Complete anchored
  zero-match searches remain `not_matched`. The existing recent-tail behavior of `unity_console_tail` is
  unchanged. (2026-08-19 anchored-scope truncation retro, P1)
- Readiness fail-fast no longer reports `interactive_compile_block_detected` as though a compile ran when its
  only evidence is compiler-diagnostic text in `Editor.log`. The top-level error now names the observed live
  condition (`editor_not_ready_bridge_not_attached`, `editor_identity_changed`, `editor_busy_compiling`,
  `editor_busy_importing`, or a log-only startup observation), stamps `compile_state=unmeasured`, and reserves
  compile truth for the compile surfaces. Transient attach/import/identity conditions keep polling and are only
  returned if readiness never settles; their recovery is a non-destructive status poll instead of editor recovery.
  Enriched errors also add the condition to the readiness gate, so `host_prerequisites.ready=true` with empty
  blocking codes cannot contradict a blocking readiness result.

## 0.3.58

Release tag: `v0.3.58`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.58
```

### Changed

- Released `v0.3.58` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Compact `unity_project_action_invoke` envelope. The tool now returns the action id, outcome, catalog-declared
  evidence scalars (`project_defined_hook_summary`), and the mutation trust verdict by default, dropping the verbatim
  scenario echo and the nested full scenario summary that previously repeated ~8-10 KB of constant host lifecycle
  payload per invocation. `includeFullPayload=true` (stamped in `full_payload_tool_arguments`) restores the full
  envelope, consistent with the released compact scene/view/playmode behavior. (2026-08-17 play-mode liveness retro,
  P1-2)
- Play-mode liveness evidence. The bridge heartbeat now samples `Time.frameCount` between heartbeats and reports
  `playmode_frame_count`, `playmode_frames_advanced_last_interval`, `playmode_frame_sample_interval_seconds`,
  `editor_application_focused`, and a derived `playmode_loop_liveness` (`advancing` / `throttled` / `paused` /
  `not_playing` / `unknown`) on `bridge_state.json`, `unity_playmode_state`, and `unity.status`.
  `unity_status_summary` surfaces the same fields when the package reports them. When play mode is on but the game
  loop is not advancing frames, the payloads carry an explicit `playmode_liveness_warning`
  (`playmode_throttled_editor_unfocused` when the editor lost OS focus, `playmode_throttled` otherwise) with the
  remediation `focus_the_unity_editor_or_set_interaction_mode_to_no_throttling`. An editor heartbeat is not a
  game-loop heartbeat: previously `is_playing=true`, `health_status=healthy`, and a fresh heartbeat all stayed green
  while the unfocused editor throttled the update loop to near zero. (2026-08-17 play-mode liveness retro, P0-1)

### Changed

- `unity.scenario.run` is no longer refused at dispatch while compilation is broken. Scenarios are ordered
  remediation flows (play-mode exit, refresh, compile), and step-level gates already own correctness inside the
  editor: scenario test steps refuse with `compile_broken` editor-side and Unity natively refuses Play Mode entry
  while compilation is broken. The host compile gate now covers direct one-shot operations only, and the
  direct-tool-versus-scenario-step gating contract is recorded in `docs/architecture/DESIGN.md` and asserted by a
  membership test. (2026-08-17 play-mode liveness retro, P0-3)

### Fixed

- `event_system_present` names its scope. The `unity_ui_click` payload now carries
  `event_system_scope=eventsystem_current_at_delivery` next to the boolean: the value is `EventSystem.current` at
  click-delivery time, not a project-wide or scene-file audit — a `false` no longer reads as "this project has no
  EventSystem". (2026-08-17 play-mode liveness retro, P2-1)
- `unity_status_summary` warns up front about a split log lane. When the running editor was not opened through the
  host wrapper (or the recorded host launch is a different editor pid), the summary carries
  `editor_launch_lane=not_opened_by_host` with the risk (`host_default_editor_log_path_may_be_stale`) and the
  remediation (pass `editorLogPath`, or reopen through `ensure-ready --open-editor`) — instead of every later log
  query discovering the stale lane on its own. (2026-08-17 play-mode liveness retro, P2-2)
- The catalog `payload.action` contradiction is resolved instead of silent. The invoker always injects the catalog
  action id into the hook payload's `action` key; a catalog whose `payload:` block declares a different `action`
  value is now reported as a `payload_action_conflict` validation error on `unity_project_action_list`, and invoking
  that action refuses with `project_action_catalog_payload_action_conflict` instead of silently contradicting the
  catalog's own declaration. The contract — hooks must accept the fully-qualified action id — is stated in the
  README scenario section. (2026-08-17 play-mode liveness retro, P1-3)
- Compiler diagnostics now carry provenance. Every payload built from bridge-state compiler evidence — the
  `compile_broken` refusal details and `unity_status_summary` — stamps `compiler_diagnostics_trust_class`
  (`confirmed` / `deferred_during_playmode` / `flag_only_not_verdict`, reusing the post-settle trust vocabulary) plus
  a `compiler_diagnostics_note` naming the remediation. A refusal can no longer quote diagnostics that a later
  recompile has already cleared, or a bare `script_compilation_failed` flag, as a current authoritative verdict
  without labelling them. (2026-08-17 play-mode liveness retro, P1-1)
- The mutation-delta warning is actionable. `passed_unverified_mutation_delta` and `passed_invalid_mutation_delta`
  verdicts now name the `xuunity.mutation-delta.v1` schema in the warning text and carry `mutation_delta_schema` plus
  `mutation_delta_contract_doc` pointing at the worked contract example
  (`docs/operations/SMOKE_TESTS.md#4c-mutating-project-action-delta-contract`), so a hook author no longer has to
  already know the shape the warning asks for. (2026-08-17 play-mode liveness retro, P1-4)
- The host-side compile gate no longer refuses `unity.playmode.set` for `exit`, `pause`, or `resume`. Exiting play
  mode is the remediation that lets Unity run the deferred recompile, so gating it created an in-band deadlock: a
  compile-broken play session could not be exited through the direct tool while the same transition expressed as a
  scenario step succeeded. Only `action=enter` remains compile-gated (fail-fast with diagnostics before Unity's own
  native refusal). (2026-08-17 play-mode liveness retro, P0-2)

## 0.3.57

Release tag: `v0.3.57`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.57
```

### Changed

- Released `v0.3.57` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Compact scene and view envelopes. `unity_scene_open`, `unity_scene_snapshot`, and `unity_game_view_configure`
  now return compact operation envelopes by default, matching the released compact behavior of refresh, compile,
  test, Play Mode, and screenshot responses: the duplicated host lifecycle evidence block is dropped, the
  operation's own facts are preserved (scene transition, scene content with `root_object_count`, resolved game
  view), and `includeFullPayload=true` opts back into the full bridge payload. Live measurement: a scene-open
  response shrank from ~12,000 to ~540 bytes with identical decision content. The Game View screenshot
  image-byte budget is documented: base64 inlines only within `imageBudgetBytes` (default `48000`), otherwise
  `image_omitted_reason=payload_budget` directs the operator to read `file_path`.
- Byte-bounded console tail. `unity_console_tail` / `request-console-tail` and the `console_tail` scenario step now
  enforce a deterministic payload byte ceiling (`maxPayloadBytes` / `--max-payload-bytes`, default `16384`; `-1`
  returns the unbounded raw tail). Oldest items are dropped first; a single oversized newest item is
  content-truncated with an explicit marker. Every response carries the accounting fields `max_payload_bytes`,
  `byte_budget_enforced_by` (`unity_bridge` for the current package, `host` fallback for older packages),
  `byte_budget_truncated`, `items_dropped_for_byte_budget`, `newest_item_truncated`, and `payload_bytes_estimate`,
  and on truncation names `unity_console_grep` as the compact recovery tool. Raw `-1` behavior and existing
  `limit`/type filters are unchanged.
- Automated Unity package CI and a release tag gate. The `Unity Package CI` workflow compiles the package and runs
  its shipped EditMode/PlayMode self-tests on two supported Unity lines (`2022.3` and `6000.0`) through pinned
  `unityci/editor` images, each in two consumer lanes: `ugui` and a `no-ugui` project that proves the package and its
  core test assemblies work without uGUI. Consumer projects are scaffolded by the tested
  `scripts/testing/scaffold_unity_ci_project.py`, which pins `com.unity.test-framework` through the same policy the
  setup wizard uses. A missing Unity license secret fails the workflow loudly instead of skipping it. Release/tag
  preparation is now blocked on CI evidence: `scripts/testing/check_release_ci_gates.py` requires a completed,
  successful `push`/`workflow_dispatch` run of `Integration Tests` (Python on Windows/macOS/Linux),
  `Unity Package CI`, and `Discovery Checks` for the release SHA before the tag may be pushed, and the tag-push
  `Release Tag Gate` workflow re-verifies the same contract in CI. Contract tests pin workflow names, Unity version
  pins, lanes, and license-failure behavior to the gate script and documentation
  (`docs/operations/UNITY_PACKAGE_CI.md`).
- A scenario `project_refresh` step that times out waiting for settle now explains itself instead of leaving a bare
  `project_refresh_timeout`. The Unity step captures settle evidence at the timeout instant (settle phase, pending
  flag, compiling/updating flags, Play Mode state, stable idle ticks) and classifies it as `package_settle_timeout`,
  `compile_import_churn_timeout`, `editor_busy_timeout`, `idle_confirmation_incomplete`, or `lost_final_accounting`.
  Scenario summaries and the run-and-wait decision verdict promote a `refresh_timeout_recovery` block with the
  classification, its source, editor reachability, a concrete recovery command, and an explicit note that the Unity
  operation may have completed even though the waiter timed out. When the editor is reachable the recommended next
  action becomes `request_status_summary_then_compile_gate`; when host health says the editor is unreachable the
  classification is `editor_failure` and the action is `recover_editor_session`. Results written by an older package
  classify as `unclassified_legacy_payload` and still carry the guidance. The released
  `applied_mutation_settle_timeout` and cleanup verdicts keep their existing actions.

### Fixed

- Direct EditMode and PlayMode test responses no longer silently overwrite the
  callback-time Play Mode state with the host's post-idle observation. They now
  retain both observations, identify the source used by the compatibility field,
  flag a disagreement without changing test totals or verdicts, and reconcile
  the matching persisted test-result artifact after Unity has finished writing it.
  Final-status recovery retains the same provenance, legacy artifacts receive an
  explicit source label, and lifecycle churn cannot contradict the settled-state
  trust class.
- Consolidated the host-side UTC timestamp parser used by bridge heartbeat, journal, scenario polling, operation
  evidence, and Editor.log health paths. Every consumer now shares the timezone- and DST-independent conversion
  while retaining its existing invalid/empty timestamp contract.

## 0.3.56

Release tag: `v0.3.56`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.56
```

### Changed

- Released `v0.3.56` package metadata, server metadata, package manifests, and Git UPM examples.

### Fixed

- Refresh, compile, and direct-test post-settle envelopes now promote structural assembly-definition failures
  from the current bridge generation of `Editor.log`, even when Unity's in-memory diagnostic list still contains
  older C# rows. Duplicate references, unresolved references, invalid `.asmdef` JSON, and assemblies Unity refuses
  to compile are typed as `assembly_definition_error`, placed before secondary compiler diagnostics, and retained
  in compact output with a no-cache-cleanup recovery action. The fallback refuses an unusable log anchor instead
  of presenting a prior-session error as current truth.

## 0.3.55

Release tag: `v0.3.55`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.55
```

### Changed

- Released `v0.3.55` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Declared-required tool arguments are enforced by the server before a call reaches Unity. `inputSchema.required`
  was advisory on both sides, so a client that ignored it could invoke a mutating operation with a missing
  argument; the host opened a Unity editor, attached a bridge generation, delivered the request, and only then
  did Unity reject it. The refusal now quotes the schema's own type, description, and enum values, and says
  `Nothing was executed`. Supplied falsy values are not treated as missing, so `approve=false` still reaches the
  operation that exists to refuse it, and `width=0` still reaches the game-view configure path.

### Fixed

- A quiet Editor.log is no longer mistaken for a rotated one. The rotation guard refused an anchor whenever the
  log's mtime predated the stamp describing it, but a live editor can leave its log untouched for minutes and
  still be the writer — measured on a real project as a `request_started` stamped seven minutes after the log's
  last write, which broke `since=` on any idle editor. Rotation is now claimed only when a replacement candidate
  exists and looks like the newer file, and `anchor_log_rotated` is reserved for a rotation whose sibling cannot
  serve the recorded offset.
- A dead editor's state no longer reports itself as ready. `build_bridge_stabilization_summary` accepted an
  `editor_running` argument but defaulted it to `True`, and four of its five callers relied on the default, so a
  stale state file produced `stabilized: true` and `safe_to_retry: true` in the same payload whose
  `host_health_classification` said `offline`. Liveness is now derived from the pid the state itself carries; only
  a state with no pid keeps the old optimistic answer.
- `transport_state.ready` and `transport_ready_for_requests` now mean "a request can be delivered", not "the
  recorded transport config looks usable". A dead editor's file still says `listener_state: listening`, which read
  as `ready: true`. The config-only verdict is preserved as `transport_config_usable`, with `bridge_state_live`,
  `not_ready_reason`, and `listener_state_source` beside it.
- `searched_scenes` no longer claims scenes the UI walk never opened. Roots share one node budget and are walked
  in scope order, so truncation stops the walk wherever the budget runs out, and `DontDestroyOnLoad` is appended
  last so it was the first scope to disappear. The budget semantics are unchanged; the new
  `target.scenes_not_reached` and the `ui_scope_truncated_before_all_scenes` warning name what was skipped.
- Compile argument validation now runs before the editor-busy guard. A caller in Play Mode with a bad argument was
  told to exit Play Mode, and the argument was still wrong afterwards.

### Added

- Every `source=editor_log` operation that opens a Unity editor as a side effect now says so in the payload
  itself: `editor_opened_by_this_call`, `editor_open_started_utc`, `editor_open_completed_utc`,
  `editor_open_duration_seconds`, and a note. The fact previously lived only inside
  `_xuunity_lifecycle.activation`, so a caller reading the payload — or a compact envelope, which whitelists
  fields — went on reporting the editor as not running after a call had launched it.

### Changed

- Argument validation inside the editor reports `operation_arguments_invalid` instead of
  `<operation>_failed`. The shared code carried by `XUUnityLightMcpEditorBusyException` is now an
  `IXUUnityLightMcpCodedException` contract, so any typed refusal maps through one resolver. Reporting a bad
  argument as `compile_player_scripts_failed` read as a compile verdict for a compile that never ran, and was
  misread that way in practice. Compile argument errors now name the parameter, list valid `BuildTarget` values,
  and state that nothing was compiled.

## 0.3.54

Release tag: `v0.3.54`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.54
```

### Changed

- Released `v0.3.54` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- `unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`, `unity_ui_get_bounds`, `unity_ui_tree_snapshot`, and
  `unity_ui_click` accept `targetKind=all_loaded_scenes`, plus `sceneName` and `includeDontDestroyOnLoad`, so an
  additive multi-scene project whose active scene is a bootstrap scene can be read and clicked. Every UI read now
  reports `scene_scope`, `searched_scenes`, `loaded_scenes`, and `dont_destroy_on_load_included`, and each node
  carries `scene_name`.
- `ui_target_out_of_scope`: a distinct diagnostic for a target that exists in a loaded scene outside the searched
  scope. `ui_target_not_found` now means only "no such object anywhere".
- `unity_console_grep` and `unity_console_tail` accept
  `since=playmode_start|bridge_generation|request_id` for `source=editor_log`, and echo
  `since_anchor`, `searched_from_line`, and `line_numbering_basis`. The editor package records the Editor.log byte
  offset at Play Mode entry and at bridge-generation start into `bridge_state.json`, and per request into the
  request journal — one stat per operator-issued request, never one inside the 0.5 s request pump. `since=request_id`
  also needs `sinceRequestId`, and answers "did *this* call log it", which a play-session anchor cannot. The same
  anchors are available on the CLI as `--since` / `--since-request-id`.
  A `session_start` anchor was implemented and then dropped: the host stamps the log size *before* launching
  Unity, but Unity truncates the log on start, so the recorded offset belongs to the previous log. It is either
  caught as `anchor_stale` or — once the new log grows past it — silently points at an arbitrary byte.
- `editor_in_play_mode`: a distinct refusal code for `unity.compile.player_scripts`, `unity.compile.matrix`, and
  `unity.build_player`, carrying both valid next actions instead of a generic "editor is busy".
- `post_settle_compile_trust_class` (`confirmed` / `editor_still_busy` / `deferred_during_playmode`) on refresh,
  compile, and test payloads, so a refresh that settles while the editor is playing no longer looks like a
  trustworthy green.
- `imageBudgetBytes` on `unity_game_view_screenshot` (default 48000). Above the budget the base64 is dropped and
  the payload reports `image_omitted_reason=payload_budget` with `file_path` intact.
- `payload_mode: compact_operation` now covers `unity.playmode.state`, `unity.playmode.set`, and
  `unity.game_view.screenshot`, each with an `includeFullPayload` opt-out.
- `projects_blocked`, `blocked_projects`, and an `aggregate_hint` in the multi-project batch compile rollup, plus a
  `blocked_by_live_editor` operator verdict, so a live-editor refusal no longer reads as a compile failure.

- `out_of_scope` on `unity.ui.query` / `exists` / `get_text` / `get_bounds`: a zero-match selector re-probes the
  widest scope before answering, so "no match here" and "no match anywhere" are distinguishable. Reported as a
  warning where zero matches are legal, and as the `ui_target_out_of_scope` error where a single match is required.
- `log_lane` on every `source=editor_log` payload, naming which log the read actually used and whether the editor
  writes it: `host_owned_logfile`, `editor_reported_platform_log`, `rotated_sibling`,
  `host_default_not_editor_reported`, `stale_not_written_by_live_editor`, or `unverified_editor_log`. Carries
  `editor_log_mtime_utc`, `editor_log_age_seconds`, and `heartbeat_age_seconds` so a stale log next to a live
  heartbeat is visible in one call, plus `log_lane_caveat` on the stale lane.
- `ui_scope_probe_incomplete`: a zero-match answer whose wider-scope probe was itself cut short by `maxNodes` or
  `maxDepth` no longer claims "no node in any loaded scene".
- `ui_scene_selector_ambiguous` and `target.scene_selector_ambiguous` when `sceneName` matches several loaded
  scenes, which previously widened the scope silently.

### Fixed

- `unity_console_grep` / `unity_console_tail` no longer default to a log the editor is not writing.
  `resolve_editor_log_path()` now prefers `bridge_state.editor_log_path` when a live bridge reports one; an
  explicit `editorLogPath` still wins. The host default is only correct for editors the host launched with
  `-logFile`, so for a Hub-opened editor the default could search a file untouched for hours while a healthy
  editor logged elsewhere — measured on a live project as a 12-hour-stale log returning a match with no
  staleness signal. The backing state is now read for every `source=editor_log` call, not only anchored ones.
- A `since` anchor is refused as `anchor_stale_dead_session` when `bridge_state.json` belongs to an editor that is
  no longer running. The liveness verdict existed one call away but an `or` fallback re-admitted the stale state,
  so a dead session's offsets were applied to the next session's log once it grew past them — the failure mode
  that got the `session_start` anchor removed.
- A `since` anchor no longer trusts a rotated log path. Unity renames `Editor.log` to `Editor-prev.log` when a
  second editor starts, and the first editor keeps writing the renamed file while `Application.consoleLogPath`
  still returns the static path; path equality, file size, and editor liveness all pass while the offset points
  into another editor's log. A log older than the stamp that describes it now forward-resolves onto its
  `-prev` sibling (`forward_resolved_editor_log_path`) or is refused as `anchor_log_rotated`. Searching the
  sibling directly is no longer reported as `anchor_log_mismatch`, and the sibling is a discovery candidate for
  `build_editor_log_identity`.
- The mid-line fabricated-match defect was also reachable at the `max_chars` truncation boundary, not only at the
  anchor: a truncated window began mid-line, so a grep for `MARKER` could match the tail of `xxNOMARKER` while
  the payload claimed `session_scoped_editor_log`. Reproduced on a real 1,187,704-byte scope and fixed.
- `unity_console_tail` reported line numbers several lines early: blank lines were filtered before numbering
  while the payload claimed `editor_log_absolute`. Numbering now happens before filtering.
- `since=request_id` verified nothing about log identity, because the offset comes from the request journal while
  the path check reads `bridge_state`, which `recover-editor-session` deletes. The editor now stamps
  `editor_log_path` beside `editor_log_offset_bytes` in the `request_started` event, and an offset with no
  identity is refused as `anchor_identity_unverified`.
- `request-console-tail` never ran: it was registered in the parser but `cmd_request_console_tail` was missing
  from the `server_cli_commands` re-export, so `build_parser()` bound no callable and the command printed help and
  exited 1 — including its documented `--since` anchors. `ui-vision-packet`, `ui-vision-submit`, and
  `ui-interaction-validate` were dead the same way. A sweep test now fails if any subcommand loses its callable.
- `unity.ui.click` reported a bare "matched no node" when the target lived in an unsearched scene, because the
  root-canvas out-of-scope case arrives as a warning and only errors were inspected. It now surfaces the scope
  diagnostic and names the scenes it searched.
- `out_of_scope` was only set on the zero-match path, so a target whose *root* was out of scope returned the
  `ui_target_out_of_scope` error with `out_of_scope: false`.
- Out-of-scope remediation no longer tells a `game_object_name` / `game_object_path` caller to retry with
  `targetKind=all_loaded_scenes`, which would discard `targetValue` and return an unrelated tree; it advises
  `sceneName` and keeps the kind.
- An Edit Mode zero-match at `all_loaded_scenes` no longer pays a second full tree walk that cannot find
  anything: `DontDestroyOnLoad` is unreachable in Edit Mode, and the widest-scope test required its flag.
- `target.scene_name` / `scene_path` no longer name a scene the call never searched, so a mistyped `sceneName`
  stops reporting the active scene as its target.

- A `since` anchor is refused as `anchor_log_mismatch` when the editor measured its offset against a different
  Editor.log than the one being searched. The editor stamps offsets against `Application.consoleLogPath`, while
  the host defaults to the project-local log — the same file only when the host launched the editor with
  `-logFile`. An editor opened from the Hub writes to the platform Editor.log, and applying its offset to the
  project-local one would have scoped the search to an arbitrary byte while still reporting
  `session_scoped_editor_log`.
- A `since` offset that lands mid-line no longer keeps the partial leading line. The editor records
  `FileInfo.Length` at a moment in time, so it can split a line being written: an offset splitting
  `xxNOMARKER here` left `MARKER here`, which a grep for `MARKER` reported as a hit on a line that literally
  says `NOMARKER` — a false positive carrying `result_trust_class: session_scoped_editor_log` and no caveat.
  The anchor now reports `starts_mid_line` and `partial_leading_line_dropped`.
- A truncated anchored scope no longer mixes numbering bases. `read_editor_log_scope` keeps the tail of the
  scope, so the window does not start at the anchor; `searched_from_line` now starts the window's own numbering
  at 1 alongside `line_numbering_basis: anchored_scope_relative`, and the anchor's absolute line moves to
  `since_anchor.anchor_line`.
- `unity.ui.click` re-resolved its target with `GameObject.Find(node.path)`, which cannot address every object the
  widened scope can now reach and silently picks the first same-named object across scenes. The click target is now
  the exact `Transform` the tree walk matched.
- `dont_destroy_on_load_status` reported `included` while `dont_destroy_on_load_included` was `false` under a
  narrower scope: the `DontDestroyOnLoad` scene is discovered for `loaded_scenes` under every scope but only
  *searched* under some. It now reports `out_of_scope_for_target_kind` in that case.

## 0.3.53

Release tag: `v0.3.53`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.53
```

### Changed

- Released `v0.3.53` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Added a capability-gated uGUI PlayMode test assembly that exercises the real
  guarded-click scenario-step path. The tests prove exactly-once delivery, a
  decision-bearing `ui.interaction.v1` receipt, before/after semantic state
  change, `playmode_state=playing`, and refusal without a minted receipt. The
  package self-test runner now includes the assembly when `com.unity.ugui` is
  available while retaining the dependency-free core PlayMode lane.

### Fixed

- Fixed the clean-project EditMode gate by removing an accidental uGUI
  dependency from the core prefab-mutation test. The allowlisted component test
  now uses Unity's built-in `MeshFilter` and proves both the add and remove
  transactions. Clean Unity `2022.3.62f3` and `6000.0.58f2` projects each pass
  EditMode `62/62` and the dependency-free PlayMode lane `5/5`.

## 0.3.51

Release tag: `v0.3.51`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.51
```

Two things land together: the residuals from the first consumer run of the
reference-driven UI acceptance surface, and the repair of `v0.3.50`, whose TMP
test assembly did not compile. That defect is the reason the editor package is
now built and tested by a real editor before a tag is cut rather than after — the
first blocker in
[`XUUNITY_MCP_ENTERPRISE_READINESS_DESIGN_2026-07-31.md`](docs/architecture/designs/XUUNITY_MCP_ENTERPRISE_READINESS_DESIGN_2026-07-31.md).

### Fixed — v0.3.50 package repair

- The TMP EditMode test assembly introduced in `v0.3.50` did not compile:
  `XUUnityLightMcpUiTreePayload` is internal and the new assembly had no
  `InternalsVisibleTo` grant, and the tests used `Is.AnyOf`, which the NUnit
  version Unity ships does not define. `v0.3.50` therefore shipped a package
  whose tests could not build for any consumer that lists it in `testables`.
- The TMP and prefab-defect fixtures failed headless. Creating a TMP label logs
  a graphics-device message on a 2021.3 runner, and the prefab-defect test
  deliberately imports a broken prefab; the test framework fails a test on any
  unhandled error log. Both now scope `LogAssert.ignoreFailingMessages` to the
  fixture that needs it and reset it in teardown.
- A TMP reader test asserted that a label with no font assigned reports
  `unresolved`. TMP substitutes its default font asset when one is available, so
  the assertion was wrong in a normal project and the corrected form was wrong in
  a bare one, where TMP Essential Resources are absent. It now asserts the
  invariant the explanation lane depends on — the status and the named font
  agree — which holds in both environments.
- Validated by execution on both supported lines rather than asserted: Unity
  `2021.3.45f2` and `6000.0.58f2` each report 99 EditMode tests, 98 passed, 0
  failed, and the one graphics-device render test correctly self-skipping
  headless. The TMP reader tests and the prefab script-GUID defect test — retro
  section 9 case 4, previously uncovered — execute for the first time. The core
  assembly was checked for the constraint-gating claim directly against the built
  DLL: `com.xuunity.light-mcp.Editor.dll` carries no `UnityEngine.UI` or
  TextMeshPro assembly reference while both satellites do.

Closes the four residuals from the first post-release consumer run of the
reference-driven UI acceptance surface, recorded in
`docs/archive/retros/2026-07-31_shipped_ui_acceptance_toolchain_first_run_retro.md`.
The protocol held end to end in that session; what it exposed was a mutation
receipt that could report success for a write that did nothing, a semantic
acceptance lane that could not be reached from the isolated-render lane, and two
surfaces whose default output was mostly noise.

### Fixed

- `unity_prefab_mutate` reports `status: "no_op"` for a value-setting operation
  whose serialized value did not change, and carries `no_op_count` on the
  transaction. It previously reported `applied` with `before == after`, no
  warning, and a passing `post_validation` — a false-positive receipt on the one
  surface where `expectedSha256`, atomic rollback, `post_validation`, and
  `reversible_patch_json` all presume the change report is truthful. An operator
  who did not re-measure the render shipped the wrong value believing it.
- Enum properties are refused rather than clamped when the supplied index is out
  of range, as `prefab_mutation_enum_value_invalid`, naming the valid
  `name=index` pairs. `SerializedProperty` addresses an enum by member index
  while a caller naturally supplies the enum's underlying value, so the natural
  call was silently discarded.
- `unity_ui_reference_compare` returns a successful envelope whenever the
  comparison ran. A passing visual lane was previously delivered inside an
  `<error>` envelope whenever an optional interaction lane or a pending semantic
  lane left overall `reference_acceptance` short of `passed`, forcing the
  operator to re-read a large payload to confirm the tool had not malfunctioned.
  The error channel is now reserved for a comparison that could not compute a
  visual verdict at all.

### Added

- `unity_prefab_render` and `unity_prefab_snapshot` persist the `ui.read.v1`
  snapshot beside the capture and return `snapshot_path`. The comparison surface
  consumes a snapshot by path, so while the snapshot was returned inline only, a
  reference declaring `acceptance.semantic: "required"` was structurally
  unsatisfiable outside Play mode and reported
  `not_evaluated / no_ui_snapshot_supplied` permanently.
- `unity_prefab_render` accepts `overrides`, the same typed operation list as
  `unity_prefab_mutate`, applied to the preview-scene instance only and never
  written to the asset, reported back as `applied_overrides`. Rendering a second
  runtime-driven UI state previously required mutate → render → inverse-mutate on
  a prefab shared by twelve projects; 54% of one session's mutation calls existed
  only to work around its absence. A failing override fails the render instead of
  capturing the un-overridden state.
- `set_serialized_field` writes asset-typed object references — `Sprite`,
  `Material`, `TMP_FontAsset`, meshes, ScriptableObjects — addressed by
  project-relative path or 32-character GUID, with `assetSubAssetName` (or a
  `path#SubAsset` suffix) for a sub-asset such as a sliced sprite, and
  `valueKind: "null"` to clear. Component and `GameObject` references stay
  refused, which is the guardrail that actually prevents swapping a component for
  another type. Refusing asset references was the only remaining reason to
  hand-edit prefab YAML.
- `unity_prefab_validate` accepts `unassignedReferenceScope`
  (`project_scripts` | `required` | `all`), defaulting to `project_scripts`, and
  always reports `unassigned_reference_suppressed_count`. One call with
  `reportUnassignedReferences` previously returned ~57 findings that were all
  standard-empty uGUI/TMP optional fields, and the one genuinely interesting
  empty field in the prefab was indistinguishable from them. `required` reads the
  project's own convention — a field attribute whose type name starts with
  `Required` — and is empty for a project that uses no such convention.
- `unity_console_grep` accepts `excludePattern` and suppresses build-pipeline
  progress lines (`CopyFiles`, `[n/m ...]`) by default on both the console-buffer
  and Editor.log lanes, reporting `excluded_count` and
  `build_pipeline_suppressed_count`. A grep for a feature keyword returned 159
  matches that were all `CopyFiles` lines, because the compile job had been named
  after the feature. `includeBuildPipelineNoise: true` restores them. A
  cross-language test pins the two lanes to the same pattern.
- `unity_prefab_mutate` reports `drift_guard`: `precondition_matched`,
  `unguarded`, or `drifted`. An Editor-API write goes through the editor's
  in-memory copy, so a serialized asset edited on disk without an intervening
  `unity_project_refresh` was silently overwritten, and nothing warned. Whether
  the editor's copy still matches the file is only decidable from the caller's
  own `expectedSha256`: from inside the editor, a file rewritten by an external
  tool and a file Unity itself reimported are indistinguishable, and an inferred
  check refuses legitimate writes. A transaction without a precondition therefore
  says so and carries the observed hash to pass next time, rather than implying
  the check ran.

### Changed

- A stale `expectedSha256` now fails as `prefab_mutation_asset_drifted` rather
  than `prefab_mutation_precondition_failed`, and names `unity_project_refresh`
  as the remedy for a stale editor import. Callers matching the old code must
  update.
- `unity_prefab_render`'s `includeSnapshot` defaults to `false`. The inline
  snapshot is large and the comparison tool cannot consume it; `snapshot_path` is
  what closes the semantic lane. Pass `includeSnapshot: true` to restore the
  previous response shape.
- An enum's `before`/`after` in the mutation change table name the enum member
  instead of its index, so the emitted `reversible_patch_json` carries a
  `restoreValue` that can be replayed through `stringValue`.

## 0.3.50

Release tag: `v0.3.50`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.50
```

This release closes the findings of an independent external audit of the
reference-driven UI acceptance surface shipped in `v0.3.49`. Several of them were
false passes: evidence that had not been earned, a mask policy that measured a
different quantity than the comparison applied, and a similarity grid that failed
the identical design captured at another resolution. Each fix is re-checked by
`scripts/testing/check_audit_regressions.py`, which also asserts the opposite
direction — that captures which are legitimately the same screen still pass.

### Security

- A scenario result only counts as an editor receipt when it is read from the
  editor's own results directory. A file the caller named anywhere else is
  reported as `evidence_source=unverified_result_path` and cannot reach
  `visual_determinism=proven`. Previously a hand-written JSON file passed as
  `fixtureResultPath` earned `reference_acceptance=passed` and
  `decision_ready=true` across every lane, because the only thing separating a
  receipt from a caller assertion was which argument the JSON arrived through.
- `judges_required` and `allow_self_review` are covered by `packet_hash`, so the
  independence half of the vision bar cannot be lowered after a judgement while
  stored reviews still read as valid.
- PNG decompression is bounded by the size the declared image needs. A 782 KB
  file declaring a 1x1 image drove peak RSS to 1.6 GB and decoded successfully;
  it now costs 32 MB and a typed `ui_reference_image_too_large`.
- PNG chunk CRCs are verified. A tampered `IHDR` silently changed the decoded
  dimensions, and those dimensions are what the registry records as the
  reference viewport.

### Changed

- **Breaking.** A reference that declares a single full-screen region is refused.
  One whole-screen average dilutes a missing element by the share of the screen
  it occupied, so a missing button or body paragraph scored above the floor and
  passed. Existing references with one full-screen region must be re-registered
  with a region per meaningful UI area.
- **Breaking.** `fixtureResultPath` and `interactionResultPath` outside the
  editor's results directory no longer produce decision-ready evidence.
- Comparison-grid cells are area weighted, so each source pixel contributes to
  the cells it overlaps in proportion. The identical design captured at 2x, 3x or
  4x now scores as identical instead of failing on binning phase.
- Masks are charged the grid-cell footprint they actually suppress rather than
  their declared pixel area, and the per-region cap applies to every declared
  region rather than only required ones.
- The `blocked_lanes` filter matches `failed_lanes`: an `optional` lane that ran
  and could not decide now gates the verdict instead of being dropped from it.
- `device` is a first-class acceptance lane with a pass/fail vocabulary and
  capture-resolution reconciliation. An acceptance key that a manifest does not
  declare takes its documented default, so references registered before a lane
  existed stay valid.
- `serialized_reference_type_mismatch` is severity `error`. Only `error`
  increments the failure count, so an unassignable serialized reference left
  prefab validation passing.

### Added

- Per-region content-coverage check, independent of region area, so a missing
  element inside a larger region fails even when cell similarity stays above the
  floor.
- `capture_below_comparison_grid` refusal for a capture smaller than the
  comparison grid, which previously raised `IndexError` mid-comparison.
- `scripts/testing/check_audit_regressions.py`: 25 executable checks that
  reproduce each audit finding and assert it stays closed, including a
  benign-variation sweep against false rejections.
- Cross-language pins for `playmode_state`, `targetKind`, clip/material/font
  states, bridge refusal codes and the file-IPC layout; `bridgeOperation`
  coverage widened from the ui/prefab subset to every declared editor operation.
- TMP EditMode test assembly and a prefab-defect test for an unresolvable script
  GUID, both previously uncovered.
- Added `unity_sdk_package_restore` and `request-sdk-package-restore`, a
  closed-project Unity batch lane that waits for Package Manager's registered
  graph to become idle-stable, then atomically records package ids/versions,
  direct dependencies, dependency-XML hashes, and manifest/lock hashes. The
  verdict is decision-ready only when Unity publishes a successful run-bound
  receipt and the same-project editor process is proven closed after exit.

### Fixed

- A rejected `overwrite=true` re-registration restores the previous
  `expected.png` instead of deleting it and leaving a manifest with no image,
  which permanently broke a working reference.
- Nested scenario operations pass through the capability gate. A
  constraint-gated operation threw out of the step handler and the scheduler
  persisted `scenario_runner_failed` without jumping to cleanup, stranding the
  editor in Play mode.
- `unity_prefab_render` builds its snapshot before detaching the render target,
  so node screen rects are not scaled by the editor display size.
- A vision review the normalizer rejects is refused rather than stored, a second
  submission by the same judge is refused rather than silently overwriting a
  previous verdict, and an unreadable review file blocks instead of being
  indistinguishable from no review.
- Duplicate or case-variant rubric criterion keys are an error instead of
  silently overwriting a low score; the vision score floor is 1, so a manifest
  cannot declare a bar no review can fail.
- A region that could not be compared reports `passed: false` rather than
  `null`, which read as a pass to any caller testing `is not False`.
- The region background is the dominant colour that actually occurs in the
  region; an independent per-channel median invented a colour the image never
  contained.
- The `sdk_package_restore` tests built a macOS-shaped Unity installation and
  failed on Windows and Linux, and an assembly-ownership assertion compared a
  native path separator against `"Ugui/"`. Both predate this release.

## 0.3.49

Release tag: `v0.3.49`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.49
```

This release adds reference-driven UI acceptance: a supplied design image becomes a
hash-pinned contract, a Game View or prefab capture is compared against it on a
resolution-independent similarity grid, and the verdict is decided across four lanes —
visual, semantic, interaction, and AI vision. Pixel equality is never the bar.

### Changed

- Released `v0.3.49` package metadata, server metadata, package manifests, and Git UPM examples.
- An acceptance lane marked `optional` that was actually evaluated and failed now fails
  the comparison. `optional` means the lane may be skipped, not that its failures do not
  count; only `not_required` opts a lane out of the verdict. This previously let a failing
  optional semantic lane pass silently.

### Added

- Added the reference-driven UI acceptance surface: `unity_ui_reference_register`,
  `unity_ui_reference_validate`, `unity_ui_reference_compare`, and the matching
  `ui-reference-register` / `ui-reference-validate` / `ui-reference-compare` host
  commands. A supplied design PNG becomes a hash-pinned `xuunity.ui-reference.v1`
  contract with declared viewport, comparison regions, reviewable masks, tolerance
  profile, and per-lane acceptance requirements.
- UI comparison is tolerance-based similarity on a resolution-independent cell grid
  (exact box average, local contrast, and per-region layout bounding boxes) rather
  than pixel equality, so a Game View capture whose resolution differs from the
  reference is valid input. `strict`, `balanced`, and `lenient` profiles plus
  per-reference numeric overrides control how close counts as accepted. Orientation
  or aspect mismatch is refused as `comparison_not_comparable` with recommended
  same-aspect capture resolutions and no score.
- Comparisons publish `actual.png`, `overlay.png`, `diff.png`, `metrics.json`, and
  `verdict.json`, and return `reference_acceptance` of `passed`, `failed`, `blocked`,
  `pending_lanes`, or `pending_manual_style` with a separate `decision_ready` flag.
  A passing verdict requires proven capture stability, and required semantic or
  interaction lanes that no tool can yet evaluate keep the reference pending instead
  of reporting acceptance.
- Added the read-only uGUI and prefab inspection surface (`xuunity.ui.read.v1`):
  `unity_prefab_snapshot`, `unity_prefab_validate`, `unity_ui_tree_snapshot`,
  `unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`, and `unity_ui_get_bounds`.
  Nodes carry a stable-within-snapshot path, active state, components, effective
  CanvasGroup alpha, raycast blocking, canvas sort order, screen-space bounds, and —
  where a backend reader is present — text, resolved font/material, interactability,
  and clip state. Every response reports `proof_class`, truncation, and ambiguity
  instead of hiding them, and no answer is ever derived from a screenshot or OCR.
- `unity_prefab_validate` reports typed pre-PlayMode defects: `missing_script_guid`,
  `serialized_reference_missing_component`, `serialized_reference_type_mismatch`,
  `missing_prefab_instance`, and opt-in `serialized_reference_unassigned`. Lanes that
  need an unavailable backend are listed in `lanes_not_evaluated` rather than passing
  silently.
- The uGUI and TextMeshPro readers ship as constraint-gated satellite assemblies
  (`com.xuunity.light-mcp.Editor.Ugui` / `.Tmp`), so the core editor assembly keeps
  zero package references and a project without `com.unity.ugui` still compiles — it
  simply reports the UI surface as `semantic_ui_partial` with the reason.
- `unity_ui_reference_compare` accepts `uiSnapshotPath` and stitches every failed
  region to the UI nodes whose bounds cover it, converting Unity's bottom-left screen
  pixels to top-left reference pixels with the transform recorded in the payload. Each
  failed region gains `explained_by` (ranked candidate nodes, per-node suspicions, a
  `likely_cause`, and a plain-language summary), so "region body is 0.59 similar"
  becomes "'Canvas/Body' overlaps this region and its font asset did not resolve". A
  region no node covers is reported as its own finding.
- The semantic acceptance lane is now real: when a snapshot is supplied, the
  reference's declared `requiredUi` selectors are checked against it and the lane
  reports `passed`/`failed` with typed failures (`ui_node_not_found`,
  `selector_ambiguous`, `ui_text_mismatch`, `ui_node_not_interactable`,
  `ui_node_not_visible`). A required-lane failure fails the reference even when the
  pixels match.
- Added the `xuunity.ui-fixture.v1` readiness contract plus `unity_ui_fixture_validate`
  and the `ui-fixture-validate` host command. A project hook reports `ui_fixture`
  (fixture and semantic state id, frozen clock, pinned locale, data source, resolved
  viewport/safe-area, and ready-predicate evidence) inside its payload; the host
  validates it, surfaces it in scenario hook summaries, and derives
  `visual_determinism`. Live or mixed data without a recorded immutable payload hash,
  an unfrozen clock, or an unpinned locale downgrade a comparison automatically
  instead of by convention.
- `unity_ui_reference_compare` / `ui-reference-compare` accept `fixtureResultPath`, so
  fixture evidence is read from the scenario result the editor wrote, with a hashed
  receipt naming the run, step, and hook. Caller-supplied `fixtureEvidence` is still
  accepted but is never receipt-backed and can no longer make a comparison
  `decision_ready`. `project-hook-scaffold --ui-fixture` generates a compliant hook
  that ships unsatisfied so it fails closed until the project fills it in.
- Added `unity_prefab_render`: renders a prefab in an isolated preview scene
  under a controlled Canvas at the declared viewport and safe area without booting the
  application, and returns both the PNG and the `ui.read.v1` snapshot it rendered, in
  render-pixel space, ready to feed straight back into `unity_ui_reference_compare`.
- Added `unity_prefab_mutate`: a typed, atomic prefab transaction through the
  Editor API — `set_serialized_field`, `set_rect_transform`, `set_canvas_group`,
  `set_active`, `delete_child`, `create_child_from_template`, `add_component`,
  `remove_component`. It previews by default, requires `approve` plus
  `previewOnly=false` to write, supports an `expectedSha256` precondition, re-validates
  bindings after mutating and discards the batch if validation fails, emits a
  reversible inverse patch, refuses ambiguous selectors and non-allowlisted components,
  and excludes object-reference fields so a component can never be swapped for another
  type.
- Added `unity_ui_click`: one guarded semantic click delivered through the
  EventSystem to a unique selector, never a coordinate click. It requires explicit
  `approve=true` and `action="click"`, refuses ambiguous, hidden, non-interactable,
  raycast-transparent, and handler-less targets, and records the matched node, the
  delivery mechanism, and before/after snapshot signatures.
- Added the device acceptance lane: `captureLane` (`game_view` | `device`) plus
  a `device` descriptor recording model, OS, resolution, orientation, safe-area insets,
  and build revision. A Game View comparison reports the device lane as
  `not_evaluated` and is never presented as device parity; a device capture with an
  incomplete descriptor blocks that lane instead of passing it.
- Added the AI-vision acceptance lane (`xuunity.ui-vision-review.v1`):
  `unity_ui_vision_packet` / `ui-vision-packet` renders one side-by-side review sheet
  (reference left, candidate right, scaled to a shared panel height, failed regions
  outlined on both panels) and ships the rubric with it; `unity_ui_vision_submit` /
  `ui-vision-submit` records a judgement and returns the lane. This answers what a
  cell-similarity score cannot: whether the candidate is recognisably the same screen in
  style, placement, and size. Every required criterion needs a score and a stated
  observation, the overall score is clamped to the worst required criterion plus one, the
  review is hash-bound to one exact image pair and expires as `vision_packet_stale` when
  either image changes, and `judge.role` records whether the judge was the agent that
  authored the UI. Numeric scores are withheld from the packet by default so the
  judgement is not anchored to the number the grid already produced. The bar moves with
  the `strict`/`balanced`/`lenient` profile and can be overridden or have criteria waived
  per reference through `visionPolicy`; no profile requires the top score.
- A comparison now reports `lane_disagreement`. Grid-passed with review-failed is
  `vision_contradicts_similarity` and fails the comparison, because cell similarity cannot
  see a wrong icon, a different type family at the same weight, or a mirrored arrangement.
  Grid-failed with review-passed is `similarity_may_be_over_strict` and names the looser
  tolerance profile that matches the observed similarity, so an over-tight bar is a
  deliberate reference-level decision rather than a per-comparison override.
- The interaction lane is real instead of a permanent `not_evaluated`. A new `ui_click`
  scenario step delivers a guarded click inside a Play-mode scenario and emits a
  `xuunity.ui-interaction.v1` receipt; `required_interactions` on the reference declares
  what must be proven, and `unity_ui_reference_compare` reads the receipt from
  `interactionResultPath`, defaulting to `fixtureResultPath` so one Play-mode run can
  establish the fixture and prove the interactions. Delivery in Edit mode **blocks** the
  lane rather than passing it: it proves handler wiring, not a running user path. A
  refused, undelivered, or effect-free click fails the lane. Added
  `unity_ui_interaction_validate` / `ui-interaction-validate` for the evidence on its own.
- `unity_ui_reference_register` / `ui-reference-register` accept `requiredInteractions`
  and `visionPolicy`, and `acceptance` gained a `vision` lane (default `optional`).

## 0.3.48

Release tag: `v0.3.48`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.48
```

### Changed

- Released `v0.3.48` package metadata, server metadata, package manifests, and Git UPM examples.

### Added

- Added capability-gated `unity.sdk.android_resolve`,
  `unity_sdk_android_resolve`, and `request-sdk-android-resolve`. The typed lane
  uses EDM4U's completion callback, requires active Android plus Android Build
  Support, waits for declared generated outputs to be SHA-256 stable across
  consecutive idle ticks, and verifies explicit expected coordinates before
  returning a decision-grade rollout verdict.
- Added a standardized `xuunity.mutation-delta.v1` trust contract for mutating
  project actions. Hook summaries promote before/after/added/removed/changed
  counts, while `unity_project_action_invoke` distinguishes successful Unity
  execution from decision readiness and warns on missing, invalid, or
  destructive-drop evidence. Mutating hook scaffolds now emit the contract.
- Extended `unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard` to
  cover Git-untracked generated outputs with an explicit, fingerprint-bound
  `Library/` baseline. Capture refuses a dirty tree apart from the selected
  untracked outputs; comparison fails closed when the project path, Unity
  version, package-lock hash, configured SDK versions, or snapshot integrity
  no longer matches the captured provenance.
- SDK generated-diff guard reports are now registered automatically as
  `sdk_generated_diff_report` artifacts after the JSON evidence is published.
  Passing and failed verdicts return the report hash plus the artifact-registry
  path, so rollout evidence stays durable and directly discoverable.

### Fixed

- Typed Android resolver callback failure/loss, missing or unstable generated
  output, missing expected coordinates, and inactive/unsupported Android target
  now produce explicit failed-closed classifications. Deferred completion state
  is atomically persisted, package-operation busy state is cleared after
  response handoff, and cached capability reports invalidate when EDM4U or
  Android support availability changes.
- Android `unity_edm4u_resolve` now fails closed with
  `edm4u_android_target_not_active` unless `BuildTarget.Android` is active, and
  rejects a missing Android Build Support module. Successful requests report
  the confirmed target precondition while explicitly keeping resolver-output
  freshness unproven and the rollout verdict non-decision-ready.
- `project_defined_hook_poll_until` now treats a passive hook payload with
  `status: not_started` as keep-waiting instead of an immediate unmatched-status
  failure. Explicit `passWhen` and `failWhen` matches retain precedence, all
  other unmatched statuses fail closed, and the existing timeout remains the
  terminal bound.

### Validation

- Typed resolver coverage passes focused host protocol/parity/atomicity tests
  `77/77`; current-source Unity `2022.3` package EditMode `24/24` and PlayMode
  `5/5`; real EDM4U callback failure and local-Maven success routes; a
  development-system consumer `14/14` + `5/5`; and a Unity `6000.0` consumer
  compile matrix `6/6`, acceptance `10/10`, contract/lifecycle, and
  project-action consistency route. The full host suite passes `476/476` with
  13 expected platform skips.
- Android-target precondition coverage passes focused host tests `61/61` and
  the full host suite `476/476` with 13 expected platform skips. Current-source
  package self-tests pass on Unity `2022.3`: EditMode `20/20` and PlayMode
  `5/5`. A Unity `6000.0` consumer passes compile matrix `6/6`, acceptance
  scenario `10/10`, and the refresh/compile contract. Its PlayMode and focused
  EditMode test requests correctly fail closed on a pre-existing unsaved scene;
  that unrelated user state was preserved. Both consumer package manifests and
  locks were restored byte-identically.
- SDK artifact-registration coverage passes focused guard/protocol/parity tests
  `80/80` and the full host suite `476/476` with 13 expected platform skips.
  A live Unity `6000.0` consumer guard passes across five Git-tracked Android
  outputs with zero changes and returns a registered report hash/pointer.
- Focused mutation-delta/protocol/parity tests pass, and the full host suite
  passes all `475` tests with `13` expected platform skips.
- A Unity `2022.3` development-system consumer passes package EditMode `14/14`
  and PlayMode `5/5`. A Unity `6000.0` consumer passes compile matrix `6/6`,
  acceptance scenario `10/10`, refresh/compile contract, PlayMode settled-state
  and lifecycle recovery, healthy final status, and project-action catalog
  consistency. Consumer package manifests and locks remain byte-identical.
- Focused SDK guard, protocol/parity, launcher-flavor, and subprocess-contract
  tests pass for the Git-tracked and Git-untracked baseline lanes.
- Host regression passes all `471` tests with `13` expected platform skips.
- Current-source package self-tests pass on a Unity `2022.3` consumer:
  EditMode `18/18` and PlayMode `5/5`, including passive `not_started` polling
  and explicit-failure precedence. A Unity `6000.0` consumer passes its compile
  preflight `6/6`, acceptance scenario `10/10`, refresh/compile contract,
  PlayMode lifecycle recovery, final-health, and project-action consistency
  routes.

## 0.3.47

Release tag: `v0.3.47`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.47
```

### Changed

- Released `v0.3.47` package metadata, server metadata, package manifests, and Git UPM examples.
- Requested EditMode and PlayMode filters that select zero tests now report the
  non-passing `test_filter_no_match` verdict with the requested-filter summary,
  direct counts, and one-refresh recovery guidance; unfiltered zero-test runs
  remain `no_tests`.
- The EditMode resolver safely attempts to load an explicitly requested test
  assembly before cataloguing its test names, and the public cold-discovery
  smoke refreshes once before requiring its fully qualified target.

### Fixed

- Removed catastrophic regex backtracking from Unity-process classification on
  long non-Unity command lines.
- Kept package self-tests from overwriting an active bridge test-run state and
  removed their temporary generated scene root when the test created it.

### Validation

- Consumer-project Unity validation passed the package self-test lane: EditMode
  `16/16`, PlayMode `5/5`, and the cold-discovery targeted EditMode smoke
  selected and passed `1/1` fully qualified test after one refresh.
- Host Python unittest suite passed: `466` tests with `13` expected platform
  skips.
- Public site Playwright checks passed: `42/42`.
- Release metadata consistency, documentation freshness, and public-release
  safety checks passed for `0.3.47`.

## 0.3.46

Release tag: `v0.3.46`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.46
```

### Changed

- Released `v0.3.46` package metadata, server metadata, package manifests, and Git UPM examples.
- Hardened `unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard` with
  structure-aware defaults: XML comparison is order-insensitive, Gradle
  comparison ignores comments/formatting and normalizes adjacent generated
  block order, and other text uses conservative line normalization. Required
  markers are token-aware and comment-safe, so reformatted calls do not fail
  while markers that survive only in comments cannot pass. Malformed structured
  outputs now fail with typed `invalid_generated_files` evidence, and per-path
  rows report the selected diff mode, semantic-change state, and marker proof.

### Fixed

- Detect the "Enter Safe Mode?" startup dialog blocking the editor even when
  Editor.log contains no "Safe Mode" marker (Unity does not log the marker while
  the prompt is displayed). `build_editor_log_diagnosis` now records
  `log_idle_seconds`, and project-health classification reports
  `startup_modal_dialog_block` with a
  `dismiss_editor_startup_dialog_or_quit_editor_then_retry` recovery when a live
  editor has compile errors, no live bridge heartbeat, and a quiescent
  Editor.log. Previously this degraded to a generic compile-block signal whose
  batch-gate recovery cannot run while the modal holds the project Library.

### Validation

- Host regression passed `461` tests with `13` expected platform skips.
- The guard passed against real Git-tracked XML/Gradle generated files in a
  Unity 6000 consumer and a tracked line-normalized file in a Unity 2022
  consumer. The same projects passed the package EditMode/PlayMode self-test
  lane and the compile/scenario/lifecycle post-change lane respectively.

## 0.3.45

Release tag: `v0.3.45`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.45
```

### Changed

- Released `v0.3.45` package metadata, server metadata, package manifests, and Git UPM examples.
- Made setup fail closed on stale canonical Git UPM pins, helper versions,
  helper integrity manifests, and client launcher flavor mismatches. Setup plans
  now upgrade older pins after approval, refuse automatic downgrades or custom
  source rewrites, and reject apply when the reviewed manifest changed.
- Reworked the public one-prompt install contract around the canonical
  `v0.3.45` source and tagged README. Existing helpers are verified before use,
  native Windows Codex blocks migrate from `bash`/`run.sh` to
  `cmd.exe`/the refresh `.cmd` without replacing unrelated config, and client
  restart plus live-tool proof is required before tests.

### Fixed

- Prevented stale/reused bridge PIDs from being trusted as Unity process
  identity. Automatic recovery no longer treats editor-open permission as
  force-termination permission, revalidates exact project ownership before an
  explicitly authorized termination, and Windows `taskkill` no longer uses
  the descendant-tree `/T` flag.
- Added a safety-epoch, hash-verified helper install manifest and published the
  legacy `server.py` version marker last, so interrupted or mixed-version
  helper rollouts are refreshed instead of executed.

### Validation

- Host Python unittest suite passed: `452` tests with `13` expected skips.
- Public site Playwright checks passed: `39/39`, including the 320 px viewport
  and clipboard safety-contract assertion.
- Release metadata consistency, documentation freshness, and public-release
  safety checks passed for `0.3.45`.

### Added

- Added `unity_sdk_generated_diff_guard` and `sdk-generated-diff-guard`, a
  compact, host-side SDK rollout proof for Git-tracked generated files. It
  compares each requested path to a named Git baseline and fails closed when a
  required marker is absent, a tracked generated file disappears, an expected
  previous native version remains, or an unallowlisted generated-file change is
  present. The guard writes a JSON proof
  under the project's ignored MCP evidence directory by default.

## 0.3.44

Release tag: `v0.3.44`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.44
```

### Fixed

- Restored macOS/Linux GUI-client startup after the Windows launcher work:
  installed POSIX refresh launchers now prefer their sibling virtual
  environment over `PATH`, generated client configs persist an absolute Bash
  path and avoid login profiles, explicit `PYTHON` overrides keep priority, and
  a forwarded `APPDATA` variable alone no longer misclassifies a POSIX host as
  Windows.
- Made `tcp_loopback` responses compact newline-delimited JSON frames and let
  the host return as soon as one complete JSON value is received, instead of
  waiting for socket close. TCP requests can also recover a completed file
  outbox fallback.
- Added decision-grade accounting for Unity operations that completed but whose
  original host delivery is unproven. Final status preserves confirmed Unity
  success, reports `unity_completed_host_delivery_unproven`, and explicitly
  prevents blind retry. MCP and CLI final/latest status surfaces are compact by
  default with an explicit full-payload opt-in.
- Made post-change validation select and report its execution lane before batch
  preflight. A live same-project editor now stays on the interactive MCP lane,
  including direct bridge-state recovery when the status-summary probe fails;
  unknown editor liveness blocks instead of falling through to batch mode.
- Made multi-project compile evidence lane-agnostic: GUI fallback now preserves
  its matrix counters from the bridge payload, and both the aggregate and GUI
  subset selector use the same normalized evidence. Explicit batch-result
  selection emits coverage accounting and fails before worker launch when the
  selected set is malformed or incomplete. Compact batch rows also report
  license-cache provenance and probe age when available.

### Validation

- Release metadata, documentation freshness, public-release safety, and public
  site checks passed for `0.3.44`.
- Host Python unittest suite passed: `430` tests with `13` expected skips.
- Live Unity validation in a representative host project passed the GUI-fallback compile
  matrix (`6/6`) and the selected GUI subset: EditMode `778/778`, PlayMode
  `279/279`.

## 0.3.43

Release tag: `v0.3.43`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.43
```

### Changed

- Scenario decision verdicts now distinguish a project-hook mutation that was
  confirmed as applied from an immediately following refresh-settle timeout.
  Such runs remain inconclusive rather than passing, but expose
  `applied_mutation_settle_timeout`, `mutation_applied_unsettled`, and a compact
  mutation/settle summary so the hook is not misread as failed.
- Refresh responses now qualify `playmode_state_after_settle` with an explicit
  source and trust class. When bridge identity changes during post-request
  settle, compact and full responses report `stale_risk` plus a
  `confirm_via_unity_playmode_state` next action instead of presenting the
  sampled PlayMode value as definitive.
- Hardened native Windows installation and launch paths: self-hosted refresh
  launchers, safe paths with spaces, predictable non-zero error propagation,
  Python 3.10+ gating, UTF-8 process handling, and client configs that point to
  the resolved launcher path.
- Improved cross-platform Unity discovery and readiness recovery, including
  extra Unity Hub installation locations, host-native recovery commands, and
  faster failure when interactive readiness cannot be achieved.
- Made bridge file IPC and request artifacts safer under lifecycle churn with
  atomic writes, torn-read resistance, process identity checks, subprocess
  timeouts, and editor-main-thread-safe runtime paths.
- Added end-to-end host regressions for Windows launchers, PowerShell setup,
  MCP stdio, installed delegate recovery, hostile code pages, and simulated
  file-IPC bridge behavior.
- Added public issue templates, contribution and conduct guidance, and an
  explicit independent-project notice.

### Validation

- Release metadata, public documentation, release-safety, host regression, and
  public-site checks passed before tagging.

## 0.3.42

Release tag: `v0.3.42`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.42
```

### Changed

- Released `v0.3.42` package metadata, server metadata, package manifests, and Git UPM examples.
- Changed `templates/smoke/run_post_change_validation.sh` to run a
  closed-project `batch-build-config-compile-matrix` preflight before
  `ensure-ready --open-editor` when the runner would otherwise open Unity,
  keeping post-C#-edit compile failures out of GUI Safe Mode startup.

### Validation

- Release version consistency, release-doc freshness, and public-release safety
  checks passed for `0.3.42`.
- Host Python unittest suite passed for `0.3.42`: `310` tests with `1`
  expected skip.
- Same-host Unity validation passed against two consumer projects: a Unity
  2022 package self-test lane with EditMode `14/14` and PlayMode `5/5`, and a
  Unity 6000 post-change route with compile preflight `6/6`, acceptance
  scenario `10/10`, and contract scenario passed.

## 0.3.41

Release tag: `v0.3.41`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.41
```

### Changed

- Released `v0.3.41` package metadata, server metadata, package manifests, and Git UPM examples.
- Made `transport_response_missing` and `editor_idle_timeout` compact by
  default while preserving full-payload recovery commands and tool arguments.
- Changed `unity_console_tail` / `request-console-tail` to use path-backed
  `Editor.log` by default, with explicit stale-buffer caveats when callers opt
  into the in-memory Unity Console buffer.
- Added Safe Mode compile-dialog classification for first-open/GUI readiness
  failures, with observe-only recovery guidance through the batch compile gate
  or manual Safe Mode handling.
- Annotated offline or unverified `editor_log_diagnosis` output with freshness
  fields so prior-session compile blockers are not mistaken for current working
  tree truth.
- Documented the manual-manifest/manual-open bridge enablement boundary and the
  "compile-green is not editor-startup-clean" validation caveat.

### Validation

- Release version consistency, release-doc freshness, and public-release safety
  checks passed for `0.3.41`.
- Host Python unittest suite: `309` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.

## 0.3.40

Release tag: `v0.3.40`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.40
```

### Changed

- Released `v0.3.40` package metadata, server metadata, package manifests, and Git UPM examples.
- Tightened `--output compact` batch helper CLI output so compact mode
  whitelists decision fields, normalized lane/verdict fields, and artifact
  pointers instead of copying the full batch result summary. Full output remains
  unchanged for deep debugging.
- Made `ensure-ready --open-editor` auto-enable the project-scoped bridge
  configuration when it is missing or disabled, without mutating user-level MCP
  client configs.
- Changed host-facing console grep defaults to path-backed `Editor.log` and
  added stale-console-buffer warnings for explicit empty Console error searches.
- Added first-open Unity upgrade/API-Updater modal-block diagnosis with
  `relaunch_noninteractive_accept_apiupdate` recovery guidance, and pass
  `-accept-apiupdate` through host-opened Unity launch and batch validation
  paths.
- Clarified setup-plan review output so client config paths are separate wiring
  review targets, not planned setup mutations.

### Validation

- Added regression coverage that keeps successful compact batch summaries under
  a 500-byte per-project budget and prevents raw log, probe-log, command, and
  workspace side-effect details from re-entering compact output.
- Added regression coverage for first-open project bridge auto-enable,
  `Editor.log` console grep defaults, stale Console false-empty warnings,
  API-Updater modal-block health classification, and project-only setup-plan
  review output.
- Release version consistency, release-doc freshness, and public-release safety
  checks passed for `0.3.40`.
- Host Python unittest suite: `300` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.

## 0.3.39

Release tag: `v0.3.39`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.39
```

### Changed

- Released `v0.3.39` package metadata, server metadata, package manifests, and Git UPM examples.
- Added `--output compact|full` to batch helper CLI commands, including
  `batch-compile`, `batch-compile-matrix`,
  `batch-build-config-compile-matrix`, `batch-editmode-tests`, and
  `batch-build-player`. The default remains `full`; compact output emits the
  decision summary and artifact pointers without the full command vector or
  nested batch payload.

### Validation

- Release version consistency, release-doc freshness, and public-release safety
  checks passed for `0.3.39`.
- Host Python unittest suite: `291` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.
- Compact batch helper dry-run output was validated against two local consumer
  projects, and full dry-run output still preserved the legacy command vector.

## 0.3.38

Release tag: `v0.3.38`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.38
```

### Changed

- Released `v0.3.38` package metadata, server metadata, package manifests, and Git UPM examples.
- Added a release-facing public-safety guard that fails when public docs contain
  host-local paths or locally configured denylist tokens before release tagging.
- Added `unity_scene_open`, `request-scene-open`, and scenario `scene_open`
  steps for deterministic Edit Mode scene setup before Play Mode and boot-flow
  validation. Scene opens fail closed during Play Mode, on missing scene paths,
  and on dirty open scenes unless `allowDirtySceneDiscard=true` is explicit.

### Validation

- Release version consistency, release-doc freshness, and public-release safety
  checks passed for `0.3.38`.
- Host Python unittest suite: `288` tests passed with `1` expected skip.
- Unity 2022.3 and Unity 6000 consumer-project local package validation passed
  package EditMode and PlayMode self-test lanes with the new scene-open tests.
- A Unity 6000 consumer-project project-local smoke suite passed readiness,
  acceptance and contract scenarios, compile matrix `6/6`, and a live health
  probe reporting `unity.scene.open` in `24` supported operations.

## 0.3.37

Release tag: `v0.3.37`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.37
```

### Changed

- Released `v0.3.37` package metadata, server metadata, package manifests, and Git UPM examples.
- Scenario `playmode_set` steps now preserve the direct
  `unity.playmode.set` payload outcome in compact summaries, so `enter` calls
  that resolve as `already_playing` are visible without full payload recovery.
- `unity_scenario_run_and_wait` compact decision verdicts now include a
  `playmode_guard_summary`; a passed scenario whose PlayMode entry reused an
  already-playing editor is marked with `trust_class=stale_risk` and a rerun
  recommendation when a fresh PlayMode start is required.

### Validation

- Release version consistency and release-doc freshness checks passed for
  `0.3.37`.
- Host Python unittest suite: `282` tests passed with `1` expected skip.
- A Unity 2022.3 consumer-project local package validation passed fast package
  self-tests: EditMode `12/12` and PlayMode `5/5`, plus a focused
  already-playing scenario guard probe with `trust_class=stale_risk`.
- A Unity 6000 consumer-project local package post-change validation passed
  readiness, compile matrix `6/6`, acceptance scenario `10/10`, contract
  scenario, PlayMode/lifecycle checks, and cleanup/restore.

## 0.3.36

Release tag: `v0.3.36`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.36
```

### Changed

- Released `v0.3.36` package metadata, server metadata, package manifests, and Git UPM examples.
- `transport_response_missing` errors now embed a compact final-status
  projection instead of the full final-status/artifact payload, while preserving
  the `request-final-status` command for full evidence recovery.
- Discovery-enriched stale-session transport failures now replace generic retry
  recovery commands with the actionable `ensure-ready --open-editor` command
  when host/session evidence proves recovery is needed before retrying.
- `ensure-ready` now defaults to a compact readiness envelope with verdict,
  health, bridge identity, package import summary, editor-log identity,
  recovery commands, and Play Mode exit hints. Use `--include-full-payload` for
  the previous nested discovery/package/import/lifecycle payload.
- `unity.status`, bridge heartbeat state, and compact status summaries now
  surface the active editor log path. Status summaries also flag newer
  project-matching foreign Editor.log candidates when practical.
- `unity_console_grep` and `request-console-grep` now support
  `source=editor_log` / `--source editor_log` for path-backed Editor.log grep,
  and docs call out Unity Console clear-on-play and ring-buffer eviction false
  negatives.
- `unity_scenario_run_and_wait` full-payload mode now omits duplicated
  `run_start.steps` by default; pass `includeStepPayloads=true` or
  `--include-step-payloads` to preserve that launch-time step copy.
- `templates/smoke/run_post_change_validation.sh` now emits durable phase lines,
  quiet-tail cleanup/auxiliary heartbeats, and classifies bridge churn as
  `non_blocking_churn` or `actionable_churn`.
- Added public-safe config-applying project-action build templates under
  `templates/project_actions/` for projects whose representative build lane
  must call project-owned config/apply/build methods instead of raw
  `unity_build_player`.

### Validation

- Release version consistency and release-doc freshness checks passed for
  `0.3.36`.
- Source checkout helper install refreshed neutral, Codex, and Claude tool
  installs; all reported package metadata version `0.3.36`.
- Host Python unittest suite: `279` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.
- Same-host Unity validation passed readiness, status-summary, and health-probe
  checks across two consumer projects, plus a project-local post-change route
  with compile matrix, acceptance scenario, contract scenario, lifecycle checks,
  and project-action catalog consistency.

## 0.3.35

Release tag: `v0.3.35`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.35
```

### Changed

- Released `v0.3.35` package metadata, server metadata, package manifests, Git
  UPM examples, public site version references, and package documentation.
- `unity_status_summary` now defaults to a compact polling payload for MCP
  callers and omits nested discovery, transport, state-group, timing, and
  artifact details unless `includeFullPayload=true` is provided. The compact
  payload keeps the decision fields needed for readiness, recovery, compiler
  state, lifecycle stabilization, host health, reconciliation, and process
  visibility.
- Added explicit `payload_mode=compact_status_summary` /
  `payload_mode=full_status_summary` markers so agents can tell whether nested
  diagnostics were intentionally omitted.
- Added `includeFullPayload` to the `unity_status_summary` tool schema and
  preserved the full previous nested summary shape for deep lifecycle and
  transport debugging.
- Kept the CLI `request-status-summary` helper on its existing full diagnostic
  default so shell smokes and local wrapper scripts continue to parse nested
  prerequisite fields without migration churn.
- Updated the token-efficiency retro registry to mark status-summary slimming
  complete and leave only batch/multi-project compact ceilings, token ledger,
  and fast-path profiles as remaining response-envelope backlog.

### Validation

- Release version consistency check passed for `0.3.35`.
- Source checkout helper install refreshed neutral, Codex, and Claude tool
  installs; all reported package metadata version `0.3.35`.
- Host Python unittest suite: `267` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.

## 0.3.34

Release tag: `v0.3.34`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.34
```

### Changed

- Released `v0.3.34` package metadata, server metadata, package manifests, and Git UPM examples.
- MCP tool responses for `unity_project_refresh`,
  `unity_compile_player_scripts`, `unity_compile_matrix`,
  `unity_compile_build_config_matrix`, `unity_tests_run_editmode`, and
  `unity_tests_run_playmode` now default to a compact operation summary that
  preserves authoritative post-settle verdict fields while omitting full
  `_xuunity_lifecycle` snapshots. Pass `includeFullPayload=true` to recover the
  previous full bridge payload for lifecycle debugging or raw artifact
  inspection.
- Compact operation summaries keep the authoritative post-settle verdict fields
  that agents need for closeout: status, error counts, first diagnostics,
  settle phase, completion basis, timing/artifact references, and full-payload
  recovery arguments.
- The compact/full bridge response conversion is centralized in
  `templates/server_bridge_payloads.py`, reducing duplicated response shaping
  across refresh, compile, build-config compile, and direct EditMode/PlayMode
  test tools.
- Public docs and retro registries were updated to record that normal MCP tool
  calls no longer dump lifecycle snapshots by default.

### Validation

- Host Python unittest suite: `267` tests passed with `1` expected skip.
- Release version consistency check passed for `0.3.34`.
- Public site Playwright checks passed: `39/39`.
- Source checkout helper install refreshed neutral, Codex, and Claude tool
  installs; all reported package metadata version `0.3.34`.
- Live MCP compact response validation passed on two local consumer projects,
  including post-settle compile truth without default lifecycle dumps.
- Unity 2022.3 consumer package self-test fast lane passed: EditMode `12/12`
  and PlayMode `5/5`.

## 0.3.33

Release tag: `v0.3.33`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.33
```

### Changed

- Released `v0.3.33` package metadata, server metadata, package manifests, and Git UPM examples.
- Reduced monolithic ownership on the Unity package side while preserving public
  MCP operation names, JSON payload shapes, scenario timing semantics, and
  persisted bridge state contracts. The existing scenario runner, project-action
  normalizer, bridge runtime state, and model entrypoints remain compatibility
  facades over smaller DTO, runtime, compiler, scheduler, catalog, and handler
  units.
- Reduced monolithic ownership on the Python server side across batch
  orchestration, bridge runtime, CLI command routing, editor-host lifecycle,
  setup wizard, summaries, and tool specs while keeping public command and MCP
  tool contracts stable.
- Tightened `unity_scenario_run_and_wait` compact/full payload semantics:
  public smoke helpers that need step-level evidence now request
  `includeFullPayload`, while compact summaries remain the default contract for
  agent-facing verdicts.
- Added regression coverage for the compact payload contract, scenario decision
  verdict parity, server parity baselines, and Windows/WSL process visibility
  routing.

### Fixed

- Fixed native Windows CI routing for `HostPlatformAdapter(platform_kind="linux")`
  so WSL-simulated PID checks do not accidentally use the host Windows
  `OpenProcess` path and report unrelated live PIDs as Unity processes.
- Hardened smoke validation docs and reusable smoke scripts so compact scenario
  results are not misread as missing per-step evidence.

### Validation

- Host Python unittest suite: `264` tests passed with `1` expected skip.
- Project devmode MCP post-change smoke passed, including readiness,
  compile matrix, acceptance, contract, playmode settled-state regression,
  lifecycle retry, and project-action catalog consistency.
- Project devmode package self-tests passed: EditMode `12/12` and PlayMode
  `5/5`.

## 0.3.32

Release tag: `v0.3.32`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.32
```

### Changed

- Released `v0.3.32` package metadata, server metadata, package manifests, and Git UPM examples.
- `unity_scenario_run_and_wait` now returns a compact decision verdict by
  default: verdict, trust class, failure class, recommended next action,
  terminal scenario status, short step summaries, UI smoke fields, and path
  coverage. Full raw scenario payloads remain available with `verbose` or
  `includeFullPayload`.
- Scenario lifecycle recovery now attributes editor cold starts and relaunches
  with `editor_relaunched`, `previous_editor_pid`, `current_editor_pid`,
  `bridge_generation_before`, `bridge_generation_after`, and
  `cold_start_reason` so latency is explainable without weakening the verdict.
- Scenario compile steps now prefer post-settle compile truth from
  `idle_wait_after`, keeping request-time transport success separate from
  final Unity compiler state.
- Infrastructure timeouts are classified as `infrastructure_timeout`, while UI
  smoke summaries continue to distinguish product assertions, preconditions,
  blocking popups, cleanup, and unproven Unity completion.
- Release version consistency now covers both MCP protocol metadata sources so
  `initialize.serverInfo.version` stays aligned with package metadata.

## 0.3.31

Release tag: `v0.3.31`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.31
```

### Changed

- Released `v0.3.31` package metadata, server metadata, package manifests, and Git UPM examples.

### Fixed

- Cleared Unity's editor progress bar after MCP-triggered compile, refresh, and build so the "Importing assets"/"Compiling" dialog no longer stays stuck on Unity 2022.3. Added `EditorUtility.ClearProgressBar()` to the compile-utility `finally` (covers every `PlayerBuildInterface.CompilePlayerScripts` caller, including matrix and scenario steps) and to the request-pump completion path (covers `AssetDatabase.Refresh` / `BuildPipeline.BuildPlayer`). Unity 6 already auto-cleared the bar; this restores parity on 2022.3.

## 0.3.30

Release tag: `v0.3.30`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.30
```

### Changed

- Released `v0.3.30` package metadata, server metadata, package manifests, and Git UPM examples.
- Native Windows Codex config generation now uses `cmd.exe` and
  `run_installed_or_refresh_xuunity_mcp.cmd`; an existing Windows `bash` block
  is reported as `windows_codex_launcher_mismatch` instead of duplicated.
- Windows setup docs now prefer `.cmd`, quote project paths, and call out
  PowerShell ExecutionPolicy risk for `.ps1`.
- `validate-setup` now reports offline readiness scope and package import-state
  evidence instead of presenting manifest/config validation as live Unity
  readiness.

### Fixed

- Added raw/resolved project-root diagnostics and Windows launcher hints for
  `project_not_found`, making path-with-spaces truncation diagnosable from one
  error payload.
- Added package import-state evidence to `ensure-ready` success and error
  payloads. A declared-but-unresolved package with a live bridgeless editor now
  recommends `reopen_project_for_clean_resolve` instead of generic editor
  recovery.
- Added an already-closed editor closeout fast path that clears stale host
  session/bridge/test state without quit or terminate attempts when process
  visibility proves no same-project editor is live.

### Validation

- Host Python suite: `243` tests passed on macOS, with one expected native
  Windows `.cmd` smoke skipped on this host.

## 0.3.29

Release tag: `v0.3.29`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.29
```

### Added

- Added `project_defined_hook_poll_until`, a first-class scenario operation for
  project-defined hook smokes that starts one hook action, polls another until a
  payload predicate reaches `passed`, `failed`, or timeout, and keeps the latest
  terminal payload in scenario results.
- Added scenario summary promotion for poll-until hook name, terminal status,
  failure class, requested scalar payload fields, screenshot path, console-tail
  evidence count, and cleanup result.

### Changed

- Released `v0.3.29` package metadata, server metadata, package manifests, and Git UPM examples.
- Scenario JSON now accepts `operation` as an alias for `kind` and accepts
  object-shaped `startPayload` / `pollPayload` inputs, which are normalized for
  both Python MCP tool callers and direct Unity bridge callers.

### Validation

- Validated package EditMode self-tests on a temporary Unity `2022.3.67f2`
  project with the local `com.xuunity.light-mcp` package: `12/12` passed.
- Validated an end-to-end temporary project hook scenario:
  `request-scenario-validate` returned `valid`, `request-scenario-run-and-wait`
  returned `passed` with `poll_count=3`, and compact summary promoted
  `selected_tab`, `user_path`, `before_value`, `after_value`, and
  `cleanup_result=passed`.
- Re-ran the host Python suite after live Unity validation: `237` tests passed
  with one expected native Windows `.cmd` smoke skipped on macOS.

## 0.3.28

Release tag: `v0.3.28`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.28
```

### Changed

- Released `v0.3.28` package metadata, server metadata, package manifests, and Git UPM examples.

### Changed

- Removed the legacy bash wrapper body (`xuunity_light_unity_mcp_legacy.sh`)
  and the `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER` escape hatch after the
  Python launcher core was proven by green Windows, macOS, and Linux CI legs
  on `v0.3.27`. The golden dual-run parity suite retired with its subject;
  cross-flavor (.sh/.cmd/.ps1) parity, the bash-spawn canary, and the full
  contract suite remain as regression guards.

## 0.3.27

Release tag: `v0.3.27`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.27
```

### Changed

- Released `v0.3.27` package metadata, server metadata, package manifests, and Git UPM examples.


### Added

- Added `xuunity_light_unity_mcp.cmd` and `xuunity_light_unity_mcp.ps1` wrapper siblings using the proven `run.cmd`/`run.ps1` Python discovery chain and executing `templates/server_launcher.py`, so Windows operators get the full wrapper surface without bash.
- Promoted shared subprocess helpers (Git Bash resolution, process-tree kill, run-to-files) into `scripts/testing/process_support.py`, consumed by both the orchestrator and the test suite.
- Added an optional `XUUNITY_LIGHT_UNITY_MCP_WORKER_TIMEOUT_SECONDS` watchdog that kills stuck worker process trees with exit code 124.
- Added cross-flavor launcher parity tests (`test_launcher_flavor_parity`) and thread-pool parallelism tests (`test_multi_project_parallelism`).

### Changed

- Ported the operator wrapper body from bash to `templates/server_launcher.py`, which owns source/repo/install-dir resolution, helper sync, compact summary emission, devmode/prodmode, and server dispatch. Client-context and install-dir resolution delegate to `server_setup_wizard` to remove duplicate bash/python logic.
- Shrank `xuunity_light_unity_mcp.sh` to a thin 28-line launcher with legacy flag checking and Python discovery (`PYTHON` env, `py -3`, `python3`, `python`, `py`). Preserved the previous bash body as `xuunity_light_unity_mcp_legacy.sh` (callable via `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER=1`).
- Ported both multi-project runners into `scripts/testing/run_multi_project.py` (subcommands `batch-compile-matrix` and `gui-test-subset`) using `ThreadPoolExecutor` workers, removing `xargs -P` and enabling identical parallelism overlap across macOS, Linux, and Windows.
- Expanded offline CI checks to run on `master` pushes and pull requests (previously tags only), smoke-executing `templates/run.cmd` and `templates/run.ps1` on the Windows leg.

### Fixed

- Fixed parity test path normalization for Windows path representations, resolving WSL/POSIX temp differences, 8.3 short names (`RUNNER~1`), and JSON-escaped backslashes.

## 0.3.26

Release tag: `v0.3.26`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.26
```

### Changed

- Released `v0.3.26` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.25

Release tag: `v0.3.25`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.25
```

### Changed

- Added `test-results-table` for reusable markdown, JSON, and TSV summaries
  from persisted Unity test-result JSON files.
- Improved multi-project GUI test subset reporting with per-project request
  ids, result paths, count summaries, lifecycle churn flags, failure grouping,
  package-source closeout, and workspace side-effect accounting.
- Documented completed test-result JSON as the immutable source of truth for
  portfolio closeout and aggregate operator verdicts.
- Released `v0.3.25` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.24

Release tag: `v0.3.24`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.24
```

### Changed

- Fixed Windows Git Bash wrapper delegation so setup and server commands use
  the resolved Python interpreter, including `python`, `python3`, and `py -3`
  launcher paths.
- Hardened setup plan/apply JSON loading for UTF-8, UTF-8 BOM, and UTF-16 plan
  files produced by common PowerShell capture flows.
- Improved Windows and WSL editor discovery, PID liveness checks, and path
  conversion for Windows-installed Unity editors used from WSL helpers.
- Added cross-platform compatibility regression tests for Windows, WSL, macOS,
  Linux, and shell wrapper Python launcher handling.
- Released `v0.3.24` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.23

Release tag: `v0.3.23`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.23
```

### Changed

- Added `unity.console.grep`, `unity_console_grep`, `request-console-grep`,
  and a reusable `console_grep` scenario template for compact Unity console
  inspection without raw log dumping.
- Added `request-loading-timing` and `unity_loading_timing` on top of console
  grep so agents can collect compact scene/loading timing evidence.
- Added `project-hook-scaffold` and profile mutation summary helpers for
  reusable project action and scenario authoring flows.
- Added public-safe completed retro archive entries and refreshed the public
  retro registry split between active backlog and completed history.
- Released `v0.3.23` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.22

Release tag: `v0.3.22`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.22
```

### Changed

- Added centralized neutral helper installation with Codex/Claude delegate
  launchers, isolated `.venv` discovery, and Antigravity IDE setup guidance.
- Hardened full-reset uninstall planning so client-specific cleanup preserves
  the shared neutral helper unless explicitly requested.
- Updated wrapper auto-resolution, setup wizard tests, and release-facing
  validation coverage for neutral helper workflows.
- Released `v0.3.22` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.21

Release tag: `v0.3.21`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.21
```

### Changed

- Fixed license capability classification so recovered Unity licensing startup
  warnings, such as transient access-token or IPC-channel messages followed by
  successful entitlement resolution and a clean batchmode exit, no longer force
  GUI fallback.
- Added explicit portfolio batch fallback-mode forwarding and compact operator
  verdicts so multi-project compile summaries distinguish `passed_via_batch`
  from `passed_via_gui_fallback`.
- Released `v0.3.21` package metadata, server metadata, package manifests, and Git UPM examples.
- Tightened the MCP release gate so `sync_release_version.py` and
  `check_release_version_consistency.py` now treat the GitHub Pages site and
  listing metadata as release-bound surfaces that must be updated before
  tagging.

## 0.3.20

Release tag: `v0.3.20`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.20
```

### Added

- Added `uninstall-plan` and `uninstall-apply` host helper commands plus
  `xuunity_uninstall_plan` and `xuunity_uninstall_apply` MCP tools for safe
  project cleanup and current-user reset flows.
- Added uninstall guidance across install, agent, client, template, and
  reference docs, including project-only cleanup and full reset modes.
- Added a GitHub Pages-ready public site surface for `XUUnity MCP`, including
  install, comparison, use-case, alternatives, and client-guide landing pages.
- Added SEO/discovery operational docs, including listing metadata, publishing
  checklist, SERP tracking guidance, and a live execution backlog.

### Changed

- Renamed the public repository slug from
  `FoxsterDev/xuunity-light-unity-mcp` to `FoxsterDev/xuunity-mcp`.
- Updated the canonical Git UPM install path to the new repository URL while
  keeping the package directory at `packages/com.xuunity.light-mcp`.
- Updated release-facing docs, package metadata, MCP metadata, GitHub Pages
  canonicals, and helper/client examples to use the new repo/site path.
- Documented uninstall as a preflight-first flow that removes only the selected
  `xuunity_light_unity` client config block, selected helper install, and
  explicit project-level MCP setup after approval.
- Released `v0.3.20` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.19

Release tag: `v0.3.19`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.19
```

### Added

- Added compact lifecycle churn output to the post-change validation runner,
  including bridge generation/session transition, request abandoned and
  reclassification counts, final health, final Play Mode state, compiler
  errors, stale request count, and warning codes.
- Added package self-test discovery output to the package self-test smoke
  runner, including testables visibility, Test Framework version, package
  source/hash, test asmdef count, test counts, and discovered MCP categories.

### Fixed

- Fixed package EditMode self-test compilation on Unity versions where
  `Object.DestroyImmediate` is ambiguous between `UnityEngine.Object` and
  `object`.
- Fixed package self-test smoke accounting so an explicit package self-test
  request fails on `no_tests` or `total=0` instead of reporting a top-level MCP
  success as a test pass.
- Fixed package self-test discovery blind spots so a requested self-test lane
  fails before execution when the expected package test asmdefs, categories, or
  lane test counts are not visible.

### Changed

- Released `v0.3.19` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.18

Release tag: `v0.3.18`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.18
```

### Added

- Added catalog-backed `project_action` scenario steps as a Unity-native
  scenario contract. Unity now resolves `project_actions.yaml`, enforces
  explicit approval for mutating actions, and executes the declared
  `project_defined_hook` without requiring host-side scenario rewriting.
- Added host-side `project_action` scenario preflight so MCP tools and wrapper
  commands can fail early with the same mutation and catalog diagnostics before
  dispatching to Unity.
- Added host-side project action tools and commands for listing and invoking
  catalog-backed project actions.
- Added artifact registry/report helpers for project validation pipelines that
  need stable report artifacts without importing them into Unity `Assets`.
- Added regression coverage for typed project action scenario expansion,
  mutation approval guards, `payloadJson` support, artifact registry helpers,
  and Unity-side raw `project_action` normalization.

### Changed

- Updated scenario schemas and docs so `project_action` is documented as a
  Unity-side contract with host preflight, rather than a host-only authoring
  convenience.
- Released `v0.3.18` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.17

Release tag: `v0.3.17`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.17
```

### Added

- Added `sync_release_version.py` to synchronize package metadata, server
  metadata, package manifest templates, and current release-facing docs from the
  package version source of truth.
- Added `check_release_version_consistency.py` and host-suite coverage so stale
  current-version references fail before release tagging.

### Changed

- Released `v0.3.17` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.16

Release tag: `v0.3.16`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16
```

### Added

- Added Unity bridge/status compiler diagnostics:
  `script_compilation_failed`, `compiler_error_count`,
  `recent_compiler_diagnostics`, and `compiler_diagnostics_source`.
- Added host-side compile-red fail-fast for EditMode tests, PlayMode tests,
  Play Mode transitions, and scenario runs before long editor-idle waits.
- Added operator-visible pre-dispatch progress phases: `activation`,
  `wait_for_idle_before`, `dispatching`, `waiting_for_response`, and
  `wait_for_idle_after`.
- Added scenario DSL dependency and cleanup support through `dependsOn`,
  `runIfStepPassed`, and `cleanupSteps`.
- Added compact scenario wait heartbeat output that reports active step, first
  failed step, wait deadline, remaining seconds, and editor health context.
- Added a visual Codex Desktop custom MCP setup guide with sanitized screenshots
  and guidance for natural Unity requests through the `xuunity_light_unity`
  server.

### Changed

- Scenario `stopOnFirstFailure` now jumps to cleanup steps when configured, so
  project state can be restored even after the scenario body fails.
- Released `v0.3.16` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.15

Release tag: `v0.3.15`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.15
```

### Changed

- Added license-aware batch lane selection: `license-capabilities`,
  `unity_license_capabilities`, `--batch-fallback-mode auto|off|require-batch`,
  GUI fallback summaries, and Unity-side `unity.build_player` for player-build
  fallback when real batchmode is blocked.
- Added `XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex|claude|auto` for wrapper
  helper resolution so Codex contexts prefer `.codex-tools` without breaking
  Claude-side `.claude-tools` installs.
- Documented optional Codex/Codex-style MCP client wiring for trusted local
  Unity projects.
- Released `v0.3.15` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.14

Release tag: `v0.3.14`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14
```

### Changed

- Released `v0.3.14` package metadata with Unity `2021.3` as the default
  minimum and removed the hard `com.unity.test-framework` dependency.
- Added optional Test Framework capability wiring through asmdef Version
  Defines and `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY`.
- Added setup wizard commands and MCP tools for per-project setup planning,
  approved setup application, setup validation, and approved Test Framework
  installation.
- Added capability statuses for optional test support, including missing and
  too-old dependency states that do not make core MCP health fail.
- Added closed-editor batch lifecycle hardening: explicit editor-close
  verification, process visibility diagnostics, `request-editor-quit
  --wait-for-exit`, and `restore-editor-state --require-closed`.
- Hardened public source-root/package-mode selection so the wrapper resolves the
  operation package source before generic `AIRoot/templates` paths.
- Fixed installed-helper setup planning so the default Git UPM dependency uses
  the package metadata version instead of falling back to `v0.0.0`.
- Added a README install simulation audit covering single-project, hub,
  mixed-version, nested-repo, and optional Test Framework setup paths.
- Added README guidance for collecting a sanitized chat retro before opening a
  GitHub issue about MCP setup or automation failures.
- Added an install-specific retro prompt for collecting structured MCP setup
  evidence before opening a GitHub issue.
- Changed `prodmode` to pin the published package release tag, such as
  `#v0.3.14`, instead of a raw source commit SHA.

## 0.3.13

Release tag: `v0.3.13`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.13
```

### Changed

- Restored Git UPM as the default production package source for project setup.
  `init_xuunity_light_unity_mcp.sh --enable-project` now enables the bridge
  without rewriting `Packages/manifest.json`.
- Kept local `file:` package wiring behind explicit wrapper mode switches only:
  `devmode` for local MCP package iteration and `prodmode` for returning to the
  published Git-backed source.
- Updated project-package alignment checks so a Git-pinned dependency is treated
  as the default healthy production state instead of warning about local-source
  expectations.
- Added a reusable clean-project Android APK smoke runner that creates a Unity
  project, installs the package from Git UPM, proves MCP readiness, restores
  the editor session, and runs a regular Unity batch APK build.
- Added Android Build Support preflight reporting for the clean-project smoke
  runner, including a structured fail-fast summary and an explicit
  `--allow-no-android` MCP-only readiness mode.
- Updated installer docs, client docs, AI integration docs, smoke contracts,
  and package examples to document the Git-default / devmode-only package
  source model consistently.

## 0.3.12

Release tag: `v0.3.12`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12
```

### Changed

- Moved the Unity package from `templates/unity-package` to the registry-native
  `packages/com.xuunity.light-mcp` path.
- Updated package metadata so Unity Package Manager and future package registries
  can identify the canonical package directory as `packages/com.xuunity.light-mcp`.
- Updated Git UPM install examples, local `file:` package examples, package
  discovery, installer wiring, wrapper `devmode` / `prodmode`, workflow
  templates, package manifests, and tests to use the new package path.
- Added the README preview banner asset and refreshed top-level install
  messaging around the new package path.

### Migration Notes

- New installs should use:
  `https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12`
- Local MCP development should use:
  `file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp`
- Projects pinned to `v0.3.11` can continue using
  `templates/unity-package`; that old path is now migration-only.
- To migrate a Unity project, replace
  `?path=/templates/unity-package#v0.3.11` with
  `?path=/packages/com.xuunity.light-mcp#v0.3.12`, remove the
  `com.xuunity.light-mcp` entry from `Packages/packages-lock.json`, and let
  Unity re-resolve packages.

### Notes

- OpenUPM publication is still pending; Git UPM is the supported install route
  for this release.
- The package remains editor-only and disabled by default, with no player-build
  footprint by default.
- Post-tag documentation refinements may exist on `master`; the package release
  tag for Unity consumers remains `v0.3.12`.

## 0.3.11

- Added wrapper help and agent workflow guidance for MCP `devmode` and `prodmode` package-source switching.
- Added client-specific MCP payload examples, structured evidence schema, and machine-readable workflow templates for agent validation workflows.

- Replaced placeholder client docs with production-ready MCP configs for Claude Code, Claude Desktop, Cursor, Windsurf, Codex-style agents, and generic stdio MCP clients.
- Added reusable client config templates under `templates/clients/`.
- Added native Windows client config templates and `run.cmd`/`run.ps1` launchers.
- Replaced the zsh-only Unix launcher with a bash-compatible launcher for Linux/macOS.
- Expanded `docs/reference/FEATURES.md` with competitive differentiators and the full MCP/host helper surface.
- Clarified feature maturity levels, implementation evidence, and compatibility validation status in `docs/reference/FEATURES.md`.
- Clarified `docs/reference/COMPARISON.md` source confidence, maturity terminology, and validation caveats.
- Added `AndreySkyFoxSidorov/UnifiedUnityMCP` to `docs/reference/COMPARISON.md` as a broad but young Unity automation reference.
- Added `docs/agents/AGENT_WORKFLOWS.md` to close Priority 15 with production-grade example agent workflows for Unity validation, triage, scenario replay, SDK checks, batch lanes, recovery, and release closeout.
- Updated installer wording and Claude Code user-scope config generation for the production stdio path.

## 0.3.10

- Extracted XUUnity Light Unity MCP into a standalone public repository.
- Added landing README, `llms.txt`, discovery metadata, install guide, feature table, security model, glossary, and client setup docs.
- Updated package metadata to point at `FoxsterDev/xuunity-mcp`.
- Preserved detailed legacy implementation notes in `docs/reference/STATUS.md`.

## 0.3.9

- Added Claude MCP wiring and robust batch matrix parsing in the source package.
- Preserved the working host-side server, Unity editor package, smoke runners, and package self-tests from the previous public-core layout.
