using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpCapabilityRecord
        {
            public string capability_id = "";
            public string adapter_id = "";
            public bool supported;
            public string status = "unknown";
            public string reason = "";
            public string dependency = "";
            public string installed_dependency_version = "";
            public string minimum_dependency_version = "";
            public string recommended_dependency_version = "";
            public string recommendation_basis = "";
            public string recommended_action = "";
            public bool upgrade_recommended;
            public List<string> operations = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCapabilitiesReport
        {
            public int probe_version = 1;
            public string project_root = "";
            public string unity_version = "";
            public string checked_at_utc = "";
            public string status = "unknown";
            public List<string> supported_operations = new();
            public List<string> disabled_operations = new();
            public List<XUUnityLightMcpCapabilityRecord> capabilities = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCapabilitiesPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public XUUnityLightMcpCapabilitiesReport report = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPlayModeStatePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public bool playmode_transition_pending;
            public string playmode_transition_request_id = "";
            public string playmode_transition_action = "";
            public string playmode_transition_target_state = "";
            public string playmode_transition_started_utc = "";
            public string playmode_transition_completed_utc = "";
            public string playmode_transition_phase = "";
            public bool is_playing;
            public bool is_paused;
            public bool is_playing_or_will_change_playmode;
            public string playmode_state = "edit";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPlayModeSetArgs
        {
            public string action = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpPlayModeSetPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string requested_action = "";
            public string outcome = "";
            public string request_completed_at_utc = "";
            public string settled_at_utc = "";
            public string completion_basis = "";
            public string settle_request_id = "";
            public string settle_phase = "";
            public string settle_target_state = "";
            public bool is_playing;
            public bool is_paused;
            public bool is_playing_or_will_change_playmode;
            public string playmode_state = "edit";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpBuildTargetGetPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string active_build_target = "";
            public string active_build_target_group = "";
            public string selected_build_target_group = "";
            public bool target_support_loaded;
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpBuildTargetSwitchArgs
        {
            public string target = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpBuildTargetSwitchPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string requested_build_target = "";
            public string previous_build_target = "";
            public string active_build_target = "";
            public string active_build_target_group = "";
            public string selected_build_target_group = "";
            public bool target_support_loaded;
            public string outcome = "";
            public string request_completed_at_utc = "";
            public string settled_at_utc = "";
            public string completion_basis = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpEditorQuitPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string outcome = "quit_requested";
            public string requested_at_utc = "";
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpInstallTestFrameworkArgs
        {
            public bool approve;
            public string version = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpInstallTestFrameworkPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string unity_version = "";
            public string dependency = "";
            public string requested_version = "";
            public string minimum_dependency_version = "";
            public string recommended_dependency_version = "";
            public string recommendation_basis = "unity_version_policy";
            public string installed_dependency_version_before = "";
            public string installed_dependency_version_after = "";
            public bool upgrade_recommended_before;
            public string outcome = "";
            public string recommended_action = "";
            public string next_action = "";
            public string requested_at_utc = "";
            public string validation_evidence = "unity_mcp";
        }
}
