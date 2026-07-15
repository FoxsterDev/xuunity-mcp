# Codex-Style Agent Setup

Use the Codex-style config when the client reads MCP servers from
`~/.codex/config.toml`.

This guide is pinned to XUUnity release `v0.3.46` from the canonical repository
`https://github.com/FoxsterDev/xuunity-mcp`. Use the matching release README:
`https://github.com/FoxsterDev/xuunity-mcp/blob/v0.3.46/README.md`.

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
- Requested package release: <v0.3.46>
- Current package pin: <missing | current | stale | custom>
- Existing helper directory: <present | missing>
- Helper state: <current | refresh required | missing> (<installed version and source root>)
- Existing Codex MCP block: <present | missing>
- Codex launcher state: <native/current | migration required>
- Planned project file changes: <manifest, bridge config, lockfile, none>
- Planned user-level config changes: <exact file paths or none>
- Restart or refresh required after mutation: <yes/no>
- Required live proof after restart: <server listed, tools listed, unity_status_summary healthy with mcp_server_info.version=0.3.46>
- Planned commands after approval: <setup-apply, validate-setup, ensure-ready, request-status-summary, unity_status_summary after reload, ...>

Do not run setup-apply, installer commands, helper sync, or Codex config edits
until the user explicitly approves this review.
```

If `~/.codex/config.toml` already contains
`[mcp_servers.xuunity_light_unity]`, inspect the existing block before reuse.
Avoid adding a duplicate. On native Windows, a block that uses `bash`, `run.sh`,
or a WSL path is `migration required`, not verify-only; do not launch it.

For one explicitly requested Unity project, use
`setup-plan --project-root /path/to/UnityProject` by default even if sibling
Unity projects exist nearby. Mention additional projects in the review, but do
not mutate them unless the user approves those exact roots.

## Install The Server

Install the host-side server files:

```bash
bash init_xuunity_light_unity_mcp.sh --target codex
```

On native Windows, install or refresh the Codex helper from the approved
v0.3.46 source through the native wrapper instead of executing an old helper or
requiring Git Bash:

```powershell
$env:XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET = "codex"
.\xuunity_light_unity_mcp.cmd server-help
```

`server-help` first synchronizes the selected installed helper from this source
checkout, then verifies that the installed server CLI starts.

When the wrapper runs from a Codex-style environment, its default `auto`
install target prefers `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}` even if a
Claude-side helper also exists. To make that explicit in scripts, set:

```bash
export XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex
```

If `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp` already exists, reuse
the directory only after comparing the installed helper version and
`.source_root` with v0.3.46. Do not execute stale helper files. Refresh them
from the approved v0.3.46 source after the preflight review is approved.

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

After changing the helper or Codex MCP block, restart or refresh Codex. Treat
this as a required setup phase, not an optional cleanup note.

If `~/.codex/config.toml` already contains
`[mcp_servers.xuunity_light_unity]`, merge or verify the existing block instead
of appending a duplicate entry.

On native Windows, the installer writes a `cmd.exe` block that calls
`run_installed_or_refresh_xuunity_mcp.cmd`. If an existing
`[mcp_servers.xuunity_light_unity]` block still uses `bash`, the installer
keeps it in place and reports `windows_codex_launcher_mismatch` with the
merge-safe replacement block.

That warning is not a successful migration. Do not execute the stale block.
After explicit approval, replace only the existing XUUnity block with the
reported native `cmd.exe`/`.cmd` block. Preserve unrelated Codex settings and
MCP servers, and do not leave a duplicate old block behind.

## Manual Config

Add this to `~/.codex/config.toml` on Linux/macOS:

```toml
[mcp_servers.xuunity_light_unity]
command = "/bin/bash"
args = ["-c", "exec \"/bin/bash\" \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""]
required = false
```

This avoids relying on client-side `~` expansion, PATH lookup for Bash, or a
login profile. The shell resolves `$HOME` and optional `CODEX_TOOLS_HOME`.

For native Windows, add this to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.xuunity_light_unity]
command = "cmd.exe"
args = ["/d", "/c", "call", "C:\\Users\\<YOUR_USERNAME>\\.codex-tools\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd"]
required = false
```

Replace `<YOUR_USERNAME>` with your Windows user name, or run
`bash init_xuunity_light_unity_mcp.sh --install-codex-config`, which writes
the resolved path. Keep every `args` entry free of embedded quotes and
parentheses: clients quote argv with the C-runtime rules, which escape
embedded quotes as `\"` — cmd.exe misparses that and the server never starts.

The Windows config uses `run_installed_or_refresh_xuunity_mcp.cmd`, which
delegates to the refresh-before-run launcher before starting the installed
server. Keep `run.cmd` as a low-level fallback, not the default client command.

The refresh launcher is source-relative. If `.source_root` points at an older
checkout, it can keep an older helper current relative to that checkout. Verify
the installed version/source against v0.3.46 before executing it for this setup.

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
`${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp`.

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

On native Windows, use `.cmd` and quote the project path:

```bat
xuunity_light_unity_mcp.cmd validate-setup --project-root "C:\path with spaces\UnityProject"
xuunity_light_unity_mcp.cmd ensure-ready --project-root "C:\path with spaces\UnityProject" --open-editor
xuunity_light_unity_mcp.cmd request-status-summary --project-root "C:\path with spaces\UnityProject" --timeout-ms 5000
```

Prefer `.cmd` for Windows setup and verification commands. PowerShell `.ps1`
can be blocked by ExecutionPolicy, and Git Bash is not the recommended native
Windows route for project paths containing spaces.

Run these commands sequentially; do not run the status check before
`ensure-ready` finishes. If the current Codex session does not hot-reload newly
installed MCP servers, this helper status summary is useful helper-side
verification, but it does not prove that Codex loaded the MCP server.

Then restart or refresh Codex, confirm that `xuunity_light_unity`
appears in the MCP server list, and ask the client to list the server tools:

```text
Use xuunity_light_unity MCP and list tools.
```

Then verify a concrete Unity project:

1. `unity_status_summary` and require `mcp_server_info.version=0.3.46`
2. `unity_capabilities`
3. `unity_health_probe`
4. `unity_console_tail`

Treat `unity_status_summary` as the canonical first live MCP-tool smoke-check
after Codex can see the server. Only move on to tests or builds after the
status summary reports a healthy bridge.

Do not report setup complete until the restart/refresh, live tool listing, and
`unity_status_summary` all succeed. If the current session still cannot see the
server, report `MCP client connection unverified` and the required restart
instead.

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
