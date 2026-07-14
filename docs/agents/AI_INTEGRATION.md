# AI Integration Guide

Date: `2026-07-01`
Status: `active public guidance`

## Purpose

Use this guide when an AI agent needs to integrate the lightweight Unity MCP
service into a different repo or Unity project.

This guide is agent-agnostic.
It is written to work for Codex, Claude Code, Cursor, Gemini-style agents, and
future MCP-capable assistants.

For concrete task playbooks after setup, see `AGENT_WORKFLOWS.md`.

Author:
- Siarhei Khalandachou
- LinkedIn: `https://www.linkedin.com/in/khalandachou/`

## What The Agent Should Understand First

This service has two layers:

1. a host-side MCP server
2. an editor-only Unity package

They communicate through file IPC under:

- `<Project>/Library/XUUnityLightMcp/`

The Unity package is:

- editor-only
- disabled by default
- removable
- not intended to affect player builds by default

The public convenience CLI entrypoint is:

- `xuunity_light_unity_mcp.sh`

When a host repo has its own wrapper, the wrapper can delegate to this script.
Otherwise this script falls back to the installed helper in `~/.codex-tools/`.

If the helper is already installed locally, reuse that install before cloning a
fresh copy of the repo just to run setup.

## Integration Goals

When integrating into a new repo or project, the agent should:

1. install the host-side service
2. install or reference the Unity package
3. enable the bridge only for the target project
4. open Unity
5. verify capability and health
6. stop if capability checks fail
7. only then run validation or automation operations

## Minimum Host Steps

From this repository root:

```bash
bash init_xuunity_light_unity_mcp.sh
```

If the Unity project is in the same repo:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

This enables the bridge only. It does not rewrite `Packages/manifest.json`.

## Preferred Guided Setup

For new integrations, especially when the workspace may contain multiple Unity
projects or mixed Unity versions, prefer the setup wizard over manual manifest
edits:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > /tmp/xuunity-setup-plan.json

# Stop here. Show a user-visible preflight review before any mutation.
bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
```

Do not globally apply one dependency version across a mixed-version hub. The
plan computes per-project actions.

Manual `Packages/manifest.json` edits are package declaration only. They may
make Unity import `com.xuunity.light-mcp`, but they do not enable local editor
control by themselves. The supported first-open paths are `setup-apply` or
`ensure-ready --open-editor`, which write the project-scoped bridge config. They
do not require user-level client config mutation for clients that are already
connected to this server.

UI auto-review, sandbox approval, or tool-level approval is not a replacement
for a user-visible preflight review. Before `setup-apply`, installer mutation,
or user-level client config changes, show the user:

- detected current client
- intended wiring target
- approved Unity project root
- additional discovered Unity projects
- whether an existing helper install will be reused or a clone is required
- exact project files that will change
- exact user-level config files that will change
- whether the client must restart or refresh after mutation
- exact commands planned after approval

## Preferred Guided Uninstall

For cleanup requests, prefer the uninstall wizard over manual deletion:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Stop here. Show the uninstall preflight review before any removal.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Use `project-only-cleanup` when the goal is to make one Unity project look
not yet set up. It removes only the selected project's package dependency,
matching package-lock entry, and `Library/XUUnityLightMcp` bridge state. It
keeps client config and helper installs.

Use `full-reset-current-user` when the goal is current-user removal:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client auto \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Before `uninstall-apply`, show the user the mode, detected client, selected
client, target project, additional discovered projects, exact project cleanup
paths, exact user-level config cleanup paths, helper installs to remove or keep,
and restart/refresh requirements. Full reset removes only the selected
`xuunity_light_unity` MCP server block and selected current-user helper install
by default. Do not delete whole config files, unrelated MCP servers, or sibling
Unity project setup.

Test operations are optional. If `validate-setup --include-tests` reports
`disabled_missing_dependency`, ask for approval before opening Unity, then run:

```bash
bash xuunity_light_unity_mcp.sh install-test-framework \
  --project-root /path/to/UnityProject \
  --yes
```

This host command edits `Packages/manifest.json` offline. Prefer it before the
first Unity open/restart so Unity resolves the package graph during normal
startup. Use the in-editor MCP install operation only when the bridge is already
healthy and the operator intentionally wants a live Package Manager mutation.

If the project already declares `com.unity.test-framework` but the version is
below `1.1.33`, treat this as a cautious package upgrade, not a fresh install.
Ask for approval, update only that dependency, let Unity resolve packages, then
validate compile/test behavior. Unity 6000 projects with `1.1.33` are supported
but may report an optional `upgrade_recommended=true` toward `1.5.1`.

## Package Install Route

For production consumers, use the current Git UPM release path:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.45"
  }
}
```

