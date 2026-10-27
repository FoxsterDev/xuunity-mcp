using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;
using XUUnity.LightMcp.Editor.ScenarioHooks;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpRetroSettleAndEvidenceEditModeTests
    {
        const string GENERATED_ROOT = "Assets/XUUnityLightMcpGenerated";
        const string PROBE_ASSET_PATH = GENERATED_ROOT + "/XUUnityLightMcpAssetSnapshotProbe.asset";

        [TearDown]
        public void TearDown()
        {
            if (AssetDatabase.LoadMainAssetAtPath(PROBE_ASSET_PATH) != null)
            {
                AssetDatabase.DeleteAsset(PROBE_ASSET_PATH);
            }

            if (AssetDatabase.IsValidFolder(GENERATED_ROOT)
                && AssetDatabase.FindAssets("", new[] { GENERATED_ROOT }).Length == 0)
            {
                AssetDatabase.DeleteAsset(GENERATED_ROOT);
            }
        }

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

        [TestCase("refresh-1", "refresh-1", false, "settled", false, false, true, true)]
        [TestCase("refresh-1", "", false, "settled", false, false, true, false)]
        [TestCase("refresh-1", "", false, "", false, false, true, false)]
        [TestCase("refresh-1", "refresh-2", false, "settled", false, false, true, false)]
        [TestCase("", "", false, "settled", false, false, true, false)]
        [TestCase("", "refresh-1", false, "settled", false, false, true, false)]
        [TestCase("refresh-1", "refresh-1", true, "settled", false, false, true, false)]
        [TestCase("refresh-1", "refresh-1", false, "waiting_for_stable_idle_ticks", false, false, true, false)]
        [TestCase("refresh-1", "refresh-1", false, "settled", true, false, true, false)]
        [TestCase("refresh-1", "refresh-1", false, "settled", false, true, true, false)]
        [TestCase("refresh-1", "refresh-1", false, "settled", false, false, false, false)]
        public void RefreshCompletion_RequiresThePersistedRequestAndSettledIdleRuntime(
            string expectedRequestId, string observedRequestId, bool settlePending, string settlePhase,
            bool isCompiling, bool isUpdating, bool playModeStable, bool expected)
        {
            var persisted = JsonUtility.FromJson<XUUnityLightMcpScenarioRunState>(
                JsonUtility.ToJson(new XUUnityLightMcpScenarioRunState { pendingNestedRequestId = expectedRequestId }));

            Assert.That(XUUnityLightMcpScenarioRefreshStepHandler.IsRefreshRequestSettled(
                persisted.pendingNestedRequestId, observedRequestId, settlePending, settlePhase,
                isCompiling, isUpdating, playModeStable), Is.EqualTo(expected));
        }

        [TestCase("", "missing_runtime_request_id")]
        [TestCase("refresh-2", "request_id_mismatch")]
        [TestCase("refresh-1", "matching_request_not_confirmed_settled")]
        public void RefreshTimeout_PreservesExpectedAndObservedIdentityWithoutClaimingCompletion(
            string observedRequestId, string reason)
        {
            var existing = JsonUtility.ToJson(new XUUnityLightMcpProjectRefreshPayload
            {
                settle_request_id = "refresh-1",
                asset_database_refreshed = true,
            });
            var json = XUUnityLightMcpScenarioRefreshStepHandler.BuildRefreshTimeoutPayloadJson(
                existing, false, false, false, "settled", "edit", 1, observedRequestId, "refresh-1");
            var payload = JsonUtility.FromJson<XUUnityLightMcpProjectRefreshTimeoutPayload>(json);

            Assert.That(payload.expected_settle_request_id, Is.EqualTo("refresh-1"));
            Assert.That(payload.observed_settle_request_id, Is.EqualTo(observedRequestId));
            Assert.That(payload.settle_request_id, Is.EqualTo("refresh-1"));
            Assert.That(payload.asset_database_refreshed, Is.True);
            Assert.That(payload.settled_completion, Is.EqualTo("unproven"));
            Assert.That(payload.settled_completion_reason, Is.EqualTo(reason));
            Assert.That(payload.settle_timeout_classification, Is.EqualTo("lost_final_accounting"));
        }

        [Test]
        public void RefreshTiming_PersistsPreciseStartAndMeasuresExecutionSeparatelyFromSettleWait()
        {
            var state = new XUUnityLightMcpScenarioRunState
            {
                pendingNestedStartedAtUtc = "2026-10-26T12:00:00.1250000Z",
                steps = new List<XUUnityLightMcpScenarioStepResult>
                {
                    new() { execution_duration_seconds = 0.125d, timing_measured = true },
                },
            };
            state = JsonUtility.FromJson<XUUnityLightMcpScenarioRunState>(JsonUtility.ToJson(state));
            var step = state.steps[0];
            var now = new DateTime(2026, 10, 26, 12, 0, 2, DateTimeKind.Utc).AddMilliseconds(375);

            Assert.That(XUUnityLightMcpScenarioRefreshStepHandler.TryCalculateProjectRefreshTiming(
                state.pendingNestedStartedAtUtc, now, step.execution_duration_seconds,
                out var totalSeconds, out var settleSeconds), Is.True);
            step.duration_seconds = totalSeconds;
            step.settle_wait_duration_seconds = settleSeconds;
            step = JsonUtility.FromJson<XUUnityLightMcpScenarioStepResult>(JsonUtility.ToJson(step));

            Assert.That(step.timing_measured, Is.True);
            Assert.That(step.duration_seconds, Is.EqualTo(2.25d));
            Assert.That(step.execution_duration_seconds, Is.EqualTo(0.125d));
            Assert.That(step.settle_wait_duration_seconds, Is.EqualTo(2.125d));
        }

        [TestCase(null)]
        [TestCase("")]
        [TestCase("not-a-timestamp")]
        [TestCase("2026-10-26T12:00:00Z")]
        [TestCase("2026-10-27T12:00:00.0000000Z")]
        public void RefreshTiming_InvalidOrImpreciseStartIsUnmeasured(string startedAtUtc)
        {
            Assert.That(XUUnityLightMcpScenarioRefreshStepHandler.TryCalculateProjectRefreshTiming(
                startedAtUtc, new DateTime(2026, 10, 26, 12, 0, 1, DateTimeKind.Utc), 0.1d,
                out _, out _), Is.False);
        }

        [Test]
        public void RefreshTiming_IsUnmeasuredWhenExecutionExceedsWallTime()
        {
            Assert.That(XUUnityLightMcpScenarioRefreshStepHandler.TryCalculateProjectRefreshTiming(
                "2026-10-26T12:00:00.0000000Z", new DateTime(2026, 10, 26, 12, 0, 1, DateTimeKind.Utc), 1.01d,
                out var totalSeconds, out var settleSeconds), Is.False);
            Assert.That(totalSeconds, Is.Zero);
            Assert.That(settleSeconds, Is.Zero);
        }

        [Test]
        public void RefreshStep_MissingPersistedStartDoesNotReportMeasuredTimingAtTimeout()
        {
            var state = new XUUnityLightMcpScenarioRunState
            {
                pendingNestedRequestId = "refresh-missing-start",
                waitingUntilUtc = "2000-01-01T00:00:00Z",
            };
            var result = new XUUnityLightMcpScenarioStepResult
            {
                status = "running",
                execution_duration_seconds = 0.25d,
                duration_seconds = 3.0d,
                settle_wait_duration_seconds = 2.75d,
                timing_measured = true,
            };

            Assert.That(XUUnityLightMcpScenarioRefreshStepHandler.ProcessProjectRefreshStep(
                state, new XUUnityLightMcpScenarioStepDefinition(), result), Is.True);
            Assert.That(result.status, Is.EqualTo("failed"));
            Assert.That(result.error_code, Is.EqualTo("project_refresh_timeout"));
            Assert.That(result.timing_measured, Is.False);
            Assert.That(result.duration_seconds, Is.Zero);
            Assert.That(result.settle_wait_duration_seconds, Is.Zero);
            Assert.That(state.pendingNestedRequestId, Is.Empty);
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

        [Test]
        public void AssetSnapshot_ReadsSerializedFieldsOfAScriptableObjectWithoutPlayMode()
        {
            if (!AssetDatabase.IsValidFolder(GENERATED_ROOT))
            {
                AssetDatabase.CreateFolder("Assets", "XUUnityLightMcpGenerated");
            }

            AssetDatabase.CreateAsset(ScriptableObject.CreateInstance<XUUnityLightMcpAssetSnapshotProbeAsset>(), PROBE_ASSET_PATH);
            AssetDatabase.SaveAssets();

            var response = Snapshot(PROBE_ASSET_PATH, maxDepth: 2, maxArrayElements: 2);
            Assert.That(response.status, Is.EqualTo("ok"), response.error?.message);
            var payload = JsonUtility.FromJson<XUUnityLightMcpAssetSnapshotPayload>(response.payload_json);

            Assert.That(payload.success, Is.True);
            Assert.That(payload.main_asset_type, Does.Contain("XUUnityLightMcpAssetSnapshotProbeAsset"));
            Assert.That(payload.guid, Is.Not.Empty);
            Assert.That(payload.field_count, Is.EqualTo(payload.fields.Count));
            Assert.That(Value(payload, "intValue"), Is.EqualTo("7"));
            Assert.That(Value(payload, "label"), Is.EqualTo("probe"));
            Assert.That(Value(payload, "flag"), Is.EqualTo("true"));
            Assert.That(Value(payload, "mode"), Is.EqualTo("Pivot"));
            Assert.That(Value(payload, "nested.weight"), Is.EqualTo("3"));
            Assert.That(Value(payload, "nested.label"), Is.EqualTo("inner"));
            Assert.That(Value(payload, "m_Script"), Does.StartWith("MonoScript:"));

            var numbers = Field(payload, "numbers");
            Assert.That(numbers.type, Is.EqualTo("Array"));
            Assert.That(numbers.array_size, Is.EqualTo(3));
            Assert.That(numbers.array_truncated, Is.True);
            Assert.That(Value(payload, "numbers.Array.data[1]"), Is.EqualTo("2"));
            Assert.That(payload.fields.Exists(field => field.path == "numbers.Array.data[2]"), Is.False);
        }

        [Test]
        public void AssetSnapshot_RefusesPathsOutsideTheProjectAndMissingAssets()
        {
            var outside = Snapshot("/tmp/outside.asset", maxDepth: 2, maxArrayElements: 8);
            var missing = Snapshot(GENERATED_ROOT + "/DoesNotExist.asset", maxDepth: 2, maxArrayElements: 8);

            Assert.That(outside.status, Is.EqualTo("error"));
            Assert.That(outside.error.code, Is.EqualTo("asset_path_invalid"));
            Assert.That(missing.status, Is.EqualTo("error"));
            Assert.That(missing.error.code, Is.EqualTo("asset_not_found"));
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

        static XUUnityLightMcpResponse Snapshot(string assetPath, int maxDepth, int maxArrayElements)
        {
            var args = new XUUnityLightMcpAssetSnapshotArgs
            {
                assetPath = assetPath,
                maxDepth = maxDepth,
                maxArrayElements = maxArrayElements,
            };
            return new XUUnityLightMcpAssetSnapshotOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = $"asset-{Guid.NewGuid():N}",
                operation = "unity.asset.snapshot",
                args_json = JsonUtility.ToJson(args),
            });
        }

        static XUUnityLightMcpAssetSnapshotField Field(XUUnityLightMcpAssetSnapshotPayload payload, string path)
        {
            var field = payload.fields.Find(candidate => candidate.path == path);
            Assert.That(field, Is.Not.Null, $"field '{path}' missing from {string.Join(", ", payload.fields.ConvertAll(candidate => candidate.path))}");
            return field;
        }

        static string Value(XUUnityLightMcpAssetSnapshotPayload payload, string path)
        {
            return Field(payload, path).value;
        }
    }

    public sealed class XUUnityLightMcpArmRefreshReloadHook : IXUUnityLightMcpScenarioHook
    {
        public const string Name = "xuunity.selftest.arm_refresh_reload";
        public string HookName => Name;

        [Serializable]
        private sealed class ReloadEvidence
        {
            public string status = "armed";
            public string run_id = "";
            public string scenario_name = "";
            public string expected_request_id = "";
            public string captured_at_utc = "";
            public int bridge_generation;
            public string bridge_session_id = "";
            public string evidence_path = "";
        }

        public XUUnityLightMcpScenarioHookResult Execute(string payloadJson)
        {
            var args = JsonUtility.FromJson<XUUnityLightMcpScenarioResultArgs>(payloadJson);
            if (args == null || string.IsNullOrEmpty(args.scenarioName)
                || !args.scenarioName.StartsWith("xuunity_selftest_refresh_reload_", StringComparison.Ordinal)
                || !XUUnityLightMcpScenarioRunRepository.TryLoadState(out var owner) || owner == null
                || owner.scenario == null || owner.scenario.name != args.scenarioName
                || owner.currentStepIndex < 0 || owner.currentStepIndex >= owner.scenario.steps.Count
                || owner.scenario.steps[owner.currentStepIndex].kind != "project_defined_hook"
                || owner.scenario.steps[owner.currentStepIndex].hookName != Name)
            {
                return new XUUnityLightMcpScenarioHookResult
                {
                    success = false,
                    error_code = "selftest_scenario_owner_required",
                    error_message = "Only the active xuunity_selftest_refresh_reload_ scenario may arm this fixture.",
                };
            }

            var evidence = new ReloadEvidence
            {
                run_id = owner.runId,
                scenario_name = args.scenarioName,
                evidence_path = Path.Combine(XUUnityLightMcpFileIpcPaths.RootPath,
                    "fixtures", "refresh-reload-" + owner.runId + ".json"),
            };
            Action publish = () =>
            {
                evidence.captured_at_utc = DateTime.UtcNow.ToString("O");
                evidence.bridge_generation = XUUnityLightMcpBridgeRuntimeState.BridgeGeneration;
                evidence.bridge_session_id = XUUnityLightMcpBridgeRuntimeState.BridgeSessionId;
                XUUnityLightMcpAtomicFileWriter.WriteAllText(evidence.evidence_path, JsonUtility.ToJson(evidence, true));
            };
            publish();
            var expiresAt = EditorApplication.timeSinceStartup + 15.0d;
            var nextPollAt = 0.0d;
            EditorApplication.CallbackFunction callback = null;
            callback = () =>
            {
                if (EditorApplication.timeSinceStartup < nextPollAt)
                {
                    return;
                }
                nextPollAt = EditorApplication.timeSinceStartup + 0.05d;
                try
                {
                    if (EditorApplication.timeSinceStartup >= expiresAt)
                    {
                        EditorApplication.update -= callback;
                        evidence.status = "expired";
                        publish();
                        return;
                    }
                    if (!XUUnityLightMcpScenarioRunRepository.TryLoadState(out var state) || state == null
                        || state.runId != evidence.run_id || state.scenario?.name != evidence.scenario_name)
                    {
                        EditorApplication.update -= callback;
                        evidence.status = "owner_run_lost";
                        publish();
                        return;
                    }
                    if (state.pendingNestedOperation != "unity.project.refresh"
                        || string.IsNullOrWhiteSpace(state.pendingNestedRequestId)
                        || state.currentStepIndex < 0 || state.currentStepIndex >= state.steps.Count
                        || state.steps[state.currentStepIndex].kind != "project_refresh"
                        || state.steps[state.currentStepIndex].status != "running")
                    {
                        return;
                    }
                    EditorApplication.update -= callback;
                    evidence.status = "reload_requested";
                    evidence.expected_request_id = state.pendingNestedRequestId;
                    publish();
                    EditorUtility.RequestScriptReload();
                }
                catch (Exception exception)
                {
                    EditorApplication.update -= callback;
                    Debug.LogException(exception);
                }
            };
            EditorApplication.update += callback;
            return new XUUnityLightMcpScenarioHookResult
            {
                outcome = "refresh_reload_armed",
                payload_json = JsonUtility.ToJson(evidence),
            };
        }
    }
}
