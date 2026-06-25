# XUUnity MCP Monolith Reduction First-Principles Plan

Date: `2026-06-25`
Status: `design plan ready for implementation`
Target: `Operations/XUUnityLightUnityMcp`

## Problem

XUUnity Light Unity MCP is a two-runtime product:

1. a host/server Python runtime under `templates/`
2. a Unity Editor C# package under `packages/com.xuunity.light-mcp`

The previous `templates/server.py` refactor already split the original entrypoint into modules, but several extracted server modules are now second-order monoliths. The Unity package also has several first-party files that have grown into mixed-responsibility hubs.

Server-side primary candidates:

- `templates/server_batch_orchestrator.py` - 2873 lines
- `templates/server_bridge_runtime.py` - 2529 lines
- `templates/server_cli_commands.py` - 2062 lines
- `templates/server_editor_host.py` - 1715 lines
- `templates/server_setup_wizard.py` - 1618 lines
- `templates/server_summaries.py` - 1400 lines
- `templates/server_specs.py` - 1194 lines
- `templates/server_project_actions.py` - 895 lines
- `templates/server_launcher.py` - 786 lines
- `templates/server_setup_regression.py` - 774 lines
- `templates/server_cli_parser.py` - 691 lines

Unity package primary candidates:

- `Editor/Helpers/XUUnityLightMcpScenarioRunner.cs` - 2182 lines
- `Editor/Helpers/XUUnityLightMcpScenarioProjectActionNormalizer.cs` - 1236 lines
- `Editor/Bridge/XUUnityLightMcpBridgeRuntimeState.cs` - 1152 lines
- `Editor/Core/XUUnityLightMcpModels.cs` - 1042 lines
- secondary candidates around 300-550 lines: test run state, game view utility, bridge transport runtime, batch CLIs, health probe, build player operation

The goal is not to chase a fixed line-count rule. The goal is to reduce hidden coupling across both runtimes, make future MCP changes cheaper, and protect observable MCP behavior while decomposing the code.

## Coordination Update

As of this handoff, another chat is already working the Unity C# package side under `packages/com.xuunity.light-mcp`.

This document still records the full product-level design, but the next implementation chat should treat the active scope as:

- **Do work:** server/template Python monoliths under `templates/`, plus server tests under `tests/` and supporting scripts only when needed.
- **Do not work:** Unity C# package files under `packages/com.xuunity.light-mcp`, except for read-only contract inspection or final cross-runtime validation after coordination.
- **Integration contract:** preserve MCP tool names, operation names, JSON shapes, persisted bridge paths, and CLI behavior so the server-side refactor remains compatible with the Unity-side refactor.
- **Platform contract:** preserve support for both Windows and Unix-like hosts. Server refactors must not introduce POSIX-only paths, shell syntax, process handling, file locking, newline assumptions, or encoding assumptions.

## Phase 1: Assumption Autopsy

1. Assumption: "large file equals bad file."
   - Source: industry habit.
   - Correction: size is only a signal. The actual defect is mixed reasons to change.

2. Assumption: "files should be split by line threshold."
   - Source: old line-count culture.
   - Correction: the XUUnity protocol already replaced line-count thinking with invariants. For MCP code, the equivalent invariant is observable contract parity.

3. Assumption: "the current folders define the right boundaries."
   - Source: inherited structure: Python `templates/server_*` modules and C# `Helpers`, `Bridge`, `Core`, `Operations`.
   - Correction: folders and file prefixes describe location, not ownership. `Helpers` and broad `server_*` modules currently hide full subsystems.

4. Assumption: "`ScenarioRunner` is one runner."
   - Source: file name.
   - Correction: it contains scenario validation, compilation to executable steps, queueing, persistence, tick scheduling, step dispatch, nested operation execution, hook execution, cleanup, and result lookup.

5. Assumption: "`BridgeRuntimeState` must be one static object because Unity Editor lifecycle is global."
   - Source: fear of race conditions and domain reload bugs.
   - Correction: Unity lifecycle is global, but its state domains are separate: session, domain reload, import/package activity, refresh settle, compile settle, playmode transition, request pump.

6. Assumption: "`Models.cs` is acceptable because it is only DTOs."
   - Source: common C# practice.
   - Correction: DTOs are the MCP external contract. Mixing all families in one file makes contract review expensive and risky.

