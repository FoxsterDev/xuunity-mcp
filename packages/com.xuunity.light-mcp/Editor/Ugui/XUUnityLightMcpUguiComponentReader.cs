using UnityEngine;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Ugui
{
    internal sealed class XUUnityLightMcpUguiComponentReader : IXUUnityLightMcpUiComponentReader
    {
        public string BackendId => "ugui";

        public bool TryDescribe(Component component, XUUnityLightMcpUiNode node)
        {
            var described = false;

            if (component is Graphic graphic)
            {
                described |= DescribeGraphic(graphic, node);
            }

            if (component is Selectable selectable)
            {
                node.interactable = node.interactable && selectable.IsInteractable();
                node.interactable_known = true;
                described = true;
            }

            if (component is Text text)
            {
                node.has_text = true;
                node.text = text.text ?? "";
                node.text_source = "UnityEngine.UI.Text";
                node.font = text.font != null ? text.font.name : "";
                node.font_resolved_status = text.font != null ? "resolved" : "unresolved";
                described = true;
            }

            if (component is InputField inputField)
            {
                node.has_text = true;
                node.text = inputField.text ?? "";
                node.text_source = "UnityEngine.UI.InputField";
                described = true;
            }

            if (component is Image image)
            {
                node.sprite = image.sprite != null ? image.sprite.name : "";
                described = true;
            }

            if (component is Button button)
            {
                var targetGraphic = button.targetGraphic;
                node.material_resolved_status = targetGraphic != null
                    ? node.material_resolved_status
                    : "target_graphic_missing";
                described = true;
            }

            if (component is Mask || component is RectMask2D)
            {
                node.clip_state = "clipper";
                described = true;
            }

            return described;
        }

        static bool DescribeGraphic(Graphic graphic, XUUnityLightMcpUiNode node)
        {
            node.raycast_target = graphic.raycastTarget;
            node.raycast_target_known = true;
            node.effective_alpha = Mathf.Clamp01(node.effective_alpha * graphic.color.a);
            node.visible = node.active_in_hierarchy && node.effective_alpha > 0f;
            DescribePointerTarget(graphic, node);

            var material = graphic.materialForRendering;
            node.material = material != null ? material.name : "";
            node.material_resolved_status = material != null ? "resolved" : "unresolved";
            node.clip_state = ResolveClipState(graphic, node);
            return true;
        }

        static void DescribePointerTarget(Graphic graphic, XUUnityLightMcpUiNode node)
        {
            if (!node.active_in_hierarchy || !node.has_bounds)
            {
                return;
            }

            node.pointer_target_status = XUUnityLightMcpUguiPointerTargeting.Evaluate(
                graphic,
                XUUnityLightMcpUiTreeBuilder.Centre(node.bounds),
                out _);
            node.pointer_targetable = node.pointer_target_status == XUUnityLightMcpUguiPointerTargeting.Targetable;
        }

        static string ResolveClipState(Graphic graphic, XUUnityLightMcpUiNode node)
        {
            var mask = graphic.GetComponentInParent<RectMask2D>();
            if (mask == null)
            {
                return "not_clipped";
            }

            node.clipped_by = mask.gameObject.name ?? "";
            var maskRectTransform = mask.transform as RectTransform;
            if (!node.has_bounds
                || maskRectTransform == null
                || !XUUnityLightMcpUiTreeBuilder.TryScreenRect(maskRectTransform, out var maskRect))
            {
                return "clipper_present";
            }

            var nodeMaxX = node.bounds.x + node.bounds.width;
            var nodeMaxY = node.bounds.y + node.bounds.height;
            var maskMaxX = maskRect.x + maskRect.width;
            var maskMaxY = maskRect.y + maskRect.height;
            var overlaps = nodeMaxX > maskRect.x
                           && node.bounds.x < maskMaxX
                           && nodeMaxY > maskRect.y
                           && node.bounds.y < maskMaxY;
            if (!overlaps)
            {
                return "fully_clipped";
            }

            var contained = node.bounds.x >= maskRect.x
                            && nodeMaxX <= maskMaxX
                            && node.bounds.y >= maskRect.y
                            && nodeMaxY <= maskMaxY;
            return contained ? "not_clipped" : "partially_clipped";
        }
    }
}
