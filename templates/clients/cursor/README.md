# Cursor Client Adapter

Status: `active`.

Cursor uses JSON MCP configuration files. Use the template in this folder as
either a project-scoped config or a user-global config.

Important:

- Reuse an existing local helper install if it is already present.
- Merge only the `mcpServers.xuunity_light_unity` block when the destination
  file already contains other MCP servers.
- Refresh Cursor's MCP server list after changing the config if the current
  session does not auto-detect the update.
- Client wiring does not prove Unity project readiness. Run `validate-setup`,
  `ensure-ready`, and `unity_status_summary` for the target project after
  wiring.

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

Treat `unity_status_summary` as the canonical first live smoke-check after
setup. If it is healthy but a later compile or test run fails, treat that as a
Unity project or runtime failure unless the error explicitly points back to MCP
setup or unsupported capability.

## Remove Or Reset

Use `uninstall-plan` before deleting project setup, Cursor config, or helper
files.

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json
```

Project-only mode keeps Cursor config and the helper install. For a current-user
reset, use `--mode full-reset-current-user --client cursor`, review the exact
config/helper removals, then run `uninstall-apply --plan-file ... --yes` only
after explicit approval. Remove only `mcpServers.xuunity_light_unity`; do not
delete whole config files or unrelated MCP servers.
