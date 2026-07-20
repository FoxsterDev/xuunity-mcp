using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using NUnit.Framework;
using UnityEditor.TestTools.TestRunner.Api;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;
using XUUnity.LightMcp.Editor.Operations;
using XUUnity.LightMcp.Editor.ScenarioHooks;

namespace XUUnity.LightMcp.Tests.EditMode
{
    [Category("XUUnity.MCP.SelfTest")]
    [Category("XUUnity.MCP.EditMode")]
    [Category("XUUnity.MCP.Fast")]
    public sealed class XUUnityLightMcpEditModeSelfTests
    {
        GameObject _createdRoot;

        [TearDown]
        public void TearDown()
        {
            if (_createdRoot != null)
            {
                UnityEngine.Object.DestroyImmediate(_createdRoot);
                _createdRoot = null;
            }
        }

        [Test]
        public void TestFilter_NormalizesEmptyAndDuplicateValues()
        {
            var values = XUUnityLightMcpTestsUtility.NormalizeOptionalStringArray(
                new[] { "", "  alpha  ", "alpha", "beta", "  " });

            CollectionAssert.AreEqual(new[] { "alpha", "beta" }, values);
        }

        [Test]
        public void TestFilter_BuildsCategoryAndAssemblyFilter()
        {
            var args = JsonUtility.ToJson(new XUUnityLightMcpTestsArgs
            {
                categoryNames = new[] { "XUUnity.MCP.Fast" },
                assemblyNames = new[] { "com.xuunity.light-mcp.Editor.Tests" }
            });

            var built = XUUnityLightMcpTestsUtility.TryBuildFilter(
                args,
                TestMode.EditMode,
                "EditMode",
                out var filter,
                out var summary,
                out var filterRequested,
                out var errorMessage);

            Assert.That(built, Is.True, errorMessage);
            Assert.That(filter.testMode, Is.EqualTo(TestMode.EditMode));
            CollectionAssert.AreEqual(new[] { "XUUnity.MCP.Fast" }, filter.categoryNames);
            CollectionAssert.AreEqual(new[] { "com.xuunity.light-mcp.Editor.Tests" }, filter.assemblyNames);
            Assert.That(filterRequested, Is.True);
            Assert.That(summary, Does.Contain("categories=XUUnity.MCP.Fast"));
        }

        [Test]
        public void RequestedEmptyTestFilter_UsesNonPassingValidationVerdict()
        {
            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(
                new XUUnityLightMcpPersistedTestRunState
                {
                    project_root = "selftest",
                    filter_summary = "tests=Missing.Namespace.Test; groups=all; categories=all; assemblies=all",
                    filter_requested = true,
                    total = 0,
                    started_at_utc = "2026-01-01T00:00:00Z",
                    completed_at_utc = "2026-01-01T00:00:01Z",
                    run_phase = "completed"
                });

            Assert.That(payload.status, Is.EqualTo("test_filter_no_match"));
            Assert.That(payload.test_verdict, Is.EqualTo("test_filter_no_match"));
            Assert.That(payload.filter_requested, Is.True);
            Assert.That(payload.filter_summary, Does.Contain("Missing.Namespace.Test"));
            Assert.That(payload.total, Is.Zero);
            Assert.That(payload.recommended_next_action, Is.EqualTo("refresh_project_once_then_retry_same_filter"));
            Assert.That(payload.recommended_recovery_command, Does.Contain("request-project-refresh"));
        }

        [Test]
        public void UnfilteredEmptyTestRun_UsesNoTestsVerdict()
        {
            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(
                new XUUnityLightMcpPersistedTestRunState
                {
                    project_root = "selftest",
                    filter_summary = "tests=all; groups=all; categories=all; assemblies=all",
                    filter_requested = false,
                    total = 0,
                    started_at_utc = "2026-01-01T00:00:00Z",
                    completed_at_utc = "2026-01-01T00:00:01Z",
                    run_phase = "completed"
                });

            Assert.That(payload.status, Is.EqualTo("no_tests"));
            Assert.That(payload.test_verdict, Is.EqualTo("no_tests"));
            Assert.That(payload.recommended_next_action, Is.EqualTo("none"));
            Assert.That(payload.recommended_recovery_command, Is.Empty);
        }

