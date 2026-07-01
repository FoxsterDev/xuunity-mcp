# Changelog

## Unreleased

## 0.3.35

Release tag: `v0.3.35`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.35
```

### Changed

- Released `v0.3.35` package metadata, server metadata, package manifests, Git
  UPM examples, public site version references, and package documentation.
- `unity_status_summary` now defaults to a compact polling payload for MCP
  callers and omits nested discovery, transport, state-group, timing, and
  artifact details unless `includeFullPayload=true` is provided. The compact
  payload keeps the decision fields needed for readiness, recovery, compiler
  state, lifecycle stabilization, host health, reconciliation, and process
  visibility.
- Added explicit `payload_mode=compact_status_summary` /
  `payload_mode=full_status_summary` markers so agents can tell whether nested
  diagnostics were intentionally omitted.
- Added `includeFullPayload` to the `unity_status_summary` tool schema and
  preserved the full previous nested summary shape for deep lifecycle and
  transport debugging.
- Kept the CLI `request-status-summary` helper on its existing full diagnostic
  default so shell smokes and local wrapper scripts continue to parse nested
  prerequisite fields without migration churn.
- Updated the token-efficiency retro registry to mark status-summary slimming
  complete and leave only batch/multi-project compact ceilings, token ledger,
  and fast-path profiles as remaining response-envelope backlog.

### Validation

- Release version consistency check passed for `0.3.35`.
- Source checkout helper install refreshed neutral, Codex, and Claude tool
  installs; all reported package metadata version `0.3.35`.
- Host Python unittest suite: `267` tests passed with `1` expected skip.
- Public site Playwright checks passed: `39/39`.

## 0.3.34

Release tag: `v0.3.34`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.34
```

### Changed

- Released `v0.3.34` package metadata, server metadata, package manifests, and Git UPM examples.
- MCP tool responses for `unity_project_refresh`,
  `unity_compile_player_scripts`, `unity_compile_matrix`,
  `unity_compile_build_config_matrix`, `unity_tests_run_editmode`, and
  `unity_tests_run_playmode` now default to a compact operation summary that
  preserves authoritative post-settle verdict fields while omitting full
  `_xuunity_lifecycle` snapshots. Pass `includeFullPayload=true` to recover the
  previous full bridge payload for lifecycle debugging or raw artifact
  inspection.
- Compact operation summaries keep the authoritative post-settle verdict fields
  that agents need for closeout: status, error counts, first diagnostics,
  settle phase, completion basis, timing/artifact references, and full-payload
  recovery arguments.
- The compact/full bridge response conversion is centralized in
  `templates/server_bridge_payloads.py`, reducing duplicated response shaping
  across refresh, compile, build-config compile, and direct EditMode/PlayMode
  test tools.
- Public docs and retro registries were updated to record that normal MCP tool
  calls no longer dump lifecycle snapshots by default.

### Validation

- Host Python unittest suite: `267` tests passed with `1` expected skip.
- Release version consistency check passed for `0.3.34`.
- Public site Playwright checks passed: `39/39`.
- Source checkout helper install refreshed neutral, Codex, and Claude tool
  installs; all reported package metadata version `0.3.34`.
- Live MCP compact response validation passed on Dev Acceleration System and
  ApperfunHub, including post-settle compile truth without default lifecycle
  dumps.
- Dev Acceleration System package self-test fast lane passed: EditMode `12/12`
  and PlayMode `5/5`.

## 0.3.33

