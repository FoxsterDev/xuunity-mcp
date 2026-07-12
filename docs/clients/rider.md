# Rider Setup

JetBrains Rider 2025.3+ includes built-in Claude AI Assistant with MCP support. XUUnity Light Unity MCP can be used with Rider, but requires specific configuration due to how Rider handles MCP servers.

## Prerequisites

- JetBrains Rider 2025.3 or newer
- Claude AI Assistant enabled in Rider settings
- Unity 2021.3 LTS+ project

## Known Limitations

**Important**: Rider's Claude AI Assistant currently has limitations when working with multiple MCP servers through `.mcp.json`:

- Rider reads `.mcp.json` but may replace its contents with the built-in JetBrains MCP server configuration
- The AI Assistant may not automatically load custom MCP servers from `.mcp.json` without manual intervention
- Current workaround: Use Codex-style configuration or direct Python script invocation

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

Enable the bridge for your Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## Configuration Method 1: Project Scope (Rider 2025.3+)

Create or update `.mcp.json` in your project root with **both** JetBrains and xuunity_light_unity servers:

```json
{
  "mcpServers": {
    "jetbrains": {
      "type": "stdio"
    },
    "xuunity_light_unity": {
      "type": "stdio",
      "command": "/bin/bash",
      "args": [
        "-c",
        "exec \"/bin/bash\" \"${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""
      ],
      "timeout": 600000
    }
  }
}
```

**Important**: Include the `jetbrains` entry, otherwise Rider will overwrite the config with its own MCP server.

### After Configuration:

1. **Restart Rider completely** (Quit and reopen)
2. Reopen your project
3. The AI Assistant should load both MCP servers

If the xuunity_light_unity MCP doesn't appear after restart, try the workaround below.

## Configuration Method 2: Codex-Style (Recommended Alternative)

If Method 1 doesn't work, use Codex-style configuration which Rider handles more reliably:

```bash
bash init_xuunity_light_unity_mcp.sh --install-codex-config
```

This adds the MCP server to `~/.codex/mcp-config.toml`:

```toml
[mcp_servers.xuunity_light_unity]
command = "/bin/bash"
args = ["-c", "exec \"/bin/bash\" \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""]
required = false
```

Restart Rider after adding this configuration.

## Workaround: Direct Script Invocation

If MCP integration doesn't work through Rider's AI Assistant, you can still use xuunity_light_unity_mcp functionality by asking the AI to invoke Python scripts directly:

```bash
# Check Unity project health
python3 ~/.claude-tools/xuunity-mcp/server.py request-status-summary \
  --project-root /path/to/UnityProject

# Run EditMode tests (batch mode, requires Unity license)
python3 ~/.claude-tools/xuunity-mcp/server.py batch-editmode-tests \
  --project-root /path/to/UnityProject

# Compile player scripts
python3 ~/.claude-tools/xuunity-mcp/server.py request-compile \
  --project-root /path/to/UnityProject
```

Example prompt for Rider's AI Assistant:

```
Use Python to check Unity project health by running:
python3 ~/.claude-tools/xuunity-mcp/server.py request-status-summary --project-root /path/to/UnityProject
```

This workaround provides full functionality while Rider's native MCP support is being improved.

## Verify

Check if the MCP server is available:

1. Open Rider AI Assistant
2. Try asking: "Check Unity project health"
3. If the AI Assistant can access xuunity_light_unity MCP tools, configuration is successful

If not working, verify:

```bash
# Check server installation
ls -la ~/.claude-tools/xuunity-mcp/

# Test server directly
python3 ~/.claude-tools/xuunity-mcp/server.py --help
```

## Rider-Specific Notes

### Claude AI Assistant Model Information

Rider 2025.3 includes Claude AI Assistant powered by Anthropic models. As of the current version:

- **Default Model**: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
- **Alternative Models**: Claude Opus 4, Claude Haiku 4.5
- **Context Window**: Up to 200K tokens
- **MCP Support**: Built-in, but may require configuration tweaks for custom servers

The AI Assistant in Rider is the same Claude agent used in Claude Code, but accessed through JetBrains' IDE integration layer.

### Unity License Requirements

When using batch-mode operations (tests, compilation) through xuunity_light_unity_mcp:

- Unity Personal/Plus license: Batch mode requires activation
- Unity Pro/Enterprise: Full batch-mode support
- Alternative: Use interactive Unity Editor with live bridge (no batch-mode license required)

### Multi-Project Workspaces

For workspaces with multiple Unity projects (like AIFoxsterDevHub):

1. The setup wizard can discover all Unity projects in the workspace
2. Review the plan before mutation
3. Apply setup only to explicit `--project-root` values chosen from the plan
4. Specify `--project-root` when invoking MCP tools to target a specific project

Example:

```bash
# Generate setup plan for all projects
python3 ~/.claude-tools/xuunity-mcp/server.py setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > setup-plan.json

# Apply setup only to the reviewed target project
python3 ~/.claude-tools/xuunity-mcp/server.py setup-apply \
  --plan-file setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes
```

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Rider/Claude config, or
helper files. For direct script invocation:

```bash
python3 ~/.claude-tools/xuunity-mcp/server.py uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > uninstall-plan.json
```

Review the plan in the AI Assistant, then run:

```bash
python3 ~/.claude-tools/xuunity-mcp/server.py uninstall-apply \
  --plan-file uninstall-plan.json \
  --yes
```

Project-only mode removes only project-level MCP setup. For a current-user reset,
use `--mode full-reset-current-user --client claude_code` for Claude-side
helper/config cleanup or `--client codex` for the Codex-style workaround. Full
reset removes only the selected `xuunity_light_unity` server block and selected
helper install by default.

## Troubleshooting

### MCP Server Not Available

If Rider's AI Assistant doesn't see xuunity_light_unity MCP tools:

1. Check `.mcp.json` includes both `jetbrains` and `xuunity_light_unity` entries
2. Restart Rider completely (not just reload project)
3. Try Codex-style configuration as alternative
4. Use direct Python script invocation as workaround

### Unity Bridge Offline

If Unity bridge shows as offline:

```bash
# Open Unity Editor and ensure bridge ready
python3 ~/.claude-tools/xuunity-mcp/server.py ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor
```

Bridge requires Unity Editor to be running. For batch operations, Unity Editor must be closed.

### Compilation Errors Block Bridge

If Unity project has compilation errors, the MCP bridge cannot initialize:

1. Fix compilation errors in Unity first
2. Or use batch-mode operations which work independently:

```bash
python3 ~/.claude-tools/xuunity-mcp/server.py batch-compile \
  --project-root /path/to/UnityProject
```

## See Also

- [INSTALL.md](../../INSTALL.md) - Full installation guide
- [Codex Client Setup](codex.md) - Alternative configuration approach
- [Claude Code Setup](claude-code.md) - For comparison with standalone Claude Code
- [AI Integration Guide](../agents/AI_INTEGRATION.md) - Advanced AI agent workflows
