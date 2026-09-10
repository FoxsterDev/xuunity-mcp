# Editor licensing diagnostics

The host normalizes OS pipe names to the editor channel format before adding
`-licensingIpc`. Explicit arguments accept either format. Discovery fingerprints
retain the raw pipe identity; the forwarded channel has a separate fingerprint.
Public payloads and smoke output contain no raw channel names.

`unity_status_summary`, `ensure-ready`, and launch results expose `license_state`
(`licensed`, `unlicensed`, or `unknown`), `licensing_channel_fingerprint`, and
`license_probe_active`. A newly spawned editor starts with unknown licensing.
Entitlement success proves licensing; connecting a socket alone does not.
A later licensing-client connection loss changes the state to unlicensed until
new entitlement evidence confirms recovery.
Package refusal remains unlicensed even if entitlement later recovers: reopen
the editor to restore its package set. External launches with licensing failures
recommend reopening through `open-editor --unity-arg=<argument>`.

Batch license probes use a per-user OS file lock across projects, threads, and
helper processes. The lock releases on process exit. A five-minute shared cache
is keyed by executable and Unity version; waiting callers recheck it before
launching Unity. `--refresh` bypasses an older cached probe, but reuses a probe
completed while that caller was waiting. GUI launches refuse immediately with
`licensing_busy` during a probe. A live editor with entitlement, a verified Hub session, and a connection
to a live licensing client skips the probe with
`probe_skipped_reason: licensed_editor_live`; this proves the GUI lane, not batch
entitlement. A live editor without that evidence, or unavailable process
visibility, prevents a new probe.

Build summaries retain `total_errors` and add `build_errors` and `startup_errors`.
The latter counts the known licensing validation/access-token lines followed by
successful entitlement resolution in the build log, capped at the original
error count. Missing logs and unrecovered lines remain build errors. This is
host log classification, not a change to Unity's BuildReport.

## Mechanism smoke

Use the source runtime when validating an uninstalled change. After closing the
validation project's editor, run the following helper subcommands:

```text
open-editor --project-root <project> --unity-arg=-buildTarget --unity-arg=Android
ensure-ready --project-root <project>
```

Then run `python3 scripts/testing/check_licensing_launch_smoke.py --project-root
<project>`. It requires a live wrapper-owned editor, licensed entitlement, and an
Editor.log connection to the exact fingerprint of the forwarded channel. A
missing-channel line fails the smoke even if a fallback bridge becomes healthy.

Bridge-disabled recovery uses the helper's `setup-plan --project-root <project>`
subcommand. Save its JSON output to a plan file, review it, then run
`setup-apply --plan-file <plan> --project-root <project> --yes`.
