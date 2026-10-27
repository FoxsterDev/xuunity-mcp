using System.Collections;
using System.IO;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Ugui;

namespace XUUnity.LightMcp.Tests.PlayModeUgui
{
    internal sealed class XUUnityLightMcpRaycastIdentityGuardedButton : MonoBehaviour, IPointerClickHandler
    {
        public int accepted;
        public int rejected;
        public GameObject observedRaycastObject;

        public void OnPointerClick(PointerEventData eventData)
        {
            observedRaycastObject = eventData?.pointerCurrentRaycast.gameObject;
            if (observedRaycastObject != gameObject)
            {
                rejected++;
                return;
            }

            accepted++;
            var label = transform.childCount > 0 ? transform.GetChild(0).GetComponent<Text>() : null;
            if (label != null)
            {
                label.text = "Accepted";
            }
        }
    }

    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.PlayMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.UiInteraction")]
    public sealed class XUUnityLightMcpUiClickRaycastIdentityPlayModeTests
    {
        GameObject _canvasRoot;
        XUUnityLightMcpRaycastIdentityGuardedButton _guarded;

        [SetUp]
        public void SetUp()
        {
            Assert.That(Application.isPlaying, Is.True,
                "raycast identity is a runtime contract and must be proven in PlayMode");

            _canvasRoot = new GameObject("XUUnityMcp_RaycastIdentityCanvas", typeof(RectTransform), typeof(Canvas), typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            var button = new GameObject("GuardedButton", typeof(RectTransform), typeof(Image));
            button.transform.SetParent(_canvasRoot.transform, false);
            button.GetComponent<RectTransform>().sizeDelta = new Vector2(400f, 160f);
            _guarded = button.AddComponent<XUUnityLightMcpRaycastIdentityGuardedButton>();

            var label = new GameObject("GuardedLabel", typeof(RectTransform), typeof(Text));
            label.transform.SetParent(button.transform, false);
            label.GetComponent<RectTransform>().sizeDelta = new Vector2(400f, 160f);
            label.GetComponent<Text>().text = "Press";
            label.GetComponent<Text>().raycastTarget = false;
        }

        [TearDown]
        public void TearDown()
        {
            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
                _canvasRoot = null;
            }
            _guarded = null;
        }

