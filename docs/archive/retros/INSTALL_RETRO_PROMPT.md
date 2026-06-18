# XUUnity Light Unity MCP Install Retro Prompt

Date: `2026-05-23`
Status: `active public prompt`

## Purpose

Use this prompt when XUUnity Light Unity MCP installation or first setup failed
and you want to collect enough structured evidence for a useful public GitHub
issue.

This prompt is for setup problems before the MCP bridge is reliably healthy:
installer failures, Git UPM resolution failures, project discovery confusion,
manifest or lockfile conflicts, MCP client configuration mistakes, Unity package
compile errors immediately after install, and optional dependency setup issues.
It also covers native Windows setup hangs where shell quoting, MCP client
launcher flavor, Unity editor closeout, or package import readiness may be
ambiguous.

Keep project-private paths, proprietary names, secrets, tokens, and unrelated
logs out of public issue text. Replace private paths with stable placeholders
such as `<workspace>`, `<unity-project>`, and `<repo>`.

## Use When

- the README install flow failed or produced unclear results
- Unity Package Manager did not resolve the Git package
- a project was not discovered in a single-project, hub, mixed-version, or
  nested-repo workspace
- `setup-plan`, `setup-apply`, `validate-setup`, or `ensure-ready` failed
- Rider, VS Code, Claude Desktop, Codex, or another MCP client cannot start the
  server after setup
- Unity compiled the package with errors immediately after installation
- optional Test Framework setup was missing, too old, or upgraded unexpectedly

## Inputs To Gather First

At minimum:

1. the relevant chat transcript or session summary
2. the README version or Git tag used for installation
3. exact commands run and their terminal output
4. Unity version and project layout
5. sanitized MCP client configuration
6. sanitized `Packages/manifest.json` and `Packages/packages-lock.json` entries
   for `com.xuunity.light-mcp` and `com.unity.test-framework`
7. setup helper output from `setup-plan`, `validate-setup`, or `ensure-ready`
   when those commands can run
8. the wrapper/client launcher flavor used for each command: `.sh`, `.cmd`,
   `.ps1`, direct `python`, Git Bash, PowerShell, `cmd.exe`, WSL, or native MCP
   client
9. when the install hangs, a snapshot captured before closing, reopening, or
   retrying Unity, if it is safe to collect

Preferred command evidence:

```bash
bash xuunity_light_unity_mcp.sh setup-plan --workspace-root <workspace> --recursive
bash xuunity_light_unity_mcp.sh validate-setup --project-root <unity-project> --include-tests
bash xuunity_light_unity_mcp.sh --compact-summary ensure-ready --project-root <unity-project> --open-editor
```

For native Windows, prefer collecting the same evidence through the Windows
wrapper and PowerShell/cmd-friendly commands:

```powershell
& <repo>\xuunity_light_unity_mcp.cmd setup-plan --project-root "<unity-project>"
& <repo>\xuunity_light_unity_mcp.cmd validate-setup --project-root "<unity-project>" --include-tests
& <repo>\xuunity_light_unity_mcp.cmd ensure-ready --project-root "<unity-project>" --open-editor --timeout-ms 120000
```

If readiness, closeout, or "waiting for Unity to close" hangs, capture these
before manually changing Unity state when possible:

```powershell
& <repo>\xuunity_light_unity_mcp.cmd project-discovery-report --project-root "<unity-project>"
& <repo>\xuunity_light_unity_mcp.cmd verify-editor-closed --project-root "<unity-project>" --timeout-ms 0
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'Unity|Unity Hub|xuunity' } |
  Select-Object ProcessId, CommandLine
```

If a command cannot run, record the command, current directory, and exact error
instead of guessing. Do not run `setup-apply`, `install-test-framework`, or other
manifest-mutating commands unless the user explicitly approves that mutation.

## Prompt