Release tag: `v0.3.33`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.33
```

### Changed

- Released `v0.3.33` package metadata, server metadata, package manifests, and Git UPM examples.
- Reduced monolithic ownership on the Unity package side while preserving public
  MCP operation names, JSON payload shapes, scenario timing semantics, and
  persisted bridge state contracts. The existing scenario runner, project-action
  normalizer, bridge runtime state, and model entrypoints remain compatibility
  facades over smaller DTO, runtime, compiler, scheduler, catalog, and handler
  units.
- Reduced monolithic ownership on the Python server side across batch
  orchestration, bridge runtime, CLI command routing, editor-host lifecycle,
  setup wizard, summaries, and tool specs while keeping public command and MCP
  tool contracts stable.
- Tightened `unity_scenario_run_and_wait` compact/full payload semantics:
  public smoke helpers that need step-level evidence now request
  `includeFullPayload`, while compact summaries remain the default contract for
  agent-facing verdicts.
- Added regression coverage for the compact payload contract, scenario decision
  verdict parity, server parity baselines, and Windows/WSL process visibility
  routing.

### Fixed

- Fixed native Windows CI routing for `HostPlatformAdapter(platform_kind="linux")`
  so WSL-simulated PID checks do not accidentally use the host Windows
  `OpenProcess` path and report unrelated live PIDs as Unity processes.
- Hardened smoke validation docs and reusable smoke scripts so compact scenario
  results are not misread as missing per-step evidence.

### Validation

- Host Python unittest suite: `264` tests passed with `1` expected skip.
- Project devmode MCP post-change smoke passed, including readiness,
  compile matrix, acceptance, contract, playmode settled-state regression,
  lifecycle retry, and project-action catalog consistency.
- Project devmode package self-tests passed: EditMode `12/12` and PlayMode
  `5/5`.

## 0.3.32

Release tag: `v0.3.32`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.32
```

### Changed

- Released `v0.3.32` package metadata, server metadata, package manifests, and Git UPM examples.
- `unity_scenario_run_and_wait` now returns a compact decision verdict by
  default: verdict, trust class, failure class, recommended next action,
  terminal scenario status, short step summaries, UI smoke fields, and path
  coverage. Full raw scenario payloads remain available with `verbose` or
  `includeFullPayload`.
- Scenario lifecycle recovery now attributes editor cold starts and relaunches
  with `editor_relaunched`, `previous_editor_pid`, `current_editor_pid`,
  `bridge_generation_before`, `bridge_generation_after`, and
  `cold_start_reason` so latency is explainable without weakening the verdict.
- Scenario compile steps now prefer post-settle compile truth from
  `idle_wait_after`, keeping request-time transport success separate from
  final Unity compiler state.
- Infrastructure timeouts are classified as `infrastructure_timeout`, while UI
  smoke summaries continue to distinguish product assertions, preconditions,
  blocking popups, cleanup, and unproven Unity completion.
- Release version consistency now covers both MCP protocol metadata sources so
  `initialize.serverInfo.version` stays aligned with package metadata.

## 0.3.31

Release tag: `v0.3.31`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.31
```

### Changed

- Released `v0.3.31` package metadata, server metadata, package manifests, and Git UPM examples.

### Fixed

- Cleared Unity's editor progress bar after MCP-triggered compile, refresh, and build so the "Importing assets"/"Compiling" dialog no longer stays stuck on Unity 2022.3. Added `EditorUtility.ClearProgressBar()` to the compile-utility `finally` (covers every `PlayerBuildInterface.CompilePlayerScripts` caller, including matrix and scenario steps) and to the request-pump completion path (covers `AssetDatabase.Refresh` / `BuildPipeline.BuildPlayer`). Unity 6 already auto-cleared the bar; this restores parity on 2022.3.

## 0.3.30

Release tag: `v0.3.30`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.30
```

### Changed

- Released `v0.3.30` package metadata, server metadata, package manifests, and Git UPM examples.
- Native Windows Codex config generation now uses `cmd.exe` and
  `run_installed_or_refresh_xuunity_mcp.cmd`; an existing Windows `bash` block
  is reported as `windows_codex_launcher_mismatch` instead of duplicated.
- Windows setup docs now prefer `.cmd`, quote project paths, and call out
  PowerShell ExecutionPolicy risk for `.ps1`.
- `validate-setup` now reports offline readiness scope and package import-state
  evidence instead of presenting manifest/config validation as live Unity
  readiness.

