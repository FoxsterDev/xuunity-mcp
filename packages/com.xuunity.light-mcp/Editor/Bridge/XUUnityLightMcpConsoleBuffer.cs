using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal sealed class XUUnityLightMcpConsoleSinceSnapshot
    {
        public bool AnchorResolved;
        public string AnchorReason = "";
        public long AnchorSequence;
        public string AnchorStartedUtc = "";
        public bool ScopeComplete;
        public List<XUUnityLightMcpConsoleItem> Items = new();
    }

    internal static class XUUnityLightMcpConsoleBuffer
    {
        public const string PlayModeStartAnchor = "playmode_start";
        const int MaxEntries = 500;
        const string PlayModeAnchorSequenceKey = "XUUnityLightMcp.ConsoleSequenceAtPlayModeStart";
        const string PlayModeAnchorSessionKey = "XUUnityLightMcp.ConsoleSessionAtPlayModeStart";
        const string PlayModeAnchorStartedUtcKey = "XUUnityLightMcp.ConsoleAnchorPlayModeStartedUtc";
        static readonly object Mutex = new();
        static readonly List<XUUnityLightMcpConsoleItem> Items = new();
        static readonly List<long> Sequences = new();
        static readonly string CounterSessionIdValue = Guid.NewGuid().ToString("N");
        static long _errorCount;
        static long _lastSequence;
        static bool _started;

        public static long ErrorCount => Interlocked.Read(ref _errorCount);
        public static string CounterSessionId => CounterSessionIdValue;

        public static void EnsureStarted()
        {
            if (_started)
            {
                return;
            }

            _started = true;
            Application.logMessageReceivedThreaded -= OnLog;
            Application.logMessageReceivedThreaded += OnLog;
        }

        static void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
            {
                Interlocked.Increment(ref _errorCount);
            }

            var item = new XUUnityLightMcpConsoleItem
            {
                type = NormalizeType(type),
                message = condition ?? "",
                timestamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                stack_trace = stackTrace ?? ""
            };

            lock (Mutex)
            {
                if (Items.Count >= MaxEntries)
                {
                    Items.RemoveAt(0);
                    Sequences.RemoveAt(0);
                }

                _lastSequence++;
                Items.Add(item);
                Sequences.Add(_lastSequence);
            }
        }

        public static List<XUUnityLightMcpConsoleItem> Snapshot()
        {
            lock (Mutex)
            {
                return new List<XUUnityLightMcpConsoleItem>(Items);
            }
        }

        public static void CapturePlayModeStartAnchor()
        {
            long lastSequence;
            lock (Mutex)
            {
                lastSequence = _lastSequence;
            }

            SessionState.SetString(PlayModeAnchorSequenceKey, lastSequence.ToString(CultureInfo.InvariantCulture));
            SessionState.SetString(PlayModeAnchorSessionKey, CounterSessionIdValue);
            SessionState.SetString(PlayModeAnchorStartedUtcKey, DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"));
        }

        public static XUUnityLightMcpConsoleSinceSnapshot SnapshotSincePlayModeStart()
        {
            var snapshot = new XUUnityLightMcpConsoleSinceSnapshot
            {
                AnchorStartedUtc = SessionState.GetString(PlayModeAnchorStartedUtcKey, ""),
            };
            var rawSequence = SessionState.GetString(PlayModeAnchorSequenceKey, "");
            if (!long.TryParse(rawSequence, NumberStyles.Integer, CultureInfo.InvariantCulture, out var anchorSequence))
            {
                snapshot.AnchorReason = "anchor_not_recorded";
                snapshot.Items = Snapshot();
                return snapshot;
            }

            snapshot.AnchorResolved = true;
            snapshot.AnchorSequence = anchorSequence;
            var anchorSession = SessionState.GetString(PlayModeAnchorSessionKey, "");
            lock (Mutex)
            {
                if (!string.Equals(anchorSession, CounterSessionIdValue, StringComparison.Ordinal))
                {
                    snapshot.AnchorReason = "console_buffer_recreated_after_anchor";
                    snapshot.ScopeComplete = Sequences.Count == 0 || Sequences[0] == 1L;
                    snapshot.Items = new List<XUUnityLightMcpConsoleItem>(Items);
                    return snapshot;
                }

                var firstIndex = Sequences.Count;
                for (var index = 0; index < Sequences.Count; index++)
                {
                    if (Sequences[index] > anchorSequence)
                    {
                        firstIndex = index;
                        break;
                    }
                }

                snapshot.AnchorReason = "console_buffer_since_anchor";
                snapshot.ScopeComplete = Sequences.Count == 0 || Sequences[0] <= anchorSequence + 1L;
                snapshot.Items = Items.GetRange(firstIndex, Items.Count - firstIndex);
                return snapshot;
            }
        }

        static string NormalizeType(LogType type)
        {
            return type switch
            {
                LogType.Error => "error",
                LogType.Assert => "warning",
                LogType.Warning => "warning",
                LogType.Exception => "exception",
                LogType.Log => "log",
                _ => "unknown"
            };
        }
    }
}
