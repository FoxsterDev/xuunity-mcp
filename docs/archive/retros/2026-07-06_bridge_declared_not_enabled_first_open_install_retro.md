# XUUnity Light Unity MCP Install Retro: Package Declared but Bridge Not Enabled on First Open

Date: `2026-07-06`
Status: `active public retro`

## 1. Issue Title
`com.xuunity.light-mcp` declared in manifest but bridge stays `bridge_disabled` on first open; project-only enable requires a separate `init --enable-project` + editor reopen, and `setup-plan` proposes unwanted user-scope client config mutations.

## 2. Executive Summary
On a newly bootstrapped Unity `6000.0.58f2` project, `com.xuunity.light-mcp`
(git UPM, `#v0.3.38`) was added to `Packages/manifest.json` by hand and the
editor was opened. The package resolved and imported, but the first MCP tool call
(`unity.health.probe`) returned `bridge_disabled`: the per-project bridge is
opt-in and no enabled `bridge_config.json` existed. The health error correctly
named the recovery (`init_xuunity_light_unity_mcp.sh --project-root <p>
--enable-project` + reopen), which worked. Two operator-experience gaps remain:
(1) declaring the package + opening the editor is not enough — a separate enable
step + reopen is required; (2) `setup-plan` bundled project bridge-config with
**user-scope** client-config mutations (`~/.claude.json`, plus codex/cursor/
windsurf/claude_desktop targets), which are unwanted when the MCP client is
already connected.

## 3. Environment Table
| Field | Value |
| --- | --- |
| OS | macOS (darwin, arm64) |
| Unity | `6000.0.58f2` |
| Package | `com.xuunity.light-mcp` (git UPM, `#v0.3.38`) |
| MCP client | Claude Code (detected via `env:CLAUDECODE`), server already connected in-session |
| Test framework | `com.unity.test-framework` `1.5.1` (supported) |
| Launcher | `init_xuunity_light_unity_mcp.sh` (bash), `server.py ensure-ready` |

## 4. Project Topology
Single Unity project (a freshly created sibling target inside a multi-project
hub workspace). One project root; not recursive/hub discovery.

