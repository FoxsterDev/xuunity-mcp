# Install XUUnity Light Unity MCP

Date: `2026-05-23`
Status: `current for v0.3.19`

XUUnity Light Unity MCP has two pieces:

1. a host-side MCP server
2. an editor-only Unity package

Install both before expecting an AI client to control Unity.

## Agent Preflight Rules

For short agent requests such as "setup MCP from this repo into
/path/to/UnityProject and run EditMode tests", prefer this default behavior:

1. treat the current host client that is executing the request as the default
   MCP wiring target unless the user explicitly names another client
2. use `setup-plan` before any mutation
3. for one explicitly requested Unity project, prefer
   `setup-plan --project-root /path/to/UnityProject`
4. for a multi-project workspace or nested repo, use
   `setup-plan --workspace-root /path/to/workspace --recursive`
5. show a short preflight review before any mutation:
   - detected current client
   - intended wiring target
   - requested Unity project root
   - additional discovered Unity projects
   - files that will change, including user-level client config
6. wait for approval before `git clone`, installer runs, `setup-apply`,
   manifest edits, lockfile edits, or user-level client config changes
7. treat `unity_status_summary` as the canonical first MCP smoke-check after
   `ensure-ready`

## Option 1: Git UPM Package

This is the current production install route until OpenUPM publication is
complete.

Add this dependency to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.19"
  }
}
```

## Option 2: Local File Package

For active local development, reference the package folder directly:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-light-unity-mcp/packages/com.xuunity.light-mcp"
  }
}
```

## Migrating From The Old Package Path

`v0.3.11` and earlier used this package subpath:

```text
templates/unity-package
```

`v0.3.12+` uses the registry-native package path:

```text
packages/com.xuunity.light-mcp
```

Existing projects pinned to `v0.3.11` can keep working until they intentionally
upgrade. New installs should use the `packages/com.xuunity.light-mcp` Git UPM
path.

## Initialize Host MCP Server

From the repository root on Linux/macOS:

```bash
bash init_xuunity_light_unity_mcp.sh
```

The installer writes `run.sh`, `run.cmd`, and `run.ps1` into each selected
host tools directory. Native Windows clients should use the Windows templates
that call `run.cmd`.

To enable a Unity project bridge without changing package mode:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

This writes bridge config under `Library/XUUnityLightMcp/` only. It does not
rewrite `Packages/manifest.json`. Keep Git UPM as the default project state and
use wrapper `devmode` only when you intentionally want the local `file:`
package source.

## Guided Workspace Setup

For one explicitly requested Unity project, prefer a scoped plan/apply flow:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --project-root /path/to/UnityProject > /tmp/xuunity-setup-plan.json

bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
```

For a flat multi-project hub, mixed Unity versions, or nested repositories,
scan first and then apply only to the approved Unity project roots:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > /tmp/xuunity-setup-plan.json

bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
```

`setup-plan` computes actions per project. It does not apply one dependency
version globally across mixed Unity versions. When the plan contains more than
one discovered Unity project, require an explicit project selection before
`setup-apply`.

The MCP core package works without `com.unity.test-framework`. EditMode and
PlayMode test operations are optional capabilities enabled by Unity asmdef
Version Defines when `com.unity.test-framework >= 1.1.33` is present.

Recommended Test Framework versions:

| Unity version | Recommended dependency |
| --- | --- |
| Unity 2021/2022 | `com.unity.test-framework@1.1.33` |
| Unity 6000+ | `com.unity.test-framework@1.5.1` |

To enable test operations after explicit approval:

```bash
bash xuunity_light_unity_mcp.sh install-test-framework \
  --project-root /path/to/UnityProject \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject \
  --include-tests
```

When the Unity bridge is already healthy, clients may use
`unity_package_install_test_framework` with `approve: true` to install the same
optional dependency through Unity Package Manager.

If the project already declares `com.unity.test-framework`, the setup wizard
does not treat every existing version the same way. A version at or above
`1.1.33` enables the test capability. Unity 6000 projects on `1.1.33` stay
supported but report `upgrade_recommended=true` toward `1.5.1`. A version below
`1.1.33` reports `disabled_dependency_too_old` and plans an explicit approved
upgrade, preserving unrelated manifest entries and requiring a Unity package
resolve/compile check afterward.

Explicit local mode switch:

