# XUUnity MCP Balanced Product Portfolio Design

Date: `2026-08-14`
Status: `approved design; ready for sequential implementation`
Scope: public-safe reusable XUUnity Light Unity MCP product work
Planning horizon: next `20` release-ready vertical slices

## 1. Decision

Allocate engineering capacity equally across five product outcomes:

1. stability and Unity lifecycle recovery;
2. verdict and evidence trust;
3. feature scope and reusable capabilities;
4. performance and operator efficiency;
5. delivery, platform reliability, and maintainability.

Each lane receives `20` of `100` relative engineering points. Balance is measured
by expected effort, including tests, documentation, and Unity regression, not by
raw task count or line count.

Implementation starts with the changes most likely to produce material user
value. Work with a meaningful overengineering risk remains in a gated backlog
until its activation evidence exists.

One run implements exactly one coherent vertical slice. A run must not begin a
second portfolio item after completing the selected item.

## 2. Why This Portfolio Exists

The current MCP surface is already broad. The highest-value verdict envelope,
post-settle compile/test/refresh truth, UI/path proof, infrastructure failure
classification, structural compile diagnostics, UTC parsing, test-result
accounting, SDK generated-diff proof, typed Android resolve, and package restore
are implemented in current source.

The next product risk is imbalance:

- reliability-only work can leave the product trustworthy but narrow;
- feature-only work can produce more commands whose evidence is difficult to
  trust;
- refactoring-only work can consume capacity without changing a user outcome;
- performance-only work can optimize paths users do not depend on;
- release-only work can improve packaging while leaving daily operation slow.

The five-lane allocation prevents any one of those local optimizations from
becoming the product strategy.

## 3. Evidence And Freshness Boundary

This plan was derived from the public retro registry, public designs, current
roadmap/status/changelog, and sanitized recurring findings from consumer runs.
Private paths, project names, run identifiers, product behavior, and local
artifacts are deliberately excluded.

Before selecting any slice, re-check:

- current `master`, `origin/master`, the newest release tag, and the latest 30
  commits;
- `CHANGELOG.md`, `docs/reference/STATUS.md`, and
  `docs/architecture/ROADMAP.md`;
- `docs/archive/retros/RETRO_REGISTRY.md` and this design history;
- current code and tests for the candidate's contract names.

Do not implement a registry description when current code already closes it.
The registries are routing aids, not substitutes for source freshness.

### Task 0 — registry normalization

Status: `complete 2026-08-14`. The design-plan history, designs index, and
public retro registry were reconciled against current source at `b13cb69`;
the next run selects the first unimplemented start-now slice.

Before Portfolio Slice 1, perform one public-safe documentation-only grooming
pass:

- reconcile stale SDK package-restore rows;
- reconcile enterprise B5 local interaction proof;
- remove test-result accounting from open-priority summaries;
- reconcile the older read-only UI-primitives status with the newer uGUI/TMP
  reference-driven read surface;
- update registry/design-history review dates only after the rows are actually
  re-verified.

Task 0 does not consume portfolio points because it changes routing accuracy,
not product behavior.

## 4. Capacity Model

Points are relative sizing units. They include implementation, focused tests,
cross-platform compatibility work, documentation, and proportionate live Unity
regression. They are not calendar-day promises.

| Lane | Outcome | Allocation |
| --- | --- | ---: |
| S | Stability and lifecycle | 20 |
| T | Verdict and evidence trust | 20 |
| C | Feature scope and capabilities | 20 |
| P | Performance and operator efficiency | 20 |
| D | Delivery, platform, and maintainability | 20 |
|  | **Total** | **100** |

## 5. Portfolio Backlog

### 5.1 Stability And Lifecycle — 20 Points

| ID | Points | Vertical slice | Release-ready outcome |
| --- | ---: | --- | --- |
| S1 | 3 | Authoritative `project_refresh_timeout` recovery guidance | Classify editor failure, package settle, compile/import churn, and lost final accounting. When the editor is reachable and healthy, return `request_status_summary_then_compile_gate`, a concrete recovery command, and an explicit note that the Unity operation may have completed. |
| S2 | 3 | Bounded refresh of stale-negative license evidence | Re-probe only stale negative evidence that would exclude or weaken a validation lane. Preserve cache provenance, bound the added time, and never turn unknown evidence into a pass. |
| S3 | 8 | SDK GUI admission pool, batch resolve, and verified quit | Enforce global, resolver-lane, and per-project admission; derive occupancy from live processes; fail closed when process visibility is unavailable; reuse graceful quit and confirmed-PID termination; prove no editor stampede or double-open. |
| S4 | 6 | Cleanup-safe Unity-side cancellation | Add a terminal cancellation receipt and cleanup accounting for work already dispatched to Unity. Distinguish cancelled-before-start, cancellation-requested-in-flight, Unity-completed-before-cancel, and Unity-unproven. Do not build distributed cancellation or arbitrary rollback. |

