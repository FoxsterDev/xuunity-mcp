# Install XUUnity Light Unity MCP

XUUnity Light Unity MCP has two pieces:

1. a host-side MCP server
2. an editor-only Unity package

Install both before expecting an AI client to control Unity.

## Option 1: Git UPM Package

Add this dependency to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/templates/unity-package#v0.3.11"
  }
}
```

## Option 2: Local File Package

For active local development, reference the package folder directly:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-light-unity-mcp/templates/unity-package"
  }
}
```

## Initialize Host MCP Server

From the repository root:

```bash
bash init_xuunity_light_unity_mcp.sh
```

To enable a Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## Connect Codex-Style Agents

The installer can append a Codex MCP config block:

```bash
bash init_xuunity_light_unity_mcp.sh --install-codex-config
```

Template:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

## Connect Claude Code

The installer can register the MCP server in the Claude Code user config:

```bash
bash init_xuunity_light_unity_mcp.sh --install-claude-config
```

Project-scoped Claude Code config:

```bash
cp templates/clients/claude-code/.mcp.json .mcp.json
```

## Connect Cursor

```bash
mkdir -p .cursor
cp templates/clients/cursor/mcp.json .cursor/mcp.json
```

For user-global Cursor config, copy the same file to `~/.cursor/mcp.json`.

## Connect Windsurf

```bash
mkdir -p ~/.codeium/windsurf
cp templates/clients/windsurf/mcp_config.json ~/.codeium/windsurf/mcp_config.json
```

## Connect Claude Desktop

On macOS:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
cp templates/clients/claude-desktop/claude_desktop_config.json \
  "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

If a target config already has other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

## Verify Installation

After package import and bridge enablement:

1. open the Unity project
2. confirm the package appears in Package Manager
3. confirm the bridge state appears under `Library/XUUnityLightMcp/`
4. call `unity.status`
5. call `unity.capabilities.get`
6. call `unity.health.probe`

Do not treat the install as ready until status, capabilities, and health probe all succeed.

## Troubleshooting

- If the bridge is disabled, run the init script with `--enable-project`.
- If the AI client cannot find the server, verify the configured `run.sh` path.
- If Unity imported the package but MCP calls fail, check `Library/XUUnityLightMcp/` for bridge state and request artifacts.
- If a Unity project is already open, prefer reusing the healthy editor session instead of starting a competing one.
