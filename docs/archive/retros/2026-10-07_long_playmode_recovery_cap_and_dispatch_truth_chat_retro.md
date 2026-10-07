# XUUnity Light Unity MCP Chat Retro — long PlayMode suites end in a lifecycle-reset error, and a scenario poll reports "not submitted" after dispatch

Date: `2026-10-07`
Status: `intake; improvements proposed, none implemented`
Lane: `interactive_mcp` GUI editors (opened by the wrapper `ensure-ready --open-editor` in one project, self-launched in another) plus raw Unity CLI batch lanes. Packages `v0.3.80` → `v0.3.83` across eight days; Unity `6000.0.58f2` and one `6000.3` reference clone. Three consumer projects; 222 MCP calls in one operator session.

## 1. Executive summary

Unity never failed a bridge request. The misleading verdicts all came from the host, and two of them were dangerous.

- **A poll error was reported as "not submitted" after dispatch (V1, P0, open at `v0.3.83`).**
  - In a consumer project being onboarded, `unity_scenario_run_and_wait` returned `bridge_owned_by_non_main_process` with `request_submitted=false` 12 times.
  - Every one of those scenarios had already been dispatched and ran to completion.
  - The refusal came from the result-polling phase, which read a `bridge_state.json` that an import worker had written.
  - One operator rerun after such a refusal became a real double run: it failed with `scene_open_blocked` because the first run was already in Play Mode.
- **Long PlayMode suites always end in an error (F1, P0, open).**
  - In a standalone game project, two full PlayMode suites (230 and 235 tests) returned `request_lifecycle_reset` after ~307 s, although the caller passed `timeoutMs` 900 000 and 1 800 000.
  - Unity passed both suites at +944 s and +952 s.
  - Cause: Play Mode entry reloads the domain, so the bridge journals `request_abandoned` at ~+6 s. From that point a fixed `post_reset_recovery_cap_ms=300000` replaces the caller's budget.
  - So every PlayMode run longer than ~5 minutes ends in this error.
- **Recovery worked, but cost too much.** `unity_request_final_status` recovered `completed_ok` / `unity_completed_confirmed` / `passed`, and the docs prevented a blind 15-minute rerun. But:
  - the error envelope was 32–33 k characters, client-truncated, and contradictory;
  - the wait for completion had to be written in the shell;
  - the run's console error count could only be a lower bound.
- **Secondary findings:**
  - `xuunity_setup_plan` issued a false "do not run Unity operations" verdict on a fresh git worktree, while the server answering the call was the requested version (F3);
  - an `editor_log` grep returned 28 stack-frame false positives (F5);
  - a raw CLI batch PlayMode run hung with no progress visibility, although the package's test callbacks were loaded (F6);
  - `game_view_configure` persists into the user layout (V2);
  - the MCP console tools drop `explicit_path_requested` (V3).

## 2. Evidence base

- **Session transcript:** 222 `unity_*` / `xuunity_*` calls.
  - 29 results had `is_error=true`.
  - 1.25 M characters of results in total; 9 were client-truncated.
  - Top error codes: `bridge_owned_by_non_main_process` 12, `scenario_failed` 10, `scenario_invalid` 2, `request_lifecycle_reset` 2.
  - The false refusals alone cost ≈112 k characters, and the two lifecycle-reset envelopes ≈66 k.
- **Request journal, game project:** 53 files.
  - Each PlayMode request has 10 events: 4 progress, submitted, started, abandoned, reclassified, delivery_unproven, completed.
  - Deltas from submit:
    - abandoned +5.75 / +6.13 s;
    - new bridge generation +6.22 / +6.70 s;
    - reclassified at abandon +300.2 / +300.0 s;
    - completed +944 / +952 s.
  - Both successful responses remain unconsumed in `outbox/`, and they are what `stale_request_artifacts_present` reports.
