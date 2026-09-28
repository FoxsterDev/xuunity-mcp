# XUUnity Light Unity MCP Chat Retro — Readiness After Safe Mode, Settle After Mutating Hooks, Evidence Surfaces

Date: `2026-09-28`
Status: `intake; host-local hook report and labelled longer wait applied the same day; public items open`
Lane: `ensure-ready` GUI editor, `unity.project.refresh` → EditMode/PlayMode loop, build-config compile matrix, `request-scenario-run-and-wait` with project-defined hooks, per-project `batch-compile` sweep with GUI fallback
Server metadata observed in session: `xuunity-mcp 0.3.80`, Unity `6000.0.58f2`

## 1. Executive Summary

A monetization feature session in a Unity hub project that shares source with thirteen consumer
projects ran roughly 190 MCP requests over one hour. Unity executed all of them; the request journal
holds 184 completed requests, 20 bridge generations, 15 reclassifications and 4 abandonments, every one
with a reason, and no wrong test or compile result. What went wrong was the layer that tells the
operator whether something failed, and the layer that lets the operator prove what happened.

| Finding | Severity | Attribution | One-line basis |
| --- | --- | --- | --- |
| F-1 `ensure-ready --open-editor` returns `startup_safe_mode_dialog_observed` with a manual-only recovery while the editor has already left Safe Mode and the bridge is attached | P2 false negative | wrapper readiness verdict | The operator's own compile error blocked the first compile; the Editor.log carried `Exiting safe mode` within a minute, `unity_status_summary` reported `healthy` with `script_compilation_failed: true` ("a flag, not a verdict"), and a fix plus `unity.project.refresh` was the whole recovery. The two surfaces disagreed on severity. |
| F-2 a checked-in scenario runs `compile_player_scripts` 10 s after a define-changing project hook and fails with `editor_busy` (`isCompiling=True`) | P2 false negative | scenario ordering / step semantics | Reproduced twice. The hook had applied the profile and its scripting defines; the scenario reported `failed` although its purpose succeeded. The scenario validator rejects a `project_refresh` settle step after a profile mutation (`project_refresh_after_profile_mutation_forbidden`), so the only in-contract host-local mitigation was a longer, labelled blind wait; the durable fix is a settle-gated compile step in the runner. |
| F-3 the compact EditMode payload lists three failures of nine | P3 evidence gap | request summary surface | The other six were inferred from a shared assertion message and confirmed by re-running; an unrelated pre-existing red surfaced only on the second run. |
| F-4 `unity_console_grep since=playmode_start` searched the oldest 500k characters of a 2.1 MB play-session scope and returned `inconclusive` | P3 evidence gap | console lane | For play-session evidence the newest lines are the interesting ones; a shell grep on the log answered in one call. Scenario `console_grep` steps also have no session anchor, so a passing grep can be a previous session's line. |
| F-5 two of thirteen consumer compiles ended with `editor_idle_timeout` (heartbeat stale 180 s during `updating` / `asset_import`) while the hub editor ran PlayMode tests; both passed on plain re-run | P3 operator guidance | batch sweep + host load | The recommended `recover-editor-session` had nothing to recover because the wrapper had already quit those editors. The batch lane was unavailable (`licensing_client_ipc_failure`) so the GUI fallback lane ran everywhere; results came in two shapes (`result.status` on GUI, `compile.status` on batch). Extends the open batch-output-shape item. |
| F-6 nothing reports which scripting defines a mutating hook applied, and nothing reads a serialized asset field | P3 observability | hook output / capability gap | A configuration question (a QA override that "did not apply") took four hypothesis rounds, including reading compiler response files, before a duplicate YAML key in a hand-edited asset was found. Host-local fix applied: the hook now reports per-platform defines and whether they changed. |

Every PlayMode run also produced `playmode_state_after_settle_trust_class: stale_risk` plus a journaled
`request_abandoned` / `request_reclassified` pair, all explained by the normal domain reload on Play Mode
exit and all reconciled (`persisted_test_result_reconciliation: reconciled`). That is correct journaling
that reads like a warning.

## 2. Evidence Base

- Request journal: 929 events in the session window; 186 submitted, 184 completed, 181 delivery-observed; abandonments only on `unity.tests.run_playmode` (`domain_reload_before_request_completion`); delivery-unproven only on `unity.scenario.result` polling (`tcp_connection_closed_without_complete_response_frame`, `response_channel_reset_before_host_delivery`), each followed by a recovered result.
- Bridge state at closeout: healthy, generation 200, one editor process, transport listening.
- Scenario result files for the two `editor_busy` failures and three passing play smokes (90–93 s each).
- Per-project batch result and summary files for the thirteen-project sweep; wrapper stderr for the two idle timeouts.
- Raw sizes the operator handled: readiness failure payload 13 KB; scenario full payload 66 KB per run (needed for `console_grep` items); profile-apply output 16 KB; per-project sweep output about 4 KB; Editor.log 55 MB / 327k lines.

## 3. What Worked Well

- Stale bridge state written by a dead batch process was classified (`bridge_owned_by_non_main_process`) and the recommended `request-stale-cleanup` removed the two stale outbox artifacts in one call.
- `ensure-ready` launched the project-matched editor with forwarded licensing; after the compile fix the bridge was already attached.
- `unity.project.refresh` → EditMode/PlayMode: 14–16 s and 63–68 s runs, totals moved by exactly the number of added tests, `post_settle_compile` never contradicted reality.
- Build-config compile matrix: six profile/target pairs with measured rebuilt/cached counts in 47 s, no editor state mutation.
- Scenario runner with project-defined hooks expressed profile apply and a play smoke with screenshots and console evidence as JSON artifacts.
- Sweep auto-fallback to the GUI lane kept thirteen projects compiling when batch licensing was unavailable; `rebuilt_assembly_count` separated real compiles from cache hits.
- Mutation-red test discipline, compile-first ordering and churn reversal all fit the existing lanes without workarounds.

