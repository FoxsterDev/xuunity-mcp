# Compile Progress Bar Not Cleared on Unity 2022.3 — Operator-Trust Retro

Date: `2026-06-24`
Status: `active public retro`
Scope: MCP-triggered compile/refresh leaves Unity's global progress bar ("Hold on… / Importing assets / Compiling…") painted on Unity 2022.3, creating a false "hung / did-not-complete" impression even though Unity-side execution and results were correct.

## 1. Executive Summary

During a routine session (bump the in-editor bridge package to a new version, then compile-validate two Unity 2022.3.62f3 consumer projects), every MCP compile and refresh **completed correctly** — accurate error/warning counts, clean bridge health, fresh heartbeats, journaled requests. But the operator repeatedly saw Unity's modal progress bar stay on screen after the operation returned, and reasonably concluded "xuunity compilation hangs in Unity 2022," while noting the project's own native compile-check tool "works ok."

Root cause is narrow and confirmed in source: the MCP bridge runs `PlayerBuildInterface.CompilePlayerScripts` (and `AssetDatabase.Refresh`, `BuildPipeline.BuildPlayer`) from an `EditorApplication.update` pump tick but **never calls `EditorUtility.ClearProgressBar()` anywhere in the package**. On Unity 2022.3 those synchronous APIs paint Unity's internal progress bar but do not reliably auto-clear it when driven from plugin update code; Unity 6 hardened this, which is why the leak is 2022.3-specific. The native tool that "works ok" differs in exactly one way: it clears the bar explicitly after compiling.

Net: this was **not** a Unity execution failure and **not** a wrapper/transport failure — it was a missing cosmetic teardown plus missing operator guidance, which together manufactured a false-negative trust outcome. The fix is a one-line `ClearProgressBar()` in a `finally`, plus a small operator-clarity note.

## 2. Evidence Base

Bridge package (the MCP itself) — canonical source:
- `packages/com.xuunity.light-mcp/Editor/Helpers/XUUnityLightMcpCompileUtility.cs` — `PlayerBuildInterface.CompilePlayerScripts(...)` at `:106`; `try/finally` at `:109-113` that only unsubscribes an event + stops a stopwatch (no `ClearProgressBar`); early-exit guard at `:24-35` (`isCompiling || isUpdating || isPlayingOrWillChangePlaymode || scriptCompilationFailed`).
- `Editor/Operations/XUUnityLightMcpCompilePlayerScriptsOperation.cs:20-46` — operation wrapper, no clear.
- `Editor/Operations/XUUnityLightMcpProjectRefreshOperation.cs:26-33` — `AssetDatabase.Refresh()`, no clear.
- `Editor/Operations/XUUnityLightMcpBuildPlayerOperation.cs:188` (finally `:190-196`) — `BuildPipeline.BuildPlayer`, no clear.
- `Editor/Bridge/XUUnityLightMcpBridgeBootstrap.cs:45-69` — work is pumped from `EditorApplication.update` (`:65`).
- `Editor/Bridge/XUUnityLightMcpBridgeRequestPump.cs:67-169` — `ProcessDecodedRequest` finally `:132-168` writes heartbeat/journal, no clear.
- `Editor/Bridge/XUUnityLightMcpBridgeRuntimeState.cs` — settle tracking is bookkeeping only; flips phase strings, never touches the bar.
- Repo-wide: **zero** `ClearProgressBar` / `DisplayProgressBar` / `DisplayCancelableProgressBar` in the canonical package and in the installed cache `com.xuunity.light-mcp@ff36059d9f`.

Native contrast tool (the one that "works ok"):
- `Editor/ProjectCompilationCheck/EditorModeRunner.cs:137` — same `PlayerBuildInterface.CompilePlayerScripts`; `:57` — `EditorUtility.ClearProgressBar()` as the first statement of post-compile handling (reached from both the menu path `MenuItems.cs:23` and batch path `BatchModeRunner.cs:41/45`).

