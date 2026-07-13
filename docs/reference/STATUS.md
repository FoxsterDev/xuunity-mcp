# Status

Date: `2026-07-10`
Status: `active public status snapshot`

XUUnity Light Unity MCP is a working same-host Unity Editor automation service
for MCP-capable AI agents. The current released source line is `v0.3.44`.

## Current Package

Unity package:

```text
com.xuunity.light-mcp
```

Current Git UPM URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.44
```

Current package path:

```text
packages/com.xuunity.light-mcp
```

Migration note:

- `v0.3.11` and earlier used `templates/unity-package`.
- `v0.3.12+` uses `packages/com.xuunity.light-mcp`.
- `v0.3.14+` keeps the default package metadata on Unity `2021.3` and makes
  Test Framework-backed operations optional.
- `v0.3.15+` adds license-aware batch fallback and Codex helper install-target
  selection.
- `v0.3.29+` adds project-defined hook poll-until scenarios and richer compact
  scenario summaries.
- `v0.3.32+` makes `unity_scenario_run_and_wait` a compact decision-verdict
  surface by default, with lifecycle relaunch attribution and full-payload
  opt-in.
- `v0.3.34+` makes refresh, compile, build-config compile, and direct test MCP
  responses compact by default while preserving authoritative post-settle
  verdict fields and `includeFullPayload=true` recovery.
- Current source qualifies refresh `playmode_state_after_settle` with explicit
  source/trust metadata; bridge identity churn yields `stale_risk` and directs
  PlayMode-sensitive callers to confirm via `unity_playmode_state`.
- Current source also keeps a terminal scenario inconclusive when a confirmed
  project-hook `*_applied` mutation is followed by a refresh-settle timeout,
  while explicitly separating the applied mutation from the unproven settle.
- `v0.3.38+` makes `unity_status_summary` compact by default for MCP callers,
  with `payload_mode` markers and full nested diagnostics available through
  `includeFullPayload=true`.
- `v0.3.39+` adds opt-in compact output for batch helper CLI commands through
  `--output compact`, while preserving `--output full` as the default.
- `v0.3.36+` makes `ensure-ready` compact by default,
  adds active editor-log identity and path-backed `editor_log` grep, removes
  duplicated scenario `run_start.steps` unless `includeStepPayloads=true`,
  adds post-change validation phase/churn dashboard output, and ships a
  public-safe config-applying project-action build template.
- The old path is kept only as a migration pointer for users pinned to
  `v0.3.11`.

OpenUPM status:

- the package layout is OpenUPM-ready
- the package is not documented as published on OpenUPM yet
- use Git UPM until the OpenUPM package page exists

## Current Surface

Current-source SDK rollout safety (unreleased):

- `unity_sdk_generated_diff_guard` / `sdk-generated-diff-guard` provides the
  Git-tracked generated-file vertical slice of the SDK rollout gate. It is a
  host-side, compact proof that detects missing required markers, stale expected
  versions, and unallowlisted changes without opening Unity. Resolver freshness,
  package restore, GUI admission control, and portfolio orchestration remain
  separate open slices.

Implemented Unity-side operations:

- `unity.status`
- `unity.capabilities.get`
- `unity.health.probe`
- `unity.build_target.get`
- `unity.build_target.switch`
- `unity.editor.quit`
- `unity.project.refresh`
- `unity.package.install_test_framework`
- `unity.edm4u.resolve`
- `unity.sdk.dependency.verify`
- `unity.console.tail`
- `unity.console.grep`
- `unity.scene.snapshot`
- `unity.scene.open`
- `unity.scene.assert`
- `unity.tests.run_editmode`
- `unity.tests.run_playmode`
- `unity.playmode.state`
- `unity.playmode.set`
- `unity.game_view.configure`
- `unity.game_view.screenshot`
- `unity.compile.player_scripts`
- `unity.compile.matrix`
- `unity.build_player`
- `unity.scenario.validate`
- `unity.scenario.run`
- `unity.scenario.result`

Implemented Unity-side scenario step families include status, health probe,
project refresh, scene open/snapshot/assert, console grep, compile, tests, Play
Mode, Game View, waits, project-defined hooks, poll-until hooks, and
catalog-backed `project_action` steps.

Implemented host-side MCP tools and helpers:

- `unity_status`
- `unity_license_capabilities`
- `unity_status_summary`
- `unity_capabilities`
- `unity_health_probe`
- `unity_console_tail`
- `unity_console_grep`
- `unity_loading_timing`
- `unity_scene_snapshot`
- `unity_scene_open`
- `unity_scene_assert`
- `unity_compile_player_scripts`
- `unity_compile_matrix`
- `unity_tests_run_editmode`
- `unity_tests_run_playmode`
- `unity_playmode_state`
- `unity_playmode_set`
- `unity_build_player`
- `unity_game_view_configure`
- `unity_game_view_screenshot`
- `unity_project_refresh`
- `unity_build_target_get`
- `unity_build_target_switch`
- `unity_edm4u_resolve`
- `unity_sdk_dependency_verify`
- `unity_sdk_generated_diff_guard`
- `xuunity_setup_plan`
- `xuunity_setup_apply`
- `xuunity_setup_validate`
- `xuunity_uninstall_plan`
- `xuunity_uninstall_apply`
- `unity_package_install_test_framework`
- `unity_request_final_status`
- `unity_scenario_result_summary`
- `unity_scenario_results_list`
- `unity_scenario_result_latest`
- `unity_scenario_run_and_wait`
- `unity_compile_build_config_matrix`
- `unity_project_action_list`
- `unity_project_action_invoke`
- `unity_artifact_register`
- `unity_artifact_write_report`
- `unity_maintenance_prune`
- `project-discovery-report`
- `registry-context-report`
- `registry-prune-contexts`
- `setup-plan`
- `setup-apply`
- `uninstall-plan`
- `uninstall-apply`
- `validate-setup`
- `install-test-framework`
- `license-capabilities`
- `open-editor`
- `ensure-ready`
- `recover-editor-session`
- `restore-editor-state`
- `request-status-summary`
- `request-final-status`
- `request-latest-status`
- `request-cancel`
- `request-stale-cleanup`
- `request-console-grep`
- `request-loading-timing`
- `request-build-player`
- `batch-compile`
- `batch-compile-matrix`
- `batch-build-config-compile-matrix`
- `batch-editmode-tests`
- `batch-test-framework-version-regression`
- `batch-build-player`
- `project-action-list`
- `project-action-invoke`
- `project-hook-scaffold`
- `artifact-register`
- `artifact-write-report`
- `artifact-probe`
- `sdk-generated-diff-guard`

## Current Validation Evidence

Latest source validation for `v0.3.44`:

| Area | Evidence | Result |
| --- | --- | --- |
| Package metadata | `packages/com.xuunity.light-mcp/package.json` | `name=com.xuunity.light-mcp`, `version=0.3.44`, `unity=2021.3`, no hard Test Framework dependency |
| Host Python tests | `python3 -m unittest discover -s tests` | `430` tests passed for `v0.3.44`, with `13` expected skips |
| Compact MCP envelopes | Changelog and regression coverage for `0.3.32`-`0.3.44` | Scenario decision verdicts, compact operation/readiness/status summaries, authoritative post-settle compile/test/refresh fields, editor-log identity, scenario step-payload opt-ins, PlayMode already-playing stale-risk summaries, deterministic scene-open setup, opt-in compact batch helper output, safer `Editor.log` console grep/tail defaults, compact transport/idle timeout errors, compile-first post-change validation, and lane-agnostic GUI-fallback compile evidence are documented with full-payload recovery. |
| Package self-tests | Clean devmode projects on installed Unity editors | Current release-line source validation passed package EditMode and PlayMode self-test lanes across Unity `2022.3` and `6000.x` consumer projects, including deterministic scene-open self-tests. |
| Public site checks | `scripts/testing/run_site_ui_checks.sh` | Public site Playwright checks passed for `v0.3.44`: `39/39`. |
| Historical Git UPM release smoke | Clean Unity project pinned to an earlier public tag | Bridge reached healthy `git_pinned` status, Android APK smoke passed, package self-tests passed, and closeout verified process exit. |
| Multi-project compile matrix | Public summary evidence from consumer validation | `9/9` projects, `38/38` compile lanes, `0` failures |
| Git tag visibility | Remote Git refs | Release tag `v0.3.44` is the current Git UPM release target; remote publication requires an authenticated push. |

Cross-platform status:

| Target | Status | Notes |
| --- | --- | --- |
| macOS host tools | `validated on this host` | Shell wrapper, host tests, same-host Unity readiness/status/health probes, and post-change validation route passed. |
| Linux host tools | `portable by design` | Bash-compatible launchers/templates exist; run a Linux Unity smoke before claiming live proof. |
| Native Windows clients | `templates provided; CI-exercised` | `run.cmd`, `run.ps1`, and Windows client configs exist; the Windows CI leg drives the real `.cmd` launcher through MCP stdio `initialize`/`tools/list`/`tools/call` end to end (`tests/test_mcp_stdio_e2e.py`), incl. a Cyrillic+spaces project path, plus: a real install through the refresh launcher serving MCP from the installed copy and a spawn of the exact command written by `--install-claude-config` (`tests/test_installed_delegate_e2e.py`), the verbatim README PowerShell 5.1 quickstart with a UTF-16 plan file (`tests/test_readme_quickstart_windows_e2e.py`), the file-IPC transport against a live editor-simulator process incl. a two-process torn-read stress (`tests/test_file_ipc_bridge_simulator_e2e.py`), and cp866/cp1252 hostile-codepage legs (`tests/test_ru_console_codepage_e2e.py`); a live Windows host session with a real Unity editor still needs execution proof. |
| Unity 2021.3+ | `default package line` | Checked-in package metadata targets Unity `2021.3`; setup wizard chooses optional Test Framework recommendations per project. |
| Optional Test Framework | `capability-gated` | Core readiness stays healthy when missing; tests report `disabled_missing_dependency`, `disabled_dependency_too_old`, or supported with `upgrade_recommended` when an existing dependency should be reviewed. |
| License-aware batch fallback | `implemented; host validated` | `license-capabilities` reports batchmode support, blocker code, probe log, and recommended lane. `batch-*` commands default to `--batch-fallback-mode auto` and emit lane summary fields. Live installed-editor matrix remains follow-up evidence. |

## Package Source Modes

Use Git UPM for production consumers:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.44"
  }
}
```

