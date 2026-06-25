# XUUnity Light Unity MCP Scenario Run-Wait Compact Smoke False-Negative Retro

Date: `2026-06-25`
Status: `implemented with follow-up watch`
Scope: scenario run-and-wait compact envelopes, smoke helper parsing, devmode refresh settle, PlayMode lifecycle churn, project-action scenario validation

## Resolution Update

Implemented on `2026-06-25` in the same maintenance wave:

- compact `unity_scenario_run_and_wait` verdicts now expose
  `payload_mode=compact_decision`, `steps_payload_mode=compact_summary`,
  `raw_steps_included=false`, raw/compact step counts, structured
  `full_payload_cli_args`, and `full_payload_tool_arguments`
- public smoke helpers that inspect per-step scenario data now request
  `--include-full-payload`
- a unit regression prevents step-level smoke helpers from parsing compact
  verdicts without full payload opt-in
- MCP tool schema, README, and smoke docs now describe compact versus full
  payload semantics
- `devmode` output now emits a concrete package re-resolve refresh command and
  structured args JSON

Remaining watch item: the consumer-project PlayMode lifecycle smoke still
exercises real Unity editor restarts/churn and should keep using status/final
status evidence to distinguish editor disappearance from contract regression.

## 1. Executive Summary

A devmode switch and post-change MCP smoke on a consumer Unity project exposed three operator-facing reliability problems.

First, the first acceptance scenario run failed with an infrastructure timeout while waiting for project refresh to settle after switching the package dependency to a local file dependency. A direct `request-project-refresh --resolve-packages` with a longer timeout settled successfully, and the acceptance scenario later passed.

Second, the PlayMode settled-state regression smoke failed with `scenario result is missing playmode_test step`, but the persisted Unity scenario result showed `status=passed`, `passed_steps=1/1`, `stepId=playmode_test`, and `playmode_state_after_settle=edit`.

Third, a project-action catalog consistency smoke failed on `hook_name,payload_action,outcome`, but the persisted Unity scenario result showed `status=passed`, `hook_name=sample.localization`, `action=list_actions`, and `outcome=actions_listed`.

The Unity-side operations did not fail in the second and third cases. The smoke helpers failed because they parsed `request-scenario-run-and-wait` default compact output as if it contained full `steps`. The smallest fix is for smoke helpers that inspect step payloads to call `request-scenario-run-and-wait --include-full-payload`, and for the public smoke contract to make that rule explicit.

## 2. Evidence Base

- Wrapper-visible failures:
  - first acceptance scenario: `project_refresh_timeout` / `refresh_waiting_for_settle`
  - PlayMode smoke: `scenario result is missing playmode_test step`
  - project-action smoke: `Unity raw run consistency errors: hook_name,payload_action,outcome`
- Wrapper-visible successes:
  - direct refresh with package resolve completed through `unity_refresh_settle_watcher`
  - compile matrix passed `6/6`
  - acceptance scenario passed `10/10` on retry
  - contract scenario passed
  - PlayMode lifecycle retry smoke passed
  - project-action catalog consistency passed after requesting full scenario payload
- Persisted scenario evidence:
  - PlayMode regression scenario result: `status=passed`, `passed_steps=1/1`, `stepId=playmode_test`, `outcome=tests_passed`
  - project-action run scenario result: `status=passed`, `passed_steps=1/1`, `kind=project_defined_hook`, `outcome=actions_listed`
- Bridge-state evidence:
  - final status was healthy, idle, edit mode, with zero compiler errors
  - status summary exposed lifecycle churn and stale outbox warnings without making them terminal
- Current public docs already mention compact summaries, lifecycle churn recovery, PlayMode result parity smoke, and project-action compact summary goals; the missing contract is when a smoke helper must opt into full payload.

## 3. Timeline

1. Switched a consumer project from Git package dependency to local devmode file dependency.
2. Ran the project post-change MCP validation wrapper.
3. Initial compile matrix passed, but acceptance scenario timed out in refresh settle.
4. Ran an explicit refresh-and-resolve request with a longer timeout; it completed and left the bridge healthy.
5. Re-ran post-change validation. Compile, acceptance, and contract scenarios passed.
6. PlayMode settled-state regression failed in the shell helper, while the Unity scenario artifact showed the PlayMode scenario passed.
7. Added `--include-full-payload` to the PlayMode regression helper's `request-scenario-run-and-wait` call.
8. Re-ran the PlayMode regression helper; direct and scenario PlayMode payloads both settled to `edit`.
9. Re-ran the full post-change wrapper. The main suite passed, then project-action catalog consistency failed in the shell helper.
10. Inspected the project-action scenario artifact; Unity had resolved the alias to the expected hook and payload.
11. Added `--include-full-payload` to the project-action consistency smoke's `request-scenario-run-and-wait` call.
12. Re-ran the project-action consistency smoke; it passed.

## 4. What Worked Well