Result-correctness evidence (Unity executed fine):
- MCP compile matrix on the package-source project: 4/4 configs passed, 0 errors; a single real warning (`CS0618`) surfaced accurately, then 0 after fix.
- MCP StandaloneOSX compile correctly reported a real latent error (3 diagnostics in `GameLoggerEntryPoint.cs`) before fix, 0 after.
- Native batchmode `RunAll` (`CompilationOutput.json`) independently confirmed the fix: `GameLoggerEntryPoint` = 0 occurrences, `RuntimeInitialize` = 0; remaining `ErrorsCount=1` configs are the intentional `ErrorWhenDevelopmentBuild` sample (`Debug.Log2` CS0117 under `DEVELOPMENT_BUILD`) and uninstalled WebGL/Windows build targets.
- Bridge state during operations: `health_status: healthy`, fresh heartbeats, `script_compilation_failed:false`, `compiler_error_count:0` after fix; transport `tcp_loopback` listening; request journal entries present per `request_id`.
- Process evidence: the background native batchmode run **completed** (it did not hang); no orphaned 2022.3 Unity process remained.

## 3. Timeline

1. Bump in-editor bridge package pin to the current version across two consumer projects (file edits only).
2. `ensure-ready --open-editor --background-open --startup-policy fail_fast_on_interactive_compile_block` brought each editor online; package re-resolved cleanly; bridge healthy.
3. MCP compile / compile-matrix / project-refresh ran; **results were correct** every time.
4. Operator observed the modal progress bar persisting after operations and reported "compilation hangs in Unity 2022"; contrasted with the native compile-check tool that clears its bar.
5. Closed the idle editor and ran the **native** batchmode `RunAll`; it completed and independently confirmed the code fix.
6. Source investigation isolated the missing `ClearProgressBar` in the bridge as the sole cause of the persistent bar.

## 4. What Worked Well

- `ensure-ready` background launch + fail-fast startup policy: editors came up healthy and the package re-resolved without manual steps.
- Compile/matrix **result fidelity**: error and warning detection was accurate and matched an independent native run.
- Independent cross-check path existed (native batchmode `RunAll`) and agreed with MCP results — strong trust anchor.
- Bridge observability: `bridge_state.json` health/heartbeat/transport fields were rich enough to prove Unity was alive and idle.
- Surgical bridge enable (writing only `Library/XUUnityLightMcp/config/bridge_config.json`) avoided heavier installer side effects.

## 5. What Worked Poorly

- **Orphaned progress bar** after compile/refresh on 2022.3 → false "hung/failed" impression despite correct execution. Single biggest trust failure of the session.
- **Token churn**: default `unity_status_summary` and compile responses are multi-KB JSON; several were spent just to read a handful of fields (health, busy_reason, error_count).
- **Out-of-band compile vs. editor console**: `compile_player_scripts`/`compile_matrix` write to isolated output dirs and do **not** refresh the editor's main Console; a stale pre-fix warning kept displaying until a full domain reload, compounding the "did it actually apply?" doubt.
- Two concurrent editors were launched across the session (one per project); fine technically but extra resource load and another surface for a stuck bar.

## 6. What Was Not Explicit Enough

- Nothing in the compile/refresh result envelope states that **results are authoritative even if a Unity progress bar is still painted**, nor that the bar is cosmetic on 2022.3.
- No recovery hint ("a residual progress bar is a known 2022.3 cosmetic leak; it does not indicate an incomplete operation; it clears on the next editor interaction / domain reload").
- No signal that an out-of-band compile does not clear the editor Console, so the Console may show stale diagnostics until a refresh/domain reload.

## 7. What The Operator Needed But Did Not Have

- A **guaranteed progress-bar teardown** after every bridge compile/refresh/build (the actual fix).
- A **compact result envelope** (pass/fail, counts, busy_reason, health) to avoid paying for large JSON on routine status/compile polling.
- An explicit "results authoritative regardless of on-screen bar" statement in the compile/refresh response.
- A first-class way to drive the **native compile-check** through the MCP (no `project_actions.yaml` catalog existed, so the trusted tool could only be run via batchmode after closing the editor).

## 8. Scoring (1–5, 5 = best)

| Category | Score | Note |
| --- | --- | --- |
| Unity-side execution stability | 5 | Compiles/refreshes executed correctly; no crash. |
| Request journaling quality | 4 | Per-`request_id` journal entries present and usable. |
| Bridge health observability | 4 | `bridge_state.json` health/heartbeat/transport rich. |
| Wrapper-to-operator clarity | 2 | Stuck bar implied failure; no "results authoritative" signal. |
| Recovery guidance quality | 2 | No guidance that the bar is cosmetic or how to clear it. |
| Transport lifecycle transparency | 4 | Transport/session/generation well reported. |
| End-to-end trustworthiness during churn | 3 | Results correct, but cosmetic bar eroded trust. |
| Parallel request handling | 4 | Sequential pump handled load without churn errors. |
| Token efficiency of default operator path | 2 | Multi-KB status/compile responses dominated cost. |
| Time-to-diagnosis | 3 | Required reading bridge source to isolate the missing clear. |
| Validation workflow discipline | 4 | Compile-first, cross-target matrix, native cross-check. |