7. Assumption: "compile success is enough after refactoring."
   - Source: normal C# refactor mindset.
   - Correction: the real risks are JSON drift, persisted state drift, status payload drift, scenario timing drift, and lifecycle accounting drift.

8. Assumption: "`templates/server.py` was already refactored, so the server is fine."
   - Source: completed 2026-06-09 server refactor.
   - Correction: the first refactor moved the monolith out of the entrypoint. It did not finish decomposing the extracted orchestration, bridge runtime, CLI command, editor host, setup, summary, and spec modules.

9. Assumption: "`server_batch_orchestrator.py` is one orchestrator."
   - Source: file name.
   - Correction: it contains batch lanes, MCP tool wrappers, registry context reporting, JSON-RPC serving, bridge invocation, request locks, scenario waiting, recovery, project cleanup, and error formatting.

10. Assumption: "`server_bridge_runtime.py` is one bridge runtime."
    - Source: file name.
    - Correction: it contains path contracts, transport invocation, heartbeat/liveness, stale request inspection, request journal reads, lifecycle final-status recovery, settle transitions, idle waits, and compile-failure policy.

11. Assumption: "`server_cli_commands.py` should contain all commands."
    - Source: argparse extraction convenience.
    - Correction: CLI handlers should be thin adapters over command families. A single command module has become a second entrypoint monolith.

## Phase 2: Irreducible Truths

1. MCP tool names, CLI subcommands, operation names, args JSON shape, payload JSON shape, response status/error shape, stdout/stderr behavior, and persisted files are external contracts.
2. Safe decomposition requires preserving observable behavior, not merely compiling.
3. Scenario execution is a state machine, not a helper method.
4. Scenario validation, scenario execution, nested operation transport, hook execution, and result storage have different consumers and failure modes.
5. Project action normalization is a translation boundary from user-authored scenario JSON to executable hook steps.
6. Bridge runtime state is a composition of lifecycle domains, even if a facade keeps one public API.
7. DTO families should be grouped by operation family so contract review can be local.
8. A file-size guard is useful only as a maintainability warning. It is not a design law.
9. The best extraction boundary is the one where a parity test can be placed.
10. The server runtime and Unity package are one product contract. Splitting only one side leaves the MCP system monolithic at the other boundary.
11. Python server decomposition must preserve the existing zero-external-runtime-dependency constraint.
12. CLI parser/command behavior is a user-facing contract equal in importance to MCP JSON behavior.
13. Windows and Unix support is a product contract, not a portability nice-to-have. Host-side code must use platform adapters, `pathlib`, argument-vector subprocess calls, explicit encodings, and tested process semantics.

## Phase 3: Rebuild From First Principles

### Approach A: Product-Contract-First MCP Core

Build both runtimes around observable MCP contracts.

Server-side:

- `server_cli_parser.py` remains parser-only.
- `server_cli_commands.py` becomes command-family adapters, not the home of business logic.
- `server_mcp_tools.py` remains MCP tool adapter layer.
- `server_batch_orchestrator.py` is split by batch lane, request locking, bridge invocation, recovery, and reporting.
- `server_bridge_runtime.py` is split by path contracts, transport, liveness, request lifecycle, journal, idle waits, and final-status recovery.
- `server_specs.py` is split into tool specs, lifecycle policies, scenario schemas, startup policies, and generated/validated registry views.
- `server_summaries.py` is split by status, scenario, discovery, verdict, and text utilities.

Unity-side:

- `Core/Models/BridgeModels.cs`
- `Core/Models/OperationModels.cs`
- `Core/Models/ConsoleModels.cs`
- `Core/Models/SceneModels.cs`
- `Core/Models/TestModels.cs`
- `Core/Models/GameViewModels.cs`
- `Core/Models/BuildCompileModels.cs`
- `Core/Models/ScenarioModels.cs`
- `Core/Models/SdkDependencyModels.cs`
- `Scenarios/` for scenario validation, execution, storage, and step handlers
- `ProjectActions/` for action catalog and normalization
- `Bridge/Runtime/` for state domains and snapshot projection

Existing public Python module functions and public C# classes stay as compatibility facades during rollout.

### Approach B: Server Pipeline First

Treat the Python server as a pipeline, not a pile of `server_*` modules:

1. input adapters: CLI, MCP JSON-RPC
2. command/tool adapters: parse validated user intent into operation calls
3. project context and registry
4. bridge request submission and transport
5. lifecycle waiting and recovery
6. evidence, summaries, final status
7. reporting and process exit behavior

