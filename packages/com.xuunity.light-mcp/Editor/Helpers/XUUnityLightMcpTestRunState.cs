using System;
using System.Globalization;
using System.IO;
using System.Linq;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpTestRunState
    {
        const string PlayModeTestsOperationName = "unity.tests.run_playmode";
        static readonly object Gate = new();

        public static XUUnityLightMcpPersistedTestRunState Begin(
            string requestId,
            string operation,
            string testMode,
            string filterSummary,
            bool filterRequested,
            int requestTimeoutMs)
        {
            var environment = XUUnityLightMcpGameViewUtility.CaptureTestEnvironment();
            lock (Gate)
            {
                XUUnityLightMcpFileIpcPaths.EnsureDirectories();
                XUUnityLightMcpConsoleBuffer.EnsureStarted();
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
                    filter_requested = filterRequested,
                    response_handoff_state = "pending",
                    console_error_count_at_request_start = XUUnityLightMcpConsoleBuffer.ErrorCount,
                    console_error_counter_session_id_at_request_start = XUUnityLightMcpConsoleBuffer.CounterSessionId,
                    console_error_classification_basis = XUUnityLightMcpConsoleErrorClassification.BasisNone,
                    failures = new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(),
                    test_environment = environment,
                };

                PersistLocked(state);
                return state;
            }
        }

        public static void RecordRunGuid(string runGuid)
        {
            lock (Gate)
            {
                if (TryLoadLocked(out var state))
                {
                    state.run_guid = runGuid ?? "";
                    PersistLocked(state);
                }
            }
        }

        public static XUUnityLightMcpTestRunSummary SummaryFromActiveState()
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return new XUUnityLightMcpTestRunSummary();
                }

                return new XUUnityLightMcpTestRunSummary
                {
                    total = Math.Max(0, state.total),
                    passed = Math.Max(0, state.passed),
                    failed = Math.Max(0, state.failed),
                    skipped = Math.Max(0, state.skipped),
                    failures = state.failures == null
                        ? new System.Collections.Generic.List<XUUnityLightMcpTestFailure>()
                        : new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(state.failures),
                };
            }
        }

        public static bool TryMarkCancelRequested(string requestId, out XUUnityLightMcpPersistedTestRunState state)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out state)
                    || !string.IsNullOrWhiteSpace(state.completed_at_utc)
                    || (!string.IsNullOrWhiteSpace(requestId)
                        && !string.Equals(state.request_id, requestId, StringComparison.Ordinal)))
                {
                    return false;
                }

                if (string.IsNullOrWhiteSpace(state.cancel_requested_at_utc))
                {
                    state.cancel_requested_at_utc = UtcNow();
                    PersistLocked(state);
                }

                return true;
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

        public static bool WillResumeAfterDomainReload(string requestId, string operation)
        {
            if (string.IsNullOrWhiteSpace(requestId)
                || !string.Equals(operation, PlayModeTestsOperationName, StringComparison.Ordinal))
            {
                return false;
            }

            lock (Gate)
            {
                return TryLoadLocked(out var state) && IsResumablePlayModeRun(state, requestId);
            }
        }

        internal static bool IsResumablePlayModeRun(XUUnityLightMcpPersistedTestRunState state, string requestId)
        {
            return state != null
                   && !string.IsNullOrWhiteSpace(requestId)
                   && string.Equals(state.request_id, requestId, StringComparison.Ordinal)
                   && string.Equals(state.operation, PlayModeTestsOperationName, StringComparison.Ordinal)
                   && string.Equals(state.response_handoff_state, "pending", StringComparison.Ordinal)
                   && string.IsNullOrWhiteSpace(state.completed_at_utc);
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

        public static void RecordTestStarted(string testName, XUUnityLightMcpConsoleErrorAttribution attribution = null)
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
                MergeConsoleErrorAttribution(state, attribution);
                PersistLocked(state);
            }
        }

        public static void RecordTestFinished(
            string testStatus,
            string testName,
            string message,
            XUUnityLightMcpConsoleErrorAttribution attribution = null)
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

                MergeConsoleErrorAttribution(state, attribution);
                PersistLocked(state);
            }
        }

        public static void RecordConsoleErrorAttribution(XUUnityLightMcpConsoleErrorAttribution attribution)
        {
            if (attribution == null || attribution.IsEmpty)
            {
                return;
            }

            lock (Gate)
            {
                if (!TryLoadLocked(out var state)
                    || !string.IsNullOrWhiteSpace(state.completed_at_utc)
                    || !MergeConsoleErrorAttribution(state, attribution))
                {
                    return;
                }

                PersistLocked(state);
            }
        }

        public static XUUnityLightMcpResponse CompleteAndBuildResponse(
            string completionBasis,
            string playmodeStateAfterSettle,
            XUUnityLightMcpTestRunSummary finalSummary,
            XUUnityLightMcpConsoleErrorAttribution attribution = null)
        {
            lock (Gate)
            {
                if (!TryLoadLocked(out var state))
                {
                    return XUUnityLightMcpResponseWriter.Error("", "missing_test_run_state", "Test run state was lost before completion.");
                }

                MergeConsoleErrorAttribution(state, attribution);
                ApplyFinalSummaryLocked(state, finalSummary);
                FreezeConsoleErrorOutcome(state, XUUnityLightMcpConsoleBuffer.ErrorCount, XUUnityLightMcpConsoleBuffer.CounterSessionId);
                state.completed_at_utc = UtcNow();
                state.run_phase = string.Equals(state.run_phase, "timed_out", StringComparison.Ordinal)
                    ? "settled_after_timeout"
                    : "completed";
                if (string.IsNullOrWhiteSpace(state.timeout_classification)
                    && ExceededRuntimeBudget(state.started_at_utc, state.completed_at_utc, state.runtime_timeout_ms))
                {
                    state.timeout_classification = CompletedAfterRuntimeBudget;
                }
                state.completion_basis = completionBasis ?? "";
                state.playmode_state_after_test_callbacks = playmodeStateAfterSettle ?? "";
                state.playmode_state_after_host_settle = "";
                state.playmode_state_after_settle = state.playmode_state_after_test_callbacks;
                state.playmode_state_after_settle_source = "unity_test_callbacks";
                state.playmode_state_accounting_consistent = true;
                state.playmode_state_accounting_note = "";
                state.cancelled = !string.IsNullOrWhiteSpace(state.cancel_requested_at_utc);
                state.status = ResolveStatus(state);
                state.test_verdict = state.status;
                state.recommended_next_action = ResolveRecommendedNextAction(state);
                state.recommended_recovery_command = ResolveRecommendedRecoveryCommand(state);
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

        internal static XUUnityLightMcpTestsPayload BuildPayloadForState(XUUnityLightMcpPersistedTestRunState state)
        {
            return BuildPayloadLocked(state);
        }

        static XUUnityLightMcpTestsPayload BuildPayloadLocked(XUUnityLightMcpPersistedTestRunState state)
        {
            ResolveConsoleErrorOutcome(
                state,
                XUUnityLightMcpConsoleBuffer.ErrorCount,
                XUUnityLightMcpConsoleBuffer.CounterSessionId,
                out var consoleErrorCount,
                out var consoleTrustClass,
                out var notExpectedCount);
            return new XUUnityLightMcpTestsPayload
            {
                project_root = state.project_root ?? XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                status = string.IsNullOrWhiteSpace(state.status) ? ResolveStatus(state) : state.status,
                total = Math.Max(0, state.total),
                passed = Math.Max(0, state.passed),
                failed = Math.Max(0, state.failed),
                skipped = Math.Max(0, state.skipped),
                not_run = Math.Max(0, state.total - state.passed - state.failed - state.skipped),
                cancelled = state.cancelled,
                cancel_requested_at_utc = state.cancel_requested_at_utc ?? "",
                duration_seconds = CalculateDurationSeconds(state.started_at_utc, state.completed_at_utc),
                failures = state.failures == null
                    ? new System.Collections.Generic.List<XUUnityLightMcpTestFailure>()
                    : new System.Collections.Generic.List<XUUnityLightMcpTestFailure>(state.failures),
                started_at_utc = state.started_at_utc ?? "",
                completed_at_utc = state.completed_at_utc ?? "",
                completion_basis = state.completion_basis ?? "",
                playmode_state_after_settle = state.playmode_state_after_settle ?? "",
                playmode_state_after_test_callbacks = state.playmode_state_after_test_callbacks ?? "",
                playmode_state_after_host_settle = state.playmode_state_after_host_settle ?? "",
                playmode_state_after_settle_source = state.playmode_state_after_settle_source ?? "",
                playmode_state_accounting_consistent = state.playmode_state_accounting_consistent,
                playmode_state_accounting_note = state.playmode_state_accounting_note ?? "",
                run_phase = state.run_phase ?? "",
                last_progress_at_utc = state.last_progress_at_utc ?? "",
                timeout_classification = state.timeout_classification ?? "",
                runtime_timeout_ms = Math.Max(0, state.runtime_timeout_ms),
                filter_summary = state.filter_summary ?? "",
                filter_requested = state.filter_requested,
                test_verdict = string.IsNullOrWhiteSpace(state.test_verdict) ? ResolveStatus(state) : state.test_verdict,
                recommended_next_action = string.IsNullOrWhiteSpace(state.recommended_next_action)
                    ? ResolveRecommendedNextAction(state)
                    : state.recommended_next_action,
                recommended_recovery_command = string.IsNullOrWhiteSpace(state.recommended_recovery_command)
                    ? ResolveRecommendedRecoveryCommand(state)
                    : state.recommended_recovery_command,
                last_started_test = state.last_started_test ?? "",
                last_finished_test = state.last_finished_test ?? "",
                lifecycle_churn_observed = state.lifecycle_churn_observed,
                console_error_count_since_request_start = consoleErrorCount,
                console_error_count_trust_class = consoleTrustClass,
                console_error_pressure_detected = notExpectedCount > 0,
                console_error_expected_by_test_count = Math.Max(0L, state.console_error_expected_by_test_count),
                console_error_not_expected_count = notExpectedCount,
                console_error_classification_basis = state.console_error_classification_basis ?? "",
                console_error_samples = state.console_error_samples == null
                    ? new System.Collections.Generic.List<XUUnityLightMcpConsoleErrorSample>()
                    : new System.Collections.Generic.List<XUUnityLightMcpConsoleErrorSample>(state.console_error_samples),
                test_environment = state.test_environment ?? new XUUnityLightMcpTestEnvironment(),
                validation_evidence = "unity_mcp"
            };
        }

        internal static void FreezeConsoleErrorOutcome(
            XUUnityLightMcpPersistedTestRunState state,
            long currentCount,
            string currentSessionId)
        {
            if (state == null)
            {
                return;
            }

            ResolveConsoleErrorPressure(state, currentCount, currentSessionId, out var count, out var trustClass);
            state.console_error_count_at_completion = count;
            state.console_error_count_trust_class_at_completion = trustClass ?? "";
            state.console_error_not_expected_count_at_completion = ResolveNotExpectedConsoleErrorCount(state, count, currentSessionId);
        }

        internal static void ResolveConsoleErrorOutcome(
            XUUnityLightMcpPersistedTestRunState state,
            long currentCount,
            string currentSessionId,
            out long count,
            out string trustClass,
            out long notExpectedCount)
        {
            if (state != null && !string.IsNullOrEmpty(state.console_error_count_trust_class_at_completion))
            {
                count = Math.Max(0L, state.console_error_count_at_completion);
                trustClass = state.console_error_count_trust_class_at_completion;
                notExpectedCount = Math.Max(
                    Math.Max(0L, state.console_error_not_expected_count_at_completion),
                    Math.Max(0L, state.console_error_not_expected_recorded_count));
                return;
            }

            ResolveConsoleErrorPressure(state, currentCount, currentSessionId, out count, out trustClass);
            notExpectedCount = ResolveNotExpectedConsoleErrorCount(state, count, currentSessionId);
        }

        internal static void ResolveConsoleErrorPressure(
            XUUnityLightMcpPersistedTestRunState state,
            out long count,
            out string trustClass)
        {
            ResolveConsoleErrorPressure(
                state,
                XUUnityLightMcpConsoleBuffer.ErrorCount,
                XUUnityLightMcpConsoleBuffer.CounterSessionId,
                out count,
                out trustClass);
        }

        internal static void ResolveConsoleErrorPressure(
            XUUnityLightMcpPersistedTestRunState state,
            long currentCount,
            string currentSessionId,
            out long count,
            out string trustClass)
        {
            count = 0;
            trustClass = "unavailable";
            if (state == null)
            {
                return;
            }

            currentCount = Math.Max(0L, currentCount);
            if (string.Equals(
                    state.console_error_counter_session_id_at_request_start,
                    currentSessionId,
                    StringComparison.Ordinal))
            {
                count = Math.Max(0L, currentCount - state.console_error_count_at_request_start);
                trustClass = "complete_since_request_start";
                return;
            }

            count = currentCount;
            trustClass = string.IsNullOrEmpty(state.console_error_counter_session_id_at_request_start)
                ? "lower_bound_without_request_baseline"
                : "lower_bound_after_domain_reload";
        }

        internal static long ResolveNotExpectedConsoleErrorCount(
            XUUnityLightMcpPersistedTestRunState state,
            long rawCount,
            string currentSessionId)
        {
            if (state == null)
            {
                return Math.Max(0L, rawCount);
            }

            var expectedInSession = !string.IsNullOrEmpty(state.console_error_expected_by_test_counter_session_id)
                                    && string.Equals(
                                        state.console_error_expected_by_test_counter_session_id,
                                        currentSessionId,
                                        StringComparison.Ordinal)
                ? Math.Max(0L, state.console_error_expected_by_test_count_in_session)
                : 0L;
            return Math.Max(
                Math.Max(0L, rawCount - expectedInSession),
                Math.Max(0L, state.console_error_not_expected_recorded_count));
        }

        internal static bool MergeConsoleErrorAttribution(
            XUUnityLightMcpPersistedTestRunState state,
            XUUnityLightMcpConsoleErrorAttribution attribution)
        {
            if (state == null || attribution == null || attribution.IsEmpty)
            {
                return false;
            }

            if (!string.IsNullOrEmpty(attribution.request_id)
                && !string.Equals(attribution.request_id, state.request_id ?? "", StringComparison.Ordinal))
            {
                return false;
            }

            state.console_error_samples ??= new System.Collections.Generic.List<XUUnityLightMcpConsoleErrorSample>();
            foreach (var sample in attribution.samples)
            {
                AddConsoleErrorSample(state.console_error_samples, sample);
            }

            var expected = Math.Max(0L, attribution.expected_by_test_count);
            state.console_error_expected_by_test_count += expected;
            var sessionId = attribution.counter_session_id ?? "";
            if (!string.Equals(state.console_error_expected_by_test_counter_session_id ?? "", sessionId, StringComparison.Ordinal))
            {
                state.console_error_expected_by_test_counter_session_id = sessionId;
                state.console_error_expected_by_test_count_in_session = 0L;
            }

            state.console_error_expected_by_test_count_in_session += expected;
            state.console_error_not_expected_recorded_count += Math.Max(0L, attribution.not_expected_count);
            state.console_error_classification_basis = MergeClassificationBasis(
                state.console_error_classification_basis,
                attribution.basis);
            return true;
        }

        static void AddConsoleErrorSample(
            System.Collections.Generic.List<XUUnityLightMcpConsoleErrorSample> samples,
            XUUnityLightMcpConsoleErrorSample sample)
        {
            if (sample == null)
            {
                return;
            }

            if (samples.Count < XUUnityLightMcpConsoleErrorClassification.MaxSamples)
            {
                samples.Add(sample);
                return;
            }

            if (IsExpectedSample(sample))
            {
                return;
            }

            for (var index = samples.Count - 1; index >= 0; index--)
            {
                if (IsExpectedSample(samples[index]))
                {
                    samples.RemoveAt(index);
                    samples.Add(sample);
                    return;
                }
            }
        }

        static bool IsExpectedSample(XUUnityLightMcpConsoleErrorSample sample)
        {
            return sample != null
                   && string.Equals(
                       sample.classification,
                       XUUnityLightMcpConsoleErrorClassification.ExpectedByTest,
                       StringComparison.Ordinal);
        }

        static string MergeClassificationBasis(string current, string incoming)
        {
            return ClassificationBasisRank(incoming) > ClassificationBasisRank(current) ? incoming : current ?? "";
        }

        static int ClassificationBasisRank(string basis)
        {
            switch (basis ?? "")
            {
                case XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable:
                    return 3;
                case XUUnityLightMcpConsoleErrorClassification.BasisLogScope:
                    return 2;
                case XUUnityLightMcpConsoleErrorClassification.BasisNone:
                    return 1;
                default:
                    return 0;
            }
        }

        static string ResolveStatus(XUUnityLightMcpPersistedTestRunState state)
        {
            if (state == null)
            {
                return "infrastructure_error";
            }

            if (state.cancelled)
            {
                return "cancelled";
            }

            return IsRequestedFilterZeroMatch(state)
                ? "test_filter_no_match"
                : state.total <= 0
                    ? "no_tests"
                    : state.failed > 0
                        ? "failed"
                        : "passed";
        }

        static bool IsRequestedFilterZeroMatch(XUUnityLightMcpPersistedTestRunState state)
        {
            return state != null && state.filter_requested && state.total <= 0;
        }

        static string ResolveRecommendedNextAction(XUUnityLightMcpPersistedTestRunState state)
        {
            return IsRequestedFilterZeroMatch(state)
                ? "refresh_project_once_then_retry_same_filter"
                : "none";
        }

        static string ResolveRecommendedRecoveryCommand(XUUnityLightMcpPersistedTestRunState state)
        {
            if (!IsRequestedFilterZeroMatch(state))
            {
                return "";
            }

            var projectRoot = state.project_root ?? XUUnityLightMcpFileIpcPaths.ProjectRootPath;
            return $"request-project-refresh --project-root \"{projectRoot}\" --timeout-ms 180000";
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

        internal const string CompletedAfterRuntimeBudget = "completed_after_runtime_budget";

        internal static bool ExceededRuntimeBudget(string startedAtUtc, string completedAtUtc, int runtimeTimeoutMs)
        {
            if (runtimeTimeoutMs <= 0
                || !DateTime.TryParse(startedAtUtc, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var started)
                || !DateTime.TryParse(completedAtUtc, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var completed))
            {
                return false;
            }

            return (completed - started).TotalMilliseconds > runtimeTimeoutMs;
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
            XUUnityLightMcpAtomicFileWriter.WriteAllText(
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
            XUUnityLightMcpAtomicFileWriter.WriteAllText(
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
            state.test_environment ??= new XUUnityLightMcpTestEnvironment();
            state.console_error_samples ??= new System.Collections.Generic.List<XUUnityLightMcpConsoleErrorSample>();
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
