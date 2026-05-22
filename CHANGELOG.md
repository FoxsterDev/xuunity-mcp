# Changelog

## Unreleased

- Replaced placeholder client docs with production-ready MCP configs for Claude Code, Claude Desktop, Cursor, Windsurf, Codex-style agents, and generic stdio MCP clients.
- Added reusable client config templates under `templates/clients/`.
- Updated installer wording and Claude Code user-scope config generation for the production stdio path.

## 0.3.10

- Extracted XUUnity Light Unity MCP into a standalone public repository.
- Added landing README, `llms.txt`, discovery metadata, install guide, feature table, security model, glossary, and client setup docs.
- Updated package metadata to point at `FoxsterDev/xuunity-light-unity-mcp`.
- Preserved detailed legacy implementation notes in `STATUS.md`.

## 0.3.9

- Added Claude MCP wiring and robust batch matrix parsing in the source package.
- Preserved the working host-side server, Unity editor package, smoke runners, and package self-tests from the previous public-core layout.
