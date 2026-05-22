# Windsurf Setup

Use XUUnity Light Unity MCP with Windsurf through a stdio MCP server entry.

Server command:

```text
~/.codex-tools/xuunity-light-unity-mcp/run.sh
```

Recommended setup:

```bash
bash init_xuunity_light_unity_mcp.sh
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

After connecting, start with:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`

Treat failures in those checks as setup issues before running validation workflows.

