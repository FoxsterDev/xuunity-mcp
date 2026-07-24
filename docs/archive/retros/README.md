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
  host's single `<host-output-root>/Operations/XUUnityLightUnityMcp/Retros/` folder.
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

See `RETRO_REGISTRY.md` for the full triage, per-file status, and the
`2026-07-12` re-evaluation. The lists below mirror that registry; the registry
is authoritative.

## Active Backlog / Needs Triage

Only three open themes remain after the `2026-07-12` re-triage against released
`v0.3.44` (SDK rollout lane, token-efficiency tail, cross-platform live-host
proof):

- `2026-05-14_sdk_rollout_mcp_portfolio_retro.md` (P1 - highest open ROI)
- `2026-06-02_token_efficiency_response_envelope_retro.md` (P2 residual)
- `2026-06-11_token_accounting_and_fast_path_retro.md` (P2)
- `2026-06-17_windows_setup_failure_retro.md` (P2 - live-host proof only)

## Completed Public History

- `2026-05-07_token_stability_and_summary_first_recovery_retro.md`
- `2026-05-09_cleanup_and_regression_lessons.md`
- `2026-05-11_chat_retro_playmode_lifecycle_reset.md`
- `2026-05-11_operator_and_backend_lessons.md`
- `2026-05-12_mcp_validation_workflow_chat_retro.md`
- `2026-05-12_mcp_validation_workflow_retro_action_plan.md`
- `2026-05-14_startup_lifecycle_evidence_ergonomics_retro.md`
- `2026-05-15_playmode_verdict_recovery_and_single_project_launch_retro.md`
- `2026-05-21_project_hook_batch_build_operator_retro.md`
- `2026-05-23_devmode_batch_lifecycle_retro.md`
- `2026-05-23_optional_capability_setup_wizard_retro.md`
- `2026-05-26_license_aware_batch_fallback_retro.md`
- `2026-06-07_xuunity_mcp_batch_compile_reliability_retro.md`
- `2026-06-08_portfolio_batch_compile_operator_ergonomics_retro.md`
- `2026-06-08_project_action_hook_scaffold_retro.md`
- `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v1.md`
- `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v2.md`
- `2026-06-10_portfolio_test_reporting_operator_ergonomics_retro.md`
- `2026-06-10_windows_process_kill_catastrophe_retro.md`
- `2026-06-11_standalone_client_auto_refresh_retro.md`
- `2026-06-16_ui_playmode_smoke_operator_speed_retro.md`
- `2026-06-18_manual_open_editor_duplicate_launch_retro.md`
- `2026-06-24_compile_progress_bar_not_cleared_unity2022_retro.md`
- `2026-06-25_scenario_run_wait_compact_smoke_false_negative_retro.md`
- `2026-07-06_batchmode_blind_to_editor_startup_reconcilers_retro.md`
- `2026-07-06_bridge_declared_not_enabled_first_open_install_retro.md`
- `2026-07-06_first_open_6000_upgrade_apiupdate_modal_and_console_source_retro.md`
- `2026-07-10_applied_mutation_settle_timeout_retro.md`
- `xuunity_mcp_chat_retro.md`
- `xuunity_mcp_install_retro.md`

## Prompt Templates

- `CHAT_RETRO_PROMPT.md`
- `INSTALL_RETRO_PROMPT.md`
