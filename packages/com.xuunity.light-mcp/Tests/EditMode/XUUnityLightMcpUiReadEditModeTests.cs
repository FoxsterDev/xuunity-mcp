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
    [Category("XUUnity.MCP.UiRead")]
    public sealed class XUUnityLightMcpUiReadEditModeTests
    {
        const string GENERATED_ROOT = "Assets/XUUnityLightMcpGenerated";
        const string PREFAB_DIR = GENERATED_ROOT + "/UiReadSelfTest";

        GameObject _canvasRoot;
        string _prefabPath = "";

        [TearDown]
        public void TearDown()
        {
            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
                _canvasRoot = null;
            }

            if (!string.IsNullOrEmpty(_prefabPath))
            {
                AssetDatabase.DeleteAsset(_prefabPath);
                AssetDatabase.DeleteAsset(PREFAB_DIR);
                _prefabPath = "";
            }
        }

        [Test]
        public void TreeSnapshot_ReportsCanvasHierarchyWithPathsAndBounds()
        {
            BuildCanvas();

            var payload = RunTree("{\"targetKind\":\"active_scene\",\"includeInactive\":true}");

            Assert.That(payload.success, Is.True);
            Assert.That(payload.schema_version, Is.EqualTo("xuunity.ui.read.v1"));
            Assert.That(payload.node_count, Is.GreaterThanOrEqualTo(3));

            var card = FindNode(payload, "Card");
            Assert.That(card, Is.Not.Null, "the Card node should be in the snapshot");
            Assert.That(card.path, Does.EndWith("Card"));
            Assert.That(card.parent_path, Does.EndWith("XUUnityMcp_UiReadCanvas"));
            Assert.That(card.depth, Is.EqualTo(1));
            Assert.That(card.has_bounds, Is.True);
            Assert.That(card.bounds.width, Is.GreaterThan(0f));
            Assert.That(card.canvas_path, Does.EndWith("XUUnityMcp_UiReadCanvas"));
        }

        [Test]
        public void TreeSnapshot_HidesInactiveNodesUnlessRequested()
        {
            BuildCanvas();

            var withoutInactive = RunTree("{\"targetKind\":\"active_scene\"}");
            var withInactive = RunTree("{\"targetKind\":\"active_scene\",\"includeInactive\":true}");

            Assert.That(FindNode(withoutInactive, "HiddenBadge"), Is.Null);
            Assert.That(FindNode(withInactive, "HiddenBadge"), Is.Not.Null);
        }

        [Test]
        public void TreeSnapshot_ReportsCanvasGroupAlphaAsInvisible()
        {
            BuildCanvas();

            var payload = RunTree("{\"targetKind\":\"active_scene\",\"includeInactive\":true}");
            var faded = FindNode(payload, "FadedPanel");

            Assert.That(faded, Is.Not.Null);
            Assert.That(faded.effective_alpha, Is.EqualTo(0f).Within(0.001f));
            Assert.That(faded.visible, Is.False);
            Assert.That(faded.blocks_raycasts, Is.False);
        }

        [Test]
        public void TreeSnapshot_TruncationIsExplicitAndDowngradesProofClass()
        {
            BuildCanvas();

            var payload = RunTree("{\"targetKind\":\"active_scene\",\"includeInactive\":true,\"maxNodes\":2}");

            Assert.That(payload.truncated, Is.True);
            Assert.That(payload.truncation_reason, Is.EqualTo("max_nodes_reached"));
            Assert.That(payload.proof_class, Is.EqualTo("semantic_ui_partial"));
        }

        [Test]
        public void TreeSnapshot_UnknownTargetFailsWithTypedError()
        {
            var payload = RunTree("{\"targetKind\":\"game_object_name\",\"targetValue\":\"XUUnityMcp_NoSuchObject\"}");

            Assert.That(payload.success, Is.False);
            Assert.That(payload.proof_class, Is.EqualTo("error"));
            Assert.That(payload.errors[0].code, Is.EqualTo("ui_target_not_found"));
        }

        [Test]
        public void Query_MatchesByNameAndReportsAmbiguity()
        {
            BuildCanvas();

            var unique = RunQuery(
                "unity.ui.query",
                new XUUnityLightMcpUiQueryOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"Card\"}}");
            var ambiguous = RunQuery(
                "unity.ui.query",
                new XUUnityLightMcpUiQueryOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"Row\"}}");

            Assert.That(unique.match_count, Is.EqualTo(1));
            Assert.That(unique.ambiguous, Is.False);
            Assert.That(ambiguous.match_count, Is.EqualTo(2));
            Assert.That(ambiguous.ambiguous, Is.True);
            Assert.That(ambiguous.warnings.Exists(item => item.code == "selector_ambiguous"), Is.True);
        }

        [Test]
        public void Query_RejectsAnEmptySelector()
        {
            BuildCanvas();

            var payload = RunQuery(
                "unity.ui.query",
                new XUUnityLightMcpUiQueryOperation(),
                "{\"selector\":{}}");

            Assert.That(payload.success, Is.False);
            Assert.That(payload.errors[0].code, Is.EqualTo("ui_selector_invalid"));
        }

        [Test]
        public void Exists_IsTrueForAMatchAndFalseForNone()
        {
            BuildCanvas();

            var present = RunQuery(
                "unity.ui.exists",
                new XUUnityLightMcpUiExistsOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"Card\"}}");
            var absent = RunQuery(
                "unity.ui.exists",
                new XUUnityLightMcpUiExistsOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"NoSuchNode\"}}");

            Assert.That(present.exists, Is.True);
            Assert.That(absent.exists, Is.False);
            Assert.That(absent.success, Is.True, "a zero-match existence check is a successful answer, not an error");
        }

        [Test]
        public void GetBounds_ReturnsScreenRectForASingleMatch()
        {
            BuildCanvas();

            var payload = RunQuery(
                "unity.ui.get_bounds",
                new XUUnityLightMcpUiGetBoundsOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"Card\"}}");

            Assert.That(payload.success, Is.True);
            Assert.That(payload.has_bounds, Is.True);
            Assert.That(payload.bounds.width, Is.GreaterThan(0f));
            Assert.That(payload.bounds.height, Is.GreaterThan(0f));
        }

        [Test]
        public void GetText_FailsAmbiguousSelectorUnlessAllowMany()
        {
            BuildCanvas();

            var payload = RunQuery(
                "unity.ui.get_text",
                new XUUnityLightMcpUiGetTextOperation(),
                "{\"includeInactive\":true,\"selector\":{\"name\":\"Row\"}}");

            Assert.That(payload.success, Is.False);
            Assert.That(payload.errors.Exists(item => item.code == "selector_ambiguous"), Is.True);
        }

        [Test]
        public void PrefabValidate_PassesAHealthyPrefab()
        {
            CreatePrefab();

            var payload = RunPrefabValidate($"{{\"prefabPath\":\"{_prefabPath}\"}}");

            Assert.That(payload.success, Is.True);
            Assert.That(payload.passed, Is.True, string.Join("; ", payload.defect_types));
            Assert.That(payload.status, Is.EqualTo("passed"));
            Assert.That(payload.prefab_guid, Is.Not.Empty);
            Assert.That(payload.inspected_object_count, Is.GreaterThanOrEqualTo(2));
            Assert.That(payload.inspected_component_count, Is.GreaterThanOrEqualTo(2));
        }

        [Test]
        public void PrefabValidate_BlocksOnAMissingAsset()
        {
            var payload = RunPrefabValidate("{\"prefabPath\":\"Assets/XUUnityMcp_NoSuchPrefab.prefab\"}");

            Assert.That(payload.status, Is.EqualTo("blocked"));
            Assert.That(payload.proof_class, Is.EqualTo("error"));
            Assert.That(payload.errors[0].code, Is.EqualTo("prefab_not_found"));
        }

        [Test]
        public void PrefabValidate_RejectsANonPrefabPath()
        {
            var payload = RunPrefabValidate("{\"prefabPath\":\"Assets/Something.asset\"}");

            Assert.That(payload.status, Is.EqualTo("blocked"));
            Assert.That(payload.errors[0].code, Is.EqualTo("prefab_path_invalid"));
        }

        [Test]
        public void PrefabValidate_ReportsUnassignedReferencesOnlyWhenAsked()
        {
            CreatePrefab();

            var quiet = RunPrefabValidate($"{{\"prefabPath\":\"{_prefabPath}\"}}");
            // scope=all, because this probe prefab carries only engine components and the default
            // project_scripts scope exists precisely to keep their default-empty fields out of the report.
            var verbose = RunPrefabValidate(
                $"{{\"prefabPath\":\"{_prefabPath}\",\"reportUnassignedReferences\":true,"
                + "\"unassignedReferenceScope\":\"all\"}");

            Assert.That(quiet.inspected_reference_count, Is.GreaterThan(0), "the reference scan must actually run");
            Assert.That(quiet.defect_types, Does.Not.Contain("serialized_reference_unassigned"));
            Assert.That(verbose.defect_types, Does.Contain("serialized_reference_unassigned"));
            Assert.That(verbose.passed, Is.True, "unassigned references are informational, never a failure");
            foreach (var defect in verbose.defects)
            {
                Assert.That(defect.severity, Is.Not.EqualTo("error"), defect.defect_type);
            }
        }

        [Test]
        public void PrefabValidate_ParsesTheDeclaredTypeOutOfASerializedPPtr()
        {
            Assert.That(XUUnityLightMcpPrefabInspector.DeclaredTypeName("PPtr<$Button>"), Is.EqualTo("Button"));
            Assert.That(XUUnityLightMcpPrefabInspector.DeclaredTypeName("PPtr<GameObject>"), Is.EqualTo("GameObject"));
            Assert.That(XUUnityLightMcpPrefabInspector.DeclaredTypeName("string"), Is.EqualTo("string"));
            Assert.That(XUUnityLightMcpPrefabInspector.DeclaredTypeName(""), Is.Empty);
        }

        [Test]
        public void PrefabSnapshot_ReportsPrefabHierarchy()
        {
            CreatePrefab();

            var response = new XUUnityLightMcpPrefabSnapshotOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-snapshot-selftest",
                operation = "unity.prefab.snapshot",
                args_json = $"{{\"prefabPath\":\"{_prefabPath}\"}}"
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiTreePayload>(response.payload_json);

            Assert.That(payload.success, Is.True);
            Assert.That(payload.target.kind, Is.EqualTo("prefab_asset"));
            Assert.That(payload.target.prefab_path, Is.EqualTo(_prefabPath));
            Assert.That(payload.node_count, Is.GreaterThanOrEqualTo(2));
            Assert.That(FindNode(payload, "Child"), Is.Not.Null);
        }

        [Test]
        public void PrefabSnapshot_AddsFullComponentTypeNamesOnlyForTheFullPayload()
        {
            CreatePrefab();

            var compact = RunPrefabSnapshot($"{{\"prefabPath\":\"{_prefabPath}\",\"writeSnapshot\":false}}");
            var full = RunPrefabSnapshot(
                $"{{\"prefabPath\":\"{_prefabPath}\",\"writeSnapshot\":false,\"includeFullPayload\":true}}");

            StringAssert.DoesNotContain("component_type_full_names", compact);
            var payload = JsonUtility.FromJson<XUUnityLightMcpPrefabSnapshotFullPayload>(full);
            Assert.That(payload.component_type_full_names.Count, Is.EqualTo(payload.nodes.Count));
            for (var index = 0; index < payload.nodes.Count; index++)
            {
                var node = payload.nodes[index];
                var row = payload.component_type_full_names[index];
                Assert.That(row.node_id, Is.EqualTo(node.node_id));
                Assert.That(row.full_names.Count, Is.EqualTo(node.components.Count), node.path);
                for (var component = 0; component < node.components.Count; component++)
                {
                    StringAssert.EndsWith(node.components[component], row.full_names[component]);
                }
            }

            var child = payload.component_type_full_names.Find(row => row.path.EndsWith("/Child"));
            Assert.That(child.full_names, Does.Contain("UnityEngine.RectTransform"));
            Assert.That(child.full_names, Does.Contain("UnityEngine.MeshFilter"));
        }

        static string RunPrefabSnapshot(string argsJson)
        {
            return new XUUnityLightMcpPrefabSnapshotOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-snapshot-full-types",
                operation = "unity.prefab.snapshot",
                args_json = argsJson
            }).payload_json;
        }

        [Test]
        public void UiOperations_AreRegisteredAndCapabilityGated()
        {
            foreach (var operation in new[]
                     {
                         "unity.ui.tree_snapshot",
                         "unity.ui.query",
                         "unity.ui.exists",
                         "unity.ui.get_text",
                         "unity.ui.get_bounds"
                     })
            {
                Assert.That(XUUnityLightMcpOperationRegistry.TryGet(operation, out _), Is.True, operation);
                Assert.That(
                    XUUnityLightMcpCapabilityRegistry.TryGetRequiredCapability(operation, out var capability),
                    Is.True,
                    operation);
                Assert.That(capability, Is.EqualTo(XUUnityLightMcpCapabilityRegistry.UiReadCapability), operation);
            }

            foreach (var operation in new[] { "unity.prefab.snapshot", "unity.prefab.validate" })
            {
                Assert.That(XUUnityLightMcpOperationRegistry.TryGet(operation, out _), Is.True, operation);
            }
        }

        void BuildCanvas()
        {
            _canvasRoot = new GameObject(
                "XUUnityMcp_UiReadCanvas",
                typeof(RectTransform),
                typeof(Canvas));
            var canvas = _canvasRoot.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var canvasRect = _canvasRoot.GetComponent<RectTransform>();
            canvasRect.sizeDelta = new Vector2(1080f, 1920f);

            var card = NewChild(_canvasRoot.transform, "Card", new Vector2(600f, 400f));
            NewChild(card.transform, "Row", new Vector2(500f, 80f));
            NewChild(card.transform, "Row", new Vector2(500f, 80f));

            var faded = NewChild(_canvasRoot.transform, "FadedPanel", new Vector2(300f, 300f));
            var group = faded.AddComponent<CanvasGroup>();
            group.alpha = 0f;
            group.blocksRaycasts = false;

            var hidden = NewChild(_canvasRoot.transform, "HiddenBadge", new Vector2(80f, 80f));
            hidden.SetActive(false);
        }

        static GameObject NewChild(Transform parent, string name, Vector2 size)
        {
            var child = new GameObject(name, typeof(RectTransform));
            child.transform.SetParent(parent, false);
            var rect = child.GetComponent<RectTransform>();
            rect.sizeDelta = size;
            return child;
        }

        void CreatePrefab()
        {
            Directory.CreateDirectory(PREFAB_DIR);
            AssetDatabase.Refresh();
            var root = new GameObject("XUUnityMcp_UiReadPrefab", typeof(RectTransform), typeof(CanvasGroup));
            var child = NewChild(root.transform, "Child", new Vector2(100f, 100f));
            child.AddComponent<MeshFilter>();
            _prefabPath = PREFAB_DIR + "/XUUnityMcp_UiReadPrefab.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, _prefabPath);
            Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
        }

        static XUUnityLightMcpUiTreePayload RunTree(string argsJson)
        {
            var response = new XUUnityLightMcpUiTreeSnapshotOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "ui-tree-selftest",
                operation = "unity.ui.tree_snapshot",
                args_json = argsJson
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpUiTreePayload>(response.payload_json);
        }

        static XUUnityLightMcpUiQueryPayload RunQuery(
            string operationName,
            IXUUnityLightMcpOperation operation,
            string argsJson)
        {
            var response = operation.Execute(new XUUnityLightMcpRequest
            {
                request_id = operationName + "-selftest",
                operation = operationName,
                args_json = argsJson
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpUiQueryPayload>(response.payload_json);
        }

        static XUUnityLightMcpPrefabValidatePayload RunPrefabValidate(string argsJson)
        {
            var response = new XUUnityLightMcpPrefabValidateOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-validate-selftest",
                operation = "unity.prefab.validate",
                args_json = argsJson
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpPrefabValidatePayload>(response.payload_json);
        }

        static XUUnityLightMcpUiNode FindNode(XUUnityLightMcpUiTreePayload payload, string name)
        {
            return payload.nodes.Find(node => node.name == name);
        }
    }
}