### Fixed

- Added raw/resolved project-root diagnostics and Windows launcher hints for
  `project_not_found`, making path-with-spaces truncation diagnosable from one
  error payload.
- Added package import-state evidence to `ensure-ready` success and error
  payloads. A declared-but-unresolved package with a live bridgeless editor now
  recommends `reopen_project_for_clean_resolve` instead of generic editor
  recovery.
- Added an already-closed editor closeout fast path that clears stale host
  session/bridge/test state without quit or terminate attempts when process
  visibility proves no same-project editor is live.

### Validation

- Host Python suite: `243` tests passed on macOS, with one expected native
  Windows `.cmd` smoke skipped on this host.

## 0.3.29

Release tag: `v0.3.29`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.29
```

### Added

- Added `project_defined_hook_poll_until`, a first-class scenario operation for
  project-defined hook smokes that starts one hook action, polls another until a
  payload predicate reaches `passed`, `failed`, or timeout, and keeps the latest
  terminal payload in scenario results.
- Added scenario summary promotion for poll-until hook name, terminal status,
  failure class, requested scalar payload fields, screenshot path, console-tail
  evidence count, and cleanup result.

### Changed

- Released `v0.3.29` package metadata, server metadata, package manifests, and Git UPM examples.
- Scenario JSON now accepts `operation` as an alias for `kind` and accepts
  object-shaped `startPayload` / `pollPayload` inputs, which are normalized for
  both Python MCP tool callers and direct Unity bridge callers.

### Validation

- Validated package EditMode self-tests on a temporary Unity `2022.3.67f2`
  project with the local `com.xuunity.light-mcp` package: `12/12` passed.
- Validated an end-to-end temporary project hook scenario:
  `request-scenario-validate` returned `valid`, `request-scenario-run-and-wait`
  returned `passed` with `poll_count=3`, and compact summary promoted
  `selected_tab`, `user_path`, `before_value`, `after_value`, and
  `cleanup_result=passed`.
- Re-ran the host Python suite after live Unity validation: `237` tests passed
  with one expected native Windows `.cmd` smoke skipped on macOS.

## 0.3.28

Release tag: `v0.3.28`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.28
```

### Changed

- Released `v0.3.28` package metadata, server metadata, package manifests, and Git UPM examples.

### Changed

- Removed the legacy bash wrapper body (`xuunity_light_unity_mcp_legacy.sh`)
  and the `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER` escape hatch after the
  Python launcher core was proven by green Windows, macOS, and Linux CI legs
  on `v0.3.27`. The golden dual-run parity suite retired with its subject;
  cross-flavor (.sh/.cmd/.ps1) parity, the bash-spawn canary, and the full
  contract suite remain as regression guards.

## 0.3.27

Release tag: `v0.3.27`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.27
```

### Changed

- Released `v0.3.27` package metadata, server metadata, package manifests, and Git UPM examples.


### Added

- Added `xuunity_light_unity_mcp.cmd` and `xuunity_light_unity_mcp.ps1` wrapper siblings using the proven `run.cmd`/`run.ps1` Python discovery chain and executing `templates/server_launcher.py`, so Windows operators get the full wrapper surface without bash.
- Promoted shared subprocess helpers (Git Bash resolution, process-tree kill, run-to-files) into `scripts/testing/process_support.py`, consumed by both the orchestrator and the test suite.
- Added an optional `XUUNITY_LIGHT_UNITY_MCP_WORKER_TIMEOUT_SECONDS` watchdog that kills stuck worker process trees with exit code 124.
- Added cross-flavor launcher parity tests (`test_launcher_flavor_parity`) and thread-pool parallelism tests (`test_multi_project_parallelism`).

### Changed

- Ported the operator wrapper body from bash to `templates/server_launcher.py`, which owns source/repo/install-dir resolution, helper sync, compact summary emission, devmode/prodmode, and server dispatch. Client-context and install-dir resolution delegate to `server_setup_wizard` to remove duplicate bash/python logic.
- Shrank `xuunity_light_unity_mcp.sh` to a thin 28-line launcher with legacy flag checking and Python discovery (`PYTHON` env, `py -3`, `python3`, `python`, `py`). Preserved the previous bash body as `xuunity_light_unity_mcp_legacy.sh` (callable via `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER=1`).
- Ported both multi-project runners into `scripts/testing/run_multi_project.py` (subcommands `batch-compile-matrix` and `gui-test-subset`) using `ThreadPoolExecutor` workers, removing `xargs -P` and enabling identical parallelism overlap across macOS, Linux, and Windows.
- Expanded offline CI checks to run on `master` pushes and pull requests (previously tags only), smoke-executing `templates/run.cmd` and `templates/run.ps1` on the Windows leg.

### Fixed

- Fixed parity test path normalization for Windows path representations, resolving WSL/POSIX temp differences, 8.3 short names (`RUNNER~1`), and JSON-escaped backslashes.

## 0.3.26

Release tag: `v0.3.26`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.26
```

