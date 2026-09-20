# XUUnity Light Unity MCP Public Retro Registry

Status: active public registry
Last triage: 2026-09-20 (readiness/editor-close retro fully closed in current source)
Current release: `v0.3.78`

Update this file whenever a public-safe MCP retro is added, moved, renamed, or
deleted. Host-private and project-specific retros belong in the host's single
`<host-output-root>/Operations/XUUnityLightUnityMcp/Retros/` folder and must be tracked by that
host-local registry.

## Storage Rule

- Public-safe reusable MCP retro: store in this folder and register here.
- Private/project-specific/raw MCP retro: store in the host-local MCP retro
  folder.
- Do not create per-project MCP retro folders.
- Do not store MCP retros in broad report buckets.

## Registry Design

- `Active Public Retro Backlog / Needs Triage` is the place to find public-safe
  retros that still look like backlog, action candidates, or status-unclear
  public work.
- `Completed Public History` is the place to find reusable lessons already
  implemented, applied, superseded, or retained only for history.
- Prompt templates are listed separately and are not backlog items.

## Re-Evaluation 2026-09-20 (batch editor-close side-effect truth)

- Freshness covered clean local/fetched `master` at `5ce7f06`, the newest 30
  commits and 30 tags, GitHub Releases and version surfaces, both retro
  registries, status/roadmap/design records, source, and tests. The mandatory
  verdict-envelope, authoritative post-settle, UI semantic/path, and
  infrastructure-versus-product clusters remain implemented in `v0.3.77`.
- The only remaining item from the readiness retro was selected over broader
  SDK orchestration and lower-priority compact/token work because the default
  batch runner could close a live editor without reporting that lifecycle side
  effect in its result.
- Current source emits a machine-readable editor-close notice before compilation
  continues and preserves the verified process id, closeout classification,
  close path, and aggregate side-effect list. Missing recovery evidence remains
  explicitly unavailable. The readiness retro is now completed history.

## Re-Evaluation 2026-09-16 (Editor.log heuristic truth)

- Freshness covered clean local/fetched `master` at `a74caae`, the newest 30
  commits and 30 tags, all 56 public retro Markdown files, the public and
  host-private registries, status/roadmap/design records, source, and tests.
  The mandatory verdict-envelope, authoritative post-settle, UI semantic/path,
  and infrastructure-versus-product clusters remain implemented in `v0.3.76`.
- The remaining readiness P2 false-positive outranked the open batch-output,
  compact-envelope, and advisory de-duplication work: health diagnosis still
  treated the non-interactive `-accept-apiupdate` recovery flag as evidence of
  the dialog it prevents.
- Current source removes that inverted marker while retaining real API Updater
  evidence and labels all Editor.log diagnoses as heuristic pattern matches.
  The batch editor-close notice remains the only open item in that retro.

## Re-Evaluation 2026-09-12 (historical release evidence integrity)

- Freshness covered clean local/fetched `master` at `19dc37a`, the newest 30
  commits and 30 local tags, the Latest GitHub Release `v0.3.74`, release and
  version surfaces, both retro registries, status/roadmap/design records, source,
  and tests. One delegated GitHub query was network-blocked; the root repeated it
  through the authenticated host route and verified the same release and commit.
- The mandatory decision-verdict, authoritative post-settle, UI semantic/path,
  and infrastructure-versus-product failure clusters remain implemented. The
  complete licensing contention/channel/state cluster is released in `v0.3.74`;
  its host-private row was stale as active backlog.
- Release `v0.3.75` prevents the release-version synchronizer
  from relabelling older measured evidence as proof for a newer tag. Release
  docs now have an explicit historical-evidence marker, and the escaped
  rebuilt/cache plus compact-batch rows retain the releases that measured them.
- The lane-independent multi-project batch output selector, compact build/EDM4U
  envelopes, and mutation-advisory de-duplication remain separate open items.

## Re-Evaluation 2026-09-08 (rebuilt-versus-cache-hit evidence)

- Freshness covered clean local/fetched `master` at `facc2081`, the newest 30
  commits, latest 30 tags, release/version surfaces, both retro registries,
  status/roadmap/design documents, implementation, and tests. The registry's
  `v0.3.71` current-release marker was stale; `v0.3.72` is the released source
  line.
- The remaining P1 compile-evidence finding outranked the dead batch-output
  flag and compact build/EDM4U envelopes because a passing matrix could be
  mistaken for proof that recently changed code was actually rebuilt.
- `v0.3.73` closes that gap with Unity's assembly-started and
  assembly-not-required events. Direct and matrix results carry rebuilt/cache
  counts plus their evidence status/basis; compact MCP, batch, and
  multi-project summaries retain them, including bounded per-configuration
  matrix rows.
- Current-source package tests passed `161/161` on Unity `2022.3.62f3` and
  `161/161` on Unity `6000.0.58f2`; live compile responses on both versions
  returned measured nonzero rebuilt and cached counts with zero diagnostics.
- The decision-verdict envelope, authoritative post-settle verdict, UI
  semantic/path proof, and infrastructure-versus-product failure clusters
  remain implemented. The batch `--output` shape pin, compact build/EDM4U
  envelopes, and mutation-advisory de-duplication remain separate candidates.

## Re-Evaluation 2026-09-04 (principal review of `v0.3.63`-`v0.3.70`)

- An independent principal-level review of the `v0.3.63`-`v0.3.70` range was
  triaged finding by finding and fixed in `v0.3.71`. The corrections that
  changed product behavior: the editor-domain currency gate now mirrors Unity's
  own asset-import exclusions and converges after a settled forced refresh
  instead of blocking forever; background execution is opt-in and restores the
  project's value, because an editor-time `Application.runInBackground`
  assignment is `PlayerSettings`-backed and had been reaching consumers'
  `ProjectSettings.asset`; point-of-use liveness evidence no longer defaults to
  `editor_truth_confirmed`; and request attribution separates the operator's own
  CLI from another client session.
- The evidence gap the review named is closed at the source: the package
  self-test runner derives its assembly plan from the package instead of a
  hand-maintained filter, runs each planned assembly as its own request, and
  fails when one contributes no tests. That put the uGUI EditMode, uGUI PlayMode
  and TextMeshPro EditMode suites under execution proof; the TextMeshPro suite
  had never run in that lane.
- Release-notes errata for `v0.3.63`, `v0.3.66`, `v0.3.69` and `v0.3.70` are
  recorded in the `0.3.71` changelog section rather than left standing.
- Deliberately not done in a patch release: renaming the `playmode_throttled`
  token that serves both as a warning code and as a trust class, and unifying
  the two `result_trust_class` namespaces. Both are breaking renames; the whole
  published vocabulary is now one table in `docs/reference/GLOSSARY.md` so the
  next drift is visible.

## Re-Evaluation 2026-09-04 (compile-warning evidence)

- Freshness review covered the exact latest 30 commits, latest 25 local tags,
  all 59 remote tags, release/version surfaces, both retro registries, and the
  current status/roadmap/design records. `master`, `origin/master`, and fetched
  `master` aligned at `4fa8dad`; `v0.3.69` was the released baseline.
- The P1 warning-evidence finding in
  `2026-09-02_batch_summary_shape_and_compile_evidence_retro.md` is implemented
  in `v0.3.70`. Direct and matrix results count warning
  occurrences, deduplicate exact identities, retain bounded diagnostic rows,
  and preserve them through compact batch and multi-project summaries.
- The decision-verdict envelope, authoritative post-settle verdict, UI
  semantic/path proof, and infrastructure-versus-product failure clusters
  remain implemented. Rebuild-versus-cache-hit evidence, the dead batch
  `--output` flag, compact build/EDM4U envelopes, and mutation-advisory
  de-duplication remain separate open candidates.