- Persisted scenario results were authoritative enough to separate Unity execution from shell parsing failure.
- Request ids and bridge generation/session ids made lifecycle churn visible rather than mysterious.
- `request-status-summary` gave a compact final state: healthy bridge, edit mode, idle, zero compiler errors.
- The compile-first validation order prevented wasting time on scenario diagnosis before confirming scripts compiled.
- The `--include-full-payload` flag already existed, so the fix did not require a public operation contract change.

## 5. What Worked Poorly

- The default compact `request-scenario-run-and-wait` envelope is excellent for operator decisions but unsafe for smoke helpers that inspect per-step fields.
- The smoke helpers did not encode that distinction and produced false-negative failures.
- The first refresh timeout after devmode did not make the obvious recovery path prominent enough.
- High lifecycle churn was reported only at the suite end, after several expensive operations had already run.
- The operator had to inspect raw scenario result files to prove that Unity had succeeded.

## 6. What Was Not Explicit Enough

- Smoke helpers must use `--include-full-payload` when they inspect `steps`, `payload_json`, `hook_name`, or per-step outcomes.
- Compact scenario verdicts are decision envelopes, not parity fixtures.
- A devmode package switch may require an explicit long-timeout refresh-and-resolve before scenario acceptance.
- A scenario artifact can be more authoritative than shell stdout after lifecycle churn or compact-output mismatch.
- Stale request artifact warnings should be accompanied by a clear "non-terminal unless..." explanation in suite summaries.

## 7. What The Operator Needed But Did Not Have

- A one-line wrapper hint: "This command returned compact scenario output; rerun with `--include-full-payload` before asserting step-level fields."
- A smoke-library helper that centralizes "run scenario and require full steps" instead of repeating raw CLI calls.
- A post-devmode validation path that performs or recommends long-timeout refresh-and-resolve before scenario smoke.
- A compact summary field that says whether `steps` are present, omitted by design, or unavailable.
- A suite-level classification for "Unity passed, smoke parser failed."

## 8. Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 8/10 | The later Unity operations passed; the initial refresh needed a longer settle window after devmode. |
| Request journaling quality | 8/10 | Request ids and persisted results gave the truth, but the operator had to dig for it. |
| Bridge health observability | 9/10 | Status summary clearly reported healthy/idle/edit/zero compiler errors. |
| Wrapper-to-operator clarity | 5/10 | Compact-vs-full payload semantics were not clear at the failure site. |
| Recovery guidance quality | 6/10 | The right recovery existed, but it was not the obvious next action from the failure. |
| Transport lifecycle transparency | 8/10 | Generation/session churn was visible and non-terminal when recovered. |
| End-to-end trustworthiness during churn | 6/10 | Persisted artifacts were trustworthy; shell smoke verdicts were not. |
| Parallel request handling | 7/10 | No evidence of unsafe parallel bridge mutation; operator discipline was still required. |
| Token efficiency of the default operator path | 6/10 | Compact output saved tokens but forced raw artifact inspection when the helper expected full data. |
| Time-to-diagnosis | 6/10 | Diagnosis was possible but required repeated reruns and manual artifact reads. |
| Validation workflow discipline | 8/10 | Compile-first and targeted reruns kept the session bounded after the root cause was found. |

## 9. Priority Improvements

P0:
- Done: update public smoke helpers that inspect per-step scenario data to use `request-scenario-run-and-wait --include-full-payload`.
- Done: add a regression test that catches `request-scenario-run-and-wait` followed by step-level parsing without `--include-full-payload`.
- Done: document the compact-vs-full scenario output contract in `docs/operations/SMOKE_TESTS.md`.

P1:
- Deferred: add a reusable shell function such as `run_full_payload_scenario_step` for smoke helpers if more call sites appear.
- Done: promote compact payload-mode fields into `request-scenario-run-and-wait` output when raw step fields are omitted by design.
- Done: add post-devmode validation guidance via docs and a concrete `recommended_refresh_args_json` launcher output.

P2:
- Make suite closeout classify false-negative smoke parser failures separately from Unity execution failures when persisted scenario results are terminal/passed.
- Add a compact "scenario result artifact path" to successful compact scenario verdicts so operators can jump directly to evidence without listing result folders.

## 10. Public-Promotion Recommendations

- `docs/operations/SMOKE_TESTS.md`: add a "Compact Scenario Verdict vs Full Scenario Payload" subsection.
- `templates/smoke/run_playmode_settled_state_regression.sh`: keep `--include-full-payload` for scenario parity checks.
- Project-specific smoke templates that validate project-action hook payloads: require `--include-full-payload`.
- Wrapper summaries: expose whether full steps were included or intentionally omitted.
- Continuation guidance: after devmode dependency switching, prefer explicit refresh-and-resolve before judging scenario timeouts.

## 11. Final Verdict

This was primarily a smoke-wrapper false-negative, not a Unity execution failure. The persisted Unity results and bridge state were sufficient to prove the distinction, but the operator path made that proof too expensive. The reusable fix is to reserve compact scenario output for operator verdicts and require full payload mode for parity fixtures, per-step assertions, and project-action payload contract checks.