Target splits:

- `server_batch/lanes.py`
- `server_batch/request_lock.py`
- `server_batch/bridge_invocation.py`
- `server_batch/recovery.py`
- `server_batch/context_reports.py`
- `server_bridge/paths.py`
- `server_bridge/transport.py`
- `server_bridge/liveness.py`
- `server_bridge/request_artifacts.py`
- `server_bridge/journal.py`
- `server_bridge/final_status.py`
- `server_cli/command_groups/*.py`
- `server_specs/tool_specs.py`
- `server_specs/lifecycle_policies.py`
- `server_specs/scenario_schema.py`

Keep old flat modules as compatibility shims until tests and downstream imports are migrated.

### Approach C: Scenario State Machine First

Treat `XUUnityLightMcpScenarioRunner` as a state-machine subsystem:

- `ScenarioValidator`
- `ScenarioCompiler`
- `ScenarioRunRepository`
- `ScenarioScheduler`
- `ScenarioStepDispatcher`
- `ScenarioStepHandlers/*`
- `NestedOperationClient`
- `ScenarioHookExecutor`
- `ScenarioResultProjector`

`XUUnityLightMcpScenarioRunner` remains the facade exposing:

- `Validate`
- `HasActiveRun`
- `QueueRun`
- `Tick`
- `TryReadResult`

### Approach D: Lifecycle Domain Runtime

Treat `XUUnityLightMcpBridgeRuntimeState` as a facade over separate runtime domains:

- `BridgeSessionRuntime`
- `EditorLifecycleRuntime`
- `RefreshSettleRuntime`
- `CompileSettleRuntime`
- `PlayModeTransitionRuntime`
- `RequestProcessingRuntime`
- `BridgeRuntimeSnapshotBuilder`

The first implementation may keep one lock at the facade level. The important first move is ownership separation, not lock micro-optimization.

## Phase 4: Assumptions vs Truths

| Started assumption | First-principles replacement |
|---|---|
| Split files because they are long | Split by reason to change and observable contract boundary |
| Use line count as law | Use parity gates as law; line count is a warning signal |
| `Helpers` is a real category | Subsystems need ownership names: scenarios, project actions, runtime state |
| `ScenarioRunner` is one object | It is a scenario VM plus storage, validation, transport, and handlers |
| Runtime state must be monolithic | Unity is global, but lifecycle domains are separable |
| DTO file is harmless | DTOs are public contract surface and need local review boundaries |
| Compile proves safety | Contract parity proves safety; compile is only one gate |

## Phase 5: Aristotelian Move

The highest-leverage move is:

**Create compatibility facades plus parity fixtures before splitting the large files.**

Do not start with a mechanical split. First freeze what must not change:

1. Golden scenario validation payloads.
2. Golden scenario queue/run/result payloads.
3. Golden project action normalized args JSON.
4. Golden bridge status/state payloads.
5. Golden representative error payloads.

Then split one ownership domain at a time behind unchanged facades. Each extraction must satisfy:

`same public input -> same public JSON/state output`

## Target Architecture

```text
Editor/
  Core/
    XUUnityLightMcpOperationRegistry.cs
    XUUnityLightMcpResponseWriter.cs
    Models/
      BridgeModels.cs
      OperationModels.cs
      ConsoleModels.cs
      SceneModels.cs
      TestModels.cs
      GameViewModels.cs
      BuildCompileModels.cs
      ScenarioModels.cs
      SdkDependencyModels.cs
  Bridge/
    XUUnityLightMcpBridgeRuntimeState.cs        # compatibility facade
    Runtime/
      BridgeSessionRuntime.cs
      EditorLifecycleRuntime.cs
      RefreshSettleRuntime.cs
      CompileSettleRuntime.cs
      PlayModeTransitionRuntime.cs
      RequestProcessingRuntime.cs
      BridgeRuntimeSnapshotBuilder.cs
  Scenarios/
    XUUnityLightMcpScenarioRunner.cs           # optional final facade location
    ScenarioValidator.cs
    ScenarioCompiler.cs
    ScenarioRunRepository.cs
    ScenarioScheduler.cs
    ScenarioStepDispatcher.cs
    NestedOperationClient.cs
    ScenarioHookExecutor.cs
    ScenarioResultProjector.cs
    StepHandlers/
      WaitStepHandler.cs
      PlayModeStepHandler.cs
      ConsoleStepHandler.cs
      SceneStepHandler.cs
      CompileStepHandler.cs
      TestsStepHandler.cs
      GameViewStepHandler.cs
      ProjectRefreshStepHandler.cs
      ProjectActionStepHandler.cs
      ProjectDefinedHookStepHandler.cs
      PollUntilStepHandler.cs
  ProjectActions/
    ScenarioProjectActionNormalizer.cs         # facade or renamed owner
    ProjectActionCatalog.cs
    ProjectActionCatalogLoader.cs
    ProjectActionStepBuilder.cs
    ScenarioArgsNormalizer.cs
    PollUntilStepNormalizer.cs
    LightJsonNode.cs
    LightJsonParser.cs
```