### 5.2 Verdict And Evidence Trust — 20 Points

| ID | Points | Vertical slice | Release-ready outcome |
| --- | ---: | --- | --- |
| T1 | 6 | Run-bound, tamper-evident evidence | Host-generated run identity is recorded in the request journal and matched on read; receipt SHA-256 is re-verified; scenario/operation/project identity must match dispatch; Play Mode claims are corroborated against bridge state for that run. |
| T2 | 4 | Typed project-action outputs and artifact interpolation | Define a reusable typed result block, register declared artifacts, support bounded `${steps.<id>.artifacts.<name>}` interpolation, and refuse missing, ambiguous, path-escaping, or untrusted references. |
| T3 | 4 | Richer scenario assertions and failure taxonomy | Add a bounded set of high-frequency assertions and promote the smallest actionable failure interpretation into compact scenario summaries without replacing raw evidence. |
| T4 | 6 | Concurrent-run isolation and attributable review identity | Namespace run/comparison/review state by a host-issued identity, use atomic/locked shared-state updates, prevent stale/live collision, and prove the same reference can be processed by two jobs without evidence mixing. |

### 5.3 Feature Scope And Capabilities — 20 Points

| ID | Points | Vertical slice | Release-ready outcome |
| --- | ---: | --- | --- |
| C1 | 4 | Core asset/package/define read surface | Add narrow read/list/query operations for the minimum diagnostic set that currently requires shell scraping. Keep the surface read-only, bounded, project-root sandboxed, and compact by default. |
| C2 | 5 | Validation-suite compiler, first slice | Parse a committed public-safe suite YAML, validate lane kinds and declared capabilities, and emit either a deterministic non-executing plan or a typed gap report. Do not add natural-language compilation or automatic execution in this slice. |
| C3 | 5 | `sdk-validate` compact portfolio verdict | Compose package restore, typed resolver freshness, generated-diff proof, compile evidence, and dependency verification into one per-project and aggregate verdict. Depends on S3. |
| C4 | 6 | Constraint-gated read-only UI Toolkit provider | Implement the minimum tree/query/exists/text/bounds surface behind capability gating, preserve zero hard dependency for projects without UI Toolkit, and publish an honest backend coverage matrix. Exclude mutation and interaction. |

### 5.4 Performance And Operator Efficiency — 20 Points

| ID | Points | Vertical slice | Release-ready outcome |
| --- | ---: | --- | --- |
| P1 | 3 | Byte-bounded console tail | Add a deterministic byte/result ceiling, explicit truncation accounting, and direct `console_grep` guidance. Keep full/raw recovery explicit. |
| P2 | 4 | Compact light scene/playmode/view envelopes | Remove default lifecycle snapshot duplication from scene open, Play Mode set, scene snapshot, Game View configure, and screenshot results; retain full payload behind an opt-in and document the image-byte budget. |
| P3 | 5 | Native PNG decode path and real-capture benchmark | Prefer a tested native/library decoder when available, retain the dependency-free decoder as fallback, benchmark engine-produced filtered PNGs, and keep decompression-bomb and dimension guards. |
| P4 | 8 | Token ledger, fast-path profile, and package-pin verifier | Measure the largest response-cost centers, add a bounded fast-path evidence profile, and provide a one-shot package-pin verifier. Do not add token accounting to every low-level function. |

### 5.5 Delivery, Platform, And Maintainability — 20 Points

| ID | Points | Vertical slice | Release-ready outcome |
| --- | ---: | --- | --- |
| D1 | 5 | Automated Unity package CI and tag gate | Compile the package and run EditMode/PlayMode on two supported Unity lines, include a no-uGUI project, keep Python Windows/macOS/Linux green, and block release/tag preparation on failed gates. |
| D2 | 3 | Launcher runtime-info and interpreter consistency | Expose the selected runtime/version/source in a typed operation and remove direct `python3` assumptions from the reusable post-change runner. Preserve Windows, macOS, and Linux behavior. |
| D3 | 5 | Release/runtime integrity | Warn when installed and source/runtime versions disagree; generate checksums and an SBOM from the release workflow; bind release documentation claims to produced validation evidence. Signing may remain a separately approved publishing step. |
| D4 | 7 | `server_batch_orchestrator.py` behavior-preserving split | Extract ownership modules behind a compatibility facade while preserving every observable MCP, CLI, JSON, file, exit-code, and platform contract. |

