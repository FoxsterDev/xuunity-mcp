using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
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
    static class XUUnityLightMcpScenarioRefreshStepHandler
    {
        public static bool ProcessProjectRefreshStep(XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            return ProcessProjectRefreshStep(null, step, stepResult);
        }

        public static bool ProcessProjectRefreshStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (state == null)
            {
                return ProcessNestedOperationStep("unity.project.refresh", BuildProjectRefreshArgsJson(step), stepResult);
            }

            if (stepResult.status == "pending")
            {
                var request = BuildNestedRequest("unity.project.refresh", BuildProjectRefreshArgsJson(step), GetTimeoutMs(step, 45.0d));
                state.pendingNestedStartedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
                var stopwatch = Stopwatch.StartNew();
                var response = ExecuteNestedOperation(request.operation, request.args_json, request);
                stopwatch.Stop();
                stepResult.execution_duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
                stepResult.timing_measured = true;
                UpdateProjectRefreshTiming(state.pendingNestedStartedAtUtc, stepResult);
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
                    UpdateProjectRefreshTiming(state.pendingNestedStartedAtUtc, stepResult);
                    return true;
                }

                state.pendingNestedRequestId = request.request_id;
                state.pendingNestedOperation = request.operation;
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

            UpdateProjectRefreshTiming(state.pendingNestedStartedAtUtc, stepResult);

            if (!TryParseUtc(state.waitingUntilUtc, out var deadlineUtc))
            {
                stepResult.status = "failed";
                stepResult.error_code = "invalid_wait_deadline";
                stepResult.error_message = "Scenario refresh step lost its deadline state.";
                ClearPendingNestedOperation(state);
                return true;
            }

            if (IsRefreshRequestSettled(
                state.pendingNestedRequestId,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettleRequestId,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettlePending,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettlePhase,
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode))
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
            stepResult.payload_json = BuildRefreshTimeoutPayloadJson(
                stepResult.payload_json, state.pendingNestedStableTickCount, state.pendingNestedRequestId);
            ClearPendingNestedOperation(state);
            return true;
        }

        public static string ClassifyRefreshSettleTimeout(bool isCompiling, bool isUpdating, bool settlePending, string settlePhase)
        {
            if (isCompiling || isUpdating)
            {
                return "compile_import_churn_timeout";
            }

            if (settlePending)
            {
                if (string.Equals(settlePhase, "waiting_for_package_settle", StringComparison.Ordinal))
                {
                    return "package_settle_timeout";
                }

                if (string.Equals(settlePhase, "waiting_for_stable_idle_ticks", StringComparison.Ordinal))
                {
                    return "idle_confirmation_incomplete";
                }

                return "editor_busy_timeout";
            }

            return "lost_final_accounting";
        }

        public static string BuildRefreshTimeoutPayloadJson(string existingPayloadJson, int stableIdleTicks, string expectedRequestId = "")
        {
            return BuildRefreshTimeoutPayloadJson(
                existingPayloadJson,
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettlePending,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettlePhase,
                XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(),
                stableIdleTicks,
                XUUnityLightMcpBridgeRuntimeState.RefreshSettleRequestId,
                expectedRequestId);
        }

        public static string BuildRefreshTimeoutPayloadJson(
            string existingPayloadJson,
            bool isCompiling,
            bool isUpdating,
            bool settlePending,
            string settlePhase,
            string playmodeState,
            int stableIdleTicks,
            string settleRequestId,
            string expectedRequestId = "")
        {
            XUUnityLightMcpProjectRefreshTimeoutPayload payload = null;
            if (!string.IsNullOrWhiteSpace(existingPayloadJson))
            {
                try
                {
                    payload = JsonUtility.FromJson<XUUnityLightMcpProjectRefreshTimeoutPayload>(existingPayloadJson);
                }
                catch (Exception)
                {
                    payload = null;
                }
            }

            payload = payload ?? new XUUnityLightMcpProjectRefreshTimeoutPayload();

            var normalizedPhase = settlePhase ?? "";
            var classification = ClassifyRefreshSettleTimeout(isCompiling, isUpdating, settlePending, normalizedPhase);
            payload.settle_timed_out = true;
            payload.settle_timeout_classification = classification;
            payload.settle_phase_at_timeout = normalizedPhase;
            payload.refresh_settle_pending_at_timeout = settlePending;
            payload.editor_is_compiling_at_timeout = isCompiling;
            payload.editor_is_updating_at_timeout = isUpdating;
            payload.playmode_state_at_timeout = playmodeState ?? "";
            payload.stable_idle_ticks_at_timeout = stableIdleTicks;
            payload.operation_may_have_completed = classification == "lost_final_accounting" || classification == "idle_confirmation_incomplete";
            payload.expected_settle_request_id = expectedRequestId ?? "";
            payload.observed_settle_request_id = settleRequestId ?? "";
            payload.settled_completion = "unproven";
            payload.settled_completion_reason = string.IsNullOrWhiteSpace(expectedRequestId)
                ? "missing_expected_request_id"
                : string.IsNullOrWhiteSpace(settleRequestId)
                    ? "missing_runtime_request_id"
                    : !string.Equals(expectedRequestId, settleRequestId, StringComparison.Ordinal)
                        ? "request_id_mismatch"
                        : "matching_request_not_confirmed_settled";
            payload.settle_phase = normalizedPhase;
            if (string.IsNullOrWhiteSpace(payload.settle_request_id))
            {
                payload.settle_request_id = settleRequestId ?? "";
            }

            return JsonUtility.ToJson(payload);
        }

        public static string BuildProjectRefreshArgsJson(XUUnityLightMcpScenarioStepDefinition step)
        {
            var args = new XUUnityLightMcpProjectRefreshArgs
            {
                forceAssetRefresh = step.forceAssetRefresh,
                resolvePackages = step.resolvePackages,
                rerunHealthProbe = step.rerunHealthProbe,
            };

            return JsonUtility.ToJson(args);
        }

        internal static bool IsRefreshRequestSettled(
            string expectedRequestId,
            string observedRequestId,
            bool settlePending,
            string settlePhase,
            bool isCompiling,
            bool isUpdating,
            bool playModeStable)
        {
            return !string.IsNullOrWhiteSpace(expectedRequestId)
                && string.Equals(expectedRequestId, observedRequestId, StringComparison.Ordinal)
                && !settlePending
                && string.Equals(settlePhase, "settled", StringComparison.Ordinal)
                && !isCompiling
                && !isUpdating
                && playModeStable;
        }

        internal static bool TryCalculateProjectRefreshTiming(
            string startedAtUtc,
            DateTime nowUtc,
            double executionDurationSeconds,
            out double durationSeconds,
            out double settleWaitDurationSeconds)
        {
            durationSeconds = 0.0d;
            settleWaitDurationSeconds = 0.0d;
            if (!DateTime.TryParseExact(startedAtUtc, "O", CultureInfo.InvariantCulture,
                    DateTimeStyles.RoundtripKind, out var startedUtc)
                || startedUtc.Kind != DateTimeKind.Utc
                || nowUtc.Kind != DateTimeKind.Utc
                || nowUtc < startedUtc
                || double.IsNaN(executionDurationSeconds)
                || double.IsInfinity(executionDurationSeconds)
                || executionDurationSeconds < 0.0d)
            {
                return false;
            }

            durationSeconds = Math.Round((nowUtc - startedUtc).TotalSeconds, 6);
            if (durationSeconds < executionDurationSeconds)
            {
                durationSeconds = 0.0d;
                return false;
            }

            settleWaitDurationSeconds = Math.Round(durationSeconds - executionDurationSeconds, 6);
            return true;
        }

        private static void UpdateProjectRefreshTiming(string startedAtUtc, XUUnityLightMcpScenarioStepResult stepResult)
        {
            if (!stepResult.timing_measured)
            {
                return;
            }

            stepResult.timing_measured = TryCalculateProjectRefreshTiming(
                startedAtUtc, DateTime.UtcNow, stepResult.execution_duration_seconds,
                out var durationSeconds, out var settleWaitDurationSeconds);
            if (stepResult.timing_measured)
            {
                stepResult.duration_seconds = durationSeconds;
                stepResult.settle_wait_duration_seconds = settleWaitDurationSeconds;
            }
            else
            {
                stepResult.duration_seconds = 0.0d;
                stepResult.settle_wait_duration_seconds = 0.0d;
            }
        }

        public static void FinalizeProjectRefreshStep(XUUnityLightMcpScenarioStepResult stepResult)
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
    }
}
