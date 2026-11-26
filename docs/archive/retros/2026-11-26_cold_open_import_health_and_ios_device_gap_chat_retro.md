# XUUnity Light Unity MCP Chat Retro — cold open of downloaded projects: quarantined plugins, invisible import failures, no iOS device lane

Date: `2026-11-26`
Status: `open (v0.3.91): RG-73..RG-80 open; RG-63 and RG-66 confirmed in practice`
Lane: one interactive operator chat. Three third-party Unity `2022.3.62f3` projects that arrived as downloaded archives were opened for the first time with `com.xuunity.light-mcp` `v0.3.91`, declared temporarily in each manifest and removed afterwards. The work ran on macOS with Xcode on a cabled iPhone. About 33 MCP calls.

Public twin of a host-private retro. Project, product and store names, device names, account ids and local paths are left out.

## Status (2026-11-26, v0.3.91)

| Item | Status | What remains / next step |
| --- | --- | --- |
| RG-73 quarantined native editor plugins | open | macOS preflight in `ensure_ready` and `status_summary` that reports `native_plugins_quarantined` with paths and an owner-run remediation. |
| RG-74 importer failures invisible to `ready`, compile and build results | open | Import-health digest; build validation fails closed on importer exceptions. |
| RG-75 no grep anchor covers the startup import | open | `since=editor_process_start`; `complete_single_session` for a fresh host-owned log. |
| RG-76 import lines match error patterns | open | Suppress `Start importing` lines by default. |
| RG-77 no iOS device lane | open | iOS support in the device tools through `devicectl`. |
| RG-78 `ready` while the editor is still updating | open | `waitForIdle`, or `ready_but_updating`. |
| RG-79 Play Mode platform not stated | open | Echo `active_build_target` and warn on a mismatch with the intended platform. |
| RG-80 no world-space input in Play Mode | open | `unity_input_pointer`. |

## 1. Executive summary

**No Unity-side failure and no transport loss in about 33 calls across three projects.** For each project, about 10 compact calls took it from a closed editor to a Play Mode screenshot to a verified quit:

1. `ensure_ready` → `scene_open` → `game_view_configure`;
2. `playmode_set` → screenshot → anchored `console_grep`;
3. `editor_quit`.

Every result was true.

Two `v0.3.91` fixes held in practice:
- **RG-66.** With the package declared but unresolved and no `Library/`, `status_summary` recommended ensure-ready, and one `unity_ensure_ready {openEditor:true}` resolved the git package, enabled the bridge, launched the editor and attached. This took 25–35 s, 3/3.
- **RG-63.** `unity_editor_quit` returned `quit_ack_and_process_exit_verified` 3/3, with no shell detour.

**The cost was what MCP could not see.**
- **What happened.** The archives were downloaded, so extraction carried the macOS quarantine flag onto editor-loaded native plugins:
  - a haptics package's editor-only dylib;
  - a physics package's native bundle.
- **The fallout.** On the first import Gatekeeper refused the dylib and showed a modal, and the user chose "Move to Trash". The package's scripted importer then threw `DllNotFoundException` for every haptic clip asset (141 clips, 282 log lines), so none became an asset.
- **Every surface stayed green:**
  - `ensure_ready` said `ready`;
  - `compiler_error_count` was 0;
  - a batch player build reported `Succeeded, errors=0`.
  - That build would have shipped without the feature. Only a manual grep of the raw batch log found it.

**Device validation for iOS fell outside MCP entirely.**
- The device tools are Android-only.
- Install, launch and console ran through `xcrun devicectl` in a shell.
- The visual proof (launch screen, a system permission prompt, a playable level) was the user's own confirmation.

## 2. Evidence base

