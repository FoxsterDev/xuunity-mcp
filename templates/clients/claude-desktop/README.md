# Claude Desktop Client Adapter

Status: `active` for macOS local stdio configuration.

Claude Desktop uses a separate MCP configuration from Claude Code. A Claude
Code `.mcp.json` file does not register tools in the Desktop chat app.

Important:

- Reuse an existing helper install under `${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}`
  if it already exists.
- Merge only the `mcpServers.xuunity_light_unity` block if the target Desktop
  config already has other MCP servers.
- Restart Claude Desktop after changing the config unless the app clearly
  refreshes MCP servers on its own.
- Client wiring does not prove Unity project readiness. Validate the project
  separately after wiring.

## Install The Server

Install the host-side server into the default Claude tools location:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

Then enable the Unity bridge for the project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## macOS Config

Claude Desktop reads this file on macOS:

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

Install the production config:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
cp templates/clients/claude-desktop/claude_desktop_config.json \
  "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

If you already have other MCP servers, merge the
`mcpServers.xuunity_light_unity` block instead of replacing the file.

Restart Claude Desktop after changing the config.

## Windows Config

Claude Desktop reads this file on Windows:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Install the production config:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\Claude" | Out-Null
Copy-Item templates\clients\claude-desktop\claude_desktop_config.windows.json `
  "$env:APPDATA\Claude\claude_desktop_config.json"
```

Restart Claude Desktop after changing the config.

## Verify

Open Claude Desktop settings, check the Developer or Connectors view, and
confirm that `xuunity_light_unity` is connected before asking Claude to run
Unity validation tools.

Treat `unity_status_summary` as the canonical first live smoke-check after
setup. If it is healthy but a later compile or test run fails, treat that as a
Unity project or runtime failure unless the error explicitly points back to MCP
setup or unsupported capability.

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Claude Desktop config, or
helper files.

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Project-only mode keeps Claude Desktop config and the helper install. For a
current-user reset, use `--mode full-reset-current-user --client
claude_desktop`, review the exact config/helper removals, then run
`uninstall-apply --plan-file ... --yes` only after explicit approval. Remove
only `mcpServers.xuunity_light_unity`; do not delete whole config files or
unrelated MCP servers.