- **Batch CLI lane:** about 76 minutes lost. One run was killed by the agent's background limit, and one hung for about 46 minutes. The cause was a test yielding `WaitForEndOfFrame` inside a nested `IEnumerator`: UTF 1.5.1's batch guard sees only top-level yields, and no test timeout fires while the enumerator is parked.
- **Verification:** each finding below was checked read-only against HEAD `b7f1efe` (`v0.3.83`).

## 3. Timeline (condensed)

1. **Onboarding project, day 1.**
   - The bridge was enabled by copying a config, then `ensure-ready --open-editor`.
   - Scenarios ran; one `scenario_invalid` (`ui_click` needs `interactionId`) and one `project_action_catalog_payload_action_conflict`.
   - 12 `bridge_owned_by_non_main_process` refusals followed, each after a Play-entering scenario had started. One rerun produced the double run.
   - Evidence was read from `scenarios/results` in the shell (19 reads).
2. **Same project.** `ui_click` refused an alpha-0 hit-area button. This is the public intake of 2026-09-29, fixed in `v0.3.82`.
3. **Game project, release day 1.**
   - The raw batch PlayMode lane hung, as described in §2.
   - In a fresh worktree:
     - `bridge_disabled`;
     - the false `installation_alignment` block from `setup_plan`;
     - `setup_apply`;
     - a self-launched editor and a shell health poll.
   - `tests_run_playmode` returned `request_lifecycle_reset` at +307 s.
   - A shell wait on `test_results/<id>.json` followed, then `request_final_status` returned `completed_ok`.
4. **Release day 2.** The same sequence: an identical +307 s error and an identical recovery.

## 4. What worked well

- **`unity_request_final_status` compact:** one call turned an error-labelled run into a confirmed pass with counts. `CONTINUATION.md:331-353` ("do not retry the original operation yet") prevented replaying a 15-minute suite.
- **`state/test_results/<id>.json`:** `run_phase`, counts and `last_started_test`/`last_finished_test` made an external wait cheap and gave the progress visibility the CLI lane lacked.
- **Anchored grep:** `unity_console_grep since=request_id` returned `not_matched` over a `complete_anchored_scope_searched` of 9.9 M characters, which is strong negative evidence.
- **Status diagnosis:** `unity_status_summary` named `bridge_disabled` with a remediation, and flagged `editor_launch_lane: not_opened_by_host` up front.
- **The wrapper's `ensure-ready --open-editor`** worked every time it was used.
- **The GUI lane passed render-dependent tests** (frame captures) that the batch lane cannot run.

## 5. What worked poorly (verified at `v0.3.83`)

### 5.1 Tool defects

- **V1 — `request_submitted=false` after dispatch.**
  - Where it comes from:
    - `templates/server_mcp_tools.py` `call_unity_scenario_run_and_wait_tool` keeps `unity.scenario.run` and the result wait in one `try`, so a poll error discards the `run_id` of a dispatch that succeeded.
    - The ownership check in `server_batch_orchestrator._invoke_bridge_locked` hard-codes `request_submitted=False` for every bridge call, the polls included.
    - The code is in neither `TRANSIENT_SCENARIO_POLL_ERROR_CODES` nor `SCENARIO_RECOVERY_ERROR_CODES`.
  - Root cause of the worker-written state: `XUUnityLightMcpLifecycleMonitor` has its own `[InitializeOnLoad]` and writes heartbeats through `BridgeStateWriter.WriteHeartbeat` with no process-class guard.
- **F1 — the post-reset cap overrides the caller's timeout.**
  - `templates/xuunity_light_unity_mcp_runtime_defaults.json` and `server_specs_lifecycle.py` set `post_reset_recovery_cap_ms=300000` for `unity.tests.run_playmode`.
  - The `transport_restarting` branch in `server_bridge_transport.py` polls for `min(remaining, cap)`.
  - A host-local `runtime_config.json` override with any value above 0 re-imposes the cap.
