using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
    [Serializable]
    internal sealed class XUUnityLightMcpAssetSnapshotArgs
    {
        public string assetPath = "";
        public int maxDepth = 2;
        public int maxFields = 200;
        public int maxArrayElements = 8;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpAssetSnapshotField
    {
        public string path = "";
        public string type = "";
        public string value = "";
        public int depth;
        public int array_size = -1;
        public bool array_truncated;
        public bool children_omitted;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpAssetSnapshotPayload
    {
        public string backend_id = "xuunity.light_unity_mcp";
        public string project_root = "";
        public string operation = "unity.asset.snapshot";
        public string asset_path = "";
        public string guid = "";
        public string main_asset_type = "";
        public string main_asset_name = "";
        public int sub_asset_count;
        public int max_depth;
        public int max_fields;
        public int max_array_elements;
        public List<XUUnityLightMcpAssetSnapshotField> fields = new();
        public int field_count;
        public bool truncated;
        public string truncation_reason = "";
        public bool success;
        public string read_scope = "serialized_fields_read_only";
        public string validation_evidence = "unity_mcp";
    }
}
