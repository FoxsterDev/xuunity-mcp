# Cursor Setup

Use XUUnity Light Unity MCP with Cursor when you want a local AI agent to validate Unity projects through MCP.

Cursor uses `.cursor/mcp.json` for project-scoped MCP servers and
`~/.cursor/mcp.json` for user-global MCP servers.

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

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
        "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp/run.sh\""
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
        "if defined CODEX_TOOLS_HOME (call \"%CODEX_TOOLS_HOME%\\xuunity-mcp\\run.cmd\") else (call \"%USERPROFILE%\\.codex-tools\\xuunity-mcp\\run.cmd\")"
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

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Cursor config, or helper
files.

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Project-only mode removes only project-level MCP setup and keeps `.cursor/mcp.json`,
`~/.cursor/mcp.json`, and the helper install.

For a current-user Cursor reset:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client cursor \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Review the plan, then run `uninstall-apply --plan-file ... --yes` only after
explicit approval. Full reset removes only the selected current-user
`mcpServers.xuunity_light_unity` block and selected helper install by default.
Remove project-scoped `.cursor/mcp.json` entries only with an explicit
project-approved edit.
