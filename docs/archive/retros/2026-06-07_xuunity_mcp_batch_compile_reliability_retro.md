# XUUnity Light Unity MCP Reliability Retrospective

Date: `2026-06-07`
Scope: multi-project MCP compile validation after upgrading a consumer Unity
package dependency to a newer XUUnity Light Unity MCP version.
Artifact root: sanitized host-local run artifacts.

## 1. Executive Summary

The primary failure was not Unity-side compile breakage across the portfolio.
The actual outcomes split into two buckets:

- `9/10` projects completed Unity compile validation successfully through MCP
  after the host helper auto-switched from requested batchmode to GUI fallback.
- `1/10` consumer project never reached Unity compile execution because the
  project bridge was disabled. That is a wrapper / project-wiring blocker, not
  a compile result.

The operator-facing confusion came from three separate signals landing at once:

- the command invoked a `batch-*` lane
- the host helper silently but validly changed the effective lane to GUI because
  license capabilities said batchmode was not available on this host/editor
- the aggregate runner summary still reported `projects_failed: 10` because it
  keyed success off `matrix_status=passed`, which is empty for GUI fallback
  summaries even when `succeeded=true` and `unity_outcome=passed`

So the main reliability issue was summary clarity and lane-truth surfacing, not
Unity compile instability.

## 2. Evidence Base

- chat/session timeline from this Codex thread
- public runner and docs:
  - `AIRoot/Operations/XUUnityLightUnityMcp/README.md`
  - `AIRoot/Operations/XUUnityLightUnityMcp/docs/reference/FEATURES.md`
  - `AIRoot/Operations/XUUnityLightUnityMcp/docs/operations/SMOKE_TESTS.md`
  - `AIRoot/Operations/XUUnityLightUnityMcp/scripts/testing/run_multi_project_batch_compile_matrix.sh`
- sanitized host-local run artifacts
- sanitized project-local state and request journal samples

Notable concrete evidence:

- One successful fallback compile payload reports:
  - `requested_execution_lane=batch`
  - `effective_execution_lane=gui`
  - `license_batchmode_supported=false`
  - `license_blocker_code=access_token_unavailable`
  - `result_summary.transport_outcome=gui_operation_completed`
  - `result_summary.unity_outcome=passed`
- One blocked project payload reports:
  - `transport_outcome=batch_prepare_blocked`
  - `unity_outcome=not_started`
  - top actionable error: bridge disabled

## 3. Timeline

1. Consumer project manifests were updated to a newer MCP package version.
2. Operator launched:
   `run_multi_project_batch_compile_matrix.sh --parallelism 4`
3. Runner discovered `10` MCP-wired Unity projects.
4. For each project, batch preflight ran a license capability check.
5. License capability evidence classified Unity `6000.0.58f2` on this host as
   `batchmode_supported=false` with blocker `access_token_unavailable`.
6. Because `--batch-fallback-mode` defaulted to `auto`, the host helper opened
   GUI fallback lanes instead of failing closed.
7. `9` projects reached live Unity MCP compile operations and completed with
   Unity-side success.
8. One consumer project opened into fallback preparation but failed before
   compile because its bridge was disabled.
9. The per-project status files correctly showed `succeeded=true` for the `9`
   successful projects.
10. The aggregate runner still printed `projects_failed: 10` because the runner
    expected `matrix_status=passed`, which GUI fallback did not populate.

## 4. What Worked Well

- License-aware lane selection did exactly what the public design promised:
  detect batchmode infeasibility and route to GUI fallback.
- Unity-side request journaling for successful fallback compiles was strong.
  For the successful fallback exemplar, request journal evidence exists for:
  - `request_submitted` for `unity.compile.matrix`
  - `request_started` from the Unity bridge
  - `request_completed` from the Unity bridge
  - `request_submitted` / `request_completed` for `unity.editor.quit`
- Closeout verification was stronger than a simple quit ack:
  `process_exit_verified=true` was present in fallback closeout summaries.
- Per-project status files were compact and quick to scan.
- The wrapper preserved enough evidence to separate:
  - license / lane decision
  - bridge readiness
  - Unity request completion
  - editor closeout

## 5. What Worked Poorly

- The aggregate runner verdict was misleading. It effectively marked all GUI
  fallback successes as failures because `matrix_status` was empty.
- The operator path started from a command named `batch-*`, but the decisive
  fact that execution had switched to GUI lived deep inside JSON instead of
  being surfaced in one loud top-line human summary.
- The failure class for the bridge-disabled project was not grouped distinctly
  enough in the aggregate output. It should have been obvious that Unity compile
  never started.
- The license probe log volume was disproportionate to its decision value.
  One blocked project's probe log alone was about `188 KB`.
- `bridge_state.json` was not present as an obvious current-state artifact for
  this retro; practical evidence came instead from embedded ready-state payloads
  and request journal files.

## 6. What Was Not Explicit Enough

- That "supports batch lanes" does not mean "this host currently proves real
  batchmode is usable." Public docs do say this, but the runtime summary did not
  make it hard to miss.
- That `auto` fallback is the default behavior for `batch-*` helpers.
- That `require-batch` is the correct mode when the operator wants a hard
  guarantee of true headless batch execution.
- That the bridge-disabled project's result was a wiring / bridge availability
  failure, not a compile verdict.
- That GUI fallback success currently leaves `matrix_status` blank, which breaks
  some downstream summarizers.

## 7. What the Operator Needed but Did Not Have

