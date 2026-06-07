# Windsurf Client Adapter

Status: `active`.

Windsurf Cascade reads MCP servers from
`~/.codeium/windsurf/mcp_config.json`.

Important:

- Reuse an existing local helper install if it is already present.
- Merge only the `mcpServers.xuunity_light_unity` block when the destination
  file already contains other MCP servers.
- Refresh Windsurf's MCP panel after changing the config if the current session
  does not auto-detect the update.
- Client wiring does not prove Unity project readiness. Validate the project
  separately after wiring.

## Install The Server

Install the host-side server into the default Codex-compatible tools location:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

Then enable the Unity bridge for the project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

## User Config

Install the production config on Linux/macOS:

```bash
mkdir -p ~/.codeium/windsurf
cp templates/clients/windsurf/mcp_config.json ~/.codeium/windsurf/mcp_config.json
```

Native Windows:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codeium\windsurf" | Out-Null
Copy-Item templates\clients\windsurf\mcp_config.windows.json "$env:USERPROFILE\.codeium\windsurf\mcp_config.json"
```

If you already have other MCP servers, merge the
`mcpServers.xuunity_light_unity` block instead of replacing the file.

## Verify

Open Cascade, open the MCP panel, and confirm that `xuunity_light_unity` is
connected before asking the agent to run Unity validation tools.

Treat `unity_status_summary` as the canonical first live smoke-check after
setup. If it is healthy but a later compile or test run fails, treat that as a
Unity project or runtime failure unless the error explicitly points back to MCP
setup or unsupported capability.
