<div align="center">

<img src="docs/assets/xuunity-light-unity-mcp-preview.png" alt="XUUnity Light Unity MCP preview banner" width="100%">

<br>

# XUUnity Light Unity MCP

**Open-source lightweight Unity MCP server for safe Unity Editor automation.**

Connect Cursor, Claude Code, Claude Desktop, Rider, Windsurf, Codex-style
agents, and custom MCP clients to Unity through a local stdio MCP server and a
small editor-only Unity package.

<p>
  <a href="https://github.com/FoxsterDev/xuunity-light-unity-mcp"><img alt="GitHub stars" src="https://img.shields.io/github/stars/FoxsterDev/xuunity-light-unity-mcp?style=flat&logo=github"></a>
  <a href="LICENSE"><img alt="License MIT" src="https://img.shields.io/badge/license-MIT-red.svg"></a>
  <img alt="Unity 2021.3+" src="https://img.shields.io/badge/Unity-2021.3%2B-black.svg?logo=unity&logoColor=white">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white">
  <img alt="MCP enabled" src="https://img.shields.io/badge/MCP-enabled-green.svg">
  <img alt="Git UPM ready" src="https://img.shields.io/badge/Git%20UPM-ready-brightgreen.svg">
  <img alt="OpenUPM planned" src="https://img.shields.io/badge/OpenUPM-planned-lightgrey.svg">
</p>

