# Changelog

## Unreleased

- Prepared `v0.3.14` package metadata with Unity `2021.3` as the default
  minimum and removed the hard `com.unity.test-framework` dependency.
- Added optional Test Framework capability wiring through asmdef Version
  Defines and `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY`.
- Added setup wizard commands and MCP tools for per-project setup planning,
  approved setup application, setup validation, and approved Test Framework
  installation.
- Added capability statuses for optional test support, including missing and
  too-old dependency states that do not make core MCP health fail.
- Fixed installed-helper setup planning so the default Git UPM dependency uses
  the package metadata version instead of falling back to `v0.0.0`.
- Added a README install simulation audit covering single-project, hub,
  mixed-version, nested-repo, and optional Test Framework setup paths.
- Added README guidance for collecting a sanitized chat retro before opening a
  GitHub issue about MCP setup or automation failures.
- Added an install-specific retro prompt for collecting structured MCP setup
  evidence before opening a GitHub issue.

## 0.3.13

Release tag: `v0.3.13`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.13
```

### Changed

- Restored Git UPM as the default production package source for project setup.
  `init_xuunity_light_unity_mcp.sh --enable-project` now enables the bridge
  without rewriting `Packages/manifest.json`.
- Kept local `file:` package wiring behind explicit wrapper mode switches only:
  `devmode` for local MCP package iteration and `prodmode` for returning to the
  published Git-backed source.
- Updated project-package alignment checks so a Git-pinned dependency is treated
  as the default healthy production state instead of warning about local-source
  expectations.
- Added a reusable clean-project Android APK smoke runner that creates a Unity
  project, installs the package from Git UPM, proves MCP readiness, restores
  the editor session, and runs a regular Unity batch APK build.
- Added Android Build Support preflight reporting for the clean-project smoke
  runner, including a structured fail-fast summary and an explicit
  `--allow-no-android` MCP-only readiness mode.
- Updated installer docs, client docs, AI integration docs, smoke contracts,
  and package examples to document the Git-default / devmode-only package
  source model consistently.

## 0.3.12

Release tag: `v0.3.12`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12
```

### Changed

- Moved the Unity package from `templates/unity-package` to the registry-native
  `packages/com.xuunity.light-mcp` path.
- Updated package metadata so Unity Package Manager and future package registries
  can identify the canonical package directory as `packages/com.xuunity.light-mcp`.
- Updated Git UPM install examples, local `file:` package examples, package
  discovery, installer wiring, wrapper `devmode` / `prodmode`, workflow
  templates, package manifests, and tests to use the new package path.
- Added the README preview banner asset and refreshed top-level install
  messaging around the new package path.

### Migration Notes

- New installs should use:
  `https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12`
- Local MCP development should use:
  `file:/absolute/path/to/xuunity-light-unity-mcp/packages/com.xuunity.light-mcp`
- Projects pinned to `v0.3.11` can continue using
  `templates/unity-package`; that old path is now migration-only.
- To migrate a Unity project, replace
  `?path=/templates/unity-package#v0.3.11` with
  `?path=/packages/com.xuunity.light-mcp#v0.3.12`, remove the
  `com.xuunity.light-mcp` entry from `Packages/packages-lock.json`, and let
  Unity re-resolve packages.

### Notes

- OpenUPM publication is still pending; Git UPM is the supported install route
  for this release.
- The package remains editor-only and disabled by default, with no player-build
  footprint by default.
- Post-tag documentation refinements may exist on `master`; the package release
  tag for Unity consumers remains `v0.3.12`.

## 0.3.11

- Added wrapper help and agent workflow guidance for MCP `devmode` and `prodmode` package-source switching.
- Added client-specific MCP payload examples, structured evidence schema, and machine-readable workflow templates for agent validation workflows.

- Replaced placeholder client docs with production-ready MCP configs for Claude Code, Claude Desktop, Cursor, Windsurf, Codex-style agents, and generic stdio MCP clients.
- Added reusable client config templates under `templates/clients/`.
- Added native Windows client config templates and `run.cmd`/`run.ps1` launchers.
- Replaced the zsh-only Unix launcher with a bash-compatible launcher for Linux/macOS.
- Expanded `docs/reference/FEATURES.md` with competitive differentiators and the full MCP/host helper surface.
- Clarified feature maturity levels, implementation evidence, and compatibility validation status in `docs/reference/FEATURES.md`.
- Clarified `docs/reference/COMPARISON.md` source confidence, maturity terminology, and validation caveats.
- Added `AndreySkyFoxSidorov/UnifiedUnityMCP` to `docs/reference/COMPARISON.md` as a broad but young Unity automation reference.
- Added `docs/agents/AGENT_WORKFLOWS.md` to close Priority 15 with production-grade example agent workflows for Unity validation, triage, scenario replay, SDK checks, batch lanes, recovery, and release closeout.
- Updated installer wording and Claude Code user-scope config generation for the production stdio path.

## 0.3.10

- Extracted XUUnity Light Unity MCP into a standalone public repository.
- Added landing README, `llms.txt`, discovery metadata, install guide, feature table, security model, glossary, and client setup docs.
- Updated package metadata to point at `FoxsterDev/xuunity-light-unity-mcp`.
- Preserved detailed legacy implementation notes in `docs/reference/STATUS.md`.

## 0.3.9

- Added Claude MCP wiring and robust batch matrix parsing in the source package.
- Preserved the working host-side server, Unity editor package, smoke runners, and package self-tests from the previous public-core layout.
