# XUUnity Light Unity MCP Retro: Devmode, Process Visibility, And Closed-Editor Batch Discipline

Date: `2026-05-23`
Status: `public-safe intake review package`
Source prompt: `./CHAT_RETRO_PROMPT.md`

## Executive Summary

The Unity-side operations ultimately succeeded: the local package-source mode
was applied, Unity re-resolved the package, and the build-config compile matrix
passed all six target/profile combinations in batch mode.

The session exposed three operator-facing reliability gaps:

1. A host-local dispatcher passed the wrong source root into the public wrapper,
   so `devmode` initially looked for the local package source in the wrong
   directory.
2. Process-liveness checks were unreliable inside a restricted host sandbox.
   The wrapper repeatedly classified a healthy or recently-live editor as
   missing until the same command was rerun with full host process visibility.
3. `unity.editor.quit` acknowledgements were not enough for a closed-editor
   batch lane. The editor accepted two quit requests but stayed live, forcing a
   manual process termination before the batch matrix could start.

The core MCP validation surface behaved correctly once the lane preconditions
were true. The most useful public improvement is to make lifecycle preconditions
and closeout truth more explicit, especially for host clients with limited
process visibility.

## Evidence Base

Public-safe evidence categories:

- initial `devmode` failed before project mutation because the wrapper resolved
  the public source root incorrectly
- after source-root correction, `devmode` rewired the package dependency to a
  local file source and Unity regenerated the lock entry as a local dependency
- project refresh completed through the MCP bridge with package resolve
  requested, refresh settled, and no compile/update work remaining
- status summaries showed a healthy bridge, live editor, usable transport,
  no pending requests, and edit mode before closed-editor batch work
- two batch attempts were safely blocked by `editor_running_batch_conflict`
  while the same project editor was still live
- request journal entries showed two `unity.editor.quit` requests completed
  with `operation_status=ok`
- process-level discovery still reported the editor live after those quit
  acknowledgements
- the successful batch build-config compile matrix passed `6/6`
- compact result summary was about 1.3 KB while the raw batch log was about
  412 KB, so compact evidence was far cheaper than raw-log inspection
- batch side-effect scanning reported no new dirty files; the existing package
  manifest and lock changes were preexisting from devmode

Project names, absolute local paths, request ids, private branch names, and
product context are intentionally omitted.

## Timeline

1. The repo and project routers selected the MCP package-source mode workflow.
2. The first `devmode` call failed because the public wrapper looked under the
   wrong source root for the local package source.
3. The host-local dispatcher was corrected to pass the MCP operation directory
   as the explicit source root.
4. `devmode` succeeded and changed the package dependency from a published Git
   source to a local file dependency.
5. `ensure-ready --open-editor` launched the project-matched Unity editor and
   the bridge became healthy.
6. A project refresh run inside restricted process visibility misclassified the
   live editor as missing and produced an editor launch failure.
7. The same refresh run with full host process visibility completed and settled.
8. The user requested a closed-editor batch build-config compile matrix.
9. The current editor was healthy, so the operator sent `unity.editor.quit`.
10. The wrapper acknowledged quit, but closeout verification did not prove that
    the same-project editor was closed.
11. The batch lane correctly refused to start while the same editor pid was
    still live.
12. A second quit acknowledgement also did not terminate the editor.
13. The operator terminated the still-live editor process.
14. The closed-editor batch build-config compile matrix started and passed all
    six generated configurations.

## What Worked Well

- The batch preflight was safe. It refused to run while the same project editor
  was open, preventing competing editor/batch ownership.
- The build-config-aware batch lane resolved the expected profiles and targets
  without hand-authored define lists.
- The successful batch matrix produced compact, high-signal evidence:
  `6/6` passed, clean batch exit, no new dirty files, and direct result paths.
- Request journaling was enough to prove that quit requests were accepted by
  the bridge.
- The project refresh settle watcher gave meaningful proof that package resolve
  was requested and the editor was idle afterward.
- The host wrapper surfaced useful recovery hints for batch conflicts instead
  of starting Unity in an unsafe state.

## What Worked Poorly

- The initial source-root failure made `devmode` depend on subtle wrapper
  environment behavior instead of a clear package-source invariant.
- Process visibility restrictions caused false editor-liveness conclusions.
  The wrapper could say `editor_not_running` while the same editor was actually
  discoverable when run with full host visibility.
- The macOS app launch error looked like a missing executable even though the
  direct Unity executable existed and later batch execution used it
  successfully.
- `restore-editor-state` reported `closeout_verified=true` for a case where it
  had not opened the editor, even though post-close discovery still showed the
  same editor live. That is true for "nothing to restore" but misleading for a
  "closed-editor batch precondition" claim.
- The recovery command for `editor_running_batch_conflict` repeated
  `request-editor-quit`, but this session needed verified exit or an explicit
  escalation path after quit acknowledgement did not terminate the process.
- The operator had to inspect several command classes before reaching the
  simple truth: Unity compile was fine, but editor lifecycle closeout was not.

## What Was Not Explicit Enough

