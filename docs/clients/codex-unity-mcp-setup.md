# Codex Unity MCP Setup

This guide shows how to connect XUUnity Light Unity MCP through the Codex
custom MCP server UI. Use this only on trusted local projects. If Rider, VS
Code, or another MCP client is also connected, avoid concurrent commands against
the same Unity project.

The images below are sanitized examples based on the Codex Desktop custom MCP
flow.

## Create The Server

In Codex, open `Settings > MCP servers > Add server`, then choose `STDIO`.

Use these values:

| Field | Value |
| --- | --- |
| Name | `xuunity_light_unity` |
| Command to launch | `bash` |
| Argument 1 | `-lc` |
| Argument 2 | `exec "${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh"` |
| Environment variable | `CODEX_TOOLS_HOME=/path/to/.codex-tools` if you do not want the default `$HOME/.codex-tools` |
| Working directory | `/path/to/trusted/workspace` |

![Codex custom MCP command configuration](../assets/codex-custom-mcp-form.svg)

The same setup in `~/.codex/config.toml` looks like this on Linux/macOS:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

Install or update the host-side helper before using the server:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

## Verify

Restart or refresh the Codex MCP server list, then ask Codex:

```text
Use xuunity_light_unity MCP and list tools.
```

You should see tools such as `unity_status`, `unity_status_summary`,
`unity_capabilities`, `unity_license_capabilities`, `unity_compile_matrix`,
`unity_tests_run_editmode`, `unity_tests_run_playmode`, and
`xuunity_setup_validate`.

![Codex MCP tool list verification](../assets/codex-custom-mcp-tools.svg)

For a real Unity project check, include the project path:

```text
Use xuunity_light_unity MCP to run unity_status_summary for /path/to/UnityProject.
```

If the bridge is not ready yet, ask Codex to run the host helper first:

```text
Run xuunity_light_unity_mcp.sh ensure-ready for /path/to/UnityProject, open the editor if needed, then check unity_status_summary.
```

## How To Ask Codex

You do not need to spell out the MCP server name every time once the server is
connected. Natural requests are fine when they name the Unity project and the
operation clearly:

- `Run Unity status for /path/to/UnityProject.`
- `Run EditMode tests in /path/to/UnityProject.`
- `Compile Android player scripts for /path/to/UnityProject.`
- `Check XUUnity setup for /path/to/UnityProject, include tests.`

Mention `xuunity_light_unity` explicitly when you are verifying setup, when more
than one Unity-capable MCP server is configured, or when Codex chooses shell
commands instead of MCP tools. A vague request like `run tests` can be
ambiguous; a request that includes `Unity project root` plus `EditMode` or
`PlayMode` gives the agent enough context to pick the right tool.

If the editor is busy, compiling, importing, or in Play Mode, Codex may report a
busy-state error instead of forcing the operation. Return the editor to an idle
Edit Mode state, or ask for a recovery/status check first.
