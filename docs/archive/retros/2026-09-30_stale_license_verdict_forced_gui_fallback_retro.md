# XUUnity Light Unity MCP Retro — Stale License Verdict Forced GUI Fallback Into Safe Mode

Date: `2026-09-30`
Status: `fixed in current source; unreleased`
Lane: `batch-compile --batch-fallback-mode auto` on a consumer project whose in-progress change had a compile error; host wrapper from current source, package `v0.3.80`, Unity `6000.0.58f2`

## Finding

| Finding | Severity | Attribution | Basis |
| --- | --- | --- | --- |
| F-1 A licensing probe that only ran out of time was recorded as `licensing_client_ipc_failure` with `batchmode_supported=false` | P1 lane selection | probe log classifier | The 30 s probe log ends at `[Licensing::Module] Licensing is not yet initialized.`. Its only IPC match is the routine `[Licensing::IpcConnector] Channel ... doesn't exist` line that every editor start writes before launching its own licensing client; the recovery check that discounts that line required exit code 0, which a timeout never has. Replaying the classifier over the 27 probe logs on the host: 15 timed-out logs carried this false verdict, the one log with a genuine connection-loss message still classifies as an IPC failure, and the 11 finished logs are unchanged. |
| F-2 The project-local verdict cache had no expiry, so the false negative was reused for 20 days across five projects | P1 lane selection | `build_license_capabilities` project cache | Only the host-wide cache had a 300 s TTL, and it was consulted after the project cache. A later proven probe on a sibling project with the same executable and version never reached the projects still holding the negative verdict. |
| F-3 The GUI fallback dropped the bridge's compile verdict | P2 evidence | `run_gui_fallback_operation` summary | The bridge answered `unity.compile.player_scripts` with `error` "Unity has compilation errors. Resolve them before running compile validation." The batch summary and terminal record reported `transport_outcome=gui_operation_failed`, `unity_outcome=unknown`, `top_actionable_error=""`. |

## Evidence

- Chain: stale negative verdict → `lane_fallback_reason=licensing_client_ipc_failure`
  → GUI editor opened on a project with a `CS0012` error → Unity showed its
  "Enter Safe Mode?" dialog (the wrapper never clicks dialogs) → once the
  dialog was dismissed the bridge refused the compile operation with the
  message above → the summary reported only `gui_operation_failed` → closeout
  `quit_ack_without_exit_sigterm_recovered`.
- The `v0.3.81` Safe Mode work changed the `ensure-ready` verdict after the
  editor leaves Safe Mode. It never aimed at dialog avoidance: only the batch
  lane avoids the dialog, and F-1 and F-2 had disabled the batch lane.

## Fix Applied

1. The classifier no longer matches the `[Licensing::IpcConnector]` logger
   prefix on its own. A timed-out probe without a licensing error line is
   `unknown_batch_failure` (`batchmode_supported=null`), so `auto` mode tries
   the batch lane, which is the real test.
2. A proven `batchmode_supported=true` verdict is reused until a later probe
   replaces it; an unproven or negative verdict expires after 24 hours. The
   newest probe for the same executable and version wins across projects, and
   a project adopts the host-wide verdict when it is newer than its own
   (`probe_skipped_reason=host_probe_cache`).
3. A GUI fallback whose bridge operation returns an error carries the error
   into the summary as `gui_operation_error_code` and `top_actionable_error`.

Live proof: `license-capabilities` on the affected project adopted the sibling
project's proven verdict from the previous day and recommended the batch lane
without launching Unity.

## Not Applied

- Launching the GUI fallback with `-ignoreCompilerErrors`. The switch string
  exists in the `6000.0.58f2` binary, but whether it suppresses the Safe Mode
  dialog for a GUI editor is unverified, and with compile errors present the
  compile operation refuses anyway. The dialog is Unity's correct signal; the
  fix is to stay on the batch lane.
- Refusing to open a GUI editor for a compile-only fallback when the project
  is "known" to have compile errors. The wrapper cannot know that before
  compiling; the bridge's refusal now reaches the summary instead.

## Residual

- A project with no verdict at all while another licensed editor is live still
  takes the GUI lane (`lane_fallback_reason=licensed_editor_live`), because
  probing is refused while editors are live. Once any project holds a proven
  verdict for that executable, sibling projects adopt it.
- The default probe timeout (30 s) is shorter than a cold project open, so a
  first probe on a large project is usually inconclusive. Recording a proven
  verdict after a successful batch-lane run would close that gap; not done here.
