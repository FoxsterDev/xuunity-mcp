using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.ScenarioHooks;
using Object = UnityEngine.Object;

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
        string _queuedRunId = "";

        [SetUp]
        public void SetUp()
        {
            Assert.That(Application.isPlaying, Is.True,
                "runtime interaction proof must execute in a real PlayMode test");

            _clickCount = 0;
            _queuedRunId = "";
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
            if (!string.IsNullOrEmpty(_queuedRunId)
                && XUUnityLightMcpScenarioRunRepository.TryLoadState(out var state)
                && state != null
                && state.runId == _queuedRunId)
            {
                XUUnityLightMcpScenarioScheduler.CompleteRun(state, "failed");
            }

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

        [UnityTest]
        public IEnumerator Scenario_DelayedCloseWaitsForDisappearanceAfterOneDeliveredClick()
        {
            var button = _canvasRoot.transform.Find("RuntimeCloseButton").GetComponent<Button>();
            var delayedClose = _canvasRoot.AddComponent<XUUnityLightMcpTwoFrameCloseFixture>();
            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(() =>
            {
                _clickCount++;
                delayedClose.Begin(button.gameObject);
            });

            var queued = QueueDisappearanceScenario("delayed_close", 5.0d);
            yield return WaitForTerminalResult(queued.run_id);
            var result = ReadResult(queued.run_id);

            Assert.That(result.status, Is.EqualTo("passed"), JsonUtility.ToJson(result));
            Assert.That(result.steps[0].status, Is.EqualTo("passed"));
            var delivery = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.steps[0].payload_json);
            Assert.That(delivery.ui_interaction.delivered, Is.True);
            Assert.That(delivery.ui_interaction.state_changed, Is.False,
                "delivery must not require the asynchronous transition to happen immediately");
            Assert.That(delayedClose.HiddenFrame, Is.GreaterThanOrEqualTo(delayedClose.ClickFrame + 2));
            Assert.That(delayedClose.ClickedAtUtc, Is.Not.Empty);
            Assert.That(delayedClose.HiddenAtUtc, Is.Not.Empty);
            Assert.That(result.steps[1].status, Is.EqualTo("passed"));
            Assert.That(result.steps[1].poll_count, Is.GreaterThan(0));
            Assert.That(result.steps[1].payload_json, Does.Contain("\"target_exists\":false"));
            Assert.That(result.steps[1].payload_json, Does.Contain("\"observed_at_utc\":"));
            Assert.That(result.steps[2].status, Is.EqualTo("passed"));
            Assert.That(result.steps[2].outcome, Is.EqualTo("ui_absence_confirmed"));
            Assert.That(_clickCount, Is.EqualTo(1));
            Assert.That(result.started_at_utc, Is.Not.Empty);
            Assert.That(result.completed_at_utc, Is.Not.Empty);
            TestContext.WriteLine($"run_id={result.run_id}; result_path={result.result_path}; "
                + $"clicked_at_utc={delayedClose.ClickedAtUtc}; hidden_at_utc={delayedClose.HiddenAtUtc}; "
                + $"click_frame={delayedClose.ClickFrame}; hidden_frame={delayedClose.HiddenFrame}");
        }

        [UnityTest]
        public IEnumerator Scenario_NoOpCloseTimesOutAndRetainsItsFailedResultWithoutReclicking()
        {
            var button = _canvasRoot.transform.Find("RuntimeCloseButton").GetComponent<Button>();
            var clickedAtUtc = "";
            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(() =>
            {
                _clickCount++;
                clickedAtUtc = DateTime.UtcNow.ToString("O");
            });

            var queued = QueueDisappearanceScenario("noop_close", 2.0d);
            yield return WaitForTerminalResult(queued.run_id);
            var result = ReadResult(queued.run_id);

            Assert.That(result.status, Is.EqualTo("failed"), JsonUtility.ToJson(result));
            Assert.That(result.terminal, Is.True);
            Assert.That(result.succeeded, Is.False);
            Assert.That(result.steps[0].status, Is.EqualTo("passed"));
            var delivery = JsonUtility.FromJson<XUUnityLightMcpUiInteractionStepPayload>(result.steps[0].payload_json);
            Assert.That(delivery.ui_interaction.delivered, Is.True);
            Assert.That(delivery.ui_interaction.state_changed, Is.False);
            Assert.That(result.steps[1].status, Is.EqualTo("failed"));
            Assert.That(result.steps[1].terminal_status, Is.EqualTo("timeout"));
            Assert.That(result.steps[1].error_code, Is.EqualTo("project_hook_poll_until_timeout"));
            Assert.That(result.steps[1].poll_count, Is.GreaterThan(0));
            Assert.That(result.steps[1].payload_json, Does.Contain("\"target_exists\":true"));
            Assert.That(result.steps[1].payload_json, Does.Contain("\"observed_at_utc\":"));
            Assert.That(_clickCount, Is.EqualTo(1));
            Assert.That(clickedAtUtc, Is.Not.Empty);
            Assert.That(result.started_at_utc, Is.Not.Empty);
            Assert.That(result.completed_at_utc, Is.Not.Empty);

            var laterObservation = Run(new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "later_presence",
                kind = "ui_exists",
                targetKind = XUUnityLightMcpUiRead.TargetGameObjectName,
                targetValue = _canvasRoot.name,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "RuntimeCloseButton" },
                expectedExists = true,
            });
            Assert.That(laterObservation.status, Is.EqualTo("passed"));
            var retained = ReadResult(queued.run_id);
            Assert.That(retained.status, Is.EqualTo("failed"));
            Assert.That(retained.completed_at_utc, Is.EqualTo(result.completed_at_utc));
            Assert.That(retained.steps[1].error_code, Is.EqualTo("project_hook_poll_until_timeout"));
            Assert.That(_clickCount, Is.EqualTo(1));
            TestContext.WriteLine($"run_id={retained.run_id}; result_path={retained.result_path}; "
                + $"clicked_at_utc={clickedAtUtc}; completed_at_utc={retained.completed_at_utc}; "
                + $"last_poll={retained.steps[1].payload_json}");
        }

        private XUUnityLightMcpScenarioRunPayload QueueDisappearanceScenario(string name, double timeoutSeconds)
        {
            Assert.That(XUUnityLightMcpScenarioRunner.HasActiveRun(), Is.False,
                "the fixture must not replace another scenario's active state");
            _canvasRoot.name += "_" + Guid.NewGuid().ToString("N");
            var click = NewStep();
            click.expectStateChange = false;
            click.targetKind = XUUnityLightMcpUiRead.TargetGameObjectName;
            click.targetValue = _canvasRoot.name;
            var queryJson = JsonUtility.ToJson(new XUUnityLightMcpUiQueryArgs
            {
                targetKind = XUUnityLightMcpUiRead.TargetGameObjectName,
                targetValue = _canvasRoot.name,
                selector = new XUUnityLightMcpUiSelectorArgs { name = "RuntimeCloseButton" },
            });
            var queued = XUUnityLightMcpScenarioRunner.QueueRun(new XUUnityLightMcpScenarioDefinition
            {
                name = "selftest_" + name,
                stopOnFirstFailure = true,
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    click,
                    new()
                    {
                        stepId = "wait_for_disappearance",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpFixtureDisappearancePollHook.Name,
                        startPayloadJson = queryJson,
                        pollPayloadJson = queryJson,
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'failed'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = timeoutSeconds,
                    },
                    new()
                    {
                        stepId = "assert_disappearance",
                        kind = "ui_exists",
                        targetKind = XUUnityLightMcpUiRead.TargetGameObjectName,
                        targetValue = _canvasRoot.name,
                        selector = new XUUnityLightMcpUiSelectorArgs { name = "RuntimeCloseButton" },
                        expectedExists = false,
                    },
                },
            });
            _queuedRunId = queued.run_id;
            return queued;
        }

        private static IEnumerator WaitForTerminalResult(string runId)
        {
            var deadline = Time.realtimeSinceStartup + 10.0f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (ReadResult(runId).terminal)
                {
                    yield break;
                }

                yield return new WaitForSecondsRealtime(0.1f);
            }

            Assert.Fail("The bridge-owned scenario ticks did not produce a terminal result within 10 seconds.");
        }

        private static XUUnityLightMcpScenarioRunPayload ReadResult(string runId)
        {
            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(runId, "", out var payload,
                out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            return payload;
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

    public sealed class XUUnityLightMcpTwoFrameCloseFixture : MonoBehaviour
    {
        public int ClickFrame { get; private set; }
        public int HiddenFrame { get; private set; }
        public string ClickedAtUtc { get; private set; } = "";
        public string HiddenAtUtc { get; private set; } = "";

        public void Begin(GameObject target)
        {
            ClickFrame = Time.frameCount;
            ClickedAtUtc = DateTime.UtcNow.ToString("O");
            StartCoroutine(HideAfterTwoFrames(target));
        }

        private IEnumerator HideAfterTwoFrames(GameObject target)
        {
            yield return null;
            yield return null;
            if (target != null)
            {
                target.SetActive(false);
                HiddenFrame = Time.frameCount;
                HiddenAtUtc = DateTime.UtcNow.ToString("O");
            }
        }
    }

    public sealed class XUUnityLightMcpFixtureDisappearancePollHook : IXUUnityLightMcpScenarioHook
    {
        public const string Name = "xuunity.selftest.pd10.fixture_disappearance";
        public string HookName => Name;

        [Serializable]
        private sealed class PollEvidence
        {
            public string status = "failed";
            public bool target_exists;
            public string observed_at_utc = "";
            public int observed_frame;
        }

        public XUUnityLightMcpScenarioHookResult Execute(string payloadJson)
        {
            var args = JsonUtility.FromJson<XUUnityLightMcpUiQueryArgs>(payloadJson);
            if (args == null || args.targetKind != XUUnityLightMcpUiRead.TargetGameObjectName
                || !args.targetValue.StartsWith("XUUnityMcp_PlayModeStepCanvas_", StringComparison.Ordinal)
                || args.selector == null || args.selector.name != "RuntimeCloseButton")
            {
                return new XUUnityLightMcpScenarioHookResult
                {
                    success = false,
                    error_code = "fixture_scope_required",
                    error_message = "This self-test hook only queries the uniquely named test-created fixture root.",
                };
            }

            var response = XUUnityLightMcpNestedOperationClient.ExecuteNestedOperation("unity.ui.exists", payloadJson);
            var query = response != null && response.status == "ok"
                ? JsonUtility.FromJson<XUUnityLightMcpUiQueryPayload>(response.payload_json)
                : null;
            var complete = query != null && query.success && !query.truncated && !query.out_of_scope && !query.ambiguous;
            var evidence = new PollEvidence
            {
                status = !complete ? "failed" : query.exists ? "running" : "passed",
                target_exists = query != null && query.exists,
                observed_at_utc = DateTime.UtcNow.ToString("O"),
                observed_frame = Time.frameCount,
            };
            return new XUUnityLightMcpScenarioHookResult
            {
                success = complete,
                payload_json = JsonUtility.ToJson(evidence),
                error_code = complete ? "" : "fixture_ui_query_incomplete",
                error_message = complete ? "" : "The fixture existence query did not prove a complete in-scope result.",
            };
        }
    }
}
