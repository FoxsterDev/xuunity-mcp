# XUUnity Light Unity MCP Retro — Editor Quit Acknowledged Without Exit

Date: `2026-09-30`
Status: `intake; backlog; no fix applied`
Lane: `ensure-ready --open-editor` GUI editor in a scaffolded consumer project, `request-playmode-tests`, `request-editor-quit`, `restore-editor-state`
Server metadata observed in session: `xuunity-mcp 0.3.81` host, package from current source, Unity `6000.0.58f2`

## Finding

| Finding | Severity | Attribution | Basis |
| --- | --- | --- | --- |
| F-1 `request-editor-quit` returns `status=ok`, `outcome=quit_requested` and exit code 0, but the editor keeps running | P3 operator guidance | editor quit lane | Seen twice in a row on the same host-opened editor after a PlayMode test run. Two minutes after the second request the process was alive, `unity_status_summary` reported `health_status=healthy`, `busy_reason=idle` and a heartbeat under 2 s, so no modal dialog was blocking the main loop. |

## Evidence

- `unity.editor.quit` answers `quit_requested` immediately and schedules
  `EditorApplication.Exit(0)` through `EditorApplication.delayCall`. The response
  therefore proves the request was accepted, not that the editor exited.
- The direct `request-editor-quit` command printed that acknowledgement and exited 0.
  It did not report `editor_quit_ack_without_exit`, the classification the verified
  closeout path already raises when the process survives.
- `restore-editor-state` closed the same editor with
  `closeout_classification=quit_ack_without_exit_sigterm_recovered` and
  `close_path=unity.editor.quit+host_sigterm`, `process_exit_verified=true`.

Why `EditorApplication.Exit(0)` did not take effect is an unverified hypothesis.
Candidates include a `delayCall` that never ran after the PlayMode test runner's
domain reload, or an `EditorApplication.wantsToQuit` subscriber that cancelled it.
Neither was checked in this session.

## Candidate Fixes

1. Make `request-editor-quit` verify process exit the same way the closeout path
   does. On survival, report `editor_quit_ack_without_exit` with the live pid and
   exit non-zero instead of printing a bare acknowledgement.
2. Record in the editor log when the scheduled `Exit` call actually runs, so the
   next occurrence shows whether `delayCall` fired.
3. Keep `restore-editor-state` as the documented closeout for host-opened
   editors in the smoke and continuation docs until (1) ships.
