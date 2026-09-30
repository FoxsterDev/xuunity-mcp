using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Ugui
{
    internal sealed class XUUnityLightMcpUiClickOperation : IXUUnityLightMcpOperation
    {
        public const string RegisteredOperationName = "unity.ui.click";

        public string OperationName => RegisteredOperationName;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpUiClickArgs()
                : JsonUtility.FromJson<XUUnityLightMcpUiClickArgs>(request.args_json) ?? new XUUnityLightMcpUiClickArgs();
            args.selector ??= new XUUnityLightMcpUiSelectorArgs();

            var payload = new XUUnityLightMcpUiClickPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                generated_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                requested_action = (args.action ?? "").Trim().ToLowerInvariant(),
                selector = args.selector
            };
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(payload);

            if (!string.Equals(payload.requested_action, "click", StringComparison.Ordinal))
            {
                return Refuse(
                    request,
                    payload,
                    "ui_action_not_permitted",
                    "Only the explicit action 'click' is permitted by this operation.");
            }

            if (!args.approve)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_click_approval_required",
                    "Set approve=true to deliver a real pointer click; this operation mutates runtime UI state.");
            }

            if (XUUnityLightMcpUiSelectorMatcher.IsEmpty(args.selector))
            {
                return Refuse(
                    request,
                    payload,
                    "ui_selector_invalid",
                    "A selector with at least one constraint is required.");
            }

            var before = XUUnityLightMcpUiTreeBuilder.Build(new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = args.targetKind,
                TargetValue = args.targetValue,
                SceneName = args.sceneName,
                IncludeDontDestroyOnLoad = args.includeDontDestroyOnLoad,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = true,
                IncludeBounds = true,
                IncludeText = true
            });
            payload.before_snapshot = Summarize(before);
            payload.search_target = before.Target;
            CopyRenderEvidence(payload, before.Target);
            payload.search_node_count = before.Nodes.Count;
            payload.search_max_depth = Math.Max(1, args.maxDepth);
            payload.search_max_nodes = Math.Max(1, args.maxNodes);
            payload.search_truncated = before.Truncated;
            payload.search_truncation_reason = before.TruncationReason;
            payload.warnings.AddRange(before.Warnings);

            foreach (var diagnostic in before.Errors)
            {
                if (string.Equals(diagnostic.code, "ui_target_out_of_scope", StringComparison.Ordinal))
                {
                    return Refuse(request, payload, diagnostic.code, $"{diagnostic.message} {diagnostic.detail}".Trim());
                }
            }

            // The root-canvas out-of-scope case arrives as a warning, not an error, so a click that dropped
            // warnings refused with a bare "matched no node" and told the operator nothing about where it lives.
            foreach (var diagnostic in before.Warnings)
            {
                if (string.Equals(diagnostic.code, "ui_target_out_of_scope", StringComparison.Ordinal))
                {
                    return Refuse(request, payload, diagnostic.code, $"{diagnostic.message} {diagnostic.detail}".Trim());
                }
            }

            var matches = XUUnityLightMcpUiSelectorMatcher.Match(before.Nodes, args.selector, 8, out _);
            if (before.Truncated)
            {
                payload.match_count = matches.Count;
                var matchEvidence = matches.Count == 0
                    ? "The selector matched no node in the scanned prefix, so absence is unproven."
                    : $"The selector matched {matches.Count} node(s) in the scanned prefix, so uniqueness is unproven.";
                var scopeGap = XUUnityLightMcpUiTreeBuilder.DescribeSearchedScope(before.Target);
                return Refuse(
                    request,
                    payload,
                    "ui_selector_search_truncated",
                    $"{matchEvidence} The search scanned {before.Nodes.Count} node(s) "
                    + $"with maxDepth={payload.search_max_depth} and maxNodes={payload.search_max_nodes} "
                    + $"and stopped because {before.TruncationReason}. {scopeGap} "
                    + "Narrow targetKind/targetValue or sceneName, or raise maxDepth/maxNodes, then retry.");
            }

            if (matches.Count == 0)
            {
                var scopeGap = XUUnityLightMcpUiTreeBuilder.DescribeSearchedScope(before.Target);
                return Refuse(
                    request,
                    payload,
                    "ui_node_not_found",
                    $"The selector matched no node. {scopeGap}".Trim());
            }

            if (matches.Count > 1)
            {
                payload.match_count = matches.Count;
                return Refuse(
                    request,
                    payload,
                    "selector_ambiguous",
                    $"The selector matched {matches.Count} nodes; a click target must be unique.");
            }

            var node = matches[0];
            payload.match_count = 1;
            payload.target_node = node;

            if (!node.active_in_hierarchy)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_not_visible",
                    "The target is inactive in the hierarchy, so a click would not be reachable by a user.");
            }

            var targetTransform = before.ResolveTransform(node);
            var targetObject = targetTransform != null ? targetTransform.gameObject : null;
            if (targetObject == null)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_not_found",
                    $"The matched path '{node.path}' could not be resolved back to a live GameObject.");
            }

            var selectable = targetObject.GetComponent<Selectable>();
            payload.target_component = selectable != null ? selectable.GetType().Name : "";
            var interactable = node.interactable && (selectable == null || selectable.IsInteractable());
            var handler = ExecuteEvents.GetEventHandler<IPointerClickHandler>(targetObject);
            var pointerPosition = XUUnityLightMcpUiTreeBuilder.Centre(node.bounds);
            var pointerTarget = XUUnityLightMcpUguiPointerTargeting.FindHandlerPointerTarget(
                targetObject,
                handler,
                pointerPosition,
                out var targetStatus,
                out var targetBlockedBy);
            payload.pointer_target_status = pointerTarget != null
                ? XUUnityLightMcpUguiPointerTargeting.Targetable
                : targetStatus;
            payload.pointer_target_blocked_by = pointerTarget == null && targetBlockedBy != null
                ? XUUnityLightMcpUiTreeBuilder.BuildPath(targetBlockedBy.transform)
                : "";

            // A hidden target keeps the pre-existing refusal unless a real pointer would reach a live handler.
            if (!node.visible && (pointerTarget == null || handler == null || !interactable))
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_not_visible",
                    "The target is hidden and no interactable click handler is reachable through a raycast target, "
                    + $"so a user could not click it. {DescribeTargetStatus(payload)}");
            }

            if (!interactable)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_not_interactable",
                    "The target is not interactable; delivering a click would fake user reachability.");
            }

            if (handler == null)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_has_no_click_handler",
                    "No IPointerClickHandler is present on the target or its ancestors.");
            }

            if (pointerTarget == null)
            {
                return RefuseNotPointerTargetable(request, payload, handler);
            }

            payload.pointer_targetable = true;
            payload.pointer_target_path = XUUnityLightMcpUiTreeBuilder.BuildPath(pointerTarget.transform);
            DescribeTransparentHitArea(payload, pointerTarget);

            var eventSystem = EventSystem.current;
            payload.event_system_present = eventSystem != null;
            payload.event_system_scope = "eventsystem_current_at_delivery";

            var pointer = BuildClickPointer(eventSystem, pointerPosition);

            var observed = ResolvePointerRaycast(eventSystem, pointer, handler, out var hitCount, out var occluder);
            payload.pointer_raycast_hit_count = hitCount;
            if (occluder != null)
            {
                payload.occluded_by_path = XUUnityLightMcpUiTreeBuilder.BuildPath(occluder.transform);
                payload.pointer_raycast_evidence = "event_system_raycast_hit_other_handler";
                return Refuse(
                    request,
                    payload,
                    "ui_target_occluded",
                    $"A live event-system raycast at the target's centre hit '{payload.occluded_by_path}', which resolves to a "
                    + "different click handler, so a real pointer would never reach this target. "
                    + "Dismiss or disable the occluding element and retry.");
            }

            if (observed.HasValue)
            {
                pointer.pointerCurrentRaycast = observed.Value;
                payload.pointer_raycast_evidence = "event_system_raycast_resolves_to_handler";
            }
            else
            {
                pointer.pointerCurrentRaycast = SynthesizeRaycast(handler.gameObject, pointerPosition);
                payload.pointer_raycast_evidence = eventSystem == null
                    ? "synthesized_no_event_system"
                    : "synthesized_no_raycast_hit";
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_click_pointer_raycast_synthesized",
                    "No live event-system raycast hit was available at the target's centre, so the pointer event carries a "
                    + "synthesized raycast naming the resolved handler. The click is delivered and handlers that validate "
                    + "pointerCurrentRaycast identity accept it, but occlusion by another element was not ruled out."));
            }

            pointer.pointerPressRaycast = pointer.pointerCurrentRaycast;
            pointer.pointerEnter = pointer.pointerCurrentRaycast.gameObject;
            pointer.pointerPress = pointer.pointerCurrentRaycast.gameObject;
            pointer.rawPointerPress = pointer.pointerCurrentRaycast.gameObject;
            payload.pointer_raycast_target_path = pointer.pointerCurrentRaycast.gameObject != null
                ? XUUnityLightMcpUiTreeBuilder.BuildPath(pointer.pointerCurrentRaycast.gameObject.transform)
                : "";

            payload.delivered_to_path = XUUnityLightMcpUiTreeBuilder.BuildPath(handler.transform);
            payload.delivered = ExecuteEvents.Execute(handler, pointer, ExecuteEvents.pointerClickHandler);
            payload.delivery_mechanism = "event_system_pointer_click_handler";

            var after = XUUnityLightMcpUiTreeBuilder.Build(new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = args.targetKind,
                TargetValue = args.targetValue,
                SceneName = args.sceneName,
                IncludeDontDestroyOnLoad = args.includeDontDestroyOnLoad,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = true,
                IncludeBounds = true,
                IncludeText = true
            });
            payload.after_snapshot = Summarize(after);
            payload.state_changed = !string.Equals(
                payload.before_snapshot.signature,
                payload.after_snapshot.signature,
                StringComparison.Ordinal);
            payload.effective = payload.delivered && payload.state_changed;
            payload.no_observable_effect = payload.delivered && !payload.state_changed;

            payload.success = payload.effective;
            payload.status = payload.effective
                ? "effective"
                : payload.delivered
                    ? "delivered_no_observable_effect"
                    : "not_delivered";
            payload.proof_class = payload.effective
                ? XUUnityLightMcpUiRead.ProofSemanticTree
                : XUUnityLightMcpUiRead.ProofSemanticPartial;
            if (!payload.delivered)
            {
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_click_not_delivered",
                    "The event system accepted the target but no handler consumed the click."));
            }
            else if (payload.no_observable_effect)
            {
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_click_no_state_change",
                    "The handler consumed the pointer event, but the UI tree did not change. "
                    + "The event carries a pointerCurrentRaycast naming "
                    + $"'{payload.pointer_raycast_target_path}' ({payload.pointer_raycast_evidence}), so a handler that "
                    + "validates raycast identity was satisfied; the effect may only be visible in logs or non-UI state. "
                    + "Verify with a UI query, an anchored log assertion, or a project-defined hook that calls the "
                    + "production API."));
            }

            return Respond(request, payload);
        }

        static PointerEventData BuildClickPointer(EventSystem eventSystem, Vector2 position)
        {
            return new PointerEventData(eventSystem)
            {
                pointerId = -1,
                button = PointerEventData.InputButton.Left,
                position = position,
                pressPosition = position,
                clickCount = 1,
                clickTime = Time.unscaledTime,
                eligibleForClick = true,
                useDragThreshold = true,
                dragging = false
            };
        }

        static RaycastResult? ResolvePointerRaycast(
            EventSystem eventSystem,
            PointerEventData pointer,
            GameObject handler,
            out int hitCount,
            out GameObject occluder)
        {
            hitCount = 0;
            occluder = null;
            if (eventSystem == null)
            {
                return null;
            }

            var hits = new List<RaycastResult>();
            try
            {
                eventSystem.RaycastAll(pointer, hits);
            }
            catch (Exception)
            {
                return null;
            }

            RaycastResult? top = null;
            for (var i = 0; i < hits.Count; i++)
            {
                if (hits[i].gameObject == null)
                {
                    continue;
                }
                hitCount++;
                if (top == null)
                {
                    top = hits[i];
                }
            }

            if (top == null)
            {
                return null;
            }

            if (ExecuteEvents.GetEventHandler<IPointerClickHandler>(top.Value.gameObject) == handler)
            {
                return top;
            }

            occluder = top.Value.gameObject;
            return null;
        }

        static RaycastResult SynthesizeRaycast(GameObject target, Vector2 position)
        {
            return new RaycastResult
            {
                gameObject = target,
                module = target != null ? target.GetComponentInParent<BaseRaycaster>() : null,
                screenPosition = position,
                worldPosition = target != null ? target.transform.position : Vector3.zero,
                worldNormal = -Vector3.forward,
                distance = 0f,
                index = 0f,
                depth = 0
            };
        }

        static string DescribeTargetStatus(XUUnityLightMcpUiClickPayload payload)
        {
            var blockedByText = payload.pointer_target_blocked_by.Length > 0
                ? $" (blocked by '{payload.pointer_target_blocked_by}')"
                : "";
            return $"The target reports {payload.pointer_target_status}{blockedByText}.";
        }

        static XUUnityLightMcpResponse RefuseNotPointerTargetable(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpUiClickPayload payload,
            GameObject handler)
        {
            var evidence = $"{DescribeTargetStatus(payload)} No Graphic under "
                           + $"'{XUUnityLightMcpUiTreeBuilder.BuildPath(handler.transform)}' accepts a pointer at the "
                           + "target's centre.";

            if (payload.pointer_target_status == XUUnityLightMcpUguiPointerTargeting.CanvasGroupBlocksRaycasts)
            {
                return Refuse(
                    request,
                    payload,
                    "ui_target_does_not_block_raycasts",
                    "A CanvasGroup does not block raycasts, so a real pointer would pass through the target. "
                    + evidence);
            }

            return Refuse(
                request,
                payload,
                "ui_target_not_pointer_targetable",
                "A real pointer at the target's centre would not reach its click handler. " + evidence);
        }

        static void DescribeTransparentHitArea(XUUnityLightMcpUiClickPayload payload, Graphic pointerTarget)
        {
            if (XUUnityLightMcpUguiPointerTargeting.Renders(pointerTarget))
            {
                return;
            }

            payload.transparent_hit_area = true;
            foreach (var graphic in pointerTarget.GetComponentsInChildren<Graphic>())
            {
                if (graphic != pointerTarget && XUUnityLightMcpUguiPointerTargeting.Renders(graphic))
                {
                    payload.transparent_hit_area_evidence = "visible_descendant_renders";
                    payload.transparent_hit_area_visible_path = XUUnityLightMcpUiTreeBuilder.BuildPath(graphic.transform);
                    return;
                }
            }

            payload.transparent_hit_area_evidence = "no_visible_descendant";
            payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                "ui_click_transparent_hit_area_without_visible_content",
                $"'{payload.pointer_target_path}' is a transparent hit area with no rendered descendant, so a user "
                + "would be tapping empty screen. Unity still raycasts it and the click is delivered; confirm the "
                + "target is meant to be an invisible hit area."));
        }

        static void CopyRenderEvidence(XUUnityLightMcpUiClickPayload payload, XUUnityLightMcpUiTargetInfo target)
        {
            payload.screen_width = target?.screen_width ?? 0;
            payload.screen_height = target?.screen_height ?? 0;
            payload.render_width = target?.render_width ?? 0;
            payload.render_height = target?.render_height ?? 0;
            payload.render_target_available = target != null && target.render_target_available;
            payload.render_target_differs_from_screen = target != null && target.render_target_differs_from_screen;
        }

        static XUUnityLightMcpUiClickSnapshotRef Summarize(XUUnityLightMcpUiTreeResult result)
        {
            var summary = new XUUnityLightMcpUiClickSnapshotRef
            {
                node_count = result.Nodes.Count,
                truncated = result.Truncated,
                truncation_reason = result.TruncationReason
            };

            var builder = new System.Text.StringBuilder();
            foreach (var node in result.Nodes)
            {
                builder.Append(node.path);
                builder.Append('|');
                builder.Append(node.active_in_hierarchy ? '1' : '0');
                builder.Append(node.visible ? '1' : '0');
                builder.Append(node.interactable ? '1' : '0');
                builder.Append(node.text);
                builder.Append(';');
            }

            summary.signature = XUUnityLightMcpUiClickSnapshotRef.Hash(builder.ToString());
            return summary;
        }

        static XUUnityLightMcpResponse Refuse(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpUiClickPayload payload,
            string code,
            string message)
        {
            payload.success = false;
            payload.delivered = false;
            payload.effective = false;
            payload.no_observable_effect = false;
            payload.status = "refused";
            payload.refusal_code = code;
            payload.proof_class = XUUnityLightMcpUiRead.ProofError;
            payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(code, message));
            return Respond(request, payload);
        }

        static XUUnityLightMcpResponse Respond(
            XUUnityLightMcpRequest request,
            XUUnityLightMcpUiClickPayload payload)
        {
            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                RegisteredOperationName,
                JsonUtility.ToJson(payload)
            );
        }
    }
}
