using System;
using UnityEngine;
using XUUnity.LightMcp.Editor.Core;
using XUUnity.LightMcp.Editor.Helpers;

namespace XUUnity.LightMcp.Editor.Operations
{
    internal sealed class XUUnityLightMcpScenarioValidateOperation : IXUUnityLightMcpOperation
    {
        public string OperationName => "unity.scenario.validate";

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
                    ? new XUUnityLightMcpScenarioValidateArgs()
                    : JsonUtility.FromJson<XUUnityLightMcpScenarioValidateArgs>(argsJson) ?? new XUUnityLightMcpScenarioValidateArgs();

                var payload = XUUnityLightMcpScenarioRunner.Validate(args.scenario);
                return XUUnityLightMcpResponseWriter.Success(
                    request.request_id,
                    OperationName,
                    JsonUtility.ToJson(payload)
                );
            }
            catch (Exception ex)
            {
                return XUUnityLightMcpResponseWriter.Error(request.request_id, "scenario_validate_failed", ex.Message);
            }
        }
    }
}
