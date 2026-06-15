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

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpScenarioRunner
    {
        public static XUUnityLightMcpScenarioValidatePayload Validate(XUUnityLightMcpScenarioDefinition scenario)
        {
            var payload = new XUUnityLightMcpScenarioValidatePayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                scenario_name = NormalizeScenarioName(scenario?.name),
            };

            var steps = BuildExecutableSteps(scenario, out var cleanupStartIndex);
            payload.total_steps = steps.Count;

            if (string.IsNullOrWhiteSpace(scenario?.name))
            {
                AddIssue(payload, "error", "missing_name", "Scenario name is required.", "", -1);
            }

            if ((scenario?.steps ?? new List<XUUnityLightMcpScenarioStepDefinition>()).Count == 0)
            {
                AddIssue(payload, "error", "missing_steps", "Scenario must contain at least one step.", "", -1);
            }

            var seenStepIds = new HashSet<string>(StringComparer.Ordinal);
            for (var i = 0; i < steps.Count; i++)
            {
                var step = steps[i] ?? new XUUnityLightMcpScenarioStepDefinition();
                var stepId = NormalizeStepId(step, i);
                payload.steps.Add(new XUUnityLightMcpScenarioStepSummary
                {
                    stepId = stepId,
                    kind = NormalizeStepKind(step),
                });

                if (!seenStepIds.Add(stepId))
                {
                    AddIssue(payload, "error", "duplicate_step_id", $"Duplicate stepId '{stepId}'.", stepId, i);
                }

                ValidateStepDependencies(payload, step, stepId, i, seenStepIds);
                ValidateStep(payload, step, stepId, i);
            }

            payload.status = payload.error_count > 0 ? "invalid" : "valid";
            return payload;
        }

        public static bool HasActiveRun()
        {
            return File.Exists(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath);
        }

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

        public static bool TryReadResult(string runId, string scenarioName, out XUUnityLightMcpScenarioRunPayload payload, out string errorCode, out string errorMessage)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            payload = null;
            errorCode = "";
            errorMessage = "";

            if (!string.IsNullOrWhiteSpace(runId))
            {
                var path = FindResultPathByRunId(runId.Trim());
                if (path == null)
                {
                    errorCode = "scenario_run_not_found";
                    errorMessage = $"No scenario result found for runId '{runId}'.";
                    return false;
                }

                return TryReadPayload(path, out payload, out errorCode, out errorMessage);
            }

            if (!string.IsNullOrWhiteSpace(scenarioName))
            {
                var path = FindLatestResultPathByScenarioName(NormalizeScenarioName(scenarioName));
                if (path == null)
                {
                    errorCode = "scenario_result_not_found";
                    errorMessage = $"No scenario result found for scenario '{scenarioName}'.";
                    return false;
                }

                return TryReadPayload(path, out payload, out errorCode, out errorMessage);
            }

            var latest = FindLatestResultPath();
            if (latest == null)
            {
                errorCode = "scenario_result_not_found";
                errorMessage = "No scenario result files found.";
                return false;
            }

            return TryReadPayload(latest, out payload, out errorCode, out errorMessage);
        }

        static XUUnityLightMcpScenarioDefinition CloneScenarioWithExecutableSteps(
            XUUnityLightMcpScenarioDefinition scenario,
            out int cleanupStartIndex)
        {
            var steps = BuildExecutableSteps(scenario, out cleanupStartIndex);
            return new XUUnityLightMcpScenarioDefinition
            {
                name = scenario?.name ?? "",
                description = scenario?.description ?? "",
                stopOnFirstFailure = scenario?.stopOnFirstFailure ?? true,
                steps = steps,
                cleanupSteps = scenario?.cleanupSteps ?? new List<XUUnityLightMcpScenarioStepDefinition>(),
            };
        }

        static List<XUUnityLightMcpScenarioStepDefinition> BuildExecutableSteps(
            XUUnityLightMcpScenarioDefinition scenario,
            out int cleanupStartIndex)
        {
            var bodySteps = scenario?.steps ?? new List<XUUnityLightMcpScenarioStepDefinition>();
            var cleanupSteps = scenario?.cleanupSteps ?? new List<XUUnityLightMcpScenarioStepDefinition>();
            cleanupStartIndex = cleanupSteps.Count > 0 ? bodySteps.Count : -1;

            var result = new List<XUUnityLightMcpScenarioStepDefinition>(bodySteps.Count + cleanupSteps.Count);
            result.AddRange(bodySteps);
            result.AddRange(cleanupSteps);
            return result;
        }

        static bool ShouldSkipStepForDependencies(
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

        static IEnumerable<string> DependencyIds(XUUnityLightMcpScenarioStepDefinition step)
        {
            foreach (var dependency in step?.dependsOn ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(dependency))
                {
                    yield return dependency.Trim();
                }
            }

            foreach (var dependency in step?.runIfStepPassed ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(dependency))
                {
                    yield return dependency.Trim();
                }
            }
        }

        static XUUnityLightMcpScenarioStepResult FindStepResult(
            XUUnityLightMcpScenarioRunState state,
            string stepId)
        {
            return state.steps.FirstOrDefault(item => string.Equals(item.stepId, stepId, StringComparison.Ordinal));
        }

        static bool TryJumpToCleanup(XUUnityLightMcpScenarioRunState state)
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

        static bool ProcessStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var kind = NormalizeStepKind(step);

            switch (kind)
            {
                case "wait":
                    return ProcessWaitStep(state, step, stepResult);
                case "wait_for_playmode_state":
                    return ProcessWaitForPlayModeStateStep(state, step, stepResult);
                case "assert_playmode_state":
                    return ProcessAssertPlayModeStateStep(step, stepResult);
                case "status":
                    return ProcessNestedOperationStep("unity.status", "{}", stepResult);
                case "health_probe":
                    return ProcessNestedOperationStep("unity.health.probe", "{}", stepResult);
                case "scene_snapshot":
                    return ProcessNestedOperationStep("unity.scene.snapshot", "{}", stepResult);
                case "assert_scene":
                    return ProcessAssertSceneStep(step, stepResult);
                case "project_refresh":
                    return ProcessProjectRefreshStep(state, step, stepResult);
                case "console_tail":
                    return ProcessConsoleTailStep(step, stepResult);
                case "console_grep":
                    return ProcessConsoleGrepStep(step, stepResult);
                case "playmode_set":
                    return ProcessPlayModeSetStep(step, stepResult);
                case "game_view_screenshot":
                    return ProcessGameViewScreenshotStep(step, stepResult);
                case "compile_player_scripts":
                    return ProcessCompilePlayerScriptsStep(state, step, stepResult);
                case "tests_run_editmode":
                    return ProcessEditModeTestsStep(state, step, stepResult);
                case "tests_run_playmode":
                    return ProcessPlayModeTestsStep(state, step, stepResult);
                case "game_view_configure":
                    return ProcessGameViewConfigureStep(step, stepResult);
                case "project_action":
                    return ProcessProjectActionStep(step, stepResult);
                case "project_defined_hook":
                    return ProcessProjectDefinedHookStep(step, stepResult);
                case "project_defined_hook_poll_until":
                    return ProcessProjectDefinedHookPollUntilStep(state, step, stepResult);
                default:
                    stepResult.status = "failed";
                    stepResult.error_code = "unsupported_scenario_step";
                    stepResult.error_message = $"Unsupported scenario step kind '{kind}'.";
                    return true;
            }
        }

        static bool ProcessWaitStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (stepResult.status == "pending")
            {
                var waitUntil = DateTime.UtcNow.AddSeconds(Math.Max(0.0d, step.durationSeconds));
                state.waitingUntilUtc = waitUntil.ToString("yyyy-MM-ddTHH:mm:ssZ");
                stepResult.status = "running";
                stepResult.outcome = "waiting";
                return false;
            }

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario wait step lost its deadline state.";
                return true;
            }

            if (DateTime.UtcNow < deadlineUtc)
            {
                return false;
            }

            stepResult.status = "passed";
            stepResult.outcome = "wait_completed";
            stepResult.duration_seconds = Math.Round(Math.Max(0.0d, step.durationSeconds), 6);
            return true;
        }

        static bool ProcessWaitForPlayModeStateStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (stepResult.status == "pending")
            {
                var timeoutSeconds = step.timeoutSeconds > 0.0d ? step.timeoutSeconds : 10.0d;
                var waitUntil = DateTime.UtcNow.AddSeconds(timeoutSeconds);
                state.waitingUntilUtc = waitUntil.ToString("yyyy-MM-ddTHH:mm:ssZ");
                stepResult.status = "running";
                stepResult.outcome = "waiting_for_playmode_state";
            }

            var currentState = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState();
            if (string.Equals(currentState, step.expectedPlaymodeState, StringComparison.OrdinalIgnoreCase))
            {
                stepResult.status = "passed";
                stepResult.outcome = $"playmode_state_reached:{currentState}";
                return true;
            }

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario play mode wait step lost its deadline state.";
                XUUnityLightMcpBridgeRuntimeState.CancelPlayModeTransitionTracking();
                return true;
            }

            if (DateTime.UtcNow < deadlineUtc)
            {
                return false;
            }

            stepResult.status = "failed";
            stepResult.error_code = "playmode_state_timeout";
            stepResult.error_message =
                $"Timed out waiting for play mode state '{step.expectedPlaymodeState}'. Last observed state: '{currentState}'.";
            XUUnityLightMcpBridgeRuntimeState.CancelPlayModeTransitionTracking();
            return true;
        }

        static bool ProcessAssertPlayModeStateStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var currentState = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState();
            if (string.Equals(currentState, step.expectedPlaymodeState, StringComparison.OrdinalIgnoreCase))
            {
                stepResult.status = "passed";
                stepResult.outcome = $"asserted_playmode_state:{currentState}";
            }
            else
            {
                stepResult.status = "failed";
                stepResult.error_code = "unexpected_playmode_state";
                stepResult.error_message =
                    $"Expected play mode state '{step.expectedPlaymodeState}', but observed '{currentState}'.";
            }

            return true;
        }

        static bool ProcessConsoleTailStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpConsoleTailArgs
            {
                limit = step.limit > 0 ? step.limit : 50,
                includeTypes = step.includeTypes,
            };

            return ProcessNestedOperationStep("unity.console.tail", JsonUtility.ToJson(args), stepResult);
        }

        static bool ProcessConsoleGrepStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpConsoleGrepArgs
            {
                pattern = step.pattern,
                regex = step.regex,
                ignoreCase = step.ignoreCase,
                includeStackTraces = step.includeStackTraces,
                limit = step.limit > 0 ? step.limit : 20,
                includeTypes = step.includeTypes,
            };

            return ProcessNestedOperationStep("unity.console.grep", JsonUtility.ToJson(args), stepResult);
        }

        static bool ProcessAssertSceneStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpSceneAssertArgs
            {
                expectedName = step.expectedName,
                expectedPath = step.expectedPath,
                requiredRootNames = step.requiredRootNames,
                allowDirty = step.allowDirty,
            };

            var response = ExecuteNestedOperation("unity.scene.assert", JsonUtility.ToJson(args));
            ApplyNestedResponse(stepResult, response, DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"));
            if (response == null || response.status != "ok")
            {
                return true;
            }

            var payload = string.IsNullOrWhiteSpace(response.payload_json)
                ? null
                : JsonUtility.FromJson<XUUnityLightMcpSceneAssertPayload>(response.payload_json);

            stepResult.payload_json = response.payload_json ?? "";
            if (payload != null && payload.passed)
            {
                stepResult.status = "passed";
                stepResult.outcome = "scene_asserted";
                return true;
            }

            stepResult.status = "failed";
            stepResult.error_code = "scene_assertion_failed";
            stepResult.error_message = string.IsNullOrWhiteSpace(payload?.failure_reason)
                ? "Scene assertion failed."
                : payload.failure_reason;
            stepResult.outcome = "scene_assertion_failed";
            return true;
        }

        static bool ProcessPlayModeSetStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpPlayModeSetArgs
            {
                action = step.action,
            };

            return ProcessNestedOperationStep("unity.playmode.set", JsonUtility.ToJson(args), stepResult);
        }

        static bool ProcessGameViewScreenshotStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpGameViewScreenshotArgs
            {
                fileName = step.fileName,
                includeImage = step.includeImage,
                maxResolution = step.maxResolution > 0 ? step.maxResolution : 640,
            };

            return ProcessNestedOperationStep("unity.game_view.screenshot", JsonUtility.ToJson(args), stepResult);
        }

        static bool ProcessCompilePlayerScriptsStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessCompilePlayerScriptsStep(null, step, stepResult);
        }

        static bool ProcessCompilePlayerScriptsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpCompilePlayerScriptsArgs
            {
                name = step.name,
                target = step.target,
                optionFlags = step.optionFlags,
                extraDefines = step.extraDefines,
            };

            if (state == null)
            {
                return ProcessNestedOperationStep("unity.compile.player_scripts", JsonUtility.ToJson(args), stepResult);
            }

            if (stepResult.status == "pending")
            {
                var request = BuildNestedRequest("unity.compile.player_scripts", JsonUtility.ToJson(args), GetTimeoutMs(step, 90.0d));
                var stopwatch = Stopwatch.StartNew();
                var response = ExecuteNestedOperation(request.operation, request.args_json, request);
                stopwatch.Stop();

                stepResult.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
                if (response == null)
                {
                    stepResult.status = "failed";
                    stepResult.error_code = "null_nested_response";
                    stepResult.error_message = "compile_player_scripts returned no response.";
                    return true;
                }

                stepResult.payload_json = response.payload_json ?? "";
                if (response.status != "ok")
                {
                    stepResult.status = "failed";
                    stepResult.error_code = response.error?.code ?? "compile_player_scripts_failed";
                    stepResult.error_message = response.error?.message ?? "compile_player_scripts failed.";
                    return true;
                }

                state.pendingNestedRequestId = request.request_id;
                state.pendingNestedOperation = request.operation;
                state.pendingNestedStartedAtUtc = request.created_at_utc;
                state.pendingNestedStableTickCount = 0;
                state.waitingUntilUtc = DateTime.UtcNow.AddSeconds(GetTimeoutSeconds(step, 90.0d)).ToString("yyyy-MM-ddTHH:mm:ssZ");
                stepResult.status = "running";
                stepResult.outcome = "compile_waiting_for_settle";
                return false;
            }

            if (stepResult.status != "running")
            {
                return true;
            }

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario compile step lost its deadline state.";
                ClearPendingNestedOperation(state);
                return true;
            }

            if (IsEditorIdleForCompileSettle(stepResult))
            {
                state.pendingNestedStableTickCount++;
                if (state.pendingNestedStableTickCount >= 2)
                {
                    FinalizeCompilePlayerScriptsStep(stepResult);
                    ClearPendingNestedOperation(state);
                    return true;
                }
            }
            else
            {
                state.pendingNestedStableTickCount = 0;
            }

            if (DateTime.UtcNow < deadlineUtc)
            {
                return false;
            }

            stepResult.status = "failed";
            stepResult.error_code = "compile_player_scripts_timeout";
            stepResult.error_message = "Timed out waiting for compile_player_scripts to settle.";
            ClearPendingNestedOperation(state);
            return true;
        }

        static bool ProcessEditModeTestsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessTestsStep(state, step, stepResult, "unity.tests.run_editmode", "EditMode");
        }

        static bool ProcessPlayModeTestsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessTestsStep(state, step, stepResult, "unity.tests.run_playmode", "PlayMode");
        }

        static bool ProcessTestsStep(
            XUUnityLightMcpScenarioRunState state,
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult,
            string operationName,
            string modeLabel)
        {
            if (stepResult.status == "pending")
            {
                var request = BuildNestedRequest(operationName, XUUnityLightMcpTestArgsUtility.BuildTestsArgsJson(step), GetTimeoutMs(step, 600.0d));
                var response = ExecuteNestedOperation(request.operation, request.args_json, request);
                if (response != null)
                {
                    ApplyTestsResponse(stepResult, response, request.created_at_utc, modeLabel);
                    return true;
                }

                state.pendingNestedRequestId = request.request_id;
                state.pendingNestedOperation = request.operation;
                state.pendingNestedStartedAtUtc = request.created_at_utc;
                state.waitingUntilUtc = DateTime.UtcNow.AddSeconds(GetTimeoutSeconds(step, 600.0d)).ToString("yyyy-MM-ddTHH:mm:ssZ");
                stepResult.status = "running";
                stepResult.outcome = "tests_running";
                return false;
            }

            if (stepResult.status != "running")
            {
                return true;
            }

            if (TryGetCapturedPendingNestedResponse(state, out var capturedResponse))
            {
                if (ShouldWaitForPlayModeTestsSettle(operationName, capturedResponse))
                {
                    if (IsEditorIdleForPlayModeTestsSettle())
                    {
                        state.pendingNestedStableTickCount++;
                        if (state.pendingNestedStableTickCount >= 2)
                        {
                            ApplyTestsResponse(stepResult, capturedResponse, state.pendingNestedStartedAtUtc, modeLabel);
                            ClearPendingNestedOperation(state);
                            return true;
                        }
                    }
                    else
                    {
                        state.pendingNestedStableTickCount = 0;
                    }

                    stepResult.outcome = "tests_waiting_for_settle";
                }
                else
                {
                    ApplyTestsResponse(stepResult, capturedResponse, state.pendingNestedStartedAtUtc, modeLabel);
                    ClearPendingNestedOperation(state);
                    return true;
                }
            }
            else if (TryTakePendingNestedResponse(state.pendingNestedRequestId, out var pendingResponse))
            {
                if (ShouldWaitForPlayModeTestsSettle(operationName, pendingResponse))
                {
                    CapturePendingNestedResponse(state, pendingResponse);
                    state.pendingNestedStableTickCount = 0;
                    stepResult.outcome = "tests_waiting_for_settle";
                }
                else
                {
                    ApplyTestsResponse(stepResult, pendingResponse, state.pendingNestedStartedAtUtc, modeLabel);
                    ClearPendingNestedOperation(state);
                    return true;
                }
            }

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario test step lost its deadline state.";
                ClearPendingNestedOperation(state);
                return true;
            }

            if (DateTime.UtcNow < deadlineUtc)
            {
                return false;
            }

            stepResult.status = "failed";
            stepResult.error_code = "tests_timeout";
            stepResult.error_message = $"Timed out waiting for {modeLabel} test completion.";
            ClearPendingNestedOperation(state);
            return true;
        }

        static bool ProcessGameViewConfigureStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpGameViewConfigureArgs
            {
                width = step.width,
                height = step.height,
                group = step.group,
                label = step.label,
                allowCreateCustomSize = step.allowCreateCustomSize,
            };

            return ProcessNestedOperationStep("unity.game_view.configure", JsonUtility.ToJson(args), stepResult);
        }

        static bool ProcessProjectActionStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (!XUUnityLightMcpScenarioProjectActionNormalizer.TryBuildExecutableProjectActionStep(
                    step,
                    out var executableStep,
                    out var errorCode,
                    out var errorMessage))
            {
                stepResult.status = "failed";
                stepResult.error_code = errorCode;
                stepResult.error_message = errorMessage;
                return true;
            }

            stepResult.hook_name = executableStep.hookName ?? "";
            return ProcessProjectDefinedHookStep(executableStep, stepResult);
        }

        static bool ProcessProjectDefinedHookStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            stepResult.hook_name = step.hookName ?? "";
            if (!TryCreateScenarioHook(step.hookName, out var hook, out var errorCode, out var errorMessage))
            {
                stepResult.status = "failed";
                stepResult.error_code = errorCode;
                stepResult.error_message = errorMessage;
                return true;
            }

            var stopwatch = Stopwatch.StartNew();
            var result = hook.Execute(step.hookPayloadJson ?? "");
            stopwatch.Stop();

            stepResult.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
            if (result == null || result.success)
            {
                stepResult.status = "passed";
                stepResult.outcome = result?.outcome ?? "hook_succeeded";
                stepResult.payload_json = result?.payload_json ?? "";
                return true;
            }

            stepResult.status = "failed";
            stepResult.error_code = string.IsNullOrWhiteSpace(result.error_code) ? "project_hook_failed" : result.error_code;
            stepResult.error_message = string.IsNullOrWhiteSpace(result.error_message)
                ? $"Scenario hook '{step.hookName}' reported failure."
                : result.error_message;
            stepResult.outcome = result.outcome ?? "";
            stepResult.payload_json = result.payload_json ?? "";
            return true;
        }

        static bool ProcessProjectDefinedHookPollUntilStep(
            XUUnityLightMcpScenarioRunState state,
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult)
        {
            stepResult.hook_name = step.hookName ?? "";
            stepResult.promote_payload_fields = step.promotePayloadFields;
            if (!TryCreateScenarioHook(step.hookName, out var hook, out var errorCode, out var errorMessage))
            {
                stepResult.status = "failed";
                stepResult.error_code = errorCode;
                stepResult.error_message = errorMessage;
                return true;
            }

            if (stepResult.status == "pending")
            {
                var now = DateTime.UtcNow;
                var timeoutSeconds = GetTimeoutSeconds(step, 180.0d);
                state.pollUntilStartedAtUtc = now.ToString("yyyy-MM-ddTHH:mm:ssZ");
                state.pollUntilDeadlineUtc = now.AddSeconds(timeoutSeconds).ToString("yyyy-MM-ddTHH:mm:ssZ");
                state.pollUntilNextPollUtc = now.ToString("yyyy-MM-ddTHH:mm:ssZ");
                state.pollUntilPollCount = 0;
                state.waitingUntilUtc = state.pollUntilNextPollUtc;

                var startResult = ExecuteScenarioHook(hook, step.startPayloadJson, out var durationSeconds);
                stepResult.duration_seconds = durationSeconds;
                stepResult.payload_json = startResult?.payload_json ?? "";
                if (startResult == null || !startResult.success)
                {
                    stepResult.status = "failed";
                    stepResult.error_code = string.IsNullOrWhiteSpace(startResult?.error_code)
                        ? "project_hook_poll_until_start_failed"
                        : startResult.error_code;
                    stepResult.error_message = string.IsNullOrWhiteSpace(startResult?.error_message)
                        ? $"Scenario hook '{step.hookName}' start action failed."
                        : startResult.error_message;
                    stepResult.outcome = startResult?.outcome ?? "hook_start_failed";
                    return true;
                }

                stepResult.status = "running";
                stepResult.outcome = string.IsNullOrWhiteSpace(startResult.outcome)
                    ? "hook_poll_until_started"
                    : startResult.outcome;
                return false;
            }

            if (stepResult.status != "running")
            {
                return true;
            }

            if (!TryParseUtc(state.pollUntilDeadlineUtc, out var deadlineUtc)
                || !TryParseUtc(state.pollUntilStartedAtUtc, out var startedUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_poll_until_state";
                stepResult.error_message = "Scenario hook poll-until step lost its deadline state.";
                ClearPollUntilState(state);
                return true;
            }

            if (DateTime.UtcNow >= deadlineUtc)
            {
                stepResult.status = "failed";
                stepResult.terminal_status = "timeout";
                stepResult.poll_count = state.pollUntilPollCount;
                stepResult.outcome = "hook_poll_until_timeout";
                stepResult.error_code = "project_hook_poll_until_timeout";
                stepResult.error_message = $"Timed out after {GetTimeoutSeconds(step, 180.0d):0.###} seconds waiting for hook '{step.hookName}' to satisfy passWhen.";
                stepResult.duration_seconds = Math.Round(Math.Max(0.0d, (DateTime.UtcNow - startedUtc).TotalSeconds), 6);
                CaptureTerminalPollUntilArtifacts(step, stepResult);
                ClearPollUntilState(state);
                return true;
            }

            if (TryParseUtc(state.pollUntilNextPollUtc, out var nextPollUtc) && DateTime.UtcNow < nextPollUtc)
            {
                state.waitingUntilUtc = state.pollUntilNextPollUtc;
                return false;
            }

            var pollResult = ExecuteScenarioHook(hook, step.pollPayloadJson, out _);
            state.pollUntilPollCount++;
            stepResult.poll_count = state.pollUntilPollCount;
            stepResult.duration_seconds = Math.Round(Math.Max(0.0d, (DateTime.UtcNow - startedUtc).TotalSeconds), 6);
            stepResult.payload_json = pollResult?.payload_json ?? stepResult.payload_json ?? "";

            if (pollResult == null || !pollResult.success)
            {
                stepResult.status = "failed";
                stepResult.error_code = string.IsNullOrWhiteSpace(pollResult?.error_code)
                    ? "project_hook_poll_until_poll_failed"
                    : pollResult.error_code;
                stepResult.error_message = string.IsNullOrWhiteSpace(pollResult?.error_message)
                    ? $"Scenario hook '{step.hookName}' poll action failed."
                    : pollResult.error_message;
                stepResult.outcome = pollResult?.outcome ?? "hook_poll_failed";
                CaptureTerminalPollUntilArtifacts(step, stepResult);
                ClearPollUntilState(state);
                return true;
            }

            var payloadJson = pollResult.payload_json ?? "";
            var payloadStatus = ExtractJsonScalar(payloadJson, "status");
            stepResult.terminal_status = payloadStatus;
            stepResult.failure_class = ExtractJsonScalar(payloadJson, "failure_class");

            if (PredicateMatches(step.passWhen, payloadJson))
            {
                stepResult.status = "passed";
                stepResult.outcome = string.IsNullOrWhiteSpace(pollResult.outcome)
                    ? "hook_poll_until_passed"
                    : pollResult.outcome;
                CaptureTerminalPollUntilArtifacts(step, stepResult);
                ClearPollUntilState(state);
                return true;
            }

            if (PredicateMatches(step.failWhen, payloadJson))
            {
                stepResult.status = "failed";
                stepResult.outcome = string.IsNullOrWhiteSpace(pollResult.outcome)
                    ? "hook_poll_until_failed"
                    : pollResult.outcome;
                stepResult.error_code = FirstNonEmpty(
                    ExtractJsonScalar(payloadJson, "error_code"),
                    ExtractJsonScalar(payloadJson, "code"),
                    "project_hook_poll_until_failed");
                stepResult.error_message = FirstNonEmpty(
                    ExtractJsonScalar(payloadJson, "error_message"),
                    ExtractJsonScalar(payloadJson, "message"),
                    $"Scenario hook '{step.hookName}' reached terminal failed status.");
                CaptureTerminalPollUntilArtifacts(step, stepResult);
                ClearPollUntilState(state);
                return true;
            }

            if (PredicateMatches(step.continueWhen, payloadJson))
            {
                stepResult.status = "running";
                stepResult.outcome = string.IsNullOrWhiteSpace(pollResult.outcome)
                    ? "hook_poll_until_running"
                    : pollResult.outcome;
                var intervalSeconds = Math.Max(0.0d, step.intervalSeconds);
                state.pollUntilNextPollUtc = DateTime.UtcNow.AddSeconds(intervalSeconds).ToString("yyyy-MM-ddTHH:mm:ssZ");
                state.waitingUntilUtc = state.pollUntilNextPollUtc;
                return false;
            }

            stepResult.status = "failed";
            stepResult.outcome = "hook_poll_until_unmatched_terminal_status";
            stepResult.error_code = "project_hook_poll_until_unmatched_status";
            stepResult.error_message = string.IsNullOrWhiteSpace(payloadStatus)
                ? $"Scenario hook '{step.hookName}' poll payload did not satisfy passWhen, failWhen, or continueWhen."
                : $"Scenario hook '{step.hookName}' poll payload status '{payloadStatus}' did not satisfy passWhen, failWhen, or continueWhen.";
            CaptureTerminalPollUntilArtifacts(step, stepResult);
            ClearPollUntilState(state);
            return true;
        }

        static XUUnityLightMcpScenarioHookResult ExecuteScenarioHook(
            IXUUnityLightMcpScenarioHook hook,
            string payloadJson,
            out double durationSeconds)
        {
            var stopwatch = Stopwatch.StartNew();
            var result = hook.Execute(string.IsNullOrWhiteSpace(payloadJson) ? "{}" : payloadJson);
            stopwatch.Stop();
            durationSeconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
            return result;
        }

        static bool PredicateMatches(string expression, string payloadJson)
        {
            if (string.IsNullOrWhiteSpace(expression))
            {
                return false;
            }

            var match = Regex.Match(
                expression.Trim(),
                "^payload\\.([A-Za-z_][A-Za-z0-9_]*)\\s*==\\s*(['\"])(.*?)\\2$");
            if (!match.Success)
            {
                return false;
            }

            var actual = ExtractJsonScalar(payloadJson, match.Groups[1].Value);
            return string.Equals(actual, match.Groups[3].Value, StringComparison.Ordinal);
        }

        static string ExtractJsonScalar(string payloadJson, string fieldName)
        {
            if (string.IsNullOrWhiteSpace(payloadJson) || string.IsNullOrWhiteSpace(fieldName))
            {
                return "";
            }

            var escapedField = Regex.Escape(fieldName);
            var match = Regex.Match(
                payloadJson,
                "\""
                + escapedField
                + "\"\\s*:\\s*(?:\"((?:\\\\.|[^\"\\\\])*)\"|([-+]?[0-9]+(?:\\.[0-9]+)?)|(true|false|null))",
                RegexOptions.IgnoreCase);
            if (!match.Success)
            {
                return "";
            }

            if (match.Groups[1].Success)
            {
                return Regex.Unescape(match.Groups[1].Value);
            }

            if (match.Groups[2].Success)
            {
                return match.Groups[2].Value;
            }

            return match.Groups[3].Value;
        }

        static void CaptureTerminalPollUntilArtifacts(
            XUUnityLightMcpScenarioStepDefinition step,
            XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (step.terminalScreenshot)
            {
                var args = new XUUnityLightMcpGameViewScreenshotArgs
                {
                    fileName = string.IsNullOrWhiteSpace(step.fileName) ? "" : step.fileName,
                    includeImage = false,
                    maxResolution = step.maxResolution > 0 ? step.maxResolution : 640,
                };
                var screenshotResponse = ExecuteNestedOperation("unity.game_view.screenshot", JsonUtility.ToJson(args));
                if (screenshotResponse != null && screenshotResponse.status == "ok")
                {
                    stepResult.terminal_screenshot_payload_json = screenshotResponse.payload_json ?? "";
                }
            }

            if (step.terminalConsoleTail)
            {
                var args = new XUUnityLightMcpConsoleTailArgs
                {
                    limit = step.limit > 0 ? step.limit : 50,
                    includeTypes = step.includeTypes,
                };
                var consoleResponse = ExecuteNestedOperation("unity.console.tail", JsonUtility.ToJson(args));
                if (consoleResponse != null && consoleResponse.status == "ok")
                {
                    stepResult.terminal_console_tail_payload_json = consoleResponse.payload_json ?? "";
                }
            }
        }

        static void ClearPollUntilState(XUUnityLightMcpScenarioRunState state)
        {
            state.pollUntilStartedAtUtc = "";
            state.pollUntilDeadlineUtc = "";
            state.pollUntilNextPollUtc = "";
            state.pollUntilPollCount = 0;
            state.waitingUntilUtc = "";
        }

        static string FirstNonEmpty(params string[] values)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    return value;
                }
            }

            return "";
        }

        static bool ProcessNestedOperationStep(string operationName, string argsJson, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var stopwatch = Stopwatch.StartNew();
            var response = ExecuteNestedOperation(operationName, argsJson);
            stopwatch.Stop();

            stepResult.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);

            if (response == null)
            {
                stepResult.status = "failed";
                stepResult.error_code = "null_nested_response";
                stepResult.error_message = $"Nested operation '{operationName}' returned no response.";
                return true;
            }

            if (response.status == "ok")
            {
                stepResult.status = "passed";
                stepResult.outcome = "operation_succeeded";
                stepResult.payload_json = response.payload_json ?? "";
                return true;
            }

            stepResult.status = "failed";
            stepResult.error_code = response.error?.code ?? "nested_operation_failed";
            stepResult.error_message = response.error?.message ?? $"Nested operation '{operationName}' failed.";
            return true;
        }

        static XUUnityLightMcpResponse ExecuteNestedOperation(string operationName, string argsJson)
        {
            return ExecuteNestedOperation(operationName, argsJson, null);
        }

        static XUUnityLightMcpResponse ExecuteNestedOperation(string operationName, string argsJson, XUUnityLightMcpRequest requestOverride)
        {
            if (!XUUnityLightMcpOperationRegistry.TryGet(operationName, out var operation))
            {
                throw new InvalidOperationException($"Scenario runner could not resolve nested operation '{operationName}'.");
            }

            var nestedRequest = requestOverride ?? BuildNestedRequest(operationName, argsJson, 30000);

            return operation.Execute(nestedRequest);
        }

        static XUUnityLightMcpRequest BuildNestedRequest(string operationName, string argsJson, int timeoutMs)
        {
            return new XUUnityLightMcpRequest
            {
                request_id = $"scenario_{Guid.NewGuid():N}",
                operation = operationName,
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                created_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                timeout_ms = timeoutMs,
                args_json = string.IsNullOrWhiteSpace(argsJson) ? "{}" : argsJson,
            };
        }

        static bool TryTakePendingNestedResponse(string requestId, out XUUnityLightMcpResponse response)
        {
            response = null;
            if (string.IsNullOrWhiteSpace(requestId))
            {
                return false;
            }

            var path = Path.Combine(XUUnityLightMcpFileIpcPaths.OutboxDirectory, $"{requestId}.json");
            if (!File.Exists(path))
            {
                return false;
            }

            try
            {
                response = JsonUtility.FromJson<XUUnityLightMcpResponse>(File.ReadAllText(path));
            }
            finally
            {
                File.Delete(path);
            }

            return response != null;
        }

        static void ApplyNestedResponse(XUUnityLightMcpScenarioStepResult stepResult, XUUnityLightMcpResponse response, string startedAtUtc)
        {
            stepResult.duration_seconds = CalculateDurationSeconds(startedAtUtc, response?.completed_at_utc ?? "");

            if (response == null)
            {
                stepResult.status = "failed";
                stepResult.error_code = "null_nested_response";
                stepResult.error_message = "Nested operation returned no response.";
                return;
            }

            if (response.status == "ok")
            {
                stepResult.status = "passed";
                stepResult.outcome = "operation_succeeded";
                stepResult.payload_json = response.payload_json ?? "";
                return;
            }

            stepResult.status = "failed";
            stepResult.error_code = response.error?.code ?? "nested_operation_failed";
            stepResult.error_message = response.error?.message ?? "Nested operation failed.";
        }

        static void ApplyTestsResponse(XUUnityLightMcpScenarioStepResult stepResult, XUUnityLightMcpResponse response, string startedAtUtc, string modeLabel)
        {
            ApplyNestedResponse(stepResult, response, startedAtUtc);
            if (response == null || response.status != "ok")
            {
                return;
            }

            var payload = string.IsNullOrWhiteSpace(response.payload_json)
                ? null
                : JsonUtility.FromJson<XUUnityLightMcpTestsPayload>(response.payload_json);

            if (payload != null)
            {
                payload.playmode_state_after_settle = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState();
                stepResult.payload_json = JsonUtility.ToJson(payload);
            }
            else
            {
                stepResult.payload_json = response.payload_json ?? "";
            }

            if (payload != null && string.Equals(payload.status, "passed", StringComparison.OrdinalIgnoreCase))
            {
                stepResult.status = "passed";
                stepResult.outcome = "tests_passed";
                return;
            }

            stepResult.status = "failed";
            stepResult.error_code = payload != null && string.Equals(payload.status, "no_tests", StringComparison.OrdinalIgnoreCase)
                ? "no_tests"
                : "tests_failed";
            stepResult.error_message = FormatTestsFailureMessage(payload, modeLabel);
        }

        static void ClearPendingNestedOperation(XUUnityLightMcpScenarioRunState state)
        {
            state.pendingNestedRequestId = "";
            state.pendingNestedOperation = "";
            state.pendingNestedStartedAtUtc = "";
            state.pendingNestedResponseStatus = "";
            state.pendingNestedResponseCompletedAtUtc = "";
            state.pendingNestedResponsePayloadJson = "";
            state.pendingNestedResponseErrorCode = "";
            state.pendingNestedResponseErrorMessage = "";
            state.pendingNestedStableTickCount = 0;
        }

        static void CapturePendingNestedResponse(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpResponse response)
        {
            state.pendingNestedResponseStatus = response?.status ?? "";
            state.pendingNestedResponseCompletedAtUtc = response?.completed_at_utc ?? "";
            state.pendingNestedResponsePayloadJson = response?.payload_json ?? "";
            state.pendingNestedResponseErrorCode = response?.error?.code ?? "";
            state.pendingNestedResponseErrorMessage = response?.error?.message ?? "";
        }

        static bool TryGetCapturedPendingNestedResponse(XUUnityLightMcpScenarioRunState state, out XUUnityLightMcpResponse response)
        {
            response = null;
            if (state == null || string.IsNullOrWhiteSpace(state.pendingNestedResponseStatus))
            {
                return false;
            }

            response = new XUUnityLightMcpResponse
            {
                request_id = state.pendingNestedRequestId ?? "",
                status = state.pendingNestedResponseStatus ?? "",
                completed_at_utc = state.pendingNestedResponseCompletedAtUtc ?? "",
                payload_json = state.pendingNestedResponsePayloadJson ?? "",
                error = new XUUnityLightMcpError
                {
                    code = state.pendingNestedResponseErrorCode ?? "",
                    message = state.pendingNestedResponseErrorMessage ?? "",
                },
            };
            return true;
        }

        static bool ShouldWaitForPlayModeTestsSettle(string operationName, XUUnityLightMcpResponse response)
        {
            return string.Equals(operationName, "unity.tests.run_playmode", StringComparison.Ordinal)
                && response != null
                && string.Equals(response.status, "ok", StringComparison.OrdinalIgnoreCase);
        }

        static bool IsEditorIdleForPlayModeTestsSettle()
        {
            return !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && !EditorApplication.isPlaying
                && !EditorApplication.isPlayingOrWillChangePlaymode
                && string.Equals(XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(), "edit", StringComparison.Ordinal);
        }

        static int GetTimeoutMs(XUUnityLightMcpScenarioStepDefinition step, double defaultSeconds)
        {
            return (int)Math.Round(GetTimeoutSeconds(step, defaultSeconds) * 1000.0d);
        }

        static double GetTimeoutSeconds(XUUnityLightMcpScenarioStepDefinition step, double defaultSeconds)
        {
            return step.timeoutSeconds > 0.0d ? step.timeoutSeconds : defaultSeconds;
        }

        static bool TryCreateScenarioHook(string hookName, out IXUUnityLightMcpScenarioHook hook, out string errorCode, out string errorMessage)
        {
            hook = null;
            errorCode = "";
            errorMessage = "";

            if (string.IsNullOrWhiteSpace(hookName))
            {
                errorCode = "missing_hook_name";
                errorMessage = "project_defined_hook step requires hookName.";
                return false;
            }

            var matches = new List<Type>();
            foreach (var type in TypeCache.GetTypesDerivedFrom<IXUUnityLightMcpScenarioHook>())
            {
                if (type == null || type.IsAbstract || type.IsInterface)
                {
                    continue;
                }

                if (Activator.CreateInstance(type) is not IXUUnityLightMcpScenarioHook candidate)
                {
                    continue;
                }

                if (string.Equals(candidate.HookName, hookName, StringComparison.OrdinalIgnoreCase))
                {
                    matches.Add(type);
                    hook ??= candidate;
                }
            }

            if (matches.Count == 1 && hook != null)
            {
                return true;
            }

            if (matches.Count > 1)
            {
                hook = null;
                errorCode = "duplicate_hook_name";
                errorMessage = $"Multiple scenario hooks registered as '{hookName}'.";
                return false;
            }

            errorCode = "hook_not_found";
            errorMessage = $"No scenario hook registered as '{hookName}'.";
            return false;
        }

        static string FormatCompileFailureMessage(XUUnityLightMcpCompilePlayerScriptsPayload payload)
        {
            if (payload?.result == null)
            {
                return "compile_player_scripts payload did not describe a passed compile.";
            }

            if (payload.result.errors != null && payload.result.errors.Count > 0)
            {
                var first = payload.result.errors[0];
                return string.IsNullOrWhiteSpace(first.message)
                    ? $"Compile failed for target '{payload.result.target}'."
                    : first.message;
            }

            return $"Compile status was '{payload.result.status}' for target '{payload.result.target}'.";
        }

        static string FormatTestsFailureMessage(XUUnityLightMcpTestsPayload payload, string modeLabel)
        {
            if (payload == null)
            {
                return $"{modeLabel} test payload did not report a passed result.";
            }

            if (payload.failures != null && payload.failures.Count > 0)
            {
                var first = payload.failures[0];
                return string.IsNullOrWhiteSpace(first.message)
                    ? $"{modeLabel} tests failed in '{first.name}'."
                    : first.message;
            }

            return payload.status == "no_tests"
                ? $"{modeLabel} test run completed with no discovered tests."
                : $"{modeLabel} tests finished with status '{payload.status}'.";
        }

        static void CompleteRun(XUUnityLightMcpScenarioRunState state, string finalStatus)
        {
            CleanupScenarioOwnedTransientState(state);
            state.status = finalStatus;
            state.completedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            state.updatedAtUtc = state.completedAtUtc;
            PersistResult(state);
            SaveState(state);
            SafeDeleteActiveState();
        }

        static void CleanupScenarioOwnedTransientState(XUUnityLightMcpScenarioRunState state)
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

        static bool IsScenarioOwnedRequestId(string requestId, XUUnityLightMcpScenarioRunState state)
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

        static void PersistResult(XUUnityLightMcpScenarioRunState state, string errorCode = "", string errorMessage = "")
        {
            var payload = BuildPayload(state);
            if (!string.IsNullOrWhiteSpace(errorCode))
            {
                payload.status = "failed";
                if (payload.steps.Count == 0)
                {
                    payload.steps.Add(new XUUnityLightMcpScenarioStepResult
                    {
                        stepId = "runner",
                        kind = "runner",
                        status = "failed",
                        error_code = errorCode,
                        error_message = errorMessage,
                    });
                }
            }

            File.WriteAllText(state.resultPath, JsonUtility.ToJson(payload, true));
        }

        static XUUnityLightMcpScenarioRunPayload BuildPayload(XUUnityLightMcpScenarioRunState state)
        {
            var isTerminal = string.Equals(state.status, "passed", StringComparison.Ordinal)
                || string.Equals(state.status, "failed", StringComparison.Ordinal);

            var payload = new XUUnityLightMcpScenarioRunPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                run_id = state.runId,
                scenario_name = NormalizeScenarioName(state.scenario?.name),
                status = state.status,
                terminal = isTerminal,
                succeeded = string.Equals(state.status, "passed", StringComparison.Ordinal),
                terminal_status = isTerminal ? state.status : "",
                started_at_utc = state.startedAtUtc,
                updated_at_utc = state.updatedAtUtc,
                completed_at_utc = state.completedAtUtc,
                result_path = state.resultPath,
                cleanup_start_index = state.cleanupStartIndex,
                total_steps = state.steps.Count,
                current_step_index = state.currentStepIndex,
                waiting_until_utc = state.waitingUntilUtc,
                steps = new List<XUUnityLightMcpScenarioStepResult>(state.steps),
                passed_steps = CountSteps(state.steps, "passed"),
                failed_steps = CountSteps(state.steps, "failed"),
                skipped_steps = CountSteps(state.steps, "skipped"),
                duration_seconds = CalculateDurationSeconds(state.startedAtUtc, string.IsNullOrWhiteSpace(state.completedAtUtc) ? state.updatedAtUtc : state.completedAtUtc),
            };

            return payload;
        }

        static double CalculateDurationSeconds(string startedAtUtc, string completedAtUtc)
        {
            if (!TryParseUtc(startedAtUtc, out var started))
            {
                return 0.0d;
            }

            if (!TryParseUtc(completedAtUtc, out var completed))
            {
                completed = DateTime.UtcNow;
            }

            return Math.Round(Math.Max(0.0d, (completed - started).TotalSeconds), 6);
        }

        static int CountSteps(List<XUUnityLightMcpScenarioStepResult> steps, string status)
        {
            var count = 0;
            foreach (var step in steps)
            {
                if (string.Equals(step.status, status, StringComparison.Ordinal))
                {
                    count++;
                }
            }
            return count;
        }

        static bool TryLoadState(out XUUnityLightMcpScenarioRunState state)
        {
            state = null;
            var path = XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath;
            if (!File.Exists(path))
            {
                return false;
            }

            var json = File.ReadAllText(path);
            state = JsonUtility.FromJson<XUUnityLightMcpScenarioRunState>(json);
            return state != null;
        }

        static void SaveState(XUUnityLightMcpScenarioRunState state)
        {
            File.WriteAllText(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath, JsonUtility.ToJson(state, true));
        }

        static void SafeDeleteActiveState()
        {
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath))
                {
                    File.Delete(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath);
                }
            }
            catch
            {
            }
        }

        static bool ProcessProjectRefreshStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessProjectRefreshStep(null, step, stepResult);
        }

        static bool ProcessProjectRefreshStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (state == null)
            {
                return ProcessNestedOperationStep("unity.project.refresh", BuildProjectRefreshArgsJson(step), stepResult);
            }

            if (stepResult.status == "pending")
            {
                var request = BuildNestedRequest("unity.project.refresh", BuildProjectRefreshArgsJson(step), GetTimeoutMs(step, 45.0d));
                var response = ExecuteNestedOperation(request.operation, request.args_json, request);
                if (response == null)
                {
                    stepResult.status = "failed";
                    stepResult.error_code = "null_nested_response";
                    stepResult.error_message = "project_refresh returned no response.";
                    return true;
                }

                if (response.status != "ok")
                {
                    ApplyNestedResponse(stepResult, response, request.created_at_utc);
                    return true;
                }

                state.pendingNestedRequestId = request.request_id;
                state.pendingNestedOperation = request.operation;
                state.pendingNestedStartedAtUtc = request.created_at_utc;
                state.pendingNestedStableTickCount = 0;
                state.waitingUntilUtc = DateTime.UtcNow.AddSeconds(GetTimeoutSeconds(step, 45.0d)).ToString("yyyy-MM-ddTHH:mm:ssZ");
                stepResult.status = "running";
                stepResult.outcome = "refresh_waiting_for_settle";
                stepResult.payload_json = response.payload_json ?? "";
                return false;
            }

            if (stepResult.status != "running")
            {
                return true;
            }

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario refresh step lost its deadline state.";
                ClearPendingNestedOperation(state);
                return true;
            }

            if (IsEditorIdleForRefreshSettle())
            {
                state.pendingNestedStableTickCount++;
                if (state.pendingNestedStableTickCount >= 2)
                {
                    FinalizeProjectRefreshStep(stepResult);
                    ClearPendingNestedOperation(state);
                    return true;
                }
            }
            else
            {
                state.pendingNestedStableTickCount = 0;
            }

            if (DateTime.UtcNow < deadlineUtc)
            {
                return false;
            }

            stepResult.status = "failed";
            stepResult.error_code = "project_refresh_timeout";
            stepResult.error_message = "Timed out waiting for project refresh to settle.";
            ClearPendingNestedOperation(state);
            return true;
        }

        static string BuildProjectRefreshArgsJson(XUUnityLightMcpScenarioStepDefinition step)
        {
            var args = new XUUnityLightMcpProjectRefreshArgs
            {
                forceAssetRefresh = step.forceAssetRefresh,
                resolvePackages = step.resolvePackages,
                rerunHealthProbe = step.rerunHealthProbe,
            };

            return JsonUtility.ToJson(args);
        }

        static bool IsEditorIdleForRefreshSettle()
        {
            return !XUUnityLightMcpBridgeRuntimeState.RefreshSettlePending
                && string.Equals(XUUnityLightMcpBridgeRuntimeState.RefreshSettlePhase, "settled", StringComparison.Ordinal)
                && !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && (EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode);
        }

        static void FinalizeProjectRefreshStep(XUUnityLightMcpScenarioStepResult stepResult)
        {
            var payload = string.IsNullOrWhiteSpace(stepResult.payload_json)
                ? new XUUnityLightMcpProjectRefreshPayload()
                : JsonUtility.FromJson<XUUnityLightMcpProjectRefreshPayload>(stepResult.payload_json) ?? new XUUnityLightMcpProjectRefreshPayload();

            payload.requested_outcome = string.IsNullOrWhiteSpace(payload.requested_outcome)
                ? payload.outcome ?? ""
                : payload.requested_outcome;
            payload.outcome = payload.package_resolve_requested
                ? "refresh_and_resolve_completed"
                : "refresh_completed";
            payload.settled_at_utc = string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeState.RefreshSettleCompletedUtc)
                ? DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
                : XUUnityLightMcpBridgeRuntimeState.RefreshSettleCompletedUtc;
            payload.completion_basis = "unity_refresh_settle_watcher";
            payload.editor_is_compiling_after_settle = EditorApplication.isCompiling;
            payload.editor_is_updating_after_settle = EditorApplication.isUpdating;
            payload.playmode_state_after_settle = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState();
            payload.settle_request_id = string.IsNullOrWhiteSpace(payload.settle_request_id)
                ? XUUnityLightMcpBridgeRuntimeState.RefreshSettleRequestId
                : payload.settle_request_id;
            payload.settle_phase = XUUnityLightMcpBridgeRuntimeState.RefreshSettlePhase;

            stepResult.status = "passed";
            stepResult.outcome = payload.outcome;
            stepResult.payload_json = JsonUtility.ToJson(payload);
        }

        static bool IsEditorIdleForCompileSettle(XUUnityLightMcpScenarioStepResult stepResult)
        {
            return TryGetCompileSettleCompletionUtc(stepResult, out _)
                && !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && (EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode);
        }

        static void FinalizeCompilePlayerScriptsStep(XUUnityLightMcpScenarioStepResult stepResult)
        {
            var payload = string.IsNullOrWhiteSpace(stepResult.payload_json)
                ? new XUUnityLightMcpCompilePlayerScriptsPayload()
                : JsonUtility.FromJson<XUUnityLightMcpCompilePlayerScriptsPayload>(stepResult.payload_json) ?? new XUUnityLightMcpCompilePlayerScriptsPayload();

            var completionBasis = "unity_compile_settle_watcher";
            if (!TryGetCompileSettleCompletionUtc(stepResult, out var settledAtUtc))
            {
                settledAtUtc = string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeState.CompileSettleCompletedUtc)
                    ? DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
                    : XUUnityLightMcpBridgeRuntimeState.CompileSettleCompletedUtc;
            }
            else if (!string.Equals(
                XUUnityLightMcpBridgeRuntimeState.CompileSettleRequestId,
                payload.settle_request_id ?? "",
                StringComparison.Ordinal))
            {
                completionBasis = "unity_compile_settle_request_history";
            }

            payload.settled_at_utc = settledAtUtc;
            payload.completion_basis = completionBasis;
            payload.editor_is_compiling_after_settle = EditorApplication.isCompiling;
            payload.editor_is_updating_after_settle = EditorApplication.isUpdating;
            payload.playmode_state_after_settle = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState();
            payload.settle_request_id = string.IsNullOrWhiteSpace(payload.settle_request_id)
                ? XUUnityLightMcpBridgeRuntimeState.CompileSettleRequestId
                : payload.settle_request_id;
            payload.settle_phase = "settled";
            stepResult.payload_json = JsonUtility.ToJson(payload);

            if (payload.result != null && string.Equals(payload.result.status, "passed", StringComparison.OrdinalIgnoreCase))
            {
                stepResult.status = "passed";
                stepResult.outcome = "compile_passed";
                return;
            }

            stepResult.status = "failed";
            stepResult.error_code = "compile_failed";
            stepResult.error_message = FormatCompileFailureMessage(payload);
        }

        static bool TryGetCompileSettleCompletionUtc(XUUnityLightMcpScenarioStepResult stepResult, out string completedAtUtc)
        {
            var expectedRequestId = "";
            if (stepResult != null && !string.IsNullOrWhiteSpace(stepResult.payload_json))
            {
                var payload = JsonUtility.FromJson<XUUnityLightMcpCompilePlayerScriptsPayload>(stepResult.payload_json);
                expectedRequestId = payload?.settle_request_id ?? "";
            }

            if (!XUUnityLightMcpBridgeRuntimeState.CompileSettlePending
                && string.Equals(XUUnityLightMcpBridgeRuntimeState.CompileSettlePhase, "settled", StringComparison.Ordinal)
                && (string.IsNullOrWhiteSpace(expectedRequestId)
                    || string.Equals(XUUnityLightMcpBridgeRuntimeState.CompileSettleRequestId, expectedRequestId, StringComparison.Ordinal)))
            {
                completedAtUtc = string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeState.CompileSettleCompletedUtc)
                    ? DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
                    : XUUnityLightMcpBridgeRuntimeState.CompileSettleCompletedUtc;
                return true;
            }

            if (!string.IsNullOrWhiteSpace(expectedRequestId)
                && XUUnityLightMcpBridgeRuntimeState.TryGetCompletedCompileSettleUtc(expectedRequestId, out completedAtUtc))
            {
                return true;
            }

            completedAtUtc = "";
            return false;
        }

        static string BuildResultPath(string runId, string scenarioName)
        {
            var timestamp = DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ");
            var safeName = SanitizeFileName(scenarioName);
            return Path.Combine(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory, $"{timestamp}_{runId}_{safeName}.json");
        }

        static FileInfo FindResultPathByRunId(string runId)
        {
            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (file.Name.Contains(runId, StringComparison.OrdinalIgnoreCase))
                {
                    return file;
                }
            }

            return null;
        }

        static FileInfo FindLatestResultPathByScenarioName(string scenarioName)
        {
            FileInfo latest = null;
            XUUnityLightMcpScenarioRunPayload latestPayload = null;

            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (!TryReadPayload(file, out var payload, out _, out _))
                {
                    continue;
                }

                if (!string.Equals(payload.scenario_name, scenarioName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (latest == null || file.LastWriteTimeUtc > latest.LastWriteTimeUtc)
                {
                    latest = file;
                    latestPayload = payload;
                }
            }

            return latestPayload != null ? latest : null;
        }

        static FileInfo FindLatestResultPath()
        {
            FileInfo latest = null;
            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (latest == null || file.LastWriteTimeUtc > latest.LastWriteTimeUtc)
                {
                    latest = file;
                }
            }

            return latest;
        }

        static bool TryReadPayload(FileInfo file, out XUUnityLightMcpScenarioRunPayload payload, out string errorCode, out string errorMessage)
        {
            payload = null;
            errorCode = "";
            errorMessage = "";

            try
            {
                var json = File.ReadAllText(file.FullName);
                payload = JsonUtility.FromJson<XUUnityLightMcpScenarioRunPayload>(json);
                if (payload == null)
                {
                    errorCode = "invalid_scenario_result";
                    errorMessage = $"Scenario result file is empty or invalid: {file.FullName}";
                    return false;
                }

                return true;
            }
            catch (Exception ex)
            {
                errorCode = "scenario_result_read_failed";
                errorMessage = ex.Message;
                return false;
            }
        }

        static void ValidateStep(XUUnityLightMcpScenarioValidatePayload payload, XUUnityLightMcpScenarioStepDefinition step, string stepId, int index)
        {
            var kind = NormalizeStepKind(step);
            if (string.IsNullOrWhiteSpace(kind))
            {
                AddIssue(payload, "error", "missing_kind", "Scenario step kind or operation is required.", stepId, index);
                return;
            }

            switch (kind)
            {
                case "status":
                case "health_probe":
                case "scene_snapshot":
                case "project_refresh":
                    break;
                case "assert_scene":
                    if (string.IsNullOrWhiteSpace(step.expectedName)
                        && string.IsNullOrWhiteSpace(step.expectedPath)
                        && (step.requiredRootNames == null || step.requiredRootNames.Length == 0)
                        && step.allowDirty)
                    {
                        AddIssue(payload, "error", "missing_scene_expectation",
                            "assert_scene requires expectedName, expectedPath, requiredRootNames, or allowDirty=false.",
                            stepId, index);
                    }
                    break;
                case "console_tail":
                    if (step.limit < 0)
                    {
                        AddIssue(payload, "error", "invalid_limit", "console_tail step requires limit >= 0; omit it or use 0 for the default.", stepId, index);
                    }
                    break;
                case "console_grep":
                    if (string.IsNullOrWhiteSpace(step.pattern))
                    {
                        AddIssue(payload, "error", "missing_pattern", "console_grep step requires pattern.", stepId, index);
                    }
                    if (step.limit < 0)
                    {
                        AddIssue(payload, "error", "invalid_limit", "console_grep step requires limit >= 0; omit it or use 0 for the default.", stepId, index);
                    }
                    break;
                case "playmode_set":
                    if (!IsPlayModeAction(step.action))
                    {
                        AddIssue(payload, "error", "invalid_action",
                            "playmode_set step requires action: enter, exit, pause, or resume.", stepId, index);
                    }
                    break;
                case "wait":
                    if (step.durationSeconds < 0.0d)
                    {
                        AddIssue(payload, "error", "invalid_duration", "wait step requires durationSeconds >= 0.", stepId, index);
                    }
                    break;
                case "wait_for_playmode_state":
                    if (!IsPlayModeState(step.expectedPlaymodeState))
                    {
                        AddIssue(payload, "error", "invalid_expected_playmode_state",
                            "wait_for_playmode_state requires expectedPlaymodeState: edit, playing, paused, or transitioning.",
                            stepId, index);
                    }
                    if (step.timeoutSeconds <= 0.0d)
                    {
                        AddIssue(payload, "error", "invalid_timeout", "wait_for_playmode_state requires timeoutSeconds > 0.", stepId, index);
                    }
                    break;
                case "assert_playmode_state":
                    if (!IsPlayModeState(step.expectedPlaymodeState))
                    {
                        AddIssue(payload, "error", "invalid_expected_playmode_state",
                            "assert_playmode_state requires expectedPlaymodeState: edit, playing, paused, or transitioning.",
                            stepId, index);
                    }
                    break;
                case "game_view_screenshot":
                    if (step.maxResolution <= 0)
                    {
                        AddIssue(payload, "error", "invalid_max_resolution",
                            "game_view_screenshot requires maxResolution > 0.", stepId, index);
                    }
                    break;
                case "compile_player_scripts":
                    if (string.IsNullOrWhiteSpace(step.target))
                    {
                        AddIssue(payload, "error", "missing_target", "compile_player_scripts requires target.", stepId, index);
                    }
                    break;
                case "tests_run_editmode":
                case "tests_run_playmode":
                    break;
                case "game_view_configure":
                    if (step.width <= 0 || step.height <= 0)
                    {
                        AddIssue(payload, "error", "invalid_resolution",
                            "game_view_configure requires width > 0 and height > 0.", stepId, index);
                    }
                    break;
                case "project_action":
                    if (!XUUnityLightMcpScenarioProjectActionNormalizer.TryBuildExecutableProjectActionStep(
                            step,
                            out _,
                            out var actionErrorCode,
                            out var actionErrorMessage))
                    {
                        AddIssue(payload, "error", actionErrorCode, actionErrorMessage, stepId, index);
                    }
                    break;
                case "project_defined_hook":
                    if (string.IsNullOrWhiteSpace(step.hookName))
                    {
                        AddIssue(payload, "error", "missing_hook_name", "project_defined_hook requires hookName.", stepId, index);
                        break;
                    }

                    if (!TryCreateScenarioHook(step.hookName, out _, out var hookErrorCode, out var hookErrorMessage))
                    {
                        AddIssue(payload, "error", hookErrorCode, hookErrorMessage, stepId, index);
                    }
                    break;
                case "project_defined_hook_poll_until":
                    ValidateProjectDefinedHookPollUntilStep(payload, step, stepId, index);
                    break;
                default:
                    AddIssue(payload, "error", "unsupported_kind", $"Unsupported scenario step kind '{kind}'.", stepId, index);
                    break;
            }
        }

        static void ValidateProjectDefinedHookPollUntilStep(
            XUUnityLightMcpScenarioValidatePayload payload,
            XUUnityLightMcpScenarioStepDefinition step,
            string stepId,
            int index)
        {
            if (string.IsNullOrWhiteSpace(step.hookName))
            {
                AddIssue(payload, "error", "missing_hook_name", "project_defined_hook_poll_until requires hookName.", stepId, index);
                return;
            }

            if (!TryCreateScenarioHook(step.hookName, out _, out var hookErrorCode, out var hookErrorMessage))
            {
                AddIssue(payload, "error", hookErrorCode, hookErrorMessage, stepId, index);
            }

            if (string.IsNullOrWhiteSpace(step.startPayloadJson))
            {
                AddIssue(payload, "error", "missing_start_payload", "project_defined_hook_poll_until requires startPayload or startPayloadJson.", stepId, index);
            }

            if (string.IsNullOrWhiteSpace(step.pollPayloadJson))
            {
                AddIssue(payload, "error", "missing_poll_payload", "project_defined_hook_poll_until requires pollPayload or pollPayloadJson.", stepId, index);
            }

            if (!IsSupportedPayloadEqualityPredicate(step.passWhen))
            {
                AddIssue(payload, "error", "invalid_pass_when", "project_defined_hook_poll_until passWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (!IsSupportedPayloadEqualityPredicate(step.failWhen))
            {
                AddIssue(payload, "error", "invalid_fail_when", "project_defined_hook_poll_until failWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (!string.IsNullOrWhiteSpace(step.continueWhen) && !IsSupportedPayloadEqualityPredicate(step.continueWhen))
            {
                AddIssue(payload, "error", "invalid_continue_when", "project_defined_hook_poll_until continueWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (step.intervalSeconds < 0.0d)
            {
                AddIssue(payload, "error", "invalid_interval", "project_defined_hook_poll_until requires intervalSeconds >= 0.", stepId, index);
            }

            if (step.timeoutSeconds <= 0.0d)
            {
                AddIssue(payload, "error", "invalid_timeout", "project_defined_hook_poll_until requires timeoutSeconds > 0.", stepId, index);
            }
        }

        static bool IsSupportedPayloadEqualityPredicate(string expression)
        {
            if (string.IsNullOrWhiteSpace(expression))
            {
                return false;
            }

            return Regex.IsMatch(
                expression.Trim(),
                "^payload\\.[A-Za-z_][A-Za-z0-9_]*\\s*==\\s*(['\"]).*?\\1$");
        }

        static void ValidateStepDependencies(
            XUUnityLightMcpScenarioValidatePayload payload,
            XUUnityLightMcpScenarioStepDefinition step,
            string stepId,
            int index,
            HashSet<string> knownPreviousOrCurrentStepIds)
        {
            foreach (var dependency in DependencyIds(step))
            {
                if (string.Equals(dependency, stepId, StringComparison.Ordinal))
                {
                    AddIssue(payload, "error", "self_dependency",
                        $"Step '{stepId}' cannot depend on itself.", stepId, index);
                    continue;
                }

                if (!knownPreviousOrCurrentStepIds.Contains(dependency))
                {
                    AddIssue(payload, "error", "unknown_dependency",
                        $"Step '{stepId}' depends on unknown or later step '{dependency}'. Dependencies must reference earlier steps.",
                        stepId, index);
                }
            }
        }

        static void AddIssue(XUUnityLightMcpScenarioValidatePayload payload, string severity, string code, string message, string stepId, int stepIndex)
        {
            payload.issues.Add(new XUUnityLightMcpScenarioIssue
            {
                severity = severity,
                code = code,
                message = message,
                stepId = stepId,
                stepIndex = stepIndex,
            });

            if (severity == "warning")
            {
                payload.warning_count++;
            }
            else
            {
                payload.error_count++;
            }
        }

        static string NormalizeScenarioName(string name)
        {
            var trimmed = (name ?? "").Trim();
            return string.IsNullOrWhiteSpace(trimmed) ? "unnamed_scenario" : trimmed;
        }

        static string NormalizeStepId(XUUnityLightMcpScenarioStepDefinition step, int index)
        {
            var trimmed = (step.stepId ?? "").Trim();
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                trimmed = $"step_{index + 1}";
                step.stepId = trimmed;
            }

            return trimmed;
        }

        static string NormalizeStepKind(XUUnityLightMcpScenarioStepDefinition step)
        {
            var kind = (step?.kind ?? "").Trim();
            if (string.IsNullOrWhiteSpace(kind))
            {
                kind = (step?.operation ?? "").Trim();
            }

            return kind.ToLowerInvariant();
        }

        static string SanitizeFileName(string name)
        {
            var safe = NormalizeScenarioName(name);
            foreach (var invalid in Path.GetInvalidFileNameChars())
            {
                safe = safe.Replace(invalid, '_');
            }
            return safe.Replace(' ', '_');
        }

        static bool IsPlayModeAction(string action)
        {
            var normalized = (action ?? "").Trim().ToLowerInvariant();
            return normalized == "enter" || normalized == "exit" || normalized == "pause" || normalized == "resume";
        }

        static bool IsPlayModeState(string state)
        {
            var normalized = (state ?? "").Trim().ToLowerInvariant();
            return normalized == "edit" || normalized == "playing" || normalized == "paused" || normalized == "transitioning";
        }

        static bool TryParseUtc(string value, out DateTime utc)
        {
            return DateTime.TryParse(
                value,
                null,
                System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                out utc);
        }

    }
}
