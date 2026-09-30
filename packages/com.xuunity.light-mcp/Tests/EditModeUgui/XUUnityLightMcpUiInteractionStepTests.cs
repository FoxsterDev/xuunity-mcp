using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Tests.EditModeUgui
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    [Category("XUUnity.MCP.UiInteraction")]
    public sealed class XUUnityLightMcpUiInteractionStepTests
    {
        GameObject _canvasRoot;
        int _clickCount;

        [SetUp]
        public void SetUp()
        {
            _clickCount = 0;
            _canvasRoot = new GameObject(
                "XUUnityMcp_StepCanvas",
                typeof(RectTransform),
                typeof(Canvas),
                typeof(GraphicRaycaster));
            _canvasRoot.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            _canvasRoot.GetComponent<RectTransform>().sizeDelta = new Vector2(1080f, 1920f);

            var child = new GameObject("CloseButton", typeof(RectTransform), typeof(Image));
            child.transform.SetParent(_canvasRoot.transform, false);
            child.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            var button = child.AddComponent<Button>();
            var label = new GameObject("Label", typeof(RectTransform), typeof(Text));
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
            }
        }

        [Test]
        public void Validator_RejectsAStepWithoutAnInteractionIdApprovalOrSelector()
        {
            var payload = Validate(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "close",
                kind = XUUnityLightMcpUiRead.InteractionStepKind
            });

            var codes = Codes(payload);
            Assert.That(codes, Contains.Item("missing_interaction_id"));
            Assert.That(codes, Contains.Item("ui_click_approval_required"));
            Assert.That(codes, Contains.Item("ui_selector_invalid"));
        }

        [Test]
        public void Validator_AcceptsAWellFormedStep()
        {
            var payload = Validate(NewStep());

            Assert.That(Codes(payload), Is.Empty, string.Join(",", Codes(payload)));
        }

        [TestCase(XUUnityLightMcpUiRead.ExistsStepKind)]
        [TestCase(XUUnityLightMcpUiRead.GetTextStepKind)]
        public void Validator_AcceptsUiReadStepsWithSelectors(string kind)
        {
            var payload = Validate(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "read",
                kind = kind,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "Label" }
            });

            Assert.That(Codes(payload), Is.Empty, string.Join(",", Codes(payload)));
        }

        [Test]
        public void Step_RefusesToDeliverWithoutApproval()
        {
            var step = NewStep();
            step.approve = false;
            var result = Run(step);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_click_approval_required"));
            Assert.That(_clickCount, Is.Zero);
        }

        [Test]
        public void Step_EmitsAnInteractionReceiptTheHostCanRead()
        {
            var result = Run(NewStep());

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(_clickCount, Is.EqualTo(1));

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.schema_version,
                Is.EqualTo(XUUnityLightMcpUiRead.InteractionSchemaVersion));
            Assert.That(payload.ui_interaction.interaction_id, Is.EqualTo("close_button"));
            Assert.That(payload.ui_interaction.delivered, Is.True);
            Assert.That(payload.ui_interaction.effective, Is.True);
            Assert.That(payload.ui_interaction.no_observable_effect, Is.False);
            Assert.That(payload.ui_interaction.state_changed, Is.True, "the label text changed, so the tree signature must differ");
            Assert.That(payload.ui_interaction.delivery_mechanism, Is.EqualTo("event_system_pointer_click_handler"));
            Assert.That(payload.ui_interaction.before_signature, Is.Not.EqualTo(payload.ui_interaction.after_signature));
            Assert.That(payload.met_expectations, Is.True);
        }

        [Test]
        public void Step_ReportsEditModeSoTheHostCanRefuseToCallItRuntimeProof()
        {
            var result = Run(NewStep());
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);

            Assert.That(payload.ui_interaction.playmode_state, Is.EqualTo("edit"),
                "an Edit-mode delivery must say so; the host blocks the interaction lane on it");
        }

        [Test]
        public void Step_FailsWhenAnExpectedStateChangeDoesNotHappen()
        {
            var inert = new GameObject("InertButton", typeof(RectTransform), typeof(Image));
            inert.transform.SetParent(_canvasRoot.transform, false);
            inert.GetComponent<RectTransform>().sizeDelta = new Vector2(300f, 120f);
            inert.AddComponent<Button>();

            var step = NewStep();
            step.interactionId = "inert";
            step.selector = new XUUnityLightMcpUiSelectorArgs { name = "InertButton" };
            var result = Run(step);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_interaction_no_state_change"));

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.delivered, Is.True);
            Assert.That(payload.ui_interaction.effective, Is.False);
            Assert.That(payload.ui_interaction.no_observable_effect, Is.True);
            Assert.That(payload.ui_interaction.state_changed, Is.False);
        }

        [Test]
        public void Step_CarriesTheRefusalCodeThroughWhenTheClickIsRefused()
        {
            var step = NewStep();
            step.interactionId = "missing";
            step.selector = new XUUnityLightMcpUiSelectorArgs { name = "NoSuchButton" };
            var result = Run(step);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_node_not_found"));

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.refusal_code, Is.EqualTo("ui_node_not_found"));
            Assert.That(payload.ui_interaction.delivered, Is.False);
            Assert.That(_clickCount, Is.Zero);
        }

        [Test]
        public void Step_PreservesTheInconclusiveSearchEvidenceAndRetryBudget()
        {
            var step = NewStep();
            step.maxNodes = 1;
            var result = Run(step);

            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("ui_selector_search_truncated"));

            var payload = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.payload_json);
            Assert.That(payload.ui_interaction.refusal_code, Is.EqualTo("ui_selector_search_truncated"));
            Assert.That(payload.ui_interaction.search_truncated, Is.True);
            Assert.That(payload.ui_interaction.search_node_count, Is.EqualTo(1));
            Assert.That(payload.ui_interaction.search_max_nodes, Is.EqualTo(1));
            Assert.That(payload.ui_interaction.search_truncation_reason, Is.EqualTo("max_nodes_reached"));
            Assert.That(payload.ui_interaction.search_target.searched_scenes, Is.Not.Empty);
            Assert.That(_clickCount, Is.Zero);
        }

        [Test]
        public void UiExistsStep_AssertsPresenceAndCarriesSearchAndLivenessEvidence()
        {
            var result = Run(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "label-exists",
                kind = XUUnityLightMcpUiRead.ExistsStepKind,
                expectedExists = true,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "Label" }
            });

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(result.playmode_state, Is.EqualTo("edit"));
            Assert.That(result.playmode_loop_liveness, Is.EqualTo("not_playing"));
            Assert.That(result.result_trust_class, Is.EqualTo("editor_truth_confirmed"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiReadStepPayload>(result.payload_json);
            Assert.That(payload.operation, Is.EqualTo("unity.ui.exists"));
            Assert.That(payload.met_expectations, Is.True);
            Assert.That(payload.query.exists, Is.True);
            Assert.That(payload.query.match_count, Is.EqualTo(1));
            Assert.That(payload.query.playmode_loop_liveness, Is.EqualTo("not_playing"));
        }

        [Test]
        public void UiExistsStep_ConfirmsAbsenceOnlyAfterACompleteSearch()
        {
            var result = Run(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "missing-is-absent",
                kind = XUUnityLightMcpUiRead.ExistsStepKind,
                expectedExists = false,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "MissingLabel" }
            });

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(result.outcome, Is.EqualTo("ui_absence_confirmed"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiReadStepPayload>(result.payload_json);
            Assert.That(payload.query.exists, Is.False);
            Assert.That(payload.query.truncated, Is.False);
            Assert.That(payload.query.out_of_scope, Is.False);
        }

        [Test]
        public void UiGetTextStep_CapturesAndAssertsSemanticText()
        {
            var result = Run(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "read-label",
                kind = XUUnityLightMcpUiRead.GetTextStepKind,
                expectedText = "Close",
                selector = new XUUnityLightMcpUiSelectorArgs { name = "Label" }
            });

            Assert.That(result.status, Is.EqualTo("passed"), result.error_message);
            Assert.That(result.outcome, Is.EqualTo("ui_text_captured"));
            var payload = JsonUtility.FromJson<XUUnityLightMcpUiReadStepPayload>(result.payload_json);
            Assert.That(payload.operation, Is.EqualTo("unity.ui.get_text"));
            Assert.That(payload.expected_text, Is.EqualTo("Close"));
            Assert.That(payload.query.has_text, Is.True);
            Assert.That(payload.query.text, Is.EqualTo("Close"));
        }

        static XUUnityLightMcpScenarioStepDefinition NewStep()
        {
            return new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "close",
                kind = XUUnityLightMcpUiRead.InteractionStepKind,
                interactionId = "close_button",
                approve = true,
                expectStateChange = true,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "CloseButton" }
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
                XUUnityLightMcpScenarioStepDispatcher.ProcessStep(new XUUnityLightMcpScenarioRunState(), step, result),
                Is.True);
            return result;
        }

        static XUUnityLightMcpScenarioValidatePayload Validate(XUUnityLightMcpScenarioStepDefinition step)
        {
            return XUUnityLightMcpScenarioValidator.Validate(new XUUnityLightMcpScenarioDefinition
            {
                name = "ui-click-selftest",
                steps = new List<XUUnityLightMcpScenarioStepDefinition> { step }
            });
        }

        static List<string> Codes(XUUnityLightMcpScenarioValidatePayload payload)
        {
            var codes = new List<string>();
            foreach (var issue in payload.issues)
            {
                if (issue.severity == "error")
                {
                    codes.Add(issue.code);
                }
            }

            return codes;
        }
    }
}