- **The chat transcript**, with every MCP result inline.
- **Request journals in each project.** Their `scene.open`, `game_view.configure`, `playmode.set`, `game_view.screenshot` and `editor.quit` sequences match the transcript.
- **Host-owned editor logs**, one per project, and **batch build logs.** The first batch log shows `library load disallowed by system policy` for the plugin, then 282 importer exceptions, then `Succeeded errors=0`.
- **Device console captures.** One reached 921,428 lines, almost all a single repeated material warning with its stack.
- **The public tree at tag `v0.3.91` (`e5bd625`).** `git grep` finds no match for `quarantine`, `library load disallowed` or `devicectl` in Python or C#. `Start importing` appears only in an archived retro.

## 3. What worked well

- **One-call cold open** of a never-opened project, including resolving the git package and reporting license state and the log path.
- **`unity_editor_quit`.** Verified exit, with a `scene_dirty` check and no force-kill. Closing only the target editor was trivial.
- **Managed background Play Mode.** About 240 frames per 2 s with the editor unfocused.
- **`console_grep since=playmode_start`.** Complete anchored scope, a trustworthy `not_matched` verdict, and small payloads.
- **Fixed-resolution Game View screenshots returned by path.** The render-versus-screen mismatch was disclosed.
- **A removable footprint.** After the check, restoring the manifest and lock file left no diff apart from an editor layout file under `UserSettings/`.

## 4. What worked poorly

- **The import-health blind spot (RG-73, RG-74).** Native plugin load refusals and scripted-importer exceptions during the first import reach no MCP surface. `ready` means "the bridge is attached", not "the project imported cleanly", and nothing says so.
- **Grep scope on a freshly opened editor (RG-75).**
  - `since=bridge_generation` starts after the bridge attaches, which is after the startup import, so a search for the importer exception returned `not_matched` over the wrong window.
  - An unanchored search of a log created minutes earlier by the call that opened the editor came back `inconclusive / editor_log_spans_multiple_sessions`.
- **Import-line noise (RG-76).** `Start importing <path>` lines match any pattern that is also a file name: `ExceptionUtils.cs` and `UnityTestTimeoutException.cs` matched `Exception`. There were 9 and 65 noise hits in two projects, and `excludePattern` was needed each time. Build-pipeline chatter is already suppressed by default; import chatter is not.
- **`ready` while `busy_reason: updating`, `is_updating: true` (RG-78).** This invites an immediate grep or Play Mode while the import is still running. It was harmless here.

## 5. What was not explicit enough

- **The active build target (RG-79).** A fresh `Library/` opened on Standalone for a project built for iOS, and `game_view_configure` echoed `group: Standalone`. Nothing said that platform `#if` paths were not exercised by the Play Mode run.
- **`interactive_compile_block_detected` together with `resolved_by: bridge_attached` and 0 compiler errors (RG-78).** It cannot be read as either a real block or a transient compile modal.
- **The `status_summary` payload for a closed editor (about 5 KB).** About 25 `active_test_*` fields are empty or null when no editor runs.

## 6. What the operator needed but did not have

1. **A quarantine preflight** before the first open or batch import of a project that came from a downloaded archive (RG-73).
2. **An import-health summary after first open** (RG-74):
   - importer exceptions by importer and type;
   - native plugin load failures;
   - assets with no main object.
3. **A grep anchor that covers this editor process from launch** (RG-75).
4. **An iOS device lane like the Android one** (RG-77):
   - list, install, uninstall and launch with console capture;
   - a locked-device classification. CoreDevice error 4016 on install and `FBSOpenApplicationErrorDomain` error 7 with reason `Locked` on launch both mean "ask the user to unlock".
   - a screenshot when the host has the prerequisite, otherwise `screenshot_unavailable` naming it;
   - a console digest that collapses repeated lines.
5. **A Play Mode pointer primitive for world-space gameplay** (RG-80). `ui_click` is uGUI-only, so 3D tap-and-hold games could not be driven past their first screen in the editor.

## 7. Scoring (1–10)

