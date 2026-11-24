# XUUnity Light Unity MCP Chat Retro — UI driving cost, two incomplete fixes, and the editor quit outside MCP

Date: `2026-11-19`
Status: `partial (v0.3.91): RG-60, RG-61, RG-62, RG-63, RG-66, RG-70, RG-71 and RG-72 done; RG-64, RG-65, RG-67, RG-68 and RG-69 open`
Lane: two interactive operator chats (a parent and a child) that worked on one reward feature from 2026-11-09 to 2026-11-16, on `v0.3.88` and then `v0.3.90`, Unity `6000.0.58f2` on macOS. A hub project with GUI editors in managed background Play Mode, plus one closed consumer project. 224 MCP calls. Two sessions shared one checkout and one editor for part of the time.

Public twin of a host-private retro. Project names, feature and ticket names, run and player ids, scenario paths and local paths are left out.

## Status (2026-11-24, v0.3.91)

| Item | Status | What shipped | What remains / next step |
| --- | --- | --- | --- |
| RG-60 a required click refused before delivery reads `unity_unproven` | done (v0.3.91) | `42c1dc4`: every refusal that proves the target's state after a complete search ends `failed` / `precondition` (`ui_target_not_interactable`, `ui_target_not_pointer_targetable`, `ui_target_has_no_click_handler`, `ui_target_does_not_block_raycasts`, `selector_ambiguous`, as well as the absent-target codes RG-53 covered). | — |
| RG-61 frame filtering misses nested and async frames | done (v0.3.91) | `19c2042`: `includeStackTraces: false` also drops `Type/<Method>d__N:MoveNext ()`, generic runners that carry such a type, and closure classes. | — |
| RG-62 unknown selector keys are ignored | done (v0.3.91) | `701bed5`: `unknown_selector_key` before anything reaches Unity, naming the key and the closest valid keys, on the five UI tools and scenario UI steps. | — |
| RG-63 editor quit is CLI-only | done (v0.3.91) | `6c90cc1`: `unity_editor_quit` runs `request-editor-quit` and `verify-editor-closed` and returns `closeout_classification`; it needs `approve: true` and refuses while the editor is busy unless `allowWhileBusy: true`. | — |
| RG-64 `busy_reason: idle` during another session's test run | open | — | Derive `busy_reason` from the active test phase and Play Mode state; add `waitForIdleMs` to `unity_status_summary`. |
| RG-65 identical sibling paths cannot be addressed | open | — | `matchIndex` (document order among matches) or ancestor-text matching in the selector. |
| RG-66 `bridge_disabled` advises setup where `ensure-ready` is enough | done (v0.3.91) | `f887f74`, plus `bb98ae8` after a live check found the error text still advised setup: with the package declared, every field recommends `open_editor_or_ensure_ready`. | — |
| RG-67 `runInBackground` churn after managed Play Mode | open; reproduce first | — | Hypothesis: a mutating action 1–2 s after leaving managed Play Mode saves before the restore. Restore at `ExitingPlayMode`, or hold saves until the restore. |
| RG-68 no scroll primitive for a target below the fold | open | — | `scrollIntoView` on `ui_click` (nearest `ScrollRect`, then raycast again) or a `ui_scroll` step. |
| RG-69 `ui_click`, `prefab_mutate` and `project_action_list` payload size | open | — | Compact defaults: verdict, target path and tree-change status for a click; ids only for the action catalog. |
| RG-70 a console line returned a session token verbatim; no per-line cap | done (v0.3.91) | `bc2b647`, `c6a0135`: token-like values come back as `[REDACTED]` with `redacted_secret_count`; one line is capped at 2048 bytes by default (`maxItemBytes`). | — |
| RG-71 `stale_risk` caveat after an ordinary refresh | done (v0.3.91) | `bf61986`: a same-editor domain reload is `expected_domain_reload`. | — |
| RG-72 scenario `ui_click` requires `interactionId` | done (v0.3.91) | `2439fbd`: it defaults to the step's `stepId`. | — |
| RG-58 extension: assembly filters are opaque in PlayMode results too | open | — | Part of RG-58 (`2026-11-19_sdk_rollout_typed_lane_discoverability_chat_retro.md`). |