## 6. Start-Now Set: Highest Probability Of Material Value

The first implementation phase is intentionally evidence-heavy. These tasks
have recurring consumer evidence, direct operator cost, or a demonstrated
release failure class:

1. D1 — automated Unity package CI and tag gate;
2. S1 — authoritative refresh-timeout recovery guidance;
3. P2 — compact light scene/playmode/view envelopes;
4. P1 — byte-bounded console tail;
5. C1 — core asset/package/define read surface;
6. P3 — native PNG decode and real-capture benchmark;
7. T3 — richer scenario assertions and failure taxonomy;
8. T1 — run-bound, tamper-evident evidence.

Recommended size-aware order:

`S1 → D1 → P1 → P2 → C1 → T3 → T1 → P3`

Progress: S1 is complete (2026-08-14, host contract tests plus Unity `2022.3`
current-source and Unity `6000.0` released-package live fault injection; see
the evidence-ergonomics design row). D1 is complete (2026-08-14: the
`Unity Package CI` workflow, the `no-ugui` lane, the tested consumer scaffold,
and `check_release_ci_gates.py` blocking tag preparation, wired into the
publishing checklist, the release skill, and the tag-push `Release Tag Gate`
workflow; local CI-equivalent batch `-runTests` proof passed all four
version × lane combinations on Unity `2022.3` and `6000.0`, and a live gate run
against the real repository correctly blocked on the not-yet-pushed workflow.
The first green GitHub run still requires the maintainer to configure Unity
license secrets and push; that external dependency is recorded in
`docs/operations/UNITY_PACKAGE_CI.md` and does not weaken the acceptance
contract). P1 is complete (2026-08-14: `unity_console_tail`, the CLI, and the
`console_tail` scenario step enforce a deterministic `maxPayloadBytes` ceiling
— default `16384`, `-1` raw — in the Unity bridge with a host-side fallback
for older packages, oldest-first drops, an explicit newest-item truncation
marker, full accounting fields, and `unity_console_grep` named as the compact
recovery tool; 18 focused host tests, host suite `890` green, and live
bounded/truncated/raw proofs plus EditMode `81/81` through the bridge on both
Unity `2022.3` and `6000.0`). P2 is complete (2026-08-14: `unity_scene_open`,
`unity_scene_snapshot`, and `unity_game_view_configure` return compact
envelopes by default with `includeFullPayload=true` opt-in, joining the
already-compact refresh/compile/test/Play Mode/screenshot responses; the
screenshot image-byte budget is documented; 7 focused host tests, host suite
`897` green, and live end-to-end proofs on Unity `2022.3` and `6000.0` showed
a scene-open response shrinking from ~12,000 to ~540 bytes with identical
decision content). The next unimplemented start-now item is C1.

D1 is deliberately early even though Unity licensing can add calendar cost: it
is the proof foundation for later Unity package changes. If runner licensing is
externally blocked, record the blocker and continue with S1/P1/P2; do not weaken
the CI acceptance contract.

## 7. Balanced Continuation

The start-now set intentionally front-loads trust and operator-efficiency work
because those items have the strongest observed evidence. The continuation must
repay that temporary imbalance. Over the full activated portfolio, consumed
points should converge to `20` per lane; do not manufacture gated work merely
to make an interim chart look balanced.

Dependency constraints override round-robin order:

- D1 precedes release claims for later Unity package changes;
- T1 precedes T4;
- S3 precedes C3;
- C2 first slice must remain compile-only/non-executing;
- C4 must remain read-only in this plan;
- D4 must satisfy its activation and parity gate below.

The size- and dependency-aware continuation after the eight start-now items is:

`S2 → D2 → C2 → S3 → D3 → C3 → T2 → S4`

The remaining four items are gated and stay ordered by dependency and expected
value when their gates activate:

`T4 → C4 → P4 → D4`

If a gate does not activate, its points remain backlog capacity until the next
portfolio review. They are not silently reassigned to unrelated scope.

## 8. Probability And Overengineering Assessment

These values are planning priors, not production statistics.

- `material value` means a noticeable user or release benefit within 6–12
  months;
- `trigger/demand` means at least one occurrence of the defect in relevant use,
  or real demand for a new capability, over the same horizon;
- `overengineering risk` means the likely cost is not justified without an
  additional activation signal.

