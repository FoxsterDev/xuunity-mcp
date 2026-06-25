using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBridgeRuntimeStorage
    {
        internal static readonly object Gate = new();
        internal static readonly Queue<string> CompletedCompileSettleRequestOrder = new();
        internal static readonly Dictionary<string, string> CompletedCompileSettleCompletedUtcByRequestId = new(StringComparer.Ordinal);

        internal static string BridgeSessionId = "";
        internal static int BridgeGeneration;
        internal static bool BridgeBootstrapAttached;
        internal static bool DomainReloadInProgress;
        internal static string DomainReloadStartedUtc = "";
        internal static bool AssetImportInProgress;
        internal static string AssetImportLastActivityUtc = "";
        internal static double AssetImportActiveUntilRealtime;
        internal static bool PackageOperationInProgress;
        internal static string PackageOperationName = "";
        internal static string PackageOperationPhase = "";
        internal static string PackageOperationStartedUtc = "";
        internal static double PackageOperationStartedRealtime;
        internal static bool ScriptReloadPending;
        internal static string ScriptReloadStartedUtc = "";
        internal static bool RefreshSettlePending;
        internal static string RefreshSettleRequestId = "";
        internal static string RefreshSettleStartedUtc = "";
        internal static string RefreshSettleCompletedUtc = "";
        internal static string RefreshSettlePhase = "";
        internal static bool RefreshSettlePackageResolveRequested;
        internal static int RefreshSettleStableTickCount;
        internal static bool CompileSettlePending;
        internal static string CompileSettleRequestId = "";
        internal static string CompileSettleStartedUtc = "";
        internal static string CompileSettleCompletedUtc = "";
        internal static string CompileSettlePhase = "";
        internal static string CompileSettleOperation = "";
        internal static int CompileSettleStableTickCount;
        internal static bool PlayModeTransitionPending;
        internal static string PlayModeTransitionRequestId = "";
        internal static string PlayModeTransitionAction = "";
        internal static string PlayModeTransitionTargetState = "";
        internal static string PlayModeTransitionStartedUtc = "";
        internal static string PlayModeTransitionCompletedUtc = "";
        internal static string PlayModeTransitionPhase = "";
        internal static int PlayModeTransitionStableTickCount;
        internal static string LastPumpUtc = "";
        internal static string LastProcessedRequestId = "";
        internal static int PendingRequestCount;
        internal static string ActiveRequestId = "";
        internal static string ActiveOperation = "";
        internal static string ActiveOperationStartedUtc = "";
        internal static string LastCompletedOperation = "";
        internal static string LastCompletedOperationStatus = "";
        internal static double LastCompletedOperationDurationSeconds;
        internal static string RequestJournalHead = "";

        internal static double CalculateDurationSeconds(string startedAtUtc, string completedAtUtc)
        {
            if (string.IsNullOrWhiteSpace(startedAtUtc))
            {
                return 0.0d;
            }

            if (!DateTime.TryParse(startedAtUtc, null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out var started))
            {
                return 0.0d;
            }

            if (!DateTime.TryParse(completedAtUtc, null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out var completed))
            {
                completed = DateTime.UtcNow;
            }

            return Math.Round(Math.Max(0.0d, (completed - started).TotalSeconds), 6);
        }

        internal static string UtcNow()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        }

        internal static bool HasUtcAgeExceeded(string startedAtUtc, double maxAgeSeconds)
        {
            if (string.IsNullOrWhiteSpace(startedAtUtc))
            {
                return false;
            }

            if (!DateTime.TryParse(
                    startedAtUtc,
                    null,
                    System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                    out var startedAt))
            {
                return false;
            }

            return (DateTime.UtcNow - startedAt).TotalSeconds > Math.Max(0.0d, maxAgeSeconds);
        }
    }
}
