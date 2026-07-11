using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpBuildPlayerOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.build_player";

        [Serializable]
        sealed class BuildPlayerArgs
        {
            public string buildTarget = "";
            public string outputPath = "";
            public string resultFile = "";
            public string[] scenePaths = Array.Empty<string>();
            public string[] buildOptions = Array.Empty<string>();
        }

        [Serializable]
        sealed class BuildPlayerResult
        {
            public string action = "unity_build_player";
            public string operation = "unity.build_player";
            public string validation_evidence = "unity_gui";
            public string project_root = "";
            public string requested_build_target = "";
            public string previous_build_target = "";
            public string active_build_target = "";
            public string active_build_target_group = "";
            public bool target_support_loaded;
            public bool restored_previous_build_target;
            public string restore_previous_build_target_error = "";
            public string output_path = "";
            public string output_directory = "";
            public bool used_default_output_path;
            public string[] scene_paths = Array.Empty<string>();
            public string[] build_options = Array.Empty<string>();
            public string outcome = "";
            public string build_result = "";
            public string top_actionable_error = "";
            public string exception_message = "";
            public string started_at_utc = "";
            public string completed_at_utc = "";
            public double duration_seconds;
            public bool succeeded;
            public int total_errors;
            public int total_warnings;
            public ulong total_size_bytes;
        }

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var startedAtUtc = DateTime.UtcNow;
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new BuildPlayerArgs()
                : JsonUtility.FromJson<BuildPlayerArgs>(request.args_json) ?? new BuildPlayerArgs();
            var result = new BuildPlayerResult
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                started_at_utc = startedAtUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                requested_build_target = args.buildTarget ?? "",
                build_result = "NotStarted",
                outcome = "gui_build_failed"
            };

            try
            {
                ExecuteBuild(args, result);
            }
            catch (Exception ex)
            {
                result.build_result = "Exception";
                result.top_actionable_error = string.IsNullOrWhiteSpace(ex.Message) ? "GUI build failed." : ex.Message;
                result.exception_message = string.IsNullOrWhiteSpace(ex.Message) ? "GUI build failed." : ex.Message;
                result.succeeded = false;
                result.outcome = "gui_build_failed";
                Debug.LogException(ex);
            }
            finally
            {
                result.completed_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
                result.duration_seconds = Math.Round((DateTime.UtcNow - startedAtUtc).TotalSeconds, 6);
                PersistResult(args.resultFile, result);
            }

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(result)
            );
        }

        static void ExecuteBuild(BuildPlayerArgs args, BuildPlayerResult result)
        {
            if (EditorApplication.isCompiling || EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isUpdating)
            {
                throw new InvalidOperationException(
                    $"Unity editor is busy. isCompiling={EditorApplication.isCompiling}, " +
                    $"isPlayingOrWillChangePlaymode={EditorApplication.isPlayingOrWillChangePlaymode}, " +
                    $"isUpdating={EditorApplication.isUpdating}");
            }

            var targetText = (args.buildTarget ?? "").Trim();
            if (string.IsNullOrWhiteSpace(targetText))
            {
                throw new InvalidOperationException("buildTarget is required.");
            }

            if (!Enum.TryParse(targetText, true, out BuildTarget target))
            {
                throw new InvalidOperationException($"Unknown Unity BuildTarget '{targetText}'.");
            }

            var targetGroup = BuildPipeline.GetBuildTargetGroup(target);
            if (targetGroup == BuildTargetGroup.Unknown)
            {
                throw new InvalidOperationException($"Unsupported Unity BuildTarget '{target}'.");
            }

            var targetSupportLoaded = XUUnityLightMcpBuildTargetGetOperation.IsPlatformSupportLoaded(target);
            result.target_support_loaded = targetSupportLoaded;
            if (!targetSupportLoaded)
            {
                throw new InvalidOperationException($"Platform support is not loaded for Unity BuildTarget '{target}'.");
            }

            var previousTarget = EditorUserBuildSettings.activeBuildTarget;
            var previousTargetGroup = BuildPipeline.GetBuildTargetGroup(previousTarget);
            result.previous_build_target = previousTarget.ToString();
            try
            {
                if (previousTarget != target)
                {
                    var switched = EditorUserBuildSettings.SwitchActiveBuildTarget(targetGroup, target);
                    if (!switched)
                    {
                        throw new InvalidOperationException($"Unity failed to switch the active build target to '{target}'.");
                    }
                }

                result.active_build_target = EditorUserBuildSettings.activeBuildTarget.ToString();
                result.active_build_target_group = BuildPipeline.GetBuildTargetGroup(EditorUserBuildSettings.activeBuildTarget).ToString();
                if (EditorUserBuildSettings.activeBuildTarget != target)
                {
                    throw new InvalidOperationException(
                        $"Unity did not settle on requested build target '{target}'. Current target is '{EditorUserBuildSettings.activeBuildTarget}'.");
                }

                var scenePaths = ResolveScenePaths(args.scenePaths);
                var outputPath = ResolveOutputPath(target, args.outputPath, out var usedDefaultOutputPath);
                var buildOptions = ParseBuildOptions(args.buildOptions);
                var previousExportAsGoogleAndroidProject = EditorUserBuildSettings.exportAsGoogleAndroidProject;
                var shouldExportAndroidProject =
                    target == BuildTarget.Android &&
                    buildOptions.HasFlag(BuildOptions.AcceptExternalModificationsToPlayer);

                result.scene_paths = scenePaths.ToArray();
                result.output_path = outputPath;
                result.output_directory = ResolveOutputDirectory(target, outputPath);
                result.used_default_output_path = usedDefaultOutputPath;
                result.build_options = NormalizeBuildOptionNames(buildOptions);

                Directory.CreateDirectory(result.output_directory);

                var buildPlayerOptions = new BuildPlayerOptions
                {
                    scenes = scenePaths.ToArray(),
                    target = target,
                    locationPathName = outputPath,
                    options = buildOptions
                };

                BuildReport report;
                try
                {
                    if (target == BuildTarget.Android)
                    {
                        EditorUserBuildSettings.exportAsGoogleAndroidProject = shouldExportAndroidProject;
                    }

                    report = BuildPipeline.BuildPlayer(buildPlayerOptions);
                }
                finally
                {
                    if (target == BuildTarget.Android)
                    {
                        EditorUserBuildSettings.exportAsGoogleAndroidProject = previousExportAsGoogleAndroidProject;
                    }
                }

                var summary = report.summary;
                result.build_result = summary.result.ToString();
                result.total_errors = summary.totalErrors;
                result.total_warnings = summary.totalWarnings;
                result.total_size_bytes = summary.totalSize;
                result.succeeded = summary.result == BuildResult.Succeeded;
                result.outcome = result.succeeded ? "gui_build_completed" : "gui_build_failed";
                if (!result.succeeded)
                {
                    result.top_actionable_error = summary.totalErrors > 0
                        ? $"Unity BuildPipeline reported {summary.totalErrors} error(s)."
                        : $"Unity BuildPipeline returned '{summary.result}'.";
                }
            }
            finally
            {
                if (previousTarget != target && previousTargetGroup != BuildTargetGroup.Unknown)
                {
                    try
                    {
                        result.restored_previous_build_target = EditorUserBuildSettings.SwitchActiveBuildTarget(previousTargetGroup, previousTarget);
                    }
                    catch (Exception ex)
                    {
                        result.restore_previous_build_target_error = ex.Message;
                    }
                }
                else
                {
                    result.restored_previous_build_target = true;
                }
            }
        }

        static List<string> ResolveScenePaths(string[] requestedScenePaths)
        {
            var explicitScenePaths = (requestedScenePaths ?? Array.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(NormalizeScenePath)
                .Distinct(StringComparer.Ordinal)
                .ToList();

            if (explicitScenePaths.Count > 0)
            {
                foreach (var scenePath in explicitScenePaths)
                {
                    if (!File.Exists(scenePath) && !File.Exists(Path.GetFullPath(scenePath)))
                    {
                        throw new FileNotFoundException($"Requested scene path was not found: {scenePath}");
                    }
                }

                return explicitScenePaths;
            }

            var enabledScenes = EditorBuildSettings.scenes
                .Where(scene => scene != null && scene.enabled && !string.IsNullOrWhiteSpace(scene.path))
                .Select(scene => scene.path)
                .ToList();

            if (enabledScenes.Count == 0)
            {
                throw new InvalidOperationException("No enabled EditorBuildSettings scenes were found.");
            }

            return enabledScenes;
        }

        static string NormalizeScenePath(string rawValue)
        {
            var trimmed = (rawValue ?? "").Trim();
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                return trimmed;
            }

            if (!Path.IsPathRooted(trimmed))
            {
                return trimmed;
            }

            var projectRoot = Path.GetFullPath(XUUnityLightMcpFileIpcPaths.ProjectRootPath);
            var fullPath = Path.GetFullPath(trimmed);
            if (!fullPath.StartsWith(projectRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) &&
                !string.Equals(fullPath, projectRoot, StringComparison.Ordinal))
            {
                return fullPath;
            }

            var relativePath = Path.GetRelativePath(projectRoot, fullPath);
            return relativePath.Replace(Path.DirectorySeparatorChar, '/');
        }

        static string ResolveOutputPath(BuildTarget target, string requestedOutputPath, out bool usedDefaultOutputPath)
        {
            var outputPath = (requestedOutputPath ?? "").Trim();
            if (!string.IsNullOrWhiteSpace(outputPath))
            {
                usedDefaultOutputPath = false;
                return Path.GetFullPath(outputPath);
            }

            usedDefaultOutputPath = true;
            var sanitizedProductName = SanitizeFileComponent(string.IsNullOrWhiteSpace(PlayerSettings.productName)
                ? "UnityPlayer"
                : PlayerSettings.productName);
            return Path.GetFullPath(GetDefaultOutputPath(target, sanitizedProductName));
        }

        static string GetDefaultOutputPath(BuildTarget target, string sanitizedProductName)
        {
            var outputDirectory = Path.Combine("Builds", target.ToString());
            return target switch
            {
                BuildTarget.Android => Path.Combine(
                    outputDirectory,
                    $"{sanitizedProductName}.{(EditorUserBuildSettings.buildAppBundle ? "aab" : "apk")}"),
                BuildTarget.iOS => Path.Combine(outputDirectory, sanitizedProductName),
                BuildTarget.WebGL => Path.Combine(outputDirectory, sanitizedProductName),
                BuildTarget.StandaloneWindows => Path.Combine(outputDirectory, $"{sanitizedProductName}.exe"),
                BuildTarget.StandaloneWindows64 => Path.Combine(outputDirectory, $"{sanitizedProductName}.exe"),
                BuildTarget.StandaloneOSX => Path.Combine(outputDirectory, $"{sanitizedProductName}.app"),
                BuildTarget.StandaloneLinux64 => Path.Combine(outputDirectory, sanitizedProductName),
                _ => Path.Combine(outputDirectory, sanitizedProductName)
            };
        }

        static string ResolveOutputDirectory(BuildTarget target, string outputPath)
        {
            return target switch
            {
                BuildTarget.iOS => outputPath,
                BuildTarget.WebGL => outputPath,
                _ => Path.GetDirectoryName(outputPath) ?? Path.GetFullPath(".")
            };
        }

        static BuildOptions ParseBuildOptions(string[] optionNames)
        {
            var options = BuildOptions.None;
            foreach (var optionName in optionNames ?? Array.Empty<string>())
            {
                var trimmed = (optionName ?? "").Trim();
                if (string.IsNullOrWhiteSpace(trimmed))
                {
                    continue;
                }

                if (!Enum.TryParse(trimmed, true, out BuildOptions parsed))
                {
                    throw new InvalidOperationException($"Unknown Unity BuildOptions flag '{trimmed}'.");
                }

                options |= parsed;
            }

            return options;
        }

        static string[] NormalizeBuildOptionNames(BuildOptions options)
        {
            if (options == BuildOptions.None)
            {
                return Array.Empty<string>();
            }

            return Enum.GetValues(typeof(BuildOptions))
                .Cast<BuildOptions>()
                .Where(value => value != BuildOptions.None && options.HasFlag(value))
                .Select(value => value.ToString())
                .ToArray();
        }

        static void PersistResult(string resultFile, BuildPlayerResult result)
        {
            if (string.IsNullOrWhiteSpace(resultFile))
            {
                return;
            }

            var resolvedPath = Path.GetFullPath(resultFile);
            Directory.CreateDirectory(Path.GetDirectoryName(resolvedPath) ?? ".");
            XUUnityLightMcpAtomicFileWriter.WriteAllText(resolvedPath, JsonUtility.ToJson(result, true));
        }

        static string SanitizeFileComponent(string value)
        {
            var text = (value ?? "").Trim();
            if (string.IsNullOrWhiteSpace(text))
            {
                return "UnityPlayer";
            }

            foreach (var invalidChar in Path.GetInvalidFileNameChars())
            {
                text = text.Replace(invalidChar, '_');
            }

            return text.Replace(' ', '_');
        }
    }
}