Keep namespaces stable unless a compile-safe move requires otherwise. Prefer keeping `XUUnity.LightMcp.Editor.Core` for DTOs so call sites do not churn.

## Server-Side Implementation Waves (Active Handoff)

These are the waves for the next chat. They avoid Unity C# package edits because that track is already in progress elsewhere.

### Server Wave 0: Contract Baseline and Size Report

Objective: make server behavior observable before decomposition.

Actions:

1. Add or extend a report-only size/ownership script for first-party server template `.py` files:
   - warn above 700 lines
   - hard-review above 1200 lines
   - exclude `node_modules`, generated artifacts, test results, and package C# files
2. Capture parity baselines for:
   - CLI `--help` and key subcommand help output
   - MCP tool list JSON
   - representative `call_tool` responses
   - bridge status/final-status summaries from fixture state
   - batch prepare failure summaries
   - scenario result summaries
3. Run the current Python test suite before any extraction.

Acceptance:

- Current code passes the server parity baseline.
- The size report identifies server monoliths, especially `server_batch_orchestrator.py`, `server_bridge_runtime.py`, `server_cli_commands.py`, `server_editor_host.py`, `server_setup_wizard.py`, and `server_summaries.py`.
- No Unity package files are modified.

### Server Wave 1: Split `server_specs.py`

Objective: separate static contracts from runtime logic early.

Actions:

1. Extract tool specs, lifecycle policies, scenario schemas, startup policies, and operation policy tables into a `server_specs/` package or clearly named flat modules.
2. Keep `server_specs.py` as a compatibility facade during migration.
3. Preserve all exported constant names used by tests and downstream modules.

Acceptance:

- MCP tool list JSON unchanged.
- Tests importing old `server_specs` names still pass.
- No import cycles.

### Server Wave 2: Split `server_bridge_runtime.py`

Objective: separate bridge path contracts, transport, liveness, request artifacts, journal, and final-status recovery.

Actions:

1. Extract bridge filesystem/path helpers.
2. Extract transport invocation.
3. Extract heartbeat/liveness and stale-state inspection.
4. Extract request artifacts and journal reading.
5. Extract wait/idle/playmode helpers.
6. Extract final-status and lifecycle recovery logic.
7. Keep `server_bridge_runtime.py` as a compatibility facade.

Acceptance:

- Existing `tests/test_bridge_runtime.py` passes.
- Bridge status/final-status parity fixtures unchanged.
- No CLI or MCP JSON drift.

### Server Wave 3: Split `server_batch_orchestrator.py`

Objective: turn the largest server monolith into batch-lane, bridge-invocation, recovery, and reporting owners.

Actions:

1. Extract batch lane orchestration.
2. Extract project request locking.
3. Extract bridge invocation and bridge response conversion wrappers.
4. Extract recovery/reconciliation helpers.
5. Extract registry/project-context reporting wrappers.
6. Extract JSON-RPC serving wrappers only if they naturally belong outside the orchestrator.
7. Keep `server_batch_orchestrator.py` as a compatibility facade until imports are migrated.

Acceptance:

- `tests/test_multi_project_batch_runner.py` passes.
- `tests/test_batch_operator_ergonomics.py` passes.
- Existing mock/patch import paths in tests remain compatible or are deliberately migrated with tests in the same wave.

### Server Wave 4: Split `server_cli_commands.py`

Objective: make CLI command handlers thin adapters over command families.

Actions:

1. Group commands by family:
   - setup/install
   - project discovery/context
   - batch/build/test
   - bridge/status/recovery
   - scenarios/project actions
   - artifact/reporting/license