- Current validation is green across focused host `211/211`, full host
  `1011/1011` with 14 expected skips, site UI `42/42`, and clean Unity
  `2022.3.62f3` and `6000.0.58f2` package EditMode `104/104` plus PlayMode
  `5/5`; each Unity lane also passed acceptance `9/9`, compile contract `2/2`,
  and verified closeout. Release metadata advanced to `v0.3.70`.

## Re-Evaluation 2026-09-03 (greenfield authoring)

### Greenfield hardening currency follow-up

- Both P1 findings in `2026-09-03_greenfield_hardening_operator_retro.md`
  are released in `v0.3.69` through one shared persisted
  `project_action_currency` preflight. Every typed/raw catalog action checks
  editor-domain currency before its hook; `requiresFreshAssets: true` actions
  first run and settle a forced AssetDatabase refresh.
- The same evidence is exposed by `unity_project_action_currency`,
  `unity_project_action_invoke`, and `unity_status_summary`. Runtime
  `Application.runInBackground` is enabled while the bridge is active, but
  native autofocus remains intentionally disabled and measured liveness stays
  authoritative.
- The compact build/EDM4U envelopes and mutation-advisory de-duplication remain
  the open P2 items from this retro. The optional focus operation and inline
  screenshot remain P3 and are not part of this release.

- All required P0-P2 findings from the greenfield scene-authoring retro are
  implemented in current source. UI reads/clicks, screenshots, and scenario
  steps carry point-of-use liveness/trust; screenshot and UI evidence names the
  Game View render target separately from `Screen.*`.
- The existing guarded `ui_click` scenario step is joined by `ui_exists` and
  `ui_get_text`. The host exposes the full scenario schema, accepts a
  project-scoped scenario file for validation, reports request-scoped console
  pressure on test verdicts, accepts scalar setup `projectRoot`, and provides
  an approval-gated project-hook scaffold. Project hooks can construct the
  shared mutation proof with `XUUnityLightMcpMutationDelta.Create(...)`.
- Local Unity `2022.3.67f2` and `6000.0.58f2` clean-consumer validation passes
  compile, interactive acceptance, core EditMode `99/99`, and PlayMode `5/5`;
  a uGUI-enabled Unity 2022 consumer passes the corrected package-runner
  EditMode lane `138/138`. The optional editor-focus mutation operation was not added: every
  affected result now
  names the safe focus/no-throttling remediation without broadening the MCP's
  editor-control authority. Full host discovery passes `1007` tests with `14`
  expected platform skips, including live loopback transport coverage.

## Re-Evaluation 2026-09-02 (`v0.3.66` release closeout)

- The mutation-trust/request-attribution retro's reusable tool findings are
  implemented, validated, and released in `v0.3.66`: applied project-hook
  mutations survive passive waits and lifecycle recovery without inviting a
  replay; every request carries a domain-reload-stable `client_session_id`;
  completed journal events carry the real editor PID; anchored log searches
  reject cross-process offsets and accept a bounded `maxSearchChars` recovery.
- The related scenario-authoring risk is closed by promoting a single plain
  project-hook `payload` object to `hookPayloadJson` and rejecting invalid or
  conflicting aliases. The dead-editor `ensure-ready` episode remains an
  operator error because the preceding status result already supplied the
  fail-closed recovery action; it is not carried as an unimplemented tool fix.
- Release evidence: host `992` passed with 14 expected platform skips, public
  site `42/42`, and clean Unity `2022.3.67f2` plus `6000.0.58f2` matrices passed
  EditMode `95/95` in uGUI and no-uGUI lanes, uGUI PlayMode 18 passed with one
  expected skip, and dependency-free PlayMode `5/5` with green post-settle
  compilation. Hosted Unity Package CI retains its documented license waiver.

## Re-Evaluation 2026-09-01

- Fetched `origin/master` and confirmed clean local `master`, `origin/master`,
  and `HEAD` at `a72c79b`. The review covered all 30 commits in the release
  window, 15 recent tags, nine release/version surfaces, all 52 public retro
  files, the host-private registry, current status/roadmap/design records, and
  the relevant source and tests. `v0.3.63` is the current released source line.
- The decision-verdict envelope, authoritative post-settle verdict, UI
  semantic/path proof, and infrastructure-versus-product failure clusters
  remain implemented. Every track from the August 30 Hub/licensing retro was
  implemented and released in `v0.3.63`, so that retro moves to completed
  history rather than remaining an open umbrella.
- The highest-ROI remaining coherent slice is the UI-selector truncation false
  negative observed independently in the August 12 and August 26 consumer
  retros. Current source makes direct and scenario `unity_ui_click` return
  `ui_selector_search_truncated` when a capped tree cannot prove absence or
  uniqueness, preserves the searched scope/node budget/reason in the receipt,
  lets scenario authors set `maxDepth`/`maxNodes`, and keeps
  `ui_node_not_found` only for a complete zero-match search.
- Click-causality attribution, readiness-log attribution, package-removal
  verification, active-configuration reporting, SDK orchestration,
  token-accounting, and live Windows/Linux proof remain separate backlog items.

## Re-Evaluation 2026-08-29

- Fetched `origin/master` without mutating tags and confirmed local `master`,
  `origin/master`, and `HEAD` at `a794216`. The latest published release before
  this cycle was `v0.3.61` at `0a31027`; the next unused semantic patch is
  `v0.3.62`. A pre-existing local/remote `v0.3.26` tag mismatch prevents a
  blanket `git fetch --tags`, so this cycle preserves both immutable refs and
  fetches the default branch without tags.
- The decision-verdict envelope, authoritative post-settle verdict, UI
  semantic/path proof, and infrastructure-versus-product failure cluster remain
  implemented. The August 26 import-worker slice is released in `v0.3.60`, and
  the August 27 editor-launch/GUI-lane slice is released in `v0.3.61`.
- Current `master` contains one coherent unreleased change: the fail-closed
  consumer release rollout helper derived from the `v0.3.60` execution retro.
  It reconciles the project denominator, refuses unsafe preflight or a dirty
  canary, proves the published package on the canary before fan-out, persists a
  resumable atomic ledger, bounds worker authority, and re-verifies process
  identity before root cleanup. This observed release-lifecycle trust risk
  outranks starting a second UI, SDK, or token-efficiency feature in this cycle.
- The active UI selector, click-causality, readiness-log, package-removal,
  Editor.log-window, SDK-orchestration, and token-efficiency residuals remain
  open or partial as recorded. None is broadened into the `v0.3.62` slice.

## Re-Evaluation 2026-08-26

- Fetched `origin/master` and confirmed it matches clean local `master` at
  `22b7641`; `v0.3.59` is the current published release. The decision-verdict,
  authoritative post-settle, UI semantic/path, infrastructure/product failure,
  liveness, readiness, and anchored-grep clusters remain implemented.
- A host-private August 12 incident exposed a higher-priority false-green than
  the remaining SDK orchestration and token-efficiency work: a Unity Asset
  Import Worker wrote bridge state that looked healthy while the main editor's
  compile state was different. Current source closes the public-safe P0 cluster
  as one bridge-ownership slice: workers refuse bootstrap before side effects;
  state and journal records carry writer provenance; the host rejects live
  non-main writers, refuses runtime dispatch, and reports their compile health
  as unknown rather than clean.
- The source retro's UI selector truncation, click-causality, package-removal,
  readiness-log, and operator-contention follow-ups remain separate P1/P2 work.
  SDK GUI/batch/portfolio orchestration remains open but broader; no unrelated
  candidate was pulled into this slice.

## Re-Evaluation 2026-08-23

- After fetching, `master` and `origin/master` align at `8825610`; the latest
  release remains `v0.3.58` at `de7c160`. The 2026-08-20 readiness P0/P1 slice
  is committed at the current tip, so its former "uncommitted" status was
  stale. The decision-verdict, authoritative post-settle, UI/path,
  infrastructure classification, liveness, and readiness clusters remain
  implemented.
