using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Experimental.Rendering;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Ugui
{
    /// <summary>GraphicRaycaster and Graphic.Raycast filters; render alpha is not one of them.</summary>
    internal static class XUUnityLightMcpUguiPointerTargeting
    {
        public const string Targetable = "targetable";
        public const string GraphicInactive = "graphic_inactive";
        public const string RaycastTargetDisabled = "raycast_target_disabled";
        public const string NoActiveCanvas = "no_active_canvas";
        public const string NoRaycaster = "no_raycaster";
        public const string CanvasRendererCulled = "canvas_renderer_culled";
        public const string OutsideRaycastArea = "outside_raycast_area";
        public const string CanvasGroupBlocksRaycasts = "canvas_group_blocks_raycasts";
        public const string AlphaHitTestRejected = "alpha_hit_test_rejected";
        public const string RaycastFilterRejected = "raycast_filter_rejected";
        public const string NoTargetableGraphic = "no_pointer_targetable_graphic";

        static readonly List<Component> ComponentBuffer = new();

        public static string Evaluate(Graphic graphic, Vector2 screenPoint, out Component blockedBy)
        {
            blockedBy = null;
            if (!graphic.isActiveAndEnabled)
            {
                return GraphicInactive;
            }

            if (!graphic.raycastTarget)
            {
                return RaycastTargetDisabled;
            }

            var canvas = graphic.canvas;
            if (canvas == null)
            {
                return NoActiveCanvas;
            }

            var raycaster = canvas.GetComponent<BaseRaycaster>();
            if (raycaster == null || !raycaster.isActiveAndEnabled)
            {
                blockedBy = canvas;
                return NoRaycaster;
            }

            var canvasRenderer = graphic.GetComponent<CanvasRenderer>();
            if (canvasRenderer != null && canvasRenderer.cull)
            {
                blockedBy = canvasRenderer;
                return CanvasRendererCulled;
            }

            var rectTransform = graphic.rectTransform;
            var eventCamera = XUUnityLightMcpUiTreeBuilder.ResolveEventCamera(rectTransform);
            if (!RectTransformUtility.RectangleContainsScreenPoint(
                    rectTransform,
                    screenPoint,
                    eventCamera,
                    graphic.raycastPadding))
            {
                return OutsideRaycastArea;
            }

            return EvaluateRaycastFilters(graphic.transform, screenPoint, eventCamera, out blockedBy);
        }

        /// <summary>
        /// The target's own Graphic, else any Graphic under the handler whose click bubbles to it.
        /// </summary>
        public static Graphic FindHandlerPointerTarget(
            GameObject target,
            GameObject handler,
            Vector2 screenPoint,
            out string targetStatus,
            out Component targetBlockedBy)
        {
            var own = target.GetComponent<Graphic>();
            if (own != null)
            {
                targetStatus = Evaluate(own, screenPoint, out targetBlockedBy);
                if (targetStatus == Targetable)
                {
                    return own;
                }
            }
            else
            {
                var eventCamera = XUUnityLightMcpUiTreeBuilder.ResolveEventCamera(target.transform as RectTransform);
                var chain = EvaluateRaycastFilters(target.transform, screenPoint, eventCamera, out targetBlockedBy);
                targetStatus = chain == Targetable ? NoTargetableGraphic : chain;
            }

            if (handler == null)
            {
                return null;
            }

            foreach (var graphic in handler.GetComponentsInChildren<Graphic>())
            {
                if (graphic == own
                    || ExecuteEvents.GetEventHandler<IPointerClickHandler>(graphic.gameObject) != handler)
                {
                    continue;
                }

                if (Evaluate(graphic, screenPoint, out _) == Targetable)
                {
                    return graphic;
                }
            }

            return null;
        }

        public static bool Renders(Graphic graphic)
        {
            if (!graphic.isActiveAndEnabled || graphic.color.a <= 0f)
            {
                return false;
            }

            var canvasRenderer = graphic.GetComponent<CanvasRenderer>();
            if (canvasRenderer != null
                && (canvasRenderer.cull || canvasRenderer.GetAlpha() <= 0f || canvasRenderer.GetColor().a <= 0f))
            {
                return false;
            }

            return XUUnityLightMcpUiTreeBuilder.ResolveCanvasGroupAlpha(graphic.transform) > 0f;
        }

        static string EvaluateRaycastFilters(
            Transform start,
            Vector2 screenPoint,
            Camera eventCamera,
            out Component blockedBy)
        {
            blockedBy = null;
            var ignoreParentGroups = false;
            var continueTraversal = true;
            for (var current = start; current != null; current = continueTraversal ? current.parent : null)
            {
                current.GetComponents(ComponentBuffer);
                foreach (var component in ComponentBuffer)
                {
                    if (component is Canvas canvas && canvas.overrideSorting)
                    {
                        continueTraversal = false;
                    }

                    if (component is not ICanvasRaycastFilter filter)
                    {
                        continue;
                    }

                    if (component is CanvasGroup group)
                    {
                        if (!group.enabled || ignoreParentGroups)
                        {
                            continue;
                        }

                        ignoreParentGroups = group.ignoreParentGroups;
                        if (!group.blocksRaycasts)
                        {
                            blockedBy = group;
                            return CanvasGroupBlocksRaycasts;
                        }

                        continue;
                    }

                    if (!IsRaycastLocationValid(component, filter, screenPoint, eventCamera))
                    {
                        blockedBy = component;
                        return component is Image ? AlphaHitTestRejected : RaycastFilterRejected;
                    }
                }
            }

            return Targetable;
        }

        static bool IsRaycastLocationValid(
            Component component,
            ICanvasRaycastFilter filter,
            Vector2 screenPoint,
            Camera eventCamera)
        {
            if (component is Image image
                && image.alphaHitTestMinimumThreshold > 0f
                && image.alphaHitTestMinimumThreshold <= 1f)
            {
                // Unity accepts an unsampleable texture after logging an error; skip the call to keep reads silent.
                var sprite = image.overrideSprite;
                var texture = sprite != null ? sprite.texture : null;
                if (sprite != null
                    && (texture == null || !texture.isReadable || GraphicsFormatUtility.IsCrunchFormat(texture.format)))
                {
                    return true;
                }
            }

            return filter.IsRaycastLocationValid(screenPoint, eventCamera);
        }
    }
}
