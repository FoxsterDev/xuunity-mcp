using System.Collections.Generic;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.PrefabMutation")]
    public sealed class XUUnityLightMcpPrefabCreateAndReferenceTests
    {
        const string FIXTURE_DIR = "Assets/XUUnityLightMcpGenerated/PrefabCreateSelfTest";
        const string PREFAB_PATH = FIXTURE_DIR + "/Nested/XUUnityMcp_Tile.prefab";
        const string ROOT = "XUUnityMcp_Tile";
        const string MATERIAL_PATH = FIXTURE_DIR + "/XUUnityMcp_Probe.mat";

        [SetUp]
        public void SetUp()
        {
            System.IO.Directory.CreateDirectory(FIXTURE_DIR);
            AssetDatabase.Refresh();
            AssetDatabase.CreateAsset(new Material(Shader.Find("Sprites/Default")), MATERIAL_PATH);
        }

        [TearDown]
        public void TearDown()
        {
            AssetDatabase.DeleteAsset(FIXTURE_DIR);
            AssetDatabase.Refresh();
        }

        [Test]
        public void ATypedNodeSpecCreatesAWiredPrefabWithoutAProjectBuilder()
        {
            var payload = Create(true, SkeletonOps() + "," + WiringOps());

            Assert.That(payload.status, Is.EqualTo("applied"), Errors(payload));
            Assert.That(payload.prefab_created, Is.True);
            Assert.That(payload.open_scene_dirtied, Is.False, "building the prefab must not dirty an open scene");

            var saved = AssetDatabase.LoadAssetAtPath<GameObject>(PREFAB_PATH);
            Assert.That(saved, Is.Not.Null);
            var button = saved.transform.Find("Button").GetComponent<Button>();
            var icon = saved.transform.Find("Button/Icon").GetComponent<Image>();
            Assert.That(button.targetGraphic, Is.SameAs(saved.transform.Find("Button").GetComponent<Image>()));
            Assert.That(saved.GetComponent<ScrollRect>().content, Is.SameAs(button.transform));
            Assert.That(saved.GetComponent<EventSystem>().firstSelectedGameObject, Is.SameAs(icon.gameObject));
            Assert.That(button.navigation.selectOnUp, Is.SameAs(button), "nested struct field");
            var materials = saved.transform.Find("Background").GetComponent<MeshRenderer>().sharedMaterials;
            Assert.That(materials[materials.Length - 1], Is.SameAs(AssetDatabase.LoadAssetAtPath<Material>(MATERIAL_PATH)));
            Assert.That(saved.transform.GetChild(0).name, Is.EqualTo("Background"), "afterSibling/siblingIndex placement");
            var background = (RectTransform)saved.transform.Find("Background");
            Assert.That(background.anchorMax, Is.EqualTo(Vector2.one));
        }

        [Test]
        public void PreviewNeverWritesAnAsset()
        {
            var payload = Create(false, SkeletonOps());

            Assert.That(payload.status, Is.EqualTo("previewed"), Errors(payload));
            Assert.That(AssetDatabase.LoadAssetAtPath<GameObject>(PREFAB_PATH), Is.Null);
        }

        [Test]
        public void AnExistingPrefabIsRefusedWithoutOverwrite()
        {
            Assert.That(Create(true, SkeletonOps()).status, Is.EqualTo("applied"));

            var second = Create(true, SkeletonOps());

            Assert.That(second.errors[0].code, Is.EqualTo("prefab_create_target_exists"));
        }

        [Test]
        public void AReferenceOfTheWrongTypeRollsBackTheWholeCreate()
        {
            var payload = Create(true, SkeletonOps() + ","
                + Field(ROOT, "ScrollRect", "m_HorizontalScrollbar", ROOT + "/Background"));

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(LastChange(payload).error_code, Is.EqualTo("prefab_mutation_reference_type_mismatch"));
            Assert.That(AssetDatabase.LoadAssetAtPath<GameObject>(PREFAB_PATH), Is.Null);
        }

        [Test]
        public void IdentityFieldsStayRefusedSoAComponentCannotBeSwapped()
        {
            var payload = Create(true, SkeletonOps() + ","
                + Field(ROOT + "/Button", "Button", "m_Script", ROOT + "/Button"));

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(LastChange(payload).error_code, Is.EqualTo("prefab_mutation_value_incompatible"));
        }

        [Test]
        public void AnArrayElementPastTheEndIsRefusedInsteadOfPadded()
        {
            var payload = Create(true, SkeletonOps() + ","
                + Field(ROOT + "/Background", "MeshRenderer", "m_Materials.Array.data[5]", MATERIAL_PATH));

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(LastChange(payload).error_code, Is.EqualTo("prefab_mutation_array_index_out_of_range"));
        }

        [Test]
        public void AComponentUnityRefusesToAttachFailsInsteadOfReportingApplied()
        {
            var payload = Create(true, Op("add_component", ROOT, "\"componentType\":\"XUUnityLightMcpEditorOnlyProbe\""));

            Assert.That(payload.status, Is.EqualTo("rolled_back"));
            Assert.That(LastChange(payload).error_code, Is.EqualTo("prefab_mutation_component_add_failed"));
        }

        [Test]
        public void TransparentHitAreasWithAVisibleChildCountAsVisible()
        {
            var nodes = new List<XUUnityLightMcpUiNode>
            {
                new() { path = "C/Tab", parent_path = "C", active_in_hierarchy = true, raycast_target_known = true, raycast_target = true },
                new() { path = "C/Tab/Icon", parent_path = "C/Tab", active_in_hierarchy = true, visible = true },
                new() { path = "C/Empty", parent_path = "C", active_in_hierarchy = true, raycast_target_known = true, raycast_target = true },
            };

            XUUnityLightMcpUiTreeBuilder.MarkVisibleViaDescendant(nodes);

            Assert.That(nodes[0].visible_via_descendant, Is.True);
            Assert.That(nodes[0].visible_descendant_path, Is.EqualTo("C/Tab/Icon"));
            Assert.That(nodes[2].visible_via_descendant, Is.False);
            Assert.That(
                XUUnityLightMcpUiSelectorMatcher.Matches(nodes[0], new XUUnityLightMcpUiSelectorArgs { requireVisible = true }),
                Is.True);
            Assert.That(
                XUUnityLightMcpUiSelectorMatcher.Matches(nodes[2], new XUUnityLightMcpUiSelectorArgs { requireVisible = true }),
                Is.False);
        }

        static string SkeletonOps()
        {
            return Op("add_component", ROOT, "\"componentType\":\"ScrollRect\"") + ","
                   + Op("add_component", ROOT, "\"componentType\":\"EventSystem\"") + ","
                   + Op("create_child", ROOT, "\"childName\":\"Button\"") + ","
                   + Op("add_component", ROOT + "/Button", "\"componentType\":\"Image\"") + ","
                   + Op("add_component", ROOT + "/Button", "\"componentType\":\"Button\"") + ","
                   + Op("create_child", ROOT + "/Button", "\"childName\":\"Icon\"") + ","
                   + Op("add_component", ROOT + "/Button/Icon", "\"componentType\":\"Image\"") + ","
                   + Op("create_child", ROOT, "\"childName\":\"Background\",\"siblingIndex\":0") + ","
                   + Op("add_component", ROOT + "/Background", "\"componentType\":\"MeshRenderer\"") + ","
                   + Op("set_rect_transform", ROOT + "/Background", "\"propertyPath\":\"stretch\"");
        }

        static string WiringOps()
        {
            return Field(ROOT + "/Button", "Button", "m_TargetGraphic", ROOT + "/Button#Image") + ","
                   + Field(ROOT, "ScrollRect", "m_Content", ROOT + "/Button") + ","
                   + Field(ROOT, "EventSystem", "m_FirstSelected", ROOT + "/Button/Icon") + ","
                   + Field(ROOT + "/Button", "Button", "m_Navigation.m_SelectOnUp", ROOT + "/Button") + ","
                   + Op("set_serialized_field", ROOT + "/Background",
                       "\"componentType\":\"MeshRenderer\",\"propertyPath\":\"m_Materials.Array.size\",\"numberValue\":2") + ","
                   + Field(ROOT + "/Background", "MeshRenderer", "m_Materials.Array.data[1]", MATERIAL_PATH);
        }

        static string Field(string path, string component, string property, string value)
        {
            return Op("set_serialized_field", path,
                "\"componentType\":\"" + component + "\",\"propertyPath\":\"" + property + "\",\"stringValue\":\"" + value + "\"");
        }

        static string Op(string op, string path, string extra)
        {
            return "{\"op\":\"" + op + "\",\"path\":\"" + path + "\"," + extra + "}";
        }

        static XUUnityLightMcpPrefabMutationChange LastChange(XUUnityLightMcpPrefabMutationPayload payload)
        {
            return payload.changes[payload.changes.Count - 1];
        }

        static string Errors(XUUnityLightMcpPrefabMutationPayload payload)
        {
            var messages = new List<string>();
            payload.errors.ForEach(error => messages.Add(error.code + ": " + error.message + " " + error.detail));
            payload.changes.ForEach(change =>
            {
                if (!string.IsNullOrEmpty(change.error_code))
                {
                    messages.Add(change.index + " " + change.error_code + ": " + change.error_message);
                }
            });
            return string.Join("; ", messages);
        }

        static XUUnityLightMcpPrefabMutationPayload Create(bool write, string operations)
        {
            var args = "{\"prefabPath\":\"" + PREFAB_PATH + "\",\"rootName\":\"" + ROOT + "\",\"approve\":" + (write ? "true" : "false")
                       + ",\"previewOnly\":" + (write ? "false" : "true") + ",\"operations\":[" + operations + "]}";
            var response = new XUUnityLightMcpPrefabCreateOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-create-selftest",
                operation = XUUnityLightMcpPrefabCreateOperation.RegisteredOperationName,
                args_json = args
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpPrefabMutationPayload>(response.payload_json);
        }
    }
}
