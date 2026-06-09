using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpConsoleGrepOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.console.grep";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpConsoleGrepArgs()
                : JsonUtility.FromJson<XUUnityLightMcpConsoleGrepArgs>(request.args_json) ?? new XUUnityLightMcpConsoleGrepArgs();

            var pattern = (args.pattern ?? "").Trim();
            if (string.IsNullOrWhiteSpace(pattern))
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "missing_pattern",
                    "unity.console.grep requires a non-empty pattern.");
            }

            var limit = Math.Max(1, args.limit);
            var options = args.ignoreCase ? RegexOptions.IgnoreCase : RegexOptions.None;
            Regex compiledRegex = null;
            if (args.regex)
            {
                try
                {
                    compiledRegex = new Regex(pattern, options);
                }
                catch (ArgumentException ex)
                {
                    return XUUnityLightMcpResponseWriter.Error(
                        request.request_id,
                        "invalid_regex",
                        $"unity.console.grep regex pattern is invalid: {ex.Message}");
                }
            }

            var includeTypes = NormalizeIncludeTypes(args.includeTypes);
            var allItems = XUUnityLightMcpConsoleBuffer.Snapshot();
            var matches = allItems
                .Where(item => includeTypes.Contains(item.type))
                .Where(item => IsMatch(item, args, pattern, compiledRegex))
                .ToList();
            var matchCount = matches.Count;

            var truncated = matches.Count > limit;
            if (truncated)
            {
                matches = matches.Skip(matches.Count - limit).ToList();
            }

            if (!args.includeStackTraces)
            {
                matches = matches
                    .Select(item => new XUUnityLightMcpConsoleItem
                    {
                        type = item.type,
                        message = item.message,
                        timestamp = item.timestamp,
                        stack_trace = "",
                    })
                    .ToList();
            }

            var payload = new XUUnityLightMcpConsolePayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                pattern = pattern,
                regex = args.regex,
                ignore_case = args.ignoreCase,
                match_count = matchCount,
                items = matches,
                truncated = truncated
            };

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
        }

        static bool IsMatch(XUUnityLightMcpConsoleItem item, XUUnityLightMcpConsoleGrepArgs args, string pattern, Regex compiledRegex)
        {
            var haystack = args.includeStackTraces
                ? $"{item.message ?? ""}\n{item.stack_trace ?? ""}"
                : item.message ?? "";

            if (args.regex)
            {
                return compiledRegex != null && compiledRegex.IsMatch(haystack);
            }

            var comparison = args.ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            return haystack.IndexOf(pattern, comparison) >= 0;
        }

        static HashSet<string> NormalizeIncludeTypes(string[] includeTypes)
        {
            if (includeTypes == null || includeTypes.Length == 0)
            {
                return new HashSet<string>(new[] { "error", "warning", "log", "exception" }, StringComparer.OrdinalIgnoreCase);
            }

            return new HashSet<string>(includeTypes.Where(value => !string.IsNullOrWhiteSpace(value)), StringComparer.OrdinalIgnoreCase);
        }
    }
}