        [Test]
        public void ResponseWriter_SuccessAndErrorPreserveRequestContract()
        {
            var success = XUUnityLightMcpResponseWriter.Success("req-1", "unity.selftest", "{\"ok\":true}");
            var error = XUUnityLightMcpResponseWriter.Error("req-2", "selftest_failed", "Failure message.");

            Assert.That(success.request_id, Is.EqualTo("req-1"));
            Assert.That(success.status, Is.EqualTo("ok"));
            Assert.That(success.payload_type, Is.EqualTo("unity.selftest"));
            Assert.That(success.payload_json, Does.Contain("\"ok\":true"));
            Assert.That(success.error, Is.Null);
            Assert.That(error.request_id, Is.EqualTo("req-2"));
            Assert.That(error.status, Is.EqualTo("error"));
            Assert.That(error.error.code, Is.EqualTo("selftest_failed"));
            Assert.That(error.error.message, Is.EqualTo("Failure message."));
        }

        [Test]
        [Category("XUUnity.MCP.Scene")]
        public void SceneSnapshotOperation_ReportsRootGameObjectNames()
        {
            _createdRoot = new GameObject("XUUnityMcp_EditModeSnapshotRoot");

            var response = new XUUnityLightMcpSceneSnapshotOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "scene-snapshot-selftest",
                operation = "unity.scene.snapshot",
                args_json = "{}"
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpSceneSnapshotPayload>(response.payload_json);

            Assert.That(response.status, Is.EqualTo("ok"));
            Assert.That(payload.active_scene.root_count, Is.GreaterThanOrEqualTo(1));
            Assert.That(
                payload.root_objects.Exists(root => root.name == "XUUnityMcp_EditModeSnapshotRoot"),
                Is.True);
        }

        [Test]
        [Category("XUUnity.MCP.Scene")]
        public void SceneOpenOperation_OpensProjectRelativeScene()
        {
            const string generatedRoot = "Assets/XUUnityLightMcpGenerated";
            var generatedRootExisted = AssetDatabase.IsValidFolder(generatedRoot) || Directory.Exists(generatedRoot);
            var testDir = $"{generatedRoot}/SceneOpenSelfTest";
            var scenePath = $"{testDir}/SceneOpenSelfTest.unity";
            Directory.CreateDirectory(testDir);
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Assert.That(EditorSceneManager.SaveScene(scene, scenePath), Is.True);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            try
            {
                var args = JsonUtility.ToJson(new XUUnityLightMcpSceneOpenArgs
                {
                    scenePath = scenePath,
                    allowDirtySceneDiscard = true
                });

                var response = new XUUnityLightMcpSceneOpenOperation().Execute(new XUUnityLightMcpRequest
                {
                    request_id = "scene-open-selftest",
                    operation = "unity.scene.open",
                    args_json = args
                });
                var payload = JsonUtility.FromJson<XUUnityLightMcpSceneOpenPayload>(response.payload_json);

                Assert.That(response.status, Is.EqualTo("ok"));
                Assert.That(payload.status, Is.EqualTo("passed"));
                Assert.That(payload.opened, Is.True);
                Assert.That(payload.active_scene.path, Is.EqualTo(scenePath));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                AssetDatabase.DeleteAsset(scenePath);
                AssetDatabase.DeleteAsset(testDir);
                if (!generatedRootExisted)
                {
                    AssetDatabase.DeleteAsset(generatedRoot);
                }
            }
        }

        [Test]
        [Category("XUUnity.MCP.Scene")]
        public void SceneOpenOperation_RequiresScenePath()
        {
            var response = new XUUnityLightMcpSceneOpenOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "scene-open-missing-path-selftest",
                operation = "unity.scene.open",
                args_json = "{}"
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpSceneOpenPayload>(response.payload_json);

            Assert.That(response.status, Is.EqualTo("ok"));
            Assert.That(payload.status, Is.EqualTo("failed"));
            Assert.That(payload.failure_reason, Does.Contain("scenePath"));
        }

