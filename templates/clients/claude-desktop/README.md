# Claude Desktop Client Adapter

Status: `active` for macOS local stdio configuration.

Claude Desktop uses a separate MCP configuration from Claude Code. A Claude
Code `.mcp.json` file does not register tools in the Desktop chat app.

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