## 5. Installation Route Attempted
Manual manifest declaration of the git UPM package (converging to a reference
project's manifest), then editor open — deliberately **not** running
`setup-apply` first, because the MCP server was already connected in the session
and user-scope client wiring was not wanted.

## 6. Expected Behavior
Declaring the package + opening the editor once would start the per-project
bridge (heartbeat state written), making `unity.*` tools usable with an explicit
`projectRoot`.

## 7. Actual Behavior
- Offline `validate-setup`: `manifest_declared=true`,
  `import_state=declared_not_resolved`, `bridge_config_state=missing`,
  `validation_status=blocked`, `blockers=[bridge_config_missing]`.
- After the editor opened, `unity.health.probe` → `bridge_disabled`:
  "Unity bridge is disabled for this project. Enable it with
  `init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project` and
  reopen Unity." `host_prerequisites.bridge_enabled.ready=false`,
  `code=bridge_disabled`; `package_dependency.ready=true`;
  `live_editor.status=ready`; `transport_ready=false`.

## 8. First Failing Step
`bridge_enabled` prerequisite: the per-project bridge was never enabled because
no `Library/XUUnityLightMcp/config/bridge_config.json` with `enabled: true`
existed. Package resolution/import and editor liveness were fine.

## 9. Timeline of Attempted Actions
1. Added `com.xuunity.light-mcp` to `Packages/manifest.json`.
2. `validate-setup` (offline) → `declared_not_resolved` + `bridge_config_missing`.
3. Opened the editor (headless import, then GUI).
4. `unity.health.probe` → `bridge_disabled` with the recovery command.
5. `setup-plan` (inspection) → project action `write_bridge_config`, **plus**
   `planned_user_level_config_changes=[~/.claude.json]` and client-config targets
   for claude_code (user + project `.mcp.json`), codex, cursor, windsurf,
   claude_desktop. Declined (server already connected).
6. Ran `init_xuunity_light_unity_mcp.sh --project-root <p> --enable-project`:
   "updated `Library/XUUnityLightMcp/config/bridge_config.json`", and it
   **skipped** Codex + Claude Code user-scope config installs by default.
7. Reopened the editor (`ensure-ready --open-editor --background-open
   --startup-policy fail_fast_on_interactive_compile_block`).
8. `unity.health.probe` → `status=healthy`, 24 supported operations, transport
   `tcp_loopback` listening. All subsequent `unity.*` calls worked.

## 10. Sanitized Package State
- `Packages/manifest.json`: `"com.xuunity.light-mcp":
  "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.38"`.
- `packages-lock.json`: entry present after first editor resolve (was absent at
  the offline `validate-setup` stage → `lock_entry_present=false` then).
- `Library/PackageCache/com.xuunity.light-mcp*`: present after first open.

## 11. Sanitized MCP Client Config
Claude Code, server already connected in-session (no per-project wiring needed).
`setup-plan` still proposed `~/.claude.json` `merge_add_server_block` + a project
`.mcp.json` create + codex/cursor/windsurf/claude_desktop targets — all declined.

## 12. Setup Helper Output Summary
- `validate-setup`: `offline_validation_status=blocked`,
  `readiness_scope=offline_manifest_and_bridge_config_only`, note that it does
  not prove Unity resolution/import/live heartbeat.
- `setup-plan`: `validation_status=ready_to_apply`, project action
  `write_bridge_config`; separated project file changes from user-level client
  config, but presented both in one plan.
- `init --enable-project`: wrote the enabled `bridge_config.json`; **skipped
  user-scope client config by default** (good).

## 13. Windows Setup and Closeout Evidence
Not applicable (macOS).

## 14. Package Import / Readiness Evidence
- Pre-open: `import_state=declared_not_resolved`, `bridge_state_present=false`,
  `package_cache_present=false`.
- Post-enable + reopen: `bridge_state.json` present, `health_status=healthy`,
  `compiler_error_count=0`, transport listening — confirming resolve + import +
  live bridge only after the explicit enable + reopen.

## 15. Failure Classification
- Primary: `bridge_not_enabled`.
- Contributing/pre-open: `package_declared_not_imported` (until first editor
  open resolved it).

## 16. Most Likely Causes
- The per-project bridge is opt-in: an enabled `bridge_config.json` must exist,
  and it is written by `setup-apply` or `init --enable-project`, not by merely
  declaring the package or opening the editor.
- `setup-apply` couples the project-scoped `write_bridge_config` with user-scope
  client wiring, so an operator who only wants the project bridge (client already
  connected) must reach for the separate `init --enable-project` path.
- Enabling requires an editor **reopen** because the config is read at bridge
  bootstrap, adding a cycle.

## 17. Smallest Reproduction Steps
1. Add `com.xuunity.light-mcp` to a project's `Packages/manifest.json`.
2. Open the editor once.
3. Call `unity.health.probe --project-root <p>` → `bridge_disabled`.

## 18. Attachments / Logs to Include
- `validate-setup` JSON (offline).
- `unity.health.probe` failure JSON (`bridge_disabled`, host_prerequisites).
- `setup-plan` JSON (planned project vs user-level changes).
- `init --enable-project` stdout (config written; user-scope skipped).
- `Library/XUUnityLightMcp/config/bridge_config.json` (`{enabled:true,...}`).
- Post-recovery `bridge_state.json` (`health_status=healthy`).

## 19. Redaction Notes
Real project paths, workspace name, and app identifiers replaced with `<p>` /
`<unity-project>`. Package name, version tag, Unity version, error codes, and
command names retained.

## 20. Maintainer Questions That Remain
- Should first `ensure-ready` (or a `--project-only` setup mode) default-write an
  enabled project `bridge_config.json` so a first editor open starts the bridge
  without a separate `--enable-project` + reopen?
- Can `setup-plan`/`setup-apply` offer a project-scope-only mode that skips
  user-level client config when a client is already connected, so the safe path
  is one command with no user-config churn?
- Can `validate-setup` / `health.probe` state more prominently that "package
  declared" ≠ "bridge enabled," with the one-line enable command, at the first
  point the gap is detectable?

## Failure Classification Vocabulary Used
`bridge_not_enabled`, `package_declared_not_imported`.

## Smallest Next Action
Default-write an enabled, project-scoped `bridge_config.json` during first
`ensure-ready`/setup (no user-scope client mutation, no reopen requirement), and
document that declaring the package is not sufficient — the bridge is opt-in and
must be enabled per project.
