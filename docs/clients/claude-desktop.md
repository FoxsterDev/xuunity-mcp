# Claude Desktop Setup

Claude Desktop uses its own MCP configuration. Claude Code `.mcp.json` files do
not apply to the Desktop chat app.

## Install The Server

Install the Claude-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

Enable the bridge for the Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

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
        "exec \"${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-light-unity-mcp/run.sh\""
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

If the file already contains other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

Restart Claude Desktop after editing the config.

## Verify

Open Claude Desktop settings, check the Developer or Connectors view, and
confirm that `xuunity_light_unity` is connected. Then ask Claude to run:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`
