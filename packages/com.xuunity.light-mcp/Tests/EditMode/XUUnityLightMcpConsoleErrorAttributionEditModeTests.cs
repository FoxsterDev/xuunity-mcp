using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpConsoleErrorAttributionEditModeTests
    {
        const string ProbeMessage = "xuunity log-scope drift probe";
        const string IgnoredProbeMessage = "xuunity log-scope ignore-failing-messages probe";

        static XUUnityLightMcpTestLogRecord Record(string message, string activeTest, object scope, LogType type = LogType.Exception)
        {
            return new XUUnityLightMcpTestLogRecord
            {
                Type = type,
                Message = message,
                ActiveTest = activeTest,
                LoggedAtUtc = new DateTime(2026, 11, 3, 16, 0, 30, DateTimeKind.Utc),
                Scope = scope
            };
        }

        static Dictionary<object, List<KeyValuePair<LogType, string>>> Handled(object scope, params string[] messages)
        {
            var events = new List<KeyValuePair<LogType, string>>();
            foreach (var message in messages)
            {
                events.Add(new KeyValuePair<LogType, string>(LogType.Exception, message));
            }

            return new Dictionary<object, List<KeyValuePair<LogType, string>>> { { scope, events } };
        }

        static XUUnityLightMcpConsoleErrorAttribution Classify(
            IReadOnlyList<XUUnityLightMcpTestLogRecord> records,
            IDictionary<object, List<KeyValuePair<LogType, string>>> handled,
            bool passed,
            bool reflectionAvailable = true)
        {
            return XUUnityLightMcpTestLogAttribution.Classify(records, 0, handled, passed, reflectionAvailable, "req", "session-a");
        }

        static XUUnityLightMcpConsoleErrorSample Sample(string classification)
        {
            return new XUUnityLightMcpConsoleErrorSample { type = "exception", message = classification, classification = classification };
        }

        [Test]
        public void Classify_PassedTestWithHandledEvent_IsExpectedByTest()
        {
            var scope = new object();
            var attribution = Classify(new[] { Record("InvalidOperationException: init failed", "Suite.Case", scope) }, Handled(scope, "InvalidOperationException: init failed"), true);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(1));
            Assert.That(attribution.not_expected_count, Is.EqualTo(0));
            Assert.That(attribution.basis, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.BasisLogScope));
            Assert.That(attribution.samples.Count, Is.EqualTo(1));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("expected_by_test"));
            Assert.That(attribution.samples[0].type, Is.EqualTo("exception"));
            Assert.That(attribution.samples[0].active_test, Is.EqualTo("Suite.Case"));
            Assert.That(attribution.samples[0].logged_at_utc, Is.EqualTo("2026-11-03T16:00:30Z"));
            Assert.That(attribution.request_id, Is.EqualTo("req"));
            Assert.That(attribution.counter_session_id, Is.EqualTo("session-a"));
        }

        [Test]
        public void Classify_FailedTest_HandledEventStaysNotExpected()
        {
            var scope = new object();
            var attribution = Classify(new[] { Record("boom", "Suite.Case", scope) }, Handled(scope, "boom"), false);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(0));
            Assert.That(attribution.not_expected_count, Is.EqualTo(1));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unexpected"));
        }

        [Test]
        public void Classify_DuplicateMessages_OnlyHandledMultiplicityIsExpected()
        {
            var scope = new object();
            var records = new[] { Record("dup", "Suite.Case", scope), Record("dup", "Suite.Case", scope) };
            var attribution = Classify(records, Handled(scope, "dup"), true);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(1));
            Assert.That(attribution.not_expected_count, Is.EqualTo(1));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unexpected"));
            Assert.That(attribution.samples[1].classification, Is.EqualTo("expected_by_test"));
        }

        [Test]
        public void Classify_HandledEventsAreMatchedPerScope()
        {
            var expectingScope = new object();
            var ignoringScope = new object();
            var records = new[] { Record("same", "Suite.Case", ignoringScope), Record("same", "Suite.Case", expectingScope) };
            var attribution = Classify(records, Handled(expectingScope, "same"), true);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(1));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unclassified"));
        }

        [Test]
        public void Classify_ErrorLoggedWhileIgnoringFailingMessages_IsExpectedOnlyInAPassedTest()
        {
            var scope = new object();
            var ignored = Record("tolerated", "Suite.Case", scope);
            ignored.IgnoringFailingMessages = true;
            var records = new[] { ignored, Record("same", "Suite.Case", scope) };

            var passed = Classify(records, Handled(scope, "same"), true);
            Assert.That(passed.expected_by_test_count, Is.EqualTo(2));
            Assert.That(passed.not_expected_count, Is.EqualTo(0));
            Assert.That(passed.basis, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.BasisLogScope));

            var withoutHandledEvidence = Classify(new[] { ignored }, null, true, reflectionAvailable: false);
            Assert.That(withoutHandledEvidence.expected_by_test_count, Is.EqualTo(1));

            var failed = Classify(new[] { ignored }, Handled(scope), false);
            Assert.That(failed.expected_by_test_count, Is.EqualTo(0));
            Assert.That(failed.samples[0].classification, Is.EqualTo("unexpected"));
        }

        [Test]
        public void Classify_NoScopeEvidence_IsUnclassified()
        {
            var scope = new object();
            var withoutScope = Classify(new[] { Record("off-thread", "Suite.Case", null) }, Handled(scope, "off-thread"), true);
            var withoutReflection = Classify(new[] { Record("drifted", "Suite.Case", scope) }, Handled(scope, "drifted"), true, reflectionAvailable: false);

            foreach (var attribution in new[] { withoutScope, withoutReflection })
            {
                Assert.That(attribution.expected_by_test_count, Is.EqualTo(0));
                Assert.That(attribution.not_expected_count, Is.EqualTo(1));
                Assert.That(attribution.samples[0].classification, Is.EqualTo("unclassified"));
                Assert.That(attribution.basis, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable));
            }
        }

        [Test]
        public void Classify_OutsideLeafWindow_IsUnexpected()
        {
            var scope = new object();
            var attribution = Classify(new[] { Record("fixture", "", scope) }, Handled(scope, "fixture"), true);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(0));
            Assert.That(attribution.not_expected_count, Is.EqualTo(1));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unexpected"));
        }

        [Test]
        public void Classify_SamplesPreferNotExpectedErrorsAndAreBounded()
        {
            var scope = new object();
            var longMessage = new string('m', 1000);
            var records = new[]
            {
                Record("a", "Suite.Case", scope),
                Record("b", "Suite.Case", scope),
                Record("c", "Suite.Case", scope),
                Record(longMessage, new string('t', 500), scope)
            };
            var attribution = Classify(records, Handled(scope, "a", "b", "c"), true);

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(3));
            Assert.That(attribution.not_expected_count, Is.EqualTo(1));
            Assert.That(attribution.samples.Count, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.MaxSamples));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unexpected"));
            Assert.That(attribution.samples[0].message.Length, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.MaxSampleMessageChars + 3));
            Assert.That(attribution.samples[0].message, Does.EndWith("..."));
            Assert.That(attribution.samples[0].active_test.Length, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.MaxSampleActiveTestChars + 3));
        }

        [Test]
        public void ClassifyOutsideWindow_CountsInterruptedTestsAsUnclassifiedAndOverflowAsNotExpected()
        {
            var records = new[] { Record("pre-reload", "", null), Record("mid-test", "Suite.Case", new object()) };
            var attribution = XUUnityLightMcpTestLogAttribution.ClassifyOutsideWindow(records, 2, "req", "session-a");

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(0));
            Assert.That(attribution.not_expected_count, Is.EqualTo(4));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("unexpected"));
            Assert.That(attribution.samples[1].classification, Is.EqualTo("unclassified"));
            Assert.That(XUUnityLightMcpTestLogAttribution.ClassifyOutsideWindow(null, 0, "req", "session-a"), Is.Null);
        }

        [Test]
        public void Window_ClaimFromBeginClearsStateLeftByAnEarlierRun()
        {
            var window = new XUUnityLightMcpTestLogWindow();
            window.Claim("req-a", true);
            window.Take("Suite.Hung", out _, out _);
            window.Append(LogType.Error, "stale", new object(), DateTime.UtcNow);

            window.Claim("req-a", false);
            Assert.That(window.PendingCount, Is.EqualTo(1), "a same-request restore keeps the pending window");

            window.Claim("req-b", true);
            Assert.That(window.PendingCount, Is.EqualTo(0));
            Assert.That(window.ActiveTest, Is.Empty);
            Assert.That(window.OwnerRequestId, Is.EqualTo("req-b"));
            Assert.That(window.Take("Suite.Next", out var overflow, out var owner), Is.Null);
            Assert.That(overflow, Is.EqualTo(0));
            Assert.That(owner, Is.EqualTo("req-b"));
        }

        [Test]
        public void Window_ReleaseClearsStateOnlyForItsOwner()
        {
            var window = new XUUnityLightMcpTestLogWindow();
            window.Claim("req-a", true);
            window.Append(LogType.Error, "pending", null, DateTime.UtcNow);

            Assert.That(window.Release("req-other"), Is.False);
            Assert.That(window.Release(""), Is.False);
            Assert.That(window.PendingCount, Is.EqualTo(1));

            Assert.That(window.Release("req-a"), Is.True);
            Assert.That(window.PendingCount, Is.EqualTo(0));
            Assert.That(window.OwnerRequestId, Is.Empty);
        }

        [Test]
        public void Window_TakeFinishedAdoptsRecordsLoggedAfterARestoreIntoTheFinishingTest()
        {
            var window = new XUUnityLightMcpTestLogWindow();
            window.Claim("req-a", true);
            var scope = new object();
            window.Append(LogType.Error, "resumed", scope, DateTime.UtcNow);

            var records = window.TakeFinished("Suite.Resumed", out var overflow, out var owner);

            Assert.That(records.Count, Is.EqualTo(1));
            Assert.That(records[0].ActiveTest, Is.EqualTo("Suite.Resumed"));
            Assert.That(overflow, Is.EqualTo(0));
            Assert.That(owner, Is.EqualTo("req-a"));
            Assert.That(window.ActiveTest, Is.Empty);

            var handled = new Dictionary<object, List<KeyValuePair<LogType, string>>>
            {
                { scope, new List<KeyValuePair<LogType, string>> { new KeyValuePair<LogType, string>(LogType.Error, "resumed") } }
            };
            var attribution = Classify(records, handled, true);
            Assert.That(attribution.expected_by_test_count, Is.EqualTo(1));
            Assert.That(attribution.not_expected_count, Is.EqualTo(0));
            Assert.That(attribution.samples[0].active_test, Is.EqualTo("Suite.Resumed"));

            window.Take("Suite.Running", out _, out _);
            window.Append(LogType.Error, "own", null, DateTime.UtcNow);
            Assert.That(window.TakeFinished("Suite.Other", out _, out _)[0].ActiveTest, Is.EqualTo("Suite.Running"));
        }

        [Test]
        public void Window_OverflowIsCountedNotStored()
        {
            var window = new XUUnityLightMcpTestLogWindow();
            window.Claim("req-a", true);
            for (var index = 0; index < XUUnityLightMcpTestLogWindow.MaxPendingRecords + 2; index++)
            {
                window.Append(LogType.Error, "spam", null, DateTime.UtcNow);
            }

            var records = window.Take("", out var overflow, out _);
            Assert.That(records.Count, Is.EqualTo(XUUnityLightMcpTestLogWindow.MaxPendingRecords));
            Assert.That(overflow, Is.EqualTo(2));
            Assert.That(window.PendingCount, Is.EqualTo(0));
        }

        [Test]
        public void Merge_NonExpectedDisplacesTheNewestExpectedSample()
        {
            var state = new XUUnityLightMcpPersistedTestRunState { request_id = "req" };
            var attribution = new XUUnityLightMcpConsoleErrorAttribution { request_id = "req", counter_session_id = "s", expected_by_test_count = 3 };
            attribution.samples.Add(Sample("expected_by_test"));
            attribution.samples.Add(Sample("expected_by_test"));
            attribution.samples.Add(Sample("expected_by_test"));
            XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, attribution);

            var unexpected = new XUUnityLightMcpConsoleErrorAttribution { request_id = "req", counter_session_id = "s", not_expected_count = 1 };
            unexpected.samples.Add(Sample("unexpected"));
            XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, unexpected);

            var expectedOverflow = new XUUnityLightMcpConsoleErrorAttribution { request_id = "req", counter_session_id = "s", expected_by_test_count = 1 };
            expectedOverflow.samples.Add(Sample("expected_by_test"));
            XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, expectedOverflow);

            Assert.That(state.console_error_samples.Count, Is.EqualTo(3));
            Assert.That(state.console_error_samples.FindAll(sample => sample.classification == "expected_by_test").Count, Is.EqualTo(2));
            Assert.That(state.console_error_samples[2].classification, Is.EqualTo("unexpected"));
            Assert.That(state.console_error_expected_by_test_count, Is.EqualTo(4));
            Assert.That(state.console_error_not_expected_recorded_count, Is.EqualTo(1));
        }

        [Test]
        public void Merge_ResetsTheInSessionCounterOnANewSessionAndKeepsUnavailableBasisSticky()
        {
            var state = new XUUnityLightMcpPersistedTestRunState { request_id = "req", console_error_classification_basis = "none" };
            XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, new XUUnityLightMcpConsoleErrorAttribution
            {
                request_id = "req", counter_session_id = "session-a", expected_by_test_count = 2, basis = XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable
            });
            XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, new XUUnityLightMcpConsoleErrorAttribution
            {
                request_id = "req", counter_session_id = "session-b", expected_by_test_count = 1, basis = XUUnityLightMcpConsoleErrorClassification.BasisLogScope
            });

            Assert.That(state.console_error_expected_by_test_count, Is.EqualTo(3));
            Assert.That(state.console_error_expected_by_test_count_in_session, Is.EqualTo(1));
            Assert.That(state.console_error_expected_by_test_counter_session_id, Is.EqualTo("session-b"));
            Assert.That(state.console_error_classification_basis, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable));
        }

        [Test]
        public void Merge_IgnoresAnotherRequestsAttribution()
        {
            var state = new XUUnityLightMcpPersistedTestRunState { request_id = "req-current" };
            var merged = XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, new XUUnityLightMcpConsoleErrorAttribution
            {
                request_id = "req-stale", counter_session_id = "s", not_expected_count = 1
            });

            Assert.That(merged, Is.False);
            Assert.That(state.console_error_not_expected_recorded_count, Is.EqualTo(0));
        }

        [Test]
        public void ResolveNotExpected_SubtractsExpectedErrorsOnlyInTheirOwnCounterSession()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                console_error_expected_by_test_count_in_session = 1,
                console_error_expected_by_test_counter_session_id = "session-b"
            };

            Assert.That(XUUnityLightMcpTestRunState.ResolveNotExpectedConsoleErrorCount(state, 1, "session-b"), Is.EqualTo(0));
            Assert.That(XUUnityLightMcpTestRunState.ResolveNotExpectedConsoleErrorCount(state, 1, "session-c"), Is.EqualTo(1));
        }

        [Test]
        public void ResolveNotExpected_RecordedFloorSurvivesALaterDomain()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                console_error_expected_by_test_count_in_session = 1,
                console_error_expected_by_test_counter_session_id = "play-domain",
                console_error_not_expected_recorded_count = 1
            };

            Assert.That(XUUnityLightMcpTestRunState.ResolveNotExpectedConsoleErrorCount(state, 0, "post-exit-domain"), Is.EqualTo(1));
            Assert.That(XUUnityLightMcpTestRunState.ResolveNotExpectedConsoleErrorCount(state, 2, "play-domain"), Is.EqualTo(1));
        }

        [Test]
        public void BuildPayloadForState_KeepsPressureForUnclassifiedErrorsAfterADomainReload()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                request_id = "req",
                total = 1,
                passed = 1,
                console_error_counter_session_id_at_request_start = "previous-domain",
                console_error_classification_basis = XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable,
                console_error_not_expected_recorded_count = 1
            };
            state.console_error_samples.Add(Sample("unclassified"));

            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(state);

            Assert.That(payload.console_error_pressure_detected, Is.True);
            Assert.That(payload.console_error_not_expected_count, Is.GreaterThanOrEqualTo(1));
            Assert.That(payload.console_error_classification_basis, Is.EqualTo("utf_log_scope_unavailable"));
            Assert.That(payload.console_error_samples.Count, Is.EqualTo(1));
            Assert.That(payload.console_error_count_trust_class, Is.EqualTo("lower_bound_after_domain_reload"));
        }

        [Test]
        public void CompletedRun_ReportsTheCountsFrozenAtCompletionNotTheLiveCounter()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                request_id = "req",
                total = 1,
                passed = 1,
                console_error_count_at_request_start = 0,
                console_error_counter_session_id_at_request_start = "edit-domain",
                console_error_expected_by_test_count = 1,
                console_error_expected_by_test_count_in_session = 1,
                console_error_expected_by_test_counter_session_id = "play-domain",
                console_error_classification_basis = XUUnityLightMcpConsoleErrorClassification.BasisLogScope
            };

            XUUnityLightMcpTestRunState.ResolveConsoleErrorOutcome(state, 1, "later-domain", out _, out _, out var liveNotExpected);
            Assert.That(liveNotExpected, Is.EqualTo(1), "an unfrozen state still resolves against the live counter");

            XUUnityLightMcpTestRunState.FreezeConsoleErrorOutcome(state, 1, "play-domain");
            Assert.That(state.console_error_count_at_completion, Is.EqualTo(1));
            Assert.That(state.console_error_count_trust_class_at_completion, Is.EqualTo("lower_bound_after_domain_reload"));
            Assert.That(state.console_error_not_expected_count_at_completion, Is.EqualTo(0));

            XUUnityLightMcpTestRunState.ResolveConsoleErrorOutcome(state, 7, "later-domain", out var count, out var trustClass, out var notExpected);
            Assert.That(count, Is.EqualTo(1));
            Assert.That(trustClass, Is.EqualTo("lower_bound_after_domain_reload"));
            Assert.That(notExpected, Is.EqualTo(0));

            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(state);
            Assert.That(payload.console_error_pressure_detected, Is.False);
            Assert.That(payload.console_error_not_expected_count, Is.EqualTo(0));
            Assert.That(payload.console_error_count_since_request_start, Is.EqualTo(1));

            var persisted = JsonUtility.FromJson<XUUnityLightMcpPersistedTestRunState>(JsonUtility.ToJson(state));
            Assert.That(persisted.console_error_count_trust_class_at_completion, Is.EqualTo("lower_bound_after_domain_reload"));

            state.console_error_not_expected_recorded_count = 2;
            XUUnityLightMcpTestRunState.ResolveConsoleErrorOutcome(state, 0, "later-domain", out _, out _, out var floored);
            Assert.That(floored, Is.EqualTo(2));
        }

        [Test]
        public void LogScopeReflection_ErrorLoggedWhileTheScopeIgnoresFailingMessagesIsExpectedByTest()
        {
            Assert.IsTrue(
                XUUnityLightMcpTestLogAttribution.ReflectionAvailable,
                "UTF LogScope/LogEvent members changed; console error classification degrades to unclassified.");
            Assert.IsTrue(
                XUUnityLightMcpTestLogAttribution.IgnoreFailingMessagesReflectionAvailable,
                "UTF LogScope.IgnoreFailingMessages changed; errors a test tolerates with LogAssert.ignoreFailingMessages count as pressure.");
            var scopeType = typeof(LogAssert).Assembly.GetType("UnityEngine.TestTools.Logging.LogScope");
            var window = new XUUnityLightMcpTestLogWindow();
            window.Claim("req", true);
            window.Take("Suite.Tolerant", out _, out _);
            Application.LogCallback capture = (condition, _, type) => XUUnityLightMcpTestLogAttribution.AppendLog(window, condition, type, true);

            var scope = Activator.CreateInstance(scopeType, true);
            Application.logMessageReceivedThreaded += capture;
            try
            {
                LogAssert.ignoreFailingMessages = true;
                Debug.LogError(IgnoredProbeMessage);
            }
            finally
            {
                Application.logMessageReceivedThreaded -= capture;
                LogAssert.ignoreFailingMessages = false;
                ((IDisposable)scope).Dispose();
            }

            LogAssert.Expect(LogType.Error, IgnoredProbeMessage);
            var attribution = XUUnityLightMcpTestLogAttribution.FinishTest(window, "Suite.Tolerant", true, "session-a");

            Assert.That(attribution.expected_by_test_count, Is.EqualTo(1));
            Assert.That(attribution.not_expected_count, Is.EqualTo(0));
            Assert.That(attribution.basis, Is.EqualTo(XUUnityLightMcpConsoleErrorClassification.BasisLogScope));
            Assert.That(attribution.samples[0].classification, Is.EqualTo("expected_by_test"));
            Assert.That(attribution.samples[0].message, Is.EqualTo(IgnoredProbeMessage));

            var state = new XUUnityLightMcpPersistedTestRunState
            {
                request_id = "req",
                total = 1,
                passed = 1,
                console_error_counter_session_id_at_request_start = "session-a"
            };
            Assert.That(XUUnityLightMcpTestRunState.MergeConsoleErrorAttribution(state, attribution), Is.True);
            XUUnityLightMcpTestRunState.FreezeConsoleErrorOutcome(state, 1, "session-a");
            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(state);
            Assert.That(payload.console_error_pressure_detected, Is.False);
            Assert.That(payload.console_error_expected_by_test_count, Is.EqualTo(1));
            Assert.That(payload.console_error_not_expected_count, Is.EqualTo(0));
        }

        [Test]
        public void LogScopeReflection_ReadsHandledFlagFromARealUtfScope()
        {
            Assert.IsTrue(
                XUUnityLightMcpTestLogAttribution.ReflectionAvailable,
                "UTF LogScope/LogEvent members changed; console error classification degrades to unclassified.");
            var scopeType = typeof(LogAssert).Assembly.GetType("UnityEngine.TestTools.Logging.LogScope");
            var evaluate = scopeType.GetMethod("EvaluateLogScope", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(evaluate);

            var scope = Activator.CreateInstance(scopeType, true);
            try
            {
                LogAssert.Expect(LogType.Error, ProbeMessage);
                Debug.LogError(ProbeMessage);
                evaluate.Invoke(scope, new object[] { true });
            }
            finally
            {
                ((IDisposable)scope).Dispose();
            }

            LogAssert.Expect(LogType.Error, ProbeMessage);
            Assert.IsTrue(XUUnityLightMcpTestLogAttribution.TryReadHandledFailingEvents(scope, out var handled));
            Assert.That(handled.Count, Is.EqualTo(1));
            Assert.That(handled[0].Key, Is.EqualTo(LogType.Error));
            Assert.That(handled[0].Value, Is.EqualTo(ProbeMessage));
        }
    }
}
