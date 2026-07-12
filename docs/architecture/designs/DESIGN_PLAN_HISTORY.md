# XUUnity Light Unity MCP Design Plan History

Date: `2026-05-26`
Status: `active design-plan history index`

## Purpose

This file tracks public-safe MCP design plans, their implementation status, and
the closeout evidence that proved or constrained the work.

Use this index when a chat produces a concrete MCP implementation plan,
retro-derived action plan, or non-trivial operator-surface design. The plan may
live as a dedicated design note under `docs/architecture/designs/` or as a
retro action plan under `docs/archive/retros/`, but this history should link it
and state what happened.

## Status Vocabulary

- `design`: approved direction exists, implementation has not started.
- `implementing`: work is in progress.
- `implemented`: code/docs/tests landed for the intended scope.
- `partially implemented`: useful subset landed, known scope remains.
- `validated`: implementation passed the intended test or smoke evidence.
- `superseded`: replaced by a narrower or newer plan.
- `moved`: design moved to another module or layer.

## Required Plan Record

For each substantial plan, keep a public-safe record with:

- title and date
- source retro, chat, or design input when relevant
- status and owner layer
- planned public interfaces or docs
- implementation checklist
- validation evidence
- post-implementation self-review
- post-retro notes: what went well, what was risky, and what follow-up remains

Do not include project-private paths, product names, credentials, request ids,
or consumer-specific evidence in public `AIRoot` records. Keep those in
project-local or host-local outputs.

## Current Plan History

