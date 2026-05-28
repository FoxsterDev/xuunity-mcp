using System.Collections.Generic;
using UnityEditor.Compilation;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Bridge
{
    internal static class XUUnityLightMcpCompilerDiagnostics
    {
        const int MaxRecentErrors = 20;
        static readonly object Gate = new();
        static readonly List<XUUnityLightMcpCompileErrorItem> RecentErrors = new();

        public static int ErrorCount
        {
            get
            {
                lock (Gate)
                {
                    return RecentErrors.Count;
                }
            }
        }

        public static string DiagnosticsSource
        {
            get
            {
                lock (Gate)
                {
                    return RecentErrors.Count > 0 ? "compilation_pipeline" : "";
                }
            }
        }

        public static void MarkCompilationStarted()
        {
            lock (Gate)
            {
                RecentErrors.Clear();
            }
        }

        public static void RecordAssemblyCompilationFinished(string assemblyName, CompilerMessage[] messages)
        {
            if (messages == null || messages.Length == 0)
            {
                return;
            }

            lock (Gate)
            {
                foreach (var message in messages)
                {
                    if (message.type != CompilerMessageType.Error)
                    {
                        continue;
                    }

                    if (RecentErrors.Count >= MaxRecentErrors)
                    {
                        RecentErrors.RemoveAt(0);
                    }

                    RecentErrors.Add(new XUUnityLightMcpCompileErrorItem
                    {
                        assembly_name = assemblyName ?? "",
                        message = message.message ?? "",
                        file = message.file ?? "",
                        line = message.line,
                        column = message.column
                    });
                }
            }
        }

        public static List<XUUnityLightMcpCompileErrorItem> Snapshot(int limit)
        {
            lock (Gate)
            {
                var effectiveLimit = limit <= 0 ? MaxRecentErrors : limit;
                var start = System.Math.Max(0, RecentErrors.Count - effectiveLimit);
                var result = new List<XUUnityLightMcpCompileErrorItem>();
                for (var i = start; i < RecentErrors.Count; i++)
                {
                    var item = RecentErrors[i];
                    result.Add(new XUUnityLightMcpCompileErrorItem
                    {
                        assembly_name = item.assembly_name,
                        message = item.message,
                        file = item.file,
                        line = item.line,
                        column = item.column
                    });
                }

                return result;
            }
        }
    }
}
