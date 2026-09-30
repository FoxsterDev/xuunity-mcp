using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
    internal static class XUUnityLightMcpUiRead
    {
        public const string SchemaVersion = "xuunity.ui.read.v1";
        public const string InteractionSchemaVersion = "xuunity.ui-interaction.v1";
        public const string InteractionStepKind = "ui_click";
        public const string ExistsStepKind = "ui_exists";
        public const string GetTextStepKind = "ui_get_text";

        public const string ProofSemanticTree = "semantic_ui_tree";
        public const string ProofSemanticPartial = "semantic_ui_partial";
        public const string ProofUnavailable = "unavailable";
        public const string ProofError = "error";

        public const string BackendUgui = "ugui";
        public const string BackendUnknown = "unknown";

        public const string TargetActiveScene = "active_scene";
        public const string TargetAllLoadedScenes = "all_loaded_scenes";
        public const string TargetGameObjectPath = "game_object_path";
        public const string TargetGameObjectName = "game_object_name";
        public const string TargetPrefabAsset = "prefab_asset";

        public const string SceneScopeActiveScene = "active_scene";
        public const string SceneScopeAllLoadedScenes = "all_loaded_scenes";
        public const string SceneScopeNamedScene = "named_scene";

        public const string DontDestroyOnLoadIncluded = "included";
        public const string DontDestroyOnLoadNotRequested = "not_requested";
        public const string DontDestroyOnLoadOutOfScope = "out_of_scope_for_target_kind";
        public const string DontDestroyOnLoadEditModeUnavailable = "edit_mode_no_dont_destroy_on_load_scene";
        public const string DontDestroyOnLoadProbeFailed = "probe_failed";

        public const int DefaultMaxDepth = 12;
        public const int DefaultMaxNodes = 500;
        public const int DefaultMaxMatches = 20;

        public const string DefaultUnassignedReferenceScope = "project_scripts";
        public const string SnapshotArtifactSuffix = ".ui-snapshot.json";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiRect
    {
        public float x;
        public float y;
        public float width;
        public float height;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiDiagnostic
    {
        public string code = "";
        public string message = "";
        public string detail = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiTargetInfo
    {
        public string kind = XUUnityLightMcpUiRead.TargetActiveScene;
        public string requested_value = "";
        public string backend = XUUnityLightMcpUiRead.BackendUgui;
        public string backend_status = "unknown";
        public int resolved_root_count;
        public bool ambiguous;
        public string scene_name = "";
        public string scene_path = "";
        public string scene_scope = XUUnityLightMcpUiRead.SceneScopeActiveScene;
        public string requested_scene_name = "";
        public bool scene_selector_ambiguous;
        public List<string> searched_scenes = new();
        public List<string> scenes_not_reached = new();
        public List<string> loaded_scenes = new();
        public bool dont_destroy_on_load_included;
        public string dont_destroy_on_load_status = XUUnityLightMcpUiRead.DontDestroyOnLoadNotRequested;
        public string prefab_path = "";
        public int capture_width;
        public int capture_height;
        public int screen_width;
        public int screen_height;
        public int render_width;
        public int render_height;
        public bool render_target_available;
        public bool render_target_differs_from_screen;
        public string bounds_origin = "bottom_left";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiNode
    {
        public string node_id = "";
        public string path = "";
        public string parent_path = "";
        public int depth;
        public int sibling_index;
        public int child_count;
        public string name = "";
        public string type = "";
        public string scene_name = "";
        public List<string> components = new();
        public bool active_self;
        public bool active_in_hierarchy;
        public bool visible;
        public bool interactable = true;
        public bool interactable_known;
        public float effective_alpha = 1f;
        public bool blocks_raycasts = true;
        public bool raycast_target;
        public bool raycast_target_known;
        public bool pointer_targetable;
        public string pointer_target_status = "not_evaluated";
        public string canvas_path = "";
        public int canvas_sort_order;
        public int render_order;
        public bool has_bounds;
        public XUUnityLightMcpUiRect bounds = new();
        public string bounds_space = "screen_pixels";
        public bool has_text;
        public string text = "";
        public string text_source = "";
        public string font = "";
        public string font_resolved_status = "not_evaluated";
        public string material = "";
        public string material_resolved_status = "not_evaluated";
        public string sprite = "";
        public string clip_state = "not_evaluated";
        public string clipped_by = "";
        public bool component_details_complete;
        public string component_detail_backend = "";
        public bool children_truncated;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiTreeArgs
    {
        public string targetKind = XUUnityLightMcpUiRead.TargetActiveScene;
        public string targetValue = "";
        public string sceneName = "";
        public bool includeDontDestroyOnLoad = true;
        public int maxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int maxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public bool includeInactive;
        public bool includeBounds = true;
        public bool includeText = true;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiSelectorArgs
    {
        public string name = "";
        public string type = "";
        public string path = "";
        public string pathContains = "";
        public string textEquals = "";
        public string textContains = "";
        public bool caseInsensitiveText;
        public bool requireVisible;
        public bool requireInteractable;
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiQueryArgs
    {
        public string targetKind = XUUnityLightMcpUiRead.TargetActiveScene;
        public string targetValue = "";
        public string sceneName = "";
        public bool includeDontDestroyOnLoad = true;
        public int maxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int maxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public int maxMatches = XUUnityLightMcpUiRead.DefaultMaxMatches;
        public bool includeInactive;
        public bool allowMany;
        public XUUnityLightMcpUiSelectorArgs selector = new();
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiTreePayload : XUUnityLightMcpPlayModeLivenessEvidence
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "";
        public string project_root = "";
        public bool success;
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public int screen_width;
        public int screen_height;
        public int render_width;
        public int render_height;
        public bool render_target_available;
        public bool render_target_differs_from_screen;
        public XUUnityLightMcpUiTargetInfo target = new();
        public List<string> component_detail_backends = new();
        public List<XUUnityLightMcpUiNode> nodes = new();
        public List<string> root_paths = new();
        public int node_count;
        public int max_depth;
        public int max_nodes;
        public bool truncated;
        public string truncation_reason = "";
        public string snapshot_path = "";
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string validation_evidence = "unity_mcp";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiQueryPayload : XUUnityLightMcpPlayModeLivenessEvidence
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "";
        public string project_root = "";
        public bool success;
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public int screen_width;
        public int screen_height;
        public int render_width;
        public int render_height;
        public bool render_target_available;
        public bool render_target_differs_from_screen;
        public XUUnityLightMcpUiTargetInfo target = new();
        public List<string> component_detail_backends = new();
        public XUUnityLightMcpUiSelectorArgs selector = new();
        public List<XUUnityLightMcpUiNode> matches = new();
        public int match_count;
        public bool exists;
        public bool ambiguous;
        public bool out_of_scope;
        public bool truncated;
        public int scanned_node_count;
        public bool has_text;
        public string text = "";
        public List<string> texts = new();
        public bool has_bounds;
        public XUUnityLightMcpUiRect bounds = new();
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string validation_evidence = "unity_mcp";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabArgs
    {
        public string prefabPath = "";
        public int maxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int maxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public bool includeInactive = true;
        public bool includeBounds;
        public bool includeText = true;
        public bool reportUnassignedReferences;
        public string unassignedReferenceScope = XUUnityLightMcpUiRead.DefaultUnassignedReferenceScope;
        public bool writeSnapshot = true;
        public string snapshotOutputPath = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiClickArgs
    {
        public string targetKind = XUUnityLightMcpUiRead.TargetActiveScene;
        public string targetValue = "";
        public string sceneName = "";
        public bool includeDontDestroyOnLoad = true;
        public string action = "click";
        public bool approve;
        public int maxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int maxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public XUUnityLightMcpUiSelectorArgs selector = new();
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiClickSnapshotRef
    {
        public int node_count;
        public bool truncated;
        public string truncation_reason = "";
        public string signature = "";

        public static string Hash(string value)
        {
            unchecked
            {
                var hash = 2166136261u;
                foreach (var character in value ?? "")
                {
                    hash ^= character;
                    hash *= 16777619u;
                }

                return hash.ToString("x8");
            }
        }
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiClickPayload : XUUnityLightMcpPlayModeLivenessEvidence
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "unity.ui.click";
        public string project_root = "";
        public bool success;
        public string status = "refused";
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public string requested_action = "";
        public string refusal_code = "";
        public XUUnityLightMcpUiSelectorArgs selector = new();
        public XUUnityLightMcpUiTargetInfo search_target = new();
        public int search_node_count;
        public int search_max_depth;
        public int search_max_nodes;
        public bool search_truncated;
        public string search_truncation_reason = "";
        public int match_count;
        public XUUnityLightMcpUiNode target_node;
        public string target_component = "";
        public bool pointer_targetable;
        public string pointer_target_status = "not_evaluated";
        public string pointer_target_path = "";
        public string pointer_target_blocked_by = "";
        public bool transparent_hit_area;
        public string transparent_hit_area_evidence = "";
        public string transparent_hit_area_visible_path = "";
        public bool event_system_present;
        public string event_system_scope = "";
        public bool delivered;
        public string delivered_to_path = "";
        public string delivery_mechanism = "";
        public string pointer_raycast_evidence = "";
        public string pointer_raycast_target_path = "";
        public int pointer_raycast_hit_count;
        public string occluded_by_path = "";
        public bool effective;
        public bool no_observable_effect;
        public bool state_changed;
        public int screen_width;
        public int screen_height;
        public int render_width;
        public int render_height;
        public bool render_target_available;
        public bool render_target_differs_from_screen;
        public XUUnityLightMcpUiClickSnapshotRef before_snapshot = new();
        public XUUnityLightMcpUiClickSnapshotRef after_snapshot = new();
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string validation_evidence = "unity_mcp";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiInteractionBlock
    {
        public string schema_version = XUUnityLightMcpUiRead.InteractionSchemaVersion;
        public string interaction_id = "";
        public string action = "click";
        public XUUnityLightMcpUiSelectorArgs selector = new();
        public bool delivered;
        public string delivery_mechanism = "";
        public string target_path = "";
        public string target_component = "";
        public string handler_path = "";
        public string pointer_target_status = "not_evaluated";
        public string pointer_target_blocked_by = "";
        public bool transparent_hit_area;
        public string transparent_hit_area_evidence = "";
        public bool effective;
        public bool no_observable_effect;
        public bool state_changed;
        public string before_signature = "";
        public string after_signature = "";
        public XUUnityLightMcpUiTargetInfo search_target = new();
        public int search_node_count;
        public int search_max_depth;
        public int search_max_nodes;
        public bool search_truncated;
        public string search_truncation_reason = "";
        public string playmode_state = "";
        public string playmode_loop_liveness = "";
        public string playmode_liveness_warning = "";
        public string playmode_liveness_remediation = "";
        public bool editor_application_focused;
        public string result_trust_class = "";
        public string refusal_code = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiInteractionStepPayload
    {
        public XUUnityLightMcpUiInteractionBlock ui_interaction = new();
        public bool expect_state_change = true;
        public bool met_expectations;
        public string click_status = "";
        public string click_error = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpUiReadStepPayload
    {
        public string operation = "";
        public bool met_expectations;
        public bool expected_exists = true;
        public string expected_text = "";
        public XUUnityLightMcpUiQueryPayload query = new();
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabRenderArgs
    {
        public string prefabPath = "";
        public int width;
        public int height;
        public int safeAreaTop;
        public int safeAreaBottom;
        public int safeAreaLeft;
        public int safeAreaRight;
        public string outputPath = "";
        public string backgroundColor = "#00000000";
        public int referenceWidth;
        public int referenceHeight;
        public float scalerMatch = 0.5f;
        public int antiAliasing = 1;
        public bool includeSnapshot;
        public bool writeSnapshot = true;
        public string snapshotOutputPath = "";
        public int maxDepth = XUUnityLightMcpUiRead.DefaultMaxDepth;
        public int maxNodes = XUUnityLightMcpUiRead.DefaultMaxNodes;
        public bool includeInactive;
        public XUUnityLightMcpPrefabMutationOperation[] overrides =
            Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
        public string[] allowedComponentTypes = Array.Empty<string>();
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabRenderPayload
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "unity.prefab.render";
        public string project_root = "";
        public bool success;
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public string prefab_path = "";
        public string prefab_guid = "";
        public string screenshot_path = "";
        public int screenshot_width;
        public int screenshot_height;
        public long screenshot_size_bytes;
        public string render_mode = "isolated_preview_scene";
        public bool application_booted;
        public bool persisted_scene_changes;
        public XUUnityLightMcpUiRect safe_area = new();
        public int reference_width;
        public int reference_height;
        public double render_duration_seconds;
        public string snapshot_path = "";
        public XUUnityLightMcpUiTreePayload snapshot;
        public int requested_override_count;
        public List<XUUnityLightMcpPrefabMutationChange> applied_overrides = new();
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string validation_evidence = "unity_mcp";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabDefect
    {
        public string defect_type = "";
        public string severity = "error";
        public string object_path = "";
        public string component_type = "";
        public string property_path = "";
        public string expected_type = "";
        public string observed_type = "";
        public string message = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabMutationOperation
    {
        public string op = "";
        public string path = "";
        public string componentType = "";
        public string propertyPath = "";
        public string valueKind = "";
        public string stringValue = "";
        public double numberValue;
        public bool boolValue;
        public float x;
        public float y;
        public float z;
        public float w;
        public string templatePath = "";
        public string childName = "";
        public string assetSubAssetName = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabMutationArgs
    {
        public string prefabPath = "";
        public bool approve;
        public bool previewOnly = true;
        public string expectedSha256 = "";
        public XUUnityLightMcpPrefabMutationOperation[] operations = Array.Empty<XUUnityLightMcpPrefabMutationOperation>();
        public string[] allowedComponentTypes = Array.Empty<string>();
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabMutationChange
    {
        public int index;
        public string op = "";
        public string status = "planned";
        public string object_path = "";
        public string component_type = "";
        public string property_path = "";
        public string before = "";
        public string after = "";
        public string inverse_op = "";
        public string error_code = "";
        public string error_message = "";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabMutationPayload
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "unity.prefab.mutate";
        public string project_root = "";
        public bool success;
        public string status = "blocked";
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public string prefab_path = "";
        public string prefab_guid = "";
        public string sha256_before = "";
        public string sha256_after = "";
        public bool preview_only = true;
        public string drift_guard = "not_evaluated";
        public bool applied;
        public bool rolled_back;
        public string rollback_reason = "";
        public int requested_operation_count;
        public int planned_change_count;
        public int no_op_count;
        public List<XUUnityLightMcpPrefabMutationChange> changes = new();
        public XUUnityLightMcpPrefabValidatePayload post_validation;
        public string reversible_patch_json = "";
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string recommended_next_action = "";
        public string validation_evidence = "unity_mcp";
    }

    [Serializable]
    internal sealed class XUUnityLightMcpPrefabValidatePayload
    {
        public string schema_version = XUUnityLightMcpUiRead.SchemaVersion;
        public string backend_id = "xuunity.light_unity_mcp";
        public string operation = "unity.prefab.validate";
        public string project_root = "";
        public bool success;
        public string proof_class = XUUnityLightMcpUiRead.ProofError;
        public string generated_at_utc = "";
        public string prefab_path = "";
        public string prefab_guid = "";
        public string status = "failed";
        public bool passed;
        public int inspected_object_count;
        public int inspected_component_count;
        public int inspected_reference_count;
        public int unverified_reference_count;
        public string unassigned_reference_scope = "not_reported";
        public int unassigned_reference_count;
        public int unassigned_reference_suppressed_count;
        public List<XUUnityLightMcpPrefabDefect> defects = new();
        public List<string> defect_types = new();
        public List<string> lanes_not_evaluated = new();
        public List<XUUnityLightMcpUiDiagnostic> warnings = new();
        public List<XUUnityLightMcpUiDiagnostic> errors = new();
        public string recommended_next_action = "";
        public string validation_evidence = "unity_mcp";
    }
}