| Date | Plan | Status | Implementation / Evidence |
| --- | --- | --- | --- |
| 2026-07-12 | `XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md` | `partially implemented; portfolio evidence slice host-validated` | Landed normalized compile evidence, GUI-fallback matrix counters, shared aggregate/selector eligibility, fail-closed batch-result selection accounting, and compact license cache provenance/age. Host suite passed. Stale-negative recheck, launcher runtime diagnostics, and live Unity fallback proof remain deferred. |
| 2026-06-18 | `../../archive/retros/2026-06-18_manual_open_editor_duplicate_launch_retro.md` | `partially implemented` | Started manual-open editor duplicate-launch hardening. Landed process-visibility fail-closed behavior before host editor open, `same_project_editor_running_bridge_not_ready` reconciliation with `wait_for_bridge_or_recover_editor`, worker-only process reporting, agent serialization guidance, smoke/doc updates, and focused regression tests. Follow-up remains for direct CLI activation single-flight audit and uniform compact launch decision summaries. |
| 2026-06-18 | `XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_PLAN_2026-06-18.md` | `active plan; minimal fix set implemented` | Canonical Windows setup reliability plan for the 2026-06-17 native Windows incident. Keeps implemented consensus fixes and deferred work in one place: native `.cmd` Codex config, mismatch warning, `.cmd`-first docs, path-with-spaces diagnostics/tests, offline validation scope, package import-state diagnostics, `ensure-ready` unresolved-package advice, already-closed closeout fast path, plus deferred force quit, exact shell-cause attribution, keepalive/progress, and live Unity CI. |
| 2026-06-18 | `XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_IMPLEMENTATION_2026-06-18.md` | `implemented; host validated` | Closeout for the minimal Windows fix set. Validation: `git diff --check` and `python3 -m unittest discover -s tests -v` passed 243 tests on macOS, with the native-Windows `.cmd` smoke skipped as expected on this host. |
| 2026-06-11 | `XUUNITY_MCP_THIN_LAUNCHER_PYTHON_CORE_DESIGN_2026-06-11.md` | `implemented; Phase 4 cleanup complete` | Shrink all shell entrypoints (.sh/.cmd/.ps1) to <=30-line launchers, move wrapper resolves and multi-project orchestration into Python, replace `xargs -P` with ThreadPoolExecutor to restore Windows parallelism, add push/PR CI triggers plus cmd/ps1 smoke legs. Derived from the June 2026 Windows silent-hang incident; porting safety used golden-output baseline and command-by-command port behind a legacy flag. Phases 0-3 landed 2026-06-11: CI push/PR triggers + run.cmd/run.ps1 smoke steps, `templates/server_launcher.py` behind a thin `.sh` launcher plus new `.cmd`/`.ps1` wrapper siblings, `scripts/testing/run_multi_project.py` with ThreadPoolExecutor workers (xargs removed), shared `process_support.py`, golden parity tests plus cross-flavor parity and worker-overlap parallelism tests; 241 host tests green on macOS. Phase 4 completed after `v0.3.27` green Windows/macOS/Linux evidence: `xuunity_light_unity_mcp_legacy.sh`, `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER`, and the golden dual-run parity suite were removed. Cross-flavor parity, bash-spawn canary, and contract tests remain as regression guards. Known follow-up preserved during the port: in the GUI runner, a lifecycle/tests_busy retry re-run truncates the step stderr file and erases the `retrying after lifecycle reset` marker, so `*_retry_attempted` / `*_retry_budget_consumed` under-report after a retry. |
| 2026-06-09 | `XUUNITY_MCP_DECOUPLED_CLIENT_WIRING_DESIGN_2026-06-09.md` | `implemented; validated` | Decoupled client wiring and centralized installation launcher design. Dynamic OS standard paths (~/Library/Application Support/, %APPDATA%, $XDG_DATA_HOME), Python environment isolation (.venv), delegate wrappers (run.sh, server.py) in client-specific directories (.codex-tools, .claude-tools), and complete cleanup during uninstall full-reset. Validation: all delegate execution smoke-tested, installer runs successfully, uninstall-plan correctly targets all directories. |
| 2026-05-26 | `XUUNITY_MCP_LICENSE_AWARE_BATCH_FALLBACK_DESIGN_2026-05-26.md` | `implemented; host validated` | Added `license-capabilities`, `unity_license_capabilities`, batch probe/cache/classification, `--batch-fallback-mode auto/off/require-batch`, GUI fallback routing for public batch helpers, Unity-side `unity.build_player`, `request-build-player`, structured lane summaries, docs, tests, self-review, and post-retro notes. Validation: `scripts/testing/run_host_python_tests.sh` passed 133 tests. Live installed-editor matrix remains follow-up evidence. |
| 2026-05-23 | `XUUNITY_MCP_READ_ONLY_UI_PRIMITIVES_DESIGN_2026-05-23.md` | `design` | Operation-owned read-only UI primitives plan transferred from `Modules/AIReferenceWatch` reference-first evidence. Scope: `unity_ui_tree_snapshot`, `unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`; explicitly excludes click, wait_for, and live mutation. |
| 2026-05-23 | `XUUNITY_MCP_OPTIONAL_CAPABILITY_SETUP_WIZARD_DESIGN_2026-05-23.md` | `implemented; live-matrix validated` | Added optional Test Framework assembly, package metadata without hard Test Framework dependency, capability statuses, setup plan/apply/validate/install CLI, setup MCP tools, approved Unity-side Test Framework install operation, batch capability preflight, and explicit handling for missing/suitable/old/newer/upgrade-recommended Test Framework versions. Validation: `scripts/testing/run_host_python_tests.sh` passed 123 tests. Live clean-project matrix passed package EditMode `6/6` and PlayMode `5/5` on 7 runnable installed editors: `2021.3.58f1`, `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`, `6000.0.61f1`, `6000.2.14f1`, `6000.3.3f1`. `2021.3.45f2` is skipped on this host because Unity reports no valid editor license before package import. |
| 2026-05-23 | `XUUNITY_MCP_DEVMODE_BATCH_LIFECYCLE_HARDENING_DESIGN_2026-05-23.md` | `implemented; validated` | Added source-root preflight, process visibility diagnostics, `verify-editor-closed`, quit wait-for-exit, strict restore closeout, batch conflict guidance, launch diagnostics, docs, and tests. Validation: `scripts/testing/run_host_python_tests.sh` passed 106 tests. |
| 2026-05-21 | `XUUNITY_MCP_BATCH_OPERATOR_ERGONOMICS_DESIGN_2026-05-21.md` | `implemented and validated` | Batch progress, summaries, artifact probes, side-effect accounting, project-defined hook summaries, and operator verdicts. |
| 2026-05-16 | `XUUNITY_MCP_TEST_RESULT_ACCOUNTING_CONSISTENCY_DESIGN_2026-05-16.md` | `backlog design note` | Reviewed against current source; retained as consistency backlog. |
| 2026-05-15 | `XUUNITY_MCP_PLAYMODE_VERDICT_RECOVERY_DESIGN_2026-05-15.md` | `implemented-through-P2; proof-closed` | PlayMode verdict recovery and lifecycle reclassification proof landed through P2. |
| 2026-05-15 | `XUUNITY_MCP_EVIDENCE_ERGONOMICS_AND_PROFILE_FLOW_DESIGN_2026-05-15.md` | `partially implemented` | Evidence ergonomics landed in several summaries; profile-flow obligations remain partly design/backlog. |
| 2026-05-14 | `XUUNITY_MCP_SDK_ROLLOUT_VALIDATION_DESIGN_2026-05-14.md` | `design` | Public-safe SDK rollout validation direction retained for future implementation. |
| 2026-05-12 | `XUUNITY_MCP_PROJECT_VALIDATION_SUITE_DESIGN_2026-05-12.md` | `active public backlog/spec design` | Validation suite spec remains active backlog. |
| 2026-05-12 | `XUUNITY_MCP_UI_PRIMITIVES_DESIGN_2026-05-12.md` | `design proposal` | UI primitives contract proposal. |
| 2026-05-12 | `XUUNITY_MCP_UI_PRIMITIVES_AND_REFERENCE_WATCH_DESIGN_2026-05-12.md` | `superseded` | Split into separate UI primitives and reference-watch docs. |
| 2026-05-12 | `XUUNITY_MCP_REFERENCE_WATCH_DESIGN_2026-05-12.md` | `moved` | Moved to a narrower module. |

## Closeout Rule

After implementing a tracked plan:

1. update the plan status and implementation checklist
2. run a self-review over the code and docs touched by the plan
3. record validation evidence or explicit validation gaps
4. write or update a post-retro under `docs/archive/retros/` when the work came
   from a retro or exposed reusable lessons
5. update this history index before final closeout
