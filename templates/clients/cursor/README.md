# Cursor Client Adapter

Status: `active`.

Cursor uses JSON MCP configuration files. Use the template in this folder as
either a project-scoped config or a user-global config.

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

## Project Scope

Copy the production config into the project:

```bash
mkdir -p .cursor
cp templates/clients/cursor/mcp.json .cursor/mcp.json
```

Native Windows:

```powershell
New-Item -ItemType Directory -Force .cursor | Out-Null
Copy-Item templates\clients\cursor\mcp.windows.json .cursor\mcp.json
```

Cursor and `cursor-agent` discover `.cursor/mcp.json` from the project tree.

## User Scope

For one user across all projects:

```bash
mkdir -p ~/.cursor
cp templates/clients/cursor/mcp.json ~/.cursor/mcp.json
```

Native Windows:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor" | Out-Null
Copy-Item templates\clients\cursor\mcp.windows.json "$env:USERPROFILE\.cursor\mcp.json"
```

## Verify

```bash
cursor-agent mcp list
cursor-agent mcp list-tools xuunity_light_unity
```

Inside Cursor, open MCP settings and confirm that `xuunity_light_unity` is
connected before asking the agent to run Unity validation tools.
