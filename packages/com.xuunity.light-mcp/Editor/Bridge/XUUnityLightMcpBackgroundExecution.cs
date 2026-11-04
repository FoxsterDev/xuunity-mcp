using System.IO;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpBackgroundExecution
    {
        internal const string ManagedMode = "managed";
        internal const string ProjectOwnedMode = "project_owned";
        internal const string ConfigKey = "background_execution_enabled";

        const string RestorePendingKey = "XUUnityLightMcp.BackgroundExecutionRestorePending";
        const string RestoreValueKey = "XUUnityLightMcp.BackgroundExecutionRestoreValue";

        static bool _resolvedThisDomain;
        static bool _configured;
        static bool _applied;

        public static string Mode => _configured ? ManagedMode : ProjectOwnedMode;

        public static bool AppliedNow => _applied;

        public static void ApplyIfConfigured()
        {
            if (_resolvedThisDomain)
            {
                return;
            }

            _resolvedThisDomain = true;
            _configured = XUUnityLightMcpBridgeActivation.LoadConfig().background_execution_enabled;
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
            Reconcile();
        }

        public static bool TrySetConfigured(bool enabled, out string error)
        {
            error = "";
            if (!TryWriteConfigKey(enabled, out error))
            {
                return false;
            }

            XUUnityLightMcpBridgeActivation.InvalidateConfig();
            _resolvedThisDomain = true;
            _configured = enabled;
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
            Reconcile();
            return true;
        }

        public static void Restore()
        {
            _applied = false;
            if (!SessionState.GetBool(RestorePendingKey, false))
            {
                return;
            }

            var original = SessionState.GetBool(RestoreValueKey, Application.runInBackground);
            SessionState.EraseBool(RestorePendingKey);
            SessionState.EraseBool(RestoreValueKey);
            if (Application.runInBackground != original)
            {
                Application.runInBackground = original;
            }
        }

        static void OnPlayModeStateChanged(PlayModeStateChange change)
        {
            switch (change)
            {
                case PlayModeStateChange.ExitingEditMode:
                case PlayModeStateChange.EnteredPlayMode:
                    Reconcile();
                    break;
                case PlayModeStateChange.EnteredEditMode:
                    Restore();
                    break;
            }
        }

        static void Reconcile()
        {
            // Unity reads runInBackground at Play entry and writes that value back after ExitingPlayMode,
            // so it is applied before entry and restored only once Edit Mode is entered.
            if (_configured && EditorApplication.isPlayingOrWillChangePlaymode)
            {
                Apply();
                return;
            }

            Restore();
        }

        static void Apply()
        {
            if (!SessionState.GetBool(RestorePendingKey, false))
            {
                SessionState.SetBool(RestoreValueKey, Application.runInBackground);
                SessionState.SetBool(RestorePendingKey, true);
            }

            _applied = true;
            if (!Application.runInBackground)
            {
                Application.runInBackground = true;
            }
        }

        static bool TryWriteConfigKey(bool enabled, out string error)
        {
            error = "";
            var path = XUUnityLightMcpFileIpcPaths.BridgeConfigPath;
            LightJsonNode root = null;
            if (File.Exists(path))
            {
                if (!LightJsonNode.TryParse(File.ReadAllText(path), out root, out var parseError)
                    || root.Kind != LightJsonKind.Object)
                {
                    error = $"bridge_config.json is not a JSON object ({parseError}); it was left untouched.";
                    return false;
                }
            }

            root ??= LightJsonNode.ObjectNode();
            root.Object[ConfigKey] = new LightJsonNode { Kind = LightJsonKind.Bool, BoolValue = enabled };
            XUUnityLightMcpAtomicFileWriter.WriteAllText(path, root.ToJson());
            return true;
        }
    }
}
