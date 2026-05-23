# README Install Simulation Audit

Date: `2026-05-23`
Status: `completed audit with one P0 fix applied`

## Scope

Simulate a first-time operator or coding agent following the public `README.md`
install path for:

- one Unity project
- a flat multi-project hub
- mixed Unity 2021/2022/6000 projects
- a nested repository containing a Unity project
- optional Test Framework missing, too old, suitable, and supported-but-upgrade-
  recommended states

The goal is install UX quality, not only command correctness.

## Commands Simulated

Representative commands:

```bash
bash xuunity_light_unity_mcp.sh setup-plan --workspace-root <workspace> --recursive
bash xuunity_light_unity_mcp.sh setup-apply --plan-file <plan> --yes
bash xuunity_light_unity_mcp.sh validate-setup --project-root <project> --include-tests
bash xuunity_light_unity_mcp.sh setup-apply --plan-file <plan>
```

The simulation also forced a fresh installed-helper path through temporary
`CODEX_TOOLS_HOME` and `CLAUDE_TOOLS_HOME` roots to mimic a real user running
the helper from an installed MCP server, not directly from the source tree.

## What Went Well

- `setup-plan --recursive` discovered all simulated projects across single,
  flat hub, mixed-version hub, and nested repo layouts.
- `setup-apply` refused mutation without `--yes`.
- `setup-apply --yes` wrote only the expected MCP dependency and bridge config
  for each project.
- Test Framework policy was per project:
  - Unity 2021/2022 missing dependency stayed optional unless explicitly
    requested.
  - Unity 2022 with Test Framework `1.0.0` planned an approved upgrade to
    `1.1.33`.
  - Unity 6000 with Test Framework `1.1.33` stayed `supported` and reported an
    optional recommendation toward `1.5.1`.
  - Unity 2021 with Test Framework `1.2.0` stayed supported without churn.
- `validate-setup --include-tests` produced actionable capability states rather
  than generic failures.

## P0 Found And Fixed

Before the fix, a README-guided `setup-plan` run through the installed helper
could produce this dependency:

```text
https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.0.0
```

Root cause: the installed helper contained `server.py` but not the package
metadata file used to infer the current release version. The source-tree path
worked, but the installed MCP path fell back to `0.0.0`.

Fix applied:

- the wrapper sync now copies `packages/com.xuunity.light-mcp/package.json` into
  the installed helper
- the installer copies the same metadata during host install
- `server.py` resolves operation root correctly for both source-tree and
  installed-helper layouts
- a wrapper regression test proves default setup plans use the real package
  version after helper sync

After the fix, the same simulation produced `#v0.3.14`.

## Remaining UX Risks

- README has two valid routes: guided wizard and manual package install. This is
  correct, but less capable agents may mix them. The wizard should remain the
  obvious default path.
- Client setup still depends on copying JSON/TOML templates. The README now says
  to merge existing config, but a future command should automate safe client
  config merge for supported clients.
- Rider and plain Visual Studio Code setup are not documented as first-class
  client guides yet. Current users must adapt the generic stdio template.
- `setup-apply` returns `applied_actions`, but the action records do not carry a
  clear `status=applied/unchanged/skipped`. This is workable for machines but
  weak for human closeout.
- `setup-plan --recursive` can discover more Unity projects than intended in a
  large workspace. A future UX pass should add include/exclude/depth controls or
  a compact confirmation table before apply.
- GitHub web pages or already-open browser tabs can show stale README content.
  Agents should prefer fresh raw/source content or local clone contents when
  exact release commands matter.

## Recommended Tuning Backlog

1. Add `install-client-config` or `setup-client` for Claude Code, Claude
   Desktop, Cursor, Windsurf, Codex, generic stdio, Rider, and VS Code.
2. Add explicit `status` and `before/after` fields to `setup-apply` action
   records.
3. Add `setup-plan --summary` or compact table output for humans before
   approval.
4. Add workspace discovery controls: `--exclude`, `--max-depth`, and possibly
   `--confirm-projects-file`.
5. Promote Rider and VS Code docs from generic stdio guidance into dedicated
   client pages after validating their current MCP UI.
6. Add a reusable README install simulation test so future releases catch
   stale version defaults and template drift before tagging.

## Self-Review

Good: the audit tested both human-facing README flow and the installed-helper
runtime path, which is where the most dangerous version bug lived.

Risk: this was still a host-side simulation. It did not re-run live Unity import
for every simulated topology because the release Git UPM smoke already covered a
clean Unity 2021 project, and the earlier matrix covered runnable installed
editors.
