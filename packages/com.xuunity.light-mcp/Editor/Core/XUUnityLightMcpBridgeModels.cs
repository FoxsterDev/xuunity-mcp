using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpBridgeConfig
        {
            public bool enabled;
            public int heartbeat_interval_ms = 2000;
            public int pump_interval_ms = 500;
            public bool auto_probe_on_startup = true;
            public string transport = "tcp_loopback";
            public string loopback_host = "127.0.0.1";
            public int loopback_port;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpBridgeState
        {
            public int bridge_version = 9;
            public string project_root = "";
            public int editor_pid;
            public string unity_version = "";
            public string transport_requested = "tcp_loopback";
            public string transport = "tcp_loopback";
            public string transport_listener_state = "";
            public string transport_host = "";
            public int transport_port;
            public string bridge_session_id = "";
            public int bridge_generation;
            public bool bridge_bootstrap_attached;
            public bool domain_reload_in_progress;
            public string domain_reload_started_utc = "";
            public bool asset_import_in_progress;
            public string asset_import_last_activity_utc = "";
            public bool package_operation_in_progress;
            public string package_operation_name = "";
            public string package_operation_phase = "";
            public string package_operation_started_utc = "";
            public bool script_reload_pending;
            public string script_reload_started_utc = "";
            public bool refresh_settle_pending;
            public string refresh_settle_request_id = "";
            public string refresh_settle_started_utc = "";
            public string refresh_settle_completed_utc = "";
            public string refresh_settle_phase = "";
            public bool refresh_settle_package_resolve_requested;
            public bool compile_settle_pending;
            public string compile_settle_request_id = "";
            public string compile_settle_started_utc = "";
            public string compile_settle_completed_utc = "";
            public string compile_settle_phase = "";
            public string compile_settle_operation = "";
            public bool playmode_transition_pending;
            public string playmode_transition_request_id = "";
            public string playmode_transition_action = "";
            public string playmode_transition_target_state = "";
            public string playmode_transition_started_utc = "";
            public string playmode_transition_completed_utc = "";
            public string playmode_transition_phase = "";
            public bool is_compiling;
            public bool script_compilation_failed;
            public int compiler_error_count;
            public List<XUUnityLightMcpCompileErrorItem> recent_compiler_diagnostics = new();
            public string compiler_diagnostics_source = "";
            public bool is_playing;
            public bool is_paused;
            public bool is_updating;
            public bool is_playing_or_will_change_playmode;
            public string playmode_state = "edit";
            public string heartbeat_utc = "";
            public string last_pump_utc = "";
            public string last_processed_request_id = "";
            public int pending_request_count;
            public string busy_reason = "";
            public string busy_reason_detail = "";
            public string active_request_id = "";
            public string active_operation = "";
            public string active_operation_started_utc = "";
            public string active_test_request_id = "";
            public string active_test_operation = "";
            public string active_test_run_phase = "";
            public string active_test_started_at_utc = "";
            public string active_test_last_started_test = "";
            public string active_test_last_finished_test = "";
            public string active_test_last_progress_at_utc = "";
            public int active_test_runtime_timeout_ms;
            public string last_completed_operation = "";
            public string last_completed_operation_status = "";
            public double last_completed_operation_duration_seconds;
            public string request_journal_directory = "";
            public string request_journal_head = "";
            public string editor_log_path = "";
            public string last_error = "";
            public string health_status = "";
            public int supported_operation_count;
            public int disabled_operation_count;
            public string capabilities_report_path = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpRequest
        {
            public string request_id = "";
            public string operation = "";
            public string project_root = "";
            public string created_at_utc = "";
            public int timeout_ms = 30000;
            public string args_json = "{}";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpError
        {
            public string code = "";
            public string message = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpResponse
        {
            public string request_id = "";
            public string status = "";
            public string completed_at_utc = "";
            public string payload_type = "";
            public string payload_json = "";
            public XUUnityLightMcpError error;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpStatusPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public bool editor_running = true;
            public bool mcp_reachable = true;
            public string transport_requested = "tcp_loopback";
            public string transport = "tcp_loopback";
            public string transport_listener_state = "";
            public string transport_host = "";
            public int transport_port;
            public string bridge_session_id = "";
            public int bridge_generation;
            public bool bridge_bootstrap_attached;
            public bool domain_reload_in_progress;
            public string domain_reload_started_utc = "";
            public bool asset_import_in_progress;
            public string asset_import_last_activity_utc = "";
            public bool package_operation_in_progress;
            public string package_operation_name = "";
            public string package_operation_phase = "";
            public string package_operation_started_utc = "";
            public bool script_reload_pending;
            public string script_reload_started_utc = "";
            public bool refresh_settle_pending;
            public string refresh_settle_request_id = "";
            public string refresh_settle_started_utc = "";
            public string refresh_settle_completed_utc = "";
            public string refresh_settle_phase = "";
            public bool refresh_settle_package_resolve_requested;
            public bool compile_settle_pending;
            public string compile_settle_request_id = "";
            public string compile_settle_started_utc = "";
            public string compile_settle_completed_utc = "";
            public string compile_settle_phase = "";
            public string compile_settle_operation = "";
            public bool playmode_transition_pending;
            public string playmode_transition_request_id = "";
            public string playmode_transition_action = "";
            public string playmode_transition_target_state = "";
            public string playmode_transition_started_utc = "";
            public string playmode_transition_completed_utc = "";
            public string playmode_transition_phase = "";
            public bool is_compiling;
            public bool script_compilation_failed;
            public int compiler_error_count;
            public List<XUUnityLightMcpCompileErrorItem> recent_compiler_diagnostics = new();
            public string compiler_diagnostics_source = "";
            public bool is_playing;
            public bool is_paused;
            public bool is_updating;
            public bool is_playing_or_will_change_playmode;
            public string playmode_state = "edit";
            public string last_pump_utc = "";
            public string last_processed_request_id = "";
            public int pending_request_count;
            public string busy_reason = "";
            public string busy_reason_detail = "";
            public string active_request_id = "";
            public string active_operation = "";
            public string active_operation_started_utc = "";
            public string last_completed_operation = "";
            public string last_completed_operation_status = "";
            public double last_completed_operation_duration_seconds;
            public string request_journal_directory = "";
            public string request_journal_head = "";
            public string editor_log_path = "";
            public string health_status = "";
            public List<string> supported_operations = new();
            public List<string> disabled_operations = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpBridgeGenerationState
        {
            public int bridge_generation;
            public string bridge_session_id = "";
            public string bootstrap_attached_at_utc = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPersistedPlayModeTransitionState
        {
            public string request_id = "";
            public string action = "";
            public string target_state = "";
            public string started_at_utc = "";
            public string phase = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpRequestJournalEvent
        {
            public string event_id = "";
            public string event_type = "";
            public string event_source = "unity_bridge";
            public string event_at_utc = "";
            public string project_root = "";
            public string bridge_session_id = "";
            public int bridge_generation;
            public string request_id = "";
            public string operation = "";
            public string operation_status = "";
            public int pending_request_count;
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public string reason = "";
            public bool retryable;
            public string reclassified_status = "";
            public int previous_bridge_generation;
            public string previous_bridge_session_id = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpActiveRequestSnapshot
        {
            public string request_id = "";
            public string operation = "";
            public string started_at_utc = "";
        }
}
