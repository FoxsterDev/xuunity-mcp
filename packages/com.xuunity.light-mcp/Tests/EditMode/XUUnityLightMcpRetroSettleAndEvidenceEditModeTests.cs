using System;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpRetroSettleAndEvidenceEditModeTests
    {
        [Test]
        public void ScenarioValidator_AcceptsStatusThenCompileAfterProfileMutationWithoutAWait()
        {
            var validation = XUUnityLightMcpScenarioRunner.Validate(ProfileScenario(
                new XUUnityLightMcpScenarioStepDefinition { stepId = "status", kind = "status" },
                new XUUnityLightMcpScenarioStepDefinition { stepId = "compile", kind = "compile_player_scripts", target = "Android" }));

            Assert.That(validation.status, Is.EqualTo("valid"), string.Join("\n", validation.issues.ConvertAll(issue => issue.message)));
        }

        [Test]
        public void ScenarioValidator_StillRequiresTheStatusStepBeforeTheGatedCompile()
        {
            var validation = XUUnityLightMcpScenarioRunner.Validate(ProfileScenario(
                new XUUnityLightMcpScenarioStepDefinition { stepId = "compile", kind = "compile_player_scripts", target = "Android" }));

            Assert.That(validation.status, Is.EqualTo("invalid"));
            Assert.That(validation.issues.Exists(issue => issue.code == "apply_then_gate_sequence_required"), Is.True);
        }

        [Test]
        public void ScenarioValidator_RejectsAConsoleGrepAnchorTheBufferCannotResolve()
        {
            var unsupported = XUUnityLightMcpScenarioRunner.Validate(ConsoleGrepScenario("bridge_generation"));
            var supported = XUUnityLightMcpScenarioRunner.Validate(ConsoleGrepScenario("playmode_start"));

            Assert.That(unsupported.issues.Exists(issue => issue.code == "invalid_since"), Is.True);
            Assert.That(supported.status, Is.EqualTo("valid"), string.Join("\n", supported.issues.ConvertAll(issue => issue.message)));
        }

        [Test]
        public void CompileStep_GateTimesOutWithoutDispatchingWhileTheEditorWasSeenBusy()
        {
            var state = new XUUnityLightMcpScenarioRunState
            {
                runId = "gate-timeout",
                waitingUntilUtc = "2000-01-01T00:00:00Z",
                pendingNestedDispatchGateStartedAtUtc = "2000-01-01T00:00:00Z",
                pendingNestedDispatchGateBusyObserved = true,
            };
            var step = new XUUnityLightMcpScenarioStepDefinition
            {
                stepId = "compile",
                kind = "compile_player_scripts",
                target = "Android",
                timeoutSeconds = 1.0d,
            };
            var result = new XUUnityLightMcpScenarioStepResult
            {
                stepId = "compile",
                kind = "compile_player_scripts",
                status = "running",
                outcome = XUUnityLightMcpScenarioCompileTestStepHandlers.CompileDispatchGateOutcome,
            };

            var advanced = XUUnityLightMcpScenarioCompileTestStepHandlers.ProcessCompilePlayerScriptsStep(state, step, result);

            Assert.That(advanced, Is.True);
            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("compile_dispatch_gate_timeout"));
            Assert.That(result.error_message, Does.Contain("isCompiling="));
            Assert.That(result.payload_json, Is.Empty, "nothing was dispatched, so there is no compile payload");
            Assert.That(state.pendingNestedDispatchGateBusyObserved, Is.False, "the gate state is cleared with the pending operation");
            Assert.That(state.pendingNestedRequestId, Is.Empty);
        }

        [Test]
        public void ConsoleGrep_SincePlayModeStartBoundsTheBufferToTheAnchor()
        {
            XUUnityLightMcpConsoleBuffer.EnsureStarted();
            var before = $"XUUNITY_SINCE_PROBE_BEFORE_{Guid.NewGuid():N}";
            var after = $"XUUNITY_SINCE_PROBE_AFTER_{Guid.NewGuid():N}";
            Debug.Log(before);
            XUUnityLightMcpConsoleBuffer.CapturePlayModeStartAnchor();
            Debug.Log(after);

            var anchored = Grep("XUUNITY_SINCE_PROBE_", "playmode_start");
            Assert.That(anchored.status, Is.EqualTo("ok"), anchored.error?.message);
            var payload = JsonUtility.FromJson<XUUnityLightMcpConsoleGrepPayload>(anchored.payload_json);
            Assert.That(payload.since_anchor_resolved, Is.True);
            Assert.That(payload.since_anchor_reason, Is.EqualTo("console_buffer_since_anchor"));
            Assert.That(payload.since_scope_complete, Is.True);
            Assert.That(payload.match_count, Is.EqualTo(1));
            Assert.That(payload.items[0].message, Is.EqualTo(after));
            Assert.That(payload.search_verdict, Is.EqualTo("matched"));

            var absent = JsonUtility.FromJson<XUUnityLightMcpConsoleGrepPayload>(Grep("XUUNITY_SINCE_NEVER_LOGGED", "playmode_start").payload_json);
            Assert.That(absent.match_count, Is.EqualTo(0));
            Assert.That(absent.search_verdict, Is.EqualTo("not_matched"));
            Assert.That(absent.search_verdict_reason, Is.EqualTo("complete_console_scope_since_anchor_searched"));

            var unanchored = JsonUtility.FromJson<XUUnityLightMcpConsoleGrepPayload>(Grep("XUUNITY_SINCE_PROBE_", "").payload_json);
            Assert.That(unanchored.match_count, Is.GreaterThanOrEqualTo(2));
            Assert.That(unanchored.since_anchor_resolved, Is.False);
            Assert.That(unanchored.search_verdict, Is.EqualTo("matched"));

            var unsupported = Grep("XUUNITY_SINCE_PROBE_", "bridge_generation");
            Assert.That(unsupported.status, Is.EqualTo("error"));
            Assert.That(unsupported.error.code, Is.EqualTo("unsupported_console_anchor"));
        }

        static XUUnityLightMcpScenarioDefinition ProfileScenario(params XUUnityLightMcpScenarioStepDefinition[] gateSteps)
        {
            var steps = new List<XUUnityLightMcpScenarioStepDefinition>
            {
                new()
                {
                    stepId = "apply_profile",
                    kind = "project_defined_hook",
                    hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                    mutationSettlePolicy = "apply_then_gate",
                },
            };
            steps.AddRange(gateSteps);
            return new XUUnityLightMcpScenarioDefinition { name = "profile_gate", steps = steps };
        }

        static XUUnityLightMcpScenarioDefinition ConsoleGrepScenario(string since)
        {
            return new XUUnityLightMcpScenarioDefinition
            {
                name = "console_grep_since",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new() { stepId = "grep", kind = "console_grep", pattern = "marker", since = since },
                },
            };
        }

        static XUUnityLightMcpResponse Grep(string pattern, string since)
        {
            var args = new XUUnityLightMcpConsoleGrepArgs { pattern = pattern, since = since, limit = 20 };
            return new XUUnityLightMcpConsoleGrepOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = $"grep-{Guid.NewGuid():N}",
                operation = "unity.console.grep",
                args_json = JsonUtility.ToJson(args),
            });
        }
    }
}