## 9. Priority Improvements

- **P0 — Always clear Unity's progress bar at bridge boundaries.** Add `EditorUtility.ClearProgressBar()` in a `finally`:
  - primary: `XUUnityLightMcpCompileUtility.Compile` finally (`XUUnityLightMcpCompileUtility.cs:109-113`) — covers operation, matrix, scenario, and batch CLI callers;
  - defense-in-depth: `XUUnityLightMcpProjectRefreshOperation.cs:26-33` (around `AssetDatabase.Refresh`) and `XUUnityLightMcpBuildPlayerOperation.cs:188` (extend finally `:190-196`);
  - belt-and-suspenders: one `ClearProgressBar()` in `XUUnityLightMcpBridgeRequestPump.ProcessDecodedRequest` finally (`:132`) so no operation — including the early-return/exception guard at `XUUnityLightMcpCompileUtility.cs:24-35` — can ever leave a bar painted. Do **not** introduce a new bar; only clear Unity's residual one.
- **P1 — Compact result envelope.** Add an opt-in compact mode (or default summary block) to compile/matrix/status returning `{status, error_count, warning_count, busy_reason, health_status, request_id}` so routine polling does not pay multi-KB JSON.
- **P1 — Authoritative-result statement.** In compile/refresh responses, include a short note: results are authoritative regardless of any on-screen Unity progress bar; on 2022.3 a residual bar is cosmetic and clears on next interaction.
- **P2 — Out-of-band compile / Console caveat.** Document and/or surface that `compile_player_scripts`/`compile_matrix` do not refresh the editor Console; recommend a domain reload (or `unity_project_refresh`) when Console parity matters.
- **P2 — Native compile-check as a project action.** Provide a `project_actions.yaml` entry to invoke `BatchModeRunner.Run` / `ProjectCompiler.RunAll` through the MCP so the trusted compile-check is reachable without closing the editor for batchmode.

## 10. Public-Promotion Recommendations

- **Wrapper/runtime template fix** (`templates/` + `packages/com.xuunity.light-mcp/Editor/...`): the P0 `ClearProgressBar` change; ship in the next package/server version and re-pin consumers.
- **`docs/architecture/DESIGN.md`**: document the progress-bar lifecycle rule — any synchronous editor op driven from the `EditorApplication.update` pump must clear Unity's progress bar in a `finally`; note the 2022.3-vs-6 auto-clear behavior delta.
- **`docs/operations/SMOKE_TESTS.md`**: add an acceptance check asserting no orphaned progress bar after compile/refresh/build (e.g., assert `EditorUtility`/progress state is clear post-op, or a documented manual check on 2022.3).
- **`docs/operations/CONTINUATION.md` / `README.md`**: operator note that a residual 2022.3 progress bar is cosmetic and results are authoritative; out-of-band compile does not clear the Console.
- **Response surfaces**: the compact envelope and authoritative-result note (P1).

## 11. Final Verdict

Unity-side execution and result fidelity were correct throughout; the bridge and transport were healthy. The session's only real defect was a **cosmetic, 2022.3-specific progress-bar leak** caused by the bridge never calling `EditorUtility.ClearProgressBar()`, amplified by the absence of an operator-facing "results are authoritative" signal and by token-heavy default responses. All are small, high-leverage fixes; the P0 one-liner removes the trust-destroying symptom outright.

## Apply Package (concrete, smallest-first)

1. `XUUnityLightMcpCompileUtility.cs` — extend finally at `:109-113` with `EditorUtility.ClearProgressBar();`.
2. `XUUnityLightMcpBridgeRequestPump.cs` — add `EditorUtility.ClearProgressBar();` to the `ProcessDecodedRequest` finally (`:132`).
3. `XUUnityLightMcpProjectRefreshOperation.cs` / `XUUnityLightMcpBuildPlayerOperation.cs` — clear in finally around `Refresh`/`BuildPlayer`.
4. Add compact result envelope (opt-in) to compile/matrix/status.
5. Add authoritative-result + cosmetic-bar note to compile/refresh responses and docs.
6. Add SMOKE acceptance check: no orphaned progress bar after compile/refresh/build.