        static XUUnityLightMcpUiClickPayload Click(string selectorJson)
        {
            var response = new XUUnityLightMcpUiClickOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "ui-click-raycast-identity-selftest",
                operation = XUUnityLightMcpUiClickOperation.RegisteredOperationName,
                args_json = "{\"action\":\"click\",\"approve\":true,\"targetKind\":\"all_loaded_scenes\","
                            + "\"maxNodes\":800,\"maxDepth\":20,\"selector\":" + selectorJson + "}"
            });
            return JsonUtility.FromJson<XUUnityLightMcpUiClickPayload>(response.payload_json);
        }

        [Test]
        public void ClickSatisfiesAHandlerThatValidatesPointerCurrentRaycastIdentity()
        {
            var payload = Click("{\"name\":\"GuardedButton\"}");

            Assert.That(payload.refusal_code, Is.Empty, payload.refusal_code);
            Assert.That(payload.delivered, Is.True, "the guarded handler must receive the pointer event");
            Assert.That(_guarded.rejected, Is.EqualTo(0),
                "a handler comparing pointerCurrentRaycast.gameObject must not reject the delivered click");
            Assert.That(_guarded.accepted, Is.EqualTo(1));
            Assert.That(_guarded.observedRaycastObject, Is.SameAs(_guarded.gameObject),
                "pointerCurrentRaycast must name the GameObject the handler compares against");
            Assert.That(payload.state_changed, Is.True);
            Assert.That(payload.effective, Is.True);
        }

        [Test]
        public void PointerRaycastEvidenceIsAlwaysPublishedAndNamesTheRaycastTarget()
        {
            var payload = Click("{\"name\":\"GuardedButton\"}");

            Assert.That(payload.pointer_raycast_evidence, Is.Not.Empty,
                "every delivered click must say where its pointerCurrentRaycast came from");
            var known = payload.pointer_raycast_evidence == "event_system_raycast_resolves_to_handler"
                        || payload.pointer_raycast_evidence == "synthesized_no_raycast_hit"
                        || payload.pointer_raycast_evidence == "synthesized_no_event_system";
            Assert.That(known, Is.True,
                $"unknown pointer raycast evidence value '{payload.pointer_raycast_evidence}'");
            Assert.That(payload.pointer_raycast_target_path, Does.EndWith("GuardedButton"));
            Assert.That(payload.occluded_by_path, Is.Empty);

            var synthesized = payload.pointer_raycast_evidence.StartsWith("synthesized");
            var warned = payload.warnings.Exists(w => w.code == "ui_click_pointer_raycast_synthesized");
            Assert.That(warned, Is.EqualTo(synthesized),
                "a synthesized raycast must warn, and an observed one must not");
        }

        [Test]
        public void ClickOnANonRaycastChildStillNamesTheHandlerAsTheRaycastTarget()
        {
            var payload = Click("{\"name\":\"GuardedLabel\"}");

            Assert.That(payload.refusal_code, Is.Empty, payload.refusal_code);
            Assert.That(payload.delivered_to_path, Does.EndWith("GuardedButton"),
                "the click must resolve up to the ancestor handler");
            Assert.That(_guarded.rejected, Is.EqualTo(0),
                "targeting a non-raycast child must not produce a raycast identity the handler rejects");
            Assert.That(_guarded.accepted, Is.EqualTo(1));
        }

        [UnityTest]
        public IEnumerator ALiveRaycastReachesATransparentHitAreaThatFramesAVisibleIcon()
        {
            var eventSystem = new GameObject("XUUnityMcp_TransparentHitAreaEventSystem", typeof(EventSystem));
            try
            {
                var hitArea = new GameObject(
                    "TransparentHitArea",
                    typeof(RectTransform),
                    typeof(Image),
                    typeof(Button));
                hitArea.transform.SetParent(_canvasRoot.transform, false);
                hitArea.transform.SetAsLastSibling();
                hitArea.GetComponent<RectTransform>().sizeDelta = new Vector2(200f, 200f);
                hitArea.GetComponent<Image>().color = new Color(0f, 0f, 0f, 0f);
                hitArea.GetComponent<CanvasRenderer>().cullTransparentMesh = true;
                var clicks = 0;
                hitArea.GetComponent<Button>().onClick.AddListener(() => clicks++);

                var icon = new GameObject(
                    "TransparentHitAreaIcon",
                    typeof(RectTransform),
                    typeof(Image),
                    typeof(CanvasGroup));
                icon.transform.SetParent(hitArea.transform, false);
                icon.GetComponent<RectTransform>().sizeDelta = new Vector2(96f, 96f);
                icon.GetComponent<Image>().raycastTarget = false;
                icon.GetComponent<CanvasGroup>().blocksRaycasts = false;

                yield return null;
                yield return null;

                var payload = Click("{\"name\":\"TransparentHitArea\"}");

                if (payload.pointer_raycast_hit_count == 0)
                {
                    Assert.Ignore("this runtime produced no event-system raycast hit, so the live raycast cannot be "
                                  + "observed here");
                }

                Assert.That(payload.refusal_code, Is.Empty,
                    "the opaque GuardedButton under the same point is the control: an occlusion refusal here means "
                    + "Unity did not raycast the alpha-0 hit area");
                Assert.That(payload.pointer_raycast_evidence, Is.EqualTo("event_system_raycast_resolves_to_handler"));
                Assert.That(payload.pointer_raycast_target_path, Does.EndWith("/TransparentHitArea"));
                Assert.That(payload.transparent_hit_area_evidence, Is.EqualTo("visible_descendant_renders"));
                Assert.That(clicks, Is.EqualTo(1));
                Assert.That(_guarded.accepted + _guarded.rejected, Is.Zero);
            }
            finally
            {
                Object.DestroyImmediate(eventSystem);
            }
        }

        [Test]
        public void AnOccludingHandlerIsRefusedInsteadOfClickedThrough()
        {
            var blocker = new GameObject("OccludingOverlay", typeof(RectTransform), typeof(Image));
            blocker.transform.SetParent(_canvasRoot.transform, false);
            blocker.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);
            blocker.AddComponent<XUUnityLightMcpRaycastIdentityGuardedButton>();
            blocker.transform.SetAsLastSibling();

            var payload = Click("{\"name\":\"GuardedButton\"}");

            if (payload.pointer_raycast_hit_count == 0)
            {
                Assert.Ignore("this runtime produced no event-system raycast hit, so occlusion cannot be observed here");
            }

            Assert.That(payload.refusal_code, Is.EqualTo("ui_target_occluded"), payload.pointer_raycast_evidence);
            Assert.That(payload.delivered, Is.False);
            Assert.That(payload.occluded_by_path, Does.EndWith("OccludingOverlay"));
            Assert.That(_guarded.accepted, Is.EqualTo(0));
        }

        [UnityTest]
        [Category("XUUnity.MCP.FixedPortrait")]
        public IEnumerator FixedPortraitClickUsesTheRenderViewportWithoutResizingThePreset()
        {
            return RunFixedPortraitCase(RenderMode.ScreenSpaceOverlay, false);
        }

        [UnityTest]
        [Category("XUUnity.MCP.FixedPortrait")]
        public IEnumerator FixedPortraitCameraCanvasUsesTheRenderViewportFromAnEditorCallback()
        {
            return RunFixedPortraitCase(RenderMode.ScreenSpaceCamera, false);
        }

        [UnityTest]
        [Category("XUUnity.MCP.FixedPortrait")]
        public IEnumerator FixedPortraitWorldCanvasUsesTheRenderViewportFromAnEditorCallback()
        {
            return RunFixedPortraitCase(RenderMode.WorldSpace, false);
        }

        [UnityTest]
        [Category("XUUnity.MCP.FixedPortrait")]
        public IEnumerator FixedPortraitOcclusionStillRefusesDeliveryFromAnEditorCallback()
        {
            return RunFixedPortraitCase(RenderMode.ScreenSpaceOverlay, true);
        }

        private IEnumerator RunFixedPortraitCase(RenderMode mode, bool occluded)
        {
            var view = XUUnityLightMcpGameViewUtility.EnsureGameView();
            const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            var selectedIndex = view.GetType().GetProperty("selectedSizeIndex", flags);
            var display = view.GetType().GetProperty("targetDisplay", flags);
            var zoomField = view.GetType().GetField("m_ZoomArea", flags);
            var snapZoom = view.GetType().GetMethod("SnapZoom", flags);
            Assert.That(selectedIndex, Is.Not.Null);
            Assert.That(display, Is.Not.Null);
            Assert.That(zoomField, Is.Not.Null);
            Assert.That(snapZoom, Is.Not.Null);
            var zoomArea = zoomField.GetValue(view);
            Assert.That(zoomArea, Is.Not.Null);
            var scaleProperty = zoomArea.GetType().GetProperty("scale", flags);
            var translationProperty = zoomArea.GetType().GetProperty("translation", flags);
            var setTransform = zoomArea.GetType().GetMethod("SetTransform", flags);
            Assert.That(scaleProperty, Is.Not.Null);
            Assert.That(translationProperty, Is.Not.Null);
            Assert.That(setTransform, Is.Not.Null);
            var previousIndex = selectedIndex.GetValue(view);
            var previousDisplay = display.GetValue(view);
            var previousScale = (Vector2)scaleProperty.GetValue(zoomArea);
            var previousTranslation = (Vector2)translationProperty.GetValue(zoomArea);
            var previousEvents = EventSystem.current;
            GameObject events = null;
            GameObject cameraRoot = null;
            EditorApplication.CallbackFunction callback = null;
            var caseName = mode + (occluded ? "-occluded" : "-delivered");
            try
            {
                try
                {
                    XUUnityLightMcpGameViewUtility.SetFixedResolution(1440, 3200, "", "", false);
                }
                catch (System.InvalidOperationException exception)
                {
                    if (exception.Message.Contains("is not available in the active group"))
                    {
                        Assert.Ignore("This acceptance fixture requires an existing 1440x3200 preset; "
                            + "no preset is created or resized for generic CI. " + exception.Message);
                    }
                    throw;
                }

                display.SetValue(view, 0);
                snapZoom.Invoke(view, new object[] { 0.35f });
                events = new GameObject("XUUnityMcp_FixedPortraitEvents", typeof(EventSystem));
                EventSystem.current = events.GetComponent<EventSystem>();
                cameraRoot = new GameObject("XUUnityMcp_FixedPortraitCamera", typeof(Camera));
                var camera = cameraRoot.GetComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = 1.6f;
                camera.aspect = 1440f / 3200f;
                camera.transform.position = new Vector3(0f, 0f, -10f);
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = Color.black;
                camera.cullingMask = 1 << 31;
                camera.depth = 1000f;
                camera.targetDisplay = 0;
                var canvas = _canvasRoot.GetComponent<Canvas>();
                canvas.renderMode = mode;
                canvas.targetDisplay = 0;
                canvas.sortingOrder = 30000;
                canvas.worldCamera = mode == RenderMode.ScreenSpaceOverlay ? null : camera;
                if (mode == RenderMode.WorldSpace)
                {
                    _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1440f, 3200f);
                    _canvasRoot.transform.position = Vector3.zero;
                    _canvasRoot.transform.localScale = Vector3.one * 0.001f;
                }
                else if (mode == RenderMode.ScreenSpaceCamera)
                {
                    canvas.planeDistance = 1f;
                }

                var rect = _guarded.GetComponent<RectTransform>();
                rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.7375f);
                rect.anchoredPosition = Vector2.zero;
                _guarded.GetComponent<Image>().color = Color.green;
                if (occluded)
                {
                    var blocker = new GameObject("FixedPortraitOccludingOverlay", typeof(RectTransform), typeof(Image));
                    blocker.transform.SetParent(_canvasRoot.transform, false);
                    var blockerRect = blocker.GetComponent<RectTransform>();
                    blockerRect.anchorMin = Vector2.zero;
                    blockerRect.anchorMax = Vector2.one;
                    blockerRect.offsetMin = blockerRect.offsetMax = Vector2.zero;
                    blocker.GetComponent<Image>().color = Color.red;
                    blocker.AddComponent<XUUnityLightMcpRaycastIdentityGuardedButton>();
                    blocker.transform.SetAsLastSibling();
                }
                foreach (var node in _canvasRoot.GetComponentsInChildren<Transform>(true))
                {
                    node.gameObject.layer = 31;
                }

                view.Repaint();
                yield return null;
                yield return null;
                Canvas.ForceUpdateCanvases();
                yield return new WaitForEndOfFrame();
                var zoomBefore = (Vector2)scaleProperty.GetValue(zoomArea);
                Assert.That(zoomBefore.x, Is.EqualTo(0.35f).Within(0.001f));
                Assert.That(zoomBefore.y, Is.EqualTo(0.35f).Within(0.001f));
                var capture = XUUnityLightMcpGameViewUtility.CaptureScreenshot(
                    "fixed-portrait-" + caseName, "fixed-portrait-" + caseName + ".png", false, 0, 0);
                var capturedFrame = Time.frameCount;
                var selectedBefore = selectedIndex.GetValue(view);
                XUUnityLightMcpUiClickPayload payload = null;
                System.Exception callbackError = null;
                var callbackCompleted = false;
                var callbackFrame = -1;
                callback = () =>
                {
                    try
                    {
                        callbackFrame = Time.frameCount;
                        payload = Click("{\"name\":\"GuardedButton\"}");
                    }
                    catch (System.Exception exception)
                    {
                        callbackError = exception;
                    }
                    finally
                    {
                        callbackCompleted = true;
                    }
                };
                EditorApplication.delayCall += callback;
                var deadline = Time.realtimeSinceStartup + 10f;
                while (!callbackCompleted && Time.realtimeSinceStartup < deadline)
                {
                    yield return null;
                }
                EditorApplication.delayCall -= callback;
                var receipt = new FixedPortraitReceipt
                {
                    render_mode = mode.ToString(),
                    occlusion_control = occluded,
                    capture = capture,
                    capture_frame = capturedFrame,
                    callback_frame = callbackFrame,
                    zoom_before = zoomBefore,
                    zoom_after = (Vector2)scaleProperty.GetValue(zoomArea),
                    selected_index_before = (int)selectedBefore,
                    selected_index_after = (int)selectedIndex.GetValue(view),
                    target_display = canvas.targetDisplay,
                    callback_error = callbackError == null ? "" : callbackError.ToString(),
                    click = payload,
                };
                var evidencePath = Path.Combine(Application.dataPath,
                    "../Library/XUUnityLightMcp/fixed-portrait-" + caseName + ".json");
                Directory.CreateDirectory(Path.GetDirectoryName(evidencePath));
                File.WriteAllText(evidencePath, JsonUtility.ToJson(receipt, true));
                TestContext.WriteLine("receipt=" + Path.GetFullPath(evidencePath) + "; screenshot=" + capture.file_path);
                Assert.That(callbackCompleted, Is.True, "the editor callback must run within 10 seconds");
                Assert.That(callbackError, Is.Null);
                Assert.That(payload, Is.Not.Null);
                Assert.That(File.Exists(capture.file_path), Is.True);
                Assert.That(capture.width, Is.EqualTo(1440));
                Assert.That(capture.height, Is.EqualTo(3200));
                Assert.That(callbackFrame, Is.GreaterThanOrEqualTo(capturedFrame));
                Assert.That(payload.render_width, Is.EqualTo(capture.width));
                Assert.That(payload.render_height, Is.EqualTo(capture.height));
                Assert.That(payload.screen_width, Is.EqualTo(capture.width));
                Assert.That(payload.screen_height, Is.EqualTo(capture.height));
                Assert.That(payload.coordinate_context_status,
                    Is.EqualTo("game_view_synchronized").Or.EqualTo("already_aligned"));
                Assert.That(payload.pointer_coordinate_space, Is.EqualTo("game_view_render_pixels"));
                Assert.That(payload.target_node, Is.Not.Null);
                Assert.That(payload.pointer_x,
                    Is.EqualTo(payload.target_node.bounds.x + payload.target_node.bounds.width * 0.5f).Within(1f));
                Assert.That(payload.pointer_y,
                    Is.EqualTo(payload.target_node.bounds.y + payload.target_node.bounds.height * 0.5f).Within(1f));
                Assert.That(payload.pointer_x, Is.EqualTo(capture.width * 0.5f).Within(2f));
                Assert.That(payload.pointer_y, Is.EqualTo(capture.height * 0.7375f).Within(2f));
                Assert.That(receipt.selected_index_after, Is.EqualTo(receipt.selected_index_before));
                Assert.That(receipt.zoom_after.x, Is.EqualTo(zoomBefore.x).Within(0.001f));
                Assert.That(receipt.zoom_after.y, Is.EqualTo(zoomBefore.y).Within(0.001f));
                var current = XUUnityLightMcpGameViewUtility.GetCurrentGameViewData();
                Assert.That(current.width, Is.EqualTo(1440));
                Assert.That(current.height, Is.EqualTo(3200));
                if (occluded)
                {
                    Assert.That(payload.refusal_code, Is.EqualTo("ui_target_occluded"));
                    Assert.That(payload.pointer_raycast_evidence, Is.EqualTo("event_system_raycast_hit_other_handler"));
                    Assert.That(payload.occluded_by_path, Does.EndWith("FixedPortraitOccludingOverlay"));
                    Assert.That(payload.delivered, Is.False);
                    Assert.That(_guarded.accepted + _guarded.rejected, Is.Zero);
                }
                else
                {
                    Assert.That(payload.refusal_code, Is.Empty, payload.refusal_code);
                    Assert.That(payload.pointer_raycast_evidence, Is.EqualTo("event_system_raycast_resolves_to_handler"));
                    Assert.That(payload.delivered, Is.True);
                    Assert.That(_guarded.accepted, Is.EqualTo(1));
                    Assert.That(_guarded.rejected, Is.Zero);
                }
            }
            finally
            {
                if (callback != null)
                {
                    EditorApplication.delayCall -= callback;
                }
                if (events != null)
                {
                    Object.DestroyImmediate(events);
                }
                if (previousEvents != null && previousEvents.isActiveAndEnabled)
                {
                    EventSystem.current = previousEvents;
                }
                if (cameraRoot != null)
                {
                    Object.DestroyImmediate(cameraRoot);
                }
                selectedIndex.SetValue(view, previousIndex);
                display.SetValue(view, previousDisplay);
                setTransform.Invoke(zoomArea, new object[] { previousTranslation, previousScale });
                view.Repaint();
            }
        }

        [System.Serializable]
        private sealed class FixedPortraitReceipt
        {
            public string render_mode = "";
            public bool occlusion_control;
            public XUUnityLightMcpGameViewScreenshotPayload capture;
            public int capture_frame;
            public int callback_frame;
            public Vector2 zoom_before;
            public Vector2 zoom_after;
            public int selected_index_before;
            public int selected_index_after;
            public int target_display;
            public string callback_error = "";
            public XUUnityLightMcpUiClickPayload click;
        }
    }
}
