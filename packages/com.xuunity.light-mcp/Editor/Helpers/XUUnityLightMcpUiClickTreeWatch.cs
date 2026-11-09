using System;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpUiClickTreeWatch
    {
        internal const string OperationName = "unity.ui.click";
        internal const int MaxWaitForTreeChangeMs = 10000;

        internal const string WaitNotRequested = "not_requested";
        internal const string ChangedInDeliveryFrame = "changed_in_delivery_frame";
        internal const string ChangedAfterWait = "changed_after_wait";
        internal const string UnchangedAfterWait = "unchanged_after_wait";

        const string StateKey = "XUUnityLightMcp.UiClickTreeWatch.State";
        const double EditModeSampleIntervalSeconds = 0.05d;

        [Serializable]
        sealed class PendingWatch
        {
            public string requestId = "";
            public string startedAtUtc = "";
            public long deadlineUtcTicks;
            public long armedUtcTicks;
            public int armedFrame;
            public int lastSampledFrame;
            public XUUnityLightMcpUiClickArgs args = new();
            public XUUnityLightMcpUiClickPayload payload = new();
        }

        static PendingWatch _pending;
        static bool _restored;
        static double _lastSampleTime;

        internal static bool IsPending
        {
            get
            {
                EnsureRestored();
                return _pending != null;
            }
        }

        internal static int ClampWaitMs(int requestedMs)
        {
            return Math.Max(0, Math.Min(MaxWaitForTreeChangeMs, requestedMs));
        }

        internal static XUUnityLightMcpUiTreeOptions BuildSnapshotOptions(XUUnityLightMcpUiClickArgs args)
        {
            return new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = args.targetKind,
                TargetValue = args.targetValue,
                SceneName = args.sceneName,
                IncludeDontDestroyOnLoad = args.includeDontDestroyOnLoad,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = true,
                IncludeBounds = true,
                IncludeText = true
            };
        }

        internal static XUUnityLightMcpUiClickSnapshotRef Summarize(XUUnityLightMcpUiTreeResult result)
        {
            var summary = new XUUnityLightMcpUiClickSnapshotRef
            {
                node_count = result.Nodes.Count,
                truncated = result.Truncated,
                truncation_reason = result.TruncationReason
            };

            var builder = new StringBuilder();
            foreach (var node in result.Nodes)
            {
                builder.Append(node.path);
                builder.Append('|');
                builder.Append(node.active_in_hierarchy ? '1' : '0');
                builder.Append(node.visible ? '1' : '0');
                builder.Append(node.interactable ? '1' : '0');
                builder.Append(node.text);
                builder.Append(';');
            }

            summary.signature = XUUnityLightMcpUiClickSnapshotRef.Hash(builder.ToString());
            return summary;
        }

        internal static XUUnityLightMcpUiClickSnapshotRef Snapshot(XUUnityLightMcpUiClickArgs args)
        {
            return Summarize(XUUnityLightMcpUiTreeBuilder.Build(BuildSnapshotOptions(args)));
        }

        internal static bool SignatureChanged(XUUnityLightMcpUiClickPayload payload)
        {
            return !string.Equals(
                payload.before_snapshot?.signature ?? "",
                payload.after_snapshot?.signature ?? "",
                StringComparison.Ordinal);
        }

        internal static void Finalize(XUUnityLightMcpUiClickPayload payload)
        {
            payload.state_changed = SignatureChanged(payload);
            payload.effective = payload.delivered && payload.state_changed;
            payload.no_observable_effect = payload.delivered && !payload.state_changed;

            payload.success = payload.effective;
            payload.status = payload.effective
                ? "effective"
                : payload.delivered
                    ? "delivered_no_observable_effect"
                    : "not_delivered";
            payload.proof_class = payload.effective
                ? XUUnityLightMcpUiRead.ProofSemanticTree
                : XUUnityLightMcpUiRead.ProofSemanticPartial;
            if (!payload.delivered)
            {
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_click_not_delivered",
                    "The event system accepted the target but no handler consumed the click."));
            }
            else if (payload.no_observable_effect)
            {
                var waited = payload.wait_for_tree_change_ms > 0
                    ? $"It was re-snapshotted for {payload.wait_for_tree_change_ms} ms "
                      + $"({payload.tree_change_sample_count} later sample(s)) without a change. "
                    : "Set waitForTreeChangeMs when the effect appears in a later frame. ";
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_click_no_state_change",
                    "The handler consumed the pointer event, but the UI tree did not change. "
                    + waited
                    + "The event carries a pointerCurrentRaycast naming "
                    + $"'{payload.pointer_raycast_target_path}' ({payload.pointer_raycast_evidence}), so a handler that "
                    + "validates raycast identity was satisfied; the effect may only be visible in logs or non-UI state. "
                    + "Verify with a UI query, an anchored log assertion, or a project-defined hook that calls the "
                    + "production API."));
            }
        }

        internal static void Arm(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpUiClickArgs args,
            XUUnityLightMcpUiClickPayload payload)
        {
            var nowUtc = DateTime.UtcNow;
            _pending = new PendingWatch
            {
                requestId = request.request_id ?? "",
                startedAtUtc = nowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture),
                armedUtcTicks = nowUtc.Ticks,
                deadlineUtcTicks = nowUtc.AddMilliseconds(payload.wait_for_tree_change_ms).Ticks,
                armedFrame = Time.frameCount,
                lastSampledFrame = Time.frameCount,
                args = args,
                payload = payload
            };
            _restored = true;
            Persist();
        }

        internal static void Tick()
        {
            if (!_restored)
            {
                EnsureRestored();
            }

            if (_pending == null)
            {
                return;
            }

            var watch = _pending;
            var frame = Time.frameCount;
            var nowTicks = DateTime.UtcNow.Ticks;
            var expired = nowTicks >= watch.deadlineUtcTicks;
            var now = EditorApplication.timeSinceStartup;
            if (!expired)
            {
                if (EditorApplication.isPlaying ? frame == watch.lastSampledFrame : now - _lastSampleTime < EditModeSampleIntervalSeconds)
                {
                    return;
                }
            }

            try
            {
                watch.lastSampledFrame = frame;
                _lastSampleTime = now;
                watch.payload.after_snapshot = Snapshot(watch.args);
                watch.payload.tree_change_sample_count++;
                var changed = SignatureChanged(watch.payload);
                if (!changed && !expired)
                {
                    return;
                }

                watch.payload.tree_change_wait_status = changed ? ChangedAfterWait : UnchangedAfterWait;
                watch.payload.tree_change_observed_after_ms = changed
                    ? Math.Round(TimeSpan.FromTicks(nowTicks - watch.armedUtcTicks).TotalMilliseconds, 1)
                    : 0d;
                watch.payload.tree_change_observed_after_frames = changed ? Math.Max(0, frame - watch.armedFrame) : 0;
                Complete(watch);
            }
            catch (Exception ex)
            {
                Clear();
                var response = XUUnityLightMcpResponseWriter.Error(watch.requestId, "ui_click_tree_watch_failed", ex.Message);
                WriteCompletion(watch, response);
            }
        }

        static void Complete(PendingWatch watch)
        {
            Clear();
            Finalize(watch.payload);
            var response = XUUnityLightMcpResponseWriter.Success(
                watch.requestId,
                OperationName,
                JsonUtility.ToJson(watch.payload));
            WriteCompletion(watch, response);
        }

        static void WriteCompletion(PendingWatch watch, XUUnityLightMcpResponse response)
        {
            if (!watch.requestId.StartsWith("scenario_", StringComparison.Ordinal))
            {
                var completedAtUtc = response.completed_at_utc ?? DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
                if (string.Equals(XUUnityLightMcpBridgeRuntimeState.ActiveRequestId, watch.requestId, StringComparison.Ordinal))
                {
                    XUUnityLightMcpBridgeRuntimeState.MarkRequestProcessed(
                        watch.requestId,
                        OperationName,
                        response.status ?? "ok",
                        watch.startedAtUtc,
                        0);
                }

                try
                {
                    XUUnityLightMcpRequestJournal.WriteRequestCompleted(
                        watch.requestId,
                        OperationName,
                        response.status ?? "ok",
                        watch.startedAtUtc,
                        completedAtUtc,
                        0,
                        response);
                }
                catch
                {
                }
            }

            XUUnityLightMcpResponseWriter.Write(response);
        }

        static void EnsureRestored()
        {
            if (_restored)
            {
                return;
            }

            _restored = true;
            var json = SessionState.GetString(StateKey, "");
            if (string.IsNullOrEmpty(json))
            {
                return;
            }

            try
            {
                _pending = JsonUtility.FromJson<PendingWatch>(json);
                if (_pending != null && string.IsNullOrEmpty(_pending.requestId))
                {
                    _pending = null;
                }

                if (_pending != null)
                {
                    _pending.lastSampledFrame = -1;
                }
            }
            catch
            {
                _pending = null;
                SessionState.EraseString(StateKey);
            }
        }

        static void Persist()
        {
            if (_pending == null)
            {
                SessionState.EraseString(StateKey);
                return;
            }

            SessionState.SetString(StateKey, JsonUtility.ToJson(_pending));
        }

        internal static void Clear()
        {
            _pending = null;
            _restored = true;
            SessionState.EraseString(StateKey);
        }
    }
}
