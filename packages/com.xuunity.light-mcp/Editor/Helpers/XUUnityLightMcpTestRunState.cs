using System;
using System.IO;
using System.Linq;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpTestRunState
    {
        const string PlayModeTestsOperationName = "unity.tests.run_playmode";
        static readonly object Gate = new();

        public static XUUnityLightMcpPersistedTestRunState Begin(string requestId, string operation, string testMode, string filterSummary, int requestTimeoutMs)
        {
            lock (Gate)
            {
                XUUnityLightMcpFileIpcPaths.EnsureDirectories();
                var state = new XUUnityLightMcpPersistedTestRunState
                {
                    request_id = requestId ?? "",
                    operation = operation ?? "",
                    project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                    test_mode = testMode ?? "",
                    started_at_utc = UtcNow(),
                    request_timeout_ms = Math.Max(1000, requestTimeoutMs),
                    runtime_timeout_ms = Math.Max(1000, requestTimeoutMs),
                    run_phase = "submitted",
                    last_progress_at_utc = "",
                    timeout_classification = "",
                    completed_at_utc = "",
                    filter_summary = filterSummary ?? "",
                    response_handoff_state = "pending",
                    failures = new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(),
                };

                PersistLocked(state);
                return state;
            }
        }

        public static bool TryLoadPending(out XUUnityLightMcpPersistedTestRunState state)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out state))
                {
                    return false;
                }

                if (ShouldDiscardStalePendingStateLocked(state))
                {
                    DeleteLocked();
                    state = null;
                    return false;
                }

                return !string.IsNullOrWhiteSpace(state.request_id)
                       && !string.Equals(state.response_handoff_state, "written", StringComparison.Ordinal);
            }
        }

        public static bool TryLoadActive(out XUUnityLightMcpPersistedTestRunState state)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out state))
                {
                    return false;
                }

                return !string.IsNullOrWhiteSpace(state.request_id)
                       && string.IsNullOrWhiteSpace(state.completed_at_utc)
                       && !string.Equals(state.response_handoff_state, "written", StringComparison.Ordinal);
            }
        }

        public static bool TryRestoreActiveForOperation(string operation, out XUUnityLightMcpPersistedTestRunState state)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out state))
                {
                    return false;
                }

                if (ShouldDiscardStalePendingStateLocked(state))
                {
                    DeleteLocked();
                    state = null;
                    return false;
                }

                return string.Equals(state.operation, operation ?? "", StringComparison.Ordinal)
                       && string.Equals(state.response_handoff_state, "pending", StringComparison.Ordinal)
                       && string.IsNullOrWhiteSpace(state.completed_at_utc)
                       && !string.IsNullOrWhiteSpace(state.request_id);
            }
        }

        public static void RecordRunStarted(int total)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                state.total = Math.Max(0, total);
                state.run_phase = "started";
                state.last_progress_at_utc = UtcNow();
                PersistLocked(state);
            }
        }

        public static void RecordTestStarted(string testName)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                state.run_phase = "running";
                state.last_started_test = testName ?? "";
                state.last_progress_at_utc = UtcNow();
                PersistLocked(state);
            }
        }

        public static void RecordTestFinished(string testStatus, string testName, string message)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return;
                }

                state.run_phase = "running";
                state.last_finished_test = testName ?? "";
                state.last_progress_at_utc = UtcNow();
                switch ((testStatus ?? "").Trim().ToLowerInvariant())
                {
                    case "passed":
                        state.passed++;
                        break;
                    case "failed":
                        state.failed++;
                        state.failures.Add(new XUUnityLightMcpTestFailure
                        {
                            name = testName ?? "",
                            message = message ?? ""
                        });
                        break;
                    case "skipped":
                        state.skipped++;
                        break;
                }

                PersistLocked(state);
            }
        }

        public static XUUnityLightMcpResponse CompleteAndBuildResponse(
            string completionBasis,
            string playmodeStateAfterSettle,
            XUUnityLightMcpTestRunSummary finalSummary)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return XUUnityLightMcpResponseWriter.Error("", "missing_test_run_state", "Test run state was lost before completion.");
                }

                ApplyFinalSummaryLocked(state, finalSummary);
                state.completed_at_utc = UtcNow();
                state.run_phase = string.Equals(state.run_phase, "timed_out", StringComparison.Ordinal)
                    ? "settled_after_timeout"
                    : "completed";
                state.completion_basis = completionBasis ?? "";
                state.playmode_state_after_settle = playmodeStateAfterSettle ?? "";
                state.response_handoff_state = "pending_write";
                PersistLocked(state);
                return BuildResponseLocked(state);
            }
        }

        static void ApplyFinalSummaryLocked(XUUnityLightMcpPersistedTestRunState state, XUUnityLightMcpTestRunSummary summary)
        {
            if (state == null || summary == null)
            {
                return;
            }

            state.total = Math.Max(0, summary.total);
            state.passed = Math.Max(0, summary.passed);
            state.failed = Math.Max(0, summary.failed);
            state.skipped = Math.Max(0, summary.skipped);
            state.failures = summary.failures == null
                ? new System.Collections.Generic.List<XUUnityLightMcpTestFailure>()
                : new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(summary.failures);
        }

        public static bool TryWritePendingCompletedResponse()
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return false;
                }

                if (!string.Equals(state.response_handoff_state, "pending_write", StringComparison.Ordinal)
                    || string.IsNullOrWhiteSpace(state.completed_at_utc))
                {
                    return false;
                }

                try
                {
                    XUUnityLightMcpResponseWriter.Write(BuildResponseLocked(state));
                    state.response_handoff_state = "written";
                    state.run_phase = "response_written";
                    PersistResultLocked(state);
                    DeleteLocked();
                    return true;
                }
                catch
                {
                    return false;
                }
            }
        }

        public static void Clear()
        {
            lock (Gate)
            {
                DeleteLocked();
            }
        }

        public static void MarkResponseWrittenAndRelease()
        {
            lock (Gate)
            {
                if (TryLoadLocked(out var state))
                {
                    state.response_handoff_state = "written";
                    state.run_phase = "response_written";
                    PersistResultLocked(state);
                }

                DeleteLocked();
            }
        }

        public static void MarkAbandonedAndRelease(string timeoutClassification)
        {
            lock (Gate)
            {
                if (TryLoadLocked(out var state))
                {
                    state.run_phase = "abandoned";
                    state.timeout_classification = timeoutClassification ?? "";
                    state.response_handoff_state = "released";
                    PersistResultLocked(state);
                }

                DeleteLocked();
            }
        }

        static XUUnityLightMcpResponse BuildResponseLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            return new XUUnityLightMcpResponse
            {
                request_id = state.request_id ?? "",
                status = "ok",
                completed_at_utc = string.IsNullOrWhiteSpace(state.completed_at_utc) ? UtcNow() : state.completed_at_utc,
                payload_type = state.operation ?? "",
                payload_json = UnityEngine.JsonUtility.ToJson(BuildPayloadLocked(state)),
                error = null
            };
        }

        static XUUnityLightMcpTestsPayload BuildPayloadLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            return new XUUnityLightMcpTestsPayload
            {
                project_root = state.project_root ?? XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                status = ResolveStatus(state),
                total = Math.Max(0, state.total),
                passed = Math.Max(0, state.passed),
                failed = Math.Max(0, state.failed),
                skipped = Math.Max(0, state.skipped),
                duration_seconds = CalculateDurationSeconds(state.started_at_utc, state.completed_at_utc),
                failures = state.failures == null
                    ? new System.Collections.Generic.List<XUUnityLightMcpTestFailure>()
                    : new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(state.failures),
                started_at_utc = state.started_at_utc ?? "",
                completed_at_utc = state.completed_at_utc ?? "",
                completion_basis = state.completion_basis ?? "",
                playmode_state_after_settle = state.playmode_state_after_settle ?? "",
                run_phase = state.run_phase ?? "",
                last_progress_at_utc = state.last_progress_at_utc ?? "",
                timeout_classification = state.timeout_classification ?? "",
                runtime_timeout_ms = Math.Max(0, state.runtime_timeout_ms),
                last_started_test = state.last_started_test ?? "",
                last_finished_test = state.last_finished_test ?? "",
                lifecycle_churn_observed = state.lifecycle_churn_observed,
                validation_evidence = "unity_mcp"
            };
        }

        static string ResolveStatus(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null)
            {
                return "infrastructure_error";
            }

            return state.total <= 0
                ? "no_tests"
                : state.failed > 0
                    ? "failed"
                    : "passed";
        }

        static bool TryLoadLocked(out XUUnityLightMcpPersistedTestRunState state)
        {
            state = null;
            try
            {
                if (!File.Exists(XUUnityLightMcpFileIpcPaths.ActiveTestRunStatePath))
                {
                    return false;
                }

                state = UnityEngine.JsonUtility.FromJson<XUUnityLightMcpPersistedTestRunState>(
                    File.ReadAllText(XUUnityLightMcpFileIpcPaths.ActiveTestRunStatePath));
                NormalizeLoadedStateLocked(state);
                return state != null;
            }
            catch
            {
                state = null;
                return false;
            }
        }

        static bool ShouldDiscardStalePendingStateLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null
                || string.IsNullOrWhiteSpace(state.request_id)
                || string.Equals(state.response_handoff_state, "written", StringComparison.Ordinal))
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(state.completed_at_utc))
            {
                return true;
            }

            try
            {
                if (!Directory.Exists(XUUnityLightMcpFileIpcPaths.RequestJournalDirectory))
                {
                    return false;
                }

                foreach (var path in Directory.EnumerateFiles(XUUnityLightMcpFileIpcPaths.RequestJournalDirectory, "*.json").OrderByDescending(value => value))
                {
                    var payload = UnityEngine.JsonUtility.FromJson<XUUnityLightMcpRequestJournalEvent>(File.ReadAllText(path));
                    if (payload == null || !string.Equals(payload.request_id, state.request_id, StringComparison.Ordinal))
                    {
                        continue;
                    }

                    if (string.Equals(payload.event_type, "request_completed", StringComparison.Ordinal))
                    {
                        return true;
                    }

                    if (string.Equals(payload.event_type, "request_reclassified", StringComparison.Ordinal))
                    {
                        return true;
                    }

                    if (string.Equals(payload.event_type, "request_abandoned", StringComparison.Ordinal)
                        && !string.Equals(state.operation, PlayModeTestsOperationName, StringComparison.Ordinal))
                    {
                        return true;
                    }

                    if (string.Equals(payload.event_type, "request_abandoned", StringComparison.Ordinal)
                        && string.Equals(state.operation, PlayModeTestsOperationName, StringComparison.Ordinal))
                    {
                        return IsRecoveryDeadlineExpiredLocked(state);
                    }
                }
            }
            catch
            {
            }

            return IsRecoveryDeadlineExpiredLocked(state);
        }

        static bool IsRecoveryDeadlineExpiredLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null)
            {
                return false;
            }

            if (!DateTime.TryParse(
                    state.started_at_utc,
                    null,
                    System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                    out var started))
            {
                return false;
            }

            var timeoutMs = Math.Max(1000, state.request_timeout_ms);
            var deadlineUtc = started.ToUniversalTime().AddMilliseconds(timeoutMs);
            return DateTime.UtcNow >= deadlineUtc;
        }

        static void PersistLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            File.WriteAllText(
                XUUnityLightMcpFileIpcPaths.ActiveTestRunStatePath,
                UnityEngine.JsonUtility.ToJson(state, true));
            PersistResultLocked(state);
        }

        static void PersistResultLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null || string.IsNullOrWhiteSpace(state.request_id))
            {
                return;
            }

            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            File.WriteAllText(
                XUUnityLightMcpFileIpcPaths.TestRunResultPath(state.request_id),
                UnityEngine.JsonUtility.ToJson(state, true));
        }

        static void DeleteLocked()
        {
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.ActiveTestRunStatePath))
                {
                    File.Delete(XUUnityLightMcpFileIpcPaths.ActiveTestRunStatePath);
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
                    System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                    out var started))
            {
                return 0.0d;
            }

            if (!DateTime.TryParse(
                    completedAtUtc,
                    null,
                    System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                    out var completed))
            {
                completed = DateTime.UtcNow;
            }

            return Math.Round(Math.Max(0.0d, (completed - started).TotalSeconds), 6);
        }

        static string UtcNow()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        }

        static void NormalizeLoadedStateLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null)
            {
                return;
            }

            if (string.IsNullOrWhiteSpace(state.run_phase))
            {
                state.run_phase = string.IsNullOrWhiteSpace(state.completed_at_utc) ? "submitted" : "completed";
            }

            if (state.runtime_timeout_ms <= 0)
            {
                state.runtime_timeout_ms = Math.Max(1000, state.request_timeout_ms);
            }

            state.failures ??= new System.Collections.Generic.List<XUUnityLightMcpTestFailure>();
        }
    }

    internal sealed class XUUnityLightMcpTestRunSummary
    {
        public int total;
        public int passed;
        public int failed;
        public int skipped;
        public System.Collections.Generic.List<XUUnityLightMcpTestFailure> failures = new();
    }
}
