# Codex-Style Agent Setup

Use the Codex-style config when the client reads MCP servers from
`~/.codex/config.toml`.

When a short install request does not name a client explicitly, treat the
current host client that is executing the request as the default wiring target.
For prompts coming from Codex, wire Codex by default and show that assumption in
the preflight review before mutating files.

Important:

- Codex UI auto-review or tool-level approval is not the same thing as user
  approval of setup mutations.
- A preflight review still has to be shown in chat before `setup-apply`,
  installer mutations, or user-level config changes.

Optional: connect XUUnity MCP to Codex/Codex-style clients when you want Codex
to validate Unity status, compile, tests, and setup directly from the chat. Use
this only on trusted local projects. If you also use Rider or VS Code MCP,
avoid running concurrent commands against the same Unity project.

For Codex Desktop's custom MCP server UI, use the visual guide:
[Codex Unity MCP Setup](codex-unity-mcp-setup.md).

## Required Preflight Review

Before mutating a Unity project, refreshing the host helper, running the
installer, or editing `~/.codex/config.toml`, show a short review like this:

```text
Preflight review
- Current client: Codex
- Wiring target: Codex
- Unity project root: <approved project root>
- Additional discovered Unity projects: <none or list>
- Existing helper install: <reuse existing helper | install or refresh after approval>
- Existing Codex MCP block: <present | missing>
- Planned project file changes: <manifest, bridge config, lockfile, none>
- Planned user-level config changes: <exact file paths or none>
- Restart or refresh required after mutation: <yes/no>
- Planned commands after approval: <setup-apply, validate-setup, ensure-ready, request-status-summary, unity_status_summary after reload, ...>

Do not run setup-apply, installer commands, helper sync, or Codex config edits
until the user explicitly approves this review.
```

If `~/.codex/config.toml` already contains
`[mcp_servers.xuunity_light_unity]`, the default action is verify-only:
inspect the block, avoid adding a duplicate, and run project readiness checks.

For one explicitly requested Unity project, use
`setup-plan --project-root /path/to/UnityProject` by default even if sibling
Unity projects exist nearby. Mention additional projects in the review, but do
not mutate them unless the user approves those exact roots.

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

When the wrapper runs from a Codex-style environment, its default `auto`
install target prefers `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}` even if a
Claude-side helper also exists. To make that explicit in scripts, set:

```bash
export XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex
```

If `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh`
already exists, reuse that helper install instead of cloning a fresh repo just
to run the installer again.

Enable the bridge for the Unity project without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Keep the Unity package on the default Git UPM dependency unless you explicitly
switch the project into local package `devmode`.

## Automatic User Config

The installer can append the MCP block:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target codex \
  --install-codex-config
```

If the current Codex session does not hot-reload newly installed MCP servers,
restart the client after this change.

If `~/.codex/config.toml` already contains
`[mcp_servers.xuunity_light_unity]`, merge or verify the existing block instead
of appending a duplicate entry.

## Manual Config

Add this to `~/.codex/config.toml` on Linux/macOS:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

This avoids relying on client-side `~` expansion. The shell resolves `$HOME`
and optional `CODEX_TOOLS_HOME`.

For native Windows, add this to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.xuunity_light_unity]
command = "cmd.exe"
args = ['/d', '/c', 'if defined CODEX_TOOLS_HOME (call "%CODEX_TOOLS_HOME%\xuunity-light-unity-mcp\run.cmd") else (call "%USERPROFILE%\.codex-tools\xuunity-light-unity-mcp\run.cmd")']
required = false
```

The Windows config uses `run.cmd`, which resolves `server.py` beside itself and
prefers `PYTHON`, then `py -3`, then `python`, then `python3`.

Manual or automatic Codex config only wires the client to the host helper. It
does not prove that a specific Unity project has the MCP package dependency,
bridge config, or test capability enabled yet. Treat user-level client wiring
and per-project Unity setup as separate stages in the review.

## Remove Or Reset

Use `uninstall-plan` before removing project setup, Codex config, or helper
files. Codex UI approval or sandbox approval is not a substitute for user
approval of the uninstall preflight review.

Project-only cleanup for one project:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Review the plan in chat first.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Project-only mode removes only the selected project's MCP package dependency,
package-lock entry, and `Library/XUUnityLightMcp` bridge state. It keeps
`~/.codex/config.toml` and
`${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp`.

Full current-user reset for Codex:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client codex \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Review exact config/helper removals in chat first.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Omit `--project-root` for a Codex user-only reset. Full reset removes only the
`[mcp_servers.xuunity_light_unity]` block from `~/.codex/config.toml`; it does
not delete the config file or unrelated MCP server blocks. It removes only the
selected Codex helper install by default. Other known helper installs are kept
unless `--include-other-client-helpers` is explicitly present in the reviewed
plan.

Restart or refresh Codex after removing the config block. Do not classify stale
Unity `Library` cache as active installation by itself.

## Verify

First verify the concrete Unity project with helper commands:

```bash
bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject

bash xuunity_light_unity_mcp.sh ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor

bash xuunity_light_unity_mcp.sh request-status-summary \
  --project-root /path/to/UnityProject \
  --timeout-ms 5000
```

Run these commands sequentially; do not run the status check before
`ensure-ready` finishes. If the current Codex session does not hot-reload newly
installed MCP servers, this helper status summary is the correct first
verification.

Then restart or refresh Codex if needed, confirm that `xuunity_light_unity`
appears in the MCP server list, and ask the client to list the server tools:

```text
Use xuunity_light_unity MCP and list tools.
```

Then verify a concrete Unity project:

1. `unity_status_summary`
2. `unity_capabilities`
3. `unity_health_probe`
4. `unity_console_tail`

Treat `unity_status_summary` as the canonical first live MCP-tool smoke-check
after Codex can see the server. Only move on to tests or builds after the
status summary reports a healthy bridge.

If Codex used `ensure-ready --open-editor` and the result reports
`opened_by_host: true`, Codex owns that temporary Unity editor session. Before
the final response, run:

```bash
bash xuunity_light_unity_mcp.sh restore-editor-state \
  --project-root /path/to/UnityProject

bash xuunity_light_unity_mcp.sh verify-editor-closed \
  --project-root /path/to/UnityProject \
  --timeout-ms 0
```

Report the closeout result alongside the test, compile, or health-check result.

Install success means Codex can reach a healthy Unity bridge. If
`unity_status_summary`, `unity_capabilities`, and `unity_health_probe` succeed
but a later compile or test run fails, treat that as a Unity project or runtime
failure unless the error explicitly points back to MCP setup or capability
support.

You can name the server explicitly while verifying setup. After that, natural
requests such as `Run EditMode tests in /path/to/UnityProject` are usually
enough as long as the Unity project path and desired operation are clear.
