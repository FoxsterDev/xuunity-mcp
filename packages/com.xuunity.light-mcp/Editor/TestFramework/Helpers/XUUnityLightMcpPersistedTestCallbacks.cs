using System;
using System.Linq;
using UnityEditor.TestTools.TestRunner.Api;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpPersistedTestCallbacks : ICallbacks
    {
        readonly string _operationName;
        readonly string _testMode;
        readonly Action<XUUnityLightMcpResponse> _onCompleted;

        bool _active;
        string _startedAtUtc = "";
        string _requestId = "";

        public bool IsActive => _active;
        public string StartedAtUtc => _startedAtUtc ?? "";

        public XUUnityLightMcpPersistedTestCallbacks(string operationName, string testMode, Action<XUUnityLightMcpResponse> onCompleted)
        {
            _operationName = operationName ?? throw new ArgumentNullException(nameof(operationName));
            _testMode = testMode ?? throw new ArgumentNullException(nameof(testMode));
            _onCompleted = onCompleted ?? throw new ArgumentNullException(nameof(onCompleted));
        }

        public void Begin(string requestId, string filterSummary, bool filterRequested, int requestTimeoutMs)
        {
            var state = XUUnityLightMcpTestRunState.Begin(
                requestId,
                _operationName,
                _testMode,
                filterSummary,
                filterRequested,
                requestTimeoutMs);
            Activate(state, resetAttribution: true);
        }

        public void Restore(XUUnityLightMcpPersistedTestRunState state)
        {
            Activate(state, resetAttribution: false);
        }

        void Activate(XUUnityLightMcpPersistedTestRunState state, bool resetAttribution)
        {
            var previousRequestId = _requestId;
            _active = state != null
                      && string.Equals(state.operation, _operationName, StringComparison.Ordinal)
                      && string.Equals(state.response_handoff_state, "pending", StringComparison.Ordinal)
                      && string.IsNullOrWhiteSpace(state.completed_at_utc);
            _startedAtUtc = _active ? state.started_at_utc ?? "" : "";
            _requestId = _active ? state.request_id ?? "" : "";
            if (!string.IsNullOrEmpty(previousRequestId)
                && !string.Equals(previousRequestId, _requestId, StringComparison.Ordinal))
            {
                XUUnityLightMcpTestLogAttribution.Unsubscribe(previousRequestId);
            }

            if (_active)
            {
                XUUnityLightMcpTestLogAttribution.Subscribe(_requestId, resetAttribution);
            }
        }

        public void Clear()
        {
            XUUnityLightMcpTestLogAttribution.Unsubscribe(_requestId);
            _active = false;
            _startedAtUtc = "";
            _requestId = "";
        }

        public void RunStarted(ITestAdaptor testsToRun)
        {
            if (_active)
            {
                XUUnityLightMcpTestRunState.RecordRunStarted(CountLeafTests(testsToRun));
            }
        }

        public void RunFinished(ITestResultAdaptor result)
        {
            if (!_active)
            {
                return;
            }

            var response = XUUnityLightMcpTestRunState.CompleteAndBuildResponse(
                "unity_test_runner_callbacks",
                XUUnityLightMcpPlayModeStateOperation.ResolvePlayModeState(),
                BuildSummary(result),
                XUUnityLightMcpTestLogAttribution.TakePending());
            _onCompleted(response);
        }

        public void TestStarted(ITestAdaptor test)
        {
            if (!_active || test == null || test.IsSuite)
            {
                return;
            }

            var testName = test.FullName ?? test.Name ?? "";
            XUUnityLightMcpTestRunState.RecordTestStarted(testName, XUUnityLightMcpTestLogAttribution.BeginTest(testName));
        }

        public void TestFinished(ITestResultAdaptor result)
        {
            if (!_active || result?.Test == null || result.Test.IsSuite)
            {
                return;
            }

            var status = NormalizeStatus(result.TestStatus);
            var testName = result.Test.FullName ?? result.Test.Name ?? "";
            XUUnityLightMcpTestRunState.RecordTestFinished(
                status,
                testName,
                result.Message ?? "",
                XUUnityLightMcpTestLogAttribution.FinishTest(testName, string.Equals(status, "passed", StringComparison.Ordinal)));
        }

        static XUUnityLightMcpTestRunSummary BuildSummary(ITestResultAdaptor result)
        {
            var summary = new XUUnityLightMcpTestRunSummary();
            AddResult(summary, result);
            return summary;
        }

        static void AddResult(XUUnityLightMcpTestRunSummary summary, ITestResultAdaptor result)
        {
            if (summary == null || result == null)
            {
                return;
            }

            if (result.HasChildren && result.Children != null)
            {
                foreach (var child in result.Children)
                {
                    AddResult(summary, child);
                }

                return;
            }

            if (result.Test != null && result.Test.IsSuite)
            {
                return;
            }

            summary.total++;
            switch (NormalizeStatus(result.TestStatus))
            {
                case "passed":
                    summary.passed++;
                    break;
                case "failed":
                    summary.failed++;
                    summary.failures.Add(new XUUnityLightMcpTestFailure
                    {
                        name = result.Test?.FullName ?? result.Test?.Name ?? "",
                        message = result.Message ?? ""
                    });
                    break;
                case "skipped":
                    summary.skipped++;
                    break;
            }
        }

        static string NormalizeStatus(TestStatus testStatus)
        {
            switch (testStatus)
            {
                case TestStatus.Passed:
                    return "passed";
                case TestStatus.Failed:
                    return "failed";
                case TestStatus.Skipped:
                    return "skipped";
                default:
                    return "";
            }
        }

        static int CountLeafTests(ITestAdaptor test)
        {
            if (test == null)
            {
                return 0;
            }

            if (test.HasChildren && test.Children != null)
            {
                return test.Children.Sum(CountLeafTests);
            }

            return test.IsSuite ? 0 : 1;
        }
    }
}
