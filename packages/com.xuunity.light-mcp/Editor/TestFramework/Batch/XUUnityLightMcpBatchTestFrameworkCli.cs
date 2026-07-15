using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.TestTools.TestRunner.Api;
using UnityEngine;
using UnityEngine.SceneManagement;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Batch
{
    public static class XUUnityLightMcpBatchTestFrameworkCli
    {
        const string ResultFileArg = "--xuunity-result-file";
        const string TestNameArg = "--xuunity-test-name";
        const string GroupNameArg = "--xuunity-group-name";
        const string CategoryNameArg = "--xuunity-category-name";
        const string AssemblyNameArg = "--xuunity-assembly-name";

        [Serializable]
        sealed class BatchTestArgs
        {
            public string resultFile = "";
            public string[] testNames = Array.Empty<string>();
            public string[] groupNames = Array.Empty<string>();
            public string[] categoryNames = Array.Empty<string>();
            public string[] assemblyNames = Array.Empty<string>();
        }

        [Serializable]
        sealed class BatchTestResult
        {
            public string action = "batch_validation";
            public string operation = "editmode-tests";
            public string project_root = "";
            public string validation_evidence = "unity_batchmode";
            public string outcome = "batch_validation_failed";
            public bool succeeded;
            public string top_actionable_error = "";
            public string exception_message = "";
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public double duration_seconds;
            public XUUnityLightMcpTestsPayload tests;
        }

        static BatchTestArgs _activeArgs;
        static BatchTestResult _activeResult;
        static DateTime _startedAtUtc;

        public static void ExecuteFromCommandLine()
        {
            _startedAtUtc = DateTime.UtcNow;
            var args = new BatchTestArgs();
            var result = new BatchTestResult
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                started_at_utc = _startedAtUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"),
            };
            var awaitAsyncCompletion = false;
            var exitCode = 1;

            try
            {
                args = ParseArgs(Environment.GetCommandLineArgs());
                _activeArgs = args;
                _activeResult = result;
                StartEditModeTests(args, result);
                awaitAsyncCompletion = true;
            }
            catch (Exception ex)
            {
                result.exception_message = string.IsNullOrWhiteSpace(ex.Message) ? "Batch EditMode tests failed." : ex.Message;
                result.top_actionable_error = result.exception_message;
                result.succeeded = false;
                result.outcome = "batch_validation_failed";
            }
            finally
            {
                if (!awaitAsyncCompletion)
                {
                    FinalizeAndExit(args, result, exitCode);
                }
            }
        }

        static void StartEditModeTests(BatchTestArgs args, BatchTestResult result)
        {
            if (EditorApplication.isCompiling)
            {
                throw new InvalidOperationException("Unity is currently compiling scripts.");
            }

            if (EditorUtility.scriptCompilationFailed)
            {
                throw new InvalidOperationException("Unity has compilation errors. Resolve them before running EditMode tests.");
            }

            var dirtyScenes = GetDirtyOpenScenes();
            if (dirtyScenes.Count > 0)
            {
                var sceneList = string.Join(", ", dirtyScenes.Select(FormatSceneForMessage));
                throw new InvalidOperationException($"Cannot run EditMode tests while open scenes have unsaved changes: {sceneList}");
            }

            if (!TryBuildFilter(args, out var filter, out var filterSummary, out var filterRequested, out var errorMessage))
            {
                throw new InvalidOperationException(errorMessage);
            }

            var api = ScriptableObject.CreateInstance<TestRunnerApi>();
            var callbacks = new BatchEditModeCallbacks(OnEditModeTestsCompleted);
            callbacks.Begin(result.project_root, filterSummary, filterRequested);
            api.RegisterCallbacks(callbacks);
            api.Execute(new ExecutionSettings(filter));
        }

        static void OnEditModeTestsCompleted(XUUnityLightMcpTestsPayload payload)
        {
            _activeResult.tests = payload;
            _activeResult.succeeded = payload.status == "passed";
            _activeResult.outcome = _activeResult.succeeded ? "batch_validation_completed" : "batch_validation_failed";
            _activeResult.top_actionable_error = FirstTestFailure(payload);
            FinalizeAndExit(_activeArgs, _activeResult, _activeResult.succeeded ? 0 : 1);
        }

        static BatchTestArgs ParseArgs(string[] rawArgs)
        {
            var args = new BatchTestArgs();
            var testNames = new List<string>();
            var groupNames = new List<string>();
            var categoryNames = new List<string>();
            var assemblyNames = new List<string>();

            for (var i = 0; i < rawArgs.Length; i++)
            {
                var current = rawArgs[i] ?? "";
                switch (current)
                {
                    case ResultFileArg:
                        args.resultFile = RequireValue(rawArgs, ref i, ResultFileArg);
                        break;
                    case TestNameArg:
                        testNames.Add(RequireValue(rawArgs, ref i, TestNameArg));
                        break;
                    case GroupNameArg:
                        groupNames.Add(RequireValue(rawArgs, ref i, GroupNameArg));
                        break;
                    case CategoryNameArg:
                        categoryNames.Add(RequireValue(rawArgs, ref i, CategoryNameArg));
                        break;
                    case AssemblyNameArg:
                        assemblyNames.Add(RequireValue(rawArgs, ref i, AssemblyNameArg));
                        break;
                }
            }

            args.testNames = testNames.ToArray();
            args.groupNames = groupNames.ToArray();
            args.categoryNames = categoryNames.ToArray();
            args.assemblyNames = assemblyNames.ToArray();
            return args;
        }

        static string RequireValue(string[] rawArgs, ref int index, string argumentName)
        {
            var valueIndex = index + 1;
            if (valueIndex >= rawArgs.Length || string.IsNullOrWhiteSpace(rawArgs[valueIndex]))
            {
                throw new InvalidOperationException($"{argumentName} requires a value.");
            }

            index = valueIndex;
            return rawArgs[valueIndex];
        }

        static bool TryBuildFilter(
            BatchTestArgs args,
            out Filter filter,
            out string filterSummary,
            out bool filterRequested,
            out string errorMessage)
        {
            filter = new Filter
            {
                testMode = TestMode.EditMode
            };
            filterSummary = "all";
            filterRequested = false;
            errorMessage = "";

            filter.testNames = XUUnityLightMcpTestArgsUtility.NormalizeOptionalStringArray(args.testNames);
            filter.groupNames = XUUnityLightMcpTestArgsUtility.NormalizeOptionalStringArray(args.groupNames);
            filter.categoryNames = XUUnityLightMcpTestArgsUtility.NormalizeOptionalStringArray(args.categoryNames);
            filter.assemblyNames = XUUnityLightMcpTestArgsUtility.NormalizeOptionalStringArray(args.assemblyNames);
            filterRequested = XUUnityLightMcpTestArgsUtility.HasRequestedFilters(
                filter.testNames,
                filter.groupNames,
                filter.categoryNames,
                filter.assemblyNames);
            filterSummary = XUUnityLightMcpTestArgsUtility.BuildFilterSummary(
                filter.testNames,
                filter.groupNames,
                filter.categoryNames,
                filter.assemblyNames);
            XUUnityLightMcpEditModeFilterResolver.ResolveTestNames(filter);
            return true;
        }

        static void FinalizeAndExit(BatchTestArgs args, BatchTestResult result, int exitCode)
        {
            result.completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            result.duration_seconds = Math.Round((DateTime.UtcNow - _startedAtUtc).TotalSeconds, 6);
            PersistResult(args.resultFile, result);
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(exitCode);
            }
        }

        static void PersistResult(string resultFile, BatchTestResult result)
        {
            if (string.IsNullOrWhiteSpace(resultFile))
            {
                return;
            }

            var fullPath = Path.GetFullPath(resultFile);
            var directory = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            XUUnityLightMcpAtomicFileWriter.WriteAllText(fullPath, JsonUtility.ToJson(result, true));
        }

        static List<Scene> GetDirtyOpenScenes()
        {
            var result = new List<Scene>(EditorSceneManager.sceneCount);
            for (var i = 0; i < EditorSceneManager.sceneCount; i++)
            {
                var scene = EditorSceneManager.GetSceneAt(i);
                if (scene.isDirty)
                {
                    result.Add(scene);
                }
            }

            return result;
        }

        static string FormatSceneForMessage(Scene scene)
        {
            var name = string.IsNullOrEmpty(scene.name) ? "(untitled)" : scene.name;
            var path = string.IsNullOrEmpty(scene.path) ? "(unsaved)" : scene.path;
            return $"'{name}' ({path})";
        }

        static string FirstTestFailure(XUUnityLightMcpTestsPayload payload)
        {
            if (payload == null)
            {
                return "";
            }

            var firstFailure = payload.failures == null ? null : payload.failures.FirstOrDefault();
            if (firstFailure != null && !string.IsNullOrWhiteSpace(firstFailure.message))
            {
                return firstFailure.message;
            }

            return payload.status == "passed"
                ? ""
                : $"EditMode tests finished with status '{payload.status}'.";
        }

        sealed class BatchEditModeCallbacks : ICallbacks
        {
            readonly Action<XUUnityLightMcpTestsPayload> _onCompleted;
            readonly List<XUUnityLightMcpTestFailure> _failures = new();

            string _projectRoot = "";
            string _filterSummary = "all";
            bool _filterRequested;
            DateTime _startedAtUtc;
            int _total;
            int _passed;
            int _failed;
            int _skipped;

            public BatchEditModeCallbacks(Action<XUUnityLightMcpTestsPayload> onCompleted)
            {
                _onCompleted = onCompleted ?? throw new ArgumentNullException(nameof(onCompleted));
            }

            public void Begin(string projectRoot, string filterSummary, bool filterRequested)
            {
                _projectRoot = projectRoot ?? "";
                _filterSummary = filterSummary ?? "all";
                _filterRequested = filterRequested;
                _startedAtUtc = DateTime.UtcNow;
                _total = 0;
                _passed = 0;
                _failed = 0;
                _skipped = 0;
                _failures.Clear();
            }

            public void RunStarted(ITestAdaptor testsToRun)
            {
                _total = CountLeafTests(testsToRun);
            }

            public void RunFinished(ITestResultAdaptor result)
            {
                var payload = new XUUnityLightMcpTestsPayload
                {
                    project_root = _projectRoot,
                    total = _total,
                    passed = _passed,
                    failed = _failed,
                    skipped = _skipped,
                    duration_seconds = Math.Round((DateTime.UtcNow - _startedAtUtc).TotalSeconds, 6),
                    failures = new List<XUUnityLightMcpTestFailure>(_failures),
                    filter_summary = _filterSummary,
                    filter_requested = _filterRequested,
                    validation_evidence = "unity_batchmode"
                };

                payload.status = payload.total == 0 && payload.filter_requested
                    ? "test_filter_no_match"
                    : payload.total == 0
                        ? "no_tests"
                    : payload.failed > 0
                            ? "failed"
                            : "passed";
                payload.test_verdict = payload.status;
                payload.recommended_next_action = payload.status == "test_filter_no_match"
                    ? "refresh_project_once_then_retry_same_filter"
                    : "none";
                payload.recommended_recovery_command = payload.status == "test_filter_no_match"
                    ? $"request-project-refresh --project-root \"{_projectRoot}\" --timeout-ms 180000"
                    : "";

                _onCompleted(payload);
            }

            public void TestStarted(ITestAdaptor test)
            {
            }

            public void TestFinished(ITestResultAdaptor result)
            {
                if (result?.Test == null || result.Test.IsSuite)
                {
                    return;
                }

                switch (result.TestStatus)
                {
                    case TestStatus.Passed:
                        _passed++;
                        break;
                    case TestStatus.Failed:
                        _failed++;
                        _failures.Add(new XUUnityLightMcpTestFailure
                        {
                            name = result.Test.FullName ?? result.Test.Name ?? "",
                            message = result.Message ?? ""
                        });
                        break;
                    case TestStatus.Skipped:
                        _skipped++;
                        break;
                }
            }

            static int CountLeafTests(ITestAdaptor test)
            {
                if (test == null)
                {
                    return 0;
                }

                if (test.HasChildren && test.Children != null)
                {
                    return test.Children.Sum(CountLeafTests);
                }

                return test.IsSuite ? 0 : 1;
            }
        }
    }
}
