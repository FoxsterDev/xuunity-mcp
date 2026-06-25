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

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpNestedOperationClient
    {
        public static bool ProcessNestedOperationStep(string operationName, string argsJson, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static XUUnityLightMcpResponse ExecuteNestedOperation(string operationName, string argsJson)
        {
            return ExecuteNestedOperation(operationName, argsJson, null);
        }

        public static XUUnityLightMcpResponse ExecuteNestedOperation(string operationName, string argsJson, XUUnityLightMcpRequest requestOverride)
        {
            if (!XUUnityLightMcpOperationRegistry.TryGet(operationName, out var operation))
            {
                throw new InvalidOperationException($"Scenario runner could not resolve nested operation '{operationName}'.");
            }

            var nestedRequest = requestOverride ?? BuildNestedRequest(operationName, argsJson, 30000);

            return operation.Execute(nestedRequest);
        }

        public static XUUnityLightMcpRequest BuildNestedRequest(string operationName, string argsJson, int timeoutMs)
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

        public static bool TryTakePendingNestedResponse(string requestId, out XUUnityLightMcpResponse response)
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

        public static void ApplyNestedResponse(XUUnityLightMcpScenarioStepResult stepResult, XUUnityLightMcpResponse response, string startedAtUtc)
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

        public static void ApplyTestsResponse(XUUnityLightMcpScenarioStepResult stepResult, XUUnityLightMcpResponse response, string startedAtUtc, string modeLabel)
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

        public static void ClearPendingNestedOperation(XUUnityLightMcpScenarioRunState state)
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

        public static void CapturePendingNestedResponse(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpResponse response)
        {
            state.pendingNestedResponseStatus = response?.status ?? "";
            state.pendingNestedResponseCompletedAtUtc = response?.completed_at_utc ?? "";
            state.pendingNestedResponsePayloadJson = response?.payload_json ?? "";
            state.pendingNestedResponseErrorCode = response?.error?.code ?? "";
            state.pendingNestedResponseErrorMessage = response?.error?.message ?? "";
        }

        public static bool TryGetCapturedPendingNestedResponse(XUUnityLightMcpScenarioRunState state, out XUUnityLightMcpResponse response)
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

        public static bool ShouldWaitForPlayModeTestsSettle(string operationName, XUUnityLightMcpResponse response)
        {
            return string.Equals(operationName, "unity.tests.run_playmode", StringComparison.Ordinal)
                && response != null
                && string.Equals(response.status, "ok", StringComparison.OrdinalIgnoreCase);
        }

        public static bool IsEditorIdleForPlayModeTestsSettle()
        {
            return !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && !EditorApplication.isPlaying
                && !EditorApplication.isPlayingOrWillChangePlaymode
                && string.Equals(XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(), "edit", StringComparison.Ordinal);
        }
        public static string FormatTestsFailureMessage(XUUnityLightMcpTestsPayload payload, string modeLabel)
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
    }
}
