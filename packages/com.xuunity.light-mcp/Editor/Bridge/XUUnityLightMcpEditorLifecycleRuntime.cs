using UnityEditor;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpEditorLifecycleRuntime
    {
        const double AssetImportActiveWindowSeconds = 2.0d;
        const double PackageOperationQuietWindowSeconds = 2.0d;

        public static bool DomainReloadInProgress
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress;
                }
            }
        }

        public static string DomainReloadStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.DomainReloadStartedUtc;
                }
            }
        }

        public static bool AssetImportInProgress
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress;
                }
            }
        }

        public static string AssetImportLastActivityUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.AssetImportLastActivityUtc;
                }
            }
        }

        public static bool PackageOperationInProgress
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress;
                }
            }
        }

        public static string PackageOperationName
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PackageOperationName;
                }
            }
        }

        public static string PackageOperationPhase
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PackageOperationPhase;
                }
            }
        }

        public static string PackageOperationStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedUtc;
                }
            }
        }

        public static bool ScriptReloadPending
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending;
                }
            }
        }

        public static string ScriptReloadStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc;
                }
            }
        }

        public static void MarkDomainReloadStarting()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress = true;
                XUUnityLightMcpBridgeRuntimeStorage.DomainReloadStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                if (string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc))
                {
                    XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.DomainReloadStartedUtc;
                }

                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = true;
            }
        }

        public static void MarkDomainReloadCompleted()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress = false;
                XUUnityLightMcpBridgeRuntimeStorage.DomainReloadStartedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = false;
                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = "";
            }
        }

        public static void MarkScriptReloadPending()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = true;
                if (string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc))
                {
                    XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                }
            }
        }

        public static void MarkScriptReloadCompleted()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = false;
                XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = "";
            }
        }

        public static void MarkAssetImportActivity()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress = true;
                XUUnityLightMcpBridgeRuntimeStorage.AssetImportLastActivityUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.AssetImportActiveUntilRealtime = EditorApplication.timeSinceStartup + AssetImportActiveWindowSeconds;
            }
        }

        public static void MarkPackageOperationStarted(string operationName, string phase = "started")
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress = true;
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationName = operationName ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationPhase = phase ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedRealtime = EditorApplication.timeSinceStartup;
            }
        }

        public static void MarkPackageOperationCompleted()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                if (!XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress)
                {
                    return;
                }

                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationPhase = "settling";
                XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedRealtime = EditorApplication.timeSinceStartup;
            }
        }

        public static void PollTransientLifecycleState()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                if (XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress
                    && EditorApplication.timeSinceStartup >= XUUnityLightMcpBridgeRuntimeStorage.AssetImportActiveUntilRealtime
                    && !EditorApplication.isUpdating)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress = false;
                }

                if (XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress
                    && !EditorApplication.isUpdating
                    && !EditorApplication.isCompiling
                    && !XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress
                    && EditorApplication.timeSinceStartup >= XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedRealtime + PackageOperationQuietWindowSeconds)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress = false;
                    XUUnityLightMcpBridgeRuntimeStorage.PackageOperationName = "";
                    XUUnityLightMcpBridgeRuntimeStorage.PackageOperationPhase = "";
                    XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedUtc = "";
                    XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedRealtime = 0.0d;
                }

                if (XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending
                    && !XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress
                    && !EditorApplication.isCompiling
                    && !EditorApplication.isUpdating)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = false;
                    XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = "";
                }

                XUUnityLightMcpRefreshSettleRuntime.PollLocked();
                XUUnityLightMcpCompileSettleRuntime.PollLocked();
                XUUnityLightMcpPlayModeTransitionRuntime.PollLocked();
            }
        }

        internal static bool IsEditorIdleForSettleLocked()
        {
            return !XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress
                && !XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress
                && !XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending
                && !XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress
                && !EditorApplication.isCompiling
                && !EditorApplication.isUpdating
                && (EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode);
        }
    }
}
