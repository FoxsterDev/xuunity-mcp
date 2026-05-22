# Cursor Setup

Use XUUnity Light Unity MCP with Cursor when you want a local AI agent to validate Unity projects through MCP.

Cursor uses `.cursor/mcp.json` for project-scoped MCP servers and
`~/.cursor/mcp.json` for user-global MCP servers.

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Enable the bridge for the Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## Project Config

Create `.cursor/mcp.json` on Linux/macOS:

```bash
mkdir -p .cursor
cp templates/clients/cursor/mcp.json .cursor/mcp.json
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
        "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""
      ]
    }
  }
}
```

For native Windows Cursor, use:

```powershell
New-Item -ItemType Directory -Force .cursor | Out-Null
Copy-Item templates\clients\cursor\mcp.windows.json .cursor\mcp.json
```

Windows config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
      "type": "stdio",
      "command": "cmd.exe",
      "args": [
        "/d",
        "/c",
        "if defined CODEX_TOOLS_HOME (call \"%CODEX_TOOLS_HOME%\\xuunity-light-unity-mcp\\run.cmd\") else (call \"%USERPROFILE%\\.codex-tools\\xuunity-light-unity-mcp\\run.cmd\")"
      ]
    }
  }
}
```

## User Config

For one user across projects:

```bash
mkdir -p ~/.cursor
cp templates/clients/cursor/mcp.json ~/.cursor/mcp.json
```

Native Windows user config:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor" | Out-Null
Copy-Item templates\clients\cursor\mcp.windows.json "$env:USERPROFILE\.cursor\mcp.json"
```

If the target config already has other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

## Verify

```bash
cursor-agent mcp list
cursor-agent mcp list-tools xuunity_light_unity
```

Inside Cursor, confirm the server is connected in MCP settings. Then run
`unity.status`, `unity.capabilities.get`, and `unity.health.probe`.
