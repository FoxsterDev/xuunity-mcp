# XUUnity Light Unity MCP Chat Retro — Batch Summary Shape and Compile-Warning Evidence

Date: `2026-09-02`
Status: `P0 and summary-artifact P2 released in v0.3.67; warning-evidence P1 released in v0.3.70; rebuild/cache P1 implemented in current source; output-shape P2 remains`
Lane: `batch-build-config-compile-matrix` via the multi-project sweep runner, GUI fallback throughout
Server metadata observed in session: `xuunity-mcp 0.3.65`

## 1. Executive Summary

A compiler-warning cleanup task cleared 12 unique warning sites across a shared consumer package and
per-project code in a multi-project monorepo, then used `run_multi_project_batch_compile_matrix.sh` to
prove the result. Unity executed every request correctly and never once reported a wrong compile
outcome. The MCP surface got two things wrong about *what it had proven*, and both are about the
batch **summary** layer rather than the compile lane.

| Finding | Attribution | One-line basis |
| --- | --- | --- |
| P0-1 the sweep runner reports `failed_wrapper_unity_unproven` / `total=0` on the wrapper's **default** output shape | **implemented for v0.3.67** | The runner now resolves nested, compact top-level, named summary-file, and confirmed result-file evidence in order. Four regression cases cover compact GUI success, both artifact fallbacks, and `unavailable` rather than false-zero counters. |
| P1-1 no warning surface anywhere in the batch compile artifacts | **released in v0.3.70** | Per-config results now count every warning occurrence, deduplicate warning identity, retain bounded diagnostic rows, and carry that evidence through matrix, compact batch, and multi-project summaries. |
| P1-2 `compiled_assembly_count` cannot distinguish a real compile from a cache hit | **product gap** | One project's run reported `compiled_assembly_count` 85 (Android) / 82 (iOS) per config while the raw log held **374** real `Csc` invocations and **330** `[CacheHit …]` invocations. Another project in the same sweep: 73 real, 0 cache hits, count 66/63. Nothing in the artifacts expresses that ratio. |
| P2-1 the runner never loads the `summary_file` it is handed | **implemented for v0.3.67** | The runner reads the named summary artifact as the third precedence source and records `summary_file_loaded` plus the selected evidence source. |
| P2-2 `--output` is parsed but never consumed | **product defect, dead flag** | `add_batch_operator_arguments` registers `--output` on the batch subcommands, but `grep` for `args.output` across `templates/*.py` yields only `args.output_path` / `args.output_dir`. Operators cannot select the shape the runner needs. |

The single most valuable fix is P0-1, and it is small: the two fields that lost their value are the
only two in that block without a payload-level fallback. The verdict taxonomy this defect breaks is
the one introduced as P0 by the 2026-06-07 batch-compile reliability retro, which was written against
`result_summary.unity_outcome` — the nested shape. The later compact-envelope work
(2026-06-02, 2026-06-11) flattened that shape for token efficiency and made compact the default.
**This is a two-feature collision: neither change was wrong on its own, and no test covers the
runner against the compact projection.**

P1-2 is new to this archive: `grep -rniE "cachehit|cache hit|cached compile|incremental"` over all 52
public retros returns nothing. It is the finding with the widest reach, because it is the difference
between "the matrix passed" and "the matrix proved anything about the code I just changed."

## 2. Evidence Base

All session-local and checkable. Runner artifacts were kept via `--results-dir`.

- Two saved wrapper stdout captures for the **same command on the same project**, 7 minutes apart:
  - run A last JSON document: 35 keys, includes a nested `result_summary` whose `unity_outcome` is
    `passed`.
  - run B last JSON document: 14 keys, `payload_mode: "compact_batch_cli"`, **no** `result_summary`
    key; `unity_outcome` and `transport_outcome` present at the **top level**.
- Runner status artifact for run B: `verdict=failed_wrapper_unity_unproven`, `succeeded=true`,
  `recover_rc=0`, `batch_rc=0`, `effective_lane=gui`,
  `fallback_reason=licensing_client_ipc_failure`, `transport=`, `unity=`, `matrix_status=`,
  `total=0|passed=0|failed=0|skipped=0`, process exit `1`.
- Unity's own result JSON for that same run B: `status: passed`, `total: 6`, `passed: 6`, `failed: 0`,
  `validation_evidence: unity_mcp`, `post_settle_compile: passed`,
  `post_settle_compile_trust_class: confirmed`, `completion_basis: unity_compile_settle_watcher`,
  `duration_seconds: 23.47`.
