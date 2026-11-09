using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using Object = UnityEngine.Object;

namespace XUUnity.LightMcp.Tests.PlayModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.PlayMode")]
    [Category("XUUnity.MCP.UiInteraction")]
    public sealed class XUUnityLightMcpUiClickTreeWaitPlayModeTests
    {
        const int PopupDelayFrames = 5;
        const int MaxTestFrames = 600;

        GameObject _canvasRoot;
        GameObject _popup;
        XUUnityLightMcpDelayedPopupFixture _fixture;

        [SetUp]
        public void SetUp()
        {
            Assert.That(Application.isPlaying, Is.True, "a frame-delayed popup needs real PlayMode frames");
            XUUnityLightMcpUiClickTreeWatch.Clear();

            _canvasRoot = new GameObject(
                "XUUnityMcp_TreeWaitCanvas",
                typeof(RectTransform),
                typeof(Canvas),
                typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            var opener = new GameObject("OpenBannerButton", typeof(RectTransform), typeof(Image));
            opener.transform.SetParent(_canvasRoot.transform, false);
            opener.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            var button = opener.AddComponent<Button>();

            _popup = new GameObject("BannerPopup", typeof(RectTransform), typeof(Image));
            _popup.transform.SetParent(_canvasRoot.transform, false);
            _popup.GetComponent<RectTransform>().anchoredPosition = new Vector2(0f, 600f);
            _popup.GetComponent<RectTransform>().sizeDelta = new Vector2(600f, 400f);
            _popup.SetActive(false);

            _fixture = _canvasRoot.AddComponent<XUUnityLightMcpDelayedPopupFixture>();
            button.onClick.AddListener(() => _fixture.Begin(_popup, PopupDelayFrames));
        }

        [TearDown]
        public void TearDown()
        {
            XUUnityLightMcpUiClickTreeWatch.Clear();
            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
                _canvasRoot = null;
            }
        }

        [UnityTest]
        public IEnumerator ClickStep_WithWindow_PassesWhenThePopupAppearsFramesLater()
        {
            var state = new XUUnityLightMcpScenarioRunState();
            var step = NewStep(3000);
            var result = NewResult(step);

            var frames = 0;
            while (!XUUnityLightMcpScenarioStepDispatcher.ProcessStep(state, step, result))
            {
                Assert.That(result.status, Is.EqualTo("running"));
                Assert.That(result.outcome, Is.EqualTo("waiting_for_tree_change"));
                Assert.That(++frames, Is.LessThan(MaxTestFrames), "the deferred click never answered");
                yield return null;
                XUUnityLightMcpUiClickTreeWatch.Tick();
            }

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(result.outcome, Is.EqualTo("interaction_delivered"));
            Assert.That(_fixture.ClickFrame, Is.GreaterThan(0));
            Assert.That(_fixture.ShownFrame, Is.GreaterThanOrEqualTo(_fixture.ClickFrame + PopupDelayFrames));

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.delivered, Is.True);
            Assert.That(payload.ui_interaction.state_changed, Is.True);
            Assert.That(payload.ui_interaction.wait_for_tree_change_ms, Is.EqualTo(3000));
            Assert.That(payload.ui_interaction.tree_change_wait_status,
                Is.EqualTo(XUUnityLightMcpUiClickTreeWatch.ChangedAfterWait));
            Assert.That(payload.ui_interaction.tree_change_observed_after_frames,
                Is.GreaterThanOrEqualTo(PopupDelayFrames));
            Assert.That(payload.ui_interaction.before_signature, Is.Not.EqualTo(payload.ui_interaction.after_signature));
            Assert.That(state.pendingNestedRequestId, Is.Empty);
            Assert.That(XUUnityLightMcpUiClickTreeWatch.IsPending, Is.False);
        }

        [Test]
        public void ClickStep_WithoutWindow_FailsBecauseTheDeliveryFrameShowsNoChange()
        {
            var state = new XUUnityLightMcpScenarioRunState();
            var step = NewStep(0);
            var result = NewResult(step);

            Assert.That(XUUnityLightMcpScenarioStepDispatcher.ProcessStep(state, step, result), Is.True);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_interaction_no_state_change"));
            Assert.That(_fixture.ClickFrame, Is.GreaterThan(0), "the click was delivered");
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.tree_change_wait_status,
                Is.EqualTo(XUUnityLightMcpUiClickTreeWatch.WaitNotRequested));
            Assert.That(XUUnityLightMcpUiClickTreeWatch.IsPending, Is.False);
        }

        [UnityTest]
        public IEnumerator ClickStep_WithWindowTooShortForAnInertTarget_FailsAfterTheWindow()
        {
            var inert = new GameObject("InertButton", typeof(RectTransform), typeof(Image));
            inert.transform.SetParent(_canvasRoot.transform, false);
            inert.GetComponent<RectTransform>().anchoredPosition = new Vector2(0f, -600f);
            inert.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            inert.AddComponent<Button>();

            var state = new XUUnityLightMcpScenarioRunState();
            var step = NewStep(150);
            step.interactionId = "inert";
            step.selector = new XUUnityLightMcpUiSelectorArgs { name = "InertButton" };
            var result = NewResult(step);

            var frames = 0;
            while (!XUUnityLightMcpScenarioStepDispatcher.ProcessStep(state, step, result))
            {
                Assert.That(++frames, Is.LessThan(MaxTestFrames), "the deferred click never answered");
                yield return null;
                XUUnityLightMcpUiClickTreeWatch.Tick();
            }

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_interaction_no_state_change"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.tree_change_wait_status,
                Is.EqualTo(XUUnityLightMcpUiClickTreeWatch.UnchangedAfterWait));
            Assert.That(result.error_message, Does.Contain("did not change"));
        }

        static XUUnityLightMcpScenarioStepDefinition NewStep(int waitForTreeChangeMs)
        {
            return new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "open_banner",
                kind = XUUnityLightMcpUiRead.InteractionStepKind,
                interactionId = "open_banner",
                approve = true,
                expectStateChange = true,
                waitForTreeChangeMs = waitForTreeChangeMs,
                targetKind = XUUnityLightMcpUiRead.TargetGameObjectName,
                targetValue = "XUUnityMcp_TreeWaitCanvas",
                selector = new XUUnityLightMcpUiSelectorArgs { name = "OpenBannerButton" }
            };
        }

        static XUUnityLightMcpScenarioStepResult NewResult(XUUnityLightMcpScenarioStepDefinition step)
        {
            return new XUUnityLightMcpScenarioStepResult
            {
                stepId = step.stepId,
                kind = step.kind,
                status = "pending"
            };
        }
    }

    public sealed class XUUnityLightMcpDelayedPopupFixture : MonoBehaviour
    {
        public int ClickFrame { get; private set; }
        public int ShownFrame { get; private set; }

        public void Begin(GameObject popup, int frames)
        {
            ClickFrame = Time.frameCount;
            StartCoroutine(ShowAfterFrames(popup, frames));
        }

        IEnumerator ShowAfterFrames(GameObject popup, int frames)
        {
            for (var i = 0; i < frames; i++)
            {
                yield return null;
            }

            if (popup != null)
            {
                popup.SetActive(true);
                ShownFrame = Time.frameCount;
            }
        }
    }
}
