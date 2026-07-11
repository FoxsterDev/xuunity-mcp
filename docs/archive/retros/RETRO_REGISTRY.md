# XUUnity Light Unity MCP Public Retro Registry

Status: active public registry

Update this file whenever a public-safe MCP retro is added, moved, renamed, or
deleted. Host-private and project-specific retros belong in the host's single
`Operations/XUUnityLightUnityMcp/Retros/` folder and must be tracked by that
host-local registry.

## Storage Rule

- Public-safe reusable MCP retro: store in this folder and register here.
- Private/project-specific/raw MCP retro: store in the host-local MCP retro
  folder.
- Do not create per-project MCP retro folders.
- Do not store MCP retros in broad report buckets.

## Registry Design

- `Active Public Retro Backlog / Needs Triage` is the place to find public-safe
  retros that still look like backlog, action candidates, or status-unclear
  public work.
- `Completed Public History` is the place to find reusable lessons already
  implemented, applied, superseded, or retained only for history.
- Prompt templates are listed separately and are not backlog items.

## Active Public Retro Backlog / Needs Triage

| Date | File | Scope | Registry Status | Why It Is Not Completed History |
| --- | --- | --- | --- | --- |
| 2026-07-10 | `2026-07-10_applied_mutation_settle_timeout_retro.md` | Scenario verdict: distinguish a confirmed project-hook mutation from an immediately following refresh-settle timeout | implemented in unreleased source; release validation pending | Compact verdicts now keep the scenario inconclusive while separating `mutation_status=applied` from `settle_completion=unproven`, preventing a slow domain reload from being read as a failed mutation. |
| 2026-07-06 | `2026-07-06_first_open_6000_upgrade_apiupdate_modal_and_console_source_retro.md` | First-open 6000 upgrade: API-Updater modal deadlock when GUI opened without `-accept-apiupdate`, plus stale-prone Console-buffer diagnostics for compile errors after a domain reload | durable fix set implemented; broader token-ledger backlog remains in 2026-06 retros | Implemented modal-block health hypothesis + `relaunch_noninteractive_accept_apiupdate` recovery, path-backed `editor_log` default for grep and tail, explicit Console-buffer stale warnings, compact default transport/idle timeout envelopes with full-payload recovery hints, and first-open `-accept-apiupdate` command construction. |
| 2026-07-06 | `2026-07-06_bridge_declared_not_enabled_first_open_install_retro.md` | Install: package declared but bridge `bridge_disabled` on first open; project-only enable needs separate `init --enable-project` + editor reopen; `setup-plan` bundles user-scope client-config mutations | durable fix set implemented; manual-open stance documented | Implemented project-scoped bridge config auto-enable during `ensure-ready --open-editor`, kept setup-plan project setup mutations free of user-level client config writes, clarified optional client wiring review targets, and documented that manual manifest edits/manual Unity open can still leave the bridge disabled until project bridge config is enabled. |
| 2026-07-06 | `2026-07-06_batchmode_blind_to_editor_startup_reconcilers_retro.md` | Batchmode/player compile does not execute `[InitializeOnLoad]`/editor-startup reconcilers and excludes editor+test assemblies (green compile != editor clean); offline `health_probe` `editor_log_diagnosis` surfaced a prior-session compile block without a freshness qualifier | implemented public-safe lessons and wrapper qualifier | `SMOKE_TESTS` now states the compile-gate scope limit and editor-startup-clean gate; health output annotates offline/unverified `editor_log_diagnosis` freshness; Editor.log grep/tail docs call out untyped/path-backed evidence. Broader response-envelope/token-ledger work remains tracked by `2026-06-02_token_efficiency_response_envelope_retro.md` and `2026-06-11_token_accounting_and_fast_path_retro.md`. |
| 2026-06-17 | `2026-06-17_windows_setup_failure_retro.md` | Windows install: path-with-spaces truncation, `.ps1` ExecutionPolicy, ensure-ready bridge timeout, 37-min hang | minimal fix set implemented; broader work deferred | Code-grounded root cause record for recurring Windows setup failures. Implemented 2026-06-18: `.cmd`-first Windows docs, quoted Windows setup examples, ExecutionPolicy note, native Windows Codex config, `windows_codex_launcher_mismatch`, raw/resolved project-root diagnostics, path-with-spaces launcher test fixture, package import-state diagnostics in `validate-setup`/`ensure-ready`, unresolved-package clean-reopen advice, and already-closed editor closeout fast path. Deferred: exact shell-cause attribution, global wall-clock/progress keepalive work, bridge-independent force quit, and live Unity CI. |
| 2026-06-18 | `2026-06-18_manual_open_editor_duplicate_launch_retro.md` | manual-open Unity editor duplicate launch during same-host validation | partially implemented P0 lifecycle fix; follow-up remains | Implemented process-visibility fail-closed launch guard, manual-open/no-bridge reconciliation, worker-only process reporting, agent serialization guidance, and regression tests. Remaining follow-up: audit direct CLI activation single-flight and finish uniform compact launch decision summaries. |
| 2026-06-10 | `2026-06-10_windows_process_kill_catastrophe_retro.md` | Windows process kill catastrophe & dry-run proposal | historical safety context; follow-up deferred | Post-mortem of process termination bug and recommendation of dry-run mode for MCP client safety. Its safety constraints are carried into the 2026-06-18 Windows setup reliability plan; bridge-independent force recovery remains deferred rather than folded into the minimal fix set. |
| 2026-06-11 | `2026-06-11_token_accounting_and_fast_path_retro.md` | token accounting and package-bump fast path retro | active candidate | Recommends token ledger, compact MCP output, one-shot package-pin verifier, and fast-path prompt profile. |
| 2026-06-16 | `2026-06-16_ui_playmode_smoke_operator_speed_retro.md` | UI PlayMode smoke operator speed and proof quality | active design candidate | Public-safe promotion from host-private UI smoke retros; remaining work is semantic UI-smoke verdicts, path coverage matrix, startup/lobby/popup failure classes, and cleanup-safe cancellation. |
| 2026-05-11 | `2026-05-11_chat_retro_playmode_lifecycle_reset.md` | PlayMode lifecycle reset chat retro | needs triage | File status is `active public retro` and includes P0/P1/P2 priority improvements. |
| 2026-05-14 | `2026-05-14_sdk_rollout_mcp_portfolio_retro.md` | SDK rollout MCP portfolio retro | needs triage | Contains P0/P1 rollout, resolver, generated diff, process pool, and closeout-contract improvements. |
| 2026-05-21 | `2026-05-21_project_hook_batch_build_operator_retro.md` | project hook batch build operator retro | needs triage / partially superseded | Contains priority improvements; some may now be covered by current project-action and batch-summary work but the file has not been fully re-triaged. |
| 2026-05-23 | `2026-05-23_devmode_batch_lifecycle_retro.md` | devmode batch lifecycle retro | needs triage | Contains process-visibility and lifecycle priority improvements. |
| 2026-06-02 | `2026-06-02_token_efficiency_response_envelope_retro.md` | token efficiency response envelope retro | partially implemented; follow-up remains | Scenario verdict compacting shipped in `v0.3.32`; compact-by-default MCP tool summaries shipped for refresh, compile, build-config compile, direct test responses, and `unity_status_summary` with `includeFullPayload=true` full-payload opt-in. `v0.3.36` also makes `ensure-ready` compact by default and de-duplicates scenario `run_start.steps` unless step payloads are explicitly requested. `v0.3.39` adds opt-in `--output compact` for batch helper CLI responses, and unreleased source now bounds compact batch summaries with a 500-byte per-project regression guard plus compact default `transport_response_missing` / `editor_idle_timeout` failure envelopes. Remaining response-envelope work: broader multi-project compact ceilings, token ledger, and fast-path profiles. |
| 2026-06-07 | `2026-06-07_xuunity_mcp_batch_compile_reliability_retro.md` | batch compile reliability retro | core implemented; low-priority follow-up deferred | Implemented fallback-aware aggregate success logic, normalized `operator_verdict` values, lane/license truth surfacing, bridge-disabled recovery commands, compact batch CLI output, and a compact-output byte-budget guard. Remaining low-priority consideration: clearer stable bridge-state artifact reporting in batch evidence when available. |
| undated | `xuunity_mcp_chat_retro.md` | general MCP chat retro | legacy needs triage | Legacy retro has priority improvements that should be checked for implemented/superseded status. |
| undated | `xuunity_mcp_install_retro.md` | general MCP install retro | legacy hygiene/status triage | Legacy install retro should be reviewed for current public-safety and implemented/superseded status. |

