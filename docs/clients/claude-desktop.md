# Claude Desktop Setup

Claude Desktop uses its own MCP configuration. Claude Code `.mcp.json` files do
not apply to the Desktop chat app.

## Install The Server

Install the Claude-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

## macOS Config

Claude Desktop reads:

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

Production config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
      "type": "stdio",
      "command": "bash",
      "args": [
        "-lc",
        "exec \"${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""
      ]
    }
  }
}
```

Install it:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
cp templates/clients/claude-desktop/claude_desktop_config.json \
  "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

## Windows Config

Claude Desktop reads:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Production config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
      "type": "stdio",
      "command": "cmd.exe",
      "args": [
        "/d",
        "/c",
        "if defined CLAUDE_TOOLS_HOME (call \"%CLAUDE_TOOLS_HOME%\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd\") else (call \"%USERPROFILE%\\.claude-tools\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd\")"
      ]
    }
  }
}
```

Install it:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\Claude" | Out-Null
Copy-Item templates\clients\claude-desktop\claude_desktop_config.windows.json `
  "$env:APPDATA\Claude\claude_desktop_config.json"
```

If the file already contains other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

Restart Claude Desktop after editing the config.

## Verify

Open Claude Desktop settings, check the Developer or Connectors view, and
confirm that `xuunity_light_unity` is connected. Then ask Claude to run:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Claude Desktop config, or
helper files.

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Project-only mode removes only project-level MCP setup and keeps Claude Desktop
config plus the Claude helper install.

For a current-user Claude Desktop reset:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client claude_desktop \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Review the plan, then run `uninstall-apply --plan-file ... --yes` only after
explicit approval. Full reset removes only
`mcpServers.xuunity_light_unity` from the selected Claude Desktop config and
the selected helper install by default. Restart Claude Desktop afterward.
