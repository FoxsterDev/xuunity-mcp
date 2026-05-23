<div align="center">

<img src="docs/assets/xuunity-light-unity-mcp-preview.png" alt="XUUnity Light Unity MCP preview banner" width="100%">

<br>

# XUUnity Light Unity MCP

**Open-source lightweight Unity MCP server for safe Unity Editor automation.**

Connect Cursor, Claude Code, Claude Desktop, Windsurf, Codex-style agents, and
custom MCP clients to Unity through a local stdio MCP server and a small
editor-only Unity package.

<p>
  <a href="https://github.com/FoxsterDev/xuunity-light-unity-mcp"><img alt="GitHub stars" src="https://img.shields.io/github/stars/FoxsterDev/xuunity-light-unity-mcp?style=flat&logo=github"></a>
  <a href="LICENSE"><img alt="License MIT" src="https://img.shields.io/badge/license-MIT-red.svg"></a>
  <img alt="Unity 2021.3+" src="https://img.shields.io/badge/Unity-2021.3%2B-black.svg?logo=unity&logoColor=white">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white">
  <img alt="MCP enabled" src="https://img.shields.io/badge/MCP-enabled-green.svg">
  <img alt="Git UPM ready" src="https://img.shields.io/badge/Git%20UPM-ready-brightgreen.svg">
  <img alt="OpenUPM planned" src="https://img.shields.io/badge/OpenUPM-planned-lightgrey.svg">
</p>

[Quick Start](#quick-start) |
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

### Prerequisites

- Unity 2021.3 LTS+; the current release has live validation on Unity 2021.3,
  2022.3, and 6000.x. See [Status](docs/reference/STATUS.md).
- Python 3.10+
- one MCP client: [Claude Code](docs/clients/claude-code.md), [Claude Desktop](docs/clients/claude-desktop.md), [Cursor](docs/clients/cursor.md), [Windsurf](docs/clients/windsurf.md), or a [Codex-style agent](docs/clients/codex.md)

### Guided Setup Wizard

For single projects, flat hubs, mixed-version hubs, or nested repositories, ask
the host helper to produce an explicit per-project plan before mutating files:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > xuunity-setup-plan.json

bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file xuunity-setup-plan.json \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
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

### AI Agent Setup Prompt

Copy this prompt into your coding agent from the Unity project you want to
connect. Replace the placeholders before running it.

```text
Configure XUUnity Light Unity MCP for this Unity project.

Inputs:
- Unity project root: <absolute path to the Unity project>
- Workspace/repository root: <absolute path to workspace; may equal project root>
- MCP client: <Claude Code | Claude Desktop | Cursor | Windsurf | Codex | custom stdio MCP client>
- Package mode: Git UPM release v0.3.14, unless this is local MCP development.
- Test operations: optional. Install Test Framework only after explicit approval.

Principles:
- Read the current README.md, INSTALL.md, and the matching docs/clients/*
  guide before editing files.
- Preserve existing user config. Merge the xuunity_light_unity MCP server block;
  do not overwrite unrelated MCP servers, editor settings, or package entries.
- Keep the Unity package editor-only. Do not add runtime/player dependencies.
- Do not add com.unity.test-framework as a hard dependency of the MCP package.
  Test features are optional capabilities gated by Version Defines.
- Use the native template for the host OS: run.sh for macOS/Linux clients,
  run.cmd or run.ps1 for native Windows clients.
- If the MCP repo is missing locally, clone
  https://github.com/FoxsterDev/xuunity-light-unity-mcp.git outside the Unity
  Assets folder and treat that clone as <MCP_REPO_ROOT>.
- Ask before destructive git operations, deleting user files, force-pushing,
  killing unrelated Unity Editor sessions, or changing production package pins.

Tasks:
1. Confirm Python 3.10+, Unity project structure, selected MCP client, and
   whether the workspace contains one project, a flat hub, mixed Unity versions,
   or nested repositories.
2. From <MCP_REPO_ROOT>, run the host installer
   through macOS/Linux shell, Git Bash, or WSL:
   bash init_xuunity_light_unity_mcp.sh
3. Produce and review a setup plan:
   bash xuunity_light_unity_mcp.sh setup-plan --workspace-root "<WORKSPACE_ROOT>" --project-root "<UNITY_PROJECT_ROOT>" --recursive > xuunity-setup-plan.json
4. Apply the plan only after user approval:
   bash xuunity_light_unity_mcp.sh setup-apply --plan-file xuunity-setup-plan.json --yes
5. If test operations are required and the plan reports
   disabled_missing_dependency, ask for approval before opening Unity, then run:
   bash xuunity_light_unity_mcp.sh install-test-framework --project-root "<UNITY_PROJECT_ROOT>" --yes
   If the project already has Test Framework but the version is too old, treat
   the same command as an approved package upgrade and review Unity's package
   resolve/compile result afterward.
6. Wire the selected MCP client using the files under templates/clients/.
   Merge config if the target file already exists.
7. Open or restart the Unity project if needed, then verify readiness with:
   bash xuunity_light_unity_mcp.sh ensure-ready --project-root "<UNITY_PROJECT_ROOT>" --open-editor
   bash xuunity_light_unity_mcp.sh request-status-summary --project-root "<UNITY_PROJECT_ROOT>"
   bash xuunity_light_unity_mcp.sh validate-setup --project-root "<UNITY_PROJECT_ROOT>"
   Use --include-tests only when test operations are expected.
8. If your agent runtime can reload MCP tools, verify the MCP tools
   xuunity_setup_validate, unity_status_summary, unity_capabilities, and
   unity_health_probe. If it cannot reload tools in-process, provide the exact
   restart steps for the user.
9. Finish with a concise report listing files changed, commands run, verification
   results, and any manual restart still required.
```

### 1. Install The Unity Package

In Unity: `Window > Package Manager > + > Add package from git URL...`

> Tip
>
> ```text
> https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14
> ```

Or add it directly to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14"
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

### 4. Verify Connection

```bash
bash xuunity_light_unity_mcp.sh ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor

bash xuunity_light_unity_mcp.sh request-status-summary \
  --project-root /path/to/UnityProject
```

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
- [Windsurf](docs/clients/windsurf.md)
- [Codex-style agents](docs/clients/codex.md)
- custom stdio MCP clients

Manual macOS/Linux and Windows configs live in `templates/clients/`.

<details>
<summary><strong>Features And Tools</strong></summary>

Popular MCP tools:

`xuunity_setup_plan` | `xuunity_setup_apply` | `xuunity_setup_validate` |
`unity_status_summary` | `unity_capabilities` | `unity_health_probe` |
`unity_console_tail` | `unity_scene_snapshot` | `unity_scene_assert` |
`unity_compile_player_scripts` | `unity_compile_matrix` |
`unity_compile_build_config_matrix` | `unity_tests_run_editmode` |
`unity_tests_run_playmode` | `unity_playmode_state` | `unity_playmode_set` |
`unity_game_view_configure` | `unity_game_view_screenshot` |
`unity_scenario_validate` | `unity_scenario_run_and_wait` |
`unity_request_final_status` | `unity_project_refresh` |
`unity_package_install_test_framework` | `unity_edm4u_resolve` |
`unity_sdk_dependency_verify`

Host helper commands include `setup-plan`, `setup-apply`, `validate-setup`,
`install-test-framework`, `ensure-ready`, `verify-editor-closed`,
`request-editor-quit --wait-for-exit`, `restore-editor-state`,
`recover-editor-session`, `batch-compile`, `batch-editmode-tests`,
`batch-build-config-compile-matrix`, `artifact-probe`, `devmode`, and `prodmode`.

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
