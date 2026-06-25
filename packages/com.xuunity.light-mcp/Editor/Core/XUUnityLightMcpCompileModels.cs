using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpCompilePlayerScriptsArgs
        {
            public string name = "";
            public string target = "";
            public string[] optionFlags = null;
            public string[] extraDefines = null;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCompileMatrixArgs
        {
            public bool stopOnFirstFailure;
            public List<XUUnityLightMcpCompilePlayerScriptsArgs> configurations = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCompileErrorItem
        {
            public string assembly_name = "";
            public string message = "";
            public string file = "";
            public int line;
            public int column;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCompileConfigPayload
        {
            public string name = "";
            public string target = "";
            public string target_group = "";
            public bool target_supported;
            public List<string> option_flags = new();
            public List<string> extra_defines = new();
            public string output_directory = "";
            public double duration_seconds;
            public string status = "infrastructure_error";
            public int compiled_assembly_count;
            public List<XUUnityLightMcpCompileErrorItem> errors = new();
            public int error_count;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCompilePlayerScriptsPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string request_completed_at_utc = "";
            public string settled_at_utc = "";
            public string completion_basis = "";
            public bool editor_is_compiling_after_request;
            public bool editor_is_updating_after_request;
            public bool editor_is_compiling_after_settle;
            public bool editor_is_updating_after_settle;
            public string playmode_state_after_settle = "edit";
            public string settle_request_id = "";
            public string settle_phase = "";
            public XUUnityLightMcpCompileConfigPayload result = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpCompileMatrixPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string status = "infrastructure_error";
            public string request_completed_at_utc = "";
            public string settled_at_utc = "";
            public string completion_basis = "";
            public bool editor_is_compiling_after_request;
            public bool editor_is_updating_after_request;
            public bool editor_is_compiling_after_settle;
            public bool editor_is_updating_after_settle;
            public string playmode_state_after_settle = "edit";
            public string settle_request_id = "";
            public string settle_phase = "";
            public bool stop_on_first_failure;
            public int total;
            public int passed;
            public int failed;
            public int skipped;
            public double duration_seconds;
            public List<XUUnityLightMcpCompileConfigPayload> results = new();
            public string validation_evidence = "unity_mcp";
        }
}