- `<project-root>/Library/XUUnityLightMcp/logs/batch/<ts>_build_config_compile_matrix.log`, 1.0-1.25 MB
  per project, the only surface carrying compiler warnings.
- Installed host helper diffed against `templates/server_batch_reporting.py` and
  `templates/server_batch_lanes.py`: **byte-identical**, so version skew is excluded as a cause.
- Public docs and source grepped per finding before writing it: `args.output`, `result_summary`,
  `warning_count`, `CacheHit`.

Not pinned in-session, and part of the fix work: which branch produced run A's full nested payload
given that `compact` is the effective default for this subcommand. Candidate is the GUI-fallback
finisher that opens and closes its own editor (`server_batch_lanes.py:498`) versus a GUI operation
against an already-open editor; run A launched an editor for the project, run B reused the one run A
left open. This is stated as a hypothesis, not a finding.

## 3. Timeline

1. Baseline sweep (pre-session, 11 projects) produced the warning inventory: 12 unique sites, 0 errors.
2. 12 sites patched across a shared package and per-project code.
3. Sweep invocation 1 aborted on operator-side argument quoting; the wrapper printed the collapsed
   argument blob followed by full usage. Operator error, ~1 round trip.
4. Sweep invocation 2, 11 projects, parallelism 4, 3m54s: `projects_failed 0`, verdict
   `passed_via_gui_fallback` x11, 48 config compilations. Full nested payload shape.
5. Warning re-grep over the 11 raw logs: 10 projects clean, one project still reporting 2 warnings —
   a real regression the operator had introduced by removing a `new` keyword, trading `CS0109` for
   `CS0108`. **The compile matrix reported `passed` for that project in both states**, because
   warnings are outside its verdict (P1-1).
6. Rebuild-coverage question raised: is "0 warnings" a real recompile or a cached skip? No artifact
   field answers it. Operator invented a `[CacheHit]` grep over the raw log (P1-2).
7. `unity.compile.player_scripts` against the live interactive editor refused with
   `editor_in_play_mode` plus the exact exit command. Correct, cheap, and actionable.
8. Single-project re-run after the correction, 45s: compact payload shape, verdict
   `failed_wrapper_unity_unproven`, `total=0`, exit 1.
9. Unity's result JSON for that same run read directly: `passed`, `6/6`, `validation_evidence: unity_mcp`.
   Root cause traced to the summary-shape mismatch, ~4 round trips.

## 4. What Worked Well

- **Unity-side execution was never wrong.** Every compile outcome the lane reported matched the
  on-disk result. 54 config compilations, zero spurious failures.
- **Licensing GUI fallback was consistent and self-labelling.** `requested_lane=batch ->
  effective_lane=gui`, `fallback_reason=licensing_client_ipc_failure`,
  `license_blocker=licensing_client_ipc_failure` on every project, with
  `license_from_cache`/`license_probe_age_seconds` attached. The operator never had to guess whether
  the fallback was degraded — the 2026-08-30 licensing retro's work is holding.
- **`unity_status_summary` was the right first call.** One compact response gave editor pid, health,
  playmode state, compile state, bridge generation, writer trust class, detected editor count, and
  `runtime_execution_allowed`. It correctly predicted the interactive lane was unusable later.
- **Play-mode refusal on `unity.compile.player_scripts` was exemplary.** Typed code, current state
  values, and two concrete remediations including the batch alternative.
- **`post_settle_compile_trust_class: confirmed`** was the field that resolved the false negative. It
  exists, it is authoritative, and it was correct.
- **`--results-dir` retention** is what made this retro possible; both stdout shapes were still on
  disk 7 minutes later.

## 5. What Worked Poorly

- The sweep runner turned a **passing** Unity run into a failing exit code and a
  `..._unity_unproven` verdict, which is the one verdict specifically designed to mean "we cannot
  tell." Here the wrapper could tell, printed the answer at the top level of its own payload, and
  also wrote it to a file it named.
- The failure is not a race. `compact` is the **default** for this subcommand, so the runner's happy
  path depends on the non-default shape. Every project in the sweep is one lane-branch away from the
  same false negative.
- `total=0|passed=0|failed=0|skipped=0` next to `succeeded=true` is an internally contradictory line
  and no field marks the counters as unpopulated rather than measured-zero.
- A compile matrix that reports `passed` while the code carries new compiler warnings gave the
  operator no signal on the regression introduced in step 5; only a manual 1.2 MB log grep caught it.

## 6. What Was Not Explicit Enough

