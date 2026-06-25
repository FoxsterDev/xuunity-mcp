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
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpNestedOperationClient;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioHookExecutor;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioCompileTestStepHandlers
    {
        public static bool ProcessCompilePlayerScriptsStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessCompilePlayerScriptsStep(null, step, stepResult);
        }

        public static bool ProcessCompilePlayerScriptsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessEditModeTestsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessTestsStep(state, step, stepResult, "unity.tests.run_editmode", "EditMode");
        }

        public static bool ProcessPlayModeTestsStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessTestsStep(state, step, stepResult, "unity.tests.run_playmode", "PlayMode");
        }

        public static bool ProcessTestsStep(
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
        public static string FormatCompileFailureMessage(XUUnityLightMcpCompilePlayerScriptsPayload payload)
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
        public static bool IsEditorIdleForCompileSettle(XUUnityLightMcpScenarioStepResult stepResult)
        {
            return TryGetCompileSettleCompletionUtc(stepResult, out _)
                && !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && (EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode);
        }

        public static void FinalizeCompilePlayerScriptsStep(XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool TryGetCompileSettleCompletionUtc(XUUnityLightMcpScenarioStepResult stepResult, out string completedAtUtc)
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
    }
}
