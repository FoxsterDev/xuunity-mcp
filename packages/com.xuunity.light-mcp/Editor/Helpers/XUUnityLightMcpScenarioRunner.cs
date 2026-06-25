using XUUnity.LightMcp.Editor.Core;

namespace XUUnity.LightMcp.Editor.Helpers
{
    internal static class XUUnityLightMcpScenarioRunner
    {
        public static XUUnityLightMcpScenarioValidatePayload Validate(XUUnityLightMcpScenarioDefinition scenario)
        {
            return XUUnityLightMcpScenarioValidator.Validate(scenario);
        }

        public static bool HasActiveRun()
        {
            return XUUnityLightMcpScenarioRunRepository.HasActiveRun();
        }

        public static XUUnityLightMcpScenarioRunPayload QueueRun(XUUnityLightMcpScenarioDefinition scenario)
        {
            return XUUnityLightMcpScenarioScheduler.QueueRun(scenario);
        }

        public static void Tick()
        {
            XUUnityLightMcpScenarioScheduler.Tick();
        }

        public static bool TryReadResult(
            string runId,
            string scenarioName,
            out XUUnityLightMcpScenarioRunPayload payload,
            out string errorCode,
            out string errorMessage)
        {
            return XUUnityLightMcpScenarioRunRepository.TryReadResult(
                runId,
                scenarioName,
                out payload,
                out errorCode,
                out errorMessage);
        }
    }
}
