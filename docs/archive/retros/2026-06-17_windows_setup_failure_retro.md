# Windows Setup Failure Retro

Date: `2026-06-17`
Status: `minimal fix set implemented 2026-06-18; broader work deferred`

## Scope

This retro covers the native Windows Codex Desktop setup incident where
XUUnity MCP setup took about 37 minutes, failed repeatedly, then succeeded only
after switching command routes and manually recovering Unity state.

macOS daily usage was healthy at the time of the report, so this retro is
Windows-host focused.

## Related Windows History

These older retros are retained as historical evidence, not competing current
plans:

- `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v1.md`
- `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v2.md`
- `2026-06-10_windows_process_kill_catastrophe_retro.md`

The 2026-06-09 reports already pointed at close/reopen as the practical
Windows unblock when a project is declared but not bridge-ready. The
2026-06-10 process-kill retro explains why the 2026-06-18 fix set deliberately
avoids broad Windows process termination and defers user-opened-editor force
recovery to a separate safety design.

## Incident Summary

The install did not fail for one reason. It hit a chain of Windows-specific
setup and readiness problems:

1. `setup-plan` through a Git Bash route saw the Unity project path truncated
   to a prefix ending at `...\Documents\Unity`, then failed with
   `project_not_found`.
2. The PowerShell `.ps1` wrapper was blocked by ExecutionPolicy.
3. The `.cmd` wrapper succeeded.
4. `validate-setup` reported offline setup ready after manifest/config changes.
5. `ensure-ready --open-editor` waited for a bridge heartbeat from a live
   editor that had not imported the package yet.
6. Recovery advice pointed toward editor-session recovery, but the editor was
   user-opened and bridgeless, so manual close/reopen was the practical fix.

The long wall time came from serial agent retries plus Unity package
resolve/import latency plus multi-minute readiness waits. It was not a single
tool-internal infinite loop.

## Confirmed Or High-Confidence Causes

- `.cmd` was the reliable native Windows route in this incident.
- The shell path truncation happened before Python could validate a Unity
  project root. The Python setup path does not split project-root strings.
- The exact shell boundary that dropped the tail was not proven without a live
  Windows repro.
- The automatic Codex config installer still wrote a Unix `bash` launcher on
  Windows even though Windows docs/templates used `cmd.exe`.
- `validate-setup=ready` was offline readiness, not proof that Unity resolved
  the package or started the bridge.
- A package declared in `manifest.json` but absent from
  `packages-lock.json`/`Library/PackageCache` cannot emit the bridge heartbeat
  yet.
- Recovery advice was too generic for the declared-but-not-imported package
  state.
- A stale host session or stale bridge state can make editor closeout look
  active after Unity is already closed.

## Corrected Non-Causes

- Spaces in every path were not universally broken. One intermediate path with
  a space worked during the same setup session.
- The package URL was eventually resolvable.
- The final EditMode test failure was project-specific, not evidence of an MCP
  installation failure.
- The tool did not automatically loop forever; repeated retries were driven by
  the operator/agent following inadequate advice.

## Evidence Gaps

The report did not contain enough evidence to prove:

- whether PowerShell, Git Bash, MSYS argument conversion, or client
  command-string construction caused the exact path truncation
- whether Unity Hub/project-picker state contributed to the closeout wait
- live Windows Unity behavior after the fix set

Those are intentionally left as research items rather than guessed in code.

## Fix Direction Chosen

The fix direction was the consensus across multiple independent reviews:

- route native Windows setup through `.cmd`
- warn on existing Windows `bash` Codex config
- add raw/resolved project-root diagnostics
- clarify offline validation semantics
- add package import-state evidence
- adjust `ensure-ready` advice for declared-but-unresolved packages
- add already-closed editor closeout fast path
- avoid force quit or broad Windows process termination in the first fix set

Implementation details live in:

- `docs/architecture/designs/XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_PLAN_2026-06-18.md`
- `docs/architecture/designs/XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_IMPLEMENTATION_2026-06-18.md`

## Deferred Follow-Up

- native Windows repro to identify the exact truncating shell/client boundary
- live Windows Unity validation
- MCP progress/keepalive design for long imports
- explicit, safe force-recovery design for user-opened bridgeless editors
- optional automatic config rewrite flow for existing bad Codex blocks
