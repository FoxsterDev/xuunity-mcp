using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpConsoleTailArgs
        {
            public int limit = 50;
            public string[] includeTypes = null;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpConsoleGrepArgs
        {
            public string pattern = "";
            public bool regex;
            public bool ignoreCase = true;
            public bool includeStackTraces;
            public int limit = 20;
            public string[] includeTypes = null;
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
        internal sealed class XUUnityLightMcpConsolePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string pattern = "";
            public bool regex;
            public bool ignore_case;
            public int match_count;
            public List<XUUnityLightMcpConsoleItem> items = new();
            public bool truncated;
            public string validation_evidence = "unity_mcp";
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
            public double duration_seconds;
            public List<XUUnityLightMcpTestFailure> failures = new();
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public string completion_basis = "";
            public string playmode_state_after_settle = "";
            public string run_phase = "";
            public string last_progress_at_utc = "";
            public string timeout_classification = "";
            public int runtime_timeout_ms;
            public string last_started_test = "";
            public string last_finished_test = "";
            public bool lifecycle_churn_observed;
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpTestsArgs
        {
            public string[] testNames = null;
            public string[] groupNames = null;
            public string[] categoryNames = null;
            public string[] assemblyNames = null;
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
            public string response_handoff_state = "pending";
            public int total;
            public int passed;
            public int failed;
            public int skipped;
            public List<XUUnityLightMcpTestFailure> failures = new();
            public string last_started_test = "";
            public string last_finished_test = "";
            public string completion_basis = "";
            public string playmode_state_after_settle = "";
            public bool lifecycle_churn_observed;
        }
}
