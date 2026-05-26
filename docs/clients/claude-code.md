# Claude Code Setup

Claude Code can use XUUnity Light Unity MCP through project scope, user scope,
or a local ad-hoc server entry. Prefer project scope for team repos.

## Install The Server

Install the Claude-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

The wrapper still supports Claude-first installs. Outside a Codex-style
environment, `auto` preserves an existing
`${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}` helper. To force the Claude-side
helper from any shell, set:

```bash
export XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=claude
```

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

## Project Scope

Use the Linux/macOS template when Claude Code runs in a Unix-like shell:

Copy the production project config into the repo root:

```bash
cp templates/clients/claude-code/.mcp.json .mcp.json
```

Config:

```json
{
  "mcpServers": {
    "xuunity_light_unity": {
      "type": "stdio",
      "command": "bash",
      "args": [
        "-lc",
        "exec \"${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-light-unity-mcp/run.sh\""
      ],
      "timeout": 600000
    }
  }
}
```

For native Windows Claude Code, use the Windows template:

```powershell
Copy-Item templates\clients\claude-code\.mcp.windows.json .mcp.json
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
        "if defined CLAUDE_TOOLS_HOME (call \"%CLAUDE_TOOLS_HOME%\\xuunity-light-unity-mcp\\run.cmd\") else (call \"%USERPROFILE%\\.claude-tools\\xuunity-light-unity-mcp\\run.cmd\")"
      ],
      "timeout": 600000
    }
  }
}
```

Claude Code asks each user to approve project-scoped MCP servers on first use.

## User Scope

For one user across all repos:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target claude \
  --install-claude-config
```

## Local CLI Scope

```bash
claude mcp add --scope local --transport stdio xuunity_light_unity \
  -- bash -lc 'exec "${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-light-unity-mcp/run.sh"'
```

Native Windows equivalent:

```powershell
claude mcp add --scope local --transport stdio xuunity_light_unity -- cmd.exe /d /c "if defined CLAUDE_TOOLS_HOME (call ""%CLAUDE_TOOLS_HOME%\xuunity-light-unity-mcp\run.cmd"") else (call ""%USERPROFILE%\.claude-tools\xuunity-light-unity-mcp\run.cmd"")"
```

## Verify

```bash
claude mcp list
```

Inside Claude Code, run `/mcp` and confirm that `xuunity_light_unity` is
connected. Then verify Unity with:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`

Do not run compile, tests, Play Mode, or screenshots until the health probe succeeds.
