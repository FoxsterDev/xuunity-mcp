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
    static class XUUnityLightMcpScenarioProjectHookStepHandlers
    {
        public static bool ProcessProjectActionStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessProjectDefinedHookStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessProjectDefinedHookPollUntilStep(
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

            var implicitlyContinueNotStarted = string.Equals(
                payloadStatus,
                "not_started",
                StringComparison.OrdinalIgnoreCase);
            if (PredicateMatches(step.continueWhen, payloadJson) || implicitlyContinueNotStarted)
            {
                stepResult.status = "running";
                stepResult.outcome = string.IsNullOrWhiteSpace(pollResult.outcome)
                    ? (implicitlyContinueNotStarted
                        ? "hook_poll_until_waiting_not_started"
                        : "hook_poll_until_running")
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
        public static void CaptureTerminalPollUntilArtifacts(
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

        public static void ClearPollUntilState(XUUnityLightMcpScenarioRunState state)
        {
            state.pollUntilStartedAtUtc = "";
            state.pollUntilDeadlineUtc = "";
            state.pollUntilNextPollUtc = "";
            state.pollUntilPollCount = 0;
            state.waitingUntilUtc = "";
        }
    }
}
