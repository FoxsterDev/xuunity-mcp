# XUUnity Light Unity MCP Chat Retro — Play Mode validation of reward, loyalty and analytics flows across two consumer projects

Date: `2026-10-07`
Status: `intake; improvements proposed, none implemented`
Lane: `interactive_mcp` (GUI editors opened by the host), package `v0.3.83`, Unity `6000.0.58f2`, two consumer projects, one operator session spanning ~6 hours and a context compaction

## 1. Executive summary

Unity never failed. Every Play Mode run, compile and scene operation completed on the Unity side; 188 MCP tool calls, 379 journaled requests across the two projects, one `request_delivery_unproven` (a `scenario.result` poll whose response channel reset during a domain reload) and 20 `request_reclassified` entries, all with reason `bridge_generation_changed_during_post_request_settle` after `project.refresh`. Both are correctly labeled and cost nothing.

What was expensive was *proving product behavior* rather than running Unity: the operator had to write a temporary editor hook in each project (asmdef + ~130 lines) three times, because the public surface had no way to (a) deliver a click that a project's custom button accepts, (b) observe which `GameObserver` events fired in which order, (c) read a value from a static game-state class. The hook pattern worked and the scenario compact summaries made the evidence cheap once it existed, so the retro promotes the pattern instead of the workaround.

Five concrete friction points are worth fixing in the public surface; none is a reliability bug.

## 2. Evidence base

