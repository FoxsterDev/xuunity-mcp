using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.Build.Player;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpHealthProbe
    {
        const int ProbeVersion = 4;
        static readonly BindingFlags StaticBindings = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static;
        static XUUnityLightMcpCapabilitiesReport _cachedReport;

        public static XUUnityLightMcpCapabilitiesReport EnsureCurrentReport()
        {
            if (_cachedReport != null && IsCurrent(_cachedReport))
            {
                return _cachedReport;
            }

            var loaded = LoadReportFromDisk();
            if (loaded != null && IsCurrent(loaded))
            {
                _cachedReport = loaded;
                return loaded;
            }

            return RunProbeAndPersist();
        }

        public static XUUnityLightMcpCapabilitiesReport RunProbeAndPersist()
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();

            var capabilities = new List<XUUnityLightMcpCapabilityRecord>
            {
                BuildCoreCapability(),
                BuildBuildTargetCapability(),
                BuildEditModeTestsCapability(),
                BuildPlayModeTestsCapability(),
                BuildCompileCapability(),
                BuildBuildPlayerCapability(),
                BuildPlayModeCapability(),
                BuildGameViewCapability(),
                BuildSdkAndroidResolverCapability(),
                BuildUiReadCapability(),
                BuildPrefabMutationCapability(),
                BuildOptionalUguiCapability(
                    XUUnityLightMcpCapabilityRegistry.UiRenderCapability,
                    "unity.prefab.render",
                    "isolated prefab rendering"),
                BuildOptionalUguiCapability(
                    XUUnityLightMcpCapabilityRegistry.UiInteractionCapability,
                    "unity.ui.click",
                    "guarded semantic interaction")
            };

            var supportedOperations = new List<string>();
            var disabledOperations = new List<string>();

            foreach (var capability in capabilities)
            {
                if (capability.operations == null)
                {
                    continue;
                }

                if (capability.supported)
                {
                    supportedOperations.AddRange(capability.operations);
                }
                else
                {
                    disabledOperations.AddRange(capability.operations);
                }
            }

            supportedOperations.Sort(StringComparer.Ordinal);
            disabledOperations.Sort(StringComparer.Ordinal);

            var report = new XUUnityLightMcpCapabilitiesReport
            {
                probe_version = ProbeVersion,
                probe_bridge_generation = XUUnityLightMcpBridgeRuntimeState.BridgeGeneration,
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                unity_version = Application.unityVersion,
                active_build_target = EditorUserBuildSettings.activeBuildTarget.ToString(),
                checked_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                status = ResolveReportStatus(capabilities),
                supported_operations = supportedOperations,
                disabled_operations = disabledOperations,
                capabilities = capabilities
            };

            XUUnityLightMcpAtomicFileWriter.WriteAllText(XUUnityLightMcpFileIpcPaths.CapabilitiesReportPath, JsonUtility.ToJson(report, true));
            _cachedReport = report;
            return report;
        }

        public static bool IsOperationSupported(string operationName, out string reason)
        {
            reason = "";

            if (XUUnityLightMcpCapabilityRegistry.IsUngated(operationName))
            {
                return true;
            }

            if (!XUUnityLightMcpCapabilityRegistry.TryGetRequiredCapability(operationName, out var capabilityId))
            {
                return true;
            }

            var report = EnsureCurrentReport();
            foreach (var capability in report.capabilities)
            {
                if (!string.Equals(capability.capability_id, capabilityId, StringComparison.Ordinal))
                {
                    continue;
                }

                if (capability.supported)
                {
                    return true;
                }

                reason = string.IsNullOrWhiteSpace(capability.reason)
                    ? $"Capability '{capabilityId}' is not supported in Unity {Application.unityVersion}."
                    : capability.reason;
                if (!string.IsNullOrWhiteSpace(capability.recommended_action))
                {
                    reason = $"{reason} Recommended action: {capability.recommended_action}";
                }
                return false;
            }

            reason = $"Capability '{capabilityId}' is not registered.";
            return false;
        }

        static XUUnityLightMcpCapabilitiesReport LoadReportFromDisk()
        {
            try
            {
                if (!File.Exists(XUUnityLightMcpFileIpcPaths.CapabilitiesReportPath))
                {
                    return null;
                }

                var json = File.ReadAllText(XUUnityLightMcpFileIpcPaths.CapabilitiesReportPath);
                return JsonUtility.FromJson<XUUnityLightMcpCapabilitiesReport>(json);
            }
            catch
            {
                return null;
            }
        }

        static bool IsCurrent(XUUnityLightMcpCapabilitiesReport report)
        {
            return report != null &&
                   report.probe_version == ProbeVersion &&
                   report.probe_bridge_generation == XUUnityLightMcpBridgeRuntimeState.BridgeGeneration &&
                   string.Equals(report.unity_version, Application.unityVersion, StringComparison.Ordinal) &&
                   string.Equals(report.project_root, XUUnityLightMcpFileIpcPaths.ProjectRootPath, StringComparison.Ordinal) &&
                   string.Equals(
                       report.active_build_target,
                       EditorUserBuildSettings.activeBuildTarget.ToString(),
                       StringComparison.Ordinal) &&
                   TestFrameworkDependencyStateMatches(report) &&
                   SdkAndroidResolverDependencyStateMatches(report) &&
                   UiReadBackendStateMatches(report);
        }

        static bool SdkAndroidResolverDependencyStateMatches(XUUnityLightMcpCapabilitiesReport report)
        {
            if (report.capabilities == null)
            {
                return false;
            }

            var adapterAvailable = XUUnityLightMcpEdm4uAdapter.TryDescribe(out _, out _);
            var androidSupportLoaded = XUUnityLightMcpBuildTargetGetOperation.IsPlatformSupportLoaded(BuildTarget.Android);
            var currentlySupported = adapterAvailable && androidSupportLoaded;
            foreach (var capability in report.capabilities)
            {
                if (capability != null
                    && string.Equals(
                        capability.capability_id,
                        XUUnityLightMcpCapabilityRegistry.SdkAndroidResolverCapability,
                        StringComparison.Ordinal))
                {
                    return capability.supported == currentlySupported;
                }
            }

            return false;
        }

        static bool UiReadBackendStateMatches(XUUnityLightMcpCapabilitiesReport report)
        {
            if (report.capabilities == null)
            {
                return false;
            }

            var expectedStatus = XUUnityLightMcpUiComponentReaderRegistry.HasReaders
                ? "supported"
                : "supported_partial";
            foreach (var capability in report.capabilities)
            {
                if (capability == null
                    || !string.Equals(
                        capability.capability_id,
                        XUUnityLightMcpCapabilityRegistry.UiReadCapability,
                        StringComparison.Ordinal))
                {
                    continue;
                }

                return string.Equals(capability.status, expectedStatus, StringComparison.Ordinal);
            }

            return false;
        }

        static bool TestFrameworkDependencyStateMatches(XUUnityLightMcpCapabilitiesReport report)
        {
            var currentVersion = XUUnityLightMcpCompatibilityPolicy.InstalledPackageVersion(
                XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName);
            var sawTestCapability = false;
            if (report.capabilities == null)
            {
                return false;
            }

            foreach (var capability in report.capabilities)
            {
                if (capability == null)
                {
                    continue;
                }

                if (!string.Equals(capability.capability_id, XUUnityLightMcpCapabilityRegistry.EditModeTestsCapability, StringComparison.Ordinal)
                    && !string.Equals(capability.capability_id, XUUnityLightMcpCapabilityRegistry.PlayModeTestsCapability, StringComparison.Ordinal))
                {
                    continue;
                }

                sawTestCapability = true;
                if (string.Equals(capability.status, "degraded", StringComparison.Ordinal)
                    || string.Equals(capability.status, "error", StringComparison.Ordinal))
                {
                    return false;
                }

                if (!string.Equals(capability.installed_dependency_version ?? "", currentVersion ?? "", StringComparison.Ordinal))
                {
                    return false;
                }
            }

            return sawTestCapability;
        }

        static XUUnityLightMcpCapabilityRecord BuildPrefabMutationCapability()
        {
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.PrefabMutationCapability,
                adapter_id = "unity_prefab_transaction_v1",
                supported = true,
                status = "supported",
                reason = "",
                recommended_action = "Preview every transaction before approving it; a failed operation discards the whole batch.",
                operations = new List<string> { "unity.prefab.mutate" }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildOptionalUguiCapability(
            string capabilityId,
            string operationName,
            string label)
        {
            var registered = XUUnityLightMcpCapabilityRegistry.BuildRegisteredCapabilityOrNull(capabilityId);
            if (registered != null)
            {
                return registered;
            }

            var installedVersion = XUUnityLightMcpCompatibilityPolicy.InstalledPackageVersion("com.unity.ugui");
            var declaredVersion = "";
            var manifestReadable = false;
            try
            {
                var manifestPath = Path.Combine(XUUnityLightMcpFileIpcPaths.ProjectRootPath, "Packages", "manifest.json");
                if (LightJsonNode.TryParse(File.ReadAllText(manifestPath), out var manifest, out _)
                    && manifest.TryGetObject("dependencies", out var dependencies))
                {
                    manifestReadable = true;
                    declaredVersion = dependencies.GetString("com.unity.ugui");
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            var dependencyPresent = !string.IsNullOrWhiteSpace(installedVersion) || !string.IsNullOrWhiteSpace(declaredVersion);
            var evidence = !string.IsNullOrWhiteSpace(declaredVersion)
                ? $"com.unity.ugui {declaredVersion} is declared in Packages/manifest.json"
                : $"com.unity.ugui {installedVersion} is installed";

            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = capabilityId,
                adapter_id = "unity_ugui_unavailable",
                supported = false,
                status = dependencyPresent ? "disabled_unregistered"
                    : manifestReadable ? "disabled_missing_dependency" : "disabled_dependency_unknown",
                reason = dependencyPresent
                    ? $"{evidence}, but the optional MCP uGUI assembly did not register in this domain; {label} is unavailable."
                    : manifestReadable
                        ? $"com.unity.ugui is not installed or declared, so {label} is unavailable."
                        : $"The optional MCP uGUI assembly did not register; dependency state could not be read for {label}.",
                dependency = "com.unity.ugui",
                installed_dependency_version = installedVersion,
                recommended_action = dependencyPresent || !manifestReadable
                    ? "Wait for package resolve/domain reload or inspect Unity compile errors and Packages/manifest.json."
                    : "Install com.unity.ugui so the optional uGUI module compiles.",
                operations = new List<string> { operationName }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildUiReadCapability()
        {
            var backends = XUUnityLightMcpUiComponentReaderRegistry.BackendIds();
            var hasReaders = backends.Count > 0;
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.UiReadCapability,
                adapter_id = "unity_ugui_read_v1",
                supported = true,
                status = hasReaders ? "supported" : "supported_partial",
                reason = hasReaders
                    ? ""
                    : "No uGUI component reader is registered; nodes report hierarchy, bounds, and canvas state only.",
                recommended_action = hasReaders
                    ? ""
                    : BuildOptionalUguiCapability(
                        XUUnityLightMcpCapabilityRegistry.UiReadCapability,
                        "unity.ui.tree_snapshot",
                        "uGUI component details").recommended_action,
                operations = new List<string>
                {
                    "unity.ui.tree_snapshot",
                    "unity.ui.query",
                    "unity.ui.exists",
                    "unity.ui.get_text",
                    "unity.ui.get_bounds"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildCoreCapability()
        {
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.CoreCapability,
                adapter_id = "unity_editor_builtin_v1",
                supported = true,
                status = "supported",
                reason = "",
                operations = new List<string>
                {
                    "unity.status",
                    "unity.editor.quit",
                    "unity.package.install_test_framework",
                    "unity.project.refresh",
                    XUUnityLightMcpProjectActionCurrencyOperation.RegisteredOperationName,
                    "unity.edm4u.resolve",
                    "unity.sdk.dependency.verify",
                    "unity.console.tail",
                    "unity.scene.snapshot",
                    "unity.scene.open",
                    "unity.scene.assert",
                    "unity.prefab.snapshot",
                    "unity.prefab.validate",
                    "unity.scenario.validate",
                    "unity.scenario.run",
                    "unity.scenario.result"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildEditModeTestsCapability()
        {
            return BuildTestFrameworkCapability(
                XUUnityLightMcpCapabilityRegistry.EditModeTestsCapability,
                "unity.tests.run_editmode",
                "EditMode");
        }

        static XUUnityLightMcpCapabilityRecord BuildPlayModeTestsCapability()
        {
            return BuildTestFrameworkCapability(
                XUUnityLightMcpCapabilityRegistry.PlayModeTestsCapability,
                "unity.tests.run_playmode",
                "PlayMode");
        }

        static XUUnityLightMcpCapabilityRecord BuildBuildTargetCapability()
        {
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.BuildTargetCapability,
                adapter_id = "editor_build_target_builtin_v1",
                supported = true,
                status = "supported",
                reason = "",
                operations = new List<string>
                {
                    "unity.build_target.get",
                    "unity.build_target.switch"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildCompileCapability()
        {
            var method = typeof(PlayerBuildInterface).GetMethod(
                "CompilePlayerScripts",
                StaticBindings,
                null,
                new[] { typeof(ScriptCompilationSettings), typeof(string) },
                null);

            var supported = method != null;
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.CompileCapability,
                adapter_id = "compile_player_scripts_v1",
                supported = supported,
                status = supported ? "supported" : "unsupported",
                reason = supported
                    ? ""
                    : "Unity PlayerBuildInterface.CompilePlayerScripts API is unavailable; compile validation operations are disabled.",
                operations = new List<string>
                {
                    "unity.compile.player_scripts",
                    "unity.compile.matrix"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildBuildPlayerCapability()
        {
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.BuildPlayerCapability,
                adapter_id = "build_player_pipeline_v1",
                supported = true,
                status = "supported",
                reason = "",
                operations = new List<string>
                {
                    "unity.build_player"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildPlayModeCapability()
        {
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.PlayModeCapability,
                adapter_id = "editor_playmode_builtin_v1",
                supported = true,
                status = "supported",
                reason = "",
                operations = new List<string>
                {
                    "unity.playmode.state",
                    "unity.playmode.set"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildGameViewCapability()
        {
            var probe = XUUnityLightMcpGameViewUtility.ProbeReflectionSurface();
            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.GameViewCapability,
                adapter_id = probe.adapter_id,
                supported = probe.supported,
                status = probe.supported ? "supported" : "unsupported",
                reason = probe.reason,
                operations = new List<string>
                {
                    "unity.game_view.configure",
                    "unity.game_view.screenshot"
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildSdkAndroidResolverCapability()
        {
            var adapterAvailable = XUUnityLightMcpEdm4uAdapter.TryDescribe(out var adapter, out var adapterReason);
            var androidSupportLoaded = XUUnityLightMcpBuildTargetGetOperation.IsPlatformSupportLoaded(BuildTarget.Android);
            var supported = adapterAvailable && androidSupportLoaded;
            var reason = "";
            var action = "";
            var dependency = "com.google.external-dependency-manager";
            if (!adapterAvailable)
            {
                reason = adapterReason;
                action = "Install or restore External Dependency Manager for Unity, then refresh the project.";
            }
            else if (!androidSupportLoaded)
            {
                reason = "Unity Android Build Support is not loaded.";
                action = "Install Android Build Support for this Unity editor version.";
                dependency = "Unity Android Build Support";
            }

            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = XUUnityLightMcpCapabilityRegistry.SdkAndroidResolverCapability,
                adapter_id = string.IsNullOrWhiteSpace(adapter) ? "edm4u_callback_v1" : adapter,
                supported = supported,
                status = supported ? "supported" : "disabled_missing_dependency",
                reason = reason,
                dependency = dependency,
                recommended_action = action,
                operations = new List<string>
                {
                    XUUnityLightMcpSdkAndroidResolveOperation.RegisteredOperationName
                }
            };
        }

        static XUUnityLightMcpCapabilityRecord BuildTestFrameworkCapability(string capabilityId, string operationName, string modeLabel)
        {
            var registered = XUUnityLightMcpCapabilityRegistry.BuildRegisteredCapabilityOrNull(capabilityId);
            if (registered != null)
            {
                return registered;
            }

            var packageName = XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName;
            var installedVersion = XUUnityLightMcpCompatibilityPolicy.InstalledPackageVersion(packageName);
            var recommendedVersion = XUUnityLightMcpCompatibilityPolicy.RecommendedTestFrameworkVersionForCurrentUnity();
            var minimumVersion = XUUnityLightMcpCompatibilityPolicy.TestFrameworkMinimumVersion;
            var status = "disabled_missing_dependency";
            var reason = $"Unity Test Framework is not installed; {modeLabel} test operations are disabled.";
            var action = $"Install {packageName} {recommendedVersion} for Unity {Application.unityVersion}.";

            if (!string.IsNullOrWhiteSpace(installedVersion))
            {
                if (!XUUnityLightMcpCompatibilityPolicy.IsVersionAtLeast(installedVersion, minimumVersion))
                {
                    status = "disabled_dependency_too_old";
                    reason = $"{packageName} {installedVersion} is older than the minimum supported version {minimumVersion}; {modeLabel} test operations are disabled.";
                    action = $"Upgrade {packageName} from {installedVersion} to {recommendedVersion} for Unity {Application.unityVersion} after approval.";
                }
                else
                {
                    status = "degraded";
                    reason = $"{packageName} {installedVersion} is installed, but the optional MCP Test Framework assembly did not register. Wait for package resolve/domain reload or inspect Unity compile errors.";
                    action = "Run project refresh and inspect Unity compile errors if the test capability remains unavailable.";
                }
            }

            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = capabilityId,
                adapter_id = "unity_test_framework_v1",
                supported = false,
                status = status,
                reason = reason,
                dependency = packageName,
                installed_dependency_version = installedVersion,
                minimum_dependency_version = minimumVersion,
                recommended_dependency_version = recommendedVersion,
                recommendation_basis = "unity_version_policy",
                recommended_action = action,
                operations = new List<string> { operationName }
            };
        }

        static string ResolveReportStatus(List<XUUnityLightMcpCapabilityRecord> capabilities)
        {
            foreach (var capability in capabilities)
            {
                if (capability == null || capability.supported)
                {
                    continue;
                }

                if (string.Equals(capability.status, "degraded", StringComparison.Ordinal)
                    || string.Equals(capability.status, "error", StringComparison.Ordinal))
                {
                    return "degraded";
                }
            }

            return "healthy";
        }
    }
}
