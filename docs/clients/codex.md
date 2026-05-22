# Codex-Style Agent Setup

Use the Codex-style config when the client reads MCP servers from
`~/.codex/config.toml`.

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

## Automatic User Config

The installer can append the MCP block:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target codex \
  --install-codex-config
```

## Manual Config

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

This avoids relying on client-side `~` expansion. The shell resolves `$HOME`
and optional `CODEX_TOOLS_HOME`.

## Verify

Start the client and confirm that `xuunity_light_unity` appears in the MCP
server list. Then run:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`
4. `unity.console.tail`