- `devmode` and `prodmode` are package-source switches, but the wrapper also
  needs to make the resolved public package source path obvious before mutation.
- Host process visibility is a first-class precondition for liveness-sensitive
  commands. A sandboxed host can make process discovery untrustworthy.
- `unity.editor.quit` success means "quit requested", not "process exited".
- `restore-editor-state` and "prove the editor is closed for batch" are related
  but not the same contract.
- Batch conflict recovery should distinguish:
  - graceful quit requested
  - process exit verified
  - quit acknowledged but process still live
  - explicit termination required
- A compact failure summary should recommend the next different action after
  repeated quit acknowledgements, not only repeat the same command.

## What The Operator Needed But Did Not Have

- A `verify-editor-closed` or `restore-editor-state --require-closed` command
  that fails when the same-project editor remains live, regardless of whether
  the host originally opened it.
- A `request-editor-quit --wait-for-exit` mode that reports both bridge
  acknowledgement and process-exit truth.
- A liveness diagnostic that says `process_visibility_restricted` instead of
  collapsing restricted `ps` or `pgrep` access into `editor_not_running`.
- A bounded escalation recommendation after quit acknowledgement without exit,
  for example "close manually or terminate pid" with clear safety wording.
- A launch diagnostic that distinguishes LaunchServices failure from the direct
  Unity executable being present and runnable.
- A source-root self-check in `devmode` that reports the resolved package source
  before attempting the manifest update.

## Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 8/10 | Package refresh and compile matrix succeeded once lifecycle preconditions were true. |
| Request journaling quality | 8/10 | Request completion was visible, but quit acknowledgement still needed process-exit pairing. |
| Bridge health observability | 8/10 | Status summaries were strong with full process visibility. |
| Wrapper-to-operator clarity | 6/10 | Batch conflicts were clear; source-root and sandbox-liveness failures were not. |
| Recovery guidance quality | 6/10 | First recovery step was concrete, but repeated quit acknowledgement needed a different next step. |
| Transport lifecycle transparency | 7/10 | Transport was visible; stale state versus process visibility remained confusing. |
| End-to-end trustworthiness during churn | 7/10 | Final evidence was trustworthy, but the path had avoidable false negatives. |
| Parallel request handling | 8/10 | Batch lane correctly protected same-project ownership. |
| Token efficiency of the default operator path | 6/10 | Compact success evidence was efficient; diagnosis required repeated polling and raw checks. |
| Time-to-diagnosis | 6/10 | The key facts emerged, but only after source-root, sandbox, and closeout detours. |
| Validation workflow discipline | 8/10 | The final lane choice was correct and the batch precondition was respected after correction. |

## Priority Improvements

1. Add a source-root/package-source preflight to `devmode` and `prodmode`.
   It should print the resolved source root and fail with a targeted message if
   the local package is not under that source root.
2. Add process-visibility classification to discovery. If host process listing
   is denied or incomplete, report `process_visibility_restricted` and avoid
   presenting `editor_not_running` as a strong fact.
3. Add a closed-editor verifier command or option. It should answer the batch
   precondition directly: "is any editor for this same project still live?"
4. Add `request-editor-quit --wait-for-exit` or an equivalent wrapper command
   that combines bridge acknowledgement with process-exit polling.
5. Make `restore-editor-state` avoid `closeout_verified=true` wording when the
   same-project editor is still live and the caller needs closed-editor proof.
6. Update batch conflict summaries to change recommendations after a repeated
   quit acknowledgement without exit.
7. Improve macOS launch diagnostics: if LaunchServices reports a missing app
   executable but `Contents/MacOS/Unity` exists, say so and recommend the
   wrapper-supported fallback or recovery path.
8. Prefer compact summaries first. Raw logs should remain a second-line
   artifact unless the summary lacks enough detail.

## Public-Promotion Recommendations

- Promote the distinction between "quit acknowledged" and "process exit
  verified" into public README, continuation docs, and batch-lane guidance.
- Promote "host process visibility is required for lifecycle truth" into the
  operator contract for sandboxed clients.
- Add a public recovery recipe for closed-editor batch lanes:
  1. request quit
  2. verify same-project editor closed
  3. if still live, perform explicit manual or bounded termination
  4. rerun batch
- Add source-root resolution checks to wrapper/runtime templates so host-local
  dispatchers cannot silently point package-source mode at the wrong folder.
- Add compact batch conflict fields for:
  - live editor pids
  - quit acknowledgement status
  - process-exit verification status
  - whether the next action is retry, wait, manual close, or terminate
- Keep project-specific package names, paths, and business context out of the
  public docs; the reusable lesson is lifecycle and operator ergonomics.

## Final Verdict

The MCP validation itself was sound. The successful final state proves the
local package dependency resolved and the build-config compile matrix passed
for the full Android/iOS profile set.

The reliability issue was operator lifecycle clarity around host wrappers:
source-root selection, sandboxed process visibility, and the difference between
quit acknowledgement and verified process exit. The public MCP surface should
make those distinctions explicit enough that the next operator does not need to
discover them by repeated polling, raw-log inspection, or manual process
triage.