- Nothing states the runner's expected payload contract, so the compact projection could drop
  `result_summary` without any consumer-side failure.
- `compiled_assembly_count` reads like compile evidence and is actually compile-set size.
- The raw log's diagnostic vocabulary is not uniform across projects: `Processing assembly …` lines
  appeared in one project's log (401 lines) and were entirely absent from three others' logs in the
  same sweep. The operator wasted a round trip on it as a rebuild proxy before finding
  `Csc … [CacheHit …]`, which is present in all of them. No doc names the reliable marker.

## 7. What The Operator Needed But Did Not Have

1. `warning_count` and `unique_warning_count` per config, plus a bounded `warnings[]` with
   `file`/`line`/`code`/`message`, mirroring the existing `error_count`/`errors` pair.
2. `rebuilt_assembly_count` and `cached_assembly_count` per config, so `passed` can be read as
   evidence about changed code.
3. A verdict that cannot be worse than the authoritative on-disk result the wrapper just named.
4. A documented, single grep idiom for "did this assembly really recompile."

## 8. Scoring

| Category | Score | Note |
| --- | --- | --- |
| Unity-side execution stability | 10/10 | 54 config compilations, zero wrong outcomes |
| Request journaling quality | 8/10 | Journal head and request ids present and usable |
| Bridge health observability | 9/10 | `unity_status_summary` answered every state question in one call |
| Wrapper-to-operator clarity | 9/10 | Lane, fallback reason and license blocker were explicit and consistent |
| Recovery guidance quality | 4/10 | The false-negative verdict carried no pointer to the result file that contradicted it |
| Transport lifecycle transparency | 8/10 | GUI fallback labelled on every project |
| End-to-end trustworthiness during churn | 3/10 | Same command, two payload shapes, opposite verdicts, same passing Unity run |
| Parallel request handling | 9/10 | Parallelism 4 across 11 projects, no cross-talk |
| Token efficiency of the default operator path | 3/10 | The task's actual question needed ~13 MB of raw-log greps across two sweeps |
| Time-to-diagnosis | 5/10 | ~4 round trips to disprove a verdict the wrapper had already answered |
| Validation workflow discipline | 8/10 | Compile-first ordering held; the interactive lane was correctly abandoned rather than forced |

## 9. Priority Improvements

### P0

- In `scripts/testing/run_multi_project.py`, resolve summary fields with the same three-source
  precedence the neighbouring fields already use: nested `result_summary`, then payload top level,
  then the on-disk `summary_file`/`result_file`. Minimum change is `unity_outcome`,
  `transport_outcome` and the matrix counter block.
- Never let the derived verdict contradict an authoritative on-disk result the payload names. If the
  result file says `status: passed` with `post_settle_compile_trust_class: confirmed`, the sweep
  verdict must be a pass, or must name why it overrode it.
- Distinguish "counters unpopulated" from "counters measured zero". `total=0` beside
  `succeeded=true` must not be reachable; emit `matrix_counters=unavailable` with the reason instead.
- Add a regression that feeds the runner the **compact** projection of a passing GUI-fallback run and
  asserts `passed_via_gui_fallback`. The existing tests assert the compact builder's own output shape
  (`tests/test_license_capabilities.py:196-226`) but nothing asserts a consumer can read it.

### P1

- **Released in `v0.3.70`:** add `warning_count`,
  `unique_warning_count`, and a bounded `warnings[]` to each compile-matrix
  config result and to the summary artifact, alongside the existing error
  fields. Compact batch and multi-project summaries retain the same evidence.
- Add `rebuilt_assembly_count` and `cached_assembly_count` per config, derived from the
  `Csc … [CacheHit …]` marker, and keep `compiled_assembly_count` as compile-set size with that
  meaning documented.

### P2

- Wire `--output` to `output_mode` or remove the flag; a parsed-and-ignored argument is worse than
  neither.
- Pin which finisher emits the full nested payload and make the shape lane-independent for a given
  `--output` value.

## 10. Public-Promotion Recommendations

- `docs/architecture/DESIGN.md` — state the batch payload contract explicitly: which fields are
  guaranteed at the payload top level, which live under `result_summary`, and that the compact
  projection flattens rather than nests. Name the on-disk `summary_file`/`result_file` as the
  authoritative fallback for any consumer.
- `docs/operations/SMOKE_TESTS.md` — add an acceptance check that a sweep verdict agrees with the
  per-project result JSON, and add the rebuilt-versus-cached check to the compile-matrix acceptance
  list.
