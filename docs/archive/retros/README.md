# XUUnity Light Unity MCP Retros

Date: `2026-05-23`
Status: `active public retro index`

This folder holds public-safe retrospectives, lessons reports, and retro action
plans for reusable `XUUnity Light Unity MCP` work.

Use this folder when a new feature, validation workflow, or operator incident
produces reusable lessons without project-specific details. Project-specific
evidence, product names, local paths, private request ids, and consumer-project
business context should stay in project-local or host-local outputs.

Storage rule:

- Public-safe reusable MCP retros live here.
- Host-private, project-specific, or raw-evidence MCP retros belong in the
  host's single `Operations/XUUnityLightUnityMcp/Retros/` folder.
- Do not create per-project MCP retro folders.
- Do not place MCP retros in a broad host report bucket.
- Whenever a public retro is added, moved, renamed, or deleted, update
  `RETRO_REGISTRY.md` in the same change.

Registry rule:

- Active public backlog and status-unclear retros are listed first in
  `RETRO_REGISTRY.md`.
- Completed, implemented, applied, superseded, or history-only retros are listed
  separately as completed public history.
- Prompt templates are listed separately and are not backlog items.

When a retro produces an implementation plan, link the plan from
`../../architecture/designs/DESIGN_PLAN_HISTORY.md`. After implementation,
write or update a post-retro note that states:

- what went well
- what remained risky
- what validation proved
- what follow-up remains

## Active Backlog / Needs Triage

- `2026-05-11_chat_retro_playmode_lifecycle_reset.md`
- `2026-05-14_sdk_rollout_mcp_portfolio_retro.md`
- `2026-05-21_project_hook_batch_build_operator_retro.md`
- `2026-05-23_devmode_batch_lifecycle_retro.md`
- `2026-06-02_token_efficiency_response_envelope_retro.md`
- `2026-06-07_xuunity_mcp_batch_compile_reliability_retro.md`
- `xuunity_mcp_chat_retro.md`
- `xuunity_mcp_install_retro.md`

## Completed Public History

- `2026-05-07_token_stability_and_summary_first_recovery_retro.md`
- `2026-05-09_cleanup_and_regression_lessons.md`
- `2026-05-11_operator_and_backend_lessons.md`
- `2026-05-12_mcp_validation_workflow_chat_retro.md`
- `2026-05-12_mcp_validation_workflow_retro_action_plan.md`
- `2026-05-14_startup_lifecycle_evidence_ergonomics_retro.md`
- `2026-05-15_playmode_verdict_recovery_and_single_project_launch_retro.md`
- `2026-05-23_optional_capability_setup_wizard_retro.md`
- `2026-05-26_license_aware_batch_fallback_retro.md`
- `2026-06-08_portfolio_batch_compile_operator_ergonomics_retro.md`
- `2026-06-08_project_action_hook_scaffold_retro.md`

## Prompt Templates

- `CHAT_RETRO_PROMPT.md`
- `INSTALL_RETRO_PROMPT.md`