### Changed

- Released `v0.3.26` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.25

Release tag: `v0.3.25`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.25
```

### Changed

- Added `test-results-table` for reusable markdown, JSON, and TSV summaries
  from persisted Unity test-result JSON files.
- Improved multi-project GUI test subset reporting with per-project request
  ids, result paths, count summaries, lifecycle churn flags, failure grouping,
  package-source closeout, and workspace side-effect accounting.
- Documented completed test-result JSON as the immutable source of truth for
  portfolio closeout and aggregate operator verdicts.
- Released `v0.3.25` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.24

Release tag: `v0.3.24`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.24
```

### Changed

- Fixed Windows Git Bash wrapper delegation so setup and server commands use
  the resolved Python interpreter, including `python`, `python3`, and `py -3`
  launcher paths.
- Hardened setup plan/apply JSON loading for UTF-8, UTF-8 BOM, and UTF-16 plan
  files produced by common PowerShell capture flows.
- Improved Windows and WSL editor discovery, PID liveness checks, and path
  conversion for Windows-installed Unity editors used from WSL helpers.
- Added cross-platform compatibility regression tests for Windows, WSL, macOS,
  Linux, and shell wrapper Python launcher handling.
- Released `v0.3.24` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.23

Release tag: `v0.3.23`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.23
```

### Changed

- Added `unity.console.grep`, `unity_console_grep`, `request-console-grep`,
  and a reusable `console_grep` scenario template for compact Unity console
  inspection without raw log dumping.
- Added `request-loading-timing` and `unity_loading_timing` on top of console
  grep so agents can collect compact scene/loading timing evidence.
- Added `project-hook-scaffold` and profile mutation summary helpers for
  reusable project action and scenario authoring flows.
- Added public-safe completed retro archive entries and refreshed the public
  retro registry split between active backlog and completed history.
- Released `v0.3.23` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.22

Release tag: `v0.3.22`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.22
```

### Changed

- Added centralized neutral helper installation with Codex/Claude delegate
  launchers, isolated `.venv` discovery, and Antigravity IDE setup guidance.
- Hardened full-reset uninstall planning so client-specific cleanup preserves
  the shared neutral helper unless explicitly requested.
- Updated wrapper auto-resolution, setup wizard tests, and release-facing
  validation coverage for neutral helper workflows.
- Released `v0.3.22` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.21

Release tag: `v0.3.21`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.21
```

### Changed

- Fixed license capability classification so recovered Unity licensing startup
  warnings, such as transient access-token or IPC-channel messages followed by
  successful entitlement resolution and a clean batchmode exit, no longer force
  GUI fallback.
- Added explicit portfolio batch fallback-mode forwarding and compact operator
  verdicts so multi-project compile summaries distinguish `passed_via_batch`
  from `passed_via_gui_fallback`.
- Released `v0.3.21` package metadata, server metadata, package manifests, and Git UPM examples.
- Tightened the MCP release gate so `sync_release_version.py` and
  `check_release_version_consistency.py` now treat the GitHub Pages site and
  listing metadata as release-bound surfaces that must be updated before
  tagging.

## 0.3.20

Release tag: `v0.3.20`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.20
```

