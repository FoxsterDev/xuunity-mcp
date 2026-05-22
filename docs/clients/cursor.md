# Cursor Setup

Use XUUnity Light Unity MCP with Cursor when you want a local AI agent to validate Unity projects through MCP.

## Steps

1. Install the host-side MCP server:

   ```bash
   bash init_xuunity_light_unity_mcp.sh
   ```

2. Add the Unity package to `Packages/manifest.json`.

3. Enable the bridge for the Unity project:

   ```bash
   bash init_xuunity_light_unity_mcp.sh \
     --project-root /path/to/UnityProject \
     --enable-project
   ```

4. Configure Cursor to run:

   ```text
   ~/.codex-tools/xuunity-light-unity-mcp/run.sh
   ```

5. Verify with `unity.status`, `unity.capabilities.get`, and `unity.health.probe`.

