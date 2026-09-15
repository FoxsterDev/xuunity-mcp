using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpSdkAndroidResolveOperation : IXUUnityLightMcpOperation
    {
        public const string RegisteredOperationName = "unity.sdk.android_resolve";
        internal const int MaxTrackedGeneratedPaths = 32;
        internal const int MaxExpectations = 128;
        public string OperationName => RegisteredOperationName;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpSdkAndroidResolveArgs()
                : JsonUtility.FromJson<XUUnityLightMcpSdkAndroidResolveArgs>(request.args_json)
                  ?? new XUUnityLightMcpSdkAndroidResolveArgs();

            if (!TryValidateArgs(args, out var argsErrorCode, out var argsErrorMessage))
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, argsErrorCode, argsErrorMessage);
            }

            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "sdk_android_resolve_editor_busy",
                    "Typed Android resolve requires an idle Unity editor in Edit Mode.");
            }

            if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "sdk_android_target_not_active",
                    $"Typed Android resolve requires active BuildTarget.Android, but Unity reports '{EditorUserBuildSettings.activeBuildTarget}'.");
            }

            if (!XUUnityLightMcpBuildTargetGetOperation.IsPlatformSupportLoaded(BuildTarget.Android))
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "sdk_android_support_missing",
                    "Typed Android resolve requires the Unity Android Build Support module.");
            }

            if (XUUnityLightMcpSdkAndroidResolveRuntime.HasPendingRequest(out var activeRequestId))
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "sdk_android_resolve_busy",
                    $"Another typed Android resolve is still active: {activeRequestId}.");
            }

            if (args.refreshBefore)
            {
                XUUnityLightMcpLifecycleMonitor.MarkAssetRefreshRequested();
                AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);
            }

            XUUnityLightMcpSdkAndroidResolveRuntime.Begin(
                request,
                args,
                EditorUserBuildSettings.activeBuildTarget.ToString(),
                targetSupportLoaded: true);
            if (!XUUnityLightMcpEdm4uAdapter.TryStart(
                    args.force,
                    XUUnityLightMcpSdkAndroidResolveRuntime.OnResolverCompleted,
                    out var adapter,
                    out var adapterError))
            {
                XUUnityLightMcpSdkAndroidResolveRuntime.Abandon();
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "sdk_android_resolver_unavailable",
                    adapterError);
            }

            XUUnityLightMcpSdkAndroidResolveRuntime.RecordAdapter(adapter);
            XUUnityLightMcpBridgeRuntimeState.MarkPackageOperationStarted(
                "EDM4U.android",
                "typed_resolve_callback_pending");
            return null;
        }

        internal static bool TryValidateArgs(
            XUUnityLightMcpSdkAndroidResolveArgs args,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";
            if (args == null)
            {
                errorCode = "sdk_android_resolve_args_missing";
                errorMessage = "Typed Android resolve arguments are required.";
                return false;
            }

            if (args.trackedGeneratedPaths == null || args.trackedGeneratedPaths.Count == 0)
            {
                errorCode = "sdk_android_resolve_tracked_outputs_missing";
                errorMessage = "trackedGeneratedPaths must contain at least one generated output.";
                return false;
            }

            if (args.trackedGeneratedPaths.Count > MaxTrackedGeneratedPaths)
            {
                errorCode = "sdk_android_resolve_tracked_outputs_limit";
                errorMessage = $"trackedGeneratedPaths supports at most {MaxTrackedGeneratedPaths} entries.";
                return false;
            }

            if (args.expectations == null || args.expectations.Count == 0)
            {
                errorCode = "sdk_android_resolve_expectations_missing";
                errorMessage = "expectations must prove at least one expected post-resolve dependency coordinate.";
                return false;
            }

            if (args.expectations.Count > MaxExpectations)
            {
                errorCode = "sdk_android_resolve_expectations_limit";
                errorMessage = $"expectations supports at most {MaxExpectations} entries.";
                return false;
            }

            if (args.stableIdleTicks < 2 || args.stableIdleTicks > 10)
            {
                errorCode = "sdk_android_resolve_stable_ticks_invalid";
                errorMessage = "stableIdleTicks must be between 2 and 10.";
                return false;
            }

            var normalized = args.trackedGeneratedPaths
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Select(path => path.Trim())
                .Distinct(StringComparer.Ordinal)
                .ToList();
            if (normalized.Count == 0)
            {
                errorCode = "sdk_android_resolve_tracked_outputs_missing";
                errorMessage = "trackedGeneratedPaths must contain at least one non-empty path.";
                return false;
            }

            foreach (var path in normalized)
            {
                if (!XUUnityLightMcpSdkPaths.TryResolveProjectFile(path, out _, out var pathError))
                {
                    errorCode = "sdk_android_resolve_tracked_output_invalid";
                    errorMessage = $"{path}: {pathError}";
                    return false;
                }
            }

            args.trackedGeneratedPaths = normalized;
            return true;
        }
    }

    internal static class XUUnityLightMcpSdkAndroidResolveRuntime
    {
        static readonly object Gate = new();

        public static XUUnityLightMcpPersistedSdkAndroidResolveState Begin(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpSdkAndroidResolveArgs args,
            string activeBuildTarget,
            bool targetSupportLoaded)
        {
            lock (Gate)
            {
                var startedAt = UtcNow();
                var timeoutMs = Math.Max(1000, request.timeout_ms - 1000);
                var state = new XUUnityLightMcpPersistedSdkAndroidResolveState
                {
                    request_id = request.request_id ?? "",
                    operation = XUUnityLightMcpSdkAndroidResolveOperation.RegisteredOperationName,
                    project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                    started_at_utc = startedAt,
                    deadline_at_utc = DateTime.UtcNow.AddMilliseconds(timeoutMs).ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    args = args,
                    active_build_target = activeBuildTarget ?? "",
                    target_support_loaded = targetSupportLoaded,
                };
                PersistLocked(state);
                return state;
            }
        }

        public static bool HasPendingRequest(out string requestId)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    requestId = "";
                    return false;
                }

                if (string.Equals(state.response_handoff_state, "pending_write", StringComparison.Ordinal))
                {
                    TryWriteResponseAndReleaseLocked(state);
                    if (!TryLoadLocked(out state))
                    {
                        requestId = "";
                        return false;
                    }
                }

                requestId = state.request_id ?? "";
                return !string.IsNullOrWhiteSpace(requestId);
            }
        }

        public static void RecordAdapter(string adapter)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                state.resolver_adapter = adapter ?? "";
                PersistLocked(state);
            }
        }

        public static void OnResolverCompleted(bool success)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                state.resolver_callback_received = true;
                state.resolver_callback_success = success;
                state.resolver_callback_at_utc = UtcNow();
                PersistLocked(state);
            }
        }

        public static void Tick()
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                if (string.Equals(state.response_handoff_state, "pending_write", StringComparison.Ordinal))
                {
                    TryWriteResponseAndReleaseLocked(state);
                    return;
                }

                if (DeadlineReached(state))
                {
                    CompleteFailedLocked(state, ResolveTimeoutFailureClass(state));
                    TryWriteResponseAndReleaseLocked(state);
                    return;
                }

                if (!state.resolver_callback_received)
                {
                    return;
                }

                if (!state.resolver_callback_success)
                {
                    CompleteFailedLocked(state, "resolver_reported_failure");
                    TryWriteResponseAndReleaseLocked(state);
                    return;
                }

                if (!IsEditorIdle())
                {
                    if (state.stable_idle_ticks_observed != 0)
                    {
                        state.stable_idle_ticks_observed = 0;
                        state.last_output_signature = "";
                        PersistLocked(state);
                    }
                    return;
                }

                var outputs = ReadGeneratedOutputs(state.args?.trackedGeneratedPaths);
                var allReadable = outputs.Count > 0 && outputs.All(output => output.file_exists && string.IsNullOrWhiteSpace(output.error));
                var signature = allReadable ? BuildOutputSignature(outputs) : "";
                if (allReadable && string.Equals(signature, state.last_output_signature, StringComparison.Ordinal))
                {
                    state.stable_idle_ticks_observed++;
                }
                else
                {
                    state.stable_idle_ticks_observed = allReadable ? 1 : 0;
                    state.last_output_signature = signature;
                }
                state.generated_outputs = outputs;

                var requiredTicks = Math.Max(2, state.args?.stableIdleTicks ?? 2);
                if (state.stable_idle_ticks_observed < requiredTicks)
                {
                    PersistLocked(state);
                    return;
                }

                state.dependency_verification = XUUnityLightMcpSdkDependencyVerifyOperation.BuildPayload(
                    new XUUnityLightMcpSdkDependencyVerifyArgs
                    {
                        stopOnFirstFailure = false,
                        expectations = state.args?.expectations ?? new List<XUUnityLightMcpSdkDependencyExpectation>(),
                    });
                if (!string.Equals(state.dependency_verification.status, "passed", StringComparison.Ordinal))
                {
                    CompleteFailedLocked(state, "resolver_expected_dependency_missing");
                    TryWriteResponseAndReleaseLocked(state);
                    return;
                }

                state.status = "passed";
                state.verdict = "passed";
                state.trust_class = "decision_grade";
                state.decision_ready = true;
                state.failure_class = "";
                state.resolver_output_freshness = "proven";
                state.recommended_next_action = "run_sdk_generated_diff_guard_then_compile";
                CompleteLocked(state);
                TryWriteResponseAndReleaseLocked(state);
            }
        }

        public static void Abandon()
        {
            lock (Gate)
            {
                DeleteLocked();
            }
        }

        internal static List<XUUnityLightMcpSdkGeneratedOutputEvidence> ReadGeneratedOutputs(
            IEnumerable<string> paths)
        {
            var outputs = new List<XUUnityLightMcpSdkGeneratedOutputEvidence>();
            foreach (var path in paths ?? Array.Empty<string>())
            {
                var output = new XUUnityLightMcpSdkGeneratedOutputEvidence { path = path ?? "" };
                if (!XUUnityLightMcpSdkPaths.TryResolveProjectFile(output.path, out var fullPath, out var pathError))
                {
                    output.full_path = fullPath ?? "";
                    output.error = pathError;
                    outputs.Add(output);
                    continue;
                }

                output.full_path = fullPath;
                try
                {
                    output.file_exists = File.Exists(fullPath);
                    if (output.file_exists)
                    {
                        var info = new FileInfo(fullPath);
                        output.file_size_bytes = info.Length;
                        output.sha256 = XUUnityLightMcpSdkHash.ComputeSha256(fullPath);
                    }
                }
                catch (Exception ex)
                {
                    output.error = ex.Message;
                }
                outputs.Add(output);
            }
            return outputs;
        }

        internal static string BuildOutputSignature(
            IEnumerable<XUUnityLightMcpSdkGeneratedOutputEvidence> outputs)
        {
            return string.Join(
                "\n",
                (outputs ?? Array.Empty<XUUnityLightMcpSdkGeneratedOutputEvidence>())
                    .OrderBy(output => output.path, StringComparer.Ordinal)
                    .Select(output => $"{output.path}\t{output.file_size_bytes}\t{output.sha256}"));
        }

        static bool IsEditorIdle()
        {
            return !EditorApplication.isCompiling
                   && !EditorApplication.isUpdating
                   && !EditorApplication.isPlayingOrWillChangePlaymode;
        }

        static string ResolveTimeoutFailureClass(XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            if (!state.resolver_callback_received)
            {
                return "resolver_completion_unproven";
            }

            if (!state.resolver_callback_success)
            {
                return "resolver_reported_failure";
            }

            if (state.generated_outputs == null
                || state.generated_outputs.Count == 0
                || state.generated_outputs.Any(output => !output.file_exists || !string.IsNullOrWhiteSpace(output.error)))
            {
                return "resolver_output_missing";
            }

            if (state.stable_idle_ticks_observed < Math.Max(2, state.args?.stableIdleTicks ?? 2))
            {
                return "resolver_output_unstable";
            }

            return "resolver_expected_dependency_missing";
        }

        static void CompleteFailedLocked(
            XUUnityLightMcpPersistedSdkAndroidResolveState state,
            string failureClass)
        {
            state.status = "failed";
            state.verdict = "failed";
            state.trust_class = "failed_closed";
            state.decision_ready = false;
            state.failure_class = failureClass ?? "resolver_output_stale";
            state.resolver_output_freshness = "unproven";
            state.recommended_next_action = state.failure_class switch
            {
                "resolver_completion_unproven" => "inspect_edm4u_console_then_retry_typed_resolve",
                "resolver_reported_failure" => "inspect_edm4u_console_and_generated_outputs",
                "resolver_expected_dependency_missing" => "review_expected_coordinate_and_resolver_output",
                _ => "wait_for_editor_idle_then_retry_typed_resolve",
            };
            CompleteLocked(state);
        }

        static void CompleteLocked(XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            state.completed_at_utc = UtcNow();
            state.response_handoff_state = "pending_write";
            PersistLocked(state);
        }

        static bool TryWriteResponseAndReleaseLocked(XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            try
            {
                var response = XUUnityLightMcpResponseWriter.Success(
                    state.request_id,
                    state.operation,
                    JsonUtility.ToJson(BuildPayload(state)));
                XUUnityLightMcpResponseWriter.Write(response);
                XUUnityLightMcpBridgeRuntimeState.MarkRequestProcessed(
                    state.request_id,
                    state.operation,
                    state.status,
                    state.started_at_utc,
                    0);
                try
                {
                XUUnityLightMcpRequestJournal.WriteRequestCompleted(
                        state.request_id,
                        state.operation,
                        state.status,
                        state.started_at_utc,
                        state.completed_at_utc,
                        0,
                        response);
                }
                catch
                {
                }

                XUUnityLightMcpBridgeRuntimeState.MarkPackageOperationCompleted();
                DeleteLocked();
                return true;
            }
            catch
            {
                return false;
            }
        }

        internal static XUUnityLightMcpSdkAndroidResolvePayload BuildPayload(
            XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            return new XUUnityLightMcpSdkAndroidResolvePayload
            {
                project_root = state.project_root ?? XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                status = state.status ?? "failed",
                verdict = state.verdict ?? "inconclusive",
                trust_class = state.trust_class ?? "unproven",
                decision_ready = state.decision_ready,
                failure_class = state.failure_class ?? "",
                active_build_target = state.active_build_target ?? "",
                build_target_precondition = string.Equals(state.active_build_target, BuildTarget.Android.ToString(), StringComparison.Ordinal)
                    ? "confirmed"
                    : "failed",
                target_support_loaded = state.target_support_loaded,
                force = state.args?.force ?? true,
                asset_refresh_before_requested = state.args?.refreshBefore ?? false,
                resolver_adapter = state.resolver_adapter ?? "",
                resolver_callback_received = state.resolver_callback_received,
                resolver_callback_success = state.resolver_callback_success,
                resolver_callback_at_utc = state.resolver_callback_at_utc ?? "",
                resolver_output_freshness = state.resolver_output_freshness ?? "unproven",
                stable_idle_ticks_required = Math.Max(2, state.args?.stableIdleTicks ?? 2),
                stable_idle_ticks_observed = state.stable_idle_ticks_observed,
                generated_outputs = state.generated_outputs ?? new List<XUUnityLightMcpSdkGeneratedOutputEvidence>(),
                dependency_verification = state.dependency_verification ?? new XUUnityLightMcpSdkDependencyVerifyPayload(),
                started_at_utc = state.started_at_utc ?? "",
                completed_at_utc = state.completed_at_utc ?? "",
                duration_seconds = CalculateDurationSeconds(state.started_at_utc, state.completed_at_utc),
                recommended_next_action = state.recommended_next_action ?? "",
            };
        }

        static bool DeadlineReached(XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            return DateTime.TryParse(
                       state.deadline_at_utc,
                       null,
                       System.Globalization.DateTimeStyles.RoundtripKind,
                       out var deadline)
                   && DateTime.UtcNow >= deadline.ToUniversalTime();
        }

        static bool TryLoadLocked(out XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            state = null;
            try
            {
                if (!File.Exists(XUUnityLightMcpFileIpcPaths.ActiveSdkAndroidResolveStatePath))
                {
                    return false;
                }

                state = JsonUtility.FromJson<XUUnityLightMcpPersistedSdkAndroidResolveState>(
                    File.ReadAllText(XUUnityLightMcpFileIpcPaths.ActiveSdkAndroidResolveStatePath));
                return state != null && !string.IsNullOrWhiteSpace(state.request_id);
            }
            catch
            {
                state = null;
                return false;
            }
        }

        static void PersistLocked(XUUnityLightMcpPersistedSdkAndroidResolveState state)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            XUUnityLightMcpAtomicFileWriter.WriteAllText(
                XUUnityLightMcpFileIpcPaths.ActiveSdkAndroidResolveStatePath,
                JsonUtility.ToJson(state, true));
        }

        static void DeleteLocked()
        {
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.ActiveSdkAndroidResolveStatePath))
                {
                    File.Delete(XUUnityLightMcpFileIpcPaths.ActiveSdkAndroidResolveStatePath);
                }
            }
            catch
            {
            }
        }

        static double CalculateDurationSeconds(string startedAtUtc, string completedAtUtc)
        {
            if (!DateTime.TryParse(
                    startedAtUtc,
                    null,
                    System.Globalization.DateTimeStyles.RoundtripKind,
                    out var started)
                || !DateTime.TryParse(
                    completedAtUtc,
                    null,
                    System.Globalization.DateTimeStyles.RoundtripKind,
                    out var completed))
            {
                return 0.0d;
            }

            return Math.Round(Math.Max(0.0d, (completed - started).TotalSeconds), 6);
        }

        static string UtcNow()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        }
    }
}
