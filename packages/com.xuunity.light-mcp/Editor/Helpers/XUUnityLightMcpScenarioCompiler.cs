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
    static class XUUnityLightMcpScenarioCompiler
    {
        public static XUUnityLightMcpScenarioDefinition CloneScenarioWithExecutableSteps(
            XUUnityLightMcpScenarioDefinition scenario,
            out int cleanupStartIndex)
        {
            var steps = BuildExecutableSteps(scenario, out cleanupStartIndex);
            return new XUUnityLightMcpScenarioDefinition
            {
                name = scenario?.name ?? "",
                description = scenario?.description ?? "",
                stopOnFirstFailure = scenario?.stopOnFirstFailure ?? true,
                steps = steps,
                cleanupSteps = scenario?.cleanupSteps ?? new List<XUUnityLightMcpScenarioStepDefinition>(),
            };
        }

        public static List<XUUnityLightMcpScenarioStepDefinition> BuildExecutableSteps(
            XUUnityLightMcpScenarioDefinition scenario,
            out int cleanupStartIndex)
        {
            var bodySteps = scenario?.steps ?? new List<XUUnityLightMcpScenarioStepDefinition>();
            var cleanupSteps = scenario?.cleanupSteps ?? new List<XUUnityLightMcpScenarioStepDefinition>();
            cleanupStartIndex = cleanupSteps.Count > 0 ? bodySteps.Count : -1;

            var result = new List<XUUnityLightMcpScenarioStepDefinition>(bodySteps.Count + cleanupSteps.Count);
            result.AddRange(bodySteps);
            result.AddRange(cleanupSteps);
            return result;
        }
    }
}
