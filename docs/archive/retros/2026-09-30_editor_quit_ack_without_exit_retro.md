# XUUnity Light Unity MCP Retro — Editor Quit Acknowledged Without Exit

Date: `2026-09-30`
Status: `resolved in Unreleased (after v0.3.84)`
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

## Resolution (2026-11-03)

Root cause: `EditorApplication.delayCall` does not run while the GUI editor is
in Edit Mode and is not the active app. Neither candidate above was the cause.

- Native evidence (Unity `6000.0.58f2` disassembly): `Application::TickTimer`
  runs the `EditorApplication.update` callbacks on every tick, but calls
  `Internal_CallDelayFunctions`, the only native caller of `delayCall`, only
  when the application is active, or is playing and not paused, or has a remote
  connection or debugger attached. The host opens editors with `open -g`, so
  they start unfocused.
- `EditorApplication.Exit` is `Terminate(force=true)`. It skips `wantsToQuit`
  and the save prompts, so a cancelling subscriber was ruled out. `Exit` was
  never reached: every quit's `request_started` shared one editor log offset,
  no shutdown lines followed, and the pump kept answering requests and
  heartbeats after the acknowledgement.
- Live proof on `v0.3.84`: an unfocused Edit Mode quit ended as
  `editor_quit_ack_without_exit` after 20 s; activating that pid made the
  editor exit within 1.18 s through `Internal_CallDelayFunctions` →
  `RequestQuit`. A quit sent while playing and unfocused exited in about 1-2 s.
- Journals show about 40 of 47 historical quits ended as ack without exit.
  The PlayMode run in F-1 only mattered because it left the editor in Edit Mode
  and unfocused.

Fix:

1. The package arms a one-shot quit intent in `SessionState` (120 s expiry)
   and the bridge's `EditorApplication.update` tick runs `Exit(0)` after the
   response and `request_completed` are written. The bootstrap re-arms it after
   a domain reload. The journal records `editor_quit_executing` (or
   `editor_quit_expired`) and the editor log gets
   `[XUUnityLightMcp] editor quit executing request_id=<id>` (candidate fix 2).
   The acknowledgement reports `quit_mechanism`, `editor_application_focused`,
   `is_playing` and `scene_dirty`.
2. `request-editor-quit` verifies process exit by default (candidate fix 1).
   On survival it exits non-zero with `editor_quit_ack_without_exit`, the
   editor pid, the live pids and `quit_executing_observed`. The recovery
   command is `restore-editor-state --require-closed` for a host-opened editor
   and a manual close plus `verify-editor-closed` otherwise. It does not signal
   the editor. `--no-wait-for-exit` keeps the ack-only result as
   `quit_ack_unverified`. A quit the bridge rejects fails at once as
   `quit_request_rejected` instead of waiting for an exit that was never armed.
3. Static checks keep `delayCall` out of the editor package; the editor
   main-thread skill records the rule.
