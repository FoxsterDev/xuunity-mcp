using System;
using System.IO;
using System.Reflection;
using System.Threading;
using UnityEditor;
using UnityEditorInternal;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpGameViewUtility
    {
        const int RepaintSettlingDelayMs = 100;
        internal const string FixedResolutionSizeTypeName = "FixedResolution";
        internal const string AspectRatioSizeTypeName = "AspectRatio";
        internal const int TestEnvironmentTextLimit = 64;
        internal const string CaptureStatusCaptured = "captured";
        internal const string CaptureStatusNotRendered = "game_view_not_rendered";
        internal const string CaptureStatusNoGameView = "no_game_view";
        internal const string CaptureStatusUnavailable = "unavailable";
        internal const string PresetKindFixedResolution = "fixed_resolution";
        internal const string PresetKindAspectRatio = "aspect_ratio";
        internal const string PresetKindFree = "free";
        internal const string PresetKindUnknown = "unknown";
        static readonly BindingFlags AllBindings = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

        public static XUUnityLightMcpGameViewProbeResult ProbeReflectionSurface()
        {
            try
            {
                var gameViewType = RequireType("UnityEditor.GameView,UnityEditor");
                RequireProperty(gameViewType, "currentGameViewSize");
                RequireProperty(gameViewType, "selectedSizeIndex");
                RequireField(gameViewType, "m_RenderTexture");

                var gameViewSizesType = RequireType("UnityEditor.GameViewSizes,UnityEditor");
                var groupEnumType = RequireType("UnityEditor.GameViewSizeGroupType,UnityEditor");
                var sizeTypeEnum = RequireType("UnityEditor.GameViewSizeType,UnityEditor");
                var sizeType = RequireType("UnityEditor.GameViewSize,UnityEditor");

                RequireMethod(gameViewSizesType, "GetGroup");
                RequireProperty(sizeType, "width");
                RequireProperty(sizeType, "height");
                RequireProperty(sizeType, "baseText");
                var sizeTypeProperty = RequireProperty(sizeType, "sizeType");
                if (sizeTypeProperty.PropertyType != sizeTypeEnum)
                {
                    throw new InvalidOperationException(
                        $"Property 'sizeType' on {sizeType.FullName} is {sizeTypeProperty.PropertyType.FullName} instead of {sizeTypeEnum.FullName}.");
                }
                RequireConstructor(sizeType, new[] { sizeTypeEnum, typeof(int), typeof(int), typeof(string) });

                var instance = GetGameViewSizesInstance();
                if (!TryResolveActiveGroupType(out var groupEnumValue, out var groupResolutionFailure))
                {
                    throw new InvalidOperationException(groupResolutionFailure);
                }
                if (!groupEnumType.IsInstanceOfType(groupEnumValue))
                {
                    throw new InvalidOperationException(
                        $"Active Unity Game View size group resolved to '{groupEnumValue.GetType().FullName}' instead of {groupEnumType.FullName}.");
                }
                var groupObject = gameViewSizesType.GetMethod("GetGroup", AllBindings)?.Invoke(instance, new[] { groupEnumValue });
                if (groupObject == null)
                {
                    throw new InvalidOperationException("Unable to resolve Unity Game View size group instance.");
                }

                var groupType = groupObject.GetType();
                RequireMethod(groupType, "GetBuiltinCount");
                RequireMethod(groupType, "GetCustomCount");
                RequireMethod(groupType, "GetGameViewSize");
                RequireMethod(groupType, "AddCustomSize");

                return new XUUnityLightMcpGameViewProbeResult
                {
                    adapter_id = "game_view_reflection_v1",
                    supported = true,
                    reason = ""
                };
            }
            catch (Exception ex)
            {
                return new XUUnityLightMcpGameViewProbeResult
                {
                    adapter_id = "game_view_reflection_v1",
                    supported = false,
                    reason = ex.Message
                };
            }
        }

        public static EditorWindow EnsureGameView()
        {
            try
            {
                if (!EditorApplication.ExecuteMenuItem("Window/General/Game"))
                {
                    EditorApplication.ExecuteMenuItem("Window/General/Game %2");
                }
            }
            catch
            {
            }

            var gameViewType = RequireType("UnityEditor.GameView,UnityEditor");
            var window = EditorWindow.GetWindow(gameViewType, false, null, false);
            if (window == null)
            {
                throw new InvalidOperationException("Unable to open Unity Game View window.");
            }

            try
            {
                window.Focus();
            }
            catch
            {
            }

            window.Repaint();
            try
            {
                SceneView.RepaintAll();
                InternalEditorUtility.RepaintAllViews();
                EditorApplication.QueuePlayerLoopUpdate();
            }
            catch
            {
            }

            Thread.Sleep(RepaintSettlingDelayMs);
            return window;
        }

        public static XUUnityLightMcpGameViewData GetCurrentGameViewData()
        {
            var gameView = EnsureGameView();
            var gameViewType = gameView.GetType();
            var currentSize = gameViewType.GetProperty("currentGameViewSize", AllBindings)?.GetValue(gameView, null);
            if (currentSize == null)
            {
                throw new InvalidOperationException("Unable to resolve current Unity Game View size.");
            }

            return BuildSizeData(currentSize, GetActiveGroupName(), false);
        }

        public static bool TryGetExistingRenderTargetSize(out int width, out int height)
        {
            return TryGetExistingRenderTarget(out _, out width, out height);
        }

        // A bridge EditorApplication.update callback can observe editor-window Screen dimensions.
        // Let the existing Game View complete its native event boundary before projecting UI or
        // calling GraphicRaycaster. This never changes the preset, zoom, or pointer position.
        public static bool TrySynchronizeScreenContext(out string status)
        {
            if (!TryGetExistingRenderTarget(out var gameView, out var width, out var height))
            {
                status = "no_existing_game_view";
                return true;
            }

            if (Screen.width == width && Screen.height == height)
            {
                status = "already_aligned";
                return true;
            }

            try
            {
                gameView.SendEvent(new Event
                {
                    type = EventType.ExecuteCommand,
                    commandName = "XUUnityMcpSynchronizeScreenContext"
                });
            }
            catch
            {
                status = "game_view_context_unresolved";
                return false;
            }

            var aligned = Screen.width == width && Screen.height == height;
            status = aligned ? "game_view_synchronized" : "game_view_context_unresolved";
            return aligned;
        }

        static bool TryGetExistingRenderTarget(out EditorWindow window, out int width, out int height)
        {
            window = null;
            width = 0;
            height = 0;
            try
            {
                var gameViewType = Type.GetType("UnityEditor.GameView,UnityEditor");
                var renderTextureField = gameViewType?.GetField("m_RenderTexture", AllBindings);
                if (gameViewType == null || renderTextureField == null)
                {
                    return false;
                }

                var lastFocusedProperty = gameViewType.GetProperty("lastFocusedGameView", AllBindings);
                var lastFocusedGetter = lastFocusedProperty?.GetGetMethod(true);
                var lastFocused = lastFocusedGetter != null && lastFocusedGetter.IsStatic
                    ? lastFocusedProperty.GetValue(null, null)
                    : null;
                if (TryReadRenderTargetSize(lastFocused, renderTextureField, out width, out height))
                {
                    window = lastFocused as EditorWindow;
                    return true;
                }

                var focusedWindow = EditorWindow.focusedWindow;
                if (gameViewType.IsInstanceOfType(focusedWindow)
                    && TryReadRenderTargetSize(focusedWindow, renderTextureField, out width, out height))
                {
                    window = focusedWindow;
                    return true;
                }

                foreach (var candidate in Resources.FindObjectsOfTypeAll(gameViewType))
                {
                    if (TryReadRenderTargetSize(candidate, renderTextureField, out width, out height))
                    {
                        window = candidate as EditorWindow;
                        return true;
                    }
                }
            }
            catch
            {
            }

            return false;
        }

        // Request-start evidence only: never opens, focuses or repaints a window and never sleeps.
        internal static XUUnityLightMcpTestEnvironment CaptureTestEnvironment()
        {
            var environment = new XUUnityLightMcpTestEnvironment
            {
                captured_at = "request_start",
                capture_status = CaptureStatusUnavailable
            };

            try
            {
                environment.build_target = BoundTestEnvironmentText(EditorUserBuildSettings.activeBuildTarget.ToString());
                environment.game_view_group = BoundTestEnvironmentText(GetActiveGroupName());
            }
            catch
            {
            }

            try
            {
                var gameViewType = Type.GetType("UnityEditor.GameView,UnityEditor");
                if (gameViewType == null || gameViewType.GetField("m_RenderTexture", AllBindings) == null)
                {
                    return environment;
                }

                object presetSource;
                if (TryGetExistingRenderTarget(out var renderedWindow, out var renderWidth, out var renderHeight))
                {
                    environment.capture_status = CaptureStatusCaptured;
                    environment.render_width = renderWidth;
                    environment.render_height = renderHeight;
                    presetSource = renderedWindow;
                }
                else
                {
                    presetSource = FindExistingGameView(gameViewType);
                    environment.capture_status = presetSource == null ? CaptureStatusNoGameView : CaptureStatusNotRendered;
                }

                if (presetSource != null)
                {
                    var sizeObject = gameViewType.GetProperty("currentGameViewSize", AllBindings)?.GetValue(presetSource, null);
                    if (sizeObject == null)
                    {
                        ApplyPresetToTestEnvironment(environment, "", "", 0, 0);
                    }
                    else
                    {
                        var label = ReadStringProperty(sizeObject, "baseText");
                        if (string.IsNullOrWhiteSpace(label))
                        {
                            label = ReadStringProperty(sizeObject, "displayText");
                        }

                        ApplyPresetToTestEnvironment(
                            environment,
                            label,
                            ReadSizeTypeName(sizeObject),
                            ReadIntProperty(sizeObject, "width"),
                            ReadIntProperty(sizeObject, "height"));
                    }
                }
            }
            catch
            {
                environment.capture_status = CaptureStatusUnavailable;
                environment.render_width = 0;
                environment.render_height = 0;
                environment.preset_label = "";
                environment.preset_kind = "";
                environment.preset_width = 0;
                environment.preset_height = 0;
                environment.render_matches_preset = "";
            }

            return environment;
        }

        internal static void ApplyPresetToTestEnvironment(
            XUUnityLightMcpTestEnvironment environment,
            string label,
            string sizeTypeName,
            int width,
            int height)
        {
            var kind = ClassifyPresetKind(sizeTypeName, width, height);
            var isFixed = kind == PresetKindFixedResolution;
            environment.preset_label = BoundTestEnvironmentText(label);
            environment.preset_kind = kind;
            environment.preset_width = isFixed ? width : 0;
            environment.preset_height = isFixed ? height : 0;
            environment.render_matches_preset =
                isFixed && environment.capture_status == CaptureStatusCaptured
                        && environment.render_width > 0 && environment.render_height > 0
                    ? (environment.render_width == width && environment.render_height == height ? "true" : "false")
                    : "";
        }

        internal static string ClassifyPresetKind(string sizeTypeName, int width, int height)
        {
            if (string.Equals(sizeTypeName, FixedResolutionSizeTypeName, StringComparison.Ordinal))
            {
                return width > 0 && height > 0 ? PresetKindFixedResolution : PresetKindUnknown;
            }

            if (string.Equals(sizeTypeName, AspectRatioSizeTypeName, StringComparison.Ordinal))
            {
                return width <= 0 && height <= 0 ? PresetKindFree : PresetKindAspectRatio;
            }

            return PresetKindUnknown;
        }

        internal static bool IsFixedResolutionMatch(string sizeTypeName, int width, int height, int targetWidth, int targetHeight)
        {
            return width == targetWidth
                && height == targetHeight
                && ClassifyPresetKind(sizeTypeName, width, height) == PresetKindFixedResolution;
        }

        internal static bool IsAspectRatioShapeMatch(string sizeTypeName, int width, int height, int targetWidth, int targetHeight)
        {
            return width == targetWidth
                && height == targetHeight
                && ClassifyPresetKind(sizeTypeName, width, height) == PresetKindAspectRatio;
        }

        internal static string DescribeMissingFixedResolution(int width, int height, string groupName, string aspectRatioLabel)
        {
            var message = $"Game View fixed resolution {width}x{height} is not available in the active group '{groupName}'. ";
            if (aspectRatioLabel != null)
            {
                var name = string.IsNullOrWhiteSpace(aspectRatioLabel) ? "" : $" '{aspectRatioLabel}'";
                message += $"An aspect-ratio preset{name} of that shape exists but is not a fixed resolution. ";
            }

            return message + "Re-run with allowCreateCustomSize=true if persistent editor user-state changes are acceptable.";
        }

        internal static string BoundTestEnvironmentText(string value)
        {
            var text = (value ?? "").Trim();
            if (text.Length <= TestEnvironmentTextLimit)
            {
                return text;
            }

            var cut = TestEnvironmentTextLimit;
            if (char.IsHighSurrogate(text[cut - 1]))
            {
                cut--;
            }

            return text.Substring(0, cut);
        }

        static UnityEngine.Object FindExistingGameView(Type gameViewType)
        {
            var lastFocusedGetter = gameViewType.GetProperty("lastFocusedGameView", AllBindings)?.GetGetMethod(true);
            if (lastFocusedGetter != null
                && lastFocusedGetter.IsStatic
                && lastFocusedGetter.Invoke(null, null) is UnityEngine.Object lastFocused
                && lastFocused != null)
            {
                return lastFocused;
            }

            var existing = Resources.FindObjectsOfTypeAll(gameViewType);
            return existing != null && existing.Length > 0 ? existing[0] : null;
        }

        static bool TryReadRenderTargetSize(object candidate, FieldInfo renderTextureField, out int width, out int height)
        {
            width = 0;
            height = 0;
            var renderTexture = candidate == null ? null : renderTextureField.GetValue(candidate) as RenderTexture;
            if (renderTexture == null || !renderTexture.IsCreated())
            {
                return false;
            }

            width = renderTexture.width;
            height = renderTexture.height;
            return width > 0 && height > 0;
        }

        public static XUUnityLightMcpGameViewData SetFixedResolution(
            int width,
            int height,
            string requestedGroup,
            string requestedLabel,
            bool allowCreateCustomSize)
        {
            if (width < 1 || height < 1)
            {
                throw new InvalidOperationException("Game View width and height must both be greater than zero.");
            }

            if (!TryResolveActiveGroupType(out var activeGroupType, out var groupResolutionFailure))
            {
                throw new InvalidOperationException(groupResolutionFailure);
            }

            var activeGroupName = DescribeGroupType(activeGroupType);
            if (!string.IsNullOrWhiteSpace(requestedGroup) && !GroupNameMatches(requestedGroup, activeGroupName))
            {
                throw new InvalidOperationException(
                    $"Requested Game View group '{requestedGroup}' does not match the active build group '{activeGroupName}'.");
            }

            var label = string.IsNullOrWhiteSpace(requestedLabel)
                ? $"XUUnity {width}x{height}"
                : requestedLabel.Trim();

            var groupObject = GetGameViewGroup(activeGroupType);
            var matchIndex = FindFixedResolutionIndex(groupObject, width, height, out var aspectRatioLabel);
            var createdCustom = false;
            if (matchIndex < 0)
            {
                if (!allowCreateCustomSize)
                {
                    throw new InvalidOperationException(
                        DescribeMissingFixedResolution(width, height, activeGroupName, aspectRatioLabel));
                }

                AddCustomSize(groupObject, width, height, label);
                matchIndex = FindFixedResolutionIndex(groupObject, width, height, out _);
                createdCustom = true;
            }

            if (matchIndex < 0)
            {
                throw new InvalidOperationException($"Unable to add or select Game View fixed resolution {width}x{height}.");
            }

            var gameView = EnsureGameView();
            var selectedSizeIndex = gameView.GetType().GetProperty("selectedSizeIndex", AllBindings);
            if (selectedSizeIndex == null)
            {
                throw new InvalidOperationException("Unity Game View does not expose selectedSizeIndex in this editor version.");
            }

            selectedSizeIndex.SetValue(gameView, matchIndex, null);
            gameView.Repaint();
            InternalEditorUtility.RepaintAllViews();
            EditorApplication.QueuePlayerLoopUpdate();
            Thread.Sleep(RepaintSettlingDelayMs);

            var current = GetCurrentGameViewData();
            current.is_custom = createdCustom;
            if (string.IsNullOrWhiteSpace(current.label))
            {
                current.label = label;
            }
            return current;
        }

        public static XUUnityLightMcpGameViewScreenshotPayload CaptureScreenshot(
            string requestId,
            string fileName,
            bool includeImage,
            int maxResolution,
            int imageBudgetBytes)
        {
            var gameView = EnsureGameView();
            var gameViewType = gameView.GetType();
            var rtField = gameViewType.GetField("m_RenderTexture", AllBindings);
            var sourceRt = rtField?.GetValue(gameView) as RenderTexture;
            if (sourceRt == null || !sourceRt.IsCreated())
            {
                throw new InvalidOperationException(
                    "Game View render texture is not available. Ensure the Game View window is open and visible.");
            }

            var safeFileName = SanitizeFileName(fileName);
            var fullPath = BuildCapturePath(requestId, safeFileName);

            var width = sourceRt.width;
            var height = sourceRt.height;
            var previousActive = RenderTexture.active;
            Texture2D captured = null;
            Texture2D inlineTexture = null;
            try
            {
                RenderTexture.active = sourceRt;
                captured = new Texture2D(width, height, TextureFormat.RGB24, false);
                captured.ReadPixels(new Rect(0, 0, width, height), 0, 0);

                if (SystemInfo.graphicsUVStartsAtTop)
                {
                    FlipTextureVertically(captured);
                }

                captured.Apply();
                File.WriteAllBytes(fullPath, captured.EncodeToPNG());

                var budget = imageBudgetBytes > 0
                    ? imageBudgetBytes
                    : XUUnityLightMcpGameView.DefaultImageBudgetBytes;
                var imageBase64 = "";
                var imageBytes = 0;
                var omittedReason = XUUnityLightMcpGameView.ImageOmittedNotRequested;
                if (includeImage)
                {
                    inlineTexture = DownscaleIfNeeded(captured, maxResolution);
                    var inlineBytes = inlineTexture.EncodeToPNG();
                    imageBytes = inlineBytes?.Length ?? 0;
                    if (imageBytes > 0 && imageBytes <= budget)
                    {
                        imageBase64 = Convert.ToBase64String(inlineBytes);
                        omittedReason = "";
                    }
                    else
                    {
                        omittedReason = XUUnityLightMcpGameView.ImageOmittedPayloadBudget;
                    }
                }

                return new XUUnityLightMcpGameViewScreenshotPayload
                {
                    project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                    file_path = fullPath,
                    width = width,
                    height = height,
                    render_width = width,
                    render_height = height,
                    screen_width = Screen.width,
                    screen_height = Screen.height,
                    render_target_available = true,
                    render_target_differs_from_screen = width != Screen.width || height != Screen.height,
                    image_base64 = imageBase64,
                    image_included = imageBase64.Length > 0,
                    image_requested = includeImage,
                    image_omitted_reason = omittedReason,
                    image_bytes = imageBytes,
                    image_budget_bytes = budget,
                    recommended_next_action = XUUnityLightMcpGameView.ImageFilePathNextAction
                };
            }
            finally
            {
                RenderTexture.active = previousActive;
                if (inlineTexture != null && !ReferenceEquals(inlineTexture, captured))
                {
                    UnityEngine.Object.DestroyImmediate(inlineTexture);
                }
                if (captured != null)
                {
                    UnityEngine.Object.DestroyImmediate(captured);
                }
            }
        }

        static string GetActiveGroupName()
        {
            return TryResolveActiveGroupType(out var groupType, out _)
                ? DescribeGroupType(groupType)
                : "";
        }

        internal static bool GroupNameMatches(string requestedGroup, string activeGroupName)
        {
            if (string.Equals(requestedGroup, activeGroupName, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            return IsLegacyIosGroupAlias(requestedGroup) && IsLegacyIosGroupAlias(activeGroupName);
        }

        static bool IsLegacyIosGroupAlias(string groupName)
        {
            return string.Equals(groupName, "iOS", StringComparison.OrdinalIgnoreCase) ||
                   string.Equals(groupName, "iPhone", StringComparison.OrdinalIgnoreCase);
        }

        internal static string DescribeGroupType(object groupType)
        {
            if (groupType == null)
            {
                return "";
            }

            var name = Enum.GetName(groupType.GetType(), groupType);
            return string.IsNullOrEmpty(name) ? Convert.ToString(groupType) : name;
        }

        static object GetGameViewSizesInstance()
        {
            var gameViewSizesType = RequireType("UnityEditor.GameViewSizes,UnityEditor");
            var scriptableSingletonType = RequireType("UnityEditor.ScriptableSingleton`1,UnityEditor").MakeGenericType(gameViewSizesType);
            var instance = scriptableSingletonType.GetProperty("instance", AllBindings)?.GetValue(null, null);
            if (instance == null)
            {
                throw new InvalidOperationException("Unable to access Unity GameViewSizes singleton.");
            }

            return instance;
        }

        static bool TryResolveActiveGroupType(out object groupType, out string failureReason)
        {
            groupType = null;
            failureReason = "";
            try
            {
                var instance = GetGameViewSizesInstance();
                groupType = instance.GetType().GetProperty("currentGroupType", AllBindings)?.GetValue(instance, null);
                if (groupType != null)
                {
                    return true;
                }

                groupType = ConvertActiveBuildTargetToGroupType(out var converterReason);
                if (groupType != null)
                {
                    return true;
                }

                failureReason =
                    "Unable to resolve the active Unity Game View size group: GameViewSizes.currentGroupType is " +
                    "unavailable and " + converterReason;
                return false;
            }
            catch (Exception ex)
            {
                groupType = null;
                failureReason = $"Unable to resolve the active Unity Game View size group: {ex.Message}";
                return false;
            }
        }

        internal static object ConvertActiveBuildTargetToGroupType(out string failureReason)
        {
            failureReason = "";
            var gameViewSizesType = RequireType("UnityEditor.GameViewSizes,UnityEditor");
            var converter = gameViewSizesType.GetMethod("BuildTargetGroupToGameViewSizeGroup", AllBindings);
            var parameters = converter?.GetParameters();
            if (converter == null || parameters == null || parameters.Length != 1)
            {
                failureReason = "GameViewSizes.BuildTargetGroupToGameViewSizeGroup is not present with a single parameter.";
                return null;
            }

            var activeTarget = EditorUserBuildSettings.activeBuildTarget;
            var parameterType = parameters[0].ParameterType;
            object argument;
            if (parameterType == typeof(BuildTarget))
            {
                argument = activeTarget;
            }
            else if (parameterType == typeof(BuildTargetGroup))
            {
                argument = BuildPipeline.GetBuildTargetGroup(activeTarget);
            }
            else
            {
                failureReason =
                    $"GameViewSizes.BuildTargetGroupToGameViewSizeGroup takes an unexpected '{parameterType.FullName}'.";
                return null;
            }

            var converted = converter.Invoke(null, new[] { argument });
            if (converted == null)
            {
                failureReason = "GameViewSizes.BuildTargetGroupToGameViewSizeGroup returned null.";
            }
            return converted;
        }

        static object GetGameViewGroup(object groupType)
        {
            if (groupType == null)
            {
                throw new InvalidOperationException("Unable to access Unity Game View size group: no active group resolved.");
            }

            var gameViewSizesType = RequireType("UnityEditor.GameViewSizes,UnityEditor");
            var instance = GetGameViewSizesInstance();
            var getGroup = gameViewSizesType.GetMethod("GetGroup", AllBindings);
            var groupObject = getGroup?.Invoke(instance, new[] { groupType });
            if (groupObject == null)
            {
                throw new InvalidOperationException(
                    $"Unable to access Unity Game View size group '{DescribeGroupType(groupType)}'.");
            }

            return groupObject;
        }

        static int FindFixedResolutionIndex(object groupObject, int width, int height, out string aspectRatioLabel)
        {
            aspectRatioLabel = null;
            var groupType = groupObject.GetType();
            var getBuiltinCount = groupType.GetMethod("GetBuiltinCount", AllBindings);
            var getCustomCount = groupType.GetMethod("GetCustomCount", AllBindings);
            var getGameViewSize = groupType.GetMethod("GetGameViewSize", AllBindings);

            if (getBuiltinCount == null || getCustomCount == null || getGameViewSize == null)
            {
                throw new InvalidOperationException("Unity Game View size group reflection surface changed.");
            }

            var total = (int)getBuiltinCount.Invoke(groupObject, null) + (int)getCustomCount.Invoke(groupObject, null);
            for (var index = 0; index < total; index++)
            {
                var sizeObject = getGameViewSize.Invoke(groupObject, new object[] { index });
                if (sizeObject == null)
                {
                    continue;
                }

                var sizeTypeName = ReadSizeTypeName(sizeObject);
                var currentWidth = ReadIntProperty(sizeObject, "width");
                var currentHeight = ReadIntProperty(sizeObject, "height");
                if (IsFixedResolutionMatch(sizeTypeName, currentWidth, currentHeight, width, height))
                {
                    return index;
                }

                if (aspectRatioLabel == null
                    && IsAspectRatioShapeMatch(sizeTypeName, currentWidth, currentHeight, width, height))
                {
                    aspectRatioLabel = ReadStringProperty(sizeObject, "baseText");
                }
            }

            return -1;
        }

        static void AddCustomSize(object groupObject, int width, int height, string label)
        {
            var gameViewSizeType = RequireType("UnityEditor.GameViewSize,UnityEditor");
            var sizeTypeEnum = RequireType("UnityEditor.GameViewSizeType,UnityEditor");
            var fixedResolution = Enum.Parse(sizeTypeEnum, FixedResolutionSizeTypeName, true);
            var constructor = gameViewSizeType.GetConstructor(AllBindings, null,
                new[] { sizeTypeEnum, typeof(int), typeof(int), typeof(string) }, null);
            if (constructor == null)
            {
                throw new InvalidOperationException("Unity GameViewSize constructor signature changed.");
            }

            var newSize = constructor.Invoke(new object[] { fixedResolution, width, height, label });
            var addCustomSize = groupObject.GetType().GetMethod("AddCustomSize", AllBindings);
            if (addCustomSize == null)
            {
                throw new InvalidOperationException("Unity Game View size group no longer exposes AddCustomSize.");
            }

            addCustomSize.Invoke(groupObject, new[] { newSize });
        }

        static XUUnityLightMcpGameViewData BuildSizeData(object sizeObject, string groupName, bool isCustom)
        {
            var width = ReadIntProperty(sizeObject, "width");
            var height = ReadIntProperty(sizeObject, "height");
            return new XUUnityLightMcpGameViewData
            {
                group = groupName,
                label = ReadStringProperty(sizeObject, "baseText"),
                width = width,
                height = height,
                is_custom = isCustom,
                preset_kind = ClassifyPresetKind(ReadSizeTypeName(sizeObject), width, height)
            };
        }

        static string ReadSizeTypeName(object sizeObject)
        {
            return Convert.ToString(sizeObject.GetType().GetProperty("sizeType", AllBindings)?.GetValue(sizeObject, null)) ?? "";
        }

        static int ReadIntProperty(object instance, string propertyName)
        {
            var value = instance.GetType().GetProperty(propertyName, AllBindings)?.GetValue(instance, null);
            return value is int intValue ? intValue : 0;
        }

        static string ReadStringProperty(object instance, string propertyName)
        {
            var value = instance.GetType().GetProperty(propertyName, AllBindings)?.GetValue(instance, null);
            return value as string ?? "";
        }

        static string BuildCapturePath(string requestId, string fileName)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            var timestamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
            var finalFileName = string.IsNullOrWhiteSpace(fileName)
                ? $"game-view-{timestamp}.png"
                : fileName;

            if (!finalFileName.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            {
                finalFileName += ".png";
            }

            var fullPath = Path.Combine(XUUnityLightMcpFileIpcPaths.CapturesDirectory, finalFileName);
            if (!File.Exists(fullPath))
            {
                return fullPath;
            }

            var suffix = string.IsNullOrWhiteSpace(requestId) ? Guid.NewGuid().ToString("N")[..8] : requestId[..Math.Min(8, requestId.Length)];
            var baseName = Path.GetFileNameWithoutExtension(finalFileName);
            return Path.Combine(XUUnityLightMcpFileIpcPaths.CapturesDirectory, $"{baseName}-{suffix}.png");
        }

        static string SanitizeFileName(string fileName)
        {
            if (string.IsNullOrWhiteSpace(fileName))
            {
                return "";
            }

            var sanitized = fileName.Trim();
            foreach (var invalid in Path.GetInvalidFileNameChars())
            {
                sanitized = sanitized.Replace(invalid, '_');
            }
            return sanitized;
        }

        static Texture2D DownscaleIfNeeded(Texture2D source, int maxResolution)
        {
            var limit = maxResolution > 0 ? maxResolution : 640;
            if (source.width <= limit && source.height <= limit)
            {
                return source;
            }

            var scale = Mathf.Min(limit / (float)source.width, limit / (float)source.height);
            var targetWidth = Mathf.Max(1, Mathf.RoundToInt(source.width * scale));
            var targetHeight = Mathf.Max(1, Mathf.RoundToInt(source.height * scale));

            var rt = RenderTexture.GetTemporary(targetWidth, targetHeight, 0, RenderTextureFormat.ARGB32);
            var previousActive = RenderTexture.active;
            try
            {
                Graphics.Blit(source, rt);
                RenderTexture.active = rt;
                var resized = new Texture2D(targetWidth, targetHeight, TextureFormat.RGBA32, false);
                resized.ReadPixels(new Rect(0, 0, targetWidth, targetHeight), 0, 0);
                resized.Apply();
                return resized;
            }
            finally
            {
                RenderTexture.active = previousActive;
                RenderTexture.ReleaseTemporary(rt);
            }
        }

        static void FlipTextureVertically(Texture2D texture)
        {
            var width = texture.width;
            var height = texture.height;
            var pixels = texture.GetPixels32();
            var flipped = new Color32[pixels.Length];
            for (var y = 0; y < height; y++)
            {
                var srcRow = y * width;
                var dstRow = (height - 1 - y) * width;
                Array.Copy(pixels, srcRow, flipped, dstRow, width);
            }
            texture.SetPixels32(flipped);
        }

        static Type RequireType(string typeName)
        {
            var type = Type.GetType(typeName);
            if (type == null)
            {
                throw new InvalidOperationException($"Required Unity editor type not found: {typeName}");
            }
            return type;
        }

        static PropertyInfo RequireProperty(Type type, string propertyName)
        {
            var property = type.GetProperty(propertyName, AllBindings);
            if (property == null)
            {
                throw new InvalidOperationException($"Required property '{propertyName}' not found on {type.FullName}.");
            }

            return property;
        }

        static FieldInfo RequireField(Type type, string fieldName)
        {
            var field = type.GetField(fieldName, AllBindings);
            if (field == null)
            {
                throw new InvalidOperationException($"Required field '{fieldName}' not found on {type.FullName}.");
            }

            return field;
        }

        static MethodInfo RequireMethod(Type type, string methodName)
        {
            var method = type.GetMethod(methodName, AllBindings);
            if (method == null)
            {
                throw new InvalidOperationException($"Required method '{methodName}' not found on {type.FullName}.");
            }

            return method;
        }

        static ConstructorInfo RequireConstructor(Type type, Type[] argumentTypes)
        {
            var constructor = type.GetConstructor(AllBindings, null, argumentTypes, null);
            if (constructor == null)
            {
                throw new InvalidOperationException($"Required constructor not found on {type.FullName}.");
            }

            return constructor;
        }
    }
}
