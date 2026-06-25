using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;
using XUUnity.LightMcp.Editor.ScenarioHooks;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioShared;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioCompiler;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioRunRepository;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioStepDispatcher;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioScheduler
    {
        public static XUUnityLightMcpScenarioRunPayload QueueRun(XUUnityLightMcpScenarioDefinition scenario)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();

            var runId = Guid.NewGuid().ToString("N");
            var scenarioName = NormalizeScenarioName(scenario?.name);
            var nowUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            var resultPath = BuildResultPath(runId, scenarioName);

            var executableScenario = CloneScenarioWithExecutableSteps(scenario, out var cleanupStartIndex);
            var state = new XUUnityLightMcpScenarioRunState
            {
                runId = runId,
                scenario = executableScenario,
                status = "queued",
                startedAtUtc = nowUtc,
                updatedAtUtc = nowUtc,
                completedAtUtc = "",
                resultPath = resultPath,
                currentStepIndex = 0,
                cleanupStartIndex = cleanupStartIndex,
                bodyFailed = false,
                waitingUntilUtc = "",
                steps = new List<XUUnityLightMcpScenarioStepResult>(),
            };

            foreach (var step in executableScenario.steps)
            {
                state.steps.Add(new XUUnityLightMcpScenarioStepResult
                {
                    stepId = step.stepId,
                    kind = NormalizeStepKind(step),
                    status = "pending",
                });
            }

            SaveState(state);
            PersistResult(state);
            return BuildPayload(state);
        }

        public static void Tick()
        {
            if (!TryLoadState(out var state))
            {
                return;
            }

            if (state == null || state.status == "passed" || state.status == "failed")
            {
                return;
            }

            try
            {
                if (state.currentStepIndex >= state.scenario.steps.Count)
                {
                    CompleteRun(state, CountSteps(state.steps, "failed") > 0 ? "failed" : "passed");
                    return;
                }

                state.status = "running";
                state.updatedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");

                var step = state.scenario.steps[state.currentStepIndex];
                var stepResult = state.steps[state.currentStepIndex];
                if (ShouldSkipStepForDependencies(state, step, stepResult))
                {
                    PersistResult(state);
                    SaveState(state);
                    state.currentStepIndex++;
                    state.waitingUntilUtc = "";
                    PersistResult(state);
                    SaveState(state);
                    return;
                }

                var shouldAdvance = ProcessStep(state, step, stepResult);

                PersistResult(state);
                SaveState(state);

                if (!shouldAdvance)
                {
                    return;
                }

                if (stepResult.status == "failed" && (state.scenario.stopOnFirstFailure || step.continueToCleanupOnFail))
                {
                    state.bodyFailed = true;
                    if (TryJumpToCleanup(state))
                    {
                        PersistResult(state);
                        SaveState(state);
                        return;
                    }

                    CompleteRun(state, "failed");
                    return;
                }

                state.currentStepIndex++;
                state.waitingUntilUtc = "";

                if (state.currentStepIndex >= state.scenario.steps.Count)
                {
                    CompleteRun(state, CountSteps(state.steps, "failed") > 0 ? "failed" : "passed");
                    return;
                }

                PersistResult(state);
                SaveState(state);
            }
            catch (Exception ex)
            {
                CleanupScenarioOwnedTransientState(state);
                state.status = "failed";
                state.completedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
                state.updatedAtUtc = state.completedAtUtc;
                PersistResult(state, "scenario_runner_failed", ex.Message);
                SaveState(state);
                SafeDeleteActiveState();
                UnityEngine.Debug.LogException(ex);
            }
        }
        public static bool ShouldSkipStepForDependencies(
            XUUnityLightMcpScenarioRunState state,
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult)
        {
            var dependencies = DependencyIds(step).ToList();
            if (dependencies.Count == 0)
            {
                return false;
            }

            foreach (var dependency in dependencies)
            {
                var dependencyResult = FindStepResult(state, dependency);
                if (dependencyResult == null || dependencyResult.status != "passed")
                {
                    stepResult.status = "skipped";
                    stepResult.outcome = $"dependency_not_passed:{dependency}";
                    stepResult.error_code = "";
                    stepResult.error_message = "";
                    return true;
                }
            }

            return false;
        }

        public static XUUnityLightMcpScenarioStepResult FindStepResult(
            XUUnityLightMcpScenarioRunState state,
            string stepId)
        {
            return state.steps.FirstOrDefault(item => string.Equals(item.stepId, stepId, StringComparison.Ordinal));
        }

        public static bool TryJumpToCleanup(XUUnityLightMcpScenarioRunState state)
        {
            if (state.cleanupStartIndex < 0
                || state.cleanupStartIndex >= state.scenario.steps.Count
                || state.currentStepIndex >= state.cleanupStartIndex)
            {
                return false;
            }

            state.currentStepIndex = state.cleanupStartIndex;
            state.waitingUntilUtc = "";
            state.updatedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            return true;
        }
        public static void CompleteRun(XUUnityLightMcpScenarioRunState state, string finalStatus)
        {
            CleanupScenarioOwnedTransientState(state);
            state.status = finalStatus;
            state.completedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            state.updatedAtUtc = state.completedAtUtc;
            PersistResult(state);
            SaveState(state);
            SafeDeleteActiveState();
        }

        public static void CleanupScenarioOwnedTransientState(XUUnityLightMcpScenarioRunState state)
        {
            if (state == null)
            {
                return;
            }

            var playModeTransitionRequestId = XUUnityLightMcpBridgeRuntimeState.PlayModeTransitionRequestId;
            if (XUUnityLightMcpBridgeRuntimeState.PlayModeTransitionPending
                && IsScenarioOwnedRequestId(playModeTransitionRequestId, state))
            {
                XUUnityLightMcpBridgeRuntimeState.CancelPlayModeTransitionTracking();
            }
        }

        public static bool IsScenarioOwnedRequestId(string requestId, XUUnityLightMcpScenarioRunState state)
        {
            if (string.IsNullOrWhiteSpace(requestId))
            {
                return false;
            }

            if (string.Equals(requestId, state.pendingNestedRequestId, StringComparison.Ordinal))
            {
                return true;
            }

            return requestId.StartsWith("scenario_", StringComparison.Ordinal);
        }
    }
}
