using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpPrefabLoadResult
    {
        public GameObject Root;
        public string NormalizedPath = "";
        public string Guid = "";
        public XUUnityLightMcpUiDiagnostic Error;
    }

    internal static class XUUnityLightMcpPrefabInspector
    {
        public const string UnassignedScopeProjectScripts = "project_scripts";
        public const string UnassignedScopeRequired = "required";
        public const string UnassignedScopeAll = "all";

        const int MAX_PROPERTIES_PER_COMPONENT = 512;

        public static string NormalizeUnassignedScope(string requested)
        {
            var scope = (requested ?? "").Trim().ToLowerInvariant();
            return scope switch
            {
                UnassignedScopeRequired => UnassignedScopeRequired,
                UnassignedScopeAll => UnassignedScopeAll,
                _ => UnassignedScopeProjectScripts,
            };
        }

        public static XUUnityLightMcpPrefabLoadResult Load(string prefabPath)
        {
            var result = new XUUnityLightMcpPrefabLoadResult();
            var path = (prefabPath ?? "").Trim().Replace('\\', '/');
            if (string.IsNullOrEmpty(path))
            {
                result.Error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_path_required",
                    "prefabPath is required.");
                return result;
            }

            if (!path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                result.Error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_path_invalid",
                    $"'{path}' is not a .prefab asset path.",
                    "Use a project-relative path such as Assets/UI/Popup.prefab.");
                return result;
            }

            result.NormalizedPath = path;
            result.Guid = AssetDatabase.AssetPathToGUID(path);
            if (string.IsNullOrEmpty(result.Guid))
            {
                result.Error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_not_found",
                    $"No prefab asset at '{path}'.");
                return result;
            }

            var root = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (root == null)
            {
                result.Error = XUUnityLightMcpUiTreeBuilder.Diagnostic(
                    "prefab_not_loadable",
                    $"'{path}' could not be loaded as a GameObject prefab.");
                return result;
            }

            result.Root = root;
            return result;
        }

        public static void Inspect(
            GameObject root,
            bool reportUnassignedReferences,
            XUUnityLightMcpPrefabValidatePayload payload)
        {
            Inspect(root, reportUnassignedReferences, UnassignedScopeProjectScripts, payload);
        }

        public static void Inspect(
            GameObject root,
            bool reportUnassignedReferences,
            string unassignedScope,
            XUUnityLightMcpPrefabValidatePayload payload)
        {
            if (root == null)
            {
                return;
            }

            var scope = NormalizeUnassignedScope(unassignedScope);
            payload.unassigned_reference_scope = reportUnassignedReferences ? scope : "not_reported";

            var transforms = root.GetComponentsInChildren<Transform>(true);
            foreach (var transform in transforms)
            {
                if (transform == null)
                {
                    continue;
                }

                payload.inspected_object_count++;
                var objectPath = XUUnityLightMcpUiTreeBuilder.BuildPath(transform);
                InspectGameObject(transform.gameObject, objectPath, reportUnassignedReferences, scope, payload);
            }
        }

        static void InspectGameObject(
            GameObject gameObject,
            string objectPath,
            bool reportUnassignedReferences,
            string unassignedScope,
            XUUnityLightMcpPrefabValidatePayload payload)
        {
            if (PrefabUtility.IsPrefabAssetMissing(gameObject))
            {
                payload.defects.Add(new XUUnityLightMcpPrefabDefect
                {
                    defect_type = "missing_prefab_instance",
                    severity = "error",
                    object_path = objectPath,
                    message = "The nested prefab instance points at a prefab asset that no longer exists."
                });
            }

            var components = gameObject.GetComponents<Component>();
            foreach (var component in components)
            {
                payload.inspected_component_count++;
                if (component == null)
                {
                    payload.defects.Add(new XUUnityLightMcpPrefabDefect
                    {
                        defect_type = "missing_script_guid",
                        severity = "error",
                        object_path = objectPath,
                        message = "A component references a script GUID that no longer resolves to a MonoScript."
                    });
                    continue;
                }

                InspectSerializedReferences(component, objectPath, reportUnassignedReferences, unassignedScope, payload);
            }
        }

        static void InspectSerializedReferences(
            Component component,
            string objectPath,
            bool reportUnassignedReferences,
            string unassignedScope,
            XUUnityLightMcpPrefabValidatePayload payload)
        {
            var componentType = component.GetType().Name;
            using var serializedObject = new SerializedObject(component);
            var declaredByProjectScript = IsProjectScript(serializedObject);
            var property = serializedObject.GetIterator();
            var visited = 0;

            while (property.NextVisible(true))
            {
                if (++visited > MAX_PROPERTIES_PER_COMPONENT)
                {
                    payload.warnings.Add(XUUnityLightMcpUiTreeBuilder.Diagnostic(
                        "prefab_property_scan_truncated",
                        $"'{objectPath}' component '{componentType}' exceeded the per-component property scan bound.",
                        MAX_PROPERTIES_PER_COMPONENT.ToString()));
                    break;
                }

                if (property.propertyType != SerializedPropertyType.ObjectReference)
                {
                    continue;
                }

                if (string.Equals(property.propertyPath, "m_Script", StringComparison.Ordinal))
                {
                    continue;
                }

                payload.inspected_reference_count++;
                var value = property.objectReferenceValue;
                if (value == null)
                {
                    if (HasSerializedObjectReference(property))
                    {
                        payload.defects.Add(new XUUnityLightMcpPrefabDefect
                        {
                            defect_type = "serialized_reference_missing_component",
                            severity = "error",
                            object_path = objectPath,
                            component_type = componentType,
                            property_path = property.propertyPath,
                            expected_type = DeclaredTypeName(property.type),
                            message = "A serialized reference points at an object that no longer exists."
                        });
                    }
                    else if (reportUnassignedReferences)
                    {
                        payload.unassigned_reference_count++;
                        if (InScope(unassignedScope, declaredByProjectScript, component, property))
                        {
                            payload.defects.Add(new XUUnityLightMcpPrefabDefect
                            {
                                defect_type = "serialized_reference_unassigned",
                                severity = "info",
                                object_path = objectPath,
                                component_type = componentType,
                                property_path = property.propertyPath,
                                expected_type = DeclaredTypeName(property.type),
                                message = "A serialized reference is empty. This is legal unless the component requires it."
                            });
                        }
                        else
                        {
                            payload.unassigned_reference_suppressed_count++;
                        }
                    }

                    continue;
                }

                ClassifyAssignedReference(property, value, objectPath, componentType, payload);
            }
        }

        static bool HasSerializedObjectReference(SerializedProperty property)
        {
#if UNITY_6000_5_OR_NEWER
            return !property.objectReferenceEntityIdValue.Equals(default(UnityEngine.EntityId));
#else
            return property.objectReferenceInstanceIDValue != 0;
#endif
        }

        static bool InScope(
            string unassignedScope,
            bool declaredByProjectScript,
            Component component,
            SerializedProperty property)
        {
            if (string.Equals(unassignedScope, UnassignedScopeAll, StringComparison.Ordinal))
            {
                return true;
            }

            if (!declaredByProjectScript)
            {
                return false;
            }

            return !string.Equals(unassignedScope, UnassignedScopeRequired, StringComparison.Ordinal)
                   || IsMarkedRequired(component, property.propertyPath);
        }

        static bool IsProjectScript(SerializedObject serializedObject)
        {
            var script = serializedObject.FindProperty("m_Script");
            if (script == null || script.propertyType != SerializedPropertyType.ObjectReference)
            {
                return false;
            }

            var scriptAsset = script.objectReferenceValue;
            if (scriptAsset == null)
            {
                return false;
            }

            var path = AssetDatabase.GetAssetPath(scriptAsset);
            return !string.IsNullOrEmpty(path)
                   && path.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase);
        }

        // Unity exposes no "required" flag on a serialized property, so the required scope reads the
        // project's own convention: a field attribute whose type name starts with Required, as used by
        // Odin's [Required] and NaughtyAttributes' [Required]. A project with no such convention gets an
        // empty required report rather than a guessed one. Nested members are not attribute-scanned.
        static bool IsMarkedRequired(Component component, string propertyPath)
        {
            if (propertyPath.IndexOf('.') >= 0)
            {
                return false;
            }

            var type = component.GetType();
            while (type != null)
            {
                var field = type.GetField(
                    propertyPath,
                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                if (field != null)
                {
                    foreach (var attribute in field.GetCustomAttributes(false))
                    {
                        if (attribute.GetType().Name.StartsWith("Required", StringComparison.Ordinal))
                        {
                            return true;
                        }
                    }

                    return false;
                }

                type = type.BaseType;
            }

            return false;
        }

        static void ClassifyAssignedReference(
            SerializedProperty property,
            UnityEngine.Object value,
            string objectPath,
            string componentType,
            XUUnityLightMcpPrefabValidatePayload payload)
        {
            var declared = DeclaredTypeName(property.type);
            if (string.IsNullOrEmpty(declared))
            {
                payload.unverified_reference_count++;
                return;
            }

            var observed = value.GetType();
            if (TypeChainContains(observed, declared))
            {
                return;
            }

            payload.defects.Add(new XUUnityLightMcpPrefabDefect
            {
                defect_type = "serialized_reference_type_mismatch",
                // Only "error" increments errorCount, so a warning here left validation passing for
                // exactly the defect class this validator exists to catch: a reference that
                // deserializes to an incompatible component and throws the moment it is used.
                severity = "error",
                object_path = objectPath,
                component_type = componentType,
                property_path = property.propertyPath,
                expected_type = declared,
                observed_type = observed.Name,
                observed_type_full_name = observed.FullName ?? observed.Name,
                message = "A serialized reference holds an object whose type is not in the declared field's type chain."
            });
        }

        public static bool TypeChainContains(Type type, string declared)
        {
            var current = type;
            while (current != null)
            {
                if (XUUnityLightMcpTypeNameMatcher.Matches(current, declared))
                {
                    return true;
                }

                current = current.BaseType;
            }

            foreach (var contract in type.GetInterfaces())
            {
                if (XUUnityLightMcpTypeNameMatcher.Matches(contract, declared))
                {
                    return true;
                }
            }

            return false;
        }

        public static string DeclaredTypeName(string serializedType)
        {
            var text = serializedType ?? "";
            var open = text.IndexOf('<');
            var close = text.LastIndexOf('>');
            if (open < 0 || close <= open)
            {
                return text;
            }

            return text.Substring(open + 1, close - open - 1).TrimStart('$');
        }

        public static List<string> DistinctDefectTypes(List<XUUnityLightMcpPrefabDefect> defects)
        {
            var types = new List<string>();
            foreach (var defect in defects)
            {
                if (types.Contains(defect.defect_type))
                {
                    continue;
                }

                types.Add(defect.defect_type);
            }

            types.Sort(StringComparer.Ordinal);
            return types;
        }
    }
}
