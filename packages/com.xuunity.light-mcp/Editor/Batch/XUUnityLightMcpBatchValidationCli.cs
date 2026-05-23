using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Batch
{
    public static class XUUnityLightMcpBatchValidationCli
    {
        const string ActionArg = "--xuunity-batch-action";
        const string ResultFileArg = "--xuunity-result-file";
        const string CompileNameArg = "--xuunity-compile-name";
        const string BuildTargetArg = "--xuunity-build-target";
        const string OptionFlagArg = "--xuunity-option-flag";
        const string ExtraDefineArg = "--xuunity-extra-define";
        const string ConfigFileArg = "--xuunity-config-file";
        const string StopOnFirstFailureArg = "--xuunity-stop-on-first-failure";
        const string TestNameArg = "--xuunity-test-name";
        const string GroupNameArg = "--xuunity-group-name";
        const string CategoryNameArg = "--xuunity-category-name";
        const string AssemblyNameArg = "--xuunity-assembly-name";

        [Serializable]
        sealed class BatchValidationArgs
        {
            public string action = "";
            public string resultFile = "";
            public string compileName = "";
            public string buildTarget = "";
            public string configFile = "";
            public bool stopOnFirstFailure;
            public string[] optionFlags = Array.Empty<string>();
            public string[] extraDefines = Array.Empty<string>();
            public string[] testNames = Array.Empty<string>();
            public string[] groupNames = Array.Empty<string>();
            public string[] categoryNames = Array.Empty<string>();
            public string[] assemblyNames = Array.Empty<string>();
        }

        [Serializable]
        sealed class BatchValidationResult
        {
            public string action = "batch_validation";
            public string operation = "";
            public string project_root = "";
            public string validation_evidence = "unity_batchmode";
            public string outcome = "batch_validation_failed";
            public bool succeeded;
            public string top_actionable_error = "";
            public string exception_message = "";
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public double duration_seconds;
            public string compile_name = "";
            public string requested_build_target = "";
            public string config_file = "";
            public XUUnityLightMcpCompilePlayerScriptsPayload compile;
            public XUUnityLightMcpCompileMatrixPayload matrix;
            public XUUnityLightMcpTestsPayload tests;
        }

        static DateTime _startedAtUtc;

        public static void ExecuteFromCommandLine()
        {
            _startedAtUtc = DateTime.UtcNow;
            var args = new BatchValidationArgs();
            var result = new BatchValidationResult
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                started_at_utc = _startedAtUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"),
            };

            var exitCode = 1;

            try
            {
                args = ParseArgs(Environment.GetCommandLineArgs());
                result.operation = args.action ?? "";
                result.compile_name = args.compileName ?? "";
                result.requested_build_target = args.buildTarget ?? "";
                result.config_file = args.configFile ?? "";

                switch ((args.action ?? "").Trim())
                {
                    case "compile-player-scripts":
                        exitCode = ExecuteCompilePlayerScripts(args, result) ? 0 : 1;
                        break;

                    case "compile-matrix":
                        exitCode = ExecuteCompileMatrix(args, result) ? 0 : 1;
                        break;

                    case "editmode-tests":
                        throw new InvalidOperationException(
                            "EditMode batch tests require the optional XUUnity Test Framework capability. " +
                            "Install com.unity.test-framework and run the optional batch test entrypoint.");

                    default:
                        throw new InvalidOperationException($"Unknown batch validation action '{args.action}'.");
                }
            }
            catch (Exception ex)
            {
                result.exception_message = string.IsNullOrWhiteSpace(ex.Message) ? "Batch validation failed." : ex.Message;
                result.top_actionable_error = string.IsNullOrWhiteSpace(ex.Message) ? "Batch validation failed." : ex.Message;
                result.succeeded = false;
                result.outcome = "batch_validation_failed";
            }
            finally
            {
                FinalizeAndExit(args, result, exitCode);
            }
        }

        static bool ExecuteCompilePlayerScripts(BatchValidationArgs args, BatchValidationResult result)
        {
            var compileArgs = new XUUnityLightMcpCompilePlayerScriptsArgs
            {
                name = args.compileName ?? "",
                target = args.buildTarget ?? "",
                optionFlags = NormalizeFilterValues(args.optionFlags),
                extraDefines = NormalizeFilterValues(args.extraDefines)
            };

            var compilePayload = XUUnityLightMcpCompileUtility.Compile(compileArgs);
            result.compile = new XUUnityLightMcpCompilePlayerScriptsPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                request_completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                settled_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                completion_basis = "batchmode",
                settle_phase = "batchmode",
                playmode_state_after_settle = "edit",
                result = compilePayload,
                validation_evidence = "unity_batchmode"
            };

            result.succeeded = compilePayload.status == "passed";
            result.outcome = result.succeeded ? "batch_validation_completed" : "batch_validation_failed";
            result.top_actionable_error = FirstCompileError(compilePayload);
            return result.succeeded;
        }

        static bool ExecuteCompileMatrix(BatchValidationArgs args, BatchValidationResult result)
        {
            var configFile = (args.configFile ?? "").Trim();
            if (string.IsNullOrWhiteSpace(configFile))
            {
                throw new InvalidOperationException($"{ConfigFileArg} is required for compile-matrix.");
            }

            if (!File.Exists(configFile))
            {
                throw new FileNotFoundException($"Compile matrix config file was not found: {configFile}");
            }

            var rawJson = File.ReadAllText(configFile);
            var matrixArgs = JsonUtility.FromJson<XUUnityLightMcpCompileMatrixArgs>(rawJson) ?? new XUUnityLightMcpCompileMatrixArgs();
            if (matrixArgs.configurations == null || matrixArgs.configurations.Count == 0)
            {
                throw new InvalidOperationException("Compile matrix config did not contain any configurations.");
            }

            var startedAtUtc = DateTime.UtcNow;
            var matrixPayload = new XUUnityLightMcpCompileMatrixPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                stop_on_first_failure = matrixArgs.stopOnFirstFailure,
                total = matrixArgs.configurations.Count,
                validation_evidence = "unity_batchmode"
            };

            var results = new List<XUUnityLightMcpCompileConfigPayload>(matrixArgs.configurations.Count);
            var passed = 0;
            var failed = 0;
            var skipped = 0;

            foreach (var configuration in matrixArgs.configurations)
            {
                XUUnityLightMcpCompileConfigPayload compilePayload;
                try
                {
                    compilePayload = XUUnityLightMcpCompileUtility.Compile(configuration);
                }
                catch (Exception ex)
                {
                    compilePayload = new XUUnityLightMcpCompileConfigPayload
                    {
                        name = string.IsNullOrWhiteSpace(configuration?.name) ? configuration?.target ?? "" : configuration.name,
                        target = configuration?.target ?? "",
                        status = "infrastructure_error",
                        errors = new List<XUUnityLightMcpCompileErrorItem>
                        {
                            new XUUnityLightMcpCompileErrorItem
                            {
                                message = ex.Message ?? "Compile matrix configuration failed."
                            }
                        },
                        error_count = 1
                    };
                }

                results.Add(compilePayload);
                switch (compilePayload.status)
                {
                    case "passed":
                        passed++;
                        break;
                    case "target_support_missing":
                        skipped++;
                        break;
                    default:
                        failed++;
                        break;
                }

                if (matrixArgs.stopOnFirstFailure && compilePayload.status != "passed")
                {
                    break;
                }
            }

            matrixPayload.results = results;
            matrixPayload.total = results.Count;
            matrixPayload.passed = passed;
            matrixPayload.failed = failed;
            matrixPayload.skipped = skipped;
            matrixPayload.status = failed > 0 ? "failed" : "passed";
            matrixPayload.request_completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            matrixPayload.settled_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            matrixPayload.completion_basis = "batchmode";
            matrixPayload.settle_phase = "batchmode";
            matrixPayload.playmode_state_after_settle = "edit";
            matrixPayload.duration_seconds = Math.Round((DateTime.UtcNow - startedAtUtc).TotalSeconds, 6);

            result.matrix = matrixPayload;
            result.succeeded = matrixPayload.status == "passed";
            result.outcome = result.succeeded ? "batch_validation_completed" : "batch_validation_failed";
            result.top_actionable_error = FirstCompileError(matrixPayload.results.FirstOrDefault(item => item.status != "passed"));
            return result.succeeded;
        }

        static BatchValidationArgs ParseArgs(string[] rawArgs)
        {
            var args = new BatchValidationArgs();
            var optionFlags = new List<string>();
            var extraDefines = new List<string>();
            var testNames = new List<string>();
            var groupNames = new List<string>();
            var categoryNames = new List<string>();
            var assemblyNames = new List<string>();

            for (var i = 0; i < rawArgs.Length; i++)
            {
                var current = rawArgs[i] ?? "";
                switch (current)
                {
                    case ActionArg:
                        args.action = RequireValue(rawArgs, ref i, ActionArg);
                        break;
                    case ResultFileArg:
                        args.resultFile = RequireValue(rawArgs, ref i, ResultFileArg);
                        break;
                    case CompileNameArg:
                        args.compileName = RequireValue(rawArgs, ref i, CompileNameArg);
                        break;
                    case BuildTargetArg:
                        args.buildTarget = RequireValue(rawArgs, ref i, BuildTargetArg);
                        break;
                    case ConfigFileArg:
                        args.configFile = RequireValue(rawArgs, ref i, ConfigFileArg);
                        break;
                    case OptionFlagArg:
                        optionFlags.Add(RequireValue(rawArgs, ref i, OptionFlagArg));
                        break;
                    case ExtraDefineArg:
                        extraDefines.Add(RequireValue(rawArgs, ref i, ExtraDefineArg));
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
                    case StopOnFirstFailureArg:
                        args.stopOnFirstFailure = true;
                        break;
                }
            }

            args.optionFlags = optionFlags.ToArray();
            args.extraDefines = extraDefines.ToArray();
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

        static void FinalizeAndExit(BatchValidationArgs args, BatchValidationResult result, int exitCode)
        {
            result.completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            result.duration_seconds = Math.Round((DateTime.UtcNow - _startedAtUtc).TotalSeconds, 6);
            PersistResult(args.resultFile, result);
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(exitCode);
            }
        }

        static void PersistResult(string resultFile, BatchValidationResult result)
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

            File.WriteAllText(fullPath, JsonUtility.ToJson(result, true));
        }

        static string[] NormalizeFilterValues(string[] values)
        {
            if (values == null || values.Length == 0)
            {
                return null;
            }

            var normalized = values
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct()
                .ToArray();

            return normalized.Length == 0 ? null : normalized;
        }

        static string FirstCompileError(XUUnityLightMcpCompileConfigPayload payload)
        {
            if (payload == null)
            {
                return "";
            }

            var firstError = payload.errors == null ? null : payload.errors.FirstOrDefault();
            if (firstError != null && !string.IsNullOrWhiteSpace(firstError.message))
            {
                return firstError.message;
            }

            return payload.status == "passed"
                ? ""
                : $"Compile validation finished with status '{payload.status}'.";
        }

    }
}