- Current uncommitted source closes both 2026-08-19 anchored-grep P1 items.
  Grep keeps the fixed window adjacent to the resolved anchor, promotes an
  explicit search verdict/window direction, and treats a partial zero-match as
  inconclusive with recovery. Complete anchored zero-matches remain real
  negatives, truncation-boundary regex safety is preserved, and console tail
  retains recent-tail behavior.
- Regression evidence for this slice is green: 213 focused host tests; the
  Unity 2022.3.62f3 package lane (14/14 EditMode and 5/5 PlayMode); and the
  Unity 6000.0.58f2 real-consumer post-change suite, including 6/6 compile
  matrix lanes, 10/10 acceptance steps, contract, lifecycle, churn, and
  project-action consistency. The full host suite ran 932 tests; its only six
  errors were sandbox-denied loopback binds in the TCP framing fixture, outside
  the changed Editor.log surface.
- The retro remains active only for its P2 window-control/import-freshness and
  P3 benign-settle-warning residuals. SDK GUI/batch/portfolio orchestration is
  still a broader P1; token-efficiency and live Windows/Linux proof remain P2.

## Re-Evaluation 2026-08-20

- `master` and `origin/master` align at `a8db49f`; the latest release is
  `v0.3.58` at `de7c160`. The decision-verdict envelope, authoritative
  post-settle truth, UI/path proof, infrastructure/product failure split, and
  the 2026-08-17 liveness/compile-gate cluster are implemented. Release notes
  record local Unity 2022 and 6000 package regression for the latter, so its
  stale active row moves to completed history; CI-recorded Unity proof remains
  a release-infrastructure waiver, not unfinished retro implementation.
- Current uncommitted source closes the 2026-08-20 readiness P0 and both P1
  items. Log observations no longer assert an unmeasured compile failure;
  transient attach/import/identity churn keeps polling and uses non-destructive
  recovery; persistent failures carry condition-specific codes,
  `compile_state=unmeasured`, and a consistent blocking readiness prerequisite.
  Focused host tests and live Unity 2022 package plus Unity 6000 full consumer
  regression pass. The heuristic-confidence/API-updater and batch-close notice
  P2 items remain open.
- The 2026-08-19 anchored truncation finding remains open and is now the highest
  bounded false-negative/verdict-quality candidate. SDK orchestration remains a
  broader P1; token-efficiency and live Windows/Linux proof remain P2.

## Re-Evaluation 2026-08-11

- `master`, `origin/master`, and release `v0.3.56` align at `487b07e`. The decision-verdict envelope,
  authoritative post-settle truth, UI/path proof, infrastructure/product failure split, and the structural
  compile-diagnostic fallback all remain released and closed.
- The former UTC parser-consolidation design is now implemented in current source: `server_core` owns the
  timezone- and DST-independent conversion, while heartbeat, journal, scenario, operation-evidence, and
  Editor.log consumers preserve their established absent-value contracts. Focused hostile-timezone coverage
  exercises every consumer; no payload contract changed.
- SDK GUI/batch/portfolio orchestration remains the highest broad P1 backlog but exceeds one safe grooming
  slice. The token-efficiency and live Windows/Linux proof tails remain P2. No private/project-specific backlog
  was promoted.

## Re-Evaluation 2026-08-14

- `master` and `origin/master` align at `29b3484`; the latest release remains `v0.3.56` at `487b07e` before this
  uncommitted grooming slice. The decision-verdict, authoritative post-settle, UI/path, infrastructure
  classification, and structural compile-diagnostic clusters remain closed.
- The previously partial test-result-accounting design is now implemented and Unity-validated in current source:
  direct test payloads retain callback-time and host-idle Play Mode observations, disclose source and disagreement,
  and atomically reconcile the matching written persisted test result. Test verdicts and callback-derived totals
  remain unchanged. Full/compact recovery summaries preserve the same fields, legacy artifacts are source-labeled,
  lifecycle churn is consistent with the settled-state trust class, and automated smoke compares the matching
  persisted result. Focused host, Unity 2022 local-package, and Unity 6000 consumer compile/scenario smoke evidence
  passed; the Unity 6000 package-test filter's zero-match is a consumer discovery gap, not package-test evidence.
- SDK GUI/batch/portfolio orchestration remains the highest broad P1 backlog; it is still too large for one safe
  vertical slice. Token-efficiency and live Windows/Linux proof remain P2.
- Task 0 registry normalization (same day, later): the slice above is now committed at `b13cb69`. The design-plan
  history was reconciled against current source: the two SDK rows no longer list `sdk.package_restore` as unbuilt
  (complete and fail-closed, host tests `5/5`), the enterprise readiness row records the locally closed B5
  runtime-interaction proof, the read-only UI-primitives rows reflect the uGUI/TMP read surface shipped 2026-07-30,
  and test-result accounting is removed from the open-priority summary. No active retro row changed status.
- Portfolio slice S1 (same day, later): scenario refresh-settle timeouts now carry Unity-side settle
  evidence captured at the timeout instant and a host-side `refresh_timeout_recovery` block that classifies the
  timeout (package settle, compile/import churn, busy editor, incomplete idle confirmation, lost final accounting,
  `editor_failure` from host health, or `unclassified_legacy_payload` for older-package results), names a concrete
  recovery command, and states that the operation may have completed; the verdict-level action becomes
  `request_status_summary_then_compile_gate` while the editor is reachable. Host suite `832` passed with 13 expected
  platform skips; live fault injection passed on a Unity `2022.3` development-system lane (current-source package,
  EditMode `75/75`, PlayMode `18` passed with one expected skip) and on a Unity `6000.0` real-consumer editor running
  the released `v0.3.56` package (legacy classification with guidance intact). Released applied-mutation and cleanup
  verdict actions are unchanged.
- Portfolio slice D1 (same day, later): automated Unity package CI and a release tag gate. The `Unity Package CI`
  workflow compiles the package and runs its EditMode/PlayMode self-tests on Unity `2022.3` and `6000.0` through
  pinned `unityci/editor` images in `ugui` and `no-ugui` consumer lanes scaffolded by a tested Python script; a
  missing Unity license secret fails the preflight loudly instead of skipping. `check_release_ci_gates.py` blocks
  tag preparation until `Integration Tests`, `Unity Package CI`, and `Discovery Checks` have a completed successful
  `push`/`workflow_dispatch` run for the release SHA, wired into the publishing checklist, the release skill, and
  the tag-push `Release Tag Gate` workflow; contract tests pin workflow names, version pins, lanes, and
  license-failure behavior. Local CI-equivalent batch `-runTests` proof passed all four version × lane combinations
  (no-uGUI: EditMode `75/75`, PlayMode `5/5`; uGUI: EditMode `112/112`, PlayMode `18` passed with one expected skip
  on both lines); a live gate run against the real repository correctly blocked on the not-yet-pushed workflow while
  passing the two existing gates. Host suite `872` passed with 13 expected platform skips. First green GitHub run
  requires maintainer-configured Unity license secrets (external dependency recorded in
  `docs/operations/UNITY_PACKAGE_CI.md`).
- Portfolio slice P1 (same day, later): byte-bounded console tail. `unity_console_tail` / `request-console-tail`
  and the `console_tail` scenario step enforce a deterministic `maxPayloadBytes` ceiling (default `16384`, `-1`
  raw) in the Unity bridge, with a host-side fallback annotating older-package payloads, oldest-first drops, an
  explicit newest-item truncation marker, full accounting fields (`byte_budget_enforced_by`,
  `byte_budget_truncated`, `items_dropped_for_byte_budget`, `newest_item_truncated`, `payload_bytes_estimate`),
  and `unity_console_grep` named as the compact recovery tool on truncation. 18 focused host tests; host suite
  `890` passed with 13 expected platform skips; live proofs on Unity `2022.3` and `6000.0` (current-source
  bridge-enforced truncation with identical accounting on both lines, unbounded `-1` raw recovery, and package
  EditMode `81/81` through the bridge on each), with both scratch editors closed via verified process exit.