        [Test]
        [Category("XUUnity.MCP.Scene")]
        public void SceneAssertOperation_ReportsMissingRequiredRoots()
        {
            _createdRoot = new GameObject("XUUnityMcp_EditModeAssertRoot");
            var args = JsonUtility.ToJson(new XUUnityLightMcpSceneAssertArgs
            {
                allowDirty = true,
                requiredRootNames = new[]
                {
                    "XUUnityMcp_EditModeAssertRoot",
                    "XUUnityMcp_MissingRoot"
                }
            });

            var response = new XUUnityLightMcpSceneAssertOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "scene-assert-selftest",
                operation = "unity.scene.assert",
                args_json = args
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpSceneAssertPayload>(response.payload_json);

            Assert.That(response.status, Is.EqualTo("ok"));
            Assert.That(payload.status, Is.EqualTo("failed"));
            CollectionAssert.Contains(payload.missing_root_names, "XUUnityMcp_MissingRoot");
            Assert.That(payload.failure_reason, Does.Contain("XUUnityMcp_MissingRoot"));
        }

        [Test]
        public void StatusOperation_ReturnsEditorStatePayload()
        {
            var response = new XUUnityLightMcpStatusOperation().Execute(new XUUnityLightMcpRequest
            {
                request_id = "status-selftest",
                operation = "unity.status",
                args_json = "{}"
            });
            var payload = JsonUtility.FromJson<XUUnityLightMcpStatusPayload>(response.payload_json);

            Assert.That(response.status, Is.EqualTo("ok"));
            Assert.That(payload.project_root, Is.Not.Empty);
            Assert.That(payload.playmode_state, Is.Not.Empty);
            Assert.That(payload.health_status, Is.Not.Empty);
            Assert.That(payload.supported_operations, Does.Contain("unity.status"));
        }

        [Test]
        public void ScenarioProjectActionNormalizer_ExpandsRawProjectActionPayload()
        {
            var catalogPath = WriteTemporaryProjectActionCatalog();
            try
            {
                var argsJson = "{\"scenario\":{\"name\":\"native_project_action\",\"steps\":[{\"stepId\":\"scan\",\"kind\":\"project_action\",\"actionId\":\"localization.scan\",\"allowMutating\":true,\"payload\":{\"target_language\":\"pt-BR\",\"include_scripts\":true}}]}}";

                var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                    argsJson,
                    catalogPath,
                    out var normalizedArgsJson,
                    out var errorCode,
                    out var errorMessage);

                Assert.That(normalized, Is.True, $"{errorCode}: {errorMessage}");
                var args = JsonUtility.FromJson<XUUnityLightMcpScenarioValidateArgs>(normalizedArgsJson);
                Assert.That(args.scenario.steps[0].kind, Is.EqualTo("project_defined_hook"));
                Assert.That(args.scenario.steps[0].hookName, Is.EqualTo("sample.localization"));
                Assert.That(args.scenario.steps[0].hookPayloadJson, Does.Contain("\"action\":\"localization.scan\""));
                Assert.That(args.scenario.steps[0].hookPayloadJson, Does.Contain("\"target_language\":\"pt-BR\""));
            }
            finally
            {
                File.Delete(catalogPath);
            }
        }

