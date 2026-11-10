using System;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBuildPlayerRuntime
    {
        internal const string BusyReason = "build_player";

        static bool _inProgress;
        static string _target = "";
        static string _startedUtc = "";

        public static bool InProgress => _inProgress || IsUnityBuildingPlayer();
        public static string Target => _target ?? "";
        public static string StartedUtc => _startedUtc ?? "";

        public static void MarkStarted(string target)
        {
            if (_inProgress)
            {
                return;
            }

            _inProgress = true;
            _target = target ?? "";
            _startedUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            TryWriteHeartbeat();
        }

        public static void MarkCompleted()
        {
            if (!_inProgress)
            {
                return;
            }

            _inProgress = false;
            TryWriteHeartbeat();
        }

        public static void Tick()
        {
            if (_inProgress && !IsUnityBuildingPlayer())
            {
                MarkCompleted();
            }
        }

        static bool IsUnityBuildingPlayer()
        {
            try
            {
                return BuildPipeline.isBuildingPlayer;
            }
            catch
            {
                return false;
            }
        }

        static void TryWriteHeartbeat()
        {
            if (!XUUnityLightMcpBridgeActivation.IsEnabled()
                || XUUnityLightMcpBridgeProcessIdentity.ResolveCurrentProcessClass()
                == XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass)
            {
                return;
            }

            try
            {
                XUUnityLightMcpBridgeStateWriter.WriteHeartbeat();
            }
            catch
            {
            }
        }
    }

    internal sealed class XUUnityLightMcpBuildPlayerBusyMarker : IPreprocessBuildWithReport, IPostprocessBuildWithReport
    {
        public int callbackOrder => int.MinValue;

        public void OnPreprocessBuild(BuildReport report)
        {
            XUUnityLightMcpBuildPlayerRuntime.MarkStarted(report?.summary.platform.ToString() ?? "");
        }

        public void OnPostprocessBuild(BuildReport report)
        {
            XUUnityLightMcpBuildPlayerRuntime.MarkCompleted();
        }
    }
}
