using System;
using UnityEditor.PackageManager;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpInstallTestFrameworkOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.package.install_test_framework";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpInstallTestFrameworkArgs()
                : JsonUtility.FromJson<XUUnityLightMcpInstallTestFrameworkArgs>(request.args_json) ?? new XUUnityLightMcpInstallTestFrameworkArgs();

            if (!args.approve)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "approval_required",
                    "Installing Unity Test Framework mutates Packages/manifest.json and requires approve=true.");
            }

            var packageName = XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName;
            var recommendedVersion = XUUnityLightMcpCompatibilityPolicy.RecommendedTestFrameworkVersionForCurrentUnity();
            var requestedVersion = string.IsNullOrWhiteSpace(args.version) ? recommendedVersion : args.version.Trim();
            var minimumVersion = XUUnityLightMcpCompatibilityPolicy.TestFrameworkMinimumVersion;
            if (XUUnityLightMcpCompatibilityPolicy.CompareVersions(requestedVersion, minimumVersion) < 0)
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "dependency_version_too_old",
                    $"{packageName} {requestedVersion} is older than the minimum supported version {minimumVersion}.");
            }

            var installedBefore = XUUnityLightMcpCompatibilityPolicy.InstalledPackageVersion(packageName);
            var upgradeRecommendedBefore = !string.IsNullOrWhiteSpace(installedBefore)
                                           && XUUnityLightMcpCompatibilityPolicy.CompareVersions(installedBefore, recommendedVersion) < 0;
            var payload = new XUUnityLightMcpInstallTestFrameworkPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                unity_version = Application.unityVersion,
                dependency = packageName,
                requested_version = requestedVersion,
                minimum_dependency_version = minimumVersion,
                recommended_dependency_version = recommendedVersion,
                installed_dependency_version_before = installedBefore,
                upgrade_recommended_before = upgradeRecommendedBefore,
                requested_at_utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                next_action = "wait_for_package_resolve_then_request_health_probe",
            };

            if (!string.IsNullOrWhiteSpace(installedBefore)
                && XUUnityLightMcpCompatibilityPolicy.CompareVersions(installedBefore, requestedVersion) >= 0)
            {
                payload.outcome = "already_suitable";
                payload.installed_dependency_version_after = installedBefore;
                payload.recommended_action = upgradeRecommendedBefore
                    ? $"Optional upgrade remains available: {packageName} {recommendedVersion} is recommended for Unity {Application.unityVersion}."
                    : "";
                payload.next_action = "request_health_probe_or_validate_setup_include_tests";
                return XUUnityLightMcpResponseWriter.Success(
                    request.request_id,
                    OperationName,
                    JsonUtility.ToJson(payload));
            }

            XUUnityLightMcpBridgeRuntimeState.MarkPackageOperationStarted(
                $"package_add({packageName}@{requestedVersion})",
                "package_manager_add");
            Client.Add($"{packageName}@{requestedVersion}");
            payload.installed_dependency_version_after = requestedVersion;
            payload.outcome = string.IsNullOrWhiteSpace(installedBefore) ? "install_requested" : "upgrade_requested";
            payload.recommended_action = string.IsNullOrWhiteSpace(installedBefore)
                ? ""
                : $"Treat this as a Test Framework upgrade from {installedBefore} to {requestedVersion}; let Unity resolve packages and inspect compile/test results.";

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload));
        }
    }
}
