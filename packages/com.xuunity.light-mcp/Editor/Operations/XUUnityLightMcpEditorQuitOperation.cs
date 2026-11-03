using System;
using System.Diagnostics;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpEditorQuitOperation : IXUUnityLightMcpOperation
    {
        internal static Func<bool> PrefabStageDirty = IsCurrentPrefabStageDirty;

        public string OperationName => "unity.editor.quit";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            using var process = Process.GetCurrentProcess();
            var payload = new XUUnityLightMcpEditorQuitPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                outcome = "quit_requested",
                requested_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                quit_mechanism = XUUnityLightMcpEditorQuitScheduler.QuitMechanism,
                editor_pid = process.Id,
                editor_application_focused = XUUnityLightMcpPlayModeLivenessTracker.EditorApplicationFocused,
                is_playing = EditorApplication.isPlaying,
                scene_dirty = AnyOpenSceneDirty(),
            };

            var expiresUtc = XUUnityLightMcpEditorQuitScheduler.Arm(request.request_id);
            payload.quit_expires_at_utc = XUUnityLightMcpEditorQuitScheduler.FormatUtc(expiresUtc);

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
        }

        static bool AnyOpenSceneDirty()
        {
            for (var index = 0; index < SceneManager.sceneCount; index++)
            {
                if (SceneManager.GetSceneAt(index).isDirty)
                {
                    return true;
                }
            }

            return PrefabStageDirty();
        }

        static bool IsCurrentPrefabStageDirty()
        {
            var prefabStage = PrefabStageUtility.GetCurrentPrefabStage();
            return prefabStage != null && prefabStage.scene.isDirty;
        }
    }
}