- One one-line final verdict per project in human terms, such as:
  - `passed_via_gui_fallback`
  - `failed_before_unity_bridge_disabled`
  - `failed_unity_compile`
  - `failed_wrapper_timeout_unity_unproven`
- A single aggregate summary that counts projects by trust class instead of
  forcing operators to inspect raw JSON.
- An obvious preflight command or runner flag suggestion:
  `license-capabilities --refresh` or `--batch-fallback-mode require-batch`
  when real batch proof matters.
- A direct recovery command for `bridge_disabled`. The error explains how to
  enable the bridge, but the batch summary does not surface a ready-to-run exact
  wrapper command as `recommended_recovery_command`.

## 8. Scoring

Scores are `1-10`, higher is better.

- Unity-side execution stability: `8/10`
- Request journaling quality: `9/10`
- Bridge health observability: `7/10`
- Wrapper-to-operator clarity: `5/10`
- Recovery guidance quality: `6/10`
- Transport lifecycle transparency: `8/10`
- End-to-end trustworthiness during churn: `6/10`
- Parallel request handling: `8/10`
- Token efficiency of the default operator path: `4/10`
- Time-to-diagnosis: `6/10`
- Validation workflow discipline: `8/10`

## 9. Priority Improvements

### P0

- Fix `run_multi_project_batch_compile_matrix.sh` aggregate success logic so GUI
  fallback successes are not counted as failed merely because
  `matrix_status=""`.
- Add a normalized terminal verdict field to status artifacts:
  - `operator_verdict=passed_via_gui_fallback`
  - `operator_verdict=passed_via_batch`
  - `operator_verdict=failed_before_unity`
  - `operator_verdict=failed_in_unity`
  - `operator_verdict=failed_wrapper_unity_unproven`

### P1

- Surface lane switch and license blocker in the first compact line of every
  batch summary, not only inside JSON.
- Add `recommended_recovery_command` for `bridge_disabled`, for example the
  exact `init_xuunity_light_unity_mcp.sh --project-root ... --enable-project`
  form.
- Add an aggregate count by lane and trust class:
  - `batch_passed`
  - `gui_fallback_passed`
  - `prepare_blocked`
  - `unity_failed`
  - `wrapper_unproven`

### P2

- Reduce license-probe log duplication in default operator artifacts. Keep full
  probe logs on disk, but summarize only blocker code, matched evidence, exit
  code, timeout flag, and cache age in compact outputs.
- Expose current bridge-state snapshot as a clearly named stable artifact when
  available, or explicitly report `bridge_state_absent` in summaries.

## 10. Public-Promotion Recommendations

Promote reusable improvements into public `AIRoot`, not project-local docs.

### Docs

- In `README.md` and `FEATURES.md`, add one explicit operator note:
  "A `batch-*` command may legitimately execute as GUI fallback when
  `--batch-fallback-mode auto` is in effect."
- In `SMOKE_TESTS.md`, add a fallback-truth acceptance check:
  GUI fallback compile success must surface a normalized pass verdict and must
  not rely on `matrix_status=passed`.

### Wrapper Output

- Print a one-line preflight summary before long work starts:
  `requested=batch effective=gui blocker=access_token_unavailable fallback=auto`
- Print a one-line terminal summary:
  `verdict=passed_via_gui_fallback unity=passed closeout=verified`

### Request Summary Surfaces

- Extend compact summaries to include:
  - `requested_execution_lane`
  - `effective_execution_lane`
  - `operator_verdict`
  - `unity_truth_class`
  - `recommended_recovery_command`
- Treat `request-final-status` as the canonical recovery hint for wrapper churn,
  but add exact command suggestions for non-request blockers like
  `bridge_disabled`.

### Smoke / Validation Order

- Add an explicit preflight recommendation:
  when true headless batch proof matters, run `license-capabilities --refresh`
  first or force `--batch-fallback-mode require-batch`.
- Keep compile-first discipline, but distinguish:
  - `compile proof in real batchmode`
  - `compile proof via GUI fallback`

### Acceptance Checks

- Add public tests that ensure aggregate runners treat GUI fallback success as a
  successful validation outcome.
- Add a smoke assertion that a `bridge_disabled` prepare blocker reports:
  - `unity_outcome=not_started`
  - a direct recovery command
  - a distinct operator verdict

## 11. Final Verdict

1. Did the Unity operation actually fail, or did only the wrapper/session fail?
   - `9/10`: Unity operation succeeded; requested batchmode failed qualification
     and the wrapper intentionally switched to GUI fallback.
   - `1/10`: Unity operation never started; wrapper/project setup failed because
     the bridge was disabled.

2. Was there enough evidence to prove that distinction?
   - Yes for the successful and blocked exemplars. Request journal and compact
     summaries were sufficient to separate Unity completion from prepare-stage
     blockers.

3. What did the operator need but not have?
   - A normalized final verdict and trustworthy aggregate counts.

4. What recovery step should have been obvious but was not?
   - For real batch proof: rerun with `--batch-fallback-mode require-batch`.
   - For `bridge_disabled`: a copy-pastable enable-bridge command.

5. Which operations or evidence paths were most expensive?
   - The biggest operator-noise sources were `*_batch_stdout.json` payloads with
     hundreds of lines and the large license probe logs.

6. What should be promoted publicly?
   - Batch-vs-GUI truth surfacing, fallback-aware aggregate success logic,
     normalized operator verdicts, and blocker-specific recovery commands.

Bottom line: the portfolio did not expose a broad compile regression from
`v0.3.20`. The retro surfaced an operator-ergonomics and summary-truth problem
in the public MCP batch runner contract.