| ID | Material value | Trigger / demand | Overengineering risk |
| --- | ---: | ---: | ---: |
| S1 | 90–95% | 35–60% | 5–10% |
| S2 | 65–75% | 15–30% | 15–25% |
| S3 | 75–85% | 25–50% in portfolio SDK use | 15–25% |
| S4 | 65–80% | 10–25% | 20–30% |
| T1 | 75–90% | 10–25% accidental mismatch | 15–25% |
| T2 | 70–85% | 40–65% demand | 15–25% |
| T3 | 80–90% | 55–75% demand | 10–20% |
| T4 | 55–75% now | 5–15% solo; 30–60% team/CI | 35–50% |
| C1 | 85–95% | 70–90% demand | 5–15% |
| C2 | 60–80% | 35–55% demand | 30–45% |
| C3 | 75–90% in SDK use | 30–50% overall demand | 15–25% |
| C4 | 55–80% | 20–45% current demand | 30–45% |
| P1 | 85–95% | 50–80% | 5–10% |
| P2 | 90–95% | 70–95% | 5–10% |
| P3 | 80–90% | 50–75% in UI use | 10–20% |
| P4 | 45–65% | 25–45% demand | 40–55% |
| D1 | 95–99% | 15–35% across several releases | <5% |
| D2 | 70–85% | 15–35% cross-platform | 10–20% |
| D3 | 75–90% | 15–30% stale runtime; higher in enterprise review | 15–25% |
| D4 | 40–60% immediate user value | 10–25% indirect defect risk | 45–60% |

## 9. Anti-Overengineering Backlog Gates

The following work stays in the backlog until its gate is satisfied:

### T4 — concurrent-run isolation

Activate after either:

- two independent workers operate against the same project/reference; or
- a concurrency fault is reproduced by a deterministic test.

T1 run identity is a prerequisite. Do not invent broad tenancy, accounts, or a
remote coordination service.

### C2 — validation-suite expansion

The first compile/gap-report slice is allowed. Additional DSL breadth, natural
language compilation, and automatic execution require at least three real suite
specifications with repeated duplicated authoring cost.

### C4 — UI Toolkit expansion

The bounded read-only provider requires either two concrete consumers or one
qualified pilot. Mutation, click delivery, and broad editor-window automation
remain out of scope.

### P4 — token ledger

Activate only after compact-envelope measurement shows material remaining cost,
for example more than 20% of a representative validation session spent on
avoidable MCP result payloads. Measure before instrumenting.

### S4 — advanced cancellation semantics

The terminal receipt and cleanup-accounting slice is allowed after a repeated
unfinished-work case. Distributed cancellation, arbitrary rollback, and
cross-host coordination require separate evidence and design.

### D4 — monolith split

**Primary criterion: contract-preserving change isolation.**

D4 is not complete merely because a large file became several smaller files.
It is complete when a future batch behavior change can be implemented and
reviewed inside one ownership module without editing the compatibility facade,
while observable behavior remains identical.

Activation requires an upcoming change that crosses at least two responsibility
regions in `server_batch_orchestrator.py`, or repeated review/test failures that
can be attributed to its mixed ownership. Do not schedule a standalone rewrite
for line count alone.

Completion requires all of the following:

1. `server_batch_orchestrator.py` becomes a compatibility facade below the
   existing `1,200`-line hard-review threshold;
2. extracted modules each own one reason to change and have an explicit parity
   test owner;
3. MCP tool names, CLI commands/help, argument shapes, JSON payload/status/error
   shapes, persisted artifacts, stdout/stderr, and exit codes remain unchanged;
4. golden/parity coverage proves representative success, refusal, timeout,
   recovery, and compact/full output paths;
5. Windows, macOS, and Linux launcher/process/path/encoding behavior remains
   green;
6. the split introduces no new runtime dependency and no compatibility alias
   beyond the existing facade;
7. the final diff contains no unrelated feature work.

The `1,200`-line threshold is a completion guard, not the architectural goal.
The architectural goal is local reasoning with observable-contract parity.

## 10. Per-Slice Implementation Contract

For every selected item:

1. perform the freshness audit;
2. state why the slice beats the other currently unblocked candidates;
3. identify public contracts and persisted files before editing;
4. implement the smallest useful vertical slice;
5. add focused unit/contract tests and adversarial cases proportionate to risk;
6. run static/format checks;
7. run current-source validation in a clean Unity 2022 development-system lane
   and a Unity 6000 real-consumer lane when the change touches the bridge,
   package, lifecycle, scenarios, SDK orchestration, or release claims;
8. restore consumer manifests, locks, profiles, Play Mode, scenes, and
   host-opened editor state;
9. update changelog, status, design status, and registries without exposing
   private evidence;
10. self-review compact/full/recovery surfaces for contradictory truth;
11. leave changes uncommitted unless separately requested;
12. report `release_ready`, `needs_manual_unity_validation`, or `blocked`.