## 1. Executive summary

No Unity-side failure and no transport loss in 224 MCP calls.

- Every test, compile and Play Mode result was true, including full suites of about 2,500 EditMode tests (the only
  failure was a known flaky project test) and about 490 PlayMode tests.
- Earlier fixes held in real work: the stale-domain refusal (RG-42) caught an edit made one second earlier by another
  session on the shared checkout; full type names resolved (RG-48); serialized references were set on real prefabs;
  console context lines (RG-50) replaced raw log reads; managed background Play Mode ran every unfocused session
  without focus workarounds.

The main cost was UI driving on a fresh test player.

- `ui_click` plus `ui_query` took 548 KB of 1,064 KB, 52% of the MCP bytes in both chats. Most of it went on
  dismissing a chain of startup popups, one query and one click per popup, at about 7.7 KB per click (RG-69).
- Two UI cases could not be done at all: two dropdowns of a third-party debug overlay share one hierarchy path
  (RG-65), and a banner below the fold needs scrolling (RG-68). Because of these, one bug repro was never run live.

Two fixes from `v0.3.89` were incomplete.

- RG-53 classified only absent targets as precondition failures. A required click refused as
  `ui_target_not_interactable` still ended `inconclusive / unity_unproven` (RG-60).
- RG-20 frame filtering missed Unity async and nested-type frames (RG-61). Up to half of a `console_grep` result was
  stack frames.

Smaller gaps: unknown selector keys were silently ignored (RG-62); quitting the editor worked only through CLI host
helpers, so the chats dropped to a shell three times (RG-63); `busy_reason: idle` during another session's test run
(RG-64); `bridge_disabled` advised setup where `unity_ensure_ready` was enough (RG-66); a `runInBackground` churn
candidate (RG-67); token and noise items (RG-69, RG-71, RG-72); and a session token returned verbatim in a log line
(RG-70).

## 2. Findings

| Finding | Severity | Attribution | Basis |
| --- | --- | --- | --- |
| RG-60 Pre-delivery click refusals other than "absent" read as unproven | P2 misleading verdict | scenario verdict classification | The absent-refusal set held only `ui_node_not_found` and `ui_target_not_visible`; `not_interactable` and `not_pointer_targetable` fell through to `inconclusive`. Recurrence of RG-53. |
| RG-61 Managed frames of nested and async types pass the frame filter | P2 noise | console frame pattern | The pattern accepted no `/` in a type name and no `<…>` method token. Three real frames (an async state machine, a generic task runner, a tween closure) all failed it. Recurrence of RG-20. |
| RG-62 An unknown selector key widens the match | P2 silent contract | UI tool selector schema | `{"nameContains": …}` was dropped and `unity_ui_query` returned 20 unrelated nodes; the selector was a bare object and the package deserializer ignores unknown keys. Sibling of RG-44. |
| RG-63 Closing the editor needs a shell | P2 discoverability | MCP tool surface | The quit helpers worked (every close ended `quit_ack_and_process_exit_verified`), but none was an MCP tool. One chat spent 6 shell calls finding the launcher. Closing was needed to revert project settings safely. |
| RG-64 A foreign test run reads as idle | P2 observability | `unity_status_summary` busy state | `busy_reason: idle` while `active_test_run_phase: running` and `playmode_state: playing` for another session's run; the chat polled `bridge_state.json` in a shell loop. |
| RG-65 Duplicate sibling paths cannot be targeted | P2 selector gap | UI selector | Two dropdowns instantiated from one prefab share the same `(Clone)` path, and no selector field picks one of them. |
| RG-66 The expensive recovery is advised first | P2 recovery advice | `bridge_disabled` envelope | On a closed project that declares the package, the advice was setup-plan, setup-apply and a reopen; `unity_ensure_ready {openEditor: true}` enabled the bridge and was ready in one call. Residual of RG-22a. |
| RG-67 `runInBackground` 0 → 1 left after managed Play Mode | P2 churn, unconfirmed | Play Mode settings restore | Seen after managed Play Mode cycles on 11-09 and twice on 11-13, with no config action. Recurrence candidate of RG-29. |
| RG-68 A clipped target cannot be scrolled into view | P3 missing primitive | `ui_click` | A banner at y=3257 in a 3200-pixel render was refused `ui_target_not_pointer_targetable`. |
| RG-69 UI and catalog payloads are not compact | P3 token cost | `ui_click`, `prefab_mutate`, `project_action_list` | `ui_click` averaged 7.7 KB (39 calls, 307 KB); a successful one-operation `prefab_mutate` 5.4 KB; the full action catalog 36 KB. |
| RG-70 A log line carried a session token; no per-item cap | P2 redaction / P3 size | `console_grep` | One item was 11.2 KB (a response body preview); another returned a session token verbatim. |
| RG-71 A plain refresh attaches a Play Mode caveat | P3 noise | `unity_project_refresh` settle classification | 8 of 9 refreshes attached `stale_risk` after an ordinary domain reload. |
| RG-72 Scenario and direct click contracts differ | P3 contract friction | scenario validation | A scenario `ui_click` required `interactionId`, the direct tool did not; one `scenario_invalid`. |