- Request journals: 1399 (project A) and 1159 (project B) files; operation mix led by `unity.scenario.result` (251 polls), `unity.scenario.run` (27), `unity.ui.click` (19), `unity.project.refresh` (16), `unity.playmode.set` (15), `unity.compile.player_scripts` (9), `unity.console.grep` (5).
- Bridge state: both editors healthy at the end, generations 48 and 44, `application_run_in_background=false` (project-owned).
- Scenario results: 31 files, 20–39 KB each in compact mode.
- Editor logs: 3.0 MB and 4.0 MB; `[GameObserver]` `Debug.Log` lines: 0 in both (the projects' logger profile drops them), while `[LogAttributes]` block lines: 389 of 14 555 lines in one log.
- Two `scenario_invalid` round trips for one `project_defined_hook_poll_until` step (`missing_start_payload`, then `invalid_fail_when`).
- Both editors were closed by the operator mid-session; `unity_status_summary` reported `stale_state` with `recommended_recovery_command`, and `recover-editor-session` reopened each editor in ~6 s with a warm `Library`.

## 3. Timeline (condensed)

1. Baseline runs through `playmode_set` + `project_defined_hook_poll_until` + `ui_exists` + `game_view_screenshot`; evidence read from `project_defined_hook_summary.payload_flags/payload_scalars`.
2. Needed to prove an event sequence (`LevelCompleted` vs `LevelUnCompleted`). `console_grep source=console since=playmode_start` returned 0 with `console_buffer_recreated_after_anchor`; `source=editor_log` matched 28 lines, 26 of them stack-frame continuations of logger calls. Switched to shell `sed`/`grep` on the editor log with manual line offsets, then added an in-hook event recorder.
3. Red run with the fix reverted by patch, green run with the fix reapplied, both via the hook recorder; one `scenario_invalid` pair on the first poll_until step.
4. Operator closed both editors between tasks; `recover-editor-session` restored each; consent EditorPrefs toggled around the run by shell.
5. Second project: same hook pattern rewritten from scratch (the first one had been deleted at closeout, as required).
6. Product-level evidence needed that no tool exposes: the ad-trigger ladder the server serves to the project (only visible as a truncated `bodyPreview` in the log) and the MAX editor-mock button paths (found from operator memory, not from any listing).

## 4. What worked well

- `unity_scenario_run_and_wait` compact decision envelope: `project_defined_hook_summary` with `payload_flags`/`payload_scalars` carried every assertion; no raw step payloads were needed.
- `project_defined_hook_poll_until` with a hook that returns state made "wait for lobby / wait for level N" deterministic.
- Stale-editor diagnosis: `unity_status_summary` said exactly what happened (`editor_pid_not_alive`) and named the recovery command; recovery was fast.
- Reclassification after domain reload is honest and harmless; nothing was double-run.
- `compile_player_scripts` for two targets after every batch: 2–7 s each, measured rebuild evidence.
- `game_view_configure` with an existing preset and group: one call, no custom size.

## 5. What worked poorly

- **Event-order evidence has no public path.** The projects' `GameObserver` seam logs through `Debug.Log` that the logger profile suppresses; the in-memory console buffer is recreated on Play; the editor log is stack-frame heavy. Every "which events fired, in which order" question required a temp hook that subscribes to the events.
- **`console_grep` on the editor log is noise-dominated for logger-based projects.** 26 of 28 matches were `Type:Method (at path:line)` continuation lines. There is no "message lines only" option.
- **`ui_click` cannot drive the projects' custom buttons.** Occlusion checks fail when the Game view panel size differs from the render size, and the projects' button class only accepts a click whose `pointerCurrentRaycast.gameObject` is the button. The hook had to build the `PointerEventData` itself.
- **`poll_until` schema errors are reported one at a time** (`startPayload` missing, then `failWhen` missing). `failWhen` is mandatory even when no fail predicate exists, so the operator writes `payload.x == 'never'`.
- **Runtime state read-back needs a hook.** `Application.runInBackground`, static game-state flags, `PlayerPrefs`-backed progress: all read or set through the hook.

## 6. What was not explicit enough

- `SMOKE_TESTS.md` documents `continueWhen` semantics but not that `startPayload` and `failWhen` are mandatory, nor a sentinel idiom for "no fail predicate".
- The capabilities payload does not say that `console_grep source=console` is empty after Play entry by design on projects with clear-on-play, so the first call is always wasted.
- `playmode_state_after_settle_trust_class: stale_risk` after every `project_refresh` reads like a warning but is routine.
- Nothing states that the host-opened editor log excludes `Debug.Log` when a project's logger profile filters it; the operator discovered it by `grep -c` returning 0.

## 7. What the operator needed but did not have

1. A built-in "record these static events from this type while the scenario runs" step, so event-order claims need no project hook.
2. A `ui_click` mode that delivers `pointerClick` with the raycast fields populated for the resolved target and skips the Screen-vs-render occlusion check when `render_target_differs_from_screen=true`.
3. `console_grep` option `messagesOnly=true` (drop lines matching the stack-frame shape) and a hint in the result when >50 % of matches are frame lines.
4. A stock runtime hook shipped by the package (`xuunity.runtime.state`) covering `run_in_background` set, `Application.isPlaying`, active scene name, and a safe `PlayerPrefs` get/set, so the first three temp-hook cases disappear.
5. One validation pass that lists every schema error of a step.

## 8. Scoring

| Category | Score | Note |
|---|---|---|
| Unity-side execution stability | 10/10 | No Unity failure in the session |
| Request journaling quality | 9/10 | Reclassification and delivery-unproven correctly labeled |
| Bridge health observability | 9/10 | Stale editor diagnosed with the recovery command |
| Wrapper-to-operator clarity | 7/10 | `stale_risk` note and one-error-at-a-time validation cost round trips |
| Recovery guidance quality | 9/10 | `recover-editor-session` worked first time, twice |
| Transport lifecycle transparency | 8/10 | Domain-reload generation changes visible and harmless |
| End-to-end trustworthiness during churn | 8/10 | One unproven poll, no false negative conclusion |
| Parallel request handling | n/a | Sequential session |
| Token efficiency of the default operator path | 6/10 | Compact scenario results still 20–39 KB; 12 liveness fields per step; recovery JSON 29 KB; first full-payload run ~25 KB |
| Time-to-diagnosis | 6/10 | Event-order and click evidence each cost a hook rewrite |
| Validation workflow discipline | 9/10 | Compile-after-edit, red-then-green, hook deleted at closeout |

## 9. Priority improvements

| # | Improvement | Surface | Size |
|---|---|---|---|
| P1 | `ui_click` raycast-filled delivery mode + occlusion bypass when render differs from screen | package `ui_click` | medium |
| P1 | Stock runtime hook (`run_in_background`, scene, isPlaying, PlayerPrefs get/set) | package editor hook | small |
| P2 | `console_grep messagesOnly` + frame-line ratio hint | server + package | small |
| P2 | `poll_until`: report all schema errors at once; make `failWhen` optional | server validation | small |
| P2 | Scenario compact mode: `stepsDetail: minimal` that drops per-step liveness unless throttled | server | small |
| P3 | Event recorder step: subscribe to named static events of a type for the scenario's lifetime, return the ordered list | package | medium |
| P3 | `recover-editor-session` compact output (`recovery_classification`, pid, duration) by default | wrapper | small |

## 10. Public-promotion recommendations

- `SMOKE_TESTS.md`: add the `poll_until` required-field table and the sentinel `failWhen` idiom until it becomes optional; add "console grep after Play entry: use `source=editor_log`; expect frame-line noise on logger-based projects".
- `CONTINUATION.md`: add the temp-hook pattern as the sanctioned fallback (asmdef refs: game asmdef, observer asmdef, `UnityEngine.UI`, `com.xuunity.light-mcp.Editor`; delete at closeout; record events via subscriptions, not logs), with a note that the stock runtime hook (P1) removes most of its uses.
- `DESIGN.md`/`ROADMAP.md`: the event-recorder step and the click delivery mode.
- Host-private: served ad-config capture and vendor mock button paths stay in host memory.

## 11. Final verdict

PASS for reliability; the lane was trustworthy end to end, and no conclusion was drawn from a false negative. The cost sits in evidence authoring: three hand-written hooks for things the package could ship. The two P1 items would have removed roughly half of the session's MCP-related operator time.