        [Test]
        public void ScenarioProjectActionNormalizer_RequiresMutationApproval()
        {
            var catalogPath = WriteTemporaryProjectActionCatalog();
            try
            {
                var argsJson = "{\"scenario\":{\"name\":\"native_project_action\",\"steps\":[{\"stepId\":\"scan\",\"kind\":\"project_action\",\"actionId\":\"localization.scan\",\"payload\":{\"target_language\":\"pt-BR\"}}]}}";

                var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                    argsJson,
                    catalogPath,
                    out _,
                    out var errorCode,
                    out var errorMessage);

                Assert.That(normalized, Is.False);
                Assert.That(errorCode, Is.EqualTo("project_action_mutation_approval_required"));
                Assert.That(errorMessage, Does.Contain("localization.scan"));
            }
            finally
            {
                File.Delete(catalogPath);
            }
        }

        [Test]
        public void ScenarioProjectActionNormalizer_ExpandsPollUntilOperationPayloads()
        {
            var argsJson = "{\"scenario\":{\"name\":\"poll_until\",\"steps\":[{\"stepId\":\"flow\",\"operation\":\"project_defined_hook_poll_until\",\"hookName\":\"example.ui_smoke\",\"startPayload\":{\"action\":\"start_flow\"},\"pollPayload\":{\"action\":\"snapshot_flow\"},\"passWhen\":\"payload.status == 'passed'\",\"failWhen\":\"payload.status == 'failed'\",\"continueWhen\":\"payload.status == 'running'\",\"intervalSeconds\":2,\"timeoutSeconds\":180}]}}";

            var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                argsJson,
                out var normalizedArgsJson,
                out var errorCode,
                out var errorMessage);

            Assert.That(normalized, Is.True, $"{errorCode}: {errorMessage}");
            var args = JsonUtility.FromJson<XUUnityLightMcpScenarioValidateArgs>(normalizedArgsJson);
            var step = args.scenario.steps[0];
            Assert.That(step.kind, Is.EqualTo("project_defined_hook_poll_until"));
            Assert.That(step.startPayloadJson, Does.Contain("\"action\":\"start_flow\""));
            Assert.That(step.pollPayloadJson, Does.Contain("\"action\":\"snapshot_flow\""));
        }

        [Test]
        public void ScenarioRunner_PollUntilPassesAfterRepeatedRunningPolls()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("passed_after_two_running_polls");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_pass",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "flow",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        startPayloadJson = "{\"action\":\"start_flow\"}",
                        pollPayloadJson = "{\"action\":\"snapshot_flow\"}",
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'failed'",
                        continueWhen = "payload.status == 'running'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 5.0d,
                        promotePayloadFields = new[] { "status", "selected_tab", "user_path" },
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("passed"));
            Assert.That(payload.steps[0].status, Is.EqualTo("passed"));
            Assert.That(payload.steps[0].poll_count, Is.EqualTo(3));
            Assert.That(payload.steps[0].payload_json, Does.Contain("\"status\":\"passed\""));
        }

        [Test]
        public void ScenarioRunner_PollUntilImplicitlyContinuesNotStartedPayloads()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("not_started_then_passed");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_not_started",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "flow",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        startPayloadJson = "{\"action\":\"start_flow\"}",
                        pollPayloadJson = "{\"action\":\"snapshot_flow\"}",
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'failed'",
                        continueWhen = "payload.status == 'running'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 5.0d,
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("passed"));
            Assert.That(payload.steps[0].status, Is.EqualTo("passed"));
            Assert.That(payload.steps[0].poll_count, Is.EqualTo(3));
            Assert.That(payload.steps[0].payload_json, Does.Contain("\"status\":\"passed\""));
        }

        [Test]
        public void ScenarioRunner_PollUntilExplicitFailureOverridesNotStartedContinuation()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("not_started_then_passed");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_not_started_is_failure",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "flow",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        startPayloadJson = "{\"action\":\"start_flow\"}",
                        pollPayloadJson = "{\"action\":\"snapshot_flow\"}",
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'not_started'",
                        continueWhen = "payload.status == 'running'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 5.0d,
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("failed"));
            Assert.That(payload.steps[0].status, Is.EqualTo("failed"));
            Assert.That(payload.steps[0].poll_count, Is.EqualTo(1));
            Assert.That(payload.steps[0].terminal_status, Is.EqualTo("not_started"));
        }

        [Test]
        public void ScenarioRunner_PollUntilFailureContinuesToCleanup()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("failed_terminal");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_fail_cleanup",
                stopOnFirstFailure = true,
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "flow",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        startPayloadJson = "{\"action\":\"start_flow\"}",
                        pollPayloadJson = "{\"action\":\"snapshot_flow\"}",
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'failed'",
                        continueWhen = "payload.status == 'running'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 5.0d,
                        continueToCleanupOnFail = true,
                    },
                },
                cleanupSteps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "cleanup",
                        kind = "project_defined_hook",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        hookPayloadJson = "{\"action\":\"cleanup\"}",
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("failed"));
            Assert.That(payload.steps[0].status, Is.EqualTo("failed"));
            Assert.That(payload.steps[0].failure_class, Is.EqualTo("product"));
            Assert.That(payload.steps[1].status, Is.EqualTo("passed"));
            Assert.That(XUUnityLightMcpSyntheticPollUntilHook.CleanupCount, Is.EqualTo(1));
        }

        [Test]
        public void ScenarioRunner_PollUntilTimeoutKeepsLatestPayload()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("always_running");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_timeout",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "flow",
                        kind = "project_defined_hook_poll_until",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        startPayloadJson = "{\"action\":\"start_flow\"}",
                        pollPayloadJson = "{\"action\":\"snapshot_flow\"}",
                        passWhen = "payload.status == 'passed'",
                        failWhen = "payload.status == 'failed'",
                        continueWhen = "payload.status == 'running'",
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 2.0d,
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            XUUnityLightMcpScenarioRunner.Tick();
            XUUnityLightMcpScenarioRunner.Tick();
            System.Threading.Thread.Sleep(2500);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("failed"));
            Assert.That(payload.steps[0].error_code, Is.EqualTo("project_hook_poll_until_timeout"));
            Assert.That(payload.steps[0].terminal_status, Is.EqualTo("timeout"));
            Assert.That(payload.steps[0].payload_json, Does.Contain("\"status\":\"running\""));
            Assert.That(payload.steps[0].payload_json, Does.Contain("\"poll_count\":1"));
        }

        static void TickScenarioUntilIdle()
        {
            for (var i = 0; i < 20 && XUUnityLightMcpScenarioRunner.HasActiveRun(); i++)
            {
                XUUnityLightMcpScenarioRunner.Tick();
            }

            Assert.That(XUUnityLightMcpScenarioRunner.HasActiveRun(), Is.False);
        }

        static string WriteTemporaryProjectActionCatalog()
        {
            var catalogPath = Path.Combine(Path.GetTempPath(), $"xuunity_project_actions_{Guid.NewGuid():N}.yaml");
            File.WriteAllText(
                catalogPath,
                "schemaVersion: xuunity.project-actions.v1\n"
                + "project: SelfTest\n"
                + "hookName: \"\"\n"
                + "actions:\n"
                + "  localization.scan:\n"
                + "    aliases:\n"
                + "      - localization.discovery\n"
                + "    hookName: sample.localization\n"
                + "    payload: {}\n"
                + "    mutates:\n"
                + "      - repo-level localization pipeline reports\n");
            return catalogPath;
        }
    }

    public sealed class XUUnityLightMcpSyntheticPollUntilHook : IXUUnityLightMcpScenarioHook
    {
        public const string Name = "xuunity.synthetic_poll_until";
        static string s_mode = "passed_after_two_running_polls";
        static int s_pollCount;
        public static int CleanupCount { get; private set; }

        public string HookName => Name;

        public static void Reset(string mode)
        {
            s_mode = mode;
            s_pollCount = 0;
            CleanupCount = 0;
        }

        public XUUnityLightMcpScenarioHookResult Execute(string payloadJson)
        {
            if ((payloadJson ?? "").Contains("\"action\":\"cleanup\""))
            {
                CleanupCount++;
                return new XUUnityLightMcpScenarioHookResult
                {
                    outcome = "cleanup_done",
                    payload_json = "{\"status\":\"cleaned\"}",
                };
            }

            if ((payloadJson ?? "").Contains("\"action\":\"start_flow\""))
            {
                s_pollCount = 0;
                return new XUUnityLightMcpScenarioHookResult
                {
                    outcome = "flow_started",
                    payload_json = "{\"status\":\"running\"}",
                };
            }

            s_pollCount++;
            if (s_mode == "failed_terminal")
            {
                return new XUUnityLightMcpScenarioHookResult
                {
                    outcome = "flow_failed",
                    payload_json = "{\"status\":\"failed\",\"failure_class\":\"product\",\"selected_tab\":\"Store\",\"user_path\":\"open_store\"}",
                };
            }

            var status = s_mode == "not_started_then_passed"
                ? (s_pollCount < 3 ? "not_started" : "passed")
                : (s_mode == "always_running" || s_pollCount < 3 ? "running" : "passed");
            return new XUUnityLightMcpScenarioHookResult
            {
                outcome = $"flow_{status}",
                payload_json = $"{{\"status\":\"{status}\",\"poll_count\":{s_pollCount},\"selected_tab\":\"Store\",\"user_path\":\"open_store\"}}",
            };
        }
    }
}
