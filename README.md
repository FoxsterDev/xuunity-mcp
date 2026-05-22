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

- Unity 2021.3 LTS+; Unity 6000 is the main validated production path
- Python 3.10+
- one MCP client: [Claude Code](docs/clients/claude-code.md), [Claude Desktop](docs/clients/claude-desktop.md), [Cursor](docs/clients/cursor.md), [Windsurf](docs/clients/windsurf.md), or a [Codex-style agent](docs/clients/codex.md)

### AI Agent Setup Prompt

Copy this prompt into your coding agent from the Unity project you want to
connect. Replace the placeholders before running it.

```text
Configure XUUnity Light Unity MCP for this Unity project.

Inputs:
- Unity project root: <absolute path to the Unity project>
- MCP client: <Claude Code | Claude Desktop | Cursor | Windsurf | Codex | custom stdio MCP client>
- Package mode: Git UPM release v0.3.12, unless this is local MCP development.

Principles:
- Read the current README.md, INSTALL.md, and the matching docs/clients/*
  guide before editing files.
- Preserve existing user config. Merge the xuunity_light_unity MCP server block;
  do not overwrite unrelated MCP servers, editor settings, or package entries.
- Keep the Unity package editor-only. Do not add runtime/player dependencies.
- Use the native template for the host OS: run.sh for macOS/Linux clients,
  run.cmd or run.ps1 for native Windows clients.
- If the MCP repo is missing locally, clone
  https://github.com/FoxsterDev/xuunity-light-unity-mcp.git outside the Unity
  Assets folder and treat that clone as <MCP_REPO_ROOT>.
- Ask before destructive git operations, deleting user files, force-pushing,
  killing unrelated Unity Editor sessions, or changing production package pins.

Tasks:
1. Confirm Python 3.10+, Unity project structure, and selected MCP client.
2. Add the Unity package dependency:
   https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12
3. From <MCP_REPO_ROOT>, run the host installer and enable the project bridge
   through macOS/Linux shell, Git Bash, or WSL:
   bash init_xuunity_light_unity_mcp.sh
   bash init_xuunity_light_unity_mcp.sh --project-root "<UNITY_PROJECT_ROOT>" --enable-project
4. Wire the selected MCP client using the files under templates/clients/.
   Merge config if the target file already exists.
5. Open or restart the Unity project if needed, then verify readiness with:
   bash xuunity_light_unity_mcp.sh ensure-ready --project-root "<UNITY_PROJECT_ROOT>" --open-editor
   bash xuunity_light_unity_mcp.sh request-status-summary --project-root "<UNITY_PROJECT_ROOT>"
6. If your agent runtime can reload MCP tools, verify the MCP tools
   unity_status_summary, unity_capabilities, and unity_health_probe. If it
   cannot reload tools in-process, provide the exact restart steps for the user.
7. Finish with a concise report listing files changed, commands run, verification
   results, and any manual restart still required.
```

### 1. Install The Unity Package

In Unity: `Window > Package Manager > + > Add package from git URL...`

> Tip
>
> ```text
> https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12
> ```

Or add it directly to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12"
  }
}
```

Local package source for MCP development:
`file:/absolute/path/to/xuunity-light-unity-mcp/packages/com.xuunity.light-mcp`.
OpenUPM is planned; use Git UPM until the package is published there.

Migration note: `v0.3.11` used `templates/unity-package`. `v0.3.12+` uses
`packages/com.xuunity.light-mcp` so the package path is registry-native for
OpenUPM and Unity Package Manager indexing.

### 2. Install The Host MCP Helper

```bash
bash init_xuunity_light_unity_mcp.sh
```

Enable the bridge for one Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

The installer writes Unix and Windows launchers: `run.sh`, `run.cmd`, and
`run.ps1`.

### 3. Connect Your Client

Use a ready-made client template:

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

`unity_status_summary` | `unity_capabilities` | `unity_health_probe` |
`unity_console_tail` | `unity_scene_snapshot` | `unity_scene_assert` |
`unity_compile_player_scripts` | `unity_compile_matrix` |
`unity_compile_build_config_matrix` | `unity_tests_run_editmode` |
`unity_tests_run_playmode` | `unity_playmode_state` | `unity_playmode_set` |
`unity_game_view_configure` | `unity_game_view_screenshot` |
`unity_scenario_validate` | `unity_scenario_run_and_wait` |
`unity_request_final_status` | `unity_project_refresh` |
`unity_edm4u_resolve` | `unity_sdk_dependency_verify`

Host helper commands include `ensure-ready`, `restore-editor-state`,
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
- Package changes not visible: run `unity_project_refresh` or reopen Unity.
- Long operation timed out: recover with `request-final-status`.

Safety defaults: local same-host MCP server, editor-only package, disabled by
default, explicit per-project enablement, no runtime/player automation in the
base package, no dynamic Roslyn execution path, and no SignalR or external relay
stack.

</details>

## Documentation

[Install](INSTALL.md) | [Features](docs/reference/FEATURES.md) | [AI integration](docs/agents/AI_INTEGRATION.md) |
[Agent workflows](docs/agents/AGENT_WORKFLOWS.md) | [Workflow templates](templates/workflows/) |
[Security](SECURITY.md) | [Comparison](docs/reference/COMPARISON.md) | [Discovery](docs/reference/DISCOVERY.md) |
[Glossary](docs/reference/GLOSSARY.md) | [Status](docs/reference/STATUS.md) | [Build automation](docs/operations/BUILD_AUTOMATION.md) |
[Smoke tests](docs/operations/SMOKE_TESTS.md) | [Roadmap](docs/architecture/ROADMAP.md)

License: MIT. See [LICENSE](LICENSE). Need help? Open an [issue](https://github.com/FoxsterDev/xuunity-light-unity-mcp/issues).