- **F2 — the lifecycle-reset error ignores compact mode.**
  - `server_mcp_tools.py` drops `includeFullPayload` on the `ToolInvocationError` path.
  - `build_lifecycle_reset_tool_error` embeds the full final-status and stabilization objects.
  - Result: 32–33 k characters against the 8 192-byte compact ceiling. `docs/reference/FEATURES.md:44` overclaims compact transport-failure envelopes.
  - The envelope also contained:
    - an `elapsed_runtime_seconds` of 14 s while progress was at +4 m 52 s;
    - `timeout_classification=runtime_timeout_after_test_start` with `runtime_timeout_observed=false`;
    - a cleanup command recommending a Play Mode exit mid-run, which would have aborted a passing suite;
    - a shell-script recovery command rather than the MCP tool.
- **F3 — `setup_plan` ignores the live session.**
  - Client targets come only from the Unity project root (`server_setup_plan.py`), and `server_setup_common.py` checks only the user-scope config and `<unity_project>/.mcp.json`.
  - A client wired at a workspace-root `.mcp.json` above a nested project is invisible.
  - `current_mcp_session_safe=False` / `live_mcp_session_status="unverified"` are hard-coded, although the answering server's `SERVER_INFO.version` matched the requested release.
- **F5 — the console error count is a lower bound for every domain-reload PlayMode run.**
  - `XUUnityLightMcpConsoleBuffer` keeps a static counter whose session id resets on each domain load, so `XUUnityLightMcpTestRunState` reports `lower_bound_after_domain_reload`.
  - Separately, `server_health.py` `grep_editor_log_payload` does not apply `includeStackTraces=false` to `source=editor_log`. The 28 matches were UIElements renderer frames whose signatures contain `System.Exception&`.
- **F6 — CLI test runs get no progress.**
  - `XUUnityLightMcpPlayModeTestsOperation` registers UTF callbacks on every domain load, including CLI `-runTests`.
  - `XUUnityLightMcpPersistedTestCallbacks` keeps them inactive unless a bridge request owns the run.
- **V2 — `game_view_configure` persists into the user layout.** `XUUnityLightMcpGameViewUtility.SetFixedResolution` writes `selectedSizeIndex` without reading or returning the previous selection, and scenario cleanup does not restore it. The size survives into `UserSettings/Layouts/*.dwlt`.
- **V3 — the MCP console tools drop `explicit_path_requested`.** The grep and tail handlers in `server_batch_orchestrator.py` never pass the flag and resolve the path without `bridge_state`. The CLI path does both.

### 5.2 Journal truth

- **`request_abandoned` is retryable for runs that resume.** It is written with `retryable=true` for a PlayMode run that the bridge resumes and completes in the next generation, which invites replaying a long suite.
- **`request_reclassified` records a stale generation.** It shows current generation = previous, with a hard-coded "generation changed" reason, because the state is read when `transport_restarting` arrives and never refreshed.
- **`lifecycle_churn_observed` stays `false`** in persisted results, although the generation changed.
- **`runtime_timeout_ms` is not enforced or classified.** A run 44 s over its runtime timeout reported `passed` with an empty classification.
- **Orphaned outbox responses are never consumed.** `request_final_status` only peeks, so every recovered run leaves `stale_request_artifacts_present`.
- **Progress events cannot be ordered:**
  - most `operation_progress` events carry `request_id: ''`;
  - same-millisecond files sort by random UUID, so file order is not causal.
- **Dead batch processes leave a "healthy" state file.** Batch CLI processes in the same project leave `bridge_state.json` `healthy` with a dead PID. The host filters by process class, but a shell poll cannot.
- **The log-path risk is always raised.** `editor_launch_lane_risk: host_default_editor_log_path_may_be_stale` is unconditional for `not_opened_by_host`, even when the bridge's own log path is the default.

### 5.3 Operator errors

