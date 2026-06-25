using System;
using System.Collections.Generic;

namespace XUUnity.LightMcp.Editor.Core
{
        [Serializable]
        internal sealed class XUUnityLightMcpScenarioDefinition
        {
            public string name = "";
            public string description = "";
            public bool stopOnFirstFailure = true;
            public List<XUUnityLightMcpScenarioStepDefinition> steps = new();
            public List<XUUnityLightMcpScenarioStepDefinition> cleanupSteps = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioStepDefinition
        {
            public string stepId = "";
            public string kind = "";
            public string operation = "";
            public string[] dependsOn = null;
            public string[] runIfStepPassed = null;
            public string action = "";
            public double durationSeconds;
            public double timeoutSeconds = 10.0d;
            public string expectedPlaymodeState = "";
            public string expectedName = "";
            public string expectedPath = "";
            public string[] requiredRootNames = null;
            public bool allowDirty = true;
            public int limit;
            public string pattern = "";
            public bool regex;
            public bool ignoreCase = true;
            public bool includeStackTraces;
            public string[] includeTypes = null;
            public string fileName = "";
            public bool includeImage;
            public int maxResolution = 640;
            public string target = "";
            public string[] optionFlags = null;
            public string[] extraDefines = null;
            public string[] testNames = null;
            public string[] groupNames = null;
            public string[] categoryNames = null;
            public string[] assemblyNames = null;
            public string name = "";
            public int width;
            public int height;
            public string group = "";
            public string label = "";
            public bool allowCreateCustomSize;
            public bool forceAssetRefresh = true;
            public bool resolvePackages = true;
            public bool rerunHealthProbe = true;
            public string hookName = "";
            public string hookPayloadJson = "";
            public string startPayloadJson = "";
            public string pollPayloadJson = "";
            public string passWhen = "";
            public string failWhen = "";
            public string continueWhen = "";
            public double intervalSeconds = 2.0d;
            public string[] promotePayloadFields = null;
            public bool terminalScreenshot;
            public bool terminalConsoleTail;
            public bool continueToCleanupOnFail;
            public string actionId = "";
            public string projectAction = "";
            public string payloadJson = "";
            public bool allowMutating;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioValidateArgs
        {
            public XUUnityLightMcpScenarioDefinition scenario = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioRunArgs
        {
            public XUUnityLightMcpScenarioDefinition scenario = new();
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioResultArgs
        {
            public string runId = "";
            public string scenarioName = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioIssue
        {
            public string severity = "error";
            public string code = "";
            public string message = "";
            public string stepId = "";
            public int stepIndex = -1;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioStepSummary
        {
            public string stepId = "";
            public string kind = "";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioValidatePayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string scenario_name = "";
            public string status = "invalid";
            public int total_steps;
            public int error_count;
            public int warning_count;
            public List<XUUnityLightMcpScenarioIssue> issues = new();
            public List<XUUnityLightMcpScenarioStepSummary> steps = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioStepResult
        {
            public string stepId = "";
            public string kind = "";
            public string status = "pending";
            public string outcome = "";
            public string hook_name = "";
            public string payload_json = "";
            public string terminal_status = "";
            public string failure_class = "";
            public int poll_count;
            public string[] promote_payload_fields = null;
            public string terminal_screenshot_payload_json = "";
            public string terminal_console_tail_payload_json = "";
            public string error_code = "";
            public string error_message = "";
            public double duration_seconds;
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioRunPayload
        {
            public string backend_id = "xuunity.light_unity_mcp";
            public string project_root = "";
            public string run_id = "";
            public string scenario_name = "";
            public string status = "queued";
            public bool terminal;
            public bool succeeded;
            public string terminal_status = "";
            public string started_at_utc = "";
            public string updated_at_utc = "";
            public string completed_at_utc = "";
            public string result_path = "";
            public int cleanup_start_index = -1;
            public int total_steps;
            public int passed_steps;
            public int failed_steps;
            public int skipped_steps;
            public int current_step_index = -1;
            public string waiting_until_utc = "";
            public double duration_seconds;
            public List<XUUnityLightMcpScenarioStepResult> steps = new();
            public string validation_evidence = "unity_mcp";
        }

        [Serializable]
        internal sealed class XUUnityLightMcpScenarioRunState
        {
            public string runId = "";
            public XUUnityLightMcpScenarioDefinition scenario = new();
            public string status = "queued";
            public string startedAtUtc = "";
            public string updatedAtUtc = "";
            public string completedAtUtc = "";
            public string resultPath = "";
            public int currentStepIndex;
            public int cleanupStartIndex = -1;
            public bool bodyFailed;
            public string waitingUntilUtc = "";
            public string pendingNestedRequestId = "";
            public string pendingNestedOperation = "";
            public string pendingNestedStartedAtUtc = "";
            public string pendingNestedResponseStatus = "";
            public string pendingNestedResponseCompletedAtUtc = "";
            public string pendingNestedResponsePayloadJson = "";
            public string pendingNestedResponseErrorCode = "";
            public string pendingNestedResponseErrorMessage = "";
            public int pendingNestedStableTickCount;
            public string pollUntilStartedAtUtc = "";
            public string pollUntilDeadlineUtc = "";
            public string pollUntilNextPollUtc = "";
            public int pollUntilPollCount;
            public List<XUUnityLightMcpScenarioStepResult> steps = new();
        }
}
