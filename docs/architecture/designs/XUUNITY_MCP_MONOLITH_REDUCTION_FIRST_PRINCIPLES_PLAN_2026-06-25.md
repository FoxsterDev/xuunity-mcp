# XUUnity MCP Monolith Reduction First-Principles Plan

Date: `2026-06-25`
Status: `design plan ready for implementation`
Target: `Operations/XUUnityLightUnityMcp/packages/com.xuunity.light-mcp`

## Problem

The MCP Unity package has several first-party files that have grown into mixed-responsibility hubs:

- `Editor/Helpers/XUUnityLightMcpScenarioRunner.cs` - 2182 lines
- `Editor/Helpers/XUUnityLightMcpScenarioProjectActionNormalizer.cs` - 1236 lines
- `Editor/Bridge/XUUnityLightMcpBridgeRuntimeState.cs` - 1152 lines
- `Editor/Core/XUUnityLightMcpModels.cs` - 1042 lines
- secondary candidates around 300-550 lines: test run state, game view utility, bridge transport runtime, batch CLIs, health probe, build player operation

The goal is not to chase a fixed line-count rule. The goal is to reduce hidden coupling, make future MCP changes cheaper, and protect observable MCP behavior while decomposing the code.

## Phase 1: Assumption Autopsy

1. Assumption: "large file equals bad file."
   - Source: industry habit.
   - Correction: size is only a signal. The actual defect is mixed reasons to change.

2. Assumption: "files should be split by line threshold."
   - Source: old line-count culture.
   - Correction: the XUUnity protocol already replaced line-count thinking with invariants. For MCP code, the equivalent invariant is observable contract parity.

3. Assumption: "the current folders define the right boundaries."
   - Source: inherited structure: `Helpers`, `Bridge`, `Core`, `Operations`.
   - Correction: folders describe location, not ownership. `Helpers` currently hides full subsystems.

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

## Phase 2: Irreducible Truths

1. MCP operation names, args JSON shape, payload JSON shape, response status/error shape, and persisted files are external contracts.
2. Safe decomposition requires preserving observable behavior, not merely compiling.
3. Scenario execution is a state machine, not a helper method.
4. Scenario validation, scenario execution, nested operation transport, hook execution, and result storage have different consumers and failure modes.
5. Project action normalization is a translation boundary from user-authored scenario JSON to executable hook steps.
6. Bridge runtime state is a composition of lifecycle domains, even if a facade keeps one public API.
7. DTO families should be grouped by operation family so contract review can be local.
8. A file-size guard is useful only as a maintainability warning. It is not a design law.
9. The best extraction boundary is the one where a parity test can be placed.

## Phase 3: Rebuild From First Principles

### Approach A: Contract-First MCP Core

Build the code around observable MCP contracts:

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

Existing public classes stay as compatibility facades during rollout.

### Approach B: Scenario State Machine First

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

### Approach C: Lifecycle Domain Runtime

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

## Implementation Waves

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
7. Every wave must compile independently.
8. Every wave must have a small, reviewable diff.

## Validation Plan

Minimum validation after each wave:

1. Unity package compile.
2. Existing package self-tests.
3. Golden fixture parity tests added in Wave 0.
4. Scenario validate/run/result smoke.
5. Bridge status/state smoke.

Strong validation before final merge:

1. EditMode self-tests.
2. PlayMode self-tests if available in the consumer project.
3. Scenario with nested operation.
4. Scenario with project-defined hook.
5. Scenario with cleanup-on-failure.
6. Bridge lifecycle check across refresh/compile/playmode transition.

## Definition of Done

1. No first-party MCP implementation file above 1000 lines unless explicitly justified.
2. The four primary monoliths are decomposed behind compatibility facades.
3. Scenario, project-action, bridge-state, and DTO contracts have parity tests.
4. Public MCP JSON contracts are unchanged.
5. Persisted state contracts are unchanged or explicitly migrated.
6. New code has named ownership boundaries, not generic `Helpers` dumping grounds.
7. Size/ownership report prevents silent re-growth.

