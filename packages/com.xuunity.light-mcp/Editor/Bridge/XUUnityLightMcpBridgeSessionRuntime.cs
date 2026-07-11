using System;
using System.IO;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBridgeSessionRuntime
    {
        public static string BridgeSessionId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.BridgeSessionId;
                }
            }
        }

        public static int BridgeGeneration
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.BridgeGeneration;
                }
            }
        }

        public static bool BridgeBootstrapAttached
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.BridgeBootstrapAttached;
                }
            }
        }

        public static void InitializeBridgeSession()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpFileIpcPaths.EnsureDirectories();
                var nextGeneration = ResolveNextGeneration();

                ResetSessionFieldsLocked(nextGeneration);
                XUUnityLightMcpPlayModeTransitionRuntime.RestorePersistedStateLocked();
                PersistGenerationStateLocked();
            }
        }

        static int ResolveNextGeneration()
        {
            var nextGeneration = 1;
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.BridgeGenerationStatePath))
                {
                    var json = File.ReadAllText(XUUnityLightMcpFileIpcPaths.BridgeGenerationStatePath);
                    var payload = JsonUtility.FromJson<XUUnityLightMcpBridgeGenerationState>(json);
                    if (payload != null)
                    {
                        nextGeneration = Math.Max(1, payload.bridge_generation + 1);
                    }
                }
            }
            catch
            {
            }

            return nextGeneration;
        }

        static void ResetSessionFieldsLocked(int nextGeneration)
        {
            XUUnityLightMcpBridgeRuntimeStorage.BridgeGeneration = nextGeneration;
            XUUnityLightMcpBridgeRuntimeStorage.BridgeSessionId = Guid.NewGuid().ToString("N");
            XUUnityLightMcpBridgeRuntimeStorage.BridgeBootstrapAttached = true;
            XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress = false;
            XUUnityLightMcpBridgeRuntimeStorage.DomainReloadStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress = false;
            XUUnityLightMcpBridgeRuntimeStorage.AssetImportLastActivityUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.AssetImportActiveUntilRealtime = 0.0d;
            XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress = false;
            XUUnityLightMcpBridgeRuntimeStorage.PackageOperationName = "";
            XUUnityLightMcpBridgeRuntimeStorage.PackageOperationPhase = "";
            XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.PackageOperationStartedRealtime = 0.0d;
            XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending = false;
            XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePending = false;
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleRequestId = "";
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleCompletedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePhase = "";
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettlePackageResolveRequested = false;
            XUUnityLightMcpBridgeRuntimeStorage.RefreshSettleStableTickCount = 0;
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePending = false;
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettleRequestId = "";
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettleCompletedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettlePhase = "";
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettleOperation = "";
            XUUnityLightMcpBridgeRuntimeStorage.CompileSettleStableTickCount = 0;
            XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleRequestOrder.Clear();
            XUUnityLightMcpBridgeRuntimeStorage.CompletedCompileSettleCompletedUtcByRequestId.Clear();
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending = false;
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = "";
            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount = 0;
            XUUnityLightMcpBridgeRuntimeStorage.RequestJournalHead = "";
            XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId = "";
            XUUnityLightMcpBridgeRuntimeStorage.ActiveOperation = "";
            XUUnityLightMcpBridgeRuntimeStorage.ActiveOperationStartedUtc = "";
        }

        static void PersistGenerationStateLocked()
        {
            var payload = new XUUnityLightMcpBridgeGenerationState
            {
                bridge_generation = XUUnityLightMcpBridgeRuntimeStorage.BridgeGeneration,
                bridge_session_id = XUUnityLightMcpBridgeRuntimeStorage.BridgeSessionId,
                bootstrap_attached_at_utc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow(),
            };

            XUUnityLightMcpAtomicFileWriter.WriteAllText(XUUnityLightMcpFileIpcPaths.BridgeGenerationStatePath, JsonUtility.ToJson(payload, true));
        }
    }
}
