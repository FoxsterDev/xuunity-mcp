# Antigravity IDE Setup

Antigravity IDE (the agentic AI coding assistant environment) supports XUUnity Light Unity MCP via its Model Context Protocol integration.

## Install The Server

Install the host-side server files in the centralized neutral location:

```bash
bash init_xuunity_light_unity_mcp.sh --target neutral
```

Enable the bridge for your Unity project without changing the package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

---

## Configuring Antigravity IDE

You can register and grant permissions to the MCP server directly within the Antigravity IDE user interface:

1. Open the **Settings** panel in Antigravity IDE.
2. Navigate to **Permissions** -> **MCP Tools**.
3. Click the **Add** button.
4. Set the permission policy dropdown to **Allow** (or **Ask** if you prefer to review every invocation).
5. In the input field, enter the path to the launcher script:
    - **macOS**: `bash "/Users/<username>/Library/Application Support/xuunity-mcp/run.sh"` *(replace `<username>` with your macOS username)*
    - **Linux**: `bash "/home/<username>/.local/share/xuunity-mcp/run.sh"` *(replace `<username>` with your Linux username)*
    - **Windows**: `cmd.exe /c %APPDATA%\xuunity-mcp\run.cmd`
6. Save the settings.

---

## Verify Connection

Once added and allowed, the Antigravity agent can communicate with the Unity Editor. You can ask the agent to verify the connection:

```text
Verify Unity MCP connection and print project health status.
```

The agent will use the following tools:
1. `unity_status_summary` (to check if the bridge is live and active)
2. `unity_health_probe` (to run a smoke test on editor status)
3. `unity_capabilities` (to list active project capabilities)

*Note: Ensure the Unity Editor is open and active for the configured project before starting live validations.*
