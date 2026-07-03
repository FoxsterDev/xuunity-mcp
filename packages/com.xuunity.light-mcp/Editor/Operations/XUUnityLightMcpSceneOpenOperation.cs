using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpSceneOpenOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.scene.open";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpSceneOpenArgs()
                : JsonUtility.FromJson<XUUnityLightMcpSceneOpenArgs>(request.args_json) ?? new XUUnityLightMcpSceneOpenArgs();

            var requestedPath = NormalizeScenePath(args.scenePath);
            var previousScene = SceneManager.GetActiveScene();
            var payload = new XUUnityLightMcpSceneOpenPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                requested_scene_path = requestedPath,
                allow_dirty_scene_discard = args.allowDirtySceneDiscard,
                previous_scene = BuildSceneData(previousScene)
            };

            var failure = ValidateRequest(requestedPath, args.allowDirtySceneDiscard);
            if (!string.IsNullOrWhiteSpace(failure))
            {
                payload.status = "failed";
                payload.outcome = "scene_open_blocked";
                payload.failure_reason = failure;
                payload.active_scene = BuildSceneData(SceneManager.GetActiveScene());
                return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
            }

            try
            {
                EditorSceneManager.OpenScene(requestedPath, OpenSceneMode.Single);
            }
            catch (Exception ex)
            {
                payload.status = "failed";
                payload.outcome = "scene_open_failed";
                payload.failure_reason = ex.Message;
                payload.active_scene = BuildSceneData(SceneManager.GetActiveScene());
                return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
            }

            var activeScene = SceneManager.GetActiveScene();
            payload.active_scene = BuildSceneData(activeScene);
            if (string.Equals(activeScene.path ?? "", requestedPath, StringComparison.Ordinal))
            {
                payload.status = "passed";
                payload.opened = true;
                payload.outcome = string.Equals(previousScene.path ?? "", requestedPath, StringComparison.Ordinal)
                    ? "scene_already_active"
                    : "scene_opened";
            }
            else
            {
                payload.status = "failed";
                payload.outcome = "scene_open_incomplete";
                payload.failure_reason = $"Unity active scene is '{activeScene.path ?? ""}' after open, expected '{requestedPath}'.";
            }

            return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
        }

        static string ValidateRequest(string scenePath, bool allowDirtySceneDiscard)
        {
            if (string.IsNullOrWhiteSpace(scenePath))
            {
                return "unity.scene.open requires scenePath.";
            }

            if (!scenePath.StartsWith("Assets/", StringComparison.Ordinal))
            {
                return "scenePath must be a project-relative Assets/... path.";
            }

            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return "Cannot open a scene while Unity is in or transitioning Play Mode; exit Play Mode first.";
            }

            if (AssetDatabase.LoadAssetAtPath<SceneAsset>(scenePath) == null)
            {
                return $"Scene asset not found at '{scenePath}'.";
            }

            if (!allowDirtySceneDiscard)
            {
                var dirtyScenes = GetDirtyOpenScenes();
                if (dirtyScenes.Count > 0)
                {
                    return "Open scenes have unsaved changes; pass allowDirtySceneDiscard=true to discard them intentionally.";
                }
            }

            return "";
        }

        static string NormalizeScenePath(string scenePath)
        {
            var trimmed = (scenePath ?? "").Trim().Replace('\\', '/');
            var projectRoot = (XUUnityLightMcpFileIpcPaths.ProjectRootPath ?? "").Replace('\\', '/').TrimEnd('/');
            if (!string.IsNullOrWhiteSpace(projectRoot)
                && trimmed.StartsWith(projectRoot + "/", StringComparison.Ordinal))
            {
                trimmed = trimmed.Substring(projectRoot.Length + 1);
            }

            return trimmed;
        }

        static XUUnityLightMcpSceneData BuildSceneData(Scene scene)
        {
            return new XUUnityLightMcpSceneData
            {
                name = scene.name ?? "",
                path = scene.path ?? "",
                is_dirty = scene.isDirty,
                root_count = scene.IsValid() ? scene.GetRootGameObjects().Length : 0
            };
        }

        static List<Scene> GetDirtyOpenScenes()
        {
            var result = new List<Scene>(EditorSceneManager.sceneCount);
            for (var i = 0; i < EditorSceneManager.sceneCount; i++)
            {
                var scene = EditorSceneManager.GetSceneAt(i);
                if (scene.IsValid() && scene.isDirty)
                {
                    result.Add(scene);
                }
            }

            return result;
        }
    }
}
