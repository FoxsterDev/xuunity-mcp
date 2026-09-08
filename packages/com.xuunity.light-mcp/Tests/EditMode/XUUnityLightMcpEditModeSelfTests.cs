using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.Compilation;
using NUnit.Framework;
using UnityEditor.TestTools.TestRunner.Api;
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
        public void CompileWarnings_CountEveryOccurrenceAndBoundUniqueEvidence()
        {
            var errors = new List<XUUnityLightMcpCompileErrorItem>();
            var warnings = new List<XUUnityLightMcpCompileErrorItem>();
            var warningKeys = new HashSet<string>(StringComparer.Ordinal);
            var warningCount = 0;
            var messages = new[]
            {
                new CompilerMessage { type = CompilerMessageType.Warning, message = "warning CS0618: old API", file = "Assets/A.cs", line = 10, column = 4 },
                new CompilerMessage { type = CompilerMessageType.Warning, message = "warning CS0618: old API", file = "Assets/A.cs", line = 10, column = 4 },
                new CompilerMessage { type = CompilerMessageType.Warning, message = "warning CS0108: hides member", file = "Assets/B.cs", line = 20, column = 2 },
                new CompilerMessage { type = CompilerMessageType.Error, message = "error CS1002: ; expected", file = "Assets/C.cs", line = 30, column = 1 },
            };

            XUUnityLightMcpCompileUtility.CollectCompilerMessages(
                "Game.dll", messages, errors, warnings, warningKeys, ref warningCount);

            Assert.That(warningCount, Is.EqualTo(3));
            Assert.That(warnings.Count, Is.EqualTo(2));
            Assert.That(warnings[0].code, Is.EqualTo("CS0618"));
            Assert.That(warnings[0].severity, Is.EqualTo("warning"));
            Assert.That(errors.Count, Is.EqualTo(1));
            Assert.That(errors[0].code, Is.EqualTo("CS1002"));
            Assert.That(errors[0].severity, Is.EqualTo("error"));
        }

        [Test]
        public void CompileRebuildEvidence_DeduplicatesAssembliesAndLetsARebuildOverrideACacheHit()
        {
            var rebuilt = new HashSet<string>(StringComparer.Ordinal);
            var cached = new HashSet<string>(StringComparer.Ordinal);

            XUUnityLightMcpCompileUtility.RecordAssemblyExecution("Game.dll", rebuilt, cached, rebuilt: false);
            XUUnityLightMcpCompileUtility.RecordAssemblyExecution("Game.dll", rebuilt, cached, rebuilt: true);
            XUUnityLightMcpCompileUtility.RecordAssemblyExecution("Game.dll", rebuilt, cached, rebuilt: true);
            XUUnityLightMcpCompileUtility.RecordAssemblyExecution("Game.Editor.dll", rebuilt, cached, rebuilt: false);
            XUUnityLightMcpCompileUtility.RecordAssemblyExecution("Game.Editor.dll", rebuilt, cached, rebuilt: false);

            var payload = new XUUnityLightMcpCompileConfigPayload();
            XUUnityLightMcpCompileUtility.PopulateRebuildEvidence(payload, rebuilt, cached);

            Assert.That(payload.rebuilt_assembly_count, Is.EqualTo(1));
            Assert.That(payload.cached_assembly_count, Is.EqualTo(1));
#if UNITY_2022_1_OR_NEWER
            Assert.That(payload.rebuild_evidence_status, Is.EqualTo("measured"));
            Assert.That(
                payload.rebuild_evidence_basis,
                Is.EqualTo("compilation_pipeline_started_and_not_required_events"));
#else
            Assert.That(payload.rebuild_evidence_status, Is.EqualTo("rebuilt_only_cache_status_unavailable"));
#endif
        }

        [Test]
        public void CompilerDiagnosticCode_IsReadFromTheDiagnosticNotThePath()
        {
            Assert.That(
                XUUnityLightMcpCompileUtility.ExtractCompilerDiagnosticCode(
                    "Assets/Physics2020/Board.cs(12,7): warning CS0168: variable declared but never used"),
                Is.EqualTo("CS0168"));
            Assert.That(
                XUUnityLightMcpCompileUtility.ExtractCompilerDiagnosticCode(
                    "Assets/CS2024Tools/Board.cs(3,1): error CS1002: ; expected"),
                Is.EqualTo("CS1002"));
            Assert.That(
                XUUnityLightMcpCompileUtility.ExtractCompilerDiagnosticCode("Assets/Docs2024/Note.cs(1,1): note"),
                Is.Empty);
            Assert.That(XUUnityLightMcpCompileUtility.ExtractCompilerDiagnosticCode(null), Is.Empty);
        }

        [Test]
        public void CompileMatrixWarnings_AggregateUniqueEvidenceAcrossConfigurations()
        {
            var shared = new XUUnityLightMcpCompileErrorItem
            {
                assembly_name = "Game.dll",
                code = "CS0618",
                severity = "warning",
                message = "warning CS0618: old API",
                file = "Assets/A.cs",
                line = 10,
                column = 4,
            };
            var distinct = new XUUnityLightMcpCompileErrorItem
            {
                assembly_name = "Game.Editor.dll",
                code = "CS0108",
                severity = "warning",
                message = "warning CS0108: hides member",
                file = "Assets/B.cs",
                line = 20,
                column = 2,
            };
            var payload = new XUUnityLightMcpCompileMatrixPayload
            {
                results = new List<XUUnityLightMcpCompileConfigPayload>
                {
                    new() { warning_count = 2, all_unique_warnings = new List<XUUnityLightMcpCompileErrorItem> { shared } },
                    new() { warning_count = 2, all_unique_warnings = new List<XUUnityLightMcpCompileErrorItem> { shared, distinct } },
                },
            };

            XUUnityLightMcpCompileUtility.PopulateMatrixWarningSummary(payload);

            Assert.That(payload.warning_count, Is.EqualTo(4));
            Assert.That(payload.unique_warning_count, Is.EqualTo(2));
            Assert.That(payload.warnings.Count, Is.EqualTo(2));
            Assert.That(payload.warning_sample_limit, Is.EqualTo(XUUnityLightMcpCompileUtility.WarningSampleLimit));
            Assert.That(payload.warnings_truncated, Is.False);
        }

        [Test]
        public void CompileMatrixRebuildEvidence_AggregatesMeasuredConfigurationCounts()
        {
            var payload = new XUUnityLightMcpCompileMatrixPayload
            {
                results = new List<XUUnityLightMcpCompileConfigPayload>
                {
                    new()
                    {
                        rebuilt_assembly_count = 3,
                        cached_assembly_count = 5,
                        rebuild_evidence_status = "measured",
                    },
                    new()
                    {
                        rebuilt_assembly_count = 2,
                        cached_assembly_count = 7,
                        rebuild_evidence_status = "measured",
                    },
                },
            };

            XUUnityLightMcpCompileUtility.PopulateMatrixRebuildEvidenceSummary(payload);

            Assert.That(payload.rebuilt_assembly_count, Is.EqualTo(5));
            Assert.That(payload.cached_assembly_count, Is.EqualTo(12));
            Assert.That(payload.rebuild_evidence_status, Is.EqualTo("measured"));
            Assert.That(payload.rebuild_evidence_basis, Is.EqualTo("per_configuration_compilation_pipeline_events"));

            var legacyPayload = new XUUnityLightMcpCompileMatrixPayload
            {
                results = new List<XUUnityLightMcpCompileConfigPayload>
                {
                    new() { rebuilt_assembly_count = 3, rebuild_evidence_status = "rebuilt_only_cache_status_unavailable" },
                },
            };
            XUUnityLightMcpCompileUtility.PopulateMatrixRebuildEvidenceSummary(legacyPayload);

            Assert.That(
                legacyPayload.rebuild_evidence_status,
                Is.EqualTo("rebuilt_only_cache_status_unavailable"));
            Assert.That(
                legacyPayload.rebuild_evidence_basis,
                Is.EqualTo("per_configuration_compilation_pipeline_started_event"));
        }

        [Test]
        public void BridgeProcessIdentity_RefusesAssetImportWorkerCommandLines()
        {
            Assert.That(
                XUUnityLightMcpBridgeProcessIdentity.ClassifyProcess(
                    new[] { "Unity", "-adb2", "-batchMode", "-name", "AssetImportWorker7" },
                    false,
                    true),
                Is.EqualTo(XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass));
            Assert.That(
                XUUnityLightMcpBridgeProcessIdentity.ClassifyProcess(
                    new[] { "Unity", "-projectPath", "/tmp/Project", "-assetImportWorker" },
                    false,
                    false),
                Is.EqualTo(XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass));
            Assert.That(
                XUUnityLightMcpBridgeProcessIdentity.ClassifyProcess(
                    new[] { "Unity", "-projectPath", "/tmp/Project" },
                    true,
                    false),
                Is.EqualTo(XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass));
        }

        [Test]
        public void BridgeProcessIdentity_DistinguishesMainEditorFromOrdinaryBatchMode()
        {
            Assert.That(
                XUUnityLightMcpBridgeProcessIdentity.ClassifyProcess(
                    new[] { "Unity", "-projectPath", "/tmp/Project" },
                    false,
                    false),
                Is.EqualTo(XUUnityLightMcpBridgeProcessIdentity.MainEditorProcessClass));
            Assert.That(
                XUUnityLightMcpBridgeProcessIdentity.ClassifyProcess(
                    new[] { "Unity", "-batchMode", "-runTests" },
                    false,
                    true),
                Is.EqualTo(XUUnityLightMcpBridgeProcessIdentity.BatchProcessClass));
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
        public void TestRunPayload_PreservesCallbackTimePlayModeAccountingProvenance()
        {
            var payload = XUUnityLightMcpTestRunState.BuildPayloadForState(
                new XUUnityLightMcpPersistedTestRunState
                {
                    project_root = "selftest",
                    playmode_state_after_settle = "playing",
                    playmode_state_after_test_callbacks = "playing",
                    playmode_state_after_host_settle = "",
                    playmode_state_after_settle_source = "unity_test_callbacks",
                    playmode_state_accounting_consistent = true,
                    playmode_state_accounting_note = ""
                });

            Assert.That(payload.playmode_state_after_settle, Is.EqualTo("playing"));
            Assert.That(payload.playmode_state_after_test_callbacks, Is.EqualTo("playing"));
            Assert.That(payload.playmode_state_after_host_settle, Is.Empty);
            Assert.That(payload.playmode_state_after_settle_source, Is.EqualTo("unity_test_callbacks"));
            Assert.That(payload.playmode_state_accounting_consistent, Is.True);
            Assert.That(payload.playmode_state_accounting_note, Is.Empty);
        }

        [Test]
        public void RefreshSettleTimeout_CompileChurnWinsOverSettlePhase()
        {
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(true, false, true, "waiting_for_package_settle"),
                Is.EqualTo("compile_import_churn_timeout"));
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, true, false, ""),
                Is.EqualTo("compile_import_churn_timeout"));
        }

        [Test]
        public void RefreshSettleTimeout_ClassifiesPendingPhases()
        {
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, false, true, "waiting_for_package_settle"),
                Is.EqualTo("package_settle_timeout"));
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, false, true, "waiting_for_stable_idle_ticks"),
                Is.EqualTo("idle_confirmation_incomplete"));
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, false, true, "waiting_for_editor_idle"),
                Is.EqualTo("editor_busy_timeout"));
        }

        [Test]
        public void RefreshSettleTimeout_NotPendingIsLostFinalAccounting()
        {
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, false, false, "settled"),
                Is.EqualTo("lost_final_accounting"));
            Assert.That(
                XUUnityLightMcpScenarioRefreshStepHandler.ClassifyRefreshSettleTimeout(false, false, false, ""),
                Is.EqualTo("lost_final_accounting"));
        }

        [Test]
        public void RefreshTimeoutPayload_MergesExistingPayloadWithEvidence()
        {
            var existing = JsonUtility.ToJson(new XUUnityLightMcpProjectRefreshPayload
            {
                outcome = "refresh_started",
                asset_database_refreshed = true,
                package_resolve_requested = true,
            });

            var json = XUUnityLightMcpScenarioRefreshStepHandler.BuildRefreshTimeoutPayloadJson(
                existing,
                false,
                false,
                false,
                "settled",
                "edit",
                1,
                "req-settle-1");

            var payload = JsonUtility.FromJson<XUUnityLightMcpProjectRefreshTimeoutPayload>(json);
            Assert.That(payload.asset_database_refreshed, Is.True);
            Assert.That(payload.package_resolve_requested, Is.True);
            Assert.That(payload.settle_timed_out, Is.True);
            Assert.That(payload.settle_timeout_classification, Is.EqualTo("lost_final_accounting"));
            Assert.That(payload.operation_may_have_completed, Is.True);
            Assert.That(payload.settle_phase_at_timeout, Is.EqualTo("settled"));
            Assert.That(payload.settle_phase, Is.EqualTo("settled"));
            Assert.That(payload.playmode_state_at_timeout, Is.EqualTo("edit"));
            Assert.That(payload.stable_idle_ticks_at_timeout, Is.EqualTo(1));
            Assert.That(payload.settle_request_id, Is.EqualTo("req-settle-1"));
        }

        [Test]
        public void RefreshTimeoutPayload_BusyEvidenceDoesNotClaimCompletion()
        {
            var json = XUUnityLightMcpScenarioRefreshStepHandler.BuildRefreshTimeoutPayloadJson(
                "",
                false,
                false,
                true,
                "waiting_for_package_settle",
                "edit",
                0,
                "req-settle-2");

            var payload = JsonUtility.FromJson<XUUnityLightMcpProjectRefreshTimeoutPayload>(json);
            Assert.That(payload.settle_timeout_classification, Is.EqualTo("package_settle_timeout"));
            Assert.That(payload.operation_may_have_completed, Is.False);
            Assert.That(payload.refresh_settle_pending_at_timeout, Is.True);
        }

        [Test]
        public void RefreshTimeoutPayload_MalformedExistingPayloadFallsBackToFreshEvidence()
        {
            var json = XUUnityLightMcpScenarioRefreshStepHandler.BuildRefreshTimeoutPayloadJson(
                "{not valid json",
                true,
                false,
                true,
                "waiting_for_editor_idle",
                "edit",
                0,
                "req-settle-3");

            var payload = JsonUtility.FromJson<XUUnityLightMcpProjectRefreshTimeoutPayload>(json);
            Assert.That(payload.settle_timed_out, Is.True);
            Assert.That(payload.settle_timeout_classification, Is.EqualTo("compile_import_churn_timeout"));
            Assert.That(payload.editor_is_compiling_at_timeout, Is.True);
        }

        [Test]
        public void ConsoleTailByteBudget_ResolvesTheSharedConvention()
        {
            Assert.That(XUUnityLightMcpConsoleTailOperation.ResolveConsoleTailByteBudget(0), Is.EqualTo(16384));
            Assert.That(XUUnityLightMcpConsoleTailOperation.ResolveConsoleTailByteBudget(-1), Is.EqualTo(-1));
            Assert.That(XUUnityLightMcpConsoleTailOperation.ResolveConsoleTailByteBudget(-50), Is.EqualTo(-1));
            Assert.That(XUUnityLightMcpConsoleTailOperation.ResolveConsoleTailByteBudget(4096), Is.EqualTo(4096));
        }

        [Test]
        public void ConsoleTailByteBudget_EstimateCountsUtf8BytesPlusOverhead()
        {
            var item = new XUUnityLightMcpConsoleItem
            {
                type = "log",
                message = "ррр",
                timestamp = "",
                stack_trace = "de",
            };
            Assert.That(
                XUUnityLightMcpConsoleTailOperation.EstimateConsoleItemBytes(item),
                Is.EqualTo(64 + 3 + 6 + 2));
        }

        [Test]
        public void ConsoleTail_DefaultCopySuppressesStackTraceUnlessRequested()
        {
            var item = new XUUnityLightMcpConsoleItem
            {
                type = "error",
                message = "signal",
                stack_trace = "large stack"
            };

            Assert.That(XUUnityLightMcpConsoleTailOperation.CopyItem(item, false).stack_trace, Is.Empty);
            Assert.That(XUUnityLightMcpConsoleTailOperation.CopyItem(item, true).stack_trace, Is.EqualTo("large stack"));
        }

        [Test]
        public void ConsoleTailByteBudget_DropsOldestItemsFirstWithAccounting()
        {
            var items = new List<XUUnityLightMcpConsoleItem>();
            for (var index = 0; index < 5; index++)
            {
                items.Add(new XUUnityLightMcpConsoleItem { type = "log", message = $"item-{index}-" + new string('x', 100) });
            }
            var perItem = XUUnityLightMcpConsoleTailOperation.EstimateConsoleItemBytes(items[0]);

            var kept = XUUnityLightMcpConsoleTailOperation.ApplyConsoleTailByteBudget(
                items,
                perItem * 2 + 10,
                out var dropped,
                out var newestTruncated,
                out var bytesEstimate);

            Assert.That(kept.Count, Is.EqualTo(2));
            Assert.That(kept[0].message, Does.StartWith("item-3"));
            Assert.That(kept[1].message, Does.StartWith("item-4"));
            Assert.That(dropped, Is.EqualTo(3));
            Assert.That(newestTruncated, Is.False);
            Assert.That(bytesEstimate, Is.LessThanOrEqualTo(perItem * 2 + 10));
        }

        [Test]
        public void ConsoleTailByteBudget_TruncatesAnOversizedNewestItemToFit()
        {
            var items = new List<XUUnityLightMcpConsoleItem>
            {
                new XUUnityLightMcpConsoleItem { type = "log", message = "old" },
                new XUUnityLightMcpConsoleItem
                {
                    type = "exception",
                    message = "giant-" + new string('y', 5000),
                    stack_trace = new string('s', 5000),
                },
            };

            var kept = XUUnityLightMcpConsoleTailOperation.ApplyConsoleTailByteBudget(
                items,
                512,
                out var dropped,
                out var newestTruncated,
                out var bytesEstimate);

            Assert.That(kept.Count, Is.EqualTo(1));
            Assert.That(dropped, Is.EqualTo(1));
            Assert.That(newestTruncated, Is.True);
            Assert.That(kept[0].message, Does.StartWith("giant-"));
            Assert.That(kept[0].message, Does.EndWith("[truncated_by_byte_budget]"));
            Assert.That(kept[0].stack_trace, Is.Empty);
            Assert.That(bytesEstimate, Is.LessThanOrEqualTo(512));
            Assert.That(XUUnityLightMcpConsoleTailOperation.EstimateConsoleItemBytes(kept[0]), Is.LessThanOrEqualTo(512));
        }

        [Test]
        public void ConsoleTailByteBudget_UnboundedKeepsEverything()
        {
            var items = new List<XUUnityLightMcpConsoleItem>
            {
                new XUUnityLightMcpConsoleItem { type = "log", message = new string('x', 50000) },
                new XUUnityLightMcpConsoleItem { type = "log", message = new string('y', 50000) },
            };

            var kept = XUUnityLightMcpConsoleTailOperation.ApplyConsoleTailByteBudget(
                items,
                -1,
                out var dropped,
                out var newestTruncated,
                out var bytesEstimate);

            Assert.That(kept.Count, Is.EqualTo(2));
            Assert.That(dropped, Is.EqualTo(0));
            Assert.That(newestTruncated, Is.False);
            Assert.That(bytesEstimate, Is.GreaterThan(100000));
        }

        [Test]
        public void ConsoleTailByteBudget_TruncateUtf8NeverSplitsBytesPastTheBudget()
        {
            var truncated = XUUnityLightMcpConsoleTailOperation.TruncateUtf8("ррррр", 5);
            Assert.That(System.Text.Encoding.UTF8.GetByteCount(truncated), Is.LessThanOrEqualTo(5));
            Assert.That(truncated, Is.EqualTo("рр"));
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
        public void Edm4uAndroidResolve_RequiresActiveAndroidBuildTarget()
        {
            var valid = XUUnityLightMcpEdm4uResolveOperation.TryValidateBuildTargetPrecondition(
                "android",
                BuildTarget.StandaloneOSX,
                out var errorCode,
                out var errorMessage);

            Assert.That(valid, Is.False);
            Assert.That(errorCode, Is.EqualTo("edm4u_android_target_not_active"));
            Assert.That(errorMessage, Does.Contain("BuildTarget.Android"));
            Assert.That(errorMessage, Does.Contain("unity_build_target_switch"));
        }

        [Test]
        public void Edm4uResolve_TargetPreconditionAllowsAndroidAndVersionHandler()
        {
            Assert.That(
                XUUnityLightMcpEdm4uResolveOperation.TryValidateBuildTargetPrecondition(
                    "android",
                    BuildTarget.Android,
                    out var androidErrorCode,
                    out var androidErrorMessage),
                Is.True);
            Assert.That(androidErrorCode, Is.Empty);
            Assert.That(androidErrorMessage, Is.Empty);

            Assert.That(
                XUUnityLightMcpEdm4uResolveOperation.TryValidateBuildTargetPrecondition(
                    "version_handler",
                    BuildTarget.StandaloneOSX,
                    out var versionHandlerErrorCode,
                    out var versionHandlerErrorMessage),
                Is.True);
            Assert.That(versionHandlerErrorCode, Is.Empty);
            Assert.That(versionHandlerErrorMessage, Is.Empty);
        }

        [Test]
        public void SdkAndroidResolve_RequiresTrackedOutputsAndExpectedCoordinates()
        {
            var missingOutputs = new XUUnityLightMcpSdkAndroidResolveArgs
            {
                expectations = new System.Collections.Generic.List<XUUnityLightMcpSdkDependencyExpectation>
                {
                    new()
                    {
                        path = "ProjectSettings/AndroidResolverDependencies.xml",
                        kind = "android_resolver_package",
                        value = "com.example:sdk:2.0.0",
                    }
                }
            };
            var missingExpectations = new XUUnityLightMcpSdkAndroidResolveArgs
            {
                trackedGeneratedPaths = new System.Collections.Generic.List<string>
                {
                    "ProjectSettings/AndroidResolverDependencies.xml"
                }
            };

            Assert.That(
                XUUnityLightMcpSdkAndroidResolveOperation.TryValidateArgs(
                    missingOutputs,
                    out var outputsErrorCode,
                    out _),
                Is.False);
            Assert.That(outputsErrorCode, Is.EqualTo("sdk_android_resolve_tracked_outputs_missing"));
            Assert.That(
                XUUnityLightMcpSdkAndroidResolveOperation.TryValidateArgs(
                    missingExpectations,
                    out var expectationsErrorCode,
                    out _),
                Is.False);
            Assert.That(expectationsErrorCode, Is.EqualTo("sdk_android_resolve_expectations_missing"));
        }

        [Test]
        public void SdkAndroidResolve_OutputSignatureIsOrderIndependentAndHashSensitive()
        {
            var first = new System.Collections.Generic.List<XUUnityLightMcpSdkGeneratedOutputEvidence>
            {
                new() { path = "b.gradle", file_size_bytes = 20, sha256 = "hash-b" },
                new() { path = "a.xml", file_size_bytes = 10, sha256 = "hash-a" },
            };
            var reordered = new System.Collections.Generic.List<XUUnityLightMcpSdkGeneratedOutputEvidence>
            {
                new() { path = "a.xml", file_size_bytes = 10, sha256 = "hash-a" },
                new() { path = "b.gradle", file_size_bytes = 20, sha256 = "hash-b" },
            };
            var changed = new System.Collections.Generic.List<XUUnityLightMcpSdkGeneratedOutputEvidence>
            {
                new() { path = "a.xml", file_size_bytes = 10, sha256 = "hash-a-new" },
                new() { path = "b.gradle", file_size_bytes = 20, sha256 = "hash-b" },
            };

            var firstSignature = XUUnityLightMcpSdkAndroidResolveRuntime.BuildOutputSignature(first);
            Assert.That(
                XUUnityLightMcpSdkAndroidResolveRuntime.BuildOutputSignature(reordered),
                Is.EqualTo(firstSignature));
            Assert.That(
                XUUnityLightMcpSdkAndroidResolveRuntime.BuildOutputSignature(changed),
                Is.Not.EqualTo(firstSignature));
        }

        [Test]
        public void SdkAndroidResolve_BoundsMainThreadHashWork()
        {
            var args = new XUUnityLightMcpSdkAndroidResolveArgs
            {
                trackedGeneratedPaths = Enumerable.Range(
                        0,
                        XUUnityLightMcpSdkAndroidResolveOperation.MaxTrackedGeneratedPaths + 1)
                    .Select(index => $"ProjectSettings/generated-{index}.xml")
                    .ToList(),
                expectations = new System.Collections.Generic.List<XUUnityLightMcpSdkDependencyExpectation>
                {
                    new()
                    {
                        path = "ProjectSettings/AndroidResolverDependencies.xml",
                        kind = "android_resolver_package",
                        value = "com.example:sdk:2.0.0",
                    }
                }
            };

            Assert.That(
                XUUnityLightMcpSdkAndroidResolveOperation.TryValidateArgs(
                    args,
                    out var errorCode,
                    out _),
                Is.False);
            Assert.That(errorCode, Is.EqualTo("sdk_android_resolve_tracked_outputs_limit"));
        }

        [Test]
        public void SdkAndroidResolve_IsRegisteredAndCapabilityGated()
        {
            Assert.That(
                XUUnityLightMcpOperationRegistry.TryGet(
                    XUUnityLightMcpSdkAndroidResolveOperation.RegisteredOperationName,
                    out var operation),
                Is.True);
            Assert.That(operation, Is.TypeOf<XUUnityLightMcpSdkAndroidResolveOperation>());
            Assert.That(
                XUUnityLightMcpCapabilityRegistry.TryGetRequiredCapability(
                    XUUnityLightMcpSdkAndroidResolveOperation.RegisteredOperationName,
                    out var capability),
                Is.True);
            Assert.That(capability, Is.EqualTo(XUUnityLightMcpCapabilityRegistry.SdkAndroidResolverCapability));
            Assert.That(
                XUUnityLightMcpCapabilityRegistry.IsUngated(
                    XUUnityLightMcpSdkAndroidResolveOperation.RegisteredOperationName),
                Is.False);
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
            Assert.That(payload.supported_operations, Does.Contain("unity.project_action.currency"));
            Assert.That(payload.playmode_loop_liveness, Is.EqualTo("not_playing"));
            Assert.That(payload.playmode_frame_count, Is.GreaterThanOrEqualTo(0));
            Assert.That(payload.playmode_liveness_warning, Is.Empty);
            Assert.That(payload.playmode_liveness_remediation, Is.Empty);
            Assert.That(payload.editor_domain_loaded_utc, Is.Not.Empty);
            Assert.That(payload.editor_domain_currency, Is.Not.Empty);
            Assert.That(payload.application_run_in_background, Is.EqualTo(Application.runInBackground));
            Assert.That(payload.native_autofocus_enabled, Is.False);
            Assert.That(payload.background_execution_mode, Is.EqualTo(XUUnityLightMcpBackgroundExecution.Mode));
        }

        [Test]
        public void BackgroundExecution_DefaultsToProjectOwnedWithoutExplicitOptIn()
        {
            var config = new XUUnityLightMcpBridgeConfig();

            Assert.That(config.background_execution_enabled, Is.False);
            Assert.That(XUUnityLightMcpBackgroundExecution.ProjectOwnedMode, Is.EqualTo("project_owned"));
            Assert.That(XUUnityLightMcpBackgroundExecution.ManagedMode, Is.EqualTo("managed"));
        }

        [Test]
        public void ProjectActionCurrency_ClassifiesCurrentStaleAndUnknownDomains()
        {
            var current = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-09-03T12:00:00.0000000Z",
                "2026-09-03T11:59:59.0000000Z",
                true,
                "",
                false,
                out var currentFlag,
                out var currentKnown,
                out var currentReason,
                out var currentBasis);
            var stale = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-09-03T12:00:00.0000000Z",
                "2026-09-03T12:00:01.0000000Z",
                true,
                "",
                false,
                out var staleFlag,
                out var staleKnown,
                out var staleReason,
                out var staleBasis);
            var unknown = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "",
                "2026-09-03T12:00:01.0000000Z",
                true,
                "",
                false,
                out var unknownFlag,
                out var unknownKnown,
                out var unknownReason,
                out _);

            Assert.That(current, Is.EqualTo("current"));
            Assert.That(currentFlag, Is.True);
            Assert.That(currentKnown, Is.True);
            Assert.That(currentReason, Is.EqualTo("editor_domain_loaded_after_newest_assets_input"));
            Assert.That(currentBasis, Is.EqualTo("editor_domain_load_vs_newest_assets_editor_input"));
            Assert.That(stale, Is.EqualTo("stale"));
            Assert.That(staleFlag, Is.False);
            Assert.That(staleKnown, Is.True);
            Assert.That(staleReason, Is.EqualTo("assets_editor_input_newer_than_loaded_editor_domain"));
            Assert.That(staleBasis, Is.EqualTo("editor_domain_load_vs_newest_assets_editor_input"));
            Assert.That(unknown, Is.EqualTo("unknown"));
            Assert.That(unknownFlag, Is.False);
            Assert.That(unknownKnown, Is.False);
            Assert.That(unknownReason, Is.EqualTo("editor_domain_load_time_unavailable"));
        }

        [Test]
        public void ProjectActionCurrency_ConvergesAfterASettledForcedRefreshButNotOnFailedCompilation()
        {
            var converged = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-09-03T12:00:00.0000000Z",
                "2026-09-03T12:00:01.0000000Z",
                true,
                "2026-09-03T12:00:05.0000000Z",
                false,
                out var convergedFlag,
                out var convergedKnown,
                out var convergedReason,
                out var convergedBasis);
            var touchedAfterRefresh = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-09-03T12:00:00.0000000Z",
                "2026-09-03T12:00:07.0000000Z",
                true,
                "2026-09-03T12:00:05.0000000Z",
                false,
                out var touchedFlag,
                out _,
                out var touchedReason,
                out var touchedBasis);
            var brokenCompilation = XUUnityLightMcpProjectActionCurrency.ClassifyEditorDomainCurrency(
                "2026-09-03T12:00:00.0000000Z",
                "2026-09-03T12:00:01.0000000Z",
                true,
                "2026-09-03T12:00:05.0000000Z",
                true,
                out var brokenFlag,
                out _,
                out var brokenReason,
                out var brokenBasis);

            Assert.That(converged, Is.EqualTo("current"));
            Assert.That(convergedFlag, Is.True);
            Assert.That(convergedKnown, Is.True);
            Assert.That(
                convergedReason,
                Is.EqualTo("settled_forced_asset_refresh_after_newest_assets_input_without_script_reload"));
            Assert.That(
                convergedBasis,
                Is.EqualTo("settled_forced_asset_refresh_covers_newest_assets_editor_input"));
            Assert.That(touchedAfterRefresh, Is.EqualTo("stale"));
            Assert.That(touchedFlag, Is.False);
            Assert.That(touchedReason, Is.EqualTo("assets_editor_input_newer_than_loaded_editor_domain"));
            Assert.That(touchedBasis, Is.EqualTo("editor_domain_load_vs_newest_assets_editor_input"));
            Assert.That(brokenCompilation, Is.EqualTo("stale"));
            Assert.That(brokenFlag, Is.False);
            Assert.That(
                brokenReason,
                Is.EqualTo("assets_editor_input_newer_than_loaded_editor_domain_with_failed_script_compilation"));
            Assert.That(brokenBasis, Is.EqualTo("editor_domain_load_vs_newest_assets_editor_input"));
        }

        [Test]
        public void ProjectActionCurrency_SkipsUnityIgnoredEntriesWhenScanningEditorInputs()
        {
            Assert.That(XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName("Samples~"), Is.True);
            Assert.That(XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName(".git"), Is.True);
            Assert.That(XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName("CVS"), Is.True);
            Assert.That(XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName("Scripts"), Is.False);
            Assert.That(XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName("Board.cs"), Is.False);

            var scanRoot = Path.Combine(Path.GetTempPath(), "XUUnityMcpCurrencyScan" + Guid.NewGuid().ToString("N"));
            var ignoredDirectory = Path.Combine(scanRoot, "Samples~");
            var importedDirectory = Path.Combine(scanRoot, "Scripts");
            try
            {
                Directory.CreateDirectory(ignoredDirectory);
                Directory.CreateDirectory(importedDirectory);
                var importedScript = Path.Combine(importedDirectory, "Imported.cs");
                var ignoredScript = Path.Combine(ignoredDirectory, "Ignored.cs");
                File.WriteAllText(importedScript, "// imported");
                File.WriteAllText(ignoredScript, "// ignored");
                File.SetLastWriteTimeUtc(importedScript, new DateTime(2026, 9, 3, 12, 0, 0, DateTimeKind.Utc));
                File.SetLastWriteTimeUtc(ignoredScript, new DateTime(2026, 9, 4, 12, 0, 0, DateTimeKind.Utc));

                var scanned = XUUnityLightMcpProjectActionCurrency.TryFindNewestEditorInput(
                    scanRoot,
                    out var newestPath,
                    out var newestWriteUtc,
                    out var inputCount,
                    out var scanError);

                Assert.That(scanned, Is.True);
                Assert.That(scanError, Is.Empty);
                Assert.That(inputCount, Is.EqualTo(1));
                Assert.That(newestPath, Does.EndWith("Imported.cs"));
                Assert.That(newestWriteUtc, Does.StartWith("2026-09-03T12:00:00"));
            }
            finally
            {
                if (Directory.Exists(scanRoot))
                {
                    Directory.Delete(scanRoot, true);
                }
            }
        }

        [Test]
        public void ProjectActionCurrencyOperation_ResolvesFreshAssetsContractWithoutRefreshing()
        {
            var catalogPath = WriteTemporaryProjectActionCatalog(true);
            try
            {
                var response = new XUUnityLightMcpProjectActionCurrencyOperation().Execute(new XUUnityLightMcpRequest
                {
                    request_id = "project-action-currency-selftest",
                    operation = "unity.project_action.currency",
                    args_json = JsonUtility.ToJson(new XUUnityLightMcpProjectActionCurrencyArgs
                    {
                        actionId = "localization.scan",
                        catalogPath = catalogPath,
                    }),
                });
                var payload = JsonUtility.FromJson<XUUnityLightMcpProjectActionCurrencyPayload>(response.payload_json);

                Assert.That(response.status, Is.EqualTo("ok"));
                Assert.That(payload.action_id, Is.EqualTo("localization.scan"));
                Assert.That(payload.catalog_path, Is.EqualTo(catalogPath));
                Assert.That(payload.requires_fresh_assets, Is.True);
                Assert.That(payload.asset_refresh_performed, Is.False);
                Assert.That(payload.safe_to_invoke, Is.False);
                Assert.That(payload.reason, Is.EqualTo("catalog_requires_fresh_assets_without_completed_refresh"));
                Assert.That(payload.recommended_next_action, Is.EqualTo("run_automatic_project_refresh_before_invoking"));
                Assert.That(payload.application_run_in_background, Is.EqualTo(Application.runInBackground));
                Assert.That(payload.native_autofocus_enabled, Is.False);
                Assert.That(payload.background_execution_mode, Is.EqualTo(XUUnityLightMcpBackgroundExecution.Mode));
            }
            finally
            {
                File.Delete(catalogPath);
            }
        }

        [Test]
        public void PlayModeStateOperation_ReportsLivenessFieldsInEditMode()
        {
            var payload = XUUnityLightMcpPlayModeStateOperation.BuildPayload();

            Assert.That(payload.playmode_state, Is.EqualTo("edit"));
            Assert.That(payload.playmode_loop_liveness, Is.EqualTo("not_playing"));
            Assert.That(payload.playmode_frame_count, Is.GreaterThanOrEqualTo(0));
            Assert.That(payload.playmode_frames_advanced_last_interval, Is.GreaterThanOrEqualTo(0));
            Assert.That(payload.playmode_liveness_warning, Is.Empty);
        }

        [Test]
        public void LivenessEvidence_WithoutPopulationClaimsNoTrustClass()
        {
            Assert.That(new XUUnityLightMcpPlayModeStatePayload().result_trust_class, Is.Empty);
            Assert.That(new XUUnityLightMcpScenarioStepResult().result_trust_class, Is.Empty);
            Assert.That(new XUUnityLightMcpUiClickPayload().result_trust_class, Is.Empty);
            Assert.That(
                JsonUtility.FromJson<XUUnityLightMcpScenarioStepResult>("{\"stepId\":\"legacy\"}").result_trust_class,
                Is.Empty);

            var populated = new XUUnityLightMcpScenarioStepResult();
            XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(populated);

            Assert.That(populated.result_trust_class, Is.EqualTo("editor_truth_confirmed"));
        }

        [Test]
        public void PlayModeLivenessTracker_ResolvesLivenessFromStateAndFrameEvidence()
        {
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("edit", false, 0), Is.EqualTo("not_playing"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("transitioning", true, 120), Is.EqualTo("not_playing"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("paused", true, 0), Is.EqualTo("paused"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("playing", false, 0), Is.EqualTo("unknown"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("playing", true, 0), Is.EqualTo("throttled"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("playing", true, 1), Is.EqualTo("throttled"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("playing", true, 2), Is.EqualTo("advancing"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveLiveness("playing", true, 120), Is.EqualTo("advancing"));
        }

        [Test]
        public void PlayModeLivenessTracker_WarnsWhenThrottledOrUnprovenAndNamesFocusTheft()
        {
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("throttled", false),
                Is.EqualTo("playmode_throttled_editor_unfocused"));
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("throttled", true),
                Is.EqualTo("playmode_throttled"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("advancing", false), Is.Empty);
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("not_playing", false), Is.Empty);
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("unknown", false),
                Is.EqualTo(XUUnityLightMcpPlayModeLivenessTracker.UnprovenUnfocusedWarning));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveWarning("unknown", true), Is.Empty);
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation("playmode_throttled_editor_unfocused"),
                Is.EqualTo("focus_the_unity_editor_or_set_interaction_mode_to_no_throttling"));
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation("playmode_throttled"),
                Is.EqualTo("focus_the_unity_editor_or_set_interaction_mode_to_no_throttling"));
            Assert.That(
                XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation(
                    XUUnityLightMcpPlayModeLivenessTracker.UnprovenUnfocusedWarning),
                Is.EqualTo("wait_for_playmode_liveness_sample_and_retry"));
            Assert.That(XUUnityLightMcpPlayModeLivenessTracker.ResolveRemediation(""), Is.Empty);
        }

        [Test]
        public void MutationDeltaBuilder_ProducesTheSharedEvidenceContract()
        {
            var delta = XUUnityLightMcpMutationDelta.Create("prefab", "Assets/UI/Menu.prefab", 3, 4, 2, 1, 1);

            Assert.That(delta.schema_version, Is.EqualTo(XUUnityLightMcpMutationDelta.SchemaVersion));
            Assert.That(delta.unit, Is.EqualTo("prefab"));
            Assert.That(delta.target, Is.EqualTo("Assets/UI/Menu.prefab"));
            Assert.That(delta.before_count, Is.EqualTo(3));
            Assert.That(delta.after_count, Is.EqualTo(4));
            Assert.That(delta.added_count, Is.EqualTo(2));
            Assert.That(delta.removed_count, Is.EqualTo(1));
            Assert.That(delta.changed_count, Is.EqualTo(1));
        }

        [Test]
        public void MutationDeltaBuilder_RejectsAnInconsistentCountInvariant()
        {
            Assert.Throws<ArgumentException>(() =>
                XUUnityLightMcpMutationDelta.Create("prefab", "Assets/UI/Menu.prefab", 3, 5, 1, 0, 0));
        }

        [Test]
        public void TestConsolePressure_CountsErrorsAfterTheRequestBaseline()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                console_error_count_at_request_start = 17,
                console_error_counter_session_id_at_request_start = "current-domain"
            };

            XUUnityLightMcpTestRunState.ResolveConsoleErrorPressure(
                state,
                19,
                "current-domain",
                out var count,
                out var trustClass);
            Assert.That(count, Is.EqualTo(2));
            Assert.That(trustClass, Is.EqualTo("complete_since_request_start"));
        }

        [Test]
        public void TestConsolePressure_DowngradesToALowerBoundAfterDomainReload()
        {
            var state = new XUUnityLightMcpPersistedTestRunState
            {
                console_error_count_at_request_start = 999,
                console_error_counter_session_id_at_request_start = "previous-domain"
            };

            XUUnityLightMcpTestRunState.ResolveConsoleErrorPressure(
                state,
                4,
                "current-domain",
                out var count,
                out var trustClass);

            Assert.That(count, Is.EqualTo(4));
            Assert.That(trustClass, Is.EqualTo("lower_bound_after_domain_reload"));
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
                Assert.That(args.scenario.steps.Count, Is.EqualTo(2));
                Assert.That(args.scenario.steps[0].kind, Is.EqualTo("project_action_currency"));
                Assert.That(args.scenario.steps[0].stepId, Is.EqualTo("scan__currency"));
                Assert.That(args.scenario.steps[1].kind, Is.EqualTo("project_defined_hook"));
                Assert.That(args.scenario.steps[1].hookName, Is.EqualTo("sample.localization"));
                CollectionAssert.AreEqual(new[] { "scan__currency" }, args.scenario.steps[1].dependsOn);
                Assert.That(args.scenario.steps[1].hookPayloadJson, Does.Contain("\"action\":\"localization.scan\""));
                Assert.That(args.scenario.steps[1].hookPayloadJson, Does.Contain("\"target_language\":\"pt-BR\""));
            }
            finally
            {
                File.Delete(catalogPath);
            }
        }

        [Test]
        public void ScenarioProjectActionNormalizer_AutomaticallyRefreshesFreshAssetActions()
        {
            var catalogPath = WriteTemporaryProjectActionCatalog(true);
            try
            {
                var argsJson = "{\"scenario\":{\"name\":\"fresh_assets\",\"steps\":[{\"stepId\":\"scan\",\"kind\":\"project_action\",\"actionId\":\"localization.scan\",\"allowMutating\":true,\"dependsOn\":[\"prepare\"],\"runIfStepPassed\":[\"prepare\"],\"payload\":{}}]}}";

                var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                    argsJson,
                    catalogPath,
                    out var normalizedArgsJson,
                    out var errorCode,
                    out var errorMessage);

                Assert.That(normalized, Is.True, $"{errorCode}: {errorMessage}");
                var args = JsonUtility.FromJson<XUUnityLightMcpScenarioValidateArgs>(normalizedArgsJson);
                Assert.That(args.scenario.steps.Count, Is.EqualTo(3));
                var refresh = args.scenario.steps[0];
                var currency = args.scenario.steps[1];
                var hook = args.scenario.steps[2];
                Assert.That(refresh.kind, Is.EqualTo("project_refresh"));
                Assert.That(refresh.stepId, Is.EqualTo("scan__refresh_assets"));
                Assert.That(refresh.forceAssetRefresh, Is.True);
                Assert.That(refresh.resolvePackages, Is.False);
                Assert.That(refresh.rerunHealthProbe, Is.False);
                Assert.That(refresh.timeoutSeconds, Is.EqualTo(180.0d));
                CollectionAssert.AreEqual(new[] { "prepare" }, refresh.dependsOn);
                CollectionAssert.AreEqual(new[] { "prepare" }, refresh.runIfStepPassed);
                Assert.That(currency.kind, Is.EqualTo("project_action_currency"));
                Assert.That(currency.actionId, Is.EqualTo("localization.scan"));
                Assert.That(currency.requiresFreshAssets, Is.True);
                Assert.That(currency.assetRefreshStepId, Is.EqualTo("scan__refresh_assets"));
                CollectionAssert.AreEqual(new[] { "scan__refresh_assets" }, currency.dependsOn);
                Assert.That(hook.kind, Is.EqualTo("project_defined_hook"));
                Assert.That(hook.stepId, Is.EqualTo("scan"));
                CollectionAssert.AreEqual(new[] { "scan__currency" }, hook.dependsOn);
                Assert.That(hook.runIfStepPassed, Is.Null);
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
        public void ScenarioProjectActionNormalizer_PromotesPlainHookObjectPayload()
        {
            var argsJson = "{\"scenario\":{\"name\":\"plain_hook\",\"steps\":[{\"kind\":\"project_defined_hook\",\"hookName\":\"example.ui_smoke\",\"payload\":{\"action\":\"apply\",\"profile\":\"dev\"}}]}}";

            var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                argsJson,
                out var normalizedArgsJson,
                out var errorCode,
                out var errorMessage);

            Assert.That(normalized, Is.True, $"{errorCode}: {errorMessage}");
            var args = JsonUtility.FromJson<XUUnityLightMcpScenarioValidateArgs>(normalizedArgsJson);
            Assert.That(args.scenario.steps[0].hookPayloadJson, Does.Contain("\"action\":\"apply\""));
            Assert.That(args.scenario.steps[0].hookPayloadJson, Does.Contain("\"profile\":\"dev\""));
        }

        [Test]
        public void ScenarioProjectActionNormalizer_RejectsAmbiguousPlainHookPayloadAliases()
        {
            var argsJson = "{\"scenario\":{\"name\":\"plain_hook\",\"steps\":[{\"kind\":\"project_defined_hook\",\"hookName\":\"example.ui_smoke\",\"payload\":{\"action\":\"apply\"},\"hookPayloadJson\":\"{}\"}]}}";

            var normalized = XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                argsJson,
                out _,
                out var errorCode,
                out _);

            Assert.That(normalized, Is.False);
            Assert.That(errorCode, Is.EqualTo("project_hook_payload_ambiguous"));
        }

        [Test]
        public void ScenarioValidation_ReportsFirstCauseInline()
        {
            var validation = new XUUnityLightMcpScenarioValidatePayload
            {
                status = "invalid",
                error_count = 2,
                issues = new List<XUUnityLightMcpScenarioIssue>
                {
                    new()
                    {
                        code = "hook_not_found",
                        message = "No scenario hook registered as 'example.missing'.",
                        stepId = "vendor_gate",
                    },
                },
            };

            var message = XUUnityLightMcpScenarioRunOperation.BuildValidationErrorMessage(validation);
            Assert.That(message, Does.Contain("hook_not_found"));
            Assert.That(message, Does.Contain("example.missing"));
            Assert.That(message, Does.Contain("step 'vendor_gate'"));
            Assert.That(message, Does.Contain("1 additional validation error"));
        }

        [Test]
        public void ScenarioHookDiagnostic_NamesConstrainedAssemblyAndActiveDefines()
        {
            var message = XUUnityLightMcpScenarioHookExecutor.FormatConstrainedHookDiagnostic(
                "example.vendor",
                "Example.Editor.Vendor",
                new[] { "EXAMPLE_DEV_BUILD" },
                "UNITY_EDITOR;RELEASE_STORE");

            Assert.That(message, Does.Contain("example.vendor"));
            Assert.That(message, Does.Contain("Example.Editor.Vendor"));
            Assert.That(message, Does.Contain("EXAMPLE_DEV_BUILD"));
            Assert.That(message, Does.Contain("RELEASE_STORE"));
            Assert.That(message, Does.Contain("Apply a profile"));
        }

        [Test]
        public void ScenarioValidator_EnforcesApplyThenGateAndRejectsRefresh()
        {
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "invalid_profile_settle",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "apply_profile",
                        kind = "project_defined_hook",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        mutationSettlePolicy = "apply_then_gate",
                    },
                    new() { stepId = "refresh", kind = "project_refresh" },
                    new() { stepId = "status", kind = "status" },
                    new() { stepId = "compile", kind = "compile_player_scripts", target = "Android" },
                },
            };

            var validation = XUUnityLightMcpScenarioRunner.Validate(scenario);
            Assert.That(validation.status, Is.EqualTo("invalid"));
            Assert.That(validation.issues.Exists(issue => issue.code == "project_refresh_after_profile_mutation_forbidden"), Is.True);
            Assert.That(validation.issues.Exists(issue => issue.code == "apply_then_gate_sequence_required"), Is.True);
        }

        [Test]
        public void ScenarioValidator_AcceptsWaitStatusCompileAfterProfileMutation()
        {
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "valid_profile_settle",
                steps = new List<XUUnityLightMcpScenarioStepDefinition>
                {
                    new()
                    {
                        stepId = "apply_profile",
                        kind = "project_defined_hook",
                        hookName = XUUnityLightMcpSyntheticPollUntilHook.Name,
                        mutationSettlePolicy = "apply_then_gate",
                    },
                    new() { stepId = "settle", kind = "wait", durationSeconds = 1.0d },
                    new() { stepId = "status", kind = "status" },
                    new() { stepId = "compile", kind = "compile_player_scripts", target = "Android" },
                },
            };

            var validation = XUUnityLightMcpScenarioRunner.Validate(scenario);
            Assert.That(validation.status, Is.EqualTo("valid"), string.Join("\n", validation.issues.ConvertAll(issue => issue.message)));
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
        public void ScenarioRunner_PollUntilContinuesByDefaultWhenContinueWhenIsOmitted()
        {
            XUUnityLightMcpSyntheticPollUntilHook.Reset("passed_after_two_running_polls");
            var scenario = new XUUnityLightMcpScenarioDefinition
            {
                name = "synthetic_poll_until_default_continue",
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
                        intervalSeconds = 0.0d,
                        timeoutSeconds = 5.0d,
                    },
                },
            };

            var queued = XUUnityLightMcpScenarioRunner.QueueRun(scenario);
            TickScenarioUntilIdle();

            Assert.That(XUUnityLightMcpScenarioRunner.TryReadResult(queued.run_id, "", out var payload, out var errorCode, out var errorMessage), Is.True, $"{errorCode}: {errorMessage}");
            Assert.That(payload.status, Is.EqualTo("passed"));
            Assert.That(payload.steps[0].poll_count, Is.EqualTo(3));
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

        static string WriteTemporaryProjectActionCatalog(bool requiresFreshAssets = false)
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
                + (requiresFreshAssets ? "    requiresFreshAssets: true\n" : "")
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
