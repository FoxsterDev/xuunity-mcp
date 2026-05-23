using UnityEditor;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;

namespace XUUnity.LightMcp.Editor.TestFramework
{
    [InitializeOnLoad]
    internal static class XUUnityLightMcpTestFrameworkModule
    {
        static XUUnityLightMcpTestFrameworkModule()
        {
            XUUnityLightMcpOperationRegistry.Register(new XUUnityLightMcpEditModeTestsOperation());
            XUUnityLightMcpOperationRegistry.Register(new XUUnityLightMcpPlayModeTestsOperation());
            XUUnityLightMcpCapabilityRegistry.RegisterProvider(
                XUUnityLightMcpCapabilityRegistry.EditModeTestsCapability,
                BuildEditModeTestsCapability);
            XUUnityLightMcpCapabilityRegistry.RegisterProvider(
                XUUnityLightMcpCapabilityRegistry.PlayModeTestsCapability,
                BuildPlayModeTestsCapability);
        }

        static XUUnityLightMcpCapabilityRecord BuildEditModeTestsCapability()
        {
            return BuildTestsCapability(
                XUUnityLightMcpCapabilityRegistry.EditModeTestsCapability,
                "unity.tests.run_editmode");
        }

        static XUUnityLightMcpCapabilityRecord BuildPlayModeTestsCapability()
        {
            return BuildTestsCapability(
                XUUnityLightMcpCapabilityRegistry.PlayModeTestsCapability,
                "unity.tests.run_playmode");
        }

        static XUUnityLightMcpCapabilityRecord BuildTestsCapability(string capabilityId, string operationName)
        {
            var installedVersion = XUUnityLightMcpCompatibilityPolicy.InstalledPackageVersion(
                XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName);
            var recommendedVersion = XUUnityLightMcpCompatibilityPolicy.RecommendedTestFrameworkVersionForCurrentUnity();
            var upgradeRecommended = !string.IsNullOrWhiteSpace(installedVersion)
                                     && XUUnityLightMcpCompatibilityPolicy.CompareVersions(installedVersion, recommendedVersion) < 0;

            return new XUUnityLightMcpCapabilityRecord
            {
                capability_id = capabilityId,
                adapter_id = "unity_test_framework_v1",
                supported = true,
                status = "supported",
                reason = "",
                dependency = XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName,
                installed_dependency_version = installedVersion,
                minimum_dependency_version = XUUnityLightMcpCompatibilityPolicy.TestFrameworkMinimumVersion,
                recommended_dependency_version = recommendedVersion,
                recommendation_basis = "unity_version_policy",
                recommended_action = upgradeRecommended
                    ? $"Optionally upgrade {XUUnityLightMcpCompatibilityPolicy.TestFrameworkPackageName} from {installedVersion} to {recommendedVersion} for this Unity version after approval."
                    : "",
                upgrade_recommended = upgradeRecommended,
                operations = new System.Collections.Generic.List<string> { operationName }
            };
        }
    }
}
