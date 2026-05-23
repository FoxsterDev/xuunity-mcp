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
    }
}
