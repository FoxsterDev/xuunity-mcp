# Generic MCP Client Adapter

Status: `active`.

Use this adapter for MCP-compatible clients that can launch a local stdio
command and accept a JSON `mcpServers` object.

## Config Shape

Use `templates/clients/generic/stdio-mcp.json` as the starting point.

The command intentionally goes through `bash -lc` so `$HOME` and optional
tool-home overrides are resolved by the shell instead of relying on client-side
tilde expansion.

## Install The Server

Install the host-side server into the default Codex-compatible tools location:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Clients that should use the Claude-side install can change `CODEX_TOOLS_HOME`
to `CLAUDE_TOOLS_HOME` and `.codex-tools` to `.claude-tools`.
