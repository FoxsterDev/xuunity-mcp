# XUUnity Light Unity MCP Design Plan History

Date: `2026-05-26`
Last re-review: `2026-07-12` (all design docs re-verified against released source line `v0.3.44`)
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

Re-review note (2026-07-12): every row below was re-verified against released
`v0.3.44`. Four previously-untracked design docs were added
(`MONOLITH_REDUCTION`, `SERVER_REFACTORING`, `PROJECT_DEFINED_HOOK_POLL_UNTIL`,
`DECISION_RECORD`) and five stale statuses were corrected
(`VALIDATION_VERDICT_COHERENCE`, `TEST_RESULT_ACCOUNTING_CONSISTENCY`,
`EVIDENCE_ERGONOMICS_AND_PROFILE_FLOW`, `PROJECT_VALIDATION_SUITE`,
`UI_PRIMITIVES`). The highest-value open designs are, in order: SDK rollout
validation lane (P1, editor-only P0 slice unbuilt), the test/refresh-lane
verdict-coherence trio (`TEST_RESULT_ACCOUNTING`, `EVIDENCE_ERGONOMICS`
refresh-timeout guidance, `VALIDATION_VERDICT_COHERENCE` launcher runtime), the
read-only UI primitives / project-validation-suite read+compose surface (P2),
and Windows/cross-platform live-host hardening (P2).

