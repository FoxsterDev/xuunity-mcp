# Claude Desktop Setup

Claude Desktop can run the same stdio MCP server as other MCP clients.

Use this command as the MCP server executable:

```text
~/.claude-tools/xuunity-light-unity-mcp/run.sh
```

Install the helper files first:

```bash
bash init_xuunity_light_unity_mcp.sh --target claude
```

Then install the Unity package and enable the bridge for the target project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Verify with `unity.status`, `unity.capabilities.get`, and `unity.health.probe`.

