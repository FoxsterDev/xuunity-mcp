"""Read-only UI primitives contract (xuunity.ui.read.v1).

The uGUI/prefab read surface spans two languages: the Python host declares the
tools, the C# editor package implements them. Nothing at runtime cross-checks
the two, so these tests hold the seam:

- every host tool with a `unity.ui.*` / `unity.prefab.*` bridgeOperation is
  registered in the C# operation registry and capability map;
- the core editor assembly stays dependency-free, so a project without
  com.unity.ugui still compiles the package (the uGUI and TextMeshPro readers
  live in constraint-gated satellite assemblies);
- the envelope constants the host documents are the ones the C# models emit.
"""

import json
import re
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_specs

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "packages" / "com.xuunity.light-mcp"
EDITOR_ROOT = PACKAGE_ROOT / "Editor"
CORE_ASMDEF = EDITOR_ROOT / "com.xuunity.light-mcp.Editor.asmdef"
UGUI_ASMDEF = EDITOR_ROOT / "Ugui" / "com.xuunity.light-mcp.Editor.Ugui.asmdef"
TMP_ASMDEF = EDITOR_ROOT / "Tmp" / "com.xuunity.light-mcp.Editor.Tmp.asmdef"

UI_READ_OPERATIONS = (
    "unity.ui.tree_snapshot",
    "unity.ui.query",
    "unity.ui.exists",
    "unity.ui.get_text",
    "unity.ui.get_bounds",
)
PREFAB_OPERATIONS = (
    "unity.prefab.snapshot",
    "unity.prefab.validate",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def core_registered_operations() -> set[str]:
    text = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpOperationRegistry.cs")
    return set(re.findall(r'\{\s*"([a-z0-9_.]+)"\s*,\s*new ', text))


def satellite_registered_operations() -> dict[str, str]:
    """Operations an optional module registers at load time, mapped to the class that owns them."""

    owners: dict[str, str] = {}
    for source in sorted(EDITOR_ROOT.rglob("*.cs")):
        text = read(source)
        for class_name in re.findall(r"XUUnityLightMcpOperationRegistry\.Register\(new (\w+)\(\)\)", text):
            owner = EDITOR_ROOT.rglob(f"{class_name}.cs")
            for path in owner:
                match = re.search(
                    r'RegisteredOperationName\s*=\s*"([a-z0-9_.]+)"',
                    read(path),
                )
                if match:
                    # as_posix, not str: the assembly checks below compare against "Ugui/", and a
                    # native separator makes them fail on Windows for a correctly gated operation.
                    owners[match.group(1)] = path.relative_to(EDITOR_ROOT).as_posix()
    return owners


def registered_operations() -> set[str]:
    return core_registered_operations() | set(satellite_registered_operations())


def capability_map() -> dict[str, str]:
    text = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpCapabilityRegistry.cs")
    body = text.split("OperationCapabilities", 1)[1]
    return dict(re.findall(r'\{\s*"([a-z0-9_.]+)"\s*,\s*(\w+)\s*\}', body))


class UiReadSurfaceContractTest(unittest.TestCase):
    def test_host_tools_declare_the_new_bridge_operations(self) -> None:
        declared = {
            spec.get("bridgeOperation")
            for spec in server_specs.TOOLS.values()
            if spec.get("bridgeOperation")
        }
        for operation in UI_READ_OPERATIONS + PREFAB_OPERATIONS:
            self.assertIn(operation, declared, f"no host tool declares {operation}")

    def test_every_declared_bridge_operation_exists_in_the_editor_registry(self) -> None:
        registered = registered_operations()
        missing = []
        for name, spec in server_specs.TOOLS.items():
            operation = spec.get("bridgeOperation")
            if not operation or not operation.startswith(("unity.ui.", "unity.prefab.")):
                continue
            if operation not in registered:
                missing.append(f"{name} -> {operation}")
        self.assertEqual([], missing, "host tools point at unregistered editor operations")

    def test_ugui_only_operations_are_registered_from_the_gated_assembly(self) -> None:
        owners = satellite_registered_operations()
        for operation in ("unity.prefab.render", "unity.ui.click"):
            owner = owners.get(operation, "")
            self.assertTrue(
                owner.startswith("Ugui/"),
                f"{operation} must be owned by the constraint-gated uGUI assembly, not the core one (owner={owner})",
            )

        mapped = capability_map()
        self.assertEqual("UiRenderCapability", mapped.get("unity.prefab.render"))
        self.assertEqual("UiInteractionCapability", mapped.get("unity.ui.click"))

    def test_optional_capabilities_fail_closed_without_ugui(self) -> None:
        text = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpHealthProbe.cs")
        self.assertIn("BuildOptionalUguiCapability(", text)
        self.assertIn("disabled_missing_dependency", text)
        self.assertIn("XUUnityLightMcpCapabilityRegistry.BuildRegisteredCapabilityOrNull(capabilityId)", text)

    def test_mutation_never_reaches_for_raw_yaml(self) -> None:
        mutator = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabMutator.cs")
        operation = read(EDITOR_ROOT / "Operations" / "XUUnityLightMcpPrefabMutateOperation.cs")

        self.assertNotIn("File.WriteAllText", mutator)
        self.assertNotIn("File.WriteAllText", operation)
        self.assertIn("PrefabUtility.LoadPrefabContents(", operation)
        self.assertIn("PrefabUtility.UnloadPrefabContents(", operation)

    def test_asset_references_are_writable_but_scene_bound_ones_are_not(self) -> None:
        """The guardrail is 'no component swap', not 'no object reference'.

        Refusing asset references is what forced operators onto raw prefab YAML, and the drift that
        came with it; refusing component/GameObject references is what stops a component being
        swapped for another type.
        """

        mutator = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabMutator.cs")
        self.assertIn("SerializedPropertyType.ObjectReference", mutator)
        self.assertIn("TryAssignObjectReference(", mutator)
        self.assertIn("IsSceneBoundReferenceType(", mutator)
        self.assertIn("asset is Component || asset is GameObject", mutator)
        self.assertIn("prefab_mutation_asset_type_mismatch", mutator)
        self.assertIn("prefab_mutation_asset_not_found", mutator)
        self.assertIn(
            "can never be swapped for another type",
            mutator,
            "the component-swap refusal must stay stated where the policy is enforced",
        )

    def test_a_write_that_changed_nothing_is_not_reported_as_applied(self) -> None:
        """A mutation receipt that says applied for an unchanged value defeats every other guardrail
        on this surface: expectedSha256, atomic rollback, post_validation and the inverse patch all
        presume the change report is truthful."""

        mutator = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabMutator.cs")
        operation = read(EDITOR_ROOT / "Operations" / "XUUnityLightMcpPrefabMutateOperation.cs")
        models = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")

        self.assertIn("ResolveWriteStatus(change)", mutator)
        self.assertIn('"no_op" : "applied"', mutator)
        self.assertIn('CountStatus(payload.changes, "no_op")', operation)
        self.assertIn("public int no_op_count;", models)

    def test_enum_properties_are_addressed_by_index_or_member_name(self) -> None:
        mutator = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabMutator.cs")
        self.assertIn("prefab_mutation_enum_value_invalid", mutator)
        self.assertIn("property.enumNames", mutator)
        self.assertIn("is the member index, not the enum's ", mutator)

    def test_mutation_refuses_a_prefab_that_drifted_and_names_an_unguarded_write(self) -> None:
        """Drift is only decidable from the caller's own expectedSha256.

        From inside the editor a file rewritten by an external tool and a file Unity itself reimported
        look identical, so an inferred drift check refuses legitimate writes. The surface therefore
        refuses a mismatched precondition and, when none was supplied, says so instead of implying the
        check ran.
        """

        operation = read(EDITOR_ROOT / "Operations" / "XUUnityLightMcpPrefabMutateOperation.cs")
        models = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")

        self.assertIn("prefab_mutation_asset_drifted", operation)
        self.assertIn("run_unity_project_refresh_then_rebuild_the_transaction", operation)
        self.assertIn("prefab_mutation_unguarded_by_precondition", operation)
        self.assertIn("public string drift_guard", models)

    def test_click_refuses_before_it_delivers(self) -> None:
        text = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpUiClickOperation.cs")
        for refusal in (
            "ui_click_approval_required",
            "ui_action_not_permitted",
            "selector_ambiguous",
            "ui_target_not_visible",
            "ui_target_not_interactable",
            "ui_target_does_not_block_raycasts",
            "ui_target_not_pointer_targetable",
            "ui_target_has_no_click_handler",
        ):
            self.assertIn(refusal, text, refusal)
        self.assertIn("ExecuteEvents.Execute(", text)
        self.assertNotIn("Input.simulateMouseWithTouches", text)

    def test_click_gates_on_pointer_targetability_instead_of_render_alpha(self) -> None:
        """Unity raycasts an alpha-0 Graphic, so render visibility must not refuse a transparent hit area."""

        operation = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpUiClickOperation.cs")
        targeting = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpUguiPointerTargeting.cs")
        models = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")

        self.assertIn("FindHandlerPointerTarget(", operation)
        self.assertIn("payload.pointer_targetable = true;", operation)
        self.assertIn("ui_click_transparent_hit_area_without_visible_content", operation)
        for filter_input in ("raycastTarget", "canvasRenderer.cull", "raycastPadding", "alphaHitTestMinimumThreshold"):
            self.assertIn(filter_input, targeting, filter_input)
        for field in (
            "pointer_targetable",
            "pointer_target_status",
            "pointer_target_path",
            "pointer_target_blocked_by",
            "transparent_hit_area",
            "transparent_hit_area_evidence",
            "transparent_hit_area_visible_path",
        ):
            self.assertRegex(models, rf"public\s+\w[\w<>\[\]]*\s+{field}\b")

    def test_click_is_inconclusive_when_the_search_budget_was_exhausted(self) -> None:
        operation = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpUiClickOperation.cs")
        models = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")

        self.assertIn('"ui_selector_search_truncated"', operation)
        self.assertIn("if (before.Truncated)", operation)
        self.assertIn("uniqueness is unproven", operation)
        self.assertIn("Narrow targetKind/targetValue or sceneName, or raise maxDepth/maxNodes", operation)
        for field in (
            "search_target",
            "search_node_count",
            "search_max_depth",
            "search_max_nodes",
            "search_truncated",
            "search_truncation_reason",
        ):
            self.assertRegex(models, rf"public\s+\w[\w<>\[\]]*\s+{field}\b")

    def test_render_is_isolated_and_non_persistent(self) -> None:
        text = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpPrefabRenderOperation.cs")
        self.assertIn("EditorSceneManager.NewPreviewScene()", text)
        self.assertIn("EditorSceneManager.ClosePreviewScene(previewScene)", text)
        self.assertIn("HideFlags.HideAndDontSave", text)
        self.assertNotIn("EditorSceneManager.SaveScene", text)
        self.assertNotIn("EditorSceneManager.OpenScene", text)

    def test_transient_render_overrides_never_reach_the_asset(self) -> None:
        """Rendering a runtime-driven second UI state must not cost a mutate/restore pair on an asset
        that other projects share."""

        text = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpPrefabRenderOperation.cs")
        self.assertIn("TryApplyOverrides(", text)
        self.assertIn("XUUnityLightMcpPrefabMutator.Apply(instance,", text)
        self.assertIn("prefab_render_override_failed", text)
        self.assertNotIn("PrefabUtility.SaveAsPrefabAsset", text)
        self.assertNotIn("PrefabUtility.ApplyPrefabInstance", text)

    def test_snapshots_are_persisted_as_artifacts_not_inline_only(self) -> None:
        """unity_ui_reference_compare consumes a snapshot by path, so an inline-only snapshot leaves
        acceptance.semantic=required permanently not_evaluated on the isolated-render lane."""

        render = read(EDITOR_ROOT / "Ugui" / "XUUnityLightMcpPrefabRenderOperation.cs")
        prefab_ops = read(EDITOR_ROOT / "Operations" / "XUUnityLightMcpPrefabOperations.cs")
        models = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")

        for text in (render, prefab_ops):
            self.assertIn("XUUnityLightMcpUiSnapshotArtifact.Write(", text)
        self.assertIn("public string snapshot_path", models)
        self.assertIn('SnapshotArtifactSuffix = ".ui-snapshot.json"', models)

        render_spec = server_specs.TOOLS["unity_prefab_render"]["inputSchema"]["properties"]
        self.assertTrue(render_spec["writeSnapshot"]["default"])
        self.assertFalse(
            render_spec["includeSnapshot"]["default"],
            "the inline copy is large and unusable by the consumer tool; the path is the product",
        )

    def test_unassigned_reference_report_is_scoped_by_default(self) -> None:
        inspector = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabInspector.cs")
        self.assertIn("NormalizeUnassignedScope(", inspector)
        self.assertIn("IsProjectScript(", inspector)
        self.assertIn("unassigned_reference_suppressed_count", inspector)

        scope = server_specs.TOOLS["unity_prefab_validate"]["inputSchema"]["properties"][
            "unassignedReferenceScope"
        ]
        self.assertEqual(["project_scripts", "required", "all"], scope["enum"])
        self.assertEqual("project_scripts", scope["default"])

    def test_new_operations_are_capability_mapped(self) -> None:
        mapped = capability_map()
        for operation in UI_READ_OPERATIONS:
            self.assertEqual("UiReadCapability", mapped.get(operation), operation)
        for operation in PREFAB_OPERATIONS:
            self.assertEqual("CoreCapability", mapped.get(operation), operation)

    def test_health_probe_publishes_the_ui_read_capability(self) -> None:
        text = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpHealthProbe.cs")
        self.assertIn("BuildUiReadCapability()", text)
        self.assertIn("UiReadBackendStateMatches(report)", text)
        for operation in UI_READ_OPERATIONS:
            self.assertIn(f'"{operation}"', text)

    def test_core_editor_assembly_stays_dependency_free(self) -> None:
        core = json.loads(read(CORE_ASMDEF))
        self.assertEqual(
            [],
            core["references"],
            "the core assembly must not depend on com.unity.ugui; optional readers live in satellite assemblies",
        )
        self.assertEqual([], core["defineConstraints"])

    def test_optional_assemblies_are_constraint_gated(self) -> None:
        for path, reference, define in (
            (UGUI_ASMDEF, "UnityEngine.UI", "XUUNITY_LIGHT_MCP_UGUI_CAPABILITY"),
            (TMP_ASMDEF, "Unity.TextMeshPro", "XUUNITY_LIGHT_MCP_TMP_CAPABILITY"),
        ):
            asmdef = json.loads(read(path))
            self.assertIn("com.xuunity.light-mcp.Editor", asmdef["references"], path.name)
            self.assertIn(reference, asmdef["references"], path.name)
            self.assertEqual([define], asmdef["defineConstraints"], path.name)
            defines = {entry["define"] for entry in asmdef["versionDefines"]}
            self.assertEqual(
                {define},
                defines,
                f"{path.name} must gate on the same define it constrains, or a project without the package breaks",
            )

    def test_core_sources_never_reference_the_optional_backends(self) -> None:
        offenders = []
        for source in sorted(EDITOR_ROOT.rglob("*.cs")):
            relative = source.relative_to(EDITOR_ROOT)
            if relative.parts[0] in {"Ugui", "Tmp"}:
                continue
            text = read(source)
            if "using UnityEngine.UI;" in text or "using TMPro;" in text:
                offenders.append(str(relative))
        self.assertEqual([], offenders, "only the constraint-gated satellite assemblies may use uGUI/TMP types")

    def test_optional_readers_register_through_the_documented_seam(self) -> None:
        for path in (
            EDITOR_ROOT / "Ugui" / "XUUnityLightMcpUguiModule.cs",
            EDITOR_ROOT / "Tmp" / "XUUnityLightMcpTmpComponentReader.cs",
        ):
            text = read(path)
            self.assertIn("[InitializeOnLoad]", text, path.name)
            self.assertIn("XUUnityLightMcpUiComponentReaderRegistry.Register(", text, path.name)

    def test_envelope_constants_match_the_published_schema(self) -> None:
        text = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")
        self.assertIn('SchemaVersion = "xuunity.ui.read.v1"', text)
        for proof_class in (
            "semantic_ui_tree",
            "semantic_ui_partial",
            "unavailable",
            "error",
        ):
            self.assertIn(f'"{proof_class}"', text)

    def test_node_model_is_flat_so_json_utility_can_serialize_it(self) -> None:
        text = read(EDITOR_ROOT / "Core" / "XUUnityLightMcpUiReadModels.cs")
        node_block = text.split("class XUUnityLightMcpUiNode", 1)[1].split("\n    }", 1)[0]
        self.assertNotIn(
            "XUUnityLightMcpUiNode>",
            node_block,
            "JsonUtility cannot serialize a self-referencing node; children are expressed via parent_path",
        )
        for field in ("path", "parent_path", "depth", "child_count"):
            self.assertIn(field, node_block)

    def test_prefab_validator_reports_the_documented_defect_types(self) -> None:
        text = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabInspector.cs")
        for defect in (
            "missing_script_guid",
            "serialized_reference_missing_component",
            "serialized_reference_type_mismatch",
            "serialized_reference_unassigned",
            "missing_prefab_instance",
        ):
            self.assertIn(f'defect_type = "{defect}"', text)

    def test_prefab_validator_gates_the_obsolete_object_reference_instance_id_api(self) -> None:
        inspector = read(EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabInspector.cs")
        self.assertEqual(
            1,
            inspector.count("objectReferenceInstanceIDValue"),
            "the obsolete API may exist only once, inside the pre-6000.5 compatibility branch",
        )
        self.assertRegex(
            inspector,
            re.compile(
                r"static bool HasSerializedObjectReference\(SerializedProperty property\)\s*"
                r"\{\s*"
                r"#if UNITY_6000_5_OR_NEWER\s*"
                r"return !property\.objectReferenceEntityIdValue\.Equals\(default\(UnityEngine\.EntityId\)\);\s*"
                r"#else\s*"
                r"return property\.objectReferenceInstanceIDValue != 0;\s*"
                r"#endif\s*"
                r"\}",
                re.MULTILINE,
            ),
            "Unity 6000.5+ must compile only the EntityId API; older editors must retain instance-ID semantics",
        )

        offenders = []
        for source in sorted(PACKAGE_ROOT.rglob("*.cs")):
            if source == EDITOR_ROOT / "Helpers" / "XUUnityLightMcpPrefabInspector.cs":
                continue
            if "objectReferenceInstanceIDValue" in read(source):
                offenders.append(source.relative_to(PACKAGE_ROOT).as_posix())
        self.assertEqual([], offenders, "no unconditional legacy object-reference API use may return")

    def test_new_package_sources_have_committed_meta_files(self) -> None:
        missing = []
        for source in sorted(PACKAGE_ROOT.rglob("*")):
            if source.is_dir():
                if source.name in {"Ugui", "Tmp"} and not source.with_name(source.name + ".meta").is_file():
                    missing.append(str(source.relative_to(PACKAGE_ROOT)))
                continue
            if source.suffix not in {".cs", ".asmdef"}:
                continue
            if not source.with_name(source.name + ".meta").is_file():
                missing.append(str(source.relative_to(PACKAGE_ROOT)))
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
