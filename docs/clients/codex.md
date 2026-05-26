# Codex-Style Agent Setup

Use the Codex-style config when the client reads MCP servers from
`~/.codex/config.toml`.

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

When the wrapper runs from a Codex-style environment, its default `auto`
install target prefers `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}` even if a
Claude-side helper also exists. To make that explicit in scripts, set:

```bash
export XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex
```

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

## Automatic User Config

The installer can append the MCP block:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target codex \
  --install-codex-config
```

## Manual Config

Add this to `~/.codex/config.toml` on Linux/macOS:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

This avoids relying on client-side `~` expansion. The shell resolves `$HOME`
and optional `CODEX_TOOLS_HOME`.

For native Windows, add this to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.xuunity_light_unity]
command = "cmd.exe"
args = ['/d', '/c', 'if defined CODEX_TOOLS_HOME (call "%CODEX_TOOLS_HOME%\xuunity-light-unity-mcp\run.cmd") else (call "%USERPROFILE%\.codex-tools\xuunity-light-unity-mcp\run.cmd")']
required = false
```

The Windows config uses `run.cmd`, which resolves `server.py` beside itself and
prefers `PYTHON`, then `py -3`, then `python`, then `python3`.

## Verify

Start the client and confirm that `xuunity_light_unity` appears in the MCP
server list. Then run:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`
4. `unity.console.tail`