- Self-launched editors in the game project, although `README.md` names `ensure-ready --open-editor` as the default launch path. The result was a hand-rolled health poll and a hand-deleted state file.
- Re-ran a scenario after the refusal without reading `scenario_result_latest` first.
- Ran raw CLI batch PlayMode against the README guidance. The consumer's own release doc prescribes it, and so does `AI_INTEGRATION.md:356-357`.
- Read one lane's `last_started_test` as the location of another lane's hang.
- Used a generic unanchored error grep, and a `^`-anchored pattern against log lines that carry a logger prefix. The tool behaved as documented.

## 6. What was not explicit enough

- **The 300 s post-reset cap** is documented nowhere. Neither is guidance to size `timeoutMs` above a suite's length; `AGENT_WORKFLOWS.md` uses 240 000.
- **There is no wait-until-terminal primitive:**
  - `unity_request_final_status` is single-shot;
  - `request-latest-status` has no MCP tool;
  - no public doc mentions the `active_test_*` progress fields of `unity_status_summary`.
- **The domain-reload lower bound** is undocumented. `SMOKE_TESTS.md` recommends a noisy `Exception|error` editor-log grep, with no request-scoped recipe.
- **The `installation_alignment` block from `setup_plan` is undocumented.**
- **The MCP surface never names `ensure-ready`.** Neither the initialize instructions nor the `bridge_disabled` envelope does; `bridge_disabled` recommends setup plan/apply plus "reopen Unity".
- **The batch-PlayMode docs contradict each other, and nothing names the hang.** `AI_INTEGRATION.md:354-357` offers raw batch PlayMode as the fallback when the bridge is unavailable, contradicting `README.md:876-877`. No doc mentions the nested `WaitForEndOfFrame` batch hang.

## 7. What the operator needed but did not have

1. A dispatch flag that stays true once a run has started, with `run_id` and a "poll, do not rerun" next step.
2. A test call that waits for the caller's whole budget across the Play-entry reload, or a compact `in_progress_after_domain_reload` envelope that names the wait call.
3. Setup output that credits the answering server as live-session proof.
4. A pointer from the MCP surface to `ensure-ready --open-editor`.
5. An exact request-scoped error count, and an `editor_log` grep that drops stack frames.
6. Per-test progress for CLI test runs.
7. The previous Game view size.

## 8. Scoring

| Category | Score | Note |
|---|---|---|
| Unity-side execution stability | 10/10 | No bridge request failed in Unity |
| Request journaling quality | 6/10 | Retryable `abandoned` for resumed runs, stale reclassification generation, progress without `request_id`, orphaned outbox |
| Bridge health observability | 6/10 | Worker-written state caused 12 false refusals; dead batch processes leave a "healthy" file |
| Wrapper-to-operator clarity | 4/10 | False `request_submitted=false`; error at a fixed 300 s; contradictory fields; a run-aborting cleanup hint; a false setup stop |
| Recovery guidance quality | 7/10 | Final-status recovery worked and prevented a blind retry; the launch helper is invisible from MCP |
| Transport lifecycle transparency | 6/10 | Reload journaled; reclassification reason and generation wrong |
| End-to-end trustworthiness during churn | 5/10 | One real double run; two green suites reported as errors |
| Parallel request handling | n/a | Sequential bridge use |
| Token efficiency of the default operator path | 5/10 | 1.25 M characters; ≈112 k on false refusals; ≈66 k on two truncated error envelopes |
| Time-to-diagnosis | 5/10 | ≈76 min in the invisible batch lane; hand-rolled waits |
| Validation workflow discipline | 7/10 | Final-status recovery, anchored grep, full regressions; self-launch and rerun-after-refusal |

## 9. Priority improvements