- Portfolio slice P2 (same day, later): compact scene/view envelopes. `unity_scene_open`, `unity_scene_snapshot`,
  and `unity_game_view_configure` now default to compact operation envelopes (duplicated host lifecycle evidence
  dropped, scene transition/content and resolved view preserved, `root_object_count` added) with
  `includeFullPayload=true` opting back into the full bridge payload — completing the compact-by-default contract
  across the interactive scene/playmode/view loop; the screenshot image-byte budget (`imageBudgetBytes`, default
  `48000`) is documented in the public references. 7 focused host tests; host suite `897` passed with 13 expected
  platform skips; live end-to-end proofs through the real bridge on Unity `2022.3` and `6000.0` (identical
  envelopes on both lines; scene-open response ~12,000 → ~540 bytes with identical decision content; full opt-in
  verified; editor-open attribution retained). Both scratch editors closed via verified process exit.

## Re-Evaluation 2026-08-08

- `master`, `origin/master`, and release `v0.3.56` were checked through current
  `4861bbc`. The decision-verdict envelope, authoritative post-settle truth,
  UI/path proof, infrastructure/product failure split, and all seven items from
  the 2026-08-03 interactive evidence retro remain implemented. The August 3
  row was stale as active backlog and moves to completed history.
- The 2026-08-04 offline-status retro's required-argument, typed-refusal,
  editor-open attribution, and stale-state liveness items shipped through
  `v0.3.56`; no item reopened.
- The August 6 structural compile-diagnostic fallback was only partial at
  `5b96ac9`: it ran only when the C# diagnostic list was empty, so it missed the
  reported stale-C#-row case, and its log read was not session-scoped. Current
  source completes that slice with bridge-generation anchoring, structural-first
  merge/deduplication, typed failure fields, compact-envelope preservation, and
  stale-log refusal. A Unity `2022.3.62f3` duplicate-reference fault injection
  returned the typed verdict and recovered to authoritative green after cleanup.
- UTC timestamp parser consolidation remains an unscheduled small refactor. SDK
  orchestration and token-efficiency residuals remain open but rank below this
  false-root-cause validation defect.

## Re-Evaluation 2026-08-02

- `master`, `origin/master`, and release tag `v0.3.51` align at `b33ec84`.
  The nine reusable improvements from the 2026-07-31 UI acceptance retro are
  released, so that retro moves from active backlog to completed history.
- Current source closes the reusable runtime-interaction execution gap with a
  uGUI-gated PlayMode package assembly. The guarded-click delivery and refusal
  tests pass as part of `7/7` PlayMode lanes on Unity `2022.3.62f3` and
  `6000.0.58f2`; a clean no-uGUI project retains the `5/5` core lane.
- Per-consumer fixtures and interaction scenarios plus independent vision
  judges remain host-private adoption work, not a reusable public toolchain
  residual. Decision verdicts, authoritative post-settle truth, UI-smoke/path
  proof, and infrastructure-vs-product classification remain closed.

## Re-Evaluation 2026-07-31

- First post-release consumer run of the `v0.3.49` UI acceptance slice is
  recorded in
  `2026-07-31_shipped_ui_acceptance_toolchain_first_run_retro.md`. The slice
  holds end to end and stays in completed history; four implementation
  residuals are now tracked as an active row. The P0 is mutation-receipt
  honesty: `set_serialized_field` reported `status: "applied"` for an enum
  write where `before == after`, because enum properties are index-addressed
  and out-of-range input is clamped rather than rejected. That defeats the
  other mutation guardrails, which all assume the change report is truthful.
- Same day, later: all nine of that retro's priority improvements are
  implemented in current unreleased source and validated on a live editor
  (99 EditMode tests: 98 passed and one graphics skip on `6000.0.58f2`; 694 host tests; parity
  baseline regenerated). P1.3 landed in an adjusted form after live runs proved
  the inferred drift check refuses legitimate writes — see the active row for
  the reasoning. The row stays active pending release and pending the
  per-consumer Play-mode interaction/fixture lanes, which no toolchain change
  can supply.
- `v0.3.49` is now the released `master`/`origin/master` line. It implements
  every reference-driven UI acceptance slice added on 2026-07-30, including
  the reference comparator, fixture contract, semantic/prefab inspection,
  isolated render, guarded mutation/click, AI-vision review, and device-lane
  contract. The July 30 row and the overlapping July 17 prefab-authoring row
  were stale active entries and move to completed history.
- Current source completes `unity.sdk.package_restore`: a closed-project batch
  lane waits for an idle-stable registered Package Manager graph, atomically
  records package ids/versions and dependency-XML plus manifest/lock hashes,
  and fails closed unless the Unity process exit is proven. GUI admission,
  batch EDM4U resolve, and portfolio orchestration remain the active SDK
  residual.
- Decision verdicts, authoritative post-settle truth, UI-smoke/path proof, and
  infrastructure-vs-product classification remain implemented; none reopened.

## Re-Evaluation 2026-07-29

- No release tag newer than `v0.3.47` exists; `HEAD`, `master`, and
  `origin/master` align at `0d3a460`, which commits the prior Android-target
  precondition slice.
- Current source completes the typed P0.2b resolver-freshness vertical slice:
  `unity.sdk.android_resolve` uses EDM4U's callback API, requires active Android
  plus Android Build Support, waits for hash-stable generated outputs, and
  verifies explicit expected coordinates before returning
  `trust_class=decision_grade` and `decision_ready=true`.
- Callback failure, callback loss/timeout, missing or unstable generated output,
  and missing expected coordinates all fail closed. The older
  `unity.edm4u.resolve` fire-and-report contract remains available and explicitly
  non-decision-ready.
- Fresh proof passes focused host protocol/parity/atomicity tests `77/77`;
  current-source Unity `2022.3` package tests (`24/24` EditMode and `5/5`
  PlayMode); a real callback failure and a local-Maven callback success with
  stable SHA-256/new-coordinate proof; a development-system consumer
  (`14/14` EditMode, `5/5` PlayMode); and a Unity `6000.0` consumer compile
  matrix `6/6`, acceptance `10/10`, contract, lifecycle, and catalog route.
- `unity.sdk.package_restore`, GUI admission, batch resolve, and portfolio
  orchestration remain open. The decision-verdict, post-settle truth, UI/path
  proof, and infrastructure classification cluster remains complete.

## Re-Evaluation 2026-07-27

- No release tag newer than `v0.3.47` exists; `master` and `origin/master` are
  aligned at `a32bb51`, which commits the prior generated-diff artifact
  registration work.
- Current source closes the smallest remaining Android-target false-positive:
  `unity.edm4u.resolve` refuses Android menu execution unless
  `BuildTarget.Android` is active and Android Build Support is loaded.
- Successful resolver-request payloads now expose the confirmed target while
  retaining `resolver_output_freshness=unproven` and `decision_ready=false`.
  This is P0.2a, not the full typed resolver verdict.
- Fresh validation passes focused host tests `61/61`, the full host suite
  `476/476` with 13 expected skips, Unity `2022.3` current-source package tests
  (`20/20` EditMode and `5/5` PlayMode), and Unity `6000.0` compile `6/6`,
  acceptance `10/10`, and refresh/compile contract coverage. The Unity `6000.0`
  PlayMode and focused EditMode requests were blocked by a pre-existing unsaved
  consumer scene, which was preserved; this is non-blocking for the changed
  editor-only target guard.