## Prompt for a New Chat

Use this prompt to start a new implementation chat:

```text
Ты работаешь в repo:
/Users/siarheikha/Projects/Work/GameStory/Apperfun/AIRoot

Цель: реализовать дизайн из файла:
/Users/siarheikha/Projects/Work/GameStory/Apperfun/AIRoot/Operations/XUUnityLightUnityMcp/docs/architecture/designs/XUUNITY_MCP_MONOLITH_REDUCTION_FIRST_PRINCIPLES_PLAN_2026-06-25.md

Таргет: только XUUnity Light Unity MCP код:
/Users/siarheikha/Projects/Work/GameStory/Apperfun/AIRoot/Operations/XUUnityLightUnityMcp/packages/com.xuunity.light-mcp

Не трогай весь XUUnity protocol и не рефактори игровые Unity проекты.

Главная задача: уменьшить монолитность MCP package code, начиная с:
- Editor/Helpers/XUUnityLightMcpScenarioRunner.cs
- Editor/Helpers/XUUnityLightMcpScenarioProjectActionNormalizer.cs
- Editor/Bridge/XUUnityLightMcpBridgeRuntimeState.cs
- Editor/Core/XUUnityLightMcpModels.cs

Ключевой принцип:
Не режь по line-count. Режь по ownership и observable contract boundaries.
Сначала compatibility facades + parity fixtures, потом extraction.

Обязательные правила:
1. Не переименовывай MCP operation names.
2. Не меняй JSON args/payload/status/error shape без explicit migration.
3. Не меняй persisted state paths/fields без explicit migration.
4. Не меняй scenario timing semantics.
5. Не меняй error codes/messages без теста и changelog.
6. Делай wave-by-wave, маленькими reviewable diffs.
7. После каждой волны запускай доступную compile/test validation.
8. Учитывай dirty git tree: не откатывай чужие изменения.

Рабочий план:
Wave 0:
- Добавь report-only size/ownership script для first-party package .cs files.
- Добавь golden/parity fixtures для scenario validation, project action normalization, bridge status/state projection, representative errors.
- Убедись, что текущий код проходит эти fixtures.

Wave 1:
- Раздели Editor/Core/XUUnityLightMcpModels.cs на DTO-family files с тем же namespace и без rename классов/полей.

Wave 2:
- Раздели XUUnityLightMcpScenarioProjectActionNormalizer.cs:
  LightJsonNode/LightJsonParser,
  ProjectActionCatalog/Record/Loader,
  ProjectActionStepBuilder,
  ScenarioArgsNormalizer,
  PollUntilStepNormalizer.
- Сохрани XUUnityLightMcpScenarioProjectActionNormalizer как facade.

Wave 3:
- Раздели XUUnityLightMcpScenarioRunner.cs:
  ScenarioValidator,
  ScenarioCompiler,
  ScenarioRunRepository,
  ScenarioScheduler,
  ScenarioStepDispatcher,
  NestedOperationClient,
  ScenarioHookExecutor,
  StepHandlers/*.
- Сохрани старые public facade methods: Validate, HasActiveRun, QueueRun, Tick, TryReadResult.

Wave 4:
- Раздели XUUnityLightMcpBridgeRuntimeState.cs:
  BridgeSessionRuntime,
  EditorLifecycleRuntime,
  RefreshSettleRuntime,
  CompileSettleRuntime,
  PlayModeTransitionRuntime,
  RequestProcessingRuntime,
  BridgeRuntimeSnapshotBuilder.
- Сохрани facade и сначала сохрани существующую locking model.

Acceptance:
- Same input -> same public JSON/state output.
- Unity package compiles.
- Existing self-tests pass.
- Golden parity tests pass.
- No public MCP contract drift.

Сначала прочитай design file, затем осмотри текущий git status внутри AIRoot и Operations/XUUnityLightUnityMcp, затем начни с Wave 0. Не останавливайся на плане, реализуй.
```