RG-58 extended: a PlayMode run filtered to two assemblies returned the same 84 tests as a run filtered to one, with no
note that the second assembly contributed 0.

## 3. Timeline

| When (UTC) | Chat | What |
| --- | --- | --- |
| 11-09 | child | Check of the previous batch on `v0.3.88`: `optional` dismissals work. Two runs end `inconclusive` after a backend 503 (RG-53, fixed in `v0.3.89`). The editor is closed through the CLI after 6 shell calls to find the launcher (RG-63). |
| 11-13 | child | A UI fix; full EditMode and PlayMode suites pass. `runInBackground` 0 → 1 appears twice after managed Play Mode and is reverted twice (RG-67). |
| 11-16 11:57 | child | `editor_domain_stale` refusal one second after another session edited code. Correct. |
| 11-16 12:16 | child | Bug repro scenario: a required click refused as `ui_target_not_interactable` ends `inconclusive / unity_unproven` (RG-60). A debug-overlay dropdown cannot be targeted (RG-65). A banner below the fold is refused and cannot be scrolled (RG-68). |
| 11-16 12:20–13:16 | parent | A refactor: compile, PlayMode 84/84, full EditMode. Proving that 4 new tests ran needed a second run by `testNames` (RG-58). |
| 11-16 13:17–13:39 | parent | Live check on a fresh test player: onboarding and 9 popups, about 9 query and click pairs. One `ui_query` with an unknown key returns 20 unrelated nodes (RG-62). The network order around an open ad is proven from the log; `console_grep` returns `MoveNext` frames (RG-61). |
| 11-16 13:39–13:43 | parent | Closed consumer project: `status_summary` says `bridge_disabled` with setup advice; `unity_ensure_ready {openEditor: true}` opens and enables the bridge in one call (RG-66). The editor is closed through the CLI (RG-63). |
| 11-16 14:00–14:23 | child | Final tests pass. The chat waits for another session's test run by polling `bridge_state.json` while `status_summary` says `busy_reason: idle` (RG-64). |

## 4. What worked well

- **Unity truth.** No call reported a false Unity failure. Long full-suite runs were single calls, and the compact test
  payload was enough for verdicts.
- **The stale-domain refusal** caught a concurrent edit on a shared checkout; without it the run would have tested old
  code.
- **Ordering questions were answered from the log.** `console_grep` with `since: playmode_start`, `afterLines` and a
  request-line pattern showed that a reward call was absent while an ad was open, appeared only after the close, and
  that the follow-up calls came in order.
- **`ui_click` refusals were precise.** `ui_target_occluded` named the popup that covered the target, so one extra
  click fixed it.
- **One-call editor open on a cold project.** `unity_ensure_ready {openEditor, backgroundOpen}` ran the compile
  preflight, launched the editor and enabled the bridge.
