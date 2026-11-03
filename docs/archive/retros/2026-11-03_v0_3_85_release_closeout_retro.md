# XUUnity Light Unity MCP Retro — v0.3.85 Release Closeout

Date: `2026-11-03`
Status: `open`
Lane: release closeout for `v0.3.85` (work `e661bc1`, release `9972e19`, test-only CI fix `ed61a7d`, tag `v0.3.85` at `ed61a7d`), consumer rollout through `scripts/testing/run_consumer_rollout.py`, remote host CI on Windows, Ubuntu and macOS
Server metadata observed in session: host and package from the release tree, Unity `6000.0.58f2` on macOS

## Status (2026-11-03, v0.3.85)

| Item | Status | What shipped | What remains / next step |
| --- | --- | --- | --- |
| R-1 rollout helper flags its own run dir as a workspace side effect | open | — | Exclude the helper's own run dir from workspace side-effect detection. Workaround: keep the run dir outside every consumer repository. |
| R-2 rollout helper global Unity process scan false positives | open | — | Match the Unity executable as the process image, not as a substring of any command line. |
| R-3 rollout helper does not track detached compiler servers | open | — | Record the `VBCSCompiler` servers left after batch compiles and report them in the ledger; decide whether cleanup is owned or report-only. |
| R-4 consumer import churn | open | — | One consumer project regenerates a UI effect settings asset on every batch import. Classify it as known churn instead of a side effect, or fix it in that project. |
| C-1 Windows CI caught a test-only failure after the release commit | open | Test fix `ed61a7d` before the tag. | Run the host suite under the Windows-like host flavor before tagging, or wait for remote CI on the release commit before the tag. |
| L-1 unproven lanes | open | — | A post-reset recovery wait over 300 s, Unity 2021.3, and Windows and Ubuntu editors are not live-proven. |

## Findings

| Finding | Severity | Attribution | Basis |
| --- | --- | --- | --- |
| R-1 The rollout helper reports its own run dir as a workspace side effect | P2 release tooling | `run_consumer_rollout.py` side-effect detection | When the run dir sits inside a consumer git workspace, the helper's own ledger and logs appear as new untracked files and the run is flagged. This recurred from `v0.3.84`. Keeping the run dir outside the consumer repositories avoids it. |
| R-2 The global Unity process scan reports processes that are not Unity | P2 release tooling | `run_consumer_rollout.py` global preflight | The scan matches any command line that contains the Unity binary path, so an operator shell wrapper that names that path is reported as a live Unity process and blocks the lane. |
| R-3 Detached `VBCSCompiler` servers are not tracked | P3 release tooling | `run_consumer_rollout.py` process ledger | Batch compiles leave detached compiler servers running after Unity exits. The ledger neither records nor reports them, so the cleanup state looks complete while those processes remain. |
| R-4 Deterministic import churn in one consumer project | P3 consumer hygiene | consumer project asset import | A UI effect settings asset is rewritten on every batch import. Any workspace diff check after a batch compile sees it. |
| C-1 A Windows-only test failure surfaced after the release commit | P3 release process | host test suite | Two `request-editor-quit` recovery-command tests computed the expected launcher prefix after the host-flavor patch had exited. On a Windows runner the expectation used the `.cmd` launcher while the command under test was rendered with the patched `.sh` launcher. The local macOS suite passed, remote CI on Windows failed, and `ed61a7d` fixed the tests before the tag. Product code was unchanged. |
| L-1 Lanes the release did not prove live | P3 coverage | release validation | The longest live test run took 250 s, so a post-reset recovery wait over 300 s is covered by host unit tests only. Unity 2021.3 was only compiled offline against 2021.3 assemblies. Windows and Ubuntu editors were not run. |

## Evidence

- The `## 0.3.85` section of `CHANGELOG.md` is the record of what shipped and
  of the lanes it did not verify live.
- R-1 to R-4 were observed while pinning the consumer projects to `v0.3.85`
  with the rollout helper.
- `ed61a7d` changes only `tests/test_server_protocol_and_parser.py`.

## Also fixed during the release

These were found and fixed in the same session and shipped in `v0.3.85`. They
are not open items.

- `game_view_configure` matched an aspect-ratio preset by size (`9x16` selected
  `16:9 Portrait`); it now selects only fixed-resolution sizes.
- The compact CLI envelope dropped the verdict when it ran over its budget; it
  now drops samples, then `test_environment`, then shortens failure text.

## Related

- `2026-08-29_consumer_release_rollout_safety_retro.md` introduced the rollout
  helper and its workspace side-effect detection.
- `2026-10-07_long_playmode_recovery_cap_and_dispatch_truth_chat_retro.md`
  holds the P0-2 status that L-1 qualifies.
