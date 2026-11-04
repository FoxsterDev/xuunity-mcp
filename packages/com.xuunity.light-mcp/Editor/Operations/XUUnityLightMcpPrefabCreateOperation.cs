using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpPrefabCreateOperation : IXUUnityLightMcpOperation
    {
        public const string RegisteredOperationName = "unity.prefab.create";

        public string OperationName => RegisteredOperationName;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpPrefabCreateArgs()
                : JsonUtility.FromJson<XUUnityLightMcpPrefabCreateArgs>(request.args_json)
                  ?? new XUUnityLightMcpPrefabCreateArgs();

            var path = (args.prefabPath ?? "").Trim().Replace('\\', '/');
            var payload = new XUUnityLightMcpPrefabMutationPayload
            {
                operation = RegisteredOperationName,
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                generated_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                prefab_path = path,
                preview_only = args.previewOnly || !args.approve,
                requested_operation_count = (args.operations ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>()).Length,
                drift_guard = "new_asset"
            };

            var refusal = ValidateRequest(args, path);
            if (refusal != null)
            {
                payload.errors.Add(refusal);
                payload.recommended_next_action = "fix_the_create_request_then_preview_again";
                return Respond(request, payload);
            }

            var exists = !string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(path))
                         && AssetDatabase.LoadAssetAtPath<GameObject>(path) != null;
            payload.sha256_before = exists ? XUUnityLightMcpPrefabMutateOperation.FileSha256(path) : "";
            RunTransaction(args, path, exists, payload);
            return Respond(request, payload);
        }

        static XUUnityLightMcpUiDiagnostic ValidateRequest(XUUnityLightMcpPrefabCreateArgs args, string path)
        {
            if (!path.StartsWith("Assets/", StringComparison.Ordinal)
                || !path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_create_path_invalid",
                    "prefabPath must be a project-relative Assets/... path ending in .prefab.",
                    path);
            }

            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_create_requires_edit_mode",
                    "Prefab assets are created in Edit Mode only; exit Play Mode first.");
            }

            var operations = args.operations ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
            if (operations.Length > XUUnityLightMcpPrefabMutator.MAX_OPERATIONS)
            {
                return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_operations_limit",
                    $"A single transaction may carry at most {XUUnityLightMcpPrefabMutator.MAX_OPERATIONS} operations; "
                    + "create the skeleton first and continue with unity_prefab_mutate.");
            }

            if (operations.Length > 0)
            {
                var shape = new XUUnityLightMcpPrefabMutationArgs { operations = operations };
                if (!XUUnityLightMcpPrefabMutator.TryValidateArgs(shape, out var shapeError))
                {
                    return shapeError;
                }
            }

            var exists = !string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(path))
                         && File.Exists(path);
            if (exists && !args.overwrite)
            {
                return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_create_target_exists",
                    $"'{path}' already exists. Edit it with unity_prefab_mutate, or pass overwrite=true to replace it.",
                    path);
            }

            return null;
        }

        static void RunTransaction(
            XUUnityLightMcpPrefabCreateArgs args,
            string path,
            bool exists,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            var dirtyBefore = SnapshotDirtyScenes();
            var previewScene = EditorSceneManager.NewPreviewScene();
            GameObject root = null;
            try
            {
                var rootName = string.IsNullOrWhiteSpace(args.rootName)
                    ? Path.GetFileNameWithoutExtension(path)
                    : args.rootName.Trim();
                root = args.rootIsRectTransform
                    ? new GameObject(rootName, typeof(RectTransform))
                    : new GameObject(rootName);
                SceneManager.MoveGameObjectToScene(root, previewScene);

                var failure = XUUnityLightMcpPrefabMutateOperation.ApplyOperations(
                    args.operations,
                    root,
                    XUUnityLightMcpPrefabMutator.ResolveAllowedComponentTypes(null),
                    payload,
                    true);
                payload.planned_change_count = XUUnityLightMcpPrefabMutateOperation.CountStatus(payload.changes, "applied");
                payload.no_op_count = XUUnityLightMcpPrefabMutateOperation.CountStatus(payload.changes, "no_op");
                if (failure != null)
                {
                    RollBack(payload, failure, "prefab_mutation_rolled_back",
                        "An operation failed, so nothing was created.", "fix_the_failing_operation_then_preview_again");
                    return;
                }

                payload.post_validation = XUUnityLightMcpPrefabMutateOperation.ValidateContents(root, payload);
                if (!payload.post_validation.passed)
                {
                    RollBack(payload, "post_mutation_validation_failed", "prefab_mutation_validation_failed",
                        "The built prefab failed binding validation, so it was not saved.",
                        "inspect_post_validation_defects_before_retrying");
                    return;
                }

                if (payload.preview_only)
                {
                    payload.status = "previewed";
                    payload.success = true;
                    payload.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;
                    payload.recommended_next_action = "review_the_delta_then_re_run_with_approve_true_and_preview_only_false";
                    return;
                }

                EnsureFolder(Path.GetDirectoryName(path)?.Replace('\\', '/') ?? "Assets");
                PrefabUtility.SaveAsPrefabAsset(root, path, out var saved);
                if (!saved)
                {
                    RollBack(payload, "save_as_prefab_asset_failed", "prefab_create_save_failed",
                        "Unity refused to save the prefab asset.", "inspect_console_then_retry");
                    return;
                }

                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                payload.prefab_guid = AssetDatabase.AssetPathToGUID(path);
                payload.sha256_after = XUUnityLightMcpPrefabMutateOperation.FileSha256(path);
                payload.prefab_created = !exists;
                payload.applied = true;
                payload.status = "applied";
                payload.success = true;
                payload.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;
                payload.recommended_next_action = "render_or_validate_the_new_prefab";
            }
            catch (Exception exception)
            {
                RollBack(payload, exception.Message, "prefab_create_failed",
                    "The create transaction threw before the asset was written.", "inspect_console_then_retry");
            }
            finally
            {
                if (root != null)
                {
                    UnityEngine.Object.DestroyImmediate(root);
                }

                EditorSceneManager.ClosePreviewScene(previewScene);
                payload.open_scene_dirtied = DirtiedSince(dirtyBefore);
                if (payload.open_scene_dirtied)
                {
                    payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_create_dirtied_open_scene",
                        "Building the prefab marked an open scene dirty; tests will refuse until it is discarded "
                        + "(allowDirtySceneDiscard) or saved."));
                }
            }
        }

        static void RollBack(
            XUUnityLightMcpPrefabMutationPayload payload,
            string reason,
            string code,
            string message,
            string nextAction)
        {
            payload.status = "rolled_back";
            payload.rolled_back = true;
            payload.rollback_reason = reason;
            payload.applied = false;
            payload.success = false;
            payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(code, message, reason));
            payload.recommended_next_action = nextAction;
        }

        static void EnsureFolder(string folder)
        {
            if (string.IsNullOrEmpty(folder) || AssetDatabase.IsValidFolder(folder))
            {
                return;
            }

            var parent = Path.GetDirectoryName(folder)?.Replace('\\', '/') ?? "Assets";
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
        }

        static HashSet<int> SnapshotDirtyScenes()
        {
            var dirty = new HashSet<int>();
            for (var index = 0; index < SceneManager.sceneCount; index++)
            {
                var scene = SceneManager.GetSceneAt(index);
                if (scene.IsValid() && scene.isDirty)
                {
                    dirty.Add(scene.handle);
                }
            }

            return dirty;
        }

        static bool DirtiedSince(HashSet<int> dirtyBefore)
        {
            for (var index = 0; index < SceneManager.sceneCount; index++)
            {
                var scene = SceneManager.GetSceneAt(index);
                if (scene.IsValid() && scene.isDirty && !dirtyBefore.Contains(scene.handle))
                {
                    return true;
                }
            }

            return false;
        }

        static XUUnityLightMcpResponse Respond(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpPrefabMutationPayload payload)
        {
            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                RegisteredOperationName,
                JsonUtility.ToJson(payload));
        }
    }
}
