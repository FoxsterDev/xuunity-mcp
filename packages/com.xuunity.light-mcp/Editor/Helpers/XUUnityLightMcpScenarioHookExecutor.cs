using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Operations;
using XUUnity.LightMcp.Editor.ScenarioHooks;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioHookExecutor
    {
        public static XUUnityLightMcpScenarioHookResult ExecuteScenarioHook(
            IXUUnityLightMcpScenarioHook hook,
            string payloadJson,
            out double durationSeconds)
        {
            var stopwatch = Stopwatch.StartNew();
            var result = hook.Execute(string.IsNullOrWhiteSpace(payloadJson) ? "{}" : payloadJson);
            stopwatch.Stop();
            durationSeconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
            return result;
        }

        public static bool PredicateMatches(string expression, string payloadJson)
        {
            if (string.IsNullOrWhiteSpace(expression))
            {
                return false;
            }

            var match = Regex.Match(
                expression.Trim(),
                "^payload\\.([A-Za-z_][A-Za-z0-9_]*)\\s*==\\s*(['\"])(.*?)\\2$");
            if (!match.Success)
            {
                return false;
            }

            var actual = ExtractJsonScalar(payloadJson, match.Groups[1].Value);
            return string.Equals(actual, match.Groups[3].Value, StringComparison.Ordinal);
        }

        public static string ExtractJsonScalar(string payloadJson, string fieldName)
        {
            if (string.IsNullOrWhiteSpace(payloadJson) || string.IsNullOrWhiteSpace(fieldName))
            {
                return "";
            }

            var escapedField = Regex.Escape(fieldName);
            var match = Regex.Match(
                payloadJson,
                "\""
                + escapedField
                + "\"\\s*:\\s*(?:\"((?:\\\\.|[^\"\\\\])*)\"|([-+]?[0-9]+(?:\\.[0-9]+)?)|(true|false|null))",
                RegexOptions.IgnoreCase);
            if (!match.Success)
            {
                return "";
            }

            if (match.Groups[1].Success)
            {
                return Regex.Unescape(match.Groups[1].Value);
            }

            if (match.Groups[2].Success)
            {
                return match.Groups[2].Value;
            }

            return match.Groups[3].Value;
        }
        public static bool TryCreateScenarioHook(string hookName, out IXUUnityLightMcpScenarioHook hook, out string errorCode, out string errorMessage)
        {
            hook = null;
            errorCode = "";
            errorMessage = "";

            if (string.IsNullOrWhiteSpace(hookName))
            {
                errorCode = "missing_hook_name";
                errorMessage = "project_defined_hook step requires hookName.";
                return false;
            }

            var matches = new List<Type>();
            foreach (var type in TypeCache.GetTypesDerivedFrom<IXUUnityLightMcpScenarioHook>())
            {
                if (type == null || type.IsAbstract || type.IsInterface)
                {
                    continue;
                }

                if (Activator.CreateInstance(type) is not IXUUnityLightMcpScenarioHook candidate)
                {
                    continue;
                }

                if (string.Equals(candidate.HookName, hookName, StringComparison.OrdinalIgnoreCase))
                {
                    matches.Add(type);
                    hook ??= candidate;
                }
            }

            if (matches.Count == 1 && hook != null)
            {
                return true;
            }

            if (matches.Count > 1)
            {
                hook = null;
                errorCode = "duplicate_hook_name";
                errorMessage = $"Multiple scenario hooks registered as '{hookName}'.";
                return false;
            }

            errorCode = "hook_not_found";
            errorMessage = $"No scenario hook registered as '{hookName}'.";
            return false;
        }
        public static bool IsSupportedPayloadEqualityPredicate(string expression)
        {
            if (string.IsNullOrWhiteSpace(expression))
            {
                return false;
            }

            return Regex.IsMatch(
                expression.Trim(),
                "^payload\\.[A-Za-z_][A-Za-z0-9_]*\\s*==\\s*(['\"]).*?\\1$");
        }
    }
}