For active local development of this MCP package, point directly at the package
folder only when you explicitly switch the consumer project into `devmode`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp"
  }
}
```

Use the Git UPM route when:

- the consumer repo should not vendor the package files locally
- the team wants a single upstream source of truth
- the project should be publishable or CI-friendly

OpenUPM is not the documented install route yet. The package layout is
OpenUPM-ready, but Git UPM remains the current production path until the package
is published there.

Use the direct local `file:` route when:

- the repo already has this checkout locally
- the team wants the latest working-tree package version immediately
- the team does not want commit-pin churn for active MCP iteration

Host-local wrappers can expose explicit package-source mode switches:

```bash
./xuunity_light_unity_mcp.sh \
  devmode \
  --project-root /path/to/UnityProject
```

```bash
./xuunity_light_unity_mcp.sh \
  prodmode \
  --project-root /path/to/UnityProject
```

## What The Agent Should Check After Install

Before doing real work, check in this order:

1. project root is a real Unity project
2. package is present in the manifest
3. bridge config exists and is enabled
4. Unity editor has opened the project
5. `bridge_state.json` exists
6. `capabilities_report.json` exists or can be generated
7. `unity.status` or compact `unity_status_summary` succeeds
8. `unity.capabilities.get` succeeds
9. `unity.health.probe` succeeds
10. if the host opened Unity for the validation session, the closeout path is defined
11. if transport churn interrupted a request, resolve it with `request-final-status --request-id <id>`

Only after that:

- compile
- tests
- scene inspection
- play mode
- screenshots
- scenario runs

For scenario acceptance checks, prefer the `unity_scenario_run_and_wait`
compact verdict path first. It returns the terminal decision, trust class,
failure class, recommended next action, short step summaries, and lifecycle
relaunch attribution when Unity had to be opened or reopened. Request verbose
or `includeFullPayload=true` only for deep diagnostics or raw per-step
assertions.

If readiness checks succeed but a later compile or test run fails, treat that as
a Unity project or runtime failure unless the error explicitly points back to
bridge readiness, package import, or unsupported capability.

## Agent Behavior Rules

An integrating agent should:

- treat capability probe as authoritative for version-sensitive operations
- keep the bridge disabled unless the current task actually needs Unity-aware validation
- prefer read and validation operations before mutation
- prefer compile before EditMode tests when changed scripts are already in play
- keep install and removal simple
- keep validation gaps explicit when Unity is not running or the bridge is disabled

An integrating agent should not:

- mutate `ProjectSettings` just to make the MCP work
- inject broad scripting defines
- assume Game View reflection works on every Unity version
- treat shell compile as equivalent to Unity validation
- silently install runtime diagnostics into production build paths
- try to click Unity Safe Mode dialogs through fragile GUI automation as a default startup path

## AI Agent Test Execution Guide

When xuunity-mcp is available, use MCP commands. Fallback to Unity CLI if MCP unavailable.

### MCP Commands
- EditMode batch: `batch-editmode-tests --project-root <path>`
- EditMode interactive: `ensure-ready --open-editor --project-root <path>` then `request-editmode-tests --project-root <path>`
- PlayMode interactive: `ensure-ready --open-editor --project-root <path>` then `request-playmode-tests --project-root <path>`

### Unity CLI Alternative
- EditMode batch: `Unity -runTests -testPlatform editmode -batchmode -projectPath <path>`
- PlayMode batch: `Unity -runTests -testPlatform playmode -batchmode -projectPath <path>`
- Use when MCP bridge unavailable or not installed

### Bridge Health Requirements
Always run `ensure-ready` before MCP requests. Check `unity.status` if issues
occur. Use `project-discovery-report` for diagnostics. Use
`recover-editor-session` for stale state. If health reports
`editor_log_diagnosis.freshness_class=prior_session_or_unverified`, verify with a
fresh editor session before treating the diagnosis as current compile truth.

### Test Framework Installation
MCP offline: `install-test-framework --yes --project-root <path>` (edits manifest.json before Unity opens)
Manual: Edit Packages/manifest.json directly if MCP not available

### Examples

EditMode batch via MCP:
```bash
bash xuunity_light_unity_mcp.sh batch-editmode-tests --project-root /path/to/UnityProject
```

All tests via MCP interactive:
```bash
bash xuunity_light_unity_mcp.sh ensure-ready --project-root /path/to/UnityProject --open-editor --background-open
bash xuunity_light_unity_mcp.sh request-editmode-tests --project-root /path/to/UnityProject
bash xuunity_light_unity_mcp.sh request-playmode-tests --project-root /path/to/UnityProject
```

## Startup Policy

For interactive editor startup, prefer the host-side `ensure-ready` helper over
blindly waiting for `bridge_state.json`.

Recommended default:
- `fail_fast_on_interactive_compile_block`

Alternative policies:
- `auto_enter_safe_mode_preferred`
- `batch_compile_lane`

Important limitation:
- this service does not auto-click the Unity Safe Mode dialog
- use Unity preferences to auto-enter Safe Mode if that is the team default
- if health reports a compile/Safe Mode dialog blocker, run the batch compile
  gate and fix compile errors, or open Safe Mode manually
- use `--background-open` when the host should avoid Unity stealing focus on macOS

When the host opened Unity only to run validation, prefer the paired closeout:

```bash
bash xuunity_light_unity_mcp.sh \
  restore-editor-state \
  --project-root /path/to/UnityProject
