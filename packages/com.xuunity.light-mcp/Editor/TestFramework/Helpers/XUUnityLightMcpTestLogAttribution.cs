using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using UnityEditor;
using UnityEngine;
using UnityEngine.TestTools;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpTestLogRecord
    {
        public LogType Type;
        public string Message = "";
        public string ActiveTest = "";
        public DateTime LoggedAtUtc;
        public object Scope;
        public bool IgnoringFailingMessages;
    }

    internal sealed class XUUnityLightMcpTestLogWindow
    {
        internal const int MaxPendingRecords = 256;

        readonly object _gate = new();
        List<XUUnityLightMcpTestLogRecord> _pending = new();
        long _overflowCount;
        string _activeTest = "";
        string _ownerRequestId = "";

        public string OwnerRequestId
        {
            get
            {
                lock (_gate)
                {
                    return _ownerRequestId;
                }
            }
        }

        public string ActiveTest
        {
            get
            {
                lock (_gate)
                {
                    return _activeTest;
                }
            }
        }

        public int PendingCount
        {
            get
            {
                lock (_gate)
                {
                    return _pending.Count + (int)Math.Min(int.MaxValue, _overflowCount);
                }
            }
        }

        public void Claim(string requestId, bool reset)
        {
            requestId ??= "";
            lock (_gate)
            {
                if (reset || !string.Equals(_ownerRequestId, requestId, StringComparison.Ordinal))
                {
                    ResetLocked();
                }

                _ownerRequestId = requestId;
            }
        }

        public bool Release(string requestId)
        {
            if (string.IsNullOrEmpty(requestId))
            {
                return false;
            }

            lock (_gate)
            {
                if (!string.IsNullOrEmpty(_ownerRequestId)
                    && !string.Equals(_ownerRequestId, requestId, StringComparison.Ordinal))
                {
                    return false;
                }

                ResetLocked();
                _ownerRequestId = "";
                return true;
            }
        }

        public void Append(LogType type, string message, object scope, DateTime loggedAtUtc, bool ignoringFailingMessages = false)
        {
            lock (_gate)
            {
                if (_pending.Count >= MaxPendingRecords)
                {
                    _overflowCount++;
                    return;
                }

                _pending.Add(new XUUnityLightMcpTestLogRecord
                {
                    Type = type,
                    Message = message ?? "",
                    ActiveTest = _activeTest,
                    LoggedAtUtc = loggedAtUtc,
                    Scope = scope,
                    IgnoringFailingMessages = ignoringFailingMessages
                });
            }
        }

        public List<XUUnityLightMcpTestLogRecord> Take(string nextActiveTest, out long overflowCount, out string ownerRequestId)
        {
            lock (_gate)
            {
                _activeTest = nextActiveTest ?? "";
                overflowCount = _overflowCount;
                ownerRequestId = _ownerRequestId;
                if (_pending.Count == 0 && _overflowCount == 0)
                {
                    return null;
                }

                var records = _pending;
                _pending = new List<XUUnityLightMcpTestLogRecord>();
                _overflowCount = 0;
                return records;
            }
        }

        public List<XUUnityLightMcpTestLogRecord> TakeFinished(string finishedTest, out long overflowCount, out string ownerRequestId)
        {
            var records = Take("", out overflowCount, out ownerRequestId);
            if (records == null || string.IsNullOrEmpty(finishedTest))
            {
                return records;
            }

            foreach (var record in records)
            {
                if (string.IsNullOrEmpty(record.ActiveTest))
                {
                    record.ActiveTest = finishedTest;
                }
            }

            return records;
        }

        void ResetLocked()
        {
            _pending = new List<XUUnityLightMcpTestLogRecord>();
            _overflowCount = 0;
            _activeTest = "";
        }
    }

    internal static class XUUnityLightMcpTestLogAttribution
    {
        internal static readonly XUUnityLightMcpTestLogWindow Window = new();

        static readonly object SubscriptionGate = new();
        static volatile int _mainThreadId = -1;
        static bool _reflectionResolved;
        static volatile bool _reflectionAvailable;
        static MethodInfo _hasCurrentLogScope;
        static PropertyInfo _currentLogScope;
        static PropertyInfo _allLogs;
        static PropertyInfo _eventIsHandled;
        static PropertyInfo _eventMessage;
        static PropertyInfo _eventLogType;
        static PropertyInfo _scopeIgnoreFailingMessages;
        static volatile bool _ignoreFailingMessagesAvailable;

        internal static bool ReflectionAvailable
        {
            get
            {
                EnsureReflection();
                return _reflectionAvailable;
            }
        }

        internal static bool IgnoreFailingMessagesReflectionAvailable
        {
            get
            {
                EnsureReflection();
                return _ignoreFailingMessagesAvailable;
            }
        }

        internal static void Subscribe(string requestId, bool resetState)
        {
            EnsureReflection();
            XUUnityLightMcpConsoleBuffer.EnsureStarted();
            lock (SubscriptionGate)
            {
                Window.Claim(requestId, resetState);
                _mainThreadId = Thread.CurrentThread.ManagedThreadId;
                Application.logMessageReceivedThreaded -= OnLog;
                Application.logMessageReceivedThreaded += OnLog;
                AssemblyReloadEvents.beforeAssemblyReload -= OnBeforeAssemblyReload;
                AssemblyReloadEvents.beforeAssemblyReload += OnBeforeAssemblyReload;
            }
        }

        internal static void Unsubscribe(string requestId)
        {
            lock (SubscriptionGate)
            {
                if (!Window.Release(requestId))
                {
                    return;
                }

                Application.logMessageReceivedThreaded -= OnLog;
                AssemblyReloadEvents.beforeAssemblyReload -= OnBeforeAssemblyReload;
            }
        }

        internal static XUUnityLightMcpConsoleErrorAttribution BeginTest(string testName)
        {
            var records = Window.Take(testName, out var overflowCount, out var requestId);
            return ClassifyOutsideWindow(records, overflowCount, requestId, XUUnityLightMcpConsoleBuffer.CounterSessionId);
        }

        internal static XUUnityLightMcpConsoleErrorAttribution FinishTest(string testName, bool testPassed)
        {
            return FinishTest(Window, testName, testPassed, XUUnityLightMcpConsoleBuffer.CounterSessionId);
        }

        internal static XUUnityLightMcpConsoleErrorAttribution FinishTest(
            XUUnityLightMcpTestLogWindow window,
            string testName,
            bool testPassed,
            string sessionId)
        {
            var records = window.TakeFinished(testName, out var overflowCount, out var requestId);
            if (records == null)
            {
                return null;
            }

            try
            {
                var handledByScope = ReadHandledFailingEvents(records);
                return Classify(records, overflowCount, handledByScope, testPassed, ReflectionAvailable, requestId, sessionId);
            }
            catch
            {
                return Classify(records, overflowCount, null, testPassed, false, requestId, sessionId);
            }
        }

        internal static XUUnityLightMcpConsoleErrorAttribution TakePending()
        {
            var records = Window.Take("", out var overflowCount, out var requestId);
            return ClassifyOutsideWindow(records, overflowCount, requestId, XUUnityLightMcpConsoleBuffer.CounterSessionId);
        }

        internal static XUUnityLightMcpConsoleErrorAttribution ClassifyOutsideWindow(
            IReadOnlyList<XUUnityLightMcpTestLogRecord> records,
            long overflowCount,
            string requestId,
            string counterSessionId)
        {
            if (records == null && overflowCount <= 0)
            {
                return null;
            }

            var attribution = NewAttribution(requestId, counterSessionId);
            attribution.not_expected_count = Math.Max(0L, overflowCount);
            var classifications = new List<string>();
            if (records != null)
            {
                foreach (var record in records)
                {
                    var classification = string.IsNullOrEmpty(record.ActiveTest)
                        ? XUUnityLightMcpConsoleErrorClassification.Unexpected
                        : XUUnityLightMcpConsoleErrorClassification.Unclassified;
                    classifications.Add(classification);
                    attribution.not_expected_count++;
                }
            }

            FinishAttribution(attribution, records, classifications);
            return attribution;
        }

        internal static XUUnityLightMcpConsoleErrorAttribution Classify(
            IReadOnlyList<XUUnityLightMcpTestLogRecord> records,
            long overflowCount,
            IDictionary<object, List<KeyValuePair<LogType, string>>> handledByScope,
            bool testPassed,
            bool reflectionAvailable,
            string requestId,
            string counterSessionId)
        {
            if (records == null && overflowCount <= 0)
            {
                return null;
            }

            var attribution = NewAttribution(requestId, counterSessionId);
            attribution.not_expected_count = Math.Max(0L, overflowCount);
            var classifications = new List<string>();
            if (records != null)
            {
                foreach (var record in records)
                {
                    var classification = ClassifyRecord(record, handledByScope, testPassed, reflectionAvailable);
                    classifications.Add(classification);
                    if (string.Equals(classification, XUUnityLightMcpConsoleErrorClassification.ExpectedByTest, StringComparison.Ordinal))
                    {
                        attribution.expected_by_test_count++;
                    }
                    else
                    {
                        attribution.not_expected_count++;
                    }
                }
            }

            FinishAttribution(attribution, records, classifications);
            return attribution;
        }

        static string ClassifyRecord(
            XUUnityLightMcpTestLogRecord record,
            IDictionary<object, List<KeyValuePair<LogType, string>>> handledByScope,
            bool testPassed,
            bool reflectionAvailable)
        {
            if (string.IsNullOrEmpty(record.ActiveTest) || !testPassed)
            {
                return XUUnityLightMcpConsoleErrorClassification.Unexpected;
            }

            if (record.IgnoringFailingMessages)
            {
                return XUUnityLightMcpConsoleErrorClassification.ExpectedByTest;
            }

            if (!reflectionAvailable
                || record.Scope == null
                || handledByScope == null
                || !handledByScope.TryGetValue(record.Scope, out var handled)
                || handled == null)
            {
                return XUUnityLightMcpConsoleErrorClassification.Unclassified;
            }

            for (var index = 0; index < handled.Count; index++)
            {
                if (handled[index].Key == record.Type
                    && string.Equals(handled[index].Value, record.Message, StringComparison.Ordinal))
                {
                    handled.RemoveAt(index);
                    return XUUnityLightMcpConsoleErrorClassification.ExpectedByTest;
                }
            }

            return XUUnityLightMcpConsoleErrorClassification.Unexpected;
        }

        static XUUnityLightMcpConsoleErrorAttribution NewAttribution(string requestId, string counterSessionId)
        {
            return new XUUnityLightMcpConsoleErrorAttribution
            {
                request_id = requestId ?? "",
                counter_session_id = counterSessionId ?? ""
            };
        }

        static void FinishAttribution(
            XUUnityLightMcpConsoleErrorAttribution attribution,
            IReadOnlyList<XUUnityLightMcpTestLogRecord> records,
            List<string> classifications)
        {
            var anyUnclassified = classifications.Contains(XUUnityLightMcpConsoleErrorClassification.Unclassified);
            attribution.basis = anyUnclassified
                ? XUUnityLightMcpConsoleErrorClassification.BasisLogScopeUnavailable
                : classifications.Count > 0
                    ? XUUnityLightMcpConsoleErrorClassification.BasisLogScope
                    : "";
            if (records == null)
            {
                return;
            }

            for (var pass = 0; pass < 2 && attribution.samples.Count < XUUnityLightMcpConsoleErrorClassification.MaxSamples; pass++)
            {
                var wantExpected = pass == 1;
                for (var index = 0; index < records.Count && attribution.samples.Count < XUUnityLightMcpConsoleErrorClassification.MaxSamples; index++)
                {
                    var isExpected = string.Equals(
                        classifications[index],
                        XUUnityLightMcpConsoleErrorClassification.ExpectedByTest,
                        StringComparison.Ordinal);
                    if (isExpected == wantExpected)
                    {
                        attribution.samples.Add(BuildSample(records[index], classifications[index]));
                    }
                }
            }
        }

        internal static XUUnityLightMcpConsoleErrorSample BuildSample(XUUnityLightMcpTestLogRecord record, string classification)
        {
            return new XUUnityLightMcpConsoleErrorSample
            {
                type = NormalizeType(record.Type),
                message = Truncate(record.Message, XUUnityLightMcpConsoleErrorClassification.MaxSampleMessageChars),
                active_test = Truncate(record.ActiveTest, XUUnityLightMcpConsoleErrorClassification.MaxSampleActiveTestChars),
                classification = classification ?? "",
                logged_at_utc = record.LoggedAtUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
            };
        }

        internal static string Truncate(string value, int limit)
        {
            value ??= "";
            if (value.Length <= limit)
            {
                return value;
            }

            var length = char.IsHighSurrogate(value[limit - 1]) ? limit - 1 : limit;
            return value.Substring(0, length) + "...";
        }

        static string NormalizeType(LogType type)
        {
            switch (type)
            {
                case LogType.Exception:
                    return "exception";
                case LogType.Assert:
                    return "assert";
                default:
                    return "error";
            }
        }

        internal static bool TryReadHandledFailingEvents(object scope, out List<KeyValuePair<LogType, string>> handled)
        {
            handled = null;
            if (scope == null || !ReflectionAvailable)
            {
                return false;
            }

            try
            {
                if (!(_allLogs.GetValue(scope) is IList logs))
                {
                    return false;
                }

                var result = new List<KeyValuePair<LogType, string>>();
                for (var index = 0; index < logs.Count; index++)
                {
                    var logEvent = logs[index];
                    if (logEvent == null || !(bool)_eventIsHandled.GetValue(logEvent))
                    {
                        continue;
                    }

                    var type = (LogType)_eventLogType.GetValue(logEvent);
                    if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                    {
                        result.Add(new KeyValuePair<LogType, string>(type, _eventMessage.GetValue(logEvent) as string ?? ""));
                    }
                }

                handled = result;
                return true;
            }
            catch
            {
                handled = null;
                return false;
            }
        }

        static Dictionary<object, List<KeyValuePair<LogType, string>>> ReadHandledFailingEvents(
            IReadOnlyList<XUUnityLightMcpTestLogRecord> records)
        {
            var handledByScope = new Dictionary<object, List<KeyValuePair<LogType, string>>>();
            var unreadable = new HashSet<object>();
            foreach (var record in records)
            {
                var scope = record.Scope;
                if (scope == null || handledByScope.ContainsKey(scope) || unreadable.Contains(scope))
                {
                    continue;
                }

                if (TryReadHandledFailingEvents(scope, out var handled))
                {
                    handledByScope[scope] = handled;
                }
                else
                {
                    unreadable.Add(scope);
                }
            }

            return handledByScope;
        }

        static void OnLog(string condition, string stackTrace, LogType type)
        {
            AppendLog(Window, condition, type, Thread.CurrentThread.ManagedThreadId == _mainThreadId);
        }

        internal static void AppendLog(XUUnityLightMcpTestLogWindow window, string condition, LogType type, bool onMainThread)
        {
            if (window == null || (type != LogType.Error && type != LogType.Exception && type != LogType.Assert))
            {
                return;
            }

            object scope = null;
            var ignoringFailingMessages = false;
            if (_reflectionAvailable && onMainThread)
            {
                scope = TryReadCurrentScope();
                ignoringFailingMessages = TryReadIgnoringFailingMessages(scope);
            }

            window.Append(type, condition, scope, DateTime.UtcNow, ignoringFailingMessages);
        }

        static bool TryReadIgnoringFailingMessages(object scope)
        {
            if (scope == null || !_ignoreFailingMessagesAvailable)
            {
                return false;
            }

            try
            {
                return _scopeIgnoreFailingMessages.GetValue(scope) is bool ignoring && ignoring;
            }
            catch
            {
                return false;
            }
        }

        static object TryReadCurrentScope()
        {
            try
            {
                return _hasCurrentLogScope.Invoke(null, null) is bool hasScope && hasScope
                    ? _currentLogScope.GetValue(null)
                    : null;
            }
            catch
            {
                return null;
            }
        }

        static void OnBeforeAssemblyReload()
        {
            try
            {
                XUUnityLightMcpTestRunState.RecordConsoleErrorAttribution(TakePending());
            }
            catch
            {
            }
        }

        static void EnsureReflection()
        {
            if (_reflectionResolved)
            {
                return;
            }

            try
            {
                const BindingFlags staticFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
                const BindingFlags instanceFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
                var assembly = typeof(LogAssert).Assembly;
                var scopeType = assembly.GetType("UnityEngine.TestTools.Logging.LogScope");
                var eventType = assembly.GetType("UnityEngine.TestTools.Logging.LogEvent");
                if (scopeType != null && eventType != null)
                {
                    _hasCurrentLogScope = scopeType.GetMethod("HasCurrentLogScope", staticFlags, null, Type.EmptyTypes, null);
                    _currentLogScope = scopeType.GetProperty("Current", staticFlags);
                    _allLogs = scopeType.GetProperty("AllLogs", instanceFlags);
                    _eventIsHandled = eventType.GetProperty("IsHandled", instanceFlags);
                    _eventMessage = eventType.GetProperty("Message", instanceFlags);
                    _eventLogType = eventType.GetProperty("LogType", instanceFlags);
                    _scopeIgnoreFailingMessages = scopeType.GetProperty("IgnoreFailingMessages", instanceFlags);
                }

                _reflectionAvailable = _hasCurrentLogScope != null
                                       && _hasCurrentLogScope.ReturnType == typeof(bool)
                                       && _currentLogScope != null
                                       && _allLogs != null
                                       && typeof(IList).IsAssignableFrom(_allLogs.PropertyType)
                                       && _eventIsHandled != null
                                       && _eventIsHandled.PropertyType == typeof(bool)
                                       && _eventMessage != null
                                       && _eventMessage.PropertyType == typeof(string)
                                       && _eventLogType != null
                                       && _eventLogType.PropertyType == typeof(LogType);
                _ignoreFailingMessagesAvailable = _scopeIgnoreFailingMessages != null
                                                  && _scopeIgnoreFailingMessages.PropertyType == typeof(bool)
                                                  && _scopeIgnoreFailingMessages.CanRead;
            }
            catch
            {
                _reflectionAvailable = false;
                _ignoreFailingMessagesAvailable = false;
            }

            _reflectionResolved = true;
        }
    }
}