| Date | Plan | Status | Implementation / Evidence |
| --- | --- | --- | --- |
| 2026-07-12 | `XUUNITY_MCP_SDK_ROLLOUT_GATE_IMPLEMENTATION_PLAN_2026-07-12.md` | `design — build-ready; not started` | Top-tier implementation plan elaborating the 2026-05-14 SDK rollout direction into build-ready contracts, exact registration seams (three-registry rule, scenario dispatcher+validator mirror, capability gating, host CLI/tool wiring), a reuse map onto existing helpers (`dependency.verify` path/hash, artifact registry/probe, editor-host lifecycle quit-and-wait, `normalize_compile_evidence`), and P0→P2 phasing. do-first = `unity.sdk.generated_diff_guard` + a shared SDK path/hash helper (highest-ROI false-positive catch, smallest surface, atop the shipped `dependency.verify`). Hardened after an adversarial self-review (§14): git-HEAD baseline (not machine-local `Library/`), new-correct-state resolver-completion predicate (not old-marker-absence), structure-aware diff + presence-after markers (not substring), and a cross-process GUI-cap lease. Nothing built yet. |
| 2026-07-12 | `XUUNITY_MCP_VALIDATION_VERDICT_COHERENCE_DESIGN_2026-07-12.md` | `partially implemented; portfolio slice released + live-validated in v0.3.44` | Portfolio compile-evidence slice shipped in `v0.3.44`: `normalize_compile_evidence`, GUI-fallback matrix counters from the bridge payload, shared aggregate/`--from-batch-results` selector eligibility, fail-closed batch-result selection accounting, and compact license cache provenance/age (`scripts/testing/run_multi_project.py`, `tests/test_multi_project_batch_runner.py`). Live-validated (GUI-fallback matrix `6/6`; subset EditMode `778/778`, PlayMode `279/279`). Deferred: bounded stale-negative license recheck, and the launcher runtime-info op + removal of direct `python3` calls from the post-change smoke runner. |
| 2026-06-25 | `XUUNITY_MCP_MONOLITH_REDUCTION_FIRST_PRINCIPLES_PLAN_2026-06-25.md` | `mostly implemented (v0.3.33/0.3.34)` | Added 2026-07-12. Python server + Unity package monolith split shipped behind compatibility facades with parity baselines and size-report scripts: `server_bridge_runtime.py`, `server_editor_host.py`, `server_setup_wizard.py`, `server_summaries.py`, `server_specs.py`, and `server_cli_commands.py` decomposed into focused modules; `server_bridge_payloads.py` centralizes response shaping. Residual: `server_batch_orchestrator.py` (~2500 lines) still exceeds the plan's 1200-line hard-review threshold — the only server monolith not fully decomposed. |
| 2026-06-18 | `../../archive/retros/2026-06-18_manual_open_editor_duplicate_launch_retro.md` | `implemented; low-ROI residue only` | Manual-open editor duplicate-launch hardening: process-visibility fail-closed behavior before host editor open, `same_project_editor_running_bridge_not_ready` reconciliation with `wait_for_bridge_or_recover_editor`, worker-only process reporting, agent serialization guidance, smoke/doc updates, and regression tests, all released and present in `v0.3.44`. Low-ROI follow-up only: direct CLI activation single-flight audit and uniform compact launch-decision summaries. |
| 2026-06-18 | `XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_PLAN_2026-06-18.md` | `active plan; minimal fix set implemented` | Canonical Windows setup reliability plan for the 2026-06-17 native Windows incident. Keeps implemented consensus fixes and deferred work in one place: native `.cmd` Codex config, mismatch warning, `.cmd`-first docs, path-with-spaces diagnostics/tests, offline validation scope, package import-state diagnostics, `ensure-ready` unresolved-package advice, already-closed closeout fast path, plus deferred force quit, exact shell-cause attribution, keepalive/progress, and live Unity CI. |
| 2026-06-18 | `XUUNITY_MCP_WINDOWS_SETUP_RELIABILITY_IMPLEMENTATION_2026-06-18.md` | `implemented; host validated` | Closeout for the minimal Windows fix set. Validation: `git diff --check` and `python3 -m unittest discover -s tests -v` passed 243 tests on macOS, with the native-Windows `.cmd` smoke skipped as expected on this host. |
| 2026-06-12 | `XUUNITY_MCP_PROJECT_DEFINED_HOOK_POLL_UNTIL_DESIGN_2026-06-12.md` | `implemented; validated (v0.3.29)` | Added 2026-07-12. `project_defined_hook_poll_until` scenario op with predicate normalizer, summary promotion, cleanup/screenshot/console-tail, and synthetic validation scenarios shipped and validated in `v0.3.29` (`XUUnityLightMcpPollUntilStepNormalizer.cs`, `server_project_actions.py`); present through `v0.3.44`. Optional future nicety: broader predicate expression language. |
| 2026-06-11 | `XUUNITY_MCP_THIN_LAUNCHER_PYTHON_CORE_DESIGN_2026-06-11.md` | `implemented; Phase 4 cleanup complete` | Shrink all shell entrypoints (.sh/.cmd/.ps1) to <=30-line launchers, move wrapper resolves and multi-project orchestration into Python, replace `xargs -P` with ThreadPoolExecutor to restore Windows parallelism, add push/PR CI triggers plus cmd/ps1 smoke legs. Derived from the June 2026 Windows silent-hang incident; porting safety used golden-output baseline and command-by-command port behind a legacy flag. Phases 0-3 landed 2026-06-11: CI push/PR triggers + run.cmd/run.ps1 smoke steps, `templates/server_launcher.py` behind a thin `.sh` launcher plus new `.cmd`/`.ps1` wrapper siblings, `scripts/testing/run_multi_project.py` with ThreadPoolExecutor workers (xargs removed), shared `process_support.py`, golden parity tests plus cross-flavor parity and worker-overlap parallelism tests; 241 host tests green on macOS. Phase 4 completed after `v0.3.27` green Windows/macOS/Linux evidence: `xuunity_light_unity_mcp_legacy.sh`, `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER`, and the golden dual-run parity suite were removed. Cross-flavor parity, bash-spawn canary, and contract tests remain as regression guards. Known follow-up preserved during the port: in the GUI runner, a lifecycle/tests_busy retry re-run truncates the step stderr file and erases the `retrying after lifecycle reset` marker, so `*_retry_attempted` / `*_retry_budget_consumed` under-report after a retry. |
| 2026-06-09 | `XUUNITY_MCP_DECOUPLED_CLIENT_WIRING_DESIGN_2026-06-09.md` | `implemented; validated` | Decoupled client wiring and centralized installation launcher design. Dynamic OS standard paths (~/Library/Application Support/, %APPDATA%, $XDG_DATA_HOME), Python environment isolation (.venv), delegate wrappers (run.sh, server.py) in client-specific directories (.codex-tools, .claude-tools), and complete cleanup during uninstall full-reset. Validation: all delegate execution smoke-tested, installer runs successfully, uninstall-plan correctly targets all directories. The POSIX GUI-client startup regression introduced by the Windows launcher work was fixed in `v0.3.44`. |
| 2026-06-09 | `XUUNITY_MCP_SERVER_REFACTORING_DESIGN_2026-06-09.md` | `implemented; validated (v0.3.33)` | Added 2026-07-12. `server.py` split into `server_cli_parser.py` / `server_cli_commands.py` / `server_batch_orchestrator.py` / `server_process_launcher.py` under a ProcessLauncher DAG; `server.py` is a thin facade (`build_parser()` then `args.func(args)`), keeping public command and MCP tool contracts stable. Part of the `v0.3.33` monolith reduction; the module set has since grown further under the same topology. |
| 2026-05-26 | `XUUNITY_MCP_LICENSE_AWARE_BATCH_FALLBACK_DESIGN_2026-05-26.md` | `implemented; host validated` | Added `license-capabilities`, `unity_license_capabilities`, batch probe/cache/classification, `--batch-fallback-mode auto/off/require-batch`, GUI fallback routing for public batch helpers, Unity-side `unity.build_player`, `request-build-player`, structured lane summaries, docs, tests, self-review, and post-retro notes. Validation: `scripts/testing/run_host_python_tests.sh` passed 133 tests. Live installed-editor matrix remains follow-up evidence. |
| 2026-05-23 | `XUUNITY_MCP_READ_ONLY_UI_PRIMITIVES_DESIGN_2026-05-23.md` | `design` | Operation-owned read-only UI primitives plan transferred from `Modules/AIReferenceWatch` reference-first evidence. Scope: `unity_ui_tree_snapshot`, `unity_ui_query`, `unity_ui_exists`, `unity_ui_get_text`; explicitly excludes click, wait_for, and live mutation. |
| 2026-05-23 | `XUUNITY_MCP_OPTIONAL_CAPABILITY_SETUP_WIZARD_DESIGN_2026-05-23.md` | `implemented; live-matrix validated` | Added optional Test Framework assembly, package metadata without hard Test Framework dependency, capability statuses, setup plan/apply/validate/install CLI, setup MCP tools, approved Unity-side Test Framework install operation, batch capability preflight, and explicit handling for missing/suitable/old/newer/upgrade-recommended Test Framework versions. Validation: `scripts/testing/run_host_python_tests.sh` passed 123 tests. Live clean-project matrix passed package EditMode `6/6` and PlayMode `5/5` on 7 runnable installed editors: `2021.3.58f1`, `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`, `6000.0.61f1`, `6000.2.14f1`, `6000.3.3f1`. `2021.3.45f2` is skipped on this host because Unity reports no valid editor license before package import. |
| 2026-05-23 | `XUUNITY_MCP_DEVMODE_BATCH_LIFECYCLE_HARDENING_DESIGN_2026-05-23.md` | `implemented; validated` | Added source-root preflight, process visibility diagnostics, `verify-editor-closed`, quit wait-for-exit, strict restore closeout, batch conflict guidance, launch diagnostics, docs, and tests. Validation: `scripts/testing/run_host_python_tests.sh` passed 106 tests. |
| 2026-05-21 | `XUUNITY_MCP_BATCH_OPERATOR_ERGONOMICS_DESIGN_2026-05-21.md` | `implemented and validated` | Batch progress, summaries, artifact probes, side-effect accounting, project-defined hook summaries, and operator verdicts. |
| 2026-05-16 | `XUUNITY_MCP_TEST_RESULT_ACCOUNTING_CONSISTENCY_DESIGN_2026-05-16.md` | `partially implemented; test-lane accounting still open` | Re-review 2026-07-12: compact test envelopes, `operator_verdict`, and `no_tests` handling shipped, but the design's core target — `run_playmode`/`run_editmode` test-result accounting — is unshipped. The tests payload still overwrites `playmode_state_after_settle` with no source/trust class, and the persisted `test_results/<request_id>.json` artifact is not source-marked/reconciled. do-first: port the refresh-side post-settle PlayMode accounting into `normalize_tests_payload_from_lifecycle`. |
| 2026-05-15 | `XUUNITY_MCP_PLAYMODE_VERDICT_RECOVERY_DESIGN_2026-05-15.md` | `implemented; proof-closed` | PlayMode verdict recovery and lifecycle reclassification proof: durable artifact, host verdict summary, final/latest-status wiring, runtime-timeout classification, cleanup guidance, and smoke all shipped through P0/P1/P2. |
| 2026-05-15 | `XUUNITY_LIGHT_UNITY_MCP_DECISION_RECORD.md` | `decision record (current)` | Added 2026-07-12. Architecture/policy decision record, not an implementable checklist. Its policy bands (A/B/C) and disabled-by-default surfaces (arbitrary C#, broad reflection, package add/remove, broad asset/scene mutation, runtime in-game MCP, remote relay) still hold in `v0.3.44`. |
| 2026-05-15 | `XUUNITY_MCP_EVIDENCE_ERGONOMICS_AND_PROFILE_FLOW_DESIGN_2026-05-15.md` | `partially implemented` | Evidence ergonomics (`structured_timing`, `artifact_manifest`, several summaries) landed. Two design "Not implemented" rows remain: the P0 `project_refresh_timeout` recovery-guidance envelope (classify editor-failure vs package-settle vs compile-churn vs lost-accounting; add `recommended_next_action=request_status_summary_then_compile_gate` + "op may have completed" note) and the profile-flow obligations. |
| 2026-05-14 | `XUUNITY_MCP_SDK_ROLLOUT_VALIDATION_DESIGN_2026-05-14.md` | `direction — elaborated by the 2026-07-12 implementation plan` | Re-review 2026-07-12: entire Required Core Additions unbuilt in `v0.3.44`. Build-ready detail now lives in `XUUNITY_MCP_SDK_ROLLOUT_GATE_IMPLEMENTATION_PLAN_2026-07-12.md`; this doc remains the direction/rationale. Only pre-existing `unity.edm4u.resolve` (no active-Android-target enforcement) and `unity.sdk.dependency.verify` (no destructive-diff guard) exist. Unbuilt: typed `sdk.package_restore` + `sdk.android_resolve` (BuildTarget.Android enforcement + generated-output freshness), `batch-edm4u-resolve` async-resolver-owning closed-editor lane, `sdk.generated_diff_guard` (baseline/allowlist/suspicious-removal classification), and GUI process cap + quit-and-wait. Device/native/iOS layers are ROADMAP Wave 5. do-first: `sdk.generated_diff_guard` atop the shipped `dependency.verify` — highest-ROI false-positive catch, since dependency presence already passes while destructive generated-file changes go undetected. |
| 2026-05-12 | `XUUNITY_MCP_PROJECT_VALIDATION_SUITE_DESIGN_2026-05-12.md` | `partially implemented; suite compiler open` | Re-review 2026-07-12: the individual validation lanes exist as MCP tools/scenarios, but the declarative layer is unbuilt — the suite YAML spec, compiled execution plan + gap report, suite/plan v1 schemas, the `validation-suite-*` host commands, the generic suite compiler, and the NL draft compiler. do-first: the host suite compiler (parse suite YAML, validate lane kinds, resolve MCP/project capabilities, emit a runnable compiled plan or a typed gap report). |
| 2026-05-12 | `XUUNITY_MCP_UI_PRIMITIVES_DESIGN_2026-05-12.md` | `superseded` | Re-review 2026-07-12: the read-only slice was reframed into the 2026-05-23 `READ_ONLY_UI_PRIMITIVES` design (itself still unimplemented). This doc's unique remaining scope is Phase 3 action primitives (click/submit/input_text/select) + wait_for, which the successor explicitly excludes; that scope is deferred and unowned. |
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