2. Preserve argparse command names, option names, output JSON, stdout/stderr behavior, and exit codes.
3. Keep `server_cli_commands.py` as a compatibility facade or command aggregator.

Acceptance:

- CLI snapshot checks pass.
- `python3 templates/server.py --help` and representative subcommand help output are unchanged except for intentional formatting covered by tests.
- No Unity package files are modified.

### Server Wave 5: Split `server_editor_host.py`, `server_setup_wizard.py`, and `server_summaries.py`

Objective: reduce remaining server-side hubs after the highest-risk modules are stable.

Actions:

1. Split editor host into process discovery, editor launch/activation, log resolution, session state, and close/cleanup helpers.
2. Split setup wizard into planning, dependency checks, template installation, validation, and reporting.
3. Split summaries into status summaries, scenario summaries, discovery summaries, verdicts, redaction/truncation utilities.
4. Keep compatibility facades until all tests import the new owners.

Acceptance:

- `tests/test_server_project_helpers.py` passes.
- `tests/test_setup_wizard.py` passes.
- `tests/test_project_discovery.py` passes.
- `tests/test_scenario_decision_verdict.py` passes.
- Summary parity fixtures unchanged.

## Unity-Side Implementation Waves (Delegated / In Progress)

The following waves are retained for product-level context only. Do not execute them in the server-focused chat unless the Unity-side owner explicitly hands them back.

### Wave 0: Guardrails and Fixtures

Objective: make behavior observable before decomposition.

Actions:

1. Add a report-only size/ownership script for first-party package `.cs` files:
   - warn above 500 lines
   - hard-review above 1000 lines
   - exclude `Library`, `node_modules`, generated files, and vendored content
2. Add golden fixture tests or snapshot-style self-tests for:
   - scenario validation
   - project action normalization
   - bridge status/state projection
   - representative error payloads
3. Document public contracts that must not drift:
   - operation names
   - args JSON fields
   - payload JSON fields
   - status/error shape
   - persisted state filenames and fields

Acceptance:

- Current code passes all new parity fixtures.
- Size report identifies the four primary monoliths without failing CI.

### Wave 1: Split DTO Families

Objective: reduce contract review cost with minimal behavioral risk.

Actions:

1. Split `Editor/Core/XUUnityLightMcpModels.cs` into model-family files.
2. Keep the same namespace.
3. Do not rename classes or fields.
4. Do not alter serialization defaults.

Acceptance:

- Unity package compiles.
- Golden JSON payloads unchanged.
- `XUUnityLightMcpModels.cs` is removed or reduced to a short compatibility note if needed.

### Wave 2: Split Project Action Normalization

Objective: separate translation logic from parsers and catalog loading.

Actions:

1. Extract `LightJsonNode` and `LightJsonParser`.
2. Extract `ProjectActionCatalog`, `ProjectActionRecord`, and loader.
3. Extract `ProjectActionStepBuilder`.
4. Extract `ScenarioArgsNormalizer` and `PollUntilStepNormalizer`.
5. Keep `XUUnityLightMcpScenarioProjectActionNormalizer` as facade initially.

Acceptance:

- Same input args JSON produces byte-equivalent normalized JSON.
- Existing unknown-action, mutating-action, invalid-payload, and reserved-key errors are unchanged.
- No scenario behavior changes.

### Wave 3: Split Scenario Runner

Objective: turn the scenario monolith into a real state-machine subsystem.

Actions:

1. Keep facade methods on `XUUnityLightMcpScenarioRunner`.
2. Extract validation to `ScenarioValidator`.
3. Extract executable-step building to `ScenarioCompiler`.
4. Extract persistence and result lookup to `ScenarioRunRepository`.
5. Extract tick/advance/finalize logic to `ScenarioScheduler`.
6. Extract step kind routing to `ScenarioStepDispatcher`.
7. Extract nested operation execution to `NestedOperationClient`.
8. Extract hook creation/execution and predicate checks to `ScenarioHookExecutor`.
9. Extract step handlers by family.

Acceptance:

- Golden scenario validation payloads unchanged.
- Queued run payloads unchanged.
- Result lookup behavior unchanged.
- Pending nested operation recovery behavior unchanged.
- Cleanup-on-failure and stop-on-first-failure behavior unchanged.

