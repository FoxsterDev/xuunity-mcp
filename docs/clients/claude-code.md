# Claude Code Setup

Use the installer to register XUUnity Light Unity MCP with Claude Code:

```bash
bash init_xuunity_light_unity_mcp.sh --install-claude-config
```

Then enable the bridge for a Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Verify the setup with these MCP calls:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`

Do not run compile, tests, Play Mode, or screenshots until the health probe succeeds.