- Engine-driven stable-hash plus new-coordinate dependency proof remains the
  highest open SDK false-positive risk. GUI admission, batch resolve, and
  portfolio orchestration remain later phases. The decision-verdict,
  post-settle truth, UI/path proof, and infrastructure classification cluster
  remains complete.

## Re-Evaluation 2026-07-25

- No release tag newer than `v0.3.47` exists; current `master` and
  `origin/master` were aligned at `b9af661` before this run.
- The final P0.1 SDK generated-diff obligation is implemented in the working
  tree: every published passing or failed report is registered as
  `sdk_generated_diff_report` evidence with a content hash, compact verdict
  metadata, and direct registry pointer.
- Validation passes focused guard/protocol/parity tests `80/80`, the full host
  suite `476/476` with 13 expected skips, Unity `2022.3` package EditMode
  `14/14` plus PlayMode `5/5`, and the Unity `6000.0` compile `6/6`,
  acceptance `10/10`, contract/lifecycle, project-action consistency, and live
  five-file guard-registration routes.
- Typed Android target enforcement plus engine-driven resolver-output freshness
  is now the highest open SDK false-positive risk. GUI admission control,
  batch resolve, and portfolio orchestration remain later coherent slices.
- The already-released decision-verdict, post-settle truth, UI/path proof, and
  infrastructure classification cluster remains complete; no candidate was
  reopened.

## Re-Evaluation 2026-07-23

- The typed project-action mutation-delta trust contract is now committed at
  `4e16389`; no release tag newer than `v0.3.47` exists.
- Fresh validation passes `475/475` host tests with 13 expected platform skips,
  Unity `2022.3` package EditMode `14/14` plus PlayMode `5/5`, and the Unity
  `6000.0` compile `6/6`, acceptance `10/10`, contract, lifecycle/final-health,
  and project-action consistency route.
- The candidate ordering is unchanged: typed SDK resolver freshness and SDK
  artifact registration remain the larger P1 follow-ups; project-hook
  mutation-delta adoption/raw-scenario warnings remain bounded follow-ups; and
  prefab authoring/render plus token polish remain lower priority.

## Re-Evaluation 2026-07-21

- The prior passive-readiness slice is committed at `7056894`; no tag newer
  than `v0.3.47` exists.
- Current-source `unity_project_action_invoke` now requires a valid,
  non-destructive `xuunity.mutation-delta.v1` for a passed mutating action to be
  decision-ready. Missing/invalid proof and removals/count shrink are explicit
  trust warnings while Unity execution success remains factual.
- Validation passes `475/475` host tests (13 expected platform skips), Unity
  `2022.3` package EditMode `14/14` + PlayMode `5/5`, and the Unity `6000.0`
  compile/scenario/lifecycle/project-action route.
- Project-hook adoption and catalog-aware warnings on arbitrary raw
  `project_action` scenario envelopes remain open. Prefab read/author/render
  remains P2; typed SDK resolver freshness remains the larger P1 follow-up.

## Re-Evaluation 2026-07-19 (what is still actual for the end user)

The end user of this MCP is the AI-agent operator/developer who drives Unity
validation through it. Value here is ranked by how much a lesson reduces
false-positive validation, false-negative validation, token/result cost, or
install/readiness failure.

Re-checked against released `v0.3.51` plus current source on 2026-08-02. The
reference-driven UI acceptance residuals are released, and the generic runtime
interaction path now has local PlayMode execution proof. Open public themes, in
priority order:

1. **P1 - SDK / EDM4U rollout validation lane (highest open ROI).**
   `2026-05-14_sdk_rollout_mcp_portfolio_retro.md`. A typed SDK-resolver lane
   with an active-Android-target precondition and resolver-freshness check, a
   generated-Gradle diff guard, a GUI process pool with quit-and-wait closeout,
   and a portfolio SDK-validation summary were the missing proof chain in
   `v0.3.44`. The generated-diff guard, callback-backed typed resolver, and
   closed-project package restore are implemented through current source. GUI
   admission, batch resolve, closeout orchestration, and portfolio summary
   remain; the orchestration tail is now the outstanding reusable work.

2. **P2 - Token-efficiency tail.**
   `2026-06-02_token_efficiency_response_envelope_retro.md` and
   `2026-06-11_token_accounting_and_fast_path_retro.md`. Compact-by-default
   envelopes are fully shipped (scenario, refresh, compile, test, status,
   `ensure-ready`, and batch, each with an `includeFullPayload` opt-in). What
   remains is broader multi-project compact ceilings, a real token-accounting
   ledger, a one-shot package-pin verifier, and fast-path prompt profiles.

3. **P2 - Cross-platform live-host proof.**
   `2026-06-17_windows_setup_failure_retro.md`. The Windows helper root causes
   are fixed and CI-exercised (MCP stdio e2e, installed delegate, PowerShell
   quickstart, file-IPC simulator, hostile codepage). A live Windows/Linux host
   session with a real Unity editor still needs execution proof. This is a
   ROADMAP Phase 3 breadth item, not a code gap.

No longer active (shipped and moved to completed history this pass): PlayMode
lifecycle-reset trust classification, UI-smoke semantic verdicts + path
coverage, batch-compile reliability + operator ergonomics, devmode batch
lifecycle, manual-open duplicate-launch guard, first-open Unity 6000
API-Updater modal + console-source diagnostics, the batchmode-blind
editor-startup freshness qualifier, the applied-mutation-vs-settle-timeout
verdict, bridge-declared-not-enabled auto-enable on first `ensure-ready`, and
the entire Windows install root-cause set (python3 delegation, UTF-8 BOM,
`os.kill` PID liveness, WSL/Windows discovery, process-kill safety).

## Active Public Retro Backlog / Needs Triage

