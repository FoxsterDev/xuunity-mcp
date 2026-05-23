# Status

Date: `2026-05-23`
Status: `active public status snapshot`

XUUnity Light Unity MCP is a working same-host Unity Editor automation service
for MCP-capable AI agents. The current source line is `v0.3.14`.

## Current Package

Unity package:

```text
com.xuunity.light-mcp
```

Current Git UPM URL:

```text
https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14
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
- The old path is kept only as a migration pointer for users pinned to
  `v0.3.11`.

OpenUPM status:

- the package layout is OpenUPM-ready
- the package is not documented as published on OpenUPM yet
- use Git UPM until the OpenUPM package page exists

## Current Surface

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
- `unity.scene.snapshot`
- `unity.scene.assert`
- `unity.tests.run_editmode`
- `unity.tests.run_playmode`
- `unity.playmode.state`
- `unity.playmode.set`
- `unity.game_view.configure`
- `unity.game_view.screenshot`
- `unity.compile.player_scripts`
- `unity.compile.matrix`
- `unity.scenario.validate`
- `unity.scenario.run`
- `unity.scenario.result`

Implemented host-side MCP tools and helpers:

- `unity_status_summary`
- `xuunity_setup_plan`
- `xuunity_setup_apply`
- `xuunity_setup_validate`
- `unity_package_install_test_framework`
- `unity_request_final_status`
- `unity_scenario_result_summary`
- `unity_scenario_results_list`
- `unity_scenario_result_latest`
- `unity_scenario_run_and_wait`
- `unity_compile_build_config_matrix`
- `unity_maintenance_prune`
- `project-discovery-report`
- `registry-context-report`
- `registry-prune-contexts`
- `setup-plan`
- `setup-apply`
- `validate-setup`
- `install-test-framework`
- `open-editor`
- `ensure-ready`
- `recover-editor-session`
- `restore-editor-state`
- `request-status-summary`
- `request-final-status`
- `request-latest-status`
- `request-cancel`
- `request-stale-cleanup`
- `batch-compile`
- `batch-compile-matrix`
- `batch-build-config-compile-matrix`
- `batch-editmode-tests`
- `batch-test-framework-version-regression`
- `batch-build-player`
- `artifact-probe`

## Current Validation Evidence

Latest source validation for `v0.3.14`:

| Area | Evidence | Result |
| --- | --- | --- |
| Package metadata | `packages/com.xuunity.light-mcp/package.json` | `name=com.xuunity.light-mcp`, `version=0.3.14`, `unity=2021.3`, no hard Test Framework dependency |
| Host Python tests | `scripts/testing/run_host_python_tests.sh` | `123/123` passed |
| Package self-tests | Clean devmode projects on installed Unity editors | EditMode `6/6`, PlayMode `5/5` on `2021.3.58f1`, `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`, `6000.0.61f1`, `6000.2.14f1`, and `6000.3.3f1` after offline optional Test Framework setup. `2021.3.45f2` could not create a project because the editor license was unavailable. |
| Multi-project compile matrix | Private multi-project consumer validation | `9/9` projects, `38/38` lanes, `0` failures |
| Git tag visibility | Git refs | Release tag `v0.3.14` must be pushed before consumers pin it from Git UPM. |

Cross-platform status:

| Target | Status | Notes |
| --- | --- | --- |
| macOS host tools | `validated on this host` | Shell wrapper, host tests, Unity package self-tests, and multi-project matrix passed. |
| Linux host tools | `portable by design` | Bash-compatible launchers/templates exist; run a Linux Unity smoke before claiming live proof. |
| Native Windows clients | `templates provided` | `run.cmd`, `run.ps1`, and Windows client configs exist; native Windows MCP connection still needs host execution proof. |
| Unity 2021.3+ | `default package line` | Checked-in package metadata targets Unity `2021.3`; setup wizard chooses optional Test Framework recommendations per project. |
| Optional Test Framework | `capability-gated` | Core readiness stays healthy when missing; tests report `disabled_missing_dependency`, `disabled_dependency_too_old`, or supported with `upgrade_recommended` when an existing dependency should be reviewed. |

## Package Source Modes

Use Git UPM for production consumers:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.14"
  }
}
```

Use local `file:` only while developing this MCP package:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "file:/absolute/path/to/xuunity-light-unity-mcp/packages/com.xuunity.light-mcp"
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
- `prodmode` pins the Unity project to the current published source commit.
- `prodmode` refuses to pin an unpublished source `HEAD`.
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