## 11. Portfolio Review Rules

Re-score the portfolio after every five completed slices or after any severe
consumer incident.

- A recurring false-positive or false-negative can temporarily move S/T above
  20%, but the imbalance must be explicitly repaid in the next planning window.
- A new capability cannot borrow from trust/stability merely because it is
  visible in a demo.
- An audit-only risk with no trigger evidence cannot displace a recurring user
  failure unless its consequence is release- or security-critical.
- Gated work that remains unactivated consumes zero implementation capacity.
- Completed work must be removed from active registry/design summaries instead
  of remaining as historical apparent backlog.

## 12. Non-Goals

- device automation or profiler scope (amended after `v0.3.86`: the Android device
  lane in ROADMAP Wave 5 is now in scope; profiler capture and iOS remain out);
- runtime-in-player MCP;
- broad arbitrary mutation or reflection;
- OpenUPM, catalog, marketing, or discovery work in place of product work;
- project-specific fixtures, profiles, hooks, or scenario names in public code;
- one large implementation covering multiple portfolio items;
- refactoring justified only by aesthetics or file size.

## 13. Source Designs And Retros

- [`XUUNITY_MCP_ENTERPRISE_READINESS_DESIGN_2026-07-31.md`](XUUNITY_MCP_ENTERPRISE_READINESS_DESIGN_2026-07-31.md)
- [`XUUNITY_MCP_SDK_ROLLOUT_GATE_IMPLEMENTATION_PLAN_2026-07-12.md`](XUUNITY_MCP_SDK_ROLLOUT_GATE_IMPLEMENTATION_PLAN_2026-07-12.md)
- [`XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md`](XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md)
- [`XUUNITY_MCP_MONOLITH_REDUCTION_FIRST_PRINCIPLES_PLAN_2026-06-25.md`](XUUNITY_MCP_MONOLITH_REDUCTION_FIRST_PRINCIPLES_PLAN_2026-06-25.md)
- [`XUUNITY_MCP_PROJECT_VALIDATION_SUITE_DESIGN_2026-05-12.md`](XUUNITY_MCP_PROJECT_VALIDATION_SUITE_DESIGN_2026-05-12.md)
- [`XUUNITY_MCP_EVIDENCE_ERGONOMICS_AND_PROFILE_FLOW_DESIGN_2026-05-15.md`](XUUNITY_MCP_EVIDENCE_ERGONOMICS_AND_PROFILE_FLOW_DESIGN_2026-05-15.md)
- [`XUUNITY_MCP_REFERENCE_DRIVEN_UI_ACCEPTANCE_DESIGN_2026-07-30.md`](XUUNITY_MCP_REFERENCE_DRIVEN_UI_ACCEPTANCE_DESIGN_2026-07-30.md)
- [`../../archive/retros/2026-06-02_token_efficiency_response_envelope_retro.md`](../../archive/retros/2026-06-02_token_efficiency_response_envelope_retro.md)
- [`../../archive/retros/2026-06-11_token_accounting_and_fast_path_retro.md`](../../archive/retros/2026-06-11_token_accounting_and_fast_path_retro.md)
- [`../../archive/retros/2026-06-16_ui_playmode_smoke_operator_speed_retro.md`](../../archive/retros/2026-06-16_ui_playmode_smoke_operator_speed_retro.md)
- [`../../archive/retros/2026-07-30_reference_driven_ui_completion_and_visual_acceptance_retro.md`](../../archive/retros/2026-07-30_reference_driven_ui_completion_and_visual_acceptance_retro.md)
- [`../../archive/retros/2026-07-31_shipped_ui_acceptance_toolchain_first_run_retro.md`](../../archive/retros/2026-07-31_shipped_ui_acceptance_toolchain_first_run_retro.md)
- [`../../archive/retros/RETRO_REGISTRY.md`](../../archive/retros/RETRO_REGISTRY.md)

## 14. Short Start Prompt

> Implement the next release-ready slice from the Start-Now Set in this design.
> Begin with Task 0 registry normalization if it is still open; otherwise select
> the first unimplemented item in `S1 → D1 → P1 → P2 → C1 → T3 → T1 → P3`.
> Re-audit current source, commits, tags, changelog, status, registries, and the
> referenced owner design before selection. Implement exactly one coherent
> slice, preserve public and persisted contracts, add adversarial tests, run
> proportionate Unity 2022 and Unity 6000 regression, update public-safe docs,
> self-review the full diff, and leave changes uncommitted. Report exact evidence
> and one of `release_ready`, `needs_manual_unity_validation`, or `blocked`.