> Still partly actual (re-confirmed 2026-06-29): the response-envelope /
> token-efficiency backlog in
> `2026-06-02_token_efficiency_response_envelope_retro.md` and
> `2026-06-11_token_accounting_and_fast_path_retro.md` remains open, but no
> longer as a blanket compile/refresh/test MCP-tool issue. Scenario verdicts
> are compact by default, refresh/compile/build-config-compile/direct-test
> MCP tools omit duplicated full `_xuunity_lifecycle` snapshots unless callers pass
> `includeFullPayload=true`, `unity_status_summary` omits nested
> discovery/transport/state-group/timing/artifact payloads by default, and
> `v0.3.36` compacts `ensure-ready` plus de-duplicates scenario
> `run_start.steps`, and `v0.3.39` adds opt-in compact output for batch helper
> CLI responses. Unreleased source now whitelists compact batch decision fields
> and guards successful compact summaries under a 500-byte per-project budget.
> Broader multi-project compact ceilings, token ledger, and fast-path profiles
> remain active backlog.

## Completed Public History

| Date | File | Scope | Registry Status | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-24 | `2026-06-24_compile_progress_bar_not_cleared_unity2022_retro.md` | Unity 2022.3 compile/refresh progress-bar teardown and compact-response follow-up | implemented with response-envelope follow-up split | P0 `EditorUtility.ClearProgressBar()` fix shipped in `v0.3.31` for compile, refresh, build, and request-pump completion. The compact-response portion is now tracked by the token-efficiency rows rather than this progress-bar row. |
| 2026-06-25 | `2026-06-25_scenario_run_wait_compact_smoke_false_negative_retro.md` | scenario run-and-wait compact envelope versus full per-step payload evidence | implemented with follow-up watch | Implemented same day: compact payload-mode fields, structured full-payload recovery hints, public smoke full-payload opt-in where step-level assertions parse raw fields, regression test, README/docs/tool-schema updates, and concrete devmode refresh guidance. Keep watching real Unity editor disappearance during PlayMode lifecycle smoke as infrastructure churn, not this contract issue. |
| 2026-05-07 | `2026-05-07_token_stability_and_summary_first_recovery_retro.md` | token stability and summary-first recovery | implemented history | Sanitized from host-private single-project evidence; private source removed after promotion. |
| 2026-05-09 | `2026-05-09_cleanup_and_regression_lessons.md` | cleanup and regression lessons | historical lesson | Reusable lesson retained for history. |
| 2026-05-11 | `2026-05-11_operator_and_backend_lessons.md` | operator and backend lessons | historical lesson | Reusable distilled lesson retained for history. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_chat_retro.md` | validation workflow chat retro | completed intake/history | Intake retro whose action plan is tracked separately and marked implemented. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_retro_action_plan.md` | validation workflow action plan | implemented history | Action plan file status is `implemented`. |
| 2026-05-14 | `2026-05-14_startup_lifecycle_evidence_ergonomics_retro.md` | startup lifecycle evidence ergonomics | implemented history | Sanitized reusable lessons from a host-private startup/profile retro. |
| 2026-05-15 | `2026-05-15_playmode_verdict_recovery_and_single_project_launch_retro.md` | PlayMode verdict and launch recovery | applied history | File status is `applied`; remaining ordinary risks are not tracked here as active backlog. |
| 2026-05-23 | `2026-05-23_optional_capability_setup_wizard_retro.md` | optional capability setup wizard retro | post-implementation history | File status is `post-implementation retro`. |
| 2026-05-26 | `2026-05-26_license_aware_batch_fallback_retro.md` | license-aware batch fallback retro | post-implementation history | File status is `post-implementation notes`. |
| 2026-06-08 | `2026-06-08_portfolio_batch_compile_operator_ergonomics_retro.md` | portfolio batch compile operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio validation. |
| 2026-06-08 | `2026-06-08_project_action_hook_scaffold_retro.md` | project action hook scaffold retro | implemented history | Sanitized reusable lessons from a host-private hook authoring session. |
| 2026-06-10 | `2026-06-10_portfolio_test_reporting_operator_ergonomics_retro.md` | portfolio test reporting operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio manifest/test validation. |
| 2026-06-11 | `2026-06-11_standalone_client_auto_refresh_retro.md` | standalone client auto-refresh | implemented history | Sanitized reusable lessons from package/server alignment work; public launchers, installer, templates, and regression tests were updated. |

## Prompt Templates

- `CHAT_RETRO_PROMPT.md`
- `INSTALL_RETRO_PROMPT.md`
