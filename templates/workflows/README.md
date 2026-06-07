# XUUnity Light Unity MCP Workflow Templates

Date: `2026-05-23`
Status: `current for v0.3.20`

This folder contains machine-readable agent workflow templates.

These files are planning and reporting artifacts for AI agents and local
wrappers. They are not Unity scenario JSON and are not executed directly by the
MCP server.

Files:

- `workflow.schema.json`
  - JSON schema for workflow template files.
- `evidence_summary.schema.json`
  - JSON schema for workflow closeout evidence.
- `readiness_gate.workflow.json`
  - First-contact readiness, capabilities, health, console, and scene checks.
- `post_change_validation.workflow.json`
  - Readiness, package refresh, compile, and EditMode validation after code edits.
- `package_mode_switch.workflow.json`
  - Wrapper-only `devmode` and `prodmode` package-source switching.

Use `../../docs/agents/AGENT_WORKFLOWS.md` for the human-readable playbooks and policy rules.

Current production package source for workflow evidence:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.20
```
