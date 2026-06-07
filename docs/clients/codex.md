# Codex-Style Agent Setup

Use the Codex-style config when the client reads MCP servers from
`~/.codex/config.toml`.

When a short install request does not name a client explicitly, treat the
current host client that is executing the request as the default wiring target.
For prompts coming from Codex, wire Codex by default and show that assumption in
the preflight review before mutating files.

Optional: connect XUUnity MCP to Codex/Codex-style clients when you want Codex
to validate Unity status, compile, tests, and setup directly from the chat. Use
this only on trusted local projects. If you also use Rider or VS Code MCP,
avoid running concurrent commands against the same Unity project.

For Codex Desktop's custom MCP server UI, use the visual guide:
[Codex Unity MCP Setup](codex-unity-mcp-setup.md).

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

If the current Codex session does not hot-reload newly installed MCP servers,
restart the client after this change.

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
server list. Then ask the client to list the server tools:

```text
Use xuunity_light_unity MCP and list tools.
```

Then verify a concrete Unity project:

1. `unity_status_summary`
2. `unity_capabilities`
3. `unity_health_probe`
4. `unity_console_tail`

Treat `unity_status_summary` as the canonical first MCP smoke-check after
setup. Only move on to tests or builds after the status summary reports a
healthy bridge.

You can name the server explicitly while verifying setup. After that, natural
requests such as `Run EditMode tests in /path/to/UnityProject` are usually
enough as long as the Unity project path and desired operation are clear.
