# XUUnity Light Unity MCP Public Retro Registry

Status: active public registry
Last triage: 2026-07-17 (re-evaluated against released source line `v0.3.47` plus current source)
Current released source line: `v0.3.47`

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

## Re-Evaluation 2026-07-17 (what is still actual for the end user)

The end user of this MCP is the AI-agent operator/developer who drives Unity
validation through it. Value here is ranked by how much a lesson reduces
false-positive validation, false-negative validation, token/result cost, or
install/readiness failure.

Re-checked against released `v0.3.47` plus current source, most of the prior
`active / needs-triage` list had actually shipped across `v0.3.32`-`v0.3.44`
and was simply never re-triaged. Eleven rows graduated to completed history in
this pass and two previously-unregistered 2026-06-09 Windows install artifacts
were added. Only **three themes remain genuinely open**, in priority order:

1. **P1 - SDK / EDM4U rollout validation lane (highest open ROI).**
   `2026-05-14_sdk_rollout_mcp_portfolio_retro.md`. A typed SDK-resolver lane
   with an active-Android-target precondition and resolver-freshness check, a
   generated-Gradle diff guard, a GUI process pool with quit-and-wait closeout,
   and a portfolio SDK-validation summary were the missing proof chain in
   `v0.3.44`. The Git-tracked guard shipped in `v0.3.45`; `v0.3.46` added
   XML/Gradle structure-aware comparison and comment-safe marker proof. Current
   source adds fingerprint-bound capture/comparison for Git-untracked generated
   outputs. Typed resolver freshness, artifact registration, and portfolio
   orchestration remain the standout false-positive-validation risk.

2. **P2 - Token-efficiency tail.**
   `2026-06-02_token_efficiency_response_envelope_retro.md` and
   `2026-06-11_token_accounting_and_fast_path_retro.md`. Compact-by-default
   envelopes are fully shipped (scenario, refresh, compile, test, status,
   `ensure-ready`, and batch, each with an `includeFullPayload` opt-in). What
   remains is broader multi-project compact ceilings, a real token-accounting
   ledger, a one-shot package-pin verifier, and fast-path prompt profiles.

3. **P2 - Cross-platform live-host proof.**
   `2026-06-17_windows_setup_failure_retro.md`. The Windows helper root causes
   are fixed and CI-exercised (MCP stdio e2e, installed delegate, PowerShell
   quickstart, file-IPC simulator, hostile codepage). A live Windows/Linux host
   session with a real Unity editor still needs execution proof. This is a
   ROADMAP Phase 3 breadth item, not a code gap.

No longer active (shipped and moved to completed history this pass): PlayMode
lifecycle-reset trust classification, UI-smoke semantic verdicts + path
coverage, batch-compile reliability + operator ergonomics, devmode batch
lifecycle, manual-open duplicate-launch guard, first-open Unity 6000
API-Updater modal + console-source diagnostics, the batchmode-blind
editor-startup freshness qualifier, the applied-mutation-vs-settle-timeout
verdict, bridge-declared-not-enabled auto-enable on first `ensure-ready`, and
the entire Windows install root-cause set (python3 delegation, UTF-8 BOM,
`os.kill` PID liveness, WSL/Windows discovery, process-kill safety).

## Active Public Retro Backlog / Needs Triage

| Date | File | Scope | Registry Status | Why It Is Not Completed History |
| --- | --- | --- | --- | --- |
| 2026-05-14 | `2026-05-14_sdk_rollout_mcp_portfolio_retro.md` | SDK/EDM4U rollout validation lane: typed resolver preconditions, generated-Gradle diff guard, GUI process pool + quit-and-wait closeout, portfolio SDK summary | **partially implemented - highest open end-user ROI (P1)** | `v0.3.45` shipped the Git-tracked `unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard`; `v0.3.46` shipped structure-aware/comment-safe hardening. Current source adds clean-tree capture plus project/Unity/package-lock/SDK-version fingerprinting for Git-untracked outputs, stale-fingerprint rejection, and snapshot-integrity proof. Still open: artifact-registry registration, typed Android resolver freshness/preconditions, GUI process pool, closeout contract, and portfolio summary. The referenced rollout plan remains retained-for-future; device lanes are ROADMAP Wave 5. |
| 2026-06-02 | `2026-06-02_token_efficiency_response_envelope_retro.md` | Response-envelope token efficiency: compact-by-default across MCP tool surfaces | mostly implemented; P2 residual | Compact-by-default shipped `v0.3.32`-`v0.3.44` for scenario, refresh, compile, build-config compile, test, `unity_status_summary`, `ensure-ready`, and batch CLI, each with `includeFullPayload`/`--output` opt-in (STATUS.md "Compact MCP envelopes"). Remaining (ROADMAP.md "Phase 2" residual): broader multi-project compact ceilings, a token ledger, and fast-path profiles. |
| 2026-06-11 | `2026-06-11_token_accounting_and_fast_path_retro.md` | Token-accounting ledger, one-shot package-pin verifier, fast-path prompt profile | partial; P2 | The biggest win (compact output) shipped through `v0.3.40`/`v0.3.44`, and the fast path is documented in `docs/agents/PACKAGE_BUMP_FAST_PATH.md`, but no token-accounting ledger, one-shot verify-package-pin verifier, or runner token-budget hints exist in source or ROADMAP/STATUS. Overlaps the response-envelope row above as the token-efficiency tail. |
| 2026-06-17 | `2026-06-17_windows_setup_failure_retro.md` | Native Windows setup failure postmortem; residual = live Windows/Linux host proof | Windows root causes fixed + CI-exercised in `v0.3.43`; live-host proof still open (P2) | The concrete Windows helper failures (path-with-spaces, ExecutionPolicy, `python3` delegation, PID liveness, discovery) are fixed and CI-exercised end to end. STATUS.md still marks a live Windows/Linux host session with a real Unity editor as needing execution proof (ROADMAP Phase 3 breadth). This row now tracks that single remaining cross-platform proof item; the Windows install root-cause retros (2026-06-09 v1/v2, 2026-06-10) are completed history. |