### Added

- Added `uninstall-plan` and `uninstall-apply` host helper commands plus
  `xuunity_uninstall_plan` and `xuunity_uninstall_apply` MCP tools for safe
  project cleanup and current-user reset flows.
- Added uninstall guidance across install, agent, client, template, and
  reference docs, including project-only cleanup and full reset modes.
- Added a GitHub Pages-ready public site surface for `XUUnity MCP`, including
  install, comparison, use-case, alternatives, and client-guide landing pages.
- Added SEO/discovery operational docs, including listing metadata, publishing
  checklist, SERP tracking guidance, and a live execution backlog.

### Changed

- Renamed the public repository slug from
  `FoxsterDev/xuunity-light-unity-mcp` to `FoxsterDev/xuunity-mcp`.
- Updated the canonical Git UPM install path to the new repository URL while
  keeping the package directory at `packages/com.xuunity.light-mcp`.
- Updated release-facing docs, package metadata, MCP metadata, GitHub Pages
  canonicals, and helper/client examples to use the new repo/site path.
- Documented uninstall as a preflight-first flow that removes only the selected
  `xuunity_light_unity` client config block, selected helper install, and
  explicit project-level MCP setup after approval.
- Released `v0.3.20` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.19

Release tag: `v0.3.19`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.19
```

### Added

- Added compact lifecycle churn output to the post-change validation runner,
  including bridge generation/session transition, request abandoned and
  reclassification counts, final health, final Play Mode state, compiler
  errors, stale request count, and warning codes.
- Added package self-test discovery output to the package self-test smoke
  runner, including testables visibility, Test Framework version, package
  source/hash, test asmdef count, test counts, and discovered MCP categories.

### Fixed

- Fixed package EditMode self-test compilation on Unity versions where
  `Object.DestroyImmediate` is ambiguous between `UnityEngine.Object` and
  `object`.
- Fixed package self-test smoke accounting so an explicit package self-test
  request fails on `no_tests` or `total=0` instead of reporting a top-level MCP
  success as a test pass.
- Fixed package self-test discovery blind spots so a requested self-test lane
  fails before execution when the expected package test asmdefs, categories, or
  lane test counts are not visible.

### Changed

- Released `v0.3.19` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.18

Release tag: `v0.3.18`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.18
```

### Added

- Added catalog-backed `project_action` scenario steps as a Unity-native
  scenario contract. Unity now resolves `project_actions.yaml`, enforces
  explicit approval for mutating actions, and executes the declared
  `project_defined_hook` without requiring host-side scenario rewriting.
- Added host-side `project_action` scenario preflight so MCP tools and wrapper
  commands can fail early with the same mutation and catalog diagnostics before
  dispatching to Unity.
- Added host-side project action tools and commands for listing and invoking
  catalog-backed project actions.
- Added artifact registry/report helpers for project validation pipelines that
  need stable report artifacts without importing them into Unity `Assets`.
- Added regression coverage for typed project action scenario expansion,
  mutation approval guards, `payloadJson` support, artifact registry helpers,
  and Unity-side raw `project_action` normalization.

### Changed

- Updated scenario schemas and docs so `project_action` is documented as a
  Unity-side contract with host preflight, rather than a host-only authoring
  convenience.
- Released `v0.3.18` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.17

Release tag: `v0.3.17`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.17
```

### Added

- Added `sync_release_version.py` to synchronize package metadata, server
  metadata, package manifest templates, and current release-facing docs from the
  package version source of truth.
- Added `check_release_version_consistency.py` and host-suite coverage so stale
  current-version references fail before release tagging.

### Changed

- Released `v0.3.17` package metadata, server metadata, package manifests, and Git UPM examples.

## 0.3.16

Release tag: `v0.3.16`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.16
```

