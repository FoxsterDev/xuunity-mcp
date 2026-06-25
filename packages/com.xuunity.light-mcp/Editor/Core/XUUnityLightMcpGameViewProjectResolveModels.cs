using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpGameViewConfigureArgs
        {
            public int width;
            public int height;
            public string group = "";
            public string label = "";
            public bool allowCreateCustomSize;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewData
        {
            public string group = "";
            public string label = "";
            public int width;
            public int height;
            public bool is_custom;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewProbeResult
        {
            public string adapter_id = "game_view_reflection_v1";
            public bool supported;
            public string reason = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewConfigurePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string outcome = "";
            public XUUnityLightMcpGameViewData game_view = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewScreenshotArgs
        {
            public string fileName = "";
            public bool includeImage;
            public int maxResolution = 640;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewScreenshotPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string capture_source = "game_view";
            public string file_path = "";
            public int width;
            public int height;
            public string image_base64 = "";
            public bool image_included;
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpProjectRefreshArgs
        {
            public bool forceAssetRefresh = true;
            public bool resolvePackages = true;
            public bool rerunHealthProbe = true;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpProjectRefreshPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string outcome = "";
            public string requested_outcome = "";
            public string request_completed_at_utc = "";
            public string settled_at_utc = "";
            public string completion_basis = "";
            public bool asset_database_refreshed;
            public bool package_resolve_requested;
            public bool capabilities_report_refreshed;
            public bool editor_is_compiling_after_request;
            public bool editor_is_updating_after_request;
            public string playmode_state_after_request = "edit";
            public bool editor_is_compiling_after_settle;
            public bool editor_is_updating_after_settle;
            public string playmode_state_after_settle = "edit";
            public string settle_request_id = "";
            public string settle_phase = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpEdm4uResolveArgs
        {
            public string platform = "android";
            public bool force = true;
            public bool refreshBefore = true;
            public bool refreshAfter = true;
            public string[] menuPathCandidates = null;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpMenuItemAttempt
        {
            public string menu_path = "";
            public bool executed;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpEdm4uResolvePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string platform = "";
            public bool force;
            public string outcome = "";
            public string executed_menu_path = "";
            public List<XUUnityLightMcpMenuItemAttempt> attempted_menu_items = new();
            public bool asset_refresh_before_requested;
            public bool asset_refresh_after_requested;
            public bool editor_is_compiling_after_request;
            public bool editor_is_updating_after_request;
            public string playmode_state_after_request = "edit";
            public string request_completed_at_utc = "";
            public string settle_request_id = "";
            public string settle_phase = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkDependencyVerifyArgs
        {
            public bool stopOnFirstFailure;
            public List<XUUnityLightMcpSdkDependencyExpectation> expectations = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkDependencyExpectation
        {
            public string id = "";
            public string platform = "";
            public string path = "";
            public string kind = "file_contains";
            public string value = "";
            public string version = "";
            public string minVersion = "";
            public bool optional;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkDependencyVerifyResult
        {
            public string id = "";
            public string platform = "";
            public string path = "";
            public string full_path = "";
            public string kind = "";
            public string value = "";
            public string expected_version = "";
            public string expected_min_version = "";
            public string actual_version = "";
            public string status = "failed";
            public string message = "";
            public bool file_exists;
            public long file_size_bytes;
            public string sha256 = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkDependencyVerifyPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "failed";
            public int total;
            public int passed;
            public int failed;
            public int skipped;
            public bool stop_on_first_failure;
            public List<XUUnityLightMcpSdkDependencyVerifyResult> results = new();
            public string validation_evidence = "unity_mcp";
        }
}
