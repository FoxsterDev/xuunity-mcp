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
    }
}
