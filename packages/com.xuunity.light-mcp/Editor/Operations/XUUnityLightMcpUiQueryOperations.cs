using System;
using System.Collections.Generic;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal abstract class XUUnityLightMcpUiQueryOperationBase : IXUUnityLightMcpOperation
    {
        public abstract string OperationName { get; }

        protected virtual bool RequiresSelector => true;

        protected virtual bool RequiresSingleMatch => false;

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpUiQueryArgs()
                : JsonUtility.FromJson<XUUnityLightMcpUiQueryArgs>(request.args_json) ?? new XUUnityLightMcpUiQueryArgs();
            args.selector ??= new XUUnityLightMcpUiSelectorArgs();

            var payload = new XUUnityLightMcpUiQueryPayload
            {
                operation = OperationName,
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                generated_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                selector = args.selector,
                component_detail_backends = XUUnityLightMcpUiComponentReaderRegistry.BackendIds()
            };
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(payload);

            if (RequiresSelector && XUUnityLightMcpUiSelectorMatcher.IsEmpty(args.selector))
            {
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_selector_invalid",
                    "A selector with at least one constraint is required.",
                    "Supported fields: name, type, path, pathContains, textEquals, textContains, requireVisible, requireInteractable."));
                payload.proof_class = XUUnityLightMcpUiRead.ProofError;
                return Respond(request, payload);
            }

            var result = XUUnityLightMcpUiTreeBuilder.Build(new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = args.targetKind,
                TargetValue = args.targetValue,
                SceneName = args.sceneName,
                IncludeDontDestroyOnLoad = args.includeDontDestroyOnLoad,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = args.includeInactive,
                IncludeBounds = true,
                IncludeText = true
            });

            payload.target = result.Target;
            CopyEditorTruth(payload, payload.target);
            payload.scanned_node_count = result.Nodes.Count;
            payload.inactive_subtrees_skipped = result.InactiveSubtreesSkipped;
            payload.warnings = result.Warnings;
            payload.errors.AddRange(result.Errors);
            payload.out_of_scope = HasOutOfScopeDiagnostic(payload.errors) || HasOutOfScopeDiagnostic(payload.warnings);

            var matches = XUUnityLightMcpUiSelectorMatcher.Match(
                result.Nodes,
                args.selector,
                args.maxMatches,
                out var matchTruncated);

            payload.matches = matches;
            payload.match_count = matches.Count;
            payload.exists = matches.Count > 0;
            payload.ambiguous = matches.Count > 1;
            payload.truncated = matchTruncated || result.Truncated;
            payload.success = payload.errors.Count == 0;
            payload.proof_class = XUUnityLightMcpUiProofClass.Resolve(
                payload.success,
                result.Nodes.Count,
                payload.truncated,
                result.ComponentDetailsComplete);

            if (!result.ComponentDetailsComplete)
            {
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_component_details_unavailable",
                    "No uGUI component reader is registered; text and interactable selectors cannot match.",
                    "Install com.unity.ugui so the optional uGUI module compiles."));
            }

            if (payload.ambiguous)
            {
                payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "selector_ambiguous",
                    $"Selector matched {matches.Count} nodes.",
                    "Narrow the selector or set allowMany when several matches are expected."));
            }

            if (payload.match_count == 0 && payload.success)
            {
                var zeroMatch = BuildZeroMatchDiagnostic(args, payload);
                payload.out_of_scope = payload.out_of_scope || zeroMatch.code == "ui_target_out_of_scope";
                if (RequiresSingleMatch)
                {
                    payload.success = false;
                    payload.proof_class = XUUnityLightMcpUiRead.ProofError;
                    payload.errors.Add(zeroMatch);
                }
                else if (payload.out_of_scope || zeroMatch.code == "ui_scope_probe_incomplete")
                {
                    // Where zero matches are a legal answer, only a diagnostic that adds something beyond
                    // "match_count is 0" is worth attaching: the target is reachable elsewhere, or absence could
                    // not be established because the probe was cut short.
                    payload.warnings.Add(zeroMatch);
                }
            }

            if (RequiresSingleMatch && payload.success)
            {
                EnforceSingleMatch(args, payload);
            }

            if (payload.success)
            {
                Finalize(args, payload);
            }

            return Respond(request, payload);
        }

        static void CopyEditorTruth(XUUnityLightMcpUiQueryPayload payload, XUUnityLightMcpUiTargetInfo target)
        {
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(payload);
            payload.screen_width = target?.screen_width ?? 0;
            payload.screen_height = target?.screen_height ?? 0;
            payload.render_width = target?.render_width ?? 0;
            payload.render_height = target?.render_height ?? 0;
            payload.render_target_available = target != null && target.render_target_available;
            payload.render_target_differs_from_screen = target != null && target.render_target_differs_from_screen;
        }

        protected virtual void Finalize(XUUnityLightMcpUiQueryArgs args, XUUnityLightMcpUiQueryPayload payload)
        {
        }

        static bool HasOutOfScopeDiagnostic(List<XUUnityLightMcpUiDiagnostic> diagnostics)
        {
            foreach (var diagnostic in diagnostics)
            {
                if (string.Equals(diagnostic.code, "ui_target_out_of_scope", StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }

        static XUUnityLightMcpUiDiagnostic BuildZeroMatchDiagnostic(
            XUUnityLightMcpUiQueryArgs args,
            XUUnityLightMcpUiQueryPayload payload)
        {
            var owners = FindOwningScenesOutsideScope(args, payload, out var probeIncomplete);
            if (owners.Count == 0)
            {
                if (probeIncomplete)
                {
                    return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "ui_scope_probe_incomplete",
                        "The selector matched no node in the searched scope, and the wider-scope probe could not "
                        + "finish, so whether the node exists elsewhere is unknown.",
                        "Raise maxNodes and maxDepth, or narrow the scope with sceneName, then retry.");
                }

                return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_node_not_found",
                    "The selector matched no node in any loaded scene.");
            }

            var searched = string.Join(", ", payload.target.searched_scenes);
            var owning = string.Join(", ", owners);
            return XUUnityLightMcpUiTreeBuilder.Diagnostic(
                "ui_target_out_of_scope",
                $"The selector matched no node in the searched scope [{searched}], but it does match in [{owning}].",
                ResolveOutOfScopeRetry(args, owners[0]));
        }

        static string ResolveOutOfScopeRetry(XUUnityLightMcpUiQueryArgs args, string owningScene)
        {
            var kind = (args.targetKind ?? "").Trim();
            var rootBoundKind = string.Equals(kind, XUUnityLightMcpUiRead.TargetGameObjectName, StringComparison.Ordinal)
                || string.Equals(kind, XUUnityLightMcpUiRead.TargetGameObjectPath, StringComparison.Ordinal);

            // targetKind doubles as the root selector for the name and path kinds, so advising
            // targetKind=all_loaded_scenes there would discard targetValue and return an unrelated tree.
            return rootBoundKind
                ? $"Retry with sceneName={owningScene}, keeping targetKind={kind}."
                : $"Retry with targetKind=all_loaded_scenes, or sceneName={owningScene}.";
        }

        static List<string> FindOwningScenesOutsideScope(
            XUUnityLightMcpUiQueryArgs args,
            XUUnityLightMcpUiQueryPayload payload,
            out bool probeIncomplete)
        {
            var owners = new List<string>();
            probeIncomplete = false;
            if (payload.target == null || IsWidestScope(payload.target))
            {
                return owners;
            }

            // The probe must widen the scope, so it cannot carry targetKind: for the scope kinds that kind *is*
            // the scope, and probing active_scene again would find nothing new. Root-bound kinds are handled by
            // the advice instead, which never tells the operator to drop targetValue.
            var wide = XUUnityLightMcpUiTreeBuilder.Build(new XUUnityLightMcpUiTreeOptions
            {
                TargetKind = XUUnityLightMcpUiRead.TargetAllLoadedScenes,
                SceneName = "",
                IncludeDontDestroyOnLoad = true,
                MaxDepth = args.maxDepth,
                MaxNodes = args.maxNodes,
                IncludeInactive = args.includeInactive,
                IncludeBounds = false,
                IncludeText = true
            });

            var wideMatches = XUUnityLightMcpUiSelectorMatcher.Match(
                wide.Nodes,
                args.selector,
                args.maxMatches,
                out _);

            foreach (var node in wideMatches)
            {
                var scene = node.scene_name ?? "";
                if (scene.Length > 0 && !owners.Contains(scene) && !payload.target.searched_scenes.Contains(scene))
                {
                    owners.Add(scene);
                }
            }

            // A truncated probe, or a scene selector that matched several same-named scenes, cannot support
            // "no node in any loaded scene": the probe stopped early or the searched set is not identifiable.
            probeIncomplete = owners.Count == 0
                && (wide.Truncated || payload.target.scene_selector_ambiguous);
            return owners;
        }

        static bool IsWidestScope(XUUnityLightMcpUiTargetInfo target)
        {
            if (!string.Equals(
                    target.scene_scope,
                    XUUnityLightMcpUiRead.SceneScopeAllLoadedScenes,
                    StringComparison.Ordinal))
            {
                return false;
            }

            // DontDestroyOnLoad cannot be included in Edit Mode or when the probe failed, so requiring the flag
            // made every zero-match Edit Mode query pay a second full tree walk that could not find anything new.
            return target.dont_destroy_on_load_included
                || string.Equals(
                    target.dont_destroy_on_load_status,
                    XUUnityLightMcpUiRead.DontDestroyOnLoadEditModeUnavailable,
                    StringComparison.Ordinal)
                || string.Equals(
                    target.dont_destroy_on_load_status,
                    XUUnityLightMcpUiRead.DontDestroyOnLoadProbeFailed,
                    StringComparison.Ordinal)
                || string.Equals(
                    target.dont_destroy_on_load_status,
                    XUUnityLightMcpUiRead.DontDestroyOnLoadNotRequested,
                    StringComparison.Ordinal);
        }

        static void EnforceSingleMatch(XUUnityLightMcpUiQueryArgs args, XUUnityLightMcpUiQueryPayload payload)
        {
            if (payload.match_count == 0)
            {
                return;
            }

            if (payload.match_count > 1 && !args.allowMany)
            {
                payload.success = false;
                payload.proof_class = XUUnityLightMcpUiRead.ProofError;
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "selector_ambiguous",
                    $"The selector matched {payload.match_count} nodes; set allowMany to accept several."));
            }
        }

        XUUnityLightMcpResponse Respond(XUUnityLightMcpRequest request, XUUnityLightMcpUiQueryPayload payload)
        {
            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
        }
    }

    internal sealed class XUUnityLightMcpUiQueryOperation : XUUnityLightMcpUiQueryOperationBase
    {
        public override string OperationName => "unity.ui.query";
    }

    internal sealed class XUUnityLightMcpUiExistsOperation : XUUnityLightMcpUiQueryOperationBase
    {
        public override string OperationName => "unity.ui.exists";
    }

    internal sealed class XUUnityLightMcpUiGetTextOperation : XUUnityLightMcpUiQueryOperationBase
    {
        public override string OperationName => "unity.ui.get_text";

        protected override bool RequiresSingleMatch => true;

        protected override void Finalize(XUUnityLightMcpUiQueryArgs args, XUUnityLightMcpUiQueryPayload payload)
        {
            var texts = new List<string>();
            var missingText = new List<string>();
            foreach (var match in payload.matches)
            {
                if (match.has_text)
                {
                    texts.Add(match.text);
                    continue;
                }

                missingText.Add(match.path);
            }

            payload.texts = texts;
            if (texts.Count == 0)
            {
                payload.success = false;
                payload.proof_class = XUUnityLightMcpUiRead.ProofError;
                payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "ui_text_unavailable",
                    "The matched node exposes no semantic text.",
                    string.Join(", ", missingText)));
                return;
            }

            payload.has_text = true;
            payload.text = texts[0];
        }
    }

    internal sealed class XUUnityLightMcpUiGetBoundsOperation : XUUnityLightMcpUiQueryOperationBase
    {
        public override string OperationName => "unity.ui.get_bounds";

        protected override bool RequiresSingleMatch => true;

        protected override void Finalize(XUUnityLightMcpUiQueryArgs args, XUUnityLightMcpUiQueryPayload payload)
        {
            foreach (var match in payload.matches)
            {
                if (!match.has_bounds)
                {
                    continue;
                }

                payload.has_bounds = true;
                payload.bounds = match.bounds;
                return;
            }

            payload.success = false;
            payload.proof_class = XUUnityLightMcpUiRead.ProofError;
            payload.errors.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                "ui_bounds_unavailable",
                "The matched node has no RectTransform, so it has no screen-space bounds."));
        }
    }
}
