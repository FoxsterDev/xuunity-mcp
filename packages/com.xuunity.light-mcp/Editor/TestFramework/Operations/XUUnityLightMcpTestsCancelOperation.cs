using System;
using System.Reflection;
using UnityEditor;
using UnityEditor.TestTools.TestRunner.Api;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpTestsCancelOperation : IXUUnityLightMcpOperation
    {
        internal const string Name = "unity.tests.cancel";
        const double CancelSettleWatchSeconds = 60.0;
        const double CancelFallbackSettleSeconds = 3.0;

        public string OperationName => Name;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            XUUnityLightMcpTestsCancelArgs args;
            try
            {
                args = string.IsNullOrWhiteSpace(request.args_json)
                    ? new XUUnityLightMcpTestsCancelArgs()
                    : JsonUtility.FromJson<XUUnityLightMcpTestsCancelArgs>(request.args_json) ?? new XUUnityLightMcpTestsCancelArgs();
            }
            catch (Exception ex)
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "invalid_args", ex.Message);
            }

            if (!XUUnityLightMcpTestRunState.TryLoadActive(out var state)
                || (!string.IsNullOrWhiteSpace(args.requestId)
                    && !string.Equals(state.request_id, args.requestId, StringComparison.Ordinal)))
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "test_run_not_active",
                    string.IsNullOrWhiteSpace(args.requestId)
                        ? "No test run is active."
                        : $"Test run {args.requestId} is not the active run; it already finished or never started.");
            }

            var payload = new XUUnityLightMcpTestsCancelPayload
            {
                request_id = state.request_id ?? "",
                operation = state.operation ?? "",
                run_guid = state.run_guid ?? "",
                cancel_requested = true,
                passed_so_far = Math.Max(0, state.passed),
                failed_so_far = Math.Max(0, state.failed),
                last_started_test = state.last_started_test ?? "",
                playmode_state = XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(),
            };

            var cancelMethod = ResolveCancelMethod();
            if (cancelMethod == null)
            {
                payload.cancel_api = "unavailable";
                payload.reason = "test_framework_has_no_cancel_api";
                payload.recommended_next_action = "upgrade_com_unity_test_framework_to_1_4_or_wait_for_the_run";
                return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
            }

            payload.cancel_api = "TestRunnerApi.CancelTestRun";
            if (string.IsNullOrWhiteSpace(state.run_guid))
            {
                payload.reason = "run_guid_unknown";
                payload.recommended_next_action = "wait_for_the_run_or_restart_the_editor";
                return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
            }

            try
            {
                payload.cancel_accepted = (bool)cancelMethod.Invoke(null, new object[] { state.run_guid });
            }
            catch (TargetInvocationException ex)
            {
                payload.reason = ex.InnerException?.GetType().Name ?? ex.GetType().Name;
            }

            if (!payload.cancel_accepted && IsRunnerGone(state.run_guid))
            {
                payload.cancel_accepted = true;
                payload.cancel_api = "orphaned_run_completion";
            }

            if (payload.cancel_accepted)
            {
                XUUnityLightMcpTestRunState.TryMarkCancelRequested(state.request_id, out _);
                payload.reason = "cancel_requested_remaining_tests_marked_not_run";
                payload.recommended_next_action = "unity_request_final_status";
                WatchCancelledRun(state.request_id, state.run_guid, state.operation);
            }
            else if (string.IsNullOrWhiteSpace(payload.reason))
            {
                payload.reason = "test_runner_rejected_cancel_run_not_running_or_already_cancelling";
                payload.recommended_next_action = "unity_request_final_status";
            }

            return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
        }

        internal static MethodInfo ResolveCancelMethod()
        {
            return typeof(TestRunnerApi).GetMethod(
                "CancelTestRun",
                BindingFlags.Public | BindingFlags.Static,
                null,
                new[] { typeof(string) },
                null);
        }

        static bool IsRunnerGone(string runGuid)
        {
            var isRunning = ResolveIsRunningMethod();
            return isRunning != null && !(bool)isRunning.Invoke(null, new object[] { runGuid });
        }

        static MethodInfo ResolveIsRunningMethod()
        {
            return typeof(TestRunnerApi).GetMethod(
                "IsRunning",
                BindingFlags.NonPublic | BindingFlags.Static,
                null,
                new[] { typeof(string) },
                null);
        }

        static void WatchCancelledRun(string requestId, string runGuid, string operation)
        {
            var isRunning = ResolveIsRunningMethod();
            var startedAt = EditorApplication.timeSinceStartup;
            var deadline = startedAt + CancelSettleWatchSeconds;
            void Tick()
            {
                var runnerStopped = isRunning == null
                    ? EditorApplication.timeSinceStartup - startedAt > CancelFallbackSettleSeconds
                    : !(bool)isRunning.Invoke(null, new object[] { runGuid });
                var stillActive = XUUnityLightMcpTestRunState.TryLoadActive(out var active)
                                  && string.Equals(active.request_id, requestId, StringComparison.Ordinal);
                if (!runnerStopped && EditorApplication.timeSinceStartup <= deadline)
                {
                    return;
                }

                EditorApplication.update -= Tick;
                if (stillActive)
                {
                    if (string.Equals(operation, XUUnityLightMcpPlayModeTestRunner.OperationName, StringComparison.Ordinal))
                    {
                        XUUnityLightMcpPlayModeTestRunner.TryCompleteCancelledRun(requestId);
                    }
                    else
                    {
                        XUUnityLightMcpEditModeTestRunner.TryCompleteCancelledRun(requestId);
                    }
                }

                if (EditorApplication.isPlaying)
                {
                    EditorApplication.ExitPlaymode();
                }
            }

            EditorApplication.update += Tick;
        }
    }
}
