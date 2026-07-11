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
        "exec \"${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""
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
        "call",
        "C:\\Users\\<YOUR_USERNAME>\\.claude-tools\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd"
      ],
      "timeout": 600000
    }
  }
}
```

Replace `<YOUR_USERNAME>` with your Windows user name (or run
`bash init_xuunity_light_unity_mcp.sh --install-claude-config`, which writes
the resolved path for you). Keep every `args` entry free of embedded quotes
and parentheses: MCP clients quote argv with the C-runtime rules, which
escape embedded quotes as `\"` — cmd.exe misparses that and the server never
starts.

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
  -- bash -lc 'exec "${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh"'
```

Native Windows equivalent:

```powershell
claude mcp add --scope local --transport stdio xuunity_light_unity -- cmd.exe /d /c call "C:\Users\<YOUR_USERNAME>\.claude-tools\xuunity-mcp\run_installed_or_refresh_xuunity_mcp.cmd"
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

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Claude config, or helper
files.

Project-only cleanup:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Review the plan in chat, then run `uninstall-apply --plan-file ... --yes` only
after explicit approval. Project-only mode keeps `.mcp.json`, `~/.claude.json`, and
`${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp`.

Full current-user reset for Claude Code:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client claude_code \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Full reset removes only the selected current-user
`mcpServers.xuunity_light_unity` block and the selected Claude helper install
by default. Remove project-scoped `.mcp.json` entries manually or with a
project-approved edit; do not delete unrelated MCP servers.
