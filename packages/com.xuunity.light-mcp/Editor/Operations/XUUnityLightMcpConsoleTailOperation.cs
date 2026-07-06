using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpConsoleTailOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.console.tail";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            var args = string.IsNullOrWhiteSpace(request.args_json)
                ? new XUUnityLightMcpConsoleTailArgs()
                : JsonUtility.FromJson<XUUnityLightMcpConsoleTailArgs>(request.args_json) ?? new XUUnityLightMcpConsoleTailArgs();

            var source = string.IsNullOrWhiteSpace(args.source) ? "console" : args.source.Trim();
            if (!string.Equals(source, "console", StringComparison.OrdinalIgnoreCase))
            {
                var message = "unity.console.tail in the Unity bridge reads only the in-memory Console buffer. "
                    + "Use the host tool with source=editor_log for Editor.log tail.";
                return XUUnityLightMcpResponseWriter.Error(
                    request.request_id,
                    "unsupported_console_tail_source",
                    message);
            }

            var limit = Math.Max(1, args.limit);
            var includeTypes = NormalizeIncludeTypes(args.includeTypes);

            var allItems = XUUnityLightMcpConsoleBuffer.Snapshot();
            var filtered = allItems.Where(item => includeTypes.Contains(item.type)).ToList();

            var truncated = filtered.Count > limit;
            if (filtered.Count > limit)
            {
                filtered = filtered.Skip(filtered.Count - limit).ToList();
            }

            var tailCaveat = "Unity Console tail reads the in-memory Console buffer, which may be stale "
                + "after clear-on-play or ring-buffer eviction; use source=editor_log for compile-error validation.";
            var payload = new XUUnityLightMcpConsolePayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                source = "console",
                items = filtered,
                truncated = truncated,
                result_trust_class = "console_buffer_may_be_stale",
                console_tail_caveat = tailCaveat,
                recommended_next_action = "use_source_editor_log_for_compile_errors"
            };

            return XUUnityLightMcpResponseWriter.Success(
                request.request_id,
                OperationName,
                JsonUtility.ToJson(payload)
            );
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
