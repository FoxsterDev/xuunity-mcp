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

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

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

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Windsurf config, or helper
files.

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Project-only mode removes only project-level MCP setup and keeps
`~/.codeium/windsurf/mcp_config.json` plus the helper install.

For a current-user Windsurf reset:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client windsurf \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Review the plan, then run `uninstall-apply --plan-file ... --yes` only after
explicit approval. Full reset removes only
`mcpServers.xuunity_light_unity` from the selected Windsurf config and the
selected helper install by default. Refresh Windsurf's MCP panel afterward.
