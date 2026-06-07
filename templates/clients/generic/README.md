# Generic MCP Client Adapter

Status: `active`.

Use this adapter for MCP-compatible clients that can launch a local stdio
command and accept a JSON `mcpServers` object.

## Config Shape

Use `templates/clients/generic/stdio-mcp.json` as the Linux/macOS starting
point.

Use `templates/clients/generic/stdio-mcp.windows.json` for native Windows
clients.

Important:

- Reuse an existing local helper install if it is already present.
- Merge only the `mcpServers.xuunity_light_unity` block when the destination
  config already contains other MCP servers.
- Refresh or restart the client after wiring if the current session does not
  hot-reload new MCP servers.
- Client wiring does not prove Unity project readiness. Validate the target
  Unity project separately after wiring.

The command intentionally goes through `bash -lc` so `$HOME` and optional
tool-home overrides are resolved by the shell instead of relying on client-side
tilde expansion.

The Windows command intentionally goes through `cmd.exe /d /c` and calls
`run.cmd` so `%USERPROFILE%`, `CODEX_TOOLS_HOME`, and Python launcher fallback
behavior are resolved by Windows instead of the MCP client.

## Install The Server

Install the host-side server into the default Codex-compatible tools location:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Clients that should use the Claude-side install can change `CODEX_TOOLS_HOME`
to `CLAUDE_TOOLS_HOME` and `.codex-tools` to `.claude-tools`.

Direct wrapper invocations also honor
`XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex|claude|auto`. In `auto`, Codex
contexts prefer `.codex-tools`; non-Codex sessions with an existing Claude
helper keep using `.claude-tools`.

After wiring, treat `unity_status_summary` as the canonical first live
smoke-check. If it is healthy but a later compile or test run fails, treat that
as a Unity project or runtime failure unless the error explicitly points back
to MCP setup or unsupported capability.
