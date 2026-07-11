using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpPlayModeTransitionRuntime
    {
        const int PlayModeTransitionStableTickTarget = 2;
        const double RestoredPlayModeTransitionExpirySeconds = 30.0d;

        public static bool PlayModeTransitionPending
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending;
                }
            }
        }

        public static string PlayModeTransitionRequestId
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId;
                }
            }
        }

        public static string PlayModeTransitionAction
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction;
                }
            }
        }

        public static string PlayModeTransitionTargetState
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState;
                }
            }
        }

        public static string PlayModeTransitionStartedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc;
                }
            }
        }

        public static string PlayModeTransitionCompletedUtc
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc;
                }
            }
        }

        public static string PlayModeTransitionPhase
        {
            get
            {
                lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
                {
                    return XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase;
                }
            }
        }

        public static void BeginPlayModeTransitionTracking(string requestId, string action, string targetState)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending = true;
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId = requestId ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction = action ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState = targetState ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = "waiting_for_target_state";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount = 0;
                PersistStateLocked();
            }
        }

        public static void CancelPlayModeTransitionTracking()
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending = false;
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount = 0;
                DeletePersistedStateLocked();
            }
        }

        public static void MarkPlayModeStateChanged(string currentState)
        {
            lock (XUUnityLightMcpBridgeRuntimeStorage.Gate)
            {
                if (XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = $"state_changed:{currentState ?? ""}";
                }
            }
        }

        internal static void PollLocked()
        {
            if (!XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending)
            {
                return;
            }

            var currentState = ResolveCurrentPlayModeState();
            var targetReached = string.Equals(currentState, XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState, StringComparison.Ordinal);
            var stableState = !EditorApplication.isUpdating
                && !EditorApplication.isCompiling
                && !XUUnityLightMcpBridgeRuntimeStorage.DomainReloadInProgress
                && !XUUnityLightMcpBridgeRuntimeStorage.ScriptReloadPending
                && !XUUnityLightMcpBridgeRuntimeStorage.AssetImportInProgress
                && !XUUnityLightMcpBridgeRuntimeStorage.PackageOperationInProgress;

            XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = targetReached
                ? "waiting_for_stable_target_state"
                : $"waiting_for_target_state:{currentState}";

            if (targetReached && stableState)
            {
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount++;
                if (XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount >= PlayModeTransitionStableTickTarget)
                {
                    XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending = false;
                    XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc = XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                    XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = "settled";
                    DeletePersistedStateLocked();
                }
            }
            else
            {
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount = 0;
            }
        }

        internal static void RestorePersistedStateLocked()
        {
            try
            {
                if (!File.Exists(XUUnityLightMcpFileIpcPaths.PlayModeTransitionStatePath))
                {
                    return;
                }

                var json = File.ReadAllText(XUUnityLightMcpFileIpcPaths.PlayModeTransitionStatePath);
                var payload = JsonUtility.FromJson<XUUnityLightMcpPersistedPlayModeTransitionState>(json);
                if (payload == null || string.IsNullOrWhiteSpace(payload.request_id))
                {
                    DeletePersistedStateLocked();
                    return;
                }

                var currentState = ResolveCurrentPlayModeState();
                if (XUUnityLightMcpBridgeRuntimeStorage.HasUtcAgeExceeded(payload.started_at_utc, RestoredPlayModeTransitionExpirySeconds)
                    && !EditorApplication.isPlayingOrWillChangePlaymode
                    && !string.Equals(currentState, payload.target_state ?? "", StringComparison.Ordinal))
                {
                    DeletePersistedStateLocked();
                    return;
                }

                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPending = true;
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId = payload.request_id ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction = payload.action ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState = payload.target_state ?? "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc = payload.started_at_utc ?? XUUnityLightMcpBridgeRuntimeStorage.UtcNow();
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionCompletedUtc = "";
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase = string.IsNullOrWhiteSpace(payload.phase) ? "waiting_for_target_state" : payload.phase;
                XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStableTickCount = 0;
            }
            catch
            {
                DeletePersistedStateLocked();
            }
        }

        static void PersistStateLocked()
        {
            var payload = new XUUnityLightMcpPersistedPlayModeTransitionState
            {
                request_id = XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionRequestId,
                action = XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionAction,
                target_state = XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionTargetState,
                started_at_utc = XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionStartedUtc,
                phase = XUUnityLightMcpBridgeRuntimeStorage.PlayModeTransitionPhase,
            };

            XUUnityLightMcpAtomicFileWriter.WriteAllText(XUUnityLightMcpFileIpcPaths.PlayModeTransitionStatePath, JsonUtility.ToJson(payload, true));
        }

        static void DeletePersistedStateLocked()
        {
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.PlayModeTransitionStatePath))
                {
                    File.Delete(XUUnityLightMcpFileIpcPaths.PlayModeTransitionStatePath);
                }
            }
            catch
            {
            }
        }

        static string ResolveCurrentPlayModeState()
        {
            if (EditorApplication.isPlaying)
            {
                return EditorApplication.isPaused ? "paused" : "playing";
            }

            return EditorApplication.isPlayingOrWillChangePlaymode ? "transitioning" : "edit";
        }
    }
}
