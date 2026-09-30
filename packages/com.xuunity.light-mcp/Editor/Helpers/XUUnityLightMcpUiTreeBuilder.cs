using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpUiTreeOptions
    {
        public string TargetKind = XUUnityLightMcpUiRead.TargetActiveScene;
        public string TargetValue = "";
        public string SceneName = "";
        public bool IncludeDontDestroyOnLoad = true;
        public int MaxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int MaxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public bool IncludeInactive;
        public bool IncludeBounds = true;
        public bool IncludeText = true;
    }

    internal sealed class XUUnityLightMcpUiTreeResult
    {
        public XUUnityLightMcpUiTargetInfo Target = new();
        public List<XUUnityLightMcpUiNode> Nodes = new();
        public List<Transform> NodeTransforms = new();
        public List<string> RootPaths = new();
        public List<XUUnityLightMcpUiDiagnostic> Warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> Errors = new();
        public bool Truncated;
        public string TruncationReason = "";
        public bool ComponentDetailsComplete = true;

        public Transform ResolveTransform(XUUnityLightMcpUiNode node)
        {
            if (node == null)
            {
                return null;
            }

            var index = Nodes.IndexOf(node);
            if (index < 0 || index >= NodeTransforms.Count)
            {
                return null;
            }

            return NodeTransforms[index];
        }
    }

    internal sealed class XUUnityLightMcpUiSceneScope
    {
        public List<Scene> Searched = new();
        public List<Scene> AllLoaded = new();
        public string Kind = XUUnityLightMcpUiRead.SceneScopeActiveScene;
        public bool DontDestroyOnLoadSearched;
        public string DontDestroyOnLoadStatus = XUUnityLightMcpUiRead.DontDestroyOnLoadNotRequested;
        public bool RequestedSceneMissing;
        public bool RequestedSceneAmbiguous;

        public bool IsNarrowerThanAllLoaded => Searched.Count < AllLoaded.Count;
    }

    internal static class XUUnityLightMcpUiTreeBuilder
    {
        static readonly Vector3[] WorldCorners = new Vector3[4];

        public static XUUnityLightMcpUiTreeResult Build(XUUnityLightMcpUiTreeOptions options)
        {
            var result = new XUUnityLightMcpUiTreeResult();
            var effective = options ?? new XUUnityLightMcpUiTreeOptions();
            var maxDepth = Math.Max(1, effective.MaxDepth);
            var maxNodes = Math.Max(1, effective.MaxNodes);

            result.Target.kind = string.IsNullOrWhiteSpace(effective.TargetKind)
                ? XUUnityLightMcpUiRead.TargetActiveScene
                : effective.TargetKind.Trim();
            result.Target.requested_value = effective.TargetValue ?? "";
            result.Target.backend = XUUnityLightMcpUiRead.BackendUgui;
            result.Target.backend_status = XUUnityLightMcpUiComponentReaderRegistry.HasReaders
                ? "component_details_available"
                : "transform_only";
            result.Target.capture_width = Screen.width;
            result.Target.capture_height = Screen.height;
            result.Target.screen_width = Screen.width;
            result.Target.screen_height = Screen.height;
            result.Target.render_target_available = XUUnityLightMcpGameViewUtility.TryGetExistingRenderTargetSize(
                out result.Target.render_width,
                out result.Target.render_height);
            result.Target.render_target_differs_from_screen = result.Target.render_target_available
                && (result.Target.render_width != result.Target.screen_width
                    || result.Target.render_height != result.Target.screen_height);
            result.Target.requested_scene_name = (effective.SceneName ?? "").Trim();

            var scope = ResolveSceneScope(result, effective);
            var roots = ResolveRoots(result, effective, scope);
            result.Target.resolved_root_count = roots.Count;
            if (roots.Count == 0)
            {
                return result;
            }

            for (var i = 0; i < roots.Count; i++)
            {
                var root = roots[i];
                if (root == null)
                {
                    continue;
                }

                var rootPath = BuildPath(root.transform);
                result.RootPaths.Add(rootPath);
                Traverse(
                    root.transform,
                    rootPath,
                    "",
                    0,
                    i,
                    maxDepth,
                    maxNodes,
                    effective,
                    result);

                if (result.Truncated)
                {
                    RecordScenesNotReached(result, roots, i);
                    break;
                }
            }

            return result;
        }

        /// <summary>
        /// Name the scenes the walk never got to. Roots share one node budget and are walked in scope order, so
        /// truncation stops the walk wherever the budget ran out — and `DontDestroyOnLoad` is appended last, so it
        /// is the first scope to vanish on a real tree. `searched_scenes` still lists every scene in scope, which
        /// read as "all of these were searched". The budget semantics stay as they are; the claim stops being
        /// wrong.
        /// </summary>
        static void RecordScenesNotReached(
            XUUnityLightMcpUiTreeResult result,
            List<GameObject> roots,
            int lastWalkedIndex)
        {
            var reached = new List<string>();
            for (var i = 0; i <= lastWalkedIndex && i < roots.Count; i++)
            {
                if (roots[i] == null)
                {
                    continue;
                }

                var name = DescribeScene(roots[i].scene);
                if (name.Length > 0 && !reached.Contains(name))
                {
                    reached.Add(name);
                }
            }

            for (var i = lastWalkedIndex + 1; i < roots.Count; i++)
            {
                if (roots[i] == null)
                {
                    continue;
                }

                var name = DescribeScene(roots[i].scene);
                if (name.Length > 0
                    && !reached.Contains(name)
                    && !result.Target.scenes_not_reached.Contains(name))
                {
                    result.Target.scenes_not_reached.Add(name);
                }
            }

            if (result.Target.scenes_not_reached.Count == 0)
            {
                return;
            }

            result.Warnings.Add(Diagnostic(
                "ui_scope_truncated_before_all_scenes",
                $"The node budget was spent before reaching {string.Join(", ", result.Target.scenes_not_reached)}, "
                + "so those scenes were listed in searched_scenes but never walked.",
                "Raise maxNodes, or set sceneName to the scene you need so the budget is spent there."));
        }

        static XUUnityLightMcpUiSceneScope ResolveSceneScope(
            XUUnityLightMcpUiTreeResult result,
            XUUnityLightMcpUiTreeOptions options)
        {
            var scope = new XUUnityLightMcpUiSceneScope();
            for (var i = 0; i < SceneManager.sceneCount; i++)
            {
                var scene = SceneManager.GetSceneAt(i);
                if (scene.IsValid() && scene.isLoaded)
                {
                    scope.AllLoaded.Add(scene);
                }
            }

            if (options.IncludeDontDestroyOnLoad)
            {
                if (!Application.isPlaying)
                {
                    scope.DontDestroyOnLoadStatus = XUUnityLightMcpUiRead.DontDestroyOnLoadEditModeUnavailable;
                }
                else if (TryResolveDontDestroyOnLoadScene(out var dontDestroyScene))
                {
                    scope.AllLoaded.Add(dontDestroyScene);
                    scope.DontDestroyOnLoadStatus = XUUnityLightMcpUiRead.DontDestroyOnLoadIncluded;
                }
                else
                {
                    scope.DontDestroyOnLoadStatus = XUUnityLightMcpUiRead.DontDestroyOnLoadProbeFailed;
                }
            }

            var requestedScene = (options.SceneName ?? "").Trim();
            var wantsAllLoaded = string.Equals(
                result.Target.kind,
                XUUnityLightMcpUiRead.TargetAllLoadedScenes,
                StringComparison.Ordinal);

            if (requestedScene.Length > 0)
            {
                scope.Kind = XUUnityLightMcpUiRead.SceneScopeNamedScene;
                foreach (var scene in scope.AllLoaded)
                {
                    if (MatchesSceneSelector(scene, requestedScene))
                    {
                        scope.Searched.Add(scene);
                    }
                }

                scope.RequestedSceneMissing = scope.Searched.Count == 0;
                scope.RequestedSceneAmbiguous = scope.Searched.Count > 1;
            }
            else if (wantsAllLoaded)
            {
                scope.Kind = XUUnityLightMcpUiRead.SceneScopeAllLoadedScenes;
                scope.Searched.AddRange(scope.AllLoaded);
            }
            else
            {
                scope.Kind = XUUnityLightMcpUiRead.SceneScopeActiveScene;
                var active = SceneManager.GetActiveScene();
                if (active.IsValid())
                {
                    scope.Searched.Add(active);
                }
            }

            foreach (var scene in scope.Searched)
            {
                if (IsDontDestroyOnLoadScene(scene))
                {
                    scope.DontDestroyOnLoadSearched = true;
                    break;
                }
            }

            ApplyScopeToTarget(result, scope);
            return scope;
        }

        static string ResolveDontDestroyOnLoadStatus(XUUnityLightMcpUiSceneScope scope)
        {
            if (scope.DontDestroyOnLoadSearched)
            {
                return XUUnityLightMcpUiRead.DontDestroyOnLoadIncluded;
            }

            return scope.DontDestroyOnLoadStatus == XUUnityLightMcpUiRead.DontDestroyOnLoadIncluded
                ? XUUnityLightMcpUiRead.DontDestroyOnLoadOutOfScope
                : scope.DontDestroyOnLoadStatus;
        }

        static void ApplyScopeToTarget(XUUnityLightMcpUiTreeResult result, XUUnityLightMcpUiSceneScope scope)
        {
            result.Target.scene_scope = scope.Kind;
            result.Target.dont_destroy_on_load_included = scope.DontDestroyOnLoadSearched;
            result.Target.dont_destroy_on_load_status = ResolveDontDestroyOnLoadStatus(scope);
            result.Target.scene_selector_ambiguous = scope.RequestedSceneAmbiguous;

            foreach (var scene in scope.Searched)
            {
                result.Target.searched_scenes.Add(DescribeScene(scene));
            }

            foreach (var scene in scope.AllLoaded)
            {
                result.Target.loaded_scenes.Add(DescribeScene(scene));
            }

            if (scope.RequestedSceneAmbiguous)
            {
                var paths = new List<string>();
                foreach (var scene in scope.Searched)
                {
                    paths.Add(scene.path ?? "");
                }

                result.Warnings.Add(Diagnostic(
                    "ui_scene_selector_ambiguous",
                    $"sceneName '{result.Target.requested_scene_name}' matches {scope.Searched.Count} loaded "
                    + $"scenes: {string.Join(", ", paths)}.",
                    "Pass the scene path instead of the name so the scope names one scene."));
            }

            // Naming a scene that was never searched made a typo'd sceneName report the active scene as its
            // target, so scene identity stays empty unless exactly one scene was searched.
            if (scope.Searched.Count == 1 && scope.Searched[0].IsValid())
            {
                result.Target.scene_name = scope.Searched[0].name ?? "";
                result.Target.scene_path = scope.Searched[0].path ?? "";
            }
        }

        static List<GameObject> ResolveRoots(
            XUUnityLightMcpUiTreeResult result,
            XUUnityLightMcpUiTreeOptions options,
            XUUnityLightMcpUiSceneScope scope)
        {
            var kind = result.Target.kind;
            var value = (options.TargetValue ?? "").Trim();

            if (string.Equals(kind, XUUnityLightMcpUiRead.TargetPrefabAsset, StringComparison.Ordinal))
            {
                result.Errors.Add(Diagnostic(
                    "ui_target_not_found",
                    "Prefab targets are served by unity.prefab.snapshot, not the scene UI tree."));
                return new List<GameObject>();
            }

            if (scope.RequestedSceneMissing)
            {
                result.Errors.Add(Diagnostic(
                    "ui_target_out_of_scope",
                    $"No loaded scene matches sceneName '{result.Target.requested_scene_name}'.",
                    DescribeScopeGap(scope)));
                return new List<GameObject>();
            }

            if (scope.Searched.Count == 0)
            {
                result.Errors.Add(Diagnostic("ui_target_not_found", "No valid loaded scene to search."));
                return new List<GameObject>();
            }

            if (string.Equals(kind, XUUnityLightMcpUiRead.TargetGameObjectPath, StringComparison.Ordinal))
            {
                return ResolveByPath(result, scope, value, options.IncludeInactive);
            }

            if (string.Equals(kind, XUUnityLightMcpUiRead.TargetGameObjectName, StringComparison.Ordinal))
            {
                return ResolveByName(result, scope, value, options.IncludeInactive);
            }

            return ResolveRootCanvases(result, scope, options.IncludeInactive);
        }

        static List<GameObject> ResolveByPath(
            XUUnityLightMcpUiTreeResult result,
            XUUnityLightMcpUiSceneScope scope,
            string value,
            bool includeInactive)
        {
            var found = GameObject.Find(value);
            if (found != null && ContainsScene(scope.Searched, found.scene))
            {
                return new List<GameObject> { found };
            }

            var inScope = FindByPathInScenes(scope.Searched, value, includeInactive);
            if (inScope != null)
            {
                return new List<GameObject> { inScope };
            }

            var elsewhere = FindByPathInScenes(scope.AllLoaded, value, includeInactive);
            if (elsewhere == null && found != null)
            {
                elsewhere = found;
            }

            if (elsewhere != null)
            {
                result.Errors.Add(Diagnostic(
                    "ui_target_out_of_scope",
                    $"GameObject path '{value}' exists in scene '{DescribeScene(elsewhere.scene)}', which is outside the searched scope.",
                    DescribeScopeGap(scope)));
                return new List<GameObject>();
            }

            result.Errors.Add(Diagnostic(
                "ui_target_not_found",
                $"No GameObject at path '{value}'.",
                DescribeSearchedScenes(scope)));
            return new List<GameObject>();
        }

        static List<GameObject> ResolveByName(
            XUUnityLightMcpUiTreeResult result,
            XUUnityLightMcpUiSceneScope scope,
            string value,
            bool includeInactive)
        {
            var matches = CollectByNameInScenes(scope.Searched, value, includeInactive);
            if (matches.Count == 0)
            {
                var elsewhere = CollectByNameInScenes(scope.AllLoaded, value, includeInactive);
                if (elsewhere.Count > 0)
                {
                    result.Errors.Add(Diagnostic(
                        "ui_target_out_of_scope",
                        $"GameObject name '{value}' matched {elsewhere.Count} object(s) in {DescribeScenesOf(elsewhere)}, "
                        + "which is outside the searched scope.",
                        DescribeScopeGap(scope)));
                    return matches;
                }

                result.Errors.Add(Diagnostic(
                    "ui_target_not_found",
                    $"No GameObject named '{value}'.",
                    DescribeSearchedScenes(scope)));
                return matches;
            }

            if (matches.Count > 1)
            {
                result.Target.ambiguous = true;
                result.Warnings.Add(Diagnostic(
                    "ui_target_ambiguous",
                    $"GameObject name '{value}' matched {matches.Count} objects.",
                    "Prefer targetKind=game_object_path, or narrow the scope with sceneName, for a unique target."));
            }

            return matches;
        }

        static List<GameObject> CollectByNameInScenes(
            List<Scene> scenes,
            string value,
            bool includeInactive)
        {
            var matches = new List<GameObject>();
            foreach (var scene in scenes)
            {
                if (!scene.IsValid())
                {
                    continue;
                }

                foreach (var root in scene.GetRootGameObjects())
                {
                    CollectByName(root.transform, value, includeInactive, matches);
                }
            }

            return matches;
        }

        static void CollectByName(Transform transform, string value, bool includeInactive, List<GameObject> matches)
        {
            if (transform == null)
            {
                return;
            }

            if (!includeInactive && !transform.gameObject.activeInHierarchy)
            {
                return;
            }

            if (string.Equals(transform.gameObject.name, value, StringComparison.Ordinal))
            {
                matches.Add(transform.gameObject);
            }

            for (var i = 0; i < transform.childCount; i++)
            {
                CollectByName(transform.GetChild(i), value, includeInactive, matches);
            }
        }

        static GameObject FindByPathInScenes(List<Scene> scenes, string path, bool includeInactive)
        {
            var segments = SplitPath(path);
            if (segments.Count == 0)
            {
                return null;
            }

            foreach (var scene in scenes)
            {
                if (!scene.IsValid())
                {
                    continue;
                }

                foreach (var root in scene.GetRootGameObjects())
                {
                    if (!string.Equals(root.name, segments[0], StringComparison.Ordinal))
                    {
                        continue;
                    }

                    var current = root.transform;
                    for (var i = 1; i < segments.Count && current != null; i++)
                    {
                        current = FindChild(current, segments[i]);
                    }

                    if (current == null)
                    {
                        continue;
                    }

                    if (!includeInactive && !current.gameObject.activeInHierarchy)
                    {
                        continue;
                    }

                    return current.gameObject;
                }
            }

            return null;
        }

        static Transform FindChild(Transform parent, string name)
        {
            for (var i = 0; i < parent.childCount; i++)
            {
                var child = parent.GetChild(i);
                if (child != null && string.Equals(child.gameObject.name, name, StringComparison.Ordinal))
                {
                    return child;
                }
            }

            return null;
        }

        static List<string> SplitPath(string path)
        {
            var segments = new List<string>();
            var text = (path ?? "").Trim().TrimStart('/');
            if (text.Length == 0)
            {
                return segments;
            }

            var builder = new System.Text.StringBuilder();
            for (var i = 0; i < text.Length; i++)
            {
                var character = text[i];
                if (character == '\\' && i + 1 < text.Length && text[i + 1] == '/')
                {
                    builder.Append('/');
                    i++;
                    continue;
                }

                if (character == '/')
                {
                    segments.Add(builder.ToString());
                    builder.Length = 0;
                    continue;
                }

                builder.Append(character);
            }

            segments.Add(builder.ToString());
            return segments;
        }

        static List<GameObject> ResolveRootCanvases(
            XUUnityLightMcpUiTreeResult result,
            XUUnityLightMcpUiSceneScope scope,
            bool includeInactive)
        {
            var roots = CollectRootCanvases(scope.Searched, includeInactive);
            if (roots.Count > 0)
            {
                return roots;
            }

            if (scope.IsNarrowerThanAllLoaded)
            {
                var elsewhere = CollectRootCanvases(scope.AllLoaded, includeInactive);
                if (elsewhere.Count > 0)
                {
                    result.Warnings.Add(Diagnostic(
                        "ui_target_out_of_scope",
                        $"The searched scope has no root Canvas, but {elsewhere.Count} root Canvas object(s) exist in "
                        + "other loaded scenes.",
                        DescribeScopeGap(scope)));
                    return roots;
                }
            }

            result.Warnings.Add(Diagnostic(
                "ui_snapshot_empty",
                "The searched scope has no root Canvas.",
                "uGUI is the only supported backend in this slice."));
            return roots;
        }

        static List<GameObject> CollectRootCanvases(List<Scene> scenes, bool includeInactive)
        {
            var roots = new List<GameObject>();
            foreach (var scene in scenes)
            {
                if (!scene.IsValid())
                {
                    continue;
                }

                foreach (var root in scene.GetRootGameObjects())
                {
                    var canvases = root.GetComponentsInChildren<Canvas>(true);
                    foreach (var canvas in canvases)
                    {
                        if (canvas == null || !canvas.isRootCanvas)
                        {
                            continue;
                        }

                        if (!includeInactive && !canvas.gameObject.activeInHierarchy)
                        {
                            continue;
                        }

                        roots.Add(canvas.gameObject);
                    }
                }
            }

            return roots;
        }

        static bool TryResolveDontDestroyOnLoadScene(out Scene scene)
        {
            scene = default;
            GameObject probe = null;
            try
            {
                probe = new GameObject("XUUnityLightMcpDontDestroyOnLoadProbe")
                {
                    hideFlags = HideFlags.HideAndDontSave
                };
                UnityEngine.Object.DontDestroyOnLoad(probe);
                scene = probe.scene;
                return scene.IsValid() && IsDontDestroyOnLoadScene(scene);
            }
            catch
            {
                return false;
            }
            finally
            {
                if (probe != null)
                {
                    UnityEngine.Object.DestroyImmediate(probe);
                }
            }
        }

        static bool IsDontDestroyOnLoadScene(Scene scene)
        {
            return scene.IsValid()
                   && scene.buildIndex == -1
                   && string.Equals(scene.name, "DontDestroyOnLoad", StringComparison.Ordinal);
        }

        static bool MatchesSceneSelector(Scene scene, string selector)
        {
            return string.Equals(scene.name ?? "", selector, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(scene.path ?? "", selector, StringComparison.OrdinalIgnoreCase);
        }

        static bool ContainsScene(List<Scene> scenes, Scene scene)
        {
            foreach (var candidate in scenes)
            {
                if (candidate.handle == scene.handle)
                {
                    return true;
                }
            }

            return false;
        }

        static string DescribeScene(Scene scene)
        {
            if (!scene.IsValid())
            {
                return "";
            }

            var name = scene.name ?? "";
            return name.Length > 0 ? name : scene.path ?? "";
        }

        static string DescribeScenesOf(List<GameObject> objects)
        {
            var names = new List<string>();
            foreach (var item in objects)
            {
                var name = DescribeScene(item.scene);
                if (name.Length > 0 && !names.Contains(name))
                {
                    names.Add(name);
                }
            }

            return names.Count > 0 ? string.Join(", ", names) : "an unnamed scene";
        }

        static string DescribeSearchedScenes(XUUnityLightMcpUiSceneScope scope)
        {
            var names = new List<string>();
            foreach (var scene in scope.Searched)
            {
                names.Add(DescribeScene(scene));
            }

            return $"Searched scenes: {string.Join(", ", names)}.";
        }

        public static string DescribeSearchedScope(XUUnityLightMcpUiTargetInfo target)
        {
            if (target == null)
            {
                return "";
            }

            var searched = string.Join(", ", target.searched_scenes);
            var loaded = string.Join(", ", target.loaded_scenes);
            var gap = target.loaded_scenes.Count > target.searched_scenes.Count
                ? " Retry with targetKind=all_loaded_scenes, or set sceneName to the owning scene."
                : "";
            return $"Searched scenes: {searched}. Loaded scenes: {loaded}.{gap}";
        }

        static string DescribeScopeGap(XUUnityLightMcpUiSceneScope scope)
        {
            var searched = new List<string>();
            foreach (var scene in scope.Searched)
            {
                searched.Add(DescribeScene(scene));
            }

            var loaded = new List<string>();
            foreach (var scene in scope.AllLoaded)
            {
                loaded.Add(DescribeScene(scene));
            }

            return $"Searched scenes: {string.Join(", ", searched)}. Loaded scenes: {string.Join(", ", loaded)}. "
                   + "Retry with targetKind=all_loaded_scenes, or set sceneName to the owning scene.";
        }

        public static void Traverse(
            Transform transform,
            string path,
            string parentPath,
            int depth,
            int siblingIndex,
            int maxDepth,
            int maxNodes,
            XUUnityLightMcpUiTreeOptions options,
            XUUnityLightMcpUiTreeResult result)
        {
            if (transform == null)
            {
                return;
            }

            var gameObject = transform.gameObject;
            if (!options.IncludeInactive && !gameObject.activeInHierarchy)
            {
                return;
            }

            if (result.Nodes.Count >= maxNodes)
            {
                result.Truncated = true;
                result.TruncationReason = "max_nodes_reached";
                return;
            }

            var node = BuildNode(transform, path, parentPath, depth, siblingIndex, options, result);
            result.Nodes.Add(node);
            result.NodeTransforms.Add(transform);

            if (depth + 1 > maxDepth - 1)
            {
                if (transform.childCount > 0)
                {
                    node.children_truncated = true;
                    result.Truncated = true;
                    result.TruncationReason = string.IsNullOrEmpty(result.TruncationReason)
                        ? "max_depth_reached"
                        : result.TruncationReason;
                }

                return;
            }

            for (var i = 0; i < transform.childCount; i++)
            {
                var child = transform.GetChild(i);
                if (child == null)
                {
                    continue;
                }

                Traverse(
                    child,
                    path + "/" + SanitizeSegment(child.gameObject.name),
                    path,
                    depth + 1,
                    i,
                    maxDepth,
                    maxNodes,
                    options,
                    result);

                if (result.Truncated && result.Nodes.Count >= maxNodes)
                {
                    node.children_truncated = true;
                    return;
                }
            }
        }

        static XUUnityLightMcpUiNode BuildNode(
            Transform transform,
            string path,
            string parentPath,
            int depth,
            int siblingIndex,
            XUUnityLightMcpUiTreeOptions options,
            XUUnityLightMcpUiTreeResult result)
        {
            var gameObject = transform.gameObject;
            var node = new XUUnityLightMcpUiNode
            {
                node_id = XUUnityLightMcpUiRead.BackendUgui + ":" + path,
                path = path,
                parent_path = parentPath,
                depth = depth,
                sibling_index = siblingIndex,
                child_count = transform.childCount,
                name = gameObject.name ?? "",
                type = transform is RectTransform ? "RectTransform" : "Transform",
                scene_name = DescribeScene(gameObject.scene),
                active_self = gameObject.activeSelf,
                active_in_hierarchy = gameObject.activeInHierarchy,
                render_order = siblingIndex
            };

            ApplyCanvasContext(transform, node);
            ApplyAlphaAndRaycasts(transform, node);
            if (options.IncludeBounds && transform is RectTransform rectTransform)
            {
                ApplyBounds(rectTransform, node);
            }

            node.visible = node.active_in_hierarchy && node.effective_alpha > 0f;

            var components = gameObject.GetComponents<Component>();
            var missingComponentCount = 0;
            foreach (var component in components)
            {
                if (component == null)
                {
                    missingComponentCount++;
                    node.components.Add("<missing script>");
                    continue;
                }

                var typeName = component.GetType().Name;
                node.components.Add(typeName);
                if (!options.IncludeText && IsTextLikeName(typeName))
                {
                    continue;
                }

                if (XUUnityLightMcpUiComponentReaderRegistry.Describe(component, node))
                {
                    node.component_details_complete = true;
                }
            }

            if (missingComponentCount > 0)
            {
                result.Warnings.Add(Diagnostic(
                    "ui_missing_script_component",
                    $"'{path}' has {missingComponentCount} missing script component(s).",
                    "Run unity.prefab.validate on the owning prefab for the typed defect."));
            }

            if (!XUUnityLightMcpUiComponentReaderRegistry.HasReaders)
            {
                result.ComponentDetailsComplete = false;
            }

            return node;
        }

        static bool IsTextLikeName(string typeName)
        {
            return typeName.IndexOf("Text", StringComparison.Ordinal) >= 0;
        }

        static void ApplyCanvasContext(Transform transform, XUUnityLightMcpUiNode node)
        {
            var canvas = transform.GetComponentInParent<Canvas>();
            if (canvas == null)
            {
                return;
            }

            node.canvas_path = BuildPath(canvas.transform);
            var rootCanvas = canvas.isRootCanvas ? canvas : canvas.rootCanvas;
            node.canvas_sort_order = rootCanvas != null ? rootCanvas.sortingOrder : canvas.sortingOrder;
        }

        public static float ResolveCanvasGroupAlpha(Transform transform)
        {
            var alpha = 1f;
            for (var current = transform; current != null; current = current.parent)
            {
                var group = current.GetComponent<CanvasGroup>();
                if (group == null)
                {
                    continue;
                }

                alpha *= group.alpha;
                if (group.ignoreParentGroups)
                {
                    break;
                }
            }

            return Mathf.Clamp01(alpha);
        }

        static void ApplyAlphaAndRaycasts(Transform transform, XUUnityLightMcpUiNode node)
        {
            var alpha = 1f;
            var blocksRaycasts = true;
            var interactableKnown = false;
            var interactable = true;
            var current = transform;

            while (current != null)
            {
                var group = current.GetComponent<CanvasGroup>();
                if (group != null)
                {
                    alpha *= group.alpha;
                    blocksRaycasts = blocksRaycasts && group.blocksRaycasts;
                    interactable = interactable && group.interactable;
                    interactableKnown = true;
                    if (group.ignoreParentGroups)
                    {
                        break;
                    }
                }

                current = current.parent;
            }

            node.effective_alpha = Mathf.Clamp01(alpha);
            node.blocks_raycasts = blocksRaycasts;
            if (interactableKnown && !interactable)
            {
                node.interactable = false;
                node.interactable_known = true;
            }
        }

        static void ApplyBounds(RectTransform rectTransform, XUUnityLightMcpUiNode node)
        {
            if (!TryScreenRect(rectTransform, out var rect))
            {
                return;
            }

            node.has_bounds = true;
            node.bounds = rect;
            var canvas = rectTransform.GetComponentInParent<Canvas>();
            node.bounds_space = canvas != null && canvas.renderMode == RenderMode.WorldSpace
                ? "world_projected_pixels"
                : "screen_pixels";
        }

        public static bool TryScreenRect(RectTransform rectTransform, out XUUnityLightMcpUiRect rect)
        {
            rect = new XUUnityLightMcpUiRect();
            if (rectTransform == null)
            {
                return false;
            }

            rectTransform.GetWorldCorners(WorldCorners);
            var camera = ResolveEventCamera(rectTransform);

            var minX = float.MaxValue;
            var minY = float.MaxValue;
            var maxX = float.MinValue;
            var maxY = float.MinValue;
            for (var i = 0; i < WorldCorners.Length; i++)
            {
                var screenPoint = RectTransformUtility.WorldToScreenPoint(camera, WorldCorners[i]);
                minX = Mathf.Min(minX, screenPoint.x);
                minY = Mathf.Min(minY, screenPoint.y);
                maxX = Mathf.Max(maxX, screenPoint.x);
                maxY = Mathf.Max(maxY, screenPoint.y);
            }

            rect.x = Round(minX);
            rect.y = Round(minY);
            rect.width = Round(maxX - minX);
            rect.height = Round(maxY - minY);
            return true;
        }

        public static Camera ResolveEventCamera(RectTransform rectTransform)
        {
            var canvas = rectTransform != null ? rectTransform.GetComponentInParent<Canvas>() : null;
            if (canvas == null
                || canvas.renderMode == RenderMode.ScreenSpaceOverlay
                || (canvas.renderMode == RenderMode.ScreenSpaceCamera && canvas.worldCamera == null))
            {
                return null;
            }

            return canvas.worldCamera != null ? canvas.worldCamera : Camera.main;
        }

        public static Vector2 Centre(XUUnityLightMcpUiRect rect)
        {
            return new Vector2(rect.x + rect.width / 2f, rect.y + rect.height / 2f);
        }

        public static string BuildPath(Transform transform)
        {
            if (transform == null)
            {
                return "";
            }

            var segments = new List<string>();
            var current = transform;
            while (current != null)
            {
                segments.Add(SanitizeSegment(current.gameObject.name));
                current = current.parent;
            }

            segments.Reverse();
            return string.Join("/", segments);
        }

        public static string SanitizeSegment(string value)
        {
            var text = value ?? "";
            return text.Replace("/", "\\/");
        }

        public static XUUnityLightMcpUiDiagnostic Diagnostic(string code, string message, string detail = "")
        {
            return new XUUnityLightMcpUiDiagnostic
            {
                code = code ?? "",
                message = message ?? "",
                detail = detail ?? ""
            };
        }

        static float Round(float value)
        {
            return Mathf.Round(value * 100f) / 100f;
        }
    }
}
