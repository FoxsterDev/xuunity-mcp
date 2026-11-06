using System;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpScenarioRunOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.scenario.run";

        public XUUnityLightMcpResponse Execute(XUUnityLightMcpRequest request)
        {
            try
            {
                if (!XUUnityLightMcpScenarioProjectActionNormalizer.TryNormalizeArgsJson(
                        request.args_json,
                        out var argsJson,
                        out var errorCode,
                        out var errorMessage))
                {
                    return XUUnityLightMcpResponseWriter.Error(request.request_id, errorCode, errorMessage);
                }

                var args = string.IsNullOrWhiteSpace(argsJson)
                    ? new XUUnityLightMcpScenarioRunArgs()
                    : JsonUtility.FromJson<XUUnityLightMcpScenarioRunArgs>(argsJson) ?? new XUUnityLightMcpScenarioRunArgs();

                var validation = XUUnityLightMcpScenarioRunner.Validate(args.scenario);
                if (validation.status != "valid")
                {
                    return XUUnityLightMcpResponseWriter.Error(
                        request.request_id,
                        "scenario_invalid",
                        BuildValidationErrorMessage(validation));
                }

                if (XUUnityLightMcpScenarioRunner.HasActiveRun())
                {
                    return XUUnityLightMcpResponseWriter.Error(
                        request.request_id,
                        "scenario_already_running",
                        "Another Unity scenario is already running. Read it with unity.scenario.result before starting a new one.");
                }

                var payload = XUUnityLightMcpScenarioRunner.QueueRun(args.scenario);
                return XUUnityLightMcpResponseWriter.Success(
                    request.request_id,
                    OperationName,
                    JsonUtility.ToJson(payload)
                );
            }
            catch (Exception ex)
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "scenario_run_failed", ex.Message);
            }
        }

        const int MaxListedValidationErrors = 8;

        public static string BuildValidationErrorMessage(XUUnityLightMcpScenarioValidatePayload validation)
        {
            var issues = validation?.issues;
            if (issues == null || issues.Count == 0)
            {
                return "Scenario validation failed with no issue details.";
            }

            var errors = issues.FindAll(issue => string.Equals(issue.severity, "error", StringComparison.Ordinal));
            if (errors.Count == 0)
            {
                errors = issues;
            }

            var listed = new System.Text.StringBuilder();
            var shown = Math.Min(errors.Count, MaxListedValidationErrors);
            for (var i = 0; i < shown; i++)
            {
                var issue = errors[i];
                listed.Append(i == 0 ? "" : "; ");
                if (!string.IsNullOrWhiteSpace(issue.stepId))
                {
                    listed.Append($"step '{issue.stepId}': ");
                }

                listed.Append($"{issue.code}: {issue.message}");
            }

            var remainder = errors.Count - shown;
            var remainderSummary = remainder > 0
                ? $" ({remainder} more; run unity.scenario.validate for the full list.)"
                : "";
            return $"Scenario validation failed with {errors.Count} error(s): {listed}{remainderSummary}";
        }
    }
}