### Wave 4: Split Bridge Runtime State

Objective: separate lifecycle domains without changing public status accounting.

Actions:

1. Keep `XUUnityLightMcpBridgeRuntimeState` as facade.
2. Extract session/bootstrap state.
3. Extract editor lifecycle state.
4. Extract refresh/compile/playmode settle trackers.
5. Extract request processing state.
6. Extract status/snapshot projection.
7. Keep the existing locking model first; narrow locks only after parity is proven.

Acceptance:

- Bridge state payload fields unchanged.
- Status payload fields unchanged.
- Domain reload recovery unchanged.
- Persisted playmode transition restore/delete behavior unchanged.
- Request lifecycle fields unchanged during active, pending, completed, and failed operations.

### Wave 5: Secondary File Cleanup

Objective: apply the same ownership standard to 300-550 line files only after the main hubs are stable.

Candidates:

- `XUUnityLightMcpTestRunState.cs`
- `XUUnityLightMcpGameViewUtility.cs`
- `XUUnityLightMcpBridgeTransportRuntime.cs`
- `XUUnityLightMcpBatchBuildCli.cs`
- `XUUnityLightMcpBatchValidationCli.cs`
- `XUUnityLightMcpHealthProbe.cs`
- `XUUnityLightMcpBuildPlayerOperation.cs`
- `XUUnityLightMcpBatchTestFrameworkCli.cs`

Acceptance:

- No secondary split without a named ownership reason.
- No public contract drift.
- Size report remains report-only until false positives are known.

## Global Non-Negotiables

1. Do not rename MCP operation names.
2. Do not rename serialized fields without an explicit migration.
3. Do not change persisted state paths silently.
4. Do not change scenario timing semantics while splitting files.
5. Do not change error codes or error messages unless a test and changelog explicitly cover it.
6. Prefer facade-first extraction over big-bang moves.
7. Every wave must validate independently.
8. Every wave must have a small, reviewable diff.
9. For the active server handoff, do not edit `packages/com.xuunity.light-mcp` because Unity-side work is already owned by another chat.
10. Preserve zero-external-runtime-dependency behavior for installed server templates.
11. Preserve Windows/Unix compatibility:
    - use `pathlib.Path` for filesystem composition
    - avoid hard-coded `/`, `:` drive assumptions, and case-sensitive path assumptions
    - prefer subprocess argument lists over shell strings
    - avoid POSIX-only commands, signals, quoting, globbing, and env syntax
    - keep process-tree cleanup behind host-platform helpers
    - specify UTF-8 when reading/writing JSON/text contracts
    - keep newline-tolerant snapshots unless exact newlines are the contract

## Validation Plan

Minimum validation after each wave:

1. Host Python unit tests relevant to the touched server modules.
2. CLI snapshot/help parity for touched commands.
3. MCP tool-list and representative `call_tool` parity.
4. Bridge status/final-status fixture parity when bridge modules are touched.
5. Scenario result summary parity when scenario/reporting modules are touched.
6. Size/ownership report remains report-only.
7. Cross-platform review for touched code: no new POSIX-only or Windows-only behavior.

Strong validation before final merge:

1. Full host Python test suite.
2. CLI snapshot checks.
3. Multi-project batch runner tests.
4. Batch operator ergonomics tests.
5. Bridge runtime tests.
6. Setup wizard tests.
7. Windows-sensitive tests when process/path/launcher/setup code is touched: `tests/test_windows_host_helpers.py`, `tests/test_wrapper_source_root.py`, `tests/test_process_support.py`, and relevant setup wizard tests.
8. Cross-runtime Unity package compile/self-tests only after coordination with the Unity-side chat.

## Definition of Done

1. Server-side first-party template monoliths above 1200 lines are decomposed or explicitly justified.
2. `server_batch_orchestrator.py`, `server_bridge_runtime.py`, `server_cli_commands.py`, `server_editor_host.py`, `server_setup_wizard.py`, and `server_summaries.py` are reduced behind compatibility facades or scheduled with clear ownership if not all fit in one implementation pass.
3. Public MCP JSON contracts are unchanged.
4. CLI subcommands, stdout/stderr behavior, and exit codes are unchanged.
5. Persisted bridge/server state contracts are unchanged or explicitly migrated.
6. New server code has named ownership boundaries, not second-order `server_*` dumping grounds.
7. Size/ownership report prevents silent re-growth.
8. Unity package work remains unmodified by the server-focused implementation unless explicitly coordinated.
9. Server code remains Windows/Unix compatible, with platform-sensitive behavior routed through existing host/platform/process helpers.

