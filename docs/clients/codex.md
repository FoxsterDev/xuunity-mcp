# Codex-Style Agent Setup

Use the installer to add a Codex MCP config block:

```bash
bash init_xuunity_light_unity_mcp.sh --install-codex-config
```

Equivalent config:

```toml
[mcp_servers.xuunity_light_unity]
command = "~/.codex-tools/xuunity-light-unity-mcp/run.sh"
required = false
```

Enable a Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Preferred first checks:

1. `unity.status`
2. `unity.capabilities.get`
3. `unity.health.probe`
4. `unity.console.tail`

