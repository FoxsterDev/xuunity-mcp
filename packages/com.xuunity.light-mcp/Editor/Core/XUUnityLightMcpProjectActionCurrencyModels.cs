using System;

namespace XUUnity.LightMcp.Editor.Core
{
    [Serializable]
    internal sealed class XUUnityLightMcpProjectActionCurrencyArgs
    {
        public string actionId = "";
        public string catalogPath = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpProjectActionCurrencyPayload
    {
        public string backend_id = "xuunity.light_unity_mcp";
        public string project_root = "";
        public string action_id = "";
        public string catalog_path = "";
        public bool requires_fresh_assets;
        public bool asset_refresh_performed;
        public string asset_refresh_step_id = "";
        public string editor_domain_loaded_utc = "";
        public bool editor_domain_current;
        public bool editor_domain_currency_known;
        public string editor_domain_currency = "";
        public string newest_editor_input_path = "";
        public string newest_editor_input_write_utc = "";
        public int editor_input_count;
        public string editor_input_content_state = "";
        public string editor_input_content_basis_utc = "";
        public int changed_editor_input_count;
        public string[] changed_editor_inputs = Array.Empty<string>();
        public string settled_forced_asset_refresh_requested_utc = "";
        public bool script_compilation_failed;
        public string currency_basis = "editor_domain_load_vs_newest_assets_editor_input";
        public bool safe_to_invoke;
        public string reason = "";
        public string recommended_next_action = "";
        public bool application_run_in_background;
        public bool native_autofocus_enabled;
        public string background_execution_mode = "";
        public string validation_evidence = "unity_mcp";
    }
}
