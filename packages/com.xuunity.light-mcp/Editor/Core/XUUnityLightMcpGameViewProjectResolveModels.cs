using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        internal static class XUUnityLightMcpGameView
        {
            public const int DefaultImageBudgetBytes = 48000;

            public const string ImageOmittedPayloadBudget = "payload_budget";
            public const string ImageOmittedNotRequested = "not_requested";
            public const string ImageFilePathNextAction = "read_file_path_with_an_image_reader";
        }

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
            public int imageBudgetBytes = XUUnityLightMcpGameView.DefaultImageBudgetBytes;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpGameViewScreenshotPayload : XUUnityLightMcpPlayModeLivenessEvidence
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string capture_source = "game_view";
            public string file_path = "";
            public int width;
            public int height;
            public int render_width;
            public int render_height;
            public int screen_width;
            public int screen_height;
            public bool render_target_available;
            public bool render_target_differs_from_screen;
            public string image_base64 = "";
            public bool image_included;
            public bool image_requested;
            public string image_omitted_reason = "";
            public int image_bytes;
            public int image_budget_bytes;
            public string recommended_next_action = "";
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
        internal class XUUnityLightMcpProjectRefreshPayload
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
        internal sealed class XUUnityLightMcpProjectRefreshTimeoutPayload : XUUnityLightMcpProjectRefreshPayload
        {
            public bool settle_timed_out;
            public string settle_timeout_classification = "";
            public string settle_phase_at_timeout = "";
            public bool refresh_settle_pending_at_timeout;
            public bool editor_is_compiling_at_timeout;
            public bool editor_is_updating_at_timeout;
            public string playmode_state_at_timeout = "";
            public int stable_idle_ticks_at_timeout;
            public bool operation_may_have_completed;
            public string expected_settle_request_id = "";
            public string observed_settle_request_id = "";
            public string settled_completion = "unproven";
            public string settled_completion_reason = "";
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
            public string required_build_target = "";
            public string active_build_target_before = "";
            public string active_build_target_after = "";
            public string build_target_precondition = "";
            public bool target_support_loaded;
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
            public string resolver_output_freshness = "unproven";
            public bool decision_ready;
            public string recommended_next_action = "verify_resolver_output_freshness_and_generated_diff";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkAndroidResolveArgs
        {
            public bool force = true;
            public bool refreshBefore = true;
            public int stableIdleTicks = 2;
            public List<string> trackedGeneratedPaths = new();
            public List<XUUnityLightMcpSdkDependencyExpectation> expectations = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkGeneratedOutputEvidence
        {
            public string path = "";
            public string full_path = "";
            public bool file_exists;
            public long file_size_bytes;
            public string sha256 = "";
            public string error = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSdkAndroidResolvePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "failed";
            public string verdict = "inconclusive";
            public string trust_class = "unproven";
            public bool decision_ready;
            public string failure_class = "";
            public string required_build_target = "Android";
            public string active_build_target = "";
            public string build_target_precondition = "";
            public bool target_support_loaded;
            public bool force;
            public bool asset_refresh_before_requested;
            public string resolver_adapter = "";
            public string resolver_completion_source = "edm4u_callback";
            public bool resolver_callback_received;
            public bool resolver_callback_success;
            public string resolver_callback_at_utc = "";
            public string resolver_output_freshness = "unproven";
            public int stable_idle_ticks_required = 2;
            public int stable_idle_ticks_observed;
            public List<XUUnityLightMcpSdkGeneratedOutputEvidence> generated_outputs = new();
            public XUUnityLightMcpSdkDependencyVerifyPayload dependency_verification = new();
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public double duration_seconds;
            public string recommended_next_action = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPersistedSdkAndroidResolveState
        {
            public string request_id = "";
            public string operation = "unity.sdk.android_resolve";
            public string project_root = "";
            public string started_at_utc = "";
            public string deadline_at_utc = "";
            public string completed_at_utc = "";
            public string response_handoff_state = "pending";
            public XUUnityLightMcpSdkAndroidResolveArgs args = new();
            public string active_build_target = "";
            public bool target_support_loaded;
            public string resolver_adapter = "";
            public bool resolver_callback_received;
            public bool resolver_callback_success;
            public string resolver_callback_at_utc = "";
            public int stable_idle_ticks_observed;
            public string last_output_signature = "";
            public List<XUUnityLightMcpSdkGeneratedOutputEvidence> generated_outputs = new();
            public XUUnityLightMcpSdkDependencyVerifyPayload dependency_verification = new();
            public string status = "running";
            public string verdict = "inconclusive";
            public string trust_class = "unproven";
            public bool decision_ready;
            public string failure_class = "";
            public string resolver_output_freshness = "unproven";
            public string recommended_next_action = "";
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
