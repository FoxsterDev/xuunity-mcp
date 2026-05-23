using System;
using System.Collections;
using System.Reflection;
using System.Text.RegularExpressions;
using UnityEditor.PackageManager;
using UnityEngine;

namespace XUUnity.LightMcp.Editor.Core
{
    internal static class XUUnityLightMcpCompatibilityPolicy
    {
        static readonly BindingFlags StaticBindings = BindingFlags.Public | BindingFlags.Static;

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
                var packageInfo = FindPackageInfo(packageName);
                return packageInfo == null ? "" : packageInfo.version ?? "";
            }
            catch
            {
                return "";
            }
        }

        static PackageInfo FindPackageInfo(string packageName)
        {
            if (string.IsNullOrWhiteSpace(packageName))
            {
                return null;
            }

            var packageInfoType = typeof(PackageInfo);
            var findForPackageName = packageInfoType.GetMethod("FindForPackageName", StaticBindings);
            if (findForPackageName != null)
            {
                return findForPackageName.Invoke(null, new object[] { packageName }) as PackageInfo;
            }

            var getAllRegisteredPackages = packageInfoType.GetMethod("GetAllRegisteredPackages", StaticBindings);
            if (getAllRegisteredPackages == null)
            {
                return null;
            }

            var packages = getAllRegisteredPackages.Invoke(null, null) as IEnumerable;
            if (packages == null)
            {
                return null;
            }

            foreach (var item in packages)
            {
                if (item is PackageInfo packageInfo && string.Equals(packageInfo.name, packageName, StringComparison.Ordinal))
                {
                    return packageInfo;
                }
            }

            return null;
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
