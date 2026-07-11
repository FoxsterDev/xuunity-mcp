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
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioShared;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioRunRepository
    {
        public static bool HasActiveRun()
        {
            return File.Exists(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath);
        }
        public static bool TryReadResult(string runId, string scenarioName, out XUUnityLightMcpScenarioRunPayload payload, out string errorCode, out string errorMessage)
        {
            XUUnityLightMcpFileIpcPaths.EnsureDirectories();
            payload = null;
            errorCode = "";
            errorMessage = "";

            if (!string.IsNullOrWhiteSpace(runId))
            {
                var path = FindResultPathByRunId(runId.Trim());
                if (path == null)
                {
                    errorCode = "scenario_run_not_found";
                    errorMessage = $"No scenario result found for runId '{runId}'.";
                    return false;
                }

                return TryReadPayload(path, out payload, out errorCode, out errorMessage);
            }

            if (!string.IsNullOrWhiteSpace(scenarioName))
            {
                var path = FindLatestResultPathByScenarioName(NormalizeScenarioName(scenarioName));
                if (path == null)
                {
                    errorCode = "scenario_result_not_found";
                    errorMessage = $"No scenario result found for scenario '{scenarioName}'.";
                    return false;
                }

                return TryReadPayload(path, out payload, out errorCode, out errorMessage);
            }

            var latest = FindLatestResultPath();
            if (latest == null)
            {
                errorCode = "scenario_result_not_found";
                errorMessage = "No scenario result files found.";
                return false;
            }

            return TryReadPayload(latest, out payload, out errorCode, out errorMessage);
        }

        public static void PersistResult(XUUnityLightMcpScenarioRunState state, string errorCode = "", string errorMessage = "")
        {
            var payload = BuildPayload(state);
            if (!string.IsNullOrWhiteSpace(errorCode))
            {
                payload.status = "failed";
                if (payload.steps.Count == 0)
                {
                    payload.steps.Add(new XUUnityLightMcpScenarioStepResult
                    {
                        stepId = "runner",
                        kind = "runner",
                        status = "failed",
                        error_code = errorCode,
                        error_message = errorMessage,
                    });
                }
            }

            XUUnityLightMcpAtomicFileWriter.WriteAllText(state.resultPath, JsonUtility.ToJson(payload, true));
        }

        public static XUUnityLightMcpScenarioRunPayload BuildPayload(XUUnityLightMcpScenarioRunState state)
        {
            var isTerminal = string.Equals(state.status, "passed", StringComparison.Ordinal)
                || string.Equals(state.status, "failed", StringComparison.Ordinal);

            var payload = new XUUnityLightMcpScenarioRunPayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                run_id = state.runId,
                scenario_name = NormalizeScenarioName(state.scenario?.name),
                status = state.status,
                terminal = isTerminal,
                succeeded = string.Equals(state.status, "passed", StringComparison.Ordinal),
                terminal_status = isTerminal ? state.status : "",
                started_at_utc = state.startedAtUtc,
                updated_at_utc = state.updatedAtUtc,
                completed_at_utc = state.completedAtUtc,
                result_path = state.resultPath,
                cleanup_start_index = state.cleanupStartIndex,
                total_steps = state.steps.Count,
                current_step_index = state.currentStepIndex,
                waiting_until_utc = state.waitingUntilUtc,
                steps = new List<XUUnityLightMcpScenarioStepResult>(state.steps),
                passed_steps = CountSteps(state.steps, "passed"),
                failed_steps = CountSteps(state.steps, "failed"),
                skipped_steps = CountSteps(state.steps, "skipped"),
                duration_seconds = CalculateDurationSeconds(state.startedAtUtc, string.IsNullOrWhiteSpace(state.completedAtUtc) ? state.updatedAtUtc : state.completedAtUtc),
            };

            return payload;
        }
        public static bool TryLoadState(out XUUnityLightMcpScenarioRunState state)
        {
            state = null;
            var path = XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath;
            if (!File.Exists(path))
            {
                return false;
            }

            var json = File.ReadAllText(path);
            state = JsonUtility.FromJson<XUUnityLightMcpScenarioRunState>(json);
            return state != null;
        }

        public static void SaveState(XUUnityLightMcpScenarioRunState state)
        {
            XUUnityLightMcpAtomicFileWriter.WriteAllText(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath, JsonUtility.ToJson(state, true));
        }

        public static void SafeDeleteActiveState()
        {
            try
            {
                if (File.Exists(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath))
                {
                    File.Delete(XUUnityLightMcpFileIpcPaths.ActiveScenarioRunPath);
                }
            }
            catch
            {
            }
        }
        public static string BuildResultPath(string runId, string scenarioName)
        {
            var timestamp = DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ");
            var safeName = SanitizeFileName(scenarioName);
            return Path.Combine(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory, $"{timestamp}_{runId}_{safeName}.json");
        }

        public static FileInfo FindResultPathByRunId(string runId)
        {
            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (file.Name.Contains(runId, StringComparison.OrdinalIgnoreCase))
                {
                    return file;
                }
            }

            return null;
        }

        public static FileInfo FindLatestResultPathByScenarioName(string scenarioName)
        {
            FileInfo latest = null;
            XUUnityLightMcpScenarioRunPayload latestPayload = null;

            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (!TryReadPayload(file, out var payload, out _, out _))
                {
                    continue;
                }

                if (!string.Equals(payload.scenario_name, scenarioName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (latest == null || file.LastWriteTimeUtc > latest.LastWriteTimeUtc)
                {
                    latest = file;
                    latestPayload = payload;
                }
            }

            return latestPayload != null ? latest : null;
        }

        public static FileInfo FindLatestResultPath()
        {
            FileInfo latest = null;
            var directory = new DirectoryInfo(XUUnityLightMcpFileIpcPaths.ScenarioResultsDirectory);
            foreach (var file in directory.GetFiles("*.json"))
            {
                if (latest == null || file.LastWriteTimeUtc > latest.LastWriteTimeUtc)
                {
                    latest = file;
                }
            }

            return latest;
        }

        public static bool TryReadPayload(FileInfo file, out XUUnityLightMcpScenarioRunPayload payload, out string errorCode, out string errorMessage)
        {
            payload = null;
            errorCode = "";
            errorMessage = "";

            try
            {
                var json = File.ReadAllText(file.FullName);
                payload = JsonUtility.FromJson<XUUnityLightMcpScenarioRunPayload>(json);
                if (payload == null)
                {
                    errorCode = "invalid_scenario_result";
                    errorMessage = $"Scenario result file is empty or invalid: {file.FullName}";
                    return false;
                }

                return true;
            }
            catch (Exception ex)
            {
                errorCode = "scenario_result_read_failed";
                errorMessage = ex.Message;
                return false;
            }
        }
    }
}
