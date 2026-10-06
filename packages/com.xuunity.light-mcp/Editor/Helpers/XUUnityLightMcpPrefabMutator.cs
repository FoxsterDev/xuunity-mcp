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
            HashSet<string> allowedComponentTypes)
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
                    return SetSerializedField(change, target, operation);
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
                case "add_component":
                    return AddComponent(change, target, operation, allowedComponentTypes);
                case "remove_component":
                    return RemoveComponent(change, target, operation, allowedComponentTypes);
                default:
                    return Fail(change, "prefab_mutation_op_unsupported", $"Unsupported op '{change.op}'.");
            }
        }

        static XUUnityLightMcpPrefabMutationChange SetSerializedField(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation)
        {
            if (!TryFindComponent(target, operation.componentType, out var component, out var failure))
            {
                return Fail(change, failure.Item1, failure.Item2);
            }

            using var serialized = new SerializedObject(component);
            var property = serialized.FindProperty(operation.propertyPath ?? "");
            if (property == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_property_not_found",
                    $"'{operation.componentType}' has no serialized property '{operation.propertyPath}'.");
            }

            change.before = DescribeProperty(property);
            if (!TryAssign(property, operation, out var assignErrorCode, out var assignError))
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
                default:
                    return Fail(
                        change,
                        "prefab_mutation_property_not_found",
                        "propertyPath must be anchorMin, anchorMax, pivot, anchoredPosition, or sizeDelta.");
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

            change.before = "absent";
            change.after = $"created:{instance.name}";
            change.inverse_op = "delete_child";
            change.status = "applied";
            return change;
        }

        static XUUnityLightMcpPrefabMutationChange AddComponent(
            XUUnityLightMcpPrefabMutationChange change,
            Transform target,
            XUUnityLightMcpPrefabMutationOperation operation,
            HashSet<string> allowedComponentTypes)
        {
            var typeName = (operation.componentType ?? "").Trim();
            if (!allowedComponentTypes.Contains(typeName))
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_allowlisted",
                    $"'{typeName}' is not in the component allowlist for this transaction.");
            }

            var type = ResolveComponentType(typeName);
            if (type == null)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_type_unresolved",
                    $"Component type '{typeName}' could not be resolved.");
            }

            if (target.GetComponent(type) != null)
            {
                return Fail(
                    change,
                    "prefab_mutation_component_already_present",
                    $"'{change.object_path}' already has a {typeName}.");
            }

            target.gameObject.AddComponent(type);
            change.before = "absent";
            change.after = $"added:{typeName}";
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
            if (!allowedComponentTypes.Contains(typeName))
            {
                return Fail(
                    change,
                    "prefab_mutation_component_not_allowlisted",
                    $"'{typeName}' is not in the component allowlist for this transaction.");
            }

            if (!TryFindComponent(target, typeName, out var component, out var failure))
            {
                return Fail(change, failure.Item1, failure.Item2);
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

                if (string.Equals(candidate.GetType().Name, wanted, StringComparison.Ordinal))
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

        static Type ResolveComponentType(string typeName)
        {
            foreach (var candidate in TypeCache.GetTypesDerivedFrom<Component>())
            {
                if (string.Equals(candidate.Name, typeName, StringComparison.Ordinal))
                {
                    return candidate;
                }
            }

            return null;
        }

        static bool TryAssign(
            SerializedProperty property,
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
                    return TryAssignObjectReference(property, operation, out errorCode, out error);
                default:
                    error =
                        $"Property '{property.propertyPath}' is a {property.propertyType}; this transaction API "
                        + "only sets string, bool, int, float, enum, color, Vector2, Vector3, and asset-typed "
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
            XUUnityLightMcpPrefabMutationOperation operation,
            out string errorCode,
            out string error)
        {
            errorCode = "prefab_mutation_value_incompatible";
            error = "";
            var declared = XUUnityLightMcpPrefabInspector.DeclaredTypeName(property.type);
            if (IsSceneBoundReferenceType(declared))
            {
                error =
                    $"Property '{property.propertyPath}' holds a {declared} reference. Component and GameObject "
                    + "references stay out of scope so a component can never be swapped for another type; only "
                    + "asset-typed references such as Sprite, Material, or TMP_FontAsset are writable.";
                return false;
            }

            if (string.Equals((operation.valueKind ?? "").Trim(), "null", StringComparison.OrdinalIgnoreCase))
            {
                property.objectReferenceValue = null;
                return true;
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

            var type = ResolveComponentType(declared);
            return type != null;
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
