using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpScenarioProjectActionNormalizer
    {
        public static bool TryNormalizeArgsJson(
            string argsJson,
            out string normalizedArgsJson,
            out string errorCode,
            out string errorMessage)
        {
            return TryNormalizeArgsJson(argsJson, "", out normalizedArgsJson, out errorCode, out errorMessage);
        }

        internal static bool TryNormalizeArgsJson(
            string argsJson,
            string explicitCatalogPath,
            out string normalizedArgsJson,
            out string errorCode,
            out string errorMessage)
        {
            return XUUnityLightMcpScenarioArgsNormalizer.TryNormalizeArgsJson(
                argsJson,
                explicitCatalogPath,
                out normalizedArgsJson,
                out errorCode,
                out errorMessage);
        }

        public static bool TryBuildExecutableProjectActionStep(
            XUUnityLightMcpScenarioStepDefinition step,
            out XUUnityLightMcpScenarioStepDefinition executableStep,
            out string errorCode,
            out string errorMessage)
        {
            return XUUnityLightMcpProjectActionStepBuilder.TryBuildExecutableProjectActionStep(
                step,
                out executableStep,
                out errorCode,
                out errorMessage);
        }
    }
}