> Re-confirmed 2026-07-15 against `v0.3.45` plus current source: the response-envelope /
> token-efficiency backlog is no longer a blanket compile/refresh/test/status
> MCP-tool issue. Scenario verdicts, refresh/compile/build-config-compile/direct
> test responses, `unity_status_summary`, `ensure-ready`, and batch CLI output
> are all compact by default with full-payload opt-in, and compact batch
> summaries are held under a 500-byte per-project budget. What remains is
> broader multi-project compact ceilings, a token-accounting ledger, a one-shot
> package-pin verifier, and fast-path prompt profiles.

## Completed Public History

| Date | File | Scope | Registry Status | Notes |
| --- | --- | --- | --- | --- |
| 2026-07-15 | `2026-07-15_editmode_targeted_filter_zero_match_retro.md` | Direct EditMode test filter returns zero selected tests after external source edits | implemented and released in `v0.3.47` | Filtered zero totals persist and report `test_filter_no_match`, including direct counts, requested-filter summary, and one-refresh recovery guidance while transport delivery remains distinct. Consumer-project proof passed the cold-discovery targeted smoke plus package EditMode `16/16` and PlayMode `5/5` lanes. |
| 2026-07-10 | `2026-07-10_applied_mutation_settle_timeout_retro.md` | Scenario verdict: confirmed project-hook mutation vs immediately-following refresh-settle timeout | implemented and live-validated | Released in `v0.3.43` (`applied_mutation_settle_timeout`, `mutation_applied_unsettled`, mutation/settle summary in `templates/server_summary_scenario.py`; regression in `tests/test_scenario_decision_verdict.py` incl. non-applied/intervening-step guard). `v0.3.44` records live Unity validation passing (GUI-fallback compile matrix, EditMode/PlayMode), closing the prior "live validation pending" caveat. |
| 2026-07-06 | `2026-07-06_first_open_6000_upgrade_apiupdate_modal_and_console_source_retro.md` | First-open Unity 6000 API-Updater modal deadlock + stale-prone Console-buffer compile diagnostics | implemented | `v0.3.44`: `relaunch_noninteractive_accept_apiupdate` recovery + `possible_interactive_dialog_block` health hypothesis (`server_health.py`), console `source=editor_log` + stale-buffer warning (`XUUnityLightMcpConsoleTailOperation.cs`), first-open `-accept-apiupdate` construction and batchmode gate docs, and compact default transport envelopes. All four priority items shipped. |
| 2026-07-06 | `2026-07-06_bridge_declared_not_enabled_first_open_install_retro.md` | Package declared but bridge `bridge_disabled` on first open; separate `--enable-project` + reopen; setup-plan bundled user-scope client config | implemented | `ensure-ready --open-editor` now auto-enables the project-scoped bridge (CHANGELOG "auto-enable the project-scoped bridge"; `server_cli_commands.py` `reason="ensure_ready_open_editor_auto_enable"`; first-open bridge auto-enable regression). setup-plan/apply separate project config from user-scope client wiring; the manual-manifest/manual-open boundary is documented. |
| 2026-07-06 | `2026-07-06_batchmode_blind_to_editor_startup_reconcilers_retro.md` | Green-compile != editor-clean scope-limit gate + offline `editor_log_diagnosis` freshness qualifier | implemented | `v0.3.41`: offline/unverified `editor_log_diagnosis` carries `freshness_class`/`reflects_current_working_tree:false` (`server_health.py`); `SMOKE_TESTS.md` states the compile-gate scope limit and editor-startup-clean gate; Editor.log grep/tail docs call out untyped path-backed evidence. |
| 2026-06-25 | `2026-06-25_scenario_run_wait_compact_smoke_false_negative_retro.md` | scenario run-and-wait compact envelope versus full per-step payload evidence | implemented with follow-up watch | Implemented same day: compact payload-mode fields, structured full-payload recovery hints, public smoke full-payload opt-in, regression test, and docs. Keep watching real editor disappearance during PlayMode lifecycle smoke as infrastructure churn, not a contract issue. |
| 2026-06-24 | `2026-06-24_compile_progress_bar_not_cleared_unity2022_retro.md` | Unity 2022.3 compile/refresh progress-bar teardown | implemented; response-envelope portion split out | P0 `EditorUtility.ClearProgressBar()` fix shipped in `v0.3.31` for compile, refresh, build, and request-pump completion. The compact-response portion is tracked by the token-efficiency rows, not here. |
| 2026-06-18 | `2026-06-18_manual_open_editor_duplicate_launch_retro.md` | manual-open Unity editor duplicate launch guard | core implemented; low-ROI residue only | Fix released ~`v0.3.31` and present in `v0.3.44`: process-visibility fail-closed launch guard (`process_visibility_restricted_before_open`), `same_project_editor_running_bridge_not_ready` reconciliation, worker-only process reporting, `launch_decision` summary, and regression tests. Residual is low-ROI only: direct-CLI activation single-flight audit and uniform launch-decision summary fields. |
| 2026-06-16 | `2026-06-16_ui_playmode_smoke_operator_speed_retro.md` | UI PlayMode smoke: semantic verdict, path-coverage matrix, readiness failure classes | core implemented; minor residue | `v0.3.32` shipped the compact decision verdict with UI-smoke fields, path coverage, and startup/lobby/popup/precondition/cleanup failure classes (verified in `tests/test_scenario_decision_verdict.py`). Residual is low-ROI: a distinct cleanup-safe cancellation op and a standardized project-hook path-inventory template. |
| 2026-06-11 | `2026-06-11_standalone_client_auto_refresh_retro.md` | standalone client auto-refresh | implemented history | Sanitized reusable lessons from package/server alignment work; public launchers, installer, templates, and regression tests were updated. |
| 2026-06-10 | `2026-06-10_windows_process_kill_catastrophe_retro.md` | Windows process-kill catastrophe fixes + proposed `--dry-run` kill mode | fixes implemented; proposal superseded | The four root-cause fixes shipped and are codified in `skills/safe_process_management/SKILL.md` (`ctypes` argtypes/restype, msys/cygwin taskkill routing, PID identity gate `tests/test_editor_host_kill_identity.py`). The proposed `--dry-run` kill mode was superseded by the stricter identity-reverify whitelist that reports-never-kills unverified PIDs. |
| 2026-06-10 | `2026-06-10_portfolio_test_reporting_operator_ergonomics_retro.md` | portfolio test reporting operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio manifest/test validation. |
| 2026-06-09 | `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v1.md` | Windows install v1: `python3` delegation, UTF-8 BOM plan files, `os.kill` PID liveness | implemented (registered 2026-07-12) | All three helper issues fixed and released by the Windows waves through `v0.3.43`/`v0.3.44`: `resolve_python_bin()` (no bare `exec python3`), `utf-8-sig` plan decoding (`server_core.py`), and `pid_is_alive()` via Windows `OpenProcess`/`tasklist` fallbacks instead of raw `os.kill` (`server_host_platform.py`), with regression in `tests/test_windows_host_helpers.py`. Previously unregistered; source evidence for the `2026-06-17` Windows setup row. |
| 2026-06-09 | `2026-06-09_windows_INSTALL_RETRO_ARTIFACT_issue_v2.md` | Windows install v2: WSL/Windows Unity editor discovery + stale bridge state | superseded (registered 2026-07-12) | Overtaken by the `v0.3.43` Windows/discovery/recovery wave (cross-platform Unity discovery, host-native recovery commands, atomic IPC + process-identity checks, installed-delegate recovery e2e) and the `v0.3.44` fix so a forwarded `APPDATA` no longer misclassifies a POSIX host as Windows. Retro was pinned to `#v0.3.23`; previously unregistered. |
| 2026-06-08 | `2026-06-08_portfolio_batch_compile_operator_ergonomics_retro.md` | portfolio batch compile operator ergonomics | implemented history | Sanitized reusable lessons from host-private portfolio validation. |
| 2026-06-08 | `2026-06-08_project_action_hook_scaffold_retro.md` | project action hook scaffold retro | implemented history | Sanitized reusable lessons from a host-private hook authoring session. |
| 2026-06-07 | `2026-06-07_xuunity_mcp_batch_compile_reliability_retro.md` | batch compile reliability: fallback-aware aggregate, `operator_verdict`, compact CLI, byte guard | core implemented; low-priority marker deferred | Fallback-aware aggregate success (`8e93585`, `v0.3.40`), normalized `operator_verdict`, lane/license truth surfacing, bridge-disabled recovery commands, compact CLI (`--output compact`), and a 500-byte per-project compact guard all shipped. Remaining low-priority consideration: a stable `bridge_state`/`bridge_state_absent` marker in batch evidence when available. |
| 2026-05-26 | `2026-05-26_license_aware_batch_fallback_retro.md` | license-aware batch fallback retro | post-implementation history | File status is `post-implementation notes`. |
| 2026-05-23 | `2026-05-23_devmode_batch_lifecycle_retro.md` | devmode source-root, sandbox process visibility, closed-editor batch quit-vs-exit lifecycle | implemented | `v0.3.14` shipped closed-editor batch lifecycle hardening (`request-editor-quit --wait-for-exit`, `restore-editor-state --require-closed`, `process_visibility_restricted` diagnostics) and public source-root/package-mode preflight; hardened through `v0.3.30` (already-closed closeout fast path) and `v0.3.44` (lane selection blocks on unknown editor liveness). All eight priority items shipped. |
| 2026-05-23 | `2026-05-23_optional_capability_setup_wizard_retro.md` | optional capability setup wizard retro | post-implementation history | File status is `post-implementation retro`. |
| 2026-05-21 | `2026-05-21_project_hook_batch_build_operator_retro.md` | project-hook batch-build operator ergonomics: heartbeats, artifact probes, side-effect accounting, hook/reclassification summaries | implemented | Ergonomics landed in `f437cb8` (2026-05-21, in `v0.3.10+` through `v0.3.44`): `server_artifact_probe.py`, `server_workspace_effects.py`, `unity_batch_running` heartbeats, artifact-probe vs `build_succeeded` split, and `tests/test_batch_operator_ergonomics.py`. Reclassification-as-confirmation hardened through `v0.3.43`/`v0.3.44`. |
| 2026-05-15 | `2026-05-15_playmode_verdict_recovery_and_single_project_launch_retro.md` | PlayMode verdict and launch recovery | applied history | File status is `applied`; remaining ordinary risks are not tracked here as active backlog. |
| 2026-05-14 | `2026-05-14_startup_lifecycle_evidence_ergonomics_retro.md` | startup lifecycle evidence ergonomics | implemented history | Sanitized reusable lessons from a host-private startup/profile retro. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_retro_action_plan.md` | validation workflow action plan | implemented history | Action plan file status is `implemented`. |
| 2026-05-12 | `2026-05-12_mcp_validation_workflow_chat_retro.md` | validation workflow chat retro | completed intake/history | Intake retro whose action plan is tracked separately and marked implemented. |
| 2026-05-11 | `2026-05-11_chat_retro_playmode_lifecycle_reset.md` | PlayMode lifecycle-reset trust classification + retry smoke coverage | implemented | `result_trust_class` (`wrapper_failed_unity_unproven` / `unity_completed_after_lifecycle_reset` / `unity_failed_confirmed` / `unity_completed_confirmed`) in `server_bridge_final_status.py`, dedicated `run_playmode_lifecycle_retry_smoke.sh` + verdict-recovery proof suite, and `SMOKE_TESTS.md` troubleshooting branch. `v0.3.44` adds `unity_completed_host_delivery_unproven` accounting. All P0/P1/P2 shipped. |
| 2026-05-11 | `2026-05-11_operator_and_backend_lessons.md` | operator and backend lessons | historical lesson | Reusable distilled lesson retained for history. |
| 2026-05-09 | `2026-05-09_cleanup_and_regression_lessons.md` | cleanup and regression lessons | historical lesson | Reusable lesson retained for history. |
| 2026-05-07 | `2026-05-07_token_stability_and_summary_first_recovery_retro.md` | token stability and summary-first recovery | implemented history | Sanitized from host-private single-project evidence; private source removed after promotion. |
| undated | `xuunity_mcp_chat_retro.md` | legacy general MCP chat/session postmortem (PASS/EXCELLENT) | history; asks shipped | Both improvement asks are shipped: `no_tests` treated as an acceptable status (`run_multi_project.py` `acceptable_test_statuses={"passed","no_tests"}`) and compact-by-default final/latest surfaces (`v0.3.44`). Legacy wrapper terminology predates the current MCP tool surface; kept as history. |
| undated | `xuunity_mcp_install_retro.md` | legacy end-to-end install/verify/Android-compile success record (v0.3.21) | history; no open items | Clean happy-path install postmortem with zero open items; the described flow still exists and was hardened through `v0.3.42`-`v0.3.44`. No backlog to implement. |

## Prompt Templates

- `CHAT_RETRO_PROMPT.md`
- `INSTALL_RETRO_PROMPT.md`
