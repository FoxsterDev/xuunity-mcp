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
- Public shell entrypoints: `init_xuunity_light_unity_mcp.sh`, `xuunity_light_unity_mcp.sh`, `run_installed_or_refresh_xuunity_mcp.sh`; native Windows flavors: `xuunity_light_unity_mcp.cmd`, `xuunity_light_unity_mcp.ps1`, `run_installed_or_refresh_xuunity_mcp.cmd`, `templates/run.cmd`, `templates/run.ps1`

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

## Entrypoint Contract
- A selected router, protocol entrypoint, or start-session file is atomic context: load it from first line through EOF before applying it.
- A partial read, summary, excerpt, search hit, or fixed line window is not valid entrypoint loading.
- Keep default-loaded entrypoints lean and head-complete: the must-load rule, routing procedure, and output/execution contract must survive within the smallest head read window. Entrypoint adequacy is governed by the byte-complete-kernel invariant (`AIRoot/Modules/XUUnity/scripts/check_entrypoint_kernel.py`), not by a fixed line count.
- Put detailed rules, command catalogs, and matrices in explicitly routed owner files.
- Longer knowledge, review, skill, and reference files are valid only when trigger-loaded; they are not default entrypoints.

## Routing Rules
- For any task involving process management (process listing, checking liveness, or terminating processes/editors), load the safe process management skill: [SKILL.md](skills/safe_process_management/SKILL.md).
- For any task that writes or edits Python under `templates/`, the root `*.py` launchers, or tests asserting rendered commands/paths, load the cross-platform python skill: [SKILL.md](skills/cross_platform_python/SKILL.md). Windows/Ubuntu/macOS parity is a hard compatibility requirement for every Python change.
- For any task that writes or edits bash scripts, the shell wrapper, `.cmd`/`.ps1` launcher flavors, `templates/run.sh`, `scripts/testing/*.sh`, CI workflows, or tests that spawn shell processes — and for any failure that reproduces only on the Windows CI leg or only in CI — load the cross-platform shell skill: [SKILL.md](skills/cross_platform_shell/SKILL.md). Windows Git Bash support is a hard compatibility requirement for every shell change.
- For any task touching files another process polls (bridge state, inbox/outbox, journal, batch or scenario results) on either the Python or C# side, load the atomic IPC files skill: [SKILL.md](skills/atomic_ipc_files/SKILL.md).
- For any task editing the Unity editor package's tick-reachable code (`Editor/Bridge`, heartbeat, request pump, transport, scenario ticks), load the editor main-thread skill: [SKILL.md](skills/editor_main_thread/SKILL.md).
- For any release, version bump, tag creation, GitHub Actions failure, or follow-up fix after CI catches a platform-only regression, load the release CI guardrails skill: [SKILL.md](skills/release_ci_guardrails/SKILL.md).
- MCP `.sh` entrypoints must stay maximally thin. They may resolve the script directory, choose the Python interpreter, set launcher metadata, and `exec` Python. Do not put version parsing, source-root discovery, install refresh, process management, project traversal, JSON editing, or retry policy in bash; move that behavior into Python and cover it with tests.
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
