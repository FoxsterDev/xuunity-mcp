using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBridgeRuntimeState
    {
        public static string BridgeSessionId => XUUnityLightMcpBridgeSessionRuntime.BridgeSessionId;
        public static int BridgeGeneration => XUUnityLightMcpBridgeSessionRuntime.BridgeGeneration;
        public static bool BridgeBootstrapAttached => XUUnityLightMcpBridgeSessionRuntime.BridgeBootstrapAttached;
        public static bool DomainReloadInProgress => XUUnityLightMcpEditorLifecycleRuntime.DomainReloadInProgress;
        public static string DomainReloadStartedUtc => XUUnityLightMcpEditorLifecycleRuntime.DomainReloadStartedUtc;
        public static bool AssetImportInProgress => XUUnityLightMcpEditorLifecycleRuntime.AssetImportInProgress;
        public static string AssetImportLastActivityUtc => XUUnityLightMcpEditorLifecycleRuntime.AssetImportLastActivityUtc;
        public static bool PackageOperationInProgress => XUUnityLightMcpEditorLifecycleRuntime.PackageOperationInProgress;
        public static string PackageOperationName => XUUnityLightMcpEditorLifecycleRuntime.PackageOperationName;
        public static string PackageOperationPhase => XUUnityLightMcpEditorLifecycleRuntime.PackageOperationPhase;
        public static string PackageOperationStartedUtc => XUUnityLightMcpEditorLifecycleRuntime.PackageOperationStartedUtc;
        public static bool ScriptReloadPending => XUUnityLightMcpEditorLifecycleRuntime.ScriptReloadPending;
        public static string ScriptReloadStartedUtc => XUUnityLightMcpEditorLifecycleRuntime.ScriptReloadStartedUtc;
        public static bool RefreshSettlePending => XUUnityLightMcpRefreshSettleRuntime.RefreshSettlePending;
        public static string RefreshSettleRequestId => XUUnityLightMcpRefreshSettleRuntime.RefreshSettleRequestId;
        public static string RefreshSettleStartedUtc => XUUnityLightMcpRefreshSettleRuntime.RefreshSettleStartedUtc;
        public static string RefreshSettleCompletedUtc => XUUnityLightMcpRefreshSettleRuntime.RefreshSettleCompletedUtc;
        public static string RefreshSettlePhase => XUUnityLightMcpRefreshSettleRuntime.RefreshSettlePhase;
        public static bool RefreshSettlePackageResolveRequested => XUUnityLightMcpRefreshSettleRuntime.RefreshSettlePackageResolveRequested;
        public static bool CompileSettlePending => XUUnityLightMcpCompileSettleRuntime.CompileSettlePending;
        public static string CompileSettleRequestId => XUUnityLightMcpCompileSettleRuntime.CompileSettleRequestId;
        public static string CompileSettleStartedUtc => XUUnityLightMcpCompileSettleRuntime.CompileSettleStartedUtc;
        public static string CompileSettleCompletedUtc => XUUnityLightMcpCompileSettleRuntime.CompileSettleCompletedUtc;
        public static string CompileSettlePhase => XUUnityLightMcpCompileSettleRuntime.CompileSettlePhase;
        public static string CompileSettleOperation => XUUnityLightMcpCompileSettleRuntime.CompileSettleOperation;
        public static bool PlayModeTransitionPending => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionPending;
        public static string PlayModeTransitionRequestId => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionRequestId;
        public static string PlayModeTransitionAction => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionAction;
        public static string PlayModeTransitionTargetState => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionTargetState;
        public static string PlayModeTransitionStartedUtc => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionStartedUtc;
        public static string PlayModeTransitionCompletedUtc => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionCompletedUtc;
        public static string PlayModeTransitionPhase => XUUnityLightMcpPlayModeTransitionRuntime.PlayModeTransitionPhase;
        public static string LastPumpUtc => XUUnityLightMcpRequestProcessingRuntime.LastPumpUtc;
        public static string LastProcessedRequestId => XUUnityLightMcpRequestProcessingRuntime.LastProcessedRequestId;
        public static int PendingRequestCount => XUUnityLightMcpRequestProcessingRuntime.PendingRequestCount;
        public static string ActiveRequestId => XUUnityLightMcpRequestProcessingRuntime.ActiveRequestId;
        public static string ActiveOperation => XUUnityLightMcpRequestProcessingRuntime.ActiveOperation;
        public static string ActiveOperationStartedUtc => XUUnityLightMcpRequestProcessingRuntime.ActiveOperationStartedUtc;
        public static string LastCompletedOperation => XUUnityLightMcpRequestProcessingRuntime.LastCompletedOperation;
        public static string LastCompletedOperationStatus => XUUnityLightMcpRequestProcessingRuntime.LastCompletedOperationStatus;
        public static double LastCompletedOperationDurationSeconds => XUUnityLightMcpRequestProcessingRuntime.LastCompletedOperationDurationSeconds;
        public static string RequestJournalHead => XUUnityLightMcpRequestProcessingRuntime.RequestJournalHead;

        public static bool TryGetCompletedCompileSettleUtc(string requestId, out string completedAtUtc)
        {
            return XUUnityLightMcpCompileSettleRuntime.TryGetCompletedCompileSettleUtc(requestId, out completedAtUtc);
        }

        public static bool TryGetActiveRequestSnapshot(out XUUnityLightMcpActiveRequestSnapshot snapshot)
        {
            return XUUnityLightMcpBridgeRuntimeSnapshotBuilder.TryGetActiveRequestSnapshot(out snapshot);
        }

        public static void InitializeBridgeSession()
        {
            XUUnityLightMcpBridgeSessionRuntime.InitializeBridgeSession();
        }

        public static void MarkJournalEvent(string eventId)
        {
            XUUnityLightMcpRequestProcessingRuntime.MarkJournalEvent(eventId);
        }

        public static void MarkDomainReloadStarting()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkDomainReloadStarting();
        }

        public static void MarkDomainReloadCompleted()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkDomainReloadCompleted();
        }

        public static void MarkScriptReloadPending()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkScriptReloadPending();
        }

        public static void MarkScriptReloadCompleted()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkScriptReloadCompleted();
        }

        public static void MarkAssetImportActivity()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkAssetImportActivity();
        }

        public static void MarkPackageOperationStarted(string operationName, string phase = "started")
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkPackageOperationStarted(operationName, phase);
        }

        public static void MarkPackageOperationCompleted()
        {
            XUUnityLightMcpEditorLifecycleRuntime.MarkPackageOperationCompleted();
        }

        public static void BeginRefreshSettleTracking(string requestId, bool packageResolveRequested)
        {
            XUUnityLightMcpRefreshSettleRuntime.BeginRefreshSettleTracking(requestId, packageResolveRequested);
        }

        public static void BeginCompileSettleTracking(string requestId, string operationName)
        {
            XUUnityLightMcpCompileSettleRuntime.BeginCompileSettleTracking(requestId, operationName);
        }

        public static void BeginPlayModeTransitionTracking(string requestId, string action, string targetState)
        {
            XUUnityLightMcpPlayModeTransitionRuntime.BeginPlayModeTransitionTracking(requestId, action, targetState);
        }

        public static void CancelPlayModeTransitionTracking()
        {
            XUUnityLightMcpPlayModeTransitionRuntime.CancelPlayModeTransitionTracking();
        }

        public static void MarkPlayModeStateChanged(string currentState)
        {
            XUUnityLightMcpPlayModeTransitionRuntime.MarkPlayModeStateChanged(currentState);
        }

        public static void PollTransientLifecycleState()
        {
            XUUnityLightMcpEditorLifecycleRuntime.PollTransientLifecycleState();
        }

        public static void MarkPumpTick(int pendingRequestCount)
        {
            XUUnityLightMcpRequestProcessingRuntime.MarkPumpTick(pendingRequestCount);
        }

        public static void MarkRequestStarted(string requestId, string operation, int pendingRequestCount)
        {
            XUUnityLightMcpRequestProcessingRuntime.MarkRequestStarted(requestId, operation, pendingRequestCount);
        }

        public static void MarkAsyncRequestPending(int remainingPendingRequests)
        {
            XUUnityLightMcpRequestProcessingRuntime.MarkAsyncRequestPending(remainingPendingRequests);
        }

        public static void MarkRequestProcessed(
            string requestId,
            string operation,
            string operationStatus,
            string startedAtUtc,
            int remainingPendingRequests)
        {
            XUUnityLightMcpRequestProcessingRuntime.MarkRequestProcessed(
                requestId,
                operation,
                operationStatus,
                startedAtUtc,
                remainingPendingRequests);
        }
    }
}
