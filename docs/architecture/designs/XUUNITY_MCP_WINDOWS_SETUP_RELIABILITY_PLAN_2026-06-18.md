# XUUnity MCP Windows Setup Reliability Plan

Date: `2026-06-18`
Status: `active plan; minimal fix set implemented`

## Purpose

This is the single design/plan document for the 2026-06 Windows setup
reliability work. It replaces the earlier split between investigation-design
and minimal-fix-set notes.

Use this document for what should exist in the product and what remains planned.
Use the incident retro for why the problem happened, and the implementation
closeout for what landed.

## Design Principles

- Native Windows setup should use native Windows launchers first:
  `cmd.exe` and `.cmd`.
- macOS/Linux behavior must stay unchanged.
- A setup command must preserve a Unity project path containing spaces or fail
  with enough evidence to identify the boundary that lost it.
- `validate-setup` is offline setup validation, not proof of live Unity bridge
  readiness.
- `ensure-ready` should distinguish "package declared" from "package imported
  by Unity".
- Recovery must not introduce broad or unsafe Windows process termination.

## Implemented Minimal Fix Set

The following consensus fixes are implemented and host-validated:

1. Windows Codex config generation uses `cmd.exe` plus
   `run_installed_or_refresh_xuunity_mcp.cmd`.
2. Existing Windows Codex config using `bash` is reported as
   `windows_codex_launcher_mismatch` without appending a duplicate block.
3. Windows docs route setup through `.cmd`, quote project paths, and mention
   PowerShell ExecutionPolicy risk for `.ps1`.
4. `project_not_found` diagnostics include raw input, resolved path, and a
   Windows launcher/quoting hint.
5. Launcher parity tests now use a fixture path containing spaces:
   `Unity Projects/Fake Project`.
6. `validate-setup` includes `offline_validation_status`, `readiness_scope`,
   and `package_import_state`.
7. Host-side package import-state inspection reports manifest, lockfile,
   PackageCache, and bridge-state evidence.
8. `ensure-ready` attaches package import-state to success and error payloads.
   For declared-but-unresolved package state with a live editor and no bridge,
   it recommends `reopen_project_for_clean_resolve`.
9. Editor closeout has a zero-time already-closed fast path that clears stale
   host session/bridge/test state without quit or terminate attempts.

## Deferred Work

These items are deliberately outside the minimal fix set:

- exact attribution of path truncation to PowerShell, Git Bash, MSYS argument
  conversion, or a client command-construction boundary
- automatic rewrite of an existing bad Codex config block
- force quit or bridge-independent termination for user-opened Unity editors
- MCP stdio keepalive/progress architecture for long Unity imports
- live Windows Unity CI with licensing
- Unity Hub/project-picker classification beyond diagnostics

## Acceptance Criteria For The Minimal Fix Set

- A native Windows automatic Codex install does not write `bash` config.
- A pre-existing Windows `bash` config is explicitly flagged.
- Windows users see `.cmd` setup examples before shell-ambiguous routes.
- A project path truncated at a space is diagnosable from one error payload.
- `validate-setup` clearly describes its offline scope.
- `ensure-ready` can report declared-but-not-resolved package state.
- Already-closed Unity editor closeout returns immediately when process
  visibility proves no same-project editor is live.
- Host-only tests pass without requiring Unity.

## Verification

Latest host validation:

```bash
git diff --check
python3 -m unittest discover -s tests -v
```

Result on macOS host: 243 tests passed, 1 native-Windows `.cmd` smoke skipped
as expected on this host.