| Category | Score | Note |
| --- | --- | --- |
| Unity-side execution stability | 10 | 3 projects, 0 failures |
| Request journaling quality | n/a | Sequences match the transcript; per-entry fields were not audited because no incident needed them |
| Bridge health observability | 7 | `ready` while updating; ambiguous compile-block observation |
| Wrapper-to-operator clarity | 8 | Compact verdicts on the main path |
| Recovery guidance quality | 8 | RG-66 effective; nothing for Gatekeeper |
| Transport lifecycle transparency | 9 | Generation, session and PID always present |
| End-to-end trustworthiness during churn | 7 | True results, but blind to import failures that changed the built player |
| Parallel request handling | n/a | Sequential use only |
| Token efficiency of the default path | 8 | Main cost ~5 KB `status_summary`, ~3–4 KB grep envelopes; screenshots by path |
| Time-to-diagnosis | 6 | The missing feature was found by hand in a ~30k-line batch log |
| Validation workflow discipline | 8 | Open → Play Mode → anchored grep → quit held; the iOS device step fell outside MCP |

## 8. Priority improvements

| ID | Priority | Change |
| --- | --- | --- |
| RG-73 | P1 safety | macOS-only preflight in `ensure_ready` (open and batch lanes) and `status_summary`. List the editor-loadable `.dylib`, `.bundle` and `.so` files under `Assets/` and `Packages/` that carry `com.apple.quarantine`. Return `native_plugins_quarantined` with paths and a remediation: recreate the files from version control, or the exact `xattr` command for the owner to run. Never strip the flag automatically. Warn that Gatekeeper's modal offers "Move to Trash", which deletes the plugin. |
| RG-74 | P1 trust | Import-health digest after the first import or refresh, read from the editor log. Report scripted-importer exceptions grouped by importer and exception type, native plugin load failures, and assets that produced no main object. Surface it in `ensure_ready` and as `status_summary.import_health` or a `unity_import_health` tool. Build and export validation fails closed on importer exceptions even when `BuildReport` counts 0 errors. |
| RG-75 | P2 scope | `console_grep`/`console_tail` `since=editor_process_start`, resolved from the launch offset of the current editor PID. When `editor_opened_by_this_call` and the log file is host-owned and new, classify an unanchored search as `complete_single_session`. |
| RG-76 | P2 noise | Suppress `Start importing …` and `-> (artifact id: …)` lines by default, as build-pipeline noise already is. `includeImportNoise: true` keeps them. |
| RG-77 | P2 missing lane | iOS in `unity_device_list/install/app/screen/logcat` through `xcrun devicectl`. Classify locked-device errors, return `screenshot_unavailable` with the missing prerequisite, and collapse repeated console lines. |
| RG-78 | P3 clarity | `ensure_ready` `waitForIdle` (default on) until `is_updating` and `is_compiling` are false, or `ready_but_updating`. Relabel a cleared startup compile modal with 0 errors as `transient_compile_modal_cleared`. |
| RG-79 | P3 clarity | Echo `active_build_target` and the project's intended platform in the `ensure_ready` and `playmode_set` results. Warn `playmode_platform_mismatch` when they differ. |
| RG-80 | P3 missing primitive | Play Mode `unity_input_pointer` (tap, hold or drag at normalized screen coordinates through the `EventSystem` and physics raycasters, or Input System device injection). |

## 9. Public-promotion recommendations

- **`docs/operations/SMOKE_TESTS.md` and the README "Recovery" section.** For a project that arrived as a downloaded archive, check for quarantined native plugins before the first open or batch import.
- **`docs/architecture/DESIGN.md`.** State that `ready` means the bridge is attached, not that the import is healthy, until RG-74 ships.
- **`docs/operations/CONTINUATION.md`.** Note that there is no iOS device lane yet, so agents don't search for one.

## 10. Final verdict

The core is good enough for a cold project: it goes from closed editor to Play Mode evidence to verified quit in about 10 compact calls, and every result was true.

What it cannot yet see:
- **startup import health, which is the priority.** A Gatekeeper prompt plus an importer exception produced a "successful" build without a gameplay feature while `ready` and `errors=0` stayed green. RG-73 and RG-74 turn that silent regression into a refused open.
- **macOS Gatekeeper;**
- **iOS devices.**
