using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpPrefabMutator
    {
        public const int MAX_OPERATIONS = 64;

        static readonly HashSet<string> SupportedOps = new(StringComparer.Ordinal)
        {
            "set_serialized_field",
            "set_rect_transform",
            "create_child",
            "set_canvas_group",
            "set_active",
            "delete_child",
            "create_child_from_template",
            "add_component",
            "remove_component",
        };

        static readonly HashSet<string> DefaultAllowedComponentTypes = new(StringComparer.Ordinal)
        {
            "CanvasGroup",
            "RectTransform",
            "LayoutElement",
            "ContentSizeFitter",
            "HorizontalLayoutGroup",
            "VerticalLayoutGroup",
            "GridLayoutGroup",
        };

        public static bool TryValidateArgs(
            XUUnityLightMcpPrefabMutationArgs args,
            out XUUnityLightMcpUiDiagnostic error)
        {
            error = null;
            var operations = args.operations ?? Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
            if (operations.Length == 0)
            {
                error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_operations_missing",
                    "At least one typed operation is required.");
                return false;
            }

            if (operations.Length > MAX_OPERATIONS)
            {
                error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_mutation_operations_limit",
                    $"A single transaction may carry at most {MAX_OPERATIONS} operations.",
                    operations.Length.ToString(CultureInfo.InvariantCulture));
                return false;
            }

            for (var index = 0; index < operations.Length; index++)
            {
                var operation = operations[index] ?? new XUUnityLightMcpPrefabMutationOperation();
                var op = (operation.op ?? "").Trim();
                if (!SupportedOps.Contains(op))
                {
                    error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_mutation_op_unsupported",
                        $"Operation {index} declares unsupported op '{op}'.",
                        string.Join(", ", SupportedOps));
                    return false;
                }

                if (string.IsNullOrWhiteSpace(operation.path))
                {
                    error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_mutation_selector_missing",
                        $"Operation {index} ('{op}') must name a target path inside the prefab.");
                    return false;
                }
            }

            return true;
        }

        public static bool TryResolveUnique(
            GameObject root,
            string path,
            out Transform resolved,
            out string errorCode,
            out string errorMessage)
        {
            resolved = null;
            errorCode = "";
            errorMessage = "";

            var wanted = (path ?? "").Trim();
            var matches = new List<Transform>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
            {
                if (transform == null)
                {
                    continue;
                }

                var candidate = XUUnityLightMcpUiTreeBuilder.BuildPath(transform);
                if (string.Equals(candidate, wanted, StringComparison.Ordinal))
                {
                    matches.Add(transform);
                    continue;
                }

                var relative = RelativePath(root.transform, transform);
                if (string.Equals(relative, wanted, StringComparison.Ordinal))
                {
                    matches.Add(transform);
                }
            }

            if (matches.Count == 0)
            {
                errorCode = "prefab_mutation_target_not_found";
                errorMessage = $"No object at '{wanted}' inside the prefab.";
                return false;
            }

            if (matches.Count > 1)
            {
                errorCode = "prefab_mutation_target_ambiguous";
                errorMessage = $"'{wanted}' matched {matches.Count} objects; a mutation target must be unique.";
                return false;
            }

            resolved = matches[0];
            return true;
        }

        public static string RelativePath(Transform root, Transform target)
        {
            if (target == root)
            {
                return target.gameObject.name ?? "";
            }

            var segments = new List<string>();
            var current = target;
            while (current != null && current != root)
            {
                segments.Add(current.gameObject.name ?? "");
                current = current.parent;
            }

            if (current == null)
            {
                return "";
            }

            segments.Add(root.gameObject.name ?? "");
            segments.Reverse();
            return string.Join("/", segments);
        }

        public static XUUnityLightMcpPrefabMutationChange Apply(
            GameObject root,
            XUUnityLightMcpPrefabMutationOperation operation,
            int index,
            HashSet<string> allowedComponentTypes,
            bool allowAnyComponentType = false)
        {
            var change = new XUUnityLightMcpPrefabMutationChange
            {
                index = index,
                op = (operation.op ?? "").Trim(),
                object_path = operation.path ?? "",
                component_type = operation.componentType ?? "",
                property_path = operation.propertyPath ?? "",
            };

            if (!TryResolveUnique(root, operation.path, out var target, out var errorCode, out var errorMessage))
            {
                return Fail(change, errorCode, errorMessage);
            }

            switch (change.op)
            {
                case "set_serialized_field":
                    return SetSerializedField(change, root.transform, target, operation);
                case "set_rect_transform":
                    return SetRectTransform(change, target, operation);
                case "set_canvas_group":
                    return SetCanvasGroup(change, target, operation);
                case "set_active":
                    return SetActive(change, target, operation);
                case "delete_child":
                    return DeleteChild(change, target);
                case "create_child_from_template":
                    return CreateChildFromTemplate(change, target, operation);
                case "create_child":
                    return CreateChild(change, target, operation);
                case "add_component":
                    return AddComponent(change, target, operation, allowedComponentTypes, allowAnyComponentType);
                case "remove_component":
                    return RemoveComponent(change, target, operation, allowedComponentTypes);
                default:
                    return Fail(change, "prefab_mutation_op_unsupported", $"Unsupported op '{change.op}'.");
            }
        }

        static XUUnityLightMcpPrefabMutationChange SetSerializedField(
            XUUnityLightMcpPrefabMutationChange change,
            Transform root,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            if (!TryFindComponent(target, operation.componentType, out var component, out var failure))
            {
                return Fail(change, failure.Item1, failure.Item2);
            }

            using var serialized = new SerializedObject(component);
            var propertyPath = operation.propertyPath ?? "";
            var property = serialized.FindProperty(propertyPath);
            if (property == null)
            {
                if (TryAppendArrayElement(serialized, propertyPath, out var appendError))
                {
                    property = serialized.FindProperty(propertyPath);
                }
                else if (appendError.Length > 0)
                {
                    return Fail(change, "prefab_mutation_array_index_out_of_range", appendError);
                }
            }

            if (property == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_property_not_found",
                    $"'{operation.componentType}' has no serialized property '{operation.propertyPath}'.");
            }

            if (IsIdentityProperty(property.propertyPath))
            {
                return Fail(
                    change,
                    "prefab_mutation_value_incompatible",
                    $"'{property.propertyPath}' is an object-identity field (owning GameObject, script, hierarchy "
                    + "or prefab link); rewriting it would detach or swap the component, so a component can never "
                    + "be swapped for another type through this API.");
            }

            change.before = DescribeProperty(property);
            if (!TryAssign(property, root, operation, out var assignErrorCode, out var assignError))
            {
                return Fail(change, assignErrorCode, assignError);
            }

            serialized.ApplyModifiedPropertiesWithoutUndo();
            change.after = DescribeProperty(property);
            change.inverse_op = "set_serialized_field";
            change.status = ResolveWriteStatus(change);
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange SetRectTransform(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            if (target is not RectTransform rect)
            {
                return Fail(
                    change,
                    "prefab_mutation_not_a_rect_transform",
                    $"'{change.object_path}' has no RectTransform.");
            }

            var field = (operation.propertyPath ?? "").Trim();
            change.before = DescribeRect(rect, field);
            switch (field)
            {
                case "anchorMin":
                    rect.anchorMin = new Vector2(operation.x, operation.y);
                    break;
                case "anchorMax":
                    rect.anchorMax = new Vector2(operation.x, operation.y);
                    break;
                case "pivot":
                    rect.pivot = new Vector2(operation.x, operation.y);
                    break;
                case "anchoredPosition":
                    rect.anchoredPosition = new Vector2(operation.x, operation.y);
                    break;
                case "sizeDelta":
                    rect.sizeDelta = new Vector2(operation.x, operation.y);
                    break;
                case "offsetMin":
                    rect.offsetMin = new Vector2(operation.x, operation.y);
                    break;
                case "offsetMax":
                    rect.offsetMax = new Vector2(operation.x, operation.y);
                    break;
                case "localScale":
                    rect.localScale = new Vector3(operation.x, operation.y, Mathf.Approximately(operation.z, 0f) ? 1f : operation.z);
                    break;
                case "stretch":
                    rect.anchorMin = Vector2.zero;
                    rect.anchorMax = Vector2.one;
                    rect.offsetMin = Vector2.zero;
                    rect.offsetMax = Vector2.zero;
                    break;
                default:
                    return Fail(
                        change,
                        "prefab_mutation_property_not_found",
                        "propertyPath must be anchorMin, anchorMax, pivot, anchoredPosition, sizeDelta, offsetMin, "
                        + "offsetMax, localScale, or stretch.");
            }

            change.after = DescribeRect(rect, field);
            change.component_type = "RectTransform";
            change.inverse_op = "set_rect_transform";
            change.status = ResolveWriteStatus(change);
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange SetCanvasGroup(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            var group = target.GetComponent<CanvasGroup>();
            if (group == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_found",
                    $"'{change.object_path}' has no CanvasGroup.");
            }

            var field = (operation.propertyPath ?? "").Trim();
            change.component_type = "CanvasGroup";
            switch (field)
            {
                case "alpha":
                    change.before = group.alpha.ToString("0.###", CultureInfo.InvariantCulture);
                    group.alpha = Mathf.Clamp01((float)operation.numberValue);
                    change.after = group.alpha.ToString("0.###", CultureInfo.InvariantCulture);
                    break;
                case "interactable":
                    change.before = group.interactable ? "true" : "false";
                    group.interactable = operation.boolValue;
                    change.after = group.interactable ? "true" : "false";
                    break;
                case "blocksRaycasts":
                    change.before = group.blocksRaycasts ? "true" : "false";
                    group.blocksRaycasts = operation.boolValue;
                    change.after = group.blocksRaycasts ? "true" : "false";
                    break;
                default:
                    return Fail(
                        change,
                        "prefab_mutation_property_not_found",
                        "propertyPath must be alpha, interactable, or blocksRaycasts.");
            }

            change.inverse_op = "set_canvas_group";
            change.status = ResolveWriteStatus(change);
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange SetActive(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            change.before = target.gameObject.activeSelf ? "true" : "false";
            target.gameObject.SetActive(operation.boolValue);
            change.after = target.gameObject.activeSelf ? "true" : "false";
            change.inverse_op = "set_active";
            change.status = ResolveWriteStatus(change);
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange DeleteChild(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target)
        {
            if (target.parent == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_cannot_delete_root",
                    "The prefab root cannot be deleted by a mutation transaction.");
            }

            change.before = $"present:{target.gameObject.name}";
            change.after = "deleted";
            change.inverse_op = "create_child_from_template";
            UnityEngine.Object.DestroyImmediate(target.gameObject);
            change.status = "applied";
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange CreateChildFromTemplate(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            var templatePath = (operation.templatePath ?? "").Trim();
            if (string.IsNullOrEmpty(templatePath))
            {
                return Fail(
                    change,
                    "prefab_mutation_template_required",
                    "create_child_from_template requires an approved templatePath prefab asset.");
            }

            var template = AssetDatabase.LoadAssetAtPath<GameObject>(templatePath);
            if (template == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_template_not_found",
                    $"No prefab template at '{templatePath}'.");
            }

            var instance = (GameObject)PrefabUtility.InstantiatePrefab(template);
            instance.transform.SetParent(target, false);
            if (!string.IsNullOrWhiteSpace(operation.childName))
            {
                instance.name = operation.childName.Trim();
            }

            ApplySiblingPlacement(instance.transform, operation);

            change.before = "absent";
            change.after = $"created:{instance.name}";
            change.inverse_op = "delete_child";
            change.status = "applied";
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange CreateChild(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            var childName = (operation.childName ?? "").Trim();
            if (childName.Length == 0)
            {
                return Fail(change, "prefab_mutation_child_name_required", "create_child requires childName.");
            }

            var child = target is RectTransform || target.GetComponentInParent<Canvas>(true) != null
                ? new GameObject(childName, typeof(RectTransform))
                : new GameObject(childName);
            child.transform.SetParent(target, false);
            child.layer = target.gameObject.layer;
            ApplySiblingPlacement(child.transform, operation);
            change.before = "absent";
            change.after = $"created:{childName}";
            change.inverse_op = "delete_child";
            change.status = "applied";
            return change;
        }

        static void ApplySiblingPlacement(Transform child, XUUnityLightMcpPrefabMutationOperation operation)
        {
            var afterSibling = (operation.afterSibling ?? "").Trim();
            if (afterSibling.Length > 0 && child.parent != null)
            {
                var anchor = child.parent.Find(afterSibling);
                if (anchor != null && anchor != child)
                {
                    child.SetSiblingIndex(Math.Min(anchor.GetSiblingIndex() + 1, child.parent.childCount - 1));
                    return;
                }
            }

            if (operation.siblingIndex >= 0)
            {
                child.SetSiblingIndex(operation.siblingIndex);
            }
        }

        static XUUnityLightMcpPrefabMutationChange AddComponent(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation,
            HashSet<string> allowedComponentTypes,
            bool allowAnyComponentType)
        {
            var typeName = (operation.componentType ?? "").Trim();
            var type = XUUnityLightMcpTypeNameMatcher.ResolveComponentType(typeName, out var candidates);
            if (!allowAnyComponentType && !XUUnityLightMcpTypeNameMatcher.AllowlistAccepts(allowedComponentTypes, typeName, type))
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_allowlisted",
                    $"'{typeName}' is not in the component allowlist for this transaction.");
            }

            if (type == null)
            {
                return candidates.Count > 1
                    ? AmbiguousType(change, typeName, candidates)
                    : Fail(
                        change,
                        "prefab_mutation_component_type_unresolved",
                        $"Component type '{typeName}' could not be resolved by full name, assembly-qualified name or short name.");
            }

            if (type.IsAbstract || type == typeof(Transform) || type == typeof(RectTransform))
            {
                return Fail(
                    change,
                    "prefab_mutation_component_type_unresolved",
                    $"'{typeName}' is abstract or a transform and cannot be added.");
            }

            if (target.GetComponent(type) != null)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_already_present",
                    $"'{change.object_path}' already has a {typeName}.");
            }

            var added = target.gameObject.AddComponent(type);
            if (added == null || target.GetComponent(type) == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_add_failed",
                    $"Unity refused to add '{typeName}' to '{change.object_path}' (for example an editor-only script, "
                    + "or a component that conflicts with one already present); see the console for its reason.");
            }

            change.before = "absent";
            change.after = $"added:{type.FullName}";
            change.inverse_op = "remove_component";
            change.status = "applied";
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange RemoveComponent(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation,
            HashSet<string> allowedComponentTypes)
        {
            var typeName = (operation.componentType ?? "").Trim();
            if (!TryFindComponent(target, typeName, out var component, out var failure))
            {
                return allowedComponentTypes.Contains(typeName)
                    ? Fail(change, failure.Item1, failure.Item2)
                    : Fail(
                        change,
                        "prefab_mutation_component_not_allowlisted",
                        $"'{typeName}' is not in the component allowlist for this transaction.");
            }

            if (!XUUnityLightMcpTypeNameMatcher.AllowlistAccepts(allowedComponentTypes, typeName, component.GetType()))
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_allowlisted",
                    $"'{component.GetType().FullName}' is not in the component allowlist for this transaction.");
            }

            if (component is Transform)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_removable",
                    "A Transform or RectTransform cannot be removed.");
            }

            change.before = $"present:{typeName}";
            UnityEngine.Object.DestroyImmediate(component, true);
            change.after = "removed";
            change.inverse_op = "add_component";
            change.status = "applied";
            return change;
        }

        static bool TryFindComponent(
            Transform target,
            string typeName,
            out Component component,
            out Tuple<string, string> failure)
        {
            component = null;
            failure = null;
            var wanted = (typeName ?? "").Trim();
            if (string.IsNullOrEmpty(wanted))
            {
                failure = Tuple.Create(
                    "prefab_mutation_component_required",
                    "componentType is required for this operation.");
                return false;
            }

            var matches = new List<Component>();
            foreach (var candidate in target.GetComponents<Component>())
            {
                if (candidate == null)
                {
                    continue;
                }

                if (XUUnityLightMcpTypeNameMatcher.Matches(candidate.GetType(), wanted))
                {
                    matches.Add(candidate);
                }
            }

            if (matches.Count == 0)
            {
                failure = Tuple.Create(
                    "prefab_mutation_component_not_found",
                    $"No component named '{wanted}' on the target.");
                return false;
            }

            var distinctTypes = new List<string>();
            foreach (var match in matches)
            {
                if (!distinctTypes.Contains(match.GetType().FullName))
                {
                    distinctTypes.Add(match.GetType().FullName);
                }
            }

            if (distinctTypes.Count > 1)
            {
                distinctTypes.Sort(StringComparer.Ordinal);
                failure = Tuple.Create(
                    "prefab_mutation_component_type_ambiguous",
                    $"'{wanted}' matches {distinctTypes.Count} component types on the target; use the full name: "
                    + string.Join(", ", distinctTypes) + ".");
                return false;
            }

            if (matches.Count > 1)
            {
                failure = Tuple.Create(
                    "prefab_mutation_component_ambiguous",
                    $"'{wanted}' is present {matches.Count} times on the target.");
                return false;
            }

            component = matches[0];
            return true;
        }

        static XUUnityLightMcpPrefabMutationChange AmbiguousType(
            XUUnityLightMcpPrefabMutationChange change,
            string typeName,
            List<string> candidates)
        {
            return Fail(
                change,
                "prefab_mutation_component_type_ambiguous",
                $"'{typeName}' names {candidates.Count} component types; use the full name: {string.Join(", ", candidates)}.");
        }

        static bool TryAssign(
            SerializedProperty property,
            Transform root,
            XUUnityLightMcpPrefabMutationOperation operation,
            out string errorCode,
            out string error)
        {
            errorCode = "prefab_mutation_value_incompatible";
            error = "";
            switch (property.propertyType)
            {
                case SerializedPropertyType.String:
                    property.stringValue = operation.stringValue ?? "";
                    return true;
                case SerializedPropertyType.Boolean:
                    property.boolValue = operation.boolValue;
                    return true;
                case SerializedPropertyType.Integer:
                case SerializedPropertyType.ArraySize:
                    property.intValue = (int)Math.Round(operation.numberValue);
                    return true;
                case SerializedPropertyType.Float:
                    property.floatValue = (float)operation.numberValue;
                    return true;
                case SerializedPropertyType.Color:
                    property.colorValue = new Color(operation.x, operation.y, operation.z, operation.w);
                    return true;
                case SerializedPropertyType.Vector2:
                    property.vector2Value = new Vector2(operation.x, operation.y);
                    return true;
                case SerializedPropertyType.Vector3:
                    property.vector3Value = new Vector3(operation.x, operation.y, operation.z);
                    return true;
                case SerializedPropertyType.Enum:
                    return TryAssignEnum(property, operation, out errorCode, out error);
                case SerializedPropertyType.ObjectReference:
                    return TryAssignObjectReference(property, root, operation, out errorCode, out error);
                default:
                    error =
                        $"Property '{property.propertyPath}' is a {property.propertyType}; this transaction API "
                        + "only sets string, bool, int, float, enum, color, Vector2, Vector3, array size, and "
                        + "object-reference fields.";
                    return false;
            }
        }

        static bool TryAssignEnum(
            SerializedProperty property,
            XUUnityLightMcpPrefabMutationOperation operation,
            out string errorCode,
            out string error)
        {
            errorCode = "prefab_mutation_enum_value_invalid";
            error = "";
            var names = property.enumNames ?? Array.Empty<string>();
            var requestedName = (operation.stringValue ?? "").Trim();
            if (requestedName.Length > 0)
            {
                var byName = IndexOfEnumName(names, requestedName);
                if (byName < 0)
                {
                    error =
                        $"'{requestedName}' is not a member of enum property '{property.propertyPath}'. "
                        + DescribeEnumMembers(names);
                    return false;
                }

                property.enumValueIndex = byName;
                errorCode = "";
                return true;
            }

            var requestedIndex = (int)Math.Round(operation.numberValue);
            if (requestedIndex < 0 || requestedIndex >= names.Length)
            {
                error =
                    $"numberValue on enum property '{property.propertyPath}' is the member index, not the enum's "
                    + $"underlying value, and {requestedIndex} is out of range. " + DescribeEnumMembers(names)
                    + " Pass stringValue to set it by name instead.";
                return false;
            }

            property.enumValueIndex = requestedIndex;
            errorCode = "";
            return true;
        }

        static bool TryAssignObjectReference(
            SerializedProperty property,
            Transform root,
            XUUnityLightMcpPrefabMutationOperation operation,
            out string errorCode,
            out string error)
        {
            errorCode = "prefab_mutation_value_incompatible";
            error = "";
            var declared = XUUnityLightMcpPrefabInspector.DeclaredTypeName(property.type);
            if (string.Equals((operation.valueKind ?? "").Trim(), "null", StringComparison.OrdinalIgnoreCase))
            {
                property.objectReferenceValue = null;
                return true;
            }

            if (IsSceneBoundReferenceType(declared))
            {
                return TryAssignSceneBoundReference(property, root, declared, operation, out errorCode, out error);
            }

            var requested = (operation.stringValue ?? "").Trim();
            if (requested.Length == 0)
            {
                errorCode = "prefab_mutation_asset_reference_required";
                error =
                    $"Property '{property.propertyPath}' is an asset reference; pass stringValue as a "
                    + "project-relative asset path or a 32-character asset GUID, with the optional "
                    + "assetSubAssetName for a sub-asset. Use valueKind=\"null\" to clear it.";
                return false;
            }

            SplitAssetReference(requested, operation.assetSubAssetName, out var target, out var subAsset);
            if (!TryLoadAssetObject(target, subAsset, declared, out var asset, out var loadError))
            {
                errorCode = "prefab_mutation_asset_not_found";
                error = loadError;
                return false;
            }

            if (asset is Component || asset is GameObject)
            {
                error =
                    $"'{requested}' resolves to a {asset.GetType().Name}. Component and GameObject references stay "
                    + "out of scope so a component can never be swapped for another type.";
                return false;
            }

            if (!string.IsNullOrEmpty(declared)
                && !XUUnityLightMcpPrefabInspector.TypeChainContains(asset.GetType(), declared))
            {
                errorCode = "prefab_mutation_asset_type_mismatch";
                error =
                    $"'{requested}' is a {asset.GetType().Name}, which is not in the type chain of the declared "
                    + $"{declared} field '{property.propertyPath}'.";
                return false;
            }

            property.objectReferenceValue = asset;
            return true;
        }

        static bool TryAssignSceneBoundReference(
            SerializedProperty property,
            Transform root,
            string declared,
            XUUnityLightMcpPrefabMutationOperation operation,
            out string errorCode,
            out string error)
        {
            errorCode = "prefab_mutation_reference_required";
            error = "";
            var requested = (operation.stringValue ?? "").Trim();
            if (requested.Length == 0)
            {
                error =
                    $"Property '{property.propertyPath}' holds a {declared} reference; pass stringValue as a path "
                    + "inside this prefab (optionally 'path#ComponentType'), or a prefab asset path or GUID. Use "
                    + "valueKind=\"null\" to clear it.";
                return false;
            }

            var wantsAsset = string.Equals((operation.valueKind ?? "").Trim(), "asset", StringComparison.OrdinalIgnoreCase)
                             || LooksLikeAssetGuid(requested)
                             || requested.StartsWith("Assets/", StringComparison.Ordinal)
                             || requested.StartsWith("Packages/", StringComparison.Ordinal);
            SplitObjectReference(requested, out var objectPath, out var componentName);

            GameObject owner;
            if (wantsAsset)
            {
                var assetPath = LooksLikeAssetGuid(objectPath) ? AssetDatabase.GUIDToAssetPath(objectPath) : objectPath;
                owner = string.IsNullOrEmpty(assetPath) ? null : AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                if (owner == null)
                {
                    errorCode = "prefab_mutation_asset_not_found";
                    error = $"'{objectPath}' is not a prefab asset, so it cannot fill the {declared} field '{property.propertyPath}'.";
                    return false;
                }
            }
            else
            {
                if (!TryResolveUnique(root.gameObject, objectPath, out var resolved, out var resolveCode, out var resolveError))
                {
                    errorCode = resolveCode == "prefab_mutation_target_not_found"
                        ? "prefab_mutation_reference_target_not_found"
                        : "prefab_mutation_reference_target_ambiguous";
                    error = $"Reference target for '{property.propertyPath}': {resolveError}";
                    return false;
                }

                owner = resolved.gameObject;
            }

            if (string.Equals(declared, "GameObject", StringComparison.Ordinal))
            {
                if (componentName.Length > 0)
                {
                    error = $"'{property.propertyPath}' is a GameObject field; drop the '#{componentName}' suffix.";
                    return false;
                }

                property.objectReferenceValue = owner;
                return true;
            }

            var matches = new List<Component>();
            foreach (var candidate in owner.GetComponents<Component>())
            {
                if (candidate == null || !XUUnityLightMcpPrefabInspector.TypeChainContains(candidate.GetType(), declared))
                {
                    continue;
                }

                if (componentName.Length > 0
                    && !XUUnityLightMcpPrefabInspector.TypeChainContains(candidate.GetType(), componentName))
                {
                    continue;
                }

                matches.Add(candidate);
            }

            if (matches.Count != 1)
            {
                errorCode = matches.Count == 0
                    ? "prefab_mutation_reference_type_mismatch"
                    : "prefab_mutation_reference_component_ambiguous";
                error = matches.Count == 0
                    ? $"'{objectPath}' has no component assignable to the {declared} field '{property.propertyPath}'"
                      + (componentName.Length > 0 ? $" matching '{componentName}'." : ".")
                    : $"'{objectPath}' has {matches.Count} components assignable to {declared}; name one with "
                      + "'path#ComponentType'.";
                return false;
            }

            property.objectReferenceValue = matches[0];
            return true;
        }

        static void SplitObjectReference(string requested, out string objectPath, out string componentName)
        {
            objectPath = requested;
            componentName = "";
            var separator = requested.LastIndexOf('#');
            if (separator <= 0 || separator >= requested.Length - 1)
            {
                return;
            }

            objectPath = requested.Substring(0, separator).Trim();
            componentName = requested.Substring(separator + 1).Trim();
        }

        static bool TryAppendArrayElement(SerializedObject serialized, string propertyPath, out string error)
        {
            error = "";
            const string marker = ".Array.data[";
            var markerIndex = propertyPath.LastIndexOf(marker, StringComparison.Ordinal);
            if (markerIndex <= 0)
            {
                return false;
            }

            var close = propertyPath.IndexOf(']', markerIndex);
            if (close < 0
                || !int.TryParse(
                    propertyPath.Substring(markerIndex + marker.Length, close - markerIndex - marker.Length),
                    NumberStyles.Integer,
                    CultureInfo.InvariantCulture,
                    out var elementIndex))
            {
                return false;
            }

            var array = serialized.FindProperty(propertyPath.Substring(0, markerIndex));
            if (array == null || !array.isArray)
            {
                return false;
            }

            if (elementIndex != array.arraySize)
            {
                error =
                    $"'{propertyPath}' is past the end of an array of size {array.arraySize}. Elements may only be "
                    + "appended in order (index == current size), or set '<field>.Array.size' first.";
                return false;
            }

            array.arraySize = elementIndex + 1;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            serialized.Update();
            return true;
        }

        static readonly HashSet<string> IdentityPropertyNames = new(StringComparer.Ordinal)
        {
            "m_GameObject",
            "m_Script",
            "m_Father",
            "m_Children",
            "m_PrefabInstance",
            "m_PrefabAsset",
            "m_CorrespondingSourceObject",
        };

        static bool IsIdentityProperty(string propertyPath)
        {
            return IdentityPropertyNames.Contains(propertyPath ?? "");
        }

        static void SplitAssetReference(
            string requested,
            string declaredSubAssetName,
            out string target,
            out string subAssetName)
        {
            target = requested;
            subAssetName = (declaredSubAssetName ?? "").Trim();
            if (subAssetName.Length > 0)
            {
                return;
            }

            var separator = requested.LastIndexOf('#');
            if (separator <= 0 || separator >= requested.Length - 1)
            {
                return;
            }

            target = requested.Substring(0, separator);
            subAssetName = requested.Substring(separator + 1);
        }

        static bool TryLoadAssetObject(
            string requested,
            string subAssetName,
            string declaredType,
            out UnityEngine.Object asset,
            out string error)
        {
            asset = null;
            error = "";
            var path = LooksLikeAssetGuid(requested)
                ? AssetDatabase.GUIDToAssetPath(requested)
                : requested.Replace('\\', '/');
            if (string.IsNullOrEmpty(path))
            {
                error = $"GUID '{requested}' does not resolve to an asset path in this project.";
                return false;
            }

            var wantedSubAsset = (subAssetName ?? "").Trim();
            if (wantedSubAsset.Length == 0)
            {
                asset = AssetDatabase.LoadMainAssetAtPath(path);
                if (asset == null)
                {
                    error = $"No asset could be loaded at '{path}'.";
                    return false;
                }

                if (!FitsDeclaredType(asset, declaredType))
                {
                    var fitting = SingleSubAssetFittingType(path, declaredType);
                    if (fitting != null)
                    {
                        asset = fitting;
                    }
                }

                return true;
            }

            UnityEngine.Object firstNameMatch = null;
            foreach (var candidate in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (candidate == null || !string.Equals(candidate.name, wantedSubAsset, StringComparison.Ordinal))
                {
                    continue;
                }

                if (FitsDeclaredType(candidate, declaredType))
                {
                    asset = candidate;
                    return true;
                }

                if (firstNameMatch == null)
                {
                    firstNameMatch = candidate;
                }
            }

            if (firstNameMatch != null)
            {
                asset = firstNameMatch;
                return true;
            }

            error = $"'{path}' has no sub-asset named '{wantedSubAsset}'.";
            return false;
        }

        static UnityEngine.Object SingleSubAssetFittingType(string path, string declaredType)
        {
            UnityEngine.Object fitting = null;
            foreach (var candidate in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (candidate == null || !FitsDeclaredType(candidate, declaredType))
                {
                    continue;
                }

                if (fitting != null)
                {
                    return null;
                }

                fitting = candidate;
            }

            return fitting;
        }

        static bool FitsDeclaredType(UnityEngine.Object candidate, string declaredType)
        {
            return string.IsNullOrEmpty(declaredType)
                   || XUUnityLightMcpPrefabInspector.TypeChainContains(candidate.GetType(), declaredType);
        }

        static bool LooksLikeAssetGuid(string value)
        {
            if (value == null || value.Length != 32)
            {
                return false;
            }

            foreach (var character in value)
            {
                var isHex = (character >= '0' && character <= '9')
                            || (character >= 'a' && character <= 'f')
                            || (character >= 'A' && character <= 'F');
                if (!isHex)
                {
                    return false;
                }
            }

            return true;
        }

        static bool IsSceneBoundReferenceType(string declared)
        {
            if (string.IsNullOrEmpty(declared))
            {
                return false;
            }

            if (string.Equals(declared, "GameObject", StringComparison.Ordinal))
            {
                return true;
            }

            var type = XUUnityLightMcpTypeNameMatcher.ResolveComponentType(declared, out var candidates);
            return type != null || candidates.Count > 0;
        }

        static int IndexOfEnumName(string[] names, string wanted)
        {
            for (var index = 0; index < names.Length; index++)
            {
                if (string.Equals(names[index], wanted, StringComparison.Ordinal))
                {
                    return index;
                }
            }

            for (var index = 0; index < names.Length; index++)
            {
                if (string.Equals(names[index], wanted, StringComparison.OrdinalIgnoreCase))
                {
                    return index;
                }
            }

            return -1;
        }

        static string DescribeEnumMembers(string[] names)
        {
            if (names.Length == 0)
            {
                return "The property reports no enum members.";
            }

            var described = new List<string>(names.Length);
            for (var index = 0; index < names.Length; index++)
            {
                described.Add($"{names[index]}={index}");
            }

            return "Valid members (name=index): " + string.Join(", ", described) + ".";
        }

        static string ResolveWriteStatus(XUUnityLightMcpPrefabMutationChange change)
        {
            return string.Equals(change.before, change.after, StringComparison.Ordinal) ? "no_op" : "applied";
        }

        static string DescribeProperty(SerializedProperty property)
        {
            return property.propertyType switch
            {
                SerializedPropertyType.String => property.stringValue ?? "",
                SerializedPropertyType.Boolean => property.boolValue ? "true" : "false",
                SerializedPropertyType.Integer => property.intValue.ToString(CultureInfo.InvariantCulture),
                SerializedPropertyType.Float => property.floatValue.ToString("0.####", CultureInfo.InvariantCulture),
                SerializedPropertyType.Enum => DescribeEnumValue(property),
                SerializedPropertyType.Color => property.colorValue.ToString(),
                SerializedPropertyType.Vector2 => property.vector2Value.ToString(),
                SerializedPropertyType.Vector3 => property.vector3Value.ToString(),
                SerializedPropertyType.ObjectReference => DescribeObjectReference(property.objectReferenceValue),
                _ => property.propertyType.ToString(),
            };
        }

        static string DescribeEnumValue(SerializedProperty property)
        {
            var names = property.enumNames ?? Array.Empty<string>();
            var index = property.enumValueIndex;
            return index >= 0 && index < names.Length
                ? names[index]
                : index.ToString(CultureInfo.InvariantCulture);
        }

        static string DescribeObjectReference(UnityEngine.Object value)
        {
            if (value == null)
            {
                return "<null>";
            }

            var path = AssetDatabase.GetAssetPath(value);
            if (string.IsNullOrEmpty(path))
            {
                return value.name ?? "";
            }

            return AssetDatabase.IsMainAsset(value) ? path : $"{path}#{value.name}";
        }

        static string DescribeRect(RectTransform rect, string field)
        {
            return field switch
            {
                "anchorMin" => rect.anchorMin.ToString(),
                "anchorMax" => rect.anchorMax.ToString(),
                "pivot" => rect.pivot.ToString(),
                "anchoredPosition" => rect.anchoredPosition.ToString(),
                "sizeDelta" => rect.sizeDelta.ToString(),
                "offsetMin" => rect.offsetMin.ToString(),
                "offsetMax" => rect.offsetMax.ToString(),
                "localScale" => rect.localScale.ToString(),
                "stretch" => $"{rect.anchorMin}{rect.anchorMax}{rect.offsetMin}{rect.offsetMax}",
                _ => "",
            };
        }

        public static HashSet<string> ResolveAllowedComponentTypes(string[] requested)
        {
            var allowed = new HashSet<string>(DefaultAllowedComponentTypes, StringComparer.Ordinal);
            foreach (var value in requested ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    allowed.Add(value.Trim());
                }
            }

            return allowed;
        }

        static XUUnityLightMcpPrefabMutationChange Fail(
            XUUnityLightMcpPrefabMutationChange change,
            string errorCode,
            string errorMessage)
        {
            change.status = "failed";
            change.error_code = errorCode;
            change.error_message = errorMessage;
            return change;
        }
    }
}
