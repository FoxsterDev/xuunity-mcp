# Features

| Area | Tool / command | Status | Notes |
| --- | --- | --- | --- |
| Editor health | `unity.status` | Supported | Compact editor status |
| Capabilities | `unity.capabilities.get` | Supported | Capability-gated operation surface |
| Health | `unity.health.probe` | Supported | Editor and bridge health probe |
| Console | `unity.console.tail` | Supported | Tail Unity console logs |
| Scene | `unity.scene.snapshot` | Supported | Inspect active scene |
| Scene | `unity.scene.assert` | Supported | Assert scene conditions |
| Tests | `unity.tests.run_editmode` | Supported | Run Unity EditMode tests |
| Tests | `unity.tests.run_playmode` | Supported | Run Unity PlayMode tests |
| Compile | `unity.compile.player_scripts` | Supported | Validate player scripts |
| Compile | `unity.compile.matrix` | Supported | Build target / define matrix |
| Build target | `unity.build_target.get` | Supported | Read current build target |
| Build target | `unity.build_target.switch` | Supported | Switch build target through Unity |
| Play Mode | `unity.playmode.state` | Supported | Read Play Mode state |
| Play Mode | `unity.playmode.set` | Supported | Enter or exit Play Mode |
| Game View | `unity.game_view.configure` | Supported | Configure Game View resolution |
| Game View | `unity.game_view.screenshot` | Supported | Capture Game View screenshots |
| Scenarios | `unity.scenario.validate` | Supported | Validate bounded scenario JSON |
| Scenarios | `unity.scenario.run` | Supported | Run bounded scenario workflows |
| Scenarios | `unity.scenario.result` | Supported | Read persisted scenario results |
| Maintenance | `unity_maintenance_prune` | Supported | Cleanup stale request state |

## Host-Side Helpers

- `project-discovery-report`
- `request-status-summary`
- `request-final-status`
- `request-cancel`
- `request-stale-cleanup`
- `request-latest-status`
- `request-scenario-result-summary`
- `request-scenario-results-list`
- `request-scenario-result-latest`
- `registry-context-report`
- `registry-prune-contexts`
- `batch-compile`
- `batch-compile-matrix`
- `batch-build-config-compile-matrix`
- `batch-editmode-tests`
- `batch-build-player`
- `artifact-probe`

## Out Of Scope By Default

- runtime/player automation
- multiplayer runtime control
- arbitrary dynamic code execution
- broad unrestricted project mutation
- exposing Unity Editor control to untrusted networks

