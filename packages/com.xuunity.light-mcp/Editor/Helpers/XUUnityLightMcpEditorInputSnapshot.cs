using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using UnityEditor;
using UnityEditor.Compilation;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal sealed class XUUnityLightMcpEditorInputComparison
    {
        public string state = "unavailable";
        public string basis_utc = "";
        public int input_count;
        public string newest_path = "";
        public string newest_write_utc = "";
        public int changed_count;
        public readonly List<string> changed_paths = new();
        public string error = "";

        public bool Ready => state == XUUnityLightMcpEditorInputSnapshot.StateReady;
        public bool ContentChanged => Ready && changed_count > 0;
    }

    [InitializeOnLoad]
    internal static class XUUnityLightMcpEditorInputSnapshot
    {
        internal const string StateReady = "ready";
        internal const string StatePending = "pending";
        internal const string StateFailed = "failed";
        internal const string StateUnavailable = "unavailable";
        const string CompileStartedSessionKey = "XUUnityLightMcp.EditorInputSnapshot.CompileStartedUtc";
        const int ChangedPathLimit = 8;
        const int PendingWaitMilliseconds = 3000;

        static readonly HashSet<string> EditorInputExtensions = new(StringComparer.OrdinalIgnoreCase)
        {
            ".cs",
            ".asmdef",
            ".asmref",
            ".rsp",
        };

        static readonly object Gate = new();
        static Snapshot Current;
        static Task<Snapshot> PendingBuild;

        internal sealed class Snapshot
        {
            public DateTime BasisUtc;
            public Dictionary<string, string> Hashes = new(StringComparer.Ordinal);
            public HashSet<string> DirtyAtCapture = new(StringComparer.Ordinal);
        }

        static XUUnityLightMcpEditorInputSnapshot()
        {
            if (XUUnityLightMcpBridgeProcessIdentity.ResolveCurrentProcessClass()
                == XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass)
            {
                return;
            }

            var basisUtc = ResolveDomainBasisUtc(SessionState.GetString(CompileStartedSessionKey, ""), DateTime.UtcNow);
            StartBuild(XUUnityLightMcpFileIpcPaths.ProjectRootPath, basisUtc);
            CompilationPipeline.compilationStarted += OnCompilationStarted;
            CompilationPipeline.compilationFinished += OnCompilationFinished;
        }

        internal static DateTime ResolveDomainBasisUtc(string compileStartedUtc, DateTime domainLoadedUtc)
        {
            if (DateTime.TryParse(
                    compileStartedUtc,
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal,
                    out var startedUtc)
                && startedUtc <= domainLoadedUtc)
            {
                return startedUtc;
            }

            return domainLoadedUtc;
        }

        static void OnCompilationStarted(object context)
        {
            SessionState.SetString(CompileStartedSessionKey, DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture));
        }

        static void OnCompilationFinished(object context)
        {
            var basisUtc = ResolveDomainBasisUtc(SessionState.GetString(CompileStartedSessionKey, ""), DateTime.UtcNow);
            StartBuild(XUUnityLightMcpFileIpcPaths.ProjectRootPath, basisUtc);
        }

        static void StartBuild(string projectRoot, DateTime basisUtc)
        {
            if (string.IsNullOrEmpty(projectRoot))
            {
                return;
            }

            lock (Gate)
            {
                PendingBuild = Task.Run(() => Build(projectRoot, basisUtc));
            }
        }

        static Snapshot Build(string projectRoot, DateTime basisUtc)
        {
            var snapshot = CaptureSnapshot(projectRoot, basisUtc);
            lock (Gate)
            {
                Current = snapshot;
            }

            return snapshot;
        }

        internal static Snapshot CaptureSnapshot(string projectRoot, DateTime basisUtc)
        {
            var snapshot = new Snapshot { BasisUtc = basisUtc };
            foreach (var path in EnumerateInputs(ResolveInputRoots(projectRoot)))
            {
                var relative = MakeRelative(projectRoot, path);
                try
                {
                    snapshot.Hashes[relative] = HashFile(path);
                    if (File.GetLastWriteTimeUtc(path) > basisUtc)
                    {
                        snapshot.DirtyAtCapture.Add(relative);
                    }
                }
                catch (IOException)
                {
                    snapshot.DirtyAtCapture.Add(relative);
                }
                catch (UnauthorizedAccessException)
                {
                    snapshot.DirtyAtCapture.Add(relative);
                }
            }

            return snapshot;
        }

        public static XUUnityLightMcpEditorInputComparison Compare(string projectRoot)
        {
            var result = new XUUnityLightMcpEditorInputComparison();
            Snapshot snapshot;
            Task<Snapshot> pending;
            lock (Gate)
            {
                snapshot = Current;
                pending = PendingBuild;
            }

            if (pending != null && !pending.IsCompleted)
            {
                try
                {
                    if (pending.Wait(PendingWaitMilliseconds))
                    {
                        snapshot = pending.Result;
                    }
                    else if (snapshot == null)
                    {
                        result.state = StatePending;
                    }
                }
                catch (AggregateException ex)
                {
                    result.state = StateFailed;
                    result.error = ex.InnerException?.GetType().Name ?? ex.GetType().Name;
                    return result;
                }
            }
            else if (pending != null && pending.IsFaulted)
            {
                result.state = StateFailed;
                result.error = pending.Exception?.InnerException?.GetType().Name ?? "snapshot_build_faulted";
                return result;
            }

            try
            {
                CompareWith(snapshot, projectRoot, result);
            }
            catch (Exception ex)
            {
                result.state = StateFailed;
                result.error = ex.GetType().Name;
            }

            return result;
        }

        internal static void CompareWith(Snapshot snapshot, string projectRoot, XUUnityLightMcpEditorInputComparison result)
        {
            var newestUtc = DateTime.MinValue;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var path in EnumerateInputs(ResolveInputRoots(projectRoot)))
            {
                result.input_count++;
                var relative = MakeRelative(projectRoot, path);
                var writeUtc = File.GetLastWriteTimeUtc(path);
                if (writeUtc > newestUtc)
                {
                    newestUtc = writeUtc;
                    result.newest_path = relative;
                }

                if (snapshot == null)
                {
                    continue;
                }

                seen.Add(relative);
                if (!snapshot.Hashes.TryGetValue(relative, out var compiledHash)
                    || snapshot.DirtyAtCapture.Contains(relative))
                {
                    AddChanged(result, relative);
                    continue;
                }

                if (writeUtc <= snapshot.BasisUtc)
                {
                    continue;
                }

                string currentHash;
                try
                {
                    currentHash = HashFile(path);
                }
                catch (IOException)
                {
                    AddChanged(result, relative);
                    continue;
                }

                if (!string.Equals(currentHash, compiledHash, StringComparison.Ordinal))
                {
                    AddChanged(result, relative);
                }
            }

            if (newestUtc != DateTime.MinValue)
            {
                result.newest_write_utc = newestUtc.ToString("O", CultureInfo.InvariantCulture);
            }

            if (snapshot == null)
            {
                if (result.state != StatePending)
                {
                    result.state = StateUnavailable;
                }

                return;
            }

            foreach (var compiledPath in snapshot.Hashes.Keys)
            {
                if (!seen.Contains(compiledPath))
                {
                    AddChanged(result, compiledPath);
                }
            }

            result.state = StateReady;
            result.basis_utc = snapshot.BasisUtc.ToString("O", CultureInfo.InvariantCulture);
        }

        static void AddChanged(XUUnityLightMcpEditorInputComparison result, string relative)
        {
            result.changed_count++;
            if (result.changed_paths.Count < ChangedPathLimit)
            {
                result.changed_paths.Add(relative);
            }
        }

        internal static List<string> ResolveInputRoots(string projectRoot)
        {
            var roots = new List<string>();
            if (string.IsNullOrEmpty(projectRoot))
            {
                return roots;
            }

            var assetsRoot = Path.Combine(projectRoot, "Assets");
            if (Directory.Exists(assetsRoot))
            {
                roots.Add(assetsRoot);
            }

            var packagesRoot = Path.Combine(projectRoot, "Packages");
            if (!Directory.Exists(packagesRoot))
            {
                return roots;
            }

            foreach (var directory in Directory.EnumerateDirectories(packagesRoot))
            {
                if (!XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName(Path.GetFileName(directory))
                    && File.Exists(Path.Combine(directory, "package.json")))
                {
                    AddRoot(roots, directory);
                }
            }

            foreach (var localPath in ReadLocalPackagePaths(Path.Combine(packagesRoot, "manifest.json")))
            {
                var resolved = Path.GetFullPath(Path.IsPathRooted(localPath) ? localPath : Path.Combine(packagesRoot, localPath));
                if (Directory.Exists(resolved) && File.Exists(Path.Combine(resolved, "package.json")))
                {
                    AddRoot(roots, resolved);
                }
            }

            return roots;
        }

        internal static List<string> ReadLocalPackagePaths(string manifestPath)
        {
            var paths = new List<string>();
            string text;
            try
            {
                text = File.Exists(manifestPath) ? File.ReadAllText(manifestPath) : "";
            }
            catch (IOException)
            {
                return paths;
            }

            const string marker = "\"file:";
            var index = 0;
            while ((index = text.IndexOf(marker, index, StringComparison.Ordinal)) >= 0)
            {
                var start = index + marker.Length;
                var end = text.IndexOf('"', start);
                if (end < 0)
                {
                    break;
                }

                var value = text.Substring(start, end - start).Replace("\\\\", "\\");
                if (!value.EndsWith(".tgz", StringComparison.OrdinalIgnoreCase)
                    && !value.EndsWith(".tar.gz", StringComparison.OrdinalIgnoreCase))
                {
                    paths.Add(value);
                }

                index = end + 1;
            }

            return paths;
        }

        static void AddRoot(List<string> roots, string root)
        {
            var full = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            foreach (var existing in roots)
            {
                if (string.Equals(
                        Path.GetFullPath(existing).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
                        full,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }
            }

            roots.Add(full);
        }

        internal static IEnumerable<string> EnumerateInputs(List<string> roots)
        {
            var pending = new Stack<string>();
            foreach (var root in roots)
            {
                pending.Push(root);
            }

            while (pending.Count > 0)
            {
                var directory = pending.Pop();
                IEnumerable<string> children;
                IEnumerable<string> files;
                try
                {
                    children = Directory.GetDirectories(directory);
                    files = Directory.GetFiles(directory);
                }
                catch (IOException)
                {
                    continue;
                }
                catch (UnauthorizedAccessException)
                {
                    continue;
                }

                foreach (var child in children)
                {
                    if (!XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName(Path.GetFileName(child)))
                    {
                        pending.Push(child);
                    }
                }

                foreach (var file in files)
                {
                    if (EditorInputExtensions.Contains(Path.GetExtension(file))
                        && !XUUnityLightMcpProjectActionCurrency.IsUnityIgnoredEntryName(Path.GetFileName(file)))
                    {
                        yield return file;
                    }
                }
            }
        }

        internal static string HashFile(string path)
        {
            const ulong offsetBasis = 14695981039346656037UL;
            const ulong prime = 1099511628211UL;
            var hash = offsetBasis;
            var buffer = new byte[64 * 1024];
            long length = 0;
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                int read;
                while ((read = stream.Read(buffer, 0, buffer.Length)) > 0)
                {
                    length += read;
                    for (var i = 0; i < read; i++)
                    {
                        hash ^= buffer[i];
                        hash *= prime;
                    }
                }
            }

            return length.ToString(CultureInfo.InvariantCulture) + ":" + hash.ToString("x16", CultureInfo.InvariantCulture);
        }

        static string MakeRelative(string projectRoot, string path)
        {
            var prefix = projectRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            var relative = path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ? path.Substring(prefix.Length) : path;
            return relative.Replace('\\', '/');
        }
    }
}
