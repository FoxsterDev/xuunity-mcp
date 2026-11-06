using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpConsoleTailArgs
        {
            public int limit = 50;
            public string[] includeTypes = null;
            public bool includeStackTraces;
            public string source = "console";
            public int maxPayloadBytes;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleGrepArgs
        {
            public string pattern = "";
            public string excludePattern = "";
            public bool regex;
            public bool ignoreCase = true;
            public bool includeStackTraces;
            public bool includeBuildPipelineNoise;
            public int limit = 20;
            public string[] includeTypes = null;
            public string since = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleItem
        {
            public string type = "unknown";
            public string message = "";
            public string timestamp = "";
            public string stack_trace = "";
        }

        [Serializable]
        internal class XUUnityLightMcpConsolePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string source = "console";
            public string pattern = "";
            public string exclude_pattern = "";
            public bool regex;
            public bool ignore_case;
            public bool include_stack_traces;
            public int match_count;
            public int excluded_count;
            public int build_pipeline_suppressed_count;
            public List<XUUnityLightMcpConsoleItem> items = new();
            public bool truncated;
            public string result_trust_class = "";
            public string console_tail_caveat = "";
            public string recommended_next_action = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleTailBoundedPayload : XUUnityLightMcpConsolePayload
        {
            public int max_payload_bytes;
            public int payload_bytes_estimate;
            public bool byte_budget_truncated;
            public int items_dropped_for_byte_budget;
            public bool newest_item_truncated;
            public string byte_budget_enforced_by = "unity_bridge";
            public string truncation_recovery_tool = "";
            public string truncation_recovery_hint = "";
            public string full_payload_recovery_hint = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleGrepPayload : XUUnityLightMcpConsolePayload
        {
            public string since = "";
            public bool since_anchor_resolved;
            public string since_anchor_reason = "";
            public long since_anchor_sequence;
            public string since_anchor_started_utc = "";
            public bool since_scope_complete;
            public string search_verdict = "";
            public string search_verdict_reason = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneData
        {
            public string name = "";
            public string path = "";
            public bool is_dirty;
            public int root_count;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpRootObject
        {
            public string name = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneSnapshotPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public XUUnityLightMcpSceneData active_scene = new();
            public List<XUUnityLightMcpRootObject> root_objects = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneOpenArgs
        {
            public string scenePath = "";
            public bool allowDirtySceneDiscard;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneOpenPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "failed";
            public bool opened;
            public string outcome = "";
            public string requested_scene_path = "";
            public bool allow_dirty_scene_discard;
            public XUUnityLightMcpSceneData previous_scene = new();
            public XUUnityLightMcpSceneData active_scene = new();
            public string failure_reason = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneAssertArgs
        {
            public string expectedName = "";
            public string expectedPath = "";
            public string[] requiredRootNames = null;
            public bool allowDirty = true;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpSceneAssertPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "failed";
            public bool passed;
            public string failure_reason = "";
            public string expected_name = "";
            public string expected_path = "";
            public bool allow_dirty = true;
            public XUUnityLightMcpSceneData active_scene = new();
            public List<XUUnityLightMcpRootObject> root_objects = new();
            public List<string> required_root_names = new();
            public List<string> missing_root_names = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestFailure
        {
            public string name = "";
            public string message = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestsPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "infrastructure_error";
            public int total;
            public int passed;
            public int failed;
            public int skipped;
            public int not_run;
            public bool cancelled;
            public string cancel_requested_at_utc = "";
            public double duration_seconds;
            public List<XUUnityLightMcpTestFailure> failures = new();
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public string completion_basis = "";
            public string playmode_state_after_settle = "";
            public string playmode_state_after_test_callbacks = "";
            public string playmode_state_after_host_settle = "";
            public string playmode_state_after_settle_source = "";
            public bool playmode_state_accounting_consistent;
            public string playmode_state_accounting_note = "";
            public string run_phase = "";
            public string last_progress_at_utc = "";
            public string timeout_classification = "";
            public int runtime_timeout_ms;
            public string filter_summary = "";
            public bool filter_requested;
            public string test_verdict = "";
            public string recommended_next_action = "";
            public string recommended_recovery_command = "";
            public string last_started_test = "";
            public string last_finished_test = "";
            public bool lifecycle_churn_observed;
            public long console_error_count_since_request_start;
            public string console_error_count_trust_class = "";
            public bool console_error_pressure_detected;
            public long console_error_expected_by_test_count;
            public long console_error_not_expected_count;
            public string console_error_classification_basis = "";
            public List<XUUnityLightMcpConsoleErrorSample> console_error_samples = new();
            public XUUnityLightMcpTestEnvironment test_environment = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleErrorSample
        {
            public string type = "";
            public string message = "";
            public string active_test = "";
            public string classification = "";
            public string logged_at_utc = "";
        }

        internal sealed class XUUnityLightMcpConsoleErrorAttribution
        {
            public string request_id = "";
            public string counter_session_id = "";
            public string basis = "";
            public long expected_by_test_count;
            public long not_expected_count;
            public List<XUUnityLightMcpConsoleErrorSample> samples = new();

            public bool IsEmpty => expected_by_test_count <= 0 && not_expected_count <= 0 && samples.Count == 0;
        }

        internal static class XUUnityLightMcpConsoleErrorClassification
        {
            public const int MaxSamples = 3;
            public const int MaxSampleMessageChars = 240;
            public const int MaxSampleActiveTestChars = 160;
            public const string ExpectedByTest = "expected_by_test";
            public const string Unexpected = "unexpected";
            public const string Unclassified = "unclassified";
            public const string BasisNone = "none";
            public const string BasisLogScope = "utf_log_scope";
            public const string BasisLogScopeUnavailable = "utf_log_scope_unavailable";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestEnvironment
        {
            public string captured_at = "";
            public string capture_status = "";
            public int render_width;
            public int render_height;
            public string preset_label = "";
            public string preset_kind = "";
            public int preset_width;
            public int preset_height;
            public string render_matches_preset = "";
            public string game_view_group = "";
            public string build_target = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestsArgs
        {
            public string[] testNames = null;
            public string[] groupNames = null;
            public string[] categoryNames = null;
            public string[] assemblyNames = null;
            public bool allowDirtySceneDiscard;
            public bool allowStaleEditorDomain;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestsCancelArgs
        {
            public string requestId = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestsCancelPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string request_id = "";
            public string operation = "";
            public string run_guid = "";
            public bool cancel_requested;
            public bool cancel_accepted;
            public string cancel_api = "";
            public string reason = "";
            public string playmode_state = "";
            public int passed_so_far;
            public int failed_so_far;
            public string last_started_test = "";
            public string recommended_next_action = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPersistedTestRunState
        {
            public string request_id = "";
            public string operation = "";
            public string project_root = "";
            public string test_mode = "";
            public string started_at_utc = "";
            public int request_timeout_ms = 30000;
            public int runtime_timeout_ms = 30000;
            public string run_phase = "submitted";
            public string last_progress_at_utc = "";
            public string timeout_classification = "";
            public string completed_at_utc = "";
            public string filter_summary = "";
            public bool filter_requested;
            public string status = "";
            public string test_verdict = "";
            public string recommended_next_action = "";
            public string recommended_recovery_command = "";
            public string response_handoff_state = "pending";
            public int total;
            public int passed;
            public int failed;
            public int skipped;
            public List<XUUnityLightMcpTestFailure> failures = new();
            public string last_started_test = "";
            public string last_finished_test = "";
            public string run_guid = "";
            public string cancel_requested_at_utc = "";
            public bool cancelled;
            public string completion_basis = "";
            public string playmode_state_after_settle = "";
            public string playmode_state_after_test_callbacks = "";
            public string playmode_state_after_host_settle = "";
            public string playmode_state_after_settle_source = "";
            public bool playmode_state_accounting_consistent;
            public string playmode_state_accounting_note = "";
            public bool lifecycle_churn_observed;
            public long console_error_count_at_request_start;
            public string console_error_counter_session_id_at_request_start = "";
            public List<XUUnityLightMcpConsoleErrorSample> console_error_samples = new();
            public long console_error_expected_by_test_count;
            public long console_error_expected_by_test_count_in_session;
            public string console_error_expected_by_test_counter_session_id = "";
            public long console_error_not_expected_recorded_count;
            public string console_error_classification_basis = "";
            public long console_error_count_at_completion;
            public string console_error_count_trust_class_at_completion = "";
            public long console_error_not_expected_count_at_completion;
            public XUUnityLightMcpTestEnvironment test_environment = new();
        }
}
