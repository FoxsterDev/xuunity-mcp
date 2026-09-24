# XUUnity Light Unity MCP Workflow Templates

Date: `2026-05-23`
Status: `current for v0.3.80`

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
- `validation_plan.schema.json`
  - Owner-approved release validation plan: one row per required proof with exact stage, channel and dimensions.
- `validation_receipts.schema.json`
  - Evidence receipts joined to plan rows; `evidenceKind: helper_response` lets the evaluator decode saved helper responses.
- `validation_acceptance.schema.json`
  - Acceptance report emitted by `scripts/testing/evaluate_validation_evidence.py`; required counts always sum to the plan denominator.

Use `../../docs/agents/AGENT_WORKFLOWS.md` for the human-readable playbooks and policy rules.

The three `validation_*` schemas are generated from the strict specs in
`scripts/testing/validation_acceptance.py`; `tests/test_validation_acceptance.py`
fails when a schema file and its spec drift apart.

Current production package source for workflow evidence:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.80
```
