# Windsurf Setup

Use XUUnity Light Unity MCP with Windsurf through a stdio MCP server entry.

Windsurf Cascade reads user MCP servers from:

```text
~/.codeium/windsurf/mcp_config.json
%USERPROFILE%\.codeium\windsurf\mcp_config.json
```

## Install The Server

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Enable the bridge for the Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## User Config

Install the production config on Linux/macOS:

```bash
mkdir -p ~/.codeium/windsurf
cp templates/clients/windsurf/mcp_config.json ~/.codeium/windsurf/mcp_config.json
```

Production config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
      "command": "bash",
      "args": [
        "-lc",
        "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""
      ]
    }
  }
}
```

For native Windows Windsurf, use:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codeium\windsurf" | Out-Null
Copy-Item templates\clients\windsurf\mcp_config.windows.json "$env:USERPROFILE\.codeium\windsurf\mcp_config.json"
```

Windows config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
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

If the file already contains other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

## Verify

Open Cascade's MCP panel and confirm that `xuunity_light_unity` is connected.
Then run:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`

Treat failures in those checks as setup issues before running validation workflows.
