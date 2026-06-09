# Client Docs Router: XUUnityLightUnityMcp

## Purpose
Route client-specific documentation work for `XUUnityLightUnityMcp`.
Use this file when a session starts in `docs/clients/` or a parent task targets a
specific MCP client guide.

## Load Order
1. MCP project router at `../../Agents.md`
2. Relevant agent integration guidance from `../agents/`
3. The requested client guide in this folder
4. Matching client template under `../../templates/clients/` when the guide and template must stay aligned

## Client Map
- Codex: `codex.md`, `codex-unity-mcp-setup.md`, and `../../templates/clients/codex/`
- Claude Code: `claude-code.md` and `../../templates/clients/claude-code/`
- Claude Desktop: `claude-desktop.md` and `../../templates/clients/claude-desktop/`
- Cursor: `cursor.md` and `../../templates/clients/cursor/`
- Rider: `rider.md`
- Windsurf: `windsurf.md` and `../../templates/clients/windsurf/`
- Antigravity IDE: `antigravity.md`

## Routing Rules
- Keep client docs consistent with the root `README.md`, `INSTALL.md`, and `docs/agents/AI_INTEGRATION.md`.
- When a client guide references config snippets, verify the matching template before changing the guide.
- Do not overwrite or generalize client-specific constraints across all clients unless the shared integration docs also support the change.
- Prefer exact file paths and merge-safe setup language for MCP config instructions.
- Keep uninstall language merge-safe too: use `uninstall-plan` before deletion,
  remove only the `xuunity_light_unity` MCP server block from client config,
  and never delete whole config files or sibling Unity project setup silently.
