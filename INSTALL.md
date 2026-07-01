# Install XUUnity Light Unity MCP

Date: `2026-05-23`
Status: `current for v0.3.35`

XUUnity Light Unity MCP has two pieces:

1. a host-side MCP server
2. an editor-only Unity package

Install both before expecting an AI client to control Unity.

Important:

- UI auto-review, sandbox auto-approval, or tool-level approval is not the same
  thing as user approval of setup mutations.
- If the host helper is already installed locally under `~/.codex-tools`,
  `~/.claude-tools`, or another explicit tools path, reuse it before cloning a
  fresh copy of the repo.

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
   - whether the client must restart or refresh after the change
6. wait for approval before `git clone`, installer runs, `setup-apply`,
   manifest edits, lockfile edits, or user-level client config changes
7. run `validate-setup`, then `ensure-ready`, then the status check
   sequentially; do not run the status check before `ensure-ready` finishes
8. use `request-status-summary` as the first helper verification when the
   current client cannot see newly wired MCP tools yet; after restart or
   refresh, treat `unity_status_summary` as the canonical first live MCP-tool
   smoke-check
9. if `ensure-ready --open-editor` opens Unity for the workflow
   (`opened_by_host: true`), run `restore-editor-state` and then
   `verify-editor-closed` before the final report

Before running the helper, verify which Python it will use:

```bash
command -v python3
python3 --version
```

If the selected interpreter is older than `3.10`, set `PYTHON` explicitly
before `run_installed_or_refresh_xuunity_mcp.sh`, `run.sh`, or
`xuunity_light_unity_mcp.sh`.

`setup-plan` is the only setup wizard command intended for pre-approval
inspection. It must not clone, run the installer, refresh installed helper
files under `~/.codex-tools` or `~/.claude-tools`, edit manifests, or change
user-level client config. If helper refresh is required, do it only after the
preflight review is approved.

For uninstall or cleanup requests, use `uninstall-plan` before any removal.
Minimal clean mode keeps user-level client config and helper installs. Full
reset mode is current-user scoped and removes only the selected
`xuunity_light_unity` server block plus selected helper install after approval.
Neither mode silently mutates sibling Unity projects.

## Required Preflight Review Template

Before `setup-apply`, show the user a short review like this and wait:

```text
Preflight review
- Current client: <detected client>
- Wiring target: <target client>
- Unity project root: <approved project root>
- Additional discovered Unity projects: <none or list>
- Existing helper install: <reuse existing helper | clone required>
- Planned project file changes: <manifest, bridge config, lockfile, none>
- Planned user-level config changes: <exact file paths or none>
- Restart or refresh required after mutation: <yes/no and which client>
- Planned commands after approval: <setup-apply, validate-setup, ensure-ready, request-status-summary, unity_status_summary after reload, ...>

Do not run setup-apply, installer commands, helper sync, or client config edits
until the user explicitly approves this review.
```

For uninstall, show the `preferred_review_summary` from `uninstall-plan` before
`uninstall-apply`. It must list the mode, selected client, target project,
additional discovered projects, exact project cleanup paths, exact user config
cleanup paths, helper installs to remove or keep, and restart/refresh
requirements.

## Option 1: Git UPM Package

This is the current production install route until OpenUPM publication is
complete.

Add this dependency to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.35"
  }
}
```

## Option 2: Local File Package

For active local development, reference the package folder directly:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp"
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

The installer writes `run_installed_or_refresh_xuunity_mcp.sh`,
`run_installed_or_refresh_xuunity_mcp.py`,
`run_installed_or_refresh_xuunity_mcp.cmd`, `run.sh`, `run.cmd`, and `run.ps1` into each selected
host tools directory. Native Windows clients should use the Windows templates
that call `run_installed_or_refresh_xuunity_mcp.cmd`; keep `run.cmd` as a
low-level fallback.

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

# Stop here. Review the plan with the user before continuing.
bash xuunity_light_unity_mcp.sh setup-apply \
  --plan-file /tmp/xuunity-setup-plan.json \
  --project-root /path/to/UnityProject \
  --yes

bash xuunity_light_unity_mcp.sh validate-setup \
  --project-root /path/to/UnityProject
```

Native Windows quickstart from `cmd.exe`:

```bat
xuunity_light_unity_mcp.cmd setup-plan --project-root "C:\path with spaces\UnityProject" > "%TEMP%\xuunity-setup-plan.json"

REM Stop here. Review the plan with the user before continuing.
xuunity_light_unity_mcp.cmd setup-apply --plan-file "%TEMP%\xuunity-setup-plan.json" --project-root "C:\path with spaces\UnityProject" --yes
xuunity_light_unity_mcp.cmd validate-setup --project-root "C:\path with spaces\UnityProject"
xuunity_light_unity_mcp.cmd ensure-ready --project-root "C:\path with spaces\UnityProject" --open-editor
```

