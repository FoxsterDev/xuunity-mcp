using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBridgeRuntimeSnapshotBuilder
    {
        public static bool TryGetActiveRequestSnapshot(out XUUnityLightMcpActiveRequestSnapshot snapshot)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                if (string.IsNullOrWhiteSpace(XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId))
                {
                    snapshot = null;
                    return false;
                }

                snapshot = new XUUnityLightMcpActiveRequestSnapshot
                {
                    request_id = XUUnityLightMcpBridgeRuntimeStorage.ActiveRequestId,
                    operation = XUUnityLightMcpBridgeRuntimeStorage.ActiveOperation,
                    started_at_utc = XUUnityLightMcpBridgeRuntimeStorage.ActiveOperationStartedUtc,
                };
                return true;
            }
        }
    }
}
