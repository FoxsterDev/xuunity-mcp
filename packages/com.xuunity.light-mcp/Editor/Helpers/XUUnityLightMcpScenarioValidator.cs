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
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioCompiler;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioHookExecutor;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioValidator
    {
        public static XUUnityLightMcpScenarioValidatePayload Validate(XUUnityLightMcpScenarioDefinition scenario)
        {
            var payload = new XUUnityLightMcpScenarioValidatePayload
            {
                project_root = XUUnityLightMcpFileIpcPaths.ProjectRootPath,
                scenario_name = NormalizeScenarioName(scenario?.name),
            };

            var steps = BuildExecutableSteps(scenario, out var cleanupStartIndex);
            payload.total_steps = steps.Count;

            if (string.IsNullOrWhiteSpace(scenario?.name))
            {
                AddIssue(payload, "error", "missing_name", "Scenario name is required.", "", -1);
            }

            if ((scenario?.steps ?? new List<XUUnityLightMcpScenarioStepDefinition>()).Count == 0)
            {
                AddIssue(payload, "error", "missing_steps", "Scenario must contain at least one step.", "", -1);
            }

            var seenStepIds = new HashSet<string>(StringComparer.Ordinal);
            for (var i = 0; i < steps.Count; i++)
            {
                var step = steps[i] ?? new XUUnityLightMcpScenarioStepDefinition();
                var stepId = NormalizeStepId(step, i);
                payload.steps.Add(new XUUnityLightMcpScenarioStepSummary
                {
                    stepId = stepId,
                    kind = NormalizeStepKind(step),
                });

                if (!seenStepIds.Add(stepId))
                {
                    AddIssue(payload, "error", "duplicate_step_id", $"Duplicate stepId '{stepId}'.", stepId, i);
                }

                ValidateStepDependencies(payload, step, stepId, i, seenStepIds);
                ValidateStep(payload, step, stepId, i);
            }

            payload.status = payload.error_count > 0 ? "invalid" : "valid";
            return payload;
        }
        public static void ValidateStep(XUUnityLightMcpScenarioValidatePayload payload, XUUnityLightMcpScenarioStepDefinition step, string stepId, int index)
        {
            var kind = NormalizeStepKind(step);
            if (string.IsNullOrWhiteSpace(kind))
            {
                AddIssue(payload, "error", "missing_kind", "Scenario step kind or operation is required.", stepId, index);
                return;
            }

            switch (kind)
            {
                case "status":
                case "health_probe":
                case "scene_snapshot":
                case "project_refresh":
                    break;
                case "assert_scene":
                    if (string.IsNullOrWhiteSpace(step.expectedName)
                        && string.IsNullOrWhiteSpace(step.expectedPath)
                        && (step.requiredRootNames == null || step.requiredRootNames.Length == 0)
                        && step.allowDirty)
                    {
                        AddIssue(payload, "error", "missing_scene_expectation",
                            "assert_scene requires expectedName, expectedPath, requiredRootNames, or allowDirty=false.",
                            stepId, index);
                    }
                    break;
                case "console_tail":
                    if (step.limit < 0)
                    {
                        AddIssue(payload, "error", "invalid_limit", "console_tail step requires limit >= 0; omit it or use 0 for the default.", stepId, index);
                    }
                    break;
                case "console_grep":
                    if (string.IsNullOrWhiteSpace(step.pattern))
                    {
                        AddIssue(payload, "error", "missing_pattern", "console_grep step requires pattern.", stepId, index);
                    }
                    if (step.limit < 0)
                    {
                        AddIssue(payload, "error", "invalid_limit", "console_grep step requires limit >= 0; omit it or use 0 for the default.", stepId, index);
                    }
                    break;
                case "playmode_set":
                    if (!IsPlayModeAction(step.action))
                    {
                        AddIssue(payload, "error", "invalid_action",
                            "playmode_set step requires action: enter, exit, pause, or resume.", stepId, index);
                    }
                    break;
                case "wait":
                    if (step.durationSeconds < 0.0d)
                    {
                        AddIssue(payload, "error", "invalid_duration", "wait step requires durationSeconds >= 0.", stepId, index);
                    }
                    break;
                case "wait_for_playmode_state":
                    if (!IsPlayModeState(step.expectedPlaymodeState))
                    {
                        AddIssue(payload, "error", "invalid_expected_playmode_state",
                            "wait_for_playmode_state requires expectedPlaymodeState: edit, playing, paused, or transitioning.",
                            stepId, index);
                    }
                    if (step.timeoutSeconds <= 0.0d)
                    {
                        AddIssue(payload, "error", "invalid_timeout", "wait_for_playmode_state requires timeoutSeconds > 0.", stepId, index);
                    }
                    break;
                case "assert_playmode_state":
                    if (!IsPlayModeState(step.expectedPlaymodeState))
                    {
                        AddIssue(payload, "error", "invalid_expected_playmode_state",
                            "assert_playmode_state requires expectedPlaymodeState: edit, playing, paused, or transitioning.",
                            stepId, index);
                    }
                    break;
                case "game_view_screenshot":
                    if (step.maxResolution <= 0)
                    {
                        AddIssue(payload, "error", "invalid_max_resolution",
                            "game_view_screenshot requires maxResolution > 0.", stepId, index);
                    }
                    break;
                case "compile_player_scripts":
                    if (string.IsNullOrWhiteSpace(step.target))
                    {
                        AddIssue(payload, "error", "missing_target", "compile_player_scripts requires target.", stepId, index);
                    }
                    break;
                case "tests_run_editmode":
                case "tests_run_playmode":
                    break;
                case "game_view_configure":
                    if (step.width <= 0 || step.height <= 0)
                    {
                        AddIssue(payload, "error", "invalid_resolution",
                            "game_view_configure requires width > 0 and height > 0.", stepId, index);
                    }
                    break;
                case "project_action":
                    if (!XUUnityLightMcpScenarioProjectActionNormalizer.TryBuildExecutableProjectActionStep(
                            step,
                            out _,
                            out var actionErrorCode,
                            out var actionErrorMessage))
                    {
                        AddIssue(payload, "error", actionErrorCode, actionErrorMessage, stepId, index);
                    }
                    break;
                case "project_defined_hook":
                    if (string.IsNullOrWhiteSpace(step.hookName))
                    {
                        AddIssue(payload, "error", "missing_hook_name", "project_defined_hook requires hookName.", stepId, index);
                        break;
                    }

                    if (!TryCreateScenarioHook(step.hookName, out _, out var hookErrorCode, out var hookErrorMessage))
                    {
                        AddIssue(payload, "error", hookErrorCode, hookErrorMessage, stepId, index);
                    }
                    break;
                case "project_defined_hook_poll_until":
                    ValidateProjectDefinedHookPollUntilStep(payload, step, stepId, index);
                    break;
                default:
                    AddIssue(payload, "error", "unsupported_kind", $"Unsupported scenario step kind '{kind}'.", stepId, index);
                    break;
            }
        }

        public static void ValidateProjectDefinedHookPollUntilStep(
            XUUnityLightMcpScenarioValidatePayload payload,
            XUUnityLightMcpScenarioStepDefinition step,
            string stepId,
            int index)
        {
            if (string.IsNullOrWhiteSpace(step.hookName))
            {
                AddIssue(payload, "error", "missing_hook_name", "project_defined_hook_poll_until requires hookName.", stepId, index);
                return;
            }

            if (!TryCreateScenarioHook(step.hookName, out _, out var hookErrorCode, out var hookErrorMessage))
            {
                AddIssue(payload, "error", hookErrorCode, hookErrorMessage, stepId, index);
            }

            if (string.IsNullOrWhiteSpace(step.startPayloadJson))
            {
                AddIssue(payload, "error", "missing_start_payload", "project_defined_hook_poll_until requires startPayload or startPayloadJson.", stepId, index);
            }

            if (string.IsNullOrWhiteSpace(step.pollPayloadJson))
            {
                AddIssue(payload, "error", "missing_poll_payload", "project_defined_hook_poll_until requires pollPayload or pollPayloadJson.", stepId, index);
            }

            if (!IsSupportedPayloadEqualityPredicate(step.passWhen))
            {
                AddIssue(payload, "error", "invalid_pass_when", "project_defined_hook_poll_until passWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (!IsSupportedPayloadEqualityPredicate(step.failWhen))
            {
                AddIssue(payload, "error", "invalid_fail_when", "project_defined_hook_poll_until failWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (!string.IsNullOrWhiteSpace(step.continueWhen) && !IsSupportedPayloadEqualityPredicate(step.continueWhen))
            {
                AddIssue(payload, "error", "invalid_continue_when", "project_defined_hook_poll_until continueWhen must use payload.<field> == 'value'.", stepId, index);
            }

            if (step.intervalSeconds < 0.0d)
            {
                AddIssue(payload, "error", "invalid_interval", "project_defined_hook_poll_until requires intervalSeconds >= 0.", stepId, index);
            }

            if (step.timeoutSeconds <= 0.0d)
            {
                AddIssue(payload, "error", "invalid_timeout", "project_defined_hook_poll_until requires timeoutSeconds > 0.", stepId, index);
            }
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

        public static void ValidateStepDependencies(
            XUUnityLightMcpScenarioValidatePayload payload,
            XUUnityLightMcpScenarioStepDefinition step,
            string stepId,
            int index,
            HashSet<string> knownPreviousOrCurrentStepIds)
        {
            foreach (var dependency in DependencyIds(step))
            {
                if (string.Equals(dependency, stepId, StringComparison.Ordinal))
                {
                    AddIssue(payload, "error", "self_dependency",
                        $"Step '{stepId}' cannot depend on itself.", stepId, index);
                    continue;
                }

                if (!knownPreviousOrCurrentStepIds.Contains(dependency))
                {
                    AddIssue(payload, "error", "unknown_dependency",
                        $"Step '{stepId}' depends on unknown or later step '{dependency}'. Dependencies must reference earlier steps.",
                        stepId, index);
                }
            }
        }

        public static void AddIssue(XUUnityLightMcpScenarioValidatePayload payload, string severity, string code, string message, string stepId, int stepIndex)
        {
            payload.issues.Add(new XUUnityLightMcpScenarioIssue
            {
                severity = severity,
                code = code,
                message = message,
                stepId = stepId,
                stepIndex = stepIndex,
            });

            if (severity == "warning")
            {
                payload.warning_count++;
            }
            else
            {
                payload.error_count++;
            }
        }
    }
}