```bash
bash xuunity_light_unity_mcp.sh devmode --project-root /path/to/UnityProject
```

Switch back to the published Git-backed dependency:

```bash
bash xuunity_light_unity_mcp.sh prodmode --project-root /path/to/UnityProject
```

## Connect Codex-Style Agents

The installer can append a Codex MCP config block:

```bash
bash init_xuunity_light_unity_mcp.sh --install-codex-config
```

If the current Codex session does not hot-reload new MCP servers, restart the
client after this change.

Template:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-light-unity-mcp/run.sh\""]
required = false
```

Windows template:

```toml
[mcp_servers.xuunity_light_unity]
command = "cmd.exe"
args = ['/d', '/c', 'if defined CODEX_TOOLS_HOME (call "%CODEX_TOOLS_HOME%\xuunity-light-unity-mcp\run.cmd") else (call "%USERPROFILE%\.codex-tools\xuunity-light-unity-mcp\run.cmd")']
required = false
```

## Connect Claude Code

The installer can register the MCP server in the Claude Code user config:

```bash
bash init_xuunity_light_unity_mcp.sh --install-claude-config
```

Project-scoped Claude Code config:

```bash
cp templates/clients/claude-code/.mcp.json .mcp.json
```

Native Windows project-scoped Claude Code config:

```powershell
Copy-Item templates\clients\claude-code\.mcp.windows.json .mcp.json
```

## Connect Cursor

```bash
mkdir -p .cursor
cp templates/clients/cursor/mcp.json .cursor/mcp.json
```

Native Windows:

```powershell
New-Item -ItemType Directory -Force .cursor | Out-Null
Copy-Item templates\clients\cursor\mcp.windows.json .cursor\mcp.json
```

For user-global Cursor config, copy the same file to `~/.cursor/mcp.json`.

## Connect Windsurf

```bash
mkdir -p ~/.codeium/windsurf
cp templates/clients/windsurf/mcp_config.json ~/.codeium/windsurf/mcp_config.json
```

Native Windows:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codeium\windsurf" | Out-Null
Copy-Item templates\clients\windsurf\mcp_config.windows.json "$env:USERPROFILE\.codeium\windsurf\mcp_config.json"
```

## Connect Claude Desktop

On macOS:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
cp templates/clients/claude-desktop/claude_desktop_config.json \
  "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

On Windows:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\Claude" | Out-Null
Copy-Item templates\clients\claude-desktop\claude_desktop_config.windows.json `
  "$env:APPDATA\Claude\claude_desktop_config.json"
```

If a target config already has other MCP servers, merge only the
`mcpServers.xuunity_light_unity` block.

## Verify Installation

After package import and bridge enablement:

1. open the Unity project
2. confirm the package appears in Package Manager
3. confirm the bridge state appears under `Library/XUUnityLightMcp/`
4. call `unity.status` or `unity_status_summary`
5. call `unity.capabilities.get`
6. call `unity.health.probe`

Do not treat the install as ready until status, capabilities, and health probe all succeed.

For package-level verification after upgrading to `v0.3.19`, run:

```bash
templates/smoke/run_package_self_tests.sh \
  --project-root /path/to/UnityProject \
  --mode all
```

The current self-test baseline is EditMode `6/6` and PlayMode `5/5` on a
healthy Unity 6000 project.

For a clean-project Android APK proof that keeps Git UPM as the default package
mode and only uses local `file:` mode through explicit `devmode`, run:

```bash
templates/smoke/run_clean_project_android_apk_smoke.sh
```

When the selected Unity editor does not include Android Build Support and you
only want MCP readiness proof, allow the runner to skip the APK lane:

```bash
templates/smoke/run_clean_project_android_apk_smoke.sh --allow-no-android
```

## Troubleshooting

- If the bridge is disabled, run the init script with `--enable-project`.
- If the AI client cannot find the server, verify the configured `run.sh` or `run.cmd` path.
- If Unity imported the package but MCP calls fail, check `Library/XUUnityLightMcp/` for bridge state and request artifacts.
- If a Unity project is already open, prefer reusing the healthy editor session instead of starting a competing one.
- If `batch-editmode-tests` reports `test_capability_unavailable`, inspect the
  reported capability status. Missing Test Framework means install it with
  `install-test-framework --yes`; an old declared Test Framework means approve
  the dependency upgrade, let Unity resolve packages, then rerun validation.
