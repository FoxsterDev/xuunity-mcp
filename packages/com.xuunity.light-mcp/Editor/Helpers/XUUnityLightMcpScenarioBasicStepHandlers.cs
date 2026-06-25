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
    static class XUUnityLightMcpScenarioBasicStepHandlers
    {
        public static bool ProcessWaitStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessWaitForPlayModeStateStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessAssertPlayModeStateStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessConsoleTailStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpConsoleTailArgs
            {
                limit = step.limit > 0 ? step.limit : 50,
                includeTypes = step.includeTypes,
            };

            return ProcessNestedOperationStep("unity.console.tail", JsonUtility.ToJson(args), stepResult);
        }

        public static bool ProcessConsoleGrepStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessAssertSceneStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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

        public static bool ProcessPlayModeSetStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpPlayModeSetArgs
            {
                action = step.action,
            };

            return ProcessNestedOperationStep("unity.playmode.set", JsonUtility.ToJson(args), stepResult);
        }

        public static bool ProcessGameViewScreenshotStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var args = new XUUnityLightMcpGameViewScreenshotArgs
            {
                fileName = step.fileName,
                includeImage = step.includeImage,
                maxResolution = step.maxResolution > 0 ? step.maxResolution : 640,
            };

            return ProcessNestedOperationStep("unity.game_view.screenshot", JsonUtility.ToJson(args), stepResult);
        }
        public static bool ProcessGameViewConfigureStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
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
    }
}
