using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.Build.Player;
using UnityEditor.Compilation;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpCompileUtility
    {
        const BindingFlags StaticBindings = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static;
        internal const int WarningSampleLimit = 20;

        public static XUUnityLightMcpCompileConfigPayload Compile(XUUnityLightMcpCompilePlayerScriptsArgs args)
        {
            if (args == null)
            {
                throw new XUUnityLightMcpInvalidArgumentsException(
                    "Compile arguments are required: pass at least target=<Unity BuildTarget enum name>, "
                    + "for example StandaloneOSX, StandaloneWindows64, Android, or iOS.");
            }

            // Argument validation is pure and cheap, so it runs before any environment check. Ordering it after
            // the busy guard meant a caller in Play Mode with a bad argument was told to exit Play Mode, and the
            // argument stayed wrong either way.
            if (string.IsNullOrWhiteSpace(args.target))
            {
                throw new XUUnityLightMcpInvalidArgumentsException(
                    "target is required: pass a Unity BuildTarget enum name, for example StandaloneOSX, "
                    + "StandaloneWindows64, Android, or iOS. Nothing was compiled.");
            }

            if (!Enum.TryParse(args.target.Trim(), true, out BuildTarget target))
            {
                throw new XUUnityLightMcpInvalidArgumentsException(
                    $"target '{args.target}' is not a Unity BuildTarget enum name. Use one of StandaloneOSX, "
                    + "StandaloneWindows64, StandaloneLinux64, Android, iOS, WebGL. Nothing was compiled.");
            }

            XUUnityLightMcpEditorBusyGuard.ThrowIfBusy("unity.compile.player_scripts");

            if (EditorUtility.scriptCompilationFailed)
            {
                throw new InvalidOperationException("Unity has compilation errors. Resolve them before running compile validation.");
            }

            var payload = new XUUnityLightMcpCompileConfigPayload
            {
                name = string.IsNullOrWhiteSpace(args.name) ? target.ToString() : args.name.Trim(),
                target = target.ToString(),
                target_group = ConvertToBuildTargetGroup(target).ToString(),
                target_supported = IsBuildTargetSupported(target),
                option_flags = NormalizeStrings(args.optionFlags),
                extra_defines = NormalizeStrings(args.extraDefines)
            };

            if (!payload.target_supported)
            {
                payload.status = "target_support_missing";
                return payload;
            }

            var outputDirectory = BuildOutputDirectory(payload.name, target);
            payload.output_directory = outputDirectory;

            var compilationSettings = new ScriptCompilationSettings
            {
                target = target,
                group = ConvertToBuildTargetGroup(target),
                options = ParseOptions(payload.option_flags),
                extraScriptingDefines = payload.extra_defines.ToArray()
            };

            var stopwatch = Stopwatch.StartNew();
            var errors = new List<XUUnityLightMcpCompileErrorItem>();
            var uniqueWarnings = new List<XUUnityLightMcpCompileErrorItem>();
            var uniqueWarningKeys = new HashSet<string>(StringComparer.Ordinal);
            var warningCount = 0;
            var rebuiltAssemblies = new HashSet<string>(StringComparer.Ordinal);
            var cachedAssemblies = new HashSet<string>(StringComparer.Ordinal);

            void HandleAssemblyCompilationStarted(string assemblyName)
            {
                RecordAssemblyExecution(assemblyName, rebuiltAssemblies, cachedAssemblies, rebuilt: true);
            }

#if UNITY_2022_1_OR_NEWER
            void HandleAssemblyCompilationNotRequired(string assemblyName)
            {
                RecordAssemblyExecution(assemblyName, rebuiltAssemblies, cachedAssemblies, rebuilt: false);
            }
#endif

            void HandleAssemblyCompilationFinished(string assemblyName, CompilerMessage[] compilerMessages)
            {
                CollectCompilerMessages(
                    assemblyName,
                    compilerMessages,
                    errors,
                    uniqueWarnings,
                    uniqueWarningKeys,
                    ref warningCount);
            }

            try
            {
                CompilationPipeline.assemblyCompilationStarted -= HandleAssemblyCompilationStarted;
                CompilationPipeline.assemblyCompilationStarted += HandleAssemblyCompilationStarted;
#if UNITY_2022_1_OR_NEWER
                CompilationPipeline.assemblyCompilationNotRequired -= HandleAssemblyCompilationNotRequired;
                CompilationPipeline.assemblyCompilationNotRequired += HandleAssemblyCompilationNotRequired;
#endif
                CompilationPipeline.assemblyCompilationFinished -= HandleAssemblyCompilationFinished;
                CompilationPipeline.assemblyCompilationFinished += HandleAssemblyCompilationFinished;
                var result = PlayerBuildInterface.CompilePlayerScripts(compilationSettings, outputDirectory);
                payload.compiled_assembly_count = result.assemblies?.Count ?? 0;
            }
            finally
            {
                CompilationPipeline.assemblyCompilationStarted -= HandleAssemblyCompilationStarted;
#if UNITY_2022_1_OR_NEWER
                CompilationPipeline.assemblyCompilationNotRequired -= HandleAssemblyCompilationNotRequired;
#endif
                CompilationPipeline.assemblyCompilationFinished -= HandleAssemblyCompilationFinished;
                stopwatch.Stop();
                EditorUtility.ClearProgressBar();
            }

            PopulateRebuildEvidence(payload, rebuiltAssemblies, cachedAssemblies);
            payload.duration_seconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
            payload.errors = errors;
            payload.error_count = errors.Count;
            payload.all_unique_warnings = uniqueWarnings;
            payload.warnings = uniqueWarnings.Take(WarningSampleLimit).ToList();
            payload.warning_count = warningCount;
            payload.unique_warning_count = uniqueWarnings.Count;
            payload.warning_sample_limit = WarningSampleLimit;
            payload.warnings_truncated = uniqueWarnings.Count > payload.warnings.Count;
            payload.status = errors.Count > 0 ? "failed" : "passed";
            return payload;
        }

        internal static void RecordAssemblyExecution(
            string assemblyName,
            HashSet<string> rebuiltAssemblies,
            HashSet<string> cachedAssemblies,
            bool rebuilt)
        {
            if (string.IsNullOrWhiteSpace(assemblyName))
            {
                return;
            }

            if (rebuilt)
            {
                rebuiltAssemblies.Add(assemblyName);
                cachedAssemblies.Remove(assemblyName);
                return;
            }

            if (!rebuiltAssemblies.Contains(assemblyName))
            {
                cachedAssemblies.Add(assemblyName);
            }
        }

        internal static void PopulateRebuildEvidence(
            XUUnityLightMcpCompileConfigPayload payload,
            HashSet<string> rebuiltAssemblies,
            HashSet<string> cachedAssemblies)
        {
            payload.rebuilt_assembly_count = rebuiltAssemblies?.Count ?? 0;
            payload.cached_assembly_count = cachedAssemblies?.Count ?? 0;
#if UNITY_2022_1_OR_NEWER
            payload.rebuild_evidence_status = "measured";
            payload.rebuild_evidence_basis = "compilation_pipeline_started_and_not_required_events";
#else
            payload.rebuild_evidence_status = "rebuilt_only_cache_status_unavailable";
            payload.rebuild_evidence_basis = "compilation_pipeline_started_event";
#endif
        }

        internal static void CollectCompilerMessages(
            string assemblyName,
            CompilerMessage[] compilerMessages,
            List<XUUnityLightMcpCompileErrorItem> errors,
            List<XUUnityLightMcpCompileErrorItem> uniqueWarnings,
            HashSet<string> uniqueWarningKeys,
            ref int warningCount)
        {
            if (compilerMessages == null)
            {
                return;
            }

            foreach (var message in compilerMessages)
            {
                var diagnostic = new XUUnityLightMcpCompileErrorItem
                {
                    assembly_name = assemblyName ?? "",
                    code = ExtractCompilerDiagnosticCode(message.message),
                    severity = message.type == CompilerMessageType.Warning ? "warning" : "error",
                    message = message.message ?? "",
                    file = message.file ?? "",
                    line = message.line,
                    column = message.column
                };

                if (message.type == CompilerMessageType.Error)
                {
                    errors.Add(diagnostic);
                    continue;
                }

                if (message.type != CompilerMessageType.Warning)
                {
                    continue;
                }

                warningCount++;
                if (uniqueWarningKeys.Add(WarningIdentity(diagnostic)))
                {
                    uniqueWarnings.Add(diagnostic);
                }
            }
        }

        internal static string ExtractCompilerDiagnosticCode(string message)
        {
            var text = message ?? "";
            for (var index = 0; index + 5 < text.Length; index++)
            {
                if (text[index] != 'C' || text[index + 1] != 'S')
                {
                    continue;
                }

                if (index > 0 && (char.IsLetterOrDigit(text[index - 1]) || text[index - 1] == '_'))
                {
                    continue;
                }

                var end = index + 2;
                while (end < text.Length && char.IsDigit(text[end]))
                {
                    end++;
                }

                if (end - index >= 6 && (end >= text.Length || !char.IsLetter(text[end])))
                {
                    return text.Substring(index, end - index);
                }
            }

            return "";
        }

        static string WarningIdentity(XUUnityLightMcpCompileErrorItem warning)
        {
            return string.Join(
                "\n",
                warning.assembly_name,
                warning.file,
                warning.line.ToString(),
                warning.column.ToString(),
                warning.code,
                warning.message);
        }

        internal static void PopulateMatrixWarningSummary(XUUnityLightMcpCompileMatrixPayload payload)
        {
            var uniqueWarnings = new List<XUUnityLightMcpCompileErrorItem>();
            var uniqueWarningKeys = new HashSet<string>(StringComparer.Ordinal);
            payload.warning_count = 0;
            foreach (var result in payload.results ?? new List<XUUnityLightMcpCompileConfigPayload>())
            {
                if (result == null)
                {
                    continue;
                }

                payload.warning_count += result.warning_count;
                var warnings = result.all_unique_warnings != null && result.all_unique_warnings.Count > 0
                    ? result.all_unique_warnings
                    : result.warnings;
                foreach (var warning in warnings ?? new List<XUUnityLightMcpCompileErrorItem>())
                {
                    if (warning == null)
                    {
                        continue;
                    }

                    if (uniqueWarningKeys.Add(WarningIdentity(warning)))
                    {
                        uniqueWarnings.Add(warning);
                    }
                }
            }

            payload.unique_warning_count = uniqueWarnings.Count;
            payload.warning_sample_limit = WarningSampleLimit;
            payload.warnings = uniqueWarnings.Take(WarningSampleLimit).ToList();
            payload.warnings_truncated = uniqueWarnings.Count > payload.warnings.Count;
        }

        internal static void PopulateMatrixRebuildEvidenceSummary(XUUnityLightMcpCompileMatrixPayload payload)
        {
            var results = payload.results ?? new List<XUUnityLightMcpCompileConfigPayload>();
            payload.rebuilt_assembly_count = results.Sum(result => result?.rebuilt_assembly_count ?? 0);
            payload.cached_assembly_count = results.Sum(result => result?.cached_assembly_count ?? 0);
            var measured = results.Count(result => result?.rebuild_evidence_status == "measured");
            var rebuiltOnly = results.Count(
                result => result?.rebuild_evidence_status == "rebuilt_only_cache_status_unavailable");
            payload.rebuild_evidence_status = results.Count == 0
                ? "not_run"
                : measured == results.Count
                    ? "measured"
                    : measured > 0
                        ? "partial"
                        : rebuiltOnly == results.Count
                            ? "rebuilt_only_cache_status_unavailable"
                            : "unmeasured";
            payload.rebuild_evidence_basis = measured > 0
                ? "per_configuration_compilation_pipeline_events"
                : rebuiltOnly > 0
                    ? "per_configuration_compilation_pipeline_started_event"
                    : "";
        }

        static List<string> NormalizeStrings(string[] values)
        {
            var result = new List<string>();
            if (values == null)
            {
                return result;
            }

            foreach (var value in values)
            {
                if (string.IsNullOrWhiteSpace(value))
                {
                    continue;
                }

                result.Add(value.Trim());
            }

            return result;
        }

        static ScriptCompilationOptions ParseOptions(List<string> optionFlags)
        {
            var options = ScriptCompilationOptions.None;
            if (optionFlags == null)
            {
                return options;
            }

            foreach (var optionFlag in optionFlags)
            {
                if (!Enum.TryParse(optionFlag, true, out ScriptCompilationOptions parsed))
                {
                    throw new InvalidOperationException($"Unknown ScriptCompilationOptions flag '{optionFlag}'.");
                }

                options |= parsed;
            }

            return options;
        }

        static string BuildOutputDirectory(string compileName, BuildTarget target)
        {
            var safeName = string.IsNullOrWhiteSpace(compileName) ? target.ToString() : compileName;
            foreach (var invalid in Path.GetInvalidFileNameChars())
            {
                safeName = safeName.Replace(invalid, '_');
            }

            var path = Path.Combine(
                XUUnityLightMcpFileIpcPaths.RootPath,
                "compile",
                $"{safeName}-{target}");

            if (Directory.Exists(path))
            {
                Directory.Delete(path, true);
            }

            Directory.CreateDirectory(path);
            return path;
        }

        static bool IsBuildTargetSupported(BuildTarget target)
        {
            try
            {
                var moduleManagerType = Type.GetType("UnityEditor.Modules.ModuleManager,UnityEditor.CoreModule");
                var method = moduleManagerType?.GetMethod(
                    "IsPlatformSupportLoadedByBuildTarget",
                    StaticBindings);
                if (method == null)
                {
                    return false;
                }

                return (bool)method.Invoke(null, new object[] { target });
            }
            catch
            {
                return false;
            }
        }

        static BuildTargetGroup ConvertToBuildTargetGroup(BuildTarget target)
        {
            switch (target)
            {
                case BuildTarget.Android:
                    return BuildTargetGroup.Android;
                case BuildTarget.iOS:
                    return BuildTargetGroup.iOS;
                case BuildTarget.WebGL:
                    return BuildTargetGroup.WebGL;
                case BuildTarget.StandaloneWindows:
                case BuildTarget.StandaloneWindows64:
                case BuildTarget.StandaloneLinux64:
                case BuildTarget.StandaloneOSX:
                    return BuildTargetGroup.Standalone;
                case BuildTarget.tvOS:
                    return BuildTargetGroup.tvOS;
                case BuildTarget.WSAPlayer:
                    return BuildTargetGroup.WSA;
                default:
                    return BuildTargetGroup.Unknown;
            }
        }
    }
}
