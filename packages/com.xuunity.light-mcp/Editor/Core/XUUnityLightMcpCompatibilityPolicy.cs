using System;
using System.Text.RegularExpressions;
using UnityEditor.PackageManager;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.Core
{
    internal static class XUUnityLightMcpCompatibilityPolicy
    {
        public const string TestFrameworkPackageName = "com.unity.test-framework";
        public const string TestFrameworkMinimumVersion = "1.1.33";
        public const string TestFrameworkCapabilityDefine = "XUUNITY_LIGHT_MCP_TESTS_CAPABILITY";

        public static string RecommendedTestFrameworkVersionForCurrentUnity()
        {
            return RecommendedTestFrameworkVersionForUnity(Application.unityVersion);
        }

        public static string RecommendedTestFrameworkVersionForUnity(string unityVersion)
        {
            var major = ParseUnityMajor(unityVersion);
            return major >= 6000 ? "1.5.1" : "1.1.33";
        }

        public static string InstalledPackageVersion(string packageName)
        {
            try
            {
                var packageInfo = PackageInfo.FindForPackageName(packageName);
                return packageInfo == null ? "" : packageInfo.version ?? "";
            }
            catch
            {
                return "";
            }
        }

        public static bool IsVersionAtLeast(string installedVersion, string minimumVersion)
        {
            return CompareVersions(installedVersion, minimumVersion) >= 0;
        }

        public static int CompareVersions(string left, string right)
        {
            var leftParts = ParseVersionParts(left);
            var rightParts = ParseVersionParts(right);
            for (var i = 0; i < 3; i++)
            {
                if (leftParts[i] != rightParts[i])
                {
                    return leftParts[i].CompareTo(rightParts[i]);
                }
            }

            return 0;
        }

        static int ParseUnityMajor(string unityVersion)
        {
            var match = Regex.Match(unityVersion ?? "", @"^(\d+)");
            return match.Success && int.TryParse(match.Groups[1].Value, out var value) ? value : 0;
        }

        static int[] ParseVersionParts(string version)
        {
            var parts = new[] { 0, 0, 0 };
            var matches = Regex.Matches(version ?? "", @"\d+");
            for (var i = 0; i < Math.Min(3, matches.Count); i++)
            {
                int.TryParse(matches[i].Value, out parts[i]);
            }

            return parts;
        }
    }
}