- **Managed background Play Mode and `waitForTreeChangeMs`** worked every time.

## 5. What the operator needed but did not have

- The existing quit helpers as an MCP tool that verifies process exit (shipped as `unity_editor_quit`, RG-63).
- A selector field to pick among duplicates (RG-65, open).
- A `scrollIntoView` option or a `ui_scroll` step (RG-68, open).
- A wait-for-idle that counts another client's test run as busy (RG-64, open).
- A compact `ui_click` envelope (RG-69, open).
- For a fresh test player, a scenario or project action that dismisses known popups with `optional: true` instead of
  one manual pair per popup. This is consumer project work on top of existing scenario steps.
- Project hooks that change environment configuration left 9–12 changed files, reverted by hand four times across both
  chats; a written-file list in the hook result would make that revert mechanical.

## 6. Scoring (1–10)

| Category | Score | Note |
| --- | --- | --- |
| Unity-side execution stability | 9 | No Unity failure in 224 calls |
| Request journaling quality | 7 | No arbitration needed; 6 journal or result reads only to rebuild a payload |
| Bridge health observability | 6 | `busy_reason: idle` during a foreign test run; `stale_risk` noise |
| Wrapper-to-operator clarity | 6 | Silent selector keys; the RG-60 verdict; frames in grep |
| Recovery guidance quality | 7 | Occluder named; `bridge_disabled` advice was the expensive path |
| Transport lifecycle transparency | 9 | No lifecycle resets |
| End-to-end trustworthiness during churn | 8 | The stale-domain refusal caught a concurrent edit |
| Parallel request handling | 6 | Two sessions on one checkout and editor; no MCP wait primitive, shell polling |
| Token efficiency of the default operator path | 5 | `ui_click` and `ui_query` 52%; a 36 KB catalog; an 11 KB log line |
| Time-to-diagnosis | 8 | Network-order proofs came from one grep each |
| Validation workflow discipline | 8 | Compile, tests, then a live check each time; churn reverted |

## 7. Evidence

- Both chat transcripts, parsed by script from 2026-11-09 16:49Z: 109 MCP calls with 555 KB of results, and 115 calls
  with 509 KB.
- Source checked read-only at `v0.3.90`: the absent-refusal set in the scenario summary, the stack-frame pattern in the
  health module (it returned false for all three real frames), the bare `selector` object in the tool specs, the
  `bridge_disabled` advice in discovery, and `FEATURES.md` listing the quit helpers as CLI host helpers only.
- After the fixes, a read-only check on one real editor log of 230,740 lines: the new frame filter dropped 84,654 more
  frame lines (77,413 async `MoveNext`), none without a frame shape; the redaction found 60 `token` values and, after
  `c6a0135`, no false positive (53 before, from `PublicKeyToken` and one type name).
- `v0.3.91` live checks in a generated project on Unity `6000.0.58f2` covered RG-60, RG-62, RG-63, RG-66, RG-71 and
  RG-72. RG-61 and RG-70 were checked against the real log above and by host tests.
- The `## 0.3.91` section of `CHANGELOG.md` is the record of what shipped.

## 8. Final verdict

Healthy core, weak UI reach. The MCP told the truth about Unity in every call, and the earlier fixes held in real
feature work. Two `v0.3.89` fixes needed a second pass and got it in `v0.3.91`, together with the editor quit tool and
the selector, redaction and recovery-advice fixes. What remains is the UI layer both ways: what it cannot reach
(duplicate paths, off-screen targets: RG-65, RG-68) and what it costs per step (RG-69), plus shared-checkout waiting
(RG-64) and the unconfirmed settings churn (RG-67).

## Related

- `2026-11-19_sdk_rollout_typed_lane_discoverability_chat_retro.md` is the other retro of the same release batch
  (RG-54..RG-59).
- `2026-10-07_playmode_business_flow_validation_chat_retro.md` records earlier custom-button click and runtime
  state gaps in the same kind of interactive Play Mode work.
