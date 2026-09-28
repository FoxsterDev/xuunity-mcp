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

            var excludePattern = (args.excludePattern ?? "").Trim();
            Regex compiledExclude = null;
            if (args.regex && excludePattern.Length > 0)
            {
                try
                {
                    compiledExclude = new Regex(excludePattern, options);
                }
                catch (ArgumentException ex)
                {
                    return XUUnityLightMcpResponseWriter.Error(
                        request.request_id,
                        "invalid_regex",
                        $"unity.console.grep excludePattern is invalid: {ex.Message}");
                }
            }

            var includeTypes = NormalizeIncludeTypes(args.includeTypes);
            var since = (args.since ?? "").Trim();
            XUUnityLightMcpConsoleSinceSnapshot sinceSnapshot = null;
            List<XUUnityLightMcpConsoleItem> allItems;
            if (since.Length == 0)
            {
                allItems = XUUnityLightMcpConsoleBuffer.Snapshot();
            }
            else if (string.Equals(since, XUUnityLightMcpConsoleBuffer.PlayModeStartAnchor, StringComparison.Ordinal))
            {
                sinceSnapshot = XUUnityLightMcpConsoleBuffer.SnapshotSincePlayModeStart();
                allItems = sinceSnapshot.Items;
            }
            else
            {
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "unsupported_console_anchor",
                    $"unity.console.grep source=console supports since=playmode_start only; since='{since}' needs source=editor_log.");
            }

            var candidates = allItems
                .Where(item => includeTypes.Contains(item.type))
                .Where(item => IsMatch(item, args, pattern, compiledRegex))
                .ToList();

            var excludedCount = 0;
            var buildPipelineSuppressedCount = 0;
            var matches = new List<XUUnityLightMcpConsoleItem>(candidates.Count);
            foreach (var item in candidates)
            {
                if (excludePattern.Length > 0 && IsExcluded(item, args, excludePattern, compiledExclude))
                {
                    excludedCount++;
                    continue;
                }

                if (!args.includeBuildPipelineNoise
                    && XUUnityLightMcpConsoleNoise.IsBuildPipelineProgress(item.message))
                {
                    buildPipelineSuppressedCount++;
                    continue;
                }

                matches.Add(item);
            }

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

            ResolveSearchVerdict(matchCount, sinceSnapshot, out var searchVerdict, out var searchVerdictReason);
            var payload = new XUUnityLightMcpConsoleGrepPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                pattern = pattern,
                exclude_pattern = excludePattern,
                regex = args.regex,
                ignore_case = args.ignoreCase,
                match_count = matchCount,
                excluded_count = excludedCount,
                build_pipeline_suppressed_count = buildPipelineSuppressedCount,
                items = matches,
                truncated = truncated,
                since = since,
                since_anchor_resolved = sinceSnapshot != null && sinceSnapshot.AnchorResolved,
                since_anchor_reason = sinceSnapshot?.AnchorReason ?? "",
                since_anchor_sequence = sinceSnapshot?.AnchorSequence ?? 0L,
                since_anchor_started_utc = sinceSnapshot?.AnchorStartedUtc ?? "",
                since_scope_complete = sinceSnapshot != null && sinceSnapshot.ScopeComplete,
                search_verdict = searchVerdict,
                search_verdict_reason = searchVerdictReason
            };

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
        }

        static void ResolveSearchVerdict(
            int matchCount,
            XUUnityLightMcpConsoleSinceSnapshot sinceSnapshot,
            out string verdict,
            out string reason)
        {
            if (matchCount > 0)
            {
                verdict = "matched";
                reason = "pattern_found_in_console_buffer";
                return;
            }

            verdict = "inconclusive";
            if (sinceSnapshot == null)
            {
                reason = "unanchored_console_buffer_does_not_prove_absence";
                return;
            }

            if (!sinceSnapshot.AnchorResolved)
            {
                reason = "requested_anchor_not_recorded";
                return;
            }

            if (!sinceSnapshot.ScopeComplete)
            {
                reason = "console_ring_buffer_evicted_items_after_anchor";
                return;
            }

            verdict = "not_matched";
            reason = "complete_console_scope_since_anchor_searched";
        }

        static bool IsMatch(XUUnityLightMcpConsoleItem item, XUUnityLightMcpConsoleGrepArgs args, string pattern, Regex compiledRegex)
        {
            return Contains(Haystack(item, args), args, pattern, compiledRegex);
        }

        static bool IsExcluded(
            XUUnityLightMcpConsoleItem item,
            XUUnityLightMcpConsoleGrepArgs args,
            string excludePattern,
            Regex compiledExclude)
        {
            return Contains(Haystack(item, args), args, excludePattern, compiledExclude);
        }

        static string Haystack(XUUnityLightMcpConsoleItem item, XUUnityLightMcpConsoleGrepArgs args)
        {
            return args.includeStackTraces
                ? $"{item.message ?? ""}\n{item.stack_trace ?? ""}"
                : item.message ?? "";
        }

        static bool Contains(string haystack, XUUnityLightMcpConsoleGrepArgs args, string pattern, Regex compiledRegex)
        {
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
