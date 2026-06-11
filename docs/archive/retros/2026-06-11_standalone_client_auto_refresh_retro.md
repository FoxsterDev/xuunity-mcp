# XUUnity Light Unity MCP Standalone Client Auto-Refresh Retro

Date: 2026-06-11
Status: public-safe sanitized, implemented
Source: sanitized from a host-local package/server update and multi-client validation session

## Executive Summary

A package version bump exposed a distribution reliability gap: Unity projects
could be moved to a newer `com.xuunity.light-mcp` package while MCP clients
continued launching an older installed host helper. The Unity-side operations
were not the core failure. The weak point was the standalone client startup
contract: client configs and installed launchers could bypass the source
checkout and therefore miss server/helper refresh after a package update.

The reusable fix is now public-first. The standalone public repo owns a thin
refresh-before-run shell launcher backed by Python implementation, the installer
deploys it into neutral and client-specific install directories, client
templates point to it, and installed helpers record `.source_root` so they can
refresh from the public source checkout without relying on host-local `AIRoot`
or `AIOutput` wrappers.

## Evidence Base

- A project package pin update was applied before the operator verified that the
  installed MCP server helper was also updated.
- The installed neutral helper version could be checked independently from the
  Unity package dependency.
- A sandbox stale-helper simulation proved that a refresh launcher can update a
  stale neutral install before delegating to `run.sh`.
- Multi-instance and multi-project test runs showed the MCP runtime could handle
  concurrent project operation; the remaining reliability gap was distribution
  and client startup consistency.
- Public installer/config tests proved that the self-refresh behavior belongs in
  the standalone MCP repo, not in host-local wrapper paths.

## Timeline

1. A package/server update request required all Unity package pins and the
   installed MCP server helper to move to the same version.
2. Initial mitigation added a host-local refresh launcher under a monorepo
   operations folder.
3. Review identified that external clients may use the public MCP repo without
   any host-local `AIRoot` or `AIOutput` layout.
4. The refresh launcher was promoted into the standalone public MCP repo.
5. Installer, Python launcher sync paths, client templates, docs, and
   regression tests were updated so client startup uses refresh-before-run by
   default.
6. Validation confirmed syntax, whitespace, installer behavior, config output,
   and setup/launcher regression coverage.

## What Worked Well

- Version evidence was explicit: the Unity package version and installed server
  helper version could be compared instead of inferred.
- Sandbox stale-install tests made the auto-refresh behavior safe to prove
  without mutating real user client directories.
- Keeping `run.sh` as a low-level fallback preserved compatibility while moving
  recommended MCP configs to the refresh launcher.
- The installer already had a neutral install model, which made it natural to
  centralize refresh and delegate client-specific installs.

## What Worked Poorly

- The first solution put the refresh launcher in a host-local operations folder,
  which helped the current workspace but did not solve standalone client
  adoption.
- Client templates still pointed at `run.sh` or `run.cmd`, so newly configured
  clients could bypass refresh even after the public launcher existed.
- Windows templates needed an explicit `.cmd` refresh shim; otherwise Windows
  client configs would have remained on the non-refresh path.
- Some sync paths required parity updates while the legacy bash fallback still
  existed; after cross-platform evidence, that fallback was removed.

## What Was Not Explicit Enough

- "Update XUUnity MCP" must mean both the Unity package dependency and the
  installed host helper/server used by MCP clients.
- Recommended client configs should not launch low-level `run.sh` directly when
  a refreshable source checkout is available.
- Public standalone clients cannot depend on host-local `AIRoot`, `AIOutput`, or
  monorepo-specific wrappers.
- A package bump is incomplete until client startup can prove or restore helper
  alignment.

## What The Operator Needed But Did Not Have

- A public, installable refresh-before-run launcher.
- A durable marker connecting installed helpers back to the public source
  checkout.
- Client templates that make the safe launcher the default.
- Windows parity for the refresh path.
- Regression tests that fail when config templates or install output regress to
  plain `run.sh`/`run.cmd`.

## Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 88 | Unity execution was not the main failure; concurrent runs were broadly healthy. |
| Request journaling quality | 86 | Sufficient for lifecycle separation, though not central to this retro. |
| Bridge health observability | 88 | Status summaries clearly separated healthy MCP operation from test outcomes. |
| Wrapper-to-operator clarity | 82 | Improved after explicit helper refresh guidance and launcher promotion. |
| Recovery guidance quality | 90 | The required recovery command is now public and explicit. |
| Transport lifecycle transparency | 84 | Multi-instance evidence was good; distribution startup was the gap. |
| End-to-end trustworthiness during churn | 86 | Stronger now that startup can self-heal stale helper installs. |
| Parallel request handling | 90 | Multi-project evidence showed concurrent operation is viable. |
| Token efficiency of the default operator path | 84 | Better after compact summaries and direct version checks; still depends on release discipline. |
| Time-to-diagnosis | 82 | Initial host-local fix delayed recognition of standalone-client scope. |
| Validation workflow discipline | 92 | Syntax, whitespace, unit, and temp install smoke checks covered the final fix. |

Overall score after fixes: 88/100.

## Priority Improvements

- Implemented: add `run_installed_or_refresh_xuunity_mcp.sh` to the standalone
  public repo as a thin Python launcher.
- Implemented: move refresh/source-root/version comparison behavior into
  `run_installed_or_refresh_xuunity_mcp.py`.
- Implemented: add `run_installed_or_refresh_xuunity_mcp.cmd` so Windows MCP
  templates can use the refresh path.
- Implemented: make the installer deploy refresh launchers and write
  `.source_root` for source checkout discovery.
- Implemented: update Codex, Claude, Cursor, Windsurf, and generic MCP
  templates to launch the refresh path by default.
- Implemented: update Python launcher sync paths to include the refresh
  launcher and `.source_root`.
- Implemented: add regression tests for installer output, client config output,
  and installed refresh behavior.
- Implemented: add release checklist coverage for
  "source checkout -> installer -> client config -> refresh launcher -> neutral
  server version".
- Implemented: update downstream client docs so default MCP startup no longer
  recommends plain `run.sh` or `run.cmd`.
- Follow-up: during release closeout, verify that the new launchers are included
  in the public release/tag.

## Public-Promotion Recommendations

- Keep the refresh launcher and Windows shim in the public repo root.
- Keep `.sh` entrypoints thin; platform-sensitive MCP behavior belongs in
  Python with tests.
- Keep low-level `run.sh`, `run.cmd`, and `run.ps1` documented as fallback
  launchers, not the preferred MCP client command.
- Keep the rule in public docs: package pin updates and installed helper/server
  updates are one operational unit.
- Treat future client templates as failing review if they point to plain
  `run.sh`/`run.cmd` for default MCP startup.
- Keep release checklist coverage for "source checkout -> installer -> client
  config -> refresh launcher -> neutral server version" before publishing a tag.

## Final Verdict

The original issue was not a Unity execution failure; it was a public
distribution and client-startup contract gap. The implemented fix makes
standalone public clients self-heal stale helper installs without relying on
host-local monorepo paths. This retro is complete as public implemented history,
with release packaging/adoption verification left as the main residual risk.