Use local `file:` only while developing this MCP package:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp"
  }
}
```

Mode switch helpers:

```bash
bash xuunity_light_unity_mcp.sh devmode --project-root /path/to/UnityProject
bash xuunity_light_unity_mcp.sh prodmode --project-root /path/to/UnityProject
```

Rules:

- `devmode` points a Unity project at the local package working tree.
- `prodmode` pins the Unity project to the published release tag that matches
  the package version, for example `#v0.3.44`.
- `prodmode` refuses to pin when that release tag is not visible on `origin`.
- both modes remove the package lock entry so Unity re-resolves honestly.

## Install And Smoke Commands

Install host helper:

```bash
bash init_xuunity_light_unity_mcp.sh
```

Enable one project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

Readiness check:

```bash
bash xuunity_light_unity_mcp.sh ensure-ready \
  --project-root /path/to/UnityProject \
  --open-editor \
  --background-open
```

Package self-test lane:

```bash
templates/smoke/run_package_self_tests.sh \
  --project-root /path/to/UnityProject \
  --mode all
```

Multi-project compile matrix:

```bash
scripts/testing/run_multi_project_batch_compile_matrix.sh \
  --repo-root /path/to/repo-with-unity-projects \
  --parallelism 4
```

## Safety Status

Current safety guarantees:

- editor-only package assembly
- disabled-by-default bridge activation
- no normal player-build footprint by default
- no dynamic Roslyn execution path
- no SignalR or external relay dependency
- local same-host transport model
- capability-gated reflection-sensitive operations
- mutable bridge/request artifacts stay under `Library/XUUnityLightMcp/`

Current limitations:

- OpenUPM publication is still pending
- Linux and native Windows need live host smoke proof before strong support claims
- Game View operations remain reflection-gated and must be capability-probed
- License-aware batch fallback is host-capability based; unknown probe failures
  keep batch as a diagnostic path instead of pretending GUI fallback is safe
- device/runtime automation is outside the base package
- broad unrestricted editor mutation is intentionally out of scope

## Related Docs

- `../../INSTALL.md`
- `FEATURES.md`
- `../../SECURITY.md`
- `COMPARISON.md`
- `DISCOVERY.md`
- `../agents/AI_INTEGRATION.md`
- `../agents/AGENT_WORKFLOWS.md`
- `../operations/BUILD_AUTOMATION.md`
- `../operations/SMOKE_TESTS.md`
- `../architecture/ROADMAP.md`
