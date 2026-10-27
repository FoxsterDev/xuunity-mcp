using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Ugui
{
    internal sealed class XUUnityLightMcpPrefabRenderOperation : IXUUnityLightMcpOperation
    {
        public const string RegisteredOperationName = "unity.prefab.render";
        const int MAX_DIMENSION = 4096;
        const float PLANE_DISTANCE = 100f;

        public string OperationName => RegisteredOperationName;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpPrefabRenderArgs()
                : JsonUtility.FromJson<XUUnityLightMcpPrefabRenderArgs>(request.args_json)
                  ?? new XUUnityLightMcpPrefabRenderArgs();

            var payload = new XUUnityLightMcpPrefabRenderPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                generated_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                prefab_path = args.prefabPath ?? ""
            };

            if (!TryValidateArgs(args, out var width, out var height, out var argsError))
            {
                payload.errors.Add(argsError);
                return Respond(request, payload);
            }

            var loaded = XUUnityLightMcpPrefabInspector.Load(args.prefabPath);
            if (loaded.Error != null)
            {
                payload.errors.Add(loaded.Error);
                return Respond(request, payload);
            }

            payload.prefab_path = loaded.NormalizedPath;
            payload.prefab_guid = loaded.Guid;
            payload.reference_width = args.referenceWidth > 0 ? args.referenceWidth : width;
            payload.reference_height = args.referenceHeight > 0 ? args.referenceHeight : height;
            payload.requested_override_count =
                (args.overrides ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>()).Length;

            var stopwatch = Stopwatch.StartNew();
            try
            {
                Render(args, loaded, width, height, payload);
            }
            catch (Exception exception)
            {
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_render_failed",
                    "The isolated prefab render failed.",
                    exception.Message));
            }

            stopwatch.Stop();
            payload.render_duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 3);
            return Respond(request, payload);
        }

        static void Render(
            XUUnityLightMcpPrefabRenderArgs args,
            XUUnityLightMcpPrefabLoadResult loaded,
            int width,
            int height,
            XUUnityLightMcpPrefabRenderPayload payload)
        {
            var previewScene = EditorSceneManager.NewPreviewScene();
            RenderTexture renderTexture = null;
            Texture2D readback = null;
            GameObject cameraRoot = null;
            GameObject canvasRoot = null;

            try
            {
                cameraRoot = new GameObject("XUUnityMcpPreviewCamera", typeof(Camera))
                {
                    hideFlags = HideFlags.HideAndDontSave
                };
                SceneManager.MoveGameObjectToScene(cameraRoot, previewScene);
                var camera = cameraRoot.GetComponent<Camera>();
                camera.scene = previewScene;
                camera.orthographic = true;
                camera.orthographicSize = height / 2f;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = PLANE_DISTANCE * 4f;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = ParseColor(args.backgroundColor);
                camera.transform.position = new Vector3(0f, 0f, -PLANE_DISTANCE);
                camera.transform.rotation = Quaternion.identity;

                canvasRoot = new GameObject("XUUnityMcpPreviewCanvas", typeof(RectTransform), typeof(Canvas))
                {
                    hideFlags = HideFlags.HideAndDontSave
                };
                SceneManager.MoveGameObjectToScene(canvasRoot, previewScene);
                var canvas = canvasRoot.GetComponent<Canvas>();
                canvas.renderMode = RenderMode.ScreenSpaceCamera;
                canvas.worldCamera = camera;
                canvas.planeDistance = PLANE_DISTANCE;
                var canvasRect = canvasRoot.GetComponent<RectTransform>();
                canvasRect.sizeDelta = new Vector2(width, height);

                if (args.referenceWidth > 0 && args.referenceHeight > 0)
                {
                    var scaler = canvasRoot.AddComponent<CanvasScaler>();
                    scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
                    scaler.referenceResolution = new Vector2(args.referenceWidth, args.referenceHeight);
                    scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
                    scaler.matchWidthOrHeight = Mathf.Clamp01(args.scalerMatch);
                }

                var contentParent = BuildSafeArea(args, canvasRect, width, height, payload);
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(loaded.Root, previewScene);
                instance.hideFlags = HideFlags.HideAndDontSave;
                var instanceRect = instance.transform as RectTransform;
                if (instanceRect == null)
                {
                    payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_render_no_rect_transform",
                        "The prefab root has no RectTransform; it is rendered without canvas layout.",
                        loaded.NormalizedPath));
                    instance.transform.SetParent(contentParent, false);
                }
                else
                {
                    instanceRect.SetParent(contentParent, false);
                }

                // Overrides land on the preview instance only. The prefab asset is never saved from this
                // operation, so a second runtime-driven UI state costs one render instead of a
                // mutate/restore pair on an asset other projects share.
                if (!TryApplyOverrides(args, instance, payload))
                {
                    return;
                }

                Canvas.ForceUpdateCanvases();
                if (instanceRect != null)
                {
                    LayoutRebuilder.ForceRebuildLayoutImmediate(instanceRect);
                }

                renderTexture = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32)
                {
                    antiAliasing = NormalizeAntiAliasing(args.antiAliasing)
                };
                camera.targetTexture = renderTexture;
                camera.Render();

                // The snapshot's screen rects come from WorldToScreenPoint(camera, ...), which reads
                // the camera's pixel rect. That is the render target only while it is attached;
                // detaching first makes every rect scale by editorDisplayHeight/height, and
                // explain_regions then blames the wrong node with full confidence.
                var renderedSnapshot = BuildSnapshot(args, instance, width, height, payload);

                camera.targetTexture = null;

                var previous = RenderTexture.active;
                RenderTexture.active = renderTexture;
                readback = new Texture2D(width, height, TextureFormat.RGBA32, false);
                readback.ReadPixels(new UnityEngine.Rect(0f, 0f, width, height), 0, 0);
                readback.Apply(false);
                RenderTexture.active = previous;

                var outputPath = ResolveOutputPath(args, loaded);
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? ".");
                var bytes = readback.EncodeToPNG();
                File.WriteAllBytes(outputPath, bytes);

                payload.capture_status = "capture_produced";
                payload.screenshot_path = outputPath;
                payload.screenshot_width = width;
                payload.screenshot_height = height;
                payload.screenshot_size_bytes = bytes.LongLength;
                payload.application_booted = false;
                payload.persisted_scene_changes = false;
                payload.success = true;
                payload.proof_class = XUUnityLightMcpUiRead.ProofSemanticTree;

                if (renderedSnapshot != null)
                {
                    payload.proof_class = renderedSnapshot.proof_class;
                    if (args.writeSnapshot)
                    {
                        payload.snapshot_path = XUUnityLightMcpUiSnapshotArtifact.Write(
                            renderedSnapshot,
                            args.snapshotOutputPath,
                            outputPath,
                            "prefab-render-" + Path.GetFileNameWithoutExtension(loaded.NormalizedPath),
                            out var snapshotError);
                        renderedSnapshot.snapshot_path = payload.snapshot_path;
                        if (snapshotError != null)
                        {
                            payload.warnings.Add(snapshotError);
                        }
                    }

                    if (args.includeSnapshot)
                    {
                        payload.snapshot = renderedSnapshot;
                    }
                }
            }
            finally
            {
                if (readback != null)
                {
                    UnityEngine.Object.DestroyImmediate(readback);
                }

                if (renderTexture != null)
                {
                    renderTexture.Release();
                    UnityEngine.Object.DestroyImmediate(renderTexture);
                }

                if (canvasRoot != null)
                {
                    UnityEngine.Object.DestroyImmediate(canvasRoot);
                }

                if (cameraRoot != null)
                {
                    UnityEngine.Object.DestroyImmediate(cameraRoot);
                }

                EditorSceneManager.ClosePreviewScene(previewScene);
            }
        }

        static bool TryApplyOverrides(
            XUUnityLightMcpPrefabRenderArgs args,
            GameObject instance,
            XUUnityLightMcpPrefabRenderPayload payload)
        {
            var overrides = args.overrides ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
            if (overrides.Length == 0)
            {
                return true;
            }

            if (overrides.Length > XUUnityLightMcpPrefabMutator.MAX_OPERATIONS)
            {
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_render_override_limit",
                    $"A render may carry at most {XUUnityLightMcpPrefabMutator.MAX_OPERATIONS} transient overrides.",
                    overrides.Length.ToString(CultureInfo.InvariantCulture)));
                return false;
            }

            var allowed = XUUnityLightMcpPrefabMutator.ResolveAllowedComponentTypes(args.allowedComponentTypes);
            for (var index = 0; index < overrides.Length; index++)
            {
                var change = XUUnityLightMcpPrefabMutator.Apply(instance, overrides[index], index, allowed);
                payload.applied_overrides.Add(change);
                if (string.Equals(change.status, "failed", StringComparison.Ordinal))
                {
                    payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_render_override_failed",
                        "A transient override failed, so no capture was taken; a render of the un-overridden state "
                        + "would be evidence for the wrong UI state.",
                        $"override {index} ({change.op}) failed as {change.error_code}"));
                    return false;
                }
            }

            return true;
        }

        static RectTransform BuildSafeArea(
            XUUnityLightMcpPrefabRenderArgs args,
            RectTransform canvasRect,
            int width,
            int height,
            XUUnityLightMcpPrefabRenderPayload payload)
        {
            var top = Mathf.Max(0, args.safeAreaTop);
            var bottom = Mathf.Max(0, args.safeAreaBottom);
            var left = Mathf.Max(0, args.safeAreaLeft);
            var right = Mathf.Max(0, args.safeAreaRight);
            payload.safe_area = new XUUnityLightMcpUiRect
            {
                x = left,
                y = top,
                width = Mathf.Max(0, width - left - right),
                height = Mathf.Max(0, height - top - bottom)
            };

            if (top == 0 && bottom == 0 && left == 0 && right == 0)
            {
                return canvasRect;
            }

            var safeArea = new GameObject("XUUnityMcpSafeArea", typeof(RectTransform))
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            var rect = safeArea.GetComponent<RectTransform>();
            rect.SetParent(canvasRect, false);
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = new Vector2(left, bottom);
            rect.offsetMax = new Vector2(-right, -top);
            return rect;
        }

        static XUUnityLightMcpUiTreePayload BuildSnapshot(
            XUUnityLightMcpPrefabRenderArgs args,
            GameObject instance,
            int width,
            int height,
            XUUnityLightMcpPrefabRenderPayload payload)
        {
            var options = new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = XUUnityLightMcpUiRead.TargetPrefabAsset,
                TargetValue = payload.prefab_path,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = args.includeInactive,
                IncludeBounds = true,
                IncludeText = true
            };

            var result = new XUUnityLightMcpUiTreeResult();
            result.Target.kind = XUUnityLightMcpUiRead.TargetPrefabAsset;
            result.Target.requested_value = payload.prefab_path;
            result.Target.prefab_path = payload.prefab_path;
            result.Target.backend = XUUnityLightMcpUiRead.BackendUgui;
            result.Target.backend_status = "isolated_preview_render";
            result.Target.resolved_root_count = 1;
            result.Target.capture_width = width;
            result.Target.capture_height = height;
            result.Target.screen_width = Screen.width;
            result.Target.screen_height = Screen.height;
            result.Target.render_width = width;
            result.Target.render_height = height;
            result.Target.render_target_available = true;
            result.Target.render_target_differs_from_screen = width != Screen.width || height != Screen.height;

            var rootPath = XUUnityLightMcpUiTreeBuilder.BuildPath(instance.transform);
            result.RootPaths.Add(rootPath);
            XUUnityLightMcpUiTreeBuilder.Traverse(
                instance.transform,
                rootPath,
                "",
                0,
                0,
                Mathf.Max(1, args.maxDepth),
                Mathf.Max(1, args.maxNodes),
                options,
                result);

            var snapshot = new XUUnityLightMcpUiTreePayload
            {
                operation = "unity.ui.tree_snapshot",
                project_root = payload.project_root,
                generated_at_utc = payload.generated_at_utc,
                target = result.Target,
                nodes = result.Nodes,
                root_paths = result.RootPaths,
                node_count = result.Nodes.Count,
                max_depth = Mathf.Max(1, args.maxDepth),
                max_nodes = Mathf.Max(1, args.maxNodes),
                truncated = result.Truncated,
                truncation_reason = result.TruncationReason,
                warnings = result.Warnings,
                errors = result.Errors,
                component_detail_backends = XUUnityLightMcpUiComponentReaderRegistry.BackendIds(),
                screen_width = result.Target.screen_width,
                screen_height = result.Target.screen_height,
                render_width = result.Target.render_width,
                render_height = result.Target.render_height,
                render_target_available = true,
                render_target_differs_from_screen = result.Target.render_target_differs_from_screen,
                success = result.Errors.Count == 0
            };
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(snapshot);
            snapshot.proof_class = XUUnityLightMcpUiProofClass.Resolve(
                snapshot.success,
                result.Nodes.Count,
                result.Truncated,
                result.ComponentDetailsComplete);
            return snapshot;
        }

        public static bool TryValidateArgs(
            XUUnityLightMcpPrefabRenderArgs args,
            out int width,
            out int height,
            out XUUnityLightMcpUiDiagnostic error)
        {
            width = args.width;
            height = args.height;
            error = null;

            if (width <= 0 || height <= 0)
            {
                error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_render_viewport_invalid",
                    "width and height must both be positive; pass the reference viewport.",
                    $"{width}x{height}");
                return false;
            }

            if (width > MAX_DIMENSION || height > MAX_DIMENSION)
            {
                error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_render_viewport_too_large",
                    $"width and height must each stay at or below {MAX_DIMENSION}.",
                    $"{width}x{height}");
                return false;
            }

            if (args.safeAreaTop + args.safeAreaBottom >= height
                || args.safeAreaLeft + args.safeAreaRight >= width)
            {
                error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_render_safe_area_invalid",
                    "The declared safe-area insets consume the whole viewport.",
                    $"{args.safeAreaLeft},{args.safeAreaTop},{args.safeAreaRight},{args.safeAreaBottom}");
                return false;
            }

            return true;
        }

        static int NormalizeAntiAliasing(int requested)
        {
            return requested switch
            {
                2 => 2,
                4 => 4,
                8 => 8,
                _ => 1
            };
        }

        public static Color ParseColor(string value)
        {
            var text = (value ?? "").Trim();
            if (string.IsNullOrEmpty(text))
            {
                return new Color(0f, 0f, 0f, 0f);
            }

            if (!text.StartsWith("#", StringComparison.Ordinal))
            {
                text = "#" + text;
            }

            return ColorUtility.TryParseHtmlString(text, out var parsed)
                ? parsed
                : new Color(0f, 0f, 0f, 0f);
        }

        static string ResolveOutputPath(XUUnityLightMcpPrefabRenderArgs args, XUUnityLightMcpPrefabLoadResult loaded)
        {
            var requested = (args.outputPath ?? "").Trim();
            if (!string.IsNullOrEmpty(requested))
            {
                return Path.IsPathRooted(requested)
                    ? requested
                    : Path.GetFullPath(Path.Combine(XUUnityLightMcpFileIpcPaths.ProjectRootPath, requested));
            }

            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            var name = Path.GetFileNameWithoutExtension(loaded.NormalizedPath);
            var stamp = DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ");
            return Path.Combine(
                XUUnityLightMcpFileIpcPaths.CapturesDirectory,
                $"prefab-render-{name}-{stamp}.png");
        }

        static XUUnityLightMcpResponse Respond(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpPrefabRenderPayload payload)
        {
            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                RegisteredOperationName,
                JsonUtility.ToJson(payload)
            );
        }
    }
}