```text
Analyze this XUUnity Light Unity MCP installation/setup problem and prepare a public GitHub issue package.

Goal:
- identify the first failing installation or setup step
- separate package resolution, Unity project discovery, MCP client config,
  bridge enablement, optional dependency, compile, and runtime readiness issues
- capture the smallest reproduction path maintainers can act on
- preserve enough evidence to diagnose the problem without leaking secrets or
  private project details

Required questions:
1. Which setup path was attempted: README Git UPM install, init script,
   setup-plan/setup-apply wizard, devmode, prodmode, or manual MCP client config?
2. What was expected to happen at that step?
3. What actually happened, including the first visible error?
4. Was the package dependency present in `Packages/manifest.json`?
5. Did `Packages/packages-lock.json` resolve the same package source, tag, or
   revision?
6. Which Unity version owns the target project, and is the workspace a
   single-project repo, flat hub, mixed-version hub, or nested-repo layout?
7. Which MCP client was configured, and what sanitized command/args/cwd did it
   use?
8. Did the server fail to start, the Unity bridge fail to enable, Unity package
   resolution fail, or Unity compile fail after install?
9. If tests are involved, was `com.unity.test-framework` missing, too old,
   already suitable, or intentionally not installed?
10. What commands were tried after the first failure, and did any of them mutate
    manifests, lockfiles, or client config?
11. On Windows, which launcher flavor was used at each stage: Git Bash `.sh`,
    native `.cmd`, `.ps1`, direct Python, or MCP client config?
12. If a project path contained spaces, did all path-with-space locations fail,
    or only a specific shell/client boundary?
13. If `project_not_found` occurred, what exact project root did the helper
    report after parsing?
14. If Unity closeout or readiness hung, did `project-discovery-report` and
    `verify-editor-closed --timeout-ms 0` show a live project editor PID,
    restricted process visibility, stale host session, stale bridge state, or
    no live editor?
15. After manifest mutation, had Unity actually resolved and imported the
    package: package-lock entry present, PackageCache entry present, bridge
    state present, and Editor.log showing package import?
16. For Codex or another MCP client, did the final user config use the native
    Windows launcher (`cmd.exe` + `.cmd`) or a Unix-like `bash` launcher?

Evidence to inspect:
- chat transcript or condensed timeline
- README link, package tag, release tag, or commit SHA used
- install/init/setup commands and output
- `ProjectSettings/ProjectVersion.txt`
- relevant `Packages/manifest.json` entries
- relevant `Packages/packages-lock.json` entries
- sanitized MCP client config: command, args, working directory, server level
- setup-plan, validate-setup, and ensure-ready output when available
- project-discovery-report output during the failing/hanging state
- verify-editor-closed output during the failing/hanging state
- Windows process snapshot for Unity, Unity Hub, and xuunity helper processes
- Unity Console or Editor.log excerpts for package resolution or compile errors
- OS, shell, Unity install path, and MCP client name/version when known
- network/proxy/Git credential errors if package resolution failed
- wrapper flavor evidence: `.sh`, `.cmd`, `.ps1`, direct Python, or client
  stdio launcher
- presence or absence of:
  - `Library/XUUnityLightMcp/state/bridge_state.json`
  - `Library/XUUnityLightMcp/state/host_editor_session.json`
  - `Library/PackageCache/com.xuunity.light-mcp*`
  - `Packages/packages-lock.json` entry for `com.xuunity.light-mcp`

Output format:
1. Issue title
2. Executive summary
3. Environment table
4. Project topology
5. Installation route attempted
6. Expected behavior
7. Actual behavior
8. First failing step
9. Timeline of attempted actions
10. Sanitized package state
11. Sanitized MCP client config
12. Setup helper output summary
13. Windows setup and closeout evidence, if applicable
14. Package import/readiness evidence
15. Failure classification
16. Most likely causes
17. Smallest reproduction steps
18. Attachments or logs to include
19. Redaction notes
20. Maintainer questions that remain

Failure classification vocabulary:
- `package_source_unreachable`
- `package_manifest_mutation_failed`
- `unity_package_resolve_failed`
- `project_discovery_ambiguous`
- `windows_shell_argument_split`
- `windows_launcher_flavor_mismatch`
- `client_mcp_config_invalid`
- `server_boot_failed`
- `bridge_not_enabled`
- `bridge_not_ready_after_install`
- `package_declared_not_imported`
- `stale_host_editor_session`
- `editor_closeout_state_ambiguous`
- `unity_hub_or_project_picker_blocking_import`
- `optional_dependency_missing`
- `optional_dependency_too_old`
- `unity_compile_error_after_install`
- `process_visibility_restricted`
- `unknown_install_failure`

Redaction rule:
- remove secrets, tokens, private repo URLs, proprietary project names, and large
  unrelated logs
- keep package names, Unity versions, command names, public GitHub URLs, error
  codes, request ids, and small relevant error excerpts

Do not stop at describing frustration.
End with an issue-ready summary and the smallest next action that would unblock
maintainer diagnosis.
```

## Expected Outputs

A good install retro should produce:

- a concise issue title
- an issue body that maintainers can read without the original chat
- a clear first-failing-step classification
- sanitized project/package/client evidence
- a short reproduction path
- explicit missing information when the evidence is incomplete

## Promotion Targets

When the install retro finds reusable value, prefer promoting into:

- `../../../README.md`
- `../../../INSTALL.md`
- `../../agents/AI_INTEGRATION.md`
- `../../agents/AGENT_WORKFLOWS.md`
- setup wizard output and validation summaries
- public smoke or install simulation docs

## Notes

- Prefer `setup-plan` evidence before any manifest mutation.
- For mixed Unity workspaces, keep evidence per project; do not collapse all
  projects into one global dependency recommendation.
- Treat optional Test Framework support as optional capability evidence, not as a
  core MCP health failure unless the user explicitly asked to install or run
  tests.
- On native Windows, do not collapse Git Bash, PowerShell, `cmd.exe`, `.cmd`,
  `.ps1`, WSL, and MCP client stdio config into one "Windows shell" bucket. The
  failing boundary matters.
- For hangs, preserve the first stuck state. A report created only after manual
  close/reopen is still useful, but it should explicitly say which evidence was
  captured before versus after recovery.
- Do not classify every path-with-space as broken just because one shell
  invocation truncated a path. Record which path with spaces worked and which
  command boundary failed.
- `validate-setup` is offline project setup evidence. It does not by itself
  prove that Unity has resolved the Git package, imported the package, or
  started a live bridge heartbeat.
