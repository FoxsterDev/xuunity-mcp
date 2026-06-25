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
    static class XUUnityLightMcpScenarioShared
    {
        public static IEnumerable<string> DependencyIds(XUUnityLightMcpScenarioStepDefinition step)
        {
            foreach (var dependency in step?.dependsOn ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(dependency))
                {
                    yield return dependency.Trim();
                }
            }

            foreach (var dependency in step?.runIfStepPassed ?? Array.Empty<string>())
            {
                if (!string.IsNullOrWhiteSpace(dependency))
                {
                    yield return dependency.Trim();
                }
            }
        }
        public static string FirstNonEmpty(params string[] values)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    return value;
                }
            }

            return "";
        }
        public static int GetTimeoutMs(XUUnityLightMcpScenarioStepDefinition step, double defaultSeconds)
        {
            return (int)Math.Round(GetTimeoutSeconds(step, defaultSeconds) * 1000.0d);
        }

        public static double GetTimeoutSeconds(XUUnityLightMcpScenarioStepDefinition step, double defaultSeconds)
        {
            return step.timeoutSeconds > 0.0d ? step.timeoutSeconds : defaultSeconds;
        }
        public static double CalculateDurationSeconds(string startedAtUtc, string completedAtUtc)
        {
            if (!TryParseUtc(startedAtUtc, out var started))
            {
                return 0.0d;
            }

            if (!TryParseUtc(completedAtUtc, out var completed))
            {
                completed = DateTime.UtcNow;
            }

            return Math.Round(Math.Max(0.0d, (completed - started).TotalSeconds), 6);
        }

        public static int CountSteps(List<XUUnityLightMcpScenarioStepResult> steps, string status)
        {
            var count = 0;
            foreach (var step in steps)
            {
                if (string.Equals(step.status, status, StringComparison.Ordinal))
                {
                    count++;
                }
            }
            return count;
        }
        public static string NormalizeScenarioName(string name)
        {
            var trimmed = (name ?? "").Trim();
            return string.IsNullOrWhiteSpace(trimmed) ? "unnamed_scenario" : trimmed;
        }

        public static string NormalizeStepId(XUUnityLightMcpScenarioStepDefinition step, int index)
        {
            var trimmed = (step.stepId ?? "").Trim();
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                trimmed = $"step_{index + 1}";
                step.stepId = trimmed;
            }

            return trimmed;
        }

        public static string NormalizeStepKind(XUUnityLightMcpScenarioStepDefinition step)
        {
            var kind = (step?.kind ?? "").Trim();
            if (string.IsNullOrWhiteSpace(kind))
            {
                kind = (step?.operation ?? "").Trim();
            }

            return kind.ToLowerInvariant();
        }

        public static string SanitizeFileName(string name)
        {
            var safe = NormalizeScenarioName(name);
            foreach (var invalid in Path.GetInvalidFileNameChars())
            {
                safe = safe.Replace(invalid, '_');
            }
            return safe.Replace(' ', '_');
        }

        public static bool IsPlayModeAction(string action)
        {
            var normalized = (action ?? "").Trim().ToLowerInvariant();
            return normalized == "enter" || normalized == "exit" || normalized == "pause" || normalized == "resume";
        }

        public static bool IsPlayModeState(string state)
        {
            var normalized = (state ?? "").Trim().ToLowerInvariant();
            return normalized == "edit" || normalized == "playing" || normalized == "paused" || normalized == "transitioning";
        }

        public static bool TryParseUtc(string value, out DateTime utc)
        {
            return DateTime.TryParse(
                value,
                null,
                System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                out utc);
        }
    }
}
