using System;
using System.Linq;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpTestArgsUtility
    {
        public static string BuildTestsArgsJson(XUUnityLightMcpScenarioStepDefinition step)
        {
            var args = new XUUnityLightMcpTestsArgs
            {
                testNames = NormalizeOptionalStringArray(step.testNames),
                groupNames = NormalizeOptionalStringArray(step.groupNames),
                categoryNames = NormalizeOptionalStringArray(step.categoryNames),
                assemblyNames = NormalizeOptionalStringArray(step.assemblyNames),
            };

            return args.testNames == null
                   && args.groupNames == null
                   && args.categoryNames == null
                   && args.assemblyNames == null
                ? "{}"
                : JsonUtility.ToJson(args);
        }

        public static string[] NormalizeOptionalStringArray(string[] values)
        {
            if (values == null || values.Length == 0)
            {
                return null;
            }

            var normalized = values
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.Ordinal)
                .ToArray();

            return normalized.Length == 0 ? null : normalized;
        }

        public static bool HasRequestedFilters(
            string[] testNames,
            string[] groupNames,
            string[] categoryNames,
            string[] assemblyNames)
        {
            return testNames != null && testNames.Length > 0
                   || groupNames != null && groupNames.Length > 0
                   || categoryNames != null && categoryNames.Length > 0
                   || assemblyNames != null && assemblyNames.Length > 0;
        }

        public static string BuildFilterSummary(
            string[] testNames,
            string[] groupNames,
            string[] categoryNames,
            string[] assemblyNames)
        {
            return string.Join(
                "; ",
                new[]
                {
                    $"tests={JoinOrAll(testNames)}",
                    $"groups={JoinOrAll(groupNames)}",
                    $"categories={JoinOrAll(categoryNames)}",
                    $"assemblies={JoinOrAll(assemblyNames)}",
                });
        }

        static string JoinOrAll(string[] values)
        {
            return values == null || values.Length == 0 ? "all" : string.Join(",", values);
        }
    }
}