- `docs/operations/CONTINUATION.md` — add the recovery step this session had to invent: on any
  sweep-level failure, read `<project-root>/Library/XUUnityLightMcp/logs/batch/<ts>_..._result.json`
  before treating it as a compile failure; `status`, `validation_evidence` and
  `post_settle_compile_trust_class` are authoritative over the runner's derived verdict.
- `docs/operations/CONTINUATION.md` — document `Csc <asm>.dll (+n others)` with **no** trailing
  `[CacheHit <hash>]` as the one reliable "this assembly really recompiled" marker, and note that
  `Processing assembly …` is not present in every project's batch log.
- `README.md` — one line in the batch section: the compile matrix verdict covers errors only;
  warnings require the raw log until the warning fields ship.
- `docs/architecture/ROADMAP.md` — the warning surface and the rebuilt/cached ratio belong with the
  compact-envelope tail already tracked from the 2026-06-02 and 2026-06-11 token-efficiency retros;
  both findings here are that tail biting a real task.

## 11. Final Verdict

Unity was right every time. The compile lane, the licensing fallback, the status summary and the
post-settle trust class all did their jobs. The damage was done entirely in the summary layer: a
consumer coupled to a payload shape it does not control, no test covering it against the default
shape, and a verdict allowed to contradict the authoritative artifact sitting next to it. P0-1 is a
few lines of precedence logic plus one regression test, and it removes a false negative that can fire
on any project in any sweep.

The two evidence gaps matter more over time than the false negative. A compile matrix that reports
only errors, and cannot say whether it recompiled the code under test, is not a sufficient proof
surface for diagnostic-cleanup work — and diagnostic cleanup is exactly the kind of portfolio task
this lane exists to serve.

## Re-Evaluation 2026-09-04

- Freshness review covered the exact latest 30 commits, latest 25 local tags,
  all 59 remote tags, current release/version surfaces, both retro registries,
  and current status/roadmap/design records. `v0.3.69` was the released
  baseline; local `master`, `origin/master`, and fetched `master` aligned at
  `4fa8dad33b7caf89b57cdc99ee820da8b2b30fcd`.
- P1-1 was selected as the highest-ROI coherent slice because the missing
  evidence let a passing error-only compile be misread as proof that a warning
  cleanup succeeded. It outranked compact build/EDM4U payload work because it
  closes an observed false-positive conclusion, not only a token-cost issue.
- Release `v0.3.70` counts warning occurrences, deduplicates exact
  warning identities, preserves a bounded 20-row diagnostic sample, and carries
  those fields through direct, matrix, compact batch, and multi-project output.
  Compile success remains error-only and backward compatible.
- Validation passes focused host `211/211`, full host `1011/1011` with 14
  expected platform skips, public site `42/42`, and a clean Unity
  `2022.3.62f3` current-source consumer (EditMode `104/104`, PlayMode `5/5`,
  interactive acceptance `9/9`, compile contract `2/2`, verified closeout).
  A clean Unity `6000.0.58f2` consumer also passes EditMode `104/104`, PlayMode
  `5/5`, interactive acceptance `9/9`, compile contract `2/2`, and verified
  closeout.
- P1-2 rebuilt-versus-cache-hit evidence and P2-2's dead `--output` flag remain
  open. This retro is therefore still active.

## Re-Evaluation 2026-09-08

- P1-2 is implemented in current source. Each compile configuration listens to
  Unity's `assemblyCompilationStarted` and (on Unity `2022.1+`)
  `assemblyCompilationNotRequired` events, deduplicates assembly paths, and
  reports `rebuilt_assembly_count`, `cached_assembly_count`,
  `rebuild_evidence_status`, and `rebuild_evidence_basis`.
- Matrix results aggregate the counts, compact MCP output retains bounded
  per-configuration rows, and batch plus multi-project summaries preserve the
  same evidence instead of requiring raw-log grep.
- Unity `2021.3` exposes rebuild-start evidence but not the native
  not-required event, so it reports the limitation explicitly rather than a
  decision-grade cache count.
- Current-source validation passed all `161` package EditMode tests on both
  Unity `2022.3.62f3` and `6000.0.58f2`. Live compile responses reported
  `9` rebuilt / `30` cached assemblies on Unity `2022.3.62f3` and `76`
  rebuilt / `181` cached assemblies on Unity `6000.0.58f2`, each with zero
  compiler errors or warnings and `rebuild_evidence_status: measured`.
- P2-2 is narrower than first recorded: direct batch commands now consume
  `--output`; the remaining work is to pin a lane-independent output shape
  through the multi-project runner. This retro stays active only for that P2.