```

## Required Evidence To Record

After integration, the agent should record:

- Unity version
- package version
- whether the package is `file:`-based or Git-pinned
- whether bridge enablement succeeded
- active bridge transport
- capability adapter IDs
- supported and disabled operations
- at least one successful:
  - `unity.status`
  - `unity.health.probe`
  - `unity.compile.player_scripts` or `unity.tests.run_editmode`

## Recommended First Validation Pass

For a new consumer project, the recommended first pass is:

Before calling bridge tools, run `ensure-ready --open-editor` for the target
project. Declaring `com.xuunity.light-mcp` in `Packages/manifest.json` is not
itself bridge enablement; the project-local `bridge_config.json` must be enabled
so the editor can publish a heartbeat. A manual Unity open after a manifest edit
can still return `bridge_disabled` until that project config is enabled.

If the project was just moved to a newer Unity version, run a non-interactive
compile/import gate first with `-batchmode -quit -accept-apiupdate`, then reopen
the GUI for Play Mode validation. This avoids the interactive API Update
Required dialog blocking the editor main thread on first open.

1. `ensure-ready --open-editor`
2. `unity.status`
3. `request-status-summary`
4. `unity.capabilities.get`
5. `unity.health.probe`
6. `unity.console.tail` (defaults to `source=editor_log`; use
   `source=console` only when the in-memory Console buffer is explicitly needed)
7. `unity.scene.snapshot`
8. `unity.compile.player_scripts`
9. `unity.tests.run_editmode`

Only after that:

10. `unity.playmode.state`
11. `unity.playmode.set`
12. `unity.game_view.screenshot`
13. `unity.scenario.validate`
14. `unity.scenario.run`
15. `unity.scenario.result`

Scenario extension route:

16. list/invoke catalog-backed project actions when the consumer publishes
    `project_actions.yaml`
17. implement `IXUUnityLightMcpScenarioHook` in a project `Assets/Editor/` assembly when the consumer needs project-local automation not worth promoting into the shared package yet

## Where To Extend

If a new consumer project needs custom automation, the agent should prefer:

1. project-defined scenario hooks
2. project-defined adapter operations
3. host-side wrappers

The agent should avoid using generic dynamic code execution as the default
extension model.

## Client Setup

The host-side install (`init_xuunity_light_unity_mcp.sh`) lands the same MCP
server regardless of which agent client will consume it. Wiring a specific
client is a separate, opt-in step. Each supported agent has a template under
`templates/clients/<client>/`.

Currently checked-in client adapters:

- `templates/clients/codex/config.toml.snippet` — Codex `~/.codex/config.toml`
  block. Also installable through
  `init_xuunity_light_unity_mcp.sh --install-codex-config`.
- `templates/clients/claude-code/.mcp.json` — Claude Code project-scope MCP
  config. Copy to a repo root for team-wide opt-in.
  `templates/clients/claude-code/README.md` documents project / user / local
  scope routes. The init script also exposes
  `--install-claude-config` for user-scope registration via `~/.claude.json`.

Pick scope by intent:

- **project scope** — config under git, team-wide opt-in, requires per-user
  approval at first launch
- **user scope** — config in the home directory, one user, all repos
- **local scope** — config in per-user per-project storage, one user, one repo,
  not committed

For repos that check in MCP client config, the project-scope route is the
recommended default for team-shared MCP wiring.

## Canonical References

- `../../README.md`
- `AGENT_WORKFLOWS.md`
- `../architecture/DESIGN.md`
- `../architecture/ROADMAP.md`
- `../reference/COMPARISON.md`
- `../../LICENSE`
- `../architecture/designs/`
- `../archive/retros/`
- `../archive/reports/`