### Added

- Added Unity bridge/status compiler diagnostics:
  `script_compilation_failed`, `compiler_error_count`,
  `recent_compiler_diagnostics`, and `compiler_diagnostics_source`.
- Added host-side compile-red fail-fast for EditMode tests, PlayMode tests,
  Play Mode transitions, and scenario runs before long editor-idle waits.
- Added operator-visible pre-dispatch progress phases: `activation`,
  `wait_for_idle_before`, `dispatching`, `waiting_for_response`, and
  `wait_for_idle_after`.
- Added scenario DSL dependency and cleanup support through `dependsOn`,
  `runIfStepPassed`, and `cleanupSteps`.
- Added compact scenario wait heartbeat output that reports active step, first
  failed step, wait deadline, remaining seconds, and editor health context.
- Added a visual Codex Desktop custom MCP setup guide with sanitized screenshots
  and guidance for natural Unity requests through the `xuunity_light_unity`
  server.

### Changed

- Scenario `stopOnFirstFailure` now jumps to cleanup steps when configured, so
  project state can be restored even after the scenario body fails.
- Released `v0.3.16` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.15

Release tag: `v0.3.15`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.15
```

### Changed

- Added license-aware batch lane selection: `license-capabilities`,
  `unity_license_capabilities`, `--batch-fallback-mode auto|off|require-batch`,
  GUI fallback summaries, and Unity-side `unity.build_player` for player-build
  fallback when real batchmode is blocked.
- Added `XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex|claude|auto` for wrapper
  helper resolution so Codex contexts prefer `.codex-tools` without breaking
  Claude-side `.claude-tools` installs.
- Documented optional Codex/Codex-style MCP client wiring for trusted local
  Unity projects.
- Released `v0.3.15` package metadata, server metadata, package manifests, and
  Git UPM examples.

## 0.3.14

Release tag: `v0.3.14`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14
```

### Changed

- Released `v0.3.14` package metadata with Unity `2021.3` as the default
  minimum and removed the hard `com.unity.test-framework` dependency.
- Added optional Test Framework capability wiring through asmdef Version
  Defines and `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY`.
- Added setup wizard commands and MCP tools for per-project setup planning,
  approved setup application, setup validation, and approved Test Framework
  installation.
- Added capability statuses for optional test support, including missing and
  too-old dependency states that do not make core MCP health fail.
- Added closed-editor batch lifecycle hardening: explicit editor-close
  verification, process visibility diagnostics, `request-editor-quit
  --wait-for-exit`, and `restore-editor-state --require-closed`.
- Hardened public source-root/package-mode selection so the wrapper resolves the
  operation package source before generic `AIRoot/templates` paths.
- Fixed installed-helper setup planning so the default Git UPM dependency uses
  the package metadata version instead of falling back to `v0.0.0`.
- Added a README install simulation audit covering single-project, hub,
  mixed-version, nested-repo, and optional Test Framework setup paths.
- Added README guidance for collecting a sanitized chat retro before opening a
  GitHub issue about MCP setup or automation failures.
- Added an install-specific retro prompt for collecting structured MCP setup
  evidence before opening a GitHub issue.
- Changed `prodmode` to pin the published package release tag, such as
  `#v0.3.14`, instead of a raw source commit SHA.

## 0.3.13

