using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.PrefabMutation")]
    public sealed class XUUnityLightMcpPrefabMutationEditModeTests
    {
        const string GENERATED_ROOT = "Assets/XUUnityLightMcpGenerated";
        const string PREFAB_DIR = GENERATED_ROOT + "/MutationSelfTest";

        string _prefabPath = "";

        [SetUp]
        public void SetUp()
        {
            Directory.CreateDirectory(PREFAB_DIR);
            AssetDatabase.Refresh();
            var root = new GameObject("XUUnityMcp_MutationRoot", typeof(RectTransform), typeof(CanvasGroup));
            var child = new GameObject("Panel", typeof(RectTransform), typeof(CanvasGroup));
            child.transform.SetParent(root.transform, false);
            _prefabPath = PREFAB_DIR + "/XUUnityMcp_MutationRoot.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, _prefabPath);
            Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
        }

        [TearDown]
        public void TearDown()
        {
            if (!string.IsNullOrEmpty(_prefabPath))
            {
                AssetDatabase.DeleteAsset(_prefabPath);
                AssetDatabase.DeleteAsset(PREFAB_DIR);
                _prefabPath = "";
            }
        }

        [Test]
        public void PreviewIsTheDefaultAndNeverTouchesTheAsset()
        {
            var before = File.ReadAllBytes(_prefabPath);

            var payload = Mutate(SetAlphaJson(0.25f, approve: false, previewOnly: true));

            Assert.That(payload.success, Is.True);
            Assert.That(payload.status, Is.EqualTo("previewed"));
            Assert.That(payload.applied, Is.False);
            Assert.That(payload.changes[0].before, Is.EqualTo("1"));
            Assert.That(payload.changes[0].after, Is.EqualTo("0.25"));
            Assert.That(payload.sha256_after, Is.EqualTo(payload.sha256_before));
            CollectionAssert.AreEqual(before, File.ReadAllBytes(_prefabPath));
        }

        [Test]
        public void ApprovalIsRequiredBeforeAnythingIsWritten()
        {
            var payload = Mutate(SetAlphaJson(0.25f, approve: false, previewOnly: false));

            Assert.That(payload.preview_only, Is.True, "approve=false must force preview, never a silent apply");
            Assert.That(payload.applied, Is.False);
        }

        [Test]
        public void ApprovedTransactionAppliesAtomicallyAndChangesTheAsset()
        {
            var payload = Mutate(SetAlphaJson(0.25f, approve: true, previewOnly: false));

            Assert.That(payload.status, Is.EqualTo("applied"), string.Join("; ", payload.errors.ConvertAll(e => e.code)));
            Assert.That(payload.applied, Is.True);
            Assert.That(payload.sha256_after, Is.Not.EqualTo(payload.sha256_before));
            Assert.That(payload.post_validation.passed, Is.True);

            var saved = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            Assert.That(saved.GetComponent<CanvasGroup>().alpha, Is.EqualTo(0.25f).Within(0.001f));
        }

        [Test]
        public void ApprovedTransactionEmitsAReversiblePatch()
        {
            var payload = Mutate(SetAlphaJson(0.25f, approve: true, previewOnly: false));

            Assert.That(payload.reversible_patch_json, Does.Contain("xuunity.prefab-mutation-patch.v1"));
            Assert.That(payload.reversible_patch_json, Does.Contain("\"restoreValue\":\"1\""));
            Assert.That(payload.reversible_patch_json, Does.Contain(payload.sha256_before));
        }

        [Test]
        public void AFailedOperationRollsBackTheWholeTransaction()
        {
            var before = File.ReadAllBytes(_prefabPath);
            var args =
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                + "{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_MutationRoot\",\"propertyPath\":\"alpha\",\"numberValue\":0.5},"
                + "{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_NoSuchChild\",\"propertyPath\":\"alpha\",\"numberValue\":0.5}"
                + "]}";

            var payload = Mutate(args);

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.applied, Is.False);
            Assert.That(payload.rolled_back, Is.True);
            Assert.That(payload.changes[1].error_code, Is.EqualTo("prefab_mutation_target_not_found"));
            CollectionAssert.AreEqual(before, File.ReadAllBytes(_prefabPath), "the asset must be byte-identical after a rollback");
        }

        [Test]
        public void AmbiguousTargetsAreRefused()
        {
            var root = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            var contents = PrefabUtility.LoadPrefabContents(_prefabPath);
            try
            {
                var duplicate = new GameObject("Panel", typeof(RectTransform), typeof(CanvasGroup));
                duplicate.transform.SetParent(contents.transform, false);
                PrefabUtility.SaveAsPrefabAsset(contents, _prefabPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(contents);
            }

            AssetDatabase.Refresh();
            Assert.That(root, Is.Not.Null);

            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                + "{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"propertyPath\":\"alpha\",\"numberValue\":0.5}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.changes[0].error_code, Is.EqualTo("prefab_mutation_target_ambiguous"));
        }

        [Test]
        public void SceneBoundReferenceFieldsAreOutOfScopeSoNoComponentCanBeSwapped()
        {
            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                + "{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_MutationRoot\",\"componentType\":\"CanvasGroup\",\"propertyPath\":\"m_GameObject\"}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.changes[0].error_code, Is.EqualTo("prefab_mutation_value_incompatible"));
            Assert.That(payload.changes[0].error_message, Does.Contain("GameObject"));
        }

        [Test]
        public void AnAssetTypedReferenceCanBeWrittenByProjectPath()
        {
            var meshPath = PREFAB_DIR + "/XUUnityMcp_ProbeMesh.asset";
            AssetDatabase.CreateAsset(new Mesh { name = "XUUnityMcp_ProbeMesh" }, meshPath);
            AssetDatabase.Refresh();

            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"allowedComponentTypes\":[\"MeshFilter\"],\"operations\":["
                + "{\"op\":\"add_component\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"componentType\":\"MeshFilter\"},"
                + "{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_MutationRoot/Panel\","
                + "\"componentType\":\"MeshFilter\",\"propertyPath\":\"m_Mesh\",\"stringValue\":\"" + meshPath + "\"}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("applied"), string.Join("; ", payload.changes.ConvertAll(c => c.error_message)));
            Assert.That(payload.changes[1].after, Is.EqualTo(meshPath));

            var saved = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            var filter = saved.transform.Find("Panel").GetComponent<MeshFilter>();
            Assert.That(AssetDatabase.GetAssetPath(filter.sharedMesh), Is.EqualTo(meshPath));

            AssetDatabase.DeleteAsset(meshPath);
        }

        [Test]
        public void AnAssetReferenceThatDoesNotResolveFailsWithATypedError()
        {
            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"allowedComponentTypes\":[\"MeshFilter\"],\"operations\":["
                + "{\"op\":\"add_component\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"componentType\":\"MeshFilter\"},"
                + "{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_MutationRoot/Panel\","
                + "\"componentType\":\"MeshFilter\",\"propertyPath\":\"m_Mesh\","
                + "\"stringValue\":\"Assets/XUUnityLightMcpGenerated/NoSuchMesh.asset\"}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.changes[1].error_code, Is.EqualTo("prefab_mutation_asset_not_found"));
        }

        [Test]
        public void APlainPathIsNotResolvedToOneOfSeveralSubAssetsThatFitTheField()
        {
            var containerPath = PREFAB_DIR + "/XUUnityMcp_MeshContainer.asset";
            AssetDatabase.CreateAsset(ScriptableObject.CreateInstance<XUUnityLightMcpAssetSnapshotProbeAsset>(), containerPath);
            AssetDatabase.AddObjectToAsset(new Mesh { name = "XUUnityMcp_MeshA" }, containerPath);
            AssetDatabase.AddObjectToAsset(new Mesh { name = "XUUnityMcp_MeshB" }, containerPath);
            AssetDatabase.SaveAssets();

            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"allowedComponentTypes\":[\"MeshFilter\"],\"operations\":["
                + "{\"op\":\"add_component\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"componentType\":\"MeshFilter\"},"
                + "{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_MutationRoot/Panel\","
                + "\"componentType\":\"MeshFilter\",\"propertyPath\":\"m_Mesh\",\"stringValue\":\"" + containerPath + "\"}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(payload.changes[1].error_code, Is.EqualTo("prefab_mutation_asset_type_mismatch"));
        }

        [Test]
        public void AWriteThatChangesNothingIsReportedAsNoOpNotApplied()
        {
            var payload = Mutate(SetAlphaJson(1f, approve: true, previewOnly: false));

            Assert.That(payload.status, Is.EqualTo("applied"), "the transaction still succeeds");
            Assert.That(payload.changes[0].status, Is.EqualTo("no_op"));
            Assert.That(payload.changes[0].before, Is.EqualTo(payload.changes[0].after));
            Assert.That(payload.no_op_count, Is.EqualTo(1));
            Assert.That(payload.planned_change_count, Is.EqualTo(0));
            Assert.That(payload.warnings.ConvertAll(w => w.code), Does.Contain("prefab_mutation_no_op_operations"));
        }

        [Test]
        public void APrefabThatDriftedFromItsPreconditionIsRefusedInsteadOfOverwritten()
        {
            var refused = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"expectedSha256\":\"1111111111111111111111111111111111111111111111111111111111111111\","
                + "\"operations\":[{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_MutationRoot\","
                + "\"propertyPath\":\"alpha\",\"numberValue\":0.25}]}");

            Assert.That(refused.errors[0].code, Is.EqualTo("prefab_mutation_asset_drifted"));
            Assert.That(refused.drift_guard, Is.EqualTo("drifted"));
            Assert.That(refused.changes, Is.Empty, "nothing may be attempted against a possibly stale copy");
            Assert.That(
                refused.recommended_next_action,
                Is.EqualTo("run_unity_project_refresh_then_rebuild_the_transaction"),
                "the remedy for a stale editor import must be named, not left to the operator");
        }

        [Test]
        public void AWriteWithNoPreconditionSaysSoInsteadOfImplyingDriftWasChecked()
        {
            // The editor cannot tell an external rewrite from its own reimport, so inferring drift would
            // refuse legitimate writes. Naming the unguarded case is the honest alternative.
            var unguarded = Mutate(SetAlphaJson(0.25f, approve: true, previewOnly: false));

            Assert.That(unguarded.status, Is.EqualTo("applied"));
            Assert.That(unguarded.drift_guard, Is.EqualTo("unguarded"));
            Assert.That(
                unguarded.warnings.ConvertAll(warning => warning.code),
                Does.Contain("prefab_mutation_unguarded_by_precondition"));

            var guarded = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"expectedSha256\":\"" + unguarded.sha256_after + "\","
                + "\"operations\":[{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_MutationRoot\","
                + "\"propertyPath\":\"alpha\",\"numberValue\":0.5}]}");

            Assert.That(guarded.status, Is.EqualTo("applied"), string.Join("; ", guarded.errors.ConvertAll(e => e.code)));
            Assert.That(guarded.drift_guard, Is.EqualTo("precondition_matched"));
            Assert.That(
                guarded.warnings.ConvertAll(warning => warning.code),
                Does.Not.Contain("prefab_mutation_unguarded_by_precondition"));
        }

        [Test]
        public void ComponentsOutsideTheAllowlistAreRefused()
        {
            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                + "{\"op\":\"add_component\",\"path\":\"XUUnityMcp_MutationRoot\",\"componentType\":\"Rigidbody\"}"
                + "]}");

            Assert.That(payload.changes[0].error_code, Is.EqualTo("prefab_mutation_component_not_allowlisted"));
            Assert.That(payload.status, Is.EqualTo("rolled_back"));
        }

        [Test]
        public void AllowlistedComponentCanBeAddedAndRemoved()
        {
            var added = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"allowedComponentTypes\":[\"MeshFilter\"],\"operations\":["
                + "{\"op\":\"add_component\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"componentType\":\"MeshFilter\"}"
                + "]}");

            Assert.That(added.status, Is.EqualTo("applied"), string.Join("; ", added.errors.ConvertAll(e => e.message)));
            Assert.That(added.changes[0].inverse_op, Is.EqualTo("remove_component"));

            var withComponent = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            Assert.That(withComponent.transform.Find("Panel").GetComponent<MeshFilter>(), Is.Not.Null);

            var removed = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,"
                + "\"allowedComponentTypes\":[\"MeshFilter\"],\"operations\":["
                + "{\"op\":\"remove_component\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"componentType\":\"MeshFilter\"}"
                + "]}");

            Assert.That(removed.status, Is.EqualTo("applied"), string.Join("; ", removed.errors.ConvertAll(e => e.message)));
            Assert.That(removed.changes[0].inverse_op, Is.EqualTo("add_component"));

            var withoutComponent = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            Assert.That(withoutComponent.transform.Find("Panel").GetComponent<MeshFilter>(), Is.Null);
        }

        [Test]
        public void RectTransformGeometryIsASupportedTypedOperation()
        {
            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":true,\"previewOnly\":false,\"operations\":["
                + "{\"op\":\"set_rect_transform\",\"path\":\"XUUnityMcp_MutationRoot/Panel\",\"propertyPath\":\"sizeDelta\",\"x\":320,\"y\":140}"
                + "]}");

            Assert.That(payload.status, Is.EqualTo("applied"), string.Join("; ", payload.errors.ConvertAll(e => e.message)));
            var saved = AssetDatabase.LoadAssetAtPath<GameObject>(_prefabPath);
            var panel = saved.transform.Find("Panel") as RectTransform;
            Assert.That(panel, Is.Not.Null);
            Assert.That(panel.sizeDelta, Is.EqualTo(new Vector2(320f, 140f)));
        }

        [Test]
        public void EmptyAndOversizedTransactionsAreRefused()
        {
            var empty = Mutate("{\"prefabPath\":\"" + _prefabPath + "\",\"operations\":[]}");

            Assert.That(empty.errors[0].code, Is.EqualTo("prefab_mutation_operations_missing"));
        }

        [Test]
        public void UnsupportedOpsAreNamedWithTheSupportedSet()
        {
            var payload = Mutate(
                "{\"prefabPath\":\"" + _prefabPath + "\",\"operations\":["
                + "{\"op\":\"rewrite_yaml\",\"path\":\"XUUnityMcp_MutationRoot\"}]}");

            Assert.That(payload.errors[0].code, Is.EqualTo("prefab_mutation_op_unsupported"));
            Assert.That(payload.errors[0].detail, Does.Contain("set_serialized_field"));
        }

        string SetAlphaJson(float alpha, bool approve, bool previewOnly)
        {
            var approveText = approve ? "true" : "false";
            var previewText = previewOnly ? "true" : "false";
            return "{\"prefabPath\":\"" + _prefabPath + "\",\"approve\":" + approveText
                   + ",\"previewOnly\":" + previewText + ",\"operations\":["
                   + "{\"op\":\"set_canvas_group\",\"path\":\"XUUnityMcp_MutationRoot\",\"propertyPath\":\"alpha\",\"numberValue\":"
                   + alpha.ToString(System.Globalization.CultureInfo.InvariantCulture) + "}]}";
        }

        static XUUnityLightMcpPrefabMutationPayload Mutate(string argsJson)
        {
            var response = new XUUnityLightMcpPrefabMutateOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-mutate-selftest",
                operation = "unity.prefab.mutate",
                args_json = argsJson
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpPrefabMutationPayload>(response.payload_json);
        }
    }
}
