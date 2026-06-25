namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpRefreshSettleRuntime
    {
        const int RefreshSettleStableTickTarget = 2;

        public static bool RefreshSettlePending
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePending;
                }
            }
        }

        public static string RefreshSettleRequestId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleRequestId;
                }
            }
        }

        public static string RefreshSettleStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStartedUtc;
                }
            }
        }

        public static string RefreshSettleCompletedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleCompletedUtc;
                }
            }
        }

        public static string RefreshSettlePhase
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePhase;
                }
            }
        }

        public static bool RefreshSettlePackageResolveRequested
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePackageResolveRequested;
                }
            }
        }

        public static void BeginRefreshSettleTracking(string requestId, bool packageResolveRequested)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePending = true;
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleRequestId = requestId ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleCompletedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePhase = packageResolveRequested ? "waiting_for_package_settle" : "waiting_for_editor_idle";
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePackageResolveRequested = packageResolveRequested;
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStableTickCount = 0;
            }
        }

        internal static void PollLocked()
        {
            if (!XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePending)
            {
                return;
            }

            var editorIsIdle = XUUnityLightMcpEditorLifecycleRuntime.IsEditorIdleForSettleLocked();
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePhase = editorIsIdle
                ? "waiting_for_stable_idle_ticks"
                : (XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePackageResolveRequested ? "waiting_for_package_settle" : "waiting_for_editor_idle");

            if (editorIsIdle)
            {
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStableTickCount++;
                if (XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStableTickCount >= RefreshSettleStableTickTarget)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePending = false;
                    XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleCompletedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                    XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePhase = "settled";
                }
            }
            else
            {
                XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStableTickCount = 0;
            }
        }
    }
}
