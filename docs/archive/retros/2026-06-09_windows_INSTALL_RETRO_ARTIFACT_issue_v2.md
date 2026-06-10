## 1) Issue title
XUUnity Light Unity MCP fails ensure-ready/batch-editmode-tests in WSL path from Windows-based Unity install and stale bridge state

## 2) Executive summary
XUUnity MCP package installation and validation completed successfully, but test/run readiness failed afterward because the active helper context in WSL could not reliably discover/attach to the Windows-installed Unity editor. Commands reported unity_app_not_found and later stale/ghost bridge state behavior, while a Windows Unity instance for the same project was already running. Tests could not be executed in batchmode until the editor lifecycle is normalized and MCP client/editor launch path is aligned to the same host context.

## 3) Environment table
- Date: 2026-06-09  
- Host OS: Windows  
- Working shell: Windows PowerShell + WSL bash  
- Repo path: D:\Development\Unity\_mtr\HumanFactory  
- Unity version: 6000.3.2f1 (ProjectSettings/ProjectVersion.txt)  
- MCP host artifacts: both /home/matro/.local/share/xuunity-mcp and /home/matro/.codex-tools/xuunity-mcp (WSL), plus Windows mirror under /mnt/c/Users/matro/.local/share/xuunity-mcp and /mnt/c/Users/matro/.codex-tools/xuunity-mcp  
- Unity installs found: D:\ProgramFiles\UnityHub\Editor\6000.3.2f1\Editor\Unity.exe (present and running in another PID)

## 4) Project topology
Single-project scope only: /Development/Unity/_mtr/HumanFactory

## 5) Installation route attempted
README flow (Git UPM + helper + wizard):
- init_xuunity_light_unity_mcp.sh (clone + install)
- setup-plan
- setup-apply
- validate-setup
- readiness checks via ensure-ready
- attempts to run batch-editmode-tests

No manifest-free/manual-only path was used.

## 6) Expected behavior
- MCP helper should auto-detect Unity installation in host environment
- ensure-ready --open-editor should transition to healthy live editor + bridge state
- batch-editmode-tests should execute EditMode tests and return test result summary/report

## 7) Actual behavior
- Setup commands succeeded and package manifest/lockfile were updated
- validate-setup returned ready
- ensure-ready failed with unity_app_not_found
- recover-editor-session reported stale bridge state and no_live_editor_process
- direct batch-editmode-tests failed with unity_app_not_found
- direct Unity batchmode command failed due another Unity instance already open with the same project

## 8) First failing step
ensure-ready (post-setup) in WSL host context.

## 9) Timeline of attempted actions
1. Cloned xuunity-mcp helper and ran installer.
2. Ran setup-plan --project-root D:/.../HumanFactory  
3. Ran setup-apply and validate-setup successfully.
4. Ran ensure-ready --project-root ... --open-editor from WSL wrapper.
5. Received unity_app_not_found (could not auto-detect Unity).
6. Attempted with XUUNITY_UNITY_EDITOR_ROOTS override; still failed and showed stale bridge/editor mismatch.
7. Ran recover-editor-session; it cleared stale state but remained offline.
8. Re-ran tests attempts:
   - batch-editmode-tests -> unity_app_not_found
   - Unity direct batch mode -> blocked by already-running Unity instance with project open.

## 10) Sanitized package state
- Added by setup: com.xuunity.light-mcp with Git URL source at #v0.3.23
- Existing com.unity.test-framework already present at 1.6.0
- In lockfile: corresponding com.xuunity.light-mcp entry is present and aligned to the same git ref
- No manifest mutation failures observed

## 11) Sanitized MCP client config
- Helper bootstrap created/updated Codex-side config on one pass; detected-client confidence was initially low and client targets were reviewed as part of plan.
- Main issue did not stem from explicit invalid MCP JSON/TOML edits; failure occurred at editor discovery/runtime attach layer and stale bridge state.

## 12) Setup helper output summary
- setup-plan: project detected, package dependency missing -> planned set_manifest_dependency action; package declared and bridge state present
- setup-apply: package mutation applied
- validate-setup: status ready, test framework supported
- ensure-ready: error unity_app_not_found
- recover-editor-session: reported stale bridge state and returned recovery classification recovered then final discovery remained no_live_editor_process
- batch-editmode-tests: unity_app_not_found even with --unity-app override in WSL

## 13) Failure classification
- server_boot_failed
- Supporting classifier: bridge_not_ready_after_install (secondary)

## 14) Most likely causes
- WSL-hosted helper cannot reliably map/launch the Windows Unity editor binary path/context
- Mixed host-state conflict: stale bridge state still present while no live editor bridge is attached
- Simultaneous Unity process already owning the project, preventing batchmode parallel execution

## 15) Smallest reproduction steps
1. In a Windows machine with Unity installed under D:\ProgramFiles\UnityHub\Editor\6000.3.2f1\Editor\Unity.exe, run:
   - setup-plan --project-root <project>
   - setup-apply --plan-file ... --project-root <project> --yes
   - validate-setup --project-root <project>
2. While project is open in a Unity session, run WSL:
   - ensure-ready --project-root <project> --open-editor
3. Observe unity_app_not_found/stale recovery behavior and test lane failure.

## 16) Attachments or logs to include
- setup-plan JSON output
- setup-apply JSON output
- validate-setup JSON output
- ensure-ready error JSON
- recover-editor-session JSON
- batch-editmode-tests error JSON
- Project Packages/manifest.json and Packages/packages-lock.json redacted package sections
- PowerShell process list showing Unity process for same project
- Editor launch command/output if available (Unity.exe logs)

## 17) Redaction notes
- Replace absolute paths with <workspace>, <unity-project>, <repo> in public issue.
- Remove process IDs, machine/user names, and any session-specific PID values.
- Keep package/version/error text intact.

## 18) Maintainer questions that remain
- Does WSL-side helper have a documented requirement for editor discovery overrides when editor is Windows-installed under nonstandard root?
- Is there a stable mapping for Unity.exe discovery from WSL in mixed WSL/Windows setups, or should users run all helper tooling from native Windows context?
- What is the intended recovery flow when stale bridge state exists but the editor is open in another instance?

---
Issue-ready summary:
- Root blocker is runtime/editor attach, not package mutation.
- setup-plan/setup-apply/validate-setup succeeded; test execution is blocked before first test run due WSL-host discovery and stale bridge state.
- Smallest unblock action: run MCP commands from a single native host context (Windows) with matching Unity launch path and clean bridge state, or fully close/reopen the project editor before ensure-ready/batch-editmode-tests.