Quote every `--project-root` and `--workspace-root` value on Windows. Prefer
the `.cmd` launcher for setup; `.ps1` can be blocked by PowerShell
ExecutionPolicy, and Git Bash is not the recommended native Windows setup route
for project paths containing spaces.

For a flat multi-project hub, mixed Unity versions, or nested repositories,
scan first and then apply only to the approved Unity project roots:

```bash
bash xuunity_light_unity_mcp.sh setup-plan \
  --workspace-root /path/to/workspace \
  --recursive > /tmp/xuunity-setup-plan.json

# Stop here. Review the plan and approve the exact target project roots first.
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

If the user gave one explicit Unity project path, default to
`setup-plan --project-root /path/to/UnityProject` even when sibling or nested
Unity projects exist nearby. Mention additional projects in the review, but do
not mutate them unless the user approves those exact roots.

If the current host already has the helper installed, prefer reusing it for
`setup-apply` and verification instead of cloning a fresh repo copy only to run
the same commands. For `setup-plan`, use the available non-mutating entrypoint:
the wrapper runs it from the source checkout, and an installed helper may run
it directly when no source checkout is available.

If the helper is missing but the repo checkout is available, `setup-plan` can
run from the source checkout for preflight. Install or refresh the host helper
only after approval, or when the user explicitly asked for helper installation.

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

## Guided Uninstall And Reset

Use this path when you want to remove XUUnity Light Unity MCP safely.

Project-only cleanup:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode project-only-cleanup \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Stop here. Review the plan and get explicit approval.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Project-only mode removes only the selected project's `com.xuunity.light-mcp`
manifest dependency, its package-lock entry, and `Library/XUUnityLightMcp`
bridge state. It keeps current-user client config and helper installs.

Full reset for the current user:

```bash
bash xuunity_light_unity_mcp.sh uninstall-plan \
  --mode full-reset-current-user \
  --client auto \
  --project-root /path/to/UnityProject > /tmp/xuunity-uninstall-plan.json

# Stop here. Review exact user config and helper removals.
bash xuunity_light_unity_mcp.sh uninstall-apply \
  --plan-file /tmp/xuunity-uninstall-plan.json \
  --yes
```

Omit `--project-root` for a user-only reset. Use
`--client codex|claude_code|cursor|windsurf|claude_desktop` when auto-detection
is not enough. Full reset removes only the `xuunity_light_unity` server block
from the selected current-user config file and removes only the selected
current-user helper install. Other known helper installs are kept unless
`--include-other-client-helpers` is explicitly present in the reviewed plan.

Do not treat stale Unity `Library` cache as active installation by itself.
`Library/XUUnityLightMcp` is removed as project bridge state; broader Unity
cache wiping is outside this uninstall flow and should be a separate explicit
project-maintenance action.

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

If `~/.codex/config.toml` already contains `[mcp_servers.xuunity_light_unity]`,
merge or verify the existing block instead of appending a duplicate entry.

Template:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp/run_installed_or_refresh_xuunity_mcp.sh\""]
required = false
```

Windows template:

```toml
[mcp_servers.xuunity_light_unity]
command = "cmd.exe"
args = ['/d', '/c', 'if defined CODEX_TOOLS_HOME (call "%CODEX_TOOLS_HOME%\xuunity-mcp\run_installed_or_refresh_xuunity_mcp.cmd") else (call "%USERPROFILE%\.codex-tools\xuunity-mcp\run_installed_or_refresh_xuunity_mcp.cmd")']
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

When an automated setup or verification step opens Unity with
`ensure-ready --open-editor`, inspect the result for `opened_by_host`. If it is
`true`, close only that helper-owned editor session before finishing:

```bash
bash xuunity_light_unity_mcp.sh restore-editor-state \
  --project-root /path/to/UnityProject

bash xuunity_light_unity_mcp.sh verify-editor-closed \
  --project-root /path/to/UnityProject \
  --timeout-ms 0
```

The final install report should state whether the editor was reused or opened
by the helper, and include the closeout verification result when the helper
opened it.

Install success means the MCP package, bridge, and client wiring are working.
If those checks succeed but a later compile or test run fails, treat that as a
Unity project or runtime failure unless the error explicitly points back to
bridge readiness, package import, or unsupported capability.

For package-level verification after upgrading to `v0.3.35`, run:

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
- If the AI client cannot find the server, verify the configured `run_installed_or_refresh_xuunity_mcp.sh`, `run_installed_or_refresh_xuunity_mcp.cmd`, `run.sh`, or `run.cmd` path.
- If Unity imported the package but MCP calls fail, check `Library/XUUnityLightMcp/` for bridge state and request artifacts.
- If a Unity project is already open, prefer reusing the healthy editor session instead of starting a competing one.
- If `batch-editmode-tests` reports `test_capability_unavailable`, inspect the
  reported capability status. Missing Test Framework means install it with
  `install-test-framework --yes`; an old declared Test Framework means approve
  the dependency upgrade, let Unity resolve packages, then rerun validation.
