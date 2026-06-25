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
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioBasicStepHandlers;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioCompileTestStepHandlers;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioProjectHookStepHandlers;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioRefreshStepHandler;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpNestedOperationClient;
using static XUUnity.LightMcp.Editor.Helpers.XUUnityLightMcpScenarioHookExecutor;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioStepDispatcher
    {
        public static bool ProcessStep(XUUnityLightMcpScenarioRunState state, XUUnityLightMcpScenarioStepDefinition step, XUUnityLightMcpScenarioStepResult stepResult)
        {
            var kind = NormalizeStepKind(step);

            switch (kind)
            {
                case "wait":
                    return ProcessWaitStep(state, step, stepResult);
                case "wait_for_playmode_state":
                    return ProcessWaitForPlayModeStateStep(state, step, stepResult);
                case "assert_playmode_state":
                    return ProcessAssertPlayModeStateStep(step, stepResult);
                case "status":
                    return ProcessNestedOperationStep("unity.status", "{}", stepResult);
                case "health_probe":
                    return ProcessNestedOperationStep("unity.health.probe", "{}", stepResult);
                case "scene_snapshot":
                    return ProcessNestedOperationStep("unity.scene.snapshot", "{}", stepResult);
                case "assert_scene":
                    return ProcessAssertSceneStep(step, stepResult);
                case "project_refresh":
                    return ProcessProjectRefreshStep(state, step, stepResult);
                case "console_tail":
                    return ProcessConsoleTailStep(step, stepResult);
                case "console_grep":
                    return ProcessConsoleGrepStep(step, stepResult);
                case "playmode_set":
                    return ProcessPlayModeSetStep(step, stepResult);
                case "game_view_screenshot":
                    return ProcessGameViewScreenshotStep(step, stepResult);
                case "compile_player_scripts":
                    return ProcessCompilePlayerScriptsStep(state, step, stepResult);
                case "tests_run_editmode":
                    return ProcessEditModeTestsStep(state, step, stepResult);
                case "tests_run_playmode":
                    return ProcessPlayModeTestsStep(state, step, stepResult);
                case "game_view_configure":
                    return ProcessGameViewConfigureStep(step, stepResult);
                case "project_action":
                    return ProcessProjectActionStep(step, stepResult);
                case "project_defined_hook":
                    return ProcessProjectDefinedHookStep(step, stepResult);
                case "project_defined_hook_poll_until":
                    return ProcessProjectDefinedHookPollUntilStep(state, step, stepResult);
                default:
                    stepResult.status = "failed";
                    stepResult.error_code = "unsupported_scenario_step";
                    stepResult.error_message = $"Unsupported scenario step kind '{kind}'.";
                    return true;
            }
        }
    }
}