| Date | File | Scope | Registry Status | Why It Is Not Completed History |
| --- | --- | --- | --- | --- |
| 2026-09-02 | `2026-09-02_batch_summary_shape_and_compile_evidence_retro.md` | Sweep-runner verdict versus the wrapper's default compact batch payload shape, plus compile-warning and rebuilt-versus-cached evidence surfaces | **P0 and summary-artifact P2 released in `v0.3.67`; warning-evidence P1 released in `v0.3.70`; rebuild/cache P1 released in `v0.3.73`; output-shape P2 remains** | `v0.3.73` adds Unity-measured `rebuilt_assembly_count` / `cached_assembly_count` evidence to direct, matrix, compact batch, and multi-project summaries. The historical measurement is now protected from release-sweep relabelling. The batch `--output` selector is consumed by direct batch commands, but pinning a lane-independent full/compact shape through the multi-project runner remains open. |
| 2026-08-26 | `2026-08-26_import_worker_bridge_ownership_retro.md` | Import-worker ownership plus UI selector, click-causality, readiness-log, package-removal, and contention follow-ups | **P0 released in `v0.3.60`; selector-truncation P1 implemented in current source; other follow-ups open** | Import-worker bridge ownership and provenance are released. The two-sighting capped-selector false negative now has a typed inconclusive result with scope/budget evidence and bounded recovery; a partial match is also refused because uniqueness is unproven. Non-causal `state_changed`, readiness-log attribution, package-removal verification, and operator-contention follow-ups remain separate work. |
| 2026-08-19 | `2026-08-19_anchored_scope_truncation_and_verdict_field_ranking_retro.md` | Console-lane verdict ranking: a truncated search scope that reports zero matches as a negative, and an anchored scope whose fixed cut kept the tail rather than the anchor-adjacent head | **both P1 items implemented in current source; P2/P3 residuals open** | Current source keeps anchored grep windows beside the anchor, exposes `search_verdict`/reason, direction and truncation at the top level, and makes partial zero-matches explicitly inconclusive with a recovery action and partial-scope trust class. Complete anchored zero-matches remain `not_matched`; console tail keeps recent-tail behavior. Focused regression owns early-boot recovery, boundary safety, absolute numbering, negative/inconclusive ranking, and tail compatibility. Remaining: P2 user-controlled window/import-freshness hints and P3 benign settle-warning downgrade. **Second sighting 2026-09-02**: ranking behaved correctly on an anchored 2.16 MB scope with 1.66 MB unsearched, and the answer still required a shell fallback, so the P2 window residual is proposed for P1. |
| 2026-05-14 | `2026-05-14_sdk_rollout_mcp_portfolio_retro.md` | SDK/EDM4U rollout validation lane: typed resolver preconditions, package restore, generated-Gradle diff guard, GUI process pool + quit-and-wait closeout, portfolio SDK summary | **generated-diff + typed resolver/package-restore P0 complete in current source; orchestration remains P1** | `v0.3.45`-`v0.3.48` shipped and hardened generated-diff plus callback-backed Android resolution. Current source adds fail-closed closed-project `unity.sdk.package_restore` with an idle-stable registered package graph, atomic package/dependency receipt, and proven process exit. Still open: GUI process pool, batch resolve, closeout orchestration, and portfolio summary. Device lanes remain ROADMAP Wave 5. |
| 2026-06-02 | `2026-06-02_token_efficiency_response_envelope_retro.md` | Response-envelope token efficiency: compact-by-default across MCP tool surfaces | mostly implemented; P2 residual | Compact-by-default shipped `v0.3.32`-`v0.3.44` for scenario, refresh, compile, build-config compile, test, `unity_status_summary`, `ensure-ready`, and batch CLI, each with `includeFullPayload`/`--output` opt-in (STATUS.md "Compact MCP envelopes"). Remaining (ROADMAP.md "Phase 2" residual): broader multi-project compact ceilings, a token ledger, and fast-path profiles. |
| 2026-06-11 | `2026-06-11_token_accounting_and_fast_path_retro.md` | Token-accounting ledger, one-shot package-pin verifier, fast-path prompt profile | partial; P2 | The biggest win (compact output) shipped through `v0.3.40`/`v0.3.44`, and the fast path is documented in `docs/agents/PACKAGE_BUMP_FAST_PATH.md`, but no token-accounting ledger, one-shot verify-package-pin verifier, or runner token-budget hints exist in source or ROADMAP/STATUS. Overlaps the response-envelope row above as the token-efficiency tail. |
| 2026-06-17 | `2026-06-17_windows_setup_failure_retro.md` | Native Windows setup failure postmortem; residual = live Windows/Linux host proof | Windows root causes fixed + CI-exercised in `v0.3.43`; live-host proof still open (P2) | The concrete Windows helper failures (path-with-spaces, ExecutionPolicy, `python3` delegation, PID liveness, discovery) are fixed and CI-exercised end to end. STATUS.md still marks a live Windows/Linux host session with a real Unity editor as needing execution proof (ROADMAP Phase 3 breadth). This row now tracks that single remaining cross-platform proof item; the Windows install root-cause retros (2026-06-09 v1/v2, 2026-06-10) are completed history. |

> Re-confirmed 2026-07-15 against `v0.3.45` plus current source: the response-envelope /
> token-efficiency backlog is no longer a blanket compile/refresh/test/status
> MCP-tool issue. Scenario verdicts, refresh/compile/build-config-compile/direct
> test responses, `unity_status_summary`, `ensure-ready`, and batch CLI output
> are all compact by default with full-payload opt-in, and compact batch
> summaries are held under a 500-byte per-project budget. What remains is
> broader multi-project compact ceilings, a token-accounting ledger, a one-shot
> package-pin verifier, and fast-path prompt profiles.

## Completed Public History