## Prompt for a New Chat

Use this prompt to start a new implementation chat:

```text
You are working in this repo:
<AIRoot>

Goal: implement the design in this file:
<AIRoot>/Operations/XUUnityLightUnityMcp/docs/architecture/designs/XUUNITY_MCP_MONOLITH_REDUCTION_FIRST_PRINCIPLES_PLAN_2026-06-25.md

Target: the server/template side of XUUnity Light Unity MCP:
<AIRoot>/Operations/XUUnityLightUnityMcp/templates

Coordination note:
Another chat is already working on the Unity C# package side:
<AIRoot>/Operations/XUUnityLightUnityMcp/packages/com.xuunity.light-mcp

Do not edit `packages/com.xuunity.light-mcp`.
You may read Unity package files only for contract inspection.
Do not touch the broader XUUnity protocol and do not refactor game Unity projects.

Main task: reduce monolithicity in the MCP server/template code, starting with:
- templates/server_batch_orchestrator.py
- templates/server_bridge_runtime.py
- templates/server_cli_commands.py
- templates/server_editor_host.py
- templates/server_setup_wizard.py
- templates/server_summaries.py
- templates/server_specs.py

Core principle:
Do not split by line count. Split by ownership and observable contract boundaries.
Build compatibility facades and parity fixtures first, then extract.

Mandatory rules:
1. Do not rename MCP operation names.
2. Do not change JSON args/payload/status/error shapes without an explicit migration.
3. Do not change persisted state paths or fields without an explicit migration.
4. Do not change scenario timing semantics.
5. Do not change error codes or error messages without tests and changelog coverage.
6. Work wave by wave with small, reviewable diffs.
7. After each wave, run the available compile/test validation.
8. Respect the dirty git tree: do not revert changes you did not make.
9. Preserve zero-external-runtime-dependency behavior for installed server templates.
10. Do not conflict with the Unity-side chat: do not edit C# package files.
11. Preserve Windows/Unix support:
    - use pathlib.Path for filesystem paths
    - use subprocess argv lists, not shell strings
    - avoid POSIX-only commands, quoting, env syntax, and signals
    - route process cleanup through host-platform/process helpers
    - use explicit UTF-8 for JSON/text I/O
    - do not assume path case sensitivity

Work plan:
Server Wave 0:
- Add or extend a report-only size/ownership script for first-party server template `.py` files.
- Add parity baselines for CLI help/snapshots, MCP tool list, representative `call_tool` responses, bridge status/final-status summaries, batch prepare failures, and scenario summaries.
- Confirm the current code passes these fixtures/tests before extraction.

Server Wave 1:
- Split `templates/server_specs.py` into tool specs, lifecycle policies, scenario schema, and startup policies.
- Keep `server_specs.py` as a compatibility facade.

Server Wave 2:
- Split `templates/server_bridge_runtime.py` into bridge paths, transport, liveness, request artifacts, journal, waits, and final-status/lifecycle recovery.
- Keep `server_bridge_runtime.py` as a compatibility facade.

Server Wave 3:
- Split `templates/server_batch_orchestrator.py` into batch lanes, request locks, bridge invocation, recovery, context reports, and error/result formatting.
- Keep `server_batch_orchestrator.py` as a compatibility facade.

Server Wave 4:
- Split `templates/server_cli_commands.py` into command-family modules.
- Preserve CLI subcommands, options, stdout/stderr behavior, and exit codes.

Server Wave 5:
- Split `templates/server_editor_host.py`, `templates/server_setup_wizard.py`, and `templates/server_summaries.py` by ownership boundaries.

Acceptance:
- Same input -> same public JSON/state output.
- CLI help/output parity unchanged.
- MCP tool list and call_tool parity unchanged.
- Host Python tests pass.
- Windows/Unix-sensitive tests pass when touched code affects paths, processes, setup, launchers, or shell behavior.
- Golden parity tests pass.
- No public MCP contract drift.
- No edits under packages/com.xuunity.light-mcp.

First read the design file, then inspect the current git status in AIRoot and Operations/XUUnityLightUnityMcp, then start with Server Wave 0. Do not stop at planning; implement the server-side track.
```
