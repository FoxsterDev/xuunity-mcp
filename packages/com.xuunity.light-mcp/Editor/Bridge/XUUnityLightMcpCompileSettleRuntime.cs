namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpCompileSettleRuntime
    {
        const int CompileSettleStableTickTarget = 2;
        const int CompletedCompileSettleHistoryLimit = 16;

        public static bool CompileSettlePending
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePending;
                }
            }
        }

        public static string CompileSettleRequestId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettleRequestId;
                }
            }
        }

        public static string CompileSettleStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStartedUtc;
                }
            }
        }

        public static string CompileSettleCompletedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettleCompletedUtc;
                }
            }
        }

        public static string CompileSettlePhase
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePhase;
                }
            }
        }

        public static string CompileSettleOperation
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.CompileSettleOperation;
                }
            }
        }

        public static bool TryGetCompletedCompileSettleUtc(string requestId, out string completedAtUtc)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                if (!string.IsNullOrWhiteSpace(requestId)
                    && XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId.TryGetValue(requestId, out completedAtUtc))
                {
                    return true;
                }

                completedAtUtc = "";
                return false;
            }
        }

        public static void BeginCompileSettleTracking(string requestId, string operationName)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                ForgetCompletedCompileSettleLocked(requestId);
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePending = true;
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleRequestId = requestId ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleCompletedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePhase = "waiting_for_editor_idle";
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleOperation = operationName ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStableTickCount = 0;
            }
        }

        internal static void PollLocked()
        {
            if (!XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePending)
            {
                return;
            }

            var editorIsIdle = XUUnityLightMcpEditorLifecycleRuntime.IsEditorIdleForSettleLocked();
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePhase = editorIsIdle
                ? "waiting_for_stable_idle_ticks"
                : "waiting_for_editor_idle";

            if (editorIsIdle)
            {
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStableTickCount++;
                if (XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStableTickCount >= CompileSettleStableTickTarget)
                {
                    var completedAtUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                    XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePending = false;
                    XUUnityLightMcpBridgeRuntimeStorage.CompileSettleCompletedUtc = completedAtUtc;
                    XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePhase = "settled";
                    RememberCompletedCompileSettleLocked(XUUnityLightMcpBridgeRuntimeStorage.CompileSettleRequestId, completedAtUtc);
                }
            }
            else
            {
                XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStableTickCount = 0;
            }
        }

        static void RememberCompletedCompileSettleLocked(string requestId, string completedAtUtc)
        {
            if (string.IsNullOrWhiteSpace(requestId))
            {
                return;
            }

            if (!XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId.ContainsKey(requestId))
            {
                XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleRequestOrder.Enqueue(requestId);
            }

            XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId[requestId] = completedAtUtc ?? "";

            while (XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleRequestOrder.Count > CompletedCompileSettleHistoryLimit)
            {
                var evictedRequestId = XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleRequestOrder.Dequeue();
                XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId.Remove(evictedRequestId);
            }
        }

        static void ForgetCompletedCompileSettleLocked(string requestId)
        {
            if (string.IsNullOrWhiteSpace(requestId))
            {
                return;
            }

            XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId.Remove(requestId);
        }
    }
}
