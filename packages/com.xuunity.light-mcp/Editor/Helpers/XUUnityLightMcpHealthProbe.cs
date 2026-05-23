using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.Build.Player;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpHealthProbe
    {
        const int ProbeVersion = 1;
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
                BuildPlayModeCapability(),
                BuildGameViewCapability()
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
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                unity_version = Application.unityVersion,
                checked_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                status = ResolveReportStatus(capabilities),
                supported_operations = supportedOperations,
                disabled_operations = disabledOperations,
                capabilities = capabilities
            };

            File.WriteAllText(XUUnityLightMcpFileIpcPaths.CapabilitiesReportPath, JsonUtility.ToJson(report, true));
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
                   string.Equals(report.unity_version, Application.unityVersion, StringComparison.Ordinal) &&
                   string.Equals(report.project_root, XUUnityLightMcpFileIpcPaths.ProjectRootPath, StringComparison.Ordinal) &&
                   TestFrameworkDependencyStateMatches(report);
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
                    "unity.edm4u.resolve",
                    "unity.sdk.dependency.verify",
                    "unity.console.tail",
                    "unity.scene.snapshot",
                    "unity.scene.assert",
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
