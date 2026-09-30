using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Ugui;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.UiRenderClick")]
    public sealed class XUUnityLightMcpRenderAndClickTests
    {
        const string GENERATED_ROOT = "Assets/XUUnityLightMcpGenerated";
        const string PREFAB_DIR = GENERATED_ROOT + "/RenderSelfTest";

        string _prefabPath = "";
        string _outputPath = "";
        string _snapshotPath = "";
        GameObject _canvasRoot;
        int _clickCount;
        readonly List<Object> _generatedObjects = new();

        [SetUp]
        public void SetUp()
        {
            _clickCount = 0;
            Directory.CreateDirectory(PREFAB_DIR);
            AssetDatabase.Refresh();

            var root = new GameObject("XUUnityMcp_RenderRoot", typeof(RectTransform), typeof(Image));
            var rect = root.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            root.GetComponent<Image>().color = new Color(0.2f, 0.6f, 0.9f, 1f);

            var label = new GameObject("Title", typeof(RectTransform), typeof(Text));
            label.transform.SetParent(root.transform, false);
            label.GetComponent<Text>().text = "Rendered";

            _prefabPath = PREFAB_DIR + "/XUUnityMcp_RenderRoot.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, _prefabPath);
            Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
        }

        [TearDown]
        public void TearDown()
        {
            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
                _canvasRoot = null;
            }

            foreach (var generated in _generatedObjects)
            {
                if (generated != null)
                {
                    Object.DestroyImmediate(generated);
                }
            }

            _generatedObjects.Clear();

            if (!string.IsNullOrEmpty(_outputPath) && File.Exists(_outputPath))
            {
                File.Delete(_outputPath);
                _outputPath = "";
            }

            if (!string.IsNullOrEmpty(_snapshotPath) && File.Exists(_snapshotPath))
            {
                File.Delete(_snapshotPath);
                _snapshotPath = "";
            }

            if (!string.IsNullOrEmpty(_prefabPath))
            {
                AssetDatabase.DeleteAsset(_prefabPath);
                AssetDatabase.DeleteAsset(PREFAB_DIR);
                _prefabPath = "";
            }
        }

        [Test]
        public void Render_ProducesAPngAtTheDeclaredViewportWithoutBootingTheApp()
        {
            var scene = SceneManager.GetActiveScene();
            var rootCountBefore = scene.rootCount;

            var payload = Render(240, 480);

            Assert.That(payload.success, Is.True, string.Join("; ", payload.errors.ConvertAll(item => item.message)));
            Assert.That(payload.application_booted, Is.False);
            Assert.That(payload.persisted_scene_changes, Is.False);
            Assert.That(File.Exists(payload.screenshot_path), Is.True);
            Assert.That(payload.screenshot_width, Is.EqualTo(240));
            Assert.That(payload.screenshot_height, Is.EqualTo(480));
            Assert.That(payload.screenshot_size_bytes, Is.GreaterThan(0));
            Assert.That(
                SceneManager.GetActiveScene().rootCount,
                Is.EqualTo(rootCountBefore),
                "the preview scene must not leak objects into the open scene");
        }

        [Test]
        public void Render_DrawsTheActualPrefabPixelsWhenAGraphicsDeviceIsPresent()
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                Assert.Ignore("Headless batchmode has no graphics device; pixel content cannot be verified here.");
            }

            var payload = Render(240, 480);
            Assert.That(payload.success, Is.True);

            var texture = new Texture2D(2, 2);
            try
            {
                Assert.That(texture.LoadImage(File.ReadAllBytes(payload.screenshot_path)), Is.True);
                Assert.That(texture.width, Is.EqualTo(240));
                Assert.That(texture.height, Is.EqualTo(480));

                var centre = texture.GetPixel(120, 240);
                Assert.That(centre.a, Is.GreaterThan(0.5f), "the rendered prefab should fill the viewport");
                Assert.That(
                    centre.b,
                    Is.GreaterThan(centre.r),
                    "the prefab's blue Image should dominate the centre pixel");
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }
        }

        [Test]
        public void Render_ReturnsTheSnapshotItRenderedInRenderPixelSpaceWhenAskedInline()
        {
            var payload = Render(240, 480, extraArgsJson: "\"includeSnapshot\":true");

            Assert.That(payload.snapshot, Is.Not.Null);
            Assert.That(payload.snapshot.target.capture_width, Is.EqualTo(240));
            Assert.That(payload.snapshot.target.capture_height, Is.EqualTo(480));
            Assert.That(payload.snapshot.node_count, Is.GreaterThanOrEqualTo(2));

            var title = payload.snapshot.nodes.Find(node => node.name == "Title");
            Assert.That(title, Is.Not.Null);
            Assert.That(title.has_text, Is.True);
            Assert.That(title.text, Is.EqualTo("Rendered"));
            Assert.That(title.has_bounds, Is.True);
        }

        [Test]
        public void Render_WritesTheSnapshotBesideTheCaptureAndKeepsItOutOfTheResponseByDefault()
        {
            var payload = Render(240, 480);

            Assert.That(payload.success, Is.True, string.Join("; ", payload.errors.ConvertAll(item => item.message)));
            // JsonUtility writes an empty object rather than null for an unset class field, so the
            // contract worth holding is that the node list is absent from the response, not that the
            // container is.
            Assert.That(
                payload.snapshot.nodes,
                Is.Empty,
                "the inline copy is large and the comparison tool cannot consume it");
            Assert.That(payload.snapshot_path, Is.Not.Empty);
            Assert.That(File.Exists(payload.snapshot_path), Is.True);
            Assert.That(
                Path.GetFileName(payload.snapshot_path),
                Is.EqualTo(Path.GetFileNameWithoutExtension(payload.screenshot_path) + ".ui-snapshot.json"));
            Assert.That(
                Path.GetFullPath(Path.GetDirectoryName(payload.snapshot_path)),
                Is.EqualTo(Path.GetFullPath(Path.GetDirectoryName(payload.screenshot_path))),
                "the snapshot must land beside the capture it describes");

            // The comparison surface reads this file by path and refuses any other schema, so the written
            // artifact has to be a complete ui.read.v1 payload, not a summary of one.
            var written = JsonUtility.FromJson<XUUnityLightMcpUiTreePayload>(
                File.ReadAllText(payload.snapshot_path));
            Assert.That(written.schema_version, Is.EqualTo("xuunity.ui.read.v1"));
            Assert.That(written.target.capture_width, Is.EqualTo(240));
            Assert.That(written.target.capture_height, Is.EqualTo(480));
            Assert.That(written.nodes.Find(node => node.name == "Title"), Is.Not.Null);
        }

        [Test]
        public void Render_AppliesTransientOverridesWithoutTouchingTheAsset()
        {
            var before = File.ReadAllBytes(_prefabPath);

            var payload = Render(
                240,
                480,
                extraArgsJson:
                "\"includeSnapshot\":true,\"overrides\":["
                + "{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_RenderRoot/Title\","
                + "\"componentType\":\"Text\",\"propertyPath\":\"m_Text\",\"stringValue\":\"Boost active\"}]");

            Assert.That(payload.success, Is.True, string.Join("; ", payload.errors.ConvertAll(item => item.message)));
            Assert.That(payload.requested_override_count, Is.EqualTo(1));
            Assert.That(payload.applied_overrides[0].status, Is.EqualTo("applied"));
            Assert.That(payload.snapshot.nodes.Find(node => node.name == "Title").text, Is.EqualTo("Boost active"));
            CollectionAssert.AreEqual(
                before,
                File.ReadAllBytes(_prefabPath),
                "a transient override must never reach the shared asset");
        }

        [Test]
        public void Render_FailsInsteadOfCapturingTheStateTheOverrideDidNotReach()
        {
            var payload = Render(
                240,
                480,
                extraArgsJson:
                "\"overrides\":[{\"op\":\"set_serialized_field\",\"path\":\"XUUnityMcp_NoSuchChild\","
                + "\"componentType\":\"Text\",\"propertyPath\":\"m_Text\",\"stringValue\":\"Boost active\"}]");

            Assert.That(payload.success, Is.False);
            Assert.That(payload.errors.ConvertAll(item => item.code), Does.Contain("prefab_render_override_failed"));
            Assert.That(payload.screenshot_path, Is.Empty, "a capture of the wrong state is worse than no capture");
            Assert.That(payload.applied_overrides[0].error_code, Is.EqualTo("prefab_mutation_target_not_found"));
        }

        [Test]
        public void Render_AppliesDeclaredSafeAreaInsets()
        {
            var payload = Render(240, 480, safeAreaTop: 40, safeAreaBottom: 20);

            Assert.That(payload.safe_area.y, Is.EqualTo(40f));
            Assert.That(payload.safe_area.height, Is.EqualTo(420f));
        }

        [Test]
        public void Render_RefusesAnInvalidViewportAndAnAllConsumingSafeArea()
        {
            var noViewport = Render(0, 0);
            Assert.That(noViewport.success, Is.False);
            Assert.That(noViewport.errors[0].code, Is.EqualTo("prefab_render_viewport_invalid"));

            var swallowed = Render(240, 480, safeAreaTop: 300, safeAreaBottom: 300);
            Assert.That(swallowed.success, Is.False);
            Assert.That(swallowed.errors[0].code, Is.EqualTo("prefab_render_safe_area_invalid"));
        }

        [Test]
        public void Render_RefusesAMissingPrefab()
        {
            var response = new XUUnityLightMcpPrefabRenderOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "render-missing",
                operation = "unity.prefab.render",
                args_json = "{\"prefabPath\":\"Assets/XUUnityMcp_NoSuchPrefab.prefab\",\"width\":240,\"height\":480}"
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpPrefabRenderPayload>(response.payload_json);

            Assert.That(payload.success, Is.False);
            Assert.That(payload.errors[0].code, Is.EqualTo("prefab_not_found"));
        }

        [Test]
        public void Click_RequiresExplicitApprovalAndTheClickAction()
        {
            BuildClickableCanvas();

            var unapproved = Click("{\"selector\":{\"name\":\"ClaimButton\"},\"action\":\"click\"}");
            Assert.That(unapproved.refusal_code, Is.EqualTo("ui_click_approval_required"));

            var wrongAction = Click("{\"selector\":{\"name\":\"ClaimButton\"},\"action\":\"drag\",\"approve\":true}");
            Assert.That(wrongAction.refusal_code, Is.EqualTo("ui_action_not_permitted"));
            Assert.That(_clickCount, Is.Zero);
        }

        [Test]
        public void Click_DeliversOnceToAUniqueInteractableTarget()
        {
            BuildClickableCanvas();

            var payload = Click("{\"selector\":{\"name\":\"ClaimButton\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(payload.success, Is.True, payload.refusal_code);
            Assert.That(payload.delivered, Is.True);
            Assert.That(payload.status, Is.EqualTo("effective"));
            Assert.That(payload.delivery_mechanism, Is.EqualTo("event_system_pointer_click_handler"));
            Assert.That(payload.event_system_scope, Is.EqualTo("eventsystem_current_at_delivery"));
            Assert.That(_clickCount, Is.EqualTo(1), "the click must be delivered exactly once");
            Assert.That(payload.before_snapshot.signature, Is.Not.Empty);
            Assert.That(payload.after_snapshot.signature, Is.Not.Empty);
        }

        [Test]
        public void Click_RefusesAmbiguousHiddenAndDisabledTargets()
        {
            BuildClickableCanvas();

            var ambiguous = Click("{\"selector\":{\"name\":\"Row\"},\"action\":\"click\",\"approve\":true}");
            Assert.That(ambiguous.refusal_code, Is.EqualTo("selector_ambiguous"));

            var hidden = Click("{\"selector\":{\"name\":\"HiddenButton\"},\"action\":\"click\",\"approve\":true}");
            Assert.That(hidden.refusal_code, Is.EqualTo("ui_target_not_visible"));

            var disabled = Click("{\"selector\":{\"name\":\"DisabledButton\"},\"action\":\"click\",\"approve\":true}");
            Assert.That(disabled.refusal_code, Is.EqualTo("ui_target_not_interactable"));

            var passThrough = Click(
                "{\"selector\":{\"name\":\"PassThroughButton\"},\"action\":\"click\",\"approve\":true}");
            Assert.That(passThrough.refusal_code, Is.EqualTo("ui_target_does_not_block_raycasts"));
            Assert.That(passThrough.pointer_target_status, Is.EqualTo("canvas_group_blocks_raycasts"));
            Assert.That(passThrough.pointer_target_blocked_by, Does.EndWith("/PassThroughButton"));
            Assert.That(passThrough.target_node.visible, Is.True, "the pass-through button renders normally");

            Assert.That(_clickCount, Is.Zero, "no refusal path may deliver a click");
        }

        [Test]
        public void Click_DeliversThroughATransparentHitAreaThatFramesAVisibleIcon()
        {
            BuildClickableCanvas();
            NewTransparentHitAreaButtonWithIcon("Settings");

            var payload = Click("{\"selector\":{\"name\":\"Settings\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(payload.refusal_code, Is.Empty, payload.errors.Count > 0 ? payload.errors[0].message : "");
            Assert.That(payload.status, Is.EqualTo("effective"));
            Assert.That(_clickCount, Is.EqualTo(1));
            Assert.That(payload.target_node.visible, Is.False, "the hit area itself renders nothing");
            Assert.That(payload.target_node.pointer_targetable, Is.True);
            Assert.That(payload.target_node.pointer_target_status, Is.EqualTo("targetable"));
            Assert.That(payload.pointer_targetable, Is.True);
            Assert.That(payload.pointer_target_path, Does.EndWith("/Settings"));
            Assert.That(payload.transparent_hit_area, Is.True);
            Assert.That(payload.transparent_hit_area_evidence, Is.EqualTo("visible_descendant_renders"));
            Assert.That(payload.transparent_hit_area_visible_path, Does.EndWith("/Settings/Icon"));
            Assert.That(
                payload.warnings.Exists(item => item.code == "ui_click_transparent_hit_area_without_visible_content"),
                Is.False);
        }

        [Test]
        public void Click_ReachesTheButtonThroughItsHitAreaWhenTheSelectorNamesTheNonRaycastIcon()
        {
            BuildClickableCanvas();
            NewTransparentHitAreaButtonWithIcon("Settings");

            var payload = Click("{\"selector\":{\"name\":\"Icon\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(payload.refusal_code, Is.Empty, payload.errors.Count > 0 ? payload.errors[0].message : "");
            Assert.That(payload.delivered_to_path, Does.EndWith("/Settings"));
            Assert.That(_clickCount, Is.EqualTo(1));
            Assert.That(payload.target_node.visible, Is.True);
            Assert.That(payload.target_node.pointer_targetable, Is.False);
            Assert.That(payload.target_node.pointer_target_status, Is.EqualTo("raycast_target_disabled"));
            Assert.That(payload.pointer_target_path, Does.EndWith("/Settings"));
            Assert.That(payload.transparent_hit_area_evidence, Is.EqualTo("visible_descendant_renders"));
        }

        [Test]
        public void Click_DeliversToATransparentHitAreaWithNothingVisibleButFlagsIt()
        {
            BuildClickableCanvas();
            NewTransparentHitAreaButton("GhostButton");

            var payload = Click("{\"selector\":{\"name\":\"GhostButton\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(payload.refusal_code, Is.Empty, payload.errors.Count > 0 ? payload.errors[0].message : "");
            Assert.That(payload.delivered, Is.True);
            Assert.That(_clickCount, Is.EqualTo(1), "Unity raycasts an alpha-0 Graphic, so a real pointer reaches it");
            Assert.That(payload.pointer_targetable, Is.True);
            Assert.That(payload.transparent_hit_area, Is.True);
            Assert.That(payload.transparent_hit_area_evidence, Is.EqualTo("no_visible_descendant"));
            Assert.That(payload.transparent_hit_area_visible_path, Is.Empty);
            Assert.That(
                payload.warnings.Exists(item => item.code == "ui_click_transparent_hit_area_without_visible_content"),
                Is.True,
                "an invisible hit area with nothing drawn over it must be flagged");
        }

        [Test]
        public void Click_RefusesATransparentSpritePixelThatTheAlphaHitTestRejects()
        {
            BuildClickableCanvas();
            NewAlphaHitTestButton("TransparentSpriteButton", Color.clear);
            NewAlphaHitTestButton("OpaqueSpriteButton", Color.white);

            var refused = Click(
                "{\"selector\":{\"name\":\"TransparentSpriteButton\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(refused.refusal_code, Is.EqualTo("ui_target_not_pointer_targetable"));
            Assert.That(refused.pointer_targetable, Is.False);
            Assert.That(refused.pointer_target_status, Is.EqualTo("alpha_hit_test_rejected"));
            Assert.That(refused.pointer_target_blocked_by, Does.EndWith("/TransparentSpriteButton"));
            Assert.That(refused.target_node.pointer_targetable, Is.False);
            Assert.That(_clickCount, Is.Zero, "a refused click must never be delivered");

            var delivered = Click(
                "{\"selector\":{\"name\":\"OpaqueSpriteButton\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(
                delivered.refusal_code,
                Is.Empty,
                delivered.errors.Count > 0 ? delivered.errors[0].message : "");
            Assert.That(delivered.pointer_target_status, Is.EqualTo("targetable"));
            Assert.That(_clickCount, Is.EqualTo(1), "the same threshold accepts an opaque pixel");
        }

        [Test]
        public void Click_NamesTheRejectingFilterForUnreachableTargets()
        {
            BuildClickableCanvas();

            var mask = NewChild("ScrollMask");
            mask.AddComponent<RectMask2D>();
            mask.GetComponent<RectTransform>().anchoredPosition = new Vector2(200f, 0f);
            var clipped = NewCountingButton("ClippedButton").GetComponent<RectTransform>();
            clipped.SetParent(mask.transform, false);
            clipped.anchoredPosition = new Vector2(-200f, 0f);

            NewCountingButton("PaddedOutButton").GetComponent<Image>().raycastPadding = new Vector4(200f, 0f, 0f, 0f);

            var bare = NewChild("BareButton");
            bare.AddComponent<Button>();
            var bareChild = new GameObject("BareChild", typeof(RectTransform));
            bareChild.transform.SetParent(bare.transform, false);

            NewCountingButton("DisabledImageButton").GetComponent<Image>().enabled = false;

            var unwired = new GameObject("XUUnityMcp_UnwiredCanvas", typeof(RectTransform), typeof(Canvas));
            unwired.transform.SetParent(_canvasRoot.transform, false);
            var unwiredButton = NewCountingButton("UnwiredButton");
            unwiredButton.transform.SetParent(unwired.transform, false);

            var expectations = new Dictionary<string, (string status, string blockedBy)>
            {
                ["ClippedButton"] = ("raycast_filter_rejected", "/ScrollMask"),
                ["PaddedOutButton"] = ("outside_raycast_area", ""),
                ["BareChild"] = ("no_pointer_targetable_graphic", ""),
                ["DisabledImageButton"] = ("graphic_inactive", ""),
                ["UnwiredButton"] = ("no_raycaster", "/XUUnityMcp_UnwiredCanvas")
            };

            foreach (var expectation in expectations)
            {
                var name = expectation.Key;
                var payload = Click(
                    "{\"selector\":{\"name\":\"" + name + "\"},\"action\":\"click\",\"approve\":true}");

                Assert.That(payload.refusal_code, Is.EqualTo("ui_target_not_pointer_targetable"), name);
                Assert.That(payload.pointer_target_status, Is.EqualTo(expectation.Value.status), name);
                Assert.That(payload.pointer_target_blocked_by, Does.EndWith(expectation.Value.blockedBy), name);
            }

            var clippedNode = Click(
                "{\"selector\":{\"name\":\"ClippedButton\"},\"action\":\"click\",\"approve\":true}").target_node;
            Assert.That(clippedNode.pointer_targetable, Is.False);
            Assert.That(clippedNode.pointer_target_status, Is.EqualTo("raycast_filter_rejected"));
            Assert.That(_clickCount, Is.Zero, "a refused click must never be delivered");
        }

        [Test]
        public void Click_RefusesATargetWithNoClickHandler()
        {
            BuildClickableCanvas();

            var payload = Click("{\"selector\":{\"name\":\"PlainPanel\"},\"action\":\"click\",\"approve\":true}");

            Assert.That(payload.refusal_code, Is.EqualTo("ui_target_has_no_click_handler"));
        }

        [Test]
        public void Click_DoesNotCallABudgetLimitedSearchANotFoundVerdict()
        {
            BuildClickableCanvas();

            var payload = Click(
                "{\"selector\":{\"name\":\"ClaimButton\"},\"action\":\"click\",\"approve\":true,\"maxNodes\":1}");

            Assert.That(payload.refusal_code, Is.EqualTo("ui_selector_search_truncated"));
            Assert.That(payload.delivered, Is.False);
            Assert.That(payload.search_truncated, Is.True);
            Assert.That(payload.search_node_count, Is.EqualTo(1));
            Assert.That(payload.search_max_nodes, Is.EqualTo(1));
            Assert.That(payload.search_truncation_reason, Is.EqualTo("max_nodes_reached"));
            Assert.That(payload.before_snapshot.truncated, Is.True);
            Assert.That(payload.before_snapshot.truncation_reason, Is.EqualTo("max_nodes_reached"));
            Assert.That(payload.search_target.searched_scenes, Is.Not.Empty);
            Assert.That(_clickCount, Is.Zero, "an inconclusive selector search must never deliver a click");
        }

        [Test]
        public void Click_DoesNotClaimUniquenessFromABudgetLimitedMatch()
        {
            BuildClickableCanvas();

            var payload = Click(
                "{\"selector\":{\"name\":\"ClaimButton\"},\"action\":\"click\",\"approve\":true,\"maxNodes\":2}");

            Assert.That(payload.refusal_code, Is.EqualTo("ui_selector_search_truncated"));
            Assert.That(payload.delivered, Is.False);
            Assert.That(payload.match_count, Is.EqualTo(1));
            Assert.That(payload.search_truncated, Is.True);
            Assert.That(payload.search_node_count, Is.EqualTo(2));
            Assert.That(payload.search_max_nodes, Is.EqualTo(2));
            Assert.That(payload.search_truncation_reason, Is.EqualTo("max_nodes_reached"));
            Assert.That(_clickCount, Is.Zero, "a partial search cannot prove that the scanned match is unique");
        }

        [Test]
        public void RenderAndClickOperationsAreRegisteredAndCapabilityGated()
        {
            foreach (var operation in new[] { "unity.prefab.render", "unity.ui.click" })
            {
                Assert.That(XUUnityLightMcpOperationRegistry.TryGet(operation, out _), Is.True, operation);
                Assert.That(
                    XUUnityLightMcpCapabilityRegistry.TryGetRequiredCapability(operation, out var capability),
                    Is.True,
                    operation);
                Assert.That(capability, Is.Not.Empty);
            }
        }

        void BuildClickableCanvas()
        {
            _canvasRoot = new GameObject(
                "XUUnityMcp_ClickCanvas",
                typeof(RectTransform),
                typeof(Canvas),
                typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            NewCountingButton("ClaimButton");

            NewButton("DisabledButton", interactable: false);

            var passThrough = NewButton("PassThroughButton", interactable: true);
            passThrough.gameObject.AddComponent<CanvasGroup>().blocksRaycasts = false;

            var hidden = NewButton("HiddenButton", interactable: true);
            var hiddenGroup = hidden.gameObject.AddComponent<CanvasGroup>();
            hiddenGroup.alpha = 0f;
            hiddenGroup.blocksRaycasts = false;

            NewChild("Row");
            NewChild("Row");
            NewChild("PlainPanel");
        }

        Button NewButton(string name, bool interactable)
        {
            var child = NewChild(name);
            child.AddComponent<Image>();
            var button = child.AddComponent<Button>();
            button.interactable = interactable;
            return button;
        }

        Button NewCountingButton(string name)
        {
            var button = NewButton(name, interactable: true);
            button.onClick.AddListener(() =>
            {
                _clickCount++;
                button.interactable = false;
            });
            return button;
        }

        Button NewTransparentHitAreaButton(string name)
        {
            var button = NewCountingButton(name);
            button.GetComponent<Image>().color = new Color(0f, 0f, 0f, 0f);
            return button;
        }

        void NewTransparentHitAreaButtonWithIcon(string name)
        {
            var button = NewTransparentHitAreaButton(name);
            var icon = new GameObject("Icon", typeof(RectTransform), typeof(Image), typeof(CanvasGroup));
            icon.transform.SetParent(button.transform, false);
            icon.GetComponent<RectTransform>().sizeDelta = new Vector2(96f, 96f);
            icon.GetComponent<Image>().raycastTarget = false;
            icon.GetComponent<CanvasGroup>().blocksRaycasts = false;
        }

        void NewAlphaHitTestButton(string name, Color pixel)
        {
            var texture = new Texture2D(4, 4, TextureFormat.RGBA32, false);
            var pixels = new Color[16];
            for (var i = 0; i < pixels.Length; i++)
            {
                pixels[i] = pixel;
            }

            texture.SetPixels(pixels);
            texture.Apply();
            var sprite = Sprite.Create(texture, new Rect(0f, 0f, 4f, 4f), new Vector2(0.5f, 0.5f));
            _generatedObjects.Add(texture);
            _generatedObjects.Add(sprite);

            var image = NewCountingButton(name).GetComponent<Image>();
            image.sprite = sprite;
            image.alphaHitTestMinimumThreshold = 0.5f;
        }

        GameObject NewChild(string name)
        {
            var child = new GameObject(name, typeof(RectTransform));
            child.transform.SetParent(_canvasRoot.transform, false);
            child.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            return child;
        }

        XUUnityLightMcpPrefabRenderPayload Render(
            int width,
            int height,
            int safeAreaTop = 0,
            int safeAreaBottom = 0,
            string extraArgsJson = "")
        {
            _outputPath = Path.Combine(Path.GetTempPath(), $"xuunity_render_{width}x{height}_{safeAreaTop}.png");
            var args = "{\"prefabPath\":\"" + _prefabPath + "\",\"width\":" + width + ",\"height\":" + height
                       + ",\"safeAreaTop\":" + safeAreaTop + ",\"safeAreaBottom\":" + safeAreaBottom
                       + ",\"outputPath\":\"" + _outputPath.Replace("\\", "/") + "\""
                       + (string.IsNullOrEmpty(extraArgsJson) ? "" : "," + extraArgsJson) + "}";
            var response = new XUUnityLightMcpPrefabRenderOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "prefab-render-selftest",
                operation = "unity.prefab.render",
                args_json = args
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpPrefabRenderPayload>(response.payload_json);
            if (!string.IsNullOrEmpty(payload.snapshot_path))
            {
                _snapshotPath = payload.snapshot_path;
            }

            return payload;
        }

        static XUUnityLightMcpUiClickPayload Click(string argsJson)
        {
            var response = new XUUnityLightMcpUiClickOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "ui-click-selftest",
                operation = "unity.ui.click",
                args_json = argsJson
            });
            Assert.That(response.status, Is.EqualTo("ok"));
            return JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(response.payload_json);
        }
    }
}
