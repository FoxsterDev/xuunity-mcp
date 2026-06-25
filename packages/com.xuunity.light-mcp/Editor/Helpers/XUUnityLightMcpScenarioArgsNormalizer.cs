using System;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpScenarioArgsNormalizer
    {
        public static bool TryNormalizeArgsJson(
            string argsJson,
            string explicitCatalogPath,
            out string normalizedArgsJson,
            out string errorCode,
            out string errorMessage)
        {
            normalizedArgsJson = argsJson;
            errorCode = "";
            errorMessage = "";

            if (string.IsNullOrWhiteSpace(argsJson))
            {
                return true;
            }

            if (!LightJsonNode.TryParse(argsJson, out var root, out errorMessage) || root.Kind != LightJsonKind.Object)
            {
                errorCode = "scenario_args_json_invalid";
                return false;
            }

            if (!root.TryGetObject("scenario", out var scenario))
            {
                return true;
            }

            var catalogPath = !string.IsNullOrWhiteSpace(explicitCatalogPath)
                ? explicitCatalogPath
                : root.GetString("catalogPath");

            if (!TryNormalizeScenario(scenario, catalogPath, out errorCode, out errorMessage))
            {
                return false;
            }

            normalizedArgsJson = root.ToJson();
            return true;
        }

        public static bool TryNormalizeScenario(LightJsonNode scenario, string catalogPath, out string errorCode, out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (!XUUnityLightMcpPollUntilStepNormalizer.TryNormalizeStepArray(scenario, "steps", out errorCode, out errorMessage)
                || !XUUnityLightMcpPollUntilStepNormalizer.TryNormalizeStepArray(scenario, "cleanupSteps", out errorCode, out errorMessage))
            {
                return false;
            }

            var hasProjectAction = HasProjectActionSteps(scenario);
            if (!hasProjectAction)
            {
                return true;
            }

            if (!ProjectActionCatalogLoader.TryLoad(catalogPath, out var catalog, out errorCode, out errorMessage))
            {
                return false;
            }

            return XUUnityLightMcpProjectActionStepBuilder.TryNormalizeStepArray(scenario, "steps", catalog, out errorCode, out errorMessage)
                && XUUnityLightMcpProjectActionStepBuilder.TryNormalizeStepArray(scenario, "cleanupSteps", catalog, out errorCode, out errorMessage);
        }

        public static bool HasProjectActionSteps(LightJsonNode scenario)
        {
            return HasProjectActionSteps(scenario, "steps") || HasProjectActionSteps(scenario, "cleanupSteps");
        }

        public static bool HasProjectActionSteps(LightJsonNode scenario, string arrayKey)
        {
            if (!scenario.TryGetArray(arrayKey, out var steps))
            {
                return false;
            }

            foreach (var step in steps.Array)
            {
                if (step.Kind == LightJsonKind.Object
                    && string.Equals(step.GetString("kind"), "project_action", StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }
    }
}
