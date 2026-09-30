using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.PlayModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.PlayMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.UiInteraction")]
    public sealed class XUUnityLightMcpUiInteractionPlayModeTests
    {
        GameObject _canvasRoot;
        int _clickCount;

        [SetUp]
        public void SetUp()
        {
            Assert.That(Application.isPlaying, Is.True,
                "runtime interaction proof must execute in a real PlayMode test");

            _clickCount = 0;
            _canvasRoot = new GameObject(
                "XUUnityMcp_PlayModeStepCanvas",
                typeof(RectTransform),
                typeof(Canvas),
                typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            var child = new GameObject("RuntimeCloseButton", typeof(RectTransform), typeof(Image));
            child.transform.SetParent(_canvasRoot.transform, false);
            child.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            var button = child.AddComponent<Button>();
            var label = new GameObject("RuntimeLabel", typeof(RectTransform), typeof(Text));
            label.transform.SetParent(child.transform, false);
            label.GetComponent<Text>().text = "Close";
            button.onClick.AddListener(() =>
            {
                _clickCount++;
                label.GetComponent<Text>().text = "Closed";
            });
        }

        [TearDown]
        public void TearDown()
        {
            if (_canvasRoot != null)
            {
                Object.DestroyImmediate(_canvasRoot);
                _canvasRoot = null;
            }
        }

        [Test]
        public void ScenarioStep_DeliversRuntimeClickAndEmitsDecisionBearingReceipt()
        {
            var result = Run(NewStep());

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(result.outcome, Is.EqualTo("interaction_delivered"));
            Assert.That(_clickCount, Is.EqualTo(1), "a guarded click must be delivered exactly once");

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.met_expectations, Is.True);
            Assert.That(payload.ui_interaction.schema_version,
                Is.EqualTo(XUUnityLightMcpUiRead.InteractionSchemaVersion));
            Assert.That(payload.ui_interaction.interaction_id, Is.EqualTo("runtime_close_button"));
            Assert.That(payload.ui_interaction.delivered, Is.True);
            Assert.That(payload.ui_interaction.state_changed, Is.True);
            Assert.That(payload.ui_interaction.playmode_state, Is.EqualTo("playing"),
                "only a PlayMode receipt can prove the runtime user path");
            Assert.That(payload.ui_interaction.delivery_mechanism,
                Is.EqualTo("event_system_pointer_click_handler"));
            Assert.That(payload.ui_interaction.before_signature, Is.Not.Empty);
            Assert.That(payload.ui_interaction.after_signature, Is.Not.Empty);
            Assert.That(payload.ui_interaction.before_signature,
                Is.Not.EqualTo(payload.ui_interaction.after_signature));
        }

        [Test]
        public void ScenarioStep_RefusalCannotBeMisreadAsRuntimeDelivery()
        {
            var step = NewStep();
            step.approve = false;

            var result = Run(step);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_click_approval_required"));
            Assert.That(result.payload_json, Is.Empty,
                "a refusal before the nested operation must not mint an interaction receipt");
            Assert.That(_clickCount, Is.Zero);
        }

        static XUUnityLightMcpScenarioStepDefinition NewStep()
        {
            return new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "runtime_close",
                kind = XUUnityLightMcpUiRead.InteractionStepKind,
                interactionId = "runtime_close_button",
                approve = true,
                expectStateChange = true,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "RuntimeCloseButton" }
            };
        }

        static XUUnityLightMcpScenarioStepResult Run(XUUnityLightMcpScenarioStepDefinition step)
        {
            var result = new XUUnityLightMcpScenarioStepResult
            {
                stepId = step.stepId,
                kind = step.kind
            };
            Assert.That(
                XUUnityLightMcpScenarioStepDispatcher.ProcessStep(
                    new XUUnityLightMcpScenarioRunState(),
                    step,
                    result),
                Is.True);
            return result;
        }
    }
}
