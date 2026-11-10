using System;
using System.IO;
using UnityEngine;
using XUUnity.LightMcp.Editor.Bridge;
using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    [Serializable]
    internal sealed class XUUnityLightMcpCliTestProgressState
    {
        public string schema = XUUnityLightMcpCliTestProgress.Schema;
        public int process_id;
        public string test_platform = "";
        public string run_phase = "";
        public string started_at_utc = "";
        public string completed_at_utc = "";
        public string last_progress_at_utc = "";
        public int total;
        public int finished;
        public int passed;
        public int failed;
        public int skipped;
        public string last_started_test = "";
        public string last_started_at_utc = "";
        public string last_finished_test = "";
        public string last_finished_status = "";
        public string result_status = "";
        public int domain_reload_count;
    }

    internal static class XUUnityLightMcpCliTestProgress
    {
        internal const string Schema = "xuunity.cli_test_progress.v1";
        internal const string RunningPhase = "running";
        internal const string CompletedPhase = "completed";

        static XUUnityLightMcpCliTestProgressState _state;

        internal static string PathOverride;
        internal static Func<int> ProcessIdProvider = CurrentProcessId;

        static int CurrentProcessId()
        {
            using var process = System.Diagnostics.Process.GetCurrentProcess();
            return process.Id;
        }

        internal static string SidecarPath =>
            string.IsNullOrEmpty(PathOverride)
                ? Path.Combine(XUUnityLightMcpFileIpcPaths.StateDirectory, "cli_test_progress.json")
                : PathOverride;

        internal static XUUnityLightMcpCliTestProgressState Current => _state;

        internal static bool ShouldTrack(bool isBatchMode, string[] arguments)
        {
            if (!isBatchMode || arguments == null || XUUnityLightMcpBridgeProcessIdentity.CommandLineLooksLikeImportWorker(arguments))
            {
                return false;
            }

            foreach (var argument in arguments)
            {
                if (string.Equals(argument, "-runTests", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }

            return false;
        }

        internal static string ResolveTestPlatform(string[] arguments)
        {
            if (arguments != null)
            {
                for (var index = 0; index + 1 < arguments.Length; index += 1)
                {
                    if (string.Equals(arguments[index], "-testPlatform", StringComparison.OrdinalIgnoreCase))
                    {
                        return arguments[index + 1] ?? "";
                    }
                }
            }

            return "EditMode";
        }

        internal static XUUnityLightMcpCliTestProgressState ReplaceStateForTests(XUUnityLightMcpCliTestProgressState state)
        {
            var previous = _state;
            _state = state;
            return previous;
        }

        public static void RunStarted(int total, string testPlatform)
        {
            var now = UtcNow();
            _state = new XUUnityLightMcpCliTestProgressState
            {
                process_id = ProcessIdProvider(),
                test_platform = testPlatform ?? "",
                run_phase = RunningPhase,
                started_at_utc = now,
                last_progress_at_utc = now,
                total = Math.Max(0, total),
            };
            Write();
        }

        public static void TestStarted(string testName)
        {
            var state = EnsureState();
            var now = UtcNow();
            state.last_started_test = testName ?? "";
            state.last_started_at_utc = now;
            state.last_progress_at_utc = now;
            Write();
        }

        public static void TestFinished(string testName, string status)
        {
            var state = EnsureState();
            state.finished += 1;
            switch (status)
            {
                case "passed":
                    state.passed += 1;
                    break;
                case "failed":
                    state.failed += 1;
                    break;
                case "skipped":
                    state.skipped += 1;
                    break;
            }

            state.last_finished_test = testName ?? "";
            state.last_finished_status = status ?? "";
            state.last_progress_at_utc = UtcNow();
            Write();
        }

        public static void RunFinished(string resultStatus)
        {
            var state = EnsureState();
            var now = UtcNow();
            state.run_phase = CompletedPhase;
            state.result_status = resultStatus ?? "";
            state.completed_at_utc = now;
            state.last_progress_at_utc = now;
            Write();
        }

        static XUUnityLightMcpCliTestProgressState EnsureState()
        {
            if (_state != null)
            {
                return _state;
            }

            _state = TryLoadRunningForThisProcess() ?? new XUUnityLightMcpCliTestProgressState
            {
                process_id = ProcessIdProvider(),
                run_phase = RunningPhase,
                started_at_utc = UtcNow(),
            };
            return _state;
        }

        static XUUnityLightMcpCliTestProgressState TryLoadRunningForThisProcess()
        {
            try
            {
                if (!File.Exists(SidecarPath))
                {
                    return null;
                }

                var loaded = JsonUtility.FromJson<XUUnityLightMcpCliTestProgressState>(File.ReadAllText(SidecarPath));
                if (loaded == null
                    || loaded.process_id != ProcessIdProvider()
                    || !string.Equals(loaded.run_phase, RunningPhase, StringComparison.Ordinal))
                {
                    return null;
                }

                loaded.domain_reload_count += 1;
                return loaded;
            }
            catch
            {
                return null;
            }
        }

        static void Write()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(SidecarPath) ?? ".");
                XUUnityLightMcpAtomicFileWriter.WriteAllText(SidecarPath, JsonUtility.ToJson(_state, true));
            }
            catch
            {
            }
        }

        static string UtcNow()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        }
    }
}