## 4. What Worked Poorly

- Two hard failure verdicts (F-1, F-2) for situations Unity had already resolved or would resolve with one refresh.
- Three evidence gaps (F-3, F-4, F-6) that pushed the operator to the raw log or to compiler response files.
- One recovery recommendation (F-5) that could not work after the wrapper's own quit.

## 5. Scoring (1 = poor, 10 = excellent)

| Category | Score | Basis |
| --- | --- | --- |
| Unity-side execution stability | 9 | 184/184 completed; no editor crash |
| Request journaling quality | 8 | every abandonment/reclassification carries a reason and request id |
| Bridge health observability | 7 | ownership and staleness precise; Safe Mode readiness lagged reality |
| Wrapper-to-operator clarity | 5 | two failure verdicts overstated failure; two result shapes on the sweep |
| Recovery guidance quality | 5 | cleanup guidance exact; Safe Mode and idle-timeout guidance pointed away from the working recovery |
| Transport lifecycle transparency | 7 | resets journaled and recovered; noise on every PlayMode run |
| End-to-end trustworthiness during churn | 8 | test totals and post-settle compile reliable through 20 generations |
| Parallel request handling | 6 | hub and consumer editors coexisted; host load produced two stale heartbeats |
| Token efficiency of the default operator path | 6 | test/compile payloads about 2 KB; scenario evidence needed 66 KB full payloads; console proof fell back to a 55 MB log |
| Time-to-diagnosis | 5 | three incidents needed 2–4 extra rounds |
| Validation workflow discipline | 9 | refresh-before-tests, matrix-before-smoke, mutation-red, churn reverted |

## 6. Priority Improvements (smallest reusable change first)

1. **Readiness re-probe after a Safe Mode observation** (`ensure-ready`): when the log shows `Exiting safe mode` or the bridge attaches with `script_compilation_failed`, return `ready_with_compile_errors` and recommend "fix compile errors, then `request-project-refresh`" instead of a manual Safe Mode step. Keep the no-dialog-clicking rule.
2. **Complete failure list in compact test payloads**: `failures[]` up to a bounded count plus `failure_count` and `test_result_path`, instead of `first_failures` capped at three.
3. **Settle-gated compile after mutating hooks** in the scenario runner: honour `mutationSettlePolicy: apply_then_gate` by waiting for compile idle (bounded) before dispatching `compile_player_scripts`, or mark `editor_busy` retryable with one automatic retry. The validator already forbids `project_refresh` after a profile mutation (it can lose domain-reload accounting), so scenario authors have no state-aware settle primitive for this case and fall back to a fixed wait, which the authoring doctrine itself calls a last resort.
4. **Tail-first anchored grep**: search newest-first inside an anchored scope, or auto-extend `maxSearchChars` to the scope size under a hard cap; accept `since: playmode_start` on scenario `console_grep` steps.
5. **Sweep terminal record**: one lane-independent last NDJSON line and summary record with `lane`, `compile.status`, `error_count`, `rebuilt_assembly_count`, licence blocker; `editor_idle_timeout` with a stale heartbeat during `asset_import` / `updating` gets `retry_recommended: true` and an opt-in single automatic retry; do not recommend session recovery after the wrapper itself quit the editor.
6. **Mutating hooks report the editor state they changed** (pattern for `mcp_scenario_authoring.md`): a profile/environment hook returns the resulting scripting defines per platform and a changed flag.
7. **Expected-reload labelling**: when `persisted_test_result_reconciliation == reconciled`, label the post-PlayMode reload `expected_domain_reload` instead of `stale_risk`.
8. **Read-only asset field snapshot** (capability): serialized fields of a ScriptableObject asset at a path, depth-limited, so configuration questions do not need Play Mode or YAML archaeology.

## 6a. Verification Of The Host-Local Changes

The hook report was verified through the two profile scenarios (apply: 7/7 in 79 s; restore: 8/8 in
90 s). The restore run reported `scripting_defines_changed: true` after an earlier `git checkout` of the
project settings file had been followed by a refresh that "passed": reverting `ProjectSettings` on disk
does not reload `PlayerSettings` in a running editor, so the editor kept compiling with the applied
profile's defines until the restore hook ran. Operator rule: revert an applied profile through the
restore hook, then use version control only for the leftover generated churn. A settle step of kind
`project_refresh` after the profile hook was rejected by the scenario validator
(`project_refresh_after_profile_mutation_forbidden`); the validator is right to protect domain-reload
accounting, which is why item 3 asks for the compile step itself to gate on idle.

## 7. Promotion Targets

- Items 1, 2, 3, 4, 5, 7: wrapper/runtime behaviour and operator docs (`README.md` operator guidance, `docs/operations/CONTINUATION.md`, `docs/operations/SMOKE_TESTS.md` ordering rule for define-changing hooks).
- Item 6: `AIRoot/Modules/XUUnity/knowledge/mcp_scenario_authoring.md` (hook output contract).
- Item 8: `docs/architecture/ROADMAP.md` capability proposal.
- Item 5 joins the existing open batch-output-shape slice tracked from the 2026-09-02 batch summary retro.

## 8. Final Verdict

Unity execution was sound for the whole session. The wrapper produced three misleading failure
verdicts and the operator path lacked four evidence surfaces; none changed the engineering outcome,
but together they cost about ten extra tool rounds and one 55 MB log grep. The fixes are output-shape
and ordering changes, each removing a false-negative conclusion the next operator would otherwise
repeat.
