# XUUnity MCP Windows Setup Reliability Implementation

Date: `2026-06-18`
Status: `implemented; host validated`

## Purpose

This is the closeout record for the Windows setup reliability fix set. It says
what changed and why, without replaying the full incident retro.

## What Changed

### Native Windows Codex Config

`init_xuunity_light_unity_mcp.sh --install-codex-config` now detects
Windows-like hosts and writes:

```toml
command = "cmd.exe"
args = ['/d', '/c', '...run_installed_or_refresh_xuunity_mcp.cmd...']
```

On macOS/Linux it keeps the existing `bash` + `.sh` behavior.

If `[mcp_servers.xuunity_light_unity]` already exists and uses `bash` on a
Windows-like host, the installer keeps the existing block, emits
`windows_codex_launcher_mismatch`, and prints a merge-safe replacement block.

Why: the incident showed `.cmd` succeeded after Git Bash/PowerShell routes
failed, while the installer still wrote Unix-style Codex config.

### Windows-First Setup Docs

`README.md`, `INSTALL.md`, `docs/clients/codex.md`, and
`docs/clients/codex-unity-mcp-setup.md` now show native Windows `.cmd` setup
and verification commands with quoted project paths. The docs also call out
PowerShell ExecutionPolicy risk for `.ps1` and say Git Bash is not the
recommended native Windows setup route.

Why: the old examples nudged Windows agents toward shell boundaries that can
lose paths with spaces.

### Project Root Diagnostics

Project-root validation now reports:

- raw project-root input
- resolved project-root path
- Windows hint to quote paths and prefer `.cmd`
- `recommended_launcher_flavor = "cmd"` on Windows-like hosts

Why: the incident error only showed the already-truncated path ending at
`...\Unity`, hiding where the path was lost.

### Offline Validation Scope

`validate-setup` now keeps `validation_status` for compatibility and adds:

- `offline_validation_status`
- `readiness_scope = "offline_manifest_and_bridge_config_only"`
- `readiness_scope_note`
- `package_import_state`

Why: a manifest/config setup can be valid before Unity has resolved/imported
the package or started the bridge.

### Package Import State

Added host-side import-state inspection for `com.xuunity.light-mcp`:

- manifest declared/dependency
- lock entry/version/hash/source
- PackageCache presence/paths
- bridge_state presence
- import state:
  `not_declared`, `declared_not_resolved`, `resolved_not_cached`,
  `cached_without_bridge_state`, `imported_or_bridge_state_present`, `unknown`

Why: a declared-but-unresolved package cannot emit a bridge heartbeat, so
readiness needs package-import evidence in the failure payload.

### Ensure-Ready Advice

`ensure-ready` attaches package import-state before waiting, after success, and
to error details. When a live editor exists without bridge state and the package
is declared but unresolved/not cached, it reports:

```text
package_import_diagnosis = package_declared_not_imported
recommended_next_action = reopen_project_for_clean_resolve
```

Why: `recover_editor_session` was the wrong advice for a user-opened editor
that had not imported the package.

### Already-Closed Closeout Fast Path

`restore_host_opened_editor_state` now starts with a zero-time process probe.
If process visibility is available and no same-project editor is live, it
clears stale host session, bridge state, active test state, safe stale lock
state, and returns:

```text
closeout_classification = tracked_editor_already_closed
close_path = zero_time_process_probe
```

Why: the Windows report included a long wait while Unity appeared already
closed.

## Tests Added Or Updated

- Windows-like installer config writes `cmd.exe` + `.cmd`.
- Existing Windows `bash` Codex block emits
  `windows_codex_launcher_mismatch` and is not duplicated.
- Launcher parity `setup-plan` fixture uses
  `Unity Projects/Fake Project`.
- Windows project-root diagnostic includes raw/resolved path and `.cmd` hint.
- Package import-state classification covers manifest, lock, PackageCache, and
  bridge state combinations.
- `validate-setup` reports offline scope fields.
- `ensure-ready` timeout reports unresolved package import-state and clean
  reopen advice.
- Already-closed editor closeout does not call quit or terminate.

## Validation

```bash
git diff --check
python3 -m unittest discover -s tests -v
```

Result on macOS host: 243 tests passed, 1 native-Windows `.cmd` smoke skipped
as expected on this host.

## Not Implemented

- force quit for user-opened Unity editors
- automatic rewrite of existing bad Codex config
- exact Windows shell-boundary attribution
- live Windows Unity CI
- MCP keepalive/progress for long imports