| Date | File | Scope | Registry Status | Notes |
| --- | --- | --- | --- | --- |
| 2026-08-20 | `2026-08-20_readiness_verdict_false_positive_retro.md` | Readiness truth, non-destructive recovery, heuristic Editor.log diagnosis, and batch editor-close side-effect reporting | all P0-P2 items implemented in current source | Readiness failures use condition-specific codes and unmeasured compile truth, transient attach/import/identity states keep polling, prerequisites agree with the top-level verdict, and Editor.log pattern matches are labelled heuristic without treating `-accept-apiupdate` as a blocker. The multi-project batch runner now emits an immediate verified editor-close notice and retains closeout evidence in per-project and aggregate summaries. |
| 2026-09-03 | `2026-09-03_greenfield_scene_authoring_operator_retro.md` | Greenfield authoring lane: point-of-use editor truth, ordered UI scenarios, test pressure, and project-hook bootstrap | implemented and locally Unity-validated in current source | All required P0-P2 findings are closed: liveness/trust and render-versus-Screen evidence travel with the operation that needs them; scenarios expose guarded click/existence/text reads plus schema/file validation; test verdicts surface console pressure; setup has scalar-root parity; and the guarded scaffold plus package mutation-delta builder make the project-local authoring lane discoverable. Clean Unity `2022.3.67f2` and `6000.0.58f2` compile/acceptance, core EditMode `99/99`, and PlayMode `5/5` pass; a uGUI-enabled Unity 2022 consumer passes the corrected package-runner EditMode lane `138/138`. The optional focus-mutation operation was deliberately omitted in favor of explicit remediation. |
| 2026-09-02 | `2026-09-02_mutation_trust_and_request_attribution_retro.md` | Mutation trust across lifecycle recovery, stable client attribution, process-aware anchored log recovery, and project-hook payload normalization | implemented, validated, and released in `v0.3.66` | Applied mutations remain applied and replay-disabled through passive wait/status plus later refresh or compile-settle failures; transport, Unity journal, and status surfaces preserve `client_session_id` and real editor PID; cross-process anchors fail closed and `maxSearchChars` gives bounded in-tool recovery; plain hook payload objects are promoted while conflicting aliases are rejected. The dead-editor episode was correctly diagnosed before the operator ignored its recovery action, so no speculative fast-fail change was made. |
| 2026-08-30 | `2026-08-30_hub_licensing_gui_playmode_operator_retro.md` | Dynamic Unity Hub licensing IPC handoff, GUI-first local PlayMode admission, terminal lifecycle aggregation, compact CLI output, and helper-owned licensing-child cleanup | implemented, validated, and released in `v0.3.63` | All retro tracks shipped. Full host `979/979`, public site `42/42`, release gates, and a live macOS Hub launch passed; Windows/Linux Hub behavior remains fixture-backed rather than live-host proven, and Unity Package CI retains its documented runner-license waiver. |
| 2026-08-29 | `2026-08-29_consumer_release_rollout_safety_retro.md` | Authoritative consumer discovery, preflight, canary-before-fan-out, resumable evidence, bounded-worker authority, and identity-gated cleanup | implemented, validated, and released in `v0.3.62` | The public helper freezes the denominator and baseline, refuses unsafe mutation, proves one published-package canary before fan-out, and preserves exact per-project resume/cleanup evidence. Focused `23/23`, full host, release/docs/public-safety, and site UI evidence are recorded in the `v0.3.62` changelog. |
| 2026-08-27 | `2026-08-27_editor_launch_and_gui_lane_retro.md` | Editor launch arguments/blocker evidence, scenario authoring diagnostics, deterministic UI lanes, output separation, and modal-blocked quit recovery | implemented, locally Unity-validated, and released in `v0.3.61` | Host `966/966`; clean Unity 2022 and 6000 licensing-channel launches; package EditMode `91/91` and PlayMode `5/5` on both; supported consumers pass Unity 2022 package tests and Unity 6000 compile/apply-gate/GUI/restore scenarios. Commit/tag gates, GitHub Release, and public-site synchronization completed on 2026-08-27; dirty consumer package files were preserved. |
| 2026-08-17 | `2026-08-17_playmode_liveness_and_compile_gate_deadlock_retro.md` | Play-mode liveness, compile-gate ownership, diagnostic provenance, compact project-action envelopes, and catalog-action consistency | implemented, locally Unity-validated, and released in `v0.3.58` | All nine P0-P2 items shipped. `CHANGELOG.md` records local Unity 2022/6000 uGUI and no-uGUI package proof for the release. Unity Package CI remains explicitly waived until runner license secrets exist; that evidence gap is release infrastructure, not unfinished retro work. |
| 2026-08-06 | `2026-08-06_structural_compile_diagnostics_retro.md` | Structural `.asmdef` and assembly-resolution failures hidden behind stale C# diagnostics | implemented and live-validated in current source | Refresh, compile, and direct-test post-settle envelopes scan only the current bridge-generation log scope, prioritize typed structural errors, preserve them in compact output, refuse stale/unscoped promotion, and direct operators to inspect `.asmdef` evidence before cache cleanup. Unity `2022.3.62f3` duplicate-reference injection and green recovery passed. |
| 2026-08-03 | `2026-08-03_multi_scene_ui_targeting_and_session_scoped_evidence_retro.md` | Interactive-lane evidence gaps: UI target scope, session-scoped log queries, live-editor verdict buckets, play-mode-aware errors, screenshot budget | implemented and released through `v0.3.55` | All seven priority items shipped. `unity_status` compact was deliberately dropped because `unity_status_summary` already owns that projection; changing `unity_status` would silently alter the default for existing callers. Host contracts and live additive-scene proof pass. |
| 2026-07-31 | `2026-07-31_shipped_ui_acceptance_toolchain_first_run_retro.md` | First post-release consumer run of the `v0.3.49` reference-driven UI acceptance slice | reusable residuals released in `v0.3.51`; generic runtime-interaction proof added in current source | All nine priority improvements shipped. Current source adds a uGUI-gated PlayMode guarded-click test proving receipt, exactly-once delivery, semantic state change, and refusal on Unity `2022.3` and `6000.0`. Consumer-specific fixtures/interactions and independent vision judges remain host-private adoption work. |
| 2026-07-30 | `2026-07-30_reference_driven_ui_completion_and_visual_acceptance_retro.md` | Reference-image contract, deterministic fixture, semantic/prefab inspection, isolated render, comparison, guarded interaction, AI vision, and device lane | implemented and released in `v0.3.49` | The complete P0/P1/P2 dependency chain is released. Comparison is resolution-independent similarity rather than pixel equality, and visual/semantic/interaction/vision/device lanes fail closed when required evidence is absent. |
| 2026-07-17 | `2026-07-17_prefab_ui_authoring_and_visual_iteration_gap_retro.md` | Prefab/UI inspection, mutation, isolated render, passive readiness, and mutation-delta safety | implemented through `v0.3.49` | Passive polling and mutation-delta trust shipped before `v0.3.49`; the release adds prefab/UI semantic read, binding validation, isolated render, guarded mutation, and guarded semantic click. Project-specific hook adoption remains consumer work, not a reusable MCP capability gap. |
| 2026-07-15 | `2026-07-15_editmode_targeted_filter_zero_match_retro.md` | Direct EditMode test filter returns zero selected tests after external source edits | implemented and released in `v0.3.47` | Filtered zero totals persist and report `test_filter_no_match`, including direct counts, requested-filter summary, and one-refresh recovery guidance while transport delivery remains distinct. Consumer-project proof passed the cold-discovery targeted smoke plus package EditMode `16/16` and PlayMode `5/5` lanes. |
| 2026-07-10 | `2026-07-10_applied_mutation_settle_timeout_retro.md` | Scenario verdict: confirmed project-hook mutation vs immediately-following refresh-settle timeout | implemented and live-validated | Released in `v0.3.43` (`applied_mutation_settle_timeout`, `mutation_applied_unsettled`, mutation/settle summary in `templates/server_summary_scenario.py`; regression in `tests/test_scenario_decision_verdict.py` incl. non-applied/intervening-step guard). `v0.3.44` records live Unity validation passing (GUI-fallback compile matrix, EditMode/PlayMode), closing the prior "live validation pending" caveat. |
| 2026-07-06 | `2026-07-06_first_open_6000_upgrade_apiupdate_modal_and_console_source_retro.md` | First-open Unity 6000 API-Updater modal deadlock + stale-prone Console-buffer compile diagnostics | implemented | `v0.3.44`: `relaunch_noninteractive_accept_apiupdate` recovery + `possible_interactive_dialog_block` health hypothesis (`server_health.py`), console `source=editor_log` + stale-buffer warning (`XUUnityLightMcpConsoleTailOperation.cs`), first-open `-accept-apiupdate` construction and batchmode gate docs, and compact default transport envelopes. All four priority items shipped. |
| 2026-07-06 | `2026-07-06_bridge_declared_not_enabled_first_open_install_retro.md` | Package declared but bridge `bridge_disabled` on first open; separate `--enable-project` + reopen; setup-plan bundled user-scope client config | implemented | `ensure-ready --open-editor` now auto-enables the project-scoped bridge (CHANGELOG "auto-enable the project-scoped bridge"; `server_cli_commands.py` `reason="ensure_ready_open_editor_auto_enable"`; first-open bridge auto-enable regression). setup-plan/apply separate project config from user-scope client wiring; the manual-manifest/manual-open boundary is documented. |
| 2026-07-06 | `2026-07-06_batchmode_blind_to_editor_startup_reconcilers_retro.md` | Green-compile != editor-clean scope-limit gate + offline `editor_log_diagnosis` freshness qualifier | implemented | `v0.3.41`: offline/unverified `editor_log_diagnosis` carries `freshness_class`/`reflects_current_working_tree:false` (`server_health.py`); `SMOKE_TESTS.md` states the compile-gate scope limit and editor-startup-clean gate; Editor.log grep/tail docs call out untyped path-backed evidence. |
| 2026-06-25 | `2026-06-25_scenario_run_wait_compact_smoke_false_negative_retro.md` | scenario run-and-wait compact envelope versus full per-step payload evidence | implemented with follow-up watch | Implemented same day: compact payload-mode fields, structured full-payload recovery hints, public smoke full-payload opt-in, regression test, and docs. Keep watching real editor disappearance during PlayMode lifecycle smoke as infrastructure churn, not a contract issue. |
| 2026-06-24 | `2026-06-24_compile_progress_bar_not_cleared_unity2022_retro.md` | Unity 2022.3 compile/refresh progress-bar teardown | implemented; response-envelope portion split out | P0 `EditorUtility.ClearProgressBar()` fix shipped in `v0.3.31` for compile, refresh, build, and request-pump completion. The compact-response portion is tracked by the token-efficiency rows, not here. |
| 2026-06-18 | `2026-06-18_manual_open_editor_duplicate_launch_retro.md` | manual-open Unity editor duplicate launch guard | core implemented; low-ROI residue only | Fix released ~`v0.3.31` and present in `v0.3.44`: process-visibility fail-closed launch guard (`process_visibility_restricted_before_open`), `same_project_editor_running_bridge_not_ready` reconciliation, worker-only process reporting, `launch_decision` summary, and regression tests. Residual is low-ROI only: direct-CLI activation single-flight audit and uniform launch-decision summary fields. |
| 2026-06-16 | `2026-06-16_ui_playmode_smoke_operator_speed_retro.md` | UI PlayMode smoke: semantic verdict, path-coverage matrix, readiness failure classes | core implemented; minor residue | `v0.3.32` shipped the compact decision verdict with UI-smoke fields, path coverage, and startup/lobby/popup/precondition/cleanup failure classes (verified in `tests/test_scenario_decision_verdict.py`). Residual is low-ROI: a distinct cleanup-safe cancellation op and a standardized project-hook path-inventory template. |
| 2026-06-11 | `2026-06-11_standalone_client_auto_refresh_retro.md` | standalone client auto-refresh | implemented history | Sanitized reusable lessons from package/server alignment work; public launchers, installer, templates, and regression tests were updated. |
| 2026-06-10 | `2026-06-10_windows_process_kill_catastrophe_retro.md` | Windows process-kill catastrophe fixes + proposed `--dry-run` kill mode | fixes implemented; proposal superseded | The four root-cause fixes shipped and are codified in `skills/safe_process_management/SKILL.md` (`ctypes` argtypes/restype, msys/cygwin taskkill routing, PID identity gate `tests/test_editor_host_kill_identity.py`). The proposed `--dry-run` kill mode was superseded by the stricter identity-reverify whitelist that reports-never-kills unverified PIDs. |
| 2026-06-10 | `2026-06-10_portfolio_test_reporting_operator_ergonomics_retro.md` | portfolio test reporting operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio manifest/test validation. |
| 2026-06-09 | `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v1.md` | Windows install v1: `python3` delegation, UTF-8 BOM plan files, `os.kill` PID liveness | implemented (registered 2026-07-12) | All three helper issues fixed and released by the Windows waves through `v0.3.43`/`v0.3.44`: `resolve_python_bin()` (no bare `exec python3`), `utf-8-sig` plan decoding (`server_core.py`), and `pid_is_alive()` via Windows `OpenProcess`/`tasklist` fallbacks instead of raw `os.kill` (`server_host_platform.py`), with regression in `tests/test_windows_host_helpers.py`. Previously unregistered; source evidence for the `2026-06-17` Windows setup row. |
| 2026-06-09 | `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v2.md` | Windows install v2: WSL/Windows Unity editor discovery + stale bridge state | superseded (registered 2026-07-12) | Overtaken by the `v0.3.43` Windows/discovery/recovery wave (cross-platform Unity discovery, host-native recovery commands, atomic IPC + process-identity checks, installed-delegate recovery e2e) and the `v0.3.44` fix so a forwarded `APPDATA` no longer misclassifies a POSIX host as Windows. Retro was pinned to `#v0.3.23`; previously unregistered. |
| 2026-06-08 | `2026-06-08_portfolio_batch_compile_operator_ergonomics_retro.md` | portfolio batch compile operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio validation. |
| 2026-06-08 | `2026-06-08_project_action_hook_scaffold_retro.md` | project action hook scaffold retro | implemented history | Sanitized reusable lessons from a host-private hook authoring session. |
| 2026-06-07 | `2026-06-07_xuunity_mcp_batch_compile_reliability_retro.md` | batch compile reliability: fallback-aware aggregate, `operator_verdict`, compact CLI, byte guard | core implemented; low-priority marker deferred | Fallback-aware aggregate success (`8e93585`, `v0.3.40`), normalized `operator_verdict`, lane/license truth surfacing, bridge-disabled recovery commands, compact CLI (`--output compact`), and a 500-byte per-project compact guard all shipped. Remaining low-priority consideration: a stable `bridge_state`/`bridge_state_absent` marker in batch evidence when available. |
| 2026-05-26 | `2026-05-26_license_aware_batch_fallback_retro.md` | license-aware batch fallback retro | post-implementation history | File status is `post-implementation notes`. |
| 2026-05-23 | `2026-05-23_devmode_batch_lifecycle_retro.md` | devmode source-root, sandbox process visibility, closed-editor batch quit-vs-exit lifecycle | implemented | `v0.3.14` shipped closed-editor batch lifecycle hardening (`request-editor-quit --wait-for-exit`, `restore-editor-state --require-closed`, `process_visibility_restricted` diagnostics) and public source-root/package-mode preflight; hardened through `v0.3.30` (already-closed closeout fast path) and `v0.3.44` (lane selection blocks on unknown editor liveness). All eight priority items shipped. |
| 2026-05-23 | `2026-05-23_optional_capability_setup_wizard_retro.md` | optional capability setup wizard retro | post-implementation history | File status is `post-implementation retro`. |
| 2026-05-21 | `2026-05-21_project_hook_batch_build_operator_retro.md` | project-hook batch-build operator ergonomics: heartbeats, artifact probes, side-effect accounting, hook/reclassification summaries | implemented | Ergonomics landed in `f437cb8` (2026-05-21, in `v0.3.10+` through `v0.3.44`): `server_artifact_probe.py`, `server_workspace_effects.py`, `unity_batch_running` heartbeats, artifact-probe vs `build_succeeded` split, and `tests/test_batch_operator_ergonomics.py`. Reclassification-as-confirmation hardened through `v0.3.43`/`v0.3.44`. |
| 2026-05-15 | `2026-05-15_playmode_verdict_recovery_and_single_project_launch_retro.md` | PlayMode verdict and launch recovery | applied history | File status is `applied`; remaining ordinary risks are not tracked here as active backlog. |
| 2026-05-14 | `2026-05-14_startup_lifecycle_evidence_ergonomics_retro.md` | startup lifecycle evidence ergonomics | implemented history | Sanitized reusable lessons from a host-private startup/profile retro. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_retro_action_plan.md` | validation workflow action plan | implemented history | Action plan file status is `implemented`. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_chat_retro.md` | validation workflow chat retro | completed intake/history | Intake retro whose action plan is tracked separately and marked implemented. |
| 2026-05-11 | `2026-05-11_chat_retro_playmode_lifecycle_reset.md` | PlayMode lifecycle-reset trust classification + retry smoke coverage | implemented | `result_trust_class` (`wrapper_failed_unity_unproven` / `unity_completed_after_lifecycle_reset` / `unity_failed_confirmed` / `unity_completed_confirmed`) in `server_bridge_final_status.py`, dedicated `run_playmode_lifecycle_retry_smoke.sh` + verdict-recovery proof suite, and `SMOKE_TESTS.md` troubleshooting branch. `v0.3.44` adds `unity_completed_host_delivery_unproven` accounting. All P0/P1/P2 shipped. |
| 2026-05-11 | `2026-05-11_operator_and_backend_lessons.md` | operator and backend lessons | historical lesson | Reusable distilled lesson retained for history. |
| 2026-05-09 | `2026-05-09_cleanup_and_regression_lessons.md` | cleanup and regression lessons | historical lesson | Reusable lesson retained for history. |
| 2026-05-07 | `2026-05-07_token_stability_and_summary_first_recovery_retro.md` | token stability and summary-first recovery | implemented history | Sanitized from host-private single-project evidence; private source removed after promotion. |
| undated | `xuunity_mcp_chat_retro.md` | legacy general MCP chat/session postmortem (PASS/EXCELLENT) | history; asks shipped | Both improvement asks are shipped: `no_tests` treated as an acceptable status (`run_multi_project.py` `acceptable_test_statuses={"passed","no_tests"}`) and compact-by-default final/latest surfaces (`v0.3.44`). Legacy wrapper terminology predates the current MCP tool surface; kept as history. |
| undated | `xuunity_mcp_install_retro.md` | legacy end-to-end install/verify/Android-compile success record (v0.3.21) | history; no open items | Clean happy-path install postmortem with zero open items; the described flow still exists and was hardened through `v0.3.42`-`v0.3.44`. No backlog to implement. |
| 2026-09-03 | `2026-09-03_greenfield_hardening_operator_retro.md` | staleness surfacing (editor domain + AssetDatabase), compact build envelope, advisory de-duplication | **both P1 currency findings released in `v0.3.69`; P2/P3 residuals open** | Every catalog-backed action now passes a shared editor-domain currency gate, while `requiresFreshAssets: true` prepends a settled forced refresh. Runtime background execution is enabled without native autofocus. Remaining: compact build/EDM4U envelopes and advisory de-duplication (P2), plus the inline-image idea (P3); native autofocus was deliberately declined. |

## Prompt Templates

- `CHAT_RETRO_PROMPT.md`
- `INSTALL_RETRO_PROMPT.md`
