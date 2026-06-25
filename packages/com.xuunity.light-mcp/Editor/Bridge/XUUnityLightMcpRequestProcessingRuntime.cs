using System;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpRequestProcessingRuntime
    {
        public static string LastPumpUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc;
                }
            }
        }

        public static string LastProcessedRequestId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.LastProcessedRequestId;
                }
            }
        }

        public static int PendingRequestCount
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PendingRequestCount;
                }
            }
        }

        public static string ActiveRequestId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId;
                }
            }
        }

        public static string ActiveOperation
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.ActiveOperation;
                }
            }
        }

        public static string ActiveOperationStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.ActiveOperationStartedUtc;
                }
            }
        }

        public static string LastCompletedOperation
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperation;
                }
            }
        }

        public static string LastCompletedOperationStatus
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperationStatus;
                }
            }
        }

        public static double LastCompletedOperationDurationSeconds
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperationDurationSeconds;
                }
            }
        }

        public static string RequestJournalHead
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.RequestJournalHead;
                }
            }
        }

        public static void MarkJournalEvent(string eventId)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.RequestJournalHead = eventId ?? "";
            }
        }

        public static void MarkPumpTick(int pendingRequestCount)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.PendingRequestCount = Math.Max(0, pendingRequestCount);
            }
        }

        public static void MarkRequestStarted(string requestId, string operation, int pendingRequestCount)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId = requestId ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.ActiveOperation = operation ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.ActiveOperationStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc;
                XUUnityLightMcpBridgeRuntimeStorage.PendingRequestCount = Math.Max(0, pendingRequestCount);
            }
        }

        public static void MarkAsyncRequestPending(int remainingPendingRequests)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.PendingRequestCount = Math.Max(0, remainingPendingRequests);
            }
        }

        public static void MarkRequestProcessed(
            string requestId,
            string operation,
            string operationStatus,
            string startedAtUtc,
            int remainingPendingRequests)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                if (!string.IsNullOrWhiteSpace(requestId))
                {
                    XUUnityLightMcpBridgeRuntimeStorage.LastProcessedRequestId = requestId;
                }

                XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperation = operation ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperationStatus = operationStatus ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.LastCompletedOperationDurationSeconds = XUUnityLightMcpBridgeRuntimeStorage.CalculateDurationSeconds(
                    startedAtUtc,
                    XUUnityLightMcpBridgeRuntimeStorage.LastPumpUtc);
                XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId = "";
                XUUnityLightMcpBridgeRuntimeStorage.ActiveOperation = "";
                XUUnityLightMcpBridgeRuntimeStorage.ActiveOperationStartedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.PendingRequestCount = Math.Max(0, remainingPendingRequests);
            }
        }
    }
}