[Agent Quick Start](#agent-quick-start) |
[Manual Install](#manual-install) |
[Verify Existing Install](#verify-existing-install) |
[AI Setup Prompt](#ai-agent-setup-prompt) |
[Features](docs/reference/FEATURES.md) |
[Client Docs](#supported-clients) |
[Security](SECURITY.md) |
[Comparison](docs/reference/COMPARISON.md) |
[Agent Workflows](docs/agents/AGENT_WORKFLOWS.md)

</div>

---

## Why Use It

Use XUUnity Light Unity MCP when you want a local-first Unity MCP for
validation-heavy AI workflows, not broad unrestricted editor mutation.

- compile checks without switching the active Unity build target
- EditMode and PlayMode tests with normalized result accounting
- scene snapshots, scene assertions, console tail, and Game View screenshots
- bounded scenario validation and request-journal recovery after editor reloads
- same-host multi-project routing for workstations with multiple Unity projects
- editor-only package, disabled by default, with no player-build footprint by default

---

## Quick Start

Choose one path first:

- [Agent Quick Start](#agent-quick-start) for AI-driven setup from a short prompt
- [Manual Install](#manual-install) for direct human setup
- [Verify Existing Install](#verify-existing-install) when the helper or client wiring may already exist

### Prerequisites

- Unity 2021.3 LTS+; the current release has live validation on Unity 2021.3,
  2022.3, and 6000.x. See [Status](docs/reference/STATUS.md).
- Python 3.10+
- one MCP client: [Claude Code](docs/clients/claude-code.md), [Claude Desktop](docs/clients/claude-desktop.md), [Cursor](docs/clients/cursor.md), [Rider](docs/clients/rider.md), [Windsurf](docs/clients/windsurf.md), or a [Codex-style agent](docs/clients/codex.md) with the [Codex visual setup guide](docs/clients/codex-unity-mcp-setup.md)

Before running the helper, verify which Python it will use:

```bash
command -v python3
python3 --version
```

If your default `python3` is older than `3.10`, set `PYTHON` explicitly before
running `run.sh` or `xuunity_light_unity_mcp.sh`.

Important:

- UI auto-review, sandbox auto-approval, or tool-level approval is not the same
  thing as user approval of setup mutations.
- If `~/.codex-tools/xuunity-light-unity-mcp/run.sh` or the equivalent
  host-tools install already exists, reuse it. Do not clone the repo locally
  unless the helper is missing or local MCP development is the goal.

## Agent Quick Start

This section is the fast-path for AI agents that need to install MCP into a new
repo and run the first MCP command or EditMode tests correctly.

### Agent Defaults

Use this contract when the user gives a short request such as:

```text
setup mcp from the repo README.md into the project /path/to/UnityProject and run edit mode tests there
```

Agent defaults:

- treat the current host client that is executing the request as the default
  MCP wiring target unless the user explicitly names a different client
- treat the explicitly requested Unity project path as the only default setup
  target
- prefer Git UPM package mode unless the user explicitly asks for local package
  development
- if the host helper is already installed locally, reuse it before asking to
  clone the repo

### Required Sequence

1. Read `README.md`, `INSTALL.md`, and the matching `docs/clients/*` guide for
   the current host client.
2. Run a non-mutating preflight:
   - confirm Python 3.10+
   - confirm Unity project structure
   - detect whether the request targets one Unity project or an entire workspace
   - identify whether user-level client config such as `~/.codex/config.toml`
     or `~/.claude.json` would change
3. Produce a setup plan before mutating files:
   - for one requested Unity project, use `setup-plan --project-root
     "<UNITY_PROJECT_ROOT>"`
   - for a workspace or nested hub, use `setup-plan --workspace-root
     "<WORKSPACE_ROOT>" --recursive`
4. Show a short preflight review and wait for approval before any mutation,
   clone, installer run, manifest change, or user-level client config update.
5. After approval, apply setup only to the approved project roots.
6. Run `validate-setup`.
7. Run `ensure-ready --open-editor` when Unity is not already ready and wait
   for it to finish before checking status.
8. Run the first status check:
   - use `request-status-summary` when the current client session cannot see
     newly wired MCP tools yet
   - use `unity_status_summary` as the first live MCP-tool smoke check after
     the client has loaded the server
9. When the user requested tests, run EditMode tests after the status summary is
   healthy.
10. Finish with:
   - files changed
   - commands run
   - readiness result
   - first MCP command result
   - EditMode test result
   - whether a client restart is still required

### Preflight Review Checklist

- detected current client
- intended client wiring target
- requested Unity project root
- any additional discovered Unity projects
- whether setup will modify user-level client config
- files planned for mutation
- commands planned after approval
- whether the client must restart or refresh its MCP server list afterward

### Required Preflight Review Template

Every agent should show a short review block like this before `setup-apply`:

```text
Preflight review
- Current client: <detected client>
- Wiring target: <target client>
- Unity project root: <approved project root>
- Additional discovered Unity projects: <none or list>
- Existing helper install: <reuse existing helper | clone required>
- Planned project file changes: <manifest, bridge config, lockfile, none>
- Planned user-level config changes: <exact file paths or none>
- Restart or refresh required after mutation: <yes/no and which client>
- Planned commands after approval: <setup-apply, validate-setup, ensure-ready, request-status-summary, unity_status_summary after reload, ...>

Do not run setup-apply, installer commands, helper sync, or client config edits
until the user explicitly approves this review.
```

### Safe Inspect Before Approval

- reading docs
- checking Python and Unity versions
- `setup-plan` from this wrapper, which must not refresh or write the installed
  helper
- `uninstall-plan` from this wrapper, which must not refresh, write, or remove
  the installed helper
- reading manifest, lockfile, and client config
- topology inspection

### Mutating Actions That Require Approval

- `git clone`
- installer runs
- `setup-apply`
- `uninstall-apply`
- `install-test-framework`
- manifest or lockfile edits
- user-level client config updates
- helper install removal
- `devmode` or `prodmode`

### Guided Setup Wizard

For one explicitly requested Unity project, produce a non-mutating plan first:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --project-root /path/to/UnityProject > /tmp/xuunity-setup-plan.json

# Stop here. Review the plan with the user before continuing.
bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
```

For flat hubs, mixed-version hubs, or nested repositories, scan the workspace
first and require an explicit target selection before `setup-apply`:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > /tmp/xuunity-setup-plan.json

# Stop here. Review the plan. Then apply only to the intended Unity project roots.
bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes
```

The core MCP package works without `com.unity.test-framework`. Test operations
are an optional capability. To enable them explicitly:

```bash
bash xuunity_light_unity_mcp.sh install-test-framework \
  --project-root /path/to/UnityProject \
  --yes
```

Prefer this before opening or restarting Unity. The host helper mutates
`Packages/manifest.json` offline, then Unity resolves the package graph during
normal startup.

The helper recommends `com.unity.test-framework@1.1.33` for Unity 2021/2022 and
`@1.5.1` for Unity 6000+, while the capability gate remains `>= 1.1.33`.

### Guided Uninstall Wizard

Use `uninstall-plan` before any removal. It prints structured JSON and a
human-readable `preferred_review_summary`.

Project-only cleanup makes one Unity project look not yet set up while
keeping current-user client wiring and helper installs:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Stop here. Review the plan with the user before continuing.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Project-only mode removes only the approved project-level MCP package dependency,
the matching packages-lock entry, and `Library/XUUnityLightMcp` bridge state
from the selected Unity project. It keeps `~/.codex/config.toml`,
`~/.claude.json`, and helper installs such as
`~/.codex-tools/xuunity-light-unity-mcp`.

Full reset for the current user removes the selected current-user client
wiring and helper install in addition to optional project cleanup:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --project-root /path/to/UnityProject \
  --client auto > /tmp/xuunity-uninstall-plan.json

# Stop here. Review exact project, user config, and helper removals.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Use `--client codex|claude_code|cursor|windsurf|claude_desktop` when the
current client cannot be detected. Full reset removes only the
`xuunity_light_unity` block from the selected user config file; it does not
delete the whole config file or unrelated MCP servers. Known helper installs
for other clients are kept unless the plan is created with
`--include-other-client-helpers`.

For workspace or nested project contexts, pass `--workspace-root` and
`--recursive` only to report additional discovered Unity projects. The uninstall
flow mutates only explicit `--project-root` values and never silently removes
setup from sibling Unity projects.

Suggested short prompt for agents:

```text
Remove XUUnity Light Unity MCP from <UNITY_PROJECT_ROOT> in project-only cleanup mode.
Read README.md and INSTALL.md, run uninstall-plan --mode project-only-cleanup
--project-root "<UNITY_PROJECT_ROOT>", show the preflight review, wait for
approval, then run uninstall-apply --plan-file <reviewed plan> --yes.
```

For a current-user reset:

```text
Fully reset XUUnity Light Unity MCP for the current user. Run uninstall-plan
--mode full-reset-current-user, include --project-root only if a Unity project
was named, show exact user config/helper removals, wait for approval, then run
uninstall-apply with the reviewed plan.
```

### AI Agent Setup Prompt

Copy this prompt into your coding agent from the Unity project you want to
connect. Replace the placeholders before running it.

```text
Configure XUUnity Light Unity MCP for this Unity project and optionally run the
first requested MCP operation after setup.

Inputs:
- Unity project root: <absolute path to the Unity project>
- Workspace root: <absolute path to workspace; may equal the project root>
- First operation after setup: <optional, for example EditMode tests, health check, compile, or none>

Rules:
- Read README.md, INSTALL.md, and the matching docs/clients/* guide before
  editing files.
- Use the current host client that is running this request as the default MCP
  wiring target unless the user explicitly requests another client.
- Prefer Git UPM release v0.3.19 unless the user explicitly requests local
  package development.
- Reuse an existing installed host helper if one is already present locally.
  Clone the repo only when the helper is missing or local MCP development is
  explicitly requested.
- Preserve existing config. Merge the `xuunity_light_unity` server block; do
  not overwrite unrelated MCP servers, editor settings, or package entries.
- Keep the package editor-only. Do not add runtime/player dependencies.
- Treat `com.unity.test-framework` as optional. Install or upgrade it only
  after explicit approval when the requested post-setup operation requires test
  capability.
- Ask before cloning the repo locally, running mutating installer steps,
  editing user-level client config, mutating manifests or lockfiles, changing
  more than one discovered Unity project, or doing destructive git/process
  actions.

Required procedure:
1. Confirm Python 3.10+, Unity project structure, current client, and workspace
   topology.
2. If the MCP repo is missing locally, ask before cloning
   https://github.com/FoxsterDev/xuunity-light-unity-mcp.git outside the Unity
   Assets folder and treat it as <MCP_REPO_ROOT>.
3. Produce a non-mutating setup plan from <MCP_REPO_ROOT>. `setup-plan` must
   not clone, run the installer, sync helper files, edit manifests, or change
   user-level client config:
   - for one requested Unity project:
     bash xuunity_light_unity_mcp.sh setup-plan --project-root "<UNITY_PROJECT_ROOT>" > /tmp/xuunity-setup-plan.json
   - for a workspace or nested hub:
     bash xuunity_light_unity_mcp.sh setup-plan --workspace-root "<WORKSPACE_ROOT>" --recursive > /tmp/xuunity-setup-plan.json
4. Show a short preflight review with:
   - detected current client
   - intended wiring target
   - requested Unity project root
   - additional discovered Unity projects
   - whether an existing helper install will be reused or a clone is required
   - files that will change, including user-level config
   - whether the client must restart or refresh after the change
   - commands that will run after approval
5. Wait for approval before cloning, installer runs, helper sync, client
   wiring, setup-apply, manifest edits, lockfile edits, or user-level config
   changes.
6. After approval, install or refresh the host helper only if it is missing or
   stale enough to block the requested setup:
   bash init_xuunity_light_unity_mcp.sh
7. Apply the approved plan only to the approved Unity project roots:
   bash xuunity_light_unity_mcp.sh setup-apply --plan-file /tmp/xuunity-setup-plan.json --project-root "<UNITY_PROJECT_ROOT>" --yes
8. Wire the selected client using templates/clients/ or the matching
   docs/clients guide.
9. If the requested post-setup operation needs tests and the plan reports
   missing or too-old Test Framework support, ask for approval and then run:
   bash xuunity_light_unity_mcp.sh install-test-framework --project-root "<UNITY_PROJECT_ROOT>" --yes
10. Verify readiness:
    bash xuunity_light_unity_mcp.sh validate-setup --project-root "<UNITY_PROJECT_ROOT>"
    bash xuunity_light_unity_mcp.sh ensure-ready --project-root "<UNITY_PROJECT_ROOT>" --open-editor
    bash xuunity_light_unity_mcp.sh request-status-summary --project-root "<UNITY_PROJECT_ROOT>" --timeout-ms 5000
11. If the current client session cannot see the new MCP server, restart or
    refresh the client now. Then treat `unity_status_summary` as the canonical
    first live MCP-tool smoke-check after setup. Verify `unity_capabilities`
    and `unity_health_probe` after the status summary is healthy.
12. If a post-setup operation was requested, run it only after the status
    summary is healthy.
13. Finish with a concise report listing files changed, commands run, readiness
    verification, the first MCP command result, any requested post-setup
    operation result, whether a client restart is still required, and whether
    any failing compile or test result is an MCP setup failure or a project
    runtime failure.
```

## Manual Install

### 1. Install The Unity Package

In Unity: `Window > Package Manager > + > Add package from git URL...`

> Tip
>
> ```text
> https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.19
> ```

Or add it directly to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.19"
  }
}
```

Local package source for MCP development:
`file:/absolute/path/to/xuunity-light-unity-mcp/packages/com.xuunity.light-mcp`.
Keep Git UPM as the default project state. Switch to the local `file:` source
only through explicit `devmode`.
OpenUPM is planned; use Git UPM until the package is published there.

Migration note: `v0.3.11` used `templates/unity-package`. `v0.3.12+` uses
`packages/com.xuunity.light-mcp` so the package path is registry-native for
OpenUPM and Unity Package Manager indexing.

### 2. Install The Host MCP Helper

```bash
bash init_xuunity_light_unity_mcp.sh
```

Enable the bridge for one Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

The installer writes Unix and Windows launchers: `run.sh`, `run.cmd`, and
`run.ps1`.

If this helper is already installed under `~/.codex-tools`,
`~/.claude-tools`, or another explicit host-tools path, reuse it instead of
cloning a fresh copy just to run setup.

For local MCP package iteration, switch package mode explicitly:

```bash
bash xuunity_light_unity_mcp.sh devmode --project-root /path/to/UnityProject
```

To switch back to the published Git-backed source:

```bash
bash xuunity_light_unity_mcp.sh prodmode --project-root /path/to/UnityProject
```

### 3. Connect Your Client

Use a ready-made client template. If the destination file already exists, merge
the `xuunity_light_unity` server block instead of overwriting unrelated MCP
servers.

```bash
# Claude Code project scope
cp templates/clients/claude-code/.mcp.json .mcp.json

# Cursor project scope
mkdir -p .cursor
cp templates/clients/cursor/mcp.json .cursor/mcp.json
```

Native Windows templates are included next to the Unix templates as
`.windows.json` files.

When running the wrapper directly, the host helper install target can be pinned
with `XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex|claude|auto`. `auto`
prefers `~/.codex-tools` inside Codex-style environments and preserves the
Claude-side `~/.claude-tools` helper for Claude clients.

### 4. Verify Connection

```bash
bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject

bash xuunity_light_unity_mcp.sh ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor

bash xuunity_light_unity_mcp.sh request-status-summary \
  --project-root /path/to/UnityProject
```

Run these helper commands sequentially; do not start the status check before
`ensure-ready` finishes. If the current client session has not hot-reloaded the
new MCP server yet, `request-status-summary` is the first verification command.
After the client can see the server, treat `unity_status_summary` as the
canonical first live MCP-tool smoke-check. After it reports a healthy bridge,
confirm `unity_capabilities` and `unity_health_probe` before moving on to tests
or builds.

Install success means:

- `validate-setup` reports a ready configuration
- `ensure-ready` brings the editor to a healthy bridge state
- `request-status-summary` reports a healthy bridge before live MCP tools are
  available, or `unity_status_summary` reports a healthy bridge after the
  client loads the server
- `unity_capabilities` and `unity_health_probe` succeed

If those checks pass but a later compile or test run fails, treat that as a
Unity project or runtime failure unless the failure explicitly points back to
bridge readiness, package import, or unsupported capability.

## Verify Existing Install

Use this path when the helper, client wiring, or package may already exist:

1. check whether the host helper already exists locally
2. inspect the client config instead of rewriting it blindly
3. run `validate-setup`
4. run `ensure-ready --open-editor` only if Unity is not already ready
5. run `request-status-summary` first if the client has not loaded the MCP
   server yet, then restart or refresh the client and run `unity_status_summary`
   as the first live smoke-check

This avoids duplicate MCP server blocks, unnecessary repo clones, and silent
rewrites of user-level config.

Then try:

```text
Use XUUnity Light Unity MCP to check this Unity project health, compile Android
player scripts, and report the first actionable failure with artifact paths.
```

For a clean-project end-to-end Android smoke, including Git-default package
install, bridge readiness, and a regular Unity batch APK build:

```bash
templates/smoke/run_clean_project_android_apk_smoke.sh
```

If the selected Unity editor does not have Android Build Support installed but
you still want MCP-only readiness evidence, allow the runner to skip the APK
lane explicitly:

```bash
templates/smoke/run_clean_project_android_apk_smoke.sh --allow-no-android
```

---

## Supported Clients

- [Claude Code](docs/clients/claude-code.md)
- [Claude Desktop](docs/clients/claude-desktop.md)
- [Cursor](docs/clients/cursor.md)
- [Rider](docs/clients/rider.md)
- [Windsurf](docs/clients/windsurf.md)
- [Codex-style agents](docs/clients/codex.md) ([visual setup](docs/clients/codex-unity-mcp-setup.md))
- custom stdio MCP clients

Optional: connect XUUnity MCP to Codex/Codex-style clients when you want Codex
to validate Unity status, compile, tests, and setup directly from the chat. Use
this only on trusted local projects. If you also use Rider or VS Code MCP,
avoid running concurrent commands against the same Unity project.

Manual macOS/Linux and Windows configs live in `templates/clients/`.

<details>
<summary><strong>Features And Tools</strong></summary>

Popular MCP tools:

`xuunity_setup_plan` | `xuunity_setup_apply` | `xuunity_setup_validate` |
`xuunity_uninstall_plan` | `xuunity_uninstall_apply` |
`unity_license_capabilities` |
`unity_status_summary` | `unity_capabilities` | `unity_health_probe` |
`unity_console_tail` | `unity_scene_snapshot` | `unity_scene_assert` |
`unity_compile_player_scripts` | `unity_compile_matrix` |
`unity_compile_build_config_matrix` | `unity_tests_run_editmode` |
`unity_tests_run_playmode` | `unity_playmode_state` | `unity_playmode_set` |
`unity_build_player` |
`unity_game_view_configure` | `unity_game_view_screenshot` |
`unity_scenario_validate` | `unity_scenario_run_and_wait` |
`unity_request_final_status` | `unity_project_refresh` |
`unity_project_action_list` | `unity_project_action_invoke` |
`unity_artifact_register` | `unity_artifact_write_report` |
`unity_package_install_test_framework` | `unity_edm4u_resolve` |
`unity_sdk_dependency_verify`

Host helper commands include `setup-plan`, `setup-apply`, `uninstall-plan`,
`uninstall-apply`, `validate-setup`, `install-test-framework`,
`license-capabilities`, `ensure-ready`, `verify-editor-closed`,
`request-editor-quit --wait-for-exit`, `restore-editor-state`,
`recover-editor-session`, `batch-compile`, `batch-compile-matrix`,
`batch-editmode-tests`, `batch-build-config-compile-matrix`,
`batch-build-player`, `project-action-list`, `project-action-invoke`,
`artifact-register`, `artifact-write-report`, `artifact-probe`, `devmode`,
and `prodmode`.

Scenario JSON may use Unity-native `project_action` steps for catalog-backed
project actions. Unity resolves `project_actions.yaml`, enforces mutation
approval, and executes the matching `project_defined_hook`; the host wrapper
also performs the same normalization before dispatch as an early diagnostic.

See [FEATURES.md](docs/reference/FEATURES.md) for maturity levels and implementation evidence.

</details>

<details>
<summary><strong>Package Mode, Troubleshooting, And Security</strong></summary>

`devmode` is for local MCP package edits:
`bash xuunity_light_unity_mcp.sh devmode --project-root /path/to/UnityProject`.

`prodmode` is for published Git-pinned package state:
`bash xuunity_light_unity_mcp.sh prodmode --project-root /path/to/UnityProject`.

Troubleshooting:

- Server not found: run `bash init_xuunity_light_unity_mcp.sh` again.
- Bridge disabled: run the installer with `--project-root` and `--enable-project`.
- Unity not ready: run `ensure-ready --open-editor` before validation tools.
- Package changes not visible: prefer reopening Unity so it resolves the
  manifest from a clean startup; use `unity_project_refresh` for an already
  healthy bridge.
- Test operations unavailable: run `validate-setup --include-tests`; if the
  Test Framework capability is missing, install it explicitly with the host
  `install-test-framework --yes` helper before opening Unity. Use the MCP tool
  `unity_package_install_test_framework` with `approve: true` only when the
  bridge is already healthy and an in-editor Package Manager mutation is
  intentional.
  If Test Framework is already declared but too old, the same command upgrades
  only that dependency after approval. If Unity 6000 already has `1.1.33`,
  tests may run, but setup reports an optional upgrade recommendation to
  `1.5.1`.
- Batchmode unavailable: run
  `license-capabilities --project-root <project> --refresh --timeout-ms 30000`.
  Batch helpers default to `--batch-fallback-mode auto`: if batchmode is blocked
  by a known license/Hub/headless condition and GUI fallback is viable, the MCP
  runs the equivalent GUI lane and reports `effective_execution_lane=gui`.
  Use `--batch-fallback-mode require-batch` when a CI or release lane must fail
  unless real Unity batchmode is proven.
- Long operation timed out: recover with `request-final-status`.
- Closed-project batch refused because the editor is open: run
  `request-editor-quit --project-root <project> --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000`,
  then `verify-editor-closed --project-root <project> --timeout-ms 30000`.
  If live PIDs remain, close or terminate the editor explicitly, verify again,
  then rerun the batch helper.
- `process_visibility_restricted`: run from a host context that can list local
  processes. Closed-editor batch lanes need process visibility to prove
  `same_project_editor_closed=true`.

Safety defaults: local same-host MCP server, editor-only package, disabled by
default, explicit per-project enablement, no runtime/player automation in the
base package, no dynamic Roslyn execution path, and no SignalR or external relay
stack.

</details>

## Opening A Useful Issue

If MCP install or first setup failed, ask your agent to run the public
[install retro prompt](docs/archive/retros/INSTALL_RETRO_PROMPT.md) before
opening an issue. For runtime, lifecycle, or automation failures after setup,
use the public [chat retro prompt](docs/archive/retros/CHAT_RETRO_PROMPT.md).
Paste the sanitized summary into the GitHub issue so maintainers can see what
was tried, what failed, command outputs, Unity version, package version, client
name, project topology, and the smallest reproduction steps.

```text
Use the XUUnity Light Unity MCP install retro prompt to summarize this setup
failure for a public GitHub issue. Remove secrets, private project details, and
unrelated logs.
```

## Documentation

[Install](INSTALL.md) | [Features](docs/reference/FEATURES.md) | [AI integration](docs/agents/AI_INTEGRATION.md) |
[Agent workflows](docs/agents/AGENT_WORKFLOWS.md) | [Workflow templates](templates/workflows/) |
[Security](SECURITY.md) | [Comparison](docs/reference/COMPARISON.md) | [Discovery](docs/reference/DISCOVERY.md) |
[Glossary](docs/reference/GLOSSARY.md) | [Status](docs/reference/STATUS.md) | [Build automation](docs/operations/BUILD_AUTOMATION.md) |
[Smoke tests](docs/operations/SMOKE_TESTS.md) | [Roadmap](docs/architecture/ROADMAP.md)

License: MIT. See [LICENSE](LICENSE). Need help? Open an [issue](https://github.com/FoxsterDev/xuunity-light-unity-mcp/issues).
