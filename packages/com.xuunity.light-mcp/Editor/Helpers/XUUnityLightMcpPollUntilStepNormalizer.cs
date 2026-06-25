using System;

namespace XUUnity.LightMcp.Editor.Helpers
{
    static class XUUnityLightMcpPollUntilStepNormalizer
    {
        public static bool TryNormalizeStepArray(
            LightJsonNode scenario,
            string arrayKey,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (!scenario.TryGetArray(arrayKey, out var steps))
            {
                return true;
            }

            for (var i = 0; i < steps.Array.Count; i++)
            {
                var step = steps.Array[i];
                if (step.Kind != LightJsonKind.Object)
                {
                    continue;
                }

                var operation = step.GetString("kind");
                if (string.IsNullOrWhiteSpace(operation))
                {
                    operation = step.GetString("operation");
                    if (!string.IsNullOrWhiteSpace(operation))
                    {
                        step.Object["kind"] = LightJsonNode.String(operation);
                    }
                }

                if (!string.Equals(operation, "project_defined_hook_poll_until", StringComparison.Ordinal))
                {
                    continue;
                }

                if (!TryPromoteObjectPayloadToJsonString(step, "startPayload", "startPayloadJson", out errorCode, out errorMessage)
                    || !TryPromoteObjectPayloadToJsonString(step, "pollPayload", "pollPayloadJson", out errorCode, out errorMessage))
                {
                    return false;
                }
            }

            return true;
        }

        static bool TryPromoteObjectPayloadToJsonString(
            LightJsonNode step,
            string objectKey,
            string jsonKey,
            out string errorCode,
            out string errorMessage)
        {
            errorCode = "";
            errorMessage = "";

            if (step.Object.ContainsKey(jsonKey) || !step.Object.TryGetValue(objectKey, out var payload))
            {
                return true;
            }

            if (payload.Kind != LightJsonKind.Object)
            {
                errorCode = $"poll_until_{objectKey}_invalid";
                errorMessage = $"project_defined_hook_poll_until {objectKey} must be a JSON object.";
                return false;
            }

            step.Object[jsonKey] = LightJsonNode.String(payload.ToJson());
            step.Object.Remove(objectKey);
            return true;
        }
    }
}