Release tag: `v0.3.13`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.13
```

### Changed

- Restored Git UPM as the default production package source for project setup.
  `init_xuunity_light_unity_mcp.sh --enable-project` now enables the bridge
  without rewriting `Packages/manifest.json`.
- Kept local `file:` package wiring behind explicit wrapper mode switches only:
  `devmode` for local MCP package iteration and `prodmode` for returning to the
  published Git-backed source.
- Updated project-package alignment checks so a Git-pinned dependency is treated
  as the default healthy production state instead of warning about local-source
  expectations.
- Added a reusable clean-project Android APK smoke runner that creates a Unity
  project, installs the package from Git UPM, proves MCP readiness, restores
  the editor session, and runs a regular Unity batch APK build.
- Added Android Build Support preflight reporting for the clean-project smoke
  runner, including a structured fail-fast summary and an explicit
  `--allow-no-android` MCP-only readiness mode.
- Updated installer docs, client docs, AI integration docs, smoke contracts,
  and package examples to document the Git-default / devmode-only package
  source model consistently.

## 0.3.12

Release tag: `v0.3.12`

Current Git UPM install URL:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12
```

### Changed

- Moved the Unity package from `templates/unity-package` to the registry-native
  `packages/com.xuunity.light-mcp` path.
- Updated package metadata so Unity Package Manager and future package registries
  can identify the canonical package directory as `packages/com.xuunity.light-mcp`.
- Updated Git UPM install examples, local `file:` package examples, package
  discovery, installer wiring, wrapper `devmode` / `prodmode`, workflow
  templates, package manifests, and tests to use the new package path.
- Added the README preview banner asset and refreshed top-level install
  messaging around the new package path.

### Migration Notes

- New installs should use:
  `https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.12`
- Local MCP development should use:
  `file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp`
- Projects pinned to `v0.3.11` can continue using
  `templates/unity-package`; that old path is now migration-only.
- To migrate a Unity project, replace
  `?path=/templates/unity-package#v0.3.11` with
  `?path=/packages/com.xuunity.light-mcp#v0.3.12`, remove the
  `com.xuunity.light-mcp` entry from `Packages/packages-lock.json`, and let
  Unity re-resolve packages.

### Notes

- OpenUPM publication is still pending; Git UPM is the supported install route
  for this release.
- The package remains editor-only and disabled by default, with no player-build
  footprint by default.
- Post-tag documentation refinements may exist on `master`; the package release
  tag for Unity consumers remains `v0.3.12`.

## 0.3.11

- Added wrapper help and agent workflow guidance for MCP `devmode` and `prodmode` package-source switching.
- Added client-specific MCP payload examples, structured evidence schema, and machine-readable workflow templates for agent validation workflows.

- Replaced placeholder client docs with production-ready MCP configs for Claude Code, Claude Desktop, Cursor, Windsurf, Codex-style agents, and generic stdio MCP clients.
- Added reusable client config templates under `templates/clients/`.
- Added native Windows client config templates and `run.cmd`/`run.ps1` launchers.
- Replaced the zsh-only Unix launcher with a bash-compatible launcher for Linux/macOS.
- Expanded `docs/reference/FEATURES.md` with competitive differentiators and the full MCP/host helper surface.
- Clarified feature maturity levels, implementation evidence, and compatibility validation status in `docs/reference/FEATURES.md`.
- Clarified `docs/reference/COMPARISON.md` source confidence, maturity terminology, and validation caveats.
- Added `AndreySkyFoxSidorov/UnifiedUnityMCP` to `docs/reference/COMPARISON.md` as a broad but young Unity automation reference.
- Added `docs/agents/AGENT_WORKFLOWS.md` to close Priority 15 with production-grade example agent workflows for Unity validation, triage, scenario replay, SDK checks, batch lanes, recovery, and release closeout.
- Updated installer wording and Claude Code user-scope config generation for the production stdio path.

## 0.3.10

- Extracted XUUnity Light Unity MCP into a standalone public repository.
- Added landing README, `llms.txt`, discovery metadata, install guide, feature table, security model, glossary, and client setup docs.
- Updated package metadata to point at `FoxsterDev/xuunity-mcp`.
- Preserved detailed legacy implementation notes in `docs/reference/STATUS.md`.

## 0.3.9

- Added Claude MCP wiring and robust batch matrix parsing in the source package.
- Preserved the working host-side server, Unity editor package, smoke runners, and package self-tests from the previous public-core layout.
