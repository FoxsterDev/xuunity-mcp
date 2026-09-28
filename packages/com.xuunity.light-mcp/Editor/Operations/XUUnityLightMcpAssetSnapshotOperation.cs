using System;
using System.Globalization;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpAssetSnapshotOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.asset.snapshot";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpAssetSnapshotArgs()
                : JsonUtility.FromJson<XUUnityLightMcpAssetSnapshotArgs>(request.args_json) ?? new XUUnityLightMcpAssetSnapshotArgs();

            var payload = new XUUnityLightMcpAssetSnapshotPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                asset_path = NormalizeAssetPath(args.assetPath),
                max_depth = Math.Max(0, args.maxDepth),
                max_fields = Math.Max(1, args.maxFields),
                max_array_elements = Math.Max(0, args.maxArrayElements),
            };

            if (!IsProjectAssetPath(payload.asset_path))
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "asset_path_invalid",
                    "assetPath must be a project-relative path under Assets/ or Packages/, for example Assets/Configs/Game.asset.");
            }

            var asset = AssetDatabase.LoadMainAssetAtPath(payload.asset_path);
            if (asset == null)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "asset_not_found",
                    $"No main asset exists at '{payload.asset_path}'.");
            }

            payload.guid = AssetDatabase.AssetPathToGUID(payload.asset_path) ?? "";
            payload.main_asset_type = asset.GetType().FullName ?? asset.GetType().Name;
            payload.main_asset_name = asset.name ?? "";
            var representations = AssetDatabase.LoadAllAssetRepresentationsAtPath(payload.asset_path);
            payload.sub_asset_count = representations == null ? 0 : representations.Length;

            try
            {
                using var serializedObject = new SerializedObject(asset);
                new FieldWalker(payload).WalkRoot(serializedObject);
            }
            catch (Exception exception)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "asset_snapshot_failed",
                    exception.Message);
            }

            payload.field_count = payload.fields.Count;
            payload.success = true;
            return XUUnityLightMcpResponseWriter.Success(request.request_id, OperationName, JsonUtility.ToJson(payload));
        }

        static string NormalizeAssetPath(string assetPath)
        {
            var normalized = (assetPath ?? "").Trim().Replace('\\', '/');
            while (normalized.StartsWith("./", StringComparison.Ordinal))
            {
                normalized = normalized.Substring(2);
            }

            return normalized;
        }

        static bool IsProjectAssetPath(string assetPath)
        {
            return assetPath.StartsWith("Assets/", StringComparison.Ordinal)
                || assetPath.StartsWith("Packages/", StringComparison.Ordinal);
        }

        sealed class FieldWalker
        {
            readonly XUUnityLightMcpAssetSnapshotPayload _payload;

            public FieldWalker(XUUnityLightMcpAssetSnapshotPayload payload)
            {
                _payload = payload;
            }

            public void WalkRoot(SerializedObject serializedObject)
            {
                var iterator = serializedObject.GetIterator();
                if (!iterator.NextVisible(true))
                {
                    return;
                }

                do
                {
                    if (!Visit(iterator, 0))
                    {
                        return;
                    }
                }
                while (iterator.NextVisible(false));
            }

            bool Visit(SerializedProperty property, int depth)
            {
                if (_payload.fields.Count >= _payload.max_fields)
                {
                    _payload.truncated = true;
                    _payload.truncation_reason = "max_fields_reached";
                    return false;
                }

                var field = new XUUnityLightMcpAssetSnapshotField
                {
                    path = property.propertyPath,
                    type = property.propertyType.ToString(),
                    value = DescribeValue(property),
                    depth = depth,
                };
                _payload.fields.Add(field);

                if (property.isArray && property.propertyType != SerializedPropertyType.String)
                {
                    field.type = "Array";
                    field.array_size = property.arraySize;
                    return VisitArrayElements(property, field, depth);
                }

                var hasChildren = property.propertyType == SerializedPropertyType.Generic
                    || property.propertyType == SerializedPropertyType.ManagedReference;
                if (!hasChildren || !property.hasVisibleChildren)
                {
                    return true;
                }

                if (depth >= _payload.max_depth)
                {
                    field.children_omitted = true;
                    return true;
                }

                return VisitChildren(property, depth + 1);
            }

            bool VisitChildren(SerializedProperty property, int depth)
            {
                var child = property.Copy();
                var end = property.GetEndProperty();
                if (!child.NextVisible(true))
                {
                    return true;
                }

                do
                {
                    if (SerializedProperty.EqualContents(child, end))
                    {
                        return true;
                    }

                    if (!Visit(child, depth))
                    {
                        return false;
                    }
                }
                while (child.NextVisible(false));
                return true;
            }

            bool VisitArrayElements(SerializedProperty arrayProperty, XUUnityLightMcpAssetSnapshotField field, int depth)
            {
                var size = arrayProperty.arraySize;
                var limit = Math.Min(size, _payload.max_array_elements);
                field.array_truncated = size > limit;
                if (depth >= _payload.max_depth)
                {
                    field.children_omitted = size > 0;
                    return true;
                }

                for (var index = 0; index < limit; index++)
                {
                    if (!Visit(arrayProperty.GetArrayElementAtIndex(index), depth + 1))
                    {
                        return false;
                    }
                }

                return true;
            }

            static string DescribeValue(SerializedProperty property)
            {
                switch (property.propertyType)
                {
                    case SerializedPropertyType.Integer:
                        return property.longValue.ToString(CultureInfo.InvariantCulture);
                    case SerializedPropertyType.Boolean:
                        return property.boolValue ? "true" : "false";
                    case SerializedPropertyType.Float:
                        return property.doubleValue.ToString("R", CultureInfo.InvariantCulture);
                    case SerializedPropertyType.String:
                        return property.stringValue ?? "";
                    case SerializedPropertyType.Color:
                        return property.colorValue.ToString();
                    case SerializedPropertyType.ObjectReference:
                        return DescribeObjectReference(property.objectReferenceValue);
                    case SerializedPropertyType.LayerMask:
                    case SerializedPropertyType.ArraySize:
                    case SerializedPropertyType.FixedBufferSize:
                        return property.intValue.ToString(CultureInfo.InvariantCulture);
                    case SerializedPropertyType.Enum:
                        return DescribeEnum(property);
                    case SerializedPropertyType.Vector2:
                        return property.vector2Value.ToString();
                    case SerializedPropertyType.Vector3:
                        return property.vector3Value.ToString();
                    case SerializedPropertyType.Vector4:
                        return property.vector4Value.ToString();
                    case SerializedPropertyType.Rect:
                        return property.rectValue.ToString();
                    case SerializedPropertyType.Character:
                        return ((char)property.intValue).ToString();
                    case SerializedPropertyType.AnimationCurve:
                        return $"AnimationCurve(keys={property.animationCurveValue?.length ?? 0})";
                    case SerializedPropertyType.Bounds:
                        return property.boundsValue.ToString();
                    case SerializedPropertyType.Gradient:
                        return "Gradient";
                    case SerializedPropertyType.Quaternion:
                        return property.quaternionValue.ToString();
                    case SerializedPropertyType.ExposedReference:
                        return "ExposedReference";
                    case SerializedPropertyType.Vector2Int:
                        return property.vector2IntValue.ToString();
                    case SerializedPropertyType.Vector3Int:
                        return property.vector3IntValue.ToString();
                    case SerializedPropertyType.RectInt:
                        return property.rectIntValue.ToString();
                    case SerializedPropertyType.BoundsInt:
                        return property.boundsIntValue.ToString();
                    case SerializedPropertyType.ManagedReference:
                        return property.managedReferenceFullTypename ?? "";
                    case SerializedPropertyType.Hash128:
                        return property.hash128Value.ToString();
                    case SerializedPropertyType.Generic:
                        return property.isArray ? $"array[{property.arraySize}]" : "struct";
                    default:
                        return "";
                }
            }

            static string DescribeObjectReference(UnityEngine.Object value)
            {
                if (value == null)
                {
                    return "null";
                }

                var assetPath = AssetDatabase.GetAssetPath(value) ?? "";
                return assetPath.Length == 0
                    ? $"{value.GetType().Name}:{value.name}"
                    : $"{value.GetType().Name}:{value.name}@{assetPath}";
            }

            static string DescribeEnum(SerializedProperty property)
            {
                var names = property.enumNames;
                var index = property.enumValueIndex;
                if (names != null && index >= 0 && index < names.Length)
                {
                    return names[index];
                }

                return property.intValue.ToString(CultureInfo.InvariantCulture);
            }
        }
    }
}