| # | Improvement | Surface | Size |
|---|---|---|---|
| P0-1 | `scenario_run_and_wait`: separate dispatch from wait. Once a `run_id` exists, a poll error returns `request_submitted=true`, `run_id` and `recommended_next_action=poll_scenario_result`. Make `bridge_owned_by_non_main_process` a transient poll error, and reconcile the persisted result before raising. Import workers never write heartbeats (`LifecycleMonitor` / `BridgeStateWriter` process-class guard) | server + package | small–medium |
| P0-2 | Test operations wait the caller's whole budget across the Play-entry reload: no post-reset cap for `unity.tests.run_*`, so the existing `transport_restarting` branch takes the outbox response | server | small |
| P1-1 | Compact lifecycle-reset error: compact final-status projection, a structured `recovery_tool: unity_request_final_status` with arguments, no contradictory fields, and no Play Mode exit cleanup while `run_phase=running` | server | small |
| P1-2 | `setup_plan` credits the answering server as live proof (`proven_by_answering_mcp_server`) and searches ancestor `.mcp.json` files | server | small |
| P1-3 | Journal truth: resumed test runs are not retryable on abandon; refresh the generation at reclassification; set `lifecycle_churn_observed`; classify runtime-timeout overruns; final status consumes the outbox; progress events carry `request_id` and a sequence number | server + package | medium |
| P2-1 | `editor_log` grep honours `includeStackTraces=false` and reports `stack_frame_suppressed_count`. The test final status adds an editor-log error count from the request's anchor offset | server | small |
| P2-2 | CLI test progress sidecar (`state/cli_test_progress.json` in batch runs not owned by the bridge). Docs: remove the raw batch PlayMode fallback and add the nested `WaitForEndOfFrame` caveat | package + docs | small–medium |
| P2-3 | The initialize instructions and the status description name `ensure-ready --open-editor`. `bridge_disabled` with no live editor recommends it. Raise the launch-lane risk only when the log paths differ | server | small |
| P3-1 | MCP console grep/tail pass `explicit_path_requested` and resolve the path with `bridge_state` | server | tiny |
| P3-2 | `game_view_configure` returns `previous_game_view`, and the docs state that the size persists | package + docs | small |
| P3-3 | Document the post-reset cap (until P0-2 ships), `timeoutMs` sizing for suites, the `active_test_*` fields and a persisted-result wait recipe | docs | tiny |

## 10. Acceptance checks

- **P0-1:**
  - A fake bridge returns a `run_id`, the first poll raises an ownership refusal, and the next poll passes. The tool returns success with that `run_id`.
  - If the refusal persists to the deadline, the envelope has `request_submitted=true`.
  - Live: ten Play-entering `run_and_wait` calls give zero refusals and exactly one persisted result each.
- **P0-2:** A fake TCP bridge answers `transport_restarting` at t≈0 and writes `request_completed` plus the outbox response at t≈2.5 s, with the cap patched to 1 s and a 4 s budget. `invoke` returns the response; no `request_reclassified` or `delivery_unproven` is written.
- **P1-1:** The lifecycle-reset envelope stays under the compact ceiling and carries `recovery_tool_arguments.requestId`.
- **P1-2:** With `CLAUDECODE=1`, no user/project server block and matching versions, the MCP-lane plan has no client blocker and `live_mcp_session_status=proven_by_answering_mcp_server`. The CLI lane is unchanged.
- **P2-1:** A synthetic log with 28 `System.Exception&` frames returns 0 matches by default and `stack_frame_suppressed_count=28`.

## 11. Promotion targets

- `README.md`: the launch-path pointer from the MCP surface, and editor_log frame suppression.
- `docs/architecture/DESIGN.md`: the reconnect policy for test operations, and journal truth.
- `docs/operations/CONTINUATION.md`: a long-suite wait recipe.
- `docs/operations/SMOKE_TESTS.md`: replace the noisy error grep; add a >5 minute PlayMode suite smoke and a dispatch-then-refusal scenario smoke.
- `docs/agents/AI_INTEGRATION.md`: the batch PlayMode contradiction.
- `docs/reference/FEATURES.md:44`: the compact error claim.

## 12. Final verdict

Unity is reliable. Host verdicts are not yet trustworthy for PlayMode suites longer than five minutes, or for scenario dispatch while import workers churn.

Both P0 fixes are small:
- separate dispatch from wait, and guard worker heartbeats;
- remove the post-reset cap for test operations.

Together they would have prevented the double run and both false errors.
