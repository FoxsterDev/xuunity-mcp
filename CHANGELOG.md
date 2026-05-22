# Changelog

## Unreleased

- Added wrapper help and agent workflow guidance for MCP `devmode` and `prodmode` package-source switching.
- Added client-specific MCP payload examples, structured evidence schema, and machine-readable workflow templates for agent validation workflows.

## 0.3.11

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
