using System;
using System.Collections.Generic;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpUiSelectorMatcher
    {
        public static bool IsEmpty(XUUnityLightMcpUiSelectorArgs selector)
        {
            if (selector == null)
            {
                return true;
            }

            return string.IsNullOrWhiteSpace(selector.name)
                   && string.IsNullOrWhiteSpace(selector.type)
                   && string.IsNullOrWhiteSpace(selector.path)
                   && string.IsNullOrWhiteSpace(selector.pathContains)
                   && string.IsNullOrWhiteSpace(selector.textEquals)
                   && string.IsNullOrWhiteSpace(selector.textContains)
                   && !selector.requireVisible
                   && !selector.requireInteractable;
        }

        public static List<XUUnityLightMcpUiNode> Match(
            IReadOnlyList<XUUnityLightMcpUiNode> nodes,
            XUUnityLightMcpUiSelectorArgs selector,
            int maxMatches,
            out bool truncated)
        {
            truncated = false;
            var matches = new List<XUUnityLightMcpUiNode>();
            if (nodes == null)
            {
                return matches;
            }

            var limit = Math.Max(1, maxMatches);
            foreach (var node in nodes)
            {
                if (!Matches(node, selector))
                {
                    continue;
                }

                if (matches.Count >= limit)
                {
                    truncated = true;
                    break;
                }

                matches.Add(node);
            }

            return matches;
        }

        public static bool Matches(XUUnityLightMcpUiNode node, XUUnityLightMcpUiSelectorArgs selector)
        {
            if (node == null)
            {
                return false;
            }

            if (selector == null)
            {
                return true;
            }

            var comparison = selector.caseInsensitiveText
                ? StringComparison.OrdinalIgnoreCase
                : StringComparison.Ordinal;

            if (!string.IsNullOrWhiteSpace(selector.name)
                && !string.Equals(node.name, selector.name.Trim(), StringComparison.Ordinal))
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(selector.path)
                && !string.Equals(node.path, selector.path.Trim(), StringComparison.Ordinal))
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(selector.pathContains)
                && node.path.IndexOf(selector.pathContains.Trim(), StringComparison.Ordinal) < 0)
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(selector.type) && !HasComponentType(node, selector.type.Trim()))
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(selector.textEquals))
            {
                if (!node.has_text || !string.Equals(node.text, selector.textEquals, comparison))
                {
                    return false;
                }
            }

            if (!string.IsNullOrWhiteSpace(selector.textContains))
            {
                if (!node.has_text || node.text.IndexOf(selector.textContains, comparison) < 0)
                {
                    return false;
                }
            }

            if (selector.requireVisible && !node.visible && !node.visible_via_descendant)
            {
                return false;
            }

            if (selector.requireInteractable && !node.interactable)
            {
                return false;
            }

            return true;
        }

        static bool HasComponentType(XUUnityLightMcpUiNode node, string type)
        {
            if (string.Equals(node.type, type, StringComparison.Ordinal))
            {
                return true;
            }

            foreach (var component in node.components)
            {
                if (string.Equals(component, type, StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }
    }
}
