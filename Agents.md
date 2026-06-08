# Project Agent Router: XUUnityLightUnityMcp

## Purpose
This file is the project-level routing layer for `XUUnityLightUnityMcp`.
Use it when a session starts from this MCP repo, or when a host repo task targets
`AIRoot/Operations/XUUnityLightUnityMcp/` from a parent workspace.

## Project Context
- Project: `XUUnityLightUnityMcp`
- Project kind: public Unity MCP tooling repo
- Standalone public repo root: this directory
- Optional host-mounted path in `AIFoxsterDevHub`: `AIRoot/Operations/XUUnityLightUnityMcp/`
- Unity package source: `packages/com.xuunity.light-mcp/`
- Client setup docs: `docs/clients/`
- Agent workflow docs: `docs/agents/`
- Templates: `templates/`
- AI/public discovery files: `llms.txt`, `mcp-server.json`
- Public shell entrypoints: `init_xuunity_light_unity_mcp.sh`, `xuunity_light_unity_mcp.sh`

## Mode Detection
- Standalone mode: `../../../Agents.md` is absent or does not describe the active workspace. Use this file and local repo docs as the full routing contract.
- Host-mounted mode: `../../../Agents.md`, `../../Modules/XUUnity/`, and optionally `../../../AIModules/XUUnityInternal/` exist. Load host routing only for parent-workspace context.
- Never require `AIFoxsterDevHub`, `AIRoot/Modules/XUUnity/`, host-local overlays, or project-local `Assets/AIOutput/` memory for normal standalone work in this public repo.

## Load Order
1. This file
2. Root public entrypoints: `README.md`, `INSTALL.md`, `llms.txt`, `mcp-server.json`, `SECURITY.md`, `CHANGELOG.md` only when relevant
3. Relevant MCP docs under `docs/agents/`, `docs/operations/`, `docs/reference/`, or `docs/clients/`
4. Relevant package, script, template, or test files from this repo
5. Host repo router at `../../../Agents.md` only when this repo is mounted under `AIFoxsterDevHub` and the task needs parent-workspace routing
6. Public `xuunity` core from `../../Modules/XUUnity/` only when present and useful for Unity package behavior, validation flows, runtime safety, SDK-style integration, or review
7. Host-local overlay from `../../../AIModules/XUUnityInternal/` only when present and the task needs host topology, nested-repo routing, or parent-workspace validation

If this repo is used outside `AIFoxsterDevHub`, skip missing host paths and use
this router plus the local docs as the source of truth.

## Routing Rules
- For client setup tasks, load `docs/clients/Agents.md` when it exists, then the requested client guide.
- For AI integration or workflow tasks, load `docs/agents/AI_INTEGRATION.md` or `docs/agents/AGENT_WORKFLOWS.md` as appropriate.
- For Unity package implementation, edit `packages/com.xuunity.light-mcp/` and validate through the repo's test or smoke guidance.
- For installer, wrapper, setup-plan/setup-apply, or uninstall-plan/uninstall-apply behavior, work in `scripts/`, `templates/`, and the root shell entrypoints.
- For parent-workspace tasks, keep `XUUnityLightUnityMcp` as the implementation target and state any external Unity project used only as a validation target.
- For public documentation, keep examples generic and public-safe. Do not add host-private paths, credentials, project names, or local workstation assumptions unless the task is explicitly host-local.
- For public site UX/UI, discovery, SEO, article, or docs navigation work under `docs/`, run the static checks plus `scripts/testing/run_site_ui_checks.sh` before final handoff when Node is available. Use the generated Playwright HTML report, JSON/JUnit results, failure screenshots, traces, and attached viewport screenshots to diagnose visual, overflow, accessibility, CTA, and route regressions.

## Git Boundary
- In standalone mode, this directory is the git repo root.
- In `AIFoxsterDevHub`, `AIRoot/Operations/XUUnityLightUnityMcp/` is a nested git repo inside `AIRoot/`.
- Review, status, commits, and tags for MCP changes should be handled from the MCP repo root, not only from `AIFoxsterDevHub` or `AIRoot`.